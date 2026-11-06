#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_linkage.py — 图文咬合对账器（零三方依赖）。

解决同事那句话：「以为图是解释上面那段文字的，结果对不上」。
它把一张图当成一份"图上声明"，逐字核对图上每一个标签/术语/数字，
是不是都能在它锚定的那段正文（以及过渡句）里找到出处；并强制过渡句把读者带进图。

输入：一份"插图包"JSON，字段：
  mode:   "supplement"（保留正文，图辅助）| "replace"（压缩正文，图承载细节）
  cover:  true 表示封面（可无过渡句；其余检查照旧）
  source_text: 必填，这张图锚定的那段原文（图要解释的就是它）
  kept_text:   replace 模式下仍留在图旁的压缩文字
  bridge: 过渡句（1~2 句，必须含"下图/如图"之类指图词，且点出图里的具体东西）
  caption: 图注（建议有，且与图、正文用词一致）
  allow_new: 允许图/过渡句新引入、但你确认要同步加进正文的词（默认空）
  figure: {"kind":"renderer","spec":{…渲染器 JSON…}}
        | {"kind":"t2i","prompt":"…含引号图上文字的提示词…"}
        | {"kind":"cover","prompt":...}

退出码：0 无必改（可有待确认 WARN）；1 有必改 ERROR；2 用法/读文件错。
用法：
  python3 check_linkage.py figure.json
  python3 check_linkage.py figure.json --json
"""
import argparse
import json
import re
import sys
import unicodedata

POINTERS = ["下图", "上图", "这张图", "如图", "见图", "看图", "图中", "图里",
            "图所示", "下面这张", "本图", "这一图", "如下图", "见下图"]
GENERIC = set("所示如下可以具体一张里的是这一下图这张图这张图中我们先再就这张如下图画")
CN = lambda c: "\u4e00" <= c <= "\u9fff"
CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9}
# 纯装饰/导航，不参与对账
SKIP_SEG = {"", "vs", "v.s", "+", "→", "←", "↑", "↓", "-", "—", "·", "|", "/",
            "✅", "❌", "⚠", "×", "vs.", "a", "b", "c"}


def norm(s: str) -> str:
    """去空格的紧凑归一：用于中文 bigram / 数字比对。"""
    s = unicodedata.normalize("NFKC", str(s)).lower()
    s = (s.replace("–", "-").replace("—", "-").replace("～", "~")
           .replace("×", "x").replace("＋", "+").replace("÷", "/"))
    s = re.sub(r"\s+", "", s)
    return s


def norm_words(s: str) -> str:
    """保留空格的归一：用于英文按词切分（不能去空格，否则词会粘连）。"""
    s = unicodedata.normalize("NFKC", str(s)).lower()
    return re.sub(r"[，。；：、！？（）【】「」“”‘’/\\|]+", " ", s)


def ascii_words(s: str):
    return set(w for w in re.findall(r"[a-z][a-z0-9.+#_-]*", norm_words(s)))


def _cn_nums(s: str):
    out = set()
    for m in re.finditer(r"[零一二两三四五六七八九]?[十百千]?[零一二三四五六七八九]?", s):
        t = m.group(0)
        if not t:
            continue
        if t in CN_NUM:
            out.add(str(CN_NUM[t]))
        elif "十" in t:
            a, _, b = t.partition("十")
            tens = CN_NUM.get(a, 1)
            ones = CN_NUM.get(b, 0) if b else 0
            out.add(str(tens * 10 + ones))
    return out


def numbers(s: str):
    nums = set(re.findall(r"\d+(?:[.\-~至到]\d+)?", norm(s)))
    nums |= _cn_nums(str(s))
    return nums


def cjk_chars(s: str):
    return set(c for c in norm(s) if CN(c))


def cjk_bigrams(s: str):
    chars = [c for c in norm(s) if CN(c)]
    if len(chars) == 1:
        return {chars[0]}
    return {chars[i] + chars[i + 1] for i in range(len(chars) - 1)}


SEG_SPLIT = re.compile(r"[｜|、，,；;。．\.！!？\?/→:：·\n\t（）()\[\]【】「」\"'“”‘’]")


def segments(label: str):
    out = []
    for raw in re.split(r"\s+", str(label)):
        for seg in SEG_SPLIT.split(raw):
            seg = seg.strip(" -—·|/")
            if not seg or norm(seg) in SKIP_SEG:
                continue
            out.append(seg)
    return out


def is_pure_latin(seg: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9.+#_\-]*", norm(seg)))


def seg_scores(seg: str, faith_bg: set, faith_chars: set):
    """返回 (bigram覆盖率, 去重字符命中率, CJK字数)。单字词按字符命中。"""
    bg = cjk_bigrams(seg)
    cc = cjk_chars(seg)
    cov = len(bg & faith_bg) / len(bg) if bg else 1.0
    hit = len(cc & faith_chars) / len(cc) if cc else 1.0
    return round(cov, 2), round(hit, 2), len(cc)


# ---- 从渲染器 spec / t2i prompt 抽出"图上声明" --------------------------------
def extract_figure_text(fig: dict):
    """返回 [(路径, 图上文字, 是否命名性严格)]"""
    kind = (fig or {}).get("kind", "renderer")
    if kind in ("t2i", "cover"):
        prompt = fig.get("prompt", "")
        quoted = re.findall(r"[“\"「『]([^”\"」』]{1,40})[”\"」』]", prompt)
        out = []
        for i, q in enumerate(quoted):
            out.append((f"图上文字{i+1}", q, i == 0))
        if not out:
            out.append(("图上文字", "", False))  # 空占位，后面跳过
        return out
    spec = fig.get("spec", {})
    items = []
    if spec.get("kicker"):
        items.append(("kicker", spec["kicker"], True))
    if spec.get("title"):
        items.append(("title", spec["title"], True))
    if spec.get("subtitle"):
        items.append(("subtitle", spec["subtitle"], False))
    d = spec.get("data", {})
    lay = spec.get("layout")
    if lay == "pipeline":
        for i, st in enumerate(d.get("steps", [])):
            items.append((f"步骤{i+1}标题", st.get("title", ""), True))
            items.append((f"步骤{i+1}说明", st.get("desc", ""), False))
        for sp in d.get("span_labels", []):
            items.append(("阶段括号", sp.get("label", ""), True))
    elif lay == "columns":
        for i, c in enumerate(d.get("columns", [])):
            items.append((f"第{i+1}栏标题", c.get("title", ""), True))
            items.append((f"第{i+1}栏副题", c.get("subtitle", ""), False))
            items.append((f"第{i+1}栏场景", c.get("scene", ""), False))
            for j, b in enumerate(c.get("bullets", [])):
                items.append((f"第{i+1}栏要点{j+1}", b, False))
        for node in d.get("chain", []):
            items.append(("底部演进", node, True))
    elif lay == "two_stage":
        for i, st in enumerate(d.get("stages", [])):
            items.append((f"阶段{i+1}标题", st.get("title", ""), True))
            items.append((f"阶段{i+1}副题", st.get("subtitle", ""), False))
            for r_ in st.get("rows", []):
                items.append((f"阶段{i+1}属性值", r_.get("v", ""), False))
    elif lay == "compare":
        for i, c in enumerate(d.get("columns", [])):
            items.append((f"列标题{i+1}", c, True))
        for i, row in enumerate(d.get("rows", [])):
            items.append((f"行{i+1}维度", row.get("label", ""), True))
            for j, v in enumerate(row.get("values", [])):
                txt = v.get("text", "") if isinstance(v, dict) else str(v)
                items.append((f"单元格{i+1}-{j+1}", txt, False))
    elif lay == "radial":
        items.append(("中心", d.get("center", ""), True))
        for i, n in enumerate(d.get("nodes", [])):
            items.append((f"要点{i+1}", n, True))
    elif lay == "metaphor":
        items.append(("核心判断", d.get("point", ""), False))
        items.append(("补充", d.get("note", ""), False))
        for key in ("left_big", "right_small"):
            if d.get(key):
                items.append((key, d[key], True))
        for key in ("left_big_sub", "right_small_sub", "gap_label"):
            if d.get(key):
                items.append((key, d[key], False))
    return [(p, t, s) for p, t, s in items if str(t).strip()]


def evaluate(pkg: dict):
    E, W, checks = [], [], []

    def err(code, where, text, detail):
        E.append({"code": code, "where": where, "text": text, "detail": detail})

    def warn(code, where, text, detail):
        W.append({"code": code, "where": where, "text": text, "detail": detail})

    source = pkg.get("source_text", "")
    if not str(source).strip():
        err("E0", "source_text", "", "缺锚定正文：每张图都要绑定它解释的那段原文，否则无法判断图文是否一致")
        return E, W, checks
    cover = bool(pkg.get("cover"))
    mode = pkg.get("mode", "supplement")
    bridge = str(pkg.get("bridge", "") or "")
    caption = str(pkg.get("caption", "") or "")
    kept = str(pkg.get("kept_text", "") or "")
    allow = set(w.lower() for w in pkg.get("allow_new", []))

    # 忠实语料 = 只有原文（+保留正文）是图内容的出处；bridge/caption 不能给图背书，
    # 否则"图自创的词被写进图注→图注里有→对账通过"就是循环论证。
    faith = source if mode == "supplement" else (kept or source)
    faith_all = faith  # 图上术语/数字只能来自原文
    faith_words, faith_nums = ascii_words(faith), numbers(faith)
    faith_bg, faith_chars = cjk_bigrams(faith), cjk_chars(faith)
    # 咬合语料（含 bridge/caption）：只用于判断过渡句是否把图带进正文
    joint = "\n".join([faith, bridge, caption])
    joint_bg = cjk_bigrams(joint)
    fig = pkg.get("figure", {})
    fig_items = extract_figure_text(fig)

    # 1) 图上每段文字对账（出处只认原文）
    for path, text, strict in fig_items:
        for seg in segments(text):
            for w in ascii_words(seg):
                if w in allow:
                    continue
                if w not in faith_words:
                    err("E2", path, seg, f"英文/术语「{w}」在锚定正文里找不到，图不能自造术语")
            for num in numbers(seg):
                if num not in numbers(faith_all):
                    err("E3", path, seg, f"数字「{num}」正文里没有，图不能自造数字/量级")
            cbg = cjk_bigrams(seg)
            if cbg:
                cov, hit, ncc = seg_scores(seg, faith_bg, faith_chars)
                pct = round(cov * 100)
                if strict:
                    # 命名性标签：要么 bigram 连续命中过半，要么完全无序命中（每字都在），
                    # 否则视为另起名字/另换比喻
                    if cov >= 0.5 or hit >= 0.95:
                        checks.append(("OK", path, seg, f"覆盖 {pct}%"))
                    elif cov == 0 and ncc >= 4:
                        err("E4", path, seg, "命名性标签的字与正文零连续重合，疑似图里另起名字/另换比喻")
                    else:
                        warn("W2", path, seg, f"命名标签覆盖 {pct}%、字命中 {round(hit*100)}%，人工确认是否另起名字")
                else:
                    # 描述性/列举性标签（允许重排，但不能凭空造字）
                    if hit >= 0.8 or cov >= 0.5:
                        checks.append(("OK", path, seg, f"字命中 {round(hit*100)}%"))
                    elif hit < 0.5:
                        err("E4", path, seg, f"超半数字在正文里找不到（{round(hit*100)}%），疑似脱锚自造")
                    else:
                        warn("W2", path, seg, f"字命中 {round(hit*100)}%，措辞偏离正文，请人工确认")

    # 2) 过渡句
    if not cover:
        bn = norm(bridge)
        if not bridge.strip():
            err("E1", "bridge", "", "缺过渡句：图不能裸放在标题下，先用 1~2 句把读者带进图（点出图要看什么）")
        else:
            if not any(p in bridge for p in POINTERS):
                err("E1", "bridge", bridge, "过渡句没有指图词（下图/如图/见图/这张图…），读者不知道这句连着图")
            stripped = bn
            for p in POINTERS:
                stripped = stripped.replace(norm(p), "")
            for ch in GENERIC:
                stripped = stripped.replace(ch, "")
            stripped = re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", stripped)
            if len(stripped) < 3:
                err("E5", "bridge", bridge, "是空指图（只说『如下图所示』），要点出这张图具体讲什么")
            if len(re.findall(r"[。！？.!?；;]", bridge)) > 2:
                warn("W3", "bridge", bridge, "过渡句超过 2 句，过渡尽量一句话")
            if len(bridge) > 90:
                warn("W3", "bridge", bridge, "过渡句偏长（>90 字），建议压到一两句")
            # 过渡句要跟图里某个具体词咬合
            fig_names = [t for _, t, s in fig_items if s]
            linked = False
            for name in fig_names:
                for seg in segments(name):
                    if ascii_words(seg) & ascii_words(bridge):
                        linked = True
                    if cjk_bigrams(seg) & cjk_bigrams(bridge):
                        linked = True
            if not linked:
                err("E6", "bridge", bridge, "过渡句没点出图里的任何具体词，和图是断开的")

    # 3) 图注（出处仍对原文，不拿图注给图背书）
    if not caption.strip():
        warn("W4", "caption", "", "建议补一行图注，复述这张图的结论（与图、正文同词）")
    else:
        cov, hit, _ = seg_scores(caption, faith_bg, faith_chars)
        if cov < 0.3 and hit < 0.6:
            warn("W4", "caption", caption, "图注措辞与锚定正文偏离较大，核对是否另说一套")

    # 4) replace 模式：压缩后图+保留正文+过渡句不能丢原文的关键术语
    if mode == "replace" and kept:
        kept_all = kept + bridge + caption + " ".join(t for _, t, _ in fig_items)
        for w in faith_words:
            if len(w) >= 3 and w not in ascii_words(kept_all) and w not in allow:
                warn("W5", "source", w, "原文术语在压缩后的正文+图里都没出现，确认不是被删丢了")
    return E, W, checks


def render(pkg: dict, E, W, checks):
    lines = []
    fig = pkg.get("figure", {})
    head = (fig.get("spec", {}).get("title") if fig.get("kind", "renderer") == "renderer"
            else ("封面" if pkg.get("cover") else "文生图"))
    lines.append(f"图文咬合检查 · {head} · 模式={pkg.get('mode','supplement')}"
                 f" · 锚定正文 {len(pkg.get('source_text',''))} 字")
    lines.append("— 图内对账 —")
    for sym, where, text, note in checks:
        lines.append(f"  [{sym}] {where}：{text}（{note}）")
    for f in E:
        lines.append(f"  [必改·{f['code']}] {f['where']}：{f['text']} —— {f['detail']}")
    for f in W:
        lines.append(f"  [待确认·{f['code']}] {f['where']}：{f['text']} —— {f['detail']}")
    lines.append(f"必改 {len(E)} 项，待确认 {len(W)} 项")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        with open(args.package, encoding="utf-8") as f:
            pkg = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"读插图包失败：{e}", file=sys.stderr)
        return 2
    E, W, checks = evaluate(pkg)
    if args.json:
        print(json.dumps({"errors": E, "warnings": W,
                          "ok": not E}, ensure_ascii=False, indent=2))
    else:
        print(render(pkg, E, W, checks))
    return 1 if E else 0


if __name__ == "__main__":
    raise SystemExit(main())
