#!/usr/bin/env python3
"""product-brief 回归测试（仅依赖 Python 3.9+ 标准库）。"""
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_IO = ROOT / "scripts" / "artifact_io.py"
CHECK_VENDORED = ROOT / "scripts" / "check_vendored.py"

sys.path.insert(0, str(ROOT / "scripts"))
import artifact_io  # noqa: E402


class ProductBriefContractTests(unittest.TestCase):
    def test_vendored_manifest_matches(self):
        r = subprocess.run([sys.executable, str(CHECK_VENDORED)], cwd=str(ROOT), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_handoff_example_opc_node_is_prd(self):
        hf = (ROOT / "references" / "handoff.md").read_text(encoding="utf-8")
        self.assertIn("opc_node: prd", hf)
        for wrong in ("opc_node: radar", "opc_node: assess", "opc_node: design", "opc_node: technical"):
            self.assertNotIn(wrong, hf)

    def test_templates_contain_required_sections(self):
        prd = (ROOT / "templates" / "prd.md").read_text(encoding="utf-8")
        for heading in ("问题与目标人群", "用户旅程", "功能范围与验收", "平台与产品数据", "成功指标", "已确认与未决"):
            self.assertIn(heading, prd)
        plan = (ROOT / "templates" / "plan.md").read_text(encoding="utf-8")
        for heading in ("里程碑与交付物", "依赖与并行安排", "估算与依据", "弱项验证四件套", "验收与资源", "风险与范围调整"):
            self.assertIn(heading, plan)

    def test_seal_validate_pack_ingest_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            prd_body = td_path / "prd-body.md"
            prd_body.write_text(
                "## 问题与目标人群\n团队需要按规范生成产品需求。\n\n"
                "## 用户旅程\n输入一句话需求 -> 拆分功能清单与验收 -> 导出计划。\n\n"
                "## 功能范围与验收\n- F1：注入 20 条边界输入均给出明确错误码。\n\n"
                "## 平台与产品数据\nWeb 控制台与 CLI。\n\n"
                "## 成功指标\n首次返工率下降，基线待测。\n\n"
                "## 已确认与未决\n- 未决：首期覆盖平台优先级。\n",
                encoding="utf-8",
            )
            prd_sealed = td_path / "prd-sealed.md"
            r = subprocess.run(
                [sys.executable, str(ARTIFACT_IO), "seal",
                 "--input", str(prd_body), "--node", "prd", "--kind", "prd",
                 "--topic", "demo-brief", "--producer", "unit-test", "--out", str(prd_sealed)],
                capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            _, errs = artifact_io.validate_envelope(prd_sealed.read_text(encoding="utf-8"))
            self.assertEqual([], errs, errs)

            plan_body = td_path / "plan-body.md"
            plan_body.write_text(
                "## 里程碑与交付物\nM1：核心流水线；对应 F1。\n\n"
                "## 依赖与并行安排\n无阻塞。\n\n"
                "## 估算与依据\n预计 2-4 周，置信中。\n\n"
                "## 验收与资源\n由自动化单测与人工评审共同验收。\n",
                encoding="utf-8",
            )
            plan_sealed = td_path / "plan-sealed.md"
            r = subprocess.run(
                [sys.executable, str(ARTIFACT_IO), "seal",
                 "--input", str(plan_body), "--node", "prd", "--kind", "plan",
                 "--topic", "demo-brief", "--upstream", "prd-demo-brief.md",
                 "--producer", "unit-test", "--out", str(plan_sealed)],
                capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            bundle = td_path / "brief-bundle.zip"
            r = subprocess.run(
                [sys.executable, str(ARTIFACT_IO), "pack",
                 "--input", str(prd_sealed), str(plan_sealed), "--out", str(bundle)],
                capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with zipfile.ZipFile(bundle) as zf:
                names = set(zf.namelist())
            self.assertTrue({"manifest.json", "prd-demo-brief.md", "plan-demo-brief.md"}.issubset(names), names)

            r = subprocess.run([sys.executable, str(ARTIFACT_IO), "validate", "--input", str(bundle)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(json.loads(r.stdout)["status"], "valid")

            out_root = td_path / "inbox"
            r = subprocess.run(
                [sys.executable, str(ARTIFACT_IO), "ingest", "--input", str(bundle), "--output-root", str(out_root)],
                capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((out_root / "prd-demo-brief.md").is_file())
            self.assertTrue((out_root / "plan-demo-brief.md").is_file())

            # 改写正文同 topic 二次导入必须拒绝覆盖
            prd_conflict = td_path / "prd-conflict.md"
            prd_conflict.write_text(prd_sealed.read_text(encoding="utf-8") + "\n冲突改动。\n", encoding="utf-8")
            r_conf = subprocess.run(
                [sys.executable, str(ARTIFACT_IO), "ingest", "--input", str(prd_conflict), "--output-root", str(out_root)],
                capture_output=True, text=True,
            )
            self.assertEqual(r_conf.returncode, 1, r_conf.stdout + r_conf.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
