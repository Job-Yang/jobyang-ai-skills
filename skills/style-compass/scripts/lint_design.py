#!/usr/bin/env python3
"""lint_design.py：不调用模型的设计检查。

子命令：
  check    检查原型或页面 HTML：中文排版、可访问性底线、动效、是否守 token（颜色、字体、字号、圆角、间距），
           以及常见的 AI 默认长相。读页面里的 <style>、style 属性和用 <link> 引入的本地样式表；
           网络地址和评审工作台外壳的样式不读。页面在 prototype 目录下时，引用的样式表也要在这个目录里。
  tokens   只检查 tokens.json：结构、对比度、中文字体与行高。
  diverge  比较候选方向（方向卡 directions.json 或多个 tokens.json），找出没有拉开的候选。

每条结果一行：<位置>  <级别>  <规则>  <说明>。--json 输出完整报告。
级别：error 必须修；warn 要么修，要么在交付说明里写理由；info 供参考。
SMELL-* 规则只提示，方向在 tokens.guardrails.accepted_defaults 里写明理由后会被标为"已接受"。
退出码：有 error 返回 1（--strict 时 warn 也算），参数或文件错误返回 2，否则 0。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from token_utils import (  # noqa: E402
    OVERUSED_FONTS,
    TRAINING_DEFAULT_FONTS,
    TokenError,
    accepted_defaults,
    delta_e,
    first_named_family,
    font_stack,
    has_cjk_family,
    hue_distance,
    is_cjk,
    is_grayish,
    iter_colors,
    load_tokens,
    oklch,
    parse_hex,
    split_families,
    to_hex,
    token_colors,
    validate_tokens,
)

PHASES = ("structure", "interaction", "direction", "final")
SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2, "accepted": 3}

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")
DESTRUCTIVE_RE = re.compile(r"删除|移除|清空|注销|解绑|撤销授权|退出登录|永久|不可恢复")
VAGUE_CONFIRM = {"确定", "确认", "好的", "好", "是", "ok", "yes", "submit", "提交"}
COLOR_PROPS = {
    "color", "background", "background-color", "background-image", "border", "border-color",
    "border-top", "border-right", "border-bottom", "border-left", "border-top-color",
    "border-right-color", "border-bottom-color", "border-left-color", "outline", "outline-color",
    "fill", "stroke", "caret-color", "accent-color", "text-decoration", "text-decoration-color",
    "column-rule", "column-rule-color", "scrollbar-color",
}
BODY_TEXT_SELECTOR = re.compile(r"(^|[\s,>+~(])(body|html|p|li|dd|blockquote|article|main)\b|\.(prose|content|desc|text|body|article)\b")
LATIN_ONLY_SELECTOR = re.compile(r":lang\((en|la)|\[lang\^?=['\"]?en|\b(en|latin|num|numeric|mono|code|kbd|eyebrow-en)\b", re.I)
# 字体取自数字或拉丁专用变量时，按“只放数字和英文”处理，不要求中文回退。
LATIN_FONT_VAR = re.compile(r"var\(\s*--font-(num|numeric|digits?|mono|code|latin|en)\b", re.I)
# 并排时一眼能看出的维度：拉开检查要求每对候选至少有一项不同。
VISIBLE_AXES = {"明暗", "强调色", "字体类别", "布局"}
NON_SEMANTIC_CLICK = {"div", "span", "li", "td", "tr", "img", "svg", "section", "article", "p", "label"}
CARD_CLASS_RE = re.compile(r"^(?:[\w-]*[-_])?card$")
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

# Tailwind 与 Linear 的默认强调色：生成工具最常落回的几个色值。
DEFAULT_ACCENTS = {
    "#6366F1": "Tailwind indigo-500", "#4F46E5": "Tailwind indigo-600", "#5E6AD2": "Linear 靛蓝",
    "#8B5CF6": "Tailwind violet-500", "#7C3AED": "Tailwind violet-600", "#A855F7": "Tailwind purple-500",
    "#3B82F6": "Tailwind blue-500", "#2563EB": "Tailwind blue-600",
}
# 本技能自带示例的色值：原样照抄说明没有为产品定方向。
EXAMPLE_FINGERPRINTS = [("#F6F7F9", "#0B7A75"), ("#0B0C0E", "#5E6AD2")]


def finding(severity: str, rule: str, message: str, line: Optional[int] = None, where: str = "") -> dict:
    return {"severity": severity, "rule": rule, "message": message, "line": line, "where": where}


# ---------- HTML 收集 ----------

class PageCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: Optional[str] = None
        self.viewport: Optional[Tuple[str, int]] = None
        self.styles: List[Tuple[str, int]] = []
        self.links: List[Tuple[str, int]] = []
        self.inline_styles: List[dict] = []
        self.elements: List[dict] = []
        self.cjk_chars = 0
        self.has_artboards = False
        self.confetti_lines: List[int] = []
        self.card_counts: Dict[str, int] = {}
        self.destructive_scopes: set = set()
        self._artboard_stack: List[Optional[dict]] = []
        self._artboard: Optional[dict] = None
        self._in_style = False
        self._in_script = False
        self._style_buf: List[str] = []
        self._style_line = 0
        self._name_stack: List[dict] = []

    def _scope(self) -> str:
        if not self._artboard:
            return "page"
        return self._artboard.get("id", "artboard")

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {k: (v or "") for k, v in attrs}
        line = self.getpos()[0]
        if tag == "html":
            self.lang = values.get("lang")
        if tag == "meta" and values.get("name", "").lower() == "viewport":
            self.viewport = (values.get("content", ""), line)
        if tag == "link" and "stylesheet" in values.get("rel", "").lower().split() and values.get("href"):
            self.links.append((values["href"], line))
        if tag == "style":
            self._in_style = True
            self._style_buf = []
            self._style_line = line
        if tag == "script":
            self._in_script = True
            if "confetti" in values.get("src", "").lower():
                self.confetti_lines.append(line)

        if tag not in VOID_TAGS:
            self._artboard_stack.append(self._artboard)
        if values.get("data-review-artboard"):
            self.has_artboards = True
            self._artboard = {
                "id": values.get("data-review-artboard"),
                "stage": values.get("data-review-stage", ""),
                "variant": values.get("data-review-variant", ""),
            }
        in_artboard = self._artboard is not None
        scope = self._scope()

        classes = values.get("class", "").split()
        if any(CARD_CLASS_RE.match(c.lower()) for c in classes):
            self.card_counts[scope] = self.card_counts.get(scope, 0) + 1
        if "confetti" in (values.get("class", "") + values.get("id", "")).lower():
            self.confetti_lines.append(line)
        if values.get("style"):
            self.inline_styles.append({
                "css": values["style"], "line": line, "in_artboard": in_artboard,
                "stage": (self._artboard or {}).get("stage", ""), "scope": scope,
            })

        role = values.get("role", "").lower()
        is_link = tag == "a" and "href" in values
        if tag == "button" or is_link or role in ("button", "link", "tab", "menuitem"):
            self._name_stack.append({
                "tag": tag, "line": line, "text": "", "alt": "",
                "labelled": bool(values.get("aria-label") or values.get("aria-labelledby") or values.get("title")),
                "in_artboard": in_artboard, "scope": scope, "kind": "control",
            })
        elif tag in ("h1", "h2", "h3"):
            self._name_stack.append({"tag": tag, "line": line, "text": "", "alt": "", "labelled": True,
                                     "in_artboard": in_artboard, "scope": scope, "kind": "heading"})
        if values.get("data-review-artboard") and self._artboard.get("stage") not in ("structure", "interaction"):
            self._artboard["visual"] = True
        if values.get("style") and self.inline_styles and self._artboard and self._artboard.get("visual"):
            self.inline_styles[-1]["visual"] = True
        if tag == "img" and self._name_stack:
            self._name_stack[-1]["alt"] += values.get("alt", "")
        if tag in NON_SEMANTIC_CLICK and ("onclick" in values or "data-prototype-action" in values):
            if not role and "tabindex" not in values:
                self.elements.append({"type": "click-div", "tag": tag, "line": line,
                                      "in_artboard": in_artboard, "scope": scope})

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and self._in_style:
            self._in_style = False
            self.styles.append(("".join(self._style_buf), self._style_line))
        if tag == "script":
            self._in_script = False
        if self._name_stack and self._name_stack[-1]["tag"] == tag:
            item = self._name_stack.pop()
            self.elements.append({"type": item["kind"], **item})
            if self._name_stack:
                self._name_stack[-1]["text"] += item["text"]
        if tag not in VOID_TAGS and self._artboard_stack:
            self._artboard = self._artboard_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self._style_buf.append(data)
            return
        if self._in_script:
            return
        self.cjk_chars += len(CJK_RE.findall(data))
        if DESTRUCTIVE_RE.search(data):
            self.destructive_scopes.add(self._scope())
        if self._name_stack:
            self._name_stack[-1]["text"] += data


# ---------- CSS 解析 ----------

def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), css, flags=re.S)


def parse_css(css: str, base_line: int) -> List[dict]:
    """把 CSS 拆成声明列表：{selector, prop, value, line, at}。只做本检查需要的粗解析。"""
    css = strip_comments(css)
    decls: List[dict] = []
    stack: List[str] = []
    buf_start = 0
    i = 0
    while i < len(css):
        ch = css[i]
        if ch in "'\"":
            end = css.find(ch, i + 1)
            i = len(css) if end < 0 else end + 1
            continue
        if ch == "{":
            stack.append(css[buf_start:i].strip())
            buf_start = i + 1
        elif ch == "}":
            _emit_decls(css, buf_start, i, stack, base_line, decls)
            if stack:
                stack.pop()
            buf_start = i + 1
        i += 1
    return decls


def _emit_decls(css: str, start: int, end: int, stack: List[str], base_line: int, out: List[dict]) -> None:
    if not stack:
        return
    selector = stack[-1]
    if selector.startswith("@"):
        return
    at = [s for s in stack[:-1] if s.startswith("@")]
    body = css[start:end]
    offset = start
    for part in body.split(";"):
        if ":" in part:
            prop, _, value = part.partition(":")
            prop = prop.strip().lower()
            lead = len(part) - len(part.lstrip())
            line = base_line + css.count("\n", 0, offset + lead)
            if prop and re.fullmatch(r"-{0,2}[a-z][a-z0-9-]*", prop):
                out.append({"selector": selector, "prop": prop, "value": value.strip(), "line": line, "at": at})
        offset += len(part) + 1


def inline_decls(css: str, line: int, selector: str) -> List[dict]:
    out = []
    for part in css.split(";"):
        if ":" in part:
            prop, _, value = part.partition(":")
            out.append({"selector": selector, "prop": prop.strip().lower(), "value": value.strip(), "line": line, "at": []})
    return out


def resolve_vars(value: str, variables: Dict[str, str], depth: int = 0) -> str:
    if depth > 4 or "var(" not in value:
        return value

    def repl(m):
        name, _, fallback = m.group(1).partition(",")
        name = name.strip()
        if name in variables:
            return resolve_vars(variables[name], variables, depth + 1)
        return fallback.strip()

    return re.sub(r"var\(\s*([^()]*?)\s*\)", repl, value)


def font_families_from(decl: dict, variables: Dict[str, str]) -> Optional[List[str]]:
    value = resolve_vars(decl["value"], variables)
    value = re.sub(r"\s*!important\s*$", "", value)
    if decl["prop"] == "font-family":
        return split_families(value)
    if decl["prop"] == "font":
        m = re.search(r"[\d.]+(px|rem|em|%|pt|vw)(\s*/\s*[\w.%-]+)?\s+(.+)$", value)
        if m:
            return split_families(m.group(3))
    return None


def parse_length_em(value: str) -> Optional[float]:
    m = re.match(r"^\s*(-?[\d.]+)\s*(em|px|rem)?\s*$", value)
    if not m:
        return None
    number = float(m.group(1))
    unit = m.group(2) or "px"
    return number if unit in ("em", "rem") else number / 16


def split_top_level(value: str, sep: str = ",") -> List[str]:
    parts, depth, current = [], 0, []
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p for p in parts if p.strip()]


def targets_visual_artboard(selector: str) -> bool:
    for attr, value in re.findall(r"data-review-(variant|stage)\s*=\s*['\"]?([\w-]+)", selector):
        if attr == "variant" and value != "base":
            return True
        if attr == "stage" and value not in ("structure", "interaction"):
            return True
    return False


def local_stylesheet(href: str, base_dir: Optional[Path]) -> Tuple[Optional[Path], bool]:
    """返回 (本地文件, 是否应该读)。网络地址、data: 和评审工作台外壳不读。"""
    if base_dir is None or re.match(r"^(?:[a-z][a-z0-9+.-]*:|//)", href, re.I) or "review-framework" in href:
        return None, False
    path = (base_dir / href.split("#")[0].split("?")[0]).resolve()
    return (path if path.is_file() else None), True


def prototype_root(base_dir: Optional[Path]) -> Optional[Path]:
    """页面所在的 prototype 目录。交接包只带这个目录，页面引用的文件要在它里面。"""
    if base_dir is None:
        return None
    for folder in (base_dir, *base_dir.parents):
        if folder.name == "prototype":
            return folder
    return None


def parse_times(value: str) -> List[float]:
    return [float(n) * (1 if u == "ms" else 1000) for n, u in re.findall(r"(?<![\w.-])([\d.]+)(ms|s)\b", value)]


SPACING_PROP_RE = re.compile(
    r"^(?:(?:padding|margin)(?:-(?:top|right|bottom|left|inline|block)(?:-(?:start|end))?)?|(?:row-|column-)?gap)$")
RADIUS_PROP_RE = re.compile(r"^border(?:-(?:top|bottom|start|end)-(?:left|right|start|end))?-radius$")
LENGTH_RE = re.compile(r"(?<![\w.#-])(-?(?:\d+\.?\d*|\.\d+))(px|rem)\b")
SHORTHAND_SIZE_RE = re.compile(r"(?<![\w.#-])((?:\d+\.?\d*|\.\d+))(px|rem)(?=\s*/|\s+[^\s/])")
CSS_WIDE_KEYWORDS = {"inherit", "initial", "unset", "revert", "revert-layer"}
ICON_FONT_RE = re.compile(r"icon|symbol|emoji|awesome", re.I)


def token_scale(group) -> List[float]:
    values = group.values() if isinstance(group, dict) else group if isinstance(group, list) else []
    return sorted({float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)})


def px_lengths(value: str) -> List[float]:
    """值里的 px/rem 长度，rem 按 16px 换算。含 calc、clamp 等运算或没解析开的变量时不判断。"""
    if re.search(r"\b(?:calc|clamp|min|max|env|var)\(", value):
        return []
    return [float(n) * (16 if unit == "rem" else 1) for n, unit in LENGTH_RE.findall(value)]


def token_font_names(tokens: dict) -> set:
    typ = tokens.get("typography", {}) or {}
    names = set()

    def collect(node):
        if isinstance(node, str):
            names.update(f.lower() for f in split_families(node))
        elif isinstance(node, dict):
            for child in node.values():
                collect(child)

    collect(typ)
    for role in ("heading", "body", "mono"):
        names.update(f.lower() for f in split_families(font_stack(tokens, role)))
    return names


def token_scale_findings(decls: List[dict], stacks: List[Tuple[dict, List[str]]],
                         variables: Dict[str, str], tokens: dict) -> List[dict]:
    """圆角、间距、字号要落在 tokens 的档位上，字体栈打头的字体要出自 tokens。每条规则只报一条，列出所有偏离的值。"""
    radius = token_scale(tokens.get("radius"))
    spacing = token_scale(tokens.get("spacing"))
    sizes = token_scale((tokens.get("typography", {}) or {}).get("scale"))
    fonts = token_font_names(tokens)
    hits: Dict[Tuple[str, str], List[Tuple[str, int]]] = {}

    def off_scale(scale: List[float], value: float) -> bool:
        return all(abs(value - step) > 0.1 for step in scale)

    def hit(rule: str, label: str, decl: dict) -> None:
        hits.setdefault((rule, label), []).append((decl["selector"], decl["line"]))

    for d in decls:
        prop = d["prop"]
        if prop.startswith("--"):
            continue
        value = resolve_vars(d["value"], variables)
        if radius and RADIUS_PROP_RE.match(prop):
            for v in px_lengths(value):
                if 0 < v < 999 and off_scale(radius, v):
                    hit("TOKEN-RADIUS", f"{v:g}px", d)
        elif spacing and SPACING_PROP_RE.match(prop):
            for v in px_lengths(value):
                if abs(v) > 2 and off_scale(spacing, abs(v)):
                    hit("TOKEN-SPACING", f"{v:g}px", d)
        elif sizes and prop in ("font-size", "font"):
            if prop == "font-size":
                found = px_lengths(value)
            else:
                m = None if re.search(r"\b(?:calc|clamp|min|max|var)\(", value) else SHORTHAND_SIZE_RE.search(value)
                found = [float(m.group(1)) * (16 if m.group(2) == "rem" else 1)] if m else []
            for v in found[:1]:
                if off_scale(sizes, v):
                    hit("TOKEN-FONT-SIZE", f"{v:g}px", d)
    if fonts:
        for d, families in stacks:
            first = first_named_family(families)
            if not first or first.lower() in CSS_WIDE_KEYWORDS or ICON_FONT_RE.search(first):
                continue
            if first.lower() not in fonts:
                hit("TOKEN-FONT", first, d)

    names = {"TOKEN-RADIUS": ("圆角", radius, "var(--radius-*)"),
             "TOKEN-SPACING": ("间距", spacing, "var(--space-*)"),
             "TOKEN-FONT-SIZE": ("字号", sizes, "var(--text-*)"),
             "TOKEN-FONT": ("字体", None, "var(--font-*)")}
    grouped: Dict[str, List[Tuple[str, List[Tuple[str, int]]]]] = {}
    for (rule, label), where in sorted(hits.items(), key=lambda item: item[1][0][1]):
        grouped.setdefault(rule, []).append((label, where))
    out = []
    for rule, values in sorted(grouped.items(), key=lambda item: item[1][0][1][0][1]):
        kind, scale, fix = names[rule]
        items = []
        for label, where in values[:6]:
            selectors = list(dict.fromkeys(selector for selector, _ in where))
            place = "、".join(selectors[:2]) + (f" 等 {len(selectors)} 处" if len(selectors) > 2 else "")
            items.append(f"{label}（{place}）")
        listed = "，".join(items) + (f" 等 {len(values)} 个" if len(values) > 6 else "")
        if scale is None:
            message = f"字体栈打头的 {listed} 不在 tokens 里；改用 {fix}，或先把它加进 tokens"
        else:
            steps = "、".join(f"{step:g}" for step in scale)
            message = (f"{kind}有 {len(values)} 个值不在 tokens 的档位里（{steps}）：{listed}；"
                       f"改用 {fix}，或把反复用到的值加进 tokens")
        out.append(finding("warn", rule, message, values[0][1][0][1]))
    return out


# ---------- check ----------

def lint_page(html: str, phase: str, tokens: Optional[dict], source: str = "page",
              base_dir: Optional[Path] = None) -> dict:
    page = PageCollector()
    page.feed(html)
    page.close()
    results: List[dict] = []
    accepted = accepted_defaults(tokens)
    final = phase == "final"
    visual = phase in ("direction", "final")

    decls: List[dict] = []
    for css, line in page.styles:
        decls.extend(parse_css(css, line))
    for item in page.inline_styles:
        if page.has_artboards and not item["in_artboard"]:
            continue
        for d in inline_decls(item["css"], item["line"], f"[style]@{item['scope']}"):
            d["visual"] = bool(item.get("visual"))
            decls.append(d)
    linked: List[Tuple[str, int]] = []
    proto = prototype_root(base_dir)
    for href, line in page.links:
        path, wanted = local_stylesheet(href, base_dir)
        if not wanted:
            continue
        target = path or (base_dir / href.split("#")[0].split("?")[0]).resolve()
        if proto is not None and proto not in target.parents:
            results.append(finding("warn" if final else "info", "CSS-LINK-OUTSIDE",
                                   f"引入的样式表 {href} 在 prototype 目录外，交接包只带 prototype，"
                                   "下游打开原型时这份样式会丢；把它放进 prototype 再引用"
                                   "（tokens.css 用 export_tokens.py --prototype 同步一份）", line))
        if path is None:
            results.append(finding("warn" if final else "info", "CSS-LINK-MISSING",
                                   f"引入的样式表 {href} 找不到，检查跳过了它；浏览器里它也不会生效", line))
            continue
        css = path.read_text(encoding="utf-8")
        linked.append((css, line))
        for d in parse_css(css, line):
            d["line"] = line
            decls.append(d)

    variables: Dict[str, str] = {}
    for d in decls:
        if d["prop"].startswith("--"):
            variables.setdefault(d["prop"], d["value"])
    undefined = sorted({name for d in decls for name in re.findall(r"var\(\s*(--[\w-]+)\s*\)", d["value"])
                        if name not in variables})
    if undefined:
        more = " 等" if len(undefined) > 6 else ""
        results.append(finding("warn" if visual else "info", "VAR-UNDEFINED",
                               f"用到了没有定义的变量 {', '.join(undefined[:6])}{more}；浏览器会当成没写，"
                               "确认页面引入了导出的 tokens.css"))

    elements = [e for e in page.elements if e.get("in_artboard") or not page.has_artboards]
    cjk_page = page.cjk_chars >= 20 or (page.lang or "").lower().startswith("zh") or bool(tokens and is_cjk(tokens))

    # 语言与缩放
    if cjk_page and not (page.lang or "").lower().startswith("zh"):
        results.append(finding("error", "LANG-ZH",
                               f"中文页面的 <html lang> 是 {page.lang!r}；写 zh-CN，否则汉字可能按日文字形渲染，屏幕阅读器也会读错", 1))
    elif not page.lang:
        results.append(finding("warn", "LANG-MISSING", "<html> 没有 lang 属性", 1))
    if page.viewport:
        content, line = page.viewport
        low = content.replace(" ", "").lower()
        scale = re.search(r"maximum-scale=([\d.]+)", low)
        if "user-scalable=no" in low or "user-scalable=0" in low or (scale and float(scale.group(1)) < 2):
            results.append(finding("error", "A11Y-ZOOM", f"viewport 禁止或限制了缩放（{content}），违反 WCAG 1.4.4", line))

    # 字体
    stacks: List[Tuple[dict, List[str]]] = []
    for d in decls:
        if d["prop"] in ("font-family", "font") and not d["prop"].startswith("--"):
            fams = font_families_from(d, variables)
            if fams:
                stacks.append((d, fams))
    if cjk_page:
        if not stacks:
            results.append(finding("info", "CJK-FONT-DEFAULT",
                                   "没有声明字体；中文会用浏览器默认字体（部分 Windows 环境是宋体）"))
        seen = set()
        for d, fams in stacks:
            key = ",".join(f.lower() for f in fams)
            if key in seen or has_cjk_family(fams):
                continue
            if any("mono" in f.lower() or f.lower() == "monospace" for f in fams):
                continue
            if LATIN_ONLY_SELECTOR.search(d["selector"]) or LATIN_FONT_VAR.search(d["value"]):
                continue
            first = first_named_family(fams)
            if first is None:
                continue
            seen.add(key)
            results.append(finding("error" if final else "warn", "CJK-FONT-STACK",
                                   f"{d['selector']} 的字体栈没有中文字体：{', '.join(fams)}；在 {first} 后面补 'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC' 等回退",
                                   d["line"]))
    for d, fams in stacks:
        first = (first_named_family(fams) or "").lower()
        if first in TRAINING_DEFAULT_FONTS:
            results.append(finding("info", "SMELL-TRAINING-FONT",
                                   f"{first_named_family(fams)} 是生成工具的高频选择；保留它需要一个别的字体给不了的理由", d["line"]))
        elif first in OVERUSED_FONTS and not cjk_page:
            results.append(finding("info", "SMELL-OVERUSED-FONT",
                                   f"{first_named_family(fams)} 是最常见的默认字体（Anthropic 点名）；确认这是方向的选择", d["line"]))

    # 中文字距与行高
    if cjk_page:
        for d in decls:
            if d["prop"] == "letter-spacing" and not LATIN_ONLY_SELECTOR.search(d["selector"]):
                value = resolve_vars(d["value"], variables)
                em = parse_length_em(value)
                if em is not None and em < 0:
                    results.append(finding("warn", "CJK-NEG-TRACKING",
                                           f"{d['selector']} 用了负字距 {value}；汉字是等宽方块，负字距会挤在一起，只对拉丁标题用 :lang(en)",
                                           d["line"]))
            if d["prop"] == "line-height" and BODY_TEXT_SELECTOR.search(d["selector"]):
                value = resolve_vars(d["value"], variables)
                m = re.fullmatch(r"\s*([\d.]+)\s*(%)?\s*", value)
                if m:
                    number = float(m.group(1)) / (100 if m.group(2) else 1)
                    if number < 1.5:
                        results.append(finding("warn", "CJK-LEADING",
                                               f"{d['selector']} 行高 {value}，中文正文偏紧；clreq 建议 1.5 到 2.0", d["line"]))

    # 焦点与动效
    if any(d["prop"] in ("outline", "outline-style") and resolve_vars(d["value"], variables).strip() in ("none", "0") for d in decls):
        if not any(":focus-visible" in d["selector"] for d in decls):
            line = next(d["line"] for d in decls if d["prop"] in ("outline", "outline-style"))
            results.append(finding("warn", "A11Y-FOCUS", "去掉了 outline，却没有 :focus-visible 样式；键盘用户看不到焦点", line))
    css_text = " ".join(css for css, _ in page.styles + linked)
    has_reduce = "prefers-reduced-motion" in css_text
    has_animation = "@keyframes" in css_text or any(
        d["prop"] in ("animation", "animation-name") and resolve_vars(d["value"], variables).strip() not in ("none", "")
        for d in decls)
    if has_animation and not has_reduce:
        results.append(finding("warn" if final else "info", "MOTION-REDUCE",
                               "有动画但没有 @media (prefers-reduced-motion: reduce) 替代"))
    for d in decls:
        value = resolve_vars(d["value"], variables)
        if d["prop"] == "transition-property" and "all" in value.split(","):
            results.append(finding("warn", "MOTION-ALL", f"{d['selector']} 用了 transition-property: all；只列出要动的属性", d["line"]))
        elif d["prop"] == "transition":
            for part in split_top_level(value):
                words = part.split()
                if words and (words[0] == "all" or re.fullmatch(r"[\d.]+m?s", words[0])):
                    results.append(finding("warn", "MOTION-ALL",
                                           f"{d['selector']} 的 transition 等于对所有属性做过渡（{part.strip()}）；只列出要动的属性",
                                           d["line"]))
                    break
        for x1, y1, x2, y2 in re.findall(r"cubic-bezier\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)", value):
            if not (0 <= float(y1) <= 1 and 0 <= float(y2) <= 1):
                results.append(finding("info", "SMELL-BOUNCE",
                                       f"{d['selector']} 用了回弹缓动 cubic-bezier({x1}, {y1}, {x2}, {y2})；只有好玩类方向适合", d["line"]))
        if d["prop"] in ("animation", "animation-name") and "bounce" in value.lower():
            results.append(finding("info", "SMELL-BOUNCE", f"{d['selector']} 用了 bounce 动画", d["line"]))
        if d["prop"] in ("transition", "animation"):
            long = [t for t in parse_times(value) if t > 700]
            if long:
                results.append(finding("info", "MOTION-LONG",
                                       f"{d['selector']} 动效 {int(max(long))}ms，界面反馈一般在 100 到 400ms", d["line"]))

    # 渐变、网格背景、小号大写字距
    for d in decls:
        value = resolve_vars(d["value"], variables)
        low = value.lower()
        if "gradient(" in low and d["prop"] in ("background", "background-image"):
            stops = [rgba for _, rgba, _ in iter_colors(value, include_named=True)]
            purple = [c for c in stops if oklch(c)[1] >= 0.08 and 250 <= oklch(c)[2] <= 330]
            strong_purple = [c for c in purple if oklch(c)[2] >= 270]
            near_white = [c for c in stops if oklch(c)[0] >= 0.93 and oklch(c)[1] <= 0.03]
            if strong_purple and (len(purple) >= 2 or near_white):
                results.append(finding("warn", "SMELL-PURPLE-GRADIENT",
                                       f"{d['selector']} 是紫蓝或紫白渐变（{', '.join(to_hex(c) for c in stops)}），这是 Design Arena 点名的 AI 默认长相",
                                       d["line"]))
            if (low.count("linear-gradient(") >= 2 and "1px" in low and "transparent" in low
                    or "repeating-linear-gradient(" in low and "1px" in low):
                results.append(finding("info", "SMELL-GRID-BG", f"{d['selector']} 是细线网格背景，Design Arena 点名的 AI 默认长相", d["line"]))
    for d in decls:
        if d["prop"] == "text-transform" and d["value"].strip().lower() == "uppercase":
            sibling = {x["prop"]: resolve_vars(x["value"], variables) for x in decls if x["selector"] == d["selector"]}
            em = parse_length_em(sibling.get("letter-spacing", "0"))
            if em is not None and em >= 0.05:
                results.append(finding("info", "SMELL-EYEBROW",
                                       f"{d['selector']} 是全大写加宽字距的小标签；Atlassian 设计规范明确不用这种写法，确认它属于方向", d["line"]))

    # 颜色：灰阶关、守 token
    colored: Dict[str, int] = {}
    off_token: Dict[str, Tuple[int, str]] = {}
    palette = token_colors(tokens) if tokens else {}
    for d in decls:
        if d["prop"].startswith("--"):
            continue
        if d["prop"] not in COLOR_PROPS:
            continue
        if d["prop"] in ("box-shadow", "text-shadow"):
            continue
        value = d["value"]
        gray_scope = phase in ("structure", "interaction") and not d.get("visual") and not (
            page.has_artboards and targets_visual_artboard(d["selector"]))
        for literal, rgba, _ in iter_colors(value, include_named=True):
            hexed = to_hex(rgba)
            if gray_scope and not is_grayish(rgba, 0.04):
                colored.setdefault(hexed, d["line"])
            if visual and palette:
                if rgba[3] < 1 and (is_grayish(rgba, 0.01)):
                    continue
                if min(delta_e(rgba, c) for c in palette.values()) > 2.5:
                    off_token.setdefault(hexed, (d["line"], d["selector"]))
    if colored:
        sample = ", ".join(list(colored)[:6])
        results.append(finding("warn", "GRAY-PHASE-COLOR",
                               f"结构关和交互关只用灰阶，出现了 {len(colored)} 个彩色：{sample}", min(colored.values())))
    if visual and palette:
        for hexed, (line, selector) in sorted(off_token.items(), key=lambda kv: kv[1][0]):
            results.append(finding("error" if final else "warn", "TOKEN-COLOR",
                                   f"{selector} 写死了 tokens 里没有的颜色 {hexed}；改用 var(--color-*) 或先把它加进 tokens", line))
        for d in decls:
            if d["prop"].startswith("--color-"):
                key = d["prop"][len("--color-"):].replace("-", "_")
                rgba = parse_hex(d["value"].strip())
                if key in palette and rgba and delta_e(rgba, palette[key]) > 1:
                    results.append(finding("warn", "TOKEN-DRIFT",
                                           f"{d['prop']} 是 {d['value']}，tokens.json 里是 {to_hex(palette[key])}；重新导出 tokens.css",
                                           d["line"]))
    if visual and tokens:
        results.extend(token_scale_findings(decls, stacks, variables, tokens))
    elif visual:
        results.append(finding("info", "TOKEN-SKIPPED",
                               "没有传 --tokens，跳过是否守 token 的检查（颜色、字体、字号、圆角、间距）"))

    # 元素：可访问名称、可点击的 div、确认文案、表情图标、卡片堆叠
    for e in elements:
        if e["type"] == "control":
            text = re.sub(r"\s+", "", e["text"])
            if not text and not e["alt"].strip() and not e["labelled"]:
                results.append(finding("error" if final else "warn", "A11Y-NAME",
                                       f"<{e['tag']}> 没有文字也没有 aria-label，读屏软件读不出它是什么", e["line"], e["scope"]))
            if EMOJI_RE.search(e["text"]):
                results.append(finding("info", "SMELL-EMOJI-ICON", f"<{e['tag']}> 用表情符号当图标：{e['text'].strip()[:20]}", e["line"], e["scope"]))
            if e["tag"] == "button" and text.lower() in VAGUE_CONFIRM and e["scope"] in page.destructive_scopes:
                results.append(finding("warn", "COPY-CONFIRM",
                                       f"危险操作的按钮写的是“{text}”；写成动作本身，比如“删除 3 个文件”", e["line"], e["scope"]))
        elif e["type"] == "heading" and EMOJI_RE.search(e["text"]):
            results.append(finding("info", "SMELL-EMOJI-ICON", f"<{e['tag']}> 标题里用了表情符号：{e['text'].strip()[:20]}", e["line"], e["scope"]))
        elif e["type"] == "click-div":
            results.append(finding("warn" if final else "info", "A11Y-CLICK-DIV",
                                   f"<{e['tag']}> 可点击但不是 button 或 a，键盘无法操作；换成 <button> 或补 role 和 tabindex",
                                   e["line"], e["scope"]))
    for scope, count in page.card_counts.items():
        if count >= 8 and visual:
            results.append(finding("info", "SMELL-CARD-STACK",
                                   f"{scope} 里有 {count} 个卡片元素；OpenAI 点名“应用界面由卡片堆叠而成”是常见失败，确认布局不是卡片网格兜底",
                                   None, scope))
    for line in page.confetti_lines[:1]:
        results.append(finding("info", "SMELL-CONFETTI", "页面用了彩带效果，Design Arena 统计超过四分之一的生成结果都有", line))

    # tokens 层面的默认长相
    if tokens and visual:
        results.extend(token_smells(tokens))

    for item in results:
        if item["rule"].startswith("SMELL-") and item["rule"] in accepted:
            item["severity"] = "accepted"
            item["message"] += f"（方向已接受：{accepted[item['rule']] or '未写理由'}）"
            if not accepted[item["rule"]]:
                item["severity"] = "warn"
                item["message"] += "；accepted_defaults 里补上理由"
    results = dedupe(results)
    results.sort(key=lambda r: (SEVERITY_ORDER[r["severity"]], r["line"] or 0, r["rule"]))
    return build_report(source, phase, results, extra={"cjkPage": cjk_page, "artboards": page.has_artboards})


def token_smells(tokens: dict) -> List[dict]:
    out: List[dict] = []
    colors = token_colors(tokens)
    accent, bg = colors.get("accent"), colors.get("bg")
    if accent:
        nearest = min(DEFAULT_ACCENTS, key=lambda h: delta_e(parse_hex(h), accent))
        L, C, H = oklch(accent)
        if delta_e(parse_hex(nearest), accent) < 3:
            out.append(finding("warn", "SMELL-DEFAULT-ACCENT",
                               f"accent {to_hex(accent)} 几乎就是 {DEFAULT_ACCENTS[nearest]}（{nearest}），生成工具最常落回的强调色"))
        elif 270 <= H <= 305 and C >= 0.12:
            out.append(finding("info", "SMELL-INDIGO-ACCENT",
                               f"accent {to_hex(accent)} 落在靛蓝到紫色区间（色相 {H:.0f}°），国内用户常说的“AI 味”配色"))
        if bg and oklch(bg)[0] < 0.22 and 255 <= H <= 305 and C >= 0.12:
            out.append(finding("warn", "SMELL-DARK-INDIGO",
                               f"近黑底 {to_hex(bg)} 加靛蓝强调 {to_hex(accent)}，是 Linear 式的默认组合"))
    if accent and bg:
        for ex_bg, ex_accent in EXAMPLE_FINGERPRINTS:
            if delta_e(bg, parse_hex(ex_bg)) < 1 and delta_e(accent, parse_hex(ex_accent)) < 1:
                out.append(finding("warn", "SMELL-EXAMPLE-COPY",
                                   "bg 和 accent 与技能自带示例一模一样；示例只演示格式，数值要从这个产品的方向推出来"))
    return out


def dedupe(results: List[dict]) -> List[dict]:
    seen = set()
    out = []
    for r in results:
        key = (r["rule"], r["line"], r["message"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def build_report(source: str, phase: str, results: List[dict], extra: Optional[dict] = None) -> dict:
    summary = {s: sum(1 for r in results if r["severity"] == s) for s in SEVERITY_ORDER}
    report = {"source": source, "phase": phase, "summary": summary, "findings": results}
    if extra:
        report.update(extra)
    return report


# ---------- diverge ----------

def classify_font(name: str) -> str:
    low = (name or "").lower()
    if any(k in low for k in ("mono", "code", "等宽")):
        return "mono"
    if any(k in low for k in ("serif", "song", "宋", "ming", "garamond", "times", "georgia", "playfair",
                              "fraunces", "lora", "merriweather", "baskerville", "caslon", "didot",
                              "wenkai", "文楷", "kai", "楷")) and "sans" not in low:
        return "serif"
    if any(k in low for k in ("rounded", "nunito", "quicksand", "圆")):
        return "rounded"
    return "sans"


def axes_from_tokens(tokens: dict, label: str) -> dict:
    colors = token_colors(tokens)
    typ = tokens.get("typography", {}) or {}
    layout = tokens.get("layout", {}) or {}
    decoration = tokens.get("decoration", {}) or {}
    motion = tokens.get("motion", {}) or {}
    heading = first_named_family(split_families(font_stack(tokens, "heading"))) or ""
    return {
        "id": (tokens.get("meta", {}) or {}).get("name", label),
        "bg": to_hex(colors["bg"]) if "bg" in colors else None,
        "accent": to_hex(colors["accent"]) if "accent" in colors else None,
        "heading_font": heading,
        "radius": (tokens.get("radius", {}) or {}).get("base"),
        "density": layout.get("density") or (tokens.get("spacing", {}) or {}).get("base"),
        "container": layout.get("container"),
        "decoration": decoration.get("app") or decoration.get("style"),
        "motion": motion.get("level") or motion.get("duration_base"),
        "contrarian": False,
    }


def compare_axes(a: dict, b: dict) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []
    ca, cb = parse_hex(a.get("bg") or ""), parse_hex(b.get("bg") or "")
    if ca and cb and abs(oklch(ca)[0] - oklch(cb)[0]) >= 0.25:
        score += 1
        reasons.append("明暗")
    elif ca and cb and delta_e(ca, cb) >= 8:
        score += 0.5
        reasons.append("底色(弱)")
    xa, xb = parse_hex(a.get("accent") or ""), parse_hex(b.get("accent") or "")
    if xa and xb:
        la, ka, ha = oklch(xa)
        lb, kb, hb = oklch(xb)
        if (ka >= 0.06 and kb >= 0.06 and hue_distance(ha, hb) >= 35) or abs(ka - kb) >= 0.08 or abs(la - lb) >= 0.3:
            score += 1
            reasons.append("强调色")
    fa, fb = a.get("heading_font") or "", b.get("heading_font") or ""
    if fa and fb:
        if classify_font(fa) != classify_font(fb):
            score += 1
            reasons.append("字体类别")
        elif fa.lower() != fb.lower():
            score += 0.5
            reasons.append("字体(同类)")
    ra, rb = a.get("radius"), b.get("radius")
    if isinstance(ra, (int, float)) and isinstance(rb, (int, float)):
        lo, hi = min(ra, rb), max(ra, rb)
        if hi - lo >= 6 or (lo >= 2 and hi / lo >= 2.5) or (lo < 2 and hi >= 4):
            score += 1
            reasons.append("圆角")
    for key, label in (("layout", "布局"), ("density", "密度"), ("container", "容器"), ("decoration", "装饰"),
                       ("motion", "动效")):
        va, vb = a.get(key), b.get(key)
        if va in (None, "") or vb in (None, ""):
            continue
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            threshold = 4 if key == "density" else 100
            if abs(va - vb) >= threshold:
                score += 1 if key != "motion" else 0.5
                reasons.append(label)
        elif str(va).strip().lower() != str(vb).strip().lower():
            score += 1 if key != "motion" else 0.5
            reasons.append(label)
    return score, reasons


def load_candidates(paths: List[str]) -> List[dict]:
    candidates: List[dict] = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("candidates"), list):
            for item in data["candidates"]:
                axes = dict(item.get("axes", {}))
                axes["id"] = item.get("id", "?")
                axes["contrarian"] = bool(item.get("contrarian"))
                axes["keeps"] = item.get("keeps")
                axes["flips"] = item.get("flips")
                axes["defaults"] = item.get("defaults", [])
                candidates.append(axes)
        elif isinstance(data, dict) and "color" in data:
            candidates.append(axes_from_tokens(data, Path(path).parent.name or Path(path).stem))
        else:
            raise ValueError(f"{path} 既不是方向卡（含 candidates）也不是 tokens.json")
    return candidates


def lint_diverge(candidates: List[dict], minimum: float) -> dict:
    results: List[dict] = []
    pairs = []
    if len(candidates) < 2:
        results.append(finding("error", "DIVERGE-COUNT", "至少需要 2 个候选方向"))
    for a, b in combinations(candidates, 2):
        score, reasons = compare_axes(a, b)
        pairs.append({"a": a["id"], "b": b["id"], "score": score, "differs": reasons})
        if score < minimum:
            results.append(finding("error", "DIVERGE-CLOSE",
                                   f"{a['id']} 和 {b['id']} 只在 {score:g} 个维度上不同（{'、'.join(reasons) or '无'}），至少要 {minimum:g} 个；改掉其中一个，不要只换颜色"))
        elif not VISIBLE_AXES & set(reasons):
            if a.get("layout") and b.get("layout"):
                hint = "明暗、主色、字体类别和整页布局都一样"
                fix = "并排看可能很像，至少让这四项中的一项拉开"
            else:
                hint = "明暗、主色和字体类别都一样，卡片也没写整页布局（layout）"
                fix = "先给两张卡写清 layout；布局也一样的话，再让明暗、主色或字体类别拉开一项"
            results.append(finding("warn", "DIVERGE-SURFACE",
                                   f"{a['id']} 和 {b['id']} 的{hint}，只在{'、'.join(reasons)}上不同；{fix}"))
    if candidates and not any(c.get("contrarian") for c in candidates):
        results.append(finding("warn", "DIVERGE-CONTRARIAN",
                               "没有标记反向候选（contrarian: true）；至少放一个违背第一直觉、但仍满足简报目标感受的方向"))
    for c in candidates:
        if c.get("contrarian") and not (c.get("keeps") and c.get("flips")):
            results.append(finding("warn", "DIVERGE-CONTRARIAN-BRIEF",
                                   f"{c['id']} 是反向候选，但没写 keeps（保住了简报的哪些目标感受）或 flips（推翻了哪些第一直觉的做法）；"
                                   "反向候选反的是第一直觉，不是需求"))
        for item in c.get("defaults", []) or []:
            if isinstance(item, dict) and item.get("status") == "accepted" and not item.get("reason"):
                results.append(finding("warn", "DIVERGE-DEFAULT-REASON",
                                       f"{c['id']} 接受了默认长相 {item.get('id', '?')} 却没写理由"))
    results.sort(key=lambda r: SEVERITY_ORDER[r["severity"]])
    return build_report("candidates", "direction", results, extra={"pairs": pairs, "minimum": minimum})


# ---------- 输出 ----------

def print_report(report: dict, label: str) -> None:
    for r in report["findings"]:
        where = f"{label}:{r['line']}" if r.get("line") else label
        if r.get("where") and r["where"] not in ("page", "tokens"):
            where += f" [{r['where']}]"
        print(f"{where}  {r['severity']:<8} {r['rule']}  {r['message']}")
    s = report["summary"]
    status = "FAIL" if s["error"] else ("PASS_WITH_WARNINGS" if s["warn"] else "PASS")
    print(f"[lint] {status} phase={report['phase']} error={s['error']} warn={s['warn']} info={s['info']} accepted={s['accepted']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="style-compass 设计检查")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="检查 HTML 原型或页面")
    check.add_argument("html", help="HTML 文件")
    check.add_argument("--phase", choices=PHASES, required=True)
    check.add_argument("--tokens", help="选定方向的 tokens.json，用于检查颜色是否守 token")
    tok = sub.add_parser("tokens", help="检查 tokens.json")
    tok.add_argument("tokens")
    div = sub.add_parser("diverge", help="检查候选方向有没有拉开")
    div.add_argument("files", nargs="+", help="方向卡 directions.json，或多个 tokens.json")
    div.add_argument("--min", type=float, default=3, help="每对候选至少不同的维度数，默认 3")
    for p in (check, tok, div):
        p.add_argument("--json", action="store_true", help="输出 JSON 报告")
        p.add_argument("--strict", action="store_true", help="warn 也算失败")
    args = parser.parse_args()

    try:
        if args.command == "check":
            tokens = load_tokens(args.tokens) if args.tokens else None
            html = Path(args.html).read_text(encoding="utf-8")
            report = lint_page(html, args.phase, tokens, source=args.html,
                               base_dir=Path(args.html).resolve().parent)
            label = args.html
        elif args.command == "tokens":
            tokens = load_tokens(args.tokens)
            items = [finding(f["severity"], f["rule"], f["message"]) for f in validate_tokens(tokens)]
            items += token_smells(tokens)
            accepted = accepted_defaults(tokens)
            for item in items:
                if item["rule"] in accepted and accepted[item["rule"]]:
                    item["severity"] = "accepted"
                    item["message"] += f"（方向已接受：{accepted[item['rule']]}）"
            items.sort(key=lambda r: SEVERITY_ORDER[r["severity"]])
            report = build_report(args.tokens, "tokens", items)
            label = args.tokens
        else:
            report = lint_diverge(load_candidates(args.files), args.min)
            label = "directions"
    except (OSError, ValueError, TokenError) as error:
        print(f"[lint] ERROR {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report, label)
        if args.command == "diverge":
            for pair in report["pairs"]:
                print(f"[diverge] {pair['a']} vs {pair['b']}: {pair['score']:g} 个维度（{'、'.join(pair['differs']) or '无'}）")
    failed = report["summary"]["error"] > 0 or (args.strict and report["summary"]["warn"] > 0)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
