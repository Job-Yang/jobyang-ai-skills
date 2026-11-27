#!/usr/bin/env python3
"""engineering-flow 纯原则规则插件静态校验测试（零后台 Hook）。"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PLUGIN_DIR.parent.parent


class EngineeringFlowPluginTests(unittest.TestCase):
    def test_plugin_manifest_and_zero_hooks(self):
        plugin_cfg = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("engineering-flow", plugin_cfg["name"])

        hooks_cfg = json.loads((PLUGIN_DIR / "hooks.json").read_text(encoding="utf-8"))["engineering-flow"]
        self.assertIs(False, hooks_cfg["enabled"])
        for event in ("PreInvocation", "PreToolUse", "PostToolUse", "Stop"):
            self.assertNotIn(event, hooks_cfg)

        self.assertFalse((PLUGIN_DIR / "hooks").exists())
        self.assertFalse((PLUGIN_DIR / "hooks" / "flow_hook.py").exists())
        self.assertFalse((PLUGIN_DIR / "tests" / "test_flow_hook.py").exists())

    def test_rules_concise_first_principles_and_valid_skill_refs(self):
        rules_path = PLUGIN_DIR / "rules" / "AGENTS.md"
        self.assertTrue(rules_path.is_file())
        text = rules_path.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        self.assertLessEqual(len(lines), 15)
        for marker in ("可逆", "不可逆", "禁止教条"):
            self.assertIn(marker, text)

        skills_dir = REPO_ROOT / "skills"
        for name in ("implement-spec", "spec-battle", "go-work", "code-bugfix", "diff-review", "pr-prep", "vdd"):
            self.assertIn(name, text)
            self.assertTrue((skills_dir / name / "SKILL.md").is_file(), f"missing skill {name}")

        # 确保未保留旧版机械钩子强制语
        self.assertIsNone(re.search(r"flow_hook|只读红线", text))


if __name__ == "__main__":
    unittest.main(verbosity=2)
