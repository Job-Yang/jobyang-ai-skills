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


def as_fetched(xml):
    """照飞书读回来的样子改一遍：代码块里的换行变成 <br/>、引号转义、块和块之间不换行。"""
    def code(m):
        return m.group(1) + m.group(2).replace("\n", "<br/>").replace('"', "&quot;") + m.group(3)
    return re.sub(r"(<code>)(.*?)(</code>)", code, xml, flags=re.S).replace("\n<", "<")


def fetched_file(env, name, content):
    path = os.path.join(env.tmp, name)
    dump(path, {"ok": True, "identity": "user", "data": {"document": {"content": content}}})
    return path


def data_snapshot():
    """数据目录（不含运行目录）和发布出去的细则，按文件读成内容，用来比恢复前后是不是一样。"""
    out = {}
    for rel in loop.state_files():
        path = os.path.join(loop.eval_home(), *rel.split("/"))
        out[rel] = loop.read_jsonl(path) if rel.endswith(".jsonl") else (
            loop.load_json(path) if rel.endswith(".json") else loop.read_text(path))
    out["@published"] = loop.read_text(loop.published_path(), None)
    return out


def through_doc(env, date):
    """模拟 Mira：收尾把状态写进状态文档，本地数据整个没了，下一轮只能从文档恢复。"""
    path = os.path.join(env.tmp, f"state-{date}.xml")
    code, out = run("--date", date, "state", "dump", "--out", path)
    assert code == 0, out
    fetched = fetched_file(env, f"fetched-{date}.json", as_fetched(loop.read_text(path)))
    code, out = run("state", "check", fetched)
    assert code == 0 and "核对无误" in out, out
    before = data_snapshot()
    shutil.rmtree(loop.eval_home())
    if os.path.exists(loop.published_path()):
        os.remove(loop.published_path())
    code, out = run("state", "load", fetched)
    assert code == 0 and "已恢复" in out, out
    assert data_snapshot() == before
    return fetched


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

    def test_full_cycle(self):
        self.full_cycle(via_doc=False)

    def test_full_cycle_through_state_doc(self):
        """每天收尾都把本地数据清空、只从状态文档恢复，整轮照样走得通。"""
        self.full_cycle(via_doc=True)

    def full_cycle(self, via_doc):
        env = self.env

        def next_day(n):
            if via_doc:
                through_doc(env, day(n))
        # 前两天攒病灶：影子期，没有够数的病灶
        for n in range(2):
            dec, rep = one_day(env, day(n))
            self.assertIn("没有够数的病灶", dec["headline"])
            self.assertIn("C1", rep)
            if n == 1:
                items = loop.load_json(os.path.join(env.rd(day(1)), "items.json"))
                self.assertTrue(any(i["kind"] == "clean-idem" for i in items), "上一轮合格的改写没拿来再洗一遍")
            next_day(n)
        rows, _ = loop.eligible_clusters(loop.load_config(), loop.load_state(), day(2))
        c1 = next(r for r in rows if r["cluster"] == "C1")
        self.assertTrue(c1["eligible"], rows)
        dec, _ = one_day(env, day(2))
        self.assertIn("有够数的病灶", dec["headline"])
        next_day(2)
        # 第四天：目标 C1，影子预发布
        dec, rep = one_day(env, day(3), cand_rules=RULE, probes=6)
        self.assertIn("影子：预发布", dec["headline"], json.dumps(dec, ensure_ascii=False)[:2000])
        st = loop.load_state()
        self.assertTrue(st["rc"]["shadow"])
        next_day(3)
        # 第五天：复测（影子），不发布
        dec, rep = one_day(env, day(4))
        self.assertIn("本来会发布", dec["headline"], json.dumps(dec, ensure_ascii=False)[:1500])
        self.assertFalse(os.path.exists(loop.published_path()))
        next_day(4)
        # 切自动，再来一轮：预发布 → 复测 → 真发布
        run("--date", day(5), "mode", "auto")
        dec, _ = one_day(env, day(5), cand_rules=RULE, probes=6)
        self.assertIn("预发布 rc", dec["headline"])
        self.assertNotIn("影子", dec["headline"])
        next_day(5)
        dec, rep = one_day(env, day(6))
        self.assertIn("已发布 v0001", dec["headline"], json.dumps(dec, ensure_ascii=False)[:1500])
        pub = loop.read_text(loop.published_path())
        self.assertIn("L001", pub)
        self.assertIn("v0001", pub)
        st = loop.load_state()
        self.assertEqual(st["published"]["release"], "v0001")
        self.assertEqual(st["cluster_fixed_at"]["C1"], "v0001")
        self.assertTrue(loop.load_json(loop.H("regression_extra.json")))
        run("--date", day(6), "doc", "read", fetched_file(env, "doc6.json", "<h1>每日迭代日志</h1><h2>你的交代</h2>"))
        rp = os.path.join(env.tmp, "rec6.xml")
        code, out = run("--date", day(6), "doc", "record", "--out", rp)
        self.assertEqual(code, 0, out)
        self.assertIn("正式发布 v0001（C1）", loop.read_text(rp))
        self.assertIn("<blockquote><p><b>细则 L001 · 程度词别降格</b></p><ul><li>适用：", loop.read_text(rp))
        next_day(6)
        if via_doc:
            xml = loop.read_text(os.path.join(env.tmp, f"state-{day(6)}.xml"))
            self.assertIn("<h2>现用细则</h2><h3>细则 L001 · 程度词别降格</h3><ul><li>适用：", xml.replace("\n", ""))
            self.assertNotIn("&lt;!--", xml)
        # 手工改动：拒绝覆盖，当天不出候选
        with open(loop.published_path(), "a", encoding="utf-8") as f:
            f.write("\n## 细则 L099 · 手工\n- 适用：测试\n- 做法：测试\n")
        code, out = run("--date", day(7), "start")
        self.assertIn("不盖掉你的改动", out)
        code, out = run("--date", day(7), "rollback")
        self.assertEqual(code, 2)
        self.assertIn("不盖掉你的改动", out)
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

    def test_calib_dedup_same_question(self):
        """体检去重：同一材料/同一句作者已亲口答过，开着的重复题 start 时自动照办，新冲突 decide 时不再开新题。"""
        env = self.env
        # 1) 开着的重复体检题在 start 时自动处理
        date0, date1 = day(0), day(1)
        run("--date", date0, "start")
        loop.write_jsonl(loop.H("disputes.jsonl"), [
            {"id": "D100", "created": date0, "kind": "体检", "item_id": "cases50#24·工具1", "version": "calib",
             "calib_id": "24|工具1", "文体": "离职告别", "原文片段": "愿各位前程似锦", "改写片段": "",
             "原因": "", "疑似编码": "G", "question": "q", "default": "跳过", "affects": "体检",
             "status": "answered", "answer": "有", "answered": date0, "note": "功能件不要改"},
            {"id": "D101", "created": date0, "kind": "体检", "item_id": "cases50#24·我们", "version": "calib",
             "calib_id": "24|我们", "文体": "离职告别", "原文片段": "愿各位前程似锦", "改写片段": "",
             "原因": "", "疑似编码": "G", "question": "q", "default": "跳过", "affects": "体检",
             "status": "open", "answer": None, "answered": None, "note": ""},
        ])
        code, out = run("--date", date1, "start")
        self.assertEqual(code, 0, out)
        d101 = next(d for d in loop.read_jsonl(loop.H("disputes.jsonl")) if d["id"] == "D101")
        self.assertEqual((d101["status"], d101["answer"]), ("auto", "有"))
        self.assertIn("D100", d101["note"])
        # 自动去重只更新人工档，不新增判例
        self.assertFalse(any(p.get("id") == "D101" for p in loop.read_jsonl(loop.H("precedents.jsonl"))))
        ov = loop.load_json(loop.H("calib_overrides.json"))
        self.assertEqual(ov["24|我们"]["f"], "橙")

        # 2) decide 时新冒出来的软分歧，同 case 别的工具上答过：不再开新题，直接照办
        run("--date", date1, "start", "--force")
        judge_calib(env, date1)
        rd = env.rd(date1)
        key = loop.load_json(os.path.join(rd, "private", "calib_key.json"))
        rows = loop.read_jsonl(os.path.join(rd, "calib", "answers.jsonl"))
        queue = {q["jid"]: q for q in loop.read_jsonl(os.path.join(rd, "calib", "queue.jsonl"))}
        green = [r for r in rows if key[r["jid"]]["f"] == "绿"][:1]
        self.assertTrue(green)
        for r in green:
            q = queue[r["jid"]]
            cid_case, cid_tool = key[r["jid"]]["case"], key[r["jid"]]["tool"]
            other = next(t for t in ("工具2", "工具1", "我们") if t != cid_tool)
            # 作者在同 case 的另一工具上已答「有」（同一句），应走同材料+片段包含匹配
            loop.write_jsonl(loop.H("disputes.jsonl"), [
                {"id": "D110", "created": date0, "kind": "体检", "item_id": f"cases50#{cid_case}·{other}",
                 "version": "calib", "calib_id": f"{cid_case}|{other}", "文体": q["文体"],
                 "原文片段": q["原文"][:8], "改写片段": "", "原因": "", "疑似编码": "G", "question": "q",
                 "default": "跳过", "affects": "体检", "status": "answered", "answer": "有",
                 "answered": date0, "note": ""}])
            r.update(结论="改坏了", 问题=[{"编码": "G", "原文引用": q["原文"][:8], "说明": "测试"}])
        loop.write_jsonl(os.path.join(rd, "calib", "answers.jsonl"), rows)
        code, out = run("--date", date1, "calib-score")
        self.assertEqual(code, 0, out)
        f = os.path.join(env.tmp, "i.json")
        dump(f, synth(2, date1))
        run("--date", date1, "add-items", f)
        write_outputs(env, date1, "current", lambda it: current_output(it["原文"]))
        run("--date", date1, "blind")
        judge_all(env, date1)
        run("--date", date1, "verify")
        code, out = run("--date", date1, "decide")
        self.assertEqual(code, 0, out)
        ds = [d for d in loop.read_jsonl(loop.H("disputes.jsonl")) if d["kind"] == "体检" and d["status"] == "open"]
        self.assertEqual(ds, [])
        auto = [d for d in loop.read_jsonl(loop.H("disputes.jsonl")) if d["id"] not in ("D110",) and d["kind"] == "体检"]
        self.assertTrue(any(d["status"] == "auto" and d["answer"] == "有" for d in auto))
        cid_tool = key[green[0]["jid"]]["tool"]
        self.assertEqual(loop.load_json(loop.H("calib_overrides.json"))[f"{cid_case}|{cid_tool}"]["f"], "橙")

    def test_manual_seed_diff_metrics(self):
        """手改稿对照：decide 指标里按种子给跟删/越动/跟改；句级口径直接核 M016/M018。"""
        from hh_eval.manualdiff import author_intent, seed_diff, summarize
        # M018：作者整段删除
        i18 = author_intent(loop.seed_index()["M018"])
        self.assertTrue(i18["kept"] == [] and len(i18["deleted"]) >= 2)
        d18 = seed_diff("M018", "")
        self.assertEqual(d18["跟删"], 1.0)
        self.assertIsNone(d18["越动"])
        d18b = seed_diff("M018", loop.seed_index()["M018"]["洗稿原句"])
        self.assertEqual(d18b["跟删"], 0.0)
        # M016：作者删了「出处交代一句」，其余原样留
        i16 = author_intent(loop.seed_index()["M016"])
        self.assertTrue(any("出处交代" in s for s in i16["deleted"]))
        self.assertTrue(any("孙宇晨2016" in s.replace(" ", "") for s in i16["kept"]))
        d16 = seed_diff("M016", loop.seed_index()["M016"]["改成"])
        self.assertEqual(d16["越动"], 0.0)

        # 端到端：手改种子题的对照进当天 metrics（不进门禁）
        env = self.env
        date = day(0)
        run("--date", date, "start", "--manual-seeds", "3")
        judge_calib(env, date)
        run("--date", date, "calib-score")
        rd = env.rd(date)
        plan = loop.load_json(os.path.join(rd, "plan.json"))
        items = loop.load_json(os.path.join(rd, "items.json"))
        write_outputs(env, date, "current", lambda it: current_output(it["原文"]))
        run("--date", date, "blind")
        judge_all(env, date)
        run("--date", date, "verify")
        code, out = run("--date", date, "decide")
        self.assertEqual(code, 0, out)
        code, rep = run("--date", date, "report")
        self.assertEqual(code, 0, rep)
        dec = loop.load_json(os.path.join(rd, "decision.json"))
        sids = {i["manual_seed"] for i in items if i.get("manual_seed")}
        self.assertEqual({d["seed"] for d in dec["seed_diffs"]}, sids)
        self.assertEqual(dec["metrics"]["seed_diff"]["n"], 3)
        rep = loop.read_text(os.path.join(rd, "report.md"))
        self.assertIn("手改稿对照", rep)

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

    def test_manual_seeds_enter_fresh_items_blind(self):
        """手改种子：start --manual-seeds 放进 fresh 合成题，作者动作/规则信号不进题；按天轮转、跨天换批。"""
        env = self.env
        code, out = run("--date", day(0), "start", "--manual-seeds", "3")
        self.assertEqual(code, 0, out)
        self.assertIn("作者手改种子题 3 条", out)
        rd0 = env.rd(day(0))
        items0 = [i for i in loop.load_json(os.path.join(rd0, "items.json")) if i.get("manual_seed")]
        self.assertEqual(len(items0), 3)
        usable = {s["id"] for s in loop.manual_seed_pool()}
        for i in items0:
            self.assertEqual(i["kind"], "synthetic")
            self.assertEqual(i["group"], "fresh")
            self.assertIn(i["manual_seed"], usable)
            self.assertEqual(i["事实"], [])
            for leaked in ("作者动作", "rule_signal", "作者理由", "改成", "反例风险"):
                self.assertNotIn(leaked, i)
        # 作废的旧种子（含 M009）都不进池
        self.assertFalse({i["manual_seed"] for i in items0} & {"M001","M007","M009","M013"})
        # 可出题=false 的作者回源/取舍种子不进池
        self.assertFalse({i["manual_seed"] for i in items0} & {"M024","M026","M030"})
        for i in items0:
            self.assertNotIn("……", i["原文"])  # 残句拼接不作题
        # 带上文的种子：题面有上文就一定来自库里标了上文的条目，且不泄露批注
        from hh_eval.seed import manual_seed_pool as _msp
        ctx_ids = {x["id"] for x in _msp() if x.get("上下文")}
        self.assertTrue(ctx_ids)
        for i in items0:
            self.assertEqual(bool(i["上下文"]), i["manual_seed"] in ctx_ids)
            self.assertNotIn("rule_signal", i["上下文"])
            self.assertNotIn("作者动作", i["上下文"])
        # 第二天再开，轮转结果允许换批（至少不能跟第一天完全同序同批）
        run("--date", day(1), "start", "--force", "--manual-seeds", "3")
        items1 = [i for i in loop.load_json(os.path.join(env.rd(day(1)), "items.json")) if i.get("manual_seed")]
        self.assertEqual(len(items1), 3)
        self.assertEqual({i["manual_seed"] for i in items1} <= usable, True)
        self.assertEqual(sum(1 for a, b in zip(items0, items1) if a["manual_seed"] == b["manual_seed"]) < 3, True)
        # 不开开关时一条都不加
        run("--date", day(2), "start", "--force")
        self.assertEqual([i for i in loop.load_json(os.path.join(env.rd(day(2)), "items.json")) if i.get("manual_seed")], [])

    def test_dead_manual_seed_findings_evicted(self):
        env = self.env
        date = day(0)
        run("--date", date, "start")
        judge_calib(env, date)
        run("--date", date, "calib-score")
        # 造一条来自已作废种子 M007 的题和一条正常 fresh 题，裁判都判 R·套话
        bad = dict(synth(1, date)[0], id=f"{date}-m07", group="fresh",
                   来源="手工批改种子 M007", manual_seed="M007")
        good = dict(synth(2, date)[1], id=f"{date}-g01", group="fresh", 来源="BadCase 表 rec9")
        f = os.path.join(env.tmp, "r.json")
        dump(f, [bad, good])
        code, out = run("--date", date, "add-items", f)
        self.assertEqual(code, 0, out)
        # add-items 会重排合成题号；把两条改成 start 手改种子的 m 编号风格（真实种子题长这样）
        ipath = os.path.join(env.rd(date), "items.json")
        its = loop.load_json(ipath)
        renamed = 0
        for it in its:
            if it["id"].endswith("-s01"):
                it["id"] = f"{date}-m07"; renamed += 1
            elif it["id"].endswith("-s02"):
                it["id"] = f"{date}-g01"; renamed += 1
        self.assertEqual(renamed, 2)
        loop.save_json(ipath, its)
        write_outputs(env, date, "current", lambda it: "AI 的一番话振聋发聩，让我们深刻认识到。")
        run("--date", date, "blind")
        # 裁判：两份新题都残留「振聋发聩」套话；对账保留，旗标全排除
        rows = []
        for q in loop.read_jsonl(os.path.join(env.rd(date), "judge", "queue.jsonl")):
            ledger = [{"事实": f["id"], "结果": "保留"} for f in q.get("事实", [])]
            flags = [{"旗标": k["kid"], "结论": "排除", "理由": "测试"} for k in q.get("旗标", [])]
            probs = ([{"编码": "R", "病灶": "套话", "改写引用": "振聋发聩", "说明": "空洞拔高的套话还在"}]
                     if "振聋发聩" in q.get("改写", "") else [])
            rows.append({"jid": q["jid"], "场合": "技术议论", "对账": ledger, "问题": probs,
                         "旗标": flags, "结论": "改坏了" if probs else "合格"})
        loop.write_jsonl(os.path.join(env.rd(date), "judge", "answers.jsonl"), rows)
        code, out = run("--date", date, "verify", "--partial")
        self.assertEqual(code, 0, out)
        code, out = run("--date", date, "decide")
        self.assertEqual(code, 0, out)
        pool = loop.read_jsonl(loop.H("pool.jsonl"))
        self.assertFalse(any(e["item_id"].endswith("-m07") for e in pool), "作废种子的召回必须驱逐")
        self.assertTrue(any(e["item_id"].endswith("-g01") for e in pool), "正常召回应保留")

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

    def test_state_doc_roundtrip_and_guards(self):
        env = self.env
        code, out = run("version")
        self.assertIn(f"第 {loop.VERSION} 版", out)
        code, out = run("--date", day(0), "state", "dump", "--empty", "--out", os.path.join(env.tmp, "empty.xml"))
        self.assertEqual(code, 0, out)
        empty = fetched_file(env, "empty.json", as_fetched(loop.read_text(os.path.join(env.tmp, "empty.xml"))))
        code, out = run("state", "load", empty)
        self.assertIn("以本地为准", out)
        one_day(env, day(0))
        loop.write_text(loop.published_path(), "# 好好说话 · 每日细则\n\n## 细则 L001 · 引号「」<b>&amp;\u3000全角空格\U0001F600\n")
        x1 = os.path.join(env.tmp, "s1.xml")
        code, out = run("--date", day(0), "state", "dump", "--out", x1)
        self.assertIn("第 1 份", out)
        xml = loop.read_text(x1)
        codes = re.findall(r"<code>(.*?)</code>", xml, re.S)
        self.assertTrue(codes)
        self.assertFalse([c for c in codes if set(c) & set("<>&\u3000")], "代码块里有飞书可能会改动的字符")
        f1 = fetched_file(env, "s1.json", as_fetched(xml))
        code, out = run("state", "check", f1)
        self.assertIn("核对无误", out)
        code, out = run("state", "load", f1)
        self.assertIn("不用恢复", out)
        before = data_snapshot()
        shutil.rmtree(loop.eval_home())
        os.remove(loop.published_path())
        code, out = run("state", "load", f1)
        self.assertEqual(code, 0, out)
        self.assertIn("已恢复第 1 份", out)
        self.assertEqual(data_snapshot(), before)
        shutil.rmtree(loop.eval_home())
        md = "# 好好说话每日召回 · 运行状态\n\n" + "\n\n".join("```json\n" + c + "\n```" for c in codes)
        code, out = run("state", "load", fetched_file(env, "s1md.json", md))
        self.assertIn("已恢复第 1 份", out)
        self.assertEqual(data_snapshot(), before)
        run("--date", day(1), "state", "dump", "--out", os.path.join(env.tmp, "s2.xml"))
        code, out = run("state", "load", f1)
        self.assertEqual(code, 0, out)
        self.assertIn("本地比状态文档新", out)
        self.assertEqual(loop.load_state()["state_seq"], 2)
        code, out = run("state", "check", f1)
        self.assertEqual(code, 2)
        self.assertIn("第 1 份，本地是第 2 份", out)
        code, out = run("state", "load", f1, "--force")
        self.assertIn("已恢复第 1 份", out)
        self.assertTrue(glob_any(loop.eval_home() + ".bak-*"))
        code, out = run("state", "load", fetched_file(env, "bad.json", as_fetched(xml).replace("pool.jsonl", "pool.jsonI", 1)), "--force")
        self.assertEqual(code, 2)
        self.assertIn("对不上", out)
        body = [loop.doc_safe(["f", "../escape.json", "json"]), loop.doc_safe(["v", "../escape.json", [], {}])]
        evil = loop.state_doc_xml(loop.state_header(body, 9, day(2)), body, ["x"], None)
        code, out = run("state", "load", fetched_file(env, "evil.json", evil), "--force")
        self.assertEqual(code, 2)
        self.assertIn("不该有的文件", out)
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(loop.eval_home()), "escape.json")))
        fail = os.path.join(env.tmp, "fail.json")
        dump(fail, {"ok": False, "error": {"message": "no permission"}})
        code, out = run("state", "load", fail)
        self.assertEqual(code, 2)
        self.assertIn("读文档失败", out)
        shutil.rmtree(loop.eval_home())
        code, out = run("state", "load", empty)
        self.assertIn("第一次运行", out)
        self.assertFalse(os.path.exists(loop.H("state.json")))

    def test_doc_read_and_record(self):
        env = self.env
        one_day(env, day(0))
        self.assertEqual(loop.read_jsonl(loop.H("disputes.jsonl")), [])
        snap = {"任务": "改写", "文体": "周报", "力度": "标准", "原文": "这周稳定性得到了显著提升。", "上下文": "", "事实": []}
        loop.write_jsonl(loop.H("disputes.jsonl"), [
            {"id": f"D{n}", "created": day(0), "kind": kind, "item_id": f"{day(0)}-s0{n}", "version": "current",
             "文体": "周报", "原文片段": "显著提升", "改写片段": "顺了一些", "原因": "拿不准", "疑似编码": "",
             "question": "问题", "default": "有", "affects": "召回", "status": "open", "answer": None, "answered": None,
             "note": "", "item": snap} for n, kind in ((1, "保真"), (2, "场合"))])
        base = "<title>好好说话技能-召回优化</title><h1>BadCase召回</h1><p>原来的内容</p><h1>每天怎么优化</h1><p>旧方案</p>"
        code, out = run("--date", day(0), "doc", "record")
        self.assertEqual(code, 2)
        self.assertIn("先 doc read", out)
        code, out = run("--date", day(0), "doc", "read", fetched_file(env, "r0.json", base))
        self.assertIn("还没有「每日迭代日志」这一节", out)
        r1 = os.path.join(env.tmp, "r1.xml")
        code, out = run("--date", day(0), "doc", "record", "--out", r1)
        self.assertEqual(code, 0, out)
        rec = loop.read_text(r1)
        for want in ("<h1>每日迭代日志</h1>", "<h2>你的交代</h2>", f"<h2>{day(0)} · ", "D1 你的判断：＿＿", "D2 你的判断：＿＿"):
            self.assertIn(want, rec)
        code, out = run("--date", day(0), "doc", "record", "--out", r1)
        self.assertEqual(code, 2)
        self.assertIn("已经生成过", out)
        # 作者在文档里写交代、填判断
        doc = as_fetched(base + rec).replace(
            "<li>（一行一条写在这里，这一行不用删）</li>",
            "<li>（一行一条写在这里，这一行不用删）</li><li>感谢信里的客套话别删（只用于：感谢信、寄语）</li>"
            "<li><b>技术名词</b>一律用原词</li>").replace("D1 你的判断：＿＿", "D1 你的判断：没有，顺了一些可以接受")
        one_day(env, day(1))
        code, out = run("--date", day(1), "doc", "read", fetched_file(env, "r2.json", doc))
        self.assertEqual(code, 0, out)
        self.assertIn("N001 记下了（只用于感谢信、寄语）：感谢信里的客套话别删", out)
        self.assertIn("N002 记下了（所有文体都适用）：技术名词一律用原词", out)
        self.assertIn("D1 记下了：没有（顺了一些可以接受）", out)
        d1 = next(d for d in loop.read_jsonl(loop.H("disputes.jsonl")) if d["id"] == "D1")
        self.assertEqual((d1["status"], d1["answer"]), ("answered", "没有"))
        self.assertEqual(loop.read_jsonl(loop.H("precedents.jsonl"))[-1]["id"], "D1")
        r2 = os.path.join(env.tmp, "r2.xml")
        # 多造几条 open 的题：「先看」按争议优先级取前 3，不是只挑今天新问的，超出的标「排队」
        ds = loop.read_jsonl(loop.H("disputes.jsonl"))
        snap2 = dict(snap)
        ds += [
            {"id": "D3", "created": day(1), "kind": "保真", "item_id": f"{day(1)}-s01", "version": "current",
             "文体": "周报", "原文片段": "显著提升的原因", "改写片段": "顺了一些的原因", "原因": "拿不准", "疑似编码": "",
             "question": "问题", "default": "有", "affects": "发布判断", "status": "open", "answer": None,
             "answered": None, "note": "", "item": snap2},
            {"id": "D4", "created": day(1), "kind": "新问题", "item_id": f"{day(1)}-s02", "version": "current",
             "文体": "周报", "原文片段": "奠定了坚实基础", "改写片段": "", "原因": "套话", "疑似编码": "R",
             "question": "问题", "default": "没有", "affects": "召回", "status": "open", "answer": None,
             "answered": None, "note": "", "item": snap2},
        ]
        loop.write_jsonl(loop.H("disputes.jsonl"), ds)
        code, out = run("--date", day(1), "doc", "record", "--out", r2)
        self.assertEqual(code, 0, out)
        rec2 = loop.read_text(r2)
        self.assertNotIn("<h1>", rec2)
        self.assertNotIn("D1 你的判断", rec2)
        # D3（保真）和 D2（场合）排前 3 是「先看」，D4（新问题）第 4 个标「排队」；槽位都保留
        self.assertIn("排队", rec2)
        self.assertIn("D2 你的判断：＿＿", rec2)
        self.assertIn("D4 你的判断：＿＿", rec2)
        self.assertIn("记下你的回话", rec2)
        code, out = run("--date", day(1), "doc", "read", fetched_file(env, "r2.json", doc))
        self.assertIn("没有新的判断和交代", out)
        # 对话里记的交代不受文档影响；文档里删一行就作废那一条
        run("--date", day(1), "note", "add", "别加口头禅")
        code, out = run("--date", day(1), "doc", "read",
                        fetched_file(env, "r3.json", doc.replace("<li><b>技术名词</b>一律用原词</li>", "")))
        self.assertIn("N002 作废了", out)
        self.assertEqual({n["id"] for n in loop.active_notes()}, {"N001", "N003"})
        run("--date", day(1), "doc", "read", fetched_file(env, "r4.json", doc))
        self.assertEqual({n["id"] for n in loop.active_notes()}, {"N001", "N003", "N004"})
        bare = doc.replace("<li>感谢信里的客套话别删（只用于：感谢信、寄语）</li><li><b>技术名词</b>一律用原词</li>", "")
        code, out = run("--date", day(1), "doc", "read", fetched_file(env, "r5.json", bare))
        self.assertIn("一条都没读到", out)
        self.assertEqual(len(loop.active_notes()), 3)
        code, out = run("--date", day(1), "doc", "read",
                        fetched_file(env, "r6.json", doc.replace("D2 你的判断：＿＿", "D2 你的判断：看情况")))
        self.assertIn("看不懂 D2", out)
        code, out = run("--date", day(1), "doc", "read",
                        fetched_file(env, "r7.json", doc.replace("D2 你的判断：＿＿</p>", "D2 你的判断：＿＿</p><p>有，场合不对</p>")))
        self.assertIn("D2 记下了：有（场合不对）", out)
        self.assertTrue(any(e.get("dispute_id") == "D2" and e["item"]["原文"] for e in loop.read_jsonl(loop.H("pool.jsonl"))))
        md = f"# 每日迭代日志\n\n## 你的交代\n\n- 寄语别写成公文\n\n## {day(0)} · 测试\n\nD2 你的判断：**跳过**\n"
        before = loop.read_text(loop.H("notes.jsonl"))
        code, out = run("--date", day(2), "doc", "read", "--dry-run", fetched_file(env, "md.json", md))
        self.assertIn("会新记 1 条交代、作废 2 条", out)
        self.assertIn("D2 会记成 跳过", out)
        self.assertEqual(loop.read_text(loop.H("notes.jsonl")), before)
        self.assertEqual(loop.load_state()["recall_doc"]["read"], day(1))
        # 这一节后面有了别人的内容：不追加
        code, out = run("--date", day(2), "doc", "read",
                        fetched_file(env, "r8.json", doc + "<h1>别的内容</h1><p>作者后来加的</p>"))
        self.assertIn("后面还有别的一级标题", out)
        code, out = run("--date", day(2), "doc", "record", "--stopped", "测试")
        self.assertEqual(code, 2)
        self.assertIn("不往后追加", out)
        run("--date", day(2), "doc", "read", fetched_file(env, "r9.json", doc))
        code, out = run("--date", day(2), "doc", "record")
        self.assertEqual(code, 2)
        self.assertIn("还没 decide", out)
        r3 = os.path.join(env.tmp, "r3.xml")
        code, out = run("--date", day(2), "doc", "record", "--stopped", "裁判体检连续两天没过", "--out", r3)
        self.assertEqual(code, 0, out)
        self.assertIn("今天停下了", loop.read_text(r3))
        self.assertIn("裁判体检连续两天没过", loop.read_text(r3))
        code, out = run("--date", day(2), "doc", "record", "--stopped", "再写一次", "--again")
        self.assertEqual(code, 0, out)
        self.assertIn(f"--content - < {loop.H('exports', f'record-{day(2)}.xml')}", out)
        # 文档里已经有今天的记录（比如状态没存上又重跑）：不再追加
        doc3 = doc + as_fetched(loop.read_text(r3))
        code, out = run("--date", day(2), "doc", "read", fetched_file(env, "r10.json", doc3))
        self.assertIn(f"已经有 {day(2)} 的记录了", out)
        run("--date", day(2), "doc", "record", "--stopped", "x", "--again")
        self.assertEqual(loop.load_state()["recall_doc"]["today"], True)
        loop.save_state({**loop.load_state(), "recorded": None})
        code, out = run("--date", day(2), "doc", "record", "--stopped", "x")
        self.assertEqual(code, 2)
        self.assertIn(f"已经有 {day(2)} 的记录了", out)
        # 状态丢过一天、题号撞了：写在出题日期之前那条记录下面的判断不算
        ds = loop.read_jsonl(loop.H("disputes.jsonl"))
        for d in ds:
            if d["id"] == "D2":
                d.update(status="open", answer=None, answered=None, created=day(2), doc_answer=None)
        loop.write_jsonl(loop.H("disputes.jsonl"), ds)
        code, out = run("--date", day(2), "doc", "read",
                        fetched_file(env, "r11.json", doc3.replace("D2 你的判断：＿＿", "D2 你的判断：没有")))
        self.assertNotIn("D2 记下了", out)
        self.assertEqual(next(d for d in loop.read_jsonl(loop.H("disputes.jsonl")) if d["id"] == "D2")["status"], "open")
        # 对话里撤回写在文档里的交代：那一行留着也不会再记上；删掉再写才算新的一条
        self.assertEqual({n["id"] for n in loop.active_notes()}, {"N001", "N003", "N004"})
        code, out = run("--date", day(2), "note", "drop", "N004")
        self.assertIn("那一行留着也不会再记上", out)
        code, out = run("--date", day(2), "doc", "read", fetched_file(env, "r12.json", doc3))
        self.assertNotIn("记下了", out)
        self.assertEqual({n["id"] for n in loop.active_notes()}, {"N001", "N003"})
        run("--date", day(2), "doc", "read",
            fetched_file(env, "r13.json", doc3.replace("<li><b>技术名词</b>一律用原词</li>", "")))
        code, out = run("--date", day(2), "doc", "read", fetched_file(env, "r14.json", doc3))
        self.assertIn("N005 记下了", out)

    def test_compact_keeps_ids_and_bounds(self):
        cfg = loop.load_config()
        old, today = day(0), day(40)
        for n in range(5):
            run("--date", old, "note", "add", f"交代 {n}")
        for n in range(1, 6):
            run("--date", old, "note", "drop", f"N00{n}")
        pool = [{"date": day(30 + n % 5), "run": day(30), "item_id": f"i{n}", "kind": "synthetic", "文体": "周报",
                 "release": "v0000", "code": "C1", "cluster": "C1", "quote_src": "显著" * 150, "quote_out": "顺了",
                 "note": "", "item": {"原文": f"第 {n} 条，稳定性得到了显著提升。", "文体": "周报"}} for n in range(12)]
        pool.append(dict(pool[0], date=old, item_id="old"))
        pool.append(dict(pool[1], quote_out="同一道题的第二个问题"))
        loop.write_jsonl(loop.H("pool.jsonl"), pool)
        loop.write_jsonl(loop.H("disputes.jsonl"), [
            {"id": "D7", "created": old, "kind": "保真", "status": "answered", "answered": old, "item": {"原文": "x"}},
            {"id": "D8", "created": day(39), "kind": "保真", "status": "defaulted", "answered": day(39), "item": {"原文": "x"}},
            {"id": "D9", "created": day(39), "kind": "保真", "status": "open", "item": {"原文": "x"}}])
        st = loop.load_state()
        loop.compact(cfg, st, today)
        loop.save_state(st)
        pool = loop.read_jsonl(loop.H("pool.jsonl"))
        self.assertNotIn("old", {e["item_id"] for e in pool})
        snaps = [e["item_id"] for e in pool if e.get("item")]
        self.assertEqual(len(snaps), cfg["retain"]["snapshots_per_cluster"])
        self.assertEqual(len(snaps), len(set(snaps)))
        self.assertTrue(all(len(e["quote_src"]) <= 200 for e in pool))
        ds = loop.read_jsonl(loop.H("disputes.jsonl"))
        self.assertEqual([(d["id"], "item" in d) for d in ds], [("D8", False), ("D9", True)])
        self.assertEqual(loop.read_jsonl(loop.H("notes.jsonl")), [])
        code, out = run("--date", today, "note", "add", "新的一条")
        self.assertIn("N006 记下了", out)
        dev, hold = loop.split_dev_holdout(pool)
        self.assertTrue(hold and all(h.get("item") for h in hold))
        self.assertTrue(any(not e.get("item") for e in dev))
        self.assertFalse({h["item_id"] for h in hold} & {e["item_id"] for e in dev})

    def test_seen_blocks_repeats_after_runs_are_gone(self):
        env = self.env
        one_day(env, day(0))
        shutil.rmtree(loop.H("runs"))
        run("--date", day(1), "start")
        f = os.path.join(env.tmp, "again.json")
        dump(f, synth(3, day(0)))
        code, out = run("--date", day(1), "add-items", f)
        self.assertEqual(code, 1, out)
        self.assertIn("收下 0 条", out)
        self.assertIn(f"{day(0)} 出过一模一样的题", out)

    def test_sign_and_quotes(self):
        self.assertAlmostEqual(loop.sign_p(5, 0), 1 / 32)
        self.assertAlmostEqual(loop.sign_p(6, 1), 8 / 128)
        self.assertTrue(loop.quote_in("交付能力……显著提升", "这周交付能力得到了显著提升。"))
        self.assertFalse(loop.quote_in("显著提升……交付能力", "这周交付能力得到了显著提升。"))
        self.assertTrue(loop.quote_in("“重构”", "把清洗逻辑「重构」了一遍"))
        chk = loop.mechanical_check({"原文": "预计明天上线，采用重构方案。", "任务": "改写"}, "明天上线，采用重写方案，QPS 5000。")
        kinds = {f["类型"] for f in chk["flags"]}
        self.assertTrue({"模态变化", "术语替换", "新英文词", "新数字"} <= kinds, kinds)

    def test_fingerprint_includes_package_modules(self):
        """eval_skill 指纹必须覆盖 scripts/hh_eval/ 包内实现，改包文件漂移检测才发现得了。"""
        import tempfile
        from unittest import mock
        from hh_eval import fp as fp_mod
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "references"))
        os.makedirs(os.path.join(d, "scripts", "hh_eval"))
        from pathlib import Path
        Path(os.path.join(d, "SKILL.md")).write_text("skill", encoding="utf-8")
        Path(os.path.join(d, "references", "a.md")).write_text("ref", encoding="utf-8")
        Path(os.path.join(d, "scripts", "loop.py")).write_text("entry", encoding="utf-8")
        pkg_p = os.path.join(d, "scripts", "hh_eval", "pipeline.py")
        Path(pkg_p).write_text("impl v1", encoding="utf-8")
        with mock.patch.object(fp_mod, "skill_dir", lambda: d), \
                mock.patch.object(fp_mod, "find_shuohua_dir", lambda cfg: ""):
            h1 = fp_mod.fingerprints({})["eval_skill"]
            Path(pkg_p).write_text("impl v2 changed", encoding="utf-8")
            h2 = fp_mod.fingerprints({})["eval_skill"]
        self.assertNotEqual(h1, h2)

    def test_corrupt_state_file_stops_cleanly(self):
        """state.json 损坏（不是合法 JSON）：退出码 2 + 人话报错，不抛 traceback，也不自动删文件。"""
        path = loop.H("state.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{这不是合法 JSON")
        code, out = run("status")
        self.assertEqual(code, 2, out)
        self.assertIn("损坏", out)
        self.assertTrue(os.path.exists(path), "损坏的状态文件不该被自动删掉")

    def test_self_added_disclaimer_is_m(self):
        """正文里自己加的「以上仅依据……未核验」抬「自加免责」旗标，裁判确认后记 M，结论是没改好。"""
        src = "两项关键实验结果还没返回，报告今天下班前交不了，预计最早明天下午才能交。"
        out = src.replace("才能交", "能交") + "\n\n以上仅依据你提供的情况，未做额外核验。"
        chk = loop.mechanical_check({"原文": src, "任务": "改写"}, out)
        mine = [f for f in chk["flags"] if f["类型"] == "自加免责"]
        self.assertEqual([f["内容"] for f in mine], ["以上仅依据", "未做额外核验"], chk["flags"])
        q = {"jid": "J002", "原文": src, "上下文": "", "改写": chk["body"], "旗标": chk["flags"]}
        ans = {"jid": "J002", "场合": "私人软场合", "对账": [],
               "问题": [{"编码": "M", "改写引用": "以上仅依据你提供的情况", "说明": "正文里自己加的免责"}],
               "旗标": [{"旗标": f["kid"], "结论": "确认" if f["类型"] == "自加免责" else "排除", "理由": "原文没有这句"}
                       for f in chk["flags"]],
               "结论": "没改好"}
        r = loop.verify_answer(ans, q)
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["verdict"], "没改好")
        # 原文自己写着的「尚未核实」不抬旗，硬记 M 也会作废
        keep = loop.mechanical_check({"原文": "这个原因尚未核实，今天继续排查。", "任务": "改写"}, "原因尚未核实，今天继续排查。")
        self.assertNotIn("自加免责", {f["类型"] for f in keep["flags"]})
        ok, why = loop.check_finding("M", "", "尚未核实", "这个原因尚未核实，今天继续排查。", "原因尚未核实，今天继续排查。")
        self.assertFalse(ok)
        self.assertEqual(why, "这段在原文里就有，不算新加的")
        # 「【给作者】」一段里的话不算正文
        sep = loop.mechanical_check({"原文": src, "任务": "改写"}, src + "\n\n【给作者】原文没写为什么延期，需要的话你补一句。")
        self.assertNotIn("自加免责", {f["类型"] for f in sep["flags"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
