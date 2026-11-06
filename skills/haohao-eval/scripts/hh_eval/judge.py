# -*- coding: utf-8 -*-
"""文本工具、机械检查、裁判答案核对（引用逐字核对）。从 loop.py 原样搬来。"""
import difflib
import os
import re
import sys

from hh_eval.const import (CERTAIN, CODES, DISCLAIM_RX, FAB, FLAG_NEED, HARM, MINOR, MODAL, PROMISE, R_LABELS,
                           REGISTERS, RESIDUE, SAME_TIME, TECH_TERMS, TERM_SWAPS, VERDICTS)
from hh_eval.fs import SCRIPTS_DIR

sys.path.insert(0, SCRIPTS_DIR)
import scorer  # noqa: E402  残留扫描和新数字预筛，只当提示用

_TRANS = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "「": '"', "」": '"', "『": '"', "』": '"',
                        "，": ",", "。": ".", "：": ":", "；": ";", "！": "!", "？": "?", "（": "(", "）": ")",
                        "\u3000": " "})


def norm(s):
    return re.sub(r"\s+", "", (s or "").translate(_TRANS))


def quote_in(quote, text):
    """引用必须是原样连续片段；允许用「……」省略中间，省略两侧各段都要按顺序找得到。"""
    q = (quote or "").strip()
    if not q:
        return False
    parts = [norm(p) for p in re.split(r"……|\.\.\.|…", q)]
    parts = [p for p in parts if p]
    if not parts or sum(len(p) for p in parts) < 2:
        return False
    t = norm(text)
    pos = 0
    for p in parts:
        i = t.find(p, pos)
        if i < 0:
            return False
        pos = i + len(p)
    return True


def bigrams(s):
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def jaccard(a, b):
    A, B = bigrams(a), bigrams(b)
    return len(A & B) / len(A | B) if A and B else 0.0


def shingles(s, k=5):
    s = norm(s)
    return {s[i:i + k] for i in range(max(1, len(s) - k + 1))}


def split_output(text):
    """输出正文和「给作者」提醒分开：机械检查只查正文，提醒里的问题不算新加的信息。"""
    m = re.search(r"(^|\n)\s*(【给作者】|[「\[]?给作者[」\]]?\s*[：:])", text or "")
    if m:
        return text[:m.start()].strip(), text[m.end():].strip()
    return (text or "").strip(), ""


def cjk_len(s):
    return len(re.sub(r"\s+", "", s or ""))


def edit_ratio(a, b):
    return round(1 - difflib.SequenceMatcher(None, norm(a), norm(b), autojunk=False).ratio(), 3)


def latin_tokens(t):
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_+#.\-]*[A-Za-z0-9+#]|[A-Za-z]{2,}", t or "")}


def mechanical_check(item, output_text):
    body, notes = split_output(output_text)
    src = item.get("原文", "")
    ctx = item.get("上下文", "") or ""
    basis = src + "\n" + ctx
    task = item.get("任务", "改写")
    flags, hints = [], []

    def flag(kind, content, why):
        flags.append({"kid": f"K{len(flags) + 1}", "类型": kind, "内容": content, "说明": why})

    oq, rq = scorer._normalize_quant(basis), scorer._normalize_quant(body)
    for v in sorted(rq - oq):
        flag("新数字", v, "改写里有、原文和上下文里没有的量化说法（已按中文数字、百分比、一半归一化）")
    for w in sorted(latin_tokens(body) - latin_tokens(basis)):
        flag("新英文词", w, "改写里新出现的英文词或缩写")
    basis_t = basis
    for a_, b_ in SAME_TIME:
        basis_t = basis_t.replace(a_, b_)
    for w in PROMISE:
        if w in body and w not in basis_t:
            flag("承诺时间词新增", w, "改写里新出现的承诺或时间说法")
    for w in CERTAIN:
        if w in body and w not in basis:
            flag("确定性加强", w, "改写里新出现的确定语气")
    src_modal = [w for w in MODAL if w in basis]
    out_modal = [w for w in MODAL if w in body]
    if src_modal and len(out_modal) < len(src_modal):
        lost = [w for w in src_modal if w not in body]
        if lost:
            flag("模态变化", "、".join(lost), "原文的不确定语气在改写里少了")
    if task == "改写":
        for w in sorted(latin_tokens(src) - latin_tokens(body)):
            flag("术语丢失", w, "原文的英文术语在改写里没有了")
        for term in TECH_TERMS:
            if term in src and term not in body:
                swapped = [s for s in TERM_SWAPS.get(term, []) if s in body and s not in src]
                if swapped:
                    flag("术语替换", f"{term}→{swapped[0]}", "专业术语可能被换成了通俗说法")
                else:
                    flag("术语丢失", term, "原文的专业术语在改写里没有了")
    for fact in item.get("事实", []) or []:
        kws = fact.get("关键词") or []
        if kws and not any(k in body for k in kws):
            flag("事实关键词缺失", fact.get("id", ""), f"这条事实的关键词（{'、'.join(kws)}）在改写里都找不到，可能丢了或改了")
    ratio = round(cjk_len(body) / max(1, cjk_len(src)), 2)
    if task == "改写" and (ratio < 0.5 or ratio > 1.6):
        flag("长度异常", str(ratio), "改写长度是原文的 %.2f 倍" % ratio)
    for frag in dict.fromkeys(m.group() for m in DISCLAIM_RX.finditer(body)):
        if frag not in basis:
            flag("自加免责", frag, "正文里新出现的免责或依据说明，原文和上下文里没有")
    dash_new = body.count("——") - src.count("——")
    if dash_new > 0:
        hints.append(f"破折号比原文多 {dash_new} 个")
    half = re.findall(r"[\u4e00-\u9fff][,;:](?=[\u4e00-\u9fff])", body)
    if half:
        hints.append(f"中文里夹了半角标点 {len(half)} 处")
    res, detail = scorer.score_residual(body)
    for d in detail:
        if d["小计"] > 0 and "密度" not in d["类别"]:
            hints.append(f"正则提示·{d['类别']}：{' / '.join(d['样本'][:2])}")
    stats = {"原文字数": cjk_len(src), "改写字数": cjk_len(body), "长度比": ratio,
             "改动比例": edit_ratio(src, body), "一字未改": norm(src) == norm(body),
             "残留分": res, "有给作者提醒": bool(notes)}
    return {"flags": flags, "hints": hints, "stats": stats, "body": body, "notes": notes}


def check_finding(code, src_q, out_q, basis, body):
    """按编码核对引用。返回 (是否有效, 原因)。"""
    need_src = code in {"B", "G", "C1", "C2", "C3", "C4", "H", "U"}
    need_out = code in FAB | {"C1", "C2", "C3", "C4", "D", "E1", "E2", "E3", "F", "R", "H", "M"}
    if need_src and not quote_in(src_q, basis):
        return False, "原文引用在原文里找不到" if src_q else "缺原文引用"
    if need_out and not quote_in(out_q, body):
        return False, "改写引用在改写里找不到" if out_q else "缺改写引用"
    if code in FAB | {"M"} and quote_in(out_q, basis):
        return False, "这段在原文里就有，不算新加的"
    if src_q and not need_src and not quote_in(src_q, basis):
        return False, "原文引用在原文里找不到"
    if out_q and not need_out and not quote_in(out_q, body):
        return False, "改写引用在改写里找不到"
    return True, ""


def cluster_of(code, label):
    if code == "R":
        return "R·" + (label if label in R_LABELS else "新")
    return code


def verify_answer(ans, q):
    errs, findings, dropped = [], [], []
    basis = (q.get("原文", "") or "") + "\n" + (q.get("上下文", "") or "")
    body = q.get("改写", "") or ""
    claim = ans.get("结论")
    if claim not in VERDICTS:
        errs.append("结论必须是：改坏了 / 没改好 / 合格 / 不确定")
    if ans.get("场合") not in REGISTERS:
        errs.append("场合必须是五类之一：" + " / ".join(REGISTERS))
    facts = {f.get("id"): f for f in (q.get("事实") or [])}
    seen = set()
    for e in ans.get("对账") or []:
        fid, res = e.get("事实"), e.get("结果")
        if facts and fid not in facts:
            errs.append(f"对账里的 {fid} 不在事实清单里")
            continue
        seen.add(fid)
        if res not in ("保留", "丢了", "变了"):
            errs.append(f"对账 {fid} 的结果必须是：保留 / 丢了 / 变了")
            continue
        if res == "保留":
            continue
        code = e.get("编码") or ("B" if res == "丢了" else "C1")
        if code not in CODES or code == "P":
            errs.append(f"对账 {fid} 的编码 {code} 不认识")
            continue
        f = {"code": code, "label": e.get("病灶", ""), "src": e.get("原文引用", ""), "out": e.get("改写引用", ""),
             "note": e.get("说明", ""), "fact": fid}
        ok, why = check_finding(code, f["src"], f["out"], basis, body)
        (findings if ok else dropped).append(f if ok else dict(f, 作废原因=why))
    if facts:
        missing = [fid for fid in facts if fid not in seen]
        if missing:
            errs.append("事实清单没对完：" + "、".join(missing))
    for p in ans.get("问题") or []:
        code = p.get("编码")
        if code not in CODES or code == "P":
            errs.append(f"问题编码 {code} 不认识")
            continue
        f = {"code": code, "label": p.get("病灶", ""), "src": p.get("原文引用", ""), "out": p.get("改写引用", ""),
             "note": p.get("说明", "")}
        ok, why = check_finding(code, f["src"], f["out"], basis, body)
        (findings if ok else dropped).append(f if ok else dict(f, 作废原因=why))
    need = {k["kid"]: k for k in (q.get("旗标") or [])}
    answered = {}
    for r in ans.get("旗标") or []:
        kid, con = r.get("旗标"), r.get("结论")
        if kid in need and con in ("确认", "排除") and (r.get("理由") or "").strip():
            answered[kid] = con
    miss = [k for k in need if k not in answered]
    if miss:
        errs.append("机器旗标没回应（每条要写 确认/排除 和理由）：" + "、".join(miss))
    codes = {f["code"] for f in findings}
    for kid, con in answered.items():
        want = FLAG_NEED.get(need[kid]["类型"], set())
        if con == "确认" and want and not (codes & want):
            errs.append(f"旗标 {kid}（{need[kid]['类型']}）确认了，问题清单里却没有对应的条目")
    dispute = None
    if claim == "不确定":
        if not (ans.get("不确定原因") or "").strip():
            errs.append("结论是不确定时，要写不确定原因")
        d = ans.get("争议片段") or {}
        if d.get("问题类型") not in ("保真", "场合"):
            errs.append("结论是不确定时，要给争议片段：问题类型（保真/场合）、原文引用、改写引用")
        elif not quote_in(d.get("原文引用", ""), basis) or not quote_in(d.get("改写引用", ""), body):
            errs.append("争议片段的引用对不上原文或改写")
        else:
            dispute = {"类型": d["问题类型"], "原文片段": d["原文引用"], "改写片段": d["改写引用"],
                       "疑似编码": d.get("疑似编码", ""), "原因": ans.get("不确定原因", "")}
    uniq = {}
    for f in findings:
        k = (f["code"], norm(f.get("src", "")), norm(f.get("out", "")))
        if k in uniq:
            if not uniq[k].get("note") and f.get("note"):
                uniq[k]["note"] = f["note"]
            if not uniq[k].get("label") and f.get("label"):
                uniq[k]["label"] = f["label"]
        else:
            uniq[k] = dict(f)
    findings = list(uniq.values())
    verdict = derive_verdict(findings, claim)
    return {"errors": errs, "findings": findings, "dropped": dropped, "verdict": verdict, "claim": claim,
            "register": ans.get("场合"), "dispute": dispute,
            "claim_mismatch": claim in VERDICTS and claim != "不确定" and claim != verdict}


def derive_verdict(findings, claim):
    if claim == "不确定":
        return "不确定"
    codes = {f["code"] for f in findings}
    if codes & HARM:
        return "改坏了"
    if codes & (MINOR | RESIDUE | {"U"}):
        return "没改好"
    return "合格"


__all__ = [
    "norm", "quote_in", "bigrams", "jaccard", "shingles", "split_output", "cjk_len", "edit_ratio",
    "latin_tokens", "mechanical_check", "check_finding", "cluster_of", "verify_answer", "derive_verdict",
]
