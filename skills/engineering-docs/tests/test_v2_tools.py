import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import diagram_kit  # noqa: E402
from diagram_kit import Diagram, LayoutError, wrap  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


doc_check = load("doc_check")
diagram_check = load("diagram_check")
lark_bind = load("lark_bind")

LAYERED_DOC = """# 插件组合治理方案

> **方案主张：** 0.5.0 只加一层组合治理：插件先过准入，再按接缝所有权挂载，核心不改。
>
> **当前范围：** 覆盖社区插件准入与 profile 分层，不改 DSH Runtime。

两个插件争抢同一接缝已造成 3 次回合中断。请评审是否批准治理设计和 10 月底上线计划。

![总体设计](diagrams/arch.svg)

先看中间的治理层，后文按准入、分层、度量的顺序展开。

## 准入流水线：先试用再钉版

新插件要过四步才能进入 daily profile，四步都在本机完成。

| 步骤 | 通过条件 |
| --- | --- |
| 静态检查 | 声明的接缝与清单不冲突 |

## Profile 分层

daily、deep、night、lab 四个 profile 各自锁定插件集合，lab 用于试用。

## 本机度量

每个回合记录上下文长度和成本，超过阈值时提示回到 lab 复查。

## 发布与回退

先在作者本机灰度一周，出现接缝冲突时回退到 0.4.0 的插件集合。
"""


class DiagramKitTests(unittest.TestCase):
    def build(self):
        d = Diagram(1200, 640, title="写入只经过网关", subtitle="目标架构")
        d.legend([("line", "调用", "main")], x=40, y=104)
        a = d.card("api", 60, 200, 300, "任务 API", desc="接收并校验任务", badge="1")
        g = d.card("gw", 480, 200, 300, "网关", code="POST /v1/tasks", tone="accent", emphasis=True,
                   chips=[("独占写入", "filled", "accent"), "可回放"])
        d.zone_around("svc", [a, g], "服务层")
        d.edge(a, g, label="转发", style="main")
        d.note("t1", 60, 440, 360, "只有一条写路径", "所有写入都经过网关")
        return d

    def test_rows_list_each_member_with_its_tag(self):
        d = Diagram(1200, 640, title="写入只经过网关", subtitle="目标架构")
        rows = [("订单库", "唯一写入方", "filled", "accent"), ("库存库", "唯一写入方", "filled", "accent"),
                ("报表副本", "只读"), "归档存储"]
        plain = d.measure_card(320, "存储")
        s = d.card("store", 60, 200, 320, "存储", rows=rows)
        self.assertAlmostEqual(s.h - plain, d.s("gap") + 4 * d._row_h(), places=3)
        with tempfile.TemporaryDirectory() as tmp:
            svg, drawio = Path(tmp) / "a.svg", Path(tmp) / "a.drawio"
            self.assertEqual(d.save(str(svg), drawio=str(drawio))["issues"], [])
            text = svg.read_text(encoding="utf-8")
            self.assertEqual(text.count(">唯一写入方<"), 2)
            self.assertIn("归档存储", text)
            self.assertIn("报表副本 &lt;b&gt;[只读]&lt;/b&gt;", drawio.read_text(encoding="utf-8"))
        with self.assertRaises(LayoutError):
            Diagram(1200, 640, title="t").card("x", 60, 200, 160, "存储", rows=[("一个很长很长的存储名字", "唯一写入方")])

    def test_clean_diagram_has_no_issues_and_valid_outputs(self):
        d = self.build()
        with tempfile.TemporaryDirectory() as tmp:
            svg, drawio = Path(tmp) / "a.svg", Path(tmp) / "a.drawio"
            report = d.save(str(svg), drawio=str(drawio))
            self.assertEqual(report["issues"], [])
            self.assertGreaterEqual(report["min_font_at_800px"], 9)
            root = ET.fromstring(svg.read_text(encoding="utf-8"))
            self.assertIn("viewBox", root.attrib)
            text = svg.read_text(encoding="utf-8")
            self.assertIn('data-kind="card" data-id="gw"', text)
            self.assertIn('data-kind="edge" data-from="api" data-to="gw"', text)
            model = ET.fromstring(drawio.read_text(encoding="utf-8"))
            edges = [c for c in model.iter("mxCell") if c.get("edge") == "1"]
            self.assertEqual(edges[0].get("source"), "api")
            self.assertEqual(edges[0].get("target"), "gw")

    def test_rounded_corners_never_exceed_half_height(self):
        text = self.build().svg()
        for m in re.finditer(r'<rect [^>]*height="([\d.]+)" rx="([\d.]+)"', text):
            self.assertLessEqual(float(m.group(2)), float(m.group(1)) / 2 + 1e-6)

    def test_arrow_markers_use_plain_auto_orient(self):
        text = self.build().svg()
        self.assertIn('orient="auto"', text)
        self.assertNotIn("auto-start-reverse", text)

    def test_overlong_title_raises_instead_of_shrinking(self):
        d = Diagram(960, 400, title="t")
        with self.assertRaises(LayoutError):
            d.card("x", 40, 120, 120, "Desktop / Agent Loop Runtime")

    def test_overlap_and_crossing_are_reported(self):
        d = Diagram(960, 500, title="t")
        a = d.card("a", 40, 120, 200, "A")
        d.card("b", 150, 150, 200, "B")
        d.card("m", 420, 100, 160, "M", desc="挡在连线上")
        c = d.card("c", 700, 130, 200, "C")
        d.edge(a, c, style="main")
        issues = d.check()["issues"]
        self.assertTrue(any("overlap: a / b" in i for i in issues))
        self.assertTrue(any("crosses m" in i for i in issues))
        self.assertFalse(any("crosses b" in i or "crosses c" in i for i in issues))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(LayoutError):
            d.save(str(Path(tmp) / "x.svg"))

    def test_straight_edge_through_overlap_of_facing_sides(self):
        d = Diagram(960, 500, title="t")
        a = d.card("a", 40, 120, 200, "A", desc="一行")
        b = d.card("b", 400, 110, 200, "B", desc="两行说明文字会让这张卡片更高一些，更高")
        pts = d.edge(a, b, style="main")
        self.assertEqual(len(pts), 2)
        self.assertAlmostEqual(pts[0][1], pts[1][1])

    def test_wrap_keeps_latin_words_whole(self):
        lines = wrap("换公司只换 Provider、MCP、Company Overlay；凭证不进迁移包。", 300, 16.25)
        self.assertTrue(all(not l.endswith("O") for l in lines))
        self.assertIn("Overlay", "".join(lines))
        self.assertFalse(any(l.startswith(("，", "。", "、")) for l in lines))

    def test_golden_examples_build_cleanly(self):
        for name in ("config-release", "personal-harness", "transactionapp-overview"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "arch.svg"
                p = subprocess.run([sys.executable, str(ROOT / "assets/examples" / name / "arch.py"), str(out)],
                                   capture_output=True, text=True, timeout=60)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn("'issues': []", p.stdout)
                self.assertTrue(out.with_suffix(".drawio").exists())
                r = diagram_check.static_check(out)
                self.assertTrue(r["ok"], r["errors"])
                self.assertEqual(r["warnings"], [])
                self.assertLessEqual(r["metrics"]["hue_families"], 3)
                self.assertLessEqual(r["metrics"]["aspect_h_over_w"], 1.3)

    def test_wrap_breaks_at_meaningful_points(self):
        self.assertEqual(wrap("人工提交与审批", 98, 16.25), ["人工提交", "与审批"])
        self.assertEqual(wrap("Schema、权限与冲突检查", 188, 16.25), ["Schema、", "权限与冲突检查"])
        self.assertEqual(wrap("每次变更一个不可变版本", 158, 16.25), ["每次变更一个", "不可变版本"])
        for text, width in (("人工提交与审批", 98), ("每次变更一个不可变版本", 158), ("长连接推送，断连时客户端用旧值", 158)):
            lines = wrap(text, width, 16.25)
            self.assertGreater(len(lines[-1]), 1, lines)

    def test_arrow_between_touching_cards_is_reported(self):
        d = Diagram(960, 500, title="t")
        a = d.card("a", 40, 120, 200, "A")
        b = d.card("b", 40, a.bottom + 12, 200, "B")
        d.edge(a, b, "bottom", "top", style="main")
        self.assertTrue(any("too" in i or "only" in i for i in d.check()["issues"]))

    def test_phase_banner_has_index_and_conclusion(self):
        d = Diagram(960, 420, title="三阶段总览")
        d.phase_banner("b1", 40, 100, 880, "01", "工程准备", "控制编译范围")
        text = d.svg()
        self.assertIn(">01<", text)
        self.assertIn("工程准备", text)
        self.assertIn("控制编译范围", text)
        self.assertIn('data-kind="banner"', text)

    def test_card_legend_sample_matches_card_fill_and_stroke(self):
        d = Diagram(960, 420, title="状态图例")
        d.card("c", 40, 120, 200, "新增件", tone="accent", emphasis=True)
        d.legend([("card", "已有能力", "neutral"), ("card", "项目新增", "accent"),
                  ("card", "待确认", "orange")])
        text = d.svg()
        # Focal marks and legend samples use the same semantic tokens.
        self.assertIn("#4F6B9A", text.upper())
        self.assertIn("#9A6A2F", text.upper())
        self.assertIn("项目新增", text)

    def test_legend_stress_long_chinese_wraps_and_never_overlaps(self):
        """6–8 legend items with long Chinese labels must wrap / shrink cleanly:
        the render-time geometry guard raises on any text↔swatch / text↔text
        overlap or margin breach instead of silently covering labels."""
        items = [
            ("card", "已有核心能力清单", "neutral"),
            ("card", "本项目新增交付项", "accent"),
            ("card", "待确认待部署事项", "orange"),
            ("zone", "本阶段新增覆盖区域", "accent", True),
            ("line", "主调用与下发顺序", "main"),
            ("dot", "外部依赖系统", "green"),
            ("line", "失败重试与人工介入路径", "alert"),
        ]
        d = Diagram(1200, 760, title="压力测试图例")
        d.legend(items)
        text = d.svg()
        for _, label, *_ in items:
            self.assertIn(label, text)
        # an impossible legend (one label wider than the whole safe band even at
        # the shrink floor) must raise LayoutError, not silently overlap.
        tiny = Diagram(960, 600, title="t")
        with self.assertRaises(LayoutError):
            tiny.legend([("card", "超长长中文标签" * 40, "neutral")])

    def test_checker_accepts_board_as_lark_alias(self):
        d = self.build()
        with tempfile.TemporaryDirectory() as tmp:
            svg = Path(tmp) / "a.svg"
            d.save(str(svg))
            p = subprocess.run([sys.executable, str(SCRIPTS / "diagram_check.py"), str(svg)],
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(p.returncode, 0, p.stderr)
            help_text = subprocess.run([sys.executable, str(SCRIPTS / "diagram_check.py"), "--help"],
                                       capture_output=True, text=True).stdout
            self.assertIn("--board", help_text)

    # ---- new zone / layout / edge rules ------------------------------------
    def test_fill_contrast_helper(self):
        from diagram_kit import fill_contrast
        self.assertIsNone(fill_contrast("none", "#fff"))
        self.assertGreater(fill_contrast("#FFFFFF", "#EAF1F6"), 0.02)
        self.assertEqual(fill_contrast("#EAF1F6", "#EAF1F6"), 0.0)

    def test_card_inside_labeled_zone_must_clear_title_band(self):
        d = Diagram(960, 520, title="t")
        z = d.zone("z", 40, 120, 880, 200, "服务层", tone="sky")
        # card intrudes into the reserved title band (zone top + 43px)
        bad = d.card("c", 60, 130, 300, "编排", desc="x")
        issues = d.check()["issues"]
        self.assertTrue(any("标题" in i and "c" in i for i in issues), issues)

    def test_card_overflowing_zone_bottom_is_reported(self):
        d = Diagram(960, 520, title="t")
        d.zone("z", 40, 120, 880, 70, "服务层", tone="sky")  # bottom = 190
        # card starts below the title band but its body crosses the zone bottom
        d.card("c", 60, 165, 300, "编排", desc="x" * 60)
        issues = d.check()["issues"]
        self.assertTrue(any("z" in i and ("落在" in i or "完整" in i) for i in issues), issues)

    def test_white_card_on_tinted_zone_is_not_flagged(self):
        d = Diagram(960, 520, title="t")
        d.zone("z", 40, 120, 880, 220, "服务层", tone="sky")
        d.card("c", 60, 180, 300, "编排", desc="x", tone="sky")
        issues = d.check()["issues"]
        self.assertFalse(any("填充" in i for i in issues), issues)

    def test_long_edge_detour_is_a_warning(self):
        d = Diagram(960, 520, title="t")
        a = d.card("a", 40, 200, 200, "A")
        b = d.card("b", 40, 380, 200, "B")  # directly below a
        # force a far-right out-and-back detour
        d.edge(a, b, "bottom", "top", via=[(900, a.cy), (900, b.cy)])
        warns = d.check()["warnings"]
        self.assertTrue(any("绕远" in w for w in warns), warns)

    def test_legacy_theme_alias_uses_light_faces_and_same_hue_focus(self):
        d = Diagram(960, 520, title="t", theme="warm-cream")
        d.zone("z", 40, 120, 880, 220, "接入层", tone="sky")
        c = d.card("c", 60, 180, 300, "网关", tone="sky", emphasis=True)
        svg = d.svg()
        # Group stays neutral; the focal entity uses a light category face and same-hue outline.
        self.assertIn("#FAFAF8", svg.upper())
        self.assertIn(c.meta["body_fill"], svg.upper())
        self.assertNotEqual(c.meta["body_fill"], "#FFFFFF")
        self.assertEqual(c.meta["body_border"], d.tones["sky"]["border"])
        # no drop shadow filter under warm-cream
        self.assertNotIn("feDropShadow", svg)

    # ---- doubao-style primitives ----
    def test_doubao_verdict_bar_is_light_with_readable_text(self):
        d = Diagram(960, 300, title="t", theme="doubao")
        d.verdict_bar("v", 40, 120, 880, "结论：待验收")
        svg = d.svg().upper()
        self.assertIn(d.db["verdict_bg"], svg)
        self.assertIn(d.db["verdict_text"], svg)
        self.assertNotIn("#1B1D22", svg)
        self.assertIn("#FFFFFF", svg)
        self.assertNotIn("feDropShadow", svg)

    def test_doubao_category_card_uses_light_category_tokens(self):
        d = Diagram(960, 300, title="t", theme="doubao")
        c = d.category_card("c", 40, 120, 300, "根因①", "漏标放过去", cat="pink")
        svg = d.svg().upper()
        self.assertIn(c.meta["body_fill"], svg)
        self.assertIn(c.meta["body_border"], svg)
        self.assertIn("#1A1B1C", svg)   # ink title
        self.assertEqual(c.bottom, 120 + c.h)

    def test_doubao_evidence_row_has_priority_bar_and_accent_action(self):
        d = Diagram(960, 300, title="t", theme="doubao")
        d.evidence_action_row("r", 40, 120, 880, "P0 漏标",
                              "实跑：文件头缺失", "修：不导出", prio="p0")
        svg = d.svg().upper()
        self.assertIn("#A14E50", svg)   # explicit P0 status
        self.assertIn("#4F6B9A", svg)    # action is not a success state

    def test_doubao_matrix_renders_pill_headers_and_status(self):
        d = Diagram(1100, 500, title="t", theme="doubao")
        bottom = d.matrix_table("m", 40, 120, 1020, ["A", "B"],
                                [("维度一", [("strong", "好"), ("weak", "差")])])
        self.assertGreater(bottom, 120)
        svg = d.svg().upper()
        self.assertIn(d.db["matrix_head_bg"], svg)
        self.assertIn(d.db["pills"]["strong"]["fill"], svg)
        self.assertIn("#EEF3F7", svg)    # row header

    def test_doubao_components_are_editable_rects_not_paths(self):
        d = Diagram(1100, 600, title="t", theme="doubao")
        d.category_card("c", 40, 120, 300, "根因", "说明", cat="amber")
        d.verdict_bar("v", 40, 220, 1020, "结论")
        d.evidence_action_row("r", 40, 300, 1020, "P0", "证据", "动作", prio="p1")
        d.status_pill(40, 400, "强", "strong")
        report = d.save("/tmp/_db_check.svg", drawio="/tmp/_db_check.drawio")
        self.assertEqual(report["issues"], [])
        svg = open("/tmp/_db_check.svg").read()
        self.assertNotIn("feDropShadow", svg)
        body = svg.split("</defs>", 1)[1]
        self.assertNotIn("<path", body)  # shapes are rects; arrowheads live in defs

class DocCheckTests(unittest.TestCase):
    def test_layered_doc_passes(self):
        r = doc_check.check(LAYERED_DOC)
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(r["warnings"], [])
        self.assertIn("准入流水线：先试用再钉版", r["skim"])
        self.assertIn("新插件要过四步", r["skim"])
        self.assertNotIn("静态检查", r["skim"])

    def test_missing_first_screen_is_an_error(self):
        md = "# 标题\n\n## 方案\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n"
        r = doc_check.check(md)
        self.assertFalse(r["ok"])
        self.assertTrue(any("首屏" in e for e in r["errors"]))

    def test_ai_phrases_generic_headings_and_leads_are_flagged(self):
        md = ("# 标题\n\n结论先行。\n\n## 方案\n\n- 列表开头\n\n## 背景\n\n"
              + "值得注意的是，我们需要赋能并打通闭环，这至关重要。综上所述，本文将介绍全方位的抓手。" * 3)
        r = doc_check.check(md)
        joined = "\n".join(r["warnings"])
        self.assertIn("套话密度", joined)
        self.assertIn("方案", joined)
        self.assertIn("首块是列表", joined)

    def test_domain_words_from_source_are_not_jargon(self):
        md = LAYERED_DOC + "\n## 统计口径\n\n成本按回合统计。\n"
        self.assertIn("口径", doc_check.check(md)["metrics"]["jargon"])
        self.assertNotIn("口径", doc_check.check(md, source_text="成本口径按回合")["metrics"]["jargon"])

    def test_density_warnings_need_real_counts(self):
        md = LAYERED_DOC + "\n" + "".join(f"第{i}步 **重点{i}** 需要处理。\n\n" for i in range(12))
        self.assertIn("加粗", "\n".join(doc_check.check(md)["warnings"]))

    def test_html_comments_are_ignored(self):
        r = doc_check.check(LAYERED_DOC + "\n<!-- 黑盒 下钻 横切 -->\n")
        self.assertEqual(r["metrics"]["jargon"], [])

    def test_talk_about_source_material_is_flagged(self):
        r = doc_check.check(LAYERED_DOC + "\n当前供应商的价格不在材料里，素材里没有基线数据。\n")
        self.assertEqual(r["metrics"]["source_talk"], 2)
        self.assertTrue(any("素材" in w for w in r["warnings"]))
        self.assertEqual(doc_check.check(LAYERED_DOC + "\n素材库的审核通过率是 92%。\n")["metrics"]["source_talk"], 0)

    def test_template_passes_structure_check(self):
        md = (ROOT / "templates/engineering-doc.md").read_text(encoding="utf-8")
        self.assertTrue(doc_check.check(md)["ok"])

    WALL = ("# 配置灰度\n\n> **方案主张：** 分批灰度。\n\n## 灰度发布\n\n"
            + "\n\n".join("第一批是内部集群，观察期内错误率不能高于变更前；第二批扩到 1% 实例，除了错误率还要求 P99 延迟不升高；"
                          "第三批扩到 10% 实例，判定条件和第二批相同，不满足时除了自动回滚还会通知负责人，第四批全量后不再自动回滚而由人工判断，因为全量后出现的问题往往和配置本身无关。" for _ in range(3))
            + "\n")

    def test_prose_wall_is_flagged(self):
        r = doc_check.check(self.WALL)
        joined = "\n".join(r["warnings"])
        self.assertIn("段落墙", joined)
        self.assertIn("没有一个表格或列表", joined)
        self.assertGreater(r["metrics"]["long_paragraphs"], 0)

    def test_structured_doc_is_not_flagged_as_wall(self):
        md = ("# 配置灰度\n\n> **方案主张：** 分批灰度。\n\n## 灰度发布\n\n每次变更分四批，**指标正常**才放量。\n\n"
              "| 批次 | 范围 | 不满足时 |\n| --- | --- | --- |\n" + "| 1 | 内部集群 | 自动回滚并通知负责人 |\n" * 12
              + "\n- **保留期**：30 天可一键回滚。\n- **触发方**：配置中心自动触发。\n")
        r = doc_check.check(md)
        joined = "\n".join(r["warnings"])
        self.assertNotIn("段落墙", joined)
        self.assertNotIn("没有一个表格或列表", joined)
        self.assertNotIn("加粗", joined)  # `- **标签**：` keys are structure, not emphasis

    def test_quote_lead_counts_as_chapter_conclusion(self):
        md = LAYERED_DOC + "\n## 风险\n\n> **结论**：配置中心故障是唯一会让回滚失效的风险。\n\n| 风险 | 缓解 |\n| --- | --- |\n| a | b |\n"
        self.assertNotIn("风险（首块", "\n".join(doc_check.check(md)["warnings"]))

    def test_whole_sentence_bold_is_flagged(self):
        md = LAYERED_DOC + "\n**本方案通过引入分批灰度机制有效降低了配置发布带来的线上风险**。\n"
        self.assertIn("整句加粗", "\n".join(doc_check.check(md)["warnings"]))

    def test_state_table_without_state_diagram_hints_wrong_diagram_type(self):
        md = (LAYERED_DOC + "\n## 任务状态\n\n任务状态由事件推导。\n\n| 状态 | 含义 |\n| --- | --- |\n| 草稿 | 未确认 |\n\n"
              "![任务图模型：目标组、任务节点、边](a.svg)\n")
        self.assertIn("没有状态图", "\n".join(doc_check.check(md)["warnings"]))
        ok = md.replace("![任务图模型：目标组、任务节点、边](a.svg)", "![任务状态图：要过验收才算完成](b.svg)")
        self.assertNotIn("没有状态图", "\n".join(doc_check.check(ok)["warnings"]))


class DiagramCheckTests(unittest.TestCase):
    def write(self, tmp, body, w=960, h=540):
        p = Path(tmp) / "t.svg"
        p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">{body}</svg>', encoding="utf-8")
        return p

    def test_forbidden_features_and_tiny_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.write(tmp, '<foreignObject/><text x="0" y="10" font-size="8">小字</text>')
            r = diagram_check.static_check(p)
            self.assertFalse(r["ok"])
            self.assertTrue(any("foreignObject" in e for e in r["errors"]))
            self.assertTrue(any("最小字号" in e for e in r["errors"]))

    def test_rainbow_palette_and_tall_strip_warn(self):
        colors = ["#E53935", "#43A047", "#1E88E5", "#FDD835", "#8E24AA"]
        rects = "".join(f'<rect x="{i*50}" y="0" width="40" height="40" fill="{c}"/>' for i, c in enumerate(colors))
        with tempfile.TemporaryDirectory() as tmp:
            p = self.write(tmp, rects + '<text x="0" y="60" font-size="14">正文</text>', w=600, h=1100)
            r = diagram_check.static_check(p)
            joined = "\n".join(r["warnings"])
            self.assertIn("色系", joined)
            self.assertIn("高宽比", joined)

    def test_whole_diagram_in_one_group_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.write(tmp, '<g><rect x="0" y="0" width="10" height="10" fill="#fff"/>'
                                '<text x="0" y="30" font-size="14">正文</text></g>')
            self.assertTrue(any("一个 <g>" in w for w in diagram_check.static_check(p)["warnings"]))

    def test_reverse_marker_orient_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.write(tmp, '<defs><marker id="a" viewBox="0 0 10 10" orient="auto-start-reverse">'
                                '<path d="M0 0 L10 5 L0 10 z"/></marker></defs>'
                                '<path d="M10 10 L10 90" stroke="#000" marker-end="url(#a)"/>'
                                '<text x="20" y="30" font-size="14">正文</text>')
            self.assertTrue(any("auto-start-reverse" in w for w in diagram_check.static_check(p)["warnings"]))

    def test_missing_viewbox_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.svg"
            p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text>x</text></svg>',
                         encoding="utf-8")
            self.assertTrue(any("viewBox" in e for e in diagram_check.static_check(p)["errors"]))

    def test_doc_names_missing_from_figure_are_listed(self):
        doc = ("# 方案\n\n## 发布入口：写入只经过网关\n\nGateway 校验请求，Gateway 限流。\n\n"
               "### Gateway 的新检查\n\nGateway 读配置；由Gateway报告。Scheduler 排队，Scheduler 重试，"
               "Scheduler 告警，Scheduler 记录。调用 `v1/tasks` 四次：`v1/tasks` `v1/tasks` "
               "`v1/tasks`。\n\n## 附录 A：Redis 参数\n\nRedis、Redis、Redis、Redis。\n")
        with tempfile.TemporaryDirectory() as tmp:
            p = self.write(tmp, '<text x="0" y="20" font-size="14">配置</text>')
            d = Path(tmp) / "doc.md"
            d.write_text(doc, encoding="utf-8")
            r = diagram_check.static_check(p)
            diagram_check.doc_coverage(d, r.pop("texts"), r)
            listed = r["metrics"]["doc_names_missing"]
            self.assertIn("Gateway×5", listed)
            self.assertIn("Scheduler×4", listed)
            self.assertFalse(any("v1/tasks" in n for n in listed))
            warned = "\n".join(r["warnings"])
            self.assertIn("Gateway", warned)
            self.assertNotIn("Scheduler", warned)
            self.assertNotIn("Redis", warned)


class LarkBindTests(unittest.TestCase):
    def nodes(self):
        shape = lambda i, x, y, w, h, **st: {"id": i, "type": "composite_shape", "x": x, "y": y, "width": w,
                                              "height": h, "style": {"border_style": "solid", "fill_color": "#ffffff",
                                                                     **st}}
        return [
            shape("o1", 40, 40, 160, 60),
            shape("o2", 360, 40, 160, 60),
            shape("zone", 20, 10, 520, 120),
            {"id": "g1", "type": "group", "x": 250, "y": 58, "width": 60, "height": 24},
            dict(shape("lab", 250, 58, 60, 24, border_style="none"), parent_id="g1"),
            {"id": "t1", "type": "text_shape", "x": 256, "y": 60, "width": 48, "height": 20, "parent_id": "g1",
             "text": {"text": "调用", "font_size": 14, "text_color": "#646a73"}},
            {"id": "c1", "type": "connector", "x": 200, "y": 70, "width": 160, "height": 0,
             "connector": {"start": {"position": {"x": 200, "y": 70}, "arrow_style": "none"},
                           "end": {"position": {"x": 360, "y": 70}, "arrow_style": "triangle_arrow"},
                           "shape": "straight", "turning_points": []}},
            {"id": "c2", "type": "connector", "x": 600, "y": 300, "width": 30, "height": 0,
             "connector": {"start": {"position": {"x": 600, "y": 300}}, "end": {"position": {"x": 630, "y": 300}},
                           "shape": "straight", "turning_points": []}},
        ]

    def test_binds_ends_to_smallest_shape_and_moves_label_into_caption(self):
        nodes, report = lark_bind.bind(self.nodes())
        c1 = next(n for n in nodes if n["id"] == "c1")["connector"]
        self.assertEqual(c1["start"]["attached_object"]["id"], "o1")
        self.assertEqual(c1["start"]["attached_object"]["snap_to"], "right")
        self.assertEqual(c1["end_object"]["id"], "o2")
        self.assertEqual(c1["end"]["attached_object"]["position"], {"x": 0.0, "y": 0.5})
        self.assertEqual(c1["captions"]["data"][0]["text"], "调用")
        self.assertAlmostEqual(c1["caption_position"], 0.5, places=2)
        ids = {n["id"] for n in nodes}
        self.assertFalse({"g1", "lab", "t1"} & ids)
        self.assertEqual(report["bound_connectors"], 1)
        self.assertEqual(report["free_lines"], 1)
        self.assertEqual(report["half_bound"], [])

    def test_half_bound_connector_is_reported(self):
        nodes = self.nodes()
        nodes[6]["connector"]["end"]["position"] = {"x": 330, "y": 70}
        _, report = lark_bind.bind(nodes)
        self.assertEqual(len(report["half_bound"]), 1)

    def test_top_level_nodes_are_stacked_in_document_order(self):
        nodes = [{"id": "page", "type": "composite_shape"}, {"id": "g", "type": "group"},
                 {"id": "card", "type": "composite_shape", "parent_id": "g", "z_index": 0},
                 {"id": "line", "type": "connector"}]
        lark_bind.stack(nodes)
        self.assertEqual([n.get("z_index") for n in nodes], [0, 1, 0, 2])


class SkillContractTests(unittest.TestCase):
    def test_skill_routes_to_new_contracts_and_tools(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for ref in ("references/writing-contract.md", "references/diagram-system.md", "references/lark-publish.md",
                    "scripts/doc_check.py", "scripts/diagram_kit.py", "scripts/diagram_check.py",
                    "scripts/lark_bind.py", "assets/examples/personal-harness/arch.py"):
            self.assertIn(ref, skill)
            self.assertTrue((ROOT / ref).exists(), ref)
        self.assertLess(len(skill), 8000)

    def test_old_conflicting_rules_are_gone(self):
        text = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "references").glob("*.md"))
        self.assertNotIn("680 至 900", text)
        self.assertNotIn("结构图优先通过上下分层", text)
        self.assertNotIn("默认使用 `document-pastel` 主题", text)

    def test_contract_documents_stay_short(self):
        for name, limit in (("writing-contract.md", 6000), ("diagram-system.md", 8000), ("lark-publish.md", 4800)):
            self.assertLess(len((ROOT / "references" / name).read_text(encoding="utf-8")), limit, name)


if __name__ == "__main__":
    unittest.main()
