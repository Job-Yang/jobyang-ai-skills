#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quick_scan.py — 好好说话 · 改前逐字扫的跨平台机械扫描（纯标准库）。

为什么要它：
  旧版 references/quick-scan-regex.md 给的一键命令里，半角标点那条用了 `grep -P`。
  macOS 自带 BSD grep 没有 -P、不认 `\\x{}`，本机直接报 `grep: invalid option -- P`，
  四条零容忍里唯独这一条在 macOS 上失效。本脚本把它写成纯 stdlib，
  macOS / Linux / Windows(py3) 一份代码通跑，不再依赖 GNU grep 的 PCRE。

扫什么（每条都标明兑现方式，与 references/quick-scan-regex.md 一一对应）：
  half     中文正文里夹半角标点 , ; : .   —— 唯一真硬闸：默认退出码卡它，必须清零
  dash     破折号串 ——                     —— 提示项（正文可留 1-2 个，滥用才改）
  b2       「不是 X 是 Y」变体族        —— 提示项，机器只报形式、人判意图
  meta     元话语（值得深思/引人深思…） —— 提示项，命中建议删，但默认不卡退出码
  heading  章节机械编号/量词标题        —— 提示项，工具说明书/清单编号豁免（人判）
  disclaim 正文里的免责尾巴（以上仅依据/未核实…）—— 提示项，原文本来就有的照留（人判）
  wall     段落墙：超长段 / 纯段落连排太多    —— 提示项，按 references/reader-layout.md 拆成列表/表格/引用块

不误报什么（受保护跨度，扫之前先屏蔽）：
  ``` 围栏代码块整段（含跨行 HTML 注释）、`行内代码`、http(s):// 与 www. 链接、markdown 链接里的 url。
  英文词尾贴的半角标点（如「调用API,完成」）故意不报——只认中文字符直接贴半角标点，
  宁可漏这一处，也不误杀中英混排的合理用法（参见 references/protected-spans.md）。

退出码：
  0 = --fail-on 指定类别（默认 half）零命中
  1 = --fail-on 指定类别有命中
  2 = 用法/文件错误，或输入异常（如未闭合代码围栏）——不静默放行
  默认只有 half 卡退出码；dash/b2/meta/heading/disclaim 是提示项，默认只报告，
  需要硬卡时用 --fail-on meta,dash,b2,heading,disclaim 打开。
"""

import argparse
import re
import sys

# 中日韩统一表意文字（含扩展 A、兼容表意文字；繁体如「體/學」也在范围内），
# 外加常见闭引号/闭书名号/闭括号——半角标点贴在这些后面也算"夹在中文里"。
CJK_OR_CLOSE = (
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\u300d\u300f\u300b\u3011\u201d\u2019\uff09]"  # 」』》〕”’）
)

# 1) 半角标点夹中文：中文字符（或闭标点）后直接跟半角逗号/分号/冒号；句号后不接数字（放过 3.14、v1.2）。
RE_HALF = re.compile(CJK_OR_CLOSE + r"[,;:]|" + CJK_OR_CLOSE + r"\.(?![0-9])")

# 2) 破折号串（中文破折号是两个 U+2014 连写 ——）。
RE_DASH = re.compile(r"\u2014{2}")

# 3) B2「不是 X 是 Y」变体族（与 quick-scan-regex.md 正则逐字对应）。
RE_B2 = re.compile(
    r"不是[^，。；\n]{1,30}[，,](而)?是[^，。\n]{1,30}"
    r"|这不是[^，。\n]{1,30}"
    r"|管的是[^，。\n]{1,20}不管"
    r"|不在[^，。\n]{1,15}[，,]?而(在|是)"
    r"|你以为[^，。\n]{1,30}[，,]?其实"
    r"|(?:看似|表面上)[^，。\n]{1,30}[，,]?实则"
    r"|回头才(?:发现|明白)"
    r"|真正[^，。\n]{1,20}的是"
    r"|不重要[，,]重要的是"
)

# 4) 元话语：抬姿态的空判断词。
RE_META = re.compile(r"值得深思|值得关注|值得玩味|不禁让人|引人深思|发人深省|令人深思|不禁要问")

# 5) 章节机械编号 / 量词标题（只在 ATX 标题行 # 上判）。
RE_HEADING = re.compile(
    r"^#{1,6}\s*("
    r"[一二三四五六七八九十]+[、.]"
    r"|第[一二三四五六七八九十0-9]+[章节、]"
    r"|[0-9]+[.、）)]"
    r"|其[一二三四五六七八九十]"
    r"|第[一二三四五六七八九十0-9]+[步刀条个板斧维度方面]"
    r"|[一二三四五六七八九十0-9]+[刀步条板斧维度]"
    r")"
)

# 6) 正文里的免责尾巴：交代依据、没核实什么，或把已说过的不确定再补一句（症状库结构级第 6 条）。
#    「尚未验证」「还要看测试结果」「未经核实的消息」这类正常说法不报；原文本来就有的，由人判断后照留。
RE_DISCLAIM = re.compile(
    r"(?:以上|上述)[^。！？\n]{0,15}(?:仅|只)(?:依据|根据|基于)"
    r"|(?:以上|上述)[^。！？\n]{0,15}按(?:你|您)的"
    r"|未(?:做|经过?)?(?:额外|进一步|实际)?的?(?:核验|核实|核查|查证)(?!的)"
    r"|(?:无法|没法|没有|尚未|还没)(?:核验|核实|查证)(?!的)"
    r"|还(?:得|要|需要)看[^。！？\n]{0,15}(?:什么时候|何时)"
)

# 受保护跨度：行内代码、链接、HTML 注释（先屏蔽，避免把代码/URL/注释标记里的半角标点当病）。
RE_INLINE_CODE = re.compile(r"`[^`]*`")
RE_URL = re.compile(r"https?://\S+|www\.\S+")
RE_MD_LINK_URL = re.compile(r"(\[[^\]]*\])\(\s*(https?://[^)\s]+|[^)\s]+\.[^)\s]+)\s*\)")
# HTML 注释（含本技能自己的宪法标记 <!-- 底线条款:开始 -->）是结构标记，不是交付正文，剥掉。
RE_HTML_COMMENT = re.compile(r"<!--.*?-->")

CHECKS = ("half", "dash", "b2", "meta", "heading", "disclaim", "wall")
CN = {
    "half": "半角标点",
    "dash": "破折号串",
    "b2": "B2 变体",
    "meta": "元话语",
    "heading": "序号标题",
    "disclaim": "免责尾巴（原文有的照留）",
    "wall": "段落墙（拆成列表/表格）",
}

CJK_CHAR = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
STRUCT_START = re.compile(r"^\s*(?:#|\||>|[-*+]\s|\d+[.)、]\s|!\[|<)")


def scan_walls(text: str, para_max: int, run_max: int):
    """按空行切块，报超长纯段落和段落墙。text 已剥掉代码围栏与注释（保留换行）。
    返回 [(起始行号, 描述, 片段)]。列表、表格、引用、标题、图都打断连排。"""
    out, run, lineno, block, start = [], [], 0, [], 0

    def flush_block():
        nonlocal block, run
        if not block:
            return
        body = "".join(l.strip() for l in block)
        first = block[0]
        quoted = [l for l in block if l.lstrip().startswith(">")]
        if quoted:
            # 引用块打断连排，但引用块本身也不许是一大坨（引用里的列表/表格不算）
            # 引用内部按「>」空行再分段，逐段量
            paras, cur = [], []
            for l in quoted + [">"]:
                inner = re.sub(r"^\s*>\s?", "", l)
                if inner.strip():
                    cur.append(inner)
                elif cur:
                    paras.append(cur); cur = []
            for para in paras:
                if STRUCT_START.match(para[0]):
                    continue
                q = re.sub(r"\s", "", "".join(para))
                if len(q) > para_max and CJK_CHAR.search(q):
                    out.append((start, "引用块内单段 %d 字（上限 %d）" % (len(q), para_max), q[:24]))
        if any(STRUCT_START.match(l) for l in block) or not CJK_CHAR.search(body):
            if len(run) > run_max:
                out.append((run[0][0], "纯段落连排 %d 段" % len(run), run[0][1][:24]))
            run = []
        else:
            n = len(re.sub(r"\s", "", body))
            if n > para_max:
                out.append((start, "单段 %d 字（上限 %d）" % (n, para_max), body[:24]))
            run.append((start, body))
        block = []

    lines = text.split("\n")
    if lines and lines[0].strip() == "---":  # YAML frontmatter 不是正文
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                lines[:j + 1] = [""] * (j + 1)
                break
    for lineno, raw in enumerate(lines, 1):
        if raw.strip():
            if not block:
                start = lineno
            block.append(raw)
        else:
            flush_block()
    flush_block()
    if len(run) > run_max:
        out.append((run[0][0], "纯段落连排 %d 段" % len(run), run[0][1][:24]))
    return out


def mask_protected(line: str) -> str:
    """把行内代码和 URL 换成等长空格，使这些位置不参与匹配；返回屏蔽后的行。"""
    masked = RE_INLINE_CODE.sub(lambda m: " " * len(m.group()), line)
    masked = RE_MD_LINK_URL.sub(lambda m: m.group(1) + "(" + " " * (len(m.group(2))) + ")", masked)
    masked = RE_URL.sub(lambda m: " " * len(m.group()), masked)
    masked = RE_HTML_COMMENT.sub(lambda m: " " * len(m.group()), masked)
    return masked


def scan_line(line: str, checks):
    """对单行跑所选检查，返回 {check: [匹配片段,...]}。line 是屏蔽后的行。"""
    hits = {}
    if "half" in checks:
        ms = RE_HALF.findall(line)
        # findall 在有分组时返回分组；这里整体匹配，用 finditer 拿片段更直观。
        frags = [m.group() for m in re.finditer(RE_HALF, line)]
        if frags:
            hits["half"] = frags
    if "dash" in checks:
        n = len(RE_DASH.findall(line))
        if n:
            hits["dash"] = ["—— x%d" % n]
    if "b2" in checks:
        frags = [m.group() for m in re.finditer(RE_B2, line)]
        if frags:
            hits["b2"] = frags
    if "meta" in checks:
        frags = [m.group() for m in re.finditer(RE_META, line)]
        if frags:
            hits["meta"] = frags
    if "heading" in checks and RE_HEADING.match(line):
        hits["heading"] = [line.strip()[:40]]
    if "disclaim" in checks:
        frags = [m.group() for m in re.finditer(RE_DISCLAIM, line)]
        if frags:
            hits["disclaim"] = frags
    return hits


def _blank_keep_newlines(m):
    """把匹配块换成等长空格，但保留换行，使行号不漂移。"""
    return re.sub(r"[^\n]", " ", m.group())


def scan_file(path: str, checks, para_max: int = 150, run_max: int = 3):
    """扫一个文件，返回 (per_line_results, error)。per_line_results: list[(lineno, hits)]。"""
    results = []
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return results, "读取失败: %s" % e

    # 跨行 HTML 注释整体剥除（DOTALL），保留换行以维持行号；块内半角标点一律不当病。
    text = re.sub(r"<!--.*?-->", _blank_keep_newlines, text, flags=re.DOTALL)

    in_fence = False
    fence_marker = None
    fence_open_line = 0
    prose_lines = []  # 代码围栏内的行换成空行，供段落墙检查使用
    for i, raw in enumerate(text.split("\n"), 1):
        stripped = raw.strip()
        # 围栏代码块状态机：``` 或 ~~~ 起/止。块内整行不扫。
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
                fence_open_line = i
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None
            prose_lines.append("")
            continue
        if in_fence:
            prose_lines.append("")
            continue
        prose_lines.append(raw)
        masked = mask_protected(raw)
        hits = scan_line(masked, checks)
        if hits:
            results.append((i, hits, raw.rstrip()))

    if in_fence:
        # 奇数个围栏标记 = 未闭合：其后内容被当代码跳过，会让脏稿假绿，必须报错而非静默放行。
        return results, (
            "第 %d 行起出现未闭合的代码围栏（%s），其后内容被当代码块跳过——"
            "这会让半角标点漏报、脏稿假绿。请先闭合围栏再扫。" % (fence_open_line, fence_marker)
        )
    if "wall" in checks:
        for ln, desc, frag in scan_walls("\n".join(prose_lines), para_max, run_max):
            results.append((ln, {"wall": [desc]}, frag))
        results.sort(key=lambda r: r[0])
    return results, None


def main(argv=None):
    p = argparse.ArgumentParser(
        description="好好说话 · 跨平台改前逐字扫（纯 stdlib，替代 grep -P）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("files", nargs="+", help="要扫的中文 markdown/文本文件，可多个")
    p.add_argument("--checks", default=",".join(CHECKS),
                   help="逗号选择要跑的检查: %s（默认全部）" % ",".join(CHECKS))
    p.add_argument("--fail-on", default="half",
                   help="哪些类别命中时退出码=1（逗号分隔；默认 half，即硬闸只卡半角标点）")
    p.add_argument("--para-max", type=int, default=150, help="wall：单段字数上限（默认 150；技术方案 120、畅想 200）")
    p.add_argument("--run-max", type=int, default=3, help="wall：纯段落最多连排几段（默认 3）")
    p.add_argument("--quiet", action="store_true", help="只输出命中摘要，不打印命中行原文")
    args = p.parse_args(argv)

    checks = tuple(c.strip() for c in args.checks.split(",") if c.strip() in CHECKS)
    if not checks:
        p.error("--checks 没有合法项，可选: %s" % ",".join(CHECKS))
    fail_on = tuple(c.strip() for c in args.fail_on.split(",") if c.strip() in CHECKS)

    total = {c: 0 for c in checks}
    failed = False
    any_file_error = False

    for path in args.files:
        results, err = scan_file(path, checks, args.para_max, args.run_max)
        if err:
            print("[!] %s: %s" % (path, err), file=sys.stderr)
            any_file_error = True
            continue
        print("=== %s ===" % path)
        if not results:
            print("    (clean)")
            continue
        for lineno, hits, raw in results:
            for c, frags in hits.items():
                total[c] += 1
                tag = "硬闸" if c == "half" else "建议/体检"
                print("  [%s·%s] L%d: %s" % (CN[c], tag, lineno, " | ".join(frags)))
                if not args.quiet:
                    print("        %s" % raw[:100])
                if c in fail_on:
                    failed = True

    print("---- 摘要 ----")
    for c in checks:
        print("  %-8s %d 处" % (CN[c], total[c]))
    print("  fail-on=%s -> %s" % (",".join(fail_on) or "(无)", "有命中，退出1" if failed else "零命中，退出0"))

    if any_file_error:
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
