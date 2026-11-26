#!/usr/bin/env python3
"""技能库健康与双模适配体检（可移植、零平台依赖、纯标准库）。

用法：
    python3 library_doctor.py [技能库目录] [--json] [--max-desc-total 4500]
    python3 library_doctor.py [目录] --strict                    # mid 也返回 exit 1
    python3 library_doctor.py [目录] --external-skills s1,s2     # 补充宿主技能白名单
    python3 library_doctor.py [目录] --save-baseline baseline.json
    python3 library_doctor.py [目录] --baseline baseline.json

设计边界：
- 静态与文本线索检查：frontmatter、description 预算与路由信号、引用完整性、
  隐形前置必读税、强模型拐杖密度、维护信息泄露、跨技能串联与规范冲突、
  平台绑定与密钥。
- P3 语义项（强弱双模消融、真实撞车、退出条件等）见 references/health-check.md。
- 动态项（真实会话触发率、读取顺序、端到端成功率）归 Harness 层，本工具不做。
- 只报告，不修改任何文件。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import yaml  # 宿主通常自带；没有则走下面的轻量解析
except Exception:  # pragma: no cover
    yaml = None

# ---------------------------------------------------------------- 规则目录
# 每条规则：(severity, 规则ID, 名称, 修复建议, 来源)
# severity: high=硬错误(exit 1) / mid=路由、预算与冲突(--strict exit 1) / low=结构与减负提示

R_NAME_MISSING   = ("high", "F001", "缺 name",             "补 frontmatter name", "quick_validate/Anthropic")
R_NAME_BAD       = ("high", "F002", "name 非法",           "name 仅允许小写字母/数字/连字符，不以连字符开头结尾、无连续连字符，≤64 字符", "Anthropic/quick_validate")
R_NAME_RESERVED  = ("high", "F003", "name 含保留词",       "不得含 anthropic/claude 等保留词", "Anthropic")
R_NAME_DIR       = ("mid",  "F004", "name 与目录不一致",   "统一 frontmatter name 与目录名", "quick_validate")
R_NAME_DUP       = ("high", "F005", "name 重名",           "多个技能声明同一 name，改名消歧", "library")
R_FM_YAML        = ("high", "F006", "frontmatter 非法",    "修复 YAML 语法", "quick_validate")
R_FM_UNKNOWN_KEY = ("low",  "F007", "frontmatter 非常用字段", "确认该字段是宿主支持的，否则移入 metadata", "quick_validate")
R_DESC_MISSING   = ("high", "F008", "缺 description",      "补 description（做什么+何时触发+不适用）", "Anthropic/quick_validate")
R_DESC_LONG      = ("high", "F009", "description 超长",    "description ≤1024 字符，细节移正文", "Anthropic/quick_validate")
R_DESC_ANGLE     = ("high", "F010", "description 含尖括号",  "去掉 < >（会与标签冲突）", "Anthropic/quick_validate")

R_DESC_SHORT     = ("mid",  "D001", "description 过短",        "过短难以承载「做什么+何时触发+边界」，建议 ≥60 字", "Anthropic 双要素")
R_DESC_NOWHEN    = ("mid",  "D002", "description 缺触发时机",  "补「何时用/触发词/当……时」，路由只看这一行", "Anthropic/agent-skill-linter")
R_DESC_NOSAMPLE  = ("low",  "D003", "description 缺用户原话样例", "加 1-3 个用户真实会说的触发短语（引号包裹）", "Anthropic")
R_BODY_NOBORDER  = ("mid",  "D004", "正文缺不适用边界",    "写明不适用场景及与相邻技能的互斥/交接", "library")

R_DESC_BLOATED   = ("mid",  "B001", "description 过胖",      "将辨析、反例与背景下沉正文或 references/，description 控制在 ≤260 字符以防挤压全库索引", "library/dual-model")
R_DESC_TOTAL     = ("mid",  "B002", "全库 description 超预算", "压缩过长 description，使全库总字符控制在预算内（默认 ≤4500），避免宿主截断丢技能", "library/dual-model")
R_STARTUP_HEAVY  = ("mid",  "B003", "隐形前置必读过重",    "改为按阶段或按分支按需读取，删去无条件起手必读要求；单次启动控制在 ≤350 行（必读参考 ≤250 行）", "library/dual-model")
R_OVER_SCAFFOLD  = ("low",  "B004", "强模型拐杖过重",      "删减机械算术配额、禁止内部思考规定或大量复读式强迫约束，轻任务留直通快路径，示范下沉按需 references/", "library/dual-model")
R_MAINT_LEAK     = ("low",  "B005", "维护信息混入运行时",  "把维护说明、发版校验命令、仓内内部路径和版本考古移出运行时 SKILL.md（可迁至 README 或 CHANGELOG）", "library/dual-model")

R_REF_BROKEN     = ("high", "R001", "引用文件不存在",      "修复路径或补文件（broken reference）", "ai-skill-lint Structure")
R_FENCE_OPEN     = ("mid",  "R002", "代码围栏未闭合",      "代码围栏 ``` 数量为奇数，补全闭合", "ai-skill-lint Content")

R_HARD_BIND      = ("high", "P001", "平台硬绑定",          "去掉绝对路径/宿主目录，改成参数或自动发现", "library")
R_SOFT_BIND      = ("low",  "P002", "平台弱引用待确认",    "确认是软依赖：写明「需要时才用，缺失则降级到通用方式」", "library")

R_BODY_LONG      = ("low",  "S001", "SKILL.md 超长",       "正文 >500 行，把条件性细节下沉到 references/", "Anthropic 渐进披露")
R_REF_NOTOC      = ("low",  "S002", "长 reference 缺目录", ">200 行的 reference 文件顶部加目录或分节标题", "Anthropic")
R_REF_ORPHAN     = ("low",  "S004", "资源未被主文件引用",  "确认该文件是否需要；需要则在 SKILL.md 标明何时读", "Anthropic")
R_PLACEHOLDER    = ("low",  "S005", "残留占位/待办",       "删除模板示例文件或补全 TODO/占位内容", "skill-creator/ai-skill-lint")
R_SECRET         = ("high", "S006", "疑似硬编码密钥",      "立即移除密钥，改用环境变量/配置", "ai-skill-lint Security")

R_C_DANGLING     = ("mid",  "C001", "悬空技能交接",        "正文/description 把任务指给了一个库中不存在的技能；补该技能、改指现有技能或加入 external 白名单", "library")
R_C_VACUUM       = ("mid",  "C003", "疑似覆盖真空",        "多个技能都把这类任务排除/指走，却没有任何技能正面认领；核对后补一个承接方或明确边界", "library")

R_CHAIN_COUPLE   = ("mid",  "X001", "跨技能串联过深或单向豁免", "简化上游→下游串联层级（避免 ≥3 跳或环）；上游依赖下游豁免时须确保双方文档对称对齐", "library/dual-model")
R_CROSS_CLASH    = ("mid",  "X002", "疑似跨技能规则打架",  "按「唯一主责协议」对齐相连或并行技能在小标题体例、翻案句型或机理-比喻顺序上的互斥指令", "library/dual-model")
R_SELF_CLASH     = ("mid",  "X003", "疑似技能内部规则自相矛盾", "检查技能正文与 references/ 对同一事项是否给出冲突规范，保留唯一生效条款", "library/dual-model")
R_OMNI_TRIGGER   = ("mid",  "X004", "全域触发撞车风险",    "收窄近全域触发措辞并补齐「不适用/与相邻技能分流/豁免」规则（常驻规范应归宿主层）", "library/dual-model")

ALLOWED_FM_KEYS = {"name", "description", "license", "allowed-tools", "compatibility", "metadata", "disable-model-invocation"}
DEFAULT_EXTERNAL_SKILLS = {
    "skill-creator", "lark-doc", "lark-drive",
    "word", "pdf", "sheet", "html", "browser-task", "ppt",
}

HARD_PATTERNS = [
    r"/Users/[^\s'\")\]]+",
    r"/home/[^\s'\")\]]+",
    r"C:\\",
    r"\.doubaowork",
    r"~/\.trae/skills",
    r"~/\.claude/skills",
]
SOFT_PATTERNS = [r"lark-cli", r"lark-doc", r"feishu\.cn", r"飞书文档?"]
SOFT_DEGRADE_HINT = r"若(具备|有|需要|可用|没有|缺失|无)|可降级|降级|没有.*时|(缺|无).*时|可选"

WHEN_PAT = re.compile(
    r"适用|用于|用时|时(?:使用|调用|用|触发|启用)|当.{0,14}(?:时|用)|触发|何时|"
    r"不适用|不要用|不走|不做|不负责|use when|when to", re.I)
SAMPLE_PAT = re.compile(r"[「『“‘\"'][^」』”’\"']{2,30}[」』”’\"']")
BORDER_PAT = re.compile(
    r"不适用|不启用|不要用|不用|不触发|不负责|边界|何时不用|不做|不走|只做|只用于|适用范围")
DESC_BORDER_PAT = re.compile(r"不适用|不要用|不做|不走|不接|不负责|区别|分别走|vs")

FENCE_RE = re.compile(r"^\s*```")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
BARE_RES_RE = re.compile(r"(?<![\w/.\-])((?:references|reference|scripts|assets)/[A-Za-z0-9_./\-]*[A-Za-z0-9_\-])")
REF_FILE_EXT_RE = re.compile(r"\.(?:md|py|sh|mjs|js|json|ya?ml|txt|toml)$", re.I)
SECRET_RE = re.compile(
    r"(?i)(?:api[_-]?key|secret|access[_-]?token|password)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']"
)
PLACEHOLDER_NAME_RE = re.compile(r"example|sample|template|示例|样板", re.I)

# B003 隐形前置必读检测
MANDATORY_READ_CUES = re.compile(
    r"先读|先\s*Read|动手前.{0,8}读|必读|必须.{0,4}(?:读|走)|每次.{0,8}读|均须.{0,6}读|"
    r"起手.{0,6}读|全部加载|写正文前必读|成稿必读|"
    r"(?:^|\s|[1-9]\.\s*|[-*]\s*)(?:读取|逐条过|过|按)\s*(?:包内\s*)?`?(?:references|templates)/"
)
CONDITIONAL_READ_HINTS = re.compile(
    r"按需|可选|必要时|若需要|不要每次加载|不要全部加载|不必全部加载|仅.{0,12}时读|"
    r"对应小节|按对象类型|按步|非必读|分支|没有就|缺失时|兜底时读|遇到.{0,10}时读"
)
MANDATORY_PATH_RE = re.compile(r"`?((?:references|templates)/[A-Za-z0-9_./\-]+\.md)`?")

# B004 / B005 强模型拐杖与维护泄露
CRUTCH_REDO_RE = re.compile(r"视为(?:本次)?失败.{0,6}重做|写不出.{0,14}=.{0,8}(?:不许交|没想清楚|没数)|不许心里默念")
CRUTCH_MATH_RE = re.compile(r"向上取整|ceil\(|平地句在\s*P|全文段落占比\s*[≤<]=?\s*\d+%|(?:总分|评分|得分)\s*[<≤]\s*\d+\s*/\s*\d+.*重写")
CRUTCH_COSTUME_RE = re.compile(r"不是可选项|必做动作（写死）|任何一篇的骨架都是|按惯例应追加到.{0,16}(?:链接|路径)给我|每[段节]必须配.{0,10}(?:比喻|金句|反问)|一字不差.{0,6}套用")
CRUTCH_META_CLOSE_RE = re.compile(r"收口自检多答一句|(?:先)?原样发.{0,20}开场话术|开场(?:话术|白).{0,10}一字不差")
COERCIVE_WORD_RE = re.compile(r"必须|严禁|禁止|不得|强制|一律|绝不|决不|不许")
MAINT_HEADING_RE = re.compile(r"^#{1,3}\s+.*(?:维护说明|发版说明|开发说明|版本考古|维护状态)", re.M)
MAINT_TEXT_RE = re.compile(r"check_vendored\.py|docs/SKILL-QUALITY-CARD\.md|不再用旧的\s*0\.|自称[\"「]?版本\s*\d")

# X 系列：反例行过滤、极性与串联模式
ANTI_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:❌|反例[:：]|错误示例[:：]|错误写法[:：]|坏样例[:：]|旧病[:：]|错[:：])")
EDGE_NEG_SENT = re.compile(
    r"不适用|不走|不接|不要用|不用|排除|不归|不是|不做|不替代|区别|让位|分流|(?<![a-zA-Z])vs(?![a-zA-Z])|"
    r"只负责.{0,12}不|不在本技能|不反向|不可用|没有.{0,8}时|缺失时|可选|跳过|它不做什么|"
    r"对比项|何时不用|仅作其他技能|如.{0,20}调用本技能"
)
CARVEOUT_RE = re.compile(r"豁免|除外|不清理|保留.{0,14}例外|冲突.{0,8}以.{0,16}为准")

H2_NOUN_RE = re.compile(r"H2(?:/H3)?\s*(?:是|写).{0,12}(?:短关键词|短模块目录|目录项)|标题不写成问句/论点句")
H2_CLAIM_RE = re.compile(r"小标题(?:自己)?是一句能立住的话|章节小标题直接写本节要点|小标题是\*\*一句论点\*\*")
B2_USE_RE = re.compile(r"你可能以为是?\s*A.{0,8}其实是?\s*B|新手会误以为\s*X.{0,8}其实是?\s*Y")
B2_NEG_RE = re.compile(r"删|禁|拆|严禁|反例|清理|禁止|不要|不得")
B2_BAN_RE = re.compile(r"必须拆掉翻案壳|翻案体一律拆掉")
METAPHOR_FIRST_RE = re.compile(r"先白话给画面.{0,16}再.{0,12}工程事实|每个硬核转折.{0,10}(?:至少一个)?比喻")
MECHANICS_FIRST_RE = re.compile(r"机制写前面.{0,16}类比.{0,8}后面|叠在机制后面|门槛型比喻零容忍|先用一两句话写清.{0,12}比喻叠在后面")
OMNI_TRIGGER_RE = re.compile(r"任何一次|每次.{0,8}都|默认常驻|所有.{0,8}都|一切.{0,12}都过一遍")
OMNI_EXCLUSION_RE = re.compile(r"不适用|不负责|不接|豁免|例外")

COVERAGE_VACUUMS = [
    {
        "name": "(源码/仓库)调研并落成文档/分享",
        "a": re.compile(r"调研|源码|开源|仓库|github|repo|读码|拆解.{0,4}项目", re.I),
        "b": re.compile(r"成稿|报告|文档|研判|解读|分享|博客|slides|文章|talk", re.I),
    },
]
CLAIM_CROSS = re.compile(
    r"先走本技能|走本技能|都先走|都走本技能|承接|负责.{0,6}调研|调研.{0,12}先走|"
    r"任何.{0,4}调研.{0,16}(先走|走本)|可以.{0,10}(产出|写).{0,8}(报告|文档|成稿|研判|解读)|"
    r"直接产出.{0,6}(调研|报告|解读)")
PUSH_CROSS = re.compile(
    r"走\s*`?[a-z][a-z0-9-]{2,}|调研.{0,14}(不适用|不接|不用|不走|交(给|由))|"
    r"(不适用|不接|不用|不走).{0,10}调研|对内.{0,6}调研.{0,8}不")


def strip_fences(text: str) -> str:
    """移除 markdown 代码围栏内的行。"""
    out, in_fence = [], False
    for ln in text.splitlines():
        if FENCE_RE.match(ln):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(ln)
    return "\n".join(out)


def strip_active_text(text: str) -> str:
    """去掉代码围栏、HTML 注释、删除线旧条款(~~...~~)与明显反例行，减少文本对比误报。"""
    no_fence = re.sub(r"<!--.*?-->", "", strip_fences(text), flags=re.S)
    cleaned_lines = []
    for ln in no_fence.splitlines():
        if ANTI_LINE_RE.match(ln):
            continue
        ln_no_strike = re.sub(r"~~[^~\n]+~~", "", ln)
        cleaned_lines.append(ln_no_strike)
    return "\n".join(cleaned_lines)


def split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"[。；;\n]", text) if s.strip()]


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
        except Exception as e:
            return {}, body, f"YAML 解析失败：{e}"
    return _tiny_yaml(head), body, None


def _tiny_yaml(head: str) -> dict:
    """无 PyYAML 时的兜底解析。"""
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


def extract_local_targets(md: str) -> list[str]:
    """抽取 SKILL.md 指向技能本地文件的目标。"""
    noinline = re.sub(r"`[^`\n]+`", "", md)
    targets = []
    for raw in LINK_RE.findall(noinline):
        t = raw.strip().split()[0].strip("\"'").split("#", 1)[0].split("?", 1)[0]
        if not t or re.match(r"^(https?:|mailto:|#|/)", t):
            continue
        targets.append(t)
    for raw in BARE_RES_RE.findall(md):
        targets.append(raw)
    return targets


def extract_ref_local_targets(md: str) -> list[str]:
    """抽取 reference 文档正文指向的本地文件引用。"""
    nofence = strip_fences(md)
    noinline = re.sub(r"`[^`\n]+`", "", nofence)
    targets = []
    for raw in LINK_RE.findall(noinline):
        t = raw.strip().split()[0].strip("\"'").split("#", 1)[0].split("?", 1)[0]
        if not t or re.match(r"^(https?:|mailto:|#|/)", t):
            continue
        if REF_FILE_EXT_RE.search(t) or t.startswith(("references/", "reference/", "scripts/", "assets/", "../")):
            targets.append(t)
    for raw in BARE_RES_RE.findall(nofence):
        if REF_FILE_EXT_RE.search(raw):
            targets.append(raw)
    return targets


def has_nav_or_headings(text: str) -> bool:
    head = "\n".join(text.splitlines()[:40])
    if len(re.findall(r"\]\(#[^)]+\)", head)) >= 2:
        return True
    return len(re.findall(r"^#{1,3}\s+\S", head, re.M)) >= 3


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def find_library(start: Path):
    cur = start.resolve()
    for d in [cur] + list(cur.parents):
        if len(list(d.glob("*/SKILL.md"))) >= 2:
            return d
    return cur if (cur / "SKILL.md").exists() else None


def measure_startup_footprint(skill: dict) -> tuple[int, int, int, list[str]]:
    """计算单次启动实效行数：body_lines + 去重后的无条件前置必读参考行数。"""
    sk_dir = skill["path"].parent
    body_lines = len(skill["body"].splitlines())
    body_nofence = strip_fences(skill["body"])
    seen_refs: dict[Path, tuple[str, int]] = {}

    for raw_ln in body_nofence.splitlines():
        is_table_row = raw_ln.lstrip().startswith("|")
        # 表格索引用途通常按步骤/按需查；仅当明确标了默认或必读时才按起手必读计入
        for sent in re.split(r"[。；;]", raw_ln):
            s = sent.strip()
            if not s:
                continue
            if CONDITIONAL_READ_HINTS.search(s):
                continue
            if is_table_row and not re.search(r"默认|必读|每次", s):
                continue
            if not MANDATORY_READ_CUES.search(s):
                continue
            for rel in MANDATORY_PATH_RE.findall(s):
                target = (sk_dir / rel).resolve()
                if target.is_file() and target not in seen_refs:
                    seen_refs[target] = (rel, len(read_text(target).splitlines()))

    ref_lines = sum(cnt for _, cnt in seen_refs.values())
    ref_names = [f"{rel}({cnt}L)" for rel, cnt in seen_refs.values()]
    return body_lines, ref_lines, body_lines + ref_lines, ref_names


def skill_corpus(skill: dict) -> str:
    """收集技能自身的 active 语料（SKILL.md + references/*.md），排除反例与删除线。"""
    sk_dir = skill["path"].parent
    parts = [strip_active_text(skill["raw"])]
    ref_dir = sk_dir / "references"
    if ref_dir.exists():
        for rf in sorted(ref_dir.rglob("*.md")):
            parts.append(strip_active_text(read_text(rf)))
    return "\n".join(parts)


def skill_runtime_lines_with_fences(skill: dict) -> list[str]:
    """收集 SKILL.md 与 references/*.md 行（含代码围栏模板），仅去掉注释、删除线与反例行。"""
    sk_dir = skill["path"].parent
    files = [skill["path"]]
    ref_dir = sk_dir / "references"
    if ref_dir.exists():
        files.extend(sorted(ref_dir.rglob("*.md")))
    lines: list[str] = []
    for f in files:
        raw = re.sub(r"<!--.*?-->", "", read_text(f), flags=re.S)
        for ln in raw.splitlines():
            if ANTI_LINE_RE.match(ln):
                continue
            lines.append(re.sub(r"~~[^~\n]+~~", "", ln))
    return lines


def check_runtime_template_clashes(skill: dict, corpus: str, intra_set: set[str]) -> None:
    """检查正文禁令与代码块模板/静默约定之间的跨文件自相矛盾。"""
    lines = skill_runtime_lines_with_fences(skill)
    ban_line_re = re.compile(r"不套|不要套|不印|禁止?|不要|反例|❌|已删|移除|写死")

    # 1) TL;DR 五字段/自指栏目名禁令 vs 正面模板列出
    tldr_ban = re.search(r"(?:不套|不要套|不印|禁)[^。\n]{0,24}(?:五字段|这篇讲|最后引出)", corpus)
    if tldr_ban:
        tldr_pos_re = re.compile(r"五字段逐条列|-\s*(?:这篇讲|最后引出)[：:]")
        if any(tldr_pos_re.search(ln) and not ban_line_re.search(ln) for ln in lines):
            intra_set.add("template_tldr_clash")

    # 2) 默认静默 〔思考：…〕 过程横幅 vs 另一处无条件要求开头输出
    banner_silent = re.search(r"默认不输出.{0,16}〔思考|默认静默.{0,20}过程(?:标签|横幅)|不主动打印.{0,12}过程标签", corpus)
    if banner_silent:
        banner_req_re = re.compile(r"(?:必须|一律|开头(?:输出|带|附|加)).{0,24}〔思考[：:]|回答开头.{0,12}〔思考[：:]")
        cond_re = re.compile(r"仅当|显式要求|明确要求|不(?:带|输出|印)|静默|禁止|❌|反例")
        if any(banner_req_re.search(ln) and not cond_re.search(ln) for ln in lines):
            intra_set.add("banner_silent_clash")


def collect_skill_polarities(corpus: str) -> dict[str, set[str]]:
    """提取单个技能在小标题体例、翻案句型与机理-比喻顺序上的立场极性。"""
    pol: dict[str, set[str]] = defaultdict(set)
    clauses = split_sentences(corpus)

    for cl in clauses:
        if H2_NOUN_RE.search(cl):
            pol["h2"].add("noun")
        if H2_CLAIM_RE.search(cl):
            pol["h2"].add("claim")
        if B2_USE_RE.search(cl) and not B2_NEG_RE.search(cl):
            pol["b2"].add("use")
        if B2_BAN_RE.search(cl):
            pol["b2"].add("ban")
        if METAPHOR_FIRST_RE.search(cl):
            pol["order"].add("metaphor_first")
        if MECHANICS_FIRST_RE.search(cl):
            pol["order"].add("mechanics_first")

    if "不设全局禁令" in corpus or "不采用全局样式禁令" in corpus or "不是默认规则" in corpus:
        pol["intra"].add("no_global_ban")
    if re.search(r"严禁.{0,12}渐变|禁用彩虹|严禁\s*ease-in|禁止使用\s*Emoji", corpus):
        pol["intra"].add("hard_global_ban")
    if any("B2" in c and re.search(r"必须拆掉|默认清理", c) for c in clauses) and \
       any("B2" in c and "绝不自动改" in c for c in clauses):
        pol["intra"].add("b2_authority_clash")
    if any("拆分段落" in c and re.search(r"标准档.{0,8}可以动", c) for c in clauses) and \
       any("拆分段落" in c and "须先由作者决定" in c for c in clauses):
        pol["intra"].add("para_split_clash")
    if "不用冒号后挂判断" in corpus and re.search(r"需要时加冒号.{0,16}判断", corpus):
        pol["intra"].add("colon_h2_clash")
    if re.search(r"≤\s*1\s*处.{0,10}造词", corpus) and re.search(r"≥\s*1\s*处.{0,10}造词", corpus):
        pol["intra"].add("coin_quota_clash")
    if re.search(r"软约束.{0,12}不阻断", corpus) and re.search(r"不许下笔|空着\s*=\s*不许删", corpus):
        pol["intra"].add("soft_hard_clash")

    return pol


def build_positive_edges(skills: list[dict], known_dirs: set[str]) -> tuple[dict[str, set[str]], dict[tuple[str, str], str]]:
    """提取库内明确正向运行时串联边 A -> B 及并行/豁免线索（排除边界分流介绍）。"""
    edges: dict[str, set[str]] = defaultdict(set)
    carveouts: dict[tuple[str, str], str] = {}

    for s in skills:
        src = s["dir"]
        desc_pos = re.split(r"不适用[:：]", str(s["fm"].get("description", "")), maxsplit=1)[0]
        active = strip_active_text(desc_pos + "\n" + s["body"])
        others = sorted(d for d in known_dirs if d != src)
        if not others:
            continue
        for sent in split_sentences(active):
            if EDGE_NEG_SENT.search(sent):
                continue
            mentioned = [d for d in others if re.search(rf"(?<![a-z0-9-]){re.escape(d)}(?![a-z0-9-])", sent)]
            if not mentioned:
                continue
            for tgt in mentioned:
                if re.search(r"diagram_kit|Explainer", sent) and re.search(
                    r"只借图|不走.{0,12}文档流程|可选|用户需要时", sent
                ):
                    continue
                et = re.escape(tgt)
                pos_pat = re.compile(
                    rf"(?:(?:读取并执行|先?读取|调用|过一遍|先过|过(?=[^。\n]{{0,12}}(?:标准档|全套|清理|清洗|收尾|润色))|"
                    rf"交(?:给|由)?(?=\s*`?{et}`?[^。\n]{{0,14}}(?:标准档|重档|轻档|清洗|清理|收尾|去\s*AI\s*味|render))|"
                    rf"走\s*(?=`?{et}`?\s*(?:标准档|全套))|借用?|吃\s*)\s*`?{et}`?(?![a-z0-9-])|"
                    rf"并行[^。\n]{{0,24}}{et}|{et}[^。\n]{{0,24}}并行)"
                )
                if pos_pat.search(sent):
                    edges[src].add(tgt)
                    if CARVEOUT_RE.search(sent):
                        carveouts[(src, tgt)] = sent.strip()[:80]

    # 补充同文件内跨句写的豁免块（如 feynman §例外与分工、tangshan §豁免）
    for s in skills:
        src = s["dir"]
        active = strip_active_text(s["body"])
        for tgt in list(edges[src]):
            if (src, tgt) not in carveouts:
                for sent in split_sentences(active):
                    if tgt in sent and CARVEOUT_RE.search(sent):
                        carveouts[(src, tgt)] = sent.strip()[:80]
                        break
    return edges, carveouts


def check_budget_and_drag(skills: list[dict], max_desc_total: int, add_fn) -> tuple[list[dict], list[tuple]]:
    """执行 B 类（预算与强模型阻力）静态检测并收集指标明细。"""
    findings = []
    desc_lengths = []
    startup_stats = []

    for s in skills:
        d = s["dir"]
        desc = str(s["fm"].get("description") or "").strip()
        if desc:
            desc_lengths.append((d, len(desc)))
            if 260 < len(desc) <= 1024:
                add_fn(R_DESC_BLOATED, d, f"description {len(desc)} 字符 > 260，挤压常驻总预算")

        body_l, ref_l, total_l, ref_names = measure_startup_footprint(s)
        startup_stats.append((d, total_l, body_l, ref_l))
        if ref_l > 250 or total_l > 350:
            detail = "、".join(ref_names[:4]) + ("…" if len(ref_names) > 4 else "")
            add_fn(R_STARTUP_HEAVY, d,
                   f"SKILL 正文 {body_l} 行 + 必读 {len(ref_names)} 份参考 {ref_l} 行 = 合计 {total_l} 行（{detail}）")

        body_clean = strip_active_text(s["body"])
        body_lines = len(s["body"].splitlines())
        crutch_hits = []
        if CRUTCH_REDO_RE.search(body_clean):
            crutch_hits.append("强制重做/禁内部思考")
        if CRUTCH_MATH_RE.search(body_clean):
            crutch_hits.append("机械算术/占比配额")
        if CRUTCH_COSTUME_RE.search(body_clean):
            crutch_hits.append("戏服模板/强迫索要后缀")
        if CRUTCH_META_CLOSE_RE.search(body_clean):
            crutch_hits.append("机械元话语收尾/强制背诵开场脚本")
        coercive_cnt = len(COERCIVE_WORD_RE.findall(body_clean))
        if (body_lines > 180 and coercive_cnt >= 18) or (body_lines >= 60 and coercive_cnt >= 16):
            crutch_hits.append(f"正文 {body_lines} 行且强迫词 {coercive_cnt} 次")
        if crutch_hits:
            add_fn(R_OVER_SCAFFOLD, d, "；".join(crutch_hits))

        body_nofence = strip_fences(s["body"])
        maint_hits = []
        hm = MAINT_HEADING_RE.search(body_nofence)
        if hm:
            maint_hits.append(hm.group(0).strip())
        tm = MAINT_TEXT_RE.search(body_nofence)
        if tm:
            maint_hits.append(tm.group(0).strip())
        if maint_hits:
            add_fn(R_MAINT_LEAK, d, f"运行时正文含维护信息：{', '.join(sorted(set(maint_hits)))}")

    total_desc = sum(n for _, n in desc_lengths)
    if len(skills) >= 5 and total_desc > max_desc_total:
        avg = round(total_desc / len(desc_lengths)) if desc_lengths else 0
        top5 = ", ".join(f"{n}:{l}" for n, l in sorted(desc_lengths, key=lambda x: -x[1])[:5])
        add_fn(R_DESC_TOTAL, "【库级】description 总预算",
               f"{len(skills)} 技能合计 {total_desc} 字符（均值 {avg}，预算上限 {max_desc_total}）；前5：{top5}")

    return desc_lengths, startup_stats


def has_upstream_single_finish_guard(corpus: str, target_c: str) -> bool:
    """判断技能是否声明：被上游作为前置环节调用时不调用下游 target_c。"""
    sents = split_sentences(corpus)
    guard_re = re.compile(r"被.{0,120}调用时.{0,60}不.{0,16}调用|仅独立成稿时.{0,24}调用")
    tc_re = re.compile(rf"(?<![a-z0-9-]){re.escape(target_c)}(?![a-z0-9-])")
    for idx, sent in enumerate(sents):
        window = sent if idx + 1 >= len(sents) else f"{sent}。{sents[idx + 1]}"
        if guard_re.search(sent) and (tc_re.search(window) or "最终成稿技能" in window):
            return True
    return False


def is_h2_clash_yielded(upstream: str, downstream: str, corpora: dict[str, str]) -> bool:
    """当上游调用下游时，检查下游的小标题主张是否仅限独立成稿且显式向该上游让位。"""
    corp = corpora[downstream]
    claim_sents = [s for s in split_sentences(corp) if H2_CLAIM_RE.search(s)]
    if not claim_sents:
        return False
    if not all(("无上游" in s or "独立成稿" in s) for s in claim_sents):
        return False
    up_re = re.compile(rf"(?<![a-z0-9-]){re.escape(upstream)}(?![a-z0-9-])")
    yield_re = re.compile(r"遵守上游小标题体例|不把上游短目录小标题改写成")
    return any(yield_re.search(s) and up_re.search(s) for s in re.split(r"[。\n]", corp) if s.strip())


def check_cross_skill_conflicts(skills: list[dict], known_dirs: set[str], add_fn) -> None:
    """执行 X 类（跨技能串联、互斥打架、内部矛盾、全域触发）检测。"""
    corpora = {s["dir"]: skill_corpus(s) for s in skills}
    polarities = {d: collect_skill_polarities(c) for d, c in corpora.items()}
    edges, carveouts = build_positive_edges(skills, known_dirs)

    # X001: 串联过深 / 互调环 / 单向豁免
    reported_asym = set()
    deep_chains = []
    for a, targets in sorted(edges.items()):
        for b in sorted(targets):
            if a in edges.get(b, set()) and a < b:
                add_fn(R_CHAIN_COUPLE, f"【库级】{a} <-> {b}", "存在双向正向引用环，易在复杂任务中反复踢球")
            for c in sorted(edges.get(b, set())):
                if c != a and not has_upstream_single_finish_guard(corpora[b], c):
                    deep_chains.append(f"{a} → {b} → {c}")
            if (a, b) in carveouts:
                b_mentions_a = bool(re.search(rf"(?<![a-z0-9-]){re.escape(a)}(?![a-z0-9-])", corpora[b]))
                if not b_mentions_a and (a, b) not in reported_asym:
                    reported_asym.add((a, b))
                    add_fn(R_CHAIN_COUPLE, f"{a} → {b}",
                           f"{a} 声明局部豁免/优先级，但 {b} 从未提及或放行 {a}：{carveouts[(a, b)]}")

    if deep_chains:
        sample = "；".join(deep_chains[:5]) + (f" 等 {len(deep_chains)} 条" if len(deep_chains) > 5 else "")
        add_fn(R_CHAIN_COUPLE, "【库级】串联链 depth ≥ 3", f"存在 3 跳串联链，上下文税叠加：{sample}")

    # X002: 相连或并行技能间的极性直接打架
    seen_pairs = set()
    for a, targets in sorted(edges.items()):
        for b in sorted(targets):
            pair = tuple(sorted((a, b)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            pa, pb = polarities[a], polarities[b]
            clashes = []
            h2_clash = ("noun" in pa["h2"] and "claim" in pb["h2"]) or ("claim" in pa["h2"] and "noun" in pb["h2"])
            if h2_clash:
                yielded = ("noun" in pa["h2"] and b in edges.get(a, set()) and is_h2_clash_yielded(a, b, corpora)) or \
                          ("noun" in pb["h2"] and a in edges.get(b, set()) and is_h2_clash_yielded(b, a, corpora))
                if not yielded:
                    clashes.append("小标题体例互斥（短目录词 vs 完整论点句）")
            if ("use" in pa["b2"] and "ban" in pb["b2"]) or ("ban" in pa["b2"] and "use" in pb["b2"]):
                clashes.append("B2 句型冲突（正面误区翻转句 vs 一律拆壳）")
            if ("metaphor_first" in pa["order"] and "mechanics_first" in pb["order"]) or \
               ("mechanics_first" in pa["order"] and "metaphor_first" in pb["order"]):
                clashes.append("机理与比喻顺序互斥（先比喻后事实 vs 机理前置/零门槛比喻）")
            if clashes:
                add_fn(R_CROSS_CLASH, f"{a} ↔ {b}", "；".join(clashes))

    # X003 & X004: 单技能内部自相矛盾 + 全域触发撞车风险
    intra_labels = {
        "b2_authority_clash": "B2 处理权限冲突（默认必拆 vs 绝不自动改）",
        "para_split_clash": "标准档拆段权限冲突（可以动 vs 须由作者决定）",
        "colon_h2_clash": "H2 冒号判断冲突（禁止冒号挂判断 vs 允许冒号加判断）",
        "coin_quota_clash": "造词数量上限矛盾（≤1 处 vs ≥1 处）",
        "soft_hard_clash": "约束强度自相矛盾（宣称软约束不阻断 vs 无条件禁止下笔）",
        "template_tldr_clash": "跨文件模板冲突（正文禁用五字段/自指 TL;DR，但模板仍正面列出）",
        "banner_silent_clash": "过程标签冲突（正文默认静默 〔思考：〕，另一处仍无条件要求开头输出）",
    }
    for s in skills:
        d = s["dir"]
        p = polarities[d]
        check_runtime_template_clashes(s, corpora[d], p["intra"])
        self_hits = []
        if "no_global_ban" in p["intra"] and "hard_global_ban" in p["intra"]:
            self_hits.append("全局禁令矛盾（宣称不设全局禁令 vs 条款写死严禁/禁用）")
        if "metaphor_first" in p["order"] and "mechanics_first" in p["order"]:
            self_hits.append("同技能内机理-比喻顺序互搏（先比喻后事实 vs 机理前置）")
        for k, msg in intra_labels.items():
            if k in p["intra"]:
                self_hits.append(msg)
        if self_hits:
            add_fn(R_SELF_CLASH, d, "；".join(self_hits))

        desc = str(s["fm"].get("description") or "")
        body_clean = strip_active_text(s["body"])
        if OMNI_TRIGGER_RE.search(desc):
            has_desc_ex = bool(OMNI_EXCLUSION_RE.search(desc))
            has_body_route = bool(re.search(r"不适用|交由|归.{0,8}处理|豁免|分流|不越位", body_clean))
            if not has_desc_ex or not has_body_route:
                miss = "description 缺排除边界" if not has_desc_ex else "正文缺邻居分流/豁免说明"
                add_fn(R_OMNI_TRIGGER, d, f"description 含全域触发词且{miss}")


def coverage_scan(skills: list[dict], known_names: set[str], external_ok: set[str] | None = None) -> list[dict]:
    """库级覆盖：C003 覆盖真空 / C001 悬空交接。只给线索，结论由人核对。"""
    out = []
    external_ok = external_ok or set()

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
                    "action": "补该技能或改指现有技能；若它是外部/系统技能，通过 --external-skills 传入白名单",
                    "source": "library",
                })
    return out


def compute_metrics(desc_lengths: list[tuple[str, int]], startup_stats: list[tuple],
                    findings: list[dict], max_desc_total: int) -> dict:
    """汇总双模预算看板与按严重度/规则计数指标。"""
    sev_counts = {"high": 0, "mid": 0, "low": 0}
    rule_counts: dict[str, int] = {}
    for f in findings:
        sev = f["sev"]
        sev_counts[sev] = sev_counts.get(sev, 0) + 1
        rule_counts[f["rule"]] = rule_counts.get(f["rule"], 0) + 1
    total_desc = sum(n for _, n in desc_lengths)
    return {
        "desc_total_chars": total_desc,
        "desc_max_total": max_desc_total,
        "desc_avg_chars": round(total_desc / len(desc_lengths), 1) if desc_lengths else 0,
        "top_fat_desc": sorted(desc_lengths, key=lambda x: (-x[1], x[0]))[:5],
        "top_startup_footprints": [
            {"skill": n, "effective_lines": tot, "body_lines": b, "mandatory_ref_lines": r}
            for n, tot, b, r in sorted(startup_stats, key=lambda x: (-x[1], x[0]))[:5]
        ],
        "severity_counts": sev_counts,
        "rule_counts": dict(sorted(rule_counts.items())),
    }


def check_library(root: Path, max_desc_total: int = 4500, extra_external: set[str] | None = None):
    """扫描技能库根目录，返回 (skills, findings, metrics)？不，兼容旧解包返回 (skills, findings)。"""
    skills, findings, _ = check_library_with_metrics(root, max_desc_total=max_desc_total, extra_external=extra_external)
    return skills, findings


def check_library_with_metrics(root: Path, max_desc_total: int = 4500, extra_external: set[str] | None = None):
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
    for s in skills:
        sk_dir = s["path"].parent
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
            if "--" in nm or (not re.match(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$", nm) and not re.match(r"^[a-z0-9]$", nm)):
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

        scan_mds = [s["path"]]
        ref_dir = sk_dir / "references"
        if ref_dir.exists():
            scan_mds += [p for p in ref_dir.rglob("*.md")]
        for mf in scan_mds:
            if sum(1 for ln in read_text(mf).splitlines() if FENCE_RE.match(ln)) % 2 == 1:
                add(R_FENCE_OPEN, d, f"{mf.relative_to(root)} 代码围栏未成对闭合")

        for t in extract_local_targets(strip_fences(raw)):
            if not (sk_dir / t).resolve().exists():
                add(R_REF_BROKEN, d, f"SKILL.md 引用的 {t} 不存在")
        if ref_dir.exists():
            for rf in sorted(ref_dir.rglob("*.md")):
                for t in extract_ref_local_targets(read_text(rf)):
                    if not (sk_dir / t).resolve().exists() and not (rf.parent / t).resolve().exists():
                        add(R_REF_BROKEN, d, f"references/{rf.relative_to(ref_dir)} 引用的 {t} 不存在")

            for rf in ref_dir.rglob("*.md"):
                rtxt = read_text(rf)
                if len(rtxt.splitlines()) > 200 and not has_nav_or_headings(rtxt):
                    add(R_REF_NOTOC, d, f"references/{rf.relative_to(ref_dir)} {len(rtxt.splitlines())} 行，顶部缺目录/清晰分节")

            file_texts = {
                p: read_text(p)
                for p in list(sk_dir.rglob("*.md")) + list(sk_dir.rglob("*.py")) + list(sk_dir.rglob("*.sh"))
            }
            for rf in ref_dir.rglob("*.md"):
                corpus = "\n".join(txt for p, txt in file_texts.items() if p != rf)
                if rf.name not in corpus and rf.stem not in corpus:
                    add(R_REF_ORPHAN, d, f"references/{rf.relative_to(ref_dir)} 全技能无任何文件点名，确认是否还需要")

        for p in sk_dir.iterdir():
            if p.is_file() and PLACEHOLDER_NAME_RE.search(p.name) and p.suffix in {".md", ".txt"} and p.stat().st_size < 40:
                add(R_PLACEHOLDER, d, f"疑似空壳占位文件：{p.name}")

        body_nofence = strip_fences(raw)
        hard_hits = sorted({m.group(0)[:40] for pat in HARD_PATTERNS for m in [re.search(pat, body_nofence)] if m})
        if hard_hits:
            add(R_HARD_BIND, d, "; ".join(hard_hits))
        soft_hits = sorted({m.group(0) for pat in SOFT_PATTERNS for m in [re.search(pat, body_nofence)] if m})
        if soft_hits and not re.search(SOFT_DEGRADE_HINT, body_nofence):
            add(R_SOFT_BIND, d, "; ".join(soft_hits))

        for p in sk_dir.rglob("*"):
            if "tests" in p.parts or "fixtures" in p.parts or p.name.startswith("test_") or p.name.endswith("_test.py"):
                continue
            if p.is_file() and p.suffix in {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".txt"}:
                if SECRET_RE.search(read_text(p)):
                    add(R_SECRET, d, f"{p.relative_to(root)} 出现疑似硬编码密钥")

    for nm in sorted({x for x in names if names.count(x) > 1}):
        add(R_NAME_DUP, nm, "多个技能声明同一 name")

    known_dirs = {s["dir"] for s in skills}
    external_ok = set(DEFAULT_EXTERNAL_SKILLS) | set(extra_external or set())
    findings.extend(coverage_scan(skills, set(names) | known_dirs, external_ok))

    desc_lengths, startup_stats = check_budget_and_drag(skills, max_desc_total, add)
    check_cross_skill_conflicts(skills, known_dirs, add)
    metrics = compute_metrics(desc_lengths, startup_stats, findings, max_desc_total)
    return skills, findings, metrics


def main():
    ap = argparse.ArgumentParser(description="技能库静态健康与双模适配体检")
    ap.add_argument("root", nargs="?", default=".", help="技能库目录（默认自动发现）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-desc-total", type=int, default=4500, help="全库 description 总字符上限（默认 4500）")
    ap.add_argument("--external-skills", default="", help="逗号分隔的宿主/外部技能白名单")
    ap.add_argument("--strict", action="store_true", help="将 mid 严重度也视为非零退出（与 high 一同拦截）")
    ap.add_argument("--save-baseline", metavar="FILE", help="把当前问题集写入基线文件")
    ap.add_argument("--baseline", metavar="FILE", help="只报告基线之外的新问题")
    args = ap.parse_args()

    root = find_library(Path(args.root))
    if root is None:
        print(f"找不到技能库：{Path(args.root).resolve()} 及其上级均无多个 <name>/SKILL.md", file=sys.stderr)
        sys.exit(2)

    extra_ext = {x.strip() for x in args.external_skills.split(",") if x.strip()}
    _, findings, metrics = check_library_with_metrics(
        root, max_desc_total=args.max_desc_total, extra_external=extra_ext
    )

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
              "metrics": metrics, "summary": summary, "findings": findings}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"技能库: {root}\n技能数: {skill_count}\n")
        order = {"high": 0, "mid": 1, "low": 2}
        for f in sorted(findings, key=lambda x: (order[x["sev"]], x["rule"], x["skill"])):
            print(f"[{f['sev'].upper():4} {f['rule']}] {f['kind']:<14} {f['skill']}")
            print(f"        证据: {f['evidence']}")
            print(f"        建议: {f['action']}")
        top_startup = ", ".join(
            f"{x['skill']}:{x['effective_lines']}L" for x in metrics["top_startup_footprints"][:3]
        )
        print(
            f"\n双模预算看板: description 合计 {metrics['desc_total_chars']}/{metrics['desc_max_total']} 字符"
            f"（均值 {metrics['desc_avg_chars']}）；最大起手行数 {top_startup}"
        )
        print(f"汇总: {summary if summary else '静态规则全部通过'}")
        print("注：仅静态与线索检查。强弱模型消融、语义矛盾裁决见 health-check.md 与 dual-model-design.md；")
        print("    真实触发率等动态检查归 Harness 层。")

    fail_sevs = {"high", "mid"} if args.strict else {"high"}
    sys.exit(1 if any(f["sev"] in fail_sevs for f in findings) else 0)


if __name__ == "__main__":
    main()
