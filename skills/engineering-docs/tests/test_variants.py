import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from diagram_kit import Diagram, VARIANTS
import diagram_check


class TestVariants(unittest.TestCase):
    def test_all_variants_present(self):
        for v in ("v1-review", "v2-magazine", "v3-outline", "v4-dashboard"):
            self.assertIn(v, VARIANTS)
            for k in ("claim", "radius", "neutral_border", "focal", "zone_fill", "heavy"):
                self.assertIn(k, VARIANTS[v])

    def test_variants_are_compatible_views_of_one_style(self):
        for name, view in VARIANTS.items():
            with self.subTest(name=name):
                self.assertEqual(view, VARIANTS["v1-review"])
                self.assertEqual(view["neutral_border"], "#D9E2E8")
                self.assertEqual(view["heavy"], "none")

    def test_render_each_variant_clean(self):
        for v in VARIANTS:
            d = Diagram(900, 600, "t", theme="doubao", variant=v)
            a = d.card("a", 40, 120, 200, "节点 A", desc="说明")
            b = d.card("b", 320, 120, 200, "焦点 B", desc="重点", emphasis=True, tone="accent")
            d.edge(a, b, style="main")
            rep = d.save(f"/tmp/v_{v}.svg")
            self.assertEqual(rep["issues"], [], f"{v} issues: {rep['issues']}")

    def test_v4_alias_collapses_to_review_posture(self):
        # v4-dashboard is a deprecated alias; it must not emit its own dark header
        # pill — every historical variant label collapses to the review posture.
        d = Diagram(900, 500, "t", theme="doubao", variant="v4-dashboard")
        d.phase_banner("p1", 40, 120, 800, "01", "阶段一", "副标题")
        self.assertEqual(d.variant["claim"], VARIANTS["v1-review"]["claim"])
        svg = d.save("/tmp/v4pill.svg")
        self.assertNotIn("#1B1D22", open("/tmp/v4pill.svg").read())

    def test_invalid_variant_falls_back(self):
        d = Diagram(900, 400, "t", theme="doubao", variant="nope")
        self.assertEqual(d.variant["claim"], VARIANTS["v1-review"]["claim"])

    def test_no_arg_default_is_unified_neutral_style(self):
        """Legacy names resolve to the white, neutral, shadow-free default."""
        from diagram_kit import DEFAULT_THEME, THEME_ALIASES
        self.assertEqual(DEFAULT_THEME, "document-neutral")
        self.assertEqual(THEME_ALIASES["doubao"], DEFAULT_THEME)
        self.assertEqual(THEME_ALIASES["default"], DEFAULT_THEME)
        d = Diagram(900, 600, "t")
        self.assertEqual(d.theme_name, DEFAULT_THEME)
        d.zone("z", 40, 120, 820, 200, "服务层")
        d.verdict_bar("v", 40, 360, 820, "结论：待验收")
        svg = d.svg().upper()
        self.assertIn('FILL="#FFFFFF"', svg)
        self.assertIn('FILL="#FAFAF8"', svg)
        self.assertNotIn("#1B1D22", svg)
        self.assertNotIn("#FBFAF7", svg)
        self.assertNotIn("#F3EEE5", svg)
        self.assertNotIn("FEDROPSHADOW", svg)

    def test_doubao_theme_alias_runs_same_default(self):
        """theme='doubao'/'cream' legacy scripts must not error and render the same
        unified default (the conclusion primitives are theme-independent)."""
        a = Diagram(900, 600, "t", theme="doubao")
        b = Diagram(900, 600, "t", theme="cream")
        self.assertEqual(a.theme_name, b.theme_name)
        a.verdict_bar("v", 40, 120, 820, "结论")
        b.verdict_bar("v", 40, 120, 820, "结论")
        self.assertEqual(a.svg(), b.svg())

    def test_plain_is_the_single_muted_opt_in(self):
        """theme='plain' is the only alternate style: neutral, no accent colour."""
        d = Diagram(900, 600, "t", theme="plain")
        self.assertEqual(d.theme_name, "plain")
        d.zone("z", 40, 120, 820, 200, "服务层")
        svg = d.svg().upper()
        # plain surface is white; it must not pick up the warm cream panel
        self.assertNotIn("#F3EEE5", svg)
        self.assertNotIn("#FBFAF7", svg)

    def test_emphasis_card_text_not_crossing_edge(self):
        """Regression: a focal (emphasis) card's desc must wrap/high enough that the last
        line stays inside the rect — measure must account for the focal-dot inset."""
        d = Diagram(900, 600, "t", theme="doubao", variant="v1-review")
        d.card("op", 40, 120, 360, "One Page",
               desc="全貌、当前进度、里程碑、依赖和产物入口", emphasis=True, tone="accent")
        path = "/tmp/reg_inset.svg"
        d.save(path)
        import xml.etree.ElementTree as ET
        root = ET.parse(path).getroot()
        g = [x for x in root.iter() if x.tag.endswith("g") and x.get("data-id") == "op"][0]
        rect = [c for c in g if c.tag.endswith("rect")][0]
        rh = float(rect.get("y")) + float(rect.get("height"))
        texts = [t for t in g if t.tag.endswith("text")]
        for t in texts:
            bottom = float(t.get("y")) + float(t.get("font-size")) * 0.25
            self.assertLess(bottom, rh - 6, f"text {t.text!r} crosses card bottom")

    def test_static_rule_flags_crossing_text(self):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">'
               '<g data-kind="card" data-id="bad"><rect x="40" y="40" width="200" height="60"/>'
               '<text x="55" y="98" font-size="14">贴底文字</text></g></svg>')
        open("/tmp/bad_inset.svg", "w").write(svg)
        errs, warns = [], []
        import xml.etree.ElementTree as ET
        root = ET.fromstring(svg)
        ns = "{http://www.w3.org/2000/svg}"
        diagram_check._layout_rules(root, ns, 400, 300, errs, warns)
        self.assertTrue(any("穿" in e or "内边距" in w for e in errs for w in [0]) or warns)


if __name__ == "__main__":
    unittest.main()
