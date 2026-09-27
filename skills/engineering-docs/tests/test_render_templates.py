"""Check semantic mappings and rejected inputs, independent of screenshot taste."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("render_templates", ROOT/"scripts/render_templates.py")
RENDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDER)
EXAMPLES = {s["id"]: s for s in json.loads((ROOT/"assets/diagram-templates/examples.json").read_text())}


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.output = Path(self.workspace.name)/"result.svg"

    def render(self, name, **updates):
        spec = copy.deepcopy(EXAMPLES[name])
        spec.update(updates)
        return RENDER.render(spec, self.output)

    def test_every_example_is_valid_xml_and_has_accessible_description(self):
        for name in EXAMPLES:
            with self.subTest(name=name):
                result = self.render(name)
                self.assertEqual(name, result["id"])
                xml = ET.parse(self.output).getroot()
                self.assertEqual(EXAMPLES[name]["note"], xml.find("{*}desc").text)
                self.assertFalse(xml.findall(".//{*}script"))

    def test_html_text_is_escaped_without_becoming_markup(self):
        self.render("system-architecture", title='结构 <&> "接口"')
        xml = ET.parse(self.output).getroot()
        self.assertEqual('结构 <&> "接口"', xml.find("{*}title").text)

    def test_real_input_does_not_receive_synthetic_label(self):
        self.render("system-architecture")
        self.assertNotIn("合成示例", self.output.read_text())
        self.render("system-architecture", sample=True)
        self.assertIn("合成示例", self.output.read_text())

    def test_pie_angles_follow_new_data(self):
        result = self.render("pie", labels=["甲","乙","丙"], values=[1,2,7])
        for observed, expected in zip(result["statistics"]["angles"], [36,72,252]):
            self.assertAlmostEqual(observed, expected, places=4)

    def test_invalid_composition_is_rejected(self):
        for values in ([0,0,0,0], [1,-1,3,4], [1,2,float("nan"),4]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.render("pie", values=values)

    def test_funnel_requires_nested_counts_and_uses_first_stage_denominator(self):
        result = self.render("funnel", values=[200,100,50,20])
        self.assertEqual(.1, result["statistics"]["overall_conversion"])
        result = self.render("funnel", values=[200,100,50,5])
        self.assertEqual(.025, result["statistics"]["overall_conversion"])
        self.assertIn("2.5%", self.output.read_text())
        with self.assertRaises(ValueError):
            self.render("funnel", values=[100,120,60,20])

    def test_radar_declared_scale_is_enforced(self):
        with self.assertRaises(ValueError):
            self.render("radar", maximum=3)

    def test_timeline_distances_follow_real_time(self):
        events = [{"at":v,"label":str(v),"detail":"事件"} for v in [0,2,8,10]]
        result = self.render("horizontal-timeline", events=events)
        # Tick circles are the actual semantic time points, not label-box centers.
        xml = ET.parse(self.output).getroot()
        xs = [float(n.get("cx")) for n in xml.findall(".//{*}circle")]
        self.assertAlmostEqual(3, (xs[2]-xs[1])/(xs[1]-xs[0]))
        self.assertEqual(4, len(result["boxes"]))
        with self.assertRaises(ValueError):
            events[2]["at"] = 2
            self.render("horizontal-timeline", events=events)

    def test_tree_cycle_and_unknown_parent_are_rejected(self):
        nodes = [{"id":"a","label":"甲"},{"id":"b","label":"乙","parent":"c"},
                 {"id":"c","label":"丙","parent":"b"}]
        with self.assertRaises(ValueError):
            self.render("hierarchy", nodes=nodes)
        with self.assertRaises(ValueError):
            self.render("hierarchy", nodes=[{"id":"a","label":"甲","parent":"missing"}])

    def test_six_level_pyramid_stays_inside_canvas(self):
        groups = [{"label":f"第{i}层","items":["支撑说明"]} for i in range(6)]
        self.render("pyramid", groups=groups)
        xml = ET.parse(self.output).getroot()
        for polygon in xml.findall(".//{*}polygon"):
            xs = [float(p.split(",")[0]) for p in polygon.get("points").split()]
            self.assertGreaterEqual(min(xs), 24)
            self.assertLessEqual(max(xs), 656)

    def test_workflow_rejects_back_edges_and_overlapping_activities(self):
        spec = copy.deepcopy(EXAMPLES["vertical-swimlane"])
        spec["edges"] = [{"from":"d","to":"a"}]
        with self.assertRaises(ValueError):
            RENDER.render(spec, self.output)
        spec["nodes"].append({"id":"e","label":"重叠","lane":0,"step":0})
        with self.assertRaises(ValueError):
            RENDER.render(spec, self.output)

    def test_long_text_is_rejected_instead_of_silently_clipped(self):
        nodes = [{"id":"a","label":"用于验证超出可读空间时是否拒绝绘制"*20}]
        with self.assertRaises(ValueError):
            self.render("hierarchy", nodes=nodes)


if __name__ == "__main__":
    unittest.main()
