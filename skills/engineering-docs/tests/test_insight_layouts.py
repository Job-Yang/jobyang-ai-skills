"""Regression tests for high-density insight layouts, dual presets, and density checks."""
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import diagram_check as DC  # noqa: E402
import diagram_kit as DK  # noqa: E402
import diagram_runtime as DR  # noqa: E402
from diagram_scene import check_svg, validate  # noqa: E402
import insight_layouts as IL  # noqa: E402
import render_templates as RT  # noqa: E402
import visual_theme as VT  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"


def contrast_ratio(c1, c2):
    ls = sorted(DK.rel_luminance(DK.hex_rgb(c)) for c in (c1, c2))
    return (ls[1] + 0.05) / (ls[0] + 0.05)


class InsightThemeAndContractTests(unittest.TestCase):
    def test_no_literal_hex_in_insight_and_planning_layouts(self):
        for fname in ("insight_layouts.py", "planning_layouts.py", "visual_theme.py"):
            src = (SCRIPTS / fname).read_text(encoding="utf-8")
            self.assertEqual(re.findall(r"#[0-9A-Fa-f]{6}\b", src), [], fname)

    def test_insight_preset_contrast_and_token_export(self):
        pal = VT.insight_palette(plain=False)
        surf = pal["surface"]
        for bg in (surf["canvas"], surf["card"], surf["panel"]):
            self.assertGreaterEqual(contrast_ratio(surf["ink"], bg), 4.5)
            self.assertGreaterEqual(contrast_ratio(surf["muted"], bg), 4.5)
        for name, acc in pal["accents"].items():
            with self.subTest(accent=name):
                self.assertGreaterEqual(contrast_ratio(acc["text"], acc["tint"]), 4.5)
                self.assertGreaterEqual(contrast_ratio(surf["card"], acc["solid"]), 4.5)

        tokens = DR.export_tokens()
        self.assertEqual(set(tokens["modes"]), {"light", "dark", "plain"})
        for hex_val in surf.values():
            key = "--dk-" + hex_val[1:].lower()
            self.assertIn(key, tokens["modes"]["light"])
        dark_surfaces = {
            k: tokens["modes"]["dark"]["--dk-" + surf[k][1:].lower()]
            for k in ("canvas", "card", "panel", "border", "divider")
        }
        self.assertEqual(len(set(dark_surfaces.values())), len(dark_surfaces), dark_surfaces)
        for val in tokens["modes"]["plain"].values():
            if val.startswith("#"):
                self.assertEqual(val[1:3], val[3:5])
                self.assertEqual(val[3:5], val[5:7])


class InsightBuildersTests(unittest.TestCase):
    def _load_template(self, filename):
        return json.loads((ROOT / "assets/diagram-templates/insight" / filename).read_text(encoding="utf-8"))

    def _run_layout(self, source):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.svg"
            norm, entry = DR.normalize(source)
            spec = {"id": "test-spec", "name": source["type"], **norm["meta"], **norm["payload"], "layout": entry["layout"]}
            if isinstance(norm["payload"].get("layout"), dict):
                spec["_layout_options"] = deepcopy(norm["payload"]["layout"])
            scene, svg, compiled = DR._layout_scene(norm, spec, out)
            adapted = DR._adapt_svg(scene, svg)
            self.assertTrue(validate(scene)["ok"], validate(scene))
            self.assertTrue(check_svg(scene, adapted)["ok"], check_svg(scene, adapted))
            report = DC.static_check(out)
            self.assertTrue(report["ok"], report["errors"])
            self.assertEqual(report["warnings"], [], report["warnings"])
            self.assertEqual(scene["visual_provenance"]["unmapped"], [], scene["visual_provenance"]["unmapped"])
            return scene, svg, adapted, compiled, report

    def test_all_four_golden_templates_build_and_pass_checks(self):
        for fname in (
            "architecture-blueprint.json",
            "composite-dashboard.json",
            "panorama-mindmap.json",
            "guardrail-flywheel.json",
        ):
            with self.subTest(template=fname):
                src = self._load_template(fname)
                scene, _, _, _, _ = self._run_layout(src)
                self.assertGreater(len(scene["objects"]), 3)

    def test_architecture_blueprint_handles_eval_layered_local_flow(self):
        eval_data = json.loads((ROOT / "evals/files/layered-local-flow.json").read_text(encoding="utf-8"))
        source = {
            "version": 1,
            "type": "architecture-blueprint",
            "meta": {"title": eval_data["title"], "subtitle": "4 层 6 分组 · 含局部流程与共享覆盖"},
            "payload": {k: v for k, v in eval_data.items() if k != "title"},
        }
        scene, svg, _, compiled, _ = self._run_layout(source)
        self.assertEqual(len(compiled["boxes"]), 15)
        self.assertEqual(len(scene["edges"]), 11)
        covs = [o for o in scene["objects"] if o["kind"] == "coverage"]
        self.assertEqual(len(covs), 2)
        for text_must in ("配置模型", "领域服务", "HTTP 查询", "界面审计"):
            self.assertIn(text_must, svg)

    def test_architecture_blueprint_horizontal_zones(self):
        source = {
            "version": 1,
            "type": "architecture-blueprint",
            "meta": {"title": "横向三栏架构", "subtitle": "接入 -> 服务 -> 存储"},
            "payload": {
                "preset": "insight",
                "layout": {"orientation": "horizontal", "width": 1200},
                "zones": [
                    {"id": "in", "label": "接入端", "tone": "blue"},
                    {"id": "svc", "label": "编排服务", "tone": "teal"},
                    {"id": "db", "label": "存储层", "tone": "purple"},
                ],
                "components": [
                    {"id": "gw", "zone": "in", "label": "网关", "code": "HTTPS", "rows": [["限流", "10k/s"]]},
                    {"id": "core", "zone": "svc", "label": "核心引擎", "desc": "执行编排", "chips": ["幂等"]},
                    {"id": "pg", "zone": "db", "label": "主库", "code": "PostgreSQL"},
                ],
                "connections": [
                    {"from": "gw", "to": "core", "label": "RPC"},
                    {"from": "core", "to": "pg", "label": "SQL 写入"},
                ],
            },
        }
        scene, _, _, compiled, _ = self._run_layout(source)
        self.assertEqual(len(scene["edges"]), 2)
        self.assertEqual(compiled["width"], 1200)
        zone_xs = [
            next(o["geometry"][0] for o in scene["objects"] if o["kind"] == "group" and o["content"].get("label") == lbl)
            for lbl in ("接入端", "编排服务", "存储层")
        ]
        self.assertEqual(zone_xs, sorted(zone_xs))
        self.assertGreater(zone_xs[1], zone_xs[0])
        self.assertGreater(zone_xs[2], zone_xs[1])

    def test_trend_panel_legend_colors_match_series_without_explicit_tone(self):
        source = {
            "version": 1,
            "type": "dashboard",
            "meta": {"title": "多系列色序一致性"},
            "payload": {
                "panels": [{
                    "id": "p1",
                    "type": "trend",
                    "title": "柱线混合趋势",
                    "categories": ["W1", "W2", "W3"],
                    "series": [
                        {"name": "吞吐量", "kind": "bar", "values": [10, 20, 30]},
                        {"name": "成功率", "kind": "line", "values": [95, 96, 98]},
                        {"name": "延迟分位", "kind": "line", "values": [12, 11, 10]},
                    ],
                }],
            },
        }
        _, svg, _, compiled, _ = self._run_layout(source)
        root = ET.fromstring(svg)
        k = float(compiled["width"]) / IL.LW
        pal = VT.insight_palette()["accents"]
        seq = VT.insight_palette()["sequence"]
        c_bar = pal[seq[0]]["mark"]
        c_line1 = pal[seq[1]]["mark"]
        c_line2 = pal[seq[2]]["mark"]
        trend_paths = [
            (el.get("d") or "", el.get("stroke"))
            for el in root.iter(NS + "path")
            if el.get("data-non-edge") == "1" and el.get("stroke") in {c_line1, c_line2}
        ]
        legend_lines = [s for d, s in trend_paths if d.count(" L") == 1]
        data_lines = [s for d, s in trend_paths if d.count(" L") >= 2]
        self.assertEqual(data_lines, [c_line1, c_line2])
        self.assertEqual(legend_lines, [c_line2, c_line1])
        legend_rects = [
            el.get("fill")
            for el in root.iter(NS + "rect")
            if abs(float(el.get("width") or 0) - 11.0 * k) < 0.2
            and abs(float(el.get("height") or 0) - 9.0 * k) < 0.2
        ]
        self.assertIn(c_bar, legend_rects)
        legend_circles = [
            el.get("fill")
            for el in root.iter(NS + "circle")
            if el.get("stroke") == "none" and abs(float(el.get("r") or 0) - 2.8 * k) < 0.2
        ]
        self.assertIn(c_line1, legend_circles)
        self.assertIn(c_line2, legend_circles)

    def test_dashboard_validation_rejects_bad_numeric_inputs(self):
        bad_ranked = self._load_template("composite-dashboard.json")
        bad_ranked["payload"]["panels"][0]["items"][0]["value"] = -5
        with tempfile.TemporaryDirectory() as td, self.assertRaises(ValueError):
            spec = {**bad_ranked["meta"], **bad_ranked["payload"], "id": "bad", "name": "d", "layout": "dashboard"}
            IL.dashboard(spec).save(Path(td) / "x.svg")

        bad_len = self._load_template("composite-dashboard.json")
        bad_len["payload"]["panels"][1]["series"][0]["values"] = [1.0, 2.0]
        with tempfile.TemporaryDirectory() as td, self.assertRaises(ValueError):
            spec = {**bad_len["meta"], **bad_len["payload"], "id": "bad2", "name": "d", "layout": "dashboard"}
            IL.dashboard(spec).save(Path(td) / "x.svg")

        bad_nan = self._load_template("composite-dashboard.json")
        bad_nan["payload"]["panels"][1]["series"][0]["values"][0] = float("nan")
        with tempfile.TemporaryDirectory() as td, self.assertRaises(ValueError):
            spec = {**bad_nan["meta"], **bad_nan["payload"], "id": "bad3", "name": "d", "layout": "dashboard"}
            IL.dashboard(spec).save(Path(td) / "x.svg")

    def test_legacy_mindmap_and_cycle_stay_unchanged_and_delegate_when_extended(self):
        examples = {s["id"]: s for s in RT._load_examples()}
        with tempfile.TemporaryDirectory() as td:
            p_old = Path(td) / "old_mm.svg"
            res_old = RT.render(examples["mind-map"], p_old)
            self.assertEqual(res_old["width"], 680)
            p_cyc = Path(td) / "old_cy.svg"
            res_cyc = RT.render(examples["cycle"], p_cyc)
            self.assertEqual(res_cyc["width"], 680)

        # Extended mindmap spec with >6 branches & leaves routes through panorama_mindmap
        mm = self._load_template("panorama-mindmap.json")
        mm_via_legacy = {"version": 1, "type": "mindmap", "meta": mm["meta"], "payload": mm["payload"]}
        scene, _, _, _, _ = self._run_layout(mm_via_legacy)
        self.assertEqual(scene["canvas"][0], 1440)

        # Extended cycle spec with guardrails routes through flywheel
        fw = self._load_template("guardrail-flywheel.json")
        fw_via_legacy = {
            "version": 1, "type": "cycle", "meta": fw["meta"],
            "payload": {**fw["payload"], "groups": fw["payload"]["stages"]},
        }
        del fw_via_legacy["payload"]["stages"]
        scene_fw, _, _, _, _ = self._run_layout(fw_via_legacy)
        self.assertEqual(scene_fw["canvas"][0], 1320)

    def test_12_branch_36_leaf_mindmap_builds_without_overlap(self):
        mm = self._load_template("panorama-mindmap.json")
        for side_key in ("left_groups", "right_groups"):
            for i in range(2):
                mm["payload"][side_key].append({
                    "id": f"extra_{side_key}_{i}",
                    "label": f"扩展维 {i+1}",
                    "leaves": [f"子项{j+1}：机制说明详情" for j in range(3)],
                })
        scene, svg, _, compiled, _ = self._run_layout(mm)
        self.assertEqual(len(compiled["boxes"]), 12 + 36 + 1)
        self.assertEqual(len(scene["edges"]), 12 + 36)

    def test_full_runtime_delivery_across_all_three_themes(self):
        src = self._load_template("guardrail-flywheel.json")
        for theme in ("light", "dark", "plain"):
            with self.subTest(theme=theme), tempfile.TemporaryDirectory() as td:
                out = Path(td) / "diagram.html"
                rep = DR.render(src, out, formats=["svg", "png"], theme=theme)
                self.assertTrue(rep["ok"])
                self.assertTrue(Path(rep["artifacts"]["svg"]["path"]).is_file())
                self.assertTrue(Path(rep["artifacts"]["png"]["path"]).is_file())
                receipt = out.with_suffix(".receipt.json")
                self.assertTrue(DR.check_delivery(receipt)["ok"])
                if theme == "plain":
                    svg_txt = Path(rep["artifacts"]["svg"]["path"]).read_text(encoding="utf-8")
                    for c in re.findall(r"#[0-9A-Fa-f]{6}\b", svg_txt):
                        self.assertEqual(c[1:3], c[3:5])
                        self.assertEqual(c[3:5], c[5:7])
                    for r, g, b in re.findall(r"rgb\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)", svg_txt):
                        self.assertEqual(r, g)
                        self.assertEqual(g, b)


class DensityWarningTests(unittest.TestCase):
    def test_bare_architecture_emits_soft_density_warning_while_rich_blueprint_does_not(self):
        d = DK.Diagram(1200, 680, title="裸框架构", subtitle="仅标题卡片测试")
        c1 = d.card("c1", 60, 140, 200, "网关")
        c2 = d.card("c2", 360, 140, 200, "服务")
        c3 = d.card("c3", 660, 140, 200, "缓存")
        c4 = d.card("c4", 60, 320, 200, "队列")
        c5 = d.card("c5", 360, 320, 200, "主库")
        d.edge(c1, c2)
        d.edge(c2, c3)
        d.edge(c2, c4)
        d.edge(c4, c5)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bare.svg"
            d.save(p)
            r = DC.static_check(p)
            self.assertTrue(r["ok"])
            self.assertTrue(any("信息密度偏低" in w for w in r["warnings"]), r["warnings"])
            self.assertEqual(r["metrics"]["bare_card_ratio"], 1.0)


if __name__ == "__main__":
    unittest.main()
