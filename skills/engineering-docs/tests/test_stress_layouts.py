"""Stress-layout regression tests: compact extensible horizontal swimlanes and
the refined thin-ring donut. Owned by the v2.3 layout-rewrite change."""
import copy
import importlib.util
import json
import sys
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
SPEC = importlib.util.spec_from_file_location("render_templates", ROOT/"scripts/render_templates.py")
RENDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDER)
STRESS = {s["id"]: s for s in json.loads((ROOT/"assets/diagram-templates/examples_stress.json").read_text())}


def _rects(path):
    root = ET.parse(path).getroot()
    out = []
    for r in root.iter():
        if r.tag.endswith("rect") and r.get("x") is not None and r.get("y") is not None:
            out.append({"x": float(r.get("x")), "y": float(r.get("y")),
                        "w": float(r.get("width")), "h": float(r.get("height")),
                        "fill": (r.get("fill") or "").upper()})
    return out


class SwimlaneStressTests(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.TemporaryDirectory()
        self.addCleanup(self.ws.cleanup)
        self.out = Path(self.ws.name)/"lane.svg"

    def render(self, spec):
        return RENDER.render({**spec, "sample": True}, self.out)

    def test_deep_six_lanes_renders_and_is_compact(self):
        spec = STRESS["deep-lane-6-roles"]
        result = self.render(spec)
        self.assertEqual(6, len(spec["lanes"]))
        self.assertEqual(12, len(spec["nodes"]))
        # every card lives in self.boxes; no overlap/overflow already enforced by Canvas
        self.assertEqual(12, len(result["boxes"]))
        rects = _rects(self.out)
        lane_rects = [r for r in rects if abs(r["w"]-616) < 1.0]
        self.assertEqual(6, len(lane_rects), "one background rect per lane")
        cards = list(result["boxes"].values())
        self.assertEqual(12, len(cards))
        # density: each lane hugs its tallest card (no big vertical whitespace)
        for lane in lane_rects:
            inside = [c for c in cards
                      if lane["y"]-1 <= c[1] and c[1]+c[3] <= lane["y"]+lane["h"]+1]
            self.assertTrue(inside, "every lane must contain cards")
            tallest = max(c[3] for c in inside)
            self.assertLessEqual(lane["h"], tallest*1.55+6,
                                 f"lane has too much whitespace ({lane['h']} vs card {tallest})")
            for c in inside:  # cards sit inside their lane (no overflow)
                self.assertGreaterEqual(c[1], lane["y"]-1)
                self.assertLessEqual(c[1]+c[3], lane["y"]+lane["h"]+1)
        # total height must not explode: 6 lanes / 12 cards stays compact
        self.assertLess(result["height"], 950, "swimlane total height exploded")
        self.assertGreater(result["height"], 600, "diagram collapsed")

    def test_too_many_lanes_and_steps_are_rejected(self):
        base = copy.deepcopy(STRESS["deep-lane-6-roles"])
        base["lanes"] = ["l%d" % i for i in range(7)]  # 7 > 6
        with self.assertRaises(ValueError):
            self.render(base)
        base2 = copy.deepcopy(STRESS["deep-lane-6-roles"])
        # force 9 columns: spread two nodes onto steps 7 and 8
        for n in base2["nodes"]:
            if n["id"] == "h":
                n["step"] = 7
            if n["id"] == "p2":
                n["step"] = 8
        with self.assertRaises(ValueError):
            self.render(base2)

    def test_back_edge_crossing_a_card_raises(self):
        # three lanes, all three at step 0; edge skips lane0->lane2 straight through lane1 card
        spec = {
            "id": "x-lane-cross", "name": "t", "layout": "workflow", "orientation": "horizontal",
            "title": "t", "subtitle": "t", "note": "t",
            "lanes": ["A", "B", "C"],
            "nodes": [{"id": "a", "lane": 0, "step": 0, "label": "起点"},
                      {"id": "mid", "lane": 1, "step": 0, "label": "被穿卡"},
                      {"id": "b", "lane": 2, "step": 0, "label": "终点"}],
            "edges": [{"from": "a", "to": "b"}],
        }
        with self.assertRaises(ValueError):
            self.render(spec)


class DonutStressTests(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.TemporaryDirectory()
        self.addCleanup(self.ws.cleanup)
        self.out = Path(self.ws.name)/"donut.svg"

    def render(self, **over):
        spec = copy.deepcopy(STRESS["donut-big-share"])
        spec.update(over)
        return RENDER.render({**spec, "sample": True}, self.out)

    def _svg(self):
        return self.out.read_text()

    def test_big_share_donut_renders_vector_and_sorted(self):
        result = self.render()
        shares = result["statistics"]["shares"]
        self.assertAlmostEqual(sum(shares), 1.0, places=6)
        self.assertAlmostEqual(sum(result["statistics"]["angles"]), 360.0, places=3)
        # descending by value
        self.assertEqual(shares, sorted(shares, reverse=True))
        self.assertAlmostEqual(result["statistics"]["theta2"][0], 90.0, places=1)
        # thin ring: inner/outer ratio within 0.70–0.78
        self.assertGreaterEqual(result["statistics"]["inner_ratio"], 0.70)
        self.assertLessEqual(result["statistics"]["inner_ratio"], 0.78)
        svg = self._svg()
        self.assertIn("<text", svg)
        self.assertIn("<path", svg)
        self.assertNotIn("<image", svg)

    def test_even_multi_item_donut_renders(self):
        result = self.render(**{k: STRESS["donut-even"][k] for k in ("labels", "values", "unit")})
        self.assertEqual(7, len(result["statistics"]["shares"]))
        self.assertAlmostEqual(sum(result["statistics"]["shares"]), 1.0, places=6)
        svg = self._svg()
        self.assertIn("<text", svg)
        self.assertNotIn("<image", svg)

    def test_invalid_composition_is_rejected(self):
        for values in ([0, 0, 0], [-1, 2, 3], [1, 2, float("nan")]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.render(values=values)
        # more than 8 items rejected
        with self.assertRaises(ValueError):
            self.render(labels=list("abcdefghi"), values=[1]*9)


if __name__ == "__main__":
    unittest.main()
