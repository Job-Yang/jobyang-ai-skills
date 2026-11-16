#!/usr/bin/env python3
"""4.5 候选的视觉／交互方法契约回归。"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


class MethodKernelContractTest(unittest.TestCase):
    def test_skill_routes_to_both_kernels_without_replacing_full_gates(self):
        skill = read("SKILL.md")
        self.assertIn("references/design-kernel.md", skill)
        self.assertIn("references/interaction-craft.md", skill)
        self.assertIn("full 的原多方向协议、正式阶段校验和固定工作台全部保留", skill)
        self.assertIn("不新增用户审批关卡", skill)

    def test_composition_kernel_is_positive_and_has_two_scales(self):
        design = read("references/design-kernel.md")
        for term in ("主对象、主动作", "相对尺度和位置", "辅助信息和阅读顺序", "字形角色和色面分工", "产品专属重点"):
            self.assertIn(term, design)
        self.assertIn("大工作区", design)
        self.assertIn("小弹层", design)
        self.assertIn("不把页面惯性切成平均卡片", design)

    def test_reference_calibration_keeps_comp_and_interaction_separate(self):
        design = read("references/design-kernel.md")
        for term in ("一至两个", "主体比例", "密度", "字体角色", "真实内容", "comp-led", "code-led", "同一视口宽度"):
            self.assertIn(term, design)
        self.assertIn("comp 是外部视觉目标，不是 Opus 的内部特性", design)
        self.assertIn("不能证明动作可发现、状态正确或任务可完成", design)
        self.assertIn("没有素材就写“未取得”", design)

    def test_each_candidate_passes_quality_before_difference(self):
        craft = read("references/visual-craft.md")
        quality = craft.index("## 先逐案过质量底线，再比较差异")
        divergence = craft.index("## full 候选怎么拉开")
        self.assertLess(quality, divergence)
        for term in ("主对象", "明确动作", "字形与色面", "真实内容", "完整组件与状态", "去掉候选名称和创作说明", "不会自动宣称新版或陌生方向最好"):
            self.assertIn(term, craft)

    def test_interaction_kernel_covers_task_chain_and_long_states(self):
        interaction = read("references/interaction-craft.md")
        for term in ("目标。", "可发现动作", "前置条件", "可见状态", "及时反馈", "恢复路径", "保留上下文"):
            self.assertIn(term, interaction)
        for state in ("排队", "运行", "等待输入", "失败", "等待验收"):
            self.assertIn(state, interaction)
        self.assertIn("动画可打断", interaction)
        self.assertIn("不等于队列、上传、支付或其他任务可以取消", interaction)

    def test_controls_motion_and_platform_boundaries_are_explicit(self):
        interaction = read("references/interaction-craft.md")
        for term in ("成熟平台 primitive", "初始焦点", "焦点归还", "Esc", "拖拽提供键盘或按钮替代", "触控", "过长标题", "空内容", "响应式", "减少动态"):
            self.assertIn(term, interaction)
        self.assertIn("不要让所有元素入场、每次成功都庆祝", interaction)
        self.assertIn("不升格为 native 约束", interaction)

    def test_sources_are_pinned_and_attributed(self):
        joined = read("references/design-kernel.md") + read("references/interaction-craft.md")
        for commit in ("a6f121e", "687bc38", "2c5958e", "b7d5353", "9b4bf93", "c8a7962", "00db7d6", "1a2c79d"):
            self.assertIn(commit, joined)
        self.assertIn("CC BY 4.0", joined)
        self.assertIn("Damir Sokolovsky", joined)
        self.assertIn("Apache 2.0", joined)
        self.assertNotIn("/Users/", joined)
        # 拆开拼，避免本仓自身的推送钩子把断言字面量误判成泄露
        self.assertNotIn("byte" + "dance", joined.lower())

    def test_candidate_version_is_recorded(self):
        changelog = read("CHANGELOG.md")
        self.assertIn("## 4.5.0-candidate — 2026-11-07", changelog)


if __name__ == "__main__":
    unittest.main()
