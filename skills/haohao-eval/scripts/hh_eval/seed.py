# -*- coding: utf-8 -*-
"""种子数据与抽样、作者说明、判例、问题池与病灶。从 loop.py 原样搬来。"""
import datetime as dt
import hashlib
import random
import re

from hh_eval.const import SEVERITY
from hh_eval.fs import H, days_between, load_json, pkg, read_jsonl
from hh_eval.judge import jaccard, mechanical_check, norm


def regression_pool():
    return pkg("regression_seed.json") + load_json(H("regression_extra.json"), [])


def clean_pool():
    return pkg("clean_seed.json") + load_json(H("clean.json"), [])


def precedent_library():
    seeds = pkg("precedents.json")
    answered = [p for p in read_jsonl(H("precedents.jsonl"))]
    return seeds, answered


def rotate(pool, k, date, salt):
    if not pool or k <= 0:
        return []
    pool = sorted(pool, key=lambda x: x["id"])
    day = dt.date.fromisoformat(date).toordinal()
    rng = random.Random(f"{salt}-{day // max(1, len(pool) // max(1, k))}")
    order = pool[:]
    rng.shuffle(order)
    start = (day * k) % len(order)
    return [order[(start + i) % len(order)] for i in range(min(k, len(order)))]


def pick_calibration(cfg, st, date):
    cases = {str(c["id"]): c for c in pkg("cases50.json")}
    labels = pkg("labels.json", {})
    recent = {tuple(x[1]) for x in st.get("calib_recent", []) if days_between(x[0], date) < 14}
    buckets = {"红": [], "橙": [], "绿": []}
    for cid, lab in labels.items():
        for tool in ("我们", "工具1", "工具2"):
            f = lab.get(tool, {}).get("f")
            if f in buckets and cases.get(cid, {}).get(tool):
                buckets[f].append((cid, tool))
    rng = random.Random("calib-" + date)
    picks = []
    for f, n in (("红", cfg["daily"]["calib_red"]), ("橙", cfg["daily"]["calib_orange"]), ("绿", cfg["daily"]["calib_green"])):
        pool = [x for x in buckets[f] if x not in recent] or buckets[f]
        rng.shuffle(pool)
        picks += [(x, f) for x in pool[:n]]
    rng.shuffle(picks)
    queue, key = [], {}
    for i, ((cid, tool), f) in enumerate(picks, 1):
        c = cases[cid]
        item = {"原文": c["原始"], "上下文": "", "任务": "改写"}
        chk = mechanical_check(item, c[tool])
        kid = f"K{i:02d}"
        queue.append({"jid": kid, "任务": "改写", "文体": c.get("文体", ""), "力度": "标准", "原文": c["原始"],
                      "上下文": "", "事实": [], "改写": chk["body"], "给作者": chk["notes"],
                      "旗标": chk["flags"], "提示": chk["hints"], "判例": [],
                      "作者说明": notes_for(c.get("文体", ""))})
        key[kid] = {"case": cid, "tool": tool, "f": f}
    return queue, key


def active_notes():
    return [n for n in read_jsonl(H("notes.jsonl")) if n.get("status") == "active"]


def notes_for(genre, k=5):
    """作者说过的原话里适用于这个文体的（没限定文体的都适用），取最近 k 条。"""
    out = [{"id": n["id"], "原话": n["text"]} for n in active_notes()
           if not n.get("文体") or any(t in (genre or "") for t in n["文体"])]
    return out[-k:]


def nearest_precedents(text, k=2, exclude_source=None):
    seeds, answered = precedent_library()
    scored = []
    for p in answered:
        s = jaccard(text, (p.get("原文片段", "") or "") + (p.get("改写片段", "") or ""))
        scored.append((s, {"来源": "作者回答 " + p.get("id", ""), "原文片段": p.get("原文片段", ""),
                           "改写片段": p.get("改写片段", ""), "作者判断": p.get("answer", ""), "备注": p.get("note", "")}))
    for p in seeds:
        if exclude_source and p.get("来源") == exclude_source:
            continue
        if not p.get("评语"):
            continue
        s = jaccard(text, p.get("原文", ""))
        scored.append((s, {"来源": p["来源"] + "·" + p["工具"], "文体": p.get("文体", ""),
                           "保真档": p.get("保真档", ""), "作者原话": (p.get("总评", "") + "；" + p["评语"]).strip("；")}))
    scored.sort(key=lambda x: -x[0])
    return [dict(v, 相似度=round(s, 2)) for s, v in scored[:k] if s >= 0.12]


def item_precedents(it):
    """真实材料带着作者对这段旧改写的评价时，它就是这道题最贴身的判例，排第一。"""
    ev = it.get("作者评价") or {}
    if not ev.get("评价"):
        return nearest_precedents(it["原文"], 2)
    own = {"来源": "作者对这段原文旧改写的评价（" + it.get("来源", "") + "）",
           "改写片段": ev.get("旧改写", "")[:400], "作者原话": ev["评价"][:800]}
    return [own] + nearest_precedents(it["原文"], 1)


def pool_entries():
    return read_jsonl(H("pool.jsonl"))


def eligible_clusters(cfg, st, date):
    fixed_at = st.get("cluster_fixed_at", {})
    groups = {}
    for e in pool_entries():
        c = e["cluster"]
        if c == "P" or e.get("release", "v0000") < fixed_at.get(c, "v0000"):
            continue
        groups.setdefault(c, []).append(e)
    out = []
    for c, es in groups.items():
        cd = st.get("cooldown", {}).get(c, {})
        spread = max(len({e["date"] for e in es}), len({e["kind"] for e in es}))
        row = {"cluster": c, "count": len(es), "days": len({e["date"] for e in es}),
               "kinds": sorted({e["kind"] for e in es}), "cooldown_until": cd.get("until"),
               "status": cd.get("status", "")}
        row["eligible"] = (len(es) >= cfg["cluster"]["min_findings"] and spread >= cfg["cluster"]["min_spread"]
                           and not (cd.get("until") and cd["until"] > date) and cd.get("status") != "stuck")
        out.append(row)
    sev = {c: i for i, c in enumerate(SEVERITY)}
    out.sort(key=lambda r: (not r["eligible"], sev.get(r["cluster"].split("·")[0], 99), -r["count"]))
    return out, groups


def split_dev_holdout(entries):
    """留作验证的只能从还留着原题快照的题里挑；其余召回（包括快照已经清掉的旧召回）都进开发组。"""
    snap = {}
    for e in entries:
        if (e.get("item") or {}).get("原文"):
            snap.setdefault(e["item_id"], e)
    ids = sorted(snap, key=lambda i: hashlib.md5(i.encode()).hexdigest())
    hold_ids = ids[1::2]
    held = set(hold_ids)
    return [e for e in entries if e["item_id"] not in held], [snap[i] for i in hold_ids]


def manual_seed_pool():
    """作者手工批改种子库里可以出题的：状态是 seed、明确可出题、原文是完整段落（>=20 字）。
    作废的（截图转录勘误）、可出题 false 的（作者回源/内容取舍，技能复制不了）都不选。"""
    doc = pkg("manual_edits.json", {})
    out = []
    for s in doc.get("seeds", []):
        if s.get("状态") != "seed" or not s.get("可出题", False):
            continue
        src = (s.get("洗稿原句") or "").strip()
        if len(src) >= 20 and not src.startswith("（") and "……" not in src:
            out.append(s)
    return out


def manual_seed_items(k, today):
    """把手工批改种子按天轮转成当天的合成题。题面只有洗稿原句和必要的上文，
    作者动作、rule_signal 不带入，盲评裁判看不到答案。"""
    seeds = sorted(manual_seed_pool(), key=lambda s: s["id"])
    picked = rotate(seeds, min(k, len(seeds)), today, "manual")
    items = []
    for n, s in enumerate(picked, 1):
        m = re.search(r"(\d+)", s.get("id", ""))
        num = int(m.group(1)) if m else n
        items.append({
            "id": f"{today}-m{num:02d}", "kind": "synthetic", "group": "fresh", "任务": "改写",
            "文体": s.get("文体", "观点解析"), "读者": "", "场合": "", "力度": "标准",
            "原文": s["洗稿原句"].strip(), "上下文": (s.get("上下文") or "").strip(), "要求": "", "事实": [],
            "陷阱": "", "cluster": "", "来源": f"手工批改种子 {s['id']}", "manual_seed": s["id"],
        })
    return items


def seed_index():
    """按 id 索引手改种子库（含已作废、不可出题的）。"""
    return {s.get("id"): s for s in pkg("manual_edits.json", {}).get("seeds", []) if s.get("id")}


def dead_manual_seed_ids():
    """当前库里已经不能作为召回依据的种子 id：作废（勘误）或可出题 false（作者回源/内容取舍）。
    这些种子早先跑进过问题池的召回不算数，由 decide 自动驱逐。"""
    return {sid for sid, s in seed_index().items()
            if s.get("状态") != "seed" or not s.get("可出题", False)}


__all__ = [
    "regression_pool", "clean_pool", "precedent_library", "rotate", "pick_calibration", "active_notes",
    "notes_for", "nearest_precedents", "item_precedents", "pool_entries", "eligible_clusters",
    "split_dev_holdout", "manual_seed_pool", "manual_seed_items", "seed_index", "dead_manual_seed_ids",
]
