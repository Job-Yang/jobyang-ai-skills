import io
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import github_trending as gt  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "trending_weekly.html")


class TestTrendingParse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with io.open(FIXTURE, "r", encoding="utf-8") as f:
            cls.doc = f.read()
        cls.repos = gt.parse_trending(cls.doc, "weekly")

    def test_parses_all_rows_in_order(self):
        self.assertGreaterEqual(len(self.repos), 14)
        self.assertEqual(self.repos[0]["repo"], "morluto/rea")

    def test_weekly_gained_stars_real_number(self):
        by = {r["repo"]: r for r in self.repos}
        rea = by["morluto/rea"]
        self.assertEqual(rea["stars_gained"], 201065)
        self.assertIsInstance(rea["stars_total"], int)
        self.assertGreater(rea["stars_total"], rea["stars_gained"])
        self.assertIn("stars this week", rea["gained_label"])
        self.assertTrue(rea["url"].startswith("https://github.com/morluto/rea"))

    def test_every_row_has_core_fields(self):
        for r in self.repos:
            self.assertTrue(r["repo"].count("/") == 1)
            self.assertTrue(r["url"].startswith("https://github.com/"))
            self.assertIsNotNone(r["stars_gained"], r["repo"])
            self.assertNotEqual(r["description"].strip(), "")

    def test_daily_parser_does_not_steal_weekly_label(self):
        # A weekly "stars this week" page parsed with range=daily must not
        # mislabel gains; this guards the period-word coupling.
        daily = gt.parse_trending(self.doc, "daily")
        self.assertIsNone(daily[0]["stars_gained"])

    def test_cli_file_mode_outputs_json(self):
        import subprocess
        out = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "github_trending.py"),
             "--range", "weekly", "--html", FIXTURE, "--top", "3"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["range"], "weekly")
        self.assertEqual(payload["count"], 3)
        self.assertFalse(payload["fetched"])
        self.assertEqual(payload["repos"][0]["repo"], "morluto/rea")


if __name__ == "__main__":
    unittest.main()
