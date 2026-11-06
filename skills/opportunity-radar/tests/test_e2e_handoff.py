#!/usr/bin/env python3
"""端到端交接回归：合成 radar 候选 → scorecard 出卡 → brief 模板渲染，全过冻结信封。

这是今天（2026-10-16）实跑确认过的主链路：score.py 出分能过冻结 artifact_io
validate；本测试把整条链路钉成回归。兄弟包（opportunity-scorecard / product-brief）
并排存在时才跑——单独安装本包时自动 skip，不制造跨包硬依赖。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITE = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts"))
from artifact_io import validate_envelope  # noqa: E402

SCORECARD = SUITE / "opportunity-scorecard"
BRIEF = SUITE / "product-brief"
HAVE_SIBLINGS = (SCORECARD / "scripts" / "score.py").exists() and (BRIEF / "scripts" / "artifact_io.py").exists()


@unittest.skipUnless(HAVE_SIBLINGS, "单独安装：兄弟包不在，跳过端到端")
class E2EHandoffTest(unittest.TestCase):
    def test_radar_to_scorecard_to_brief(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            # 1. radar 产物：一份带候选的 radar 信封，过冻结校验
            radar_md = "\n".join([
                "---", "schema: opc-artifact/v1", "opc_node: radar", "artifact_kind: radar",
                "opc_version: 0.2.0", "topic: null", "created: 2026-10-16T10:00:00+00:00",
                "upstream: null", "produced_by: e2e", "human_review: pending", "---", "",
                "## 候选：围绝经期半夜醒的个性化提醒",
                "- 领域：女性健康", "- 证据：https://example.com/reddit — 原话",
                "- 信号强度：强 + 理由", "evidence: real", ""])
            _, errs = validate_envelope(radar_md)
            self.assertEqual([], errs, errs)

            # 2. scorecard 出卡：用 examples 合成样例，跑兄弟包 score.py
            ex = SCORECARD / "examples" / "scoring.synthetic.json"
            card_out = td / "assess.md"
            p = subprocess.run([sys.executable, str(SCORECARD / "scripts" / "score.py"),
                                "--input", str(ex), "--out", str(card_out), "--producer", "e2e"],
                               capture_output=True, text=True)
            self.assertEqual(0, p.returncode, p.stderr + p.stdout)
            _, errs = validate_envelope(card_out.read_text(encoding="utf-8"))
            self.assertEqual([], errs, f"scorecard 出卡未过冻结校验：{errs}")

            # 3. product-brief：prd / plan 两个正文 seal 后过冻结校验
            io = BRIEF / "scripts" / "artifact_io.py"
            prd_body = td / "prd-body.md"
            prd_body.write_text(
                "## 问题与目标人群\n场景。\n## 用户旅程\n触发到完成。\n"
                "## 功能范围与验收\nF1 验收用例。\n## 平台与产品数据\nWeb。\n"
                "## 成功指标\n待测。\n## 已确认与未决\n无。\n", encoding="utf-8")
            prd_out = td / "prd.md"
            p = subprocess.run([sys.executable, str(io), "seal", "--input", str(prd_body),
                               "--node", "prd", "--kind", "prd", "--topic", "e2e-demo",
                               "--producer", "e2e", "--out", str(prd_out)],
                              capture_output=True, text=True)
            self.assertEqual(0, p.returncode, p.stderr + p.stdout)
            _, errs = validate_envelope(prd_out.read_text(encoding="utf-8"))
            self.assertEqual([], errs, f"prd 未过冻结校验：{errs}")

            plan_body = td / "plan-body.md"
            plan_body.write_text(
                "## 里程碑与交付物\nM1。\n## 依赖与并行安排\n无。\n"
                "## 估算与依据\n区间 2-4 周，置信中。\n## 验收与资源\n人审。\n",
                encoding="utf-8")
            plan_out = td / "plan.md"
            p = subprocess.run([sys.executable, str(io), "seal", "--input", str(plan_body),
                                "--node", "prd", "--kind", "plan", "--topic", "e2e-demo",
                                "--upstream", "prd.md", "--out", str(plan_out)],
                               capture_output=True, text=True)
            self.assertEqual(0, p.returncode, p.stderr + p.stdout)
            _, errs = validate_envelope(plan_out.read_text(encoding="utf-8"))
            self.assertEqual([], errs, f"plan 未过冻结校验：{errs}")

    def test_handoff_examples_have_no_opc_node_drift(self):
        """三包 handoff.md 的 opc_node 必须是本节点自己（防 radar 写成 prd 复发）。"""
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_handoff.py"),
                           str(ROOT), str(SCORECARD), str(BRIEF)],
                          capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
