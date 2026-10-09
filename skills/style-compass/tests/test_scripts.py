#!/usr/bin/env python3
"""style-compass 脚本测试。运行：python3 -m unittest discover -s tests -v（在技能根目录）。"""

import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import design_memory  # noqa: E402
import export_tokens  # noqa: E402
import lint_design  # noqa: E402
import token_utils  # noqa: E402
import validate_stage_contract  # noqa: E402

EXAMPLE_TOKENS = json.loads((ROOT / "examples" / "tokens.example.json").read_text(encoding="utf-8"))
EXAMPLE_CONTRACT = json.loads((ROOT / "examples" / "stage-contract.example.json").read_text(encoding="utf-8"))

# v3 的示例 tokens：旧格式必须继续能导出。
LEGACY_TOKENS = {
    "meta": {"name": "示例:克制工程感 (Calm-Tech)", "based_on": "calm-tech", "reference": "Linear / Vercel", "scheme": "dark"},
    "color": {"bg": "#0B0C0E", "surface": "#16181C", "surface_alt": "#1C1F24", "text": "#E6E8EB",
              "text_muted": "#8A9099", "accent": "#5E6AD2", "accent_soft": "#3A3F66", "border": "#23262B",
              "success": "#3FB950", "warning": "#D29922", "danger": "#F85149"},
    "typography": {"heading_font": "Geist, 'SF Pro Display', system-ui, sans-serif",
                   "body_font": "Geist, 'SF Pro Text', system-ui, sans-serif",
                   "mono_font": "'Geist Mono', 'JetBrains Mono', monospace",
                   "weight_regular": 400, "weight_medium": 540, "weight_bold": 680,
                   "scale": {"xs": 12, "sm": 13, "base": 15, "lg": 18, "xl": 22, "2xl": 28, "3xl": 36},
                   "line_height": 1.5},
    "radius": {"sm": 4, "base": 6, "lg": 10, "full": 999},
    "spacing": {"xs": 4, "sm": 8, "base": 12, "lg": 20, "xl": 32, "2xl": 48},
    "motion": {"duration_fast": 120, "duration_base": 200, "duration_slow": 320, "easing": "cubic-bezier(0.2, 0, 0, 1)"},
    "elevation": {"flat": "none", "soft": "0 1px 2px rgba(0,0,0,0.4)", "raised": "0 4px 16px rgba(0,0,0,0.5)"},
    "guardrails": {"use": "几何无衬线、深灰阶背景(非纯黑)", "avoid": "紫白渐变、圆润卡通"},
}

BAD_PAGE = """<!doctype html>
<html lang="en"><head>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<style>
  body { font-family: Inter, system-ui, sans-serif; line-height: 1.4; }
  h1 { letter-spacing: -0.03em; }
  .hero { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
  .btn { transition: all .2s ease; outline: none; color: #ff3366; }
  @keyframes pop { from { opacity: 0 } to { opacity: 1 } }
  .toast { animation: pop 300ms ease; }
</style></head>
<body>
  <h1>项目总览，管理你的所有项目和任务，随时掌握进度与风险情况</h1>
  <p>这里是一段中文正文，用来测试中文页面的检测逻辑。</p>
  <button class="icon"><svg width="16" height="16"></svg></button>
  <div onclick="go()">打开</div>
  <section><p>确定要删除这个项目吗？删除后不可恢复。</p><button>确定</button></section>
</body></html>
"""

GOOD_PAGE = """<!doctype html>
<html lang="zh-CN"><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --color-bg: #F6F7F9; --color-text: #1E2228; --color-accent: #0B7A75; --color-on-accent: #FFFFFF; }
  body { font-family: 'SF Pro Text', 'PingFang SC', 'Microsoft YaHei', sans-serif; line-height: 1.75;
         background: var(--color-bg); color: var(--color-text); }
  .btn { background: var(--color-accent); color: var(--color-on-accent); transition: background-color 120ms ease; }
  .btn:focus-visible { outline: 2px solid var(--color-accent); }
  @keyframes fade { from { opacity: 0 } to { opacity: 1 } }
  .toast { animation: fade 200ms ease; }
  @media (prefers-reduced-motion: reduce) { .toast { animation: none; } }
</style></head>
<body>
  <h1>项目总览</h1>
  <p>这里是一段中文正文，用来确认合格页面不会被误报，行高和字体栈都按中文排版设置。</p>
  <button class="btn" aria-label="新建项目"><svg width="16" height="16"></svg></button>
  <section><p>删除后 5 秒内可以撤销。</p><button class="btn">删除项目</button></section>
</body></html>
"""


def run(script, *args, env=None, cwd=None):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True,
                          text=True, env=full_env, cwd=cwd)


def rules(report):
    return {f["rule"] for f in report["findings"]}


def contract_html(contract):
    """按契约生成能通过校验的最小工作台 HTML：交互基线覆盖全部，方案覆盖它声明的部分。"""
    def section(stage, variant, pages, journeys, actions, states):
        buttons = "".join(
            f'<button data-design-action="{a}" data-prototype-action="state:{a}" '
            f'data-design-result="{action_index[a]["toState"]}">{action_index[a]["title"]}</button>'
            for a in actions)
        return (f'<article data-review-artboard="{stage}-{variant}" data-review-stage="{stage}" '
                f'data-review-variant="{variant}"><section data-design-page="{" ".join(pages)}" '
                f'data-design-journey="{" ".join(journeys)}" data-design-state="{" ".join(states)}">'
                f'{buttons}</section></article>')

    action_index = {a["id"]: a for a in contract["actions"]}
    ids = {name: [item["id"] for item in contract[name]] for name in ("pages", "journeys", "actions", "states")}
    parts = [section("interaction", "base", ids["pages"], ids["journeys"], ids["actions"], ids["states"])]
    for variant in contract["variants"]:
        parts.append(section("visual-direction", variant["id"], variant["pageIds"], variant["journeyIds"],
                             variant["actionIds"], variant["stateIds"]))
    return '<!doctype html><html lang="zh-CN"><body>' + "".join(parts) + "</body></html>"


class TokenUtilsTest(unittest.TestCase):
    def test_color_parsing(self):
        self.assertEqual(token_utils.parse_color("#fff")[:3], (255.0, 255.0, 255.0))
        self.assertAlmostEqual(token_utils.parse_color("rgb(99 102 241 / 50%)")[3], 0.5)
        self.assertEqual(token_utils.to_hex(token_utils.parse_color("hsl(0, 100%, 50%)")), "#FF0000")
        found = [lit for lit, _, _ in token_utils.iter_colors("linear-gradient(#667eea, var(--x, #000)) white")]
        self.assertEqual(found, ["#667eea", "white"])

    def test_contrast(self):
        white, black = token_utils.parse_hex("#FFFFFF"), token_utils.parse_hex("#000000")
        self.assertAlmostEqual(token_utils.contrast_ratio(white, black), 21, places=1)

    def test_font_stack_composes_latin_then_cjk(self):
        stack = token_utils.font_stack(EXAMPLE_TOKENS, "body")
        families = token_utils.split_families(stack)
        self.assertEqual(families[0], "SF Pro Text")
        self.assertIn("PingFang SC", families)
        self.assertEqual(families[-1], "sans-serif")
        self.assertEqual(token_utils.split_families(token_utils.font_stack(EXAMPLE_TOKENS, "mono"))[-1], "monospace")

    def test_legacy_explicit_stack_wins(self):
        self.assertEqual(token_utils.font_stack(LEGACY_TOKENS, "heading"), LEGACY_TOKENS["typography"]["heading_font"])

    def test_example_has_no_errors(self):
        findings = token_utils.validate_tokens(EXAMPLE_TOKENS)
        self.assertEqual([f for f in findings if f["severity"] in ("error", "warn")], [])

    def test_invalid_tokens(self):
        broken = copy.deepcopy(EXAMPLE_TOKENS)
        broken["color"]["accent"] = "teal"
        broken["typography"]["line_height"]["body"] = 9
        found = {f["rule"] for f in token_utils.validate_tokens(broken) if f["severity"] == "error"}
        self.assertEqual(found, {"TOKENS-COLOR", "TOKENS-LEADING"})

    def test_cjk_warnings(self):
        latin_only = copy.deepcopy(LEGACY_TOKENS)
        latin_only["locale"] = {"lang": "zh-CN"}
        found = {f["rule"] for f in token_utils.validate_tokens(latin_only)}
        self.assertIn("TOKENS-CJK-FONT", found)
        low = copy.deepcopy(EXAMPLE_TOKENS)
        low["color"]["text_muted"] = "#A0A4AB"
        self.assertIn("TOKENS-CONTRAST", {f["rule"] for f in token_utils.validate_tokens(low)})


class ExportTokensTest(unittest.TestCase):
    def test_all_targets_for_new_and_legacy(self):
        for tokens in (EXAMPLE_TOKENS, LEGACY_TOKENS):
            for target in export_tokens.ALL_TARGETS:
                self.assertTrue(export_tokens.render(target, tokens, "").strip(), target)

    def test_css_has_cjk_baseline(self):
        css = export_tokens.export_css(EXAMPLE_TOKENS)
        self.assertIn("html:lang(zh) { text-autospace: normal; }", css)
        self.assertIn("--leading-body: 1.75;", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("'PingFang SC'", css)

    def test_legacy_css_keeps_old_variables(self):
        css = export_tokens.export_css(LEGACY_TOKENS)
        for name in ("--color-surface-alt: #1C1F24;", "--radius-base: 6px;", "--space-2xl: 48px;",
                     "--font-heading: Geist, 'SF Pro Display', system-ui, sans-serif;", "--duration-base: 200ms;"):
            self.assertIn(name, css)
        self.assertNotIn("text-autospace", css)

    def test_tailwind_keeps_color_keys(self):
        js = export_tokens.export_tailwind(LEGACY_TOKENS)
        self.assertIn('"surface_alt": "#1C1F24"', js)

    def test_swift_identifiers_are_valid(self):
        swift = export_tokens.export_swift(LEGACY_TOKENS)
        self.assertIn("static let s2xl: CGFloat = 48", swift)
        self.assertNotIn("static let 2xl", swift)

    def test_design_md_round_trip(self):
        text = export_tokens.export_design_md(EXAMPLE_TOKENS, "冷静、密、可信。")
        front = design_memory.parse_front_matter(text)
        self.assertEqual(front["version"], "alpha")
        self.assertEqual(front["colors"]["primary"], "#0B7A75")
        self.assertEqual(front["typography"]["body-md"]["fontSize"], "14px")
        self.assertEqual(front["components"]["button-primary"]["backgroundColor"], "{colors.primary}")
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        order = ["## Overview", "## Colors", "## Typography", "## Layout", "## Elevation & Depth", "## Shapes",
                 "## Components", "## Do's and Don'ts"]
        self.assertEqual(headings[:8], order)
        self.assertIn("冷静、密、可信。", text)

    def test_dtcg_shapes(self):
        data = json.loads(export_tokens.export_dtcg(EXAMPLE_TOKENS))
        self.assertEqual(data["color"]["$type"], "color")
        self.assertEqual(data["color"]["accent"]["$value"]["colorSpace"], "srgb")
        self.assertEqual(len(data["color"]["accent"]["$value"]["components"]), 3)
        self.assertEqual(data["space"]["base"]["$value"], {"value": 12, "unit": "px"})
        self.assertEqual(data["duration"]["base"]["$value"], {"value": 200, "unit": "ms"})
        self.assertEqual(data["easing"]["standard"]["$value"], [0.2, 0.0, 0.0, 1.0])

    def test_prompt_has_no_global_bans(self):
        prompt = export_tokens.export_prompt(EXAMPLE_TOKENS)
        self.assertNotIn("禁止用 Inter", prompt)
        self.assertIn("卡片网格当首页", prompt)
        self.assertIn("text-autospace", prompt)

    def test_cli_refuses_invalid_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = copy.deepcopy(EXAMPLE_TOKENS)
            bad["color"]["bg"] = "nope"
            path = Path(tmp) / "tokens.json"
            path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            result = run("export_tokens.py", path, "--out", Path(tmp) / "out", "--targets", "all")
            self.assertEqual(result.returncode, 1)
            self.assertFalse((Path(tmp) / "out").exists())

    def test_cli_all_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = Path(tmp) / "direction.md"
            brief.write_text("# 方向简报\n\n冷静、密、可信。\n", encoding="utf-8")
            result = run("export_tokens.py", ROOT / "examples" / "tokens.example.json", "--out", tmp,
                         "--targets", "all", "--brief", brief, "--design-md", Path(tmp) / "root" / "DESIGN.md")
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in ("DesignTokens.swift", "tokens.css", "tailwind.tokens.js", "style-prompt.md", "tokens.dtcg.json"):
                self.assertTrue((Path(tmp) / name).exists(), name)
            self.assertTrue((Path(tmp) / "root" / "DESIGN.md").exists())


class LintDesignTest(unittest.TestCase):
    def test_bad_page(self):
        report = lint_design.lint_page(BAD_PAGE, "final", EXAMPLE_TOKENS)
        expected = {"LANG-ZH", "A11Y-ZOOM", "CJK-FONT-STACK", "TOKEN-COLOR", "A11Y-NAME", "MOTION-REDUCE",
                    "CJK-LEADING", "CJK-NEG-TRACKING", "SMELL-PURPLE-GRADIENT", "A11Y-FOCUS", "MOTION-ALL",
                    "A11Y-CLICK-DIV", "COPY-CONFIRM"}
        self.assertTrue(expected <= rules(report), expected - rules(report))
        self.assertGreater(report["summary"]["error"], 0)

    def test_good_page(self):
        tokens = copy.deepcopy(EXAMPLE_TOKENS)
        tokens["color"]["accent"] = "#0E6B8C"
        page = GOOD_PAGE.replace("#0B7A75", "#0E6B8C")
        report = lint_design.lint_page(page, "final", tokens)
        self.assertEqual(report["summary"]["error"], 0, report["findings"])
        self.assertEqual(report["summary"]["warn"], 0, report["findings"])

    def test_example_copy_is_flagged(self):
        report = lint_design.lint_page(GOOD_PAGE, "final", EXAMPLE_TOKENS)
        self.assertIn("SMELL-EXAMPLE-COPY", rules(report))

    def test_legacy_example_smells(self):
        found = {f["rule"] for f in lint_design.token_smells(LEGACY_TOKENS)}
        self.assertTrue({"SMELL-DEFAULT-ACCENT", "SMELL-DARK-INDIGO", "SMELL-EXAMPLE-COPY"} <= found)

    def test_accepted_default_needs_reason(self):
        tokens = copy.deepcopy(LEGACY_TOKENS)
        tokens["guardrails"]["accepted_defaults"] = [{"id": "SMELL-DARK-INDIGO", "reason": "品牌色就是这个"},
                                                     "SMELL-DEFAULT-ACCENT"]
        report = lint_design.lint_page(GOOD_PAGE, "direction", tokens)
        by_rule = {f["rule"]: f["severity"] for f in report["findings"]}
        self.assertEqual(by_rule["SMELL-DARK-INDIGO"], "accepted")
        self.assertEqual(by_rule["SMELL-DEFAULT-ACCENT"], "warn")

    def test_gray_phase_and_artboard_scope(self):
        page = """<!doctype html><html lang="zh-CN"><body>
<button class="shell"><svg></svg></button>
<article data-review-artboard="s1" data-review-stage="structure" data-review-variant="base">
<p style="color:#999">灰阶线框里的说明文字，灰阶线框里的说明文字。</p><p style="color:#0B7A75">彩色</p></article>
<article data-review-artboard="v1" data-review-stage="visual-final" data-review-variant="direction-a">
<p style="color:#C23B3B">视觉方案里的颜色，不算结构关的问题。</p></article></body></html>"""
        report = lint_design.lint_page(page, "structure", None)
        gray = [f for f in report["findings"] if f["rule"] == "GRAY-PHASE-COLOR"]
        self.assertEqual(len(gray), 1)
        self.assertIn("#0B7A75", gray[0]["message"])
        self.assertNotIn("#C23B3B", gray[0]["message"])
        self.assertNotIn("A11Y-NAME", rules(report))

    def test_template_is_clean(self):
        html = (ROOT / "assets" / "review-framework" / "template.html").read_text(encoding="utf-8")
        for phase in lint_design.PHASES:
            report = lint_design.lint_page(html, phase, None)
            self.assertEqual(report["summary"]["error"], 0, (phase, report["findings"]))
            self.assertEqual(report["summary"]["warn"], 0, (phase, report["findings"]))

    def test_diverge(self):
        close = [
            {"id": "A", "bg": "#F6F7F9", "accent": "#0B7A75", "heading_font": "PingFang SC", "radius": 6,
             "density": "compact", "container": "dividers", "decoration": "none", "motion": "subtle"},
            {"id": "B", "bg": "#F5F6F8", "accent": "#0E7C86", "heading_font": "PingFang SC", "radius": 8,
             "density": "compact", "container": "dividers", "decoration": "none", "motion": "subtle"},
        ]
        report = lint_design.lint_diverge(close, 3)
        self.assertIn("DIVERGE-CLOSE", rules(report))
        self.assertIn("DIVERGE-CONTRARIAN", rules(report))
        far = copy.deepcopy(close)
        far[1].update({"bg": "#14161A", "accent": "#D9822B", "heading_font": "Source Han Serif SC", "radius": 0,
                       "container": "bands", "contrarian": True})
        report = lint_design.lint_diverge(far, 3)
        self.assertEqual(report["summary"]["error"], 0, report["findings"])
        self.assertNotIn("DIVERGE-CONTRARIAN", rules(report))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.html"
            bad.write_text(BAD_PAGE, encoding="utf-8")
            self.assertEqual(run("lint_design.py", "check", bad, "--phase", "final").returncode, 1)
            self.assertEqual(run("lint_design.py", "check", Path(tmp) / "missing.html", "--phase", "final").returncode, 2)
            result = run("lint_design.py", "tokens", ROOT / "examples" / "tokens.example.json", "--json")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["summary"]["error"], 0)
            result = run("lint_design.py", "tokens", ROOT / "examples" / "tokens.example.json")
            self.assertEqual(result.returncode, 0)
            self.assertIn("[lint] PASS_WITH_WARNINGS", result.stdout)
            result = run("lint_design.py", "tokens", ROOT / "examples" / "tokens.example.json", "--strict")
            self.assertEqual(result.returncode, 1)
            self.assertIn("[lint] PASS_WITH_WARNINGS", result.stdout)

    def test_diverge_surface_only(self):
        base = {"bg": "#F3F4F1", "accent": "#1C6B50", "heading_font": "PingFang SC", "radius": 3,
                "density": "compact", "container": "分隔线", "decoration": "色条", "motion": "subtle"}
        other = dict(base, id="B", accent="#1F6E55", radius=8, density="comfortable", container="留白分组",
                     decoration="无", contrarian=True)
        report = lint_design.lint_diverge([dict(base, id="A"), other], 3)
        self.assertEqual(report["summary"]["error"], 0, report["findings"])
        self.assertIn("DIVERGE-SURFACE", rules(report))
        other.update(bg="#14161A")
        self.assertNotIn("DIVERGE-SURFACE", rules(lint_design.lint_diverge([dict(base, id="A"), other], 3)))

    def test_diverge_layout_counts_as_visible(self):
        base = {"bg": "#F6F7F9", "accent": "#0B7A75", "heading_font": "PingFang SC", "radius": 6,
                "density": "compact", "container": "卡片", "decoration": "无", "motion": "subtle"}
        tabs = dict(base, id="tabs")
        rail = dict(base, id="rail", density="comfortable", container="分隔线", decoration="色条")
        surface = [f for f in lint_design.lint_diverge([tabs, rail], 3)["findings"] if f["rule"] == "DIVERGE-SURFACE"]
        self.assertEqual(len(surface), 1)
        self.assertIn("layout", surface[0]["message"])
        tabs["layout"] = "顶部指标卡，横排状态 Tab，下面表格"
        rail["layout"] = ""
        self.assertIn("DIVERGE-SURFACE", rules(lint_design.lint_diverge([tabs, rail], 3)))
        rail["layout"] = "左侧状态和取货点筛选栏，一句话汇总，右侧表格"
        report = lint_design.lint_diverge([tabs, rail], 3)
        self.assertNotIn("DIVERGE-SURFACE", rules(report))
        self.assertIn("布局", report["pairs"][0]["differs"])
        rail["layout"] = tabs["layout"]
        surface = [f for f in lint_design.lint_diverge([tabs, rail], 3)["findings"] if f["rule"] == "DIVERGE-SURFACE"]
        self.assertEqual(len(surface), 1)
        self.assertIn("整页布局都一样", surface[0]["message"])

    def test_contrarian_keeps_brief(self):
        def card(d):
            meta = ("id", "contrarian", "keeps", "flips")
            return dict({k: d[k] for k in meta if k in d}, axes={k: v for k, v in d.items() if k not in meta})

        a = {"id": "A", "bg": "#FFF8EC", "accent": "#E4572E", "heading_font": "PingFang SC", "radius": 12,
             "layout": "瀑布流卡片"}
        c = {"id": "C", "bg": "#FFFDF7", "accent": "#2E86AB", "heading_font": "Source Han Serif SC", "radius": 2,
             "layout": "按课程分组的清单", "contrarian": True}
        self.assertIn("DIVERGE-CONTRARIAN-BRIEF", rules(lint_design.lint_diverge([a, c], 3)))
        c["keeps"] = ["年轻", "轻松"]
        self.assertIn("DIVERGE-CONTRARIAN-BRIEF", rules(lint_design.lint_diverge([a, c], 3)))
        c["flips"] = ["卡片流换成分组清单", "无衬线标题换成衬线"]
        report = lint_design.lint_diverge([a, c], 3)
        self.assertEqual(report["summary"]["warn"], 0, report["findings"])
        with tempfile.TemporaryDirectory() as tmp:
            cards = Path(tmp) / "directions.json"
            cards.write_text(json.dumps({"candidates": [card(a), card(c)]}, ensure_ascii=False), encoding="utf-8")
            result = run("lint_design.py", "diverge", cards, "--json", "--strict")
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_latin_font_variable_is_not_cjk_stack_error(self):
        page = """<!doctype html><html lang="zh-CN"><head><style>
:root { --font-num: 'DIN Alternate', Arial, sans-serif; --font-heading: 'DIN Alternate', Arial, sans-serif; }
body { font-family: 'SF Pro Text', 'PingFang SC', 'Microsoft YaHei', sans-serif; line-height: 1.75; }
.sb { font: 700 13px/1 var(--font-num); }
.title { font-family: var(--font-heading); }
</style></head><body><div class="sb">9:41</div><h1 class="title">最新发布的二手教材，按课程找书更快</h1>
<p>这里是一段中文正文，用来确认数字专用字体不会被当成缺少中文字体。</p></body></html>"""
        report = lint_design.lint_page(page, "final", None)
        flagged = [f for f in report["findings"] if f["rule"] == "CJK-FONT-STACK"]
        self.assertEqual(len(flagged), 1, flagged)
        self.assertIn(".title", flagged[0]["message"])

    def test_linked_stylesheets(self):
        tokens = copy.deepcopy(EXAMPLE_TOKENS)
        tokens["color"]["accent"] = "#0E6B8C"
        page = """<!doctype html><html lang="zh-CN"><head>
<link rel="stylesheet" href="review-framework/review-framework.css?v=5">
<link rel="stylesheet" href="https://example.com/remote.css">
<link rel="stylesheet" href="design/tokens.css">
<style>body { font-family: var(--font-body); background: var(--color-bg); color: var(--color-text); }</style></head>
<body><p>这里是一段中文正文，用来确认引入的 tokens.css 会被读取，变量能解析出中文字体栈。</p></body></html>"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "design").mkdir()
            (root / "design" / "tokens.css").write_text(export_tokens.export_css(tokens), encoding="utf-8")
            report = lint_design.lint_page(page, "final", tokens, base_dir=root)
            noisy = {"CJK-FONT-DEFAULT", "CJK-FONT-STACK", "VAR-UNDEFINED", "CSS-LINK-MISSING"} & rules(report)
            self.assertFalse(noisy, report["findings"])
            self.assertEqual(report["summary"]["error"], 0, report["findings"])
            (root / "design" / "tokens.css").unlink()
            report = lint_design.lint_page(page, "final", tokens, base_dir=root)
            self.assertTrue({"CSS-LINK-MISSING", "VAR-UNDEFINED"} <= rules(report), report["findings"])
            missing = [f for f in report["findings"] if f["rule"] == "CSS-LINK-MISSING"]
            self.assertEqual(len(missing), 1, missing)

    def test_token_scale_checks(self):
        tokens = copy.deepcopy(EXAMPLE_TOKENS)
        tokens["color"]["accent"] = "#0E6B8C"
        page = f"""<!doctype html><html lang="zh-CN"><head><style>{export_tokens.export_css(tokens)}
  body {{ font-family: var(--font-body); background: var(--color-bg); color: var(--color-text); }}
  .card {{ border-radius: 37px; padding: 97px 16px; font-size: 13.7px; }}
  .tag {{ border-radius: 37px; margin: -97px 0 0; font: 600 13.7px/1.5 'Comic Sans MS', 'PingFang SC', sans-serif; }}
  .ok {{ border-radius: var(--radius-base); padding: var(--space-lg) 1rem; font-size: var(--text-base); gap: 0.5rem; }}
  .free {{ border-radius: 50% 9999px; margin: 0 auto; padding: 1px 2px; gap: 1.5em; font-family: inherit; }}
  .calc {{ padding: calc(var(--space-lg) + 3px); font-size: clamp(15px, 2vw, 31px); }}
  .icon {{ font-family: 'Material Symbols Outlined'; }}
</style></head><body><p class="card">这里是一段中文正文，用来确认档位检查只报真正偏离 tokens 的值。</p></body></html>"""
        report = lint_design.lint_page(page, "final", tokens)
        found = {}
        for f in report["findings"]:
            if f["rule"] in ("TOKEN-RADIUS", "TOKEN-SPACING", "TOKEN-FONT", "TOKEN-FONT-SIZE"):
                found.setdefault(f["rule"], []).append(f)
        self.assertEqual(sorted(found), ["TOKEN-FONT", "TOKEN-FONT-SIZE", "TOKEN-RADIUS", "TOKEN-SPACING"])
        self.assertTrue(all(f["severity"] == "warn" for group in found.values() for f in group))
        self.assertTrue(all(len(group) == 1 for group in found.values()), found)
        messages = {rule: group[0]["message"] for rule, group in found.items()}
        self.assertIn("37px（.card、.tag）", messages["TOKEN-RADIUS"])
        self.assertIn("13.7px（.card、.tag）", messages["TOKEN-FONT-SIZE"])
        self.assertIn("Comic Sans MS（.tag）", messages["TOKEN-FONT"])
        flagged = {rule: set(re.findall(r"(-?[\d.]+px)（", text)) for rule, text in messages.items()}
        self.assertEqual(flagged["TOKEN-RADIUS"], {"37px"})
        self.assertEqual(flagged["TOKEN-SPACING"], {"97px", "-97px"})
        self.assertEqual(flagged["TOKEN-FONT-SIZE"], {"13.7px"})
        self.assertNotIn("Material", messages["TOKEN-FONT"])
        self.assertNotIn("inherit", messages["TOKEN-FONT"])
        quiet = lint_design.lint_page(page, "structure", tokens)
        self.assertFalse({"TOKEN-RADIUS", "TOKEN-SPACING", "TOKEN-FONT", "TOKEN-FONT-SIZE"} & rules(quiet))

    def test_final_page_must_bring_its_stylesheet(self):
        tokens = copy.deepcopy(EXAMPLE_TOKENS)
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp).resolve()
            tokens_file = prod / "design" / "tokens.json"
            tokens_file.parent.mkdir()
            tokens_file.write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(run("export_tokens.py", tokens_file, "--targets", "css").returncode, 0)
            proto = prod / "prototype"
            proto.mkdir()
            body = "<body><p>这里是一段中文正文，用来确认交接包里的原型能带上自己的样式表。</p></body></html>"
            outside = f'<!doctype html><html lang="zh-CN"><head><link rel="stylesheet" href="../design/tokens.css"></head>{body}'
            report = lint_design.lint_page(outside, "final", tokens, base_dir=proto)
            flagged = [f for f in report["findings"] if f["rule"] == "CSS-LINK-OUTSIDE"]
            self.assertEqual([f["severity"] for f in flagged], ["warn"])
            report = lint_design.lint_page(outside, "direction", tokens, base_dir=proto)
            self.assertEqual([f["severity"] for f in report["findings"] if f["rule"] == "CSS-LINK-OUTSIDE"], ["info"])

            result = run("export_tokens.py", tokens_file, "--targets", "css", "--prototype", proto)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((proto / "tokens.css").read_bytes(), (prod / "design" / "tokens.css").read_bytes())
            inside = outside.replace("../design/tokens.css", "tokens.css")
            report = lint_design.lint_page(inside, "final", tokens, base_dir=proto)
            self.assertFalse({"CSS-LINK-OUTSIDE", "CSS-LINK-MISSING"} & rules(report), report["findings"])


class DesignMemoryTest(unittest.TestCase):
    def test_routes_record_taste_and_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"STYLE_COMPASS_HOME": str(Path(tmp) / "home")}
            empty, legacy, prod = (Path(tmp) / n for n in ("empty", "legacy", "prod"))
            empty.mkdir()
            (legacy / "src").mkdir(parents=True)
            (legacy / "package.json").write_text('{"dependencies": {"antd": "^5"}}', encoding="utf-8")
            (legacy / "src" / "app.css").write_text(".a{color:#1677ff;border-radius:6px;padding:8px}", encoding="utf-8")
            (prod / "design").mkdir(parents=True)
            (prod / "design" / "tokens.json").write_text(json.dumps(EXAMPLE_TOKENS, ensure_ascii=False), encoding="utf-8")

            def route(path):
                result = run("design_memory.py", "scan", path, "--json", env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)["route"]

            self.assertEqual(route(empty), "新产品")
            self.assertEqual(route(legacy), "补档")
            self.assertEqual(route(prod), "延续")

            draft = Path(tmp) / "draft.json"
            self.assertEqual(run("design_memory.py", "extract", legacy, "--out", draft, env=env).returncode, 0)
            data = json.loads(draft.read_text(encoding="utf-8"))
            self.assertEqual(data["suggested_color"]["accent"], "#1677FF")
            self.assertEqual(data["inventory"]["ui_libraries"], ["Ant Design"])

            exported = run("export_tokens.py", prod / "design" / "tokens.json", "--targets", "css,design-md",
                           "--design-md", prod / "DESIGN.md", env=env)
            self.assertEqual(exported.returncode, 0, exported.stderr)
            self.assertEqual(run("design_memory.py", "check", prod, env=env).returncode, 0)
            changed = copy.deepcopy(EXAMPLE_TOKENS)
            changed["color"]["accent"] = "#8A4B08"
            (prod / "design" / "tokens.json").write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(run("design_memory.py", "check", prod, env=env).returncode, 1)

            for i, day in enumerate(("01", "02", "03", "03")):
                consent = ["--remember-taste"] if i == 0 else []
                result = run("design_memory.py", "record", prod, "--chosen", "calm-tech/冷静表格",
                             "--offered", "calm-tech,editorial", "--rejected", "editorial（太像杂志）",
                             "--date", f"2026-10-{day}", *consent, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
            entries = design_memory.parse_entries((prod / "design" / "decisions.md").read_text(encoding="utf-8"))
            self.assertEqual(len(entries), 3)
            taste = json.loads(run("design_memory.py", "taste", "--json", env=env).stdout)
            self.assertEqual(taste["entries"], 3)
            self.assertTrue(taste["noveltyWarning"])
            self.assertEqual(taste["repeatedRejections"], [["太像杂志", 3]])

    def test_plain_css_project_routes_to_backfill(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, fresh = Path(tmp) / "plain", Path(tmp) / "fresh"
            (plain / "src").mkdir(parents=True)
            css = "".join(f".c{i}{{color:#{i:02d}3a5f;background:#fff}}\n" for i in range(6))
            (plain / "src" / "app.css").write_text(css, encoding="utf-8")
            (fresh / "prototype").mkdir(parents=True)
            for n in range(4):
                (fresh / "prototype" / f"wireframe-{n}.html").write_text("<p style='color:#999'>线框</p>", encoding="utf-8")
            report = json.loads(run("design_memory.py", "scan", plain, "--json").stdout)
            self.assertEqual(report["route"], "补档", report["signals"])
            self.assertGreaterEqual(report["signals"]["colorLiterals"], 10)
            report = json.loads(run("design_memory.py", "scan", fresh, "--json").stdout)
            self.assertEqual(report["route"], "新产品", report["signals"])
            self.assertEqual(report["signals"]["uiFiles"], 0)

    def test_no_taste_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"STYLE_COMPASS_HOME": str(Path(tmp) / "home")}
            result = run("design_memory.py", "record", tmp, "--chosen", "editorial", "--no-taste", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((Path(tmp) / "home" / "taste.md").exists())

    def test_check_covers_every_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp)
            tokens_file = prod / "design" / "tokens.json"
            tokens_file.parent.mkdir()
            tokens_file.write_text(json.dumps(EXAMPLE_TOKENS, ensure_ascii=False), encoding="utf-8")
            (prod / "design" / "direction.md").write_text("# 方向简报\n\n目标感受：冷静、可信。\n", encoding="utf-8")

            def export(*extra):
                result = run("export_tokens.py", tokens_file, "--brief", prod / "design" / "direction.md",
                             "--design-md", prod / "DESIGN.md", *extra)
                self.assertEqual(result.returncode, 0, result.stderr)

            def check():
                result = run("design_memory.py", "check", prod, "--json")
                return result.returncode, json.loads(result.stdout)

            export("--targets", "all", "--prototype", prod / "prototype")
            code, report = check()
            self.assertEqual(code, 0, report)
            self.assertEqual(len(report["checked"]), 7, report["checked"])

            (prod / "DESIGN.md").unlink()
            code, report = check()
            self.assertEqual(code, 1)
            self.assertIn({"file": "DESIGN.md", "key": None, "problem": "missing"}, report["mismatches"])

            changed = copy.deepcopy(EXAMPLE_TOKENS)
            changed["color"]["accent"] = "#8A4B08"
            tokens_file.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
            export("--targets", "css,design-md")
            code, report = check()
            self.assertEqual(code, 1)
            stale = {m["file"] for m in report["mismatches"] if m.get("problem") == "stale"}
            self.assertEqual(stale, {"design/tailwind.tokens.js", "design/DesignTokens.swift",
                                     "design/tokens.dtcg.json", "design/style-prompt.md"})
            self.assertIn("prototype/tokens.css", {m["file"] for m in report["mismatches"]})
            self.assertIn("--prototype prototype", report["fix"])

            export("--targets", "all", "--prototype", prod / "prototype")
            self.assertEqual(check()[0], 0)
            with (prod / "DESIGN.md").open("a", encoding="utf-8") as f:
                f.write("\n手写的一段补充。\n")
            code, report = check()
            self.assertEqual(code, 1)
            self.assertEqual(report["mismatches"], [{"file": "DESIGN.md", "key": None, "problem": "stale"}])

            for name in ("tokens.css", "tailwind.tokens.js", "DesignTokens.swift", "tokens.dtcg.json"):
                (prod / "design" / name).unlink()
            export("--targets", "design-md")
            code, report = check()
            self.assertEqual(code, 0, report)
            self.assertTrue(report["warnings"])

    def test_taste_needs_consent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"STYLE_COMPASS_HOME": str(Path(tmp) / "home")}
            taste_file = Path(tmp) / "home" / "taste.md"

            def record(day, *extra):
                result = run("design_memory.py", "record", tmp, "--chosen", "editorial", "--date", f"2026-10-0{day}",
                             *extra, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout

            def count():
                return len(design_memory.parse_entries(taste_file.read_text(encoding="utf-8")))

            out = record(1)
            self.assertFalse(taste_file.exists())
            self.assertIn("--remember-taste", out)
            self.assertIn("taste --off", out)
            self.assertEqual(len(design_memory.parse_entries(
                (Path(tmp) / "design" / "decisions.md").read_text(encoding="utf-8"))), 1)
            record(2, "--remember-taste")
            record(3)
            self.assertEqual(count(), 2)

            self.assertEqual(run("design_memory.py", "taste", "--off", env=env).returncode, 0)
            out = record(4)
            self.assertEqual(count(), 2)
            self.assertNotIn("--remember-taste", out)
            self.assertIn("已关闭", run("design_memory.py", "taste", env=env).stdout)
            scan = json.loads(run("design_memory.py", "scan", tmp, "--json", env=env).stdout)
            self.assertEqual((scan["tasteState"], scan["taste"]), ("off", None))

            record(5, "--remember-taste")
            self.assertEqual(count(), 3)
            self.assertNotIn(design_memory.TASTE_OFF, taste_file.read_text(encoding="utf-8"))

            env["STYLE_COMPASS_HOME"] = str(Path(tmp) / "declined")
            self.assertEqual(run("design_memory.py", "taste", "--off", env=env).returncode, 0)
            out = record(6)
            self.assertNotIn("--remember-taste", out)
            declined = (Path(tmp) / "declined" / "taste.md").read_text(encoding="utf-8")
            self.assertEqual(design_memory.parse_entries(declined), [])


class StageContractTest(unittest.TestCase):
    def test_example_passes_without_warnings(self):
        report = validate_stage_contract.validate(EXAMPLE_CONTRACT, contract_html(EXAMPLE_CONTRACT), "direction")
        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(report["warnings"], [])

    def test_legacy_contract_still_passes(self):
        legacy = copy.deepcopy(EXAMPLE_CONTRACT)
        legacy["requirements"] = legacy["requirements"][:1]
        legacy["pages"][0]["requirementIds"] = ["R01"]
        legacy["journeys"] = [{"id": "J01", "title": "进入项目", "actionIds": ["A01"], "directionRequired": True, "finalRequired": True}]
        legacy["actions"] = [{"id": "A01", "title": "打开项目", "fromState": "S01", "toState": "S02",
                              "directionRequired": True, "finalRequired": True}]
        legacy["states"] = [{"id": "S01", "title": "项目列表", "directionRequired": True, "finalRequired": True},
                            {"id": "S02", "title": "项目已打开", "directionRequired": True, "finalRequired": True}]
        report = validate_stage_contract.validate(legacy, contract_html(legacy), "direction")
        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(len(report["warnings"]), 1)

    def test_behavior_fields_are_enforced(self):
        broken = copy.deepcopy(EXAMPLE_CONTRACT)
        actions = {a["id"]: a for a in broken["actions"]}
        del actions["A01"]["errorState"]
        actions["A03"]["reversibility"] = "maybe"
        broken["states"][0]["kind"] = "normal"
        actions["A04"]["optimistic"] = True
        report = validate_stage_contract.validate(broken, contract_html(broken), "direction")
        text = "\n".join(report["errors"])
        self.assertIn("errorState", text)
        self.assertIn("reversibility", text)
        self.assertIn("kind", text)
        self.assertIn("rollbackState", text)

    def test_dead_end_error_state_warns(self):
        contract = copy.deepcopy(EXAMPLE_CONTRACT)
        contract["actions"] = [a for a in contract["actions"] if a["id"] != "A02"]
        contract["actions"][0]["recoveryActionId"] = "A04"
        contract["journeys"][0]["actionIds"] = ["A01"]
        report = validate_stage_contract.validate(contract, contract_html(contract), "direction")
        self.assertTrue(any("错误状态 S04" in w for w in report["warnings"]), report["warnings"])


class WorkbenchRegressionTest(unittest.TestCase):
    def test_scaffold_validate_lint_and_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            proto = Path(tmp) / "prototype"
            self.assertEqual(run("scaffold_review.py", proto).returncode, 0)
            index = proto / "index.html"
            result = run("validate_review_workspace.py", index)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(run("lint_design.py", "check", index, "--phase", "structure").returncode, 0)
            spec = run("export_spec.py", index, "-o", Path(tmp) / "spec.md")
            self.assertEqual(spec.returncode, 0, spec.stderr)

    def test_handoff_scripts_reject_bad_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "bad.json").write_text("{bad", encoding="utf-8")
            page = tmp / "page.html"
            page.write_text("<!doctype html><html><body><p>记账</p></body></html>", encoding="utf-8")
            cases = [
                ("compare_variants.py", tmp / "nope.html", "-o", tmp / "c.html"),
                ("export_spec.py", tmp / "nope.html", "-o", tmp / "s1.md"),
                ("export_spec.py", tmp / "bad.json", "-o", tmp / "s2.md"),
                ("export_spec.py", page, "--meta", tmp / "missing.design.json", "-o", tmp / "s3.md"),
                ("export_spec.py", page, "--meta", tmp / "bad.json", "-o", tmp / "s4.md"),
            ]
            for script, *args in cases:
                result = run(script, *args)
                self.assertNotEqual(result.returncode, 0, (script, args, result.stdout))
                self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["bad.json", "page.html"])

    def test_export_spec_reads_linked_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "design").mkdir()
            (tmp / "design" / "tokens.css").write_text(":root { --color-accent: #B4532A; --radius-base: 6px; }",
                                                       encoding="utf-8")
            page = tmp / "home.html"
            page.write_text('<!doctype html><html><head><link rel="stylesheet" href="design/tokens.css">'
                            "<style>:root { --radius-base: 8px; }</style></head><body><main>记账</main></body></html>",
                            encoding="utf-8")
            result = run("export_spec.py", page, "-o", tmp / "spec.md")
            self.assertEqual(result.returncode, 0, result.stderr)
            spec = (tmp / "spec.md").read_text(encoding="utf-8")
            self.assertIn("#B4532A", spec)
            self.assertIn("8px", spec)
            self.assertNotIn("6px", spec)

    def test_export_spec_prefers_tokens_json(self):
        tokens = copy.deepcopy(EXAMPLE_TOKENS)
        tokens["color"]["accent"] = "#0E6B8C"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "design").mkdir()
            (tmp / "design" / "tokens.json").write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
            (tmp / "prototype").mkdir()
            page = tmp / "prototype" / "final.html"
            page.write_text('<!doctype html><html lang="zh-CN"><head><style>:root { --radius-base: 37px; --hero-gap: 40px; }'
                            ".add { background: #0E6B8C; border-radius: 6px; }</style></head>"
                            "<body><main>记账</main></body></html>", encoding="utf-8")
            result = run("export_spec.py", page, "-o", tmp / "spec.md")
            self.assertEqual(result.returncode, 0, result.stderr)
            spec = (tmp / "spec.md").read_text(encoding="utf-8")
            sections = {part.split("\n", 1)[0]: part for part in spec.split("\n### ")}
            self.assertIn("`--color-accent` | `#0E6B8C`", sections["颜色"])
            self.assertIn("`--radius-base` | `6px`", sections["圆角"])
            self.assertNotIn("37px", spec)
            self.assertIn("--hero-gap", spec)
            self.assertIn("`--text-base`", sections["字体"])
            self.assertNotIn("--text-base", sections["颜色"])
            self.assertIn("数值取自", spec)
            self.assertIn("--radius-base 是 37px", result.stdout)

            bare = tmp / "bare"
            bare.mkdir()
            (bare / "page.html").write_text("<!doctype html><html><body><main>记账</main></body></html>", encoding="utf-8")
            result = run("export_spec.py", bare / "page.html", "--tokens", tmp / "design" / "tokens.json",
                         "-o", bare / "spec.md")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("#0E6B8C", (bare / "spec.md").read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as other:
            other = Path(other)
            page = other / "page.html"
            page.write_text("<!doctype html><html><body><main>记账</main></body></html>", encoding="utf-8")
            result = run("export_spec.py", page, "-o", other / "spec.md")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[spec] 警告", result.stderr)
            (other / "bad.json").write_text("{bad", encoding="utf-8")
            for tokens_arg in (other / "missing.json", other / "bad.json"):
                result = run("export_spec.py", page, "--tokens", tokens_arg, "-o", other / "s.md")
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
