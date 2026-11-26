#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
writing_check.py — writing-craft 成稿确定性字面门禁（纯 Python 标准库）。

只检确定性字面与明显结构边界，不拿五字段表单、复杂度公式或幽默配额绑死强模型。

用法：
    python3 writing_check.py <稿子.md> --mode sharing|opinion|note|tangshan [--format article|talk|slides]

退出码：有 ERROR = 1；仅 WARN 或全净 = 0。
"""
from __future__ import annotations

import argparse
import re
import sys

CN = r"[\u4e00-\u9fff]"

FORBIDDEN_OPENERS = [
    "本文将介绍",
    "本文介绍",
    "在当今时代",
    "众所周知",
]
UNVERIFIED = ["TODO", "TBD", "FIXME", "待补", "待核实", "[?]"]


def mask_code_and_url(text: str) -> tuple[str, bool]:
    """将 HTML 注释、围栏代码、行内代码、Markdown URL 与裸 URL 替换为等长空格，同时检查未闭合围栏。"""
    unclosed = text.count("```") % 2 == 1
    masked = re.sub(r"<!--.*?-->", lambda m: " " * len(m.group()), text, flags=re.DOTALL)
    masked = re.sub(r"```.*?```", lambda m: " " * len(m.group()), masked, flags=re.DOTALL)
    masked = re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group()), masked)
    masked = re.sub(
        r"(\[[^\]]+\]\()([^)\n]+)(\))",
        lambda m: m.group(1) + (" " * len(m.group(2))) + m.group(3),
        masked,
    )
    masked = re.sub(
        r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+",
        lambda m: " " * len(m.group()),
        masked,
    )
    return masked, unclosed


def count_cn(text: str) -> int:
    return len(re.findall(CN, text))


def split_paragraphs(text: str) -> list[str]:
    """按空行分段，忽略纯标题行。"""
    paras = []
    for raw in re.split(r"\n\s*\n", text):
        lines = [
            ln for ln in raw.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        if lines:
            paras.append("\n".join(lines))
    return paras


def check(mode: str, text: str, fmt: str = "article") -> tuple[list[str], list[str], dict]:
    errors: list[str] = []
    warns: list[str] = []

    masked, unclosed = mask_code_and_url(text)
    paras = split_paragraphs(masked)
    head = "\n".join(paras[:3]) if paras else ""
    cn = count_cn(masked)

    # 1. 前 3 段禁用空导语（note 短手记跳过，正常文章全查）
    if mode != "note":
        for phrase in FORBIDDEN_OPENERS:
            if phrase in head:
                errors.append(f"开头禁用空导语：前 3 段出现「{phrase}」")
        if re.search(r"随着.{0,8}(?:的发展|的普及|的演进|的推进)", head):
            errors.append("开头禁用空导语：前 3 段出现「随着……的发展」式开场")

    # 2. 未闭合代码围栏
    if unclosed:
        errors.append("检测到未闭合代码围栏（``` 不成对），已跳过正文半角标点扫描")
    else:
        # 3. 中文正文夹半角标点（代码/URL/数字千分位/小数已避开）
        half = re.findall(CN + r"[,;:]|" + CN + r"[!?]|" + CN + r"\.(?![0-9.])", masked)
        if half:
            errors.append(f"中文正文夹半角标点 {len(half)} 处，示例：{half[:4]}")

    # 4. 未核实残留标记
    for mark in UNVERIFIED:
        if mark in masked:
            errors.append(f"正文残留未核实标记「{mark}」")

    # 5. 分支特定轻量 WARN（不阻断退出码）
    if mode == "note" and cn > 120:
        warns.append(f"锻造手记当前 {cn} 中文字，超过 120 字上限，建议进一步压缩修饰语并保住因果环")

    h2_count = len(re.findall(r"(?m)^##\s", masked))

    if mode == "opinion":
        h1_match = re.search(r"(?m)^#\s+(.+)$", masked)
        if h1_match and "——" in h1_match.group(1):
            warns.append("观点硬文主标题建议避免破折号「——」，改成一句直白陈述判断")
        if fmt == "article":
            if cn >= 200 and not h1_match:
                warns.append("观点硬文建议补上简练 # 一级主标题")
            if cn < 600:
                warns.append(
                    f"当前观点硬文仅 {cn} 中文字，若非明确要求极短评，建议补实工程机理与适用边界（参考 1,000–2,500 字）"
                )

    if mode == "tangshan":
        h1_match = re.search(r"(?m)^#\s+(.+)$", masked)
        h3_count = len(re.findall(r"(?m)^###\s", masked))
        if cn >= 200 and not h1_match:
            warns.append("专栏长评首行请使用 # 一级主标题，勿用 ## 充当主标题")
        if cn >= 800 and h3_count >= 2 and (h2_count == 0 or (h2_count == 1 and not h1_match)):
            warns.append("检测到用 ### 替代主章节且缺少 ## 路标，长评主章节请使用 ##")
        if re.search(r"(?m)^#{2,3}\s*结语\s*$", masked):
            warns.append("长评宜顺着因果收在刃口，避免单开「结语」空壳尾节")

    if mode in ("sharing", "opinion") and fmt == "article":
        if mode == "sharing" and not re.search(r"(?m)^#\s+\S", masked):
            warns.append("缺少 # 一级主标题，建议补上简练标题（勿用 ## 充当主标题）")
        structural = re.compile(r"^\s*(?:#|\||>|[-*+•·]\s|\d+[.、)]\s|!\[|<)")
        long_paras, walls, run = [], 0, 0
        blocks = [b.strip() for b in re.split(r"\n\s*\n", masked) if b.strip()]
        for blk in blocks + ["#"]:
            if structural.match(blk) or not re.search(CN, blk):
                if run > 4:
                    walls += 1
                run = 0
                continue
            run += 1
            if count_cn(blk) > 180:
                long_paras.append(re.sub(r"\s", "", blk)[:16])
        if long_paras:
            warns.append(f"{len(long_paras)} 个段落超过 180 字，分享/观点正文宜适度分段保持呼吸：{'；'.join(long_paras[:3])}…")
        if walls:
            warns.append(f"{walls} 处连续纯段落超过 4 段，可酌情插入小标题、表格、列表或高亮锚点")

    return errors, warns, {"cn": cn, "h2": h2_count}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="writing-craft 成稿确定性字面门禁")
    ap.add_argument("file", help="待检查 Markdown 文件路径")
    ap.add_argument("--mode", required=True, choices=["sharing", "opinion", "note", "tangshan"])
    ap.add_argument("--format", default="article", choices=["article", "talk", "slides"])
    args = ap.parse_args(argv)

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"读取失败：{e}", file=sys.stderr)
        return 2

    errors, warns, stats = check(args.mode, text, args.format)
    print(f"== writing_check · mode={args.mode} format={args.format} ==")
    print(f"中文字数 {stats['cn']} ｜ H2 章节 {stats['h2']}")

    if errors:
        print(f"\n[ERROR] {len(errors)} 项：")
        for err in errors:
            print(f"  - {err}")
    if warns:
        print(f"\n[WARN] {len(warns)} 项：")
        for w in warns:
            print(f"  - {w}")
    if not errors and not warns:
        print("\n硬约束全净。")

    print(f"\n结论：{'不通过（先修 ERROR）' if errors else '通过'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
