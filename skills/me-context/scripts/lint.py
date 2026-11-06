#!/usr/bin/env python3
"""me-context 数据仓 lint：校验 frontmatter v1 schema。

纯标准库，共用 mectx_common。扫描 --data 下 *.md：
  - 档案文件（ME.md / profile/*.md / network.md / entities/*.md）必须有"完整合法"
    frontmatter，否则 ERROR（不再是 WARN 后仍 PASS）。
  - 豁免：relations.md / CHANGELOG.md / inbox/ / exports/ / private/ / README·_README/.gitkeep。
  - 枚举：schema=personal-context/v1；layer∈L0-L4；source∈declared/inferred/observed；
    circle∈inner/close/peripheral（实体）。
  - layer=L4 的文件必须位于 private/ 下，否则 ERROR。
错误分级 ERROR/WARN；有 ERROR 退出码 1，否则 0。
"""
import argparse
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mectx_common as C  # noqa: E402

REQUIRED = ["schema", "entity", "layer", "source", "updated"]
RECOMMENDED = ["type", "domain", "confidence", "audience"]

# inbox 草稿超过这个天数未确认 → checkup 提示"丢弃或归档"（一个 current 复核周期 60 天）
INBOX_OLD_DAYS = 60
# 疑似"过程/任务/一次性"误入正式档案的启发式信号（仅提示人工，不自动判错、不删）
PROCESS_SIGNALS = [
    "明早", "明天检查", "截止日", "deadline", "本周交付", "这次任务",
    "找老板对齐", "分工", "待办", "Transition 指标", "本次迭代",
]
# 会默认带出去的文件（L0/L1，或没声明只在本机）里出现这些词 → 提醒挪到健康/财务分片或人物档案。
# 只提醒、不改文件；"过敏/忌口"这类安全禁忌允许留一句，不在名单里。
SENSITIVE_HINT_WORDS = {
    "健康": ("透析", "确诊", "病史", "试管", "取卵", "移植", "备孕", "怀孕", "化疗",
             "手术", "住院", "抑郁", "焦虑症", "尿酸", "血脂", "血压", "血糖", "肌酐", "体检结论"),
    "财务": ("房贷", "车贷", "负债", "欠款", "月供", "存款", "年收入", "月收入", "薪资", "年薪"),
}


def sensitive_hints(text):
    """返回 [(类别, 命中词)]；扫正文和 HTML 注释（gate 外发时注释原样带出），不看 frontmatter。"""
    _meta, _body = C.parse_frontmatter(text)
    fm = re.match(r"\A\s*(?:<!--.*?-->\s*)*---.*?\n---[ \t]*\n?", text, re.S)
    body = text[fm.end():] if fm else text
    return [(k, w) for k, words in SENSITIVE_HINT_WORDS.items() for w in words if w in body]


def outgoing_by_default(meta):
    """这个文件是否会默认带给外部 AI：L0/L1 且没声明 audience: local。"""
    layer = C.normalize_layer((meta or {}).get("layer"))
    return layer in ("L0", "L1") and not C.audience_local(meta)


def outgoing_hint(meta, text):
    """会默认带给外部 AI 的文件里出现健康/财务细节 → 提醒文案；否则 None。只提醒，不改退出码。"""
    if not outgoing_by_default(meta):
        return None
    hits = sensitive_hints(text)
    if not hits:
        return None
    words = "、".join(w for _k, w in hits[:6])
    kinds = "/".join(sorted({k for k, _w in hits}))
    return (f"这个文件会默认带给外部 AI，正文出现{kinds}细节（{words}）；"
            f"建议挪到对应分片或人物档案，这里只留一句不带细节的索引")


def is_data_file(rel):
    """需要"完整 frontmatter"的档案文件。"""
    parts = rel.replace("\\", "/").split("/")
    if parts[0] == "profile" and parts[-1].endswith(".md"):
        return True
    if parts[0] == "entities" and parts[-1].endswith(".md") and not parts[-1].startswith("_"):
        return True
    if parts[-1] in ("ME.md", "network.md"):
        return True
    return False


def lint_file(path, rel, today=None):
    errs, warns = [], []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    meta, body = C.parse_frontmatter(text)

    needs_full = is_data_file(rel)
    if meta is None:
        if needs_full:
            errs.append("头部异常：缺 frontmatter 或缺结尾 ---（fail-closed，必须补完整 frontmatter）")
        else:
            warns.append("无 frontmatter（豁免文件，跳过校验）")
        return errs, warns

    for fld in REQUIRED:
        if fld not in meta or meta[fld] in (None, ""):
            errs.append(f"缺必填字段：{fld}")
    if meta.get("schema") and meta["schema"] != "personal-context/v1":
        errs.append(f"schema 必须 personal-context/v1，实为 {meta['schema']!r}")

    layer = C.normalize_layer(meta.get("layer"))
    if not meta.get("layer"):
        errs.append("缺 layer 字段（必须 L0-L4）")
    elif layer is None:
        errs.append(f"layer 非法：{meta['layer']!r}（strip+upper 后须 L0-L4，禁止静默降级）")
    # L4 文件必须在 private/ 下
    if layer == "L4" and not rel.replace("\\", "/").startswith("private/"):
        errs.append(f"layer=L4 的文件必须放在 private/ 下（现位于 {rel}）")

    src = meta.get("source")
    if src and src not in C.SOURCES:
        errs.append(f"source 非法：{src!r}（应 declared/inferred/observed）")
    upd = meta.get("updated")
    if upd and not (isinstance(upd, str) and C.DATE_RE.match(upd)):
        errs.append(f"updated 非 ISO 日期：{upd!r}")
    rel_norm = rel.replace("\\", "/")
    is_entity = rel_norm.startswith("entities/") or "/entities/" in rel_norm
    circle = meta.get("circle")
    if circle and circle not in C.CIRCLES:
        errs.append(f"circle 非法：{circle!r}")
    elif circle is None and is_entity:
        warns.append("实体建议标注 circle（inner/close/peripheral）")

    # 群组实体（夫妇/父母等）必须能列出成员，否则图谱只能显示泛称、不能点名每个人
    if is_entity and os.path.basename(path) != "_entity.md":
        eid = os.path.splitext(os.path.basename(path))[0].lower()
        etype = (meta.get("type") or "").strip().lower()
        seg_m = re.search(r"^##\s*成员[^\n]*\n(.*?)(?=^##\s|\Z)", body, re.M | re.S)
        members = re.findall(r"\*\*\s*([一-龥A-Za-z·]{2,})\s*\*\*", seg_m.group(1) if seg_m else "")
        is_group = etype in ("group", "couple", "family") or len(members) >= 2 \
            or any(h in eid for h in ("parent", "couple", "family", "friends"))
        if is_group and len(members) < 2:
            warns.append("群组实体（夫妇/父母/一家人）请在「## 成员」分节用 **姓名** 逐个列出成员，"
                         "图谱才会显示中文名并能点名每个人（否则只显示“父母/好友”泛称）")

    # v11 时效：超期 current / 已归档只给 WARN（非阻断，rc 仍 0），绝不改层、绝不 fail-closed
    st = C.freshness_status(meta, meta.get("domain"), today=today)
    if st and st["level"] == "archived":
        warns.append("stale:true 已归档，不再当现行事实（如需恢复去掉 stale 并更新 updated）")
    elif st and st["level"] == "stale":
        hard = "；已超 180 天，体检建议问'还成立吗？不成立就清/转历史'" if st["hard"] else ""
        warns.append(f"可能过期：{st['freshness']} 已 {st['age']} 天未更新（上次 {st['updated']}，复核期 {st['review']} 天）{hard}")

    # 健康结构：统一用 loss-aware parser 校验，避免合并行/定性项静默丢失
    if rel_norm == "profile/health.md":
        if any(re.search(r"^##\s*" + h, body, re.M) for h in C.HEALTH_DETAIL_HEADINGS):
            warns.append("体检指标明细还在结论层；建议跑 scripts/migrate.py 挪到 journal/health-metrics.md，"
                         "做判断时只带结论，问具体数值或趋势时再读明细")
        e2, w2 = lint_health_metrics(body, today)
        errs += e2
        warns += w2

    for fld in RECOMMENDED:
        if fld not in meta or meta[fld] in (None, ""):
            warns.append(f"建议补充：{fld}")

    # 会默认带出去的文件里出现健康/财务细节 → 提醒挪走（只提醒，rc 不变）
    hint = outgoing_hint(meta, text)
    if hint:
        warns.append(hint)
    if rel_norm == "network.md":
        hits = sensitive_hints(text)
        if hits:
            words = "、".join(w for _k, w in hits[:6])
            kinds = "/".join(sorted({k for k, _w in hits}))
            warns.append(f"关系网概览只放'是谁、什么关系'，出现{kinds}细节（{words}）；"
                         f"建议挪到对应人物档案（健康放身体分区，钱的事放财务分区）")
    return errs, warns


def lint_health_metrics(body, today=None):
    """健康指标格式校验（结论层 health.md 与过程层 health-metrics.md 共用）。返回 (errs, warns)。"""
    errs, warns = [], []
    latest, hist = C.health_sections(body)
    latest_section = re.search(r"^##\s*最新关键指标[^\n]*\n(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    meaningful_lines = []
    if latest_section:
        for ln in latest_section.group(1).splitlines():
            if not re.match(r"^\s*-\s*指标\s+", ln):
                continue
            # 空白模板 `<v>` / 空值不是数据，不应让刚 init 的仓报错
            vm = re.search(r"\|\s*数值\s*([^|]*)", ln)
            if vm and (not vm.group(1).strip() or vm.group(1).strip().startswith("<")):
                continue
            meaningful_lines.append(ln)
            head = ln.split("|", 1)[0]
            name = re.sub(r"^\s*-\s*指标\s+", "", head).strip()
            if "/" in name or "、" in name:
                errs.append(f"健康指标「{name}」合并了多个项目；必须一项一行，避免单位/参考区间/趋势错配")
    for row in latest:
        label = C.HR.LABELS.get(row["name"], row["name"])
        if not row.get("unit") and row.get("value") is not None and row["name"] not in ("bmi",):
            warns.append(f"健康指标「{label}」缺单位；趋势只可保守使用")
        if not row.get("date"):
            errs.append(f"健康指标「{label}」缺日期字段")
        if C.HR.status(row) == "待核对":
            warns.append(f"健康指标「{label}」缺可判定的参考区间/定性标记，展示为待核对，不得当正常")
    if meaningful_lines and not latest:
        errs.append("最新关键指标区存在内容但未解析出任何规范指标；请按 08 协议改为一项一行")
    # 同一日期+指标只能有一个正式点；重复会导致趋势歧义
    seen = set()
    for row in latest + hist:
        key = (row.get("date"), row.get("name"), row.get("lab"))
        if key in seen:
            warns.append(f"健康时序重复点：{row.get('date') or '无日期'} / {C.HR.LABELS.get(row['name'], row['name'])} / {row.get('lab') or '无机构'}")
        seen.add(key)
    fm = re.search(r"followup_due\s*:\s*(\d{4}-\d{2}-\d{2})", body)
    if fm and today:
        d0 = C.parse_iso_date(fm.group(1))
        if d0 and d0 < today:
            warns.append(f"复查计划 followup_due={fm.group(1)} 已到期，建议跟进（仅提醒，非诊断）")
    return errs, warns


def lint_relations(path, known):
    errs = []
    code = C.strip_html_comments(open(path, encoding="utf-8").read())
    for m in re.finditer(r"^\s+to:\s*([\w.-]+)\s*$", code, re.M):
        t = m.group(1)
        if t == "me" or t in known:
            continue
        errs.append(f"relations to={t!r} 无 entities/{t}.md（或未标 external: true）")
    return errs


def lint_inbox_scope_hints(data):
    """对 inbox/*.md 草稿做保守的工程类启发式 WARN（仅提醒，不改写、不计 ERROR、不影响 rc）。

    草稿正文/quote 命中强工程信号词、且未显式写 scope: engineering 或 scope: general 时提示。
    正式 profile/ME 绝不做这种内容扫描。最终 scope 判定与分流仍由用户在确认环节拍板。
    返回发出的 WARN 条数。
    """
    inbox = os.path.join(data, "inbox")
    if not os.path.isdir(inbox):
        return 0
    SIGNALS = [
        "git commit", "提交前", "跑测试", "单元测试", "跑全量测试",
        "自检", "对抗自检", "三层不越界", "架构分层", "去个人化",
        "发版", "发布规范", "code review", "PR 合并", "PR合并",
        "CLAUDE.md", "AGENTS.md", ".cursor/rules", "仓库约定",
    ]
    n = 0
    for fn in sorted(os.listdir(inbox)):
        fp = os.path.join(inbox, fn)
        if not fn.endswith(".md") or fn.startswith("_") or os.path.islink(fp):
            continue
        with open(fp, encoding="utf-8") as f:
            text = f.read()
        # 已显式标 scope（无论 engineering/general）→ 不再重复 WARN
        if re.search(r"^\s*scope\s*:", text, re.M):
            continue
        if not any(sig in text for sig in SIGNALS):
            continue
        rel = os.path.relpath(fp, data)
        print(f"WARN   {rel}: 疑似工程类候选，建议 scope: engineering 并按作用域边界分流（见 references/05 §5）")
        n += 1
    return n


def lint_status_sync(data):
    """过程层有指标明细时，比对结论层「当前状态」与最新指标标出的异常项。只提醒，返回 WARN 条数。"""
    hp = C.safe_join(data, C.DOMAIN_FILE["health"])
    mp = C.safe_join(data, C.HEALTH_METRICS_FILE)
    if not (hp and mp and os.path.isfile(hp) and os.path.isfile(mp)):
        return 0
    _m, hbody = C.parse_frontmatter(open(hp, encoding="utf-8").read())
    sec = re.search(r"^##\s*" + C.STATUS_HEADING + r"[^\n]*\n(.*?)(?=^##\s|\Z)", hbody, re.M | re.S)
    if not sec:
        print(f"WARN   profile/health.md: 有体检指标明细，但结论层缺「{C.STATUS_HEADING}」；"
              f"建议补一节，只写偏高/偏低的项，做判断时就不用翻明细")
        return 1
    latest, _h = C.health_sections(C.read_health_body(data))
    want = {re.sub(r"（.*?）$", "", ln[2:]) for ln in C.health_status_lines(latest)}
    have = {re.sub(r"（.*?）$", "", ln.strip()[2:]) for ln in sec.group(1).splitlines()
            if ln.strip().startswith("- ") and not ln.strip().startswith("- <")}
    have = {h for h in have if "：" in h}
    missing, extra = sorted(want - have), sorted(have - want)
    if not (missing or extra):
        return 0
    parts = []
    if missing:
        parts.append("最新指标标出、当前状态没写：" + "、".join(missing))
    if extra:
        parts.append("当前状态写了、最新指标已不是这样：" + "、".join(extra))
    print(f"WARN   profile/health.md: 「{C.STATUS_HEADING}」和最新体检对不上（{'；'.join(parts)}）；更新体检后记得同步")
    return 1


def run_checkup(data, today=None):
    """体检/清理：只列不删。删除/合并/转历史一律人工确认。纯只读，不改任何文件。"""
    today = today or date.today()
    a_items, b_items, c_items, d_items, e_items = [], [], [], [], []

    # a) 超期未复核的 current；d) 过程词扫描对所有分片（含 stable）；e) stable 年度回看（轻量）
    archived = []
    for root, dirs, files in os.walk(data):
        dirs[:] = [d for d in dirs if d not in (".git", "exports", "inbox", "private", C.JOURNAL_DIR, C.MIGRATE_BACKUP_DIR)
                   and not os.path.islink(os.path.join(root, d))]
        for fn in sorted(files):
            fp = os.path.join(root, fn)
            if not fn.endswith(".md") or os.path.islink(fp):
                continue
            rel = os.path.relpath(fp, data).replace("\\", "/")
            raw = open(fp, encoding="utf-8").read()
            meta, _body = C.parse_frontmatter(raw)
            # d) 疑似过程/任务/一次性误入正式档案（启发式，待人工确认；与 current/stable 无关，所有分片都扫）
            body = C.strip_html_comments(raw)
            hit = [s for s in PROCESS_SIGNALS if s in body]
            if hit:
                d_items.append(f"{rel}: 命中过程/任务词 {hit}，请人工确认是否该留在个人档案")
            if meta is None:
                continue
            st = C.freshness_status(meta, today=today)
            if st and st["level"] == "archived":
                archived.append(rel)
            elif st and st["level"] == "stale":
                tag = "建议清理/转历史" if st["hard"] else "请复核是否仍成立"
                a_items.append(f"{rel}: {st['freshness']} 已 {st['age']} 天未更新"
                               f"（上次 {st['updated']}，复核 {st['review']} 天）→ {tag}")
            # e) stable 年度回看：updated 超 360 天的稳定分片，中性提示可顺手回看（非过期、非阻断）
            if C.freshness_of(meta) == "stable":
                d0 = C.parse_iso_date(meta.get("updated"))
                if d0 and (today - d0).days > 360:
                    e_items.append(f"{rel}: stable 已 {(today - d0).days} 天未更新，可顺手回看是否仍准确（非过期）")

    # b) inbox 堆超过一个复核周期未确认的旧草稿
    inbox = os.path.join(data, "inbox")
    if os.path.isdir(inbox):
        for fn in sorted(os.listdir(inbox)):
            fp = os.path.join(inbox, fn)
            if not fn.endswith(".md") or fn.startswith("_") or os.path.islink(fp):
                continue
            meta, _ = C.parse_frontmatter(open(fp, encoding="utf-8").read())
            d0 = C.parse_iso_date((meta or {}).get("date"))
            age = (today - d0).days if d0 else None
            if age is not None and age > INBOX_OLD_DAYS:
                b_items.append(f"inbox/{fn}: 草稿已 {age} 天未确认 → 建议丢弃或归档")

    # c) 显式标 conflict: needs_review 的条目（确定性检测；其余冲突标待人工，不瞎判）
    for root, dirs, files in os.walk(data):
        dirs[:] = [d for d in dirs if d not in (".git", "exports", "private", C.MIGRATE_BACKUP_DIR)
                   and not os.path.islink(os.path.join(root, d))]
        for fn in sorted(files):
            fp = os.path.join(root, fn)
            if not fn.endswith(".md") or os.path.islink(fp):
                continue
            rel = os.path.relpath(fp, data).replace("\\", "/")
            meta, _ = C.parse_frontmatter(open(fp, encoding="utf-8").read())
            if (meta or {}).get("conflict") == "needs_review":
                c_items.append(f"{rel}: 标了 conflict: needs_review，待人工裁决新旧值")

    print("== 体检（只列不删，删除/转历史/合并一律人工确认）==")
    print(f"\n[a] 超期未复核（{len(a_items)}）:")
    print("\n".join("  · " + x for x in a_items) or "  · 无")
    print(f"\n[b] inbox 旧草稿（{len(b_items)}）:")
    print("\n".join("  · " + x for x in b_items) or "  · 无")
    print(f"\n[c] 待人工核对的冲突（{len(c_items)}）:")
    print("\n".join("  · " + x for x in c_items) or "  · 无（未显式标 conflict 的不瞎判）")
    print(f"\n[d] 疑似过程/任务误入（{len(d_items)}，启发式待人工）:")
    print("\n".join("  · " + x for x in d_items) or "  · 无")
    print(f"\n[e] stable 年度回看（{len(e_items)}，中性、非过期、非阻断）:")
    print("\n".join("  · " + x for x in e_items) or "  · 无")
    if archived:
        print(f"\n[已归档 stale:true]（{len(archived)}）: " + ", ".join(archived))
    print("\n提示：以上仅建议，本命令不修改/删除任何文件。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="lint me-context 数据仓 frontmatter schema（fail-closed）；--checkup 只列过期/旧草稿，不删。")
    ap.add_argument("--data", required=True)
    ap.add_argument("--checkup", action="store_true", help="体检：只列超期 current/旧 inbox/冲突/疑似误入，不修改任何文件")
    ap.add_argument("--today", help="覆盖今天日期 YYYY-MM-DD（确定性测试用，默认当天）")
    args = ap.parse_args()
    data = os.path.abspath(args.data)
    if not os.path.isdir(data):
        print(f"[错误] 数据仓不存在：{data}", file=sys.stderr)
        return 2
    today = C.parse_iso_date(args.today) if args.today else None
    if args.checkup:
        return run_checkup(data, today=today)

    md_files = []
    for root, dirs, files in os.walk(data):
        dirs[:] = [d for d in dirs if d not in (".git", "exports", "inbox", "private", C.JOURNAL_DIR, C.MIGRATE_BACKUP_DIR)
                   and not os.path.islink(os.path.join(root, d))]
        for fn in files:
            fp = os.path.join(root, fn)
            if fn.endswith(".md") and not os.path.islink(fp):
                md_files.append(fp)
    md_files.sort()

    known = {"me"}
    ent = os.path.join(data, "entities")
    if os.path.isdir(ent):
        for fn in os.listdir(ent):
            if fn.endswith(".md") and not fn.startswith("_"):
                known.add(fn[:-3])

    te, tw = 0, 0
    for path in md_files:
        rel = os.path.relpath(path, data)
        if os.path.basename(path) in C.LINT_EXEMPT_BASENAMES:
            # 结构文件不查档案 schema；但 relations.md 会随默认 md 导出带给外部 AI，备注里的健康/财务细节照样提醒
            if os.path.basename(path) == "relations.md":
                text = open(path, encoding="utf-8").read()
                hint = outgoing_hint(C.parse_frontmatter(text)[0], text)
                if hint:
                    print(f"WARN   {rel}: {hint}")
                    tw += 1
            continue
        errs, warns = lint_file(path, rel, today=today)
        if os.path.basename(path) == "relations.md":
            errs += lint_relations(path, known)
        for e in errs:
            print(f"ERROR  {rel}: {e}")
        for w in warns:
            print(f"WARN   {rel}: {w}")
        te += len(errs); tw += len(warns)

    # 过程层 journal/：不要求档案 frontmatter，只查两件事——不能放 L4、文件开头要标层（便于外发时判断）
    jdir = os.path.join(data, C.JOURNAL_DIR)
    if os.path.isdir(jdir):
        for fn in sorted(os.listdir(jdir)):
            fp = os.path.join(jdir, fn)
            if not fn.endswith(".md") or os.path.islink(fp):
                continue
            jmeta, jbody = C.parse_frontmatter(open(fp, encoding="utf-8").read())
            jlayer = C.normalize_layer((jmeta or {}).get("layer"))
            if jlayer is None:
                print(f"WARN   journal/{fn}: 过程层文件建议在开头标 layer（体检指标标 L3），外发时才能正确拦截")
                tw += 1
            elif jlayer == "L4":
                print(f"ERROR  journal/{fn}: L4 秘密不能放过程层，请放 private/")
                te += 1
            if f"{C.JOURNAL_DIR}/{fn}" == C.HEALTH_METRICS_FILE:
                e2, w2 = lint_health_metrics(jbody, today)
                for e in e2:
                    print(f"ERROR  journal/{fn}: {e}")
                for w in w2:
                    print(f"WARN   journal/{fn}: {w}")
                te += len(e2); tw += len(w2)

    # inbox 草稿的工程类启发式 WARN（仅提醒，不改写、不影响 rc）
    tw += lint_inbox_scope_hints(data)

    # 两层一致：结论层「当前状态」要和过程层最新指标对得上（体检更新后忘了同步时提醒）
    tw += lint_status_sync(data)

    # v12 本地健康授权：存在健康分片但未授权 → 非阻断 WARN 引导（不阻断非健康、不自动写授权）
    health_fp = os.path.join(data, "profile", "health.md")
    if os.path.isfile(health_fp):
        cc = C.parse_consent(data)
        if not cc["allowed"]:
            print("WARN   CONSENT-health.md: 本地健康记录未开启/已撤回；如需记录请先由本人显式选择四档"
                  "（full/facts_only/index_only/off）生成授权，当前不读取结构化健康。")
            tw += 1

    print("-" * 60)
    print(f"扫描 {len(md_files)} 个 md 文件；ERROR={te} WARN={tw}")
    if te:
        print("结果：FAIL")
        return 1
    print("结果：PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
