#!/usr/bin/env python3
"""go-work 双轨进度（repo trailer + local state）与归档全流程回归测试。"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent


class GoWorkFlowTests(unittest.TestCase):
    def _git(self, cwd: Path, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def _init_repo(self, root: Path) -> None:
        self._git(root, "init")
        self._git(root, "config", "user.email", "local-test")
        self._git(root, "config", "user.name", "T")
        (root / "README.md").write_text("hi\n", encoding="utf-8")
        self._git(root, "add", "README.md")
        self._git(root, "commit", "-m", "init")

    def test_contract_links_exist(self):
        skill_md = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for rel in ("references/engineering-workspace.md", "references/runner-protocol.md", "scripts/workspace_guard.py"):
            self.assertIn(rel, skill_md)
            self.assertTrue((SKILL_ROOT / rel).is_file(), rel)

    def test_repo_and_local_end_to_end_resume_and_archive(self):
        sys.path.insert(0, str(SKILL_ROOT / "scripts"))
        import workspace_guard as wg  # noqa: E402

        # 1) repo mode: trailer resume + archive
        with tempfile.TemporaryDirectory(prefix="gw-repo-") as td:
            root = Path(td)
            self._init_repo(root)
            (root / "docs" / "feature").mkdir(parents=True)
            (root / "docs" / "spec").mkdir(parents=True)
            feat = root / "docs" / "feature" / "pay.md"
            feat.write_text("# Pay\nStatus: decided\n", encoding="utf-8")
            sha = wg.git_blob_sha1(feat)
            spec = root / "docs" / "spec" / "pay.md"
            spec.write_text(
                f"# Pay Spec\nSource: `docs/feature/pay.md` @ `{sha}`\n\n"
                "## Steps\n"
                "1. Step A. After: none. Check: `true`\n"
                "2. Step B. After: 1. Check: `true`\n"
                "3. Step C. After: 1. Check: `true`\n",
                encoding="utf-8",
            )
            self._git(root, "add", "docs")
            self._git(root, "commit", "-m", "add spec")

            (root / "a.txt").write_text("a\n", encoding="utf-8")
            self._git(root, "add", "a.txt")
            self._git(root, "commit", "-m", "Implement A\n\nSpec-Step: pay#1")

            with contextlib.redirect_stdout(io.StringIO()) as buf:
                wg.main(["progress", "--spec", str(spec), "--root", str(root)])
            prog = json.loads(buf.getvalue())
            self.assertEqual([1], prog["landed"])
            self.assertEqual([2, 3], prog["ready"])

            (root / "b.txt").write_text("b\n", encoding="utf-8")
            self._git(root, "add", "b.txt")
            self._git(root, "commit", "-m", "Implement B\n\nSpec-Step: pay#2")
            (root / "c.txt").write_text("c\n", encoding="utf-8")
            self._git(root, "add", "c.txt")
            self._git(root, "commit", "-m", "Implement C\n\nSpec-Step: pay#3")

            with contextlib.redirect_stdout(io.StringIO()):
                wg.main(["archive", "--spec", str(spec), "--root", str(root), "--date", "2026-11-26"])
            self.assertFalse(spec.exists())
            self.assertTrue((root / "docs" / "spec" / "archived" / "2026-11-26-pay.md").is_file())
            self.assertEqual("*\n", (root / "docs" / "spec" / "archived" / ".ignore").read_text(encoding="utf-8"))

        # 2) local mode: zero git status pollution
        with tempfile.TemporaryDirectory(prefix="gw-local-") as td:
            root = Path(td)
            self._init_repo(root)
            wg.main(["init-local", "--root", str(root)])
            spec = root / ".agent-work" / "spec" / "fix.md"
            spec.write_text("# Fix Spec\nSource: none\n\n## Steps\n1. Fix. After: none. Check: `true`\n", encoding="utf-8")
            wg.main(["record-step", "--slug", "fix", "--step", "1", "--sha", "abc123", "--root", str(root)])
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                wg.main(["progress", "--spec", str(spec), "--root", str(root)])
            self.assertEqual([], json.loads(buf.getvalue())["ready"])
            with contextlib.redirect_stdout(io.StringIO()):
                wg.main(["archive", "--spec", str(spec), "--root", str(root), "--date", "2026-11-26"])
            self.assertEqual("", self._git(root, "status", "--short"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
