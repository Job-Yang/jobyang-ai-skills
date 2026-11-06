#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
talk_check.py — talk-smith 成稿硬约束扫描（纯 Python 标准库，macOS/Linux 通跑）。

用途：第五步质检里"机器能判净"的那层。只扫字面/结构硬约束，不自动改稿；
意图类（开头强弱、启示收得实不实、幽默分寸）由人判，这里只出 WARN。

用法：
    python3 talk_check.py <稿子.md> --state article|talk|slides

退出码：有 ERROR = 1；只有 WARN 或全净 = 0。
"""
import argparse
import re
import sys

CN = r"[\u4e00-\u9fff]"
# 拉丁术语词（用于"术语原词+中文注释"这一进阶层信号）
LATIN = r"[A-Za-z][A-Za-z0-9\-/]*"

FORBIDDEN_OPENERS = [
    "本文将介绍", "本文介绍", "在当今时代", "众所周知", "随着",
]
# "随着…的发展" 类用正则单独抓，上面列表是精确短语

UNVERIFIED = ["TODO", "待补", "待核实", "[?]", "TBD", "FIXME"]
ACTION_WORDS = ["明天", "下一步", "可以试试", "建议你", "你可以", "动手"]

# 0.2.0 新结构项：只出 WARN（不强制、不做 ERROR），幽默不做机器硬判
TLDR_FIELDS = ["干了啥", "最大的坑", "真正的收获", "这篇讲", "最后引出"]
# 严肃/正式场合标记：命中时若出现卖萌符号/词，给 WARN（幽默应归零）。
# 只用明确元话语搭配，不收裸词"声明"（避免"声明式编程"这类技术文误报）。
FORMAL_MARKERS = ["事故复盘", "正式发布", "正式对外", "官方声明", "正式声明",
                  "法律声明", "安全声明", "安全公告"]
# 卖萌信号（AI 强行俏皮/个人梗词），非穷举，仅作场合冲突提示
CUTE_PATTERN = re.compile(
    r"绝绝子|家人们|谁懂啊|一整个|大震惊|😂|🤣|😆|🥰|😅|🤪|🎉|✨"
)
# "先看数据/先成果"成果节标题
FIRST_DATA_HEADING = re.compile(r"(?m)^#{1,6}\s.*(先看数据|先看结果|先看效果|最终效果|成果看板)")

# 各 state 的字数目标区间（中文字符数）与 H2 下限
STATE_RULES = {
    "article": {"cn_min": 2000, "cn_max": 5000, "h2_min": 5,
                 "desc": "中长文 2000-5000 中文字"},
    "talk":    {"cn_min": 2000, "cn_max": 7000, "h2_min": 4,
                 "desc": "口播稿按分钟换算（约200-240字/分钟），宽区间 2000-7000"},
    "slides":  {"cn_min": 200,  "cn_max": 2500, "h2_min": 5,
                 "desc": "幻灯片分镜应克制，正文 >2500 中文字提示过密"},
}


def mask_code_and_url(text: str):
    """先把围栏代码块、行内 code、URL 真正 mask 成等长空格，再让标点扫描在干净正文上跑。

    返回 (masked_text, unclosed_fence)。未闭合围栏无法判定代码边界，
    调用方应单独报错且不把围栏内内容当正文扫。
    """
    unclosed = text.count("```") % 2 == 1
    masked = re.sub(r"```.*?```", lambda m: " " * len(m.group()), text, flags=re.DOTALL)
    masked = re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group()), masked)
    # URL：RFC3986 pchar 字符集，自然停在中文/空白处；逗号是合法 URL 字符，
    # 故 `https://x/bench,我们` 里的逗号随 URL 一起被 mask，不误报。
    masked = re.sub(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+",
                    lambda m: " " * len(m.group()), masked)
    return masked, unclosed


def strip_code_blocks(text: str) -> str:
    """旧入口：保留语义（去围栏代码块），内部改走 mask。"""
    masked, _ = mask_code_and_url(text)
    return masked


def count_cn(text: str) -> int:
    return len(re.findall(CN, text))


def split_paragraphs(text: str):
    """按空行切段，去掉标题行（# 开头）和空段。"""
    paras = []
    for raw in re.split(r"\n\s*\n", text):
        lines = [ln for ln in raw.splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#")]
        if lines:
            paras.append("\n".join(lines))
    return paras


def check(state: str, text: str):
    errors, warns = [], []
    body = strip_code_blocks(text)
    rules = STATE_RULES[state]

    paras = split_paragraphs(body)
    head = "\n".join(paras[:3]) if paras else ""

    # 1. 禁开头语（前 3 段）
    for phrase in FORBIDDEN_OPENERS:
        if phrase in head:
            errors.append(f"开头禁用导语：前3段出现「{phrase}」——禁寒暄/课件腔开场")
    if re.search(r"随着.{0,6}的发展", head):
        errors.append("开头禁用导语：前3段出现「随着…的发展」式开场")

    # 2. 开头信号：现场钩子（数字/引语「」/问句）或新默认合法开头（TL;DR 卡 / 先成果节）
    has_hook = bool(re.search(r"\d", head)) or ("「" in head) or ("？" in head) or ("?" in head)
    # TL;DR 卡：明确标记（TL;DR/速览/摘要）或五字段命中 ≥3 个（全窗匹配，不限前 600 字）
    tldr_marker = re.search(r"TL;DR|速览|内容摘要|摘要[:：]", body, re.IGNORECASE)
    tldr_fields_hit = sum(1 for f in TLDR_FIELDS if f in body)
    tldr_card = bool(tldr_marker) or tldr_fields_hit >= 3
    # 先成果后过程：前部成果节标题（先看数据/先看结果/最终效果/成果看板/成果/结论先行）
    first_data = bool(FIRST_DATA_HEADING.search(body)) or bool(
        re.search(r"(?m)^#{1,6}\s.*(成果|结论先行|先看效果|最终效果)", body))
    legal_opener = tldr_card or first_data
    if not has_hook and not legal_opener:
        warns.append("前3段未检出开头信号（现场钩子：数字/「」引语/问句；或 TL;DR 卡/先成果节）——确认是不是真开头，不是就重写")

    # 3. 字数区间
    cn = count_cn(body)
    if cn < rules["cn_min"]:
        warns.append(f"中文字数 {cn} 低于 {rules['cn_min']}（{rules['desc']}）——太薄或漏了进阶层")
    if cn > rules["cn_max"]:
        warns.append(f"中文字数 {cn} 超过 {rules['cn_max']}（{rules['desc']}）——考虑拆分或删水段")

    # 4. H2 章节完整性
    h2 = len(re.findall(r"(?m)^##\s", body))
    if h2 < rules["h2_min"]:
        warns.append(f"H2 章节数 {h2} 少于 {rules['h2_min']}——叙事结构可能没铺满")

    # 5. 结尾收口：默认"几点启示"分节即合规；明天动作/加粗金句仅可选加分，缺了不报错
    tail = "\n".join(paras[-2:]) if len(paras) >= 2 else (paras[0] if paras else "")
    has_action = any(w in tail for w in ACTION_WORDS)
    has_bold_closer = "**" in tail
    insight_head = re.search(r"(?m)^#{1,6}\s.*(几点启示|复盘启示|收获与体会|心得体会|几点体会)", body)
    list_items = len(re.findall(r"(?m)^\s*(?:\d+[.、)]|[•·\-])\s+\S", body))
    has_insight = bool(insight_head) and list_items >= 2
    if not (has_insight or has_action or has_bold_closer):
        warns.append("结尾未见「几点启示」分节/可搬走动作/加粗收口——结尾别空收（金句、明天动作均为可选，不强制）")

    # 6. 未核实断言
    for mark in UNVERIFIED:
        if mark in body:
            errors.append(f"残留未核实标记「{mark}」——技术核实闸没过就不许交付")

    # 7. 中文夹半角标点（先 mask 围栏代码/行内码/URL；未闭合围栏单独报错、不当正文扫）
    masked, unclosed = mask_code_and_url(text)
    if unclosed:
        errors.append("检测到未闭合围栏（``` 不成对）——代码块边界无法判定，已跳过正文标点扫描；请先闭合围栏")
    else:
        half = re.findall(CN + r"[,.;:!?]|[,.;:!?]" + CN, masked)
        if half:
            errors.append(f"中文正文夹半角标点 {len(half)} 处（围栏代码/行内码/URL/数字千分位除外）——换全角，示例：{half[:3]}")

    # 8. 文体提示 WARN（只查字面结构，不判路由；路由以 SKILL 边界表为准）
    # "进阶层机制"信号：不用裸字「层/参数」，要更有信息量的证据——
    #   复杂度 O(·) / 等式公式 / 明确的进阶层小节标题 / 拉丁术语原词+中文注释。
    has_complexity = bool(re.search(r"O\s*\([^)]{1,12}\)", body))
    has_equation = bool(re.search(r"[A-Za-zωασ∂][A-Za-z0-9₀-₉_\-]*\s*[=≈≤≥]\s*[A-Za-z0-9_(（₀-₉]", body))
    has_layer_heading = bool(re.search(r"(?m)^#{1,6}\s.*(进阶层|原理层|通俗层|机制层|复杂度|公式|状态方程)", body))
    has_term_gloss = bool(re.search(LATIN + r"\s*[（(][^）)]{2,30}[）)]", body))
    has_advanced = has_complexity or has_equation or has_layer_heading or has_term_gloss
    has_takeaway = any(w in body for w in ["搬走", "落地", "适用", "你可以", "明天", "可用于", "拿来", "可以试试"])
    if state == "article":
        if not has_advanced:
            warns.append("[文体] 未见进阶层机制信号（复杂度 O(·)/等式公式/进阶层小节标题/拉丁术语+中文注释）——确认不是把观点短稿当文章；本项只查字面，路由以边界表为准")
            if cn >= 600:
                warns.append("[文体] 稿子不算薄却全程无机制/公式/术语注释，更像观点判断——确认是否该归 cuihuo")
        if not has_takeaway:
            warns.append("[文体] 未见「可搬走的东西」（适用场景/你可以怎么用）——文章要落到读者能搬走什么")

    # 9. 新结构项 WARN（0.2.0）：只提示不强制，幽默不做机器硬判
    # 9a. TL;DR 卡片：article 态出现则全窗查五字段；talk 口播自行压缩，豁免五字段卡，不强制
    if state == "article" and tldr_card:
        missing = [f for f in TLDR_FIELDS if f not in body]
        if missing:
            warns.append(f"TL;DR 卡片缺字段：{'、'.join(missing)}——五字段为干了啥/最大的坑/真正的收获/这篇讲/最后引出（可选，缺了只提示）")
    elif state == "article" and cn >= 1200 and not legal_opener:
        warns.append("未见 TL;DR 卡片（默认开头，可选）；若没用卡片，确认开头用了「先成果后过程」或现场钩子，禁寒暄导语")

    # 9b. 系列交代块：仅匹配真实系列标记（系列第N篇/系列：/上一篇/下一篇），裸词"系列"不匹配
    if re.search(r"系列第[一二三四五六七八九十百0-9]+篇|系列[:：]|上一篇|下一篇", body) \
            and not ("上一篇" in body or "下一篇" in body):
        warns.append("出现系列交代标记但未见「上一篇/下一篇」（系列交代块为可选，非系列文可忽略）")

    # 9c. "先看数据/最终效果"成果节：可选项，仅对复盘/成果型长文且既无 TL;DR 也无成果节时提示；短文/talk 不刷
    retrospective = bool(re.search(r"复盘|成果|实践|改造|落地", body)) and cn >= 1500
    if state == "article" and retrospective and not tldr_card and not first_data:
        warns.append("复盘/成果型长文未见「先看数据/先看结果/最终效果」成果节（先成果后过程为可选开头，不用可忽略）")

    # 9d. 节首设问计数：只统计并轻提示，不强制密度
    q_count = body.count("？") + body.count("?")
    if state == "article" and q_count == 0 and cn >= 1500:
        warns.append(f"全文未见设问（节首替读者问再自答，可选装置，每 2–3 节一个）；当前问号计数 {q_count}，只提示不强制")

    # 9e. 正式/事故场合却出现卖萌符号/词 → WARN（幽默在这些场合应归零；永不 ERROR）
    if any(m in body for m in FORMAL_MARKERS) and CUTE_PATTERN.search(body):
        warns.append("正式/事故/声明场合出现卖萌符号或玩梗词（绝绝子/家人们/笑脸 emoji 等）——按规则这些场合幽默归零，建议删除；本项只 WARN")

    # 10. 段落墙 WARN：分享稿给人扫读，单段 ≤ 150 字，纯段落不连排超过 3 段（talk 口播稿豁免）
    if state != "talk":
        structural = re.compile(r"^\s*(?:#|\||>|[-*+•·]\s|\d+[.、)]\s|!\[|<)")
        long_paras, walls, run = [], 0, 0
        blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]  # 保留标题，标题打断连排
        for p in blocks + ["#"]:
            if structural.match(p) or not re.search(CN, p):
                if run > 3:
                    walls += 1
                run = 0
                continue
            run += 1
            if count_cn(p) > 150:
                long_paras.append(re.sub(r"\s", "", p)[:16])
        if long_paras:
            warns.append(f"{len(long_paras)} 个段落超过 150 字：分享稿要能扫读，拆短段或把并列/对比挪进列表、表格：{'；'.join(long_paras[:3])}…")
        if walls:
            warns.append(f"{walls} 处段落墙（纯段落连排超过 3 段）：插入小标题、加粗金句、列表、表格或图")

    return errors, warns, {"cn": cn, "h2": h2, "questions": q_count}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--state", required=True, choices=list(STATE_RULES))
    args = ap.parse_args(argv)

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"读取失败：{e}", file=sys.stderr)
        return 2

    errors, warns, stats = check(args.state, text)

    print(f"== talk_check · state={args.state} ==")
    print(f"中文字数 {stats['cn']} ｜ H2 章节 {stats['h2']} ｜ 参考区间：{STATE_RULES[args.state]['desc']}")
    if errors:
        print(f"\n[ERROR] {len(errors)} 项：")
        for e in errors:
            print(f"  - {e}")
    if warns:
        print(f"\n[WARN] {len(warns)} 项（人判）：")
        for w in warns:
            print(f"  - {w}")
    if not errors and not warns:
        print("\n硬约束全净。")
    print(f"\n结论：{'不通过（有 ERROR，先修）' if errors else '通过（WARN 请人工复核）'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
