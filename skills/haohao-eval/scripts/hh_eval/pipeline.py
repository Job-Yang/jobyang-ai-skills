# -*- coding: utf-8 -*-
"""各个子命令的编排。从 loop.py 的 cmd_* 原样搬来；行为增量只有一处：
门禁里依赖小样本的比较收进 decision.json 的 observations（观察项），日报打印出来。
"""
import datetime as dt
import glob
import hashlib
import json
import os
import random
import re

from hh_eval.const import (ANSWER_WORDS, CODES, FAB, HARM, NOTES_TITLE, REQUIRED_FACT_KINDS, SECTION_TITLE,
                           SLOT, SNAP_KEYS, VERSION, VERSIONS, Stop)
from hh_eval.docdoc import (apply_doc_answers, doc_lines, recall_section, record_body, section_head,
                             section_notes, sync_doc_notes)
from hh_eval.fp import find_shuohua_dir, fingerprints
from hh_eval.fs import (H, Lock, append_jsonl, badcase_source, days_between, eval_home, file_sha,
                        lark_cmd, load_config, load_json, load_state, log_author, pkg, published_path,
                        read_json, read_jsonl, read_text, run_dir, save_json, save_state, sha,
                        today_str, write_jsonl, write_text)
from hh_eval.gates import (all_past_items, answer_dispute, apply_answer, auto_match, check_audit_pause,
                           cluster_tag, compact, dispute_order, expire_disputes, gate_compare,
                           item_key, item_metrics, load_checks, load_judgments, match_calib_answer,
                           maybe_auto_switch, mode_label, monitor, new_dispute, needed, next_dispute_id,
                           next_idem, pick_clean, print_plan, promote, publish_text, read_answers,
                           render_dispute, resolve_calib_disputes, set_cooldown, split_tags, add_note, drop_note,
                           unfix, versions_present)
from hh_eval.judge import (cjk_len, cluster_of, mechanical_check, norm, quote_in, shingles, split_output,
                           verify_answer)
from hh_eval.manualdiff import seed_diff, summarize as summarize_seed_diff
from hh_eval.rules import release_text, rules_of, validate_candidate, with_header
from hh_eval.seed import (active_notes, clean_pool, dead_manual_seed_ids, eligible_clusters, item_precedents, manual_seed_items,
                          notes_for, pick_calibration, pool_entries, regression_pool, rotate, split_dev_holdout)
from hh_eval.statedoc import (doc_content, install_state, state_body, state_from_doc, state_header,
                              state_summary, state_doc_xml, unflatten)


# ---------------------------------------------------------------- init / status

def cmd_init(args):
    os.makedirs(eval_home(), exist_ok=True)
    if os.path.exists(H("state.json")):
        if not args.force:
            print(f"已经初始化过：{eval_home()}。只想刷新配置（技能目录、模型名）就加 --force，数据和发布记录都不动。")
            return 0
        with Lock():
            cfg = load_config()
            if args.shuohua_dir:
                cfg["shuohua_skill_dir"] = os.path.abspath(args.shuohua_dir)
            cfg["shuohua_skill_dir"] = find_shuohua_dir(cfg)
            if args.model:
                cfg["model_name"] = args.model
            save_json(H("config.json"), cfg)
            st = load_state()
            st["constitution"] = fingerprints(cfg).get("constitution", "")
            save_state(st)
        print(f"配置已刷新：好好说话技能目录 {cfg['shuohua_skill_dir'] or '没找到'}。数据和发布记录没动。")
        return 0
    with Lock():
        cfg = load_config()
        if args.shuohua_dir:
            cfg["shuohua_skill_dir"] = os.path.abspath(args.shuohua_dir)
        found = find_shuohua_dir(cfg)
        cfg["shuohua_skill_dir"] = found
        if args.model:
            cfg["model_name"] = args.model
        save_json(H("config.json"), cfg)
        today = today_str(args)
        old = {}
        pub = published_path()
        existing = read_text(pub) if os.path.exists(pub) else ""
        existing = re.sub(r"^# 好好说话 · 每日细则\s*", "", rules_of(existing)[1]).strip()
        existing = "" if existing == "（还没有细则）" else existing
        write_text(H("releases", "v0000", "daily-learning.md"), existing)
        save_json(H("releases", "v0000", "meta.json"), {"id": "v0000", "date": today,
                                                        "source": "初始化时已有的文件" if existing else "空"})
        st = {"schema": 1, "created": old.get("created", today), "mode": "shadow", "shadow_start": today,
              "published": {"release": "v0000", "sha": file_sha(pub), "date": today},
              "rc": None, "anchor": "v0000", "releases": old.get("releases", []),
              "cluster_fixed_at": old.get("cluster_fixed_at", {}), "cooldown": old.get("cooldown", {}),
              "calib_recent": [], "calib_history": old.get("calib_history", []), "audits": old.get("audits", []),
              "next_dispute": old.get("next_dispute", 1), "next_rc": old.get("next_rc", 1),
              "next_release": old.get("next_release", 1), "paused_reason": None,
              "constitution": fingerprints(cfg).get("constitution", "")}
        save_state(st)
        for d in ("runs", "releases", "exports"):
            os.makedirs(H(d), exist_ok=True)
    print(f"初始化完成：{eval_home()}")
    print(f"好好说话技能目录：{found or '没找到，底线哈希和技能指纹先跳过；在 config.json 里填 shuohua_skill_dir'}")
    print(f"细则发布位置：{pub}（{'已有文件，记为 v0000' if existing else '还没有，记为空的 v0000'}）")
    print(f"模式：影子运行 {cfg['shadow_days']} 天，只记录不发布。")
    print("可选：把人写的干净文本导进来做误改对照：python3 scripts/loop.py import-clean 文件.json")
    return 0


def cmd_status(args):
    cfg, st = load_config(), load_state()
    today = today_str(args)
    rows, _ = eligible_clusters(cfg, st, today)
    open_d = [d for d in read_jsonl(H("disputes.jsonl")) if d["status"] == "open"]
    print(f"数据目录：{eval_home()}")
    print(f"模式：{mode_label(cfg, st, today)}")
    print(f"现用细则：{st['published']['release']}（{st['published']['date']}）· 锚点：{st['anchor']}"
          + (f" · 预发布：{st['rc']['id']}（{st['rc']['cluster']}）" if st.get("rc") else ""))
    print(f"待你判断：{len(open_d)} 条 · 作者说明：{len(active_notes())} 条")
    if st.get("state_seq"):
        print(f"状态文档：最近存的是第 {st['state_seq']} 份（{st.get('state_saved', '')}）")
    print("问题池（前 8 类）：")
    for r in rows[:8]:
        print(f"  {r['cluster']:<10} {r['count']:>3} 条 · {r['days']} 天 · {'/'.join(r['kinds'])} · {cluster_tag(r, today)}")
    last = st.get("last")
    if last:
        print(f"最近一次：{last['date']} · {last['headline']}")
    return 0


# ---------------------------------------------------------------- start

def cmd_start(args):
    cfg, st = load_config(), load_state()
    today = today_str(args)
    rd = run_dir(today)
    if os.path.exists(os.path.join(rd, "manifest.json")) and not args.force:
        print(f"今天这一轮已经开过：{rd}。接着往下跑就行；要整轮重开加 --force。")
        print_plan(load_json(os.path.join(rd, "plan.json")), rd)
        return 0
    with Lock():
        if args.force and os.path.exists(rd):
            import datetime as _dt
            os.replace(rd, rd + ".bak-" + _dt.datetime.now().strftime("%H%M%S"))
        notes = []
        maybe_auto_switch(cfg, st, today, notes)
        _, dedup_msgs = resolve_calib_disputes(cfg, st, today)
        notes += dedup_msgs
        notes += expire_disputes(cfg, st, today)
        if cfg["sources"].get("read_new_badcases") and not badcase_source(cfg)[0]:
            notes.append("BadCase 母表没配置（环境变量 HAOHAO_EVAL_BADCASE_BASE/TABLE 和 config.json 都没有），"
                         "今天不从母表新增真实材料；要恢复就设环境变量或把表 ID 填回 config.json。")
        fp = fingerprints(cfg)
        if fp.get("constitution") and st.get("constitution") and fp["constitution"] != st["constitution"]:
            notes.append("好好说话的底线条款你改过，我已经记下新版本。")
            st["constitution"] = fp["constitution"]
        manual = fp["published"] != st["published"]["sha"]
        if manual:
            notes.append("你改过规则细则（和我上次存的不一样）：为了不盖掉你的改动，今天先不出新规则。"
                         "你可以回复「接受手工修改」，我把它记成正式版本；"
                         "也可以等我攒齐一批方案时并进来，你说 OK 一起生效。")
        confirm = bool(st.get("rc")) and st["rc"]["date"] < today and not manual
        calib_q, calib_key = pick_calibration(cfg, st, today)
        calib_cases = {f"cases50#{v['case']}" for v in calib_key.values()}
        items = []
        reg_pool = [r for r in regression_pool() if r.get("来源") not in calib_cases]
        for it in rotate(reg_pool, cfg["daily"]["regression"], today, "reg"):
            items.append(dict(it, id=f"{today}-{it['id']}", kind="regression", group="regression", origin=it["id"]))
        items += pick_clean(cfg, st, today)
        target = None
        if not confirm and not manual:
            rows, groups = eligible_clusters(cfg, st, today)
            elig = [r for r in rows if r["eligible"]]
            if elig:
                c = elig[0]["cluster"]
                dev, hold = split_dev_holdout(groups[c])
                target = {"cluster": c, "name": CODES.get(c.split("·")[0], c), "count": elig[0]["count"],
                          "dev": dev, "holdout": [h["item_id"] for h in hold]}
                for n, h in enumerate(hold, 1):
                    snap = h.get("item", {})
                    items.append({"id": f"{today}-h{n:02d}", "kind": "holdout", "group": "target", "cluster": c,
                                  "origin": h["item_id"], "任务": snap.get("任务", "改写"), "文体": snap.get("文体", ""),
                                  "力度": snap.get("力度", "标准"), "原文": snap.get("原文", ""),
                                  "上下文": snap.get("上下文", ""), "事实": snap.get("事实", [])})
        manual_seed_n = 0
        if getattr(args, "manual_seeds", False):
            m_items = manual_seed_items(cfg["daily"].get("manual_seeds", 0), today)
            manual_seed_n = len(m_items)
            items += m_items
        write_jsonl(os.path.join(rd, "calib", "queue.jsonl"), calib_q)
        save_json(os.path.join(rd, "private", "calib_key.json"), calib_key)
        st["calib_recent"] = [x for x in st.get("calib_recent", []) if days_between(x[0], today) < 14] + \
            [[today, [v["case"], v["tool"]]] for v in calib_key.values()]
        save_json(os.path.join(rd, "items.json"), items)
        write_text(os.path.join(rd, "overlays", "current.md"), read_text(published_path()) or with_header("", st["published"]["release"], today))
        versions = ["current"]
        if confirm:
            write_text(os.path.join(rd, "overlays", "rc.md"), with_header(release_text(st["rc"]["id"]), st["rc"]["id"], today))
            versions.append("rc")
            if st["anchor"] != st["published"]["release"]:
                write_text(os.path.join(rd, "overlays", "anchor.md"), with_header(release_text(st["anchor"]), st["anchor"], today))
                versions.append("anchor")
        if target:
            save_json(os.path.join(rd, "target.json"), target)
        d = cfg["daily"]
        plan = {"date": today, "mode": st["mode"], "confirm_rc": confirm, "versions": versions,
                "target": {k: target[k] for k in ("cluster", "name", "count", "holdout")} if target else None,
                "quota": {"synthetic": d["synthetic"], "drafting": d["drafting"], "real_max": d["real_max"],
                          "probes": d["probes"] if target else 0},
                "manual_seeds": manual_seed_n,
                "calib_n": len(calib_q), "notes": notes, "manual_edit": manual}
        save_json(os.path.join(rd, "plan.json"), plan)
        save_json(os.path.join(rd, "manifest.json"), {"date": today, "fingerprints": fp, "mode": st["mode"],
                                                      "published": st["published"], "rc": st.get("rc"),
                                                      "anchor": st["anchor"], "model": args.model or cfg.get("model_name", "")})
        st["last_run"] = today
        save_state(st)
    print_plan(plan, rd)
    return 0


# ---------------------------------------------------------------- 题目

def cmd_add_items(args):
    today = today_str(args)
    rd = run_dir(today)
    plan = load_json(os.path.join(rd, "plan.json"))
    if not plan:
        raise Stop("今天还没 start。")
    new = load_json(args.file)
    if isinstance(new, dict):
        new = new.get("items", [])
    items = load_json(os.path.join(rd, "items.json"), [])
    past = all_past_items(today)[-2000:] + items + regression_pool() + clean_pool()
    past_sh = [(p.get("id"), shingles(p.get("原文", ""))) for p in past]
    seen = {h: d for d, hs in (load_state().get("seen") or {}).items() if d < today for h in hs.split()}
    prefix = {"synthetic": "s", "probe": "p", "drafting": "d", "real": "r"}
    errs, added = [], []
    counts = {k: sum(1 for i in items if i.get("kind") == k) for k in prefix}
    q_all = plan["quota"]
    for n, it in enumerate(new, 1):
        kind = it.get("kind")
        tag = f"第 {n} 条"
        if kind not in prefix:
            errs.append(f"{tag}：kind 必须是 synthetic / probe / drafting / real")
            continue
        task = "起草" if kind == "drafting" else it.get("任务", "改写")
        src = (it.get("原文") or "").strip()
        if cjk_len(src) < 20:
            errs.append(f"{tag}：原文（起草题是材料）太短")
            continue
        if not it.get("文体"):
            errs.append(f"{tag}：缺文体")
            continue
        if kind == "drafting" and not it.get("要求"):
            errs.append(f"{tag}：起草题要写「要求」")
            continue
        facts = it.get("事实") or []
        if kind in REQUIRED_FACT_KINDS:
            if len(facts) < 3:
                errs.append(f"{tag}：{kind} 题至少要 3 条事实")
                continue
            bad = [f.get("id") for f in facts if not f.get("id") or not f.get("关键词")
                   or not all(quote_in(k, src) for k in f["关键词"])]
            if bad:
                errs.append(f"{tag}：这些事实缺 id/关键词，或关键词不在原文里：{bad}")
                continue
        if kind == "probe" and (it.get("cluster") != (plan.get("target") or {}).get("cluster") or not it.get("陷阱")):
            errs.append(f"{tag}：探针要写 cluster（等于今天的目标病灶）和 陷阱")
            continue
        if kind == "real" and not it.get("来源"):
            errs.append(f"{tag}：真实材料要写来源")
            continue
        ev = it.get("作者评价")
        if ev is not None and (kind != "real" or not isinstance(ev, dict) or not (ev.get("评价") or "").strip()):
            errs.append(f"{tag}：作者评价只给真实材料，写成 {{\"旧改写\": \"...\", \"评价\": \"作者原话\"}}")
            continue
        cap = {"synthetic": q_all["synthetic"], "drafting": q_all["drafting"], "probe": q_all["probes"],
               "real": q_all["real_max"]}[kind]
        if counts[kind] >= cap:
            errs.append(f"{tag}：今天的 {kind} 题已经够 {cap} 条了")
            continue
        sh = shingles(src)
        dup = next((pid for pid, psh in past_sh if psh and len(sh & psh) / max(1, len(sh | psh)) >= 0.8), None)
        if dup:
            errs.append(f"{tag}：跟 {dup} 几乎一样，换一条")
            continue
        if item_key(src) in seen:
            errs.append(f"{tag}：{seen[item_key(src)]} 出过一模一样的题，换一条")
            continue
        counts[kind] += 1
        iid = f"{today}-{prefix[kind]}{counts[kind]:02d}"
        rec = {"id": iid, "kind": kind, "group": "target" if kind == "probe" else "fresh", "任务": task,
               "文体": it["文体"], "读者": it.get("读者", ""), "场合": it.get("场合", ""),
               "力度": it.get("力度", "标准"), "原文": src, "上下文": it.get("上下文", ""),
               "要求": it.get("要求", ""), "事实": facts, "陷阱": it.get("陷阱", ""),
               "cluster": it.get("cluster", ""), "来源": it.get("来源", "synthetic:" + today)}
        if ev:
            rec["作者评价"] = {"旧改写": (ev.get("旧改写") or "").strip(), "评价": ev["评价"].strip()}
        items.append(rec)
        past_sh.append((iid, sh))
        added.append(iid)
    save_json(os.path.join(rd, "items.json"), items)
    print(f"收下 {len(added)} 条：{'、'.join(added) if added else '无'}")
    for e in errs:
        print("退回：" + e)
    q = plan["quota"]
    have = {k: sum(1 for i in items if i.get("kind") == k) for k in prefix}
    print(f"今天已有：合成 {have['synthetic']}/{q['synthetic']}，起草 {have['drafting']}/{q['drafting']}，"
          f"探针 {have['probe']}/{q['probes']}，真实 {have['real']}/{q['real_max']}")
    return 1 if errs else 0


def cmd_writer_view(args):
    today = today_str(args)
    rd = run_dir(today)
    plan = load_json(os.path.join(rd, "plan.json"))
    items = load_json(os.path.join(rd, "items.json"), [])
    v = args.version
    if v == "cand" and not os.path.exists(os.path.join(rd, "overlays", "cand.md")):
        raise Stop("候选还没 stage，不能改写 cand。")
    if v not in plan["versions"] and v != "cand":
        raise Stop(f"今天不需要改写 {v} 版。")
    todo = [i for i in needed(v, items, plan) if not os.path.exists(os.path.join(rd, "outputs", v, i["id"] + ".txt"))]
    print(f"版本 {v}：还有 {len(todo)} 条要写。改写时把 {os.path.join(rd, 'overlays', v + '.md')} 当作 daily-learning.md 读，"
          f"不读已发布那份。每条只看下面给的内容，写到指定文件；原文缺的具体写在正文后面的「【给作者】」一段里。")
    for i in todo:
        print("\n" + "=" * 60)
        print(f"题 {i['id']} → 写到 {os.path.join(rd, 'outputs', v, i['id'] + '.txt')}")
        print(f"任务：{i.get('任务', '改写')} · 文体：{i.get('文体', '')}" + (f" · 读者：{i['读者']}" if i.get("读者") else "")
              + f" · 力度：{i.get('力度', '标准')}")
        if i.get("任务") == "起草":
            print("【材料】\n" + i["原文"])
            print("【要求】\n" + i.get("要求", ""))
        else:
            print("【原文】\n" + i["原文"])
        if i.get("上下文"):
            print("【上下文】\n" + i["上下文"])
    return 0


# ---------------------------------------------------------------- 候选

def cmd_target(args):
    rd = run_dir(today_str(args))
    t = load_json(os.path.join(rd, "target.json"))
    if not t:
        print("今天没有目标病灶。")
        return 0
    print(f"目标病灶：{t['cluster']}（{t['name']}），开发组证据 {len(t['dev'])} 条：")
    for e in t["dev"]:
        print(f"- [{e['date']} {e['文体']}] 原文：{e.get('quote_src') or '（无）'} ｜ 改写：{e.get('quote_out') or '（无）'} ｜ 裁判：{e.get('note', '')}")
    notes = active_notes()
    if notes:
        print("\n作者说过的话（候选细则不许跟这些冲突）：")
        for n in notes:
            print(f"- {n['id']}（{'、'.join(n['文体']) if n.get('文体') else '所有文体'}）：{n['text']}")
    print(f"\n现用细则：{os.path.join(rd, 'overlays', 'current.md')}")
    print("写候选前读 references/fix-proposal.md。写好后：python3 scripts/loop.py stage 候选文件.md")
    return 0


def cmd_stage(args):
    cfg, st = load_config(), load_state()
    today = today_str(args)
    rd = run_dir(today)
    plan = load_json(os.path.join(rd, "plan.json"))
    items = load_json(os.path.join(rd, "items.json"), [])
    if plan.get("confirm_rc"):
        raise Stop("今天是复测日，不出新候选。")
    if args.aa:
        if st["mode"] != "shadow":
            raise Stop("A/A 自测只在影子期做。")
    elif not plan.get("target"):
        raise Stop("今天没有目标病灶，不出候选。")
    calib = load_json(os.path.join(rd, "calib", "result.json"))
    if not calib or not calib.get("pass"):
        raise Stop("裁判体检没过（或还没跑 calib-score），今天不出候选。")
    gate_items = needed("cand", items, plan)
    if not args.aa and not any(i["kind"] == "probe" for i in gate_items):
        raise Stop("还没加针对目标病灶的探针题（add-items，kind=probe）。")
    missing = [i["id"] for i in gate_items if not os.path.exists(os.path.join(rd, "outputs", "current", i["id"] + ".txt"))]
    if missing:
        raise Stop("这些题的现用版改写还没写，先写完再 stage（防止候选影响现用版）：" + "、".join(missing))
    text = read_text(args.file)
    current = read_text(os.path.join(rd, "overlays", "current.md"))
    if args.aa:
        text = current
    hold = [i["原文"] for i in items if i.get("group") == "target"]
    errs, changed = validate_candidate(text, cfg, current, hold, aa=args.aa)
    if errs:
        print("候选没通过格式检查：")
        for e in errs:
            print("- " + e)
        return 1
    _, body = rules_of(text)
    body = re.sub(r"^# 好好说话 · 每日细则\s*", "", body).strip()
    write_text(os.path.join(rd, "overlays", "cand.md"), with_header(body, "候选", today))
    save_json(os.path.join(rd, "candidate.json"), {"sha": sha(body), "changed": sorted(changed), "aa": bool(args.aa),
                                                   "cluster": (plan.get("target") or {}).get("cluster", "A/A"),
                                                   "note": read_text(args.note) if args.note else ""})
    print(f"候选已冻结：overlays/cand.md（改动细则：{'、'.join(sorted(changed)) or 'A/A 自测，无改动'}）。")
    print("下一步：python3 scripts/loop.py writer-view cand，逐条写 cand 版改写。")
    return 0


# ---------------------------------------------------------------- 检查、盲评、核对

def cmd_check(args):
    rd = run_dir(today_str(args))
    plan = load_json(os.path.join(rd, "plan.json"))
    items = load_json(os.path.join(rd, "items.json"), [])
    missing, total = [], 0
    vs = [v for v in VERSIONS if v in plan["versions"] or (v == "cand" and os.path.exists(os.path.join(rd, "overlays", "cand.md")))]
    for v in vs:
        for it in needed(v, items, plan):
            p = os.path.join(rd, "outputs", v, it["id"] + ".txt")
            if not os.path.exists(p):
                missing.append(f"{v}/{it['id']}")
                continue
            out = read_text(p)
            if not split_output(out)[0]:
                missing.append(f"{v}/{it['id']}（文件是空的）")
                continue
            save_json(os.path.join(rd, "checks", v, it["id"] + ".json"), mechanical_check(it, out))
            total += 1
    print(f"机械检查完成 {total} 份。")
    if missing:
        print("还缺这些改写：" + "、".join(missing))
        return 1
    return 0


def cmd_blind(args):
    rd = run_dir(today_str(args))
    if cmd_check(args) != 0:
        raise Stop("还有改写没写完，写完再生成盲评队列。")
    items = {i["id"]: i for i in load_json(os.path.join(rd, "items.json"), [])}
    keyp = os.path.join(rd, "private", "judge_key.json")
    key = load_json(keyp, {})
    queue = read_jsonl(os.path.join(rd, "judge", "queue.jsonl"))
    have = {(m[0], m[1]) for ms in key.values() for m in ms}
    by_body = {}
    for jid, ms in key.items():
        for iid, v, bsha in ms:
            by_body[(iid, bsha)] = jid
    fresh = []
    for v in versions_present(rd):
        for path in sorted(glob.glob(os.path.join(rd, "checks", v, "*.json"))):
            iid = os.path.basename(path)[:-5]
            if (iid, v) in have or iid not in items:
                continue
            chk = load_json(path)
            fresh.append((iid, v, chk))
    rng = random.Random(os.urandom(8))
    rng.shuffle(fresh)
    n = len(key)
    for iid, v, chk in fresh:
        bsha = sha(norm(chk["body"]) + "|" + norm(chk["notes"]))
        if (iid, bsha) in by_body:
            key[by_body[(iid, bsha)]].append([iid, v, bsha])
            continue
        n += 1
        jid = f"J{n:03d}"
        it = items[iid]
        key[jid] = [[iid, v, bsha]]
        by_body[(iid, bsha)] = jid
        queue.append({"jid": jid, "任务": it.get("任务", "改写"), "文体": it.get("文体", ""), "读者": it.get("读者", ""),
                      "力度": it.get("力度", "标准"), "原文": it["原文"], "上下文": it.get("上下文", ""),
                      "要求": it.get("要求", ""),
                      "事实": [{"id": f["id"], "内容": f.get("内容", "")} for f in it.get("事实", []) or []],
                      "改写": chk["body"], "给作者": chk["notes"], "旗标": chk["flags"], "提示": chk["hints"],
                      "判例": item_precedents(it), "作者说明": notes_for(it.get("文体", ""))})
    write_jsonl(os.path.join(rd, "judge", "queue.jsonl"), queue)
    save_json(keyp, key)
    print(f"盲评队列 {len(queue)} 份（新加 {len(fresh)} 份；同一题两个版本一字不差的只判一次）。")
    print(f"队列：{os.path.join(rd, 'judge', 'queue.jsonl')}；答案一行一个 JSON，写到 judge/answers.jsonl。")
    print("判之前不要打开 private/ 目录。判法见 references/judge-protocol.md。")
    return 0


def cmd_verify(args):
    rd = run_dir(today_str(args))
    queue = {q["jid"]: q for q in read_jsonl(os.path.join(rd, "judge", "queue.jsonl"))}
    key = load_json(os.path.join(rd, "private", "judge_key.json"), {})
    answers = {a["jid"]: a for a in read_answers(os.path.join(rd, "judge"))}
    bad, missing, mism, dropped_n = [], [], 0, 0
    results = {}
    for jid, q in queue.items():
        a = answers.get(jid)
        if not a:
            if args.partial:
                results[jid] = {"errors": [], "findings": [], "dropped": [], "verdict": "不确定", "claim": "没判",
                                "register": None, "dispute": None, "claim_mismatch": False, "unjudged": True}
            else:
                missing.append(jid)
            continue
        r = verify_answer(a, q)
        if r["errors"]:
            bad.append((jid, r["errors"]))
            continue
        mism += r["claim_mismatch"]
        dropped_n += len(r["dropped"])
        results[jid] = r
    if bad or missing:
        for jid, es in bad:
            print(f"{jid} 要重判：" + "；".join(es))
        if missing:
            print("还没判：" + "、".join(missing))
        print("改好 judge/answers.jsonl 里对应的行（同一个 jid 以最后一行为准），再跑一次 verify。")
        return 1
    for jid, r in results.items():
        for iid, v, _ in key.get(jid, []):
            findings = [dict(f, cluster=cluster_of(f["code"], f.get("label", ""))) for f in r["findings"]]
            save_json(os.path.join(rd, "judgments", v, iid + ".json"),
                      {"item_id": iid, "version": v, "jid": jid, "verdict": r["verdict"], "claim": r["claim"],
                       "register": r["register"], "findings": findings, "dropped": r["dropped"],
                       "dispute": r["dispute"], "unjudged": r.get("unjudged", False)})
    save_json(os.path.join(rd, "judge", "verify.json"), {"n": len(results), "dropped_findings": dropped_n,
                                                         "claim_mismatch": mism, "partial": bool(args.partial)})
    print(f"核对完成：{len(results)} 份有效；引用对不上被作废的问题 {dropped_n} 条；结论和问题清单对不上 {mism} 份（按问题清单算）。")
    return 0


def cmd_calib_score(args):
    cfg, st = load_config(), load_state()
    today = today_str(args)
    rd = run_dir(today)
    queue = {q["jid"]: q for q in read_jsonl(os.path.join(rd, "calib", "queue.jsonl"))}
    key = load_json(os.path.join(rd, "private", "calib_key.json"), {})
    answers = {a["jid"]: a for a in read_answers(os.path.join(rd, "calib"))}
    overrides = load_json(H("calib_overrides.json"), {})
    bad = []
    caught = bad_n = fa = good_n = unsure = soft_fa = 0
    detail, conflicts = [], []
    for jid, q in queue.items():
        a = answers.get(jid)
        if not a:
            bad.append((jid, ["还没判"]))
            continue
        r = verify_answer(a, q)
        if r["errors"]:
            bad.append((jid, r["errors"]))
            continue
        k = key[jid]
        cid = f"{k['case']}|{k['tool']}"
        f = overrides.get(cid, {}).get("f") or k["f"]
        is_bad = f in ("红", "橙")
        hit = r["verdict"] == "改坏了"
        unsure += r["verdict"] == "不确定"
        soft = False
        if is_bad:
            bad_n += 1
            caught += hit
        else:
            good_n += 1
            hard = hit and (f == "绿确认" or any(x["code"] in FAB for x in r["findings"]))
            soft = hit and not hard
            fa += hard
            soft_fa += soft
            if soft:
                harm = next(x for x in r["findings"] if x["code"] in HARM)
                conflicts.append({"calib_id": cid, "case": k["case"], "tool": k["tool"], "文体": q.get("文体", ""),
                                  "code": harm["code"], "src": harm.get("src", ""), "out": harm.get("out", ""),
                                  "note": harm.get("note", "")})
        detail.append({"jid": jid, "case": k["case"], "tool": k["tool"], "人工档": f, "裁判": r["verdict"],
                       "对上": hit == is_bad, "分歧": soft})
    if bad:
        for jid, es in bad:
            print(f"{jid}：" + "；".join(es))
        print("体检答案要全部判完且格式合格，改好 calib/answers.jsonl 再跑。")
        return 1
    catch = caught / bad_n if bad_n else 1.0
    far = fa / good_n if good_n else 0.0
    g = cfg["gates"]
    ok = catch >= g["calib_min_catch"] and far <= g["calib_max_false_alarm"]
    res = {"date": today, "catch": round(catch, 2), "false_alarm": round(far, 2), "caught": caught, "bad_n": bad_n,
           "fa": fa, "good_n": good_n, "soft_fa": soft_fa, "unsure": unsure, "pass": ok, "detail": detail,
           "conflicts": conflicts}
    save_json(os.path.join(rd, "calib", "result.json"), res)
    with Lock():
        st = load_state()
        st["calib_history"] = [h for h in st.get("calib_history", []) if h["date"] != today] + \
            [{"date": today, "catch": res["catch"], "false_alarm": res["false_alarm"], "pass": ok}]
        save_state(st)
    extra = f"（另有 {soft_fa} 条跟你当时的判断不一样，会问你一次）" if soft_fa else ""
    print(f"裁判体检：已知改坏的抓到 {caught}/{bad_n}，已知没改坏的误报 {fa}/{good_n}{extra}，拿不准 {unsure} 条 → "
          f"{'通过' if ok else '没过，今天先不出新规则'}")
    return 0


# ---------------------------------------------------------------- 决策

def cmd_decide(args):
    cfg = load_config()
    today = today_str(args)
    rd = run_dir(today)
    if os.path.exists(os.path.join(rd, "decision.json")) and not args.force:
        print(f"今天已经决策过：{load_json(os.path.join(rd, 'decision.json'))['headline']}")
        return 0
    with Lock():
        st = load_state()
        plan = load_json(os.path.join(rd, "plan.json"))
        items = load_json(os.path.join(rd, "items.json"), [])
        byid = {i["id"]: i for i in items}
        if not os.path.exists(os.path.join(rd, "judge", "verify.json")):
            raise Stop("还没 verify，不能决策。")
        # 手改种子勘误后，已作废/不可出题种子早先产生的召回不算数：按来源里的种子 id 自动驱逐。
        dead = dead_manual_seed_ids()
        def _seed_id_of(item_id, source):
            m = re.match(r"^\d{4}-\d{2}-\d{2}-m(\d+)$", item_id or "")
            if m:
                return f"M{int(m.group(1)):03d}"
            m = re.search(r"手工批改种子\s*(M\d+)", source or "")
            return m.group(1) if m else None
        kept_pool, evicted = [], []
        for e in pool_entries():
            sid = _seed_id_of(e.get("item_id", ""), json.dumps(e.get("item", {}), ensure_ascii=False))
            if sid in dead:
                evicted.append((e.get("date"), sid, e.get("cluster")))
            else:
                kept_pool.append(e)
        if evicted:
            write_jsonl(H("pool.jsonl"), kept_pool)
            log_author(today, "作废种子召回驱逐：" + "；".join(f"{d} {sid} {c}" for d, sid, c in evicted))
        man = load_json(os.path.join(rd, "manifest.json"))
        fp_now = fingerprints(cfg)
        drift = [k for k in ("shuohua_skill", "shuohua_refs", "eval_skill", "config") if man["fingerprints"].get(k) != fp_now.get(k)]
        J = load_judgments(rd)
        JCUR = J.get("current", {})
        calib = load_json(os.path.join(rd, "calib", "result.json")) or {"pass": False}
        dec = {"date": today, "mode": st["mode"], "actions": [], "notes": list(plan.get("notes", [])), "gates": {},
               "observations": []}
        if drift:
            dec["notes"].append("跑到一半，这些东西变了：" + "、".join(drift) + "。今天只记录，不发布。")
        # 1 召回入池
        pool_old = {(e["run"], e["item_id"], e["code"], e.get("quote_out", "")) for e in pool_entries()}
        new_pool = []
        for iid, j in JCUR.items():
            it = byid.get(iid)
            if not it or it.get("group") not in ("fresh", "regression", "clean"):
                continue
            for f in j.get("findings", []):
                k = (today, iid, f["code"], f.get("out", ""))
                if k in pool_old:
                    continue
                pool_old.add(k)
                if _seed_id_of(iid, it.get("来源", "")) in dead:
                    continue
                new_pool.append({"date": today, "run": today, "item_id": iid, "kind": it.get("kind"),
                                 "文体": it.get("文体", ""), "release": st["published"]["release"], "code": f["code"],
                                 "cluster": f["cluster"], "quote_src": f.get("src", ""), "quote_out": f.get("out", ""),
                                 "note": f.get("note", ""),
                                 "item": {k2: it.get(k2) for k2 in ("任务", "文体", "力度", "原文", "上下文", "事实", "要求")}})
        append_jsonl(H("pool.jsonl"), new_pool)
        dec["recalled"] = {}
        for e in new_pool:
            dec["recalled"][e["cluster"]] = dec["recalled"].get(e["cluster"], 0) + 1
        # 2 指标
        m = item_metrics(items, JCUR, load_checks(rd, "current"), cfg["gates"]["clean_edit_alarm"])
        m["calib"] = [calib.get("caught", 0), calib.get("bad_n", 0), calib.get("fa", 0), calib.get("good_n", 0)]
        m.update(date=today, release=st["published"]["release"], calib_pass=bool(calib.get("pass")))
        # 手改种子对照：作者亲手删/留的句子，我们当天改写跟上多少（只句级核对，不进门禁）
        seed_diffs = []
        for it in items:
            sid = it.get("manual_seed")
            if not sid or it["id"] not in JCUR:
                continue
            outp = os.path.join(rd, "outputs", "current", it["id"] + ".txt")
            if not os.path.exists(outp):
                continue
            body = split_output(read_text(outp))[0]
            d = seed_diff(sid, body)
            if d:
                seed_diffs.append(d)
        m["seed_diff"] = summarize_seed_diff(seed_diffs) if seed_diffs else None
        dec["seed_diffs"] = seed_diffs
        rows = [r for r in read_jsonl(H("metrics.jsonl")) if r["date"] != today] + [m]
        write_jsonl(H("metrics.jsonl"), rows)
        dec["metrics"] = m
        st.setdefault("seen", {})[today] = " ".join(sorted({item_key(i["原文"]) for i in items
                                                            if i.get("kind") in REQUIRED_FACT_KINDS | {"real"}}))
        st["idem"] = next_idem(items, JCUR, rd, today)
        # 3 争议
        disputes = read_jsonl(H("disputes.jsonl"))
        st["_next_d"] = max(next_dispute_id(disputes), next_dispute_id(read_jsonl(H("precedents.jsonl"))),
                            st.get("next_dispute", 1))
        created = []
        for v, JV in J.items():
            for iid, j in JV.items():
                it = byid.get(iid)
                if not it:
                    continue
                if j.get("dispute") and (v == "current" or it.get("group") in ("target", "regression", "clean", "fresh")):
                    d = j["dispute"]
                    created.append(new_dispute(st, d["类型"], it, v, d["原文片段"], d["改写片段"], d["原因"],
                                               d.get("疑似编码", ""), today, "发布判断" if v != "current" else "召回"))
                if v == "current":
                    for f in j.get("findings", []):
                        if f["code"] == "R" and f.get("cluster") == "R·新":
                            created.append(new_dispute(st, "新问题", it, v, f.get("src", ""), f.get("out", ""),
                                                       f.get("note", ""), "R", today, "召回"))
        if dt.date.fromisoformat(today).isoweekday() == cfg["disputes"]["audit_weekday"] and \
                not any(d["kind"] == "抽查" and days_between(d["created"], today) < 6 for d in disputes):
            ok_items = [iid for iid, j in JCUR.items() if j["verdict"] == "合格" and byid.get(iid, {}).get("group") == "fresh"
                        and cjk_len(byid[iid]["原文"]) <= 260]
            random.Random("audit" + today).shuffle(ok_items)
            for iid in ok_items[:cfg["disputes"]["audit_count"]]:
                body = split_output(read_text(os.path.join(rd, "outputs", "current", iid + ".txt")))[0]
                created.append(new_dispute(st, "抽查", byid[iid], "current", byid[iid]["原文"], body, "每周随机抽查", "", today, "抽查"))
        asked = {d.get("calib_id") for d in disputes if d["kind"] == "体检"}
        comments = {(p["来源"], p["工具"]): (p.get("评语") or p.get("总评") or "") for p in pkg("precedents.json", [])}
        overall = {str(c["id"]): re.split(r"<br/>|\n", c.get("意见", ""))[0].strip() for c in pkg("cases50.json", [])}
        answered_calib = [d for d in disputes
                          if d.get("kind") == "体检" and d.get("status") == "answered"
                          and d.get("answer") in ("有", "没有")]
        for c in calib.get("conflicts", []):
            said = comments.get((f"cases50#{c['case']}", c["tool"]), "") or overall.get(str(c["case"]), "")
            said = said if len(said) <= 60 else said[:60] + "……"
            reason = (f"你当时对这版的评语：「{said}」" if said else "你当时没挑这版的毛病") + \
                f"；裁判认为{CODES.get(c['code'], c['code'])}：{c.get('note', '')}"
            d = new_dispute(st, "体检", {"id": f"cases50#{c['case']}·{c['tool']}", "文体": c["文体"]}, "calib",
                            c["src"], c["out"], reason, c["code"], today, "体检")
            d["calib_id"] = c["calib_id"]
            # 作者已在同一材料/同一句的别的体检题上亲口答过：照办，更新人工档，不再开新题
            hit = match_calib_answer(d, answered_calib, cfg["disputes"]["auto_match_similarity"])
            if hit:
                h = hit[0]
                d.update(status="auto", answer=h["answer"], answered=today,
                         note=f"与 {h['id']} 重复，自动去重（{hit[1]}）")
                log_author(today, f"体检软分歧 {c['calib_id']} 照 {h['id']} 记成「{h['answer']}」（自动去重）")
                dec["notes"].append(f"今天有个体检分歧（{c['calib_id']}）跟你答过的 {h['id']} 是同一处，"
                                    f"已自动按「{h['answer']}」处理，没再问你。")
                # 落盘成 auto 题：人工档照此更新（下面统一 apply），override 能追溯到这条
                created.append(d)
                continue
            if c["calib_id"] in asked:
                continue
            asked.add(c["calib_id"])
            created.append(d)
        seen_d = {(d["created"], d["item_id"], d["version"], d["kind"], d["原文片段"]) for d in disputes}
        uniq = []
        for d in created:
            k = (d["created"], d["item_id"], d["version"], d["kind"], d["原文片段"])
            if k not in seen_d:
                seen_d.add(k)
                uniq.append(auto_match(d, cfg))
        created = uniq
        disputes += created
        write_jsonl(H("disputes.jsonl"), disputes)
        for d in created:
            if d["status"] == "auto":
                apply_answer(d, st, today, to_precedent=False)
        # 4 门禁
        blocked = drift or not calib.get("pass")
        headline = None
        chk_cur = load_checks(rd, "current")
        cand_meta = load_json(os.path.join(rd, "candidate.json"))
        if plan.get("confirm_rc") and st.get("rc"):
            rc = st["rc"]
            if blocked:
                rc["retries"] = rc.get("retries", 0) + 1
                if rc["retries"] >= 2:
                    dec["actions"].append(f"预发布 {rc['id']} 连续两天没法复测，撤回")
                    set_cooldown(st, rc["cluster"], today, cfg)
                    st["rc"] = None
                    headline = "预发布撤回（连续两天没法复测）"
                else:
                    headline = "裁判体检没过，预发布顺延一天复测" if not calib.get("pass") else "运行中途有文件变化，预发布顺延"
            else:
                grp = [i for i in items if i.get("group") in ("fresh", "regression", "clean")]
                g1 = gate_compare("current", "rc", grp, JCUR, J.get("rc", {}), cfg,
                                  checks={"base": chk_cur, "cand": load_checks(rd, "rc")})
                tgt = rc["cluster"]
                fb = sum(1 for i in grp if any(f.get("cluster") == tgt for f in JCUR.get(i["id"], {}).get("findings", [])))
                fc = sum(1 for i in grp if any(f.get("cluster") == tgt for f in J.get("rc", {}).get(i["id"], {}).get("findings", [])))
                g1["stats"]["目标病灶在新题上"] = [fb, fc]
                if fc > fb:
                    g1["pass"] = False
                    g1["reasons"].append(f"目标病灶在新题上反而变多：{fb} → {fc}")
                dec["gates"]["复测"] = g1
                dec["observations"] += g1["stats"].get("observations", [])
                if "anchor" in plan["versions"]:
                    reg = [i for i in items if i.get("group") == "regression"]
                    g2 = gate_compare("anchor", "rc", reg, J.get("anchor", {}), J.get("rc", {}), cfg)
                    dec["gates"]["对锚点"] = g2
                    dec["observations"] += g2["stats"].get("observations", [])
                    if not g2["pass"]:
                        g1["pass"] = False
                        g1["reasons"] += ["对锚点：" + r for r in g2["reasons"]]
                if g1["pass"]:
                    if rc.get("shadow") or st["mode"] != "auto":
                        headline = f"影子：复测通过，本来会发布（{tgt}）"
                        st["rc"] = None
                    else:
                        rid = promote(st, rc, today, cfg, items, J)
                        headline = f"已发布 {rid}（{tgt}）"
                        dec["actions"].append(headline)
                else:
                    headline = "复测没过，预发布撤回：" + "；".join(g1["reasons"][:2])
                    set_cooldown(st, tgt, today, cfg)
                    st["rc"] = None
        elif cand_meta:
            grp = needed("cand", items, plan)
            tgt = None if cand_meta.get("aa") else cand_meta["cluster"]
            g = gate_compare("current", "cand", grp, JCUR, J.get("cand", {}), cfg, target=tgt,
                             checks={"base": chk_cur, "cand": load_checks(rd, "cand")})
            dec["gates"]["候选"] = g
            dec["observations"] += g["stats"].get("observations", [])
            if cand_meta.get("aa"):
                headline = "A/A 自测：" + ("两份一样的细则没被判出差别" if not [r for r in g["reasons"] if not r.startswith("目标")] else "同一份细则跑两遍被判出差别：" + "；".join(g["reasons"][:2]))
                dec["aa"] = g["stats"]
            elif blocked:
                headline = "候选作废（运行中途有文件变化）"
            elif g["pass"]:
                rcid = f"rc{st['next_rc']:04d}"
                st["next_rc"] += 1
                body = rules_of(read_text(os.path.join(rd, "overlays", "cand.md")))[1]
                body = re.sub(r"^# 好好说话 · 每日细则\s*", "", body).strip()
                write_text(H("releases", rcid, "daily-learning.md"), body)
                save_json(H("releases", rcid, "meta.json"), {"id": rcid, "date": today, "cluster": tgt, "gate": g,
                                                             "changed": cand_meta.get("changed", []), "note": cand_meta.get("note", "")})
                hold = [i for i in items if i.get("group") == "target"]
                st["rc"] = {"id": rcid, "date": today, "cluster": tgt, "shadow": st["mode"] != "auto",
                            "holdout": [i["id"] for i in hold], "run": today,
                            "holdout_items": [{k: i.get(k) for k in ("id",) + SNAP_KEYS} for i in hold[:3]]}
                headline = ("影子：" if st["mode"] != "auto" else "") + f"预发布 {rcid}（{tgt}），明天用新题复测"
                dec["actions"].append(headline)
            else:
                headline = f"候选被拒（{tgt}）：" + "；".join(g["reasons"][:2])
                set_cooldown(st, tgt, today, cfg)
        if headline is None:
            if not calib.get("pass"):
                headline = "今天正常召回了，但裁判体检没过，先不出新规则"
            elif plan.get("manual_edit"):
                headline = "你改过规则，我原样保留了；今天照常召回，等你确认后再继续出新规则"
            elif plan.get("target"):
                headline = f"有够数的病灶（{plan['target']['cluster']}），但今天没出候选"
            else:
                headline = "今天没有够数的病灶，先攒着，没出新规则"
        # 5 监控回滚
        rb = monitor(st, cfg, today)
        if rb:
            dec["actions"].append(rb)
            headline = rb + "；" + headline
        dec["headline"] = headline
        dec["calib"] = {k: calib.get(k) for k in ("caught", "bad_n", "fa", "good_n", "pass")}
        st["next_dispute"] = st.pop("_next_d")
        st["last"] = {"date": today, "headline": headline}
        save_json(os.path.join(rd, "decision.json"), dec)
        compact(cfg, st, today)
        save_state(st)
    print(headline)
    for a in dec["actions"]:
        print("动作：" + a)
    return 0


# ---------------------------------------------------------------- 争议

def cmd_disputes(args):
    cfg = load_config()
    today = today_str(args)
    if args.action == "list":
        ds = read_jsonl(H("disputes.jsonl"))
        show = [d for d in ds if d["status"] == "open"] if not args.all else ds
        for d in show:
            print(render_dispute(d) + (f"\n  状态：{d['status']} {d.get('answer') or ''} {d.get('note') or ''}" if args.all else ""))
        if not show:
            print("没有待判断的题。")
        return 0
    if args.action == "answer":
        ans = ANSWER_WORDS.get(args.answer or "")
        if not ans:
            raise Stop("回答只认：有 / 没有 / 跳过（也认 是 / 否）")
        with Lock():
            st = load_state()
            ds = read_jsonl(H("disputes.jsonl"))
            d = next((x for x in ds if x["id"].upper() == (args.id or "").upper()), None)
            if not d:
                raise Stop(f"找不到 {args.id}")
            if d["status"] not in ("open", "defaulted", "auto"):
                print(f"{d['id']} 已经回答过（{d['answer']}），这次覆盖。")
            msg = answer_dispute(cfg, st, ds, d, ans, args.note, today)
            save_state(st)
        print(f"{d['id']} 记下了：{ans}" + (f"（{args.note}）" if args.note else ""))
        if msg:
            print(msg)
        return 0
    return 0


# ---------------------------------------------------------------- 报告

def cmd_report(args):
    cfg, st = load_config(), load_state()
    today = today_str(args)
    rd = run_dir(today)
    dec = load_json(os.path.join(rd, "decision.json"))
    if not dec:
        raise Stop("今天还没 decide。")
    rows = read_jsonl(H("metrics.jsonl"))
    past = [r for r in rows if 0 < days_between(r["date"], today) <= 7]

    def rate(k, rs, base="n"):
        n = sum(r[base] for r in rs)
        return (sum(r[k] for r in rs), n)
    m = dec["metrics"]

    def fmt(k, base="n"):
        a, n = m[k], m[base]
        pa, pn = rate(k, past, base)
        avg = f"7 天 {pa}/{pn}" if pn else "7 天无数据"
        return f"{a}/{n}（{avg}）"
    lines = [f"好好说话 · 每日召回 {today} · {mode_label(cfg, st, today)}",
             f"结论：{dec['headline']}",
             f"实际改写 {m.get('output_n', '历史未统计')} 份；纳入主指标 {m['n']} 份（不含探针、留出题与干净对照）",
             f"改坏 {fmt('harm')}，其中编造 {m['fab']} · 残留 {fmt('residue')} · 干净稿误改 {fmt('over_edit', 'clean_n')}"]
    sd = m.get("seed_diff")
    if sd:
        def _r(k):
            r = sd[k]
            return f"{r['hit']}/{r['n']}" if r["n"] else "无对照句"

        def _p(k):
            r = sd[k]
            return f"{r['rate']:.0%}" if r["rate"] is not None else "—"
        lines.append(f"手改稿对照（作者亲手改过的 {sd['n']} 条种子）：作者删的我们也删了 {_r('delete')}"
                     f"（{_p('delete')}）；作者原样留的我们没动 {sd['keep']['n'] - sd['keep']['hit']}/{sd['keep']['n']}"
                     f"，越动率 {_p('keep')}"
                     + (f"；作者替换的新片段字面命中 {_r('edit')}（{_p('edit')}）" if sd["edit"]["n"] else ""))
    c = dec.get("calib") or {}
    if c.get("bad_n") is not None:
        lines.append(f"裁判体检：已知改坏的抓到 {c.get('caught')}/{c.get('bad_n')}，已知没改坏的误报 {c.get('fa')}/{c.get('good_n')}"
                     + ("" if c.get("pass") else "，没过"))
    rec = dec.get("recalled") or {}
    if rec:
        top = sorted(rec.items(), key=lambda x: -x[1])[:4]
        lines.append("今天新召回：" + "，".join(f"{k}（{CODES.get(k.split('·')[0], k)}）×{n}" for k, n in top))
    if dt.date.fromisoformat(today).isoweekday() == cfg["disputes"]["audit_weekday"]:
        wk = [r for r in st.get("releases", []) if 0 <= days_between(r["date"], today) < 7]
        stuck = [k for k, v in st.get("cooldown", {}).items() if v.get("status") == "stuck"]
        lines.append(f"本周：发布 {sum(1 for r in wk if r['type'] == '发布')} 次，回滚 {sum(1 for r in wk if r['type'] == '回滚')} 次"
                     + (f"；招不回、待研究：{'、'.join(stuck)}" if stuck else ""))
    heard = [r["text"] for r in read_jsonl(H("inbox.jsonl")) if r.get("date") == today]
    if heard:
        lines.append("今天记下你的回话：" + "；".join(t if len(t) <= 60 else t[:60] + "……" for t in heard))
    ds = sorted([d for d in read_jsonl(H("disputes.jsonl")) if d["status"] == "open"], key=dispute_order)
    show = ds[:cfg["disputes"]["max_per_day"]]
    if show:
        lines.append(f"待你判断 {len(ds)} 条（先看这 {len(show)} 条，不回也行，{cfg['disputes']['default_after_days']} 天后按保守默认处理）：")
        lines += [render_dispute(d) for d in show]
    else:
        lines.append("今天没有要你判断的。")
    for n in dec.get("notes", []):
        lines.append("注意：" + n)
    for o in dec.get("observations", []):
        lines.append("观察项：" + o)
    lines.append(f"运行目录：{rd}")
    text = "\n".join(lines)
    write_text(os.path.join(rd, "report.md"), text + "\n")
    print(text)
    return 0


# ---------------------------------------------------------------- 作者指令

def cmd_mode(args):
    with Lock():
        st = load_state()
        if args.mode == "auto":
            st["mode"], st["paused_reason"] = "auto", None
            if st.get("rc"):
                st["rc"]["shadow"] = False
        elif args.mode == "shadow":
            st["mode"] = "shadow"
            st["shadow_start"] = today_str(args)
        else:
            st["mode"], st["paused_reason"] = "paused", args.reason or "作者手动暂停"
        save_state(st)
        log_author(today_str(args), f"模式切到 {st['mode']}")
    print(f"模式已切到：{st['mode']}")
    return 0


def cmd_anchor(args):
    with Lock():
        st = load_state()
        st["anchor"] = st["published"]["release"]
        save_state(st)
        log_author(today_str(args), f"锚点设为 {st['anchor']}")
    print(f"锚点设为 {st['anchor']}：以后每次发布都要在回归题上不比它差。")
    return 0


def cmd_rollback(args):
    cfg = load_config()
    today = today_str(args)
    with Lock():
        st = load_state()
        cur = st["published"]["release"]
        to = args.to
        if not to:
            rels = [r for r in st.get("releases", []) if r["id"] == cur and r["type"] == "发布"]
            to = rels[-1]["prev"] if rels else None
        if not to or not os.path.exists(H("releases", to, "daily-learning.md")):
            raise Stop("没有可以回滚到的版本。")
        if args.force:
            st["published"]["sha"] = file_sha(published_path())
        publish_text(st, release_text(to), to, today)
        cl = next((r["cluster"] for r in reversed(st.get("releases", [])) if r["id"] == cur), "")
        st.setdefault("releases", []).append({"id": to, "date": today, "cluster": cl, "prev": cur, "type": "回滚"})
        unfix(st, to)
        if cl and cl != "手工":
            set_cooldown(st, cl, today, cfg, days=14)
        save_state(st)
        log_author(today, f"回滚 {cur} → {to}")
    print(f"已回滚：{cur} → {to}")
    return 0


def cmd_accept_manual(args):
    today = today_str(args)
    with Lock():
        st = load_state()
        path = published_path()
        text = read_text(path)
        rid = f"v{st['next_release']:04d}"
        st["next_release"] += 1
        body = re.sub(r"^# 好好说话 · 每日细则\s*", "", rules_of(text)[1]).strip()
        write_text(H("releases", rid, "daily-learning.md"), body)
        save_json(H("releases", rid, "meta.json"), {"id": rid, "date": today, "source": "作者手工修改"})
        prev = st["published"]["release"]
        st["published"] = {"release": rid, "sha": file_sha(path), "date": today}
        st.setdefault("releases", []).append({"id": rid, "date": today, "cluster": "手工", "prev": prev, "type": "手工"})
        st["anchor"] = rid
        save_state(st)
        log_author(today, f"手工修改记成 {rid}")
    print(f"手工修改已记成 {rid}，并设为锚点。明天起恢复正常。")
    return 0


def cmd_import_clean(args):
    rows = load_json(args.file)
    have = load_json(H("clean.json"), [])
    seen = {norm(x["原文"]) for x in have}
    n0 = len(have)
    for r in rows:
        t = (r.get("原文") or r.get("text") or "").strip()
        if cjk_len(t) < 20 or norm(t) in seen:
            continue
        seen.add(norm(t))
        have.append({"id": f"clean-u{len(have) + 1:03d}", "kind": "clean", "group": "clean", "任务": "改写",
                     "文体": r.get("文体", "随笔"), "力度": "标准", "原文": t, "上下文": "", "来源": r.get("来源", "作者导入")})
    save_json(H("clean.json"), have)
    print(f"干净对照新增 {len(have) - n0} 条，共 {len(have)} 条（另有技能自带 {len(pkg('clean_seed.json'))} 条）。")
    return 0


def cmd_export(args):
    st = load_state()
    today = today_str(args)
    text = release_text(st["published"]["release"])
    rels = [r for r in st.get("releases", []) if r["type"] == "发布"]
    lines = [f"# 每日细则合并提案 {today}", "",
             f"现用版本 {st['published']['release']}，累计发布 {len(rels)} 次。下面这些细则已经过门禁，"
             "稳定了可以并进 haohao-shuohua 的 references（不要动底线条款），并进之后把 daily-learning.md 清空并记成新锚点。", "",
             "## 现用细则", "", text or "（没有）", "", "## 发布记录", ""]
    for r in st.get("releases", []):
        lines.append(f"- {r['date']} {r['type']} {r['id']}（{r['cluster']}，上一版 {r['prev']}）")
    out = H("exports", f"{today}-merge.md")
    write_text(out, "\n".join(lines) + "\n")
    print(f"写出 {out}")
    return 0


def cmd_note(args):
    today = today_str(args)
    if args.action == "list":
        rows = active_notes()
        for n in rows:
            print(f"{n['id']}（{n['date']}，{'、'.join(n['文体']) if n.get('文体') else '所有文体'}）：{n['text']}")
        if not rows:
            print("还没有记下的作者说明。")
        return 0
    if not (args.text or "").strip():
        raise Stop("add 后面跟作者原话，drop 后面跟编号（比如 N003）。")
    load_state()
    with Lock():
        st = load_state()
        rows = read_jsonl(H("notes.jsonl"))
        if args.action == "add":
            n, msg = add_note(st, rows, args.text.strip(), split_tags(args.genre or ""), today, "对话")
        else:
            n = next((x for x in rows if x["id"].upper() == args.text.strip().upper()), None)
            if not n:
                raise Stop(f"找不到 {args.text}")
            msg = drop_note(n, today)
            if n.get("来源") == "文档":
                n["doc_hold"] = True
                msg += f"（这条写在召回文档「{NOTES_TITLE}」里：那一行留着也不会再记上，删掉以后再写才算新的一条）"
        write_jsonl(H("notes.jsonl"), rows)
        save_state(st)
        log_author(today, msg)
    print(msg)
    return 0


# ---------------------------------------------------------------- 状态文档

def cmd_state(args):
    today = today_str(args)
    if args.action == "dump":
        out = os.path.abspath(args.out or H("exports", "state-doc.xml"))
        if args.empty:
            write_text(out, state_doc_xml(state_header([], 0, today, empty=True), [],
                                          ["还没有跑过：第一次运行时从头初始化，收尾时把状态写到这里。"], None))
            print(f"空的状态文档内容：{out}")
            return 0
        cfg = load_config()
        with Lock():
            st = load_state()
            compact(cfg, st, today)
            st["state_seq"] = st.get("state_seq", 0) + 1
            st["state_saved"] = today
            save_state(st)
            body = state_body()
        header = state_header(body, st["state_seq"], today)
        write_text(out, state_doc_xml(header, body, state_summary(cfg, st, today), release_text(st["published"]["release"])))
        print(f"状态文档内容：{out}")
        print(f"第 {header['seq']} 份 · {len(body)} 行 · {sum(len(x) for x in body)} 字 · 校验 {header['sha256'][:12]}")
        print(f"下一步：{lark_cmd()} docs +update --doc <状态文档> --command overwrite --content - < {out}"
              "（整篇覆盖），再把状态文档读回来跑 state check。")
        return 0
    header, body = state_from_doc(doc_content(args.file))
    if args.action == "check":
        st = load_state()
        if header.get("empty") or header["seq"] != st.get("state_seq"):
            raise Stop(f"状态文档里是第 {header.get('seq')} 份，本地是第 {st.get('state_seq')} 份：没写进去，或者写到别的文档了。")
        if hashlib.sha256("\n".join(state_body()).encode("utf-8")).hexdigest() != header["sha256"]:
            raise Stop("状态文档跟本地数据对不上：写完以后本地又变了，或者写进去的不是这一份。重新 state dump 再写一次。")
        print(f"状态文档核对无误：第 {header['seq']} 份，{header['lines']} 行。")
        return 0
    lock = H("loop.lock")
    if os.path.exists(lock) and dt.datetime.now().timestamp() - os.path.getmtime(lock) < 6 * 3600:
        raise Stop(f"另一个流程正在跑（{lock}），先别恢复。")
    local = load_json(H("state.json"))
    if header.get("empty"):
        print("状态文档是空的（还没存过）：" + ("本地已有数据，以本地为准。" if local else "这是第一次运行，接着跑 loop.py init。"))
        return 0
    if local is not None and not args.force:
        ls = local.get("state_seq", 0)
        if ls > header["seq"]:
            print(f"本地比状态文档新（本地第 {ls} 份，文档里第 {header['seq']} 份），以本地为准；收尾时照常把状态写回文档。")
            return 0
        if ls == header["seq"]:
            print(f"本地就是第 {ls} 份，跟状态文档一样，不用恢复。")
            return 0
    files = unflatten(body)
    if "state.json" not in files:
        raise Stop("状态文档里没有 state.json，不恢复。")
    moved = install_state(files)
    print(f"已恢复第 {header['seq']} 份状态（{header['date']} 存进状态文档的），{len(files)} 个文件，校验通过。")
    for p in moved:
        print(f"原来的挪到了 {p}")
    return 0


# ---------------------------------------------------------------- 召回文档

def cmd_doc(args):
    cfg, today = load_config(), today_str(args)
    if args.action == "read":
        sec, status = recall_section(doc_lines(doc_content(args.file)))
        apply = not args.dry_run
        load_state()
        with Lock():
            st = load_state()
            msgs = []
            if status == "missing":
                msgs.append(f"召回文档里还没有「{SECTION_TITLE}」这一节：今天的记录会连这一节的开头一起写。")
            else:
                if status == "not_last":
                    msgs.append(f"「{SECTION_TITLE}」后面还有别的一级标题：今天的记录不往文档里追加，只发在对话里。")
                msgs += sync_doc_notes(st, section_notes(sec), today, apply)
                msgs += apply_doc_answers(cfg, st, sec, today, apply)
            has_today = any(lv == 2 and s.startswith(f"{today} ·") for lv, s in sec)
            if has_today:
                msgs.append(f"召回文档里已经有 {today} 的记录了：今天不再追加。")
            if apply:
                st["recall_doc"] = {"read": today, "section": status, "today": has_today}
                save_state(st)
        print("\n".join(msgs) if msgs else "召回文档里没有新的判断和交代。")
        return 0
    with Lock():
        st = load_state()
        rdoc = st.get("recall_doc") or {}
        if rdoc.get("read") != today:
            raise Stop(f"今天还没读召回文档：先 doc read，确认「{SECTION_TITLE}」这一节在不在，再生成记录。")
        if rdoc.get("section") == "not_last":
            raise Stop(f"召回文档里「{SECTION_TITLE}」后面还有别的一级标题，不往后追加。今天的记录只发在对话里，"
                       "并请作者把那部分挪到这一节前面。")
        if rdoc.get("today") and not args.again:
            raise Stop(f"召回文档里已经有 {today} 的记录了，不再追加。确实要再写一条，加 --again。")
        if st.get("recorded") == today and not args.again:
            raise Stop("今天的记录已经生成过。确认没写进召回文档，再加 --again 重新生成。")
        dec = load_json(os.path.join(run_dir(today), "decision.json"))
        if not dec and not args.stopped:
            raise Stop("今天还没 decide。流程中途停下的话，用 --stopped \"原因\" 写一条停下的记录。")
        x = (section_head(cfg) if rdoc.get("section") == "missing" else []) + record_body(cfg, st, today, dec, args.stopped)
        st["recorded"] = today
        save_state(st)
    out = os.path.abspath(args.out or H("exports", f"record-{today}.xml"))
    write_text(out, "\n".join(x) + "\n")
    print(f"今天的记录：{out}")
    print(f"下一步：{lark_cmd()} docs +update --doc <召回文档> --command append --content - < {out}"
          f"（追加到末尾），再用 --scope keyword --keyword {today} 读一下，确认写进去了。")
    return 0


def cmd_version(args):
    print(f"haohao-eval 第 {VERSION} 版：跨天的状态存在飞书文档里（state dump / load / check），"
          "每天的记录追加进召回文档（doc read / record）。")
    return 0


__all__ = [
    "cmd_init", "cmd_status", "cmd_start", "cmd_add_items", "cmd_writer_view", "cmd_target", "cmd_stage",
    "cmd_check", "cmd_blind", "cmd_verify", "cmd_calib_score", "cmd_decide", "cmd_disputes", "cmd_report",
    "cmd_mode", "cmd_anchor", "cmd_rollback", "cmd_accept_manual", "cmd_import_clean", "cmd_export",
    "cmd_note", "cmd_state", "cmd_doc", "cmd_version",
]
