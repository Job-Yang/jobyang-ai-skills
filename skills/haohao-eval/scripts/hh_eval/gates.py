# -*- coding: utf-8 -*-
"""门禁、指标、争议队列、发布/回滚/监控、压缩清理、当天编排的领域函数。从 loop.py 原样搬来。

小样本诚实化（本轮新增）：门禁的 pass/fail 判定一字未动；凡依赖小样本的比较
（干净稿个位数、discordant 题个位数、体检题池约 17 天重复），结果进 stats["observations"]，
在 decision.json 和日报里标成「观察项」，不当成检验通过。
"""
import datetime as dt
import glob
import json
import math
import os
import random
import re
import shutil

from hh_eval.const import (ANSWER_WORDS, CODES, FAB, HARM, MINOR, RESIDUE, SNAP_KEYS, VERSIONS, Stop)
from hh_eval.fs import (H, Lock, append_jsonl, days_between, eval_home, file_sha, load_json, load_state,
                        log_author, published_path, read_jsonl, read_text, run_dir, save_json, save_state,
                        sha, write_jsonl, write_text)
from hh_eval.judge import cjk_len, cluster_of, jaccard, norm, split_output
from hh_eval.rules import release_text, rules_of, with_header
from hh_eval.seed import (active_notes, clean_pool, pool_entries, regression_pool, rotate, seed_index)


# ---------------------------------------------------------------- 指标与门禁

def load_judgments(rd):
    J = {}
    for v in VERSIONS:
        for p in glob.glob(os.path.join(rd, "judgments", v, "*.json")):
            j = load_json(p)
            J.setdefault(v, {})[j["item_id"]] = j
    return J


def codes_of(j):
    return [f["code"] for f in j.get("findings", [])]


def count_in(j, s):
    return sum(1 for c in codes_of(j) if c in s)


def gate_compare(base, cand, items, JB, JC, cfg, target=None, checks=None):
    reasons, stats = [], {}
    obs = []
    ids = [i["id"] for i in items if i["id"] in JB and i["id"] in JC]
    if not ids:
        return {"pass": False, "reasons": ["没有两个版本都判过的题"], "stats": {}}
    unc = sum(1 for i in ids if JB[i]["verdict"] == "不确定" or JC[i]["verdict"] == "不确定")
    stats["题数"] = len(ids)
    stats["不确定"] = unc
    if unc / len(ids) > cfg["gates"]["max_uncertain"]:
        reasons.append(f"拿不准的题占 {unc}/{len(ids)}，超过 {int(cfg['gates']['max_uncertain'] * 100)}%，今天不下结论")
    newfab = [i for i in ids if count_in(JC[i], FAB) and not count_in(JB[i], FAB)]
    stats["新增编造"] = newfab
    if newfab:
        reasons.append("候选新编了原文没有的信息：" + "、".join(newfab))
    cand_unsure = sum(1 for i in ids if JC[i]["verdict"] == "不确定")
    hb = sum(count_in(JB[i], HARM) for i in ids)
    hc = sum(count_in(JC[i], HARM) for i in ids) + cand_unsure
    stats["改坏问题"] = [hb, hc]
    if hc > hb:
        reasons.append(f"改坏类问题变多：{hb} → {hc}（候选拿不准的按改坏算）")
    mb = sum(count_in(JB[i], MINOR) for i in ids)
    mc = sum(count_in(JC[i], MINOR) for i in ids)
    stats["新毛病"] = [mb, mc]
    if mc > mb:
        reasons.append(f"破折号、绕口、手痒、自加免责这类新毛病变多：{mb} → {mc}")
    reg = [i["id"] for i in items if i.get("group") == "regression" and i["id"] in ids]
    broke = [i for i in reg if JC[i]["verdict"] in ("改坏了", "不确定") and JB[i]["verdict"] not in ("改坏了", "不确定")]
    stats["回归变坏"] = broke
    if broke:
        reasons.append("回归题有原来没坏、现在改坏的：" + "、".join(broke))
    clean = [i["id"] for i in items if i.get("group") == "clean" and i["id"] in ids]
    if clean and checks:
        eb = sum(checks["base"].get(i, {}).get("stats", {}).get("改动比例", 0) for i in clean) / len(clean)
        ec = sum(checks["cand"].get(i, {}).get("stats", {}).get("改动比例", 0) for i in clean) / len(clean)
        stats["干净稿改动比例"] = [round(eb, 3), round(ec, 3)]
        if ec > eb + cfg["gates"]["clean_edit_slack"]:
            reasons.append(f"干净稿被改得更多：改动比例 {eb:.2f} → {ec:.2f}")
        if len(clean) < 10:
            obs.append(f"干净稿只有 {len(clean)} 条，改动比例 {eb:.2f} → {ec:.2f} 只是观察项"
                       f"（启发式粗闸，不是统计检验）")
    if target:
        tids = [i["id"] for i in items if i.get("group") == "target" and i["id"] in ids]
        has = lambda j: any(f.get("cluster") == target for f in j.get("findings", []))  # noqa: E731
        fixed = sum(1 for i in tids if has(JB[i]) and not has(JC[i]))
        broken = sum(1 for i in tids if has(JC[i]) and not has(JB[i]))
        p = sign_p(fixed, broken)
        stats["目标病灶"] = {"题数": len(tids), "修好": fixed, "新犯": broken, "p": round(p, 3)}
        if fixed + broken < cfg["gates"]["target_min_discordant"] or p >= cfg["gates"]["target_alpha"]:
            reasons.append(f"目标病灶 {target} 修好 {fixed}、新犯 {broken}（p={p:.2f}），不够显著")
        if fixed + broken < 10:
            obs.append(f"目标病灶 discordant 只有 {fixed + broken} 题，sign test p={p:.2f} 只是观察项："
                       f"每天个位数 discordant 时 p 值波动很大，单天贴线不算铁证")
    stats["observations"] = obs
    return {"pass": not reasons, "reasons": reasons, "stats": stats}


def sign_p(fixed, broken):
    n = fixed + broken
    if n == 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(fixed, n + 1)) / 2 ** n


def item_metrics(items, JV, checks_v, alarm=0.3):
    body = [i for i in items if i.get("group") in ("fresh", "regression") and i["id"] in JV]
    clean = [i for i in items if i.get("group") == "clean" and i["id"] in JV]
    n = len(body)
    harm = sum(1 for i in body if JV[i["id"]]["verdict"] == "改坏了")
    fab = sum(1 for i in body if count_in(JV[i["id"]], FAB))
    resi = sum(1 for i in body if count_in(JV[i["id"]], RESIDUE))
    unsure = sum(1 for i in body if JV[i["id"]]["verdict"] == "不确定")
    over = 0
    for i in clean:
        er = checks_v.get(i["id"], {}).get("stats", {}).get("改动比例", 0)
        if count_in(JV[i["id"]], {"H"}) or er >= alarm:
            over += 1
    return {"n": n, "output_n": len(JV), "harm": harm, "fab": fab, "residue": resi, "unsure": unsure, "clean_n": len(clean), "over_edit": over}


def load_checks(rd, v):
    return {os.path.basename(p)[:-5]: load_json(p) for p in glob.glob(os.path.join(rd, "checks", v, "*.json"))}


# ---------------------------------------------------------------- 显示小工具

def cluster_tag(r, today):
    if r["eligible"]:
        return "够数"
    if r["cooldown_until"] and r["cooldown_until"] > today:
        return "冷却到 " + r["cooldown_until"]
    return "招不回" if r["status"] == "stuck" else "未够数"


def mode_label(cfg, st, date):
    if st["mode"] == "shadow":
        n = days_between(st["shadow_start"], date) + 1
        return f"影子运行第 {n}/{cfg['shadow_days']} 天（只记录不发布）"
    if st["mode"] == "paused":
        return "自动发布已暂停：" + (st.get("paused_reason") or "")
    return "自动发布"


def dispute_order(d):
    return ({"保真": 0, "场合": 1, "体检": 2, "新问题": 3, "抽查": 4}[d["kind"]], d["affects"] == "发布判断", d["created"])


def render_dispute(d):
    return (f"{d['id']} · {d['kind']} · {d.get('文体', '')}\n  原文：{d['原文片段']}\n"
            f"  改写：{d['改写片段'] or '（改写里没有对应的话）'}\n"
            + (f"  拿不准的地方：{d['原因']}\n" if d.get("原因") else "")
            + f"  {d['question']} 回复「{d['id']} 有」或「{d['id']} 没有」")


# ---------------------------------------------------------------- 题与版本

def item_key(src):
    return sha(norm(src))[:10]


def all_past_items(before):
    out = []
    for d in sorted(glob.glob(H("runs", "*"))):
        if os.path.basename(d) >= before:
            continue
        out += load_json(os.path.join(d, "items.json"), [])
    return out


def needed(version, items, plan):
    groups = {"current": {"fresh", "target", "regression", "clean"}, "cand": {"target", "regression", "clean"},
              "rc": {"fresh", "regression", "clean"}, "anchor": {"regression"}}[version]
    return [i for i in items if i.get("group") in groups]


def versions_present(rd):
    return [v for v in VERSIONS if os.path.isdir(os.path.join(rd, "outputs", v))]


def read_answers(d):
    rows = []
    p = os.path.join(d, "answers.jsonl")
    if os.path.exists(p):
        rows = read_jsonl(p)
    pj = os.path.join(d, "answers.json")
    if os.path.exists(pj):
        obj = load_json(pj)
        rows += obj if isinstance(obj, list) else []
    last = {}
    for r in rows:
        if isinstance(r, dict) and r.get("jid"):
            last[r["jid"]] = r
    return list(last.values())


def next_idem(items, JCUR, rd, today):
    """今天判为合格的一条改写，下一轮当干净稿再洗一遍（洗过的不该再大改）。"""
    byid = {i["id"]: i for i in items}
    for iid in sorted(JCUR):
        it, j = byid.get(iid), JCUR[iid]
        if not it or j["verdict"] != "合格" or it.get("任务") != "改写" or it.get("group") not in ("fresh", "regression"):
            continue
        body = split_output(read_text(os.path.join(rd, "outputs", "current", iid + ".txt")))[0]
        if body and not cjk_len(body) > 400:
            return {"date": today, "文体": it.get("文体", ""), "原文": body, "上下文": it.get("上下文", ""), "origin": iid}
    return None


def pick_clean(cfg, st, today):
    out = []
    k = cfg["daily"]["clean"]
    idem = st.get("idem")
    if idem and idem["date"] < today and k > 0:
        out.append({"id": f"{today}-idem01", "kind": "clean-idem", "group": "clean", "任务": "改写",
                    "文体": idem["文体"], "力度": "标准", "原文": idem["原文"], "上下文": idem["上下文"],
                    "origin": idem["origin"], "来源": "上一轮判为合格的改写，再洗一遍"})
    for n, it in enumerate(rotate(clean_pool(), k - len(out), today, "clean"), 1):
        out.append(dict(it, id=f"{today}-{it['id']}", kind="clean", group="clean", origin=it["id"]))
    return out


def print_plan(plan, rd):
    print(f"今天的运行目录：{rd}")
    for n in plan.get("notes", []):
        print("注意：" + n)
    print(f"模式：{plan['mode']} · 要改写的版本：{'、'.join(plan['versions'])}"
          + (" · 今天复测预发布，不出新候选" if plan["confirm_rc"] else ""))
    t = plan.get("target")
    if t:
        print(f"今天的目标病灶：{t['cluster']}（{t['name']}，池里 {t['count']} 条）。开发组证据在 target.json，"
              f"留作验证的 {len(t['holdout'])} 条已放进题目，写候选时不许看它们。")
    else:
        print("今天没有够数的病灶，先攒着，不出新规则。")
    q = plan["quota"]
    print(f"要出的新题：合成改写 {q['synthetic']} 条、起草 {q['drafting']} 条"
          + (f"、针对目标病灶的探针 {q['probes']} 条" if q["probes"] else "")
          + f"；真实材料最多 {q['real_max']} 条（没有就不加）。")
    if plan.get("manual_seeds"):
        print(f"另有作者手改种子题 {plan['manual_seeds']} 条已自动放进今天的题（只给原文，裁判看不到作者动作）。")
    print(f"裁判体检：{plan['calib_n']} 条，在 calib/queue.jsonl，答案写到 calib/answers.jsonl。")
    print("下一步：体检 → python3 scripts/loop.py calib-score；出题 → add-items；改写 → writer-view。")


def maybe_auto_switch(cfg, st, date, notes):
    if st["mode"] != "shadow" or not cfg.get("auto_switch"):
        return
    if days_between(st["shadow_start"], date) < cfg["shadow_days"]:
        return
    hist = [h for h in st.get("calib_history", []) if h["date"] >= st["shadow_start"]]
    ok_days = sum(1 for h in hist if h["pass"])
    audits = [a for a in st.get("audits", []) if a.get("answer") in ("有", "没有")]
    miss = sum(1 for a in audits if a["answer"] == "有")
    miss_rate = miss / len(audits) if audits else 0.0
    if hist and ok_days / len(hist) >= 0.7 and miss_rate <= cfg["disputes"]["audit_miss_pause"]:
        st["mode"] = "auto"
        st["anchor"] = st["published"]["release"]
        thin = "（抽查答得少，漏判率只能参考）" if len(audits) < cfg["disputes"]["audit_min_answered"] else ""
        notes.append(f"影子期结束：裁判体检 {ok_days}/{len(hist)} 天通过，抽查漏判 {miss}/{len(audits)}{thin}，已切到自动发布。"
                     "想继续只记录不发布，回复「保持影子」。")
    else:
        st["shadow_start"] = (dt.date.fromisoformat(date) - dt.timedelta(days=cfg["shadow_days"] - 7)).isoformat()
        notes.append(f"影子期到期但条件不够（体检通过 {ok_days}/{len(hist)} 天，抽查漏判 {miss}/{len(audits)}），再影子运行 7 天。")


# ---------------------------------------------------------------- 争议队列

def next_dispute_id(existing):
    nums = [int(d["id"][1:]) for d in existing if re.match(r"D\d+$", d.get("id", ""))]
    return max(nums, default=0) + 1


def new_dispute(st, kind, item, version, src, out, reason, suspect, date, affects):
    did = f"D{st['_next_d']}"
    st["_next_d"] += 1
    q = {"保真": "这处改写有没有改掉原文的意思？", "场合": f"放在「{item.get('文体', '')}」里，这个说法有没有不合适？",
         "新问题": "改写这句读着还有 AI 味吗？", "抽查": "整段看，这版改写有没有改坏或者没改好？",
         "体检": "这处算不算改坏了？"}[kind]
    default = {"保真": "有", "场合": "有", "新问题": "没有", "抽查": "跳过", "体检": "跳过"}[kind]
    d = {"id": did, "created": date, "kind": kind, "item_id": item["id"], "version": version, "文体": item.get("文体", ""),
         "原文片段": src, "改写片段": out, "原因": reason, "疑似编码": suspect, "question": q, "default": default,
         "affects": affects, "status": "open", "answer": None, "answered": None, "note": ""}
    if kind in ("保真", "场合", "新问题") and version == "current" and item.get("原文"):
        d["item"] = {k: item.get(k) for k in SNAP_KEYS}
    return d


def auto_match(d, cfg):
    if d["kind"] in ("抽查", "体检"):
        return d
    best, bs = None, 0.0
    for p in read_jsonl(H("precedents.jsonl")):
        if p.get("kind") != d["kind"]:
            continue
        s = jaccard(d["原文片段"] + d["改写片段"], p.get("原文片段", "") + p.get("改写片段", ""))
        if s > bs:
            best, bs = p, s
    if best and bs >= cfg["disputes"]["auto_match_similarity"]:
        d.update(status="auto", answer=best["answer"], answered=d["created"], note=f"跟 {best['id']} 几乎一样，照你当时的判断处理")
    return d


def _calib_same_case(a, b):
    return bool(a and b) and a.split("|", 1)[0] == b.split("|", 1)[0]


def _frag_contains(a, b):
    """两处原文片段是不是同一处：归一化后一段是另一段的连续子串。"""
    na, nb = norm(a), norm(b)
    return bool(na and nb) and (na in nb or nb in na)


def _calib_answered(ds):
    out = []
    for d in ds:
        if d.get("kind") == "体检" and d.get("status") == "answered" and d.get("answer") in ("有", "没有"):
            out.append(d)
    return out


def match_calib_answer(d, answered, cut):
    """同一材料、问题编码、原文与改写片段全部一致才复用；cut 只作调用兼容。
    相似原句不代表相同改法；自动/超时答案不作依据。冲突的最新人工答案不自动处理。
    """
    if d.get("kind") != "体检" or d.get("answer") not in (None, "跳过"):
        return None
    src, out = norm(d.get("原文片段", "")), norm(d.get("改写片段", ""))
    if not src:
        return None
    matches = []
    for p in answered:
        if (p.get("kind") != "体检" or p.get("status") != "answered"
                or p.get("answer") not in ("有", "没有")):
            continue
        if not _calib_same_case(d.get("calib_id"), p.get("calib_id")):
            continue
        # 跨工具的「有」可证明整份至少有一处改坏；局部「没有」不能证明另一整份全绿。
        if p["answer"] == "没有" and d.get("calib_id") != p.get("calib_id"):
            continue
        if (d.get("文体", "") != p.get("文体", "")
                or d.get("疑似编码", "") != p.get("疑似编码", "")):
            continue
        if src != norm(p.get("原文片段", "")) or out != norm(p.get("改写片段", "")):
            continue
        matches.append(p)
    if not matches:
        return None
    latest_day = max(p.get("answered") or p.get("created") or "" for p in matches)
    latest = [p for p in matches if (p.get("answered") or p.get("created") or "") == latest_day]
    if len({p["answer"] for p in latest}) != 1:
        return None
    return latest[-1], "同一材料、同一原句与改法"


def resolve_calib_disputes(cfg, st, today):
    """体检题去重只处理同一材料、文体、问题编码、原文及改法均一致的重复题。
    跨工具仅复用作者确认的「有」；相似句子、另一种改法或自动答案都不作为依据。
    """
    ds = read_jsonl(H("disputes.jsonl"))
    answered = _calib_answered(ds)
    cut = cfg["disputes"]["auto_match_similarity"]
    msgs, changed = [], False
    for d in ds:
        if d.get("kind") != "体检" or d.get("status") != "open":
            continue
        hit = match_calib_answer(d, answered, cut)
        if hit is None:
            continue
        hit, how = hit
        d["status"] = "auto"
        d["answer"] = hit["answer"]
        d["answered"] = today
        d["note"] = f"{how}，你在 {hit['id']} 已答「{hit['answer']}」，这题自动照此处理，不再重复问"
        apply_answer(d, st, today, to_precedent=False)
        log_author(today, f"{d['id']} {d['answer']}（{how}，与 {hit['id']} 重复，自动去重）")
        msgs.append(f"{d['id']} 和你答过的 {hit['id']} 是同一处（{how}），已自动记成「{d['answer']}」，不再问你。")
        changed = True
    if changed:
        write_jsonl(H("disputes.jsonl"), ds)
    return len(msgs), msgs


def expire_disputes(cfg, st, today):
    ds = read_jsonl(H("disputes.jsonl"))
    notes, changed = [], False
    for d in ds:
        if d["status"] == "open" and days_between(d["created"], today) >= cfg["disputes"]["default_after_days"]:
            d.update(status="defaulted", answer=d["default"], answered=today, note="超时，按保守默认处理")
            changed = True
            apply_answer(d, st, today, defaulted=True)
    if changed:
        write_jsonl(H("disputes.jsonl"), ds)
        n = sum(1 for d in ds if d["answered"] == today and d["status"] == "defaulted")
        notes.append(f"{n} 条待判断的题超过 {cfg['disputes']['default_after_days']} 天没回，已按保守默认处理。")
    return notes


def apply_answer(d, st, today, defaulted=False, to_precedent=True):
    """超时默认只影响当时的发布判断，不进问题池、不进判例；作者亲自回答的才进。"""
    if defaulted:
        return
    if d["kind"] == "体检":
        ov = load_json(H("calib_overrides.json"), {})
        if d["answer"] == "有":
            ov[d["calib_id"]] = {"f": "橙", "dispute": d["id"], "date": today}
        elif d["answer"] == "没有":
            ov[d["calib_id"]] = {"f": "绿确认", "dispute": d["id"], "date": today}
        else:
            ov.pop(d["calib_id"], None)
        save_json(H("calib_overrides.json"), ov)
    if d["kind"] == "抽查":
        st["audits"] = [a for a in st.get("audits", []) if a["id"] != d["id"]]
        if d["answer"] in ("有", "没有"):
            st["audits"].append({"id": d["id"], "date": today, "answer": d["answer"]})
        return
    pool = read_jsonl(H("pool.jsonl"))
    had = [e for e in pool if e.get("kind") == "dispute" and e.get("dispute_id") == d["id"]]
    if had:
        write_jsonl(H("pool.jsonl"), [e for e in pool if not (e.get("kind") == "dispute" and e.get("dispute_id") == d["id"])])
    if d["answer"] == "有" and d["version"] == "current":
        code = d.get("疑似编码") or ("D" if d["kind"] == "场合" else ("R" if d["kind"] == "新问题" else "P"))
        if code not in CODES:
            code = "P"
        it = d.get("item") or {i["id"]: i for i in load_json(os.path.join(run_dir(d["created"]), "items.json"), [])}.get(d["item_id"], {})
        append_jsonl(H("pool.jsonl"), [{"date": today, "run": d["created"], "item_id": d["item_id"], "kind": "dispute",
                                        "dispute_id": d["id"], "文体": d.get("文体", ""),
                                        "release": st["published"]["release"], "code": code,
                                        "cluster": cluster_of(code, "新") if code == "R" else code,
                                        "quote_src": d["原文片段"], "quote_out": d["改写片段"],
                                        "note": "作者判定：" + d.get("原因", ""),
                                        "item": {k: it.get(k) for k in ("任务", "文体", "力度", "原文", "上下文", "事实", "要求")}}])
    if not to_precedent:
        return
    prec = [p for p in read_jsonl(H("precedents.jsonl")) if p.get("id") != d["id"]]
    if d["answer"] in ("有", "没有"):
        prec.append({"id": d["id"], "date": today, "kind": d["kind"], "文体": d.get("文体", ""),
                     "原文片段": d["原文片段"], "改写片段": d["改写片段"], "answer": d["answer"], "note": d.get("note", "")})
    write_jsonl(H("precedents.jsonl"), prec)


def answer_dispute(cfg, st, ds, d, ans, note, today):
    """记下作者对一道题的回答，返回要另外告诉作者的话（比如抽查漏判太多、自动发布暂停了）。"""
    d.update(status="answered", answer=ans, answered=today, note=note or "")
    apply_answer(d, st, today)
    write_jsonl(H("disputes.jsonl"), ds)
    log_author(today, f"{d['id']} {ans}" + (f"（{note}）" if note else ""))
    return check_audit_pause(st, cfg)


def check_audit_pause(st, cfg):
    audits = [a for a in st.get("audits", []) if a["answer"] in ("有", "没有")][-20:]
    if len(audits) < cfg["disputes"]["audit_min_answered"]:
        return None
    miss = sum(1 for a in audits if a["answer"] == "有") / len(audits)
    if miss > cfg["disputes"]["audit_miss_pause"] and st["mode"] == "auto":
        st["mode"] = "paused"
        st["paused_reason"] = f"抽查里裁判漏判 {miss:.0%}，超过 {cfg['disputes']['audit_miss_pause']:.0%}"
        return "抽查漏判率超标，自动发布已暂停，召回照常跑。"
    return None


# ---------------------------------------------------------------- 发布、回滚、监控

def set_cooldown(st, cluster, today, cfg, days=None):
    cd = st.setdefault("cooldown", {}).setdefault(cluster, {"attempts": []})
    cd["attempts"] = [d for d in cd.get("attempts", []) if days_between(d, today) < cfg["cluster"]["stuck_window_days"]] + [today]
    cd["until"] = (dt.date.fromisoformat(today) + dt.timedelta(days=days or cfg["cluster"]["cooldown_days"])).isoformat()
    if len(cd["attempts"]) >= cfg["cluster"]["stuck_after"]:
        cd["status"] = "stuck"


def publish_text(st, body, release_id, today):
    path = published_path()
    cur = file_sha(path)
    if cur != st["published"]["sha"]:
        raise Stop("检测到你改过规则细则，为不盖掉你的改动，这一步先停下。回复「接受手工修改」把它记成新版本，或者先恢复原样。")
    content = with_header(body, release_id, today)
    write_text(path, content)
    back = file_sha(path)
    if back != sha(content):
        raise Stop("发布后回读对不上，停下检查磁盘。")
    st["published"] = {"release": release_id, "sha": back, "date": today}


def promote(st, rc, today, cfg, items, J):
    rid = f"v{st['next_release']:04d}"
    st["next_release"] += 1
    body = release_text(rc["id"])
    write_text(H("releases", rid, "daily-learning.md"), body)
    prev = st["published"]["release"]
    save_json(H("releases", rid, "meta.json"), {"id": rid, "date": today, "from_rc": rc["id"], "cluster": rc["cluster"], "prev": prev})
    publish_text(st, body, rid, today)
    st.setdefault("releases", []).append({"id": rid, "date": today, "cluster": rc["cluster"], "prev": prev, "type": "发布"})
    st.setdefault("cluster_fixed_at", {})[rc["cluster"]] = rid
    st.get("cooldown", {}).pop(rc["cluster"], None)
    st["rc"] = None
    extra = load_json(H("regression_extra.json"), [])
    snaps = rc.get("holdout_items")
    if snaps is None:
        snaps = [i for i in load_json(os.path.join(run_dir(rc["run"]), "items.json"), []) if i.get("id") in rc.get("holdout", [])][:3]
    for it in snaps:
        extra.append({"id": f"reg-{it['id']}", "kind": "regression", "group": "regression", "任务": it.get("任务", "改写"),
                      "文体": it.get("文体", ""), "力度": it.get("力度", "标准"), "原文": it["原文"],
                      "上下文": it.get("上下文", ""), "事实": it.get("事实", []), "来源": f"{rid} 修好的 {rc['cluster']}"})
    save_json(H("regression_extra.json"), extra)
    return rid


def unfix(st, to_release):
    fixed = st.setdefault("cluster_fixed_at", {})
    for c in [c for c, r in fixed.items() if r > to_release]:
        fixed.pop(c)


def monitor(st, cfg, today):
    if st["mode"] != "auto" or file_sha(published_path()) != st["published"]["sha"]:
        return None
    rels = [r for r in st.get("releases", []) if r["type"] == "发布"]
    if not rels:
        return None
    last = rels[-1]
    if st["published"]["release"] != last["id"] or days_between(last["date"], today) > cfg["monitor"]["window_days"]:
        return None
    rows = read_jsonl(H("metrics.jsonl"))
    after = [r for r in rows if r["date"] > last["date"] and r["release"] == last["id"]]
    before = [r for r in rows if 0 <= days_between(r["date"], last["date"]) <= cfg["monitor"]["window_days"] and r["release"] != last["id"]]
    if len(after) < cfg["monitor"]["min_days_after_release"] or not before:
        return None
    ra = sum(r["harm"] for r in after) / max(1, sum(r["n"] for r in after))
    rb = sum(r["harm"] for r in before) / max(1, sum(r["n"] for r in before))
    if ra - rb > cfg["monitor"]["harm_rate_margin"] and sum(r["harm"] for r in after) >= cfg["monitor"]["min_harm_items"]:
        body = release_text(last["prev"])
        publish_text(st, body, last["prev"], today)
        st["releases"].append({"id": last["prev"], "date": today, "cluster": last["cluster"], "prev": last["id"], "type": "回滚"})
        unfix(st, last["prev"])
        set_cooldown(st, last["cluster"], today, cfg, days=14)
        return f"已自动回滚到 {last['prev']}：发布 {last['id']} 后改坏率 {ra:.0%}，发布前 {rb:.0%}"
    return None


# ---------------------------------------------------------------- 作者说明的增删

def split_tags(s):
    return [t.strip() for t in re.split(r"[,，、/]", s or "") if t.strip()]


def add_note(st, rows, text, tags, today, source):
    """编号只增不减：清理掉的旧交代不会把编号让出来。"""
    nums = [int(x["id"][1:]) for x in rows if re.match(r"N\d+$", x.get("id", ""))]
    num = max(max(nums, default=0) + 1, st.get("next_note", 1))
    st["next_note"] = num + 1
    n = {"id": f"N{num:03d}", "date": today, "text": text, "文体": tags, "status": "active", "来源": source}
    rows.append(n)
    return n, f"{n['id']} 记下了（{'只用于' + '、'.join(tags) if tags else '所有文体都适用'}）：{text}"


def drop_note(n, today):
    n.update(status="dropped", dropped=today)
    return f"{n['id']} 作废了：{n['text']}"


# ---------------------------------------------------------------- 清理

def rewrite_jsonl(name, keep):
    path = H(name)
    if os.path.exists(path):
        rows = read_jsonl(path)
        kept = [r for r in rows if keep(r)]
        if len(kept) != len(rows):
            write_jsonl(path, kept)


def compact(cfg, st, today):
    """每天决策完清一次，数据目录只留跨天用得上的；状态文档每天整篇重写，不清就会越写越长。"""
    r = cfg["retain"]
    if os.path.exists(H("pool.jsonl")):
        pool = [e for e in read_jsonl(H("pool.jsonl")) if days_between(e["date"], today) <= r["pool_days"]]
        kept = {}
        for e in sorted(pool, key=lambda e: e["date"], reverse=True):
            if e.get("item"):
                ids = kept.setdefault(e["cluster"], set())
                if e["item_id"] not in ids and len(ids) < r["snapshots_per_cluster"]:
                    ids.add(e["item_id"])
                else:
                    e.pop("item")
            for k in ("quote_src", "quote_out", "note"):
                if len(e.get(k) or "") > 200:
                    e[k] = e[k][:200]
        write_jsonl(H("pool.jsonl"), pool)
    if os.path.exists(H("disputes.jsonl")):
        ds = []
        for d in read_jsonl(H("disputes.jsonl")):
            if d["status"] != "open":
                d.pop("item", None)
                if days_between(d.get("answered") or d["created"], today) > r["disputes_days"]:
                    continue
            ds.append(d)
        write_jsonl(H("disputes.jsonl"), ds)
    prec = read_jsonl(H("precedents.jsonl"))
    if len(prec) > r["precedents_max"]:
        write_jsonl(H("precedents.jsonl"), prec[-r["precedents_max"]:])
    rewrite_jsonl("notes.jsonl", lambda n: n.get("status") == "active" or n.get("doc_hold")
                  or days_between(n.get("dropped") or n["date"], today) <= r["notes_dropped_days"])
    rewrite_jsonl("inbox.jsonl", lambda x: days_between(x["date"], today) <= r["inbox_days"])
    rewrite_jsonl("metrics.jsonl", lambda x: days_between(x["date"], today) <= r["metrics_days"])
    extra = load_json(H("regression_extra.json"), [])
    if len(extra) > r["regression_extra_max"]:
        save_json(H("regression_extra.json"), extra[-r["regression_extra_max"]:])
    st["calib_history"] = st.get("calib_history", [])[-r["history_max"]:]
    st["audits"] = st.get("audits", [])[-r["history_max"]:]
    st["seen"] = {d: v for d, v in (st.get("seen") or {}).items() if days_between(d, today) <= r["seen_days"]}
    open_ids = {d["id"] for d in read_jsonl(H("disputes.jsonl")) if d["status"] == "open"}
    st["doc_shown"] = {k: v for k, v in (st.get("doc_shown") or {}).items()
                       if k in open_ids or days_between(v, today) <= r["disputes_days"]}
    keep = {"v0000", st["published"]["release"], st.get("anchor"), (st.get("rc") or {}).get("id")}
    for rel in st.get("releases", [])[-6:]:
        keep.update((rel["id"], rel.get("prev")))
    for d in glob.glob(H("releases", "*")):
        meta = load_json(os.path.join(d, "meta.json"), {}) or {}
        if os.path.basename(d) not in keep and days_between(meta.get("date") or today, today) > 7:
            shutil.rmtree(d, ignore_errors=True)
    for d in glob.glob(H("runs", "*")):
        name = os.path.basename(d)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", name) and days_between(name, today) > r["runs_days"]:
            shutil.rmtree(d, ignore_errors=True)
    for p in glob.glob(H("exports", "record-*.xml")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})\.xml$", p)
        if m and days_between(m.group(1), today) > r["runs_days"]:
            os.remove(p)


__all__ = [
    "load_judgments", "codes_of", "count_in", "gate_compare", "sign_p", "item_metrics", "load_checks",
    "cluster_tag", "mode_label", "dispute_order", "render_dispute", "item_key", "all_past_items",
    "needed", "versions_present", "read_answers", "next_idem", "pick_clean", "print_plan",
    "maybe_auto_switch", "next_dispute_id", "new_dispute", "auto_match", "expire_disputes",
    "apply_answer", "answer_dispute", "check_audit_pause", "match_calib_answer", "resolve_calib_disputes", "set_cooldown", "publish_text", "promote",
    "unfix", "monitor", "split_tags", "add_note", "drop_note", "rewrite_jsonl", "compact",
]
