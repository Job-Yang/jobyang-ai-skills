#!/usr/bin/env python3
"""pr-prep 离线 HTML 视觉导览与防仓内污染回归测试（零外部依赖）。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import pr_visual_report as pvr  # noqa: E402


class PrVisualReportTests(unittest.TestCase):
    def _git(self, cwd: Path, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def test_contract_and_visual_report_generation(self):
        skill_md = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for rel in (
            "references/engineering-workspace.md",
            "references/big-repo-safety.md",
            "references/pr-checklist.md",
            "scripts/pr_visual_report.py",
        ):
            self.assertIn(rel, skill_md)
            self.assertTrue((SKILL_ROOT / rel).is_file(), rel)

        with tempfile.TemporaryDirectory(prefix="pr-repo-") as td, \
             tempfile.TemporaryDirectory(prefix="pr-out-") as out_td:
            root = Path(td)
            self._git(root, "init")
            self._git(root, "config", "user.email", "local-test")
            self._git(root, "config", "user.name", "T")
            (root / "README.md").write_text("base\n", encoding="utf-8")
            self._git(root, "add", "README.md")
            self._git(root, "commit", "-m", "init")
            base_branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD")

            self._git(root, "checkout", "-b", "feat/payment-v2")
            (root / "migrations").mkdir()
            (root / "migrations" / "001_init.sql").write_text("CREATE TABLE t(id INT);\n", encoding="utf-8")
            (root / "billing").mkdir()
            (root / "billing" / "charge.py").write_text(
                "def charge():\n    return '<script>alert(1)</script>'\n", encoding="utf-8"
            )
            self._git(root, "add", "migrations", "billing")
            self._git(root, "commit", "-m", "Add billing & migration <test>")

            data = pvr.collect_pr_data(root, base_branch)
            self.assertIn("migration", data["risk_tags"])
            self.assertIn("billing", data["risk_tags"])

            html_path, md_path = pvr.write_reports(data, Path(out_td))
            self.assertTrue(html_path.is_file())
            self.assertTrue(md_path.is_file())

            html_txt = html_path.read_text(encoding="utf-8")
            self.assertNotIn("<script src=", html_txt)
            self.assertNotIn("https://", html_txt)
            self.assertIn("&lt;test&gt;", html_txt)
            self.assertIn("PR 视觉导览", html_txt)

            # 禁止写入业务仓内部
            with self.assertRaises(RuntimeError):
                pvr.write_reports(data, root / "reports")

            # 代码仓工作树保持零污染
            self.assertEqual("", self._git(root, "status", "--short"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
