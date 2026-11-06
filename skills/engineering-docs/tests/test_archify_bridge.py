"""薄桥接的边界与真实后端冒烟；不启动浏览器或联网。"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("archify_bridge", ROOT / "scripts/archify_bridge.py")
BR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BR)


class BridgeUnitTests(unittest.TestCase):
    def test_unknown_type_rejected(self):
        with self.assertRaises(SystemExit):
            BR.parser().parse_args(["render", "--type", "anything", "--input", "x", "--output", "x.html"])

    def test_existing_output_requires_explicit_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "old.html"
            p.write_text("keep me")
            with self.assertRaises(BR.BridgeError):
                BR.output_guard(p, False)
            self.assertEqual(p.read_text(), "keep me")

    def test_output_symlink_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            p, target = Path(td) / "alias.html", Path(td) / "target.html"
            target.write_text("keep me")
            p.symlink_to(target)
            with self.assertRaises(BR.BridgeError):
                BR.output_guard(p, True)
            self.assertEqual(target.read_text(), "keep me")

    def test_remote_brand_capture_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "input.json"
            p.write_text(json.dumps({"components": [{"brand": {"url": "https://example.test/logo"}}]}))
            with self.assertRaises(BR.BridgeError):
                BR.reject_remote_brands(p)

    def test_update_check_disabled_and_no_shell(self):
        result = subprocess.CompletedProcess([], 0, '{"ok": true}', '')
        with patch.object(BR.subprocess, "run", return_value=result) as run:
            got = BR.run_command(["node", "backend", "deliver"], Path.cwd())
        self.assertEqual(run.call_args.kwargs["env"]["ARCHIFY_UPDATE_CHECK_DISABLED"], "1")
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertTrue(got["receipt"]["ok"])

    def test_failed_receipt_is_not_success_even_with_zero_exit(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "input.json"
            p.write_text(json.dumps({"schema_version": 3, "diagram_type": "lifecycle"}))
            args = BR.parser().parse_args(["render", "--type", "lifecycle", "--input", str(p), "--output", str(Path(td)/"out.html")])
            version = subprocess.CompletedProcess([], 0, 'v22.0.0', '')
            with patch.object(BR.shutil, "which", return_value="node"), patch.object(BR.subprocess, "run", return_value=version), patch.object(BR, "run_command", return_value={"exit_code":0,"receipt":{"ok":False},"stdout":"","stderr":""}):
                report, code = BR.execute(args)
            self.assertFalse(report["ok"])
            self.assertNotEqual(code, 0)
            self.assertFalse(report["browser_verified"])

    def test_missing_node_does_not_silently_use_legacy(self):
        args = BR.parser().parse_args(["explain", "--input", "x.md", "--output", "x.html"])
        with patch.object(BR.shutil, "which", return_value=None):
            with self.assertRaisesRegex(BR.BridgeError, "未自动降级"):
                BR.execute(args)

    def test_vendored_pin_and_licenses_exist(self):
        pin = json.loads(BR.PIN.read_text())
        self.assertEqual(pin["version"], "3.2.0")
        self.assertEqual(len(pin["commit"]), 40)
        for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
            self.assertTrue((ROOT / "vendor/archify" / name).is_file())

    def legacy_spec(self, layout="mindmap"):
        return {
            "id": "fallback-test", "name": "旧模板测试", "layout": layout,
            "title": "有边界的旧模板兜底", "subtitle": "输入格式决定后端",
            "note": "旧输入原样保留，不转换为 Archify schema。",
            "center": "发布准备",
            "groups": [
                {"label": "质量", "items": ["回归结果", "风险评估"]},
                {"label": "交付", "items": ["版本产物", "发布窗口"]},
            ],
        }

    def parse_render(self, source, diagram_type, output="out.html", *extra):
        return BR.parser().parse_args([
            "render", "--type", diagram_type, "--input", str(source),
            "--output", str(source.parent / output), *extra,
        ])

    def test_capabilities_are_ast_derived_without_optional_imports(self):
        before = set(os.sys.modules)
        report = BR.capabilities()
        self.assertEqual(report["legacy"]["count"], 27)
        self.assertEqual(len(report["legacy"]["structural"]), 14)
        self.assertEqual(len(report["legacy"]["quantitative"]), 6)
        self.assertEqual(len(report["legacy"]["extra_structural"]), 7)
        self.assertEqual(report["overlapping_names"], ["sequence", "timeline", "tree", "workflow"])
        self.assertNotIn("matplotlib", set(os.sys.modules) - before)

    def test_three_legacy_only_layouts_route_without_schema_conversion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for layout in ("matrix", "mindmap", "image_annotate"):
                source = root / f"{layout}.json"
                source.write_text(json.dumps(self.legacy_spec(layout)))
                decision = BR.route_render(self.parse_render(source, layout))
                self.assertEqual(decision["selected"], "legacy")
                self.assertEqual(decision["fallback_reason"], "native_type_unavailable")
                self.assertEqual(decision["data"]["layout"], layout)

    def test_same_name_is_disambiguated_by_input_schema(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            native = root / "native.json"
            native.write_text(json.dumps({"schema_version": 3, "diagram_type": "tree"}))
            legacy = root / "legacy.json"
            legacy.write_text(json.dumps(self.legacy_spec("tree")))
            self.assertEqual(BR.route_render(self.parse_render(native, "tree"))["selected"], "native")
            old = BR.route_render(self.parse_render(legacy, "tree"))
            self.assertEqual(old["selected"], "legacy")
            self.assertEqual(old["reason"], "legacy_schema_for_overlapping_name")

    def test_native_layout_objects_are_not_legacy_markers(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "native.json"
            for kind in ("architecture", "tree", "class", "erd", "timeline", "waterfall"):
                with self.subTest(kind=kind):
                    source.write_text(json.dumps({"diagram_type": kind, "schema_version": 1, "layout": {}}))
                    self.assertEqual(BR.route_render(self.parse_render(source, kind))["selected"], "native")

    def test_legacy_output_cannot_overwrite_input_even_when_requested(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source.html"
            before = json.dumps(self.legacy_spec())
            source.write_text(before)
            with self.assertRaisesRegex(BR.BridgeError, "拒绝覆盖图源"):
                BR.execute(self.parse_render(source, "mindmap", source.name, "--overwrite"))
            self.assertEqual(source.read_text(), before)

    def test_legacy_empty_check_receipt_is_not_success(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "input.json"
            source.write_text(json.dumps(self.legacy_spec()))
            output = source.parent / "out.svg"
            def fake_run(command, cwd, timeout=120):
                if str(BR.LEGACY_RENDERER) in command:
                    Path(command[command.index("--out") + 1]).write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
                    return {"exit_code": 0, "receipt": {"id": "x"}, "stdout": "", "stderr": ""}
                return {"exit_code": 0, "receipt": {}, "stdout": "", "stderr": ""}
            with patch.object(BR, "run_command", side_effect=fake_run):
                report, code = BR.execute(self.parse_render(source, "mindmap", output.name))
            self.assertFalse(report["ok"])
            self.assertNotEqual(code, 0)
            self.assertFalse(output.exists())

    def test_legacy_renders_frozen_source_not_later_edits(self):
        import hashlib
        import xml.etree.ElementTree as ET
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "input.json"
            before = json.dumps(self.legacy_spec(), ensure_ascii=False).encode("utf-8")
            source.write_bytes(before)
            output = source.parent / "out.svg"
            def fake_run(command, cwd, timeout=120):
                if str(BR.LEGACY_RENDERER) in command:
                    frozen = Path(command[command.index("--input") + 1])
                    self.assertNotEqual(frozen, source)
                    self.assertEqual(frozen.read_bytes(), before)
                    changed = self.legacy_spec()
                    changed["title"] = "后续修改"
                    source.write_text(json.dumps(changed))
                    Path(command[command.index("--out") + 1]).write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
                    return {"exit_code": 0, "receipt": {"id": "x"}, "stdout": "", "stderr": ""}
                return {"exit_code": 0, "receipt": {"errors": []}, "stdout": "", "stderr": ""}
            with patch.object(BR, "run_command", side_effect=fake_run):
                report, code = BR.execute(self.parse_render(source, "mindmap", output.name))
            self.assertEqual(code, 0, report)
            self.assertEqual(report["source_sha256"], hashlib.sha256(before).hexdigest())
            metadata = ET.parse(output).getroot().find("{http://www.w3.org/2000/svg}metadata")
            self.assertEqual(json.loads(metadata.text)["title"], self.legacy_spec()["title"])

    def test_mixed_and_mismatched_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mixed = self.legacy_spec("mindmap")
            mixed.update({"schema_version": 3, "diagram_type": "tree"})
            source = root / "mixed.json"
            source.write_text(json.dumps(mixed))
            with self.assertRaisesRegex(BR.BridgeError, "混合输入"):
                BR.route_render(self.parse_render(source, "mindmap"))
            source.write_text(json.dumps(self.legacy_spec("mindmap")))
            with self.assertRaisesRegex(BR.BridgeError, "不匹配"):
                BR.route_render(self.parse_render(source, "matrix"))

    def test_damaged_native_input_never_routes_to_legacy(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "damaged.json"
            source.write_text(json.dumps({"schema_version": "broken"}))
            decision = BR.route_render(self.parse_render(source, "lifecycle"))
            self.assertEqual(decision["selected"], "native")
            with patch.object(BR, "execute_legacy") as legacy, patch.object(BR.shutil, "which", return_value=None):
                with self.assertRaisesRegex(BR.BridgeError, "未自动降级"):
                    BR.execute(self.parse_render(source, "lifecycle"))
            legacy.assert_not_called()

    def test_explicit_backend_refuses_wrong_schema(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            legacy = root / "legacy.json"
            legacy.write_text(json.dumps(self.legacy_spec()))
            with self.assertRaisesRegex(BR.BridgeError, "不会丢字段"):
                BR.route_render(self.parse_render(legacy, "mindmap", "x.html", "--backend", "native"))
            native = root / "native.json"
            native.write_text(json.dumps({"schema_version": 3, "diagram_type": "tree"}))
            with self.assertRaisesRegex(BR.BridgeError, "不接受 Archify schema"):
                BR.route_render(self.parse_render(native, "tree", "y.html", "--backend", "legacy"))

    def test_legacy_check_failure_does_not_commit_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "legacy.json"
            source.write_text(json.dumps(self.legacy_spec()))
            output = root / "out.svg"
            args = self.parse_render(source, "mindmap", output.name)

            calls = []

            def fake_run(command, cwd, timeout=120):
                calls.append((command, cwd))
                if str(BR.LEGACY_RENDERER) in command:
                    Path(command[command.index("--out") + 1]).write_text(
                        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>')
                    return {"exit_code": 0, "receipt": {"id": "x"}, "stdout": "", "stderr": ""}
                return {"exit_code": 1, "receipt": {"errors": ["broken"]}, "stdout": "", "stderr": ""}

            with patch.object(BR, "run_command", side_effect=fake_run):
                report, code = BR.execute(args)
            self.assertNotEqual(code, 0)
            self.assertEqual(report["stage"], "artifact_check")
            self.assertIn("broken", report["error"])
            self.assertFalse(output.exists())
            self.assertEqual(calls[0][0][:2], [os.sys.executable, "-I"])
            self.assertEqual(calls[0][0][2], str(BR.LEGACY_RENDERER))
            self.assertEqual(calls[0][1], source.parent)

    def test_legacy_html_is_static_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "legacy.json"
            source_text = json.dumps(self.legacy_spec(), ensure_ascii=False, indent=2)
            source.write_text(source_text)
            output = root / "out.html"
            report, code = BR.execute(self.parse_render(source, "mindmap", output.name))
            self.assertEqual(code, 0, report)
            page = output.read_text()
            self.assertTrue(report["ok"])
            self.assertEqual(report["route"]["selected"], "legacy")
            self.assertFalse(report["browser_verified"])
            self.assertIn('data-backend="legacy"', page)
            self.assertIn('data-static="true"', page)
            self.assertIn('content="false"', page)
            self.assertIn('id="legacy-source-json" type="application/json"', page)
            self.assertIn('"layout": "mindmap"', page)

    def test_image_annotation_fallback_resolves_relative_image(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            examples = json.loads((ROOT / "assets/diagram-templates/examples_extra.json").read_text())
            data = next(item for item in examples if item["id"] == "ia-sample-review")
            shutil.copyfile(ROOT / data["image_path"], root / "screen.png")
            data["image_path"] = "screen.png"
            source = root / "annotation.json"
            source.write_text(json.dumps(data, ensure_ascii=False))
            output = root / "annotation.html"
            report, code = BR.execute(self.parse_render(source, "image_annotate", output.name))
            self.assertEqual(code, 0, report)
            self.assertEqual(report["route"]["selected"], "legacy")
            self.assertIn("data:image/png;base64,", output.read_text())
            self.assertEqual(json.loads(source.read_text())["image_path"], "screen.png")

    @unittest.skipIf(os.name == "nt", "仅验证POSIX文件权限")
    def test_legacy_commit_preserves_existing_file_permissions(self):
        with tempfile.TemporaryDirectory() as td:
            target, staged = Path(td) / "target.svg", Path(td) / "staged.svg"
            target.write_text("old")
            target.chmod(0o600)
            staged.write_text("new")
            BR._commit_staged(staged, target, True)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(target.read_text(), "new")

    def test_legacy_overwrite_guard_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "legacy.json"
            source.write_text(json.dumps(self.legacy_spec()))
            output = root / "out.html"
            output.write_text("keep me")
            with self.assertRaises(BR.BridgeError):
                BR.execute(self.parse_render(source, "mindmap", output.name))
            self.assertEqual(output.read_text(), "keep me")


@unittest.skipUnless(shutil.which("node"), "本机无 Node，真实后端测试未运行")
class BridgeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.tmp.name)
        cls.script = ROOT / "scripts/archify_bridge.py"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def invoke(self, *args):
        x = subprocess.run([os.sys.executable, "-I", str(self.script), *args], text=True, capture_output=True, timeout=120)
        self.assertEqual(x.returncode, 0, x.stdout + x.stderr)
        report = json.loads(x.stdout)
        self.assertTrue(report["ok"], report)
        self.assertFalse(report["browser_verified"])
        return report

    def test_native_lifecycle_and_artifact_check(self):
        inp = ROOT / "vendor/archify/examples/agent-run.lifecycle.json"
        output = self.work / "lifecycle.html"
        report = self.invoke("render", "--type", "lifecycle", "--input", str(inp), "--output", str(output))
        self.assertEqual(report["stage"], "checked")
        self.assertIn('data-node-id="queued"', output.read_text())
        self.assertTrue(report["stages"]["artifact_check"]["receipt"]["ok"])

    def test_native_erd_with_layout_config_stays_native(self):
        inp = ROOT / "vendor/archify/examples/orders.erd.json"
        output = self.work / "native-erd.html"
        report = self.invoke("render", "--type", "erd", "--input", str(inp), "--output", str(output))
        self.assertEqual(report["route"]["selected"], "native")
        self.assertIn('data-node-id="order"', output.read_text())

    def test_architecture_comparison(self):
        examples = ROOT / "vendor/archify/examples"
        output = self.work / "comparison.html"
        report = self.invoke("compare", "--base", str(examples / "checkout-platform.base.architecture.json"), "--head", str(examples / "checkout-platform.head.architecture.json"), "--output", str(output))
        self.assertEqual(report["stage"], "checked")
        self.assertTrue(output.is_file())

    def test_explainer_and_local_panel_patch(self):
        source = self.work / "candidate.md"
        source.write_text('# 核对后才交付 {#answer}\n\n执行通过不等于验收通过。\n\n- 先核对证据。\n\n@answer scope="合成验证"\n@meta locale=zh-CN\n\n## 验证 {#checks}\n\n- [ ] 检查结果。\n', encoding='utf-8')
        output = self.work / "page.html"
        self.invoke("explain", "--input", str(source), "--output", str(output))
        replacement = self.work / "replacement.md"
        replacement.write_text('## 再核对 {#checks}\n\n- [ ] 核对实际结果。\n', encoding='utf-8')
        patched = self.work / "patched.html"
        self.invoke("patch", "--artifact", str(output), "--panel-id", "checks", "--replacement", str(replacement), "--output", str(patched))
        self.assertIn('再核对', patched.read_text())
        self.assertIn('执行通过不等于验收通过', patched.read_text())
