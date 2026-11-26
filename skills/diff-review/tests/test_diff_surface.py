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

    def test_range_option_injection_rejected(self):
        with tempfile.TemporaryDirectory(prefix="diff-inj-") as td:
            root = Path(td)
            self._init_repo(root)
            victim = root / "pwned.txt"
            with self.assertRaises(RuntimeError):
                ds.analyze_surface(root, f"--output={victim}")
            self.assertFalse(victim.exists())
            with self.assertRaises(RuntimeError):
                ds.analyze_surface(root, f"--ext-diff..HEAD")

    def test_rename_detection_tests_exclusion_and_extended_delete_suffixes(self):
        with tempfile.TemporaryDirectory(prefix="diff-ren-") as td:
            root = Path(td)
            self._init_repo(root)
            (root / "schema.sql").write_text("CREATE TABLE t(id INT);\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "helper.py").write_text("def x():\n    return 1\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "auth").mkdir()
            (root / "tests" / "auth" / "test_login.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
            self._git(root, "add", "schema.sql", "src/helper.py", "tests/auth/test_login.py")
            self._git(root, "commit", "-m", "add files")

            base_branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD")
            self._git(root, "checkout", "-b", "feat/refactor")
            # 1) 测试目录高危关键词不触发生产风险
            (root / "tests" / "auth" / "test_login.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
            res_test_only = ds.analyze_surface(root)
            self.assertEqual({}, res_test_only["risk_tags"])
            self.assertFalse(res_test_only["human_review_needed"])

            # 2) 重命名迁入 auth/ 与删除 .sql 均需准确识别
            (root / "auth").mkdir()
            self._git(root, "mv", "src/helper.py", "auth/helper.py")
            self._git(root, "rm", "schema.sql")
            self._git(root, "add", "tests/auth/test_login.py")
            self._git(root, "commit", "-m", "move to auth and drop sql")

            res = ds.analyze_surface(root, f"{base_branch}...HEAD")
            self.assertEqual("Deep", res["depth"])
            self.assertIn("auth", res["risk_tags"])
            self.assertIn("auth/helper.py", res["risk_tags"]["auth"])
            self.assertIn("delete", res["risk_tags"])
            self.assertIn("schema.sql", res["risk_tags"]["delete"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
