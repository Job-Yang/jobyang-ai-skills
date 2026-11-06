import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDER = os.path.join(ROOT, "scripts", "render_brief.py")
EXAMPLE = os.path.join(ROOT, "examples", "brief_input.example.json")


def render(obj):
    p = subprocess.run([sys.executable, RENDER], input=json.dumps(obj),
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    return p.stdout


def base():
    with open(EXAMPLE, "r", encoding="utf-8") as f:
        return json.load(f)


class TestRenderer(unittest.TestCase):
    def test_contains_required_sections(self):
        out = render(base())
        self.assertIn("# 2026-10-23 周五 · AI 早报", out)
        self.assertIn("## ⚡ 今日最值得看的 3 条", out)
        self.assertIn("【我的判断】", out)
        self.assertIn("【机会分】⭐4", out)
        self.assertIn("对哪条感兴趣，回我编号或名字，我接着深挖。", out)
        self.assertIn("## 🐙 本周 GitHub Trending 复盘", out)
        self.assertIn("**渠道状态**", out)

    def test_empty_group_uses_fixed_phrase(self):
        d = base()
        for g in d["groups"]:
            g["items"] = []
        d["weekly_github"] = []
        out = render(d)
        self.assertIn("今日无值得报的。", out)
        self.assertNotIn("## 🐙", out)

    def test_missing_field_is_rejected_not_silently_dropped(self):
        d = base()
        del d["groups"][0]["items"][0]["judgment"]
        p = subprocess.run([sys.executable, RENDER], input=json.dumps(d),
                           capture_output=True, text=True, timeout=30)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("judgment", p.stderr)

    def test_three_line_card_separates_judgment(self):
        out = render(base())
        # Judgment must start on its own line, not be glued to the fact line.
        self.assertRegex(out, r"\n【我的判断】")


if __name__ == "__main__":
    unittest.main()
