#!/usr/bin/env python3
"""spec-battle 漂移熔断与已落地步骤过滤回归测试。"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SKILL_ROOT = Path(__file__).resolve().parent.parent
ISOLATED_GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


class SpecBattleContractTests(unittest.TestCase):
    def setUp(self):
        env_patch = patch.dict(os.environ, ISOLATED_GIT_ENV)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def test_references_and_protocol_markers(self):
        skill_md = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for rel in ("references/engineering-workspace.md", "references/prosecution.md", "scripts/workspace_guard.py"):
            self.assertIn(rel, skill_md)
            self.assertTrue((SKILL_ROOT / rel).is_file(), rel)
        for token in ("Refute", "Fix", "Open", "Out of scope", "Hand-off", "verify-hash"):
            self.assertIn(token, skill_md)

    def test_stale_upstream_triggers_fuse_and_skips_landed_steps(self):
        sys.path.insert(0, str(SKILL_ROOT / "scripts"))
        import workspace_guard as wg  # noqa: E402

        with tempfile.TemporaryDirectory(prefix="battle-fuse-") as td:
            root = Path(td)
            subprocess.run(["git", "init"], cwd=str(root), capture_output=True, check=True)
            subprocess.run(["git", "config", "user.email", "local-test"], cwd=str(root), capture_output=True, check=True)
            subprocess.run(["git", "config", "user.name", "T"], cwd=str(root), capture_output=True, check=True)
            wg.main(["init-local", "--root", str(root)])
            feat = root / ".agent-work" / "feature" / "x.md"
            feat.write_text("# X\n", encoding="utf-8")
            sha = wg.git_blob_sha1(feat)
            spec = root / ".agent-work" / "spec" / "x.md"
            spec.write_text(
                f"# X Spec\nSource: `.agent-work/feature/x.md` @ `{sha}`\n\n"
                "## Steps\n1. S1. After: none. Check: `true`\n2. S2. After: 1. Check: `true`\n",
                encoding="utf-8",
            )
            wg.main(["record-step", "--slug", "x", "--step", "1", "--sha", "deadbeef", "--root", str(root)])
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                wg.main(["progress", "--spec", str(spec), "--root", str(root)])
            prog = json.loads(buf.getvalue())
            self.assertEqual([1], prog["landed"])
            self.assertEqual([2], prog["ready"])

            feat.write_text("# X changed\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = wg.main(["verify-hash", "--spec", str(spec), "--root", str(root)])
            self.assertEqual(2, rc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
