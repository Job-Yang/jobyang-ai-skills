"""Role contract: independent semantics, contrast, frozen geometry and exports."""
import copy
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import diagram_kit as DK
import render_templates as RT
import structural_extra as SE
import visual_theme as VT
from test_visual_theme import BASE, NS, tree, geometry, box_paint, text_contrast


class RoleThemeTests(unittest.TestCase):
    def test_seven_explicit_roles_are_separate_from_tone_aliases(self):
        expected = {"frontend", "backend", "database", "cloud", "security", "messagebus", "external"}
        self.assertEqual(set(VT.roles()), expected)
        self.assertEqual(len({t["tint"] for t in VT.roles().values()}), 7)
        for role, t in VT.roles().items():
            self.assertNotIn(role, VT.tones())
            self.assertEqual(VT.semantic_tone({"role": role}), t)
            self.assertEqual(VT.semantic_tone({"tone": role}), VT.tones()["neutral"])
        self.assertNotEqual(VT.roles()["security"], VT.tones()["error"])

    def test_priority_unknowns_and_no_label_inference(self):
        cases = [({"role": "security"}, VT.roles()["security"]),
                 ({"role": "security", "emphasis": True}, VT.roles()["security"]),
                 ({"role": "security", "status": "success"}, VT.tones()["success"]),
                 ({"role": "security", "tone": "warning", "status": "error"}, VT.tones()["warning"]),
                 ({"role": "backend", "emphasis": "error"}, VT.tones()["error"]),
                 ({"role": "backend", "tone": "neutral"}, VT.tones()["neutral"]),
                 ({"role": "backend", "tone": "unknown"}, VT.tones()["neutral"]),
                 ({"role": "unknown", "emphasis": True}, VT.tones()["neutral"]),
                 ({"role": ["backend"]}, VT.tones()["neutral"]),
                 ({"role": "", "emphasis": True}, VT.tones()["neutral"]),
                 ({"role": 0, "emphasis": True}, VT.tones()["neutral"]),
                 ({"label": "数据库错误", "id": "security", "index": 3}, VT.tones()["neutral"])]
        for item, expected in cases:
            with self.subTest(item=item):
                self.assertEqual(VT.semantic_tone(item), expected)

    def test_empty_override_fields_preserve_legacy_unset_behavior(self):
        # 空覆盖字段不是显式中性色；保留旧状态回退，并允许已声明的角色生效。
        cases = [({"tone": "", "status": "success"}, VT.tones()["success"]),
                 ({"status": "", "emphasis": "warning"}, VT.tones()["warning"]),
                 ({"emphasis": ""}, VT.tones()["neutral"]),
                 ({"role": "backend", "tone": ""}, VT.roles()["backend"]),
                 ({"role": "backend", "status": ""}, VT.roles()["backend"]),
                 ({"role": "backend", "emphasis": ""}, VT.roles()["backend"]),
                 ({"role": "backend", "tone": "unknown"}, VT.tones()["neutral"])]
        for item, expected in cases:
            with self.subTest(item=item):
                self.assertEqual(VT.semantic_tone(item), expected)

    def test_all_role_text_badges_and_key_outlines_have_contrast(self):
        for plain in (False, True):
            for role, t in VT.roles(plain).items():
                with self.subTest(plain=plain, role=role):
                    for fg in (t["text"], DK.INK, DK.MUTED):
                        self.assertGreaterEqual(text_contrast(fg, t["tint"]), 4.5)
                    self.assertGreaterEqual(text_contrast(DK.PAPER, t["solid"]), 4.5)
                    for border in (t["border"], t["entity_border"]):
                        self.assertGreaterEqual(text_contrast(border, t["tint"]), 3)
                    self.assertNotEqual(t["border"], t["entity_border"])
                    self.assertEqual(VT.structural_tone({"role": role}, plain=plain), (t["entity_border"], t["tint"]))
                    self.assertEqual(VT.structural_tone({"role": role, "emphasis": True}, plain=plain), (t["border"], t["tint"]))

    def scene(self, role=None, emphasis=False, **kwargs):
        d = DK.Diagram(960, 480, "角色测试", **kwargs)
        a = d.card("a", 40, 140, 320, "原有模块", desc="完整说明保持原有换行宽度与文本位置", code="module-id",
                   badge="1", chips=[("已通过", "filled", "success")], rows=[("原有成员", "只读")],
                   role=role, emphasis=emphasis)
        b = d.zone("boundary", 500, 120, 400, 260, "可绑定分组端点")
        d.edge(a, b, label="交接", style="accent")
        return d

    def test_role_does_not_change_card_geometry_wrap_or_bound_edges(self):
        for emphasis in (False, True):
            baseline = self.scene(emphasis=emphasis)
            before_svg = geometry(ET.fromstring(baseline.svg()))
            before_drawio = ET.fromstring(baseline.drawio())
            for role in VT.roles():
                styled = self.scene(role, emphasis)
                self.assertEqual(geometry(ET.fromstring(styled.svg())), before_svg)
                root = ET.fromstring(styled.drawio())
                self.assertEqual([ET.tostring(g) for g in root.iter("mxGeometry")],
                                 [ET.tostring(g) for g in before_drawio.iter("mxGeometry")])
                cells = {c.get("id"): c for c in root.iter("mxCell")}
                edge = next(c for c in cells.values() if c.get("edge") == "1")
                self.assertEqual((edge.get("source"), edge.get("target")), ("a", "boundary"))
                a = styled.nodes["a"]
                self.assertIn("fillColor=" + a.meta["body_fill"], cells["a"].get("style"))
                self.assertIn("strokeColor=" + a.meta["body_border"], cells["a"].get("style"))

    def test_drawio_edge_ids_never_collide_with_original_node_ids(self):
        d = DK.Diagram(960, 400, "绑定")
        a = d.card("e0", 40, 140, 180, "入口")
        b = d.card("edge-e0", 340, 140, 180, "服务")
        c = d.zone("e1", 640, 120, 260, 220, "分组端点")
        d.edge(a, b)
        d.edge(b, c)
        root = ET.fromstring(d.drawio())
        cells = list(root.iter("mxCell"))
        ids = [n.get("id") for n in cells]
        self.assertEqual(len(ids), len(set(ids)))
        vertices = {n.get("id") for n in cells if n.get("vertex") == "1"}
        edges = [n for n in cells if n.get("edge") == "1"]
        self.assertEqual([(n.get("source"), n.get("target")) for n in edges],
                         [("e0", "edge-e0"), ("edge-e0", "e1")])
        self.assertTrue(all(n.get(k) in vertices for n in edges for k in ("source", "target")))

    def test_noncolliding_drawio_retains_legacy_edge_ids(self):
        d = DK.Diagram(960, 400, "兼容编号")
        a = d.card("alpha", 40, 140, 180, "甲")
        b = d.card("beta", 340, 140, 180, "乙")
        c = d.card("gamma", 640, 140, 180, "丙")
        d.edge(a, b)
        d.edge(b, c)
        cells = list(ET.fromstring(d.drawio()).iter("mxCell"))
        self.assertEqual([n.get("id") for n in cells if n.get("edge") == "1"], ["e0", "e1"])
        self.assertEqual(len(cells), len({n.get("id") for n in cells}))

    def test_old_tone_priority_plain_and_interleaved_instances(self):
        a = self.scene("frontend")
        b = self.scene("security", theme="plain")
        for role, t in b.roles.items():
            for color in t.values():
                self.assertEqual(color[1:3], color[3:5], role)
                self.assertEqual(color[3:5], color[5:7], role)
        b.svg()
        self.assertEqual(a.svg(), self.scene("frontend").svg())
        a.roles["frontend"]["solid"] = DK.PAPER
        self.assertNotEqual(a.roles, self.scene("frontend").roles)
        d = DK.Diagram(960, 400, "兼容")
        n = d.card("n", 40, 130, 320, "显式状态", role="security", tone="success")
        self.assertEqual(n.meta["body_fill"], VT.tones()["success"]["tint"])
        n = d.card("b", 450, 130, 320, "状态别名", role="security", status="warning")
        self.assertEqual(n.meta["body_fill"], VT.tones()["warning"]["tint"])

    def test_shared_role_paint_reaches_workflow_sequence_and_er_without_input_mutation(self):
        for role, t in VT.roles().items():
            c = RT.Canvas(BASE, 400)
            c.box("a", 40, 140, 200, 70, "普通", role=role)
            self.assertEqual(box_paint(c, "a"), (t["entity_border"], VT.node_surface(t)))
        examples = {s["id"]: s for s in RT._load_examples()}
        pairs = [(examples["lane-three-handoff"], "nodes", RT.workflow),
                 (examples["er-task-graph"], "entities", SE.er),
                 ({**BASE, "participants": [{"id": "a", "label": "甲"}, {"id": "b", "label": "乙"}],
                   "messages": [{"from": "a", "to": "b", "label": "请求"}]}, "participants", SE.sequence)]
        for spec, field, builder in pairs:
            base = copy.deepcopy(spec)
            for item in base[field]:
                for key in ("tone", "status", "emphasis", "role"):
                    item.pop(key, None)
            before = tree(builder(base))
            for role, t in VT.roles().items():
                styled = copy.deepcopy(base)
                styled[field][0]["role"] = role
                frozen = copy.deepcopy(styled)
                after = tree(builder(styled))
                self.assertEqual(styled, frozen)
                self.assertEqual(geometry(after), geometry(before))
                expected_fill = VT.node_surface(t) if builder is RT.workflow else t["tint"]
                self.assertTrue(any(e.get("fill") == expected_fill for e in after.iter(NS + "rect")))
                self.assertTrue(any(e.get("stroke") == t["entity_border"] for e in after.iter(NS + "rect")))


if __name__ == "__main__":
    unittest.main()
