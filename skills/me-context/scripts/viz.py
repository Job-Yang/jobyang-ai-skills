#!/usr/bin/env python3
"""viz.py — 个人知识图谱（左·关系网导航 + 右·档案页，纯原生 HTML+CSS+JS，单文件自包含）。

节点 = Markdown 文件，边 = relations.md 的 10 词关系。Python 端 mectx_common 确定性解析、
按 audience/layers/分区 过滤、清洗模板占位后才序列化为 JSON 注入前端，前端只渲染。

CLI：--data（必填）；--view network|profile|all（默认 all）；--audience local|cloud（默认 local）；
--layers（仅 local 过滤分片+实体）；--show-l4（仅 local 展开 L4）；
--reveal-l3-entities（兼容旧参数，v10 人物节点照常显示，仅按分区过滤敏感内容）；
--out（默认 <数据仓>/exports/我的个人图谱.html）。
URL hash：#view=profile、#person=<entity_id>、#dim=<dimension_id>、#expand=all（可组合）；
id 白名单 [a-z0-9_-]+，非法忽略防注入。

隐私（Python 端过滤，不靠前端藏）：
- cloud：≥L3（L3/L4）分片正文字符串根本不进 HTML，只留锁块；实体按分区过滤，敏感分区
  （身体/病史/过敏/财务/共同计划/私密备注）剔除明文只留锁块，非敏感分区照常显示；
  标了 audience: local 的实体整人正文锁住，只留称呼和关系。
- L4 两种 audience 默认都不注入，仅 local+--show-l4 才展开并红警示；inbox 永不入数据。
- 坏头/缺层/缺分片/坏关系/幽灵边/空仓 fail-closed 跳过提示，不崩；symlink 不跟随。
"""
import argparse
import datetime
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mectx_common as C

SYMMETRIC = {"spouse_of", "partner_of", "sibling_of", "lives_with",
             "knows", "works_with", "related_to"}
DIRECTED = {"parent_of", "child_of"}
# 10 词 → 中文关系（页面可见标签，不暴露英文枚举）
REL_CN = {
    "spouse_of": "配偶", "partner_of": "伴侣", "sibling_of": "兄弟姐妹",
    "lives_with": "同住", "knows": "认识", "works_with": "同事",
    "related_to": "亲属", "parent_of": "父母", "child_of": "子女",
}
CIRCLE_COLOR = {"inner": "#4c6ef5", "close": "#7b61ff", "peripheral": "#adb5bd"}
CIRCLE_LABEL = {"inner": "核心圈 · 详写", "close": "重要圈 · 主要事实", "peripheral": "外围圈 · 梗概"}
LEVEL_CN = {"L0": "公开", "L1": "个人", "L2": "偏好", "L3": "敏感", "L4": "秘密"}

# 指标英文 code → 人话名（表格里不显示 ua/ldl_c 这种代号）
_ANALYTE_CN = {
    "systolic": "收缩压", "diastolic": "舒张压", "weight": "体重", "bmi": "BMI", "waist": "腰围",
    "ua": "尿酸", "tg": "甘油三酯", "tc": "总胆固醇", "ldl_c": "低密度脂蛋白 LDL-C",
    "hdl_c": "高密度脂蛋白 HDL-C", "fpg": "空腹血糖", "hba1c": "糖化血红蛋白",
    "alt": "谷丙转氨酶 ALT", "ast": "谷草转氨酶 AST",
    "creatinine": "肌酐", "egfr": "肾小球滤过率 eGFR", "ck": "肌酸激酶 CK",
    "urine_rbc": "尿红细胞", "urine_protein": "尿蛋白", "urine_occult": "尿隐血",
}

# 实体/分片内"敏感分区"标题关键词（cloud 只留锁块、剔除明文）
SENS_HEAD = ["身体", "健康", "病史", "用药", "过敏", "财务", "收入", "储蓄",
             "资产", "负债", "共同计划", "家庭计划", "备孕", "私密", "相处", "备注"]
# 条目级敏感键（即便落在非敏感分区也剔除）
SENS_KEY = ("过敏", "禁忌", "密码", "病史", "诊断", "用药", "财务", "收入",
            "储蓄", "相处", "私密", "备注")

# 模板占位/说明行判定（含这些就当未填，不显示）
_PLACEHOLDER_RES = [
    re.compile(r"^\s*>"),                                  # 引用块说明
    re.compile(r"<[^>]+>"),                                 # <先给结论>/<例>/<true/false>
    re.compile(r"例\s*[:：]|例如\s*[:：]"),
    re.compile(r"rational\s*/\s*intuitive\s*/\s*avoidant", re.I),  # 旧 GDMS 残留
    re.compile(r"profile\.risk\.opt_in"),                   # 配置项残留
    re.compile(r"[>]\s*$"),                                # 行尾半截 >
]

# 无尖括号的固定指南/使用说明行（非事实），整行丢弃，不当已记录条目
_GUIDE_RES = [
    re.compile(r"^\s*(永不记|只记|不记|请勿|不要记录|不要|别记|仅记录|只防)\b"),
    re.compile(r"用于.{0,12}不是"),
]


# ----------------------------- 隐私/读取助手（保留） -----------------------------
def _read(rel, data):
    """(layer, meta, ok, body)；缺文件/坏头 → ok=False，调用方占位不崩。"""
    p = C.safe_join(data, rel)
    if not p or not os.path.isfile(p) or os.path.islink(p):
        return None, {}, False, ""
    layer, meta, ok = C.file_layer(p)
    with open(p, encoding="utf-8") as f:
        body = f.read()
    return layer, (meta or {}), ok, body


def _layer_rank(layer):
    """L0→0 … L4→4；非法/空 → -1。"""
    if not layer or not re.fullmatch(r"L[0-4]", str(layer)):
        return -1
    return int(str(layer)[1])


def _cloud_locked(audience, layer, meta=None):
    """cloud 脱敏阈值：≥L3（L3/L4）一律锁，不输出正文字符串；local 不受此限。
    标了 audience: local 的低层文件按 L3 对待（与 gate/export 同一条：C.outgoing_layer）。"""
    return audience == "cloud" and _layer_rank(C.outgoing_layer(layer, meta)) >= 3


def _is_placeholder(line):
    s = line.strip()
    if not s:
        return True
    return any(rx.search(s) for rx in _PLACEHOLDER_RES)


def _is_guide_line(text):
    return any(rx.search(text or "") for rx in _GUIDE_RES)


def _filter_guide_items(items):
    """丢弃指南/使用说明条目（永不记/只记…），只留事实条目。"""
    kept = []
    for it in items:
        txt = it.get("v") or it.get("t") or ""
        if it.get("k") and _is_guide_line(it["k"]):
            continue
        if _is_guide_line(txt):
            continue
        kept.append(it)
    return kept


def _clean_inline(text):
    """清反引号；保留合法 **加粗** / 链接标记交前端 md() 渲染；转义交给前端。"""
    return text.replace("`", "").strip()


def _is_sens_head(heading):
    return any(k in (heading or "") for k in SENS_HEAD)


def _is_sens_key(k):
    return any(w in (k or "") for w in SENS_KEY)


_SENS_VAL = re.compile(r"过敏|禁忌|病史|诊断|用药|密码|备孕|坐骨|高血压|糖尿病|心脏病")


def _item_sensitive(it):
    """条目级敏感：键命中敏感词，或值本身含过敏/病史/密码等敏感事实。"""
    if _is_sens_key(it.get("k", "")):
        return True
    return bool(_SENS_VAL.search(it.get("v") or it.get("t") or ""))


# ----------------------------- 解析 -----------------------------
def _parse_blocks(body):
    """按 ## 小节切分 → [{heading, items:[{k,v} 或 {t}]}]；清洗占位/引用/注释/frontmatter。"""
    _, body = C.parse_frontmatter(body)
    body = C.strip_html_comments(body)
    blocks, cur = [], {"heading": "", "items": []}
    blocks.append(cur)
    for raw in body.splitlines():
        s = raw.strip()
        mh = re.match(r"^#{2,4}\s+(.*)", s)
        if mh:
            cur = {"heading": _clean_inline(mh.group(1)), "items": []}
            blocks.append(cur)
            continue
        if not s or s.startswith("#") or s == "---":
            continue
        mb = re.match(r"^-\s*(.+?)[：:]\s*(.+)", s)
        if mb and "**" not in mb.group(1):
            k, v = _clean_inline(mb.group(1)), _clean_inline(mb.group(2))
            if v and not _is_placeholder(v) and not _is_placeholder(k):
                cur["items"].append({"k": k, "v": v})
            continue
        if mb and "**" in mb.group(1):
            # 冒号前加粗（如「**刘铭儇**（男）：老羊的…」）是叙事句，整句按文本交给 md() 渲染，
            # 不能当「字段：值」（否则 **人名** 残留且冒号前半句被当字段重复）。
            t = _clean_inline(re.match(r"^-\s*(.+)", s).group(1))
            if t and not _is_placeholder(t):
                cur["items"].append({"t": t})
            continue
        mt = re.match(r"^(?:-\s+|\d+[.、]\s+)(.+)", s)
        if mt:
            t = _clean_inline(mt.group(1))
            if t and not _is_placeholder(t):
                cur["items"].append({"t": t})
            continue
        t = _clean_inline(s)
        if t and not _is_placeholder(t):
            cur["items"].append({"t": t})
    return [b for b in blocks if b["items"]]


def _first_han(name):
    """第一个汉字做头像；跳过括号/标点/英文/slug；取不到退回首字符。"""
    if not name:
        return "·"
    m = re.search(r"[\u4e00-\u9fff]", name)
    if m:
        return m.group(0)
    m = re.search(r"[A-Za-z0-9]", name)
    return m.group(0).upper() if m else "·"


# 称谓词（非真名），头像回退时跳过，避免"老婆"取成"老"
_TITLE_WORDS = ["老婆", "老公", "宝贝", "亲爱的", "爱人", "师傅", "老师", "医生",
                "护士", "朋友", "同事", "领导", "老板", "叔叔", "阿姨", "哥", "姐",
                "弟", "妹", "爸", "妈", "先生", "女士"]


def _extract_realname(bullets, label):
    """真名提取回退链：独立本名/姓名/真名 → 任意字段内嵌'本名 X' → 称呼分号后段 → 去称谓词首字。"""
    for k in ("本名", "姓名", "真名", "名字"):
        v = bullets.get(k)
        if v and not _is_placeholder(v):
            m = re.search(r"[一-龥A-Za-z·]+", v)
            if m:
                return m.group(0)
    for v in bullets.values():
        m = re.search(r"(?:本名|姓名|真名)\s*[：:]?\s*([一-龥A-Za-z·]{2,})", v or "")
        if m:
            return m.group(1)
    name = label or ""
    for seg in re.split(r"[；;、，,]", name):
        seg = seg.strip()
        if seg and not any(w in seg for w in _TITLE_WORDS):
            m = re.search(r"[一-龥]{2,}", seg)
            if m:
                return m.group(0)
    s = name
    for w in _TITLE_WORDS:
        s = s.replace(w, "")
    m = re.search(r"[一-龥A-Za-z]", s)
    return m.group(0) if m else (label or "")


def parse_relations(data):
    """解析 relations.md 边 → (edges, notes)。

    标准空仓（根本没有 relations.md）是正常空态，不报异常；
    仅文件存在但坏头/符号链接才进 notes（fail-closed，非静默归零）。
    """
    rel_path = C.safe_join(data, "relations.md")
    edges, notes, cur = [], [], {}
    if not rel_path or not os.path.exists(rel_path):
        return edges, []
    if os.path.islink(rel_path):
        return edges, ["relations.md 为符号链接，按 fail-closed 跳过（不跟随）"]
    layer, meta, ok, body = _read("relations.md", data)
    if not ok:
        return edges, ["relations.md 头部异常/缺层，按 fail-closed 跳过（非'没有关系'）"]
    body = C.strip_html_comments(body)  # 先剥 <!-- --> 模板示例注释，避免注释里的示例边变幽灵提示
    for raw in body.splitlines():
        s = raw.strip()
        mf = re.match(r"(?:-\s*)?from\s*:\s*(.+)", s)
        if mf:
            if cur:
                edges.append(cur)
            cur = {"from": mf.group(1).strip()}
            continue
        m = re.match(r"(?:-\s*)?(type|to|direction|since)\s*:\s*(.+)", s)
        if m and cur:
            cur[m.group(1)] = m.group(2).strip()
    if cur:
        edges.append(cur)
    return edges, notes


def load_entities_raw(data):
    """读原始实体（未脱敏）；{id:{circle,layer,meta,body,label}} + skipped。"""
    out, skipped = {}, []
    ent_dir = C.safe_join(data, "entities")
    if not ent_dir or not os.path.isdir(ent_dir):
        return out, skipped
    for fn in sorted(os.listdir(ent_dir)):
        if not fn.endswith(".md") or fn.startswith("_"):
            continue
        rel = f"entities/{fn}"
        layer, meta, ok, body = _read(rel, data)
        if not ok or layer is None:
            skipped.append(rel)
            continue
        eid = fn[:-3]
        b = dict((k, v) for k, v in _bullets(body))
        members = _entity_members(body)
        is_group = _is_group(meta, eid, members)
        raw_label = b.get("称呼") or b.get("本名") or b.get("是谁") or eid
        # 群组优先用成员中文名；任何实体都不把英文 slug 当显示名
        label = _entity_display(raw_label, members, eid, is_group) or \
            _extract_realname(b, raw_label) or "未命名"
        out[eid] = {"circle": meta.get("circle", "peripheral"), "layer": layer,
                    "meta": meta, "body": body, "label": label,
                    "is_group": is_group, "members": members}
    return out, skipped


def _bullets(body):
    body = C.strip_html_comments(body)
    out = []
    for raw in body.splitlines():
        s = raw.strip()
        m = re.match(r"-\s*(.+?)[：:]\s*(.+)", s)
        if m and "**" not in m.group(1):
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


# 群组类型（一个文件记多个人，如夫妇/父母）：网络节点应显示成员中文名，不显示英文 slug
_GROUP_TYPES = {"group", "couple", "family"}
# 文件名里带这些词，即便忘了标 type 也按群组兜底（父母/夫妇一家是天然多成员）
_GROUP_ID_HINT = ("parent", "couple", "family", "friends")


def _is_group(meta, eid, members=None):
    # 「## 成员」里有两个及以上真名 = 群组（哪怕 frontmatter 误标 person）
    if members and len(members) >= 2:
        return True
    t = (meta.get("type") or "").strip().lower()
    if t in _GROUP_TYPES:
        return True
    # 文件名前缀是我们自己的复数约定（parents/couple/family/friends），权威地表示群组
    return any(h in (eid or "").lower() for h in _GROUP_ID_HINT)


def _entity_members(body):
    """从「## 成员」分节解析成员名，如 **刘铭儇**（男）…。返回中文名有序列表。"""
    names = []
    m = re.search(r"^##\s*成员[^\n]*\n(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    seg = m.group(1) if m else ""
    for raw in seg.splitlines():
        mm = re.search(r"\*\*\s*([一-龥A-Za-z·]{2,})\s*\*\*", raw)
        if mm and mm.group(1) not in names:
            names.append(mm.group(1))
    return names


def _entity_display(label, members, eid, is_group):
    """网络节点中文显示名：群组→成员名（刘铭儇·吴雪婷）；否则去括号取称呼。
    任何情况下都不返回英文 slug（friends-liu-wu 之类）。"""
    if is_group:
        if members:
            return "·".join(members)
        # 群组但解析不到成员：用中文标题，不回退 slug
        return "家人" if any(h in (eid or "").lower() for h in ("parent", "family")) else "朋友"
    nm = re.split(r"[（(，,；;·]", label or "")[0].strip()
    if nm and not re.fullmatch(r"[a-z0-9_\\-]+", nm):
        return nm
    return ""  # 单人解析不到中文名 → 交由上层 realname 兜底，绝不显示 slug


def _group_short(label, members, eid):
    """群组节点圆下短名（≤4 字，有温度）：朋友夫妇→刘·吴夫妇；父母→父母。"""
    e = (eid or "").lower()
    if "parent" in e or "family" in e:
        return "父母"
    if members:
        ini = [_first_han(n) for n in members[:2]]
        return "·".join(ini) + "夫妇"
    return "好友"


def _me_header(data, audience):
    """ME 个人主页头；cloud ≥L3 锁、坏头 fail-closed。"""
    me_path = C.safe_join(data, "ME.md")
    if not me_path or not os.path.isfile(me_path) or os.path.islink(me_path):
        return {"name": "（未命名）"}, False
    me_layer, _m, ok = C.file_layer(me_path)
    with open(me_path, encoding="utf-8") as f:
        _, me_body = C.parse_frontmatter(f.read())
    if not ok:
        if audience == "cloud":
            return {"locked": True}, True
        return {"name": "（未命名）"}, False
    if _cloud_locked(audience, me_layer, _m):
        return {"locked": True}, True
    b = dict(_bullets(me_body))

    def _clean_field(v):
        """ME 名片字段过占位清洗：尖括号占位/引用说明/示例行视为未填。"""
        v = (v or "").strip()
        if not v or _is_placeholder(v):
            return ""
        v = re.sub(r"<[^>]*>", "", v).strip()
        return v.strip()

    raw_name = _clean_field(b.get("称呼")) or "（未命名）"
    # 称呼与本名拆开：老羊（本名杨权 / Job Yang）→ name=老羊，alt=杨权 / Job Yang
    alt = ""
    m = re.search(r"本名\s*([^（)）]+)", raw_name)
    if m:
        alt = m.group(1).strip()
    name = re.split(r"[（(]", raw_name)[0].strip() or "（未命名）"
    role = _clean_field(b.get("职业角色") or b.get("角色") or "")
    city = ""
    mz = re.search(r"常驻\s*([一-龥]+)", me_body)
    if mz:
        city = mz.group(1)
    else:
        for k in ("城市/时区", "城市"):
            cv = _clean_field(b.get(k) or "")
            if cv:
                city = re.split(r"[／/；;]", cv)[0]
                break
    lang = _clean_field(b.get("协作语言") or "")
    gender = _clean_field(b.get("性别/年龄段") or b.get("性别 / 年龄段") or "")
    # 自我标签：小节优先，兼容 bullet
    def _clean_tag(t):
        t = _clean_inline(t).lstrip(">- ").strip("、， ")
        if not t or _is_placeholder(t) or len(t) >= 30:
            return ""
        # 模板说明引用句（引导填写、非真实标签）一律丢弃
        if any(g in t for g in ("这是你自己给我的标签", "你自己给我的标签", "测评",
                                "随时可改", "对齐风格", "方便我", "可留空", "可只给")):
            return ""
        return t

    def _section_tags(blob):
        out = []
        for raw in blob.splitlines():
            s = raw.strip()
            if not s or s.startswith(">"):
                continue
            if _is_placeholder(s):  # 整行 <例：...>/引用块先丢，避免拆括号后漏网
                continue
            for t in re.split(r"[、，,·；;]", s):
                ct = _clean_tag(t)
                if ct:
                    out.append(ct)
        return out

    tags = []
    tb = re.search(r"自我标签[^\n]*\n?(.*?)(?:\n##|\Z)", me_body, re.S)
    if tb:
        tags = _section_tags(tb.group(1))
    if not tags:
        for k, v in b.items():
            if "自我标签" in k and v:
                tags = _section_tags(v)
                break
    # 公开链接：只收 http/https，其余协议丢弃；标签用域名
    links = []
    for u in re.findall(r"https?://[^\s｜|）)】\]<>]+", me_body):
        if u in [x["url"] for x in links]:
            continue
        host = re.sub(r"^https?://", "", u).split("/")[0]
        links.append({"url": u, "label": host})
    return {"name": name, "alt": alt, "role": role, "city": city,
            "lang": lang, "gender": gender, "tags": tags, "links": links}, False


def _item_text(it):
    if "v" in it:
        return f"{it['k']}：{it['v']}" if it.get("k") else it["v"]
    return it.get("t", "")


# 我的 6 个维度：(id, 展示名, 副标题, 源分片列表, kind 映射)
# kind: lead / timeline / chips / kv / list
DIMENSIONS = [
    ("identity", "身份", "称呼 · 出生 · 常驻 · 主页", ["__me__"], None),
    ("work", "事业", "在做的事 & 走过的路", ["profile/work.md"],
     {"一句话定位": "lead", "履历": "timeline", "核心能力": "list",
      "代表项目": "list", "做成过的事": "list", "AI 技能作品": "list",
      "作品": "list", "常用工具": "chips"}),
    ("goals", "方向", "想去的地方", ["profile/goals.md"], None),
    ("body", "身体", "身体和精力", ["profile/body.md"],
     {"身材": "kv", "作息": "chips", "作息与运动": "kv"}),
    ("life", "生活", "日子怎么过", ["profile/preferences.md"],
     {"生活": "chips", "爱好": "chips", "饮食": "chips", "口味": "chips"}),
    ("collab", "协作", "希望我怎么配合", ["profile/preferences.md", "profile/decisions.md"],
     {"沟通": "kv", "回答": "kv", "给建议": "kv", "格式": "kv",
      "我倾向": "kv", "拍板": "kv", "重要决定": "kv"}),
]
# 展示层温度标题映射（机器内部字段名/用户原文不动，仅前端换温度词，去"量化"硬词）
HEAD_RENAME = {
    "履历": "走过的路",
    "核心能力": "擅长的事",
    "代表项目": "做成过的事",
    "代表项目（量化）": "做成过的事",
}


def _display_heading(h):
    h = re.sub(r"（量化）", "", h or "").strip()
    return HEAD_RENAME.get(h, h)


# 独立敏感锁块（cloud 整块锁，local 明文）
LOCK_SLICES = [
    ("health", "健康", "过敏 · 在服药 · 关键指标时序", "profile/health.md"),
    ("finance", "财务", "只记区间，不记账户密钥", "profile/finance.md"),
]


def _slice_groups(rel, data, audience, layer_set, kind_map):
    """读分片 → {layer, ok, locked, empty, groups}；cloud ≥L3 整锁。"""
    layer, meta, ok, body = _read(rel, data)
    out = {"layer": layer or "?", "ok": ok}
    if not ok:
        out["empty"] = True
        return out
    if _cloud_locked(audience, layer, meta):
        out["locked"] = True
        return out
    if audience == "local" and layer_set and layer not in layer_set:
        out["empty"] = True
        return out
    blocks = _parse_blocks(body)
    groups = []
    for bk in blocks:
        kind = "list"
        if kind_map:
            for kw, kd in kind_map.items():
                if kw in bk["heading"]:
                    kind = kd
                    break
        items = _filter_guide_items(bk["items"])
        if not items:
            continue  # 整节只剩指南/示例 → 丢弃，不当已记录
        groups.append({"heading": _display_heading(bk["heading"]), "kind": kind,
                       "items": items})
    out["groups"] = groups
    out["empty"] = not groups
    # v11 过期轻提示：仅中性文案（天数+上次日期，无正文），不改锁、不改层、不泄露敏感细节
    st = C.freshness_status(meta, meta.get("domain"))
    if st and st["level"] == "archived":
        out["stale"] = "已归档"
    elif st and st["level"] == "stale":
        out["stale"] = f"可能过期（{st['age']} 天未更新，上次 {st['updated']}）"
    return out


DIM_INCLUDE = {
    "life": ["生活", "爱好", "饮食", "忌口", "口味", "节奏", "日子"],
    "collab": ["沟通", "回答", "给建议", "格式", "do-not", "我倾向", "拍板",
               "重要决定", "决策", "希望我怎么", "怎么工作"],
}


def _me_dimensions(data, audience, layer_set):
    dims = []
    for did, title, sub, rels, kind_map in DIMENSIONS:
        dim = {"id": did, "title": title, "sub": sub, "layer": "L1"}
        if did == "identity":
            dim["kind"] = "identity"
            dim["empty"] = False
            dims.append(dim)
            continue
        merged = {"groups": [], "locked": False, "empty": True, "stale": None}
        inc = DIM_INCLUDE.get(did)
        dim_layer = None
        for rel in rels:
            r = _slice_groups(rel, data, audience, layer_set, kind_map or {})
            if r.get("layer") and r["layer"] != "?":
                dim_layer = r["layer"]
            if r.get("stale") and not merged["stale"]:
                merged["stale"] = r["stale"]
            if r.get("locked"):
                merged["locked"] = True
            elif r.get("groups"):
                keep = r["groups"]
                if inc:
                    keep = [g for g in r["groups"]
                            if any(w in g["heading"] for w in inc) or not g["heading"]]
                merged["groups"].extend(keep)
                merged["empty"] = not keep
        if dim_layer:
            dim["layer"] = dim_layer
        dim.update(merged)
        if merged["stale"]:
            dim["sub"] = (dim.get("sub") or "") + " · " + merged["stale"]
        dims.append(dim)
    # 独立敏感锁块
    locked_blocks = []
    for lid, title, sub, rel in LOCK_SLICES:
        r = _slice_groups(rel, data, audience, layer_set, None)
        # v12 本地健康授权门（独立于 cloud L3 锁）：未授权/index_only 在 local 也不出结构化健康；
        # facts_only 只注入安全事实小节（过敏/在服药/忌口），剔除指标/结论/历史/里程碑/索引。
        consent_note = None
        if lid == "health":
            cc = C.parse_consent(data)
            if not cc["allowed"]:
                consent_note = "本地健康记录未开启或已撤回，不显示结构化健康（当轮就事问用药/急症可给安全必要信息，但不落盘）"
                r = {"locked": False, "empty": True, "layer": "L3"}
            elif cc["scope"] == "index_only":
                consent_note = "仅存体检原件本地索引，不展示指标/结论/趋势"
                r = {"locked": False, "empty": True, "layer": "L3"}
            elif cc["scope"] == "facts_only" and r.get("groups"):
                r["groups"] = [g for g in r["groups"]
                               if any(k in g.get("heading", "") for k in C.FACTS_SAFE_HEADINGS)]
                r["empty"] = not r["groups"]
        health_table = None
        health_summary = None
        health_milestones = None
        health_watchlist = None
        if lid == "health" and cc.get("allowed") and cc["scope"] == "full" \
                and not r.get("locked") and r.get("groups"):
            # full local：专门表格化最新关键指标 + 读时趋势/状态；跨院换单位显"仅供参考"不出箭头
            # 指标明细迁到过程层 journal/health-metrics.md 后，这里合并读，表格与趋势结果不变
            hbody = C.read_health_body(data)
            latest, hist = C.health_sections(hbody)
            # watchlist（关注因子）：只读 health.md + body.md 目标，绝不读 finance 等无关分片
            body_goal = ""
            bp = C.safe_join(data, "profile/body.md")
            if bp and os.path.isfile(bp):
                body_goal = open(bp, encoding="utf-8").read()
            watchlist = C.derive_watchlist(hbody, body_goal)
            watch_analytes = {w["analyte"] for w in watchlist if w["analyte"]}
            watch_reason = {w["analyte"]: w["reason"] for w in watchlist if w["analyte"]}
            # 历史按指标分组、从新到旧；比较基准=最近一次（不是文本里第一条）
            hby = C.history_by_analyte(hist)
            rows = []
            for cur in latest:
                past = hby.get(cur["name"], [])
                prev = past[0] if past else None
                label = C.trend_label(prev, cur)
                conf = C.trend_confidence(prev, cur)
                status = C.HR.status(cur)
                # 三档：所有明确异常/阳性/临界都固定呈现；待核对也不藏进“正常”折叠。
                if status in C.HR.ABNORMAL or status == "待核对":
                    tier = "fixed"
                elif cur["name"] in watch_analytes:
                    tier = "watched"
                else:
                    tier = "rest"
                rows.append({
                    "name": _ANALYTE_CN.get(cur["name"], C.HR.LABELS.get(cur["name"], cur["name"])),
                    "canonical": cur["name"],
                    "value": cur.get("raw_value") or cur.get("value"),
                    "unit": cur.get("unit", ""),
                    "ref": cur.get("raw_ref", cur.get("ref", "")), "status": status, "trend": label,
                    "conf": conf, "date": cur.get("date", ""),
                    "lab": cur.get("lab", ""), "tier": tier,
                    "watch_reason": watch_reason.get(cur["name"], ""),
                    "history": past,
                })
            abn = sum(1 for x in rows if x["status"] in C.HR.ABNORMAL)
            review = sum(1 for x in rows if x["status"] == "待核对")
            n_watched = sum(1 for x in rows if x["tier"] == "watched")
            n_rest = sum(1 for x in rows if x["tier"] == "rest")
            fm = re.search(r"followup_due[:：]\s*(\d{4}-\d{2}-\d{2})", hbody)
            health_summary = {"abnormal": abn, "review": review,
                              "followup": fm.group(1) if fm else None,
                              "watched": n_watched, "rest": n_rest}
            health_table = rows
            health_watchlist = watchlist
            # confirmed 变化里程碑（人话注解），挂在表格下
            ms = re.search(r"^##\s*变化里程碑[^\n]*\n(.*?)(?=^##\s|\Z)", hbody, re.M | re.S)
            health_milestones = [ln.strip("- ").strip() for ln in
                                 (ms.group(1).strip().splitlines() if ms else []) if ln.strip()]
        layer = r["layer"] if re.fullmatch(r"L[0-4]", str(r["layer"])) else "L3"
        # 空/锁时不把模板使用说明当内容，只留温度空态/锁块
        show_sub = sub if (r.get("groups") and not r.get("locked")) else ""
        if show_sub and r.get("stale"):
            show_sub = show_sub + " · " + r["stale"]
        if consent_note:
            show_sub = consent_note
        lb = {"id": lid, "title": title, "sub": show_sub, "layer": layer,
              "locked": r.get("locked", False), "empty": r.get("empty", True)}
        if health_table:
            lb["health_table"] = health_table
            lb["health_summary"] = health_summary
            lb["health_milestones"] = health_milestones
            lb["health_watchlist"] = health_watchlist or []
        if not r.get("locked") and r.get("groups"):
            lb["groups"] = r["groups"]
            lb["empty"] = False
        locked_blocks.append(lb)
    return dims, locked_blocks


def _l4_payload(data, audience, show_l4):
    """L4：默认两种 audience 都不注入明文；仅 local+--show-l4。(items, count, revealed)。"""
    items, n = [], 0
    if audience != "local":
        return items, n, False
    for rel, fp, is_link in C.iter_data_files(data, include_private=True):
        if is_link or not rel.endswith(".md"):
            continue
        layer, _m, ok = C.file_layer(fp)
        if not ok or layer != "L4":
            continue
        n += 1
        if show_l4:
            with open(fp, encoding="utf-8") as f:
                _, body = C.parse_frontmatter(f.read())
            for b in body.splitlines():
                b = b.strip()
                if b.startswith("-") and len(b) > 3:
                    items.append(_clean_inline(b.lstrip("- ").strip()))
    return items, n, (show_l4 and n > 0)


def _edge_cn(etype, frm, to):
    """方向感知：我→孩子 parent_of 显'子女'，孩子→我 child_of 显'父母'。"""
    if etype == "parent_of":
        return "子女" if frm == "me" else "父母"
    if etype == "child_of":
        return "父母" if frm == "me" else "子女"
    return REL_CN.get(etype, etype)


def _rel_paren(etype, frm, to, gender=""):
    """节点第二行身份括弧：性别细化，不明用中性。"""
    g = (gender or "")
    female = any(w in g for w in ("女", "妻", "母", "姑娘"))
    male = any(w in g for w in ("男", "夫", "父"))
    if etype == "spouse_of":
        return "（妻子）" if female else ("（丈夫）" if male else "（配偶）")
    if etype == "partner_of":
        return "（伴侣）"
    if (etype == "child_of" and to == "me") or (etype == "parent_of" and to == "me"):  # 对方是我的父母
        return "（妈妈）" if female else ("（爸爸）" if male else "（父母）")
    if (etype == "parent_of" and frm == "me") or (etype == "child_of" and frm == "me"):  # 对方是我的孩子
        return "（女儿）" if female else ("（儿子）" if male else "（孩子）")
    if etype == "works_with":
        return "（同事）"
    if etype == "knows":
        return "（认识）"
    if etype == "sibling_of":
        return "（兄弟姐妹）"
    if etype == "lives_with":
        return "（同住）"
    if etype == "related_to":
        return "（亲属）"
    return "（" + REL_CN.get(etype, "关系尚未记录") + "）"


def _entity_zone(heading, items, audience, layer):
    """实体分区：cloud 下敏感分区整块锁、敏感条目（过敏/备注等）剔除，只留锁块标记。"""
    sens = _is_sens_head(heading)
    kept = []
    for it in items:
        if audience == "cloud" and (_is_sens_head(heading) or _item_sensitive(it)):
            continue
        kept.append(it)
    return {"heading": heading, "items": kept,
            "sensitive": sens and audience == "cloud"}


def build_payload(data, audience, layer_set, show_l4, reveal_l3_entities, view):
    me, me_locked = _me_header(data, audience)
    dims, locked_blocks = _me_dimensions(data, audience, layer_set)

    entities_raw, ent_skip = load_entities_raw(data)
    edges, rel_notes = parse_relations(data)

    people = []
    for eid, info in entities_raw.items():
        if audience == "local" and layer_set and info["layer"] not in layer_set:
            continue
        eb = dict((k, v) for k, v in _bullets(info["body"]))
        members = info.get("members", [])
        is_group = info.get("is_group", False)
        if is_group and members:
            realname = "·".join(members[:2])
            avatar = "".join(_first_han(n) for n in members[:2])  # 刘吴（圆内横排两字）
            short = _group_short(info["label"], members, eid)
        elif is_group:
            realname, short = info["label"], _group_short(info["label"], [], eid)
            avatar = "父母" if any(h in eid.lower() for h in ("parent", "family")) else "好友"
        else:
            realname = _extract_realname(eb, info["label"])
            avatar = _first_han(realname)
            short = re.split(r"[·、,，/／]", info["label"] or "")[0].strip() or info["label"]
        gender_hint = eb.get("性别") or eb.get("性别/年龄段") or ""
        entry = {"id": eid, "circle": info["circle"], "layer": info["layer"],
                 "label": info["label"], "avatar": avatar, "realname": realname,
                 "short": short, "gender": gender_hint,
                 "is_group": is_group, "members": members}
        blocks = _parse_blocks(info["body"])
        # v12.1：人物实体健康分区在 local 也过本地授权门（与 gate/export 同一套裁剪结果）；
        # cloud 已有 L3 锁保持不变。off/index_only 剔除健康分区，facts_only 只留安全子句。
        _cc = C.parse_consent(data)
        _scope = _cc["scope"] if _cc.get("allowed") else "off"
        if _scope != "full":
            _clean, _ = C.consent_filtered_body(f"entities/{eid}.md", info["body"], _cc)
            blocks = _parse_blocks(_clean)
        # 分区归位：无 ## 的扁平文件 → 按键归入"TA 大概是这样/喜好/你们俩"
        zones = []
        if any(b["heading"] for b in blocks):
            for bk in blocks:
                zones.append(_entity_zone(bk["heading"], bk["items"], audience, info["layer"]))
        else:
            kv, likes, rel = [], [], []
            for bk in blocks:
                for it in bk["items"]:
                    k = it.get("k", "")
                    if audience == "cloud" and _item_sensitive(it):
                        continue
                    if any(w in k for w in ("喜好", "口味", "爱好", "忌口")):
                        likes.append(it)
                    elif any(w in k for w in ("关系", "认识", "结婚")):
                        rel.append(it)
                    else:
                        kv.append(it)
            if kv:
                zones.append({"heading": "TA 大概是这样", "items": kv, "sensitive": False})
            if likes:
                zones.append({"heading": "喜好", "items": likes, "sensitive": False})
            if rel:
                zones.append({"heading": "你们俩", "items": rel, "sensitive": False})
        entry["zones"] = [z for z in zones if z["items"] or z["sensitive"]]
        # cloud：标了 audience: local 的实体整人正文锁住（与 gate/export 同一条 audience_local）。
        # L3 实体仍按分区过滤（敏感分区锁、职业等照常显示），这是既有设计。
        ent_locked = audience == "cloud" and C.audience_local(info.get("meta") or {})
        if ent_locked:
            # 称呼/本名也来自正文，一并不出：只用标题（如"# 配偶"）或 id 当称呼
            _h1 = next((ln[2:].strip() for ln in info["body"].splitlines() if ln.startswith("# ")), "")
            safe = _h1 or eid
            entry["zones"] = [{"heading": "TA 的档案", "items": [], "sensitive": True}]
            entry.update({"label": safe, "realname": safe, "short": safe, "gender": "",
                          "avatar": _first_han(safe) or "🔒", "members": []})

        def _plain(it):
            t = _item_text(it)
            return t.replace("**", "").replace("__", "").strip()

        # 非敏感一行摘要（cloud 不放 L3 明文）。
        # 群组跳过「成员」分节（成员名单已在标题/成员区展示，摘要别再重复一条带 ** 的原文）。
        summary = ""
        for z in entry["zones"]:
            if z["sensitive"] or (is_group and z["heading"] == "成员"):
                continue
            for it in z["items"]:
                if "**" in _item_text(it):
                    continue
                k = it.get("k", "")
                if k in ("称呼", "本名", "生日", "籍贯", "纪念日", "是谁"):
                    continue
                if any(w in k for w in ("工作", "职业", "公司", "主要事实")):
                    summary = _plain(it)
                    break
            if summary:
                break
        if not summary:
            for z in entry["zones"]:
                if z["sensitive"] or (is_group and z["heading"] == "成员"):
                    continue
                for it in z["items"]:
                    if "**" in _item_text(it):
                        continue
                    if it.get("k") not in ("称呼", "本名", "生日", "籍贯", "纪念日", "是谁"):
                        summary = _plain(it)
                        break
                if summary:
                    break
        entry["summary"] = "" if ent_locked else summary
        people.append(entry)

    # 边：保留所有可见实体间的边；幽灵边提示；cloud 不画指向锁分区的额外边
    visible = {"me"} | {p["id"] for p in people}
    alive_edges = []
    for e in edges:
        a, b, etype = e.get("from"), e.get("to"), e.get("type")
        if a in visible and b in visible:
            alive_edges.append({"from": a, "to": b, "type": etype,
                                "label": _edge_cn(etype, a, b),
                                "directed": etype in DIRECTED,
                                "since": e.get("since", "")})
        else:
            rel_notes.append(f"关系边指向未记录实体（{a}→{b}），已跳过")

    # 与"我"的中文关系（节点第二行身份括弧用）
    rel_index = {}
    me_edge = {}
    for e in alive_edges:
        other = None
        if e["from"] == "me":
            other = e["to"]; frm, to = "me", e["to"]
        elif e["to"] == "me":
            other = e["from"]; frm, to = e["from"], "me"
        if other:
            rel_index.setdefault(other, [])
            if e["label"] not in rel_index[other]:
                rel_index[other].append(e["label"])
            me_edge[other] = (e["type"], frm, to)
    for p in people:
        p["relations"] = rel_index.get(p["id"], [])
        # 第二行身份：内圈/重要圈写"本名（关系）"，外围圈简化为"称呼（关系）"
        etype, frm, to = me_edge.get(p["id"], ("", "me", p["id"]))
        paren = _rel_paren(etype, frm, to, p.get("gender", ""))
        if p.get("is_group"):
            e = p["id"].lower()
            # 群组 short 已含“父母/夫妇”，第二行括弧不重复：父母留空，朋友给关系性质
            p["identity"] = "" if ("parent" in e or "family" in e) else "（好友）"
        elif p["circle"] == "peripheral":
            p["identity"] = paren
        else:
            base = p["realname"] if p["realname"] and p["realname"] != p["short"] else ""
            p["identity"] = base + paren

    l4_items, l4_count, l4_revealed = _l4_payload(data, audience, show_l4)

    return {
        "meta": {
            "now": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "audience": audience, "view": view,
            "show_l4": show_l4, "reveal_l3_entities": reveal_l3_entities,
            "l4_count": l4_count, "l4_revealed": l4_revealed,
        },
        "me": me, "me_locked": me_locked,
        "dims": dims, "locked_blocks": locked_blocks,
        "people": people, "edges": alive_edges,
        "l4": {"items": l4_items, "count": l4_count, "revealed": l4_revealed},
        "skipped": ent_skip + rel_notes,
    }


def _json_safe(obj):
    s = json.dumps(obj, ensure_ascii=False)
    return s.replace("</", "<\\/")  # 防 </script> 注入


GRAPH_MODEL = open(os.path.join(os.path.dirname(__file__), "graph_model.js"), encoding="utf-8").read()

CSS = """
:root{--blue:#4c6ef5;--purple:#7b61ff;--gray:#adb5bd;--amber:#f08c00;--bg:#eef1f7;--line:#e8eaf1;--ink:#23272e;--sub:#6b7280;--card:#fff;--soft:#f4f6fb;}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif;background:linear-gradient(180deg,#eef1f8,#f7f8fb);color:var(--ink);line-height:1.6}
.app{width:100%;max-width:1800px;margin:0 auto;padding:24px;display:flex;gap:20px;align-items:flex-start}
.col-left{width:360px;flex:0 0 360px;min-width:0;position:sticky;top:24px}
.col-right{flex:1;min-width:0}
body.view-network .col-right{display:none}
body.view-profile .col-left{display:none}
body.view-network .col-left,body.view-profile .col-right{width:100%;min-width:0;position:static;flex-basis:auto}
body.view-network .col-left{max-width:780px;margin:0 auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:20px;box-shadow:0 6px 22px rgba(30,40,80,.06);padding:20px}
.hint{font-size:13.5px;color:var(--sub);margin:0 0 10px;line-height:1.7}
.banner{font-size:12px;color:var(--sub);margin:6px 0}
.warn{background:#fff4f4;border:1px solid #ffc9c9;color:#c92a2a;border-radius:12px;padding:10px 14px;font-size:13px;margin:10px 0}
#net{position:relative;width:100%;max-width:560px;aspect-ratio:1/1;margin:0 auto}
#net svg{position:absolute;inset:0;width:100%;height:100%;preserveAspectRatio:xMidYMid meet}
.ringband{fill-opacity:.07}
.ringlbl{font-size:12px;font-weight:600}
.edge{stroke:#c9d0dd;stroke-width:1.6;fill:none;cursor:pointer}
.edge.hl{stroke:var(--blue);stroke-width:2.6}
.edgepill{fill:#fff;stroke:#e2e7f0}
.edgetxt{font-size:11.5px;fill:#5a6472;text-anchor:middle;pointer-events:none}
#edgeTip{position:absolute;z-index:20;pointer-events:none;background:#2f3e6e;color:#fff;
  font-size:12px;padding:4px 10px;border-radius:999px;white-space:nowrap;display:none;transform:translate(-50%,-140%)}
.node{position:absolute;transform:translate(-50%,-50%);cursor:pointer;text-align:center;z-index:5;width:58px;height:58px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.node.me{width:88px;height:88px}
.node .avatar{width:58px;height:58px;border-radius:50%;margin:0 auto;display:flex;align-items:center;justify-content:center;color:#fff;font-size:20px;font-weight:600;box-shadow:0 6px 16px rgba(30,40,80,.18);border:2px solid #fff;white-space:nowrap;overflow:hidden}
.node .avatar.f1{font-size:22px}
.node .avatar.f2{font-size:18px}
.node .avatar.f3{font-size:13px;font-weight:500}
.node.me .avatar{width:88px;height:88px;font-size:30px;background:linear-gradient(135deg,#2f3e6e,#3a4a7a)!important;border:3px solid var(--amber)}
.node.me .avatar.f2{font-size:26px}
.node.me .nm{top:96px}
.node.me .ident{top:114px}
.node.me .mehint{top:134px}
.node .nm{position:absolute;top:64px;left:50%;transform:translateX(-50%);font-size:12.5px;font-weight:600;line-height:1.3;max-width:120px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.node .ident{position:absolute;top:82px;left:50%;transform:translateX(-50%);font-size:10.5px;color:var(--sub);line-height:1.3;max-width:130px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.node .chip{display:inline-block;font-size:10.5px;color:#5a6478;background:#eef1f7;border-radius:999px;padding:1px 8px;white-space:nowrap}
.node .mehint{position:absolute;top:112px;left:50%;transform:translateX(-50%);font-size:11px;color:var(--blue);background:#eef1ff;border-radius:999px;padding:1px 9px;white-space:nowrap}
.node .sum{position:absolute;top:100px;left:50%;transform:translateX(-50%);font-size:11px;color:var(--sub);max-width:150px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:none}
.node:hover .sum,.node.sel .sum{display:block}
.node.dim{opacity:.3}
.node.sel .avatar{box-shadow:0 0 0 4px rgba(76,110,245,.22),0 6px 16px rgba(30,40,80,.2)}
.spoke{stroke:#e6eaf2;stroke-width:1}
.ringdisc{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);border-radius:50%;border:1px dashed;background:transparent;pointer-events:none;z-index:0}
.ph{position:absolute;transform:translate(-50%,-50%);text-align:center;color:var(--sub);cursor:default}
.ph .dash{width:44px;height:44px;border-radius:50%;border:1.5px dashed #c4cad6;margin:0 auto;display:flex;align-items:center;justify-content:center;font-size:20px}
.ph .t{font-size:11.5px;margin-top:4px}
.legend{display:flex;gap:8px 14px;flex-wrap:wrap;justify-content:center;font-size:10.5px;line-height:1.8;color:var(--sub);margin-top:12px;padding:12px 4px 0;border-top:1px solid var(--line);box-sizing:border-box;width:100%}
.legend span{white-space:nowrap}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle}
/* right doc */
.crumbbar{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.backbtn{cursor:pointer;border:1px solid var(--line);background:#fff;color:var(--blue);border-radius:999px;padding:6px 14px;font-size:13.5px;min-height:36px}
.backbtn:hover{background:#eef1ff;border-color:#c7d2fe}
.backbtn:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.crumb{font-size:13px;color:var(--sub)}
.toolbar{display:flex;gap:10px;margin:6px 0 14px}
.toolbar button{cursor:pointer;border:1px solid var(--line);background:#fff;color:var(--blue);border-radius:999px;padding:6px 14px;font-size:13.5px;min-height:36px}
.toolbar button:hover{background:#eef1ff;border-color:#c7d2fe}
.toolbar button:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.phead{display:flex;gap:18px;align-items:center;margin-bottom:16px}
.phead .avatar{width:66px;height:66px;border-radius:50%;background:linear-gradient(135deg,#2f3e6e,#4c6ef5);color:#fff;font-size:28px;font-weight:600;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.phead h2{margin:0;font-size:24px}
.phead .meta{color:var(--sub);font-size:14px;margin-top:3px}
.ptags{margin-top:8px}
.ptags .tag{display:inline-block;background:#eef1ff;color:var(--blue);border-radius:999px;padding:3px 12px;font-size:13px;margin:3px 6px 0 0}
.plinks{margin-top:8px;font-size:13px}
.plinks a{color:var(--blue);text-decoration:none;margin-right:16px}
.sect-h{font-size:15px;font-weight:700;margin:18px 0 10px}
.dimgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.dimcard{border:1px solid var(--line);border-radius:16px;padding:15px;cursor:pointer;transition:.15s;background:#fff}
.dimcard:hover{border-color:#c7d2fe}
.dimcard.sel{border-color:var(--blue);background:#f6f8ff;box-shadow:0 0 0 3px rgba(76,110,245,.12)}
.dimcard h3{margin:0;font-size:16px}
.dimcard .sub{font-size:12.5px;color:var(--sub);margin-top:5px}
.dimcard.locked{opacity:.75}
.badge{display:inline-block;font-size:11px;padding:1px 8px;border-radius:999px;margin-left:6px;font-weight:500}
.lv-L0{background:#e6f4ea;color:#1e7e34}.lv-L1{background:#eef1ff;color:var(--blue)}.lv-L2{background:#f1ecff;color:var(--purple)}.lv-L3{background:#fff3e0;color:#b26a00}.lv-L4{background:#ffe9e9;color:#c92a2a}
.detail{margin-top:16px}
.lead{background:#f6f8ff;border-left:3px solid var(--blue);border-radius:12px;padding:14px 16px;font-size:15px}
.tl{list-style:none;margin:0;padding:0;border-left:2px solid #e3e8f5}
.tl li{position:relative;padding:4px 0 14px 22px}
.tl li::before{content:"";position:absolute;left:-7px;top:9px;width:11px;height:11px;border-radius:50%;background:var(--blue);border:2px solid #fff}
.tl .when{font-weight:700;color:var(--blue);margin-right:10px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chips .c{background:var(--soft);border-radius:999px;padding:4px 12px;font-size:13px}
.kvgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.kv{background:var(--soft);border-radius:12px;padding:10px 13px;font-size:13.5px}
.kv b{color:#374151;display:block;font-size:12px;color:var(--sub);font-weight:500;margin-bottom:2px}
.list{margin:0;padding-left:18px}
.list li{margin:7px 0;font-size:14px}
.lockbox{background:#faf7f0;border:1px dashed #e8d9b8;color:#9a7a3a;border-radius:14px;padding:16px;font-size:13.5px;text-align:center}
.empty{color:#9aa3af;font-size:13.5px;padding:14px;text-align:center;background:var(--soft);border-radius:14px}
/* v12 健康关键指标表：克制着色，窄屏横滑不溢出 */
.hsummary{font-size:13px;color:#6b7280;margin:4px 0 10px}
.htable-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid #eef0f3;border-radius:12px}
table.htable{border-collapse:collapse;min-width:560px;width:100%;font-size:13px}
table.htable th,table.htable td{padding:8px 10px;border-bottom:1px solid #f0f1f4;text-align:left;white-space:nowrap}
table.htable th{color:#6b7280;font-weight:600;background:#fafbfc}
.ht-name{font-weight:600}
.ht-meta{color:#9aa3af;font-size:12px}
.hstatus.st-ok{color:#3f7d5b}.hstatus.st-warn{color:#c07a2a}.hstatus.st-ref{color:#9aa3af}
.trend{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px}
.tg-improved{background:#e9f3ec;color:#3f7d5b}.tg-worsened{background:#fbeee0;color:#c07a2a}
.tg-resolved{background:#e9f3ec;color:#3f7d5b}.tg-new{background:#eef2f8;color:#4a6ea9}
.tg-persistent{background:#f2f3f5;color:#6b7280}.tg-fluctuating{background:#f2f3f5;color:#6b7280}
.tg-mid{background:#eef2f8;color:#5a7896}.tg-ref{background:#f2f3f5;color:#9aa3af}
.wl-strip{margin:8px 0;display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:13px}
.wl-h{color:#374151;font-weight:600}
.wl-chip{background:#eef2f8;color:#4a6ea9;border-radius:999px;padding:2px 10px}
.wl-rs{color:#7a8aa0;font-size:12px}
.watch-badge{display:inline-block;margin-left:6px;background:#eef2f8;color:#4a6ea9;border-radius:999px;padding:0 7px;font-size:11px}
.row-watched td{background:#f7f9fc}
.watch-ctx{color:#6b7280;font-size:12px;padding:2px 4px}
.ht-ctx td{color:#6b7280;font-size:12px;background:#fafbfc}
.rest-fold{margin:8px 0;font-size:13px;color:#6b7280}
.rest-fold summary{cursor:pointer;color:#4a6ea9}
.rest-fold table{margin-top:6px}
.ht-hist td{color:#9aa3af;font-size:12px;background:#fafbfc}
.hmilestones{margin-top:12px;font-size:13px;color:#4a5568}
.hm-h{font-weight:600;margin-bottom:4px}
.hm-item{color:#5b6675;line-height:1.7}
.subgroup{margin:14px 0}
.subgroup h4{font-size:14px;margin:0 0 8px;color:#374151}
.toolbar{margin:10px 0}
.toolbar button{font-size:12.5px;border:1px solid var(--line);background:#fff;border-radius:9px;padding:6px 13px;cursor:pointer;margin-right:8px}
.meta{font-size:12px;color:var(--sub);margin-top:16px;border-top:1px solid var(--line);padding-top:10px}
/* Compact personal notebook: navigation stays small, actual records own the page. */
body{background:#f3f5f8}
.card{padding:22px;border-radius:16px;box-shadow:0 3px 16px rgba(30,40,80,.035)}
.col-left .card{padding:16px}
.hint{font-size:14px;line-height:1.5;margin-bottom:6px}
#net{max-width:360px}
.legend{font-size:12px;gap:5px 12px;margin-top:0;padding-top:10px}
.crumbbar{margin-bottom:16px;gap:10px}
.backbtn,.toolbar button{min-height:44px;font-size:14px}
.phead{align-items:flex-start;gap:14px;margin-bottom:14px}
.phead>div:last-child{flex:1;min-width:0}
.phead .avatar{width:52px;height:52px;font-size:23px}
.phead h2{font-size:25px;line-height:1.3}
.phead .meta{margin:5px 0 0;padding:0;border:0;font-size:14px;line-height:1.55}
.phead h2 .meta{font-size:15px;font-weight:400}
.ptags{margin-top:5px}
.ptags .tag{font-size:12px;padding:2px 9px;margin:2px 5px 0 0}
.plinks{margin-top:5px}
.toolbar{margin:10px 0;gap:6px}
.toolbar button{margin-right:0;padding:6px 11px}
.dimgrid{grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.dimcard{padding:10px 12px;border-radius:10px;min-height:74px;min-width:0}
.dimcard h3{font-size:15px}
.dimcard .sub{font-size:12px;line-height:1.45;margin-top:4px}
.dimcard .badge{font-size:10px;padding:1px 5px;margin-left:3px}
.dimcard.locked{opacity:1}
.dimcard.sel{box-shadow:none;background:#eef3ff}
.detail{margin-top:18px}
.hsummary{font-size:14px;line-height:1.6}
.htable-wrap{border-radius:10px}
table.htable{font-size:14px;min-width:640px}
table.htable th,table.htable td{padding:9px 10px}
.ht-meta{font-size:12px;max-width:210px;white-space:normal!important}
.watch-ctx{font-size:13px}
.ht-ctx td{white-space:normal!important;line-height:1.5}
.metric-history{font-size:12px;color:var(--sub);font-weight:400;position:relative}
.metric-history summary{cursor:pointer;min-height:28px;display:flex;align-items:center;color:#5a7896}
.metric-history[open]{min-width:340px}
.history-point{display:grid;grid-template-columns:88px 110px minmax(0,1fr);gap:8px;line-height:1.5;padding:6px 0;white-space:normal}
.history-point strong{font-weight:500;color:#526172}
.side-people{display:flex;flex-direction:column;gap:3px;margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
.person-nav{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;min-height:48px;border:0;border-radius:8px;background:transparent;color:var(--ink);padding:8px 10px;text-align:left;cursor:pointer;font-family:inherit}
.person-nav:hover,.person-nav.active{background:#eef3ff;color:var(--blue)}
.person-nav .person-name{font-size:14px;font-weight:600;line-height:1.4}
.person-nav .person-rel{font-size:12px;color:var(--sub);white-space:nowrap}
button:focus-visible,.dimcard:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
@media(min-width:1600px){.app{padding:28px 40px;gap:24px}.col-left{width:380px;flex-basis:380px}}
@media(max-width:1100px) and (min-width:901px){.col-left{width:310px;flex-basis:310px}.dimgrid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:900px){.app{flex-direction:column;padding:16px;gap:14px}.col-left{width:100%;min-width:0;flex-basis:auto;position:static}.col-right{width:100%}.dimgrid{grid-template-columns:repeat(4,minmax(0,1fr))}.side-people{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.app{padding:12px;gap:12px}.card{padding:16px}.dimgrid{grid-template-columns:repeat(2,minmax(0,1fr))}.kvgrid{grid-template-columns:1fr}.phead h2{font-size:22px}.phead{gap:10px}.phead .avatar{width:44px;height:44px}.phead .meta{font-size:14px}.crumb{font-size:12px}.side-people{grid-template-columns:1fr}.dimcard .sub{font-size:12px}.ht-meta{font-size:12px}.person-nav .person-name{font-size:14px}}
@media(max-width:560px){.node .avatar{width:44px;height:44px;font-size:16px}.node.me .avatar{width:64px;height:64px;font-size:24px}.node .nm{font-size:12px;max-width:110px}.legend{display:grid;grid-template-columns:1fr 1fr;justify-items:start;gap:6px 10px;font-size:10px;white-space:normal;width:100%;box-sizing:border-box;padding:12px 8px 0}.legend span{white-space:normal;max-width:100%;line-height:1.5}}
"""

CSS += "/* Graph as primary workspace; detail stays alongside, not below a long roster. */\n.col-left{width:54%;flex:0 0 54%;position:sticky;top:24px;min-width:0}\n.col-right{flex:1;min-width:0}\n@media(min-width:1600px){.col-left{width:54%;flex-basis:54%}}\n@media(max-width:1100px) and (min-width:901px){.col-left{width:52%;flex-basis:52%}}\nbody.view-network .col-left{max-width:none}\n.graph-card{padding:18px;overflow:hidden}\n.graph-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:8px}\n.graph-heading h2{font-size:20px;margin:0}.graph-heading button,.graph-controls button{font-family:inherit;min-height:44px;border:1px solid #cbd8e3;border-radius:8px;background:#fff;color:#365b78;padding:8px 12px;cursor:pointer}\n.graph-controls{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin:12px 0}\n.graph-controls button[aria-pressed=true]{background:#365b78;color:white}\n#zoom-label{font-size:13px;min-width:36px;text-align:center}\n#graph-status{font-size:14px;color:#5e7385;margin:8px 0}.path-note{font-size:12px;color:#728394;margin:4px 0 8px}\n.graph-path{display:flex;gap:6px;flex-wrap:wrap;align-items:center;font-size:13px}\n.graph-path button{font-family:inherit;min-height:32px;background:#f1f5f9;color:#365b78;border:0;border-radius:6px;padding:4px 9px;cursor:pointer}.path-edge{color:#72889b;font-size:12px}.path-edge::before{content:'— ';}.path-edge::after{content:' →';}\n#net{width:100%;max-width:none;height:570px;aspect-ratio:auto;position:relative;overflow:auto;margin:0;border:1px solid #dee7ee;border-radius:10px;background:#f8fafc;overscroll-behavior:contain}\n#net svg{position:absolute;inset:0;width:auto;height:auto;pointer-events:none}\n#net .edge{stroke:#aabfce;stroke-width:1.5;cursor:default}\n.graph-shell{position:relative;min-width:100%}.graph-world{position:relative;transform-origin:top left}\n.depth-label{position:absolute;top:16px;width:210px;color:#698093;font-size:13px;border-bottom:1px solid #d5e0e8;padding-bottom:6px}\n#net .graph-node,#net .graph-node.me{position:absolute;display:flex;flex-direction:row;align-items:center;justify-content:flex-start;gap:10px;width:210px;height:92px;transform:none;border:1px solid #dae3eb;border-left:4px solid #426c91;background:#fff;border-radius:12px;padding:12px;box-shadow:0 2px 5px rgba(35,60,80,.04);text-align:left;z-index:3;cursor:pointer}\n#net .graph-node.sel{border-color:#426c91;background:#eff5fa}#net .graph-node:hover{border-color:#426c91}\n#net .graph-node .avatar,#net .graph-node.me .avatar{flex:0 0 36px;width:36px;height:36px;border:0;background:#e9f0f6;color:#365b78;font-size:18px;border-radius:50%;display:flex;align-items:center;justify-content:center}\n#net .graph-node .node-copy{flex:1;min-width:0;padding-right:0}\n#net .graph-node .nm{font-size:15px;line-height:1.4;font-weight:600;white-space:normal;max-width:none;overflow:visible;display:block;margin:0;overflow-wrap:anywhere}\n#net .graph-node .ident{font-size:12px;line-height:1.5;margin-top:3px;color:#728292;white-space:normal;max-width:none}\n#net .graph-node .node-expand{position:absolute;bottom:-12px;right:10px;min-width:44px;min-height:30px;border:1px solid #cbd8e3;border-radius:7px;color:#3c6586;background:#fff;font-size:12px;cursor:pointer;z-index:4;padding:3px 8px;font-family:inherit}\n.graph-key{display:flex;gap:12px;flex-wrap:wrap;color:#708398;font-size:12px;margin:10px 0}.graph-key i{display:inline-block;width:6px;height:12px;margin-right:5px;vertical-align:middle;border-radius:2px}.graph-search label{display:block;font-size:14px;font-weight:500;margin:12px 0 6px}\n#person-search{width:100%;min-height:44px;font-family:inherit;font-size:16px;border:1px solid #cbd8e3;border-radius:8px;padding:9px 12px;background:white;color:#243748}\n#people-list.side-people{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));max-height:190px;overflow:auto;margin:8px 0 0;padding:0;border:0;gap:4px}\n.person-nav{min-height:48px;align-items:flex-start;flex-direction:column;gap:2px;padding:8px}\n.person-nav .person-rel{white-space:normal;font-size:12px}.person-nav .person-name{font-size:14px;overflow-wrap:anywhere}\n.related-section{border-top:1px solid #e1e8ee;margin-top:18px;padding-top:16px}.related-section h3{font-size:16px;margin:0 0 10px}.related-list{display:flex;gap:8px;flex-wrap:wrap}.related-list button{font-family:inherit;background:#f6f8fb;border:1px solid #dbe4eb;border-radius:8px;min-height:44px;cursor:pointer;padding:8px 10px;color:#355b77}.related-list strong{font-size:14px;font-weight:500}.related-list span{display:block;font-size:12px;color:#6c8295}\n#focus-person{font-family:inherit;min-height:44px;border:1px solid #cbd8e3;background:white;border-radius:8px;padding:8px 12px;color:#365b78;cursor:pointer;margin:6px 0 12px}\n@media(max-width:1200px){.dimgrid{grid-template-columns:repeat(2,minmax(0,1fr))}}\n@media(max-width:900px){.col-left{width:100%;flex-basis:auto;position:static}.col-right{width:100%}#net{height:460px}.dimgrid{grid-template-columns:repeat(4,minmax(0,1fr))}}\n@media(max-width:560px){.graph-card{padding:12px}#net{height:420px}#people-list.side-people{grid-template-columns:repeat(2,minmax(0,1fr));max-height:170px}.dimgrid{grid-template-columns:repeat(2,minmax(0,1fr))}.graph-heading h2{font-size:18px}.graph-path button{min-height:36px}.graph-controls{gap:6px}.graph-controls button{padding:7px 9px}}\n"

CSS += """
#net .graph-node .nm,#net .graph-node .ident{position:static;left:auto;top:auto;transform:none}
#net .graph-node .avatar{margin:0;box-shadow:none}
#net .graph-node.me .avatar{background:#365b78!important;color:#fff;border:0}
#net .graph-node .node-expand{min-height:44px;bottom:-15px}
.graph-path button{min-height:44px}
.graph-key{font-size:14px}.graph-key span{line-height:1.5}
.related-list{max-height:290px;overflow:auto}
#net .edge.hl{stroke:#426c91;stroke-width:3}
.small-network .col-left{width:40%;flex-basis:40%}
.small-network #net{height:420px}
.wide-graph{flex-direction:column}.wide-graph .col-left{width:100%;flex-basis:auto;position:static}.wide-graph .col-right{width:100%}.wide-graph #net{height:620px}
@media(max-width:900px){.small-network .col-left{width:100%;flex-basis:auto}.wide-graph #net{height:460px}}
"""

CSS += """
/* Ego-centered graph: circular portraits and full labels, not hierarchy cards. */
#net .graph-node,#net .graph-node.me{width:136px;height:120px;transform:translate(-50%,-27px);padding:0;border:0!important;background:transparent!important;box-shadow:none!important;border-radius:0;flex-direction:column;gap:4px;justify-content:flex-start;text-align:center}
#net .graph-node .avatar{width:54px;height:54px;flex:0 0 54px;font-size:19px;background:#fff;color:#43657d;border:2px solid #93aabd;box-shadow:0 2px 8px rgba(38,67,86,.08);margin:0}
#net .graph-node.me .avatar{width:80px;height:80px;flex-basis:80px;border:3px solid #e8bb74!important;color:white;background:#3c627b!important;font-size:23px}
#net .graph-node .node-copy{flex:none;width:136px;background:rgba(248,250,252,.96);border-radius:6px;padding:0 4px;line-height:1.35}
#net .graph-node .nm{position:static;font-size:16.5px;line-height:1.3;font-weight:600;overflow-wrap:normal;white-space:normal}
#net .graph-node .ident{position:static;font-size:16.5px;margin:1px 0 0;line-height:1.3}
#net .graph-node.me{transform:translate(-50%,-40px)}
#net .graph-node.me .node-copy{position:absolute;top:84px}
#net .graph-node .node-expand{right:4px;top:0;bottom:auto;min-width:44px;min-height:44px;border-radius:50%;font-size:12px;padding:2px;background:#fff}
#net .graph-node.me .node-expand{display:block;right:-6px;top:0}
#net .graph-node.sel .avatar,#net .graph-node.focus .avatar{border-color:#3c627b;box-shadow:0 0 0 4px rgba(60,98,123,.14)}
#net{touch-action:none;cursor:grab;background:#f8fafc;height:660px}
#net:active{cursor:grabbing}.small-network #net{height:530px}
#net svg{pointer-events:none}.ego-ring{stroke-width:1;stroke-dasharray:5 7;opacity:.36}.ring-label{font-size:16.5px;paint-order:stroke;stroke:#f8fafc;stroke-width:5px}
.graph-overview{display:flex;align-items:center;gap:12px;margin:10px 0;min-width:0}.graph-overview[hidden]{display:none}.graph-overview svg{width:150px;height:114px;border:1px solid #dbe4eb;border-radius:8px;cursor:crosshair;flex:none;touch-action:none}.graph-overview p{font-size:14px;line-height:1.6;color:#627a8d;margin:0}
#net .edge{stroke:#aec0ca;stroke-width:1.3;opacity:.65}
#net .edge.hl{stroke:#557b93;stroke-width:2.8;opacity:1}#net .edge.muted{opacity:.1}
.phead>.avatar{flex:0 0 auto;white-space:nowrap;overflow:hidden;font-size:22px}.phead>.avatar:has(+div){min-width:44px}
#net .node:focus-visible{outline:2px solid #436a84;outline-offset:4px;border-radius:6px}
@media(max-width:900px){#net,.small-network #net{height:640px}}
@media(max-width:560px){#net,.small-network #net{height:640px}.graph-key{font-size:13px}}
.small-network .col-left{width:48%;flex-basis:48%}.small-network #net{height:580px}
@media(max-width:900px){.small-network .col-left{width:100%;flex-basis:auto}.small-network #net{height:640px}.ring-label{display:none}}
"""

CSS += """
/* Reading-first split workspace. A diagram is navigated by drag, never a wheel trap. */
:root{--blue:#3b6b78;--purple:#697e79;--bg:#eef3f3;--ink:#263d43;--sub:#697f83;--soft:#f2f6f6;--line:#dfe8e8}
body{background:#eef3f3}
.app{display:grid;grid-template-columns:minmax(0,var(--left-weight,40fr)) 24px minmax(0,var(--right-weight,60fr));gap:0;padding:24px;align-items:start}
.app .col-left,.app .col-right{width:auto;flex-basis:auto;min-width:0;position:static;margin:0}
.card{border:1px solid #dce7e7;border-radius:18px;box-shadow:0 5px 20px rgba(43,77,79,.035)}
.graph-card{background:#f8fbfb;padding:20px}
.graph-heading{padding-bottom:12px;border-bottom:1px solid #dfe8e8;margin-bottom:12px}.graph-heading h2{color:#2c5158;font-size:21px}
#net,.small-network #net{overflow:hidden;overscroll-behavior:auto;touch-action:none;scrollbar-width:none;background:#f3f8f7;border-color:#d9e6e3;height:600px}
#net::-webkit-scrollbar{display:none}#net .graph-node .node-copy{background:rgba(243,248,247,.95)}
#net .graph-node .avatar{border-color:#8daeb1;color:#39616a;background:#fff;box-shadow:0 3px 9px rgba(45,80,81,.08)}
#net .graph-node.me .avatar{background:#3b6b78!important;border-color:#ddbd84!important;box-shadow:0 0 0 7px rgba(221,189,132,.13)}
#net .graph-node .node-expand{border-color:#c8dadb;color:#466e76}.ring-label{stroke:#f3f8f7}
.graph-controls{padding:7px;background:#eaf2f2;border-radius:12px;gap:6px}.graph-controls button{background:#fff;border-color:transparent;box-shadow:0 1px 3px rgba(43,77,79,.04)}
.graph-controls button:hover,.graph-heading button:hover{background:#deebeb}.graph-controls button[aria-pressed=true]{background:#3b6b78;color:#fff}
#graph-status{font-size:13px}.person-nav{border-radius:8px}.person-nav.active{background:#e4f0ed;color:#305f66}.person-nav:hover{background:#edf4f2}
#person-search{border-color:#d3e1e0;background:#fff}#person-search:focus{outline:2px solid #9abdbd;outline-offset:1px}
#doc{padding:26px;background:#fff}.crumbbar{padding-bottom:14px;border-bottom:1px solid #e4eded;margin-bottom:18px}.crumb{color:#799093}.backbtn{color:#477781;background:#f1f7f6;border-color:#dde9e7}
.phead{padding-bottom:18px;margin-bottom:0}.phead h2{font-size:26px;color:#284b53;line-height:1.45}.phead>.avatar{background:#3b6b78;box-shadow:0 0 0 5px #eef5f3;flex:0 0 auto}
.ptags .tag{background:#eef4f3;color:#55716e}.plinks a{color:#397382}.toolbar{padding:10px 0;margin-bottom:10px;border-top:1px solid #e7eeee}.toolbar button{border-color:#dae7e5;color:#477781;background:#f8fbfa}
.dimgrid{gap:8px}.dimcard{background:#f8fbfa;border-color:#e0e9e8;border-radius:11px;padding:12px;box-shadow:none}.dimcard h3{color:#36575d}.dimcard .sub{font-size:13px;color:#7c8e90;line-height:1.55}.dimcard:hover{background:#edf5f2;border-color:#aac9c3}.dimcard.sel{background:#eaf4f0;border-color:#82b3a3;box-shadow:inset 0 0 0 1px #82b3a3}
.badge.lv-L1{background:#eaf1f4;color:#577b91}.badge.lv-L2{background:#e9f3ee;color:#5f8270}.badge.lv-L3{background:#faf1e3;color:#9a753d}
.detail{margin-top:20px}.sect-h{color:#31555d;font-size:18px;margin-bottom:12px}.subgroup h4{font-size:15px;color:#46696d}.list{color:#35494d;line-height:1.85}.kvgrid .kv{background:#f3f7f6;border:1px solid #e5edeb;border-radius:10px}
table.htable th{background:#eff5f4;color:#5b777c}.htable-wrap{border-color:#e2ebe8}.htable td{border-bottom-color:#e7eeee}.htable tr.watch-row{background:#f3f8f5}.htable tr:hover{background:#f4f8f7}.wl-strip{margin:12px 0}.wl-strip .wl-chip{background:#edf4f1;color:#527368;border-color:#dce9e1}
.column-divider{position:relative;align-self:stretch;min-height:200px;cursor:col-resize;touch-action:none;outline:none;z-index:5}
.column-divider::before{content:'';position:absolute;left:-10px;right:-10px;top:0;bottom:0}
.column-divider .divider-grip{display:flex;align-items:center;justify-content:center;position:sticky;top:180px;height:76px;width:12px;margin:140px auto 0;background:#dce8e6;border-radius:8px;color:#6c9296;transition:background .15s}
.column-divider .divider-grip::before{content:'';height:25px;width:3px;border-left:1px solid currentColor;border-right:1px solid currentColor}
.column-divider:hover .divider-grip,.column-divider:focus-visible .divider-grip{background:#b9d4ce;color:#365f67}
body.resizing-columns{cursor:col-resize;user-select:none}.app.wide-graph{display:block}.app.wide-graph .col-left,.app.wide-graph .col-right{width:100%}.app.wide-graph .col-right{margin-top:18px}.app.wide-graph .column-divider,body.view-network .column-divider,body.view-profile .column-divider{display:none}
body.view-network .app,body.view-profile .app{display:block}
@media(max-width:1100px) and (min-width:901px){.dimgrid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:900px){.app{display:flex;flex-direction:column;gap:16px;padding:16px}.app .col-left,.app .col-right{width:100%;flex-basis:auto}.column-divider{display:none}#doc{padding:20px}#net,.small-network #net{height:640px}.dimgrid{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:560px){.app{padding:12px}.graph-card{padding:16px}#doc{padding:18px}.phead h2{font-size:23px}.dimgrid{grid-template-columns:repeat(2,minmax(0,1fr))}.dimcard .sub{font-size:13px}.graph-controls{padding:5px}.graph-controls button{padding:8px}.column-divider{display:none}}
@media(prefers-reduced-motion:reduce){.column-divider .divider-grip{transition:none}}
"""

JS = r"""
(function(){
  var el=document.getElementById('mc-data');var D;
  try{D=JSON.parse(el.textContent);}catch(e){return;}
  try{
  var $=function(s){return document.querySelector(s);};
  var LEVEL_CN={L0:'公开',L1:'个人',L2:'偏好',L3:'敏感',L4:'秘密'};
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function md(s){var t=esc(s);
    t=t.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
    t=t.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
    return t.replace(/\*\*/g,'');}
  function lvBadge(lv){return '<span class="badge lv-'+esc(lv)+'">'+(LEVEL_CN[lv]||esc(lv))+'</span>';}
  var CIRC={inner:'#487891',close:'#849784',peripheral:'#a8b3bf'};

  // ---- hash 路由（id 白名单防注入）----
  function parseHash(){var o={};var h=(location.hash||'').replace(/^#/,'');
    h.split('&').forEach(function(p){if(!p)return;var i=p.indexOf('=');var k=i<0?p:p.slice(0,i);var v=i<0?'':p.slice(i+1);try{o[k]=decodeURIComponent(v||'');}catch(e){/* invalid hash ignored */}});return o;}
  function validId(id){return /^[a-z0-9_-]+$/.test(id||'');}
  // 无头验收钩子：?netw=NNN 仅强制 #net 容器宽度（模拟真机窄屏），正常打开无此参数不受影响
  function netw(){var m=(location.search||'').match(/[?&]netw=(\d+)/);return m?parseInt(m[1],10):0;}
  function setHash(k,v){var q=parseHash();if(v==null){delete q[k];}else{q[k]=v;}
    var s=Object.keys(q).map(function(x){return x+'='+encodeURIComponent(q[x]);}).join('&');
    try{history.replaceState(null,'','#'+s);}catch(e){location.hash=s;}}

  // ---- Relationship explorer: recorded edges, progressive disclosure, shortest paths ----
  var GP=new Map([['me',{id:'me',label:D.me.name||'我',circle:'inner'}]]);
  D.people.forEach(function(p){GP.set(p.id,p);});
  var graph=MCGraph.build(Array.from(GP.keys()),D.edges),G={focus:'me',expanded:new Set(),all:false,zoom:1,query:'',camera:true};
  var rank={};D.people.forEach(function(p,i){rank[p.id]=i;});rank.me=-1;
  function nameOf(id){var p=GP.get(id);if(!p)return '未记录';return p.is_group?(p.member_names||p.members||[]).join('、')||p.label:(p.realname&&p.realname.length>1?p.realname:p.label);}
  function edgeWord(e,from){return MCGraph.edgeLabel(e,from);}
  function directWord(from,to){var ns=graph.adj.get(from)||[],words=[];ns.forEach(function(n){if(n.id===to){var w=edgeWord(n.edge,from);if(words.indexOf(w)<0)words.push(w);}});return words.join('、');}
  function meRelation(id){if(id==='me')return '本人';var p=MCGraph.path(graph,'me',id);return p?(p.edges.length===1?directWord('me',id):'经 '+nameOf(p.nodes[1])+' 相连'):'关系尚未记录';}
  function pathway(id){var p=MCGraph.path(graph,'me',id);
    if(!p)return '<p class="path-note">与你的连接路径还没记录，不据此推断关系。</p>';
    return '<div class="graph-path" aria-label="已记录关系路径">'+p.nodes.map(function(n,i){return (i?'<span class="path-edge">'+esc(edgeWord(p.edges[i-1],p.nodes[i-1]))+'</span>':'')+'<button type="button" data-jump="'+esc(n)+'">'+esc(nameOf(n))+'</button>';}).join('')+'</div><p class="path-note">'+(p.edges.length?'一条已记录的最短连接路径，不代表亲密程度或影响力。':'这是你本人。')+'</p>';
  }
  function bindPath(el){el.querySelectorAll('[data-jump]').forEach(function(b){b.addEventListener('click',function(){onNode(b.dataset.jump);});});}
  function relatedHtml(id){
    var ns=graph.adj.get(id)||[];
    var seen=new Set();ns=ns.filter(function(n){if(seen.has(n.id))return false;seen.add(n.id);return true;});
    return '<section class="related-section"><h3>和 TA 有联系的人</h3><div class="related-list">'+(ns.length?ns.map(function(n){return '<button type="button" data-jump="'+esc(n.id)+'"><strong>'+esc(nameOf(n.id))+'</strong><span>'+esc(directWord(id,n.id))+'</span></button>';}).join(''):'<p>还没有更多关系记录。</p>')+'</div></section>';
  }
  function focusOn(id){if(!GP.has(id))return;G.focus=id;G.all=false;G.expanded.clear();G.zoom=1;G.camera='focus';renderNet();onNode(id);var net=$('#net');if(net){net.scrollIntoView({block:'nearest',behavior:'auto'});}}
  function shortName(s){return (s||'').split(/[·、,，/／]/)[0].trim()||'我';}
  function firstHan(s){var m=(s||'').match(/[一-龥]/);return m?m[0]:'人';}
  function renderList(){
    var box=$('#people-list');if(!box)return;var query=G.query.trim().toLowerCase();
    var ids=Array.from(GP.keys()).filter(function(id){var p=GP.get(id);return !query||[nameOf(id),p.label,p.short,meRelation(id)].join(' ').toLowerCase().indexOf(query)>=0;});
    box.innerHTML=ids.map(function(id){return '<button type="button" class="person-nav" data-person="'+esc(id)+'"><span class="person-name">'+esc(nameOf(id))+'</span><span class="person-rel">'+esc(meRelation(id))+'</span></button>';}).join('')||'<p class="empty">没有匹配的人，换个名字试试。</p>';
    box.querySelectorAll('[data-person]').forEach(function(b){b.addEventListener('click',function(){focusOn(b.dataset.person);});});
    var count=$('#people-count');if(count)count.textContent='全部 '+GP.size+' 个记录'+(query?' · 匹配 '+ids.length+' 个':'');
  }
  var currentShown=new Set(),currentGeo=null;
  function updateOverview(){
    var wrap=$('#graph-overview'),map=$('#graph-minimap'),net=$('#net'),geo=currentGeo;if(!wrap||!map||!net||!geo)return;
    wrap.hidden=GP.size<=9;if(wrap.hidden)return;
    var h='';geo.rings.forEach(function(r){h+='<circle cx="'+geo.cx+'" cy="'+geo.cy+'" r="'+r.radius+'" fill="none" stroke="#c8d7df" stroke-width="3"/>';});
    graph.edges.forEach(function(e){var a=geo.positions.get(e.from),b=geo.positions.get(e.to);if(a&&b)h+='<line x1="'+a.x+'" y1="'+a.y+'" x2="'+b.x+'" y2="'+b.y+'" stroke="#c6d2da" stroke-width="2"/>';});
    geo.positions.forEach(function(p,id){h+='<circle cx="'+p.x+'" cy="'+p.y+'" r="'+(id==='me'?14:7)+'" fill="'+(id==='me'?'#3c627b':CIRC[p.circle]||'#a8b3bf')+'"/>';});
    map.setAttribute('viewBox','0 0 '+geo.width+' '+geo.height);
    var world=net.querySelector('.graph-world'),px=world?world.offsetLeft:0,py=world?world.offsetTop:0;
    map.innerHTML=h+'<rect x="'+(net.scrollLeft-px)/G.zoom+'" y="'+(net.scrollTop-py)/G.zoom+'" width="'+net.clientWidth/G.zoom+'" height="'+net.clientHeight/G.zoom+'" fill="#557b93" fill-opacity=".1" stroke="#557b93" stroke-width="5"/>';
  }
  function renderNet(){
    var net=$('#net');if(!net)return;
    // A search matches the full safe payload, not only currently visible nodes.
    var vw=net.clientWidth||500;
    var circles={};GP.forEach(function(p,id){circles[id]=p.circle;});
    var budget=vw<500?5:9;
    currentShown=MCGraph.neighborhood(graph,G.focus,G.expanded,G.all,{limit:budget,circles:circles,rank:rank});
    var geo=MCGraph.layout(graph,currentShown,G.focus,rank,vw,circles);
    if(!G.all&&!G.expanded.size&&G.focus==='me'){
      while(budget>3){var fits=true;geo.positions.forEach(function(p){if((Math.abs(p.x-geo.cx)+70)*1.7>vw-8||(Math.abs(p.y-geo.cy)+96)*1.7>net.clientHeight-8)fits=false;});
        if(fits)break;budget--;currentShown=MCGraph.neighborhood(graph,G.focus,G.expanded,false,{limit:budget,circles:circles,rank:rank});geo=MCGraph.layout(graph,currentShown,G.focus,rank,vw,circles);
      }
    }
    var pos=geo.positions;currentGeo=geo;
    if(G.camera)G.zoom=Math.max(.85,Math.min(1,(Math.min(vw,net.clientHeight)-24)/geo.width));
    var oldX=net.scrollLeft,oldY=net.scrollTop;
    var nodes='',edgeHtml='',labels='';
    geo.rings.forEach(function(r){var colors={inner:'#487891',close:'#849784',peripheral:'#a8b3bf'},cn={inner:'最亲近的人',close:'重要联系',peripheral:'外围联系'};
      labels+='<circle class="ego-ring" cx="'+geo.cx+'" cy="'+geo.cy+'" r="'+r.radius+'" stroke="'+colors[r.circle]+'" fill="none"/><text class="ring-label" x="'+(geo.cx-r.radius+18)+'" y="'+(geo.cy+8)+'" fill="'+colors[r.circle]+'">'+cn[r.circle]+'</text>';
    });
    graph.edges.forEach(function(e){if(!currentShown.has(e.from)||!currentShown.has(e.to))return;
      var a=pos.get(e.from),b=pos.get(e.to);if(!a||!b)return;
      var dx=b.x-a.x,dy=b.y-a.y,length=Math.max(1,Math.hypot(dx,dy)),ux=dx/length,uy=dy/length;
      var offsetA=e.from==='me'?42:28,offsetB=e.to==='me'?42:28;
      var x1=a.x+ux*offsetA,y1=a.y+uy*offsetA,x2=b.x-ux*offsetB,y2=b.y-uy*offsetB;
      var bend=e.from==='me'||e.to==='me'?0:Math.min(40,length*.12);
      // Separate different relationship types joining the same pair; preserve every recorded edge.
      var peers=graph.edges.filter(function(p){return (p.from===e.from&&p.to===e.to)||(p.from===e.to&&p.to===e.from);});
      var pi=peers.indexOf(e);if(peers.length>1)bend+=(pi-(peers.length-1)/2)*30;
      var canonical=e.from.localeCompare(e.to)<=0?1:-1;
      var mx=(x1+x2)/2-uy*bend*canonical,my=(y1+y2)/2+ux*bend*canonical;
      var curve='M'+x1+' '+y1+' Q'+mx+' '+my+' '+x2+' '+y2;
      edgeHtml+='<path class="edge" data-from="'+esc(e.from)+'" data-to="'+esc(e.to)+'" d="'+curve+'"'+(e.directed?' marker-end="url(#arw)"':'')+'><title>'+esc(nameOf(e.from)+' — '+edgeWord(e,e.from)+' — '+nameOf(e.to))+'</title></path>';
    });
    var selected=parseHash().person||'me';
    currentShown.forEach(function(id){var p=GP.get(id),q=pos.get(id),neighbors=graph.adj.get(id)||[],remaining=new Set(neighbors.filter(function(n){return !currentShown.has(n.id);}).map(function(n){return n.id;})).size;
      var pathTo=MCGraph.path(graph,'me',id);
      var word=id==='me'?'本人':directWord('me',id)||(pathTo?'间接关系 · '+pathTo.edges.length+'步':'关系尚未连通');
      if(id!=='me'&&directWord('me',id)){var hm=(p.identity||'').match(/（([^）]+)）/);if(hm&&hm[1]!=='关系尚未记录')word=hm[1];}
      nodes+='<div class="node graph-node '+(id==='me'?'me ':'')+(id===G.focus?'focus ':'')+(id===selected&&id!=='me'?'sel':'')+'" data-id="'+esc(id)+'" role="button" tabindex="0" aria-label="查看 '+esc(nameOf(id))+'" style="left:'+q.x+'px;top:'+q.y+'px;border-left-color:'+(CIRC[p.circle]||'#9aa7b6')+'"><div class="avatar">'+esc(id==='me'?firstHan(nameOf(id)):(p.avatar||firstHan(nameOf(id))))+'</div><div class="node-copy"><div class="nm" title="'+esc(nameOf(id))+'">'+esc(nameOf(id))+'</div><div class="ident">（'+esc(word)+'）</div></div><button type="button" class="node-expand" data-more="'+esc(id)+'" title="'+(remaining?'展开关联的人':'查看此人的关联')+'" aria-label="'+(remaining?'展开 '+nameOf(id)+' 的 '+remaining+' 个关联':'查看 '+nameOf(id)+' 的关联')+'">'+(remaining?'+'+remaining:'关联')+'</button></div>';
    });
    var shellW=Math.max(vw,geo.width*G.zoom),shellH=Math.max(net.clientHeight,geo.height*G.zoom),padX=(shellW-geo.width*G.zoom)/2,padY=(shellH-geo.height*G.zoom)/2;
    net.innerHTML='<div class="graph-shell" style="width:'+shellW+'px;height:'+shellH+'px"><div class="graph-world" style="left:'+padX+'px;top:'+padY+'px;width:'+geo.width+'px;height:'+geo.height+'px;transform:scale('+G.zoom+')">'+'<svg width="'+geo.width+'" height="'+geo.height+'" viewBox="0 0 '+geo.width+' '+geo.height+'" aria-label="已记录关系连线"><defs><marker id="arw" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="#8eacbf"/></marker></defs>'+labels+edgeHtml+'</svg>'+nodes+'</div></div>';
    if(G.camera){var target=G.camera==='focus'?pos.get(G.focus):null;net.scrollLeft=Math.max(0,(target?target.x:geo.cx)*G.zoom+padX-net.clientWidth/2);net.scrollTop=Math.max(0,(target?target.y:geo.cy)*G.zoom+padY-net.clientHeight/2);G.camera=false;}else{net.scrollLeft=oldX;net.scrollTop=oldY;}
    net.querySelectorAll('.node').forEach(function(n){
      n.addEventListener('click',function(ev){if(ev.target.closest('[data-more]'))return;onNode(n.dataset.id);});
      n.addEventListener('keydown',function(ev){if(ev.target!==n)return;if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();onNode(n.dataset.id);}});
    });
    net.querySelectorAll('[data-more]').forEach(function(b){b.addEventListener('click',function(ev){ev.stopPropagation();var id=b.dataset.more;var missing=(graph.adj.get(id)||[]).some(function(n){return !currentShown.has(n.id);});if(missing){G.expanded.add(id);renderNet();}else focusOn(id);});});
    var stat=$('#graph-status');if(stat)stat.textContent='以 '+nameOf('me')+' 为中心 · '+(G.focus!=='me'?'正在查看 '+nameOf(G.focus)+' 的关联 · ':'')+'已展开 '+currentShown.size+' / '+GP.size+' 个记录'+(G.all?' · 全部关系':'');
    var z=$('#zoom-label');if(z)z.textContent=Math.round(G.zoom*100)+'%';
    var path=$('#focus-path');if(path){path.innerHTML=pathway(G.focus);bindPath(path);}
    var all=$('#graph-all');if(all)all.setAttribute('aria-pressed',String(G.all));
    renderList();updateOverview();requestAnimationFrame(geoCheck);
  }
  function geoCheck(){
    var ns=Array.from(document.querySelectorAll('#net .node')),fail='',minFont=Infinity;
    for(var i=0;i<ns.length;i++){var a=ns[i].getBoundingClientRect();var nm=ns[i].querySelector('.nm');minFont=Math.min(minFont,parseFloat(getComputedStyle(nm).fontSize)*G.zoom);
      for(var j=i+1;j<ns.length;j++){var b=ns[j].getBoundingClientRect();if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)fail='GEO_FAIL_groups';}}
    var check=$('#geoCheck');if(!check){check=document.createElement('div');check.id='geoCheck';check.hidden=true;document.body.appendChild(check);}
    check.textContent=fail||'GEO_OK visible='+ns.length+' min-font='+minFont;
  }
  function onNode(id){if(!GP.has(id))return;if(!currentShown.has(id)){G.focus=id;G.expanded.clear();G.all=false;G.camera=true;renderNet();}setHash('person',id==='me'?null:id);setHash('dim',null);setHash('expand',null);setHash('view',null);route();}
  function backNet(){G.focus='me';G.expanded.clear();G.all=false;G.zoom=1;G.camera=true;G.query='';var search=$('#person-search');if(search)search.value='';renderNet();setHash('person',null);setHash('dim',null);setHash('expand',null);setHash('view',null);route();}
  var refitColumns=function(){return false;};
  function initColumnDivider(){
    var app=document.querySelector('.app'),bar=$('#column-divider');if(!app||!bar)return;
    var percent=40,active=null,raf=0;
    function apply(value){
      var r=app.getBoundingClientRect(),styles=getComputedStyle(app),w=r.width-parseFloat(styles.paddingLeft)-parseFloat(styles.paddingRight)-24;
      var low=Math.max(28,Math.min(40,320/Math.max(1,w)*100)),high=Math.min(62,Math.max(40,100-380/Math.max(1,w)*100));
      percent=Math.max(low,Math.min(high,value));
      app.style.setProperty('--left-weight',percent+'fr');app.style.setProperty('--right-weight',(100-percent)+'fr');
      bar.setAttribute('aria-valuenow',String(Math.round(percent)));bar.setAttribute('aria-valuetext','关系网 '+Math.round(percent)+'%，详情 '+Math.round(100-percent)+'%');
      if(!raf)raf=requestAnimationFrame(function(){raf=0;G.camera=true;renderNet();route();});
    }
    bar.addEventListener('pointerdown',function(e){if(active!==null||e.button!==0||innerWidth<=900)return;e.preventDefault();active=e.pointerId;try{bar.setPointerCapture(e.pointerId);}catch(ignore){}document.body.classList.add('resizing-columns');});
    bar.addEventListener('pointermove',function(e){if(active!==e.pointerId)return;var r=app.getBoundingClientRect(),s=getComputedStyle(app),left=r.left+parseFloat(s.paddingLeft),w=r.width-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight)-24;apply((e.clientX-left-12)/Math.max(1,w)*100);});
    function stop(e){if(e&&e.pointerId!==active)return;active=null;document.body.classList.remove('resizing-columns');}
    ['pointerup','pointercancel','lostpointercapture'].forEach(function(t){bar.addEventListener(t,stop);});
    window.addEventListener('blur',function(){stop();});
    refitColumns=function(){stop();if(innerWidth<=900||app.classList.contains('wide-graph')||!document.body.classList.contains('view-all'))return false;apply(percent);return true;};
    bar.addEventListener('dblclick',function(){apply(40);});
    bar.addEventListener('keydown',function(e){if(innerWidth<=900)return;if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();apply(percent+(e.key==='ArrowLeft'?-2:2));}else if(e.key==='Home'||e.key==='Enter'){e.preventDefault();apply(40);}});
  }
  function initGraphControls(){
    var search=$('#person-search');if(search)search.addEventListener('input',function(){G.query=search.value;renderList();});
    var reset=$('#graph-reset');if(reset)reset.addEventListener('click',backNet);
    var wide=$('#graph-wide');if(wide)wide.addEventListener('click',function(){var app=document.querySelector('.app');var on=app.classList.toggle('wide-graph');wide.setAttribute('aria-pressed',String(on));wide.textContent=on?'恢复并排':'放大工作区';if(!on&&refitColumns())return;G.camera=true;renderNet();});
    var home=$('#graph-home');if(home)home.addEventListener('click',function(){G.camera=true;renderNet();});
    var map=$('#graph-minimap');if(map){map.addEventListener('click',function(e){if(!currentGeo)return;var r=map.getBoundingClientRect(),ratio=Math.min(r.width/currentGeo.width,r.height/currentGeo.height),ox=(r.width-currentGeo.width*ratio)/2,oy=(r.height-currentGeo.height*ratio)/2,n=$('#net');n.scrollLeft=Math.max(0,(e.clientX-r.left-ox)/ratio*G.zoom-n.clientWidth/2);n.scrollTop=Math.max(0,(e.clientY-r.top-oy)/ratio*G.zoom-n.clientHeight/2);updateOverview();});map.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();G.camera=true;renderNet();}});}
    var net=$('#net');if(net){
      net.addEventListener('scroll',updateOverview);var drag=null;
      net.addEventListener('pointerdown',function(e){if(drag||e.target.closest('.node')||e.button!==0)return;drag={x:e.clientX,y:e.clientY,sx:net.scrollLeft,sy:net.scrollTop,id:e.pointerId};try{net.setPointerCapture(e.pointerId);}catch(ignore){}});
      net.addEventListener('pointermove',function(e){if(!drag||drag.id!==e.pointerId)return;net.scrollLeft=drag.sx+drag.x-e.clientX;net.scrollTop=drag.sy+drag.y-e.clientY;});
      function stopPan(e){if(e&&(!drag||e.pointerId!==drag.id))return;drag=null;}
      ['pointerup','pointercancel','lostpointercapture'].forEach(function(t){net.addEventListener(t,stopPan);});
      window.addEventListener('blur',function(){stopPan();});
      window.addEventListener('resize',function(){stopPan();});
    }
    var all=$('#graph-all');if(all)all.addEventListener('click',function(){G.all=!G.all;G.zoom=1;G.camera=true;renderNet();});
    [['zoom-in',.1],['zoom-out',-.1]].forEach(function(x){var b=$('#'+x[0]);if(b)b.addEventListener('click',function(){G.zoom=Math.max(.85,Math.min(1.8,Math.round((G.zoom+x[1])*100)/100));renderNet();});});
  }

  // ---- 渲染条目 ----
  function itemHtml(it){
    if(it.k)return '<li><b>'+md(it.k)+'：</b>'+md(it.v||'')+'</li>';
    return '<li>'+md(it.t||'')+'</li>';}
  function groupHtml(g){
    if(g.sensitive)return '<div class="subgroup"><h4>'+esc(g.heading||'')+'</h4><div class="lockbox">🔒 这部分只留在你本机，导出/发给外部 AI 时默认不带出</div></div>';
    var inner='';
    if(g.kind==='lead')inner='<div class="lead">'+md(g.items.map(itemText).join(' '))+'</div>';
    else if(g.kind==='timeline')inner='<ul class="tl">'+g.items.map(function(it){
      var txt=itemText(it),m=txt.match(/^\s*((?:19|20)\d{2}(?:[.\-–—~至][^　\s·]*)?)\s*(?:　+|\s·\s+|\s{2,})?/);
      var when=m?m[1]:'';var rest=m?txt.slice(m[0].length):txt;
      return '<li>'+(when?'<span class="when">'+esc(when)+'</span>':'')+md(rest)+'</li>';}).join('')+'</ul>';
    else if(g.kind==='chips')inner='<div class="chips">'+g.items.map(function(it){return '<span class="c">'+md(it.v||it.t||'')+'</span>';}).join('')+'</div>';
    else if(g.kind==='kv')inner='<div class="kvgrid">'+g.items.map(function(it){return '<div class="kv"><b>'+md(it.k||'')+'</b>'+md(it.v||'')+'</div>';}).join('')+'</div>';
    else inner='<ul class="list">'+g.items.map(itemHtml).join('')+'</ul>';
    return '<div class="subgroup"><h4>'+esc(g.heading||'')+'</h4>'+inner+'</div>';}
  function itemText(it){return it.v?(it.k?it.k+'：'+it.v:it.v):(it.t||'');}

  // ---- 我的档案 ----
  function renderMe(expandDim,expandAll){
    var me=D.me,box=$('#doc');var h='';
    h+='<div class="crumbbar"><button id="back-net" type="button" class="backbtn">‹ 返回关系网</button><span class="crumb">关系网 / '+esc(me.name||'我')+'（本人）</span></div>';
    if(D.me_locked){h+='<div class="phead"><div class="avatar">🔒</div><div><h2>未命名</h2><div class="meta locked">名片较敏感，当前按“外发预览”模式不显示（仅本机模拟，未上传）</div></div></div>';}
    else{h+='<div class="phead"><div class="avatar">'+esc(firstHan(me.name||'我'))+'</div><div>'
      +'<h2>'+esc(me.name||'（未命名）')+(me.alt?' <span class="meta">· '+esc(me.alt)+'</span>':'')+'</h2>'
      +'<div class="meta">'+[me.gender,me.city,me.lang].filter(Boolean).map(esc).join(' ｜ ')+'</div>'
      +(me.role?'<div class="meta">'+md(me.role)+'</div>':'')
      +'<div class="ptags">'+(me.tags||[]).map(function(t){return '<span class="tag">'+esc(t)+'</span>';}).join('')+'</div>'
      +(me.links&&me.links.length?'<div class="plinks">'+me.links.map(function(l){return '<a href="'+esc(l.url)+'" target="_blank" rel="noopener">'+esc(l.label)+'</a>';}).join('')+'</div>':'')
      +'</div></div>';}
    h+='<div class="toolbar"><button id="expand-all" type="button">全部展开</button><button id="collapse-all" type="button">全部收起</button></div>';
    h+='<div class="dimgrid">'+D.dims.map(function(d){
      return '<div class="dimcard" role="button" tabindex="0" data-dim="'+esc(d.id)+'"><h3>'+esc(d.title)+' '+lvBadge(d.layer)+'</h3><div class="sub">'+((!d.empty&&!d.locked)?esc(d.sub||''):'')+(d.locked?' · 敏感·本地展开':d.empty?' · 还没告诉我':'')+'</div></div>';}).join('')
      +D.locked_blocks.map(function(b){return '<div class="dimcard'+(b.locked?' locked':'')+'" role="button" tabindex="0" data-block="'+esc(b.id)+'"><h3>'+esc(b.title)+' '+lvBadge(b.layer)+'</h3><div class="sub">'+esc(b.sub||'')+(b.locked?' · 仅本地':b.empty?' · 还没告诉我':'')+'</div></div>';}).join('')+'</div>';
    h+='<div id="medetail"></div>';
    box.innerHTML=h;
    box.querySelectorAll('.dimcard').forEach(function(c){
      function activate(){var id=c.dataset.dim||c.dataset.block;setHash('dim',id);setHash('expand',null);setHash('person',null);route();}
      c.addEventListener('click',activate);
      c.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}});
    });
    var ea=$('#expand-all'),ca=$('#collapse-all');if(ea)ea.addEventListener('click',function(){setAll(true);});if(ca)ca.addEventListener('click',function(){setAll(false);});
    var bn=$('#back-net');if(bn)bn.addEventListener('click',backNet);
    // 展开指定/全部
    // 已记录健康且本次可显示时，默认打开健康概览；没有健康数据则从基本情况开始。
    // 有明确收起指令时不自动展开，敏感/未授权内容不会因此注入。
    var active=expandDim||(expandAll===false&&parseHash().collapsed==='1'?null:(D.locked_blocks.some(function(b){return b.id==='health'&&b.health_table&&!b.locked&&!b.empty;})?'health':'identity'));
    D.dims.concat(D.locked_blocks).forEach(function(d){
      var on=expandAll||(active===d.id);
      var card=box.querySelector('[data-dim="'+d.id+'"],[data-block="'+d.id+'"]');
      if(card)card.classList.toggle('sel',on);
    });
    renderDetail(active,expandAll);
  }
  function setAll(on){
    document.querySelectorAll('#doc .dimcard').forEach(function(c){
      if(c.classList.contains('locked'))return;
      c.classList.toggle('sel',on);
    });
    setHash('dim',null);setHash('expand',on?'all':null);setHash('collapsed',on?null:'1');
    renderDetail(on?'-all':null,on);
  }
  function renderDetail(active,expandAll){
    var box=$('#medetail');if(!box)return;var out='';
    D.dims.forEach(function(d){
      var on=!(d.locked||d.empty)&&(expandAll||active===d.id);if(!on)return;
      out+='<div class="detail"><div class="sect-h">'+esc(d.title)+'</div>';
      if(d.id==='identity'){out+='<div class="kvgrid">'
        +'<div class="kv"><b>称呼</b>'+esc(D.me.name||'')+'</div>'
        +(D.me.alt?'<div class="kv"><b>本名</b>'+esc(D.me.alt)+'</div>':'')
        +(D.me.gender?'<div class="kv"><b>性别/出生</b>'+esc(D.me.gender)+'</div>':'')
        +(D.me.city?'<div class="kv"><b>常驻</b>'+esc(D.me.city)+'</div>':'')
        +(D.me.lang?'<div class="kv"><b>语言</b>'+esc(D.me.lang)+'</div>':'')
        +(D.me.links&&D.me.links.length?'<div class="kv"><b>公开链接</b>'+D.me.links.map(function(l){return '<a href="'+esc(l.url)+'" target="_blank" rel="noopener">'+esc(l.label)+'</a>';}).join(' · ')+'</div>':'')
        +'</div>';}
      else if(d.locked)out+='<div class="lockbox">🔒 这部分较敏感，外发预览时默认不带出（仅本机模拟，未上传）</div>';
      else if(d.empty)out+='<div class="empty">这块你还没跟我聊过，不急，以后聊到我会记上</div>';
      else out+=(d.groups||[]).map(groupHtml).join('');
      out+='</div>';});
    D.locked_blocks.forEach(function(b){
      var on=!(b.locked||b.empty)&&(expandAll||active===b.id);if(!on)return;
      out+='<div class="detail"><div class="sect-h">'+esc(b.title)+'</div>';
      if(b.locked)out+='<div class="lockbox">🔒 这部分较敏感，外发预览时默认不带出（仅本机模拟，未上传）</div>';
      else if(b.empty)out+='<div class="empty">这块你还没跟我聊过，不急，以后聊到我会记上</div>';
      else if(b.health_table)out+=healthTableHtml(b);
      else out+=(b.groups||[]).map(groupHtml).join('');
      out+='</div>';});
    box.innerHTML=out;
  }

  var TREND_TXT={new:'新出现',improved:'好转',worsened:'恶化',persistent:'持续',fluctuating:'波动',resolved:'已恢复',followup_due:'复查到期'};
  function healthTableHtml(b){
    var s=b.health_summary||{};
    var h='<div class="hsummary">';
    h+='异常/临界项 '+(s.abnormal||0)+' 条';
    if(s.review)h+=' · 待核对 '+s.review+' 条';
    if(s.followup)h+=' · 复查到期 '+esc(s.followup);
    h+='（以医生报告为准，不做诊断）</div>';
    var wl=b.health_watchlist||[];
    var WL_NAME={ua:'尿酸',creatinine:'肌酐',alt:'谷丙转氨酶',ast:'谷草转氨酶',ldl_c:'低密度脂蛋白',hdl_c:'高密度脂蛋白',tg:'甘油三酯',tc:'总胆固醇',waist:'腰围',bmi:'BMI',fpg:'空腹血糖',hba1c:'糖化血红蛋白',systolic:'收缩压',diastolic:'舒张压'};
    if(wl.length){
      h+='<div class="wl-strip"><span class="wl-h">关注：</span>'
        +wl.map(function(w){var nm=WL_NAME[w.analyte]||w.item||w.analyte||'';return '<span class="wl-chip">'+esc(nm)
          +(w.reason?'<span class="wl-rs"> · '+esc(w.reason)+'</span>':'')+'</span>';}).join('')
        +'</div>';
    }
    function rowHtml(r){
      var stCls=r.status==='正常'?'st-ok':(r.status==='待核对'?'st-ref':'st-warn');
      var trendTxt, tCls;
      if(r.conf==='high'){
        trendTxt=TREND_TXT[r.trend]||r.trend; tCls='tg-'+r.trend;
      } else if(r.conf==='mid'){
        var midTxt={improved:'大致好转',worsened:'大致上升',resolved:'大致回到正常',persistent:'大致持平'}[r.trend]||'变化';
        trendTxt=midTxt+'（不同机构·仅供参考）';
        tCls='tg-mid';
      } else {
        trendTxt='仅供参考'; tCls='tg-ref';
      }
      var badge = r.tier==='watched' ? ' <span class="watch-badge">关注</span>' : '';
      var extras='';
      if(r.history&&r.history.length){
        extras='<details class="metric-history"><summary>历史 '+r.history.length+' 次</summary>';
        if(r.watch_reason)extras+='<div class="watch-ctx">'+esc(r.watch_reason)+'</div>';
        r.history.forEach(function(p){extras+='<div class="history-point"><span>'+esc(p.date||'日期未记录')+'</span><strong>'+esc(p.raw_value==null?p.value:p.raw_value)+' '+esc(p.unit||'')+'</strong><span>'+esc(p.lab||'机构未记录')+(p.method?' / '+esc(p.method):'')+'</span></div>';});
        extras+='</details>';
      }else if(r.watch_reason){extras='<details class="metric-history"><summary>关注原因</summary><div class="watch-ctx">'+esc(r.watch_reason)+'</div></details>';}
      var x='<tr class="'+(r.tier==='watched'?'row-watched':'')+'"><td class="ht-name">'+esc(r.name)+badge+extras+'</td>'
        +'<td>'+esc(r.value)+' '+esc(r.unit)+'</td>'
        +'<td>'+esc(r.ref||'—')+'</td>'
        +'<td><span class="hstatus '+stCls+'">'+esc(r.status)+'</span></td>'
        +'<td><span class="trend '+tCls+'">'+esc(trendTxt)+'</span></td>'
        +'<td class="ht-meta">'+esc(r.date||'')+(r.lab?'<br>'+esc(r.lab):'')+'</td></tr>';
      return x;
    }
    var all=b.health_table||[];
    var fixed=all.filter(function(r){return r.tier==='fixed';});
    var watched=all.filter(function(r){return r.tier==='watched';});
    var rest=all.filter(function(r){return r.tier==='rest';});
    h+='<div class="htable-wrap"><table class="htable"><thead><tr>'
      +'<th>指标</th><th>最新值</th><th>本院参考</th><th>状态</th><th>趋势</th><th>日期·机构</th></tr></thead><tbody>';
    fixed.forEach(function(r){h+=rowHtml(r);});
    watched.forEach(function(r){h+=rowHtml(r);});
    h+='</tbody></table></div>';
    if(rest.length){
      h+='<details class="rest-fold"><summary>其余 '+rest.length+' 项正常（展开）</summary>'
        +'<table class="htable"><tbody>'
        +rest.map(function(r){return '<tr><td class="ht-name">'+esc(r.name)+'</td><td>'+esc(r.value)+' '+esc(r.unit)+'</td><td colspan="4" class="ht-meta">'+esc(r.status)+' · '+esc(r.date||'')+'</td></tr>';}).join('')
        +'</tbody></table></details>';
    }
    if(b.health_milestones&&b.health_milestones.length){
      h+='<div class="hmilestones"><div class="hm-h">变化里程碑（本人确认）</div>'
        +b.health_milestones.map(function(m){return '<div class="hm-item">· '+esc(m)+'</div>';}).join('')+'</div>';
    }
    return h;
  }

  // ---- 人物档案 ----
  function renderPerson(id){
    var p=null;D.people.forEach(function(x){if(x.id===id)p=x;});
    var box=$('#doc');if(!p){renderMe();return;}
    var rel=esc(meRelation(id));
    var psn=shortName(p.label);
    var fullName=p.is_group ? (p.label||psn) : (p.short||psn);
    var crumbName=(p.is_group)? (p.label||fullName)
      :((p.circle!=='peripheral'&&p.realname&&p.realname!==fullName)?fullName+' · '+p.realname:fullName);
    var avatarTxt=p.is_group ? (p.avatar||[...psn].slice(0,2).join('')) : [...psn].slice(0,2).join('');
    var h='<div class="crumbbar"><button id="back-net" type="button" class="backbtn">‹ 返回关系网</button><span class="crumb">关系网 / '+esc(crumbName)+'</span></div>';
    h+='<div class="phead"><div class="avatar">'+esc(avatarTxt)+'</div><div>'
      +'<h2>'+esc(p.label)+' <span class="meta">'+rel+' · '+(CIRC[p.circle]?'':'')+({inner:'核心圈',close:'重要圈',peripheral:'外围圈'}[p.circle]||'')+'</span></h2>'
      +'<div class="meta">'+(p.summary?esc(p.summary):'')+'</div></div></div>';
    h+=pathway(id)+'<button type="button" id="focus-person">查看 '+esc(nameOf(id))+' 的关联</button>';
    h+=(p.zones||[]).map(groupHtml).join('')+relatedHtml(id);
    box.innerHTML=h;
    var bn=$('#back-net');if(bn)bn.addEventListener('click',backNet);
    var fp=$('#focus-person');if(fp)fp.addEventListener('click',function(){focusOn(id);});
    bindPath(box);
  }

  function route(){
    var q=parseHash();var pid=q.person;
    // view 三态：network=仅左栏关系网 / profile=仅右栏档案 / all=左右（默认）；非法回退 all
    var v=q.view;if(['network','profile','all'].indexOf(v)<0)v=D.meta.view||'all';
    document.querySelectorAll('.person-nav').forEach(function(b){b.classList.toggle('active',b.dataset.person===(pid||'me'));});
    var previousView=document.body.classList.contains('view-all');
    document.body.classList.remove('view-network','view-profile','view-all');
    document.body.classList.add('view-'+v);
    if(v==='all'&&!previousView)refitColumns();
    var activePath=pid?MCGraph.path(graph,'me',pid):null;
    document.querySelectorAll('#net .edge').forEach(function(e){var touched=pid&&(e.dataset.from===pid||e.dataset.to===pid);var onPath=activePath&&activePath.edges.some(function(a){return a.from===e.dataset.from&&a.to===e.dataset.to;});e.classList.toggle('hl',!!(touched||onPath));e.classList.toggle('muted',!!pid&&!touched&&!onPath);});
    document.querySelectorAll('#net .node').forEach(function(n){n.classList.toggle('sel',n.dataset.id===pid);});
    if(v==='network'){var nb=$('#doc');if(nb)nb.innerHTML='';return;}
    if(validId(pid)&&D.people.some(function(x){return x.id===pid;})){renderPerson(pid);}
    else{renderMe(q.dim||null,q.expand==='all');}
  }
  window.addEventListener('hashchange',function(){var id=parseHash().person;if(GP.has(id)&&!currentShown.has(id)){G.focus=id;G.expanded.clear();G.camera=true;renderNet();}route();});
  var rzT;window.addEventListener('resize',function(){clearTimeout(rzT);rzT=setTimeout(function(){if(!refitColumns()){G.camera=true;renderNet();}},60);});
  initColumnDivider();initGraphControls();document.querySelector('.app').classList.toggle('small-network',D.people.length<=8);renderNet();route();
  }catch(e){console.error(e);var box=document.getElementById('net');if(box)box.textContent='关系图暂时无法展开，记录仍保存在本地。请重新生成图谱。';}
})();
"""


def build_html(payload, view, data):
    meta = payload["meta"]
    skip = ""
    if payload["skipped"]:
        skip = ('<p class="banner">未分级/头部异常已跳过 ' + str(len(payload["skipped"]))
                + ' 项：' + "、".join(html.escape(x) for x in payload["skipped"]) + "</p>")
    l4_warn = ""
    if meta["l4_revealed"]:
        l4_warn = ('<div class="warn">⚠ 已按 --show-l4 展开 L4 秘密层，禁止上传云端/外发，仅本机查看。</div>'
                   "<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in payload["l4"]["items"]) + "</ul>")
    elif meta["l4_count"]:
        l4_warn = f'<p class="banner">有 {meta["l4_count"]} 条 L4 秘密未展示（--show-l4 才展开）。</p>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>我的个人图谱</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%234c6ef5'/%3E%3Ccircle cx='16' cy='16' r='5' fill='white'/%3E%3Ccircle cx='7' cy='7' r='2' fill='white'/%3E%3Ccircle cx='25' cy='25' r='2' fill='white'/%3E%3C/svg%3E">
<style>{CSS}</style></head><body>
<div class="app">
  <aside class="col-left"><div class="card graph-card">
    <div class="graph-heading"><h2>我和身边的人</h2><button type="button" id="graph-reset">回到我</button></div>
    <p class="hint">你在中心，亲近的人在内侧。点人物看记录，点 + 展开关联；拖动画布看关系，用 + / − 缩放。</p>
    <div id="focus-path"></div>
    <div class="graph-controls"><button type="button" id="graph-all" aria-pressed="false">全部关系</button><button type="button" id="graph-home">居中</button><button type="button" id="graph-wide" aria-pressed="false">放大工作区</button><button type="button" id="zoom-out" aria-label="缩小关系图">−</button><span id="zoom-label">100%</span><button type="button" id="zoom-in" aria-label="放大关系图">+</button></div>
    <p id="graph-status"></p><div id="net" tabindex="0" aria-label="关系图，拖拽平移，使用按钮缩放"></div>
    <div id="graph-overview" class="graph-overview" hidden><svg id="graph-minimap" role="button" tabindex="0" aria-label="关系网导航，点击定位；回车返回本人"></svg><p>这是当前展开关系的全貌。<br>点缩略图定位，主图保留姓名大小；可搜索或继续展开。</p></div>
    <div class="graph-key"><span><i style="background:#487891"></i>核心圈</span><span><i style="background:#849784"></i>重要圈</span><span><i style="background:#a8b3bf"></i>外围圈</span><span>亲近度不是关系步数</span></div>
    <div class="graph-search"><label for="person-search">找一个人</label><input id="person-search" type="search" placeholder="输入姓名或称呼" autocomplete="off"><p class="hint" id="people-count"></p><nav class="side-people" id="people-list" aria-label="人物导航"></nav></div>
  </div></aside>
  <div id="column-divider" class="column-divider" role="separator" tabindex="0" aria-label="调整关系网与详情的宽度，双击恢复四六分" aria-orientation="vertical" aria-valuemin="28" aria-valuemax="62" aria-valuenow="40" title="左右拖动调节宽度，双击恢复四六分"><span class="divider-grip" aria-hidden="true"></span></div>
  <main class="col-right"><div class="card" id="doc"></div>
    {l4_warn}{skip}
    <p class="meta">更新于 {meta['now']}<br>这份图谱在本机生成，没有上传。记录可查看、修改或删除。</p>
  </main>
</div>
<script type="application/json" id="mc-data">{_json_safe(payload)}</script>
<!-- 实现约束：确定性渲染、无黑盒；这些内部说明不占用用户界面。 -->
<script>{GRAPH_MODEL}
{JS}</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description="me-context 个人知识图谱（左导航+右档案，纯原生零外链）")
    ap.add_argument("--data", required=True)
    ap.add_argument("--view", choices=["profile", "network", "all"], default="all")
    ap.add_argument("--audience", choices=["local", "cloud"], default="local")
    ap.add_argument("--layers", default="", help="可选，逗号分隔 L0,L1,...（仅 local 过滤）")
    ap.add_argument("--show-l4", action="store_true", help="仅 local 展开 L4 明文，默认不展开")
    ap.add_argument("--reveal-l3-entities", action="store_true",
                    help="兼容旧参数：v10 人物节点照常显示，仅按分区过滤敏感内容")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    data = os.path.abspath(args.data)
    if not os.path.isdir(data):
        print(f"[错误] 数据仓不存在：{data}", file=sys.stderr)
        return 2

    layer_set = set()
    for x in args.layers.split(","):
        x = x.strip().upper()
        if x:
            layer_set.add(x)

    payload = build_payload(data, args.audience, layer_set,
                            args.show_l4, args.reveal_l3_entities, args.view)
    # 常规查看永远覆盖同一份最新图谱；脱敏版使用另一个固定文件，避免覆盖私人本地版。
    out = args.out or os.path.join(data, "exports",
                                  "我的个人图谱.html" if args.audience == "local" else "我的个人图谱-脱敏版.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_html(payload, args.view, data))
    os.chmod(out, 0o600)  # 本地版带着健康/家人明文，只给本人看

    print(f"[viz] {out}")
    print(f"  视图={args.view} audience={args.audience} 实体={len(payload['people'])} "
          f"边={len(payload['edges'])} 维度={len(payload['dims'])}")
    if payload["skipped"]:
        print(f"  已跳过/提示 {len(payload['skipped'])} 项：{', '.join(payload['skipped'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
