#!/usr/bin/env python3
"""implement-spec 模板与工作区守卫联动测试。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SKILL_ROOT = Path(__file__).resolve().parent.parent
ISOLATED_GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


class ImplementSpecContractTests(unittest.TestCase):
    def setUp(self):
        env_patch = patch.dict(os.environ, ISOLATED_GIT_ENV)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def test_references_and_shared_scripts_present(self):
        skill_md = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for rel in (
            "references/engineering-workspace.md",
            "references/big-repo-safety.md",
            "references/spec-template.md",
            "references/deep-module-design.md",
            "scripts/workspace_guard.py",
        ):
            self.assertIn(rel, skill_md)
            self.assertTrue((SKILL_ROOT / rel).is_file(), f"missing {rel}")

    def test_workspace_guard_cli_detect_and_verify(self):
        guard = SKILL_ROOT / "scripts" / "workspace_guard.py"
        with tempfile.TemporaryDirectory(prefix="impl-spec-") as td:
            root = Path(td)
            subprocess.run(["git", "init"], cwd=str(root), capture_output=True, check=True)
            r = subprocess.run([sys.executable, str(guard), "init-local", "--root", str(root)],
                               capture_output=True, text=True)
            self.assertEqual(0, r.returncode, r.stderr)
            feat = root / ".agent-work" / "feature" / "demo.md"
            feat.write_text("# Demo\nStatus: decided\n", encoding="utf-8")
            sha = subprocess.check_output([sys.executable, str(guard), "hash", str(feat)], text=True).strip()
            spec = root / ".agent-work" / "spec" / "demo.md"
            spec.write_text(
                f"# Demo Spec\n\nSource: `.agent-work/feature/demo.md` @ `{sha}`\n\n"
                "## Steps\n\n1. Step one. After: none. Check: `true`\n",
                encoding="utf-8",
            )
            vr = subprocess.run([sys.executable, str(guard), "verify-hash", "--spec", str(spec), "--root", str(root)],
                                capture_output=True, text=True)
            self.assertEqual(0, vr.returncode, vr.stdout + vr.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
