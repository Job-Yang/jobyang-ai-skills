"""v2.3 extra structural layouts: rendering, validation and gold-standard lint."""
import base64
import binascii
import importlib.util
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RT = _load("render_templates", "scripts/render_templates.py")
SE = _load("structural_extra", "scripts/structural_extra.py")
DC = _load("diagram_check", "scripts/diagram_check.py")

EXTRA = {s["id"]: s for s in json.loads((ROOT / "assets/diagram-templates/examples_extra.json").read_text())}


def png_bytes(w=64, h=40, rgb=(230, 235, 245)):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(t, d):
        body = t + d
        return struct.pack(">I", len(d)) + body + struct.pack(">I", zlib.crc32(body))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


BASE = {"id": "t", "name": "测试", "title": "测试标题", "subtitle": "副标题", "note": "备注"}


class ExtraRenderTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)

    def render(self, builder, spec):
        out = Path(self.workspace.name) / f"{spec.get('id','x')}.svg"
        builder({**BASE, **spec}).save(out)
        return out.read_text()

    # ---- valid cases: gold standards render and carry key tags -------------
    def test_gold_stage_gate(self):
        svg = self.render(SE.BUILDERS["stage_gate"], EXTRA["sg-stage-gate"])
        self.assertIn("<svg", svg)
        self.assertIn("viewBox", svg)
        self.assertNotIn("polygon", svg)       # 门禁用可编辑圆角胶囊，不用会被画板冻结的多边形
        self.assertIn("rx=\"19.0\"", svg)       # 胶囊 rx 小于窄边一半，避免被画板判为椭圆而冻结
        self.assertIn("通过", svg)
        self.assertIn("阻断", svg)             # 阻断结论

    def test_gold_causal_chain(self):
        svg = self.render(SE.BUILDERS["causal_chain"], EXTRA["cc-causal-chain"])
        self.assertIn("<svg", svg)
        self.assertIn("+ 增强", svg)
        self.assertIn("− 抑制", svg)

    def test_gold_feedback_loop(self):
        svg = self.render(SE.BUILDERS["feedback_loop"], EXTRA["fl-feedback-loop"])
        self.assertIn("<svg", svg)
        self.assertIn("负反馈", svg)
        self.assertIn("自我收敛", svg)
        self.assertIn("人工标注修正", svg)      # 外部干预点

    def test_gold_state_machine(self):
        svg = self.render(SE.BUILDERS["state_machine"], EXTRA["sm-state-machine"])
        self.assertIn("<svg", svg)
        self.assertIn("viewBox", svg)
        self.assertIn("重试", svg)              # 唯一回退边标签

    def test_end_state_is_two_nested_editable_rects_with_clear_gap(self):
        import xml.etree.ElementTree as ET
        svg = self.render(SE.BUILDERS["state_machine"], EXTRA["sm-state-machine"])
        root = ET.fromstring(svg)
        ns = "{http://www.w3.org/2000/svg}"
        rects = [(float(r.get("x")), float(r.get("y")), float(r.get("width")),
                  float(r.get("height")), float(r.get("rx") or 0))
                 for r in root.iter(ns + "rect") if r.get("x") and r.get("y")]
        # final state = two rounded rects; the inner one must be inset >=5 from the
        # outer on every side (a clear double-frame gap), and both stay editable.
        found = False
        for outer in rects:
            for inner in rects:
                if inner is outer:
                    continue
                dx, dy = inner[0] - outer[0], inner[1] - outer[1]
                if 5 <= dx <= 8 and 5 <= dy <= 8:
                    self.assertGreater(outer[2], inner[2])   # outer wider
                    self.assertGreater(outer[3], inner[3])  # outer taller
                    self.assertLess(inner[4], inner[3] / 2 + 1e-6)  # rx < half narrow side
                    found = True
        self.assertTrue(found, "终态缺少两个间距≥5px的嵌套圆角矩形")
        self.assertNotIn("<polygon", svg)              # 终态必须是可编辑圆角矩形
        self.assertNotIn("<ellipse", svg)

    def test_retry_route_uses_below_card_channel_and_does_not_cross_cards(self):
        import xml.etree.ElementTree as ET
        svg = self.render(SE.BUILDERS["state_machine"], EXTRA["sm-state-machine"])
        root = ET.fromstring(svg)
        ns = "{http://www.w3.org/2000/svg}"
        # the dashed retry path exists and runs below every card box (channel)
        dashes = [p.get("d") for p in root.iter(ns + "path")
                  if p.get("stroke-dasharray")]
        self.assertTrue(dashes, "回退边应为虚线")
        # the internal geometry guard must not fire on the gold standard (would raise)
        self.render(SE.BUILDERS["state_machine"], EXTRA["sm-state-machine"])

    def test_gold_image_annotate_embeds_base64_and_legend(self):
        svg = self.render(SE.BUILDERS["image_annotate"], EXTRA["ia-sample-review"])
        self.assertIn("data:image/png;base64,", svg)
        for n in range(1, 4):                  # 图例编号齐全
            self.assertIn(f"问题：", svg)
        self.assertIn("动作：", svg)

    def test_gold_lane_workflow_renders(self):
        out = Path(self.workspace.name) / "lane.svg"
        RT.STRUCTURAL["workflow"]({**BASE, **EXTRA["lane-three-handoff"], "sample": True}).save(out)
        svg = out.read_text()
        self.assertIn("<svg", svg)
        self.assertIn("鉴权后转发", svg)        # 带标签的跨泳道边

    # ---- invalid inputs must raise ValueError ------------------------------
    def test_stage_gate_rejects_bad_gates(self):
        good = dict(EXTRA["sg-stage-gate"])
        with self.assertRaises(ValueError):   # 门禁数量与阶段不匹配
            self.render(SE.stage_gate, {**good, "gates": good["gates"][:1]})
        bad = json.loads(json.dumps(good))
        bad["gates"][0]["status"] = "maybe"   # 非法状态
        with self.assertRaises(ValueError):
            self.render(SE.stage_gate, bad)
        dup = json.loads(json.dumps(good))
        dup["stages"][1]["id"] = dup["stages"][0]["id"]  # 重复 id
        with self.assertRaises(ValueError):
            self.render(SE.stage_gate, dup)

    def test_causal_chain_rejects_dangling_and_bad_polarity(self):
        good = dict(EXTRA["cc-causal-chain"])
        dangling = json.loads(json.dumps(good))
        dangling["links"][0]["to"] = "ghost"   # 悬空边
        with self.assertRaises(ValueError):
            self.render(SE.causal_chain, dangling)
        bad = json.loads(json.dumps(good))
        bad["links"][0]["polarity"] = "x"      # 极性非法
        with self.assertRaises(ValueError):
            self.render(SE.causal_chain, bad)
        dup = json.loads(json.dumps(good))
        dup["chain"][1]["id"] = dup["chain"][0]["id"]  # 重复 id
        with self.assertRaises(ValueError):
            self.render(SE.causal_chain, dup)

    def test_feedback_loop_rejects_bad_polarity_and_missing_trigger(self):
        good = dict(EXTRA["fl-feedback-loop"])
        bad = json.loads(json.dumps(good))
        bad["polarity"] = "sideways"           # 极性非法
        with self.assertRaises(ValueError):
            self.render(SE.feedback_loop, bad)
        missing = json.loads(json.dumps(good))
        del missing["trigger"]                 # 缺触发条件
        with self.assertRaises(ValueError):
            self.render(SE.feedback_loop, missing)

    def test_state_machine_rejects_dangling_edges_and_bad_start(self):
        good = dict(EXTRA["sm-state-machine"])
        dangling = json.loads(json.dumps(good))
        dangling["transitions"][0]["to"] = "ghost"   # 悬空边
        with self.assertRaises(ValueError):
            self.render(SE.state_machine, dangling)
        badstart = json.loads(json.dumps(good))
        badstart["start"] = "ghost"                   # 未知起点
        with self.assertRaises(ValueError):
            self.render(SE.state_machine, badstart)
        notfirst = json.loads(json.dumps(good))        # start 不是 states 第一个
        notfirst["states"] = [notfirst["states"][1], notfirst["states"][0]]
        notfirst["start"] = "idle"
        with self.assertRaises(ValueError):
            self.render(SE.state_machine, notfirst)

    def test_state_machine_rejects_duplicate_pair_edges_and_branch_off_start(self):
        good = dict(EXTRA["sm-state-machine"])
        dup = json.loads(json.dumps(good))
        dup["transitions"].append({"from": "fail", "to": "idle", "label": "又试一次"})
        with self.assertRaises(ValueError):           # 同一对状态两条重叠边
            self.render(SE.state_machine, dup)
        offstart = json.loads(json.dumps(EXTRA["sm-order-fulfillment"]))
        offstart["transitions"].append({"from": "created", "to": "paid", "label": "跳过"})
        # 从起点出发的第二条前向迁移要挂分叉，但起点是实心圆不能挂分叉
        with self.assertRaises(ValueError):
            self.render(SE.state_machine, offstart)

    def test_state_machine_guards_detect_crossings(self):
        """几何守卫本身：穿卡检测与正交交叉检测必须能抓到非法走线
        （合法 spec 由布局算法保证不触发；这里直接喂非法走线断言 raise）。"""
        boxes = {"sm-a": (100, 200, 100, 46)}
        # 一条边从 (150,100) 垂直落到 (150,300)，正好穿过 sm-a 内部
        hit = SE._polyline_clears_boxes([(150, 100), (150, 300)], boxes, exclude=set())
        self.assertEqual(hit, "sm-a")
        self.assertIsNone(SE._polyline_clears_boxes([(50, 100), (250, 100)], boxes, exclude=set()))
        # 水平边与垂直边在内部正交交叉 → True；共用端点 → False
        self.assertTrue(SE._hv_cross_interior(((100, 50), (200, 50)), ((150, 0), (150, 100))))
        self.assertFalse(SE._hv_cross_interior(((100, 50), (200, 50)), ((100, 0), (100, 100))))

    def test_gold_order_fulfillment_stress_renders_with_key_nodes(self):
        svg = self.render(SE.BUILDERS["state_machine"], EXTRA["sm-order-fulfillment"])
        for label in ("支付处理中", "已支付", "已完成", "支付失败", "超时关闭"):
            self.assertIn(label, svg)
        for label in ("发起支付", "支付成功", "支付失败", "重试支付", "履约完成", "超过30分钟"):
            self.assertIn(label, svg)
        self.assertNotIn("<polygon", svg)
        self.assertNotIn("<ellipse", svg)
        # 回退边为虚线
        import xml.etree.ElementTree as ET
        root = ET.fromstring(svg)
        ns = "{http://www.w3.org/2000/svg}"
        self.assertTrue([p for p in root.iter(ns + "path") if p.get("stroke-dasharray")],
                        "回退边应为虚线")

    def test_image_annotate_rejects_out_of_bounds_and_gaps(self):
        b64 = binascii.b2a_base64(png_bytes(100, 100)).decode().strip()
        base = {"image_b64": b64, "markers": [{"n": 1, "x": 10, "y": 10, "w": 50, "h": 30,
                                               "problem": "p", "action": "a"}]}
        self.render(SE.image_annotate, base)            # 合法
        oob = json.loads(json.dumps(base))
        oob["markers"][0]["w"] = 500                    # 超出截图边界
        with self.assertRaises(ValueError):
            self.render(SE.image_annotate, oob)
        gap = json.loads(json.dumps(base))
        gap["markers"] = [gap["markers"][0], dict(gap["markers"][0], n=3)]  # 编号不连续
        with self.assertRaises(ValueError):
            self.render(SE.image_annotate, gap)


class GoldStandardLintTests(unittest.TestCase):
    """Every gold-standard SVG must pass diagram_check statically with no errors."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.paths = {}
        for sid, spec in EXTRA.items():
            out = Path(cls.tmp.name) / f"{sid}.svg"
            if spec["layout"] in SE.BUILDERS:
                SE.BUILDERS[spec["layout"]]({**BASE, **spec, "sample": True}).save(out)
            else:
                RT.STRUCTURAL[spec["layout"]]({**BASE, **spec, "sample": True}).save(out)
            cls.paths[sid] = out

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_static_errors(self):
        for sid, path in self.paths.items():
            with self.subTest(sid=sid):
                result = DC.static_check(path)
                self.assertEqual([], result["errors"],
                                 f"{sid} 静态错误: {result['errors']}")
                if result["warnings"]:
                    print(f"\n[{sid}] warnings: {result['warnings']}")


class SequenceErTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)

    def render(self, builder, spec):
        out = Path(self.workspace.name) / f"{spec.get('id','x')}.svg"
        builder({**BASE, **spec}).save(out)
        return out.read_text()

    def test_gold_sequence_renders_lifelines_and_groups(self):
        svg = self.render(SE.BUILDERS["sequence"], EXTRA["seq-agent-dispatch"])
        for p in EXTRA["seq-agent-dispatch"]["participants"]:
            self.assertIn(p["label"], svg)
        self.assertIn("派活", svg)
        self.assertIn("stroke-dasharray", svg)  # lifelines and async messages

    def test_sequence_rejects_bad_specs(self):
        two = [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]
        with self.assertRaises(ValueError):
            SE.sequence({**BASE, "participants": two, "messages": [{"from": "a", "to": "c", "label": "x"}]})
        with self.assertRaises(ValueError):
            SE.sequence({**BASE, "participants": two, "messages": [{"from": "a", "to": "a", "label": "x"}]})
        with self.assertRaises(ValueError):  # label wider than the gap between lifelines
            SE.sequence({**BASE, "participants": two + [{"id": "c", "label": "C"}, {"id": "d", "label": "D"},
                                                         {"id": "e", "label": "E"}],
                         "messages": [{"from": "a", "to": "b", "label": "这是一条非常非常长放不下的消息标签"}]})

    def test_gold_er_renders_cardinality(self):
        svg = self.render(SE.BUILDERS["er"], EXTRA["er-task-graph"])
        self.assertIn("0..*", svg)
        self.assertIn("Task 任务节点", svg)

    def test_er_rejects_relation_through_entity(self):
        ents = [{"id": "a", "label": "A", "col": 0, "row": 0}, {"id": "b", "label": "B", "col": 1, "row": 0},
                {"id": "c", "label": "C", "col": 2, "row": 0}]
        with self.assertRaises(ValueError):
            SE.er({**BASE, "entities": ents, "relations": [{"from": "a", "to": "c", "card_from": "1", "card_to": "1"}]})

    def test_state_machine_multi_back_edges_do_not_overlap(self):
        # 3 条回退 + 父子回退：渲染期硬检查（共线重叠、回退横穿前向）都要通过
        svg = self.render(SE.BUILDERS["state_machine"], EXTRA["sm-task-lifecycle"])
        self.assertIn("退回重跑", svg)
        self.assertIn("条件满足", svg)

    def test_state_machine_rejects_collinear_back_edges(self):
        states = [{"id": "s", "label": "S"}, {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
                  {"id": "c", "label": "C", "kind": "end"}]
        trans = [{"from": "s", "to": "a", "label": "1"}, {"from": "a", "to": "b", "label": "2"},
                 {"from": "b", "to": "c", "label": "3"}, {"from": "b", "to": "s", "label": "x"},
                 {"from": "b", "to": "a", "label": "y"}, {"from": "c", "to": "a", "label": "z"},
                 {"from": "c", "to": "s", "label": "w"}]
        with self.assertRaises(ValueError):
            SE.state_machine({**BASE, "start": "s", "states": states, "transitions": trans})


if __name__ == "__main__":
    unittest.main()
