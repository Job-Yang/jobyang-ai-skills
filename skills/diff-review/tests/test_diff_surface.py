#!/usr/bin/env python3
"""diff-review 表面分析脚本与契约回归测试（零外部依赖）。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import diff_surface as ds  # noqa: E402


class DiffSurfaceTests(unittest.TestCase):
    def _git(self, cwd: Path, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def _init_repo(self, root: Path) -> None:
        self._git(root, "init")
        self._git(root, "config", "user.email", "local-test")
        self._git(root, "config", "user.name", "Test")
        (root / "app.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
        self._git(root, "add", "app.py")
        self._git(root, "commit", "-m", "init")

    def test_empty_quick_standard_and_high_risk_deep(self):
        with tempfile.TemporaryDirectory(prefix="diff-surf-") as td:
            root = Path(td)
            self._init_repo(root)

            # Empty
            res = ds.analyze_surface(root)
            self.assertEqual("Empty", res["depth"])
            self.assertEqual(0, res["file_count"])

            # Quick (with untracked file)
            (root / "notes.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
            res = ds.analyze_surface(root)
            self.assertEqual("Quick", res["depth"])
            self.assertEqual(1, res["untracked_count"])

            # Standard (>=100 lines)
            (root / "notes.py").write_text("\n".join(f"x_{i} = {i}" for i in range(120)) + "\n", encoding="utf-8")
            res = ds.analyze_surface(root)
            self.assertEqual("Standard", res["depth"])

            # High risk path triggers Deep + human_review_needed even if tiny
            (root / "notes.py").unlink()
            (root / "auth").mkdir()
            (root / "auth" / "jwt.py").write_text("def verify():\n    return True\n", encoding="utf-8")
            res = ds.analyze_surface(root)
            self.assertEqual("Deep", res["depth"])
            self.assertTrue(res["human_review_needed"])
            self.assertIn("auth", res["human_review_tags"])

    def test_branch_range_analysis(self):
        with tempfile.TemporaryDirectory(prefix="diff-range-") as td:
            root = Path(td)
            self._init_repo(root)
            base_branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD")
            self._git(root, "checkout", "-b", "feat/demo")
            (root / "app.py").write_text("def ok():\n    return 2\n", encoding="utf-8")
            self._git(root, "add", "app.py")
            self._git(root, "commit", "-m", "update ok")

            res = ds.analyze_surface(root, f"{base_branch}...HEAD")
            self.assertEqual("Quick", res["depth"])
            self.assertEqual(1, res["file_count"])
            self.assertEqual(0, res["untracked_count"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
