"""Paint regressions: shared tokens, semantic selection, compatibility and geometry."""
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import diagram_kit as DK
import render_templates as RT
import structural_extra as SE
import visual_theme as VT

BASE = {"id": "palette-test", "name": "颜色", "title": "共享配色",
        "subtitle": "只改外观", "note": "测试数据"}
NS = "{http://www.w3.org/2000/svg}"


def tree(canvas):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "result.svg"
        # Canvas.save appends its footer; each inspection consumes a fresh copy.
        copy.deepcopy(canvas).save(path)
        return ET.parse(path).getroot()


def geometry(root):
    return [(e.tag, {k: v for k, v in e.attrib.items() if k not in ("fill", "stroke")}, e.text)
            for e in root.iter()]


def box_paint(canvas, key):
    x, y, w, h = canvas.boxes[key]
    root = tree(canvas)
    for r in root.iter(NS + "rect"):
        if all(r.get(k) is not None and float(r.get(k)) == v
               for k, v in (("x", x), ("y", y), ("width", w), ("height", h))):
            return r.get("stroke"), r.get("fill")
    raise AssertionError(f"Missing rect for {key}")


def text_contrast(a, b):
    # Independent existing WCAG implementation, not the new helper under test.
    ls = sorted(DK.rel_luminance(DK.hex_rgb(c)) for c in (a, b))
    return (ls[1] + .05) / (ls[0] + .05)


class SharedThemeTests(unittest.TestCase):
    def test_authoritative_base_tokens_and_both_engines_match(self):
        self.assertEqual(VT.DEFAULT_THEME, "document-neutral")
        self.assertEqual(DK.INK, RT.INK)
        self.assertEqual(DK.MUTED, RT.MUTED)
        self.assertEqual(DK.BORDER, VT.THEME["entity_border"])
        self.assertEqual(DK.ZONE_BORDER, VT.THEME["group_border"])
        self.assertNotEqual(DK.BORDER, RT.LINE)
        self.assertEqual(DK.INK, "#1A1B1C")
        self.assertEqual(RT.MUTED, "#5F6670")
        self.assertEqual(VT.THEME["panel_bg"], "#FAFAF8")
        self.assertEqual(VT.THEME["grid"], "#E4E3DD")
        self.assertEqual(DK.Diagram(960, 400, "t").palette["canvas"], RT.THEME["canvas_bg"])
        self.assertEqual(RT.THEME["canvas_bg"], "#FFFFFF")
        self.assertEqual(VT.THEME["semantic"], {"accent": "#4F6B9A", "success": "#35705A",
                                               "warning": "#9A6A2F", "error": "#A14E50"})

    def test_legacy_views_are_derived_and_json_readers_still_work(self):
        raw = json.loads(VT.THEME_PATH.read_text())
        self.assertEqual(DK.TONES, VT.tones())
        self.assertEqual(DK.DOUBAO, VT.legacy_components())
        self.assertIsInstance(RT.tone(0), list)
        self.assertEqual(SE.SEM["blue"], list(VT.structural_tone({"tone": "accent"})))
        self.assertEqual(SE.SEM["teal"], list(VT.structural_tone({"tone": "success"})))
        for name, palette in DK.PALETTES.items():
            self.assertEqual(palette, VT.palette(plain=name == "plain"))
        for view in DK.VARIANTS.values():
            self.assertEqual(view, VT.variant())
        for key in ("blue", "purple", "teal", "amber", "red", "gray", *raw["sequence"]):
            self.assertEqual(len(raw["colors"][key]), 2)
            self.assertRegex(raw["border"][key], r"^#[0-9A-F]{6}$")
            dark, fill = raw["colors"][key]
            expected = raw["panel_bg"] if key == "gray" else VT.mix_white(dark, raw["tint_amount"])
            self.assertEqual(fill, expected)

    def test_text_contrast_and_important_boundaries(self):
        backgrounds = [VT.THEME["paper"], VT.THEME["panel_bg"]]
        for plain in (False, True):
            for name, tone in VT.tones(plain).items():
                with self.subTest(plain=plain, tone=name):
                    self.assertGreaterEqual(text_contrast(tone["text"], tone["tint"]), 4.5)
                    self.assertGreaterEqual(text_contrast(VT.THEME["paper"], tone["solid"]), 4.5)
                    self.assertGreaterEqual(text_contrast(tone["border"], tone["tint"]), 3)
                    backgrounds.append(tone["tint"])
        for bg in backgrounds:
            for fg in (DK.INK, DK.MUTED):
                self.assertGreaterEqual(text_contrast(fg, bg), 4.5, (fg, bg))
        self.assertGreaterEqual(text_contrast(RT.LINE, RT.THEME["panel_bg"]), 3)
        self.assertNotEqual(RT.LINE, RT.THEME["grid"])

    def test_semantic_and_category_faces_are_explicit_not_one_six_percent_mix(self):
        for name, base in VT.THEME["semantic"].items():
            self.assertEqual(VT.tones()[name]["tint"], VT.THEME["semantic_fill"][name])
            self.assertNotEqual(VT.tones()[name]["tint"], VT.mix_white(base, VT.THEME["tint_amount"]))
        self.assertEqual(len({VT.tones()[n]["tint"] for n in VT.THEME["category"]}), 5)

    def test_no_second_literal_hex_library_in_engines_or_adapter(self):
        for filename in ("diagram_kit.py", "render_templates.py", "structural_extra.py", "visual_theme.py"):
            source = (ROOT / "scripts" / filename).read_text()
            self.assertFalse(re.findall(r"#[0-9A-Fa-f]{6}\b", source), filename)

    def test_semantic_selection_and_unknown_fallback(self):
        cases = [({}, "neutral"), ({"tone": "success"}, "success"),
                 ({"status": "warning"}, "warning"), ({"emphasis": True}, "accent"),
                 ({"emphasis": "error"}, "error"), ({"tone": "unknown"}, "neutral"),
                 ({"status": "unknown"}, "neutral"),
                 ({"label": "失败", "index": 2}, "neutral"),
                 ({"tone": "success", "status": "error", "emphasis": True}, "success")]
        for item, expected in cases:
            with self.subTest(item=item):
                self.assertEqual(VT.semantic_tone(item), VT.tones()[expected])
        for old, category in (("sky", "sky"), ("sage", "sage"), ("purple", "lavender"),
                              ("lavender", "lavender"), ("sand", "sand"),
                              ("pink", "rose"), ("rose", "rose")):
            self.assertEqual(VT.semantic_tone({"tone": old}), VT.tones()[category])

    def test_data_categories_remain_distinct_and_not_status_tokens(self):
        colors = [RT.tone(i)[0] for i in range(8)]
        self.assertEqual(len(set(colors)), 8)
        self.assertFalse(set(colors) & set(VT.THEME["semantic"].values()))
        self.assertNotEqual(RT.tone(0), RT.tone(5))


class DiagramPaintTests(unittest.TestCase):
    def scene(self, **kw):
        d = DK.Diagram(960, 900, "Legacy", **kw)
        d.category_card("cat", 40, 120, 300, "类别", "说明", cat="pink")
        d.verdict_bar("verdict", 40, 280, 880, "结论")
        d.evidence_action_row("row", 40, 380, 880, "证据", "观测", "动作", prio="p0")
        d.status_pill(40, 520, "强", "strong")
        d.status_pill(120, 520, "中", "mid")
        d.status_pill(200, 520, "弱", "weak")
        d.matrix_table("matrix", 40, 620, 880, ["A", "B"], [("维度", [("strong", "好"), ("future", "未知")])])
        return d

    def test_all_historical_theme_palette_and_variant_names_run_same_style(self):
        expected = self.scene().svg()
        for alias in (*DK.THEME_ALIASES, "unknown-theme"):
            with self.subTest(theme=alias):
                self.assertEqual(self.scene(theme=alias).svg(), expected)
        for name in (*DK.VARIANTS, "unknown-variant"):
            self.assertEqual(self.scene(variant=name).svg(), expected)
        for name in ("warm", "cream-blue", "warm-cream", "unknown-palette"):
            self.assertEqual(self.scene(palette=name).svg(), expected)

    def test_legacy_components_render_svg_and_drawio(self):
        d = self.scene()
        with tempfile.TemporaryDirectory() as tmp:
            svg, drawio = Path(tmp) / "legacy.svg", Path(tmp) / "legacy.drawio"
            result = d.save(svg, drawio=drawio)
            self.assertEqual(result["issues"], [])
            root = ET.parse(svg).getroot()
            ET.parse(drawio)
        self.assertEqual({g.get("data-kind") for g in root.iter(NS + "g")},
                         {"header", "category", "verdict", "row", "pill", "matrix"})
        self.assertNotIn("feDropShadow", d.svg())
        verdict = next(g for g in root.iter(NS + "g") if g.get("data-id") == "verdict")
        self.assertEqual(verdict.find(NS + "rect").get("fill"), d.db["verdict_bg"])
        self.assertGreaterEqual(text_contrast(verdict.find(NS + "text").get("fill"),
                                             verdict.find(NS + "rect").get("fill")), 4.5)

    def test_entities_groups_edges_and_drawio_use_separate_paint(self):
        d = DK.Diagram(960, 520, "t")
        group = d.zone("g", 40, 110, 880, 300, "分组")
        normal = d.card("n", 70, 180, 230, "普通")
        category = d.card("c", 360, 180, 230, "分类", tone="sky")
        focus = d.card("f", 650, 180, 230, "重点", tone="sky", emphasis=True)
        d.edge(normal, category)
        self.assertEqual(group.meta["body_border"], VT.THEME["group_border"])
        self.assertEqual(normal.meta["body_fill"], VT.THEME["entity_fill"])
        self.assertEqual(normal.meta["body_border"], VT.THEME["entity_border"])
        self.assertNotEqual(normal.meta["body_border"], VT.THEME["edge"])
        self.assertEqual(category.meta["body_fill"], VT.tones()["sky"]["tint"])
        self.assertEqual(category.meta["body_border"], VT.tones()["sky"]["entity_border"])
        self.assertEqual(focus.meta["body_fill"], category.meta["body_fill"])
        self.assertEqual(focus.meta["body_border"], VT.tones()["sky"]["border"])
        drawio = d.drawio()
        for node in (normal, category, focus):
            self.assertIn(f"fillColor={node.meta['body_fill']};strokeColor={node.meta['body_border']};", drawio)
        self.assertIn(f"strokeColor={VT.THEME['edge']};", drawio)

    def test_legacy_category_cards_are_distinct_and_unknowns_stay_safe(self):
        paints = []
        for cat in ("sky", "sage", "lavender", "sand", "rose"):
            d = DK.Diagram(960, 420, "t")
            node = d.category_card("c", 40, 120, 320, "类别", "说明", cat=cat)
            paints.append((node.meta["body_fill"], node.meta["body_border"]))
        self.assertEqual(len(set(paints)), 5)
        d = DK.Diagram(960, 420, "t")
        node = d.category_card("c", 40, 120, 320, "未知", "说明", cat="unknown")
        self.assertEqual(node.meta["body_fill"], VT.THEME["entity_fill"])
        d.card("unknown", 450, 120, 220, "未知色名", tone="unseen")
        d.status_pill(40, 300, "未知", "unseen")
        self.assertEqual(d.check()["issues"], [])

    def test_plain_has_no_coloured_paint_including_legacy_and_edges(self):
        for args in ({"theme": "plain"}, {"palette": "plain"}):
            d = self.scene(**args)
            a = d.card("a", 400, 120, 180, "A", tone="success", emphasis=True, badge="1")
            b = d.card("b", 700, 120, 180, "B", tone="error", chips=[("chip", "filled", "accent")])
            d.edge(a, b, style="accent")
            for document in (d.svg(), d.drawio()):
                colors = re.findall(r"#[0-9A-Fa-f]{6}\b", document)
                self.assertTrue(colors)
                for c in colors:
                    self.assertEqual(c[1:3], c[3:5], c)
                    self.assertEqual(c[3:5], c[5:7], c)

    def test_plain_keeps_short_hex_text_color_api_compatible(self):
        d = DK.Diagram(960, 400, "t", theme="plain")
        d.text(40, 120, "短色值", color="#f00")
        # Inspect the emitted label paint, not the unrelated deferred-label lifecycle.
        label = ET.fromstring(d.layers["label"][-1])
        self.assertEqual(label.get("fill"), "#363636")
        self.assertEqual(VT.grayscale("#f00"), VT.grayscale("#FF0000"))

    def test_interleaved_instances_do_not_mutate_exports_or_pending_edges(self):
        exports = copy.deepcopy((DK.TONES, DK.LINES, DK.DOUBAO, DK.PALETTES, DK.THEMES))
        a = DK.Diagram(960, 400, "t", theme="warm-cream")
        x = a.card("a", 40, 120, 220, "A", tone="accent")
        y = a.card("b", 400, 120, 220, "B")
        a.edge(x, y, style="accent")  # finalization is deliberately delayed
        b = self.scene(theme="plain")
        b.svg()
        a.card("c", 40, 240, 220, "C", tone="success")
        reference = DK.Diagram(960, 400, "t")
        x = reference.card("a", 40, 120, 220, "A", tone="accent")
        y = reference.card("b", 400, 120, 220, "B")
        reference.edge(x, y, style="accent")
        reference.card("c", 40, 240, 220, "C", tone="success")
        self.assertEqual(a.svg(), reference.svg())
        self.assertEqual(a.drawio(), reference.drawio())
        self.assertEqual((DK.TONES, DK.LINES, DK.DOUBAO, DK.PALETTES, DK.THEMES), exports)
        a.tones["accent"]["solid"] = VT.THEME["paper"]
        self.assertNotEqual(a.tones["accent"], reference.tones["accent"])


class StructuralPaintTests(unittest.TestCase):
    def state_spec(self):
        return {**BASE, "states": [{"id": "s", "label": "开始"},
                                  {"id": "a", "label": "成功"},
                                  {"id": "b", "label": "失败"},
                                  {"id": "c", "label": "等待"},
                                  {"id": "d", "label": "结束", "kind": "end"}],
                "start": "s", "transitions": [{"from": a, "to": b, "label": "转移"}
                                               for a, b in zip("sabc", "abcd")]}

    def test_states_never_cycle_or_guess_label_meanings(self):
        c = SE.state_machine(self.state_spec())
        for key in c.boxes:
            # 显式kind=end的终态双框保持较强中性轮廓，不按“成功/失败”等名字猜颜色。
            expected = VT.structural_tone() if key == "sm-d" else (VT.THEME["group_border"], VT.THEME["panel_bg"])
            self.assertEqual(box_paint(c, key), expected, key)

    def test_explicit_state_semantics_preserve_geometry_and_input(self):
        base = self.state_spec()
        expected = geometry(tree(SE.state_machine(base)))
        styled = copy.deepcopy(base)
        styled["states"][1]["tone"] = "success"
        styled["states"][2]["status"] = "error"
        styled["states"][3]["emphasis"] = True
        styled["states"][4]["tone"] = "warning"
        before = copy.deepcopy(styled)
        c = SE.state_machine(styled)
        self.assertEqual(geometry(tree(c)), expected)
        self.assertEqual(styled, before)
        for key, name in (("a", "success"), ("b", "error"), ("c", "accent"), ("d", "warning")):
            self.assertEqual(box_paint(c, "sm-" + key), VT.structural_tone({"tone": name}))

    def test_canvas_box_ignores_index_but_accepts_semantic_keywords(self):
        for index in (-1, 0, 1, 2, 5, 999):
            c = RT.Canvas(BASE, 400)
            c.box("a", 40, 140, 200, 60, "普通", index=index, filled=True)
            self.assertEqual(box_paint(c, "a"), (VT.THEME["entity_border"], VT.THEME["entity_fill"]))
        for field, value, name in (("tone", "success", "success"), ("status", "warning", "warning"),
                                   ("emphasis", True, "accent"), ("tone", "unseen", "neutral")):
            c = RT.Canvas(BASE, 400)
            c.box("a", 40, 140, 200, 60, "重点", **{field: value})
            expected = (VT.THEME["entity_border"], VT.THEME["entity_fill"]) if name == "neutral" else VT.structural_tone({"tone": name})
            self.assertEqual(box_paint(c, "a"), expected)

    def test_sequence_groups_and_participants_neutral_unless_explicit(self):
        spec = {**BASE, "participants": [{"id": "a", "label": "甲"}, {"id": "b", "label": "乙"}],
                "messages": [{"from": "a", "to": "b", "label": "请求"} for _ in range(3)],
                "groups": [{"label": str(i), "start": i, "end": i} for i in range(3)]}
        c = SE.sequence(spec)
        root = tree(c)
        groups = [r for r in root.iter(NS + "rect") if r.get("width") == "624"]
        self.assertEqual([r.get("fill") for r in groups], [VT.THEME["panel_bg"]] * 3)
        for key in c.boxes:
            self.assertEqual(box_paint(c, key), (VT.THEME["group_border"], VT.THEME["panel_bg"]))
        styled = copy.deepcopy(spec)
        styled["groups"][1]["emphasis"] = True
        styled["participants"][0]["emphasis"] = True
        c = SE.sequence(styled)
        self.assertEqual(geometry(tree(c)), geometry(root))
        self.assertEqual(box_paint(c, "seq-a"), VT.structural_tone({"emphasis": True}))
        groups = [r for r in tree(c).iter(NS + "rect") if r.get("width") == "624"]
        self.assertEqual(groups[1].get("fill"), VT.tones()["accent"]["tint"])
        self.assertEqual(groups[0].get("fill"), VT.THEME["panel_bg"])

    def test_er_and_swimlane_style_changes_leave_geometry_unchanged(self):
        examples = {s["id"]: s for s in RT._load_examples()}
        for name, field, builder in (("er-task-graph", "entities", SE.er),
                                     ("lane-three-handoff", "nodes", RT.workflow)):
            with self.subTest(name=name):
                spec = copy.deepcopy(examples[name])
                for item in spec[field]:
                    for key in ("tone", "status", "emphasis"):
                        item.pop(key, None)
                base = tree(builder(spec))
                spec[field][0]["tone"] = "accent"
                changed = tree(builder(spec))
                self.assertEqual(geometry(base), geometry(changed))
                self.assertNotEqual(ET.tostring(base), ET.tostring(changed))

    def test_annotated_actions_are_emphasis_not_success_states(self):
        spec = next(s for s in RT._load_examples() if s["id"] == "ia-sample-review")
        c = SE.image_annotate(spec)
        for key in c.boxes:
            if key.startswith("ac-"):
                self.assertEqual(box_paint(c, key), VT.structural_tone({"emphasis": True}))

    def test_non_data_templates_do_not_use_categorical_or_implicit_status_color(self):
        categories = {c for key in VT.THEME["sequence"] for c in VT.THEME["colors"][key]}
        states = set(VT.THEME["semantic"].values()) - {VT.THEME["semantic"]["accent"]}
        for spec in RT._load_examples():
            if spec["layout"] not in RT.STRUCTURAL:
                continue
            root = tree(RT.STRUCTURAL[spec["layout"]](spec))
            used = {e.get(k) for e in root.iter() for k in ("fill", "stroke")}
            with self.subTest(name=spec["id"]):
                self.assertFalse(used & categories)
                self.assertFalse(used & states)
                # Divider is decorative; card/cell boundaries need visible contrast.
                self.assertFalse(any(r.get("stroke") == VT.THEME["grid"] for r in root.iter(NS + "rect")))


if __name__ == "__main__":
    unittest.main()
