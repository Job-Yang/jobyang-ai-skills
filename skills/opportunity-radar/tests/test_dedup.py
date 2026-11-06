#!/usr/bin/env python3
"""dedup.py 回归：每日雷达幂等去重（标准库 unittest，无第三方依赖）。

核心场景（来自 2026-10-16 真实运行）：
  A. 历史 = 两条立条记录（09-28 语音直达 / 10-12 浏览器 Agent 确认层）。
     今天扫到的"主动式 AI 助手"必须判 RELATED→09-28，"MGX 烧积分"必须判
     RELATED→10-12；戒烟/版税/笔记三条与历史零重合，判 NEW。
  B. 明天再扫同一信号（历史已含 10-16 运行记录，记录里写着这两条次级信号）：
     重新捞起"主动式 AI 助手"必须判 DUP——这就是幂等：昨天 triage 过的信号
     今天不许再开一条新条目。
  C. 全 DUP/RELATED 时退出码 4（安静日信号，不是错误），cron 据此走无机会留痕分支。

跑法：python3 -m unittest tests.test_dedup -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "dedup.py"
FX = ROOT / "tests" / "fixtures"


def run(history, candidates, extra=None):
    cmd = [sys.executable, str(SCRIPT), "--history", *[str(h) for h in history],
           "--candidates", str(candidates)]
    if extra:
        cmd += extra
    return subprocess.run(cmd, capture_output=True, text=True)


def write_cands(items):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(items, f, ensure_ascii=False)
    f.close()
    return Path(f.name)


HIST_STANDUP = [FX / "history-2026-09-28.md", FX / "history-2026-10-12.md"]


class TodayScenarioTest(unittest.TestCase):
    def test_today_signals_are_related_not_new(self):
        """场景 A：proactive 助手→RELATED(09-28)，烧积分→RELATED(10-12)。"""
        cands = json.loads((FX / "today-candidates-2026-10-16.json").read_text(encoding="utf-8"))
        p = write_cands(cands)
        try:
            proc = run(HIST_STANDUP, p)
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
            out = json.loads(proc.stdout)
            by_title = {r["title"][:12]: r for r in out["results"]}
            r1 = out["results"][0]
            self.assertEqual("RELATED", r1["verdict"], r1["reason"])
            self.assertEqual("2026-09-28", r1["matched"]["date"])
            r2 = out["results"][1]
            self.assertEqual("RELATED", r2["verdict"], r2["reason"])
            self.assertEqual("2026-10-12", r2["matched"]["date"])
            self.assertEqual(3, out["summary"]["NEW"], "戒烟/版税/笔记历史未覆盖应 NEW")
        finally:
            p.unlink()

    def test_idempotent_rerun_is_dup(self):
        """场景 B：历史含今日运行记录后，再捞起同一信号必须判 DUP，退出码 4。"""
        history = HIST_STANDUP + [FX / "run-2026-10-16-no-strong.md"]
        cands = write_cands([
            {"title": "主动式个人 AI 助手又冒出来（Poke、PPLX 邮件日历助手）",
             "direction": "AI 主动代处理邮件日历事务，主动助手直达工作流"},
            {"title": "AI 建站烧积分不出活（MGX/Atoms 差评）",
             "direction": "agent 产出确认层近亲：AI 建站工具烧积分不出活"},
        ])
        try:
            proc = run(history, cands)
            out = json.loads(proc.stdout)
            self.assertTrue(out["all_dup"])
            for r in out["results"]:
                self.assertEqual("DUP", r["verdict"], r["reason"])
            self.assertEqual(4, proc.returncode, "全 DUP/RELATED 必须退出码 4")
        finally:
            cands.unlink()


class JudgmentRulesTest(unittest.TestCase):
    def test_exact_repeat_is_dup(self):
        """逐字重复历史标题 → DUP。"""
        cands = write_cands([
            {"title": "浏览器 Agent 结果确认层", "direction": ""},
        ])
        try:
            proc = run(HIST_STANDUP, cands)
            out = json.loads(proc.stdout)
            self.assertEqual("DUP", out["results"][0]["verdict"], out["results"][0]["reason"])
        finally:
            cands.unlink()

    def test_unrelated_topic_is_new(self):
        cands = write_cands([
            {"title": "围绝经期半夜醒的个性化提醒", "direction": "女性健康围绝经期睡眠"},
        ])
        try:
            proc = run(HIST_STANDUP, cands)
            out = json.loads(proc.stdout)
            self.assertEqual("NEW", out["results"][0]["verdict"])
        finally:
            cands.unlink()

    def test_rewritten_same_subject_is_dup(self):
        """复评驳回#2：明显换皮改写（词换了主体没变）必须判 DUP，不漏判重复。"""
        cands = write_cands([
            {"title": "浏览器 agent 跑出来的结果要人工确认才能用", "direction": "agent 产出确认"},
        ])
        try:
            proc = run(HIST_STANDUP, cands)
            out = json.loads(proc.stdout)
            self.assertEqual("DUP", out["results"][0]["verdict"], out["results"][0]["reason"])
        finally:
            cands.unlink()

    def test_new_direction_not_killed_by_rewrite_rule(self):
        """复评驳回#2 反例：换皮判据不能误杀真新方向。"""
        cands = write_cands([
            {"title": "围绝经期半夜醒的个性化提醒", "direction": "女性健康围绝经期睡眠"},
        ])
        try:
            proc = run(HIST_STANDUP, cands)
            out = json.loads(proc.stdout)
            self.assertEqual("NEW", out["results"][0]["verdict"], out["results"][0]["reason"])
        finally:
            cands.unlink()

    def test_bad_input_exit_code_2(self):
        bad = write_cands([{"title": "x"}])
        bad.write_text("{not json")
        proc = run(HIST_STANDUP, bad)
        self.assertEqual(2, proc.returncode)
        err = json.loads(proc.stderr)
        self.assertEqual("rejected", err["status"])
        bad.unlink()

    def test_deterministic_two_runs_identical(self):
        cands = json.loads((FX / "today-candidates-2026-10-16.json").read_text(encoding="utf-8"))
        p = write_cands(cands)
        try:
            a = run(HIST_STANDUP, p).stdout
            b = run(HIST_STANDUP, p).stdout
            self.assertEqual(a, b, "同一输入两次跑必须逐字一致（确定性）")
        finally:
            p.unlink()


if __name__ == "__main__":
    unittest.main()
