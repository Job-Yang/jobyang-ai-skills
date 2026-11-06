#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对抗式自检：主动构造反例，每条都要有确定行为（停/拒/重试上限），
不许有 traceback，也不许静默成功。跑法：python3 scripts/test_adversarial.py

覆盖（对应改造说明里的对抗清单）：
1. 状态 JSON 损坏（不合法 JSON）：退出 2 + 人话报错，不抛 traceback，不自动删文件
2. 状态文档 sha 对不上：state check 退出 2，不恢复
3. 召回文档缺今日节/缺整节：doc read / record 有确定提示，不追加
4. 裁判引用原文找不到 / 伪造引用（原文里就有）：verify_answer 报错或作废
5. 同一天重复跑（幂等）：start / decide / doc record 不重复写
6. --data-root 隔离：临时根下跑全程，用户全局 ~/.local/share 一个字节不动
7. 缺 lark-cli：preflight 标出来但不 block 离线流程
8. preflight 坏文档（无权限 JSON）：按「数据没接上：原始报错」停，绝不 init
9. 小样本门禁结论落 decision.json 的 observations（观察项），不进 pass/fail
10. fit_weights 缺 scipy：人话提示，不是 traceback
"""
import datetime as dt
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import loop  # noqa: E402

D0 = dt.date(2026, 10, 5)


def day(n):
    return (D0 + dt.timedelta(days=n)).isoformat()


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = loop.main(list(argv))
    return code, out.getvalue() + err.getvalue()


def dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def as_fetched(xml):
    def code(m):
        return m.group(1) + m.group(2).replace("\n", "<br/>").replace('"', "&quot;") + m.group(3)
    return re.sub(r"(<code>)(.*?)(</code>)", code, xml, flags=re.S).replace("\n<", "<")


def fetched_file(env, name, content):
    path = os.path.join(env.tmp, name)
    dump(path, {"ok": True, "identity": "user", "data": {"document": {"content": content}}})
    return path


def synth(n, date):
    return [{"kind": "synthetic", "文体": "周报", "读者": "组内", "场合": "技术议论",
              "原文": f"{date} 这周我们对搜索召回做了全面的梳理，搜索召回的稳定性得到了显著提升，预计下周收尾，编号 {date}-{i}。",
              "事实": [{"id": "F1", "内容": "梳理优化", "关键词": ["搜索召回"]},
                       {"id": "F2", "内容": "稳定性显著提升", "关键词": ["显著提升"]},
                       {"id": "F3", "内容": "预计下周收尾", "关键词": ["预计"]}]} for i in range(n)]


class Env:
    def __init__(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_DATA_HOME"] = os.path.join(self.tmp, "xdg")
        os.environ["HAOHAO_EVAL_HOME"] = os.path.join(self.tmp, "eval")

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class AdversarialTest(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        code, out = run("--date", day(0), "init")
        self.assertEqual(code, 0, out)

    def tearDown(self):
        self.env.close()

    # 1 损坏状态 JSON
    def test_corrupt_state_json(self):
        path = loop.H("state.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{这不是合法 JSON")
        code, out = run("status")
        self.assertEqual(code, 2, out)
        self.assertIn("损坏", out)
        self.assertTrue(os.path.exists(path), "损坏的状态文件不该被自动删掉")

    # 2 sha 对不上：真 dump 一份，篡改文档头里的校验和
    def test_state_doc_sha_mismatch(self):
        out_path = os.path.join(self.env.tmp, "s.xml")
        code, out = run("--date", day(0), "state", "dump", "--out", out_path)
        self.assertEqual(code, 0, out)
        content = as_fetched(loop.read_text(out_path))
        obj = {"ok": True, "identity": "user", "data": {"document": {"content": content}}}
        obj["data"]["document"]["content"] = content.replace(
            '&quot;sha256&quot;:&quot;', '&quot;sha256&quot;:&quot;0000000000000000', 1)
        fetched = os.path.join(self.env.tmp, "tampered.json")
        dump(fetched, obj)
        code, out = run("state", "load", fetched, "--force")
        self.assertEqual(code, 2, out)
        self.assertIn("对不上", out)

    # 3 召回文档缺整节
    def test_recall_doc_missing_section(self):
        base = "<title>好好说话技能-召回优化</title><h1>BadCase召回</h1><p>原来的内容</p>"
        code, out = run("--date", day(0), "doc", "record")
        self.assertEqual(code, 2)
        self.assertIn("先 doc read", out)
        code, out = run("--date", day(0), "doc", "read", fetched_file(self.env, "r.json", base))
        self.assertIn("还没有「每日迭代日志」这一节", out)

    # 4 裁判引用核对
    def test_judge_quotes(self):
        q = {"jid": "J1", "原文": "这周稳定性得到了显著提升。", "上下文": "", "改写": "这周稳定性顺了一些。",
             "事实": [{"id": "F1", "内容": "x"}], "旗标": []}
        bad = {"jid": "J1", "场合": "技术议论", "对账": [{"事实": "F1", "结果": "保留"}],
               "问题": [{"编码": "C1", "原文引用": "根本不存在的一句话", "改写引用": "顺了一些", "说明": "x"}],
               "结论": "改坏了"}
        r = loop.verify_answer(bad, q)
        self.assertEqual(r["errors"], [], r)
        self.assertEqual(r["dropped"][0]["作废原因"], "原文引用在原文里找不到", r["dropped"])
        fake = {"jid": "J1", "场合": "技术议论", "对账": [{"事实": "F1", "结果": "保留"}],
                "问题": [{"编码": "A1", "改写引用": "这周稳定性", "说明": "原文里就有"}], "结论": "改坏了"}
        r = loop.verify_answer(fake, q)
        self.assertEqual(r["dropped"][0]["作废原因"], "这段在原文里就有，不算新加的")

    # 5 同一天重复跑幂等
    def test_same_day_rerun_idempotent(self):
        code, out = run("--date", day(0), "start")
        self.assertEqual(code, 0, out)
        code, out = run("--date", day(0), "start")
        self.assertEqual(code, 0, out)
        self.assertIn("今天这一轮已经开过", out)
        # decide 没跑过时不该有 decision.json；跑过再跑不重写
        code, out = run("--date", day(0), "decide")
        self.assertEqual(code, 2, out)  # 没 verify
        self.assertIn("还没 verify", out)

    # 6 --data-root 隔离：全局 ~/.local/share 一个字节不动
    def test_data_root_does_not_touch_global(self):
        tmp = tempfile.mkdtemp(prefix="eq-root-")
        old = {k: os.environ.get(k) for k in ("HOME", "XDG_DATA_HOME", "HAOHAO_EVAL_HOME")}
        for k in ("HOME", "XDG_DATA_HOME", "HAOHAO_EVAL_HOME"):
            os.environ.pop(k, None)
        sentinel_home = os.path.join(tmp, "home")
        os.environ["HOME"] = sentinel_home
        sentinel = os.path.join(sentinel_home, ".local", "share", "haohao-shuohua", "daily-learning.md")
        os.makedirs(os.path.dirname(sentinel))
        with open(sentinel, "w", encoding="utf-8") as f:
            f.write("SENTINEL-GLOBAL-不要动")
        root = os.path.join(tmp, "root")
        try:
            code, out = run("--data-root", root, "--date", day(0), "init")
            self.assertEqual(code, 0, out)
            out_path = os.path.join(tmp, "state.xml")
            code, out = run("--data-root", root, "--date", day(0), "state", "dump", "--out", out_path)
            self.assertEqual(code, 0, out)
            fetched = os.path.join(tmp, "state-fetched.json")
            dump(fetched, {"ok": True, "identity": "user",
                           "data": {"document": {"content": as_fetched(loop.read_text(out_path))}}})
            code, out = run("--data-root", root, "state", "load", fetched)
            self.assertEqual(code, 0, out)
            with open(sentinel, encoding="utf-8") as f:
                self.assertEqual(f.read(), "SENTINEL-GLOBAL-不要动", "全局发布文件被碰了")
            self.assertFalse(glob_any(sentinel + ".bak-*"), "全局目录里出现了 .bak 备份")
            self.assertTrue(os.path.exists(os.path.join(root, "haohao-eval", "state.json")),
                            "data-root 下的 eval 数据目录没建出来")
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            shutil.rmtree(tmp, ignore_errors=True)

    # 7 preflight：坏文档按「数据没接上」停
    def test_preflight_bad_doc_stops(self):
        bad = os.path.join(self.env.tmp, "bad.json")
        dump(bad, {"ok": False, "error": {"message": "no permission"}})
        code, out = run("preflight", "--state-doc-file", bad)
        self.assertEqual(code, 2, out)
        self.assertIn("数据没接上", out)
        code, out = run("preflight", "--json")
        self.assertEqual(code, 0, out)
        obj = json.loads(out)
        self.assertTrue(obj["offline_ok"])
        self.assertIsNone(obj["online_ok"], "没给文档文件时 online_ok 应该是未知")
        self.assertNotIn("state_doc", obj["blocked"])

    # 9 观察项落 decision.json：跑一天，decision.json 有 observations 键
    def test_observations_collected(self):
        code, out = run("--date", day(0), "start")
        self.assertEqual(code, 0, out)
        f = os.path.join(self.env.tmp, "i.json")
        dump(f, synth(1, day(0)))
        code, out = run("--date", day(0), "add-items", f)
        self.assertEqual(code, 0, out)
        rd = loop.run_dir(day(0))
        for it in loop.load_json(os.path.join(rd, "items.json")):
            p = os.path.join(rd, "outputs", "current", it["id"] + ".txt")
            loop.write_text(p, it["原文"].replace("显著提升", "顺了一些"))
        code, out = run("--date", day(0), "blind")
        self.assertEqual(code, 0, out)
        key = loop.load_json(os.path.join(rd, "private", "judge_key.json"))
        items = {i["id"]: i for i in loop.load_json(os.path.join(rd, "items.json"))}
        rows = []
        for q in loop.read_jsonl(os.path.join(rd, "judge", "queue.jsonl")):
            iid, v, _ = key[q["jid"]][0]
            rows.append({"jid": q["jid"], "场合": "技术议论",
                         "对账": [{"事实": f["id"], "结果": "变了", "编码": "C1", "原文引用": "显著提升", "改写引用": "顺了一些"}
                                  if f["id"] == "F2" and "顺了一些" in q["改写"] else {"事实": f["id"], "结果": "保留"}
                                  for f in q.get("事实", [])],
                         "问题": [{"编码": "C1", "原文引用": "显著提升", "改写引用": "顺了一些", "说明": "程度降了"}]
                         if "显著提升" in q["原文"] and "顺了一些" in q["改写"] else [],
                         "旗标": [{"旗标": k["kid"], "结论": "排除", "理由": "测试"} for k in q.get("旗标", [])],
                         "结论": "改坏了" if "显著提升" in q["原文"] and "顺了一些" in q["改写"] else "合格"})
        loop.write_jsonl(os.path.join(rd, "judge", "answers.jsonl"), rows)
        code, out = run("--date", day(0), "verify")
        self.assertEqual(code, 0, out)
        code, out = run("--date", day(0), "decide")
        self.assertEqual(code, 0, out)
        dec = loop.load_json(os.path.join(rd, "decision.json"))
        self.assertIn("observations", dec, "decision.json 必须有 observations 字段")

    def test_calib_same_source_different_rewrite_not_reused(self):
        p = {"id": "D80", "kind": "体检", "status": "answered", "answer": "有",
             "answered": day(0), "calib_id": "42|我们", "文体": "颁奖词", "疑似编码": "C1",
             "原文片段": "使命必达", "改写片段": "按时交出来"}
        d = dict(p, id="D81", status="open", answer=None)
        self.assertIsNotNone(loop.match_calib_answer(d, [p], 0.75))
        self.assertIsNone(loop.match_calib_answer(dict(d, 改写片段="使命必达"), [p], 0.75))
        self.assertIsNone(loop.match_calib_answer(dict(d, calib_id="42|工具1", 原文片段="他总能使命必达",
                                                     改写片段="交给他基本能落地"), [p], 0.75))
        for change in ({"文体": "私人留言"}, {"疑似编码": "G"}, {"calib_id": "43|我们"}):
            self.assertIsNone(loop.match_calib_answer(dict(d, **change), [p], 0.75))
        for status in ("auto", "defaulted"):
            self.assertIsNone(loop.match_calib_answer(d, [dict(p, status=status)], 0.75))
        green = dict(p, answer="没有")
        self.assertIsNone(loop.match_calib_answer(dict(d, calib_id="42|工具1"), [green], 0.75))
        self.assertIsNone(loop.match_calib_answer(d, [p, green], 0.75))
        newer = dict(green, answered=day(1))
        self.assertEqual(loop.match_calib_answer(d, [p, newer], 0.75)[0]["answer"], "没有")

    def test_seed_diff_noop_and_unrelated_output_do_not_learn(self):
        from hh_eval.manualdiff import author_intent, seed_diff
        seed = loop.seed_index()["M016"]
        # 完全不改也能与作者稿高度相似，但不得算跟上替换。
        noop = seed_diff("M016", seed["洗稿原句"])
        self.assertEqual(noop["跟上改"], 0)
        self.assertEqual(noop["跟上删"], 0)
        self.assertEqual(seed_diff("M016", seed["改成"])["跟改"], 1.0)
        self.assertIsNone(seed_diff("M007", ""))  # 作废种子
        self.assertIsNone(seed_diff("M026", ""))  # 作者回源的内容
        self.assertEqual(author_intent({"洗稿原句": "原文完好，不可自行删除。", "改成": ""})["deleted"], [])
        unrelated = seed_diff("M018", "这是一条没有任何共同措辞的另一条消息。")
        self.assertLess(unrelated["跟删"], 1.0)

    # 10 强制隔离 site-packages，确定性覆盖缺 scipy 分支，不因本机装了依赖跳过
    def test_fit_weights_hint(self):
        p = subprocess.run([sys.executable, "-S", os.path.join(HERE, "fit_weights.py")],
                           capture_output=True, text=True, cwd=HERE)
        text = (p.stdout + p.stderr).lower()
        self.assertIn("scipy", text)
        self.assertNotIn("traceback", text)


def glob_any(pattern):
    import glob
    return bool(glob.glob(pattern))


if __name__ == "__main__":
    unittest.main(verbosity=2)
