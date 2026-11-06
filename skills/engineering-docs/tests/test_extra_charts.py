"""Tests for the extra data charts: treemap and sankey.

Covers artifact conventions (vector SVG, manifest/stats fields), numeric
conservation (treemap children sum, sankey node in/out balance), input
rejection, and the in-canvas text overflow assertion.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets/visual-examples" / "render_extra_charts.py"
DATA = json.loads((ROOT / "assets" / "visual-examples"
                   / "chart-data-extra.json").read_text())

spec = importlib.util.spec_from_file_location("render_extra_charts", SRC)
RENDER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RENDER)
RENDER.configure()


class ExtraChartRenderTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.out = Path(self.workspace.name)

    def test_render_treemap_artifacts(self):
        manifest, stats = RENDER.render_treemap(DATA, self.out)
        self.assertEqual(manifest["id"], "22-treemap")
        for key in ("id", "type", "title", "conclusion", "source", "preview"):
            self.assertIn(key, manifest)
        svg = (self.out / "22-treemap.svg").read_text()
        self.assertTrue(svg.startswith("<?xml"))
        self.assertIn("<svg", svg)
        self.assertIn("<title>", svg)
        self.assertIn("<desc>", svg)
        self.assertNotIn("<image", svg)  # vector shapes, not an embedded bitmap
        self.assertTrue("<path" in svg or "<rect" in svg)
        self.assertTrue((self.out / "22-treemap.png").exists())
        self.assertIn("total", stats)

    def test_render_sankey_artifacts(self):
        manifest, stats = RENDER.render_sankey(DATA, self.out)
        self.assertEqual(manifest["id"], "23-sankey")
        for key in ("id", "type", "title", "conclusion", "source", "preview"):
            self.assertIn(key, manifest)
        svg = (self.out / "23-sankey.svg").read_text()
        self.assertIn("<svg", svg)
        self.assertNotIn("<image", svg)
        self.assertTrue("<path" in svg)
        self.assertTrue((self.out / "23-sankey.png").exists())
        self.assertEqual(stats["loss"], 1100.0)
        self.assertAlmostEqual(stats["loss_share"], 0.11, places=6)


class TreemapGeometryTests(unittest.TestCase):
    def test_leaf_area_shares_follow_values(self):
        layout = RENDER.compute_treemap(DATA["treemap"]["groups"])
        leaves = [(c["value"], c["rect"][2] * c["rect"][3])
                  for g in layout for c in g["children"]]
        total_value = sum(v for v, _ in leaves)
        total_area = sum(a for _, a in leaves)
        for value, area in leaves:
            # Group insets and group label strips remove a fixed amount of area,
            # so proportionality holds within ~1.5 percentage points.
            self.assertLess(abs(value / total_value - area / total_area), 0.015,
                            msg=f"leaf area share off: {value}")

    def test_group_children_sum_matches_declared_total(self):
        for g in DATA["treemap"]["groups"]:
            self.assertAlmostEqual(sum(c["value"] for c in g["children"]),
                                   g["total"], places=6)

    def test_negative_value_rejected(self):
        bad = {"groups": [{"name": "A", "total": 10,
                           "children": [{"name": "x", "value": 12},
                                        {"name": "y", "value": -2}]}]}
        with self.assertRaises(ValueError):
            RENDER.compute_treemap(bad["groups"])

    def test_parent_child_sum_mismatch_rejected(self):
        bad = {"groups": [{"name": "A", "total": 99,
                           "children": [{"name": "x", "value": 40},
                                        {"name": "y", "value": 10}]}]}
        with self.assertRaises(AssertionError):
            RENDER.compute_treemap(bad["groups"])


class SankeyConservationTests(unittest.TestCase):
    def setUp(self):
        self.nodes = DATA["sankey"]["nodes"]
        self.links = DATA["sankey"]["links"]

    def test_internal_nodes_balance_inflow_outflow(self):
        flow = RENDER.validate_sankey(self.nodes, self.links)
        for name, d in flow.items():
            if d["in"] > 0 and d["out"] > 0:
                self.assertAlmostEqual(d["in"], d["out"], places=6, msg=name)
        # totals: entry == sinks sum
        self.assertEqual(flow["入口请求"]["out"],
                         flow["缓存命中"]["in"] + flow["数据库访问"]["in"]
                         + flow["降级丢弃"]["in"])

    def test_negative_link_rejected(self):
        links = self.links + [{"source": "入口请求", "target": "订单服务",
                               "value": -5}]
        with self.assertRaises(ValueError):
            RENDER.validate_sankey(self.nodes, links)

    def test_dangling_link_rejected(self):
        links = self.links + [{"source": "入口请求", "target": "不存在",
                               "value": 5}]
        with self.assertRaises(ValueError):
            RENDER.validate_sankey(self.nodes, links)

    def test_unbalanced_internal_node_rejected(self):
        links = self.links[:]
        links.append({"source": "订单服务", "target": "数据库访问", "value": 1})
        with self.assertRaises(AssertionError):
            RENDER.validate_sankey(self.nodes, links)


class TextOverflowTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.out = Path(self.workspace.name)

    def test_oversized_title_is_rejected(self):
        with self.assertRaises(ValueError):
            RENDER.render_treemap(DATA, self.out, title="超长标题" * 30)


if __name__ == "__main__":
    unittest.main()
