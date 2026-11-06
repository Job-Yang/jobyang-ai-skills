#!/usr/bin/env python3
"""技能库静态健康体检（可移植、零平台依赖、纯标准库）。

用法：
    python3 library_doctor.py [技能库目录] [--json]
    python3 library_doctor.py [目录] --save-baseline baseline.json   # 记录现状
    python3 library_doctor.py [目录] --baseline baseline.json        # 只报基线之外的新问题

设计边界（重要）：
- 本工具只做「静态」检查：frontmatter、命名、description 路由信号、引用完整性、
  平台绑定、结构体积、占位/密钥等文本可判定的问题。
- P3 语义类（退出条件、有限重试、可观察触发、选项有默认、规则矛盾）正则不可靠，
  不写死在脚本里，见 references/health-check.md 的人工清单。
- 动态类（真实触发率、乱触/漏触、文件实际读取顺序、端到端成功率）归 Harness 层，
  本工具不做。
- 规则来源：Anthropic 官方 Skill 规范、agent-skill-linter、ai-skill-lint、
  宿主 skill-creator 的 quick_validate.py。每条规则 ID 可在 health-check.md 查到依据。
- 只报告，不修改任何文件。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml  # 宿主通常自带；没有则走下面的轻量解析
except Exception:  # pragma: no cover
    yaml = None

# ---------------------------------------------------------------- 规则目录

# 每条规则：(severity, 规则ID, 名称, 修复建议, 来源)
# severity: high=硬错误(exit 1) / mid=路由与正确性 / low=结构与卫生
R_NAME_MISSING   = ("high", "F001", "缺 name",            "补 frontmatter name",                    "quick_validate/Anthropic")
R_NAME_BAD       = ("high", "F002", "name 非法",          "name 仅允许小写字母/数字/连字符，不以连字符开头结尾、无连续连字符，≤64 字符", "Anthropic/quick_validate")
R_NAME_RESERVED  = ("high", "F003", "name 含保留词",      "不得含 anthropic/claude 等保留词",       "Anthropic")
R_NAME_DIR       = ("mid",  "F004", "name 与目录不一致",  "统一 frontmatter name 与目录名",         "quick_validate")
R_NAME_DUP       = ("high", "F005", "name 重名",          "多个技能声明同一 name，改名消歧",        "library")
R_FM_YAML        = ("high", "F006", "frontmatter 非法",   "修复 YAML 语法",                         "quick_validate")
R_FM_UNKNOWN_KEY = ("low",  "F007", "frontmatter 非常用字段", "确认该字段是宿主支持的，否则移入 metadata", "quick_validate")
R_DESC_MISSING   = ("high", "F008", "缺 description",     "补 description（做什么+何时触发+不适用）", "Anthropic/quick_validate")
R_DESC_LONG      = ("high", "F009", "description 超长",   "description ≤1024 字符，细节移正文",     "Anthropic/quick_validate")
R_DESC_ANGLE     = ("high", "F010", "description 含尖括号", "去掉 < >（会与标签冲突）",             "Anthropic/quick_validate")
R_DESC_SHORT     = ("mid",  "D001", "description 过短",   "过短难以承载「做什么+何时触发+边界」，建议 ≥60 字", "Anthropic 双要素")
R_DESC_NOWHEN    = ("mid",  "D002", "description 缺触发时机", "补「何时用/触发词/当……时」，路由只看这一行", "Anthropic/agent-skill-linter R18")
R_DESC_NOSAMPLE  = ("low",  "D003", "description 缺用户原话样例", "加 1-3 个用户真实会说的触发短语（引号包裹）", "Anthropic")
R_BODY_NOBORDER  = ("mid",  "D004", "正文缺不适用边界",   "写明不适用场景及与相邻技能的互斥/交接",   "library")
R_REF_BROKEN     = ("high", "R001", "引用文件不存在",     "修复路径或补文件（broken reference）",   "ai-skill-lint Structure")
R_FENCE_OPEN     = ("mid",  "R002", "代码围栏未闭合",     "代码围栏 ``` 数量为奇数，补全闭合",      "ai-skill-lint Content")
R_HARD_BIND      = ("high", "P001", "平台硬绑定",         "去掉绝对路径/宿主目录，改成参数或自动发现", "library")
R_SOFT_BIND      = ("low",  "P002", "平台弱引用待确认",   "确认是软依赖：写明「需要时才用，缺失则降级到通用方式」", "library")
R_COLLISION      = ("mid",  "T001", "疑似触发撞车",       "人工确认真实 query 是否互抢；重划边界或在 description 互指", "library")
R_BODY_LONG      = ("low",  "S001", "SKILL.md 超长",      "正文 >500 行，把条件性细节下沉到 references/", "Anthropic 渐进披露")
R_REF_NOTOC      = ("low",  "S002", "长 reference 缺目录", ">100 行的 reference 文件顶部加目录",     "Anthropic")
R_REF_DEEP       = ("low",  "S003", "reference 嵌套超过一层", "reference 只应被 SKILL.md 直接引用一层，抹平层级", "Anthropic")
R_REF_ORPHAN     = ("low",  "S004", "资源未被主文件引用", "确认该文件是否需要；需要则在 SKILL.md 标明何时读", "Anthropic")
R_PLACEHOLDER    = ("low",  "S005", "残留占位/待办",      "删除模板示例文件或补全 TODO/占位内容",    "skill-creator/ai-skill-lint")
R_SECRET         = ("high", "S006", "疑似硬编码密钥",     "立即移除密钥，改用环境变量/配置",         "ai-skill-lint Security")

# ---- C 类：库级覆盖（不是单个技能写错，而是一版图围出了一个谁都不接的任务洞）----
R_C_DANGLING     = ("mid",  "C001", "悬空技能交接",
                    "正文/description 把任务指给了一个库中不存在的技能；补该技能或改指现有技能", "library")
R_C_VACUUM       = ("mid",  "C003", "疑似覆盖真空",
                    "多个技能都把这类任务排除/推走，却没有任何技能正面认领；核对后补一个承接方或明确边界", "library")

ALLOWED_FM_KEYS = {"name", "description", "license", "allowed-tools", "compatibility", "metadata"}

# 强绑定：出现基本就是问题（绝对路径、宿主目录）
HARD_PATTERNS = [
    r"/Users/[^\s'\")\]]+",
    r"/home/[^\s'\")\]]+",
    r"C:\\",
    r"\.doubaowork",
    r"~/\.trae/skills",
]
# 弱引用：平台名/专属工具，命中不代表错，但要确认是否「需要时才用、可降级」
SOFT_PATTERNS = [r"lark-cli", r"lark-doc", r"feishu\.cn", r"飞书文档?"]
SOFT_DEGRADE_HINT = r"若(具备|有|需要|可用|没有|缺失|无)|可降级|降级|没有.*时|(缺|无).*时|可选"

# 触发时机信号（description 里出现才算写了「何时用」）。中文技能常只写「时使用/…时调用/
# 当…用」，阈值放宽，避免把明明写了触发时机的描述误判为缺信号。
WHEN_PAT = re.compile(
    r"适用|用于|用时|时(?:使用|调用|用|触发|启用)|当.{0,14}(?:时|用)|触发|何时|"
    r"不适用|不要用|不走|不做|不负责|use when|when to", re.I)
# 用户原话样例：引号包裹的短语。兼容中文直角引号「」『』、弯引号“”‘’和英文引号。
SAMPLE_PAT = re.compile(r"[「『“‘\"'][^」』”’\"']{2,30}[」』”’\"']")
# 边界信号（正文）。中文技能常写「不用/不负责/只做/范围」，阈值放宽。
BORDER_PAT = re.compile(
    r"不适用|不启用|不要用|不用|不触发|不负责|边界|何时不用|不做|不走|只做|只用于|适用范围")
# description 路由行里写的边界（正文没重复时也够，路由只看这一行）
DESC_BORDER_PAT = re.compile(r"不适用|不要用|不做|不走|不接|不负责|区别|分别走|vs")

# 只统计 markdown 围栏的起始/结束行；围栏内是代码/命令，不算正文引用，
# 避免把 `cp -R ... ~/.trae/skills`、`scripts/foo.py` 这类命令当成正文引用。
def strip_fences(text: str) -> str:
    out, in_fence = [], False
    for ln in text.splitlines():
        if FENCE_RE.match(ln):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(ln)
    return "\n".join(out)

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
BARE_RES_RE = re.compile(r"(?<![\w/.\-])((?:references|reference|scripts|assets)/[A-Za-z0-9_./\-]+)")
FENCE_RE = re.compile(r"^\s*```")
SECRET_RE = re.compile(
    r"(?i)(?:api[_-]?key|secret|access[_-]?token|password)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']"
)
PLACEHOLDER_NAME_RE = re.compile(r"example|sample|template|示例|样板", re.I)
TODO_RE = re.compile(r"TODO|FIXME|XXX|待补充|占位符|placeholder here", re.I)


def hit_group(desc, group):
    return sum(1 for pat in group if re.search(pat, desc))


# ---------------------------------------------------------------- 解析

def parse_frontmatter(text: str):
    """返回 (fm_dict, body, error)。优先 PyYAML，失败/缺失时走轻量解析。"""
    if not text.startswith("---"):
        return {}, text, None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text[3:], "frontmatter 未闭合（缺少第二个 ---）"
    head, body = parts[1], parts[2]
    if yaml is not None:
        try:
            data = yaml.safe_load(head)
            if data is None:
                return {}, body, None
            if not isinstance(data, dict):
                return {}, body, "frontmatter 必须是键值映射"
            return data, body, None
        except Exception as e:  # YAML 真的非法
            return {}, body, f"YAML 解析失败：{e}"
    return _tiny_yaml(head), body, None


def _tiny_yaml(head: str) -> dict:
    """无 PyYAML 时的兜底：支持 key: value、引号、>- / | 折叠块、一层嵌套。"""
    fm, lines = {}, head.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.startswith(" ") or ":" not in line:
            i += 1
            continue
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip()
        if val in (">-", "|", "|-", ">"):
            buf, i = [], i + 1
            while i < len(lines) and (lines[i].startswith("  ") or not lines[i].strip()):
                if lines[i].strip():
                    buf.append(lines[i].strip())
                i += 1
            fm[key] = " ".join(buf)
            continue
        fm[key] = val.strip("'\"")
        i += 1
    return fm


def extract_local_targets(md: str):
    """抽出 markdown 中指向技能本地文件的目标（排除 URL/锚点/命令）。"""
    targets = []
    for raw in LINK_RE.findall(md):
        t = raw.strip().split()[0].strip("\"'")
        # 去掉 #fragment 与 ?query，否则 references/a.md#节 会因文件名带后缀而误判 broken
        t = t.split("#", 1)[0].split("?", 1)[0]
        if not t:
            continue
        if re.match(r"^(https?:|mailto:|#|/)", t) or t.startswith("#"):
            continue
        targets.append(t)
    for raw in BARE_RES_RE.findall(md):
        targets.append(raw)
    # 归一：reference/ 与 references/ 两种写法都试
    return targets


def has_nav_or_headings(text: str) -> bool:
    """长 reference 的可读性：顶部有锚点目录，或前 40 行有多个分节标题，都算结构清楚。"""
    head = "\n".join(text.splitlines()[:40])
    if len(re.findall(r"\]\(#[^)]+\)", head)) >= 2:
        return True
    return len(re.findall(r"^#{1,3}\s+\S", head, re.M)) >= 3


def read_text(p: Path) -> str:
    # 容错：测试夹具里可能有故意指向不存在目标的符号链接（如越界链接负例），
    # 读不到不算被检内容，返回空串，绝不让体检在这种夹具上崩掉。
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------- 发现

def find_library(start: Path):
    cur = start.resolve()
    for d in [cur] + list(cur.parents):
        if len(list(d.glob("*/SKILL.md"))) >= 2:
            return d
    return cur if (cur / "SKILL.md").exists() else None


# ---------------------------------------------------------------- 库级覆盖

# 库级覆盖真空词表。踩过的真洞是「(源码/仓库)调研 × 还要落成(文档/分享)」这个交叉地带：
# 一圈技能各自排除，谁都不正面接，模型只能退回 lark-doc 等工具人。
# 静态只能给「线索」：技能级看它同时提到 A/B 两组词后，是正面认领还是推走，>=3 个推走、
# 0 个认领才报，强制人工核对，避免把「各司其职的正常边界」误报成洞。
COVERAGE_VACUUMS = [
    {
        "name": "(源码/仓库)调研并落成文档/分享",
        "a": re.compile(r"调研|源码|开源|仓库|github|repo|读码|拆解.{0,4}项目", re.I),
        "b": re.compile(r"成稿|报告|文档|研判|解读|分享|博客|slides|文章|talk", re.I),
    },
]
# 强认领：明确把这类任务纳进本技能（出现即视为有人接，哪怕它别处又推走某个子类型）。
CLAIM_CROSS = re.compile(
    r"先走本技能|走本技能|都先走|都走本技能|承接|负责.{0,6}调研|调研.{0,12}先走|"
    r"任何.{0,4}调研.{0,16}(先走|走本)|可以.{0,10}(产出|写).{0,8}(报告|文档|成稿|研判|解读)|"
    r"直接产出.{0,6}(调研|报告|解读)")
# 推走：把任务排除或指给别的技能。
PUSH_CROSS = re.compile(
    r"走\s*`?[a-z][a-z0-9-]{2,}|调研.{0,14}(不适用|不接|不用|不走|交(给|由))|"
    r"(不适用|不接|不用|不走).{0,10}调研|对内.{0,6}调研.{0,8}不")
HANDOFF_OUT = re.compile(r"不适用|不要用|不用|不走|不接|不做|交(给|由)|走\s*`?[a-z]", re.I)


def split_sentences(text: str):
    return [s for s in re.split(r"[。；;\n]", text) if s.strip()]


def coverage_scan(skills, known_names, external_ok=None):
    """库级覆盖：C003 覆盖真空 / C001 悬空交接。只给线索，结论由人核对。"""
    out = []
    external_ok = external_ok or set()

    # C003：技能级判定。某技能同时提到 A/B 两组词，就算覆盖到这个交叉地带；
    # 有强认领算 claimer，否则出现推走算 pusher。>=3 推走、0 认领 → 疑似真空。
    for vac in COVERAGE_VACUUMS:
        pushers, claimers = set(), set()
        for s in skills:
            text = str(s["fm"].get("description", "")) + "\n" + s["body"]
            if not (vac["a"].search(text) and vac["b"].search(text)):
                continue
            if CLAIM_CROSS.search(text):
                claimers.add(s["dir"])
            elif PUSH_CROSS.search(text):
                pushers.add(s["dir"])
        if len(pushers) >= 3 and not claimers:
            out.append({
                "sev": "mid", "rule": "C003", "kind": "疑似覆盖真空",
                "skill": f"【库级】{vac['name']}",
                "evidence": f"{len(pushers)} 个技能都提到但把「{vac['name']}」排除/指走"
                            f"（{', '.join(sorted(pushers)[:6])}），且没有技能正面认领",
                "action": "人工用真实 query 核对：确属高频任务就补承接方或放宽某技能边界；无人需要则忽略",
                "source": "library",
            })

    # C001：被 `走/交给 xxx 技能` 显式指认、但库里不存在的技能。
    # 刻意极窄（宁可漏报）：文件/脚本/目录/配置引用（backends.md、loop.py、config、templates/…）
    # 不是技能交接，最容易误报，所以要求——同句明确出现「技能/skill」、target 无扩展名/路径、
    # 且不是「xx 类方法/方法论」这种泛指。外部/宿主技能走白名单。
    handoff_re = re.compile(r"(?:走|交给|交[给由]|用)\s*`?([a-z][a-z0-9-]{1,40})`?")
    fileish = re.compile(r"[./]|\.(md|py|sh|json|txt|yaml|yml)$")
    dir_words = {"references", "reference", "scripts", "assets", "templates", "config",
                 "examples", "tests", "data", "evals", "requirements"}
    skill_word = re.compile(r"技能|(?<![a-z_])skill(?![a-z_])", re.I)
    method_context = re.compile(r"类方法|方法论|方法(?!论)|文件|脚本|目录|配置|适配|参数|命令")
    for s in skills:
        text = str(s["fm"].get("description", "")) + "\n" + s["body"]
        for sent in split_sentences(text):
            if not skill_word.search(sent):
                continue
            for m in handoff_re.finditer(sent):
                t = m.group(1)
                if t in dir_words or fileish.search(t) or method_context.search(sent):
                    continue
                if t in known_names or t in external_ok:
                    continue
                if any(n == t or n.startswith(t) or t.startswith(n) for n in known_names):
                    continue
                out.append({
                    "sev": "mid", "rule": "C001", "kind": "悬空技能交接",
                    "skill": s["dir"],
                    "evidence": f"把任务指给技能「{t}」，但库里没有该技能：{sent.strip()[:90]}",
                    "action": "补该技能或改指现有技能；若它是外部/系统技能，加入 external 白名单",
                    "source": "library",
                })
    return out


def check_library(root: Path):
    findings = []

    def add(rule, who, evidence):
        sev, rid, kind, action, source = rule
        findings.append({"sev": sev, "rule": rid, "kind": kind, "skill": who,
                         "evidence": evidence, "action": action, "source": source})

    skill_mds = sorted(root.glob("*/SKILL.md"))
    if not skill_mds and (root / "SKILL.md").exists():
        skill_mds = [root / "SKILL.md"]

    skills = []
    for sk_md in skill_mds:
        text = read_text(sk_md)
        fm, body, err = parse_frontmatter(text)
        skills.append({"dir": sk_md.parent.name, "path": sk_md, "fm": fm,
                       "body": body, "raw": text, "err": err})

    names = []
    declared = {}  # name -> description（用于撞车）

    for s in skills:
        # 关键：循环内必须重新绑定到「当前技能」的路径。
        # 之前这里沿用了外层收集 skills 时残留的最后一个 sk_md，
        # 导致引用/围栏/孤儿/绑定/密钥检查全跑到最后一个技能目录上，产生成片误报。
        sk_md = s["path"]
        sk_dir = sk_md.parent
        d, fm, body, raw = s["dir"], s["fm"], s["body"], s["raw"]

        if s["err"]:
            add(R_FM_YAML, d, s["err"])

        for k in fm:
            if k not in ALLOWED_FM_KEYS:
                add(R_FM_UNKNOWN_KEY, d, f"非常用 frontmatter 字段：{k}")

        nm = fm.get("name")
        if not nm:
            add(R_NAME_MISSING, d, "frontmatter 无 name")
        else:
            nm = str(nm).strip()
            names.append(nm)
            if not re.match(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$", nm) and not re.match(r"^[a-z0-9]$", nm):
                add(R_NAME_BAD, d, f"name='{nm}' 不符合 ^[a-z0-9-]+$ 规范")
            if len(nm) > 64:
                add(R_NAME_BAD, d, f"name 长度 {len(nm)} > 64")
            if "anthropic" in nm or "claude" in nm:
                add(R_NAME_RESERVED, d, f"name='{nm}' 含保留词")
            if nm != d:
                add(R_NAME_DIR, d, f"目录名 '{d}' 与 name '{nm}' 不一致")

        desc = fm.get("description")
        if desc is None or not str(desc).strip():
            add(R_DESC_MISSING, d, "无 description")
            desc = ""
        desc = str(desc)
        if desc:
            declared[nm or d] = desc
            if len(desc) > 1024:
                add(R_DESC_LONG, d, f"description {len(desc)} 字符 > 1024")
            if "<" in desc or ">" in desc:
                add(R_DESC_ANGLE, d, "description 含 < 或 >")
            if len(desc) < 60:
                add(R_DESC_SHORT, d, f"description 仅 {len(desc)} 字符")
            if not WHEN_PAT.search(desc):
                add(R_DESC_NOWHEN, d, "description 未写「何时触发/适用/不适用」")
            if not SAMPLE_PAT.search(desc):
                add(R_DESC_NOSAMPLE, d, "未出现引号包裹的用户真实说法样例")

        if not BORDER_PAT.search(body) and not DESC_BORDER_PAT.search(desc):
            add(R_BODY_NOBORDER, d, "正文与 description 都没写「不适用/边界」（边界至少在路由行出现一次）")

        body_lines = body.splitlines()
        if len(body_lines) > 500:
            add(R_BODY_LONG, d, f"正文 {len(body_lines)} 行 > 500，建议下沉 references/")

        # 代码围栏闭合：只查 SKILL.md 与 references/，排除 tests/fixtures（负例夹具本就故意坏）。
        scan_mds = [s["path"]]
        ref_dir = sk_dir / "references"
        if ref_dir.exists():
            scan_mds += [p for p in ref_dir.rglob("*.md")]
        for mf in scan_mds:
            if sum(1 for ln in read_text(mf).splitlines() if FENCE_RE.match(ln)) % 2 == 1:
                add(R_FENCE_OPEN, d, f"{mf.relative_to(root)} 代码围栏未成对闭合")

        # broken references：只看 SKILL.md「正文」（去掉代码围栏/命令）里指向本地的真实链接。
        for t in extract_local_targets(strip_fences(raw)):
            if not (sk_dir / t).resolve().exists():
                add(R_REF_BROKEN, d, f"SKILL.md 引用的 {t} 不存在")

        # S002 仅查 references/ 下真正长（>200 行）且顶部没有任何导航/标题结构的文件；
        # README、示例库、有清晰分节标题的都不算。S003（reference 嵌套层级）规则噪声大、
        # 违背正常渐进披露，已下线（语义层见 health-check.md）。
        direct_targets = {Path(t).name for t in extract_local_targets(strip_fences(raw))}
        if ref_dir.exists():
            for rf in ref_dir.rglob("*.md"):
                rtxt = read_text(rf)
                if len(rtxt.splitlines()) > 200 and not has_nav_or_headings(rtxt):
                    add(R_REF_NOTOC, d,
                        f"references/{rf.relative_to(ref_dir)} {len(rtxt.splitlines())} 行，顶部缺目录/清晰分节")

        # S004 孤儿 reference（高精确、宁可漏报）：references/ 下的 md，只要在技能目录
        # 任意 md/py/sh（SKILL 或别的 reference、脚本）里出现过文件名/主干，就算被用
        #（二级 reference 是正常渐进披露，不算孤儿）。全技能没有任何文件提到才提示。
        corpus = "\n".join(read_text(p) for p in list(sk_dir.rglob("*.md"))
                           + list(sk_dir.rglob("*.py")) + list(sk_dir.rglob("*.sh")))
        if ref_dir.exists():
            for rf in ref_dir.rglob("*.md"):
                if rf.name not in corpus and rf.stem not in corpus:
                    add(R_REF_ORPHAN, d,
                        f"references/{rf.relative_to(ref_dir)} 全技能无任何文件点名，确认是否还需要")

        # S005 只查技能根目录散落的空壳占位文件（example/sample/template 命名且体积极小）；
        # references/templates 里的正常模板库、测试夹具、正文里出现 TODO 字样都不算。
        for p in sk_dir.iterdir():
            if p.is_file() and PLACEHOLDER_NAME_RE.search(p.name) \
                    and p.suffix in {".md", ".txt"} and p.stat().st_size < 40:
                add(R_PLACEHOLDER, d, f"疑似空壳占位文件：{p.name}")

        # 平台硬绑定：只扫 SKILL.md 正文（不含代码块）。README 安装示例、CHANGELOG 变更记录、
        # 可移植性文档里教用户怎么拷到 ~/.trae/skills 的命令，都是合法内容，不判绑定。
        body_nofence = strip_fences(raw)
        hard_hits = sorted({m.group(0)[:40] for pat in HARD_PATTERNS
                            for m in [re.search(pat, body_nofence)] if m})
        if hard_hits:
            add(R_HARD_BIND, d, "; ".join(hard_hits))
        soft_hits = sorted({m.group(0) for pat in SOFT_PATTERNS
                            for m in [re.search(pat, body_nofence)] if m})
        if soft_hits and not re.search(SOFT_DEGRADE_HINT, body_nofence):
            add(R_SOFT_BIND, d, "; ".join(soft_hits))

        # 疑似密钥：排除 tests/ 与测试文件（这些地方会故意放假密钥串做负例）。
        for p in sk_dir.rglob("*"):
            if "tests" in p.parts or "fixtures" in p.parts \
                    or p.name.startswith("test_") or p.name.endswith("_test.py"):
                continue
            if p.is_file() and p.suffix in {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".txt"}:
                if SECRET_RE.search(read_text(p)):
                    add(R_SECRET, d, f"{p.relative_to(root)} 出现疑似硬编码密钥")

    # 重名
    for nm in sorted({x for x in names if names.count(x) > 1}):
        add(R_NAME_DUP, nm, "多个技能声明同一 name")

    # 库级覆盖：覆盖真空 / 悬空交接。外部/系统技能（宿主提供、不在本库）走白名单，不判悬空。
    external_ok = {
        "skill-creator", "skill-creator-for-work", "lark-doc", "lark-drive",
        "doubao-visualization", "doubao-creative-design", "word", "pdf", "sheet",
        "html", "browser-task", "ppt",
    }
    findings.extend(coverage_scan(skills, set(names) | {s["dir"] for s in skills}, external_ok))

    return skills, findings


def main():
    ap = argparse.ArgumentParser(description="技能库静态健康体检")
    ap.add_argument("root", nargs="?", default=".", help="技能库目录（默认自动发现）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--save-baseline", metavar="FILE", help="把当前问题集写入基线文件")
    ap.add_argument("--baseline", metavar="FILE", help="只报告基线之外的新问题")
    args = ap.parse_args()

    root = find_library(Path(args.root))
    if root is None:
        print(f"找不到技能库：{Path(args.root).resolve()} 及其上级均无多个 <name>/SKILL.md", file=sys.stderr)
        sys.exit(2)

    _, findings = check_library(root)

    if args.save_baseline:
        base = sorted({f"{f['rule']}@{f['skill']}" for f in findings})
        Path(args.save_baseline).write_text(
            json.dumps({"root": str(root), "baseline": base}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"已写入基线 {args.save_baseline}：{len(base)} 条存量问题")

    if args.baseline:
        bp = Path(args.baseline)
        if not bp.exists():
            print(f"基线文件不存在：{bp}", file=sys.stderr)
            sys.exit(2)
        base = set(json.loads(bp.read_text(encoding="utf-8")).get("baseline", []))
        findings = [f for f in findings if f"{f['rule']}@{f['skill']}" not in base]

    skill_count = len(list(root.glob("*/SKILL.md"))) or (1 if (root / "SKILL.md").exists() else 0)
    summary = {}
    for f in findings:
        summary[f["kind"]] = summary.get(f["kind"], 0) + 1
    report = {"root": str(root), "skill_count": skill_count,
              "summary": summary, "findings": findings}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"技能库: {root}\n技能数: {skill_count}\n")
        order = {"high": 0, "mid": 1, "low": 2}
        for f in sorted(findings, key=lambda x: (order[x["sev"]], x["rule"], x["skill"])):
            print(f"[{f['sev'].upper():4} {f['rule']}] {f['kind']:<12} {f['skill']}")
            print(f"        证据: {f['evidence']}")
            print(f"        建议: {f['action']}")
        print(f"\n汇总: {summary if summary else '静态规则全部通过'}")
        print("注：仅静态检查。语义质量（退出条件/重试上限/可观察触发/规则矛盾）见 health-check.md 人工清单；")
        print("    真实触发率等动态检查归 Harness 层。规则依据见 references/health-check.md。")

    sys.exit(1 if any(f["sev"] == "high" for f in findings) else 0)


if __name__ == "__main__":
    main()
