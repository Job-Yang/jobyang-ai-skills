#!/usr/bin/env python3
"""preflight.py 回归：留痕三分支 + 卡片渲染（标准库 unittest）。

今天（2026-10-16）真实故障：飞书文档留痕成功，群卡片被挡（im scope / bot 不在群，
错误 230002）。这条降级分支必须是确定性的，不能临场发挥：
  doc 不可写            → block（exit 7，不停在文档外补写）
  doc 可写 + 群可发      → full（exit 0，文档 + 群卡片）
  doc 可写 + 群 230002  → degrade-docs（exit 6，只文档留痕 + 回报 blocker）
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "preflight.py"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


class BranchTest(unittest.TestCase):
    def test_full_branch(self):
        p = run("check", "--doc-writable", "yes", "--group-sendable", "yes")
        self.assertEqual(0, p.returncode, p.stderr)
        out = json.loads(p.stdout)
        self.assertEqual("full", out["branch"])

    def test_degrade_docs_only_on_230002(self):
        """今天的真实走法：文档可写、群 230002 → 降级纯文档留痕，exit 6。"""
        p = run("check", "--doc-writable", "yes", "--group-sendable", "no",
                "--group-error", "230002")
        self.assertEqual(6, p.returncode)
        out = json.loads(p.stdout)
        self.assertEqual("degrade-docs", out["branch"])
        self.assertIn("230002", out["blocker"])
        self.assertTrue(any("不发群卡片" in a or "群卡片" in a for a in out["actions"]))
        self.assertEqual("ok", out["skill_dir"], "本包目录自检必须通过")

    def test_block_when_doc_not_writable(self):
        p = run("check", "--doc-writable", "no", "--group-sendable", "no",
                "--group-error", "230002")
        self.assertEqual(7, p.returncode)
        out = json.loads(p.stdout)
        self.assertEqual("block", out["branch"])
        self.assertEqual("doc_not_writable", out["blocker"])

    def test_skill_dir_self_probe_passes_on_this_package(self):
        p = run("check", "--doc-writable", "yes", "--group-sendable", "yes")
        out = json.loads(p.stdout)
        self.assertEqual([], out["skill_issues"], out)


class CardRenderTest(unittest.TestCase):
    def test_render_no_opportunity_card(self):
        data = {"date": "2026-10-16", "conclusion": "无强机会，今天不打分",
                "related_list": "主动式 AI 助手（近亲 09-28 语音直达）；MGX 烧积分（近亲 10-12 确认层）",
                "stale_list": "戒烟问责/版税聚合（原话停在 2 月）",
                "group_status": "群通道 230002 不可发，降级文档留痕"}
        p = run("render-card", "--template", "no_opportunity", "--data", json.dumps(data, ensure_ascii=False))
        self.assertEqual(0, p.returncode, p.stderr)
        out = json.loads(p.stdout)
        self.assertIn("无强机会", out["title"])
        self.assertEqual(4, len(out["elements"]))

    def test_render_rejects_missing_required_field(self):
        data = {"date": "2026-10-16"}  # 缺 conclusion 等
        p = run("render-card", "--template", "no_opportunity", "--data", json.dumps(data))
        self.assertEqual(2, p.returncode)
        err = json.loads(p.stderr)
        self.assertEqual("rejected", err["status"])
        self.assertIn("conclusion", err["error"])


if __name__ == "__main__":
    unittest.main()
