#!/usr/bin/env python3
"""vdd 终审协议、对抗评测与文案一致性回归测试。"""
from __future__ import annotations

import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent


class VddContractTests(unittest.TestCase):
    def test_skill_readme_and_adversarial_panel_contract(self):
        skill_md = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        panel_path = SKILL_ROOT / "references" / "adversarial-panel.md"
        readme_path = SKILL_ROOT / "README.md"

        self.assertTrue(panel_path.is_file())
        self.assertTrue(readme_path.is_file())

        self.assertIn("references/adversarial-panel.md", skill_md)
        self.assertIn("符合设计，不用改", skill_md)
        self.assertIn("局部微改／文案笔误", skill_md)

        panel_txt = panel_path.read_text(encoding="utf-8")
        self.assertIn("过度防御与可逆摩擦一票否决", panel_txt)
        self.assertNotIn("插件钩子", panel_txt)
        self.assertNotIn("钩子规则", panel_txt)

        readme_txt = readme_path.read_text(encoding="utf-8")
        self.assertNotIn("第二部分", readme_txt)
        self.assertIn("第三节", readme_txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
