"""专用旧图兜底的视觉边界：轻轮廓不能连带淡化路径或状态。"""
import importlib.util
from pathlib import Path
import unittest
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fallback_templates", ROOT / "scripts/render_templates.py")
RT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RT)


def canvas():
    return RT.Canvas({"id": "test", "name": "测试", "title": "边界", "subtitle": "测试数据", "note": "仅测试"})


class StandardSvgCheckTests(unittest.TestCase):
    def make_svg(self, root, extra):
        p = root / "plot.svg"
        p.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><title>图</title>' + extra + '<text x="10" y="60" font-size="12">数据</text></svg>')
        return p

    def test_clipping_allowed_for_standard_display_but_not_default_profile(self):
        import diagram_check as dc
        with tempfile.TemporaryDirectory() as td:
            p = self.make_svg(Path(td), '<defs><clipPath id="c"><rect width="150" height="80"/></clipPath></defs>')
            self.assertFalse(dc.static_check(p)["ok"])
            self.assertTrue(dc.static_check(p, standard_svg=True)["ok"])

    def test_standard_svg_still_rejects_script_and_foreign_html(self):
        import diagram_check as dc
        with tempfile.TemporaryDirectory() as td:
            for tag in ("script", "foreignObject"):
                p = self.make_svg(Path(td), f'<{tag}></{tag}>')
                report = dc.static_check(p, standard_svg=True)
                self.assertFalse(report["ok"])
                self.assertTrue(any(tag in item for item in report["errors"]))

    def test_standard_display_cannot_claim_board_compatibility(self):
        import diagram_check as dc
        with self.assertRaises(SystemExit):
            dc.main(["unused.svg", "--standard-svg", "--board"])


class FallbackVisualTests(unittest.TestCase):
    def test_default_entity_has_surface_and_soft_outline(self):
        c = canvas()
        c.box("n", 32, 150, 240, 80, "节点")
        rect = ET.fromstring(c.parts[-2])
        self.assertEqual(rect.get("fill"), RT.THEME["entity_fill"])
        self.assertEqual(rect.get("stroke"), RT.THEME["entity_border"])
        self.assertEqual(tuple(rect.get(k) for k in ("x", "y", "width", "height")), ("32", "150", "240", "80"))

    def test_focus_outline_remains_semantic(self):
        c = canvas()
        c.box("n", 32, 150, 240, 80, "重点", tone="accent", emphasis=True)
        rect = ET.fromstring(c.parts[-2])
        self.assertEqual(rect.get("stroke"), RT.THEME["semantic"]["accent"])

    def test_group_border_does_not_change_path_colour(self):
        c = canvas()
        c.rect(32, 150, 240, 100)
        c.path("M32 150 H272", arrow=True)
        self.assertEqual(ET.fromstring(c.parts[-2]).get("stroke"), RT.THEME["group_border"])
        self.assertEqual(ET.fromstring(c.parts[-1]).get("stroke"), RT.LINE)

    def test_filled_polygon_border_is_soft_but_unfilled_is_not(self):
        c = canvas()
        c.shape("polygon", points="0,0 10,0 5,10", fill="white", stroke=RT.LINE)
        c.shape("polygon", points="0,0 10,0 5,10", fill="none", stroke=RT.LINE)
        self.assertEqual(ET.fromstring(c.parts[-2]).get("stroke"), RT.THEME["group_border"])
        self.assertEqual(ET.fromstring(c.parts[-1]).get("stroke"), RT.LINE)

    def test_matrix_preserves_values_with_entity_surfaces(self):
        c = RT.matrix({"name": "矩阵", "title": "能力对照", "subtitle": "测试", "note": "仅测试",
                       "rows": ["格式"], "columns": ["新", "旧"], "values": [["HTML", "SVG"]]})
        texts = [x["text"] for x in c.labels]
        self.assertIn("HTML", texts)
        self.assertIn("SVG", texts)
        rects = [ET.fromstring(x) for x in c.parts if x.startswith("<rect ")]
        self.assertEqual(rects[-1].get("fill"), RT.THEME["entity_fill"])

    def test_small_card_keeps_explicit_error_colour(self):
        import structural_extra as extra
        c = canvas()
        extra.manual_box(c, "e", 32, 150, 240, 30, "错误", extra.RED_BG, extra.RED)
        rect = ET.fromstring(c.parts[-2])
        self.assertEqual(rect.get("stroke"), extra.RED)
        self.assertEqual(rect.get("fill"), extra.RED_BG)
