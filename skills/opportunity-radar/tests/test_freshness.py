#!/usr/bin/env python3
"""freshness.py 回归：证据对抗式自检（标准库 unittest）。

0.4.0 语义：dedup 判 RELATED 只是软旗（近亲可再看新切面），freshness 的
stale_evidence 是硬旗。2026-10-16 的 5 条候选里 3 条是半年旧愿（硬旗挡住）、
2 条近亲（软旗放行），因此 deep_dig=2、退出码 0；真正让那天"不立条"的是
旧愿时间窗 + Agent 的人工裁决，不是 freshness 一刀切。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "freshness.py"
DEDUP = ROOT / "scripts" / "dedup.py"
FX = ROOT / "tests" / "fixtures"


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def write(items):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(items, f, ensure_ascii=False)
    f.close()
    return Path(f.name)


class FreshnessTest(unittest.TestCase):
    def test_old_wishes_blocked_related_soft_passes(self):
        """0.4.0：3 条半年旧愿被硬旗挡住；2 条近亲只是软旗，仍可深挖。"""
        cands = FX / "today-candidates-2026-10-16.json"
        # 先 dedup
        d = run([sys.executable, str(DEDUP), "--history",
                 str(FX / "history-2026-09-28.md"), str(FX / "history-2026-10-12.md"),
                 "--candidates", str(cands)])
        dedup_out = Path(tempfile.mktemp(suffix=".json"))
        dedup_out.write_text(d.stdout, encoding="utf-8")
        # 再 freshness 接上 dedup 结果
        f = run([sys.executable, str(SCRIPT), "--candidates", str(cands),
                 "--today", "2026-10-16", "--dedup", str(dedup_out)])
        self.assertEqual(0, f.returncode, f.stderr + f.stdout)
        out = json.loads(f.stdout)
        self.assertEqual(2, out["deep_dig"], "只有 RELATED 软旗的两条应可深挖")
        by_part = {r["title"][:6]: r for r in out["results"]}

        def find(part):
            return next(r for r in out["results"] if part in r["title"])

        rel1 = find("主动式个人")
        rel2 = find("烧积分")
        self.assertIn("already_logged:RELATED", rel1["soft_flags"])
        self.assertIn("already_logged:RELATED", rel2["soft_flags"])
        self.assertTrue(rel1["deep_dig"] and rel2["deep_dig"], "近亲软旗不挡候选")
        for part in ("戒烟社交", "自出版", "笔记囤着"):
            r = find(part)
            self.assertIn("stale_evidence", r["hard_flags"], part)
            self.assertFalse(r["deep_dig"], part)
        dedup_out.unlink()

    def test_polluted_source_flagged(self):
        p = write([{"title": "垃圾源来的机会", "direction": "",
                    "evidence_url": "https://imtqy.com/article", "evidence_date": "2026-10-10",
                    "payment_signal": "付费订阅"}])
        f = run([sys.executable, str(SCRIPT), "--candidates", str(p), "--today", "2026-10-16"])
        out = json.loads(f.stdout)
        self.assertIn("polluted_source", out["results"][0]["flags"])
        p.unlink()

    def test_no_payment_signal_is_soft_flag(self):
        """0.4.0：缺付费信号不再挡候选，只记软旗，深挖时补「谁在付钱」。"""
        p = write([{"title": "Show HN 上新出的开发者小工具", "direction": "",
                    "evidence_url": "https://example.com/x", "evidence_date": "2026-10-10",
                    "payment_signal": ""}])
        f = run([sys.executable, str(SCRIPT), "--candidates", str(p), "--today", "2026-10-16"])
        out = json.loads(f.stdout)
        r = out["results"][0]
        self.assertIn("payment_unverified", r["soft_flags"])
        self.assertTrue(r["deep_dig"], "缺付费信号是软旗，不挡新供给")
        p.unlink()

    def test_fresh_paying_candidate_passes(self):
        p = write([{"title": "围绝经期半夜醒的个性化提醒", "direction": "女性健康",
                    "evidence_url": "https://reddit.com/r/example", "evidence_date": "2026-10-14",
                    "payment_signal": "有人在私医和补剂上花钱，付费订阅意愿"}])
        f = run([sys.executable, str(SCRIPT), "--candidates", str(p), "--today", "2026-10-16"])
        self.assertEqual(0, f.returncode, f.stderr + f.stdout)
        out = json.loads(f.stdout)
        self.assertTrue(out["results"][0]["deep_dig"])
        p.unlink()

    def test_future_evidence_date_rejected(self):
        """复评驳回#1：未来日期（2027-xx）不能当 real 证据放过。"""
        p = write([{"title": "明年才发生的未来趋势", "direction": "",
                    "evidence_url": "https://example.com/x", "evidence_date": "2027-05-01",
                    "payment_signal": "有人付费订阅"}])
        f = run([sys.executable, str(SCRIPT), "--candidates", str(p), "--today", "2026-10-16"])
        out = json.loads(f.stdout)
        self.assertIn("future_evidence", out["results"][0]["flags"])
        self.assertFalse(out["results"][0]["deep_dig"])
        p.unlink()

    def test_today_and_past_dates_are_real(self):
        """复评驳回#1 对照：今天与过去正常日期不被误判 future。"""
        p = write([
            {"title": "今天的新鲜证据", "direction": "", "evidence_url": "https://example.com/a",
             "evidence_date": "2026-10-16", "payment_signal": "付费订阅"},
            {"title": "一周前的证据", "direction": "", "evidence_url": "https://example.com/b",
             "evidence_date": "2026-10-09", "payment_signal": "付费订阅"},
        ])
        f = run([sys.executable, str(SCRIPT), "--candidates", str(p), "--today", "2026-10-16"])
        out = json.loads(f.stdout)
        for r in out["results"]:
            self.assertNotIn("future_evidence", r["flags"], r)
        p.unlink()


if __name__ == "__main__":
    unittest.main()
