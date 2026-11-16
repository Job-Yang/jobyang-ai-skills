#!/usr/bin/env python3
"""quick/full 方法契约与引用完整性测试。"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


class QuickRouteContractTest(unittest.TestCase):
    def test_name_and_route_criteria_are_self_contained(self):
        skill = read("SKILL.md")
        self.assertIn('name: "style-compass"', skill)
        for term in ("基础单页", "简单组件", "直接做一版", "现有页面", "多页面跨角色", "新设计系统", "OPC"):
            self.assertIn(term, skill)
        self.assertIn("不要只按页数分流", skill)

    def test_quick_exemptions_delivery_and_verification(self):
        quick = read("references/quick-ui.md")
        for term in ("不问样式", "8–12", "固定“空间画室”工作台", "全量 `DESIGN.md`", "完整 prototype 代码",
                     "实际使用的 tokens", "--phase final --tokens", "独立 Playwright", "桌面与移动", "最多集中修复一轮",
                     "未视觉验收", "不证明页面更好看", "正式审批记录"):
            self.assertIn(term, quick)

    def test_full_scopes_keep_formal_gates(self):
        skill = read("SKILL.md")
        stage = read("references/stage-contracts.md")
        review = read("references/review-framework.md")
        self.assertIn("full 的原多方向协议、正式阶段校验和固定工作台全部保留", skill)
        self.assertIn("只适用于 full 与 OPC", "\n".join(stage.splitlines()[:6]))
        self.assertIn("只适用于 full 与 OPC", "\n".join(review.splitlines()[:6]))

    def test_referenced_markdown_exists(self):
        texts = [read("SKILL.md"), read("references/quick-ui.md")]
        targets = set(re.findall(r"references/([a-z0-9-]+\.md)", texts[0]))
        targets.update(re.findall(r"`([a-z0-9-]+\.md)`", texts[1]))
        self.assertTrue(targets)
        self.assertEqual([], [name for name in sorted(targets) if not (ROOT / "references" / name).is_file()])


if __name__ == "__main__":
    unittest.main()
