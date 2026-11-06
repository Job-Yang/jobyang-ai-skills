#!/usr/bin/env python3
"""rotate.py 回归：方向轮换确定性 + 周期覆盖 + 历史覆盖感知（标准库 unittest）。"""
import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "rotate.py"


def run(date, coverage=None):
    cmd = [sys.executable, str(SCRIPT), "--date", date]
    if coverage:
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(coverage, f)
        f.close()
        cmd += ["--coverage", f.name]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p


class RotateTest(unittest.TestCase):
    def test_deterministic(self):
        a = run("2026-10-16").stdout
        b = run("2026-10-16").stdout
        self.assertEqual(a, b, "同一日期两次输出必须逐字一致")

    def test_anchor_rotates_through_pool_over_a_cycle(self):
        """连续 6 天，anchor 应遍历方向池每个方向一次（周期覆盖）。"""
        anchors = []
        for i in range(6):
            d = (dt.date(2026, 10, 16) + dt.timedelta(days=i)).isoformat()
            out = json.loads(run(d).stdout)
            anchors.append(out["anchor"])
        self.assertEqual(6, len(set(anchors)), f"6 天 anchor 不重复：{anchors}")

    def test_selected_has_no_duplicate_direction(self):
        out = json.loads(run("2026-10-16").stdout)
        self.assertEqual(2, len(out["selected"]))
        self.assertEqual(2, len(set(out["selected"])), "anchor 与补位不能是同一个方向")
        self.assertTrue(out["queries"], "每天必须输出可照抄的查询词")

    def test_coverage_prefers_longest_not_scanned(self):
        """除 wishes 外都刚扫过 → 补位必须选最久没扫的 wishes。"""
        today = "2026-10-16"
        pool = json.loads((ROOT / "references" / "rotation-pool.json").read_text(encoding="utf-8"))["pool"]
        others = [d["id"] for d in pool if d["id"] != "demand-sweep"]
        coverage = {today: others}
        out = json.loads(run(today, coverage).stdout)
        self.assertIn("demand-sweep", out["selected"], out)

    def test_bad_date_rejected(self):
        p = run("not-a-date")
        self.assertEqual(2, p.returncode)
        self.assertEqual("rejected", json.loads(p.stderr)["status"])


if __name__ == "__main__":
    unittest.main()
