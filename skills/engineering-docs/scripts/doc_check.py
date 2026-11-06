#!/usr/bin/env python3
"""Check that a Markdown engineering doc reads top-down: conclusion first, then chapters, then detail.

The skim layer is what a busy reader actually reads: the title, the text before the
first H2, every H2 heading and the first paragraph under it. A layered doc makes
sense from the skim layer alone; details live in H3 sections, tables and the appendix.

    python3 doc_check.py doc.md            # human-readable report
    python3 doc_check.py doc.md --skim     # also print the skim layer to proofread it
    python3 doc_check.py doc.md --json     # machine-readable
    python3 doc_check.py doc.md --source brief.md   # domain words from the brief are not jargon

Exit code 1 means a structural error (no conclusion before the first H2, missing title).
Warnings never fail the run unless --strict is given.
"""
import argparse
import json
import re
import sys
from pathlib import Path

BUDGET = {
    "first_screen_max": 450,   # chars before the first H2: conclusion, decision ask, overview figure
    "h2_min": 3, "h2_max": 9,  # main-line chapters, appendix excluded
    "h2_title_max": 20,
    "lead_max": 150,           # first paragraph of a chapter: its conclusion in one or two sentences
    "para_max": 120,           # ~3 lines at doc width; longer prose becomes a list or a table
    "prose_run_max": 2,        # consecutive plain paragraphs before readers lose the shape
    "section_needs_structure": 300,  # a chapter body this long needs at least one table or list
    "prose_share_max": 0.55,   # plain-paragraph chars / all chars: above this the doc reads as an essay
    "skim_ratio_min": 0.08, "skim_ratio_max": 0.45,
    "appendix_after": 6000,    # longer docs need an appendix or folded details
    "ai_per_1k": 3.0, "bold_per_1k": 25.0, "bold_len_max": 16, "bold_per_block": 1,
    "arrows_per_1k": 12.0, "bullet_line_share": 0.8,
}
GENERIC_H2 = {"概述", "背景", "简介", "总结", "其他", "说明", "介绍", "正文", "详情", "方案", "设计", "总体设计",
              "详细设计", "概要", "小结", "结论", "附注", "备注"}
# Headings are a short topic word, like a TOC entry — no numbering, no sentence.
HEADING_NUMBER_RE = re.compile(
    r"^\s*(?:第\s*[0-9０-９一二三四五六七八九十百]+\s*[步阶段部分章节条款]"
    r"|[0-9０-９]+[\.、\)）]"
    r"|[（(][0-9０-９]+[）)]"
    r"|[一二三四五六七八九十]+[、\.])\s*"
)
HEADING_SENTENCE_END = ("是什么", "怎么样", "怎么办", "为什么", "怎么做", "如何", "多少", "哪些")
HEADING_SENTENCE_RE = re.compile(
    r"(?:怎么|怎样|如何|为什么)|从[^，。]{1,12}到|的[^，。]{1,10}(?:对照|对比|验收|链路|旅程|关系|区别)"
)
# Conversation provenance and personal data never belong in the document.
CONVERSATION_LEAK_RE = re.compile(
    r"老板(?:[和跟与](?:同事|同学))?(?:问|说|要求|让|提|催|反馈)"
    r"|(?:同事|同学|领导|评审|对方)(?:问|说|要求|让|提|催|反馈)"
    r"|你(?:问|说|要求|让|提|催|反馈|之前|刚才)"
    r"|我跟他说|我和他说|跟你说过|前面说过|上次说"
)
# name+title anchored on a common surname so a preceding verb (找李明老师) does not
# get swallowed; role words 老板/同事/同学/领导 are never personal data.
_SURNAME = ("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛"
            "奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康")
PERSONAL_INFO_RE = re.compile(
    r"1[3-9]\d{9}|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
    rf"|[{_SURNAME}][一-龥]{{1,2}}(?:老师|先生|女士)"
)
LEX = {
    "套话连接": r"值得注意的是|需要注意的是|需要指出的是|与此同时|综上所述|总而言之|总的来说|换句话说|事实上|本质上|从根本上|在此基础上|不难发现|显而易见|由此可见|可以看出",
    "空泛强调": r"至关重要|非常重要|关键在于|核心在于|全方位|多维度|体系化|一站式|无缝|极大地|显著地|有效地",
    "互联网黑话": r"赋能|抓手|打通|沉淀|拉通|颗粒度|组合拳|心智|兜底|抓住|闭环|落地",
    "句式套路": r"不是[^。；\n]{1,24}而是|不仅[^。；\n]{1,24}(?:还|也|而且)|既[^。；\n]{1,16}又",
    "元叙述": r"本文将|本节将|下面将|接下来(?:我们|将)|本章(?:将|介绍)|如下所示|详见下文|让我们",
}
JARGON = ["黑盒", "白盒", "下钻", "横切", "章首", "口径", "收口", "门禁", "同构", "派生", "落点", "读者动作", "主线层",
          "证据层", "扫读层"]
# the writer's inputs showing through; readers do not have them
SOURCE_TALK = (r"素材包|素材信息|(?:素材|材料)(?:里|中)?(?:没有|未提|未给|未提供|未说明|未注明|缺失|未核实)"
               r"|不在(?:素材|材料)(?:里|中)|(?:给定|提供|所给)的(?:素材|材料)")
CJK = re.compile(r"[\u4e00-\u9fff]")
APPENDIX = re.compile(r"^(附录|appendix|参考|references?)\b", re.I)


def nospace(s):
    return re.sub(r"\s", "", s)


def strip_code(md):
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    return re.sub(r"```.*?```", "", md, flags=re.S)


def blocks(text):
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


def is_prose(b):
    return not (b.startswith(("#", "|", "- ", "* ", "> ", "![", "<", "```")) or re.match(r"^\d+[.)]\s", b))


def is_structure(b):
    """table or list — the shapes that let a reader scan instead of read"""
    return b.startswith(("|", "- ", "* ")) or bool(re.match(r"^\d+[.)]\s", b))


def is_label_line(b):
    """`**待拍板：**` style one-line labels introduce a list; they are not prose"""
    return bool(re.fullmatch(r"\*\*[^*\n]{1,16}\*\*[：:]?|[^\n]{1,30}[：:]", b))


# `- **保留期**：` / `> **结论**：` / `**待拍板：**` are structural keys, not emphasis
BOLD_LABEL_RE = re.compile(r"(?m)^(\s*(?:[-*]|\d+[.)]|>)?\s*)\*\*[^*\n]{1,12}?[：:]?\*\*[：:]?")


def split_h2(text):
    parts = re.split(r"(?m)^##[ \t]+(.*)$", text)
    head, chapters = parts[0], []
    for i in range(1, len(parts), 2):
        chapters.append((parts[i].strip(), parts[i + 1] if i + 1 < len(parts) else ""))
    return head, chapters


def check(md, source_text=""):
    text = strip_code(md)
    errors, warns = [], []
    total = len(nospace(text))
    cjk = len(CJK.findall(text)) or 1
    per1k = lambda n: round(n * 1000 / cjk, 2)

    head, chapters = split_h2(text)
    title = re.search(r"(?m)^#\s+(.+)$", head)
    if not title:
        errors.append("缺少一级标题（# 标题）")
    first_screen = re.sub(r"(?m)^#\s+.*$", "", head)
    first_screen = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", first_screen)
    fs_chars = len(nospace(first_screen))
    if fs_chars == 0:
        errors.append("第一个二级标题之前没有正文：首屏应先给结论、要读者做的决定和总览")
    elif fs_chars > BUDGET["first_screen_max"]:
        warns.append(f"首屏 {fs_chars} 字，超过 {BUDGET['first_screen_max']}：只留结论、决策请求和总览，其余下沉到章节")

    main = [(t, body) for t, body in chapters if not APPENDIX.match(t)]
    appendix = [t for t, _ in chapters if APPENDIX.match(t)]
    # H3 headings: short topics, no numbering, no sentence phrasing.
    h3_titles = re.findall(r"(?m)^###\s+(.+?)\s*$", text)
    numbered, sentence = [], []
    for ht in h3_titles + [t for t, _ in main]:
        bare = HEADING_NUMBER_RE.sub("", ht).strip(" ：:、. ")
        if HEADING_NUMBER_RE.match(ht):
            numbered.append(ht)
        if bare.endswith(HEADING_SENTENCE_END) or HEADING_SENTENCE_RE.search(bare):
            sentence.append(ht)
    if total > 1500 and not (BUDGET["h2_min"] <= len(main) <= BUDGET["h2_max"]):
        warns.append(f"正文二级标题 {len(main)} 个，建议 {BUDGET['h2_min']}–{BUDGET['h2_max']} 个：太少说明没有分章，太多说明主线被细节打散")
    skim = [title.group(0) if title else "", first_screen.strip()]
    leads_bad, generic, long_titles, unstructured = [], [], [], []
    for t, body in main:
        clean_t = re.sub(r"^[\d.、\s]+", "", t)
        if clean_t in GENERIC_H2:
            generic.append(t)
        if len(nospace(clean_t)) > BUDGET["h2_title_max"]:
            long_titles.append(t)
        bs = [b for b in blocks(body)]
        lead = bs[0] if bs else ""
        lead_ok = bool(lead) and (is_prose(lead) or lead.startswith(">"))  # a `> **结论**：` block is a lead too
        skim += ["## " + t, lead if lead_ok else ""]
        if not lead_ok:
            leads_bad.append(f"{t}（首块是{'空' if not lead else '列表/表格/图/小标题'}）")
        elif len(nospace(lead)) > BUDGET["lead_max"]:
            leads_bad.append(f"{t}（首段 {len(nospace(lead))} 字）")
        # a long chapter written only as paragraphs has no shape to scan
        body_chars = len(nospace(re.sub(r"(?m)^#{3,}\s.*$", "", body)))
        if body_chars > BUDGET["section_needs_structure"] and not any(is_structure(b) for b in bs):
            unstructured.append(f"{t}（{body_chars} 字）")
    if generic:
        warns.append("二级标题只写了类别，没写本章结论或对象：" + "、".join(generic))
    if long_titles:
        errors.append(f"二级标题超过 {BUDGET['h2_title_max']} 字（标题写短关键词，结论放正文）：" + "、".join(long_titles))
    if numbered:
        errors.append("标题不要编号（不写“第 N 步/1./一、”），顺序由目录表达：" + "、".join(sorted(set(numbered))))
    if sentence:
        errors.append("标题写成了一句话或把作用域/结论塞进标题，改成短关键词（如“聚合校验”而非“聚合校验是什么、为什么调整它”）："
                      + "、".join(sorted(set(sentence))))
    conv = sorted(set(CONVERSATION_LEAK_RE.findall(text)))
    if conv:
        errors.append("不要把对话来源/提问者写进技术文档（如“老板/同事问”“你让我”），直接陈述事实：" + "、".join(conv[:6]))
    pi = sorted(set(PERSONAL_INFO_RE.findall(text)))
    if pi:
        errors.append("出现手机号/邮箱/姓名称谓等个人信息，删除或脱敏：" + "、".join(pi[:6]))
    if leads_bad:
        warns.append(f"这些章节没有用一段 ≤{BUDGET['lead_max']} 字的话先给本章结论：" + "；".join(leads_bad))

    skim_text = "\n\n".join(s for s in skim if s)
    skim_ratio = round(len(nospace(skim_text)) / max(1, total), 2)
    if total > 3000 and not (BUDGET["skim_ratio_min"] <= skim_ratio <= BUDGET["skim_ratio_max"]):
        hint = "主线太薄，读者只看标题和首段拼不出全貌" if skim_ratio < BUDGET["skim_ratio_min"] else \
            "几乎没有下沉的细节，主次没有拉开"
        warns.append(f"速读层占比 {skim_ratio}（建议 {BUDGET['skim_ratio_min']}–{BUDGET['skim_ratio_max']}）：{hint}")

    body_blocks = [b for b in blocks(re.sub(r"(?m)^#\s+.*$", "", text))]
    prose_blocks = [b for b in body_blocks if is_prose(b) and not is_label_line(b)]
    long_paras = [b for b in prose_blocks if len(nospace(b)) > BUDGET["para_max"]]
    if long_paras:
        sample = "；".join(nospace(b)[:24] + "…" for b in long_paras[:3])
        warns.append(f"{len(long_paras)} 个段落超过 {BUDGET['para_max']} 字（约 3 行）：按 formatting.md 形状表"
                     f"改成列表、表格或引用块：{sample}")
    # walls: runs of plain paragraphs with no table/list/quote between them (headings break a run)
    walls, run = [], []
    for b in body_blocks + ["#"]:
        if is_prose(b) and not is_label_line(b):
            run.append(b)
            continue
        if len(run) > BUDGET["prose_run_max"]:
            walls.append(f"{nospace(run[0])[:20]}…（连续 {len(run)} 段）")
        run = []
    if walls:
        warns.append(f"{len(walls)} 处段落墙（超过 {BUDGET['prose_run_max']} 段纯段落连排）：中间换成列表/表格/引用块，"
                     "或删掉不改变决定的段：" + "；".join(walls[:3]))
    if unstructured:
        warns.append(f"这些章节超过 {BUDGET['section_needs_structure']} 字却没有一个表格或列表，读者只能逐字读："
                     + "、".join(unstructured))
    prose_chars = sum(len(nospace(b)) for b in prose_blocks)
    prose_share = round(prose_chars / max(1, total), 2)
    if total > 800 and prose_share > BUDGET["prose_share_max"]:
        warns.append(f"纯段落占全文 {int(prose_share * 100)}%（建议 ≤ {int(BUDGET['prose_share_max'] * 100)}%）："
                     "整篇在写散文，回到 formatting.md 先判断每块内容的形状")
    h4 = len(re.findall(r"(?m)^####+\s", text))
    if h4:
        warns.append(f"出现 {h4} 个四级及以下标题：层级太深，改成表格、列表或放进附录")
    if total > BUDGET["appendix_after"] and not appendix and "<details" not in md:
        warns.append(f"全文 {total} 字但没有附录或折叠块：把证据、参数、推导放到“附录”，正文只留判断和依据")

    lex = {k: re.findall(v, text) for k, v in LEX.items()}
    ai_total = sum(len(v) for v in lex.values())
    if ai_total >= 3 and per1k(ai_total) > BUDGET["ai_per_1k"]:
        top = sorted(((k, len(v), sorted(set(v))[:4]) for k, v in lex.items() if v), key=lambda x: -x[1])
        warns.append(f"套话密度 {per1k(ai_total)}/千字：" + "；".join(f"{k}{n}处（{'、'.join(e)}）" for k, n, e in top))
    jargon = [w for w in JARGON if w in text and w not in source_text]
    if jargon:
        warns.append("出现写作方法里的内部术语，读者看不懂，换成直白说法：" + "、".join(jargon))
    source_talk = re.findall(SOURCE_TALK, text)
    if source_talk:
        warns.append(f"正文提到写作用的素材 {len(source_talk)} 处（{'、'.join(sorted(set(source_talk))[:4])}）："
                     "读者手里没有这份素材，改写成事实状态，例如“未核实”“目前没有数据”")
    labels = BOLD_LABEL_RE.sub(r"\1", text)  # structural keys are not emphasis
    labels = "\n".join(l for l in labels.splitlines() if not l.lstrip().startswith("|"))  # table cells
    bolds = re.findall(r"\*\*([^*\n]+)\*\*", labels)
    bold = len(bolds)
    long_bold = [b for b in bolds if len(nospace(b)) > BUDGET["bold_len_max"]]
    if long_bold:
        warns.append(f"{len(long_bold)} 处整句加粗（超过 {BUDGET['bold_len_max']} 字）：只加粗关键词或数字，"
                     "如“**25 分钟**”而非整句：" + "；".join(nospace(b)[:16] + "…" for b in long_bold[:3]))
    crowded = [b for b in blocks(labels) if not b.startswith("|")
               for items in [re.split(r"(?m)^\s*(?:[-*]|\d+[.)])\s", b)]
               if any(len(re.findall(r"\*\*[^*\n]+\*\*", it)) > BUDGET["bold_per_block"] for it in items)]
    if crowded:
        warns.append(f"{len(crowded)} 段/项里加粗超过 {BUDGET['bold_per_block']} 处：一段只突出一个点，"
                     "两个都重要说明该拆：" + "；".join(nospace(b)[:20] + "…" for b in crowded[:3]))
    if bold >= 5 and per1k(bold) > BUDGET["bold_per_1k"]:
        warns.append(f"加粗 {bold} 处（{per1k(bold)}/千字）：加粗太多等于没有重点，只留结论、数字和风险")
    arrows = text.count("→")
    if arrows >= 5 and per1k(arrows) > BUDGET["arrows_per_1k"]:
        warns.append(f"箭头 {arrows} 处（{per1k(arrows)}/千字）：长箭头串说不清流程，超过三步的流程画图或写成有序列表")
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith(("#", "|"))]
    bullet_share = round(sum(1 for l in lines if re.match(r"^\s*([-*]|\d+[.)])\s", l)) / max(1, len(lines)), 2)
    if total > 2000 and bullet_share > BUDGET["bullet_line_share"]:
        warns.append(f"{int(bullet_share * 100)}% 的行是列表且几乎没有引导句：每组列表前用一句话说明它证明了什么")

    # 图型提示：正文讲状态/一来一回/对象模型，图的说明里却看不到对应图型。
    imgs = re.findall(r"!\[([^\]]*)\]\(", md)
    alts = " ".join(imgs)
    state_table = re.search(r"(?m)^\|\s*[^|\n]*状态[^|\n]*\|", text) and len(re.findall(r"(?m)^\|", text)) > 0
    hints = []
    if state_table and imgs and not re.search(r"状态图|状态机|生命周期", alts):
        hints.append("正文有状态表，却没有状态图（图说明里没出现“状态图/生命周期”）")
    if re.search(r"一对多|1\s*[:：]\s*n|多个执行实例|每个[^，。\n]{1,8}有多个", text) and imgs \
            and not re.search(r"ER|实体|对象模型|类图", alts):
        hints.append("正文描述了一对多的对象模型，却没有 ER/类图")
    if hints:
        warns.append("图型可能选错：" + "；".join(hints) + "。按 references/diagram-selection.md 选图型，"
                     "时序/状态/ER 不要画成卡片图")
    typed = re.findall(r"时序|状态图|状态机|生命周期|ER|实体|数据流|泳道|部署|甘特|里程碑|依赖", alts)
    if len(imgs) >= 4 and len(typed) <= 1:
        warns.append(f"本文有 {len(imgs)} 张图，图说明里几乎看不出图型差异：逐张对一遍 references/diagram-selection.md，"
                     "多张卡片架构图通常说明时序、状态或实体关系被画成了卡片")

    metrics = {"chars": total, "first_screen_chars": fs_chars, "h2_main": len(main), "appendix_h2": len(appendix),
               "skim_ratio": skim_ratio, "long_paragraphs": len(long_paras), "h4plus": h4,
               "prose_walls": len(walls), "unstructured_sections": len(unstructured), "prose_share": prose_share,
               "long_bold": len(long_bold),
               "h2_without_lead": len(leads_bad),
               "ai_phrases_per_1k": per1k(ai_total), "jargon": jargon, "source_talk": len(source_talk),
               "bold_per_1k": per1k(bold),
               "arrows_per_1k": per1k(arrows), "bullet_line_share": bullet_share}
    return {"ok": not errors, "errors": errors, "warnings": warns, "metrics": metrics, "skim": skim_text}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("document")
    ap.add_argument("--source", help="brief or notes; words that appear there are not reported as jargon")
    ap.add_argument("--skim", action="store_true", help="print the skim layer")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="fail on warnings too")
    args = ap.parse_args(argv)
    md = Path(args.document).read_text(encoding="utf-8")
    src = Path(args.source).read_text(encoding="utf-8") if args.source else ""
    r = check(md, src)
    if args.json:
        out = dict(r)
        if not args.skim:
            out.pop("skim")
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        m = r["metrics"]
        print(f"{args.document}: {m['chars']} 字，首屏 {m['first_screen_chars']} 字，正文章节 {m['h2_main']} 个，"
              f"速读层占比 {m['skim_ratio']}，套话 {m['ai_phrases_per_1k']}/千字")
        for e in r["errors"]:
            print(f"  错误：{e}")
        for w in r["warnings"]:
            print(f"  提醒：{w}")
        if not r["errors"] and not r["warnings"]:
            print("  结构检查通过")
        if args.skim:
            print("\n----- 速读层（只读这些能否讲清全文？）-----\n" + r["skim"])
    failed = r["errors"] or (args.strict and r["warnings"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
