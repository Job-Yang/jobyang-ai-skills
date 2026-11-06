#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""talk_check.py 的单元测试（纯标准库 unittest）。运行：python3 -m unittest -v。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import talk_check  # noqa: E402


class TestTalkCheck(unittest.TestCase):

    def _err_keys(self, errors):
        return " | ".join(errors)

    def test_forbidden_opener_detected(self):
        text = (
            "我最近撞上一件事，数字是 8。\n\n"
            "本文将介绍 Mamba 的原理。\n\n"
            "## 背景\n正文段落。\n\n结尾你可以试试。"
        )
        errors, warns, _ = talk_check.check("article", text)
        self.assertIn("开头禁用导语", self._err_keys(errors))

    def test_unverified_mark_detected(self):
        text = (
            "开头有数字 8 倍。\n\n"
            "## 一\n这里的结论待核实。\n\n"
            "## 二\n结尾明天动手。"
        )
        errors, _, _ = talk_check.check("article", text)
        self.assertIn("待核实", self._err_keys(errors))

    def test_halfwidth_punctuation_detected(self):
        text = (
            "开头有数字 8。\n\n"
            "## 一\n他说做完了,然后就走了。\n\n"
            "## 二\n结尾明天动手。"
        )
        errors, _, _ = talk_check.check("article", text)
        self.assertIn("半角", self._err_keys(errors))

    def test_clean_sample_has_no_error(self):
        text = (
            "我最近撞上一件事，数字是 8，「它自己揪出三个问题」。\n\n"
            "## 一\n机制段落，通俗层讲清楚。\n\n"
            "## 二\n进阶层给复杂度 O(N)。\n\n"
            "## 三\n反直觉点单独成节。\n\n"
            "## 四\n拆台划边界。\n\n"
            "## 五\n可搬走的三块硬货。\n\n"
            "结尾你可以明天就动手试试。"
        )
        errors, warns, stats = talk_check.check("article", text)
        self.assertEqual(errors, [], f"干净样例不应有 ERROR：{errors}")
        self.assertGreaterEqual(stats["h2"], 5)

    def test_hook_missing_warns_not_errors(self):
        # 前3段没有数字/引语/问句 → WARN，不是 ERROR
        text = (
            "我们来聊一聊一个常见的技术话题。\n\n"
            "## 一\n正文。\n\n"
            "## 二\n结尾明天动手。"
        )
        errors, warns, _ = talk_check.check("article", text)
        self.assertIn("钩子", " | ".join(warns))
        self.assertEqual(errors, [])

    def test_word_count_warns_when_thin(self):
        text = "开头数字 8。\n\n## 一\n短。\n\n结尾明天动手。"
        errors, warns, stats = talk_check.check("article", text)
        self.assertTrue(any("中文字数" in w for w in warns))
        self.assertLess(stats["cn"], 2000)

    def test_article_hint_warns_when_no_advanced(self):
        # article 态但通篇无进阶层机制标记 → 文体 WARN（不判路由，只提示）
        text = (
            "开头有数字 8。\n\n"
            "## 一\n我认为这个观点不对。\n\n"
            "## 二\n纯属判断，没有机制。\n\n"
            "## 三\n结尾明天动手。"
        )
        errors, warns, _ = talk_check.check("article", text)
        self.assertTrue(any("[文体]" in w and "进阶层" in w for w in warns))
        self.assertEqual(errors, [])

    def test_article_no_hint_when_advanced_present(self):
        # article 态且有进阶层机制 + 可搬走动作 → 不应再报文体提示
        text = (
            "开头数字 8。\n\n"
            "## 一\n复杂度是 O(N)，进阶机制讲清楚。\n\n"
            "## 二\n矩阵运算展开。\n\n"
            "## 三\n你可以明天落地试试。"
        )
        errors, warns, _ = talk_check.check("article", text)
        wen = [w for w in warns if w.startswith("[文体]")]
        self.assertFalse(any("进阶层机制信号" in w for w in wen))
        self.assertFalse(any("可搬走" in w for w in wen))
        self.assertEqual(errors, [])

    # ---------- 旧败新胜回归（0.1.2 对抗实测修复） ----------

    def test_inline_code_masked_not_flagged(self):
        # 行内 code 内的半角逗号不应误报
        text = "开头数字 8。\n\n## 一\n调用 `compute(x, y)` 后，结果出来了。\n\n## 二\n结尾明天动手。"
        errors, _, _ = talk_check.check("article", text)
        self.assertNotIn("半角", self._err_keys(errors))

    def test_url_masked_not_flagged(self):
        # URL 后直接接中文，逗号随 URL 一起 mask，不应误报
        text = "开头数字 8。\n\n## 一\n看这个 https://example.com/bench,我们跑通了。\n\n## 二\n结尾明天动手。"
        errors, _, _ = talk_check.check("article", text)
        self.assertNotIn("半角", self._err_keys(errors))

    def test_unclosed_fence_reported(self):
        # 未闭合围栏：单独报"未闭合围栏"，且不把围栏内内容当正文扫
        text = (
            "开头数字 8。\n\n"
            "## 一\n这里有一段没闭合的代码：\n"
            "```\n"
            "print('x,我们')  # 围栏内的中文半角注释，不该当正文\n"
            "\n## 二\n结尾明天动手。"
        )
        errors, _, _ = talk_check.check("article", text)
        self.assertIn("未闭合围栏", self._err_keys(errors))

    def test_thousand_separator_not_flagged(self):
        # 千分位 1,000 数字夹逗号，不误报
        text = "开头数字 8。\n\n## 一\n产量是 1,000 件，不错。\n\n## 二\n结尾明天动手。"
        errors, _, _ = talk_check.check("article", text)
        self.assertNotIn("半角", self._err_keys(errors))

    def test_substantial_opinion_triggers_cuihuo_hint(self):
        # 旧败：满字数满 H2 的纯观点文（自然出现"层面/参数"）旧版因裸关键词漏报。
        # 新判据：无 O(·)/公式/进阶层标题/术语注释 → 稳定报"更像观点判断"。
        text = (
            "我认为验收权应当独立于实现权，这是这篇要讲的核心判断。\n\n"
            "## 一\n很多团队在这个层面上搞反了：把验收交给写实现的人，等于让运动员当裁判。"
            "你不能一边定规则一边下场踢，还宣布自己赢了。\n\n"
            "## 二\n从组织结构上看，验收这个参数不该由实现方自己设定，"
            "否则它一定会在进度压力下悄悄放宽。今天少测一个边界，明天就敢少写一整类用例。\n\n"
            "## 三\n我们在三个项目里都看到同一个现象：一旦验收权和实现权合一，"
            "验收标准就会在排期紧的时候漂移。这不是某个人不负责，是结构使然。\n\n"
            "## 四\n有人说那我们多写点自动化不就行了。没用，自动化用例还是实现方写的，"
            "它会照着自己想通过的方式去断言，测的是自己想听的话。\n\n"
            "## 五\n这不是技术问题，是权力结构问题，讨论再多技术方案也绕不开这一层。"
        )
        text += (
            "## 六\n所以我的结论很简单：把验收权从实现权里拆出去，单独成岗。"
            "谁验收、谁对什么负责、依据什么标准，这三件事必须和写代码的人分开。\n\n"
            "## 七\n拆出去之后，验收方不再为进度背锅，才敢说不过；"
            "实现方也不用一边赶工一边自我怀疑，责任清楚了，彼此反而更信任。\n\n"
            "## 八\n这听起来像管理常识，但落到工程里最难的不是想明白，"
            "而是在排期压顶的那个当口，肯为一个说不过的版本按下暂停。\n\n"
            "## 九\n至于怎么拆、拆多细、跨团队怎么对齐验收口径，那是另一篇文章的事，"
            "这里只立住这一个判断。\n\n"
            "## 十\n回到开头那句话：验收权独立于实现权，不是谁更敬业的问题，"
            "是这个系统还能不能信的问题。结尾明天动手。\n\n"
            "## 十一\n我知道有人会说，小团队哪有资源单设一个验收岗，"
            "两个人的事非要拆成三个人干，这不是增加成本吗。恰恰相反，"
            "小团队最贵的不是人力，是信任被一次说不过的发布耗光之后，"
            "每次上线都要靠喊来兜底的那个隐性成本。\n\n"
            "## 十二\n所以问题从来不是要不要独立，而是你打算为这种不独立付多久的账。"
            "今天按下的每一个说不过的版本，都会在三个月后变成线上一个说不清的事故，"
            "到那时再回头补验收，代价是现在的十倍。这就是我坚持这个判断的全部理由。\n\n"
        )
        errors, warns, stats = talk_check.check("article", text)
        wen = [w for w in warns if w.startswith("[文体]")]
        self.assertTrue(stats["cn"] >= 600, f"样例应算足够厚：{stats['cn']}")
        self.assertTrue(any("更像观点判断" in w for w in wen), f"应触发 cuihuo 提示：{wen}")
        self.assertEqual(errors, [])

    def test_mamba_like_no_false_positive(self):
        # 新胜：真技术分享（有复杂度 O(·)、机制讲解）不应误报"更像观点判断"
        text = (
            "开头数字 8 倍。\n\n"
            "## 一\nMamba 基于状态空间模型，递推 hₜ = A·hₜ₋₁ + B·xₜ。\n\n"
            "## 二\n它把复杂度从注意力的 O(N²) 压到 O(N)。\n\n"
            "## 三\n你可以明天落地试试。"
        )
        errors, warns, _ = talk_check.check("article", text)
        wen = [w for w in warns if w.startswith("[文体]")]
        self.assertFalse(any("更像观点判断" in w for w in wen))
        self.assertFalse(any("进阶层机制信号" in w for w in wen))
        self.assertEqual(errors, [])

    # ---------- 0.2.0 新结构项 WARN（只提示不强制，幽默永不 ERROR） ----------

    def test_tldr_missing_fields_warns_not_error(self):
        # 出现 TL;DR 但缺字段 → WARN，不是 ERROR
        text = (
            "开头数字 8。\n\n"
            "## TL;DR\n- 干了啥：做了一个工具。\n\n"
            "## 一\n复杂度 O(N)，机制讲清楚。\n\n"
            "## 二\n你可以明天落地试试。"
        )
        errors, warns, _ = talk_check.check("article", text)
        self.assertTrue(any("TL;DR 卡片缺字段" in w and "最大的坑" in w for w in warns))
        self.assertEqual(errors, [])

    def test_tldr_all_fields_no_warn(self):
        # 五字段齐全 → 不报缺字段 WARN
        text = (
            "开头数字 8。\n\n"
            "## TL;DR\n"
            "- 干了啥：做了一个工具。\n"
            "- 最大的坑：反馈链断了。\n"
            "- 真正的收获：沉淀了一套方法。\n"
            "- 这篇讲：怎么补这条链。\n"
            "- 最后引出：下一步方向。\n\n"
            "## 一\n复杂度 O(N)，机制讲清楚。\n\n"
            "## 二\n你可以明天落地试试。"
        )
        errors, warns, _ = talk_check.check("article", text)
        self.assertFalse(any("TL;DR 卡片缺字段" in w for w in warns))
        self.assertEqual(errors, [])

    def test_series_without_prev_next_warns(self):
        # 提到系列/第几篇但缺上一篇/下一篇交代 → WARN
        text = (
            "开头数字 8。\n\n"
            "## 一\n这是系列第二篇，本篇接着前一篇往下讲。\n\n"
            "## 二\n复杂度 O(N)。\n\n"
            "## 三\n你可以明天落地试试。"
        )
        errors, warns, _ = talk_check.check("article", text)
        self.assertTrue(any("上一篇/下一篇" in w for w in warns))
        self.assertEqual(errors, [])

    def test_first_data_section_optional_warn(self):
        # 9c 仅对复盘/成果型长文（≥1500 字）且既无 TL;DR 也无成果节时提示；短文/非复盘不刷
        pad = "这一段把机制展开讲清楚，复杂度与边界都交代明白。" * 80
        no_data = (
            "开头数字 8。\n\n"
            "## 复盘\n" + pad + "\n\n"
            "## 二\n你可以明天落地试试。"
        )
        errors, warns, stats = talk_check.check("article", no_data)
        self.assertGreaterEqual(stats["cn"], 1500)
        self.assertTrue(any("先看数据" in w or "先看结果" in w or "成果节" in w for w in warns))
        self.assertEqual(errors, [])

        with_data = (
            "开头数字 8。\n\n"
            "## 先看结果\n数据看板一组。\n\n"
            "## 复盘\n" + pad + "\n\n"
            "## 二\n你可以明天落地试试。"
        )
        errors, warns, _ = talk_check.check("article", with_data)
        self.assertFalse(any("成果节" in w or "先看结果" in w for w in warns))
        self.assertEqual(errors, [])

        # 短文/非复盘型：不刷这条可选提示
        thin = (
            "开头数字 8。\n\n"
            "## 一\n复杂度 O(N)，机制讲清楚。\n\n"
            "## 二\n你可以明天落地试试。"
        )
        errors, warns, _ = talk_check.check("article", thin)
        self.assertFalse(any("成果节" in w for w in warns))
        self.assertEqual(errors, [])

    def test_formal_setting_cute_warns_not_error(self):
        # 事故/正式场合出现卖萌词 → WARN，幽默永不 ERROR
        text = (
            "开头数字 8。\n\n"
            "## 事故复盘\n这次故障的经过，绝绝子，客观陈述。\n\n"
            "## 一\n复杂度 O(N)。\n\n"
            "## 二\n你可以明天落地试试。"
        )
        errors, warns, _ = talk_check.check("article", text)
        self.assertTrue(any("正式/事故/声明场合" in w for w in warns))
        self.assertEqual(errors, [])

    def test_formal_setting_without_cute_no_warn(self):
        # 正式场合但无卖萌信号 → 不报该 WARN
        text = (
            "开头数字 8。\n\n"
            "## 事故复盘\n这次故障的经过与根因，客观陈述。\n\n"
            "## 一\n复杂度 O(N)。\n\n"
            "## 二\n你可以明天落地试试。"
        )
        errors, warns, _ = talk_check.check("article", text)
        self.assertFalse(any("正式/事故/声明场合" in w for w in warns))
        self.assertEqual(errors, [])

    # ---------- P1 旧败新胜：新默认结构不再被旧字面闸误报 ----------

    def test_tldr_card_opener_avoids_hook_warn(self):
        # 旧败：TL;DR 卡片开头（无数字/引语/问句）被旧闸误报"钩子缺失"。
        # 新胜：识别为合法开头，不报钩子缺失，且无 ERROR。
        text = (
            "> **TL;DR**\n"
            "> - **干了啥**：做了一个工具。\n"
            "> - **最大的坑**：反馈链断了。\n"
            "> - **真正的收获**：沉淀了一套方法。\n"
            "> - **这篇讲**：怎么补上这条链。\n"
            "> - **最后引出**：下一步方向。\n\n"
            "## 背景\n记住「反馈」这个词，下文反复提到。\n\n"
            "## 机制\n复杂度 O(N)，机制讲清楚。\n\n"
            "## 启示\n1. 先补回路。2. 人工兜底。3. 工具留下了。"
        )
        errors, warns, _ = talk_check.check("article", text)
        self.assertFalse(any("开头信号" in w or "钩子" in w for w in warns))
        self.assertEqual(errors, [])

    def test_insight_ending_compliant_no_warn(self):
        # 旧败：几点启示结尾（无明天动作词/无加粗金句）被旧闸误报结尾缺失。
        # 新胜：识别"几点启示"分节为合规结尾，不报缺失，且无 ERROR。
        text = (
            "开头数字 8。\n\n"
            "## 一\n复杂度 O(N)，机制讲清楚。\n\n"
            "## 几点启示\n"
            "1. 先补回路再调参。\n"
            "2. 半自动也要有人兜底。\n"
            "3. 没走完的路也留下了工具。"
        )
        errors, warns, _ = talk_check.check("article", text)
        self.assertFalse(any("结尾" in w for w in warns))
        self.assertEqual(errors, [])

    def test_live_hook_still_recognized_not_killed(self):
        # 现场钩子稿（画面+读者反驳问句）仍被识别为合法开头，不被新规则误杀
        text = (
            "凌晨两点，监控里还在吐同一条日志。你大概会反驳：重试不是早做熟了吗？\n\n"
            "## 一\n复杂度 O(N)，机制讲清楚。\n\n"
            "## 二\n你可以明天落地试试。"
        )
        errors, warns, _ = talk_check.check("article", text)
        self.assertFalse(any("开头信号" in w or "钩子" in w for w in warns))
        self.assertEqual(errors, [])

    def test_action_bold_ending_still_accepted(self):
        # 可选的明天动作/加粗金句结尾仍被接受（加分项不被移除）
        text = (
            "开头数字 8。\n\n"
            "## 一\n复杂度 O(N)，机制讲清楚。\n\n"
            "**一句加粗收口的判断。** 你可以明天动手试试。"
        )
        errors, warns, _ = talk_check.check("article", text)
        self.assertFalse(any("结尾" in w for w in warns))
        self.assertEqual(errors, [])

    def test_prose_wall_warns(self):
        long = "这次改造把冷启动从两秒压到八百毫秒，核心是把三个同步初始化挪到首帧之后，再把图片解码放进后台队列。" * 4
        text = "# 冷启动\n\n" + long + "\n\n" + "\n\n".join(["短段落一句话说完。"] * 4) + "\n"
        _, warns, _ = talk_check.check("article", text)
        joined = "\n".join(warns)
        self.assertIn("超过 150 字", joined)
        self.assertIn("段落墙", joined)

    def test_headings_and_lists_break_wall(self):
        text = "# 冷启动\n\n短段一。\n\n短段二。\n\n## 方案\n\n短段三。\n\n- 列表\n\n短段四。\n"
        _, warns, _ = talk_check.check("article", text)
        self.assertNotIn("段落墙", "\n".join(warns))


if __name__ == "__main__":
    unittest.main()
