"""mectx_common: me-context 三工具共用的确定性函数（纯 Python3 标准库）。

集中三处此前各自实现、容易漂移的逻辑：
  - frontmatter 解析（含"缺结尾 ---"判定 = 头部异常）
  - layer 规范化与校验（strip + upper；非法一律 None，绝不静默降级 L1）
  - domain 映射与白名单
  - 路径安全（防 ../ 越出数据仓）

lint / gate / export 全部 import 本模块，保证同一份坏 frontmatter 在三个工具里
结论一致：lint 报 ERROR、gate 不加载且非 0、export 跳过且非 0。
"""
import os
import re
from datetime import date, datetime

import health_records as HR
# ---- domain 映射与白名单（唯一事实源） ----
DOMAIN_FILE = {
    "work": "profile/work.md",
    "goals": "profile/goals.md",
    "preferences": "profile/preferences.md",
    "decisions": "profile/decisions.md",
    "body": "profile/body.md",
    "health": "profile/health.md",
    "finance": "profile/finance.md",
    "network": "network.md",
}
DOMAIN_DEFAULT_LAYER = {
    "work": "L1", "goals": "L1", "preferences": "L1",
    "decisions": "L2", "body": "L2", "health": "L3", "finance": "L3", "network": "L2",
}

# 采集时机门槛（信任梯度 T0/T1/T2）——与读取层级 L0-L4 相互独立，别混用：
#   T0 = onboarding 建档即可问（低敏/半公开事实与通用偏好）
#   T1 = 建立信任后/按需顺带问（中敏，不做固定轮次）
#   T2 = 高敏，绝不主动批量问；只在用户当次任务确实需要、说明用途、用户愿意给时就事问最小一条
# 未列出的域默认 T0。这是"什么时候可以问"，不是"读到第几层"。
DOMAIN_ASK_GATE = {
    "finance": "T2-need-trigger",
    "health": "T2-need-trigger",
    "network": "T1",
    "body": "T0",
    "work": "T0",
    "preferences": "T0",
    "goals": "T0",
    "decisions": "T0",
}
DEFAULT_ASK_GATE = "T0"
VALID_DOMAINS = tuple(DOMAIN_FILE.keys())

LAYERS = ("L0", "L1", "L2", "L3", "L4")
SOURCES = {"declared", "inferred", "observed"}
CIRCLES = {"inner", "close", "peripheral"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ---- 两层结构：结论层（做判断时按域加载）/ 过程层 journal/（默认不加载、不导出）----
# 结论层回答"现在是什么情况"（尿酸偏高、在服某药、过敏）；过程层放"细节和经过"：
# 体检指标明细（最新值 + 历史快照）、重要决定及当时的理由。只在问数值/趋势/做复盘时才读。
JOURNAL_DIR = "journal"
HEALTH_METRICS_FILE = "journal/health-metrics.md"
DECISIONS_LOG_FILE = "journal/decisions.md"
MIGRATE_BACKUP_DIR = ".migrate-backup"  # migrate.py 写前备份；不导出、不 lint、不进版本记录
# 指标明细小节：迁移时整节从 profile/health.md 挪到 HEALTH_METRICS_FILE
HEALTH_DETAIL_HEADINGS = ("最新关键指标", "历史快照")
# audience=local：作者声明"只在本机用"。外发（cloud）时与 L3 一样要逐次确认。
LOCAL_AUDIENCE = "local"


def audience_local(meta):
    """frontmatter audience 是否声明为只在本机（大小写/空白不敏感）。"""
    return str((meta or {}).get("audience") or "").strip().lower() == LOCAL_AUDIENCE


def outgoing_layer(layer, meta):
    """外发时按哪一层对待：标了 audience: local 的低层文件与 L3 一样，要显式放开才带出去。
    gate 的确认、md 导出、viz 脱敏版共用这一条。"""
    if audience_local(meta) and layer in ("L0", "L1", "L2"):
        return "L3"
    return layer


def read_health_body(data):
    """读健康全文：结论层 profile/health.md + 过程层 journal/health-metrics.md。

    给趋势/看板/体检用（本机），不经 gate 外发。迁移前后解析结果一致：指标小节原样拼接。
    """
    parts = []
    for rel in (DOMAIN_FILE["health"], HEALTH_METRICS_FILE):
        p = safe_join(data, rel)
        if p and os.path.isfile(p) and not os.path.islink(p):
            with open(p, encoding="utf-8") as f:
                _meta, body = parse_frontmatter(f.read())
            parts.append(body)
    return "\n\n".join(parts)


STATUS_HEADING = "当前状态"


def health_status_lines(latest):
    """最新指标里需要留意的项 → 结论层「当前状态」的人话行（只写方向，不写数值）。"""
    lines = []
    for r in latest:
        st = HR.status(r)
        if st in HR.ABNORMAL:
            label = HR.LABELS.get(r["name"], r["name"])
            when = f"（{r['date']}）" if r.get("date") else ""
            lines.append(f"- {label}：{st}{when}")
    return lines

# ---- 时效 freshness（v11 收录宪法 §7；可选字段，缺省按域默认，不改层门禁）----
# stable = 基本不变的身份/禁忌/长期偏好；current = 在做什么/近期目标/当前方向，易过期。
FRESHNESS = ("stable", "current")
FRESHNESS_DEFAULT = {
    "identity": "stable",
    "work": "current",
    "goals": "current",
    "preferences": "stable",
    "decisions": "stable",
    "body": "stable",
    "health": "stable",
    "finance": "stable",
    "network": "stable",
    "relations": "stable",
}
# 复核周期（天）：stable 90–180 取 180；current 30–90 取 60。超期仅弱提示，不阻断、不改层。
REVIEW_DAYS = {"stable": 180, "current": 60}
# current 超过该天数 → 体检建议"还成立吗？不成立就清/转历史"（180 天）。
STALE_HARD_DAYS = 180


def parse_iso_date(raw):
    """YYYY-MM-DD → date；非法/空返回 None（不编造、不抛）。"""
    if not isinstance(raw, str) or not DATE_RE.match(raw):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def freshness_of(meta):
    """文件时效：显式 freshness 优先；缺失只按文件自身 meta.domain 查默认表，兜底 stable。
    请求域（gate 的 --domain）不参与时效兜底，避免跨域误报。"""
    f = (meta or {}).get("freshness")
    if f in FRESHNESS:
        return f
    return FRESHNESS_DEFAULT.get((meta or {}).get("domain"), "stable")


def _review_days(meta, f):
    """frontmatter review_cycle（如 15d/90d/180d）覆盖默认复核周期；非法/缺失回退默认。"""
    rc = (meta or {}).get("review_cycle")
    if isinstance(rc, str):
        m = re.fullmatch(r"\s*(\d+)\s*d\s*", rc.strip(), re.I)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 3650:
                return n
    return REVIEW_DAYS[f]


def freshness_status(meta, domain=None, today=None):
    """返回 None（现行/无日期）或 dict：
      {"level":"archived"}                       # stale:true 已归档
      {"level":"stale","age":n,"updated":d,
       "review":rd,"freshness":f,"hard":bool}    # 超复核期；hard=True 表示超 180 天建议清理
    只读 frontmatter，绝不改层、绝不 fail-closed。domain 参数保留兼容但不参与判定。
    """
    meta = meta or {}
    if meta.get("stale") is True:
        return {"level": "archived"}
    f = freshness_of(meta)
    # stable（身份/禁忌/长期偏好）基本不变，不因年老误报过期；只有 current 按龄复核。
    if f != "current":
        return None
    rd = _review_days(meta, f)
    d = parse_iso_date(meta.get("updated"))
    if d is None:
        return None
    today = today or date.today()
    age = (today - d).days
    if age <= rd:
        return None
    return {"level": "stale", "age": age, "updated": meta.get("updated"),
            "review": rd, "freshness": f, "hard": age > STALE_HARD_DAYS}


# lint 豁免：这些文件不要求"完整合法 frontmatter"
LINT_EXEMPT_BASENAMES = {"relations.md", "CHANGELOG.md", ".gitkeep", "CONSENT-health.md"}
LINT_EXEMPT_DIRS = {"inbox", "exports", "private", ".git", "journal"}
LINT_EXEMPT_PREFIX = ("README", "_README")


def strip_html_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def parse_frontmatter(text):
    """解析 frontmatter。返回 (meta, body)。

    - 文件没有以 --- 开头、或开了 --- 但缺结尾 --- → 返回 (None, text)，
      这就是"头部异常"，三工具统一按异常处理，不当作无层级放行。
    """
    text = strip_html_comments(text).lstrip()
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, text

    meta = {}
    for raw in lines[1:end]:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", raw.strip())
        if not m:
            continue
        meta[m.group(1)] = _scalar(_strip_inline_comment(m.group(2).strip()))
    return meta, "\n".join(lines[end + 1:])


def _strip_inline_comment(v):
    """按 YAML 规则去掉行内注释（空白后的 #）。模板里有 `scope: off  # full | ...` 这类写法，
    不去掉的话 `audience: local  # 只在本机` 会认不出 local，外发时不拦。引号内的 # 保留。"""
    if v[:1] in ("'", '"'):
        end = v.find(v[0], 1)
        return v[:end + 1] if end > 0 else v
    if v.startswith("#"):  # `style:   # 可选 ...`：值为空，后面整段是注释
        return ""
    return re.sub(r"\s+#.*$", "", v)


def _scalar(v):
    v = v.strip()
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no", "null", "none", "~"):
        return None
    if v.isdigit():
        return int(v)
    return v.strip("\"'")


def normalize_layer(raw):
    """规范化 layer：strip + upper。合法返回 L0-L4；非法/空/乱码返回 None。

    严禁任何形式的静默降级（如缺层默认 L1）。"l3" → "L3"（合法）；
    "l9"/"" /乱码 → None。
    """
    if raw is None:
        return None
    s = re.sub(r"\s+", "", str(raw)).upper()
    if re.fullmatch(r"L[0-4]", s):
        return s
    return None


def file_layer(path):
    """读取一个档案文件，返回其规范化 layer。

    返回值：
      (layer, meta, ok)  ok=False 表示头部异常（无/坏 frontmatter），
      此时 layer=None；调用方必须按"未分级/异常"处理，不得当 L1。
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    meta, _body = parse_frontmatter(text)
    if meta is None:
        return None, None, False
    layer = normalize_layer(meta.get("layer"))
    return layer, meta, True


def safe_join(data, rel):
    """把相对路径 rel 拼到数据仓 data 下，防 ../ 越出数据仓。

    越界返回 None。中间目录是符号链接也返回 None（不跟随：entities/ 链到 journal/
    或仓外，都会绕过分片边界）；末端文件是不是链接由调用方判断并提示。
    """
    data = os.path.abspath(data)
    cand = os.path.normpath(os.path.join(data, rel))
    if cand != data and not cand.startswith(data + os.sep):
        return None
    cur = data
    for part in os.path.relpath(cand, data).split(os.sep)[:-1]:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            return None
    return cand


def rel_of(path, data):
    return os.path.relpath(path, data).replace("\\", "/")


def iter_data_files(data, include_private=False, extra_exclude_dirs=(), include_journal=False):
    """遍历数据仓下的文件，yield (rel, abs, is_link)。

    统一安全规则：**不跟随符号链接**（is_link=True 的项由调用方跳过，绝不读链接目标）。
    默认排除 inbox/ exports/ .git/ .migrate-backup/ journal/（过程层）；private/ 仅 include_private 时进入。
    迁移备份是改动前的原文件，文件名不对应任何分片，健康授权裁剪认不出，所以一律不遍历。
    """
    excluded = {"exports", "inbox", ".git", MIGRATE_BACKUP_DIR} | set(extra_exclude_dirs)
    if not include_private:
        excluded.add("private")
    if not include_journal:
        excluded.add(JOURNAL_DIR)
    for root, dirs, files in os.walk(data):
        dirs[:] = sorted(d for d in dirs
                          if d not in excluded and not os.path.islink(os.path.join(root, d)))
        for fn in sorted(files):
            fp = os.path.join(root, fn)
            rel = rel_of(fp, data)
            if os.path.islink(fp):
                yield rel, fp, True
                continue
            yield rel, fp, False


def sniff_declared_l4(path):
    """defense-in-depth：文件解析为"头部异常/未分级"时，保守嗅探是否独立声明 L4。

    扫残头/正文中独立的 `layer:\\s*L4` 键值（大小写/空白不敏感），命中即视为"声明了 L4"。
    L4 声明优先级高于"未分级放行"——即使坏头也按 L4 处置，仅 --include-private / --include-l4 才纳入。
    不做完整 frontmatter 解析，只求宁可错杀不漏放。
    """
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    return re.search(r"(?im)^\s*layer\s*:\s*L4\s*(?:#.*)?$", text) is not None


# ---- 健康本地授权门（v12）：与 L3 云门是两道独立开关。纯 Markdown，fail-closed。 ----
CONSENT_FILE = "CONSENT-health.md"
HEALTH_SCOPES = ("full", "facts_only", "index_only", "off")
# 高值为坏（升高=恶化）的指标；低值为坏的（HDL-C/egfr）另行处理。
HIGH_BAD = {"tc", "ldl_c", "tg", "ua", "alt", "ast", "ck", "creatinine", "systolic", "diastolic", "fpg", "hba1c", "bmi", "waist"}
LOW_BAD = {"hdl_c", "egfr"}


def parse_consent(data):
    """读取根目录 CONSENT-health.md 本地授权。缺文件/坏头/granted!=true/scope=off → 未授权（fail-closed）。

    返回 dict：present, granted, scope(full/facts_only/index_only/off), granted_date, source, updated, style,
    allowed(bool)。style 只改怎么说（direct|gentle），不改能不能访问。只读，绝不写。
    """
    res = {"present": False, "granted": False, "scope": "off",
           "granted_date": None, "source": None, "updated": None,
           "style": None, "allowed": False}
    path = safe_join(data, CONSENT_FILE)
    if not path or not os.path.isfile(path) or os.path.islink(path):
        return res
    try:
        meta, _body = parse_frontmatter(open(path, encoding="utf-8").read())
    except OSError:
        return res
    if meta is None:
        return res
    res["present"] = True
    res["granted"] = meta.get("granted") is True
    scope = str(meta.get("scope") or "off").strip().lower()
    res["scope"] = scope if scope in HEALTH_SCOPES else "off"
    res["granted_date"] = meta.get("granted_date")
    res["source"] = meta.get("source")
    res["updated"] = meta.get("updated")
    style = str(meta.get("style") or "").strip().lower()
    res["style"] = style if style in ("direct", "gentle") else None
    res["allowed"] = bool(res["granted"] and res["scope"] != "off")
    return res


def _metric_rows(section_text):
    """兼容入口：由 health_records 负责无损指标解析与规范化。"""
    return HR.metric_rows(section_text)


def _row_date_key(row):
    """行日期排序键：YYYY-MM-DD / YYYY-MM / YYYY 前缀；缺日期排最前（最不可能是"最近一次"）。"""
    m = re.match(r"(\d{4})(?:[-./](\d{1,2}))?(?:[-./](\d{1,2}))?", (row.get("date") or "").strip())
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0))


def health_sections(body):
    """返回规范化最新指标与历史时间点；兼容规范行和有限旧版人话快照。"""
    return HR.sections(body)


def history_by_analyte(hist):
    """把历史行按指标分组并按日期**从新到旧**排序：{name: [最近一次, 次近, …]}。
    趋势比较基准 = 列表第 0 项（最近一次），而不是文本里出现的第一条。"""
    out = {}
    for r in hist:
        out.setdefault(r["name"], []).append(r)
    for k in out:
        out[k].sort(key=_row_date_key, reverse=True)
    return out


# ---------------------------------------------------------------------------
# 关注因子 watchlist（只改呈现重点/详略，不诊断、不硬安病）
# 构建只读健康分片（health.md + body.md 运动/目标），绝不读 finance 等无关分片。

# auto 映射：已记录的既往/用药关键词 → 相关指标（克制，宁少勿滥；无病史正常人不触发）
# 每项 = (关键词元组, canonical 指标名, 人话关联原因)
AUTO_WATCH_RULES = [
    (("痛风", "高尿酸", "尿酸高"), "ua", "痛风/高尿酸史→盯尿酸与肾功能"),
    (("痛风", "高尿酸", "尿酸高"), "creatinine", "痛风/高尿酸史→盯肾功能（肌酐）"),
    (("脂肪肝", "肝功异常", "转氨酶高", "alt高", "ast高"), "alt", "脂肪肝/肝功异常→盯转氨酶"),
    (("脂肪肝",), "ldl_c", "脂肪肝史→盯血脂（LDL-C）"),
    (("脂肪肝",), "waist", "脂肪肝史→盯腰围"),
    (("高血压",), "systolic", "高血压史→盯收缩压"),
    (("高血压",), "diastolic", "高血压史→盯舒张压"),
    (("高血压",), "creatinine", "高血压史→盯肾功能（肌酐）"),
    (("糖尿病", "糖代谢", "hba1c高", "血糖偏高"), "fpg", "糖代谢史→盯空腹血糖"),
    (("糖尿病", "糖代谢", "hba1c高"), "hba1c", "糖代谢史→盯 HbA1c"),
    (("糖尿病", "糖代谢"), "creatinine", "糖代谢史→盯肾功能"),
    (("血脂异常", "高血脂", "ldl高", "胆固醇高", "甘油三酯高"), "ldl_c", "血脂史→盯 LDL-C"),
    (("血脂异常", "高血脂", "甘油三酯高"), "tg", "血脂史→盯甘油三酯"),
    (("他汀",), "ldl_c", "在服他汀→监测 LDL-C"),
    (("他汀",), "alt", "在服他汀→监测转氨酶"),
    (("降压药",), "systolic", "在服降压药→监测血压"),
]

# watchlist 小节里每条 bullet 的可识别来源；proposed 未确认不生效
_WL_SOURCE = ("stated", "proposed_confirmed", "auto", "proposed")


def parse_watchlist(body):
    """从 health.md 的 `## 关注因子（watchlist）` 小节解析条目。
    bullet 形如：`- 尿酸 ua | 来源 stated | 原因 痛风史继续盯`；
    删除（~~ strikethrough 或含「已删除/删除」）→ deleted；proposed（未确认）→ 不生效。
    返回 (active:[{item,analyte,source,reason}], deleted:{analyte})。"""
    active, deleted = [], set()
    m = re.search(r"##\s*关注因子[（(]watchlist[)）].*?\n(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    if not m:
        return active, deleted
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        raw = line.lstrip("- ").strip()
        # 模板示例/占位行（<例：…>、<…>）不是用户条目，一律跳过
        if raw.startswith("<") or "<例" in raw:
            continue
        struck = "~~" in raw or ("删除" in raw and "不" not in raw.split("删除")[0][-3:])
        # 解析键值：指标/analyte、来源 source、原因 reason
        cells = [c.strip() for c in raw.split("|")]
        kv = {}
        head = cells[0] if cells else ""
        for c in cells[1:]:
            if " " in c:
                k, v = c.split(" ", 1)
                kv[k.strip()] = v.strip()
        # 指标名：显式 analyte 优先，否则取首词
        analyte = (kv.get("analyte") or kv.get("指标") or "").strip().lower()
        label = head.strip("~~ ").strip()
        if not analyte:
            # 首词可能是英文 canonical 名
            tok = re.search(r"[a-z_][a-z0-9_]+", label)
            analyte = tok.group(0) if tok else ""
        source = (kv.get("来源") or kv.get("source") or "").strip().lower()
        reason = kv.get("原因") or kv.get("reason") or ""
        if struck:
            if analyte:
                deleted.add(analyte)
            continue
        if source == "proposed":  # AI 提议未 confirmed → 不置顶、不生效
            continue
        active.append({"item": label, "analyte": analyte,
                       "source": source if source in _WL_SOURCE else "stated",
                       "reason": reason})
    return active, deleted


# auto 扫描只看"本人正向事实"：这些小节不扫（清单自身/结论原文/家族史/指标表/历史/原件/授权说明）
_AUTO_SKIP_HEADINGS = ("关注因子", "watchlist", "家族", "结论", "最新关键指标", "历史快照", "当前状态",
                       "变化里程碑", "原件索引", "do-not", "授权状态")
# 行内否定/非本人/占位：命中即整行不参与 auto（宁少勿滥，宁可漏关联也不给正常人硬安病）
_AUTO_NEG_RE = re.compile(r"否认|未见|未发现|未提示|无明显|排除|没有|不是|阴性|"
                          r"父亲|母亲|爸爸|妈妈|父母|爷爷|奶奶|外公|外婆|姥姥|姥爷|祖父|祖母|"
                          r"兄弟|姐妹|哥哥|姐姐|弟弟|妹妹|家族|亲属|家人|配偶|老婆|老公|妻子|丈夫|孩子")


def _auto_scan_text(text):
    """抽出可用于 auto 关联的"本人正向事实"行：跳过 _AUTO_SKIP_HEADINGS 小节、frontmatter、
    引用说明行(>)、模板占位行(<例…>/<…>)、否定/亲属行。正常人与空白模板 → 空串。"""
    keep = []
    skip = False
    lines = (text or "").splitlines()
    start = 0
    # 跳过文件头 frontmatter（首行 --- 到下一个 ---）
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                start = j + 1
                break
    for line in lines[start:]:
        s = line.strip()
        if s.startswith("#"):
            head = s.lstrip("#").strip().lower()
            skip = any(k.lower() in head for k in _AUTO_SKIP_HEADINGS)
            continue
        if skip or not s or s.startswith(">"):
            continue
        if "<" in s and ">" in s:  # 模板占位 <例：…>
            continue
        if _AUTO_NEG_RE.search(s):
            continue
        keep.append(s)
    return "\n".join(keep).lower()


def derive_watchlist(health_body, body_goal=""):
    """合并 stated/proposed_confirmed（小节）+ auto 既往/用药映射 + body 显式目标。
    去重、尊重用户删除（删除后不再自动重加，除非新事实且未在 deleted 集合——这里直接尊重删除标记）。
    只扫描传入的健康/目标文本，不打开任何无关分片（如 finance）。
    auto 只扫本人正向事实（见 _auto_scan_text）：否认句、未见、亲属/家族史、模板占位、
    watchlist 小节（含 proposed 未确认条目的原因）与结论原文都不触发，避免给正常人硬安病。"""
    active, deleted = parse_watchlist(health_body)
    seen = {a["analyte"] for a in active if a["analyte"]}
    out = [dict(a) for a in active if a["analyte"] not in deleted]

    # auto：仅由已记录的本人既往/用药正向事实触发；正常人无关键词 → 空
    scan = _auto_scan_text(health_body)
    for keys, analyte, reason in AUTO_WATCH_RULES:
        if analyte in deleted or analyte in seen:
            continue
        if any(k.lower() in scan for k in keys):
            out.append({"item": analyte, "analyte": analyte,
                        "source": "auto", "reason": reason})
            seen.add(analyte)

    # body.md 显式目标（stated，非病名）：健身/备赛/备孕 等作为个人目标关注，不映射成病
    # 同样过滤模板占位与否定句（如"<例：…健身…>""不健身"不算目标）
    goal = _auto_scan_text(body_goal)
    if goal:
        gl = goal.lower()
        for tag, label, reason in (
            ("备赛", "备赛", "个人目标：备赛期关注训练相关指标"),
            ("健身", "健身", "个人目标：健身期关注肌肉相关指标"),
            ("备孕", "备孕", "个人目标：备孕（只记录，不做生育诊断）"),
        ):
            if tag in goal and label not in seen:
                out.append({"item": label, "analyte": "", "source": "stated", "reason": reason})
                seen.add(label)
    return out


def watch_tier(rows, watch_analytes):
    """把最新指标行分三档：fixed=异常项（固定呈现，兜底）；
    watched=在关注清单且本次正常（也显示+情境句）；rest=其余正常（只计数索引，折叠）。"""
    watched = set(watch_analytes)
    fixed, watched_rows, rest = [], [], []
    for r in rows:
        if r.get("status") in ("偏高", "偏低"):
            fixed.append(r)
        elif r.get("name") in watched:
            watched_rows.append(r)
        else:
            rest.append(r)
    return fixed, watched_rows, rest


# 运动性升高守卫：这些指标在练后/高强度/脱水采血时，单次升高不判 worsened（ALT/AST/肌酐/UA/CK）
EXERCISE_GUARD = {"alt", "ast", "creatinine", "ua", "ck"}
EXERCISE_RE = re.compile(r"练后|训练后|高强度|运动后|剧烈运动|脱水")
# 可信置信度（仅这些驱动方向；single_measurement/inferred 不单独驱动）
TRUSTED_CONFIDENCE = {"confirmed", "doctor_diagnosed", "imported_report", ""}

# 三级置信：仅标准化生化项可在单位归一后做"中置信·仅供参考"软方向。
# 归一到 canonical；非表内项、单位无法归一 → 不可比，不判方向。不伪算精确 RCV，只做生活辅助级判读。
# {name: {单位(小写): (canonical_unit, 乘数, 归一方向)}}；canonical 自身乘数 1.0。
_UNIT_NORMALIZE = {
    "ua": {
        "μmol/l": ("μmol/L", 1.0), "umol/l": ("μmol/L", 1.0), "μmol": ("μmol/L", 1.0),
        "mg/dl": ("μmol/L", 59.48),
    },
    "fpg": {
        "mmol/l": ("mmol/L", 1.0), "mmol": ("mmol/L", 1.0),
        "mg/dl": ("mmol/L", 1.0 / 18.0),
    },
    "creatinine": {
        "μmol/l": ("μmol/L", 1.0), "umol/l": ("μmol/L", 1.0), "μmol": ("μmol/L", 1.0),
        "mg/dl": ("μmol/L", 88.4),
    },
    # 血脂：mg/dL→mmol/L 近似换算（TC/LDL/HDL ÷38.67，TG ÷88.57；生活辅助级，非精确）
    "tc": {
        "mmol/l": ("mmol/L", 1.0), "mmol": ("mmol/L", 1.0),
        "mg/dl": ("mmol/L", 1.0 / 38.67),
    },
    "ldl_c": {
        "mmol/l": ("mmol/L", 1.0), "mmol": ("mmol/L", 1.0),
        "mg/dl": ("mmol/L", 1.0 / 38.67),
    },
    "hdl_c": {
        "mmol/l": ("mmol/L", 1.0), "mmol": ("mmol/L", 1.0),
        "mg/dl": ("mmol/L", 1.0 / 38.67),
    },
    "tg": {
        "mmol/l": ("mmol/L", 1.0), "mmol": ("mmol/L", 1.0),
        "mg/dl": ("mmol/L", 1.0 / 88.57),
    },
}


def _normalize_unit(name, value, unit):
    """把该指标的数值/单位归一到 canonical；不在表内或单位无法识别 → (None, None)。"""
    table = _UNIT_NORMALIZE.get((name or "").lower())
    if not table:
        return None, None
    key = (unit or "").strip().lower()
    if key in table:
        canon, factor = table[key]
        return value * factor, canon
    return None, None


# 方法相容族：同一指标的相近方法归为一族（跨院可中置信软方向）；族外/不同方法 → 不可比。
# 仅收录明确等效的常用方法，宁严勿宽。
_METHOD_FAMILIES = [
    {"己糖激酶", "hexokinase", "hk", "葡萄糖氧化酶", "氧化酶法", "葡萄糖氧化", "god"},  # 血糖
    {"尿酸酶", "uricase", "尿酸过氧化物酶"},  # 尿酸
]

# 方法空白时仍可跨院中置信比较的"通用标准化项"：国内体检报告普遍不写检测方法，
# 这些项目常规方法高度统一（血脂/血糖/尿酸/肌酐/转氨酶/血压/体测）——生活辅助级可比，配"仅供参考"。
# 不在此表（如 hba1c 不同色谱法/CK 不同偶联法差异较大）方法空白 → 仍不可比。
_STANDARD_ANALYTES = {"ua", "fpg", "creatinine", "tc", "ldl_c", "hdl_c", "tg",
                      "alt", "ast", "systolic", "diastolic", "bmi", "waist"}


def _methods_compatible(m1, m2, name=""):
    """两方法是否相容：完全相同，或同属一个等效方法族；
    任一方未写方法时，仅通用标准化项（_STANDARD_ANALYTES）视为相容（中置信），其余不相容。
    两方都写了且明显不同（如酶法 vs 比色）→ 不相容。"""
    a = (m1 or "").strip().lower()
    b = (m2 or "").strip().lower()
    if not a or not b:
        return (name or "").lower() in _STANDARD_ANALYTES
    if a == b:
        return True
    for fam in _METHOD_FAMILIES:
        if a in fam and b in fam:
            return True
    return False


def _parse_ref_range(ref):
    """兼容入口：只返回可确定的参考区间，未知为 None。"""
    rr = HR.reference(ref)
    if rr is None:
        return None
    lo, hi, _li, _ui = rr
    return lo, hi


def _outside_range(value, ref):
    """兼容入口：True=高于上界；False=低于下界或在范围内；未知=None。
    新代码应调用 HR.status(row) 获得偏高/偏低/正常/临界/阳性/待核对。"""
    rr = HR.reference(ref)
    if rr is None:
        return None
    lo, hi, li, ui = rr
    if lo is not None and (value < lo or (value == lo and not li)):
        return True
    if hi is not None and (value > hi or (value == hi and not ui)):
        return True
    return False


def _trend_pair(prev, cur):
    """读时派生 (label, confidence)。三级置信：
    - high（出方向箭头）：同机构+同方法+同单位，两点都可信，幅度明确；
    - mid（软方向，仅供参考）：跨机构/单位不同但属标准化生化项、单位可归一，归一后方向明确；
      体检报告未写方法时，仅通用标准化项（血脂/血糖/尿酸/肌酐/转氨酶/血压/体测）可走 mid；
    - none（不判方向）：单位不可归一 / 方法或标本明显不同 / 不可信点 / 单次 / 运动守卫 / 差异微小。
    prev/cur 行 dict：name/value/unit/lab/method/preconditions/confidence/ref。
    """
    if prev is None:
        return "new", "none"
    # 定性/边界值没有可安全相减的精确数值，只展示本次状态，不推导数值方向。
    if prev.get("value") is None or cur.get("value") is None:
        return "fluctuating", "none"
    # 不可信点（single_measurement/inferred）不单独驱动方向
    if (prev.get("confidence") or "") not in TRUSTED_CONFIDENCE \
            or (cur.get("confidence") or "") not in TRUSTED_CONFIDENCE:
        return "fluctuating", "none"
    # resolved：既往在**各自本院区间外**、本次回到区间内。区间各按本院判，状态本身可跨院成立；
    # 置信随可比性：同院同法同单位=high，跨院=mid（仅供参考）；两方写明且方法明显不同时仍不下结论。
    prev_out = _outside_range(prev["value"], prev.get("ref", ""))
    cur_in = _outside_range(cur["value"], cur.get("ref", ""))
    same_lab = bool(prev.get("lab")) and bool(cur.get("lab")) and prev.get("lab") == cur.get("lab")
    methods_known = bool(prev.get("method")) and bool(cur.get("method"))
    specimens_ok = not (prev.get("specimen") and cur.get("specimen") and prev.get("specimen") != cur.get("specimen"))
    same_setting = (same_lab and methods_known
                    and prev.get("method") == cur.get("method")
                    and specimens_ok
                    and (prev.get("unit") or "").strip() == (cur.get("unit") or "").strip())
    if prev_out is True and cur_in is False:
        if same_setting:
            return "resolved", "high"
        if _methods_compatible(prev.get("method", ""), cur.get("method", ""), cur.get("name", "")):
            return "resolved", "mid"
        return "fluctuating", "none"

    # 取值比较：同设置（同机构/同方法/同标本/同单位）=high；其余最多 mid/none。
    pval, cval = prev["value"], cur["value"]
    confidence = "high" if same_setting else "none"
    if not same_setting:
        # 没有明确实验室/方法时绝不伪造 high；标准化项目最多给 mid 软方向。
        if not specimens_ok:
            return "fluctuating", "none"
        if not _methods_compatible(prev.get("method", ""), cur.get("method", ""), cur.get("name", "")):
            return "fluctuating", "none"
        pu = (prev.get("unit") or "").strip().lower()
        cu = (cur.get("unit") or "").strip().lower()
        if not pu or not cu:
            return "fluctuating", "none"
        if pu == cu:
            pval, cval = prev["value"], cur["value"]
            confidence = "mid"
        else:
            pn, pcanon = _normalize_unit(cur["name"], prev["value"], prev.get("unit", ""))
            cn, ccanon = _normalize_unit(cur["name"], cur["value"], cur.get("unit", ""))
            if pn is None or cn is None or pcanon != ccanon:
                return "fluctuating", "none"
            pval, cval = pn, cn
            confidence = "mid"

    # 运动性守卫：必须在**单位归一之后**用归一值判断是否升高（避免跨单位原始值比较被绕过）；
    # cur 练后/高强度/脱水且归一后确实升高 → 任何置信档（含 mid）都中性，绝不 worsened。
    cond = cur.get("preconditions", "")
    if cur["name"] in EXERCISE_GUARD and EXERCISE_RE.search(cond) and cval > pval:
        return "fluctuating", "none"

    # 差异微小 → persistent/fluctuating，不强行给方向
    if abs(cval - pval) < 1e-9:
        return "persistent", confidence
    rel = abs(cval - pval) / max(abs(pval), 1e-9)
    if rel < 0.05:
        return "fluctuating", "none"

    if cur["name"] in HIGH_BAD:
        if cval < pval:
            return "improved", confidence
        if cval > pval:
            return "worsened", confidence
    elif cur["name"] in LOW_BAD:
        if cval > pval:
            return "improved", confidence
        if cval < pval:
            return "worsened", confidence
    return "fluctuating", "none"


def trend_label(prev, cur):
    """读时派生趋势标签（new/improved/worsened/persistent/fluctuating/resolved/followup_due）。
    置信度（high/mid/none）见 trend_confidence；mid 为归一后软方向，需配"仅供参考"。"""
    return _trend_pair(prev, cur)[0]


def trend_confidence(prev, cur):
    """high=明确同机构/同方法/同标本/同单位；mid=标准化项的软方向；none=不可比/单次/运动守卫/不可信。"""
    return _trend_pair(prev, cur)[1]


# facts_only 允许的安全事实小节标题关键词（过敏/在服药/慢病禁忌/饮食忌口）；其余一律剔除
FACTS_SAFE_HEADINGS = ("过敏", "在服药", "慢病禁忌", "长期用药", "饮食忌口", "忌口")


def facts_only_facts(body):
    """从 health.md 正文抽取 facts_only 允许的安全事实小节（过敏/在服药/慢病禁忌/饮食忌口），
    剔除最新指标表/结论/医嘱/历史快照/里程碑/原件索引。返回过滤后的 Markdown（无则空串）。"""
    keep = []
    for m in re.finditer(r"^##\s*(.+?)\n(.*?)(?=^##\s|\Z)", body, re.M | re.S):
        heading, sec = m.group(1), m.group(2)
        if any(k in heading for k in FACTS_SAFE_HEADINGS):
            keep.append(f"## {heading.strip()}\n{sec.strip()}")
    return "\n\n".join(keep)


# entities/network 等非 health 文件里的健康分区标题（按标题整块剔除）
HEALTH_SECTION_HEADINGS = (
    "身体情况", "健康", "病史", "用药", "慢病", "体检", "生育", "备孕",
    "避孕", "妇科", "共同计划", "私密备注", "病史与禁忌",
)
# 散落在概览/正文句里的健康敏感词（按行剔除；facts_only 仅保留安全事实词）
HEALTH_SENTENCE_KEYWORDS = (
    "过敏", "备孕", "怀孕", "避孕", "病史", "慢病", "体检", "血脂", "血压",
    "血糖", "尿酸", "肌酐", "用药", "服药", "禁忌", "忌口", "妇科", "生育",
    "身体情况", "脂肪肝", "甲状腺",
)
# facts_only 在非 health 文件里允许保留的安全事实词
HEALTH_SAFE_WORDS = ("过敏", "在服药", "长期用药", "禁忌", "忌口")

# 句内（子句级）过滤：安全白名单子句（过敏原/在服药/药物或食物禁忌/忌口）
_SAFE_CLAUSE_RE = re.compile(
    r"过敏|过敏原|在服药|长期用药|服药|用药|在服|吃药|药物禁忌|食物禁忌|药物或食物禁忌|禁忌|忌口"
)
# 非安全健康内容：命中即丢弃该子句（备孕/病史/诊断/疼痛/指标/家庭计划等）
_BAD_CLAUSES = (
    "备孕", "怀孕", "避孕", "月经", "病史", "诊断", "焦虑", "抑郁", "坐骨神经",
    "疼痛", "头痛", "失眠", "体重", "体检", "血压", "血脂", "血糖", "尿酸",
    "肌酐", "结节", "肿瘤", "甲状腺", "脂肪肝", "胆固醇", "家庭计划", "身体",
    "压力", "慢性病", "疾病", "眩晕",
)


def _filter_clauses(line):
    """按句读切分子句，只保留命中安全白名单、且不含非安全健康内容的子句；
    全部被过滤则返回空串（整行去掉）。用于 facts_only 对夹带位置做子句级裁剪。"""
    parts = re.split(r"[，,。；;/、\n]", line)
    kept = []
    for p in parts:
        p = p.strip(" 　\t")
        if not p:
            continue
        if any(b in p for b in _BAD_CLAUSES):
            continue
        if _SAFE_CLAUSE_RE.search(p):
            kept.append(p)
    return "，".join(kept)


def _strip_health_sections(body, scope):
    """只裁剪健康内容，不把健康授权误当作整份人物档案的白名单。

    非健康行原样保留；夹带健康内容的行保守裁剪。无 ## 的扁平档案、
    首个分区前的称呼与简介同样处理，frontmatter 保留供下游解析。
    """
    header = ""
    fm = re.match(r"\A(---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|$))", body, re.S)
    if fm:
        header, body = fm.group(1), body[fm.end():]

    def filter_lines(text, health_section=False):
        kept = []
        for line in text.splitlines():
            health_line = (health_section
                           or any(k in line for k in HEALTH_SENTENCE_KEYWORDS)
                           or any(b in line for b in _BAD_CLAUSES)
                           or bool(_SAFE_CLAUSE_RE.search(line)))
            if not health_line:
                kept.append(line)
            elif scope == "facts_only":
                safe = _filter_clauses(line)
                if safe:
                    kept.append(safe)
        return "\n".join(kept).strip()

    sections = list(re.finditer(r"^##[ \t]+([^\n]+)(?:\n|$)", body, re.M))
    out = []
    prelude = filter_lines(body[:sections[0].start()] if sections else body)
    if prelude:
        out.append(prelude)
    for i, match in enumerate(sections):
        heading = match.group(1).strip()
        end = sections[i + 1].start() if i + 1 < len(sections) else len(body)
        sec = body[match.end():end]
        is_health_sec = any(k in heading for k in HEALTH_SECTION_HEADINGS)
        if is_health_sec and scope != "facts_only":
            continue
        clean = filter_lines(sec, is_health_sec)
        if clean:
            out.append(f"## {heading}\n{clean}")
    return header + "\n\n".join(out)


def consent_filtered_body(rel, body, cc):
    """统一健康授权裁剪（export md/zip 与 gate 共用同一套 scope 契约，避免各写一套）。

    返回 (clean_body, removed_note|None)。full 原样；off/无授权/index_only 删健康；
    facts_only 只留安全事实。rel=profile/health.md 走专用事实抽取，其余文件走分区+逐行剔除。
    """
    scope = cc["scope"] if cc.get("allowed") else "off"
    if scope == "full":
        return body, None
    if rel == HEALTH_METRICS_FILE:
        # 过程层指标明细只有 full 才给；其余档位一律不出数值/历史
        return "（健康授权不是完整档，体检指标明细不输出）", None
    if rel == "profile/health.md":
        if scope == "facts_only":
            return facts_only_facts(body) or "（facts_only：无安全事实可披露）", None
        if scope == "index_only":
            return "（index_only：仅存体检原件本地索引，未导出指标/结论/正文）", None
        return "（健康记录未开启本地授权，本次未导出结构化健康正文，详见 CONSENT-health.md）", None
    clean = _strip_health_sections(body, scope)
    if clean == body:
        return body, None
    note = None
    if scope in ("off", "index_only"):
        note = "（本地健康未授权，已剔除本文件中的健康分区/健康细节）"
    return clean, note
