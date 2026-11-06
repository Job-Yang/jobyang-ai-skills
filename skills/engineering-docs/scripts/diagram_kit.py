#!/usr/bin/env python3
"""Compose editable, platform-neutral technical diagrams with one visual grammar.

The kit emits plain, self-contained SVG using a restricted, portable subset
(rect, circle, ellipse, text, path, g, marker, optional feDropShadow) plus
semantic data-* attributes. The SVG opens directly in browsers, GitHub, Figma,
draw.io and most document editors. Editable-whiteboard adapters (e.g. the
Feishu whiteboard importer) convert the same file into native editable shapes;
scripts/lark_bind.py is an optional adapter that also binds connector endpoints
to shapes after conversion. Nothing in the core generator is Feishu-specific.
The same model can be exported to draw.io with connectors bound to nodes.
Layout stays in the author's hands; the kit owns styling, text fitting,
anchors, orthogonal edges and consistency checks.

Sizes are designed for a 960-unit canvas and scale with the canvas width, so text
keeps the same size when the diagram is shown at document width.

Example:
    from diagram_kit import Diagram
    d = Diagram(1200, 720, title="写入只经过网关", subtitle="目标架构 · 实线为调用")
    api = d.card("api", 80, 160, 260, "任务 API", desc="接收并校验任务", tone="accent")
    q = d.card("q", 460, 160, 220, "任务队列", code="kafka://tasks")
    d.edge(api, q, label="入队", style="main")
    d.save("arch.svg", drawio="arch.drawio")
"""
import html
import json
import math
import re
import unicodedata
from pathlib import Path

FONT = '"PingFang SC", "Noto Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", Arial, sans-serif'
MONO = 'Menlo, Consolas, "DejaVu Sans Mono", "Noto Sans Mono", monospace'

# Compatibility exports are derived views of the sole JSON token source.
from copy import deepcopy
from visual_theme import (THEME as VISUAL_THEME, DEFAULT_THEME, THEME_ALIASES,
                          tones, palette as theme_palette, lines as theme_lines,
                          legacy_components, variant as theme_variant, grayscale)

PALETTES = {name: theme_palette() for name in (DEFAULT_THEME, *THEME_ALIASES)}
PALETTES["plain"] = theme_palette(plain=True)
TONES = tones()
INK = VISUAL_THEME["ink"]
INK2 = MUTED = FAINT = VISUAL_THEME["muted"]
PAPER = VISUAL_THEME["paper"]
BORDER = VISUAL_THEME["entity_border"]
ZONE_BORDER = VISUAL_THEME["group_border"]
LINES = theme_lines()

# Retain the default geometry and line weights; only the paint is replaced.
_DEFAULT_STYLE = {
    "card_shadow": (0.0, 0.0, 0.0), "focal_shadow": (0.0, 0.0, 0.0), "note_shadow": (0.0, 0.0, 0.0),
    "edge_main": VISUAL_THEME["edge"], "edge_main_w": 2.0, "edge_accent_w": 2.0,
    "focal_mode": "ink-outline", "banner_mode": "tint", "zone_mode": "neutral-panel",
    "gradients": False,
}
THEMES = {name: dict(_DEFAULT_STYLE) for name in (DEFAULT_THEME, *THEME_ALIASES)}
THEMES["plain"] = {**_DEFAULT_STYLE, "edge_main": grayscale(VISUAL_THEME["line"]),
                   "edge_main_w": 1.6, "edge_accent_w": 1.8,
                   "focal_mode": "tint", "zone_mode": "grey"}
DEPRECATED_VARIANTS = {"v2-magazine", "v3-outline", "v4-dashboard"}
DOUBAO = legacy_components()
VARIANTS = {name: theme_variant() for name in ("v1-review", *sorted(DEPRECATED_VARIANTS))}
BASE = {  # font sizes and metrics on a 960-unit canvas
    "title": 24, "subtitle": 14, "zone": 14, "card": 15, "desc": 13, "code": 12, "chip": 12.5,
    "badge": 12, "label": 12.5, "note_title": 14, "note": 13, "legend": 12.5,
    "pad": 12, "gap": 6, "radius": 8, "chip_h": 22, "margin": 32,
    "card_sw": 1.3, "zone_sw": 1.0, "corner": 6.0,  # rounded-elbow radius (cosmetic only)
}


class LayoutError(ValueError):
    """Raised when content does not fit; fix the layout instead of shrinking text."""


def text_units(s):
    """Approximate advance width in em: CJK/full-width = 1, Latin ~0.6 (Feishu reflow rule)."""
    total = 0.0
    for ch in str(s):
        if unicodedata.east_asian_width(ch) in "WF":
            total += 1.0
        elif ch == " ":
            total += 0.32
        elif ch in "il.,:;|!'·":
            total += 0.34
        elif ch.isupper() or ch in "mwMW@%&":
            total += 0.72
        else:
            total += 0.58
    return total


_TOKEN = re.compile(r"\n|[A-Za-z0-9_./:@#%+-]+[ ]?|[ ]|.")
_NO_LINE_START = set("，。、；：？！）》」』】,.;:?!)")


def _mono_units(s):
    return sum(1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.6 for ch in str(s))


def _greedy_wrap(s, width, size):
    lines, cur = [], ""
    for tok in _TOKEN.findall(str(s)):
        if tok == "\n":
            lines.append(cur.rstrip())
            cur = ""
        elif cur and text_units((cur + tok).rstrip()) * size > width and tok[0] not in _NO_LINE_START:
            lines.append(cur.rstrip())
            cur = tok.lstrip()
        else:
            cur += tok
    return [line for line in lines + [cur.rstrip()]]


_BREAK_AFTER = set("、，；：,;: ")
_BREAK_BEFORE = set("与和及或")
_KEEP_AFTER, _KEEP_BEFORE = set("一二三四五六七八九十两几每这那各某"), set("个次条种项批份位")


def _two_line_split(s, width, size):
    toks = _TOKEN.findall(s)
    best = None
    for i in range(1, len(toks)):
        a, b = "".join(toks[:i]).rstrip(), "".join(toks[i:]).lstrip()
        if not a or not b or b[0] in _NO_LINE_START:
            continue
        ua, ub = text_units(a), text_units(b)
        if max(ua, ub) * size > width:
            continue
        score = abs(ua - ub) - (3 if toks[i - 1][-1] in _BREAK_AFTER else 1.5 if b[0] in _BREAK_BEFORE else 0)
        score += 2 if a[-1] in _KEEP_AFTER or b[0] in _KEEP_BEFORE else 0
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1] if best else None


def wrap(s, width, size):
    """Keep Latin words and numbers whole, never start a line with punctuation, break two-line
    text at punctuation or before a conjunction when possible, and never strand a short last line."""
    lines = _greedy_wrap(s, width, size)
    if len(lines) < 2 or "\n" in str(s):
        return lines
    if len(lines) == 2:
        return _two_line_split(str(s), width, size) or lines
    if text_units(lines[-1]) * size >= width * 0.4:
        return lines
    lo, hi = width * 0.5, width
    for _ in range(14):
        mid = (lo + hi) / 2
        if len(_greedy_wrap(s, mid, size)) <= len(lines):
            hi = mid
        else:
            lo = mid
    return _greedy_wrap(s, hi, size)


def esc(s):
    return html.escape(str(s), quote=True)


def _seg_hits(p, q, box, eps=0.5):
    """True if an axis-aligned segment p-q passes through the interior of box (x0, y0, x1, y1)."""
    (x0, y0), (x1, y1) = p, q
    bx0, by0, bx1, by1 = box
    if abs(y0 - y1) < 0.01:
        return by0 + eps < y0 < by1 - eps and min(x0, x1) < bx1 - eps and max(x0, x1) > bx0 + eps
    if abs(x0 - x1) < 0.01:
        return bx0 + eps < x0 < bx1 - eps and min(y0, y1) < by1 - eps and max(y0, y1) > by0 + eps
    steps = 24
    return any(bx0 + eps < x0 + (x1 - x0) * i / steps < bx1 - eps and by0 + eps < y0 + (y1 - y0) * i / steps < by1 - eps
               for i in range(1, steps))


def _box_overlap(a, b, eps=0.5):
    return min(a[2], b[2]) > max(a[0], b[0]) + eps and min(a[3], b[3]) > max(a[1], b[1]) + eps


def _box_inside(a, b):
    return a[0] >= b[0] and a[1] >= b[1] and a[2] <= b[2] and a[3] <= b[3]


def hex_rgb(c):
    """#rgb / #rrggbb -> (r, g, b) floats 0..1; None if not a plain hex colour."""
    c = (c or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", c):
        return tuple(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
    if re.fullmatch(r"#[0-9a-f]{3}", c):
        return tuple(int(ch * 2, 16) / 255 for ch in c[1:])
    return None


def rel_luminance(rgb):
    """WCAG relative luminance of an (r,g,b) float triple."""
    def chan(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def lightness(c):
    """Perceptual-ish HSL L (0..1) for one colour; used as a fill-contrast proxy.

    Zones use a very light pastel wash; cards are near-white, so the gap between
    them is small in absolute terms. We report it so an accidental identical fill
    (the old bug: zone tint == card tint) is always caught."""
    rgb = hex_rgb(c)
    if not rgb:
        return None
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    return (mx + mn) / 2.0


def fill_contrast(c1, c2):
    """|ΔL| between two hex fills; None if either is not a plain colour."""
    l1, l2 = lightness(c1), lightness(c2)
    if l1 is None or l2 is None:
        return None
    return abs(l1 - l2)


class Node:
    def __init__(self, nid, kind, x, y, w, h, **meta):
        self.id, self.kind, self.x, self.y, self.w, self.h = nid, kind, x, y, w, h
        self.meta = meta

    @property
    def right(self):
        return self.x + self.w

    @property
    def bottom(self):
        return self.y + self.h

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    def port(self, side, t=0.5):
        """Point on a side: left/right use t along height, top/bottom along width."""
        if side == "left":
            return (self.x, self.y + self.h * t)
        if side == "right":
            return (self.right, self.y + self.h * t)
        if side == "top":
            return (self.x + self.w * t, self.y)
        if side == "bottom":
            return (self.x + self.w * t, self.bottom)
        raise ValueError(f"unknown side {side}")


class Diagram:
    def __init__(self, width, height, title, subtitle="", summary="", font=FONT,
                 theme=DEFAULT_THEME, palette=None, variant="v1-review"):
        self.W, self.H = width, height
        self.k = width / 960.0
        # Resolve historical theme/variant aliases onto the single default style.
        resolved = THEME_ALIASES.get(theme, theme)
        self.theme_name = resolved if resolved in THEMES else DEFAULT_THEME
        self.theme = dict(THEMES[self.theme_name])
        # Historical variant/palette names are executable aliases, not new looks.
        self.variant = deepcopy(VARIANTS["v1-review"])
        self.palette_name = "plain" if self.theme_name == "plain" or palette == "plain" else DEFAULT_THEME
        self.palette = deepcopy(PALETTES[self.palette_name])
        self._plain = self.palette_name == "plain"
        if self._plain:
            self.theme["edge_main"] = grayscale(self.theme["edge_main"])
        self._bind_colors()
        self.title, self.subtitle, self.summary, self.font = title, subtitle, summary, font
        self.layers = {name: [] for name in ("zone", "edge", "card", "label", "top")}
        self.nodes, self.edges, self.fonts, self.colors = {}, [], [], set()
        self.markers = {}
        self.shadow_defs = {}
        self.label_boxes = []  # (owner, x0, y0, x1, y1) for zone titles and edge labels
        self._edge_specs = []
        self._finalized = False
        self.header_bottom = self.s("margin") + self.s("title") * 1.2
        if subtitle:
            self.header_bottom += self.s("subtitle") * 1.6
        self._header()

    def _bind_colors(self):
        """Bind paint to this instance; never rebind module compatibility exports."""
        self.tones = tones(self._plain)
        self.lines = theme_lines(self._plain)
        self.db = legacy_components(self._plain)
        self._paper = PAPER

    def _tone(self, name):
        return self.tones.get(name, self.tones["neutral"])

    def _color(self, color):
        return grayscale(color) if self._plain and hex_rgb(color) is not None else color

    # ---------- primitives ----------
    def s(self, key):
        return BASE[key] * self.k

    def _text(self, layer, x, y, value, size, color=INK, weight=400, anchor="start", family=None, extra=""):
        color = self._color(color)
        self.fonts.append(size)
        fam = f' font-family="{esc(family)}"' if family else ""
        self.layers[layer].append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size:.1f}" fill="{color}" font-weight="{weight}" '
            f'text-anchor="{anchor}"{fam}{extra}>{esc(value)}</text>')

    def _rect(self, layer, x, y, w, h, fill, stroke="none", sw=1.0, rx=None, dash=None, shadow=None,
              extra="", gradient=None):
        fill, stroke = self._color(fill), self._color(stroke)
        rx = self.s("radius") if rx is None else rx
        rx = math.floor(min(rx, h / 2, w / 2) * 10) / 10  # rx above h/2 makes Feishu fall back to an image node
        if not stroke or stroke == "none":
            stroke = "none"; sw = 0
        d = f' stroke-dasharray="{dash}"' if dash else ""
        if shadow is None:
            f = ""
        else:
            f = f' filter="url(#{shadow})"'
        fill_attr = f' fill="{fill}"'
        if gradient:
            fill_attr = f' fill="url(#{gradient})"'
        self.colors.update(c for c in (fill, stroke) if c and c != "none")
        self.layers[layer].append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx:.1f}"{fill_attr} '
            f'stroke="{stroke}" stroke-width="{sw:.2f}"{d}{f}{extra}/>')

    def _group(self, layer, kind, nid):
        """Open a <g>; Feishu turns each group into one movable group node."""
        self.layers[layer].append(f'<g data-kind="{kind}" data-id="{esc(nid)}">')
        return lambda: self.layers[layer].append("</g>")

    def _marker(self, color):
        mid = "ah-" + color.lstrip("#").lower()
        self.markers[mid] = color
        return mid

    def _ensure_shadow(self, sid, dy, sd, op, color=INK):
        self.shadow_defs[sid] = (dy, sd, op, color)
        return sid

    def _header(self):
        m = self.s("margin")
        end = self._group("top", "header", "header")
        self._text("top", m, m + self.s("title") * 0.9, self.title, self.s("title"), INK, 700)
        if self.subtitle:
            self._text("top", m, m + self.s("title") * 1.2 + self.s("subtitle") * 1.25, self.subtitle,
                       self.s("subtitle"), MUTED)
        end()

    # ---------- layout helpers ----------
    def cols(self, n, x, width, gap=None):
        """Split [x, x+width] into n equal columns; returns [(x_i, w_i)]."""
        gap = self.s("pad") * 1.5 if gap is None else gap
        w = (width - gap * (n - 1)) / n
        return [(x + i * (w + gap), w) for i in range(n)]

    def _text_inset(self, emphasis=False, tone="neutral", badge=None):
        """Horizontal inset from card left edge to where body text starts, used BOTH by
        measure_card (line wrap estimate) and by the renderer, so a card's computed height
        always matches the lines actually drawn. Accounts for the focal dot / left bar /
        badge that shift the text block right."""
        off = self.s("pad")
        vr = self.variant if self.theme_name == "doubao" else {}
        if emphasis:
            fm = self.theme.get("focal_mode")
            if fm == "ink-outline" or vr.get("focal") in ("ink-outline-num",):
                off += 8 * self.k + self.s("gap")      # focal dot diameter + gap
            elif vr.get("focal") in ("soft-tint", "panel-pill"):
                pass                                    # tint fill, no text shift
            else:
                off += 4.5 * self.k                     # solid left bar
        if badge is not None:
            off += self.s("badge") * 0.95 * 2 + self.s("gap")
        return off

    def measure_card(self, w, title, desc=None, code=None, chips=(), badge=None, rows=(),
                     emphasis=False, tone="neutral"):
        pad, gap = self.s("pad"), self.s("gap")
        inner = w - 2 * pad
        for r in rows:
            label, tag = self._row(r)[:2]
            need = text_units(label) * self.s("desc") + (self._chip_w(tag) + gap if tag else 0)
            if need > inner:
                raise LayoutError(f"row {label!r} needs {need:.0f} of {inner:.0f} in card {title!r}; "
                                  "shorten it or widen the card")
        tw = w - self._text_inset(False, tone, badge) - pad
        if text_units(title) * self.s("card") > tw:
            raise LayoutError(f"card title too long for width {w:.0f}: {title!r}; widen the card or shorten the title")
        h = pad + self.s("card") * 1.25
        if code:
            h += gap + self.s("chip_h") * 0.9
        if desc:
            # Wrap width must match the renderer: text starts at _text_inset, ends one pad
            # from the right edge.
            text_w = w - self._text_inset(emphasis, tone, badge) - pad
            lines = wrap(desc, text_w, self.s("desc"))
            if len(lines) > 3:
                raise LayoutError(f"desc wraps to {len(lines)} lines in card {title!r}; keep it to <=3 lines or split")
            h += gap + len(lines) * self.s("desc") * 1.4
        if chips:
            chip_rows = self._chip_rows(chips, inner)
            h += gap + len(chip_rows) * (self.s("chip_h") + gap) - gap
        if rows:
            h += gap + len(rows) * self._row_h()
        return h + pad

    def _row_h(self):
        return self.s("chip_h") + self.s("gap")

    @staticmethod
    def _row(r):
        """rows item: "label" or (label, tag[, style[, tone]]) -> (label, tag, style, tone)."""
        r = (r,) if isinstance(r, str) else tuple(r)
        return (r + (None, "outline", "neutral")[len(r) - 1:])[:4]

    def _chip_w(self, text):
        return text_units(text) * self.s("chip") + self.s("pad") * 1.3

    def _chip_rows(self, chips, inner):
        rows, cur, cw = [], [], 0.0
        for c in chips:
            label = c[0] if isinstance(c, (tuple, list)) else c
            w = self._chip_w(label)
            if w > inner:
                raise LayoutError(f"chip {label!r} wider than card content; shorten it")
            if cur and cw + self.s("gap") + w > inner:
                rows.append(cur)
                cur, cw = [], 0.0
            cur.append(c)
            cw += (self.s("gap") if len(cur) > 1 else 0) + w
        if cur:
            rows.append(cur)
        return rows

    # ---------- components ----------
    def zone(self, zid, x, y, w, h, label, tone="neutral", dashed=False, fill=True, label_side="top"):
        """Region for grouping (system boundary, phase, lane). Pass tone="sky"/"sage"/...
        to tint a whole layer with that low-saturation pastel (architecture layers)."""
        t = self._tone(tone)
        neu = self._tone("neutral")
        end = self._group("zone", "zone", zid)
        if fill:
            # Groups are neutral context, independent of entity category paint.
            zfill = VISUAL_THEME["panel_bg"]
            zborder = VISUAL_THEME["group_border"]
        else:
            # An unfilled/dashed boundary is intentional, so keep its requested outline.
            zfill, zborder = "none", t["border"]
        if self.theme_name == "doubao":
            vz = self.variant
            zfill, zborder = vz["zone_fill"], vz["zone_border"]
            zsw = 1.0 * self.k
            self._rect("zone", x, y, w, h, zfill, zborder, zsw,
                       rx=vz["radius"] * self.k, dash="6 4" if dashed else None)
        else:
            zsw = 1.25 * self.k if self.theme_name == DEFAULT_THEME else self.s("zone_sw")
            self._rect("zone", x, y, w, h, zfill, zborder, zsw,
                       rx=6 * self.k if self.theme_name == DEFAULT_THEME else self.s("radius") * 1.5,
                       dash="6 4" if dashed else None)
        size = self.s("zone")
        if label_side == "top":
            lx = x + self.s("pad") * 1.3
            self._text("zone", lx, y + size * 1.55, label, size, t["text"] if tone != "neutral" else INK2, 600)
            self.label_boxes.append((f"zone:{zid}", lx - 2, y + size * 0.45,
                                     lx + text_units(label) * size + 2, y + size * 1.9))
        else:
            self._text("zone", x + size * 1.3, y + h / 2, label, size,
                       t["text"] if tone != "neutral" else INK2, 600, anchor="middle",
                       extra=f' transform="rotate(-90 {x + size * 1.3:.1f} {y + h / 2:.1f})"')
        end()
        n = Node(zid, "zone", x, y, w, h, label=label, tone=tone, dashed=dashed,
                 body_fill=zfill if zfill != "none" else None,
                 body_border=zborder)
        self.nodes[zid] = n
        return n

    def zone_around(self, zid, members, label, pad=None, top=None, **kw):
        pad = self.s("pad") * 1.5 if pad is None else pad
        top = self.s("zone") * 2.4 if top is None else top
        x0 = min(m.x for m in members) - pad
        y0 = min(m.y for m in members) - top
        x1 = max(m.right for m in members) + pad
        y1 = max(m.bottom for m in members) + pad
        return self.zone(zid, x0, y0, x1 - x0, y1 - y0, label, **kw)

    def chip(self, x, y, label, style="soft", tone="neutral", layer="card", on_focal=False):
        """Pill tag. filled = deep pastel solid with white text; outline = white fill
        + soft border; soft = very light tint. on_focal is accepted for API
        compatibility and renders the same soft pastel pill."""
        t = self._tone(tone)
        w, h = self._chip_w(label), self.s("chip_h")
        if style == "filled":
            fill, stroke, color, opacity = t["solid"], "none", PAPER, 1
        elif style == "outline":
            fill, stroke, color, opacity = PAPER, t["border"], t["text"], 1
        elif style == "dashed":
            fill, stroke, color, opacity = PAPER, t["border"], t["text"], 1
        else:
            fill, stroke, color, opacity = (t["tint"] if tone != "neutral" else self._tone("neutral")["tint"]), "none", t["text"], 1
        extra = ' fill-opacity="%.2f"' % opacity if opacity != 1 else ""
        self._rect(layer, x, y, w, h, fill, stroke, 1.1 * self.k, rx=h / 2,
                   dash="4 3" if style == "dashed" else None, extra=extra)
        self._text(layer, x + w / 2, y + h * 0.68, label, self.s("chip"), color, 500, anchor="middle")
        return w

    def card(self, cid, x, y, w, title, desc=None, code=None, chips=(), badge=None, tone="neutral",
             emphasis=False, dashed=False, h=None, shadow=True, rows=()):
        """Node card: [badge] title / code id / desc / chips / rows. Height fits content unless h is given.

        chips: list of str or (label, style, tone). tone colours the border and badge;
        emphasis=True fills the card with the tone tint (use for the one focal node).
        rows: one line per member of a group, each with an optional right-aligned tag, e.g.
        [("订单库", "唯一写入方", "filled", "accent"), ("报表副本", "只读")]. Use it when the design's rule
        applies member by member, so readers can see which members carry it instead of a bare count.
        """
        need = self.measure_card(w, title, desc, code, chips, badge, rows,
                                 emphasis=emphasis, tone=tone)
        if h is not None and h + 0.5 < need:
            raise LayoutError(f"card {cid} needs height {need:.0f}, got {h:.0f}")
        h = need if h is None else h
        t = self._tone(tone)
        th = self.theme
        # Ordinary entities use a category-tinted face and a subtle border. Focal
        # entities keep the same face but gain a stronger same-hue outline and dot.
        focal_bar = None
        focal_dot = None
        vr = self.variant
        if emphasis:
            fill, border, card_sw = t["tint"], t["border"], 1.5 * self.k
            if th.get("focal_mode") == "ink-outline":
                focal_dot = t["solid"]
        else:
            fill, border, card_sw = t["tint"], t["entity_border"], 1.0 * self.k
        end = self._group("card", "card", cid)
        sh_key = "focal_shadow" if emphasis else "card_shadow"
        dy, sd, op = th[sh_key]
        use_shadow = bool(shadow and not dashed and op > 0.01)
        if use_shadow:
            self._ensure_shadow(f"sh-{sh_key}", dy, sd, op)
        self._rect("card", x, y, w, h, fill, border, card_sw,
                   dash="6 4" if dashed else None,
                   shadow=(f"sh-{sh_key}" if use_shadow else None))
        if focal_bar:
            self._rect("card", x, y, 4.5 * self.k, h, focal_bar, "none", rx=2 * self.k)
        pad, gap = self.s("pad"), self.s("gap")
        cy = y + pad
        tx = x + pad + (4.5 * self.k if focal_bar else 0)
        if focal_dot:
            ds = 8 * self.k
            self.layers["card"].append(
                f'<circle cx="{x + pad + ds / 2:.1f}" cy="{cy + self.s("card") * 0.55:.1f}" r="{ds / 2:.1f}" '
                f'fill="{focal_dot}"/>')
            tx += ds + gap
        if badge is not None:
            r = self.s("badge") * 0.95
            badge_fill = t["solid"] if tone != "neutral" or emphasis else self._color(INK2)
            self.layers["card"].append(
                f'<circle cx="{x + pad + r:.1f}" cy="{cy + self.s("card") * 0.62:.1f}" r="{r:.1f}" '
                f'fill="{badge_fill}"/>')
            self._text("card", x + pad + r, cy + self.s("card") * 0.62 + self.s("badge") * 0.36, badge,
                       self.s("badge"), PAPER, 700, anchor="middle")
            tx += r * 2 + gap
        self._text("card", tx, cy + self.s("card") * 0.95, title, self.s("card"), INK, 600)
        cy += self.s("card") * 1.25
        if code:
            cy += gap
            cw = _mono_units(code) * self.s("code") + pad
            self._rect("card", x + pad, cy, cw, self.s("chip_h") * 0.9, self._tone("neutral")["tint"], "none", rx=4 * self.k)
            self._text("card", x + pad + pad / 2, cy + self.s("chip_h") * 0.62, code, self.s("code"), INK2,
                       family=MONO)
            cy += self.s("chip_h") * 0.9
        if desc:
            cy += gap
            for line in wrap(desc, w - (tx - x) - pad, self.s("desc")):
                self._text("card", tx, cy + self.s("desc") * 1.05, line, self.s("desc"), MUTED)
                cy += self.s("desc") * 1.4
        if chips:
            cy += gap
            for row in self._chip_rows(chips, w - 2 * pad):
                cx = x + pad
                for c in row:
                    label, style, ctone = (c if isinstance(c, (tuple, list)) else (c, "soft", "neutral"))
                    cx += self.chip(cx, cy, label, style, ctone) + gap
                cy += self.s("chip_h") + gap
        if rows:
            cy += gap if not chips else 0
            for r in rows:
                label, tag, style, rtone = self._row(r)
                self._text("card", x + pad, cy + self.s("chip_h") * 0.68, label, self.s("desc"), INK2)
                if tag:
                    self.chip(x + w - pad - self._chip_w(tag), cy, tag, style, rtone)
                cy += self._row_h()
        end()
        n = Node(cid, "card", x, y, w, h, title=title, desc=desc, code=code, chips=list(chips), tone=tone,
                 emphasis=emphasis, dashed=dashed, rows=[self._row(r)[:2] for r in rows],
                 body_fill=fill, body_border=border)
        self.nodes[cid] = n
        return n

    def bar(self, bid, x, y, w, label, items=(), tone="neutral", h=None):
        """Full-width strip for a shared layer (installer, seam bus). items are joined with ·."""
        t = self._tone(tone)
        size = self.s("card")
        h = h or size * 2.6
        end = self._group("card", "bar", bid)
        self._rect("card", x, y, w, h, t["tint"], t["border"], 1.1 * self.k)
        text = label + ("：" + " · ".join(items) if items else "")
        if text_units(text) * size > w - 2 * self.s("pad"):
            raise LayoutError(f"bar {bid} text too long; shorten items")
        self._text("card", x + w / 2, y + h / 2 + size * 0.35, text, size, t["text"] if tone != "neutral" else INK,
                   600, anchor="middle")
        end()
        n = Node(bid, "card", x, y, w, h, title=text, tone=tone, kind_tag="bar")
        self.nodes[bid] = n
        return n

    def phase_banner(self, bid, x, y, w, index, title, desc=None, tone="neutral", h=None):
        """Numbered phase banner: "01 工程源与 Profile → 控制编译范围".

        A thin tinted strip that labels a phase row without becoming a card.
        index is rendered in a solid square badge; title is bold, desc muted after a
        middle dot. Use one banner per phase zone, visually lighter than the cards.
        """
        t = self._tone(tone)
        size = self.s("zone")
        h = h or size * 2.5
        pad = self.s("pad") * 0.9
        end = self._group("card", "banner", bid)
        heavy = self.variant.get("heavy") == "header-pills" and self.theme_name == "doubao"
        if heavy:
            self._rect("card", x, y, w, h, INK, "none", rx=h / 2)
            bx = x + pad + 4
            bsize = h * 0.52
            self._rect("card", bx, y + (h - bsize) / 2, bsize, bsize, PAPER, "none", rx=bsize / 2)
            self._text("card", bx + bsize / 2, y + h / 2 + size * 0.34, str(index).zfill(2),
                       size * 0.95, INK, 700, anchor="middle")
            tx = bx + bsize + pad
            self._text("card", tx, y + h / 2 + size * 0.36, title, size, PAPER, 700)
            if desc:
                tw = text_units(title) * size
                self._text("card", tx + tw + size * 0.8, y + h / 2 + size * 0.36, desc,
                           size * 0.92, MUTED)
            end()
            n = Node(bid, "card", x, y, w, h, title=f"{index} {title}", tone=tone, kind_tag="banner")
            self.nodes[bid] = n
            return n
        # Cream banner: light pastel slab + one solid index chip + dark text.
        self._rect("card", x, y, w, h, t["tint"], t["border"], 1.0 * self.k, rx=8 * self.k)
        bx = x + pad
        bsize = size * 1.62
        self._rect("card", bx, y + (h - bsize) / 2, bsize, bsize, t["solid"], "none", rx=4 * self.k)
        self._text("card", bx + bsize / 2, y + h / 2 + size * 0.4, str(index).zfill(2),
                   size * 1.0, PAPER, 700, anchor="middle")
        tx = bx + bsize + pad
        tcol, dcol = INK, MUTED
        if desc:
            if text_units(title) * size > (w - (tx - x) - pad) * 0.55:
                self._text("card", tx, y + h * 0.42, title, size, tcol, 700)
                self._text("card", tx, y + h * 0.82, desc, size * 0.92, dcol)
            else:
                self._text("card", tx, y + h / 2 + size * 0.36, title, size, tcol, 700)
                tw = text_units(title) * size
                self._text("card", tx + tw + size * 0.8, y + h / 2 + size * 0.36, desc,
                           size * 0.92, dcol)
        else:
            self._text("card", tx, y + h / 2 + size * 0.36, title, size, tcol, 700)
        end()
        n = Node(bid, "card", x, y, w, h, title=f"{index} {title}", tone=tone, kind_tag="banner")
        self.nodes[bid] = n
        return n

    def note(self, nid, x, y, w, title, text, tone="neutral", h=None):
        """Takeaway card with a colour bar: one rule or conclusion the reader should keep."""
        t = self._tone(tone)
        pad = self.s("pad")
        lines = wrap(text, w - 2 * pad - 4 * self.k, self.s("note"))
        need = pad * 2 + self.s("note_title") * 1.3 + len(lines) * self.s("note") * 1.45
        h = max(h or 0, need)
        end = self._group("card", "note", nid)
        ndy, nsd, nop = self.theme["note_shadow"]
        note_shadow = "sh-note" if nop > 0.01 else None
        if note_shadow:
            self._ensure_shadow(note_shadow, ndy, nsd, nop)
        self._rect("card", x, y, w, h, t["tint"], t["border"], 1.0 * self.k, shadow=note_shadow)
        self._rect("card", x, y, 4 * self.k, h, t["solid"], rx=2 * self.k)
        self._text("card", x + pad + 4 * self.k, y + pad + self.s("note_title") * 0.95, title,
                   self.s("note_title"), t["text"], 700)
        cy = y + pad + self.s("note_title") * 1.3
        for line in lines:
            self._text("card", x + pad + 4 * self.k, cy + self.s("note") * 1.05, line, self.s("note"), INK2)
            cy += self.s("note") * 1.45
        end()
        n = Node(nid, "note", x, y, w, h, title=title, text=text, tone=tone)
        self.nodes[nid] = n
        return n

    # ---------- doubao-style primitives (flat, near-white surface) ----------
    def _db(self):
        return self.db

    def verdict_bar(self, nid, x, y, w, text, h=None):
        """Light accent conclusion bar with readable ink; geometry and API are unchanged."""
        k = self.k
        h = h or 52 * k
        end = self._group("card", "verdict", nid)
        self._rect("card", x, y, w, h, self.db["verdict_bg"], "none", rx=12 * k)
        self._text("card", x + 18 * k, y + h / 2 + self.s("desc") * 0.36, text, self.s("desc"),
                   self.db["verdict_text"], 700)
        end()
        n = Node(nid, "card", x, y, w, h, title=text, body_fill=self.db["verdict_bg"])
        self.nodes[nid] = n
        return n

    def status_pill(self, x, y, label, level="strong"):
        """Full-rounded status pill (strong/mid/weak). Drains to the baseline;
        returns (x, y, w, h)."""
        k = self.k
        tok = self.db["pills"].get(level, self.db["pills"]["neutral"])
        h = 22 * k
        tw = text_units(label) * self.s("note")
        w = tw + 20 * k
        end = self._group("card", "pill", f"pill-{label}")
        self._rect("card", x, y, w, h, tok["fill"], "none", rx=h / 2)
        self._text("card", x + w / 2, y + h / 2 + self.s("note") * 0.36, label, self.s("note"),
                   tok["text"], 700, anchor="middle")
        end()
        return (x, y, w, h)

    def category_card(self, nid, x, y, w, title, body, cat="pink", h=None, left_bar=False):
        """Neutral category card; cat=accent opts into emphasis, never status colour."""
        k = self.k
        tok = self.db["categories"].get(cat, self.db["categories"]["neutral"])
        pad = 16 * k
        body_lines = wrap(body, w - 2 * pad - (6 * k if left_bar else 0), self.s("note"))
        need = pad + self.s("card") * 1.2 + 8 * k + len(body_lines) * self.s("note") * 1.45 + pad
        h = max(h or 0, need)
        end = self._group("card", "category", nid)
        self._rect("card", x, y, w, h, tok["fill"], tok["border"], 1.1 * k, rx=12 * k)
        bx = x
        if left_bar:
            self._rect("card", x, y, 6 * k, h, tok["border"], rx=3 * k)
            bx = x + 6 * k
        self._text("card", bx + pad, y + pad + self.s("card") * 0.95, title, self.s("card"),
                   tok["title"], 700)
        cy = y + pad + self.s("card") * 1.25
        for ln in body_lines:
            self._text("card", bx + pad, cy + self.s("note") * 1.05, ln, self.s("note"),
                       self.db["body"], 400)
            cy += self.s("note") * 1.45
        end()
        n = Node(nid, "card", x, y, w, h, title=title, tone=cat, body_fill=tok["fill"],
                 body_border=tok["border"], emphasis=True)
        self.nodes[nid] = n
        return n

    def evidence_action_row(self, nid, x, y, w, title, evidence, action, prio="p0", h=None):
        """Evidence→action two-column row: white card, light border, 6px priority
        left bar, muted evidence on the left, accent action text on the right."""
        k = self.k
        pad = 16 * k
        bar = self.db["prio_bar"].get(prio, self.db["prio_bar"]["none"])
        ev_lines = wrap(evidence, w * 0.52 - pad - 8 * k, self.s("note"))
        ac_lines = wrap(action, w * 0.36, self.s("note"))
        lines = max(len(ev_lines), len(ac_lines), 1)
        need = pad + self.s("card") * 1.15 + 6 * k + lines * self.s("note") * 1.45 + pad
        h = max(h or 0, need)
        end = self._group("card", "row", nid)
        self._rect("card", x, y, w, h, PAPER, self.db["row_border"], 1.25 * k, rx=10 * k)
        self._rect("card", x, y, 6 * k, h, bar, rx=3 * k)
        tx = x + pad + 6 * k
        self._text("card", tx, y + pad + self.s("card") * 0.95, title, self.s("card"),
                   self.db["ink"], 700)
        cy = y + pad + self.s("card") * 1.25
        for ln in ev_lines:
            self._text("card", tx, cy + self.s("note") * 1.05, ln, self.s("note"),
                       self.db["muted"], 400)
            cy += self.s("note") * 1.45
        ax = x + w * 0.58
        acy = y + pad + self.s("card") * 1.25
        for ln in ac_lines:
            self._text("card", ax, acy + self.s("note") * 1.05, ln, self.s("note"),
                       self.db["action"], 400)
            acy += self.s("note") * 1.45
        end()
        n = Node(nid, "card", x, y, w, h, title=title, body_fill=PAPER)
        self.nodes[nid] = n
        return n

    def matrix_table(self, nid, x, y, w, headers, rows, row_header_w=None, cell_h=None):
        """Assessment matrix: neutral pill headers, gray row headers, white cells
        with a status pill at the top-left. headers=[str...], rows=[(rowheader,[(level,text)])].
        Returns the bottom y."""
        k = self.k
        row_header_w = row_header_w or 150 * k
        ncol = len(headers)
        gap = 10 * k
        cell_w = (w - row_header_w - gap * (ncol + 1)) / ncol
        head_h = 40 * k
        cell_h = cell_h or 96 * k
        end = self._group("card", "matrix", nid)
        # column headers: neutral pills
        cx = x + row_header_w + gap
        for htext in headers:
            self._rect("card", cx, y, cell_w, head_h, self.db["matrix_head_bg"], "none", rx=head_h / 2)
            self._text("card", cx + cell_w / 2, y + head_h / 2 + self.s("note") * 0.36, htext,
                       self.s("note"), self.db["matrix_head_text"], 700, anchor="middle")
            cx += cell_w + gap
        cy = y + head_h + gap
        for rhead, cells in rows:
            # row header
            self._rect("card", x, cy, row_header_w, cell_h, self.db["row_header_bg"], "none", rx=10 * k)
            for i, rln in enumerate(wrap(rhead, row_header_w - 20 * k, self.s("note"))[:2]):
                self._text("card", x + 12 * k, cy + 18 * k + i * self.s("note") * 1.4, rln,
                           self.s("note"), self.db["ink"], 700)
            ccx = x + row_header_w + gap
            PILL_CN = {"strong": "强", "mid": "中", "weak": "弱"}
            for level, ctext in cells:
                self._rect("card", ccx, cy, cell_w, cell_h, PAPER, self.db["cell_border"],
                           1.25 * k, rx=10 * k)
                self.status_pill(ccx + 12 * k, cy + 12 * k, PILL_CN.get(level, level),
                                 level if level in self.db["pills"] else "neutral")
                ty = cy + 12 * k + 22 * k + 8 * k
                for ln in wrap(ctext, cell_w - 24 * k, self.s("note"))[:3]:
                    self._text("card", ccx + 12 * k, ty + self.s("note") * 1.05, ln, self.s("note"),
                               self.db["body"], 400)
                    ty += self.s("note") * 1.4
                ccx += cell_w + gap
            cy += cell_h + gap
        end()
        n = Node(nid, "card", x, y, w, cy - y, title="matrix", body_fill=PAPER)
        self.nodes[nid] = n
        return cy - gap

    def text(self, x, y, value, size="desc", color=MUTED, weight=400, anchor="start"):
        self._text("label", x, y, value, self.s(size) if isinstance(size, str) else size, color, weight, anchor)

    def edge(self, a, b, a_side="right", b_side="left", via=None, label=None, style="normal",
             a_t=0.5, b_t=0.5, label_at=None, arrow=True, label_dx=0, label_dy=0, align=None,
             port="auto"):
        """Orthogonal connector from a to b. via pins exact waypoints; port="auto" spreads
        several edges leaving one side by the other end's position."""
        if align is None and via is None and isinstance(a, Node) and isinstance(b, Node) and a_t == b_t == 0.5:
            horiz = {"left", "right"}
            if a_side in horiz and b_side in horiz:
                lo, hi = max(a.y, b.y), min(a.bottom, b.bottom)
            elif a_side not in horiz and b_side not in horiz:
                lo, hi = max(a.x, b.x), min(a.right, b.right)
            else:
                lo, hi = 1, 0
            if hi - lo > 2 * self.s("pad"):
                align = (lo + hi) / 2
        if align is not None:
            def t_for(n, side):
                if not isinstance(n, Node):
                    return 0.5
                t = (align - n.x) / n.w if side in ("top", "bottom") else (align - n.y) / n.h
                if not 0 <= t <= 1:
                    raise LayoutError(f"align={align:.0f} is outside {n.id} on its {side} side")
                return t
            a_t, b_t = t_for(a, a_side), t_for(b, b_side)
        spec = {"a": a, "b": b, "a_side": a_side, "b_side": b_side, "via": list(via) if via else None,
                "label": label, "style": style,
                "a_t": a_t,
                "a_auto": port == "auto" and align is None and via is None and a_t == 0.5
                          and isinstance(b, Node),
                "b_t": b_t,
                "b_auto": port == "auto" and align is None and via is None and b_t == 0.5
                          and isinstance(a, Node),
                "label_at": label_at, "label_dx": label_dx, "label_dy": label_dy, "arrow": arrow}
        self._edge_specs.append(spec)
        self._finalized = False
        return self._route(spec)

    def _other_coord(self, spec, end):
        n = spec["b"] if end == "a" else spec["a"]
        side = spec["a_side"] if end == "a" else spec["b_side"]
        if isinstance(n, Node):
            return n.cy if side in ("left", "right") else n.cx
        return n[1] if side in ("left", "right") else n[0]

    def _distribute_ports(self):
        groups = {}
        for spec in self._edge_specs:
            for end, side in (("a", spec["a_side"]), ("b", spec["b_side"])):
                if isinstance(spec[end], Node):
                    groups.setdefault((spec[end].id, side), []).append((spec, end))
        for (_, side), items in groups.items():
            # An edge whose other end is a free point tuple pins this end (the author chose
            # the coordinate, e.g. aligning to the target row); only fully node-to-node
            # edges with default ports are eligible for distribution.
            fixed = sorted(sp["a_t"] if end0 == "a" else sp["b_t"]
                           for sp, end0 in items
                           if not (sp["a_auto"] if end0 == "a" else sp["b_auto"]))
            auto_items = [(sp, end0) for sp, end0 in items
                          if (sp["a_auto"] if end0 == "a" else sp["b_auto"])]
            auto_items.sort(key=lambda it: self._other_coord(it[0], it[1]))
            m = len(auto_items)
            if not m:
                continue
            slots = [(i + 1) / (m + 1) for i in range(m)]
            for k in range(m):
                for f in fixed:
                    if abs(slots[k] - f) < 0.11:
                        slots[k] = f + (0.13 if slots[k] >= f else -0.13)
            for (sp, end), t in zip(auto_items, slots):
                t = max(0.14, min(0.86, t))
                if end == "a":
                    sp["a_t"] = t
                else:
                    sp["b_t"] = t

    @staticmethod
    def _simplify(points):
        clean = [points[0]]
        for p in points[1:]:
            if abs(p[0] - clean[-1][0]) > 0.01 or abs(p[1] - clean[-1][1]) > 0.01:
                clean.append(p)
        merged = clean[:1]
        for i, p in enumerate(clean[1:], 1):
            if i + 1 < len(clean):
                a0, nxt = merged[-1], clean[i + 1]
                if (abs(a0[0] - p[0]) < 0.01 and abs(p[0] - nxt[0]) < 0.01) or \
                        (abs(a0[1] - p[1]) < 0.01 and abs(p[1] - nxt[1]) < 0.01):
                    continue
            merged.append(p)
        return merged

    def _route(self, spec):
        a, b = spec["a"], spec["b"]
        p0 = a.port(spec["a_side"], spec["a_t"]) if isinstance(a, Node) else a
        p1 = b.port(spec["b_side"], spec["b_t"]) if isinstance(b, Node) else b
        pts = [p0] + list(spec["via"] or []) + [p1]
        if not spec["via"]:
            horiz = {"left", "right"}
            if spec["a_side"] in horiz and spec["b_side"] in horiz:
                mx = (p0[0] + p1[0]) / 2
                pts = [p0, (mx, p0[1]), (mx, p1[1]), p1]
            elif spec["b_side"] not in horiz and spec["a_side"] not in horiz:
                my = (p0[1] + p1[1]) / 2
                pts = [p0, (p0[0], my), (p1[0], my), p1]
            elif spec["a_side"] in horiz:
                pts = [p0, (p1[0], p0[1]), p1]
            else:
                pts = [p0, (p0[0], p1[1]), p1]
        return self._simplify(pts)

    def _line_paint(self, style):
        """Resolve an edge style to (color, width, dash) from the active palette."""
        color, width, dash = self.lines[style]
        if style == "main":
            color, width = self.theme["edge_main"], self.theme["edge_main_w"]
        elif style == "accent":
            width = self.theme["edge_accent_w"]
        return color, width * self.k, dash

    def _rounded_path(self, pts, style, arrow):
        """Orthogonal path with small rounded elbows; sharp waypoints stay in data-points."""
        color, width, dash = self._line_paint(style)
        radius = self.s("corner")
        if radius <= 0 or len(pts) < 3:
            d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        else:
            d = [f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"]
            for i, p in enumerate(pts[1:], 1):
                if i == len(pts) - 1:
                    d.append(f"L{p[0]:.1f} {p[1]:.1f}")
                    continue
                pre, post = pts[i - 1], pts[i + 1]
                h_in, h_out = abs(pre[1] - p[1]) < 0.01, abs(p[1] - post[1]) < 0.01
                if h_in == h_out:
                    d.append(f"L{p[0]:.1f} {p[1]:.1f}")
                    continue
                rin = max(0.0, min(radius, math.dist(pre, p) / 2 - 0.01, math.dist(p, post) / 2 - 0.01))
                if rin < 1.5:
                    d.append(f"L{p[0]:.1f} {p[1]:.1f}")
                    continue
                if h_in:
                    pin = (p[0] - rin if pre[0] < p[0] else p[0] + rin, p[1])
                else:
                    pin = (p[0], p[1] - rin if pre[1] < p[1] else p[1] + rin)
                if h_out:
                    pout = (p[0] + rin if post[0] > p[0] else p[0] - rin, p[1])
                else:
                    pout = (p[0], p[1] + rin if post[1] > p[1] else p[1] - rin)
                d.append(f"L{pin[0]:.1f} {pin[1]:.1f}")
                d.append(f"Q{p[0]:.1f} {p[1]:.1f} {pout[0]:.1f} {pout[1]:.1f}")
            d = " ".join(d)
        mk = f' marker-end="url(#ah-{style})"' if arrow else ""
        ds = f' stroke-dasharray="{dash}"' if dash else ""
        points_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width:.2f}" '
                f'stroke-linejoin="round" stroke-linecap="round"{ds}{mk} data-points="{points_attr}"/>')

    def _finalize(self):
        """Recompute ports, routes, paths and edge labels once the whole graph is known."""
        if getattr(self, "_finalized", False):
            return
        self._distribute_ports()
        self.layers["edge"] = []
        self.label_boxes = [b for b in self.label_boxes if not b[0].startswith("edge-label:")]
        self.layers["label"] = []
        self.edges = []
        for i, spec in enumerate(self._edge_specs):
            pts = self._route(spec)
            spec["points"] = pts
            src = spec["a"].id if isinstance(spec["a"], Node) else ""
            dst = spec["b"].id if isinstance(spec["b"], Node) else ""
            path = self._rounded_path(pts, spec["style"], spec["arrow"])
            self.layers["edge"].append(
                path.replace("/>", f' data-kind="edge" data-from="{esc(src)}" data-to="{esc(dst)}"/>'))
            self.edges.append({"from": src, "to": dst, "points": pts, "label": spec["label"],
                               "style": spec["style"], "arrow": spec["arrow"]})
        for i, spec in enumerate(self._edge_specs):
            if spec["label"]:
                pos = spec["label_at"]
                if pos is None:
                    endpoints = {x for x in (spec["a"].id if isinstance(spec["a"], Node) else "",
                                                   spec["b"].id if isinstance(spec["b"], Node) else "") if x}
                pos = self._place_label(spec["points"], spec["label"], endpoints)
                self._draw_edge_label(i, pos[0] + spec["label_dx"], pos[1] + spec["label_dy"],
                                      spec["label"], spec["style"], spec["points"])
        self._finalized = True

    def _draw_edge_label(self, i, x, y, label, style, pts):
        size = self.s("label")
        w = text_units(label) * size + self.s("pad")
        h = size * 1.6
        on_line = False
        for p, q in zip(pts, pts[1:]):
            if abs(p[1] - q[1]) < 0.01 and abs(y - p[1]) <= h / 2 + 1 and min(p[0], q[0]) <= x <= max(p[0], q[0]):
                on_line = True
            if abs(p[0] - q[0]) < 0.01 and abs(x - p[0]) <= w / 2 + 1 and min(p[1], q[1]) <= y <= max(p[1], q[1]):
                on_line = True
        if on_line:
            end = self._group("label", "edge-label", label)
            self._rect("label", x - w / 2, y - h / 2, w, h, PAPER, "none", rx=h / 2)
            end()
        color = self.lines[style][0] if style in ("alert", "accent", "planned") else MUTED
        self._text("label", x, y + size * 0.36, label, size, color, 500, anchor="middle")
        self.label_boxes.append((f"edge-label:{i}", x - w / 2, y - h / 2, x + w / 2, y + h / 2))


    def _label_size(self, label):
        return text_units(label) * self.s("label") + self.s("pad"), self.s("label") * 1.6

    def _label_ok(self, box, endpoints=()):
        for n in self.nodes.values():
            if n.id in endpoints:
                continue
            r = (n.x, n.y, n.right, n.bottom)
            if n.kind in ("card", "note") and _box_overlap(box, r):
                return False
            if n.kind == "zone" and _box_overlap(box, r) and not _box_inside(box, r):
                return False  # straddles a zone border; Feishu treats it as overflowing that container
        return not any(_box_overlap(box, b) for owner, *b in self.label_boxes if owner != "legend")

    def _place_label(self, pts, label, endpoints=()):
        """Label the longest straight segment: above/below (or left/right) by default,
        on the line only when it is comfortably long. Never sit at a corner."""
        lw, lh = self._label_size(label)
        segs = sorted(zip(pts, pts[1:]), key=lambda seg: -(abs(seg[0][0] - seg[1][0]) + abs(seg[0][1] - seg[1][1])))
        fallback = None
        for s0, s1 in segs[:3]:
            horizontal = abs(s0[1] - s1[1]) < 0.01
            length = abs(s0[0] - s1[0]) if horizontal else abs(s0[1] - s1[1])
            fits_on_line = length >= (lw if horizontal else lh) + 2 * self.s("pad")
            for t in (0.5, 0.38, 0.62, 0.28, 0.72):
                x = s0[0] + (s1[0] - s0[0]) * t
                y = s0[1] + (s1[1] - s0[1]) * t
                gap = 5 * self.k
                if horizontal:
                    offsets = [(0, -lh / 2 - gap), (0, lh / 2 + gap)]
                    if fits_on_line:
                        offsets.append((0, 0))
                else:
                    offsets = [(lw / 2 + gap, 0), (-lw / 2 - gap, 0)]
                    if fits_on_line:
                        offsets.append((0, 0))
                for dx, dy in offsets:
                    cx, cy = x + dx, y + dy
                    box = (cx - lw / 2, cy - lh / 2, cx + lw / 2, cy + lh / 2)
                    if fallback is None:
                        fallback = (cx, cy)
                    if self._label_ok(box, endpoints):
                        return cx, cy
        return fallback

    def edge_label(self, x, y, label, style="normal"):
        size = self.s("label")
        w = text_units(label) * size + self.s("pad")
        h = size * 1.6
        self.label_boxes.append((f"edge-label:{label}", x - w / 2, y - h / 2, x + w / 2, y + h / 2))
        color = self.lines.get(style, self.lines["normal"])[0]
        end = self._group("label", "edge-label", label)
        self._rect("label", x - w / 2, y - h / 2, w, h, PAPER, "none", rx=h / 2)
        self._text("label", x, y + size * 0.36, label, size, color if style in ("alert", "accent", "planned") else MUTED,
                   500, anchor="middle")
        end()

    # ---------- legend ----------
    def _legend_item_width(self, it, size, sw):
        """Advance width of one legend item at the given scale:
        [swatch][fixed gap][real-measured text]. The old bug was measuring only
        the text width (via _chip_w) and forgetting the swatch, so the next
        swatch landed on the previous item's last characters."""
        kind = it[0]
        if kind == "chip":
            return self._chip_w(it[1])
        if kind == "line":
            return 26 * self.k + 6 * self.k + text_units(it[1]) * size
        return sw + 6 * self.k + text_units(it[1]) * size

    def legend(self, items, x=None, y=None, per_row=None):
        """items: ("chip", label, style, tone) | ("line", label, style) |
        ("zone", label, tone, dashed?) | ("card", label, tone) | ("dot", label, tone).

        Layout is computed, never hand-placed:
          * every item occupies exactly [square swatch][fixed gap][text][item gap];
          * the swatch is a small rounded square ≈ one line tall, with a same-colour
            thin outline (not a narrow vertical strip), matching the body card 1:1;
          * text width is measured with the real advance-width helper (text_units),
            no guessed constants;
          * items flow left to right; a row that would cross the right safe margin
            wraps to a fresh row that restarts at the left boundary (uniform row
            gap); if even a single row cannot fit, the whole block is uniformly
            scaled down until it fits, and raises below the readability floor.

        Render-time hard geometry guard: every legend text box must not intersect
        any swatch rect / other text box, and the whole block must stay inside the
        left/right safe margins — violations raise LayoutError (never a warning).

        Default position: single row sits top-right beside the title block; wrapped
        rows drop to a left-aligned block under the header."""
        m = self.s("margin")
        avail = self.W - 2 * m
        size0 = self.s("legend")
        rh0 = self.s("chip_h")                 # row height
        sw0 = rh0 - 6 * self.k                 # swatch side: a small square ≈ one line tall
        g1, g2, rg = 6 * self.k, self.s("pad"), 10 * self.k   # swatch→text, item→item, row gap
        widths0 = [self._legend_item_width(it, size0, sw0) for it in items]
        # Greedy row packing within the safe horizontal band.
        rows, cur, curw = [], [], 0.0
        for it, w in zip(items, widths0):
            need = w + (g2 if cur else 0.0)
            if cur and curw + need > avail + 0.5:
                rows.append(cur)
                cur, curw = [], 0.0
            cur.append((it, w))
            curw += need
        if cur:
            rows.append(cur)
        row_widths0 = [sum(w for _, w in row) + g2 * (len(row) - 1) for row in rows]
        max_row_w0 = max(row_widths0)
        scale = 1.0 if max_row_w0 <= avail + 0.5 else avail / max_row_w0
        if scale < 0.55:
            raise LayoutError(f"图例总宽 {max_row_w0:.0f}px 无法在安全宽度 {avail:.0f}px 内放下"
                              f"（缩小到 {scale:.2f} 已低于可读下限）：减少图例项或缩短文字")
        size, rh, sw, g1, g2, rg = (size0 * scale, rh0 * scale, sw0 * scale,
                                    g1 * scale, g2 * scale, rg * scale)
        x0 = x if x is not None else (self.W - m - row_widths0[0] * scale if len(rows) == 1 else m)
        y0 = y if y is not None else m + self.s("title") * 0.2
        end = self._group("top", "legend", "legend")
        sw_rects, text_boxes = [], []
        ry, block_x1, block_y1 = y0, x0, y0
        for row in rows:
            cx = x0
            for it, w0 in row:
                kind = it[0]
                cy = ry + rh / 2
                if kind == "chip":
                    w = self.chip(cx, ry, it[1], it[2], it[3], layer="top")
                    sw_rects.append((cx, ry, cx + w, ry + rh))
                    cx += w + g2
                    continue
                sw_w = sw
                if kind == "card":
                    # Mini body card 1:1: white tile, soft tone outline, thin tone
                    # solid left cue — same value ladder as the body focal card.
                    t = self._tone(it[2])
                    self._rect("top", cx, cy - sw / 2, sw, sw, PAPER, t["border"], 1.1 * self.k,
                               rx=3.5 * self.k)
                    self._rect("top", cx, cy - sw / 2, 3.5 * self.k, sw, t["solid"], "none",
                               rx=1.5 * self.k)
                elif kind == "dot":
                    t = self._tone(it[2])
                    self._rect("top", cx, cy - sw / 2, sw, sw, t["solid"], "none", rx=2 * self.k)
                elif kind == "zone":
                    t = self._tone(it[2])
                    self._rect("top", cx, cy - sw / 2, sw, sw, t["tint"], t["border"], 1.1 * self.k,
                               rx=3 * self.k, dash="4 3" if (len(it) > 3 and it[3]) else None)
                elif kind == "line":
                    color, width, dash = self._line_paint(it[2])
                    ds = f' stroke-dasharray="{dash}"' if dash else ""
                    sw_w = 26 * self.k * scale
                    self.layers["top"].append(
                        f'<path d="M{cx:.1f} {cy:.1f} L{cx + sw_w:.1f} {cy:.1f}" stroke="{color}" '
                        f'stroke-width="{width:.2f}"{ds} marker-end="url(#ah-{it[2]})"/>')
                sw_rects.append((cx, cy - sw / 2, cx + sw_w, cy + sw / 2))
                tx = cx + sw_w + g1
                tw = text_units(it[1]) * size
                self._text("top", tx, cy + size * 0.36, it[1], size, MUTED)
                text_boxes.append((tx, cy - size / 2, tx + tw, cy + size / 2))
                cx += sw_w + g1 + tw + g2
            block_x1 = max(block_x1, cx - g2)
            ry += rh + rg
        block_y1 = ry - rg
        end()
        # ---- hard geometry guard (render-time raise, never a warning) -------
        for i, tb in enumerate(text_boxes):
            if tb[0] < m - 0.5 or tb[2] > self.W - m + 0.5:
                raise LayoutError(f"图例文字盒越出左右安全边距: {tb}（x∈[{m:.0f}, {self.W - m:.0f}]）")
            for j, ob in enumerate(text_boxes):
                if i != j and _box_overlap(tb, ob):
                    raise LayoutError(f"图例文字盒互相重叠: {tb} vs {ob}")
            for sr in sw_rects:
                if _box_overlap(tb, sr):
                    raise LayoutError(f"图例文字压到色样矩形: {tb} vs {sr}")
        self.label_boxes.append(("legend", x0, y0, block_x1, block_y1))
        return (x0, y0, block_x1 - x0)

    # ---------- output ----------
    def check(self):
        self._finalize()
        issues = []
        solid = [n for n in self.nodes.values() if n.kind in ("card", "note")]
        for i, a in enumerate(solid):
            if a.x < 0 or a.y < self.header_bottom - 1 or a.right > self.W or a.bottom > self.H:
                issues.append(f"out of canvas or overlaps header: {a.id}")
            for b in solid[i + 1:]:
                if min(a.right, b.right) > max(a.x, b.x) + 0.5 and min(a.bottom, b.bottom) > max(a.y, b.y) + 0.5:
                    issues.append(f"overlap: {a.id} / {b.id}")
        for n in self.nodes.values():
            if n.kind == "zone" and (n.right > self.W or n.bottom > self.H):
                issues.append(f"zone out of canvas: {n.id}")
        for e in self.edges:
            ends = {e["from"], e["to"]}
            segs = list(zip(e["points"], e["points"][1:]))
            name = f'{e["from"] or "point"}->{e["to"] or "point"}'
            length = sum(abs(q[0] - p[0]) + abs(q[1] - p[1]) for p, q in segs)
            if e.get("arrow", True) and length < 24 * self.k:
                issues.append(f"edge {name} is only {length:.0f}px long; the arrow is unreadable, "
                              f"leave at least {24 * self.k:.0f}px between the nodes")
            for n in solid:
                if n.id not in ends and any(_seg_hits(p, q, (n.x, n.y, n.right, n.bottom)) for p, q in segs):
                    issues.append(f"edge {name} crosses {n.id}; reroute with via= or align=")
            for owner, *box in self.label_boxes:
                if owner.startswith("zone:") and any(_seg_hits(p, q, box) for p, q in segs):
                    issues.append(f"edge {name} crosses the title of {owner[5:]}")
        for owner, *box in self.label_boxes:
            if owner == "legend":
                for n in self.nodes.values():
                    if _box_overlap(box, (n.x, n.y - 6 * self.k, n.right, n.bottom)):
                        issues.append(f"legend is too close to {n.id}; leave space below the legend")
                        break
        for i, (owner, *box) in enumerate(self.label_boxes):
            if not owner.startswith("edge-label:"):
                continue
            edge = next((e for e in self.edges if f"edge-label:" in owner and
                         int(owner.split(":")[1]) == self.edges.index(e)), None)
            endpoints = {edge["from"], edge["to"]} if edge else set()
            for n in solid:
                if n.id in endpoints:
                    continue
                if _box_overlap(box, (n.x, n.y, n.right, n.bottom)):
                    issues.append(f"{owner} covers {n.id}; move it with label_at/label_dx/label_dy")
            for n in self.nodes.values():
                r = (n.x, n.y, n.right, n.bottom)
                if n.kind == "zone" and _box_overlap(box, r) and not _box_inside(box, r):
                    issues.append(f"{owner} straddles the border of zone {n.id}; move it fully inside or outside")
            for other, *obox in self.label_boxes[i + 1:]:
                if _box_overlap(box, obox):
                    issues.append(f"{owner} overlaps {other}")
        issues.extend(self._zone_integrity_issues())
        at_doc = min(self.fonts) * 800 / self.W if self.fonts else 0
        warnings = self._geometry_warnings()
        return {"issues": issues, "warnings": warnings, "min_font_at_800px": round(at_doc, 1),
                "cards": len(solid),
                "main_cards": sum(1 for n in self.nodes.values()
                                  if n.kind == "card" and n.meta.get("kind_tag") != "bar"),
                "edges": len(self.edges), "colors": sorted(self.colors)}

    def _zone_title_band(self):
        """Height a zone reserves for its title band: cards must start below this."""
        return self.s("zone") * 2.4

    def _zone_of(self, node):
        """Zone the node belongs to: the zone whose rect overlaps the node by the
        largest area (a card that slips out of its zone is still attributed to it)."""
        nb = (node.x, node.y, node.right, node.bottom)
        best, best_area = None, 0.0
        for z in self.nodes.values():
            if z.kind != "zone":
                continue
            ox = min(nb[2], z.right) - max(nb[0], z.x)
            oy = min(nb[3], z.bottom) - max(nb[1], z.y)
            area = ox * oy if ox > 0 and oy > 0 else 0.0
            if area > best_area:
                best, best_area = z, area
        return best

    def _zone_integrity_issues(self):
        """Cards must live inside their zone, clear of the title band, and sit on a
        zone fill that is not the same colour as the card body (the old bug)."""
        out = []
        eps = 1.0  # a card that truly crosses the zone border; a 2px breathing room is fine
        band = self._zone_title_band()
        for n in self.nodes.values():
            if n.kind not in ("card", "note"):
                continue
            z = self._zone_of(n)
            if z is None:
                continue
            # 1) card fully inside the zone (allow a hairline tolerance).
            if n.x < z.x - eps or n.right > z.right + eps or \
                    n.y < z.y - eps or n.bottom > z.bottom + eps:
                out.append(f"{n.id} 没有完整落在区域 {z.id}（{z.meta.get('label', '')}）内："
                           f"撑高区域或把卡片收进边距")
            # 2) title band: a labelled zone reserves a band; cards must start below it.
            #    Zones with no label (a phase row headed by a banner) have no title band.
            elif z.meta.get("label") and n.y < z.y + band - eps:
                out.append(f"{n.id} 与区域 {z.id} 的标题贴得太近：卡片顶部应在标题带"
                           f"（{self.s('zone') * 2.4:.0f}px）之下")
            # 3) fill contrast: the card body must not read as the zone ground.
            #    The focal/emphasis card keeps the tint slab but owns a solid left
            #    bar, so it is exempt from this contrast rule.
            zfill = z.meta.get("body_fill")
            nfill = n.meta.get("body_fill")
            if zfill and nfill and not n.meta.get("emphasis"):
                d = fill_contrast(zfill, nfill)
                if d is not None and d < 0.02:
                    out.append(f"{n.id} 的填充与区域 {z.id} 底色几乎相同（ΔL={d:.3f}）："
                               f"卡片改白底、区域用更浅的底或加描边")
        return out

    def _geometry_warnings(self):
        """Soft checks for the two aesthetics that affect understanding most: crossings and bends."""
        warnings = []
        segments = [(e, p, q) for e in self.edges for p, q in zip(e["points"], e["points"][1:])]
        # Crossings at a shared bus x (fan-out/fan-in elbows) are joins, not crossings:
        # two edges entering/leaving the same node on the same side share that channel.
        def shared_bus(e1, e2, hx, hy):
            # A crossing is a real join only when the exact elbow belongs to both routes
            # (one edge's vertical run meets the other's bend it also travels through).
            for e_a, e_b in ((e1, e2), (e2, e1)):
                for p_a in e_a["points"]:
                    if abs(p_a[0] - hx) < 0.5 and abs(p_a[1] - hy) < 0.5:
                        for p_b in e_b["points"]:
                            if abs(p_b[0] - hx) < 0.5 and abs(p_b[1] - hy) < 0.5:
                                return True
            return False
        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                e1, p, q = segments[i]
                e2, r, s = segments[j]
                if {e1["from"], e1["to"]} == {e2["from"], e2["to"]}:
                    continue
                h1, h2 = abs(p[1] - q[1]) < 0.01, abs(r[1] - s[1]) < 0.01
                if h1 == h2:
                    continue
                (hx0, hy), (hx1, _) = (p, q) if h1 else (r, s)
                (vx, vy0), (_, vy1) = (r, s) if h1 else (p, q)
                if min(hx0, hx1) + 0.5 < vx < max(hx0, hx1) - 0.5 and \
                        min(vy0, vy1) + 0.5 < hy < max(vy0, vy1) - 0.5:
                    if shared_bus(e1, e2, vx, hy):
                        continue
                    warnings.append(f"连线交叉：{e1['from']}→{e1['to']} 与 {e2['from']}→{e2['to']}，重排节点或用 via 绕行")
        for e in self.edges:
            bends = len(e["points"]) - 2
            if bends > 2:
                warnings.append(f"{e['from']}→{e['to']} 有 {bends} 个拐点：拆图或走外侧通道")
        main_cards = [n for n in self.nodes.values()
                      if n.kind == "card" and n.meta.get("kind_tag") != "bar"]
        if len(main_cards) > 12:
            warnings.append(f"主卡片 {len(main_cards)} 张（不含横贯层和结论卡），超过 12 张：拆成总览与详图")
        warnings.extend(self._layout_density_warnings())
        warnings.extend(self._edge_detour_warnings())
        return warnings

    def _layout_density_warnings(self):
        """Flag a canvas that is mostly empty or weighted to one side: the eye reads a
        large blank strip (the old right-third empty band) as 'no focus'. Containers
        (zones/bars) are excluded from the measure: only cards/notes define the real
        content footprint, otherwise an over-wide zone would hide its own empty space."""
        out = []
        body = [n for n in self.nodes.values() if n.kind in ("card", "note")]
        body = [n for n in body if n.meta.get("kind_tag") not in ("bar", "banner")]
        if len(body) < 2:
            return out
        x0 = min(n.x for n in body)
        y0 = min(n.y for n in body)
        x1 = max(n.right for n in body)
        y1 = max(n.bottom for n in body)
        content_w, content_h = x1 - x0, y1 - y0
        coverage = (content_w * content_h) / (self.W * self.H)
        margin = self.s("margin")
        left_gap = x0 - margin
        right_gap = self.W - margin - x1
        if coverage < 0.42:
            out.append(f"内容包围盒只占画布 {coverage:.0%}：右侧/上下有大片空白，"
                       f"按内容收紧画布宽度或把元素均衡铺开")
        elif right_gap > left_gap * 2.2 and right_gap > 3.5 * margin:
            out.append(f"右侧空白（{right_gap:.0f}px）远大于左侧（{left_gap:.0f}px）："
                       f"重心偏左，裁掉右侧空白或把列均衡分布")
        return out

    def _edge_detour_warnings(self):
        """Flag edges that run far out of their way: route length well above the
        endpoint Manhattan distance means a long decorative line (the old alert edge
        that ran to the far-right edge and back)."""
        out = []
        for e in self.edges:
            pts = e["points"]
            if len(pts) < 2:
                continue
            p0, p1 = pts[0], pts[-1]
            manhattan = abs(p1[0] - p0[0]) + abs(p1[1] - p0[1])
            route = sum(abs(q[0] - p[0]) + abs(q[1] - p[1]) for p, q in zip(pts, pts[1:]))
            if manhattan < 1 or route < 60:
                continue
            ratio = route / manhattan
            if ratio > 2.1:
                out.append(f"{e['from']}→{e['to']} 路由长 {route:.0f}px，是两端直线距离的 {ratio:.1f} 倍："
                           f"长边绕远，改走就近通道或贴一个标注")
        return out

    def svg(self):
        self._finalize()
        defs = []
        # Every shadow depth actually used by components on this canvas.
        for sid, (dy, sd, op, color) in sorted(self.shadow_defs.items()):
            defs.append(f'<filter id="{sid}" x="-20%" y="-20%" width="140%" height="160%">'
                        f'<feDropShadow dx="0" dy="{dy * self.k:.1f}" stdDeviation="{sd * self.k:.1f}" '
                        f'flood-color="{color}" flood-opacity="{op}"/></filter>')
        # orient="auto", not "auto-start-reverse": resvg (PNG previews) leaves the latter unrotated,
        # so vertical arrows get a sideways head. Markers are only used as marker-end.
        # Fixed-size, slim triangle heads: they do not scale with stroke width (Feishu renders
        # markerUnits="userSpaceOnUse"), stay inside the Feishu narrow line bucket, and keep
        # orient="auto" so resvg/Feishu rotate vertical arrows correctly.
        for st in self.lines:
            color, _, _ = self._line_paint(st)
            defs.append(f'<marker id="ah-{st}" viewBox="0 0 10 10" refX="9.2" refY="5" '
                        f'markerWidth="{self.s("label") * 0.72:.2f}" markerHeight="{self.s("label") * 0.72:.2f}" '
                        f'markerUnits="userSpaceOnUse" orient="auto">'
                        f'<path d="M0.8 0.9 L9.2 5 L0.8 9.1 z" fill="{color}"/></marker>')
        body = "".join("".join(self.layers[k]) for k in ("zone", "edge", "card", "label", "top"))
        canvas = self.palette["canvas"]
        # Responsive root: fixed pixel width/height would overflow a narrow doc
        # container (vertical/horizontal scrollbar). viewBox + width:100% +
        # preserveAspectRatio lets the diagram scale to its container while
        # keeping aspect ratio; rsvg-convert --width still sets the PNG size.
        return (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'viewBox="0 0 {self.W:.0f} {self.H:.0f}" '
                f'preserveAspectRatio="xMidYMid meet" '
                f'style="width:100%;height:auto;display:block" '
                f'role="img" font-family="{esc(self.font)}">'
                f'<title>{esc(self.title)}</title><desc>{esc(self.summary or self.subtitle)}</desc>'
                f'<defs>{"".join(defs)}</defs><rect width="100%" height="100%" fill="{canvas}"/>'
                f'{body}</svg>\n')

    def save(self, path, drawio=None, strict=True):
        report = self.check()
        if strict and report["issues"]:
            raise LayoutError("; ".join(report["issues"]))
        Path(path).write_text(self.svg(), encoding="utf-8")
        if drawio:
            Path(drawio).write_text(self.drawio(), encoding="utf-8")
        return report

    def drawio(self):
        """Export the same model to draw.io; edges are bound to their source/target cells."""
        self._finalize()
        cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']

        def geo(x, y, w, h):
            return f'<mxGeometry x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" as="geometry"/>'

        cells.append(f'<mxCell id="title" value="{esc(self.title)}" style="text;html=1;fontSize={self.s("title"):.0f};'
                     f'fontStyle=1;align=left;verticalAlign=top;" vertex="1" parent="1">'
                     f'{geo(self.s("margin"), self.s("margin"), self.W * 0.7, self.s("title") * 1.4)}</mxCell>')
        order = sorted(self.nodes.values(), key=lambda n: 0 if n.kind == "zone" else 1)
        for n in order:
            t = self._tone(n.meta.get("tone", "neutral"))
            neu = self._tone("neutral")
            if n.kind == "zone":
                zfill = n.meta.get("body_fill") or "none"
                zborder = n.meta.get("body_border") or "none"
                style = (f"rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor={zfill};strokeColor={zborder};"
                         f"verticalAlign=top;align=left;spacingLeft=12;fontStyle=1;fontSize={self.s('zone'):.0f};"
                         f"fontColor={self._color(INK2)};" + ("dashed=1;" if n.meta.get("dashed") else ""))
                value = esc(n.meta.get("label", ""))
            elif n.kind == "note":
                style = (f"rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor={t['tint']};strokeColor={t['border']};"
                         f"align=left;verticalAlign=top;spacing=10;fontSize={self.s('note'):.0f};")
                value = esc(f"<b>{html.escape(n.meta.get('title', ''))}</b><br>{html.escape(n.meta.get('text', ''))}")
            else:
                emph = n.meta.get("emphasis")
                fill = n.meta.get("body_fill", t["tint"] if emph else t["tint"])
                stroke = n.meta.get("body_border", t["border"] if emph else t["entity_border"])
                fill, stroke = self._color(fill), self._color(stroke or "none")
                style = (f"rounded=1;arcSize=8;whiteSpace=wrap;html=1;fillColor={fill};"
                         f"strokeColor={stroke};align=left;verticalAlign=top;spacing=10;fontSize={self.s('desc'):.0f};"
                         + ("dashed=1;" if n.meta.get("dashed") else ""))
                parts = [f"<b style='font-size:{self.s('card'):.0f}px'>{html.escape(n.meta.get('title', ''))}</b>"]
                if n.meta.get("code"):
                    parts.append(f"<code>{html.escape(n.meta['code'])}</code>")
                if n.meta.get("desc"):
                    parts.append(f"<span style='color:{self._color(MUTED)}'>{html.escape(n.meta['desc'])}</span>")
                chips = [c[0] if isinstance(c, (tuple, list)) else c for c in n.meta.get("chips", [])]
                if chips:
                    parts.append(" · ".join(html.escape(c) for c in chips))
                for label, tag in n.meta.get("rows", []):
                    parts.append(html.escape(label) + (f" <b>[{html.escape(tag)}]</b>" if tag else ""))
                value = esc("<br>".join(parts))
            cells.append(f'<mxCell id="{esc(n.id)}" value="{value}" style="{style}" vertex="1" parent="1">'
                         f'{geo(n.x, n.y, n.w, n.h)}</mxCell>')
        for i, e in enumerate(self.edges):
            color, width, dash = self._line_paint(e["style"])
            style = (f"edgeStyle=orthogonalEdgeStyle;rounded=1;curved=0;html=1;strokeColor={color};strokeWidth={width:.1f};"
                     f"endArrow=block;endFill=1;fontSize={self.s('label'):.0f};fontColor={self._color(MUTED)};"
                     + ("dashed=1;" if dash else ""))
            ends = ""
            if e["from"]:
                ends += f' source="{esc(e["from"])}"'
            if e["to"]:
                ends += f' target="{esc(e["to"])}"'
            pts = e["points"]
            mids = "".join(f'<mxPoint x="{x:.1f}" y="{y:.1f}"/>' for x, y in pts[1:-1])
            g = (f'<mxGeometry relative="1" as="geometry">'
                 f'<mxPoint x="{pts[0][0]:.1f}" y="{pts[0][1]:.1f}" as="sourcePoint"/>'
                 f'<mxPoint x="{pts[-1][0]:.1f}" y="{pts[-1][1]:.1f}" as="targetPoint"/>'
                 + (f'<Array as="points">{mids}</Array>' if mids else "") + '</mxGeometry>')
            cells.append(f'<mxCell id="e{i}" value="{esc(e["label"] or "")}" style="{style}" edge="1" parent="1"{ends}>'
                         f'{g}</mxCell>')
        return ('<mxfile host="diagram_kit"><diagram name="Page-1"><mxGraphModel dx="0" dy="0" grid="1" gridSize="8" '
                f'pageWidth="{self.W:.0f}" pageHeight="{self.H:.0f}"><root>' + "".join(cells) +
                '</root></mxGraphModel></diagram></mxfile>\n')


if __name__ == "__main__":
    import sys
    d = Diagram(960, 420, "示例：写入只经过网关", "目标架构 · 实线为调用方向")
    c1, c2, c3 = d.cols(3, 32, 896, gap=72)
    a = d.card("client", c1[0], 150, c1[1], "客户端", desc="提交写请求", badge="1")
    g = d.card("gw", c2[0], 150, c2[1], "网关", code="POST /v1/tasks", desc="鉴权与限流", tone="accent",
               emphasis=True, badge="2")
    s = d.card("store", c3[0], 150, c3[1], "存储", desc="唯一写入方", chips=[("独占", "filled", "accent"), "可回放"],
               badge="3")
    d.edge(a, g, label="HTTPS", style="main")
    d.edge(g, s, label="写入", style="main")
    d.legend([("chip", "独占", "filled", "accent"), ("line", "调用", "main")])
    out = sys.argv[1] if len(sys.argv) > 1 else "demo.svg"
    print(json.dumps(d.save(out, drawio=out.replace(".svg", ".drawio")), ensure_ascii=False))
