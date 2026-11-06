# -*- coding: utf-8 -*-
"""手改稿的字面对照（观察项，不是学习效果或质量评分）。

仅统计可复核的文字动作：作者纯删除的片段、作者完整保留的句子、作者明确替换的新片段。
改写保留同义意思、重排句序等情况不推断；低相似度不得充当「删了」或「学会了」的证据。
只读可出题且有效的种子，在盲评结束后的 decide 中运行，不给改写员或裁判提供答案。
"""
import difflib
import re

from hh_eval.judge import norm
from hh_eval.seed import seed_index

_SENT = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")


def split_sentences(text):
    return [norm(m.group(0)) for m in _SENT.finditer(text or "")
            if len(norm(m.group(0))) >= 4]


def _meaningful(s):
    return len(re.sub(r"[\W_]", "", s)) >= 4


def _edits(src, target):
    return difflib.SequenceMatcher(None, src, target, autojunk=False).get_opcodes()


def author_intent(seed):
    src = norm(seed.get("洗稿原句", ""))
    target = (seed.get("改成") or "").strip()
    sentences = split_sentences(seed.get("洗稿原句", ""))
    if seed.get("作者动作") == "delete":
        return {"deleted": sentences, "kept": [], "edited": [], "replacements": []}
    # 无定稿或只有备注，不凭缺失目标推断作者删除了全文。
    if not target or target.startswith("（"):
        return {"deleted": [], "kept": [], "edited": sentences, "replacements": []}
    tgt = norm(target)
    deleted = [src[a:b] for tag, a, b, _, _ in _edits(src, tgt)
               if tag == "delete" and _meaningful(src[a:b])]
    kept = [s for s in sentences if s in tgt]
    edited = [s for s in sentences if s not in tgt and s not in deleted]
    replacements = [tgt[c:d] for tag, _, _, c, d in _edits(src, tgt)
                    if tag == "replace" and _meaningful(tgt[c:d])
                    and tgt[c:d] not in src]
    return {"deleted": deleted, "kept": kept, "edited": edited, "replacements": replacements}


def seed_diff(seed_id, output):
    seed = seed_index().get(seed_id)
    if (not seed or seed.get("状态") != "seed" or not seed.get("可出题", False)):
        return None
    intent = author_intent(seed)
    src, ours = norm(seed.get("洗稿原句", "")), norm(output)
    pure_deletes = [src[a:b] for tag, a, b, _, _ in _edits(src, ours) if tag == "delete"]
    # 只认可机器 diff 的纯删除；重写成无关内容不能算「跟删」。
    del_hits = sum(1 for s in intent["deleted"]
                   if s not in ours and any(s in chunk for chunk in pure_deletes))
    keep_bad = sum(1 for s in intent["kept"] if s not in ours)
    targets = intent["replacements"]
    edit_hits = sum(1 for t in targets if t in ours)

    def pct(h, n):
        return round(h / n, 3) if n else None

    return {"seed": seed_id,
            "跟删": pct(del_hits, len(intent["deleted"])),
            "越动": pct(keep_bad, len(intent["kept"])),
            "跟改": pct(edit_hits, len(targets)),
            "作者删": len(intent["deleted"]), "跟上删": del_hits,
            "作者留": len(intent["kept"]), "我们动了": keep_bad,
            "作者改": len(targets), "跟上改": edit_hits,
            "口径": "纯文字动作；跟改仅为新片段字面命中，不代表改对或学会"}


def summarize(diffs):
    def agg(h, n):
        hn, nn = sum(d[h] for d in diffs), sum(d[n] for d in diffs)
        return {"hit": hn, "n": nn, "rate": round(hn / nn, 3) if nn else None}
    return {"n": len(diffs), "delete": agg("跟上删", "作者删"),
            "keep": agg("我们动了", "作者留"), "edit": agg("跟上改", "作者改")}


__all__ = ["split_sentences", "author_intent", "seed_diff", "summarize"]
