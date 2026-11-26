#!/usr/bin/env python3
"""code-bugfix 契约、引用完整性与脱敏检查回归测试。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent


class CodeBugfixContractTests(unittest.TestCase):
    def test_required_files_and_references_exist(self):
        skill_md = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: code-bugfix", skill_md)
        refs = re.findall(r"references/([a-z0-9-]+\.md)", skill_md)
        self.assertIn("repro-ladder.md", refs)
        self.assertIn("failure-patterns.md", refs)
        self.assertIn("engineering-workspace.md", refs)
        for name in ("repro-ladder.md", "failure-patterns.md"):
            self.assertTrue((SKILL_ROOT / "references" / name).is_file(), name)

    def test_red_loop_and_redaction_rules_present(self):
        skill_md = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for marker in ("红灯", "<REDACTED>", "3 个假设", "Sibling Sweep", "resolved with caveats"):
            self.assertIn(marker, skill_md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
