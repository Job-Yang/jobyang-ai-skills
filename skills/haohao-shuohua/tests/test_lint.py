#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quick_scan.py / check_integrity.py 的回归测试。

跑法（在技能根目录）：
    python3 -m unittest tests.test_lint -v
或：
    cd tests && python3 test_lint.py

测试分两组：
  正向 fixture（必须被抓到）：半角标点、B2、破折号、元话语、序号标题、免责尾巴。
  反向 / 对抗 fixture（必须不误报）：干净中文、围栏代码块、行内码、URL、
    数字小数点/千分位、英文术语中英混排、繁体中文、嵌套引号、像免责的正常论证。
这组反向 fixture 就是"像外部锐评一样构造的对抗样例库"——
脚本在这些恶意/边界输入下误报或漏报，本测试就挂。
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
QS = os.path.join(ROOT, "scripts", "quick_scan.py")
CI = os.path.join(ROOT, "scripts", "check_integrity.py")


def run(args, cwd=None):
    return subprocess.run(
        [sys.executable, QS] + args,
        capture_output=True, text=True, cwd=cwd,
    )


# ---------------------------------------------------------------------------
# fixture 库：(文件名, 内容)
# ---------------------------------------------------------------------------

POSITIVE = {
    # 中文夹半角标点（硬闸，必须抓到）
    "pos_half.md": (
        "这是一段正常中文。\n"
        "这段夹了半角逗号,应该被抓到。句号.也该抓;分号:一起。\n"
    ),
    # B2 变体族（用全角标点，确保只测 B2、不连带触发半角硬闸）
    "pos_b2.md": (
        "这不是简单的升级，而是一次范式重构。\n"
        "你以为改的是标点，其实改的是句法。\n"
        "真正难的是节奏。\n"
    ),
    # 破折号串
    "pos_dash.md": (
        "这条路的尽头——是一个新范式——一个人机共写的时代。\n"
    ),
    # 元话语
    "pos_meta.md": (
        "这种写法值得深思,也引人深思。\n"
    ),
    # 章节机械编号
    "pos_heading.md": (
        "# 标题\n"
        "## 一、背景\n"
        "### 1. 概述\n"
        "## 三板斧\n"
    ),
    # 闭引号/闭书名号/闭括号后贴半角逗号（上轮漏报）
    "pos_closing_punct.md": (
        "他说「明白」,转身就走。\n"
        "这本书《重构》,已经出到第二版。\n"
        "引述”完,就结束了。\n"
    ),
    # 元话语（全角标点，只测 meta，不带半角）
    "pos_meta_only.md": (
        "这种说法值得深思，也引人深思。\n"
    ),
    # 正文里的免责尾巴（GPT-6 Astra 加载本技能后的实测样例）
    "pos_disclaim.md": (
        "我建议继续保留工程师的合并审批。\n"
        "以上仅依据已提供的情况，未做额外核验。\n"
        "未核实实际实验进度，以上时间按你的预估表述。\n"
        "具体时间还得看这两项结果什么时候返回。\n"
    ),
}

NEGATIVE = {
    # 干净中文（全角标点，不该报）
    "neg_clean.md": (
        "这是一段正常中文，标点全是全角。句号在这儿。问号呢？感叹号！\n"
        "读起来像人说的话，没有 AI 腔。\n"
    ),
    # 围栏代码块 + 行内码 + URL 里的半角标点（绝不能误报）
    "neg_code_url.md": (
        "正文提一句配置：`foo,bar;baz` 必须写成这样。\n"
        "```\n"
        "x = a, b; c.d = 1.5\n"
        "url = \"https://example.com/a,b;c\"\n"
        "```\n"
        "参考 https://foo.com/x,y 和 [点这里](https://bar.com/p,q)。\n"
    ),
    # 数字小数点 / 千分位 / 版本号（绝不能误报）
    "neg_number.md": (
        "圆周率约 3.14，千分位写 1,000，版本 v1.2，比例 92.65%。\n"
        "从 3 秒降到 0.8 秒。\n"
    ),
    # 英文术语中英混排（英文词尾贴半角逗号是合理用法，保守不报）
    "neg_english_mix.md": (
        "调用 API 完成鉴权，再写回结果。\n"
        "用 Python 训练模型，TensorFlow 1.14 版本跑得很稳。\n"
        "AST 遍历会把节点打印出来。\n"
    ),
    # 繁体中文（本身合法，不该被当病；但这里用全角标点，不夹半角）
    "neg_traditional.md": (
        "他說中文，寫作很自然。繁體字不是 AI 味，不用洗。\n"
    ),
    # 嵌套引号（合法中文引用，全角标点）
    "neg_quotes.md": (
        "他說：「這個『底線』很清楚。」我們點頭。\n"
        "引用别人「不是 X，而是 Y」时，按原意保留。\n"
    ),
    # 跨行 HTML 注释（整体剥除，里面夹半角逗号也不许误报）
    "neg_multiline_comment.md": (
        "正文开头一句正常话。\n"
        "<!--\n"
        "这段跨行注释里的中文,夹了半角逗号,不该被扫出来。\n"
        "-->\n"
        "正文收尾正常。\n"
    ),
    # 像免责、其实是正常论证的说法（不许报免责尾巴）
    "neg_disclaim_lookalike.md": (
        "这个方案尚未验证，下周压测。\n"
        "上线时间还要看测试结果。\n"
        "未经核实的消息不要转发。\n"
        "上述方案只按原计划推进。\n"
        "我们目前还没有验证 AI 能否识别这些约束。\n"
    ),
}


def write_fixtures(tmp):
    paths = {}
    for name, content in {**POSITIVE, **NEGATIVE}.items():
        p = os.path.join(tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        paths[name] = p
    return paths


class TestQuickScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="haoqs_")
        self.p = write_fixtures(self.tmp)

    # ---- 正向：必须被抓到 ----
    def test_positive_half_is_hard_gate(self):
        r = run([self.p["pos_half.md"]])
        self.assertEqual(r.returncode, 1, "半角标点命中必须退出1\n" + r.stdout + r.stderr)
        self.assertIn("半角标点", r.stdout)

    def test_positive_meta_reported(self):
        r = run(["--checks", "meta", self.p["pos_meta.md"]])
        self.assertIn("元话语", r.stdout)
        self.assertIn("值得深思", r.stdout)

    def test_positive_b2_reported(self):
        r = run(["--checks", "b2", self.p["pos_b2.md"]])
        self.assertIn("B2", r.stdout)
        self.assertIn("你以为", r.stdout)

    def test_positive_dash_reported(self):
        r = run(["--checks", "dash", self.p["pos_dash.md"]])
        self.assertIn("破折号", r.stdout)

    def test_positive_heading_reported(self):
        r = run(["--checks", "heading", self.p["pos_heading.md"]])
        self.assertIn("序号标题", r.stdout)
        self.assertIn("一、背景", r.stdout)

    def test_b2_not_default_fail(self):
        # B2 默认只是建议层，不驱动退出码（与技能 L73/L215 一致）
        r = run([self.p["pos_b2.md"]])
        self.assertEqual(r.returncode, 0, "B2 默认不该驱动退出码\n" + r.stdout)

    # ---- 反向 / 对抗：必须不误报 ----
    def test_negative_all_clean_exit_zero(self):
        for name in NEGATIVE:
            with self.subTest(file=name):
                r = run([self.p[name]])
                self.assertEqual(
                    r.returncode, 0,
                    "%s 应是干净的（退出0），但被报了：\n%s" % (name, r.stdout),
                )

    def test_code_block_not_flagged(self):
        r = run([self.p["neg_code_url.md"]])
        self.assertNotIn("a, b", r.stdout)
        self.assertNotIn("foo,bar", r.stdout)

    def test_number_not_flagged(self):
        r = run([self.p["neg_number.md"]])
        self.assertIn("(clean)", r.stdout, "数字/小数点/千分位不该报\n" + r.stdout)

    def test_english_mix_not_flagged(self):
        r = run([self.p["neg_english_mix.md"]])
        self.assertIn("(clean)", r.stdout, "英文术语中英混排不该误报\n" + r.stdout)

    def test_traditional_not_flagged(self):
        r = run([self.p["neg_traditional.md"]])
        self.assertIn("(clean)", r.stdout, "繁体中文不该被当 AI 味\n" + r.stdout)

    def test_nonexistent_file_exit_2(self):
        r = run(["/tmp/__no_such_file__.md"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("读取失败", r.stderr)

    # ---- 复评驳回的 4 个回归 ----
    def test_closing_punct_before_comma_flagged(self):
        # 」 》 ” 后贴半角逗号必须抓到（上轮漏报）
        r = run(["--checks", "half", self.p["pos_closing_punct.md"]])
        self.assertIn("半角标点", r.stdout, "闭引号/书名号后半角逗号漏报\n" + r.stdout)
        self.assertIn("」,", r.stdout)

    def test_multiline_html_comment_stripped(self):
        # 跨行 HTML 注释整体剥除，里面夹半角逗号不许误报
        r = run([self.p["neg_multiline_comment.md"]])
        self.assertEqual(r.returncode, 0, "跨行 HTML 注释里的半角逗号误报了\n" + r.stdout)

    def test_unclosed_fence_not_false_green(self):
        # 只开一个 ``` 不收尾：之后的半角逗号绝不能被当代码静默跳过
        content = "正常一句中文。\n```\n这句后面藏着,半角逗号,本不该被当代码静默跳过。\n"
        d = tempfile.mkdtemp(prefix="haofence_")
        p = os.path.join(d, "unclosed.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        r = run([p])
        self.assertNotEqual(r.returncode, 0, "未闭合围栏竟返回 0（脏稿假绿）\n" + r.stdout)
        self.assertIn("围栏", r.stdout + r.stderr)

    def test_meta_is_advisory_default(self):
        # 默认退出码只卡 half：纯 meta 文件 exit 0；--fail-on meta 才卡
        r = run([self.p["pos_meta_only.md"]])
        self.assertEqual(r.returncode, 0, "meta 默认不该驱动退出码\n" + r.stdout)
        self.assertIn("元话语", r.stdout)
        r2 = run(["--fail-on", "meta", self.p["pos_meta_only.md"]])
        self.assertEqual(r2.returncode, 1, "--fail-on meta 应让 meta 命中卡退出码\n" + r2.stdout)

    # ---- 免责尾巴：建议层，只报不卡 ----
    def test_disclaim_reported(self):
        r = run(["--checks", "disclaim", self.p["pos_disclaim.md"]])
        self.assertIn("免责尾巴", r.stdout)
        for frag in ("以上仅依据", "未做额外核验", "以上时间按你的", "还得看这两项结果什么时候"):
            self.assertIn(frag, r.stdout, "漏报免责尾巴：%s\n%s" % (frag, r.stdout))

    def test_disclaim_is_advisory_default(self):
        r = run([self.p["pos_disclaim.md"]])
        self.assertEqual(r.returncode, 0, "免责尾巴默认不该驱动退出码\n" + r.stdout)
        r2 = run(["--fail-on", "disclaim", self.p["pos_disclaim.md"]])
        self.assertEqual(r2.returncode, 1, "--fail-on disclaim 应卡退出码\n" + r2.stdout)

    def test_disclaim_lookalike_not_flagged(self):
        r = run(["--checks", "disclaim", self.p["neg_disclaim_lookalike.md"]])
        self.assertIn("(clean)", r.stdout, "正常论证被当成免责尾巴\n" + r.stdout)


class TestIntegrity(unittest.TestCase):
    def write(self, content):
        p = os.path.join(tempfile.mkdtemp(prefix="haoci_"), "SKILL.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p

    def test_balanced_blocks_ok(self):
        md = (
            "# 技能\n"
            "<!-- 底线条款:开始 · 不许改 -->\n"
            "**保真 > 场合 > 力度 > 风格。**\n"
            "<!-- 底线条款:结束 -->\n"
            "正文。\n"
        )
        p = self.write(md)
        r = subprocess.run([sys.executable, CI, "--skill", p],
                          capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("找到宪法块 1 个", r.stdout)

    def test_unbalanced_open_detected(self):
        md = ("# 技能\n<!-- 底线条款:开始 · 漏了结束 -->\n正文没收尾。\n")
        p = self.write(md)
        r = subprocess.run([sys.executable, CI, "--skill", p],
                          capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("缺少对应的「结束」", r.stdout)

    def test_unbalanced_close_detected(self):
        md = ("# 技能\n<!-- 底线条款:结束 · 没有开始 -->\n")
        p = self.write(md)
        r = subprocess.run([sys.executable, CI, "--skill", p],
                          capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("没有对应的「开始」", r.stdout)

    def test_expect_hash_mismatch(self):
        md = (
            "# 技能\n<!-- 底线条款:开始 -->\n内容甲。\n<!-- 底线条款:结束 -->\n"
        )
        p = self.write(md)
        r = subprocess.run([sys.executable, CI, "--skill", p, "--expect", "deadbeef"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("哈希变了", r.stdout)

    def test_skill_self_check_passes(self):
        # 技能自带 SKILL.md 必须通过（3 个宪法块配对完整）
        r = subprocess.run([sys.executable, CI], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("找到宪法块 3 个", r.stdout)


class TestWall(unittest.TestCase):
    def write(self, md):
        fd, p = tempfile.mkstemp(suffix=".md"); os.close(fd)
        with open(p, "w", encoding="utf-8") as f:
            f.write(md)
        return p

    LONG = "当前配置变更一次性全量下发，过去三个月有四次错误配置在两分钟内影响全部实例。" * 4

    def test_long_paragraph_reported_not_gated(self):
        r = run([self.write("# 标题\n\n" + self.LONG + "\n"), "--checks", "wall"])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("单段", r.stdout)

    def test_prose_run_reported(self):
        md = "# 标题\n\n" + "\n\n".join(["这是一段短文字。"] * 5) + "\n"
        r = run([self.write(md), "--checks", "wall"])
        self.assertIn("连排 5 段", r.stdout)

    def test_lists_tables_break_runs_and_code_ignored(self):
        md = ("# 标题\n\n短段一。\n\n短段二。\n\n- 列表\n\n短段三。\n\n| a | b |\n| - | - |\n\n短段四。\n\n"
              "```\n" + self.LONG + "\n```\n")
        r = run([self.write(md), "--checks", "wall"])
        self.assertIn("(clean)", r.stdout)

    def test_long_quote_paragraph_reported_but_quoted_list_ok(self):
        r = run([self.write("# 标题\n\n> " + self.LONG + "\n"), "--checks", "wall"])
        self.assertIn("引用块内单段", r.stdout)
        r = run([self.write("# 标题\n\n> 短引言。\n>\n> - 一项\n> - 两项\n"), "--checks", "wall"])
        self.assertIn("(clean)", r.stdout)

    def test_threshold_flag(self):
        p = self.write("# 标题\n\n" + "一" * 130 + "\n")
        self.assertIn("(clean)", run([p, "--checks", "wall"]).stdout)
        self.assertIn("单段 130 字", run([p, "--checks", "wall", "--para-max", "120"]).stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
