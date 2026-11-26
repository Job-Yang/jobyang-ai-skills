#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing_check.py 确定性单元测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import writing_check  # noqa: E402


class TestWritingCheck(unittest.TestCase):
    def test_clean_sharing_article_with_questions_passes(self):
        # 问句 H2、无 TL;DR 五字段、无公式，应零 ERROR 零 WARN 通过
        text = (
            "# 为什么真机 UI 巡检总在发版前卡壳\n\n"
            "上个月连续两次白屏事故漏到线上，测试同学每次发版前都要点 60 个入口。\n\n"
            "## 为什么 XCTest 跑不起来？\n\n"
            "老页面弹窗太多，脚本动不动就卡死。\n\n"
            "## 哪些没搞定？\n\n"
            "涉及短信风控的 18 个入口目前还是半自动，参考 [日志](https://example.com/a,b?x=1)。\n"
        )
        errors, warns, _ = writing_check.check("sharing", text)
        self.assertEqual(errors, [])
        self.assertEqual(warns, [])

    def test_forbidden_opener_detected(self):
        text = "# 标题\n\n随着人工智能技术的发展，一切都在改变。\n"
        errors, _, _ = writing_check.check("sharing", text)
        self.assertTrue(any("随着" in e for e in errors))

    def test_halfwidth_punctuation_and_masking(self):
        # 代码块、行内代码、URL 里的半角标点不应误报；正文里的应报错
        good = (
            "# 测试\n\n"
            "见 `foo(a, b)` 与 [文档](https://example.com/a,b;c) 和 1,000 次调用，一切正常。\n\n"
            "```python\nx = [1, 2, 3]\n```\n"
        )
        errors_good, _, _ = writing_check.check("opinion", good)
        self.assertEqual(errors_good, [])

        bad = "# 测试\n\n这里有个问题,需要立刻改.\n"
        errors_bad, _, _ = writing_check.check("opinion", bad)
        self.assertTrue(any("半角标点" in e for e in errors_bad))

    def test_unclosed_fence_blocks_scan(self):
        text = "# 测试\n\n```python\nprint(1)\n"
        errors, _, _ = writing_check.check("tangshan", text)
        self.assertTrue(any("未闭合代码围栏" in e for e in errors))

    def test_unverified_marker_fails(self):
        text = "# 测试\n\n这部分收益约为待补。\n"
        errors, _, _ = writing_check.check("sharing", text)
        self.assertTrue(any("待补" in e for e in errors))

    def test_note_length_warning_and_pass(self):
        short_note = "代码生成速度超过人工审查带宽后，走查自然让位于自动化测试，人真正该做的是定义验收标准。"
        errors, warns, stats = writing_check.check("note", short_note)
        self.assertEqual(errors, [])
        self.assertEqual(warns, [])
        self.assertLessEqual(stats["cn"], 120)

        long_note = "这是一段故意凑得很长的手记思考，" * 15
        errors2, warns2, _ = writing_check.check("note", long_note)
        self.assertEqual(errors2, [])
        self.assertTrue(any("120 字" in w for w in warns2))

    def test_opinion_em_dash_title_warns(self):
        text = "# 规范越写越厚——一次管理反思\n\n直白说说看法。\n"
        errors, warns, _ = writing_check.check("opinion", text)
        self.assertEqual(errors, [])
        self.assertTrue(any("破折号" in w for w in warns))

    def test_sharing_missing_h1_warns(self):
        text = "## 二级充当一级标题\n\n正文只讲实事，不写空话。\n"
        errors, warns, _ = writing_check.check("sharing", text)
        self.assertEqual(errors, [])
        self.assertTrue(any("一级主标题" in w for w in warns))

    def test_opinion_missing_h1_and_short_warns(self):
        text = "这是一段超过两百字但没有一级主标题的短观点。" * 15
        errors, warns, _ = writing_check.check("opinion", text)
        self.assertEqual(errors, [])
        self.assertTrue(any("# 一级主标题" in w for w in warns))
        self.assertTrue(any("600" in w or "1,000" in w for w in warns))

    def test_tangshan_h3_without_h2_warns(self):
        body = "这里先拆解底层商业与工程约束。" * 35
        text = f"# 主标题\n\n### 第一部分\n\n{body}\n\n### 第二部分\n\n{body}\n"
        errors, warns, _ = writing_check.check("tangshan", text)
        self.assertEqual(errors, [])
        self.assertTrue(any("###" in w and "##" in w for w in warns))

    def test_tangshan_continuous_prose_without_h2_clean(self):
        body = "用连贯散文从激励结构推演到底。" * 35
        text = f"# 短评散文\n\n{body}\n"
        errors, warns, _ = writing_check.check("tangshan", text)
        self.assertEqual(errors, [])
        self.assertEqual(warns, [])

    def test_tangshan_h2_as_h1_with_h3_and_jieyu_warns(self):
        body = "这里先拆解底层商业与工程约束。" * 35
        text = f"## 误把二级当主标题\n\n### 第一节\n\n{body}\n\n### 第二节\n\n{body}\n\n### 结语\n\n收口。\n"
        errors, warns, _ = writing_check.check("tangshan", text)
        self.assertEqual(errors, [])
        self.assertTrue(any("勿用 ## 充当主标题" in w for w in warns))
        self.assertTrue(any("###" in w and "##" in w for w in warns))
        self.assertTrue(any("结语" in w for w in warns))


if __name__ == "__main__":
    unittest.main(verbosity=2)
