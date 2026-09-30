#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""loop.py 的端到端测试：临时目录里模拟十来天，裁判和改写都是假的，只测流程和门禁算得对不对。

跑法：python3 scripts/test_loop.py
"""
import datetime as dt
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_labels  # noqa: E402
import build_seed  # noqa: E402
import loop  # noqa: E402

D0 = dt.date(2026, 10, 5)  # 周一


def day(n):
    return (D0 + dt.timedelta(days=n)).isoformat()


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = loop.main(list(argv))
    return code, out.getvalue() + err.getvalue()


def synth(n, date, salt=0):
    """合成题：每条都含「显著提升」，现用版会把它改成「顺了一些」（C1）。"""
    topics = ["支付链路", "搜索召回", "日志平台", "消息推送", "订单中心", "风控模型", "报表系统", "客服工单",
              "权限系统", "配置中心", "数据看板", "推荐排序", "账单对账", "埋点平台", "告警系统", "发布平台"]
    out = []
    for i in range(n):
        tp = topics[(i + int(date[-2:]) * 3 + salt) % len(topics)]
        out.append({"kind": "synthetic", "文体": "周报", "读者": "组内", "场合": "技术议论",
                    "原文": f"{date}/{salt} 这周我们对{tp}做了全面的梳理，并进行了针对性的优化，{tp}的稳定性得到了显著提升，预计下周完成收尾，编号 {date}-{i}。",
                    "事实": [{"id": "F1", "内容": f"梳理并优化了{tp}", "关键词": [tp]},
                             {"id": "F2", "内容": "稳定性显著提升", "关键词": ["显著提升"]},
                             {"id": "F3", "内容": "预计下周完成收尾", "关键词": ["预计", "下周"]}]})
    return out


def dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def glob_any(pattern):
    import glob
    return bool(glob.glob(pattern))


def current_output(src):
    return src.replace("显著提升", "顺了一些").replace("并进行了针对性的优化", "对症做了优化")


def cand_output(src):
    return src.replace("并进行了针对性的优化", "对症做了优化")


class Env:
    def __init__(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_DATA_HOME"] = os.path.join(self.tmp, "xdg")
        os.environ["HAOHAO_EVAL_HOME"] = os.path.join(self.tmp, "eval")

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rd(self, date):
        return loop.run_dir(date)


def fake_judge(q, truth):
    """按植入的问题出答案：C1 = 「显著提升」被改成「顺了一些」；A1 = 改写里多了「37%」。"""
    src, out = q["原文"], q["改写"]
    probs = []
    if "显著提升" in src and "顺了一些" in out:
        probs.append({"编码": "C1", "原文引用": "显著提升", "改写引用": "顺了一些", "说明": "程度降了"})
    if "37%" in out and "37%" not in src:
        probs.append({"编码": "A1", "改写引用": "37%", "说明": "原文没有这个数"})
    if truth == "H" and loop.norm(src) != loop.norm(out):
        probs.append({"编码": "H", "原文引用": src[:6], "改写引用": out[:6], "说明": "原文没毛病却改了"})
    ledger = []
    for f in q.get("事实", []):
        ledger.append({"事实": f["id"], "结果": "变了", "编码": "C1", "原文引用": "显著提升", "改写引用": "顺了一些"}
                      if f["id"] == "F2" and "顺了一些" in out else {"事实": f["id"], "结果": "保留"})
    flags = []
    for k in q.get("旗标", []):
        con = "确认" if (k["类型"] == "新数字" and "37%" in out) or (k["类型"] == "事实关键词缺失" and "顺了一些" in out) else "排除"
        flags.append({"旗标": k["kid"], "结论": con, "理由": "测试"})
    codes = {p["编码"] for p in probs} | {e.get("编码") for e in ledger if e.get("结果") != "保留"}
    verdict = "改坏了" if codes & loop.HARM else ("没改好" if codes else "合格")
    return {"jid": q["jid"], "场合": "技术议论", "对账": ledger, "问题": probs, "旗标": flags, "结论": verdict}


def judge_calib(env, date, miss=False):
    rd = env.rd(date)
    key = loop.load_json(os.path.join(rd, "private", "calib_key.json"))
    rows = []
    for q in loop.read_jsonl(os.path.join(rd, "calib", "queue.jsonl")):
        k = key[q["jid"]]
        flags = [{"旗标": f["kid"], "结论": "排除", "理由": "测试"} for f in q["旗标"]]
        if k["f"] in ("红", "橙") and not miss:
            sent = re.split(r"[。！？]", q["改写"])[0][:8] or q["改写"][:8]
            rows.append({"jid": q["jid"], "场合": "技术议论", "问题": [{"编码": "D", "改写引用": sent, "说明": "测试"}],
                         "旗标": flags, "结论": "改坏了"})
        else:
            rows.append({"jid": q["jid"], "场合": "技术议论", "问题": [], "旗标": flags, "结论": "合格"})
    loop.write_jsonl(os.path.join(rd, "calib", "answers.jsonl"), rows)


def write_outputs(env, date, version, fn):
    rd = env.rd(date)
    items = loop.load_json(os.path.join(rd, "items.json"))
    plan = loop.load_json(os.path.join(rd, "plan.json"))
    for it in loop.needed(version, items, plan):
        p = os.path.join(rd, "outputs", version, it["id"] + ".txt")
        loop.write_text(p, fn(it))


def judge_all(env, date):
    rd = env.rd(date)
    key = loop.load_json(os.path.join(rd, "private", "judge_key.json"))
    items = {i["id"]: i for i in loop.load_json(os.path.join(rd, "items.json"))}
    rows = []
    for q in loop.read_jsonl(os.path.join(rd, "judge", "queue.jsonl")):
        iid, v, _ = key[q["jid"]][0]
        truth = "H" if items[iid]["group"] == "clean" else ""
        rows.append(fake_judge(q, truth))
    loop.write_jsonl(os.path.join(rd, "judge", "answers.jsonl"), rows)


def one_day(env, date, cand_rules=None, cur_fn=None, cand_fn=None, rc_fn=None, probes=0):
    code, out = run("--date", date, "start")
    assert code == 0, out
    judge_calib(env, date)
    code, out = run("--date", date, "calib-score")
    assert code == 0 and "通过" in out, out
    f = os.path.join(env.tmp, f"items-{date}.json")
    items = synth(3, date)
    plan = loop.load_json(os.path.join(env.rd(date), "plan.json"))
    if probes and plan.get("target"):
        for p in synth(probes, date, salt=7):
            p.update(kind="probe", cluster=plan["target"]["cluster"], 陷阱="程度词")
            items.append(p)
    dump(f, items)
    code, out = run("--date", date, "add-items", f)
    assert code == 0, out
    cur_fn = cur_fn or (lambda it: current_output(it["原文"]))
    write_outputs(env, date, "current", cur_fn)
    if cand_rules and plan.get("target"):
        rp = os.path.join(env.tmp, f"cand-{date}.md")
        loop.write_text(rp, cand_rules)
        code, out = run("--date", date, "stage", rp)
        assert code == 0, out
        write_outputs(env, date, "cand", cand_fn or (lambda it: cand_output(it["原文"])))
    if "rc" in plan["versions"]:
        write_outputs(env, date, "rc", rc_fn or (lambda it: cand_output(it["原文"])))
    if "anchor" in plan["versions"]:
        write_outputs(env, date, "anchor", cur_fn)
    code, out = run("--date", date, "blind")
    assert code == 0, out
    judge_all(env, date)
    code, out = run("--date", date, "verify")
    assert code == 0, out
    code, out = run("--date", date, "decide")
    assert code == 0, out
    code, rep = run("--date", date, "report")
    assert code == 0, rep
    return loop.load_json(os.path.join(env.rd(date), "decision.json")), rep


RULE = """## 细则 L001 · 程度词别降格
- 适用：原文用了「显著」「全面」这类带分量的程度词。
- 做法：保留原词或换成分量相同的说法，拿不准就用原词。
- 例：「稳定性得到了显著提升」不能改成「顺了一些」。
"""


class LoopTest(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        code, out = run("--date", day(0), "init")
        self.assertEqual(code, 0, out)

    def tearDown(self):
        self.env.close()

    def test_build_clean_supports_current_and_legacy_examples(self):
        root = os.path.join(self.env.tmp, "shuohua")
        refs = os.path.join(root, "references")
        os.makedirs(refs)
        with open(os.path.join(refs, "before-after-worktext.md"), "w", encoding="utf-8") as f:
            f.write(
                "# 对照\n\n"
                "## 当前格式\n\n原文：原句。\n\n改稿：改句。\n\n"
                "## 保留格式\n\n原文：本来就好。\n\n处理：保留。\n\n"
                "## 旧格式\n\n**❌** 旧原句。\n\n**✅** 旧改句。\n"
            )
        rows = build_seed.build_clean(root)
        self.assertEqual([r["原文"] for r in rows], ["改句。", "本来就好。", "旧改句。"])

    def test_build_labels_is_portable_and_complete(self):
        labels = build_labels.build_labels()
        self.assertEqual(len(labels), 50)
        self.assertEqual(labels["1"]["我们"]["f"], "黄")

    def test_external_badcase_source_is_disabled_by_default(self):
        self.assertEqual(
            loop.load_config()["sources"],
            {"badcase_base": "", "badcase_table": "", "read_new_badcases": False},
        )

    def test_full_cycle(self):
        env = self.env
        # 前两天攒病灶：影子期，没有够数的病灶
        for n in range(2):
            dec, rep = one_day(env, day(n))
            self.assertIn("没有够数的病灶", dec["headline"])
            self.assertIn("C1", rep)
        rows, _ = loop.eligible_clusters(loop.load_config(), loop.load_state(), day(2))
        c1 = next(r for r in rows if r["cluster"] == "C1")
        self.assertTrue(c1["eligible"], rows)
        dec, _ = one_day(env, day(2))
        self.assertIn("有够数的病灶", dec["headline"])
        # 第四天：目标 C1，影子预发布
        dec, rep = one_day(env, day(3), cand_rules=RULE, probes=6)
        self.assertIn("影子：预发布", dec["headline"], json.dumps(dec, ensure_ascii=False)[:2000])
        st = loop.load_state()
        self.assertTrue(st["rc"]["shadow"])
        # 第五天：复测（影子），不发布
        dec, rep = one_day(env, day(4))
        self.assertIn("本来会发布", dec["headline"], json.dumps(dec, ensure_ascii=False)[:1500])
        self.assertFalse(os.path.exists(loop.published_path()))
        # 切自动，再来一轮：预发布 → 复测 → 真发布
        run("--date", day(5), "mode", "auto")
        dec, _ = one_day(env, day(5), cand_rules=RULE, probes=6)
        self.assertIn("预发布 rc", dec["headline"])
        self.assertNotIn("影子", dec["headline"])
        dec, rep = one_day(env, day(6))
        self.assertIn("已发布 v0001", dec["headline"], json.dumps(dec, ensure_ascii=False)[:1500])
        pub = loop.read_text(loop.published_path())
        self.assertIn("L001", pub)
        self.assertIn("v0001", pub)
        st = loop.load_state()
        self.assertEqual(st["published"]["release"], "v0001")
        self.assertEqual(st["cluster_fixed_at"]["C1"], "v0001")
        self.assertTrue(loop.load_json(loop.H("regression_extra.json")))
        # 手工改动：拒绝覆盖，当天不出候选
        with open(loop.published_path(), "a", encoding="utf-8") as f:
            f.write("\n## 细则 L099 · 手工\n- 适用：测试\n- 做法：测试\n")
        code, out = run("--date", day(7), "start")
        self.assertIn("手工改过", out)
        code, out = run("--date", day(7), "rollback")
        self.assertEqual(code, 2)
        self.assertIn("手工改过", out)
        code, out = run("--date", day(7), "accept-manual")
        self.assertEqual(code, 0, out)
        st = loop.load_state()
        self.assertEqual(st["published"]["release"], "v0002")
        self.assertEqual(st["anchor"], "v0002")
        self.assertIn("C1", loop.load_state()["cluster_fixed_at"])
        code, out = run("--date", day(7), "rollback", "--to", "v0000")
        self.assertEqual(code, 0, out)
        self.assertNotIn("L001", loop.read_text(loop.published_path()))
        self.assertNotIn("C1", loop.load_state()["cluster_fixed_at"])

    def test_candidate_rejected_on_new_fabrication(self):
        env = self.env
        for n in range(2):
            one_day(env, day(n))
        run("--date", day(3), "mode", "auto")
        dec, _ = one_day(env, day(3), cand_rules=RULE, probes=6,
                         cand_fn=lambda it: cand_output(it["原文"]) + "故障率降了 37%。")
        self.assertIn("候选被拒", dec["headline"])
        self.assertIn("新编", json.dumps(dec["gates"], ensure_ascii=False))
        st = loop.load_state()
        self.assertIsNone(st["rc"])
        self.assertTrue(st["cooldown"]["C1"]["until"] > day(3))

    def test_verify_rejects_bad_quotes_and_missing_flags(self):
        q = {"jid": "J001", "原文": "这周稳定性得到了显著提升。", "上下文": "", "改写": "这周稳定性顺了一些，故障率降了 37%。",
             "事实": [{"id": "F1", "内容": "稳定性显著提升"}],
             "旗标": [{"kid": "K1", "类型": "新数字", "内容": "37.0"}]}
        bad = {"jid": "J001", "场合": "技术议论", "对账": [{"事实": "F1", "结果": "保留"}],
               "问题": [{"编码": "A1", "改写引用": "降了一半", "说明": "x"}], "结论": "改坏了"}
        r = loop.verify_answer(bad, q)
        self.assertTrue(any("旗标" in e for e in r["errors"]))
        self.assertEqual(len(r["dropped"]), 1)
        good = {"jid": "J001", "场合": "技术议论", "对账": [{"事实": "F1", "结果": "变了", "编码": "C1", "原文引用": "显著提升", "改写引用": "顺了一些"}],
                "问题": [{"编码": "A1", "改写引用": "故障率降了 37%", "说明": "原文没有"}],
                "旗标": [{"旗标": "K1", "结论": "确认", "理由": "原文没有数字"}], "结论": "改坏了"}
        r = loop.verify_answer(good, q)
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["verdict"], "改坏了")
        fake = dict(good, 问题=[{"编码": "A1", "改写引用": "稳定性", "说明": "原文里就有"}])
        r = loop.verify_answer(fake, q)
        self.assertEqual(r["dropped"][0]["作废原因"], "这段在原文里就有，不算新加的")
        unsure = dict(good, 结论="不确定", 不确定原因="拿不准")
        r = loop.verify_answer(unsure, q)
        self.assertTrue(any("争议片段" in e for e in r["errors"]))

    def test_candidate_validation(self):
        cfg = loop.load_config()
        errs, _ = loop.validate_candidate(RULE.replace("拿不准就用原词", "可以适当补充具体数字"), cfg, "", [])
        self.assertTrue(any("禁用" in e for e in errs), errs)
        errs, _ = loop.validate_candidate(RULE, cfg, RULE, [])
        self.assertTrue(any("一样" in e for e in errs), errs)
        many = "".join(RULE.replace("L001", f"L00{i}") for i in range(1, 5))
        errs, _ = loop.validate_candidate(many, cfg, "", [])
        self.assertTrue(any("一次改了" in e for e in errs), errs)
        errs, _ = loop.validate_candidate(RULE, cfg, "", ["原文用了「显著」「全面」这类带分量的程度词。其余"])
        self.assertTrue(any("留作验证" in e for e in errs), errs)
        errs, _ = loop.validate_candidate("随便写点\n" + RULE, cfg, "", [])
        self.assertTrue(any("细则之外" in e for e in errs), errs)
        errs, _ = loop.validate_candidate(RULE, cfg, "", [])
        self.assertEqual(errs, [])

    def test_disputes_default_and_answer(self):
        env = self.env
        date = day(0)
        run("--date", date, "start")
        judge_calib(env, date)
        run("--date", date, "calib-score")
        f = os.path.join(env.tmp, "i.json")
        dump(f, synth(2, date))
        run("--date", date, "add-items", f)
        write_outputs(env, date, "current", lambda it: current_output(it["原文"]))
        run("--date", date, "blind")
        judge_all(env, date)
        rd = env.rd(date)
        rows = loop.read_jsonl(os.path.join(rd, "judge", "answers.jsonl"))
        q0 = loop.read_jsonl(os.path.join(rd, "judge", "queue.jsonl"))[0]
        rows[0].update(结论="不确定", 不确定原因="「顺了一些」算不算降格拿不准",
                       争议片段={"问题类型": "保真", "原文引用": q0["原文"][:10], "改写引用": q0["改写"][:10], "疑似编码": "C1"})
        loop.write_jsonl(os.path.join(rd, "judge", "answers.jsonl"), rows)
        code, out = run("--date", date, "verify")
        self.assertEqual(code, 0, out)
        run("--date", date, "decide")
        code, rep = run("--date", date, "report")
        self.assertIn("D1", rep)
        self.assertIn("回复「D1 有」", rep)
        code, out = run("--date", date, "disputes", "answer", "D1", "没有", "--note", "顺了一些可以接受")
        self.assertEqual(code, 0, out)
        prec = loop.read_jsonl(loop.H("precedents.jsonl"))
        self.assertEqual(prec[0]["answer"], "没有")
        ds = loop.read_jsonl(loop.H("disputes.jsonl"))
        ds.append(dict(ds[0], id="D2", status="open", answer=None, created=date))
        loop.write_jsonl(loop.H("disputes.jsonl"), ds)
        code, out = run("--date", day(3), "start")
        self.assertIn("保守默认", out)
        d2 = next(d for d in loop.read_jsonl(loop.H("disputes.jsonl")) if d["id"] == "D2")
        self.assertEqual((d2["status"], d2["answer"]), ("defaulted", "有"))

    def test_auto_match_and_forbidden(self):
        run("--date", day(0), "start")
        cfg = loop.load_config()
        loop.write_jsonl(loop.H("precedents.jsonl"), [{"id": "D1", "kind": "保真", "原文片段": "业内普遍认为连接池配置不当是主要诱因",
                                                       "改写片段": "根源是连接池配置不当", "answer": "有"}])
        d = {"kind": "保真", "原文片段": "业内普遍认为连接池配置不当是主要诱因", "改写片段": "根源就是连接池配置不当",
             "created": day(1), "status": "open"}
        self.assertEqual(loop.auto_match(dict(d), cfg)["status"], "auto")
        self.assertEqual(loop.auto_match(dict(d, kind="抽查"), cfg)["status"], "open")
        self.assertEqual(loop.auto_match(dict(d, 改写片段="完全不同的一句话，跟原来没关系"), cfg)["status"], "open")
        for s in ("不要忽略敬语", "别为了人味加口头禅", "不允许补数字"):
            self.assertEqual(loop.forbidden_hit(s), "", s)
        for s in ("可以适当补充细节", "允许补上原因", "要更像人"):
            self.assertTrue(loop.forbidden_hit(s), s)

    def test_calib_conflict_becomes_dispute(self):
        env = self.env
        date = day(0)
        run("--date", date, "start")
        judge_calib(env, date)
        rd = env.rd(date)
        key = loop.load_json(os.path.join(rd, "private", "calib_key.json"))
        rows = loop.read_jsonl(os.path.join(rd, "calib", "answers.jsonl"))
        queue = {q["jid"]: q for q in loop.read_jsonl(os.path.join(rd, "calib", "queue.jsonl"))}
        green = [r for r in rows if key[r["jid"]]["f"] == "绿"][:2]
        for r in green:
            q = queue[r["jid"]]
            r.update(结论="改坏了", 问题=[{"编码": "B", "原文引用": q["原文"][:8], "说明": "测试：说丢了"}])
        loop.write_jsonl(os.path.join(rd, "calib", "answers.jsonl"), rows)
        code, out = run("--date", date, "calib-score")
        self.assertIn("误报 0/4", out)
        self.assertIn("另有 2 条", out)
        self.assertIn("通过", out)
        f = os.path.join(env.tmp, "i.json")
        dump(f, synth(2, date))
        run("--date", date, "add-items", f)
        write_outputs(env, date, "current", lambda it: current_output(it["原文"]))
        run("--date", date, "blind")
        judge_all(env, date)
        run("--date", date, "verify")
        run("--date", date, "decide")
        ds = [d for d in loop.read_jsonl(loop.H("disputes.jsonl")) if d["kind"] == "体检"]
        self.assertEqual(len(ds), 2)
        self.assertIn("改写里没有对应的话", loop.render_dispute(ds[0]))
        for d in ds:
            code, out = run("--date", date, "disputes", "answer", d["id"], "没有")
            self.assertEqual(code, 0, out)
        ov = loop.load_json(loop.H("calib_overrides.json"))
        self.assertEqual({v["f"] for v in ov.values()}, {"绿确认"})
        code, out = run("--date", date, "calib-score")
        self.assertIn("误报 2/4", out)
        self.assertIn("没过", out)
        run("--date", date, "decide", "--force")
        self.assertEqual(len([d for d in loop.read_jsonl(loop.H("disputes.jsonl")) if d["kind"] == "体检"]), 2)

    def test_notes_reach_judges_and_report(self):
        env = self.env
        code, out = run("--date", day(0), "note", "add", "感谢信里的客套别删", "--文体", "感谢信、寄语")
        self.assertEqual(code, 0, out)
        self.assertIn("N001", out)
        code, out = run("--date", day(0), "note", "add", "计算机专业名词一律用原词")
        self.assertIn("所有文体都适用", out)
        dec, rep = one_day(env, day(0))
        rd = env.rd(day(0))
        for q in loop.read_jsonl(os.path.join(rd, "judge", "queue.jsonl")) + \
                loop.read_jsonl(os.path.join(rd, "calib", "queue.jsonl")):
            want = {"N002"} | ({"N001"} if ("感谢信" in q["文体"] or "寄语" in q["文体"]) else set())
            self.assertEqual({n["id"] for n in q["作者说明"]}, want, q["文体"])
        self.assertIn("今天记下你的回话：N001", rep)
        code, out = run("--date", day(1), "note", "drop", "n002")
        self.assertEqual(code, 0, out)
        code, out = run("--date", day(1), "note", "list")
        self.assertIn("N001", out)
        self.assertNotIn("N002", out)
        dec, rep = one_day(env, day(1))
        self.assertIn("N002 作废了", rep)
        self.assertNotIn("N001 记下了", rep)

    def test_real_item_carries_author_review(self):
        env = self.env
        date = day(0)
        run("--date", date, "start")
        judge_calib(env, date)
        run("--date", date, "calib-score")
        src = "这么一来，前面那个挑刺打补丁的循环也散了，裁判从能不能挑出毛病换成结果对不对，这循环才算有了底。"
        review = {"旧改写": "这个循环才算有了底。", "评价": "循环什么叫底？一个圆圈有底吗？这个意象不对。"}
        wrong = dict(synth(1, date)[0], 作者评价=review)
        f = os.path.join(env.tmp, "r.json")
        dump(f, [{"kind": "real", "文体": "技术随笔", "原文": src, "来源": "BadCase 表 rec123", "作者评价": review}, wrong])
        code, out = run("--date", date, "add-items", f)
        self.assertEqual(code, 1, out)
        self.assertIn("收下 1 条", out)
        self.assertIn("作者评价只给真实材料", out)
        write_outputs(env, date, "current", lambda it: it["原文"].replace("散了", "断了"))
        code, out = run("--date", date, "blind")
        self.assertEqual(code, 0, out)
        q = next(q for q in loop.read_jsonl(os.path.join(env.rd(date), "judge", "queue.jsonl")) if q["原文"] == src)
        self.assertEqual(q["判例"][0]["作者原话"], review["评价"])
        self.assertIn("rec123", q["判例"][0]["来源"])

    def test_pack_unpack_roundtrip(self):
        env = self.env
        code, out = run("pack", "--empty", "--out", os.path.join(env.tmp, "p0"))
        self.assertEqual(code, 0, out)
        p0 = re.search(r"空数据包：(\S+)", out).group(1)
        code, out = run("unpack", p0)
        self.assertEqual(code, 0, out)
        self.assertIn("以本地为准", out)
        one_day(env, day(0))
        loop.write_text(loop.published_path(), "# 好好说话 · 每日细则\n")
        code, out = run("--date", day(0), "pack", "--out", os.path.join(env.tmp, "p1"))
        self.assertEqual(code, 0, out)
        p1 = re.search(r"数据包：(\S+)", out).group(1)
        self.assertTrue(p1.endswith(loop.PACK_NAME), p1)
        self.assertIn("第 1 份", out)
        code, out = run("unpack", p1)
        self.assertIn("不用恢复", out)
        state_before = loop.read_text(loop.H("state.json"))
        shutil.rmtree(loop.eval_home())
        os.remove(loop.published_path())
        code, out = run("unpack", p1)
        self.assertEqual(code, 0, out)
        self.assertIn("已恢复第 1 份", out)
        self.assertEqual(loop.read_text(loop.H("state.json")), state_before)
        self.assertEqual(loop.read_text(loop.published_path()), "# 好好说话 · 每日细则\n")
        self.assertTrue(os.path.exists(os.path.join(env.rd(day(0)), "decision.json")))
        code, out = run("--date", day(20), "pack", "--out", os.path.join(env.tmp, "p2"))
        p2 = re.search(r"数据包：(\S+)", out).group(1)
        import tarfile
        with tarfile.open(p2) as tf:
            names = tf.getnames()
        self.assertFalse(any(n.startswith("eval/runs/" + day(0)) for n in names), names)
        self.assertIn("eval/state.json", names)
        code, out = run("unpack", p1)
        self.assertEqual(code, 2)
        self.assertIn("本地数据比数据包新", out)
        code, out = run("unpack", p1, "--force")
        self.assertEqual(code, 0, out)
        self.assertEqual(loop.load_state()["pack_seq"], 1)
        self.assertTrue(glob_any(loop.eval_home() + ".bak-*"))
        bad = os.path.join(env.tmp, "bad.tgz")
        with tarfile.open(bad, "w:gz") as tf:
            data = b"{}"
            info = tarfile.TarInfo("eval/../../escape.json")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        code, out = run("unpack", bad)
        self.assertEqual(code, 2)
        self.assertIn("不该有的东西", out)
        self.assertFalse(os.path.exists(os.path.join(env.tmp, "escape.json")))
        shutil.rmtree(loop.eval_home())
        code, out = run("unpack", p0)
        self.assertEqual(code, 0, out)
        self.assertIn("第一次运行", out)
        self.assertFalse(os.path.exists(loop.H("state.json")))

    def test_sign_and_quotes(self):
        self.assertAlmostEqual(loop.sign_p(5, 0), 1 / 32)
        self.assertAlmostEqual(loop.sign_p(6, 1), 8 / 128)
        self.assertTrue(loop.quote_in("交付能力……显著提升", "这周交付能力得到了显著提升。"))
        self.assertFalse(loop.quote_in("显著提升……交付能力", "这周交付能力得到了显著提升。"))
        self.assertTrue(loop.quote_in("“重构”", "把清洗逻辑「重构」了一遍"))
        chk = loop.mechanical_check({"原文": "预计明天上线，采用重构方案。", "任务": "改写"}, "明天上线，采用重写方案，QPS 5000。")
        kinds = {f["类型"] for f in chk["flags"]}
        self.assertTrue({"模态变化", "术语替换", "新英文词", "新数字"} <= kinds, kinds)


if __name__ == "__main__":
    unittest.main(verbosity=2)
