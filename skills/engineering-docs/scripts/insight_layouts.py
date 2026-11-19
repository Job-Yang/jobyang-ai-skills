"""High-density declarative layouts: architecture-blueprint, dashboard, panorama-mindmap, flywheel.

Pure Python standard library; all colours resolve from assets/visual-examples/theme.json
via visual_theme helpers (zero literal hex codes in this file).
All internal geometry is computed in 960-unit logical space and scaled by k = width / 960
so rendered font sizes remain readable at 800px document width for any canvas width >= 680.
"""
from copy import deepcopy
import html
import math
from pathlib import Path
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram_kit import text_units, wrap as kit_wrap  # noqa: E402
from visual_theme import preset_palette, resolve_preset_accent, THEME  # noqa: E402

LW = 960.0
MIN_FONT = 11.4
BODY_FONT = 12.8
TAG_FONT = 12.6


def _check(ok, msg):
    if not ok:
        raise ValueError(msg)


def _finite(val, label):
    _check(isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val),
           f"{label} must be a finite number")
    return float(val)


def _layout_opts(spec):
    for key in ("_layout_options", "layout"):
        val = spec.get(key)
        if isinstance(val, dict):
            return val
    return {}


def _diag_tw(text, size):
    """Conservative width matching both diagram_kit.text_units and diagram_check._tw."""
    s = str(text)
    w1 = text_units(s) * size
    w2 = sum(1.0 if ord(ch) > 0x2E80 else 0.58 for ch in s) * size
    return max(w1, w2)


def _mono_units(text):
    return sum(1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.62 for ch in str(text))


_KEEP_TRAIL_PUNCT = set("。，、；：！？）】》」』”’.,;:!?)")


def _wrap(text, width, size):
    """Wrap text conservatively so neither diagram_kit nor diagram_check overflows."""
    width = max(width, size * 2.0)
    raw_lines = kit_wrap(str(text), width, size)
    fixed = []
    for line in raw_lines:
        if fixed and line and line[0] in _KEEP_TRAIL_PUNCT and len(fixed[-1]) >= 2:
            split_idx = 1
            while split_idx < len(line) and line[split_idx] in _KEEP_TRAIL_PUNCT:
                split_idx += 1
            fixed[-1], carry = fixed[-1][:-1], fixed[-1][-1]
            fixed.append(carry + line)
        else:
            fixed.append(line)
    out = []
    for line in fixed:
        if _diag_tw(line, size) <= width + 0.4:
            out.append(line)
            continue
        cur = ""
        for ch in line:
            if cur and _diag_tw(cur + ch, size) > width:
                if ch in _KEEP_TRAIL_PUNCT and len(cur) >= 2:
                    out.append(cur[:-1].rstrip())
                    cur = cur[-1] + ch
                else:
                    out.append(cur.rstrip())
                    cur = ch.lstrip()
            else:
                cur += ch
        if cur or not out:
            out.append(cur)
    return out


def _label_left(item):
    shift = {"middle": item["width"] / 2.0, "end": item["width"]}.get(item["anchor"], 0.0)
    return item["x"] - shift


def _box_overlap(a, b, eps=0.5):
    return (min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0]) + eps
            and min(a[1] + a[3], b[1] + b[3]) > max(a[1], b[1]) + eps)


def _seg_hits_box(p, q, box, pad=4.0):
    (x0, y0), (x1, y1) = p, q
    bx, by, bw, bh = box
    bx0, by0, bx1, by1 = bx - pad, by - pad, bx + bw + pad, by + bh + pad
    if abs(y0 - y1) < 0.05:
        return by0 < y0 < by1 and min(x0, x1) < bx1 and max(x0, x1) > bx0
    if abs(x0 - x1) < 0.05:
        return bx0 < x0 < bx1 and min(y0, y1) < by1 and max(y0, y1) > by0
    steps = 24
    for i in range(1, steps):
        px = x0 + (x1 - x0) * i / steps
        py = y0 + (y1 - y0) * i / steps
        if bx0 < px < bx1 and by0 < py < by1:
            return True
    return False


def _route_clear(pts, blockers, exclude_boxes):
    for p, q in zip(pts, pts[1:]):
        for k, b in blockers:
            if k in exclude_boxes:
                continue
            if _seg_hits_box(p, q, b):
                return False
    return True


def _ortho_rounded_path(pts, r=8.0):
    if len(pts) < 2:
        return ""
    if len(pts) == 2:
        return f"M{pts[0][0]:.1f} {pts[0][1]:.1f} L{pts[1][0]:.1f} {pts[1][1]:.1f}"
    d = [f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for i in range(1, len(pts) - 1):
        px, py = pts[i - 1]
        cx, cy = pts[i]
        nx, ny = pts[i + 1]
        v1x, v1y = cx - px, cy - py
        v2x, v2y = nx - cx, ny - cy
        l1, l2 = math.hypot(v1x, v1y), math.hypot(v2x, v2y)
        cr = min(r, l1 * 0.45, l2 * 0.45)
        if cr < 1.5 or (abs(v1x * v2y - v1y * v2x) < 1e-3):
            d.append(f"L{cx:.1f} {cy:.1f}")
        else:
            ax, ay = cx - v1x / l1 * cr, cy - v1y / l1 * cr
            bx, by = cx + v2x / l2 * cr, cy + v2y / l2 * cr
            d.append(f"L{ax:.1f} {ay:.1f} Q{cx:.1f} {cy:.1f} {bx:.1f} {by:.1f}")
    d.append(f"L{pts[-1][0]:.1f} {pts[-1][1]:.1f}")
    return " ".join(d)


class InsightCanvas:
    """Self-contained SVG canvas operating in 960-unit logical geometry, scaled cleanly by k = width / 960."""

    def __init__(self, spec, width=1280, preset="insight", plain=False):
        _check(isinstance(width, (int, float)) and not isinstance(width, bool)
               and math.isfinite(width) and width >= 680,
               "canvas width must be a finite number >= 680")
        self.spec = spec
        self.width = float(width)
        self.k = self.width / LW
        self.height = 600
        self.preset = preset
        self.plain = bool(plain or spec.get("plain"))
        self.pal = preset_palette(preset, plain=self.plain)
        self.surf = self.pal["surface"]
        self.fonts_cfg = {
            "sans": THEME["font"],
            "mono": "Menlo, Consolas, \"DejaVu Sans Mono\", monospace",
        }
        # Logical coordinates (0..960 horizontal)
        self.margin = 26.0
        self.pad = 12.0
        self.gap = 10.0
        self.content_width = LW - 2.0 * self.margin
        self.parts = []
        self.markers = {}
        self.boxes = {}
        self.labels = []
        self.scene_objects = {}
        self.scene_graph = {"objects": [], "edges": []}
        self._seen_ids = set()

        self.content_top = self._draw_header()

    def tone(self, item=None, fallback="slate"):
        return resolve_preset_accent(self.pal, item, fallback=fallback)

    def marker(self, color):
        mid = "ah-" + color.lstrip("#").lower()
        self.markers[mid] = color
        return mid

    def _s(self, v):
        return float(v) * self.k

    def _draw_header(self):
        m = self.margin
        badges = self.spec.get("kpi_badges") or self.spec.get("badges") or []
        badge_total_w = 0.0
        badge_specs = []
        if isinstance(badges, list) and badges:
            for b in badges[:5]:
                bobj = {"label": b} if isinstance(b, str) else dict(b)
                lbl = str(bobj.get("label", "")).strip()
                if not lbl:
                    continue
                pw = _diag_tw(lbl, MIN_FONT) + 18.0
                badge_specs.append((lbl, pw, self.tone(bobj, "blue")))
                badge_total_w += pw + 8.0
        title_avail = max(300.0, self.content_width - (badge_total_w + 14.0 if badge_specs else 0.0))
        title_rows = _wrap(self.spec["title"], title_avail, 22.0)
        sub = self.spec.get("subtitle", "")
        sub_rows = _wrap(sub, title_avail, BODY_FONT) if sub else []

        y_title = m + 20.0
        end = self.group("header", {"title": self.spec["title"], "subtitle": sub},
                         (m, m, self.content_width, 48.0), "header")
        for i, row in enumerate(title_rows):
            self.text(m, y_title + i * 28.0, row, 22.0, self.surf["ink"], 700)
        y_sub = y_title + len(title_rows) * 28.0 - 4.0
        for i, row in enumerate(sub_rows):
            self.text(m, y_sub + i * 18.0, row, BODY_FONT, self.surf["muted"], 400)

        if badge_specs:
            bx = LW - m
            by = m + 2.0
            for lbl, pw, acc in reversed(badge_specs):
                bx -= pw
                self.rect(bx, by, pw, 24.0, acc["tint"], acc["border"], 12.0, sw=1.0)
                self.text(bx + pw / 2.0, by + 16.0, lbl, MIN_FONT, acc["text"], 600, anchor="middle")
                bx -= 8.0
        end()
        header_bottom = max(y_sub + (len(sub_rows) * 18.0 - 5.0 if sub_rows else 0.0), m + 34.0) + 10.0
        self.line(m, header_bottom, LW - m, header_bottom, self.surf["border"], 1.0)
        return header_bottom + 14.0

    def group(self, key, content, geometry, kind="group", members=None, interactive=True):
        key = str(key)
        _check(key not in self._seen_ids, f"Duplicate scene ID: {key}")
        self._seen_ids.add(key)
        geom_px = [round(float(v) * self.k, 2) for v in geometry]
        obj = {
            "id": key,
            "kind": kind,
            "geometry": geom_px,
            "content": deepcopy(content),
            "membership": {
                "state": "explicit" if members is not None else "unknown",
                "members": list(members) if members is not None else None,
            },
        }
        if not interactive:
            obj["interactive"] = False
        self.scene_graph["objects"].append(obj)
        label = content.get("title", content.get("label", key))
        dk = html.escape(str(kind), quote=True)
        self.parts.append(
            f'<g data-kind="{dk}" data-id="{html.escape(key, quote=True)}" '
            f'data-node-id="{html.escape(key, quote=True)}" '
            f'data-node-label="{html.escape(str(label), quote=True)}">'
        )
        return lambda: self.parts.append("</g>")

    def register_box(self, key, x, y, w, h):
        self.boxes[str(key)] = (self._s(x), self._s(y), self._s(w), self._s(h))

    def rect(self, x, y, w, h, fill, stroke="none", rx=7.0, sw=1.0, dash=None,
             fill_opacity=1.0, stroke_opacity=1.0, preserve_stroke=True):
        px, py, pw, ph = self._s(x), self._s(y), self._s(w), self._s(h)
        prx = max(0.0, math.floor(min(self._s(rx), pw / 2.0, ph / 2.0) * 10.0) / 10.0)
        psw = self._s(sw)
        attrs = [
            f'x="{px:.1f}"', f'y="{py:.1f}"', f'width="{max(0.0, pw):.1f}"', f'height="{max(0.0, ph):.1f}"',
            f'rx="{prx:.1f}"', f'fill="{html.escape(str(fill), quote=True)}"',
        ]
        if fill_opacity < 0.999:
            attrs.append(f'fill-opacity="{fill_opacity:.2f}"')
        if stroke and stroke != "none":
            attrs.append(f'stroke="{html.escape(str(stroke), quote=True)}"')
            attrs.append(f'stroke-width="{psw:.2f}"')
            if stroke_opacity < 0.999:
                attrs.append(f'stroke-opacity="{stroke_opacity:.2f}"')
            if dash:
                attrs.append(f'stroke-dasharray="{html.escape(str(dash), quote=True)}"')
        else:
            attrs.append('stroke="none"')
        if preserve_stroke:
            attrs.append('data-preserve-stroke="1"')
        self.parts.append("<rect " + " ".join(attrs) + "/>")

    def line(self, x1, y1, x2, y2, stroke, sw=1.0, dash=None):
        self.polyline([(x1, y1), (x2, y2)], stroke=stroke, width=sw, dash=dash)

    def circle(self, cx, cy, r, fill, stroke="none", sw=1.0, dash=None, fill_opacity=1.0):
        attrs = [
            f'cx="{self._s(cx):.1f}"', f'cy="{self._s(cy):.1f}"', f'r="{max(0.0, self._s(r)):.1f}"',
            f'fill="{html.escape(str(fill), quote=True)}"',
        ]
        if fill_opacity < 0.999:
            attrs.append(f'fill-opacity="{fill_opacity:.2f}"')
        if stroke and stroke != "none":
            attrs.append(f'stroke="{html.escape(str(stroke), quote=True)}"')
            attrs.append(f'stroke-width="{self._s(sw):.2f}"')
            if dash:
                attrs.append(f'stroke-dasharray="{html.escape(str(dash), quote=True)}"')
        else:
            attrs.append('stroke="none"')
        self.parts.append("<circle " + " ".join(attrs) + "/>")

    def raw_path(self, d, stroke="none", width=1.4, arrow=False, dash=None, fill="none",
                 fill_opacity=1.0, relation=None, non_edge=False, data_points=None):
        psw = self._s(width)
        attrs = [f'd="{d}"', f'fill="{html.escape(str(fill), quote=True)}"']
        if non_edge or relation is None:
            attrs.append('data-non-edge="1"')
        if data_points:
            attrs.append(f'data-points="{data_points}"')
        if fill != "none" and fill_opacity < 0.999:
            attrs.append(f'fill-opacity="{fill_opacity:.2f}"')
        if stroke and stroke != "none":
            attrs.extend([
                f'stroke="{html.escape(str(stroke), quote=True)}"',
                f'stroke-width="{psw:.2f}"',
                'stroke-linecap="round"',
                'stroke-linejoin="round"',
            ])
        else:
            attrs.append('stroke="none"')
        if dash:
            attrs.append(f'stroke-dasharray="{html.escape(str(dash), quote=True)}"')
        if arrow and stroke and stroke != "none":
            mid = self.marker(stroke)
            attrs.append(f'marker-end="url(#{mid})"')
        if relation is not None:
            r = dict(relation)
            r.setdefault("id", f"relation-{len(self.scene_graph['edges'])}")
            r.setdefault("label", "")
            r.setdefault("directed", bool(arrow))
            r["path"] = d
            self.scene_graph["edges"].append(r)
            for k, v in {
                "from": r["from"], "to": r["to"], "key": r["id"],
                "label": r.get("label") or "",
                "directed": "true" if r["directed"] else "false",
            }.items():
                attrs.append(f'data-edge-{k}="{html.escape(str(v), quote=True)}"')
        self.parts.append("<path " + " ".join(attrs) + "/>")

    def polyline(self, pts, stroke="none", width=1.4, rounded=False, radius=8.0,
                 arrow=False, dash=None, fill="none", fill_opacity=1.0, relation=None, close=False):
        spts = [(self._s(x), self._s(y)) for x, y in pts]
        if rounded and len(spts) >= 3:
            d = _ortho_rounded_path(spts, r=self._s(radius))
        else:
            d = f"M{spts[0][0]:.1f} {spts[0][1]:.1f} " + " ".join(f"L{x:.1f} {y:.1f}" for x, y in spts[1:])
        if close:
            d += " Z"
        dp = " ".join(f"{x:.1f},{y:.1f}" for x, y in spts) if not close and len(spts) >= 2 else None
        self.raw_path(d, stroke=stroke, width=width, arrow=arrow, dash=dash,
                      fill=fill, fill_opacity=fill_opacity, relation=relation, data_points=dp)

    def cubic(self, p0, c0, c1, p1, stroke="none", width=1.4, arrow=False, dash=None, relation=None):
        sp = [tuple(self._s(v) for v in pt) for pt in (p0, c0, c1, p1)]
        d = (f"M{sp[0][0]:.1f} {sp[0][1]:.1f} "
             f"C{sp[1][0]:.1f} {sp[1][1]:.1f} {sp[2][0]:.1f} {sp[2][1]:.1f} {sp[3][0]:.1f} {sp[3][1]:.1f}")
        self.raw_path(d, stroke=stroke, width=width, arrow=arrow, dash=dash, relation=relation)

    def quad(self, p0, ctrl, p1, stroke="none", width=1.4, arrow=False, dash=None, relation=None):
        sp = [tuple(self._s(v) for v in pt) for pt in (p0, ctrl, p1)]
        d = f"M{sp[0][0]:.1f} {sp[0][1]:.1f} Q{sp[1][0]:.1f} {sp[1][1]:.1f} {sp[2][0]:.1f} {sp[2][1]:.1f}"
        self.raw_path(d, stroke=stroke, width=width, arrow=arrow, dash=dash, relation=relation)

    def text(self, x, y, value, size=BODY_FONT, color=None, weight=400, anchor="start",
             family=None, code=False, check_overlap=True):
        if color is None:
            color = self.surf["ink"]
        size = max(MIN_FONT, float(size))
        s = str(value)
        px, py, psize = self._s(x), self._s(y), self._s(size)
        fam = f' font-family="{html.escape(family or (self.fonts_cfg["mono"] if code else self.fonts_cfg["sans"]), quote=True)}"'
        extra = ' data-code="true"' if code else ""
        self.parts.append(
            f'<text x="{px:.1f}" y="{py:.1f}" font-size="{psize:.1f}" fill="{html.escape(str(color), quote=True)}" '
            f'font-weight="{weight}" text-anchor="{anchor}"{fam}{extra}>{html.escape(s)}</text>'
        )
        w = (_mono_units(s) * psize if code else _diag_tw(s, psize))
        item = {"text": s, "x": px, "y": py, "size": psize,
                "width": float(w), "anchor": anchor, "check_overlap": bool(check_overlap)}
        self.labels.append(item)
        return item

    def wrapped_text(self, x, y, value, width, size=BODY_FONT, color=None, weight=400,
                     anchor="start", line_h=None, check_overlap=True):
        size = max(MIN_FONT, float(size))
        lh = line_h if line_h is not None else size * 1.42
        rows = _wrap(value, width, size)
        for i, row in enumerate(rows):
            self.text(x, y + i * lh, row, size, color, weight, anchor, check_overlap=check_overlap)
        return len(rows) * lh

    def finish(self, bottom):
        note = self.spec.get("note", "")
        y = float(bottom) + 16.0
        if note:
            self.line(self.margin, y, LW - self.margin, y, self.surf["divider"], 0.8)
            y += 18.0
            nh = self.wrapped_text(self.margin, y, note, self.content_width, MIN_FONT,
                                   self.surf["muted"], line_h=16.0, check_overlap=False)
            y += nh - 4.0
        if self.spec.get("sample"):
            self.text(self.margin, y + 14.0, "合成示例", MIN_FONT, self.surf["muted"], check_overlap=False)
            y += 18.0
        self.height = math.ceil(self._s(y + self.margin * 0.75))
        return self

    def save(self, path):
        path = Path(path)
        pm = self._s(self.margin)
        ptop = self._s(self.content_top)
        for key, (x, by, w, h) in self.boxes.items():
            _check(x >= pm - 6.0 and x + w <= self.width - pm + 6.0
                   and by >= ptop - 4.0 and by + h <= self.height - 8.0,
                   f"Box outside content area: {key}")
            for other, (ox, oy, ow, oh) in self.boxes.items():
                if key < other:
                    _check(not _box_overlap((x, by, w, h), (ox, oy, ow, oh), eps=0.5),
                           f"Overlapping boxes: {key}, {other}")
        for item in self.labels:
            left = _label_left(item)
            _check(left >= 4.0 and left + item["width"] <= self.width - 4.0,
                   f"Label out of bounds: {item['text']}")
            _check(0.0 < item["y"] <= self.height - 4.0,
                   f"Vertical overflow: {item['text']}")
        checked = [it for it in self.labels if it.get("check_overlap", True)]
        for i, a in enumerate(checked):
            ax = _label_left(a)
            for b in checked[i + 1:]:
                bx = _label_left(b)
                h_ov = min(ax + a["width"], bx + b["width"]) > max(ax, bx) + 1.0
                v_ov = min(a["y"] + 1.0, b["y"] + 1.0) > max(a["y"] - a["size"] * 0.82, b["y"] - b["size"] * 0.82) + 1.0
                _check(not (h_ov and v_ov), f"Text labels overlap: {a['text']} / {b['text']}")
        defs = "".join(
            f'<marker id="{mid}" viewBox="0 0 10 10" refX="8" refY="5" '
            f'markerWidth="6" markerHeight="6" orient="auto">'
            f'<path d="M1 1 L8 5 L1 9" fill="none" stroke="{col}" stroke-width="1.6" stroke-linecap="round"/></marker>'
            for mid, col in sorted(self.markers.items())
        )
        preset_attr = f' data-preset="{html.escape(self.preset, quote=True)}"' if self.preset != "document-roles" else ""
        font_attr = html.escape(self.fonts_cfg["sans"], quote=True)
        note = html.escape(self.spec.get("note", ""))
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(self.width)}" height="{int(self.height)}" '
            f'viewBox="0 0 {int(self.width)} {int(self.height)}" role="img"{preset_attr}>'
            f'<title>{html.escape(self.spec["title"])}</title><desc>{note}</desc>'
            f'<defs>{defs}</defs>'
            f'<rect width="{int(self.width)}" height="100%" fill="{self.surf["canvas"]}" stroke="none" data-preserve-stroke="1"/>'
            f'<g font-family="{font_attr}">' + "".join(self.parts) + '</g></svg>\n'
        )
        path.write_text(svg, encoding="utf-8")
        return {
            "boxes": self.boxes,
            "labels": self.labels,
            "scene_objects": self.scene_objects,
            "scene_graph": self.scene_graph,
            "width": self.width,
            "height": self.height,
        }


# ===========================================================================
# 1. architecture-blueprint: high-density auto-layout blueprint with rich cards
# ===========================================================================
def _norm_row(r):
    if isinstance(r, dict):
        return (str(r.get("label", "")), str(r.get("tag", "")) if r.get("tag") is not None else None,
                r.get("style", "soft"), r.get("tone"))
    if isinstance(r, (list, tuple)):
        label = str(r[0]) if len(r) > 0 else ""
        tag = str(r[1]) if len(r) > 1 and r[1] not in (None, "") else None
        style = r[2] if len(r) > 2 else "soft"
        tone = r[3] if len(r) > 3 else None
        return (label, tag, style, tone)
    return (str(r), None, "soft", None)


def _norm_chip(ch):
    if isinstance(ch, dict):
        return (str(ch.get("label", "")), ch.get("style", "soft"), ch.get("tone"))
    if isinstance(ch, (list, tuple)):
        return (str(ch[0]), ch[1] if len(ch) > 1 else "soft", ch[2] if len(ch) > 2 else None)
    return (str(ch), "soft", None)


def _measure_blueprint_card(item, w):
    pad = 10.0
    gap = 6.0
    inner = w - 2.0 * pad
    title = str(item.get("label") or item.get("title") or item["id"])
    badge = item.get("badge")
    title_inset = pad + (22.0 if badge is not None else 0.0)
    title_rows = _wrap(title, max(40.0, w - title_inset - pad), 13.5)
    h = pad + len(title_rows) * 18.5
    code = item.get("code")
    if code:
        h += gap + 20.0
    desc = item.get("desc") or item.get("detail") or ""
    desc_rows = _wrap(desc, inner, BODY_FONT) if desc else []
    if desc_rows:
        h += gap + len(desc_rows) * 17.5
    chips = [_norm_chip(ch) for ch in item.get("chips", [])]
    chip_rows, cur, cx = [], [], 0.0
    for lbl, st, tn in chips:
        cw = _diag_tw(lbl, MIN_FONT) + 14.0
        if cur and cx + 5.0 + cw > inner:
            chip_rows.append(cur)
            cur, cx = [], 0.0
        cur.append((lbl, min(cw, inner), st, tn))
        cx += (5.0 if cur[:-1] else 0.0) + cw
    if cur:
        chip_rows.append(cur)
    if chip_rows:
        h += gap + len(chip_rows) * 23.0 - 4.0
    rows = [_norm_row(r) for r in item.get("rows", [])]
    row_layouts = []
    for rlbl, rtag, rstyle, rtone in rows:
        tw = (min(inner - 24.0, _diag_tw(rtag, TAG_FONT) + 12.0)) if rtag else 0.0
        stacked = bool(rtag) and (inner - tw - 16.0 < _diag_tw(rlbl, BODY_FONT) * 0.55 or inner - tw < 58.0)
        lw = max(40.0, (inner - 10.0) if stacked else (inner - tw - 16.0))
        lwrap = _wrap(rlbl, lw, BODY_FONT)
        rh = max(22.0, len(lwrap) * 16.8 + (22.0 if stacked else 5.0))
        row_layouts.append((lwrap, rtag, tw, rstyle, rtone, rh, stacked))
        h += 4.0 + rh
    h += pad
    return {
        "title_rows": title_rows, "badge": badge, "code": code,
        "desc_rows": desc_rows, "chip_rows": chip_rows, "row_layouts": row_layouts,
        "height": math.ceil(h),
    }


def _draw_blueprint_card(c, item, x, y, w, h, m, default_tone=None):
    nid = str(item["id"])
    has_explicit = any(item.get(k) not in (None, "") for k in ("tone", "status", "role", "emphasis"))
    acc = c.tone(item if has_explicit else (default_tone or "slate"), fallback="slate")
    focused = item.get("emphasis") is True or bool(item.get("status"))
    dashed = bool(item.get("dashed") or item.get("planned"))
    fill = acc["tint"] if has_explicit or focused else c.surf["card"]
    border = acc["solid"] if focused else acc["border"]
    sw = 1.6 if focused else 1.1
    pad, gap = 10.0, 6.0

    end = c.group(nid, item, (x, y, w, h), "card")
    c.rect(x, y, w, h, fill, border, 7.0, sw=sw, dash="6 4" if dashed else None)
    if focused:
        c.rect(x + 1.0, y + 5.0, 3.0, max(4.0, h - 10.0), acc["solid"], "none", 1.5)

    cy = y + pad
    tx = x + pad
    if m["badge"] is not None:
        br = 8.5
        c.circle(tx + br, cy + 8.5, br, acc["solid"])
        c.text(tx + br, cy + 12.2, str(m["badge"]), MIN_FONT, c.surf["card"], 700, anchor="middle")
        tx += br * 2.0 + 5.0
    for i, row in enumerate(m["title_rows"]):
        c.text(tx, cy + 13.5 + i * 18.5, row, 13.5, c.surf["ink"], 700 if focused else 600)
    cy += len(m["title_rows"]) * 18.5

    if m["code"]:
        cy += gap
        cw = min(w - 2 * pad, _mono_units(m["code"]) * TAG_FONT + 14.0)
        c.rect(x + pad, cy, cw, 21.0, c.surf["track"], c.surf["border"], 4.0, sw=0.8)
        c.text(x + pad + 6.0, cy + 14.5, str(m["code"]), TAG_FONT, c.surf["text"], 500, code=True)
        cy += 21.0

    if m["desc_rows"]:
        cy += gap
        for i, row in enumerate(m["desc_rows"]):
            c.text(x + pad, cy + 12.8 + i * 17.5, row, BODY_FONT, c.surf["muted"], 400)
        cy += len(m["desc_rows"]) * 17.5

    if m["chip_rows"]:
        cy += gap
        for crow in m["chip_rows"]:
            cx = x + pad
            for lbl, cw, st, tn in crow:
                ct = c.tone(tn, fallback="slate") if tn else acc
                if st == "filled":
                    cf, cs, cc = ct["solid"], "none", c.surf["card"]
                elif st == "outline":
                    cf, cs, cc = c.surf["card"], ct["border"], ct["text"]
                else:
                    cf, cs, cc = ct["tint"], ct["border"], ct["text"]
                c.rect(cx, cy, cw, 19.0, cf, cs, 9.5, sw=0.8)
                c.text(cx + cw / 2.0, cy + 13.3, lbl, MIN_FONT, cc, 500, anchor="middle")
                cx += cw + 5.0
            cy += 23.0

    if m["row_layouts"]:
        if not m["chip_rows"]:
            cy += gap * 0.5
        for lwrap, rtag, tw, rstyle, rtone, rh, stacked in m["row_layouts"]:
            cy += 2.0
            c.rect(x + pad, cy, w - 2 * pad, rh, c.surf["track"], "none", 4.0, sw=0.0)
            for li, lline in enumerate(lwrap):
                c.text(x + pad + 6.0, cy + 15.0 + li * 16.8, lline, BODY_FONT, c.surf["text"], 500)
            if rtag:
                rt = c.tone(rtone, fallback="slate") if rtone else c.tone("slate")
                if rstyle == "filled":
                    rf, rs, rc = rt["solid"], "none", c.surf["card"]
                else:
                    rf, rs, rc = c.surf["card"], rt["border"], rt["text"]
                if stacked:
                    tx_r = x + pad + 6.0
                    ty_r = cy + len(lwrap) * 16.8 + 3.0
                    c.rect(tx_r, ty_r, tw, 17.0, rf, rs, 8.5, sw=0.8)
                    c.text(tx_r + tw / 2.0, ty_r + 12.8, rtag, TAG_FONT, rc, 600, anchor="middle")
                else:
                    c.rect(x + w - pad - 4.0 - tw, cy + 2.5, tw, 17.5, rf, rs, 8.5, sw=0.8)
                    c.text(x + w - pad - 4.0 - tw / 2.0, cy + 15.0, rtag, TAG_FONT, rc, 600, anchor="middle")
            cy += rh + 2.0

    end()
    c.register_box(nid, x, y, w, h)
    c.scene_objects[nid] = dict(item)


def architecture_blueprint(spec):
    """High-density auto-layout architecture blueprint supporting layers/groups or zones."""
    items = spec.get("components") or spec.get("nodes") or []
    _check(isinstance(items, list) and 1 <= len(items) <= 40,
           "architecture-blueprint supports 1–40 components/nodes")
    by_id = {}
    for it in items:
        _check(isinstance(it, dict) and isinstance(it.get("id"), str) and it["id"],
               "Each component requires a string id")
        _check(it["id"] not in by_id, f"Duplicate component id: {it['id']}")
        by_id[it["id"]] = it
    node_ids = set(by_id)

    raw_layers = spec.get("layers")
    raw_zones = spec.get("zones")
    raw_groups = spec.get("groups") or []
    rels = spec.get("connections") or spec.get("relations") or spec.get("edges") or []
    shared = spec.get("shared_coverage") or spec.get("shared_bars") or spec.get("shared") or []
    notes = spec.get("notes") or []

    preset = spec.get("preset", "document-roles")
    opts = _layout_opts(spec)
    canvas_w = int(opts.get("width", spec.get("canvas_width", 1280)))
    orientation = opts.get("orientation", spec.get("orientation", "vertical"))

    c = InsightCanvas(spec, width=canvas_w, preset=preset)

    def safe_container_id(prefix, raw_id, taken):
        sid = str(raw_id)
        if sid in taken:
            sid = f"{prefix}:{sid}"
        while sid in taken:
            sid = f"{prefix}:{sid}"
        taken.add(sid)
        return sid

    taken_cids = set(node_ids)
    tiers = []
    placed_nodes = set()
    if raw_layers:
        layer_map = {str(ly["id"]): dict(ly) for ly in raw_layers}
        group_map = {}
        for gr in raw_groups:
            gid = str(gr["id"])
            glayer = gr.get("layer")
            if not glayer:
                ref_layers = {it.get("layer") for it in items if it.get("group") == gid and it.get("layer")}
                glayer = next(iter(ref_layers)) if len(ref_layers) == 1 else next(iter(layer_map))
            _check(glayer in layer_map, f"Group {gid} references unknown layer {glayer}")
            group_map[gid] = {**gr, "_scene_id": safe_container_id("group", gid, taken_cids), "layer": glayer}
        for ly in raw_layers:
            lid = str(ly["id"])
            ly_obj = {**ly, "_scene_id": safe_container_id("layer", lid, taken_cids)}
            lgroups = [g for g in group_map.values() if g["layer"] == lid]
            grouped_nodes = [it for it in items if it.get("layer") == lid]
            if not lgroups and grouped_nodes:
                lgroups = [{"id": f"grp-{lid}", "_scene_id": safe_container_id("group", f"grp-{lid}", taken_cids),
                            "label": ly.get("label", lid), "layer": lid, "_implicit": True}]
            if not lgroups:
                continue
            tier_groups = []
            for g in lgroups:
                gid = str(g["id"])
                gnodes = ([it for it in items if it.get("group") == gid]
                          if not g.get("_implicit") else grouped_nodes)
                placed_nodes.update(n["id"] for n in gnodes)
                tier_groups.append({"group": g, "nodes": gnodes})
            tiers.append({"layer": ly_obj, "groups": tier_groups})
    elif raw_zones and orientation == "horizontal":
        tier_groups = []
        for z in raw_zones:
            zid = str(z["id"])
            znodes = [it for it in items if (it.get("zone") or it.get("group")) == zid]
            placed_nodes.update(n["id"] for n in znodes)
            z_obj = {**z, "_scene_id": safe_container_id("zone", zid, taken_cids)}
            tier_groups.append({"group": z_obj, "nodes": znodes})
        tiers.append({"layer": None, "groups": tier_groups})
    elif raw_zones:
        for z in raw_zones:
            zid = str(z["id"])
            znodes = [it for it in items if (it.get("zone") or it.get("group")) == zid]
            placed_nodes.update(n["id"] for n in znodes)
            z_obj = {**z, "_scene_id": safe_container_id("zone", zid, taken_cids)}
            tiers.append({"layer": z_obj, "groups": [{
                "group": {**z_obj, "_scene_id": safe_container_id("group", f"grp-{zid}", taken_cids), "_implicit": True},
                "nodes": znodes,
            }]})
    else:
        placed_nodes.update(n["id"] for n in items)
        tiers.append({"layer": None, "groups": [{
            "group": {"id": "main", "_scene_id": safe_container_id("group", "main", taken_cids),
                      "label": "系统组件", "_implicit": True},
            "nodes": items,
        }]})

    unplaced = [it for it in items if it["id"] not in placed_nodes]
    if unplaced:
        tiers.append({"layer": None, "groups": [{
            "group": {"id": "other", "_scene_id": safe_container_id("group", "other", taken_cids),
                      "label": "其他组件", "_implicit": True},
            "nodes": unplaced,
        }]})

    for rel in rels:
        _check(rel.get("from") in by_id and rel.get("to") in by_id,
               f"Dangling relation: {rel.get('from')} -> {rel.get('to')}")

    m = c.margin
    gutter_x = 26.0
    card_gap = 14.0
    group_pad = 10.0
    group_head_h = 28.0
    tier_pad_x = 12.0
    tier_head_h = 28.0
    layer_channel = 36.0

    show_cond = bool(spec.get("show_conditions", False))

    def _rel_label(rel):
        lbl = str(rel.get("label") or "").strip()
        if show_cond and rel.get("condition") and rel["condition"] not in lbl:
            lbl = f"{lbl}（{rel['condition']}）" if lbl else str(rel["condition"])
        return lbl

    labeled_pairs = {}
    for rel in rels:
        lbl = _rel_label(rel)
        if lbl:
            key = frozenset((rel["from"], rel["to"]))
            labeled_pairs[key] = max(labeled_pairs.get(key, 0.0), _diag_tw(lbl, MIN_FONT) + 28.0)

    tier_cross_gap = gutter_x + 2.0 * group_pad

    card_geom = {}
    card_measure = {}
    group_layouts = []
    y_cursor = c.content_top

    for tier in tiers:
        layer = tier["layer"]
        groups = [g for g in tier["groups"] if g["nodes"]]
        if not groups:
            continue
        has_layer_chrome = layer is not None and not (len(groups) == 1 and groups[0]["group"].get("_implicit"))
        inner_tier_w = c.content_width - (2.0 * tier_pad_x if has_layer_chrome else 0.0)
        avail_groups_w = inner_tier_w - gutter_x * (len(groups) - 1)

        col_counts = []
        if len(groups) == 2:
            n0, n1 = len(groups[0]["nodes"]), len(groups[1]["nodes"])
            rich0 = any(nd.get("rows") or nd.get("chips") or nd.get("code") for nd in groups[0]["nodes"])
            rich1 = any(nd.get("rows") or nd.get("chips") or nd.get("code") for nd in groups[1]["nodes"])
            if rich0 and not rich1 and n0 <= 3:
                col_counts = [max(1, n0), 1]
            elif rich1 and not rich0 and n1 <= 3:
                col_counts = [1, max(1, n1)]
            else:
                col_counts = [max(1, min(3, nc) if n0 + n1 <= 4 else min(2, nc)) for nc in (n0, n1)]
        else:
            for gr in groups:
                nc = len(gr["nodes"])
                if len(groups) >= 3:
                    cols = 1 if nc <= 2 else 2
                else:
                    cols = min(4, nc) if nc <= 4 else (3 if nc <= 6 else 4)
                col_counts.append(max(1, cols))

        total_cols = sum(col_counts)
        group_widths = [max(180.0, avail_groups_w * cc / total_cols) for cc in col_counts]
        gw_sum = sum(group_widths)
        group_widths = [w * avail_groups_w / gw_sum for w in group_widths]

        tier_body_top = y_cursor + (tier_head_h + 4.0 if has_layer_chrome else 0.0)
        gx = m + (tier_pad_x if has_layer_chrome else 0.0)
        max_group_h = 0.0
        prepared_groups = []
        node_group_idx = {n["id"]: gi for gi, g_info in enumerate(groups) for n in g_info["nodes"]}
        cross_group_tight = len(groups) >= 2 and any(
            len(pair) == 2 and all(nid in node_group_idx for nid in pair)
            and len({node_group_idx[nid] for nid in pair}) == 2 and need_w > tier_cross_gap
            for pair, need_w in labeled_pairs.items()
        )
        for g_info, gw, cols in zip(groups, group_widths, col_counts):
            gr = g_info["group"]
            gnodes = g_info["nodes"]
            cw = (gw - 2.0 * group_pad - card_gap * (cols - 1)) / cols
            rows = [gnodes[i:i + cols] for i in range(0, len(gnodes), cols)]
            row_heights = []
            row_tight_counts = []
            for row in rows:
                rh = 0.0
                for node in row:
                    meas = _measure_blueprint_card(node, cw)
                    card_measure[node["id"]] = meas
                    rh = max(rh, meas["height"])
                row_heights.append(rh)
                rids = {nd["id"] for nd in row}
                t_cnt = sum(1 for pair, need_w in labeled_pairs.items() if len(pair) == 2 and pair <= rids and need_w > card_gap)
                row_tight_counts.append(t_cnt)
            show_ghead = not gr.get("_implicit") or layer is not None
            gy0 = tier_body_top
            cy_card = gy0 + (group_head_h + 6.0 if show_ghead else group_pad)
            extra_bot = 0.0
            for ri, (row, rh, t_cnt) in enumerate(zip(rows, row_heights, row_tight_counts)):
                if t_cnt > 0 or (ri == 0 and cross_group_tight):
                    cy_card += 16.0
                row_w = len(row) * cw + (len(row) - 1) * card_gap
                rx = gx + group_pad + ((gw - 2.0 * group_pad - row_w) / 2.0 if len(groups) == 1 and len(row) < cols else 0.0)
                for ci, node in enumerate(row):
                    nx = rx + ci * (cw + card_gap)
                    card_geom[node["id"]] = (nx, cy_card, cw, rh)
                cy_card += rh + card_gap
                if ri == len(rows) - 1 and t_cnt >= 2:
                    extra_bot = 8.0
            cov_items = []
            node_set = {n["id"] for n in gnodes}
            for band in shared:
                mem = set(band.get("members") or [])
                if mem and mem <= node_set:
                    cov_items.append(band)
            cov_layouts = []
            for band in cov_items:
                covered = [card_geom[mid] for mid in band["members"]]
                bx0 = min(b[0] for b in covered)
                bx1 = max(b[0] + b[2] for b in covered)
                bw = bx1 - bx0
                det_rows = _wrap(band.get("detail", ""), max(80.0, bw - 22.0), MIN_FONT) if band.get("detail") else []
                bh = 24.0 + len(det_rows) * 15.5
                cov_layouts.append((band, bx0, cy_card - 2.0, bw, bh, det_rows))
                cy_card += bh + 6.0
            gh = ((cy_card - card_gap + group_pad - gy0) if not cov_items else (cy_card + group_pad * 0.6 - gy0)) + extra_bot
            max_group_h = max(max_group_h, gh)
            prepared_groups.append({
                "group": gr, "nodes": gnodes, "x": gx, "y": gy0, "w": gw, "h": gh,
                "show_head": show_ghead, "coverages": cov_layouts,
            })
            gx += gw + gutter_x

        for pg in prepared_groups:
            pg["h"] = max_group_h
        tier_h = (tier_body_top - y_cursor) + max_group_h + (10.0 if has_layer_chrome else 0.0)
        group_layouts.append({"layer": layer, "y": y_cursor, "h": tier_h,
                              "has_layer_chrome": has_layer_chrome, "groups": prepared_groups})
        y_cursor += tier_h + layer_channel

    content_bottom = y_cursor - layer_channel
    tone_seq = c.pal["sequence"]
    header_avoid_boxes = []

    for t_idx, tl in enumerate(group_layouts):
        layer = tl["layer"]
        ltone = (layer if layer and any(layer.get(k) for k in ("tone", "role", "status"))
                 else (tone_seq[t_idx % len(tone_seq)] if len(group_layouts) > 1 else "slate"))
        lacc = c.tone(ltone, fallback="slate")
        if tl["has_layer_chrome"] and layer is not None:
            lmembers = [n["id"] for pg in tl["groups"] for n in pg["nodes"]]
            end = c.group(layer.get("_scene_id", layer["id"]), layer, (m, tl["y"], c.content_width, tl["h"]), "group", lmembers)
            c.rect(m, tl["y"], c.content_width, tl["h"], lacc["tint"], lacc["border"], 9.0, sw=1.0, fill_opacity=0.45)
            lbl_l = str(layer.get("label", layer["id"]))
            c.text(m + 12.0, tl["y"] + 21.0, lbl_l, 13.0, lacc["text"], 700)
            header_avoid_boxes.append((m + 8.0, tl["y"] + 5.0, _diag_tw(lbl_l, 13.0) + 10.0, 22.0))
            end()

        for pg in tl["groups"]:
            gr = pg["group"]
            if not gr.get("_implicit") or not tl["has_layer_chrome"]:
                gacc = c.tone(gr if any(gr.get(k) for k in ("tone", "role", "status")) else ltone, fallback="slate")
                gfill = c.surf["panel"] if not tl["has_layer_chrome"] else c.surf["card"]
                g_op = 0.75 if tl["has_layer_chrome"] else 0.55
                gmembers = [n["id"] for n in pg["nodes"]]
                end = c.group(gr.get("_scene_id", gr["id"]), gr, (pg["x"], pg["y"], pg["w"], pg["h"]), "group", gmembers)
                c.rect(pg["x"], pg["y"], pg["w"], pg["h"], gfill, gacc["border"], 7.0, sw=1.0, fill_opacity=g_op)
                if pg["show_head"]:
                    lbl_g = str(gr.get("label", gr["id"]))
                    c.text(pg["x"] + 10.0, pg["y"] + 21.0, lbl_g, BODY_FONT,
                           gacc["text"] if c.preset == "insight" else c.surf["muted"], 600)
                    header_avoid_boxes.append((pg["x"] + 6.0, pg["y"] + 5.0, _diag_tw(lbl_g, BODY_FONT) + 10.0, 20.0))
                end()

            for band, bx, by, bw, bh, det_rows in pg["coverages"]:
                bacc = c.tone(band if any(band.get(k) for k in ("tone", "role", "status")) else "slate")
                bsid = safe_container_id("cov", band["id"], taken_cids)
                end = c.group(bsid, band, (bx, by, bw, bh), "coverage", list(band["members"]))
                c.rect(bx, by, bw, bh, bacc["tint"], bacc["border"], 6.0, sw=0.9, dash="4 3")
                c.rect(bx + 1.0, by + 4.0, 3.0, max(4.0, bh - 8.0), bacc["border"], "none", 1.5)
                c.text(bx + 10.0, by + 16.5, str(band["label"]), MIN_FONT, bacc["text"], 600)
                for di, drow in enumerate(det_rows):
                    c.text(bx + 10.0, by + 32.0 + di * 15.0, drow, MIN_FONT, c.surf["muted"], 400)
                header_avoid_boxes.append((bx, by, bw, bh))
                end()

    for tl in group_layouts:
        for pg in tl["groups"]:
            for node in pg["nodes"]:
                nx, ny, nw, nh = card_geom[node["id"]]
                _draw_blueprint_card(c, node, nx, ny, nw, nh, card_measure[node["id"]])

    all_blockers = list(card_geom.items())
    inter_tier_ys = [
        group_layouts[i]["y"] + group_layouts[i]["h"] + layer_channel * 0.5
        for i in range(len(group_layouts) - 1)
    ]
    xs_candidates = [m - 12.0, LW - m + 12.0]
    for tl in group_layouts:
        for gi in range(len(tl["groups"]) - 1):
            right_edge = tl["groups"][gi]["x"] + tl["groups"][gi]["w"]
            left_next = tl["groups"][gi + 1]["x"]
            xs_candidates.append((right_edge + left_next) / 2.0)

    port_usage = {}
    rel_ports = []
    for rel in rels:
        a, b = card_geom[rel["from"]], card_geom[rel["to"]]
        acx, acy = a[0] + a[2] / 2.0, a[1] + a[3] / 2.0
        bcx, bcy = b[0] + b[2] / 2.0, b[1] + b[3] / 2.0
        same_row = abs(acy - bcy) < min(a[3], b[3]) * 0.45
        if same_row:
            a_side, b_side = ("right", "left") if bcx > acx else ("left", "right")
        elif bcy > acy:
            a_side, b_side = "bottom", "top"
        else:
            a_side, b_side = "top", "bottom"
        rel_ports.append((a_side, b_side))
        port_usage[(rel["from"], a_side)] = port_usage.get((rel["from"], a_side), 0) + 1
        port_usage[(rel["to"], b_side)] = port_usage.get((rel["to"], b_side), 0) + 1

    port_cursor = {}

    def next_port(nid, side):
        cnt = port_usage.get((nid, side), 1)
        idx = port_cursor.get((nid, side), 0)
        port_cursor[(nid, side)] = idx + 1
        t = 0.5 if cnt == 1 else 0.25 + 0.5 * idx / (cnt - 1)
        nx, ny, nw, nh = card_geom[nid]
        if side == "top":
            return (nx + nw * t, ny)
        if side == "bottom":
            return (nx + nw * t, ny + nh)
        if side == "left":
            return (nx, ny + nh * t)
        return (nx + nw, ny + nh * t)

    placed_label_rects = list(card_geom.values()) + header_avoid_boxes
    placed_edge_routes = []

    def _hv_segs(pts):
        out = []
        for p, q in zip(pts, pts[1:]):
            if abs(p[0] - q[0]) < 0.05 or abs(p[1] - q[1]) < 0.05:
                out.append((p, q))
            else:
                mid = (q[0], p[1])
                out.extend([(p, mid), (mid, q)])
        return out

    def _count_crossings(cand_pts):
        c_segs = _hv_segs(cand_pts)
        crosses = 0
        for prev_pts in placed_edge_routes:
            p_segs = _hv_segs(prev_pts)
            for p, q in c_segs:
                h1 = abs(p[1] - q[1]) < 0.05
                for r, s in p_segs:
                    h2 = abs(r[1] - s[1]) < 0.05
                    if h1 == h2:
                        continue
                    (hx0, hy), (hx1, _) = (p, q) if h1 else (r, s)
                    (vx, vy0), (_, vy1) = (r, s) if h1 else (p, q)
                    if min(hx0, hx1) + 0.5 < vx < max(hx0, hx1) - 0.5 and min(vy0, vy1) + 0.5 < hy < max(vy0, vy1) - 0.5:
                        if not (any(abs(pt[0] - vx) < 0.5 and abs(pt[1] - hy) < 0.5 for pt in cand_pts)
                                and any(abs(pt[0] - vx) < 0.5 and abs(pt[1] - hy) < 0.5 for pt in prev_pts)):
                            crosses += 1
        return crosses

    def _path_len(pts):
        return sum(abs(q[0] - p[0]) + abs(q[1] - p[1]) for p, q in zip(pts, pts[1:]))

    for idx, (rel, (a_side, b_side)) in enumerate(zip(rels, rel_ports)):
        p0 = next_port(rel["from"], a_side)
        p1 = next_port(rel["to"], b_side)
        excl = {rel["from"], rel["to"]}

        lbl = _rel_label(rel)
        horiz_gap = abs(p1[0] - p0[0])
        need_w = (_diag_tw(lbl, MIN_FONT) + 26.0) if lbl else 0.0

        candidates = []
        if a_side in ("left", "right") and b_side in ("left", "right"):
            if not lbl or horiz_gap >= need_w:
                if abs(p0[1] - p1[1]) < 4.0:
                    candidates.append([p0, (p1[0], p0[1])])
                else:
                    mx = (p0[0] + p1[0]) / 2.0
                    candidates.append([p0, (mx, p0[1]), (mx, p1[1]), p1])
            fa, fb = card_geom[rel["from"]], card_geom[rel["to"]]
            if fb[0] >= fa[0]:
                ta_ratio, tb_ratio = 0.64, 0.36
            else:
                ta_ratio, tb_ratio = 0.36, 0.64
            top_a = fa[0] + fa[2] * ta_ratio, fa[1]
            top_b = fb[0] + fb[2] * tb_ratio, fb[1]
            bot_a = fa[0] + fa[2] * ta_ratio, fa[1] + fa[3]
            bot_b = fb[0] + fb[2] * tb_ratio, fb[1] + fb[3]
            for off in (13.0, 20.0, 27.0):
                above_y = min(fa[1], fb[1]) - off
                below_y = max(fa[1] + fa[3], fb[1] + fb[3]) + off
                candidates.append([top_a, (top_a[0], above_y), (top_b[0], above_y), top_b])
                candidates.append([bot_a, (bot_a[0], below_y), (bot_b[0], below_y), bot_b])
        else:
            mid_y = (p0[1] + p1[1]) / 2.0
            best_ys = sorted(inter_tier_ys, key=lambda yy: abs(yy - mid_y)) + [mid_y]
            for ty in best_ys:
                for stagger in (0.0, -7.0, 7.0, -14.0, 14.0):
                    candidates.append([p0, (p0[0], ty + stagger), (p1[0], ty + stagger), p1])
            for vx in sorted(xs_candidates, key=lambda xval: abs(xval - (p0[0] + p1[0]) / 2.0)):
                exit_y = p0[1] + (12.0 if a_side == "bottom" else -12.0)
                enter_y = p1[1] + (-12.0 if b_side == "top" else 12.0)
                candidates.append([p0, (p0[0], exit_y), (vx, exit_y), (vx, enter_y), (p1[0], enter_y), p1])

        clear_cands = [cand for cand in candidates if _route_clear(cand, all_blockers, excl)]
        pool = clear_cands or candidates
        chosen = min(pool, key=lambda cand: (_count_crossings(cand), _path_len(cand)))
        placed_edge_routes.append(chosen)
        is_planned = rel.get("style") in ("dash", "dashed", "planned") or rel.get("kind") == "planned"
        is_emph = rel.get("emphasis") is True or rel.get("style") == "accent"
        ecolor = c.tone("blue")["solid"] if is_emph else c.surf["subtle"] if not is_planned else c.tone("slate")["solid"]
        r_obj = {**rel, "id": rel.get("id", f"rel-{idx}")}
        c.polyline(chosen, stroke=ecolor, width=1.6 if is_emph else 1.25, rounded=True,
                   arrow=rel.get("directed", True), dash="6 4" if is_planned else None, relation=r_obj)

        lbl = _rel_label(rel)
        if lbl:
            lw = _diag_tw(lbl, MIN_FONT) + 12.0
            lh = 17.0
            segs = sorted(zip(chosen, chosen[1:]), key=lambda s: abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1]), reverse=True)
            placed = False
            for sp, sq in segs:
                cx_seg, cy_seg = (sp[0] + sq[0]) / 2.0, (sp[1] + sq[1]) / 2.0
                for dy, dx in ((d_y, d_x) for d_y in (0.0, -14.0, 14.0, -22.0, 22.0) for d_x in (0.0, -32.0, 32.0)):
                    rc = (cx_seg + dx - lw / 2.0, cy_seg + dy - lh * 0.65, lw, lh)
                    if (m <= rc[0] and rc[0] + lw <= LW - m
                            and not any(_box_overlap(rc, pb, eps=0.5) for pb in placed_label_rects)):
                        c.rect(rc[0], rc[1], lw, lh, c.surf["card"], c.surf["border"], 8.5, sw=0.7)
                        c.text(rc[0] + lw / 2.0, rc[1] + 12.5, lbl, MIN_FONT, c.surf["text"], 500, anchor="middle", check_overlap=False)
                        placed_label_rects.append(rc)
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                cx_seg, cy_seg = (segs[0][0][0] + segs[0][1][0]) / 2.0, (segs[0][0][1] + segs[0][1][1]) / 2.0
                c.rect(cx_seg - lw / 2.0, cy_seg - 9.0, lw, lh, c.surf["card"], c.surf["border"], 8.5, sw=0.7)
                c.text(cx_seg, cy_seg + 3.5, lbl, MIN_FONT, c.surf["text"], 500, anchor="middle", check_overlap=False)

    bottom = content_bottom
    if notes:
        bottom += 14.0
        nw = (c.content_width - 12.0 * (len(notes) - 1)) / len(notes)
        note_heights, note_wraps = [], []
        for nt in notes:
            title_n = str(nt.get("label") or nt.get("title") or "")
            body_n = str(nt.get("detail") or nt.get("text") or "")
            brows = _wrap(body_n, nw - 26.0, BODY_FONT) if body_n else []
            nh = 12.0 + (20.0 if title_n else 0.0) + len(brows) * 17.5 + 10.0
            note_heights.append(nh)
            note_wraps.append((title_n, brows))
        max_nh = max(note_heights)
        for ni, (nt, (title_n, brows)) in enumerate(zip(notes, note_wraps)):
            nx = m + ni * (nw + 12.0)
            nid = str(nt.get("id", f"note-{ni}"))
            nacc = c.tone(nt, fallback="blue")
            end = c.group(nid, nt, (nx, bottom, nw, max_nh), "note")
            c.rect(nx, bottom, nw, max_nh, nacc["tint"], nacc["border"], 7.0, sw=1.0)
            c.rect(nx + 1.0, bottom + 5.0, 3.0, max(4.0, max_nh - 10.0), nacc["solid"], "none", 1.5)
            ny_t = bottom + 22.0
            if title_n:
                c.text(nx + 12.0, ny_t, title_n, 13.0, nacc["text"], 700)
                ny_t += 19.0
            for bi, brow in enumerate(brows):
                c.text(nx + 12.0, ny_t + bi * 17.5, brow, BODY_FONT, c.surf["text"], 400)
            end()
            c.register_box(nid, nx, bottom, nw, max_nh)
        bottom += max_nh

    return c.finish(bottom)


# ===========================================================================
# 2. dashboard: composite quantitative KPI + ranked_bars + trend + drivers
# ===========================================================================
def _nice_ticks(lo, hi, count=5):
    span = hi - lo
    if span <= 0:
        return [lo, lo + 1.0]
    raw_step = span / max(1, count - 1)
    mag = 10 ** math.floor(math.log10(raw_step))
    norm = raw_step / mag
    step_unit = 1.0 if norm <= 1.2 else 2.0 if norm <= 2.5 else 5.0 if norm <= 5.5 else 10.0
    step = step_unit * mag
    t_lo = math.floor(lo / step) * step
    t_hi = math.ceil(hi / step) * step
    ticks, cur = [], t_lo
    while cur <= t_hi + step * 1e-6:
        ticks.append(round(cur, 8))
        cur += step
    return ticks


def _fmt_num(val):
    if abs(val - round(val)) < 1e-6:
        return f"{int(round(val)):,}"
    return f"{val:,.1f}"


def _measure_panel_takeaway(takeaway, w):
    if not takeaway:
        return [], 0.0
    rows = _wrap(str(takeaway), max(120.0, w - 52.0), BODY_FONT)
    return rows, 16.0 + len(rows) * 17.5


def _measure_dashboard_panel(panel, w):
    kind = panel.get("type", "ranked_bars")
    head_h = 26.0 + (18.0 if panel.get("subtitle") else 0.0)
    tk_rows, tk_h = _measure_panel_takeaway(panel.get("takeaway"), w)
    bottom_tk = (10.0 + tk_h) if tk_h else 0.0

    if kind == "ranked_bars":
        items = panel.get("items") or []
        _check(isinstance(items, list) and 1 <= len(items) <= 14, "ranked_bars panel supports 1–14 items")
        has_div = panel.get("divider_before") is not None
        body_h = len(items) * 34.0 + (10.0 if has_div else 0.0)
        return head_h + 14.0 + body_h + bottom_tk + 14.0, {"tk_rows": tk_rows, "tk_h": tk_h}

    if kind == "trend":
        cats = panel.get("categories") or panel.get("x") or []
        series = panel.get("series") or []
        _check(isinstance(cats, list) and len(cats) >= 2, "trend panel requires >= 2 categories")
        _check(isinstance(series, list) and 1 <= len(series) <= 4, "trend panel supports 1–4 series")
        for s in series:
            vals = s.get("values") or []
            _check(len(vals) == len(cats), f"Series {s.get('name', '?')} length mismatches categories")
            for v in vals:
                if v is not None:
                    _finite(v, f"Series {s.get('name', '?')} value")
        return head_h + 215.0 + bottom_tk + 14.0, {"tk_rows": tk_rows, "tk_h": tk_h}

    if kind == "grouped_bars":
        cats = panel.get("categories") or panel.get("x") or []
        series = panel.get("series") or []
        _check(isinstance(cats, list) and 2 <= len(cats) <= 12, "grouped_bars supports 2–12 categories")
        _check(isinstance(series, list) and 1 <= len(series) <= 5, "grouped_bars supports 1–5 series")
        for s in series:
            vals = s.get("values") or []
            _check(len(vals) == len(cats), f"Series {s.get('name', '?')} length mismatches categories")
            for v in vals:
                _finite(v, f"Series {s.get('name', '?')} value")
        return head_h + 205.0 + bottom_tk + 14.0, {"tk_rows": tk_rows, "tk_h": tk_h}

    if kind in ("drivers", "cards"):
        items = panel.get("items") or []
        _check(isinstance(items, list) and 1 <= len(items) <= 6, "drivers panel supports 1–6 items")
        cols = min(len(items), int(panel.get("columns", 3)))
        cw = (w - 36.0 - 12.0 * (cols - 1)) / cols
        row_cards = [items[i:i + cols] for i in range(0, len(items), cols)]
        total_h, card_layouts = 0.0, []
        for rc in row_cards:
            rh, rc_meas = 0.0, []
            for it in rc:
                d_rows = _wrap(it.get("detail", ""), cw - 24.0, BODY_FONT) if it.get("detail") else []
                buls = [_wrap(f"• {b}", cw - 24.0, TAG_FONT) for b in it.get("bullets", [])]
                ch = 34.0 + len(d_rows) * 17.5 + sum(len(br) * 16.5 + 3.0 for br in buls) + 10.0
                rh = max(rh, ch)
                rc_meas.append((it, d_rows, buls, ch))
            total_h += rh + 10.0
            card_layouts.append((rh, rc_meas))
        return head_h + 12.0 + total_h - 10.0 + bottom_tk + 14.0, {
            "tk_rows": tk_rows, "tk_h": tk_h, "cols": cols, "cw": cw, "card_layouts": card_layouts,
        }

    raise ValueError(f"Unsupported dashboard panel type: {kind}")


def _draw_ranked_bars_panel(c, panel, px, py, pw, ph, top_y, tk_rows, tk_h):
    items = panel["items"]
    vals = [_finite(it["value"], f"ranked_bars[{i}].value") for i, it in enumerate(items)]
    _check(all(v >= 0 for v in vals), "ranked_bars values must be non-negative")
    max_val = float(panel["max_value"]) if panel.get("max_value") is not None else max(vals or [1.0]) * 1.12
    _check(max_val > 0, "ranked_bars max_value must be positive")
    has_reason = any(it.get("reason") for it in items)
    has_delta = any(it.get("delta") for it in items)

    pad_x = 16.0
    label_w = max(86.0, min(118.0, pw * 0.24))
    right_col_w = (max(115.0, pw * 0.27) if has_reason else 82.0 if has_delta else 0.0)
    bar_x = px + pad_x + label_w + 6.0
    bar_w = max(90.0, pw - pad_x * 2 - label_w - 6.0 - (right_col_w + 10.0 if right_col_w else 0.0))
    right_x = bar_x + bar_w + 10.0
    divider_before = panel.get("divider_before")

    cy = top_y + 8.0
    for idx, it in enumerate(items):
        if divider_before is not None and idx == divider_before:
            c.line(px + pad_x, cy - 2.0, px + pw - pad_x, cy - 2.0, c.surf["divider"], 1.0, dash="4 3")
            cy += 10.0
        tone_it = it if it.get("tone") else (panel.get("tone") or "blue")
        acc = c.tone(tone_it, fallback="blue")
        if it.get("highlight"):
            c.rect(px + 10.0, cy - 3.0, pw - 20.0, 29.0, acc["tint"], acc["border"], 6.0, sw=0.9)
        c.text(px + pad_x, cy + 15.0, str(it["label"]), BODY_FONT,
               c.surf["ink"] if it.get("highlight") else c.surf["text"],
               700 if it.get("highlight") else 500)
        c.rect(bar_x, cy + 2.0, bar_w, 19.0, c.surf["track"], "none", 5.0, sw=0.0)
        fill_w = max(4.0, min(bar_w, bar_w * (vals[idx] / max_val))) if vals[idx] > 0 else 0.0
        if fill_w > 0:
            c.rect(bar_x, cy + 2.0, fill_w, 19.0, acc["mark"], "none", 5.0, sw=0.0)
        val_txt = str(it.get("display") or (_fmt_num(vals[idx]) + (f" {panel['unit']}" if panel.get("unit") else "")))
        vw = _diag_tw(val_txt, TAG_FONT)
        if fill_w > vw + 16.0:
            c.text(bar_x + fill_w - 7.0, cy + 15.5, val_txt, TAG_FONT, c.surf["card"], 700, anchor="end", check_overlap=False)
        else:
            tx_v = min(bar_x + bar_w - vw - 4.0, bar_x + fill_w + 6.0)
            c.text(tx_v, cy + 15.5, val_txt, TAG_FONT, acc["text"], 700, check_overlap=False)

        if has_reason and it.get("reason"):
            r_rows = _wrap(it["reason"], right_col_w - 4.0, TAG_FONT)
            c.text(right_x, cy + 15.5, r_rows[0], TAG_FONT, c.surf["muted"], 500, check_overlap=False)
        elif it.get("delta"):
            dtxt = str(it["delta"])
            d_tone = it.get("delta_tone") or ("teal" if dtxt.startswith("+") else "red" if dtxt.startswith("-") else "slate")
            dacc = c.tone(d_tone, fallback="slate")
            dw = min(right_col_w, _diag_tw(dtxt, TAG_FONT) + 12.0)
            c.rect(px + pw - pad_x - dw, cy + 1.5, dw, 20.0, dacc["tint"], dacc["border"], 10.0, sw=0.8)
            c.text(px + pw - pad_x - dw / 2.0, cy + 15.5, dtxt, TAG_FONT, dacc["text"], 600, anchor="middle", check_overlap=False)
        cy += 34.0

    if tk_h:
        tky = py + ph - tk_h - 12.0
        pacc = c.tone(panel, fallback="blue")
        c.rect(px + 14.0, tky, pw - 28.0, tk_h, pacc["tint"], pacc["border"], 6.0, sw=0.9)
        c.rect(px + 14.0, tky + 4.0, 3.0, max(4.0, tk_h - 8.0), pacc["solid"], "none", 1.5)
        for ti, trow in enumerate(tk_rows):
            c.text(px + 24.0, tky + 19.0 + ti * 17.5, trow, BODY_FONT, c.surf["ink"], 600 if ti == 0 else 400, check_overlap=False)


def _draw_trend_panel(c, panel, px, py, pw, ph, top_y, tk_rows, tk_h):
    cats = [str(x) for x in (panel.get("categories") or panel.get("x"))]
    series = panel["series"]
    has_right = any(s.get("axis") == "right" for s in series)
    pad_l = 44.0
    pad_r = 44.0 if has_right else 18.0
    gx = px + pad_l
    gw = pw - pad_l - pad_r
    gy = top_y + 24.0
    chart_bottom = py + ph - (tk_h + 22.0 if tk_h else 12.0) - 24.0
    gh = max(100.0, chart_bottom - gy)

    bar_series = [s for s in series if s.get("kind") == "bar"]
    line_series = [s for s in series if s.get("kind", "line") != "bar"]
    series_acc = {
        id(s): c.tone(s, fallback=c.pal["sequence"][idx % len(c.pal["sequence"])])
        for idx, s in enumerate([*bar_series, *line_series])
    }

    lx = px + pw - 16.0
    for s in reversed(series):
        sname = str(s.get("name", ""))
        sacc = series_acc[id(s)]
        sw_l = _diag_tw(sname, TAG_FONT)
        lx -= sw_l
        c.text(lx, top_y + 9.0, sname, TAG_FONT, c.surf["text"], 500, check_overlap=False)
        lx -= 18.0
        if s.get("kind") == "bar":
            c.rect(lx, top_y, 11.0, 9.0, sacc["mark"], "none", 2.0, sw=0.0)
        else:
            c.line(lx - 2.0, top_y + 5.0, lx + 11.0, top_y + 5.0, sacc["mark"], 2.0)
            c.circle(lx + 4.5, top_y + 5.0, 2.8, sacc["mark"])
        lx -= 12.0

    def axis_range(ax_name):
        s_list = [s for s in series if s.get("axis", "left") == ax_name]
        vals = [float(v) for s in s_list for v in s["values"] if v is not None]
        if not vals:
            return 0.0, 1.0, [0.0, 1.0]
        has_bar = any(s.get("kind") == "bar" for s in s_list)
        lo = min(vals) if not has_bar else min(0.0, min(vals))
        hi = max(vals)
        pad = max(1e-3, (hi - lo) * 0.16)
        if not has_bar:
            lo = max(0.0, lo - pad * 0.6) if lo >= 0 else lo - pad * 0.6
        hi = hi + pad
        if ax_name == "left":
            if panel.get("y_min") is not None:
                lo = _finite(panel["y_min"], "y_min")
            if panel.get("y_max") is not None:
                hi = _finite(panel["y_max"], "y_max")
        else:
            if panel.get("y2_min") is not None:
                lo = _finite(panel["y2_min"], "y2_min")
            if panel.get("y2_max") is not None:
                hi = _finite(panel["y2_max"], "y2_max")
        _check(hi > lo, "trend y_max must exceed y_min")
        ticks = _nice_ticks(lo, hi, 5)
        return ticks[0], ticks[-1], ticks

    l_lo, l_hi, l_ticks = axis_range("left")
    r_lo, r_hi, r_ticks = axis_range("right") if has_right else (0.0, 1.0, [])

    def y_of(val, ax_name="left"):
        lo, hi = (r_lo, r_hi) if ax_name == "right" else (l_lo, l_hi)
        return gy + gh - (float(val) - lo) / (hi - lo) * gh

    split_after = panel.get("split_after")
    n = len(cats)
    xs = ([gx + (i + 0.5) * (gw / n) for i in range(n)] if bar_series
          else [gx + i * (gw / (n - 1)) for i in range(n)])

    if split_after is not None:
        _check(isinstance(split_after, int) and 0 <= split_after < n - 1,
               "split_after must be a valid category index < len(categories)-1")
        sx = (xs[split_after] + xs[split_after + 1]) / 2.0
        facc = c.tone("amber", fallback="amber")
        c.rect(sx, gy, gx + gw - sx, gh, facc["tint"], "none", 4.0, sw=0.0, fill_opacity=0.6)
        c.line(sx, gy, sx, gy + gh, c.surf["divider"], 1.1, dash="5 4")
        flabel = str(panel.get("forecast_label", "预测期"))
        c.text(sx + 6.0, gy + 14.0, flabel, MIN_FONT, facc["text"], 600, check_overlap=False)

    for tv in l_ticks:
        yy = y_of(tv, "left")
        c.line(gx, yy, gx + gw, yy, c.surf["divider"], 0.8 if abs(tv - l_lo) < 1e-6 else 0.5,
               dash=None if abs(tv - l_lo) < 1e-6 else "3 3")
        c.text(gx - 6.0, yy + 4.0, _fmt_num(tv), MIN_FONT, c.surf["muted"], anchor="end", check_overlap=False)
    if has_right:
        for tv in r_ticks:
            yy = y_of(tv, "right")
            c.text(gx + gw + 6.0, yy + 4.0, _fmt_num(tv), MIN_FONT, c.surf["muted"], anchor="start", check_overlap=False)

    max_x_w = max(_diag_tw(cat, MIN_FONT) for cat in cats) + 8.0
    slot_dx = gw / max(1, n - 1 if not bar_series else n)
    step_x = max(1, math.ceil(max_x_w / max(1.0, slot_dx)))
    last_drawn_x = -1e9
    for i, cat in enumerate(cats):
        cw_x = _diag_tw(cat, MIN_FONT)
        if i % step_x == 0 or (i == n - 1 and xs[i] - cw_x / 2.0 > last_drawn_x + 6.0):
            c.text(xs[i], gy + gh + 16.0, cat, MIN_FONT, c.surf["muted"], anchor="middle", check_overlap=False)
            last_drawn_x = xs[i] + cw_x / 2.0

    slot_w = gw / n
    if bar_series:
        bw = min(30.0, (slot_w * 0.62) / len(bar_series))
        for si, s in enumerate(bar_series):
            sacc = series_acc[id(s)]
            ax_name = s.get("axis", "left")
            base_y = y_of(max(0.0, l_lo if ax_name == "left" else r_lo), ax_name)
            off = (si - (len(bar_series) - 1) / 2.0) * (bw + 2.5)
            for i, v in enumerate(s["values"]):
                if v is None:
                    continue
                vy = y_of(v, ax_name)
                is_fc = split_after is not None and i > split_after
                c.rect(xs[i] + off - bw / 2.0, min(vy, base_y), bw, max(2.0, abs(base_y - vy)),
                       sacc["tint"] if is_fc else sacc["mark"],
                       sacc["mark"] if is_fc else "none", 3.0, sw=1.0 if is_fc else 0.0,
                       dash="4 3" if is_fc else None)
                if s.get("show_values") and vy > gy + 15.0:
                    c.text(xs[i] + off, vy - 5.0, _fmt_num(v), MIN_FONT, sacc["text"], 600, anchor="middle", check_overlap=False)

    for s in line_series:
        sacc = series_acc[id(s)]
        ax_name = s.get("axis", "left")
        pts = [(xs[i], y_of(v, ax_name)) for i, v in enumerate(s["values"]) if v is not None]
        idxs = [i for i, v in enumerate(s["values"]) if v is not None]
        if s.get("kind") == "area" and len(pts) >= 2:
            base_y = gy + gh
            c.polyline([(pts[0][0], base_y), *pts, (pts[-1][0], base_y)], stroke="none",
                       fill=sacc["mark"], fill_opacity=0.10, close=True)
        if split_after is not None:
            hist_pts = [(xs[i], y_of(s["values"][i], ax_name)) for i in idxs if i <= split_after]
            fc_pts = [(xs[i], y_of(s["values"][i], ax_name)) for i in idxs if i >= split_after]
            if len(hist_pts) >= 2:
                c.polyline(hist_pts, stroke=sacc["mark"], width=2.1)
            if len(fc_pts) >= 2:
                c.polyline(fc_pts, stroke=sacc["mark"], width=2.1, dash="6 4")
        elif len(pts) >= 2:
            c.polyline(pts, stroke=sacc["mark"], width=2.1)
        for i in idxs:
            px0, py0 = xs[i], y_of(s["values"][i], ax_name)
            is_fc = split_after is not None and i > split_after
            c.circle(px0, py0, 3.6, c.surf["card"] if is_fc else sacc["mark"],
                     stroke=sacc["mark"] if is_fc else c.surf["card"], sw=1.5)
            if s.get("show_values", n <= 9) and py0 > gy + 14.0:
                c.text(px0, py0 - 8.0, _fmt_num(s["values"][i]), TAG_FONT, sacc["text"], 600, anchor="middle", check_overlap=False)

    ann_rects = []
    for ann in panel.get("annotations") or []:
        idx = int(ann["at"])
        si = int(ann.get("series", 0))
        _check(0 <= idx < n and 0 <= si < len(series), "Annotation index out of bounds")
        s = series[si]
        val = s["values"][idx]
        if val is None:
            continue
        ax_name = s.get("axis", "left")
        px0, py0 = xs[idx], y_of(val, ax_name)
        aacc = c.tone(ann, fallback="amber")
        albl = str(ann["label"])
        aw = _diag_tw(albl, MIN_FONT) + 12.0
        ah = 19.0
        ax0 = min(max(gx + 2.0, px0 + float(ann.get("dx", 0.0)) - aw / 2.0), gx + gw - aw - 2.0)
        dy = float(ann.get("dy", -26.0))
        ay0 = min(max(gy + 2.0, py0 + dy - ah / 2.0), gy + gh - ah - 4.0)
        cand = (ax0, ay0, aw, ah)
        while any(_box_overlap(cand, r, eps=0.5) for r in ann_rects) and cand[1] + ah + 16.0 < gy + gh:
            cand = (cand[0], cand[1] + 20.0, aw, ah)
        ann_rects.append(cand)
        c.circle(px0, py0, 4.6, aacc["mark"], stroke=c.surf["card"], sw=1.5)
        c.line(px0, py0, cand[0] + aw / 2.0, cand[1] + (ah if cand[1] < py0 else 0.0), aacc["solid"], 1.0, dash="3 2")
        c.rect(cand[0], cand[1], aw, ah, aacc["tint"], aacc["border"], 5.5, sw=0.8)
        c.text(cand[0] + aw / 2.0, cand[1] + 13.0, albl, MIN_FONT, aacc["text"], 700, anchor="middle", check_overlap=False)

    if tk_h:
        tky = py + ph - tk_h - 12.0
        pacc = c.tone(panel, fallback="blue")
        c.rect(px + 14.0, tky, pw - 28.0, tk_h, pacc["tint"], pacc["border"], 6.0, sw=0.9)
        c.rect(px + 14.0, tky + 4.0, 3.0, max(4.0, tk_h - 8.0), pacc["solid"], "none", 1.5)
        for ti, trow in enumerate(tk_rows):
            c.text(px + 24.0, tky + 19.0 + ti * 17.5, trow, BODY_FONT, c.surf["ink"], 600 if ti == 0 else 400, check_overlap=False)


def _draw_grouped_bars_panel(c, panel, px, py, pw, ph, top_y, tk_rows, tk_h):
    converted = {
        **panel,
        "type": "trend",
        "series": [{**s, "kind": "bar", "show_values": s.get("show_values", True)} for s in panel["series"]],
    }
    _draw_trend_panel(c, converted, px, py, pw, ph, top_y, tk_rows, tk_h)


def _draw_drivers_panel(c, panel, px, py, pw, ph, top_y, info):
    cy = top_y + 6.0
    cw = info["cw"]
    for rh, rc_meas in info["card_layouts"]:
        for ci, (it, d_rows, buls, _) in enumerate(rc_meas):
            cx = px + 18.0 + ci * (cw + 12.0)
            iacc = c.tone(it, fallback=c.pal["sequence"][ci % len(c.pal["sequence"])])
            c.rect(cx, cy, cw, rh, iacc["tint"], iacc["border"], 7.0, sw=0.9)
            c.rect(cx, cy + 5.0, 3.0, max(4.0, rh - 10.0), iacc["solid"], "none", 1.5)
            c.text(cx + 12.0, cy + 21.0, str(it.get("title") or it.get("label") or ""), 13.0, iacc["text"], 700, check_overlap=False)
            if it.get("tag"):
                tw = _diag_tw(it["tag"], MIN_FONT) + 12.0
                c.rect(cx + cw - 8.0 - tw, cy + 7.0, tw, 18.0, c.surf["card"], iacc["border"], 9.0, sw=0.8)
                c.text(cx + cw - 8.0 - tw / 2.0, cy + 19.5, str(it["tag"]), MIN_FONT, iacc["text"], 600, anchor="middle", check_overlap=False)
            ty = cy + 39.0
            for dr in d_rows:
                c.text(cx + 12.0, ty, dr, BODY_FONT, c.surf["ink"], 500, check_overlap=False)
                ty += 17.5
            for br in buls:
                for line in br:
                    c.text(cx + 12.0, ty, line, TAG_FONT, c.surf["muted"], 400, check_overlap=False)
                    ty += 16.5
                ty += 3.0
        cy += rh + 10.0

    tk_rows, tk_h = info["tk_rows"], info["tk_h"]
    if tk_h:
        tky = py + ph - tk_h - 12.0
        pacc = c.tone(panel, fallback="blue")
        c.rect(px + 14.0, tky, pw - 28.0, tk_h, pacc["tint"], pacc["border"], 6.0, sw=0.9)
        c.rect(px + 14.0, tky + 4.0, 3.0, max(4.0, tk_h - 8.0), pacc["solid"], "none", 1.5)
        for ti, trow in enumerate(tk_rows):
            c.text(px + 24.0, tky + 19.0 + ti * 17.5, trow, BODY_FONT, c.surf["ink"], 600 if ti == 0 else 400, check_overlap=False)


def dashboard(spec):
    """Composite data dashboard with KPI strip, 1x2/2x2 panels, ranked bars & split trends."""
    panels = spec.get("panels") or []
    _check(isinstance(panels, list) and 1 <= len(panels) <= 8, "dashboard supports 1–8 panels")
    kpis = spec.get("kpi_cards") or []
    _check(len(kpis) <= 5, "dashboard supports up to 5 kpi_cards")

    preset = spec.get("preset", "insight")
    opts = _layout_opts(spec)
    canvas_w = int(opts.get("width", spec.get("canvas_width", 1360)))
    cols = int(spec.get("columns", 2 if len(panels) >= 2 else 1))
    _check(cols in (1, 2), "dashboard columns must be 1 or 2")

    c = InsightCanvas(spec, width=canvas_w, preset=preset)
    m = c.margin
    y = c.content_top

    if kpis:
        kgap = 12.0
        kw = (c.content_width - kgap * (len(kpis) - 1)) / len(kpis)
        kh = 76.0 if any(k.get("detail") for k in kpis) else 64.0
        for i, kpi in enumerate(kpis):
            kx = m + i * (kw + kgap)
            kid = str(kpi.get("id", f"kpi-{i}"))
            kacc = c.tone(kpi, fallback=c.pal["sequence"][i % len(c.pal["sequence"])])
            end = c.group(kid, kpi, (kx, y, kw, kh), "card")
            c.rect(kx, y, kw, kh, c.surf["card"], c.surf["border"], 8.0, sw=1.0)
            c.rect(kx + 10.0, y, max(20.0, kw - 20.0), 3.0, kacc["solid"], "none", 1.5)
            c.text(kx + 12.0, y + 20.0, str(kpi.get("label", "")), TAG_FONT, c.surf["muted"], 600)
            c.text(kx + 12.0, y + 46.0, str(kpi.get("value", "")), 20.0, c.surf["ink"], 700)
            if kpi.get("delta"):
                dtxt = str(kpi["delta"])
                dw = _diag_tw(dtxt, MIN_FONT) + 12.0
                c.rect(kx + kw - 10.0 - dw, y + 10.0, dw, 18.0, kacc["tint"], kacc["border"], 9.0, sw=0.8)
                c.text(kx + kw - 10.0 - dw / 2.0, y + 22.5, dtxt, MIN_FONT, kacc["text"], 600, anchor="middle")
            if kpi.get("detail"):
                det_rows = _wrap(kpi["detail"], kw - 24.0, TAG_FONT)
                c.text(kx + 12.0, y + 64.0, det_rows[0], TAG_FONT, c.surf["muted"])
            end()
            c.register_box(kid, kx, y, kw, kh)
        y += kh + 14.0

    pgap = 16.0
    rows, cur_row, cur_span = [], [], 0
    for p in panels:
        span = 2 if (cols == 2 and int(p.get("span", 1)) >= 2) or cols == 1 else 1
        if cur_row and cur_span + span > cols:
            rows.append(cur_row)
            cur_row, cur_span = [], 0
        cur_row.append((p, span))
        cur_span += span
    if cur_row:
        rows.append(cur_row)

    for row in rows:
        widths = [c.content_width if sp == cols else (c.content_width - pgap) / 2.0 for _, sp in row]
        measured = [_measure_dashboard_panel(p, w) for (p, _), w in zip(row, widths)]
        row_h = max(mh for mh, _ in measured)
        px = m
        for (p, _), pw, (mh, info) in zip(row, widths, measured):
            pid = str(p.get("id", f"panel-{panels.index(p)}"))
            pacc = c.tone(p, fallback="blue")
            end = c.group(pid, p, (px, y, pw, row_h), "panel")
            c.rect(px, y, pw, row_h, c.surf["card"], c.surf["border"], 8.0, sw=1.1)
            c.rect(px + 14.0, y + 12.0, 3.5, 16.0, pacc["solid"], "none", 1.75)
            c.text(px + 24.0, y + 25.0, str(p.get("title", pid)), 14.5, c.surf["ink"], 700)
            top_y = y + 36.0
            if p.get("subtitle"):
                c.text(px + 24.0, y + 43.0, str(p["subtitle"]), TAG_FONT, c.surf["muted"], 400)
                top_y = y + 54.0
            ptype = p.get("type", "ranked_bars")
            if ptype == "ranked_bars":
                _draw_ranked_bars_panel(c, p, px, y, pw, row_h, top_y, info["tk_rows"], info["tk_h"])
            elif ptype == "trend":
                _draw_trend_panel(c, p, px, y, pw, row_h, top_y, info["tk_rows"], info["tk_h"])
            elif ptype == "grouped_bars":
                _draw_grouped_bars_panel(c, p, px, y, pw, row_h, top_y, info["tk_rows"], info["tk_h"])
            elif ptype in ("drivers", "cards"):
                _draw_drivers_panel(c, p, px, y, pw, row_h, top_y, info)
            end()
            c.register_box(pid, px, y, pw, row_h)
            px += pw + pgap
        y += row_h + pgap

    return c.finish(y - pgap)


# ===========================================================================
# 3. panorama-mindmap: 3-level dual-wing panorama mindmap (up to 12 branches)
# ===========================================================================
def _norm_leaf(leaf, fallback_id):
    if isinstance(leaf, dict):
        lid = str(leaf.get("id") or fallback_id)
        lbl = str(leaf.get("label") or leaf.get("title") or "")
        det = str(leaf.get("detail") or leaf.get("desc") or "")
        return {"id": lid, "label": lbl, "detail": det}
    s = str(leaf)
    if "：" in s:
        title, det = s.split("：", 1)
        return {"id": fallback_id, "label": title.strip(), "detail": det.strip()}
    if ": " in s:
        title, det = s.split(": ", 1)
        return {"id": fallback_id, "label": title.strip(), "detail": det.strip()}
    return {"id": fallback_id, "label": s, "detail": ""}


def panorama_mindmap(spec):
    """3-level high-density radial/bilateral mindmap with smooth bezier routing."""
    preset = spec.get("preset", "insight")
    opts = _layout_opts(spec)
    canvas_w = int(opts.get("width", spec.get("canvas_width", 1440)))
    c = InsightCanvas(spec, width=canvas_w, preset=preset)

    if "left_groups" in spec or "right_groups" in spec:
        left_groups = list(spec.get("left_groups") or [])
        right_groups = list(spec.get("right_groups") or [])
    else:
        groups = list(spec.get("groups") or [])
        _check(2 <= len(groups) <= 12, "panorama-mindmap supports 2–12 groups")
        left_groups, right_groups = [], []
        lh_est = rh_est = 0
        for g in groups:
            cnt = max(1, len(g.get("leaves") or g.get("items") or []))
            if lh_est <= rh_est:
                left_groups.append(g)
                lh_est += cnt + 1
            else:
                right_groups.append(g)
                rh_est += cnt + 1

    all_groups = left_groups + right_groups
    _check(1 <= len(all_groups) <= 12, "panorama-mindmap supports 1–12 branches total")

    center_spec = spec["center"] if isinstance(spec["center"], dict) else {"label": str(spec["center"])}
    dense = max(len(left_groups), len(right_groups)) >= 5
    hub_w = 122.0 if dense else 132.0
    branch_w = 114.0 if dense else 124.0
    leaf_w = (c.content_width - hub_w - 2.0 * branch_w - (86.0 if dense else 96.0)) / 2.0
    _check(leaf_w >= 140.0, "Canvas too narrow for 3-level panorama-mindmap; increase layout.width")

    def prep_side(side_groups, side_tag):
        prepared = []
        vpad = 6.5 if dense else 9.0
        l_line_t = 15.5 if dense else 16.5
        l_line_d = 14.5 if dense else 15.0
        l_gap = 4.0 if dense else 6.0
        for gi, g in enumerate(side_groups):
            gid = str(g.get("id") or f"branch-{side_tag}-{gi}")
            raw_leaves = g.get("leaves") or g.get("items") or []
            if not raw_leaves and g.get("detail"):
                raw_leaves = [g["detail"]]
            leaves_m = []
            for li, lf in enumerate(raw_leaves):
                nleaf = _norm_leaf(lf, f"{gid}-leaf-{li}")
                trows = _wrap(nleaf["label"], leaf_w - 26.0, BODY_FONT)
                drows = _wrap(nleaf["detail"], leaf_w - 26.0, MIN_FONT) if nleaf["detail"] else []
                lh = vpad + len(trows) * l_line_t + (len(drows) * l_line_d + 1.5 if drows else 0.0) + vpad
                leaves_m.append({"raw": nleaf, "trows": trows, "drows": drows, "h": lh,
                                 "vpad": vpad, "lt": l_line_t, "ld": l_line_d})
            b_trows = _wrap(g["label"], branch_w - 22.0, 13.0)
            bh = 10.0 + len(b_trows) * 17.0 + 8.0
            span_h = max(bh, sum(lm["h"] for lm in leaves_m) + l_gap * max(0, len(leaves_m) - 1))
            prepared.append({"group": g, "id": gid, "b_trows": b_trows, "bh": bh,
                             "leaves": leaves_m, "span_h": span_h, "l_gap": l_gap})
        return prepared

    left_prep = prep_side(left_groups, "L")
    right_prep = prep_side(right_groups, "R")
    branch_gap = 9.0 if dense else 14.0
    has_side_hdr = bool(spec.get("left_header") or spec.get("right_header"))
    top_start = c.content_top + (30.0 if has_side_hdr else 6.0)

    def side_total_h(prep):
        return sum(p["span_h"] for p in prep) + branch_gap * max(0, len(prep) - 1)

    total_h = max(160.0, side_total_h(left_prep), side_total_h(right_prep))
    mid_y = top_start + total_h / 2.0

    m = c.margin
    cx_center = LW / 2.0
    if spec.get("left_header"):
        acc_l = c.tone("teal", fallback="teal")
        lw_h = min(c.content_width * 0.42, _diag_tw(spec["left_header"], MIN_FONT) + 24.0)
        c.rect(m, c.content_top, lw_h, 22.0, acc_l["tint"], acc_l["border"], 11.0, sw=0.8)
        c.text(m + 12.0, c.content_top + 15.0, str(spec["left_header"]), MIN_FONT, acc_l["text"], 700)
    if spec.get("right_header"):
        acc_r = c.tone("purple", fallback="purple")
        rw_h = min(c.content_width * 0.42, _diag_tw(spec["right_header"], MIN_FONT) + 24.0)
        c.rect(LW - m - rw_h, c.content_top, rw_h, 22.0, acc_r["tint"], acc_r["border"], 11.0, sw=0.8)
        c.text(LW - m - 12.0, c.content_top + 15.0, str(spec["right_header"]), MIN_FONT, acc_r["text"], 700, anchor="end")

    c_trows = _wrap(center_spec["label"], hub_w - 22.0, 15.0)
    c_sub = center_spec.get("sublabel") or center_spec.get("detail") or ""
    c_drows = _wrap(c_sub, hub_w - 22.0, MIN_FONT) if c_sub else []
    hub_h = max(76.0, 20.0 + len(c_trows) * 19.5 + len(c_drows) * 15.5 + 14.0)
    hub_x = cx_center - hub_w / 2.0
    hub_y = mid_y - hub_h / 2.0
    hub_acc = c.tone(center_spec, fallback="blue")

    def render_side(prep, is_right, color_offset):
        sh = side_total_h(prep)
        cur_y = top_start + (total_h - sh) / 2.0
        for bi, b in enumerate(prep):
            g = b["group"]
            bacc = c.tone(g, fallback=c.pal["sequence"][(bi + color_offset) % len(c.pal["sequence"])])
            leaf_x = (LW - m - leaf_w) if is_right else m
            branch_x = (cx_center + hub_w / 2.0 + 26.0) if is_right else (cx_center - hub_w / 2.0 - 26.0 - branch_w)
            by_center = cur_y + b["span_h"] / 2.0
            branch_y = by_center - b["bh"] / 2.0

            hx = hub_x + (hub_w if is_right else 0.0)
            bx_in = branch_x + (0.0 if is_right else branch_w)
            c.cubic((hx, mid_y), ((hx + bx_in) / 2.0, mid_y), ((hx + bx_in) / 2.0, by_center), (bx_in, by_center),
                    stroke=bacc["mark"], width=1.8, relation={"from": "center", "to": b["id"], "kind": "mindmap-branch", "directed": False})

            leaves_h = sum(lm["h"] for lm in b["leaves"]) + b["l_gap"] * max(0, len(b["leaves"]) - 1)
            ly = cur_y + (b["span_h"] - leaves_h) / 2.0
            bx_out = branch_x + (branch_w if is_right else 0.0)
            lx_in = leaf_x + (0.0 if is_right else leaf_w)

            end_b = c.group(b["id"], g, (branch_x, branch_y, branch_w, b["bh"]), "card")
            c.rect(branch_x, branch_y, branch_w, b["bh"], bacc["tint"], bacc["border"], 8.0, sw=1.1)
            c.rect(branch_x + (0.0 if is_right else branch_w - 3.5), branch_y + 4.0, 3.5, max(4.0, b["bh"] - 8.0),
                   bacc["solid"], "none", 1.75)
            for ti, trow in enumerate(b["b_trows"]):
                c.text(branch_x + branch_w / 2.0, branch_y + 20.5 + ti * 17.5, trow, 13.0, bacc["text"], 700, anchor="middle")
            end_b()
            c.register_box(b["id"], branch_x, branch_y, branch_w, b["bh"])

            for lm in b["leaves"]:
                lid = lm["raw"]["id"]
                lh = lm["h"]
                ly_mid = ly + lh / 2.0
                c.cubic((bx_out, by_center), ((bx_out + lx_in) / 2.0, by_center), ((bx_out + lx_in) / 2.0, ly_mid), (lx_in, ly_mid),
                        stroke=bacc["border"], width=1.25, relation={"from": b["id"], "to": lid, "kind": "mindmap-leaf", "directed": False})
                end_l = c.group(lid, lm["raw"], (leaf_x, ly, leaf_w, lh), "card")
                c.rect(leaf_x, ly, leaf_w, lh, c.surf["card"], c.surf["border"], 7.0, sw=0.9)
                c.circle(leaf_x + 11.0, ly + lm["vpad"] + 6.5, 2.8, bacc["mark"])
                for ti, trow in enumerate(lm["trows"]):
                    c.text(leaf_x + 19.0, ly + lm["vpad"] + 10.5 + ti * lm["lt"], trow, BODY_FONT, c.surf["ink"], 600)
                dy0 = ly + lm["vpad"] + 10.5 + len(lm["trows"]) * lm["lt"] + 1.0
                for di, drow in enumerate(lm["drows"]):
                    c.text(leaf_x + 19.0, dy0 + di * lm["ld"], drow, MIN_FONT, c.surf["muted"], 400)
                end_l()
                c.register_box(lid, leaf_x, ly, leaf_w, lh)
                ly += lh + b["l_gap"]

            cur_y += b["span_h"] + branch_gap

    render_side(left_prep, is_right=False, color_offset=0)
    render_side(right_prep, is_right=True, color_offset=len(left_prep))

    end_c = c.group("center", center_spec, (hub_x, hub_y, hub_w, hub_h), "card")
    c.rect(hub_x, hub_y, hub_w, hub_h, hub_acc["solid"], hub_acc["border"], 14.0, sw=1.8)
    ty0 = hub_y + (hub_h - (len(c_trows) * 19.5 + len(c_drows) * 15.5)) / 2.0 + 15.0
    for ti, trow in enumerate(c_trows):
        c.text(cx_center, ty0 + ti * 19.5, trow, 15.0, c.surf["card"], 700, anchor="middle")
    dy_h = ty0 + len(c_trows) * 19.5
    for di, drow in enumerate(c_drows):
        c.text(cx_center, dy_h + di * 15.5, drow, MIN_FONT, c.surf["card"], 500, anchor="middle")
    end_c()
    c.register_box("center", hub_x, hub_y, hub_w, hub_h)

    return c.finish(top_start + total_h)


# ===========================================================================
# 4. flywheel: dual-ring core + header-strip quadrant cards + guardrail base
# ===========================================================================
def flywheel(spec):
    """Rich closed-loop flywheel with header-strip quadrant cards, arcs & guardrail base."""
    stages = spec.get("stages") or spec.get("groups") or []
    _check(isinstance(stages, list) and len(stages) in (3, 4), "flywheel supports 3 or 4 stages")
    guardrails = spec.get("guardrails") or spec.get("premises") or []
    _check(len(guardrails) <= 3, "flywheel supports at most 3 bottom guardrails/premises")
    links = spec.get("links") or []

    preset = spec.get("preset", "insight")
    opts = _layout_opts(spec)
    canvas_w = int(opts.get("width", spec.get("canvas_width", 1320)))
    c = InsightCanvas(spec, width=canvas_w, preset=preset)

    ids = [str(st.get("id") or f"stage-{i}") for i, st in enumerate(stages)]
    _check(len(set(ids)) == len(ids), "Duplicate flywheel stage IDs")
    link_map = {}
    for lk in links:
        _check(lk.get("from") in ids and lk.get("to") in ids, "Unknown flywheel link endpoint")
        k = ids.index(lk["from"])
        _check(lk["to"] == ids[(k + 1) % len(ids)] and k not in link_map,
               "Flywheel links must advance clockwise along consecutive stages")
        link_map[k] = lk

    m = c.margin
    card_w = 290.0
    measured_cards = []
    for st in stages:
        items = list(st.get("bullets") or st.get("items") or [])
        det = str(st.get("detail") or "").strip()
        if det and not items:
            items = [det]
        elif det:
            items = [det] + items
        body_lines = [_wrap(f"• {it}", card_w - 24.0, BODY_FONT) for it in items]
        ch = 34.0 + 14.0 + sum(len(bl) * 17.5 + 4.0 for bl in body_lines) + 8.0
        measured_cards.append((ch, body_lines))

    center_r = 82.0
    cx = LW / 2.0

    if len(stages) == 4:
        top_h = measured_cards[0][0]
        side_h = max(measured_cards[1][0], measured_cards[3][0])
        bot_h = measured_cards[2][0]
        cy = c.content_top + top_h + 36.0 + center_r
        positions = [
            (cx - card_w / 2.0, c.content_top),
            (LW - m - card_w, cy - side_h / 2.0),
            (cx - card_w / 2.0, cy + center_r + 36.0),
            (m, cy - side_h / 2.0),
        ]
        card_boxes = [
            (positions[0][0], positions[0][1], card_w, top_h),
            (positions[1][0], positions[1][1], card_w, side_h),
            (positions[2][0], positions[2][1], card_w, bot_h),
            (positions[3][0], positions[3][1], card_w, side_h),
        ]
        loop_bottom = positions[2][1] + bot_h
        b0, b1, b2, b3 = card_boxes
        arc_specs = [
            ((b0[0] + b0[2] + 8.0, b0[1] + b0[3] * 0.52), (b1[0] + b1[2] * 0.48, b0[1] + b0[3] * 0.52), (b1[0] + b1[2] * 0.48, b1[1] - 8.0)),
            ((b1[0] + b1[2] * 0.48, b1[1] + b1[3] + 8.0), (b1[0] + b1[2] * 0.48, b2[1] + b2[3] * 0.48), (b2[0] + b2[2] + 8.0, b2[1] + b2[3] * 0.48)),
            ((b2[0] - 8.0, b2[1] + b2[3] * 0.48), (b3[0] + b3[2] * 0.52, b2[1] + b2[3] * 0.48), (b3[0] + b3[2] * 0.52, b3[1] + b3[3] + 8.0)),
            ((b3[0] + b3[2] * 0.52, b3[1] - 8.0), (b3[0] + b3[2] * 0.52, b0[1] + b0[3] * 0.52), (b0[0] - 8.0, b0[1] + b0[3] * 0.52)),
        ]
    else:
        top_h = measured_cards[0][0]
        bot_h = max(measured_cards[1][0], measured_cards[2][0])
        cy = c.content_top + top_h + 32.0 + center_r
        positions = [
            (cx - card_w / 2.0, c.content_top),
            (LW - m - card_w, cy + center_r * 0.50),
            (m, cy + center_r * 0.50),
        ]
        card_boxes = [
            (positions[0][0], positions[0][1], card_w, top_h),
            (positions[1][0], positions[1][1], card_w, bot_h),
            (positions[2][0], positions[2][1], card_w, bot_h),
        ]
        loop_bottom = cy + center_r * 0.50 + bot_h
        b0, b1, b2 = card_boxes
        arc_specs = [
            ((b0[0] + b0[2] + 8.0, b0[1] + b0[3] * 0.52), (b1[0] + b1[2] * 0.50, b0[1] + b0[3] * 0.52), (b1[0] + b1[2] * 0.50, b1[1] - 8.0)),
            ((b1[0] - 8.0, b1[1] + b1[3] * 0.50), (cx, b1[1] + b1[3] * 0.68), (b2[0] + b2[2] + 8.0, b2[1] + b2[3] * 0.50)),
            ((b2[0] + b2[2] * 0.50, b2[1] - 8.0), (b2[0] + b2[2] * 0.50, b0[1] + b0[3] * 0.52), (b0[0] - 8.0, b0[1] + b0[3] * 0.52)),
        ]

    arc_color = c.tone("blue")["mark"]
    placed_pills = list(card_boxes) + [(cx - center_r, cy - center_r, center_r * 2.0, center_r * 2.0)]
    n_st = len(stages)
    for i, (start_pt, ctrl_pt, end_pt) in enumerate(arc_specs):
        lk = link_map.get(i, {})
        lbl = str(lk.get("label") or stages[i].get("edge_label") or "").strip()
        rel_obj = {"id": lk.get("id", f"flywheel-{i}"), "from": ids[i],
                   "to": ids[(i + 1) % n_st], "label": lbl, "directed": True}
        c.quad(start_pt, ctrl_pt, end_pt, stroke=arc_color, width=2.0, arrow=True, relation=rel_obj)
        if lbl:
            pw = _diag_tw(lbl, MIN_FONT) + 16.0
            ph = 20.0
            mx_b = 0.25 * start_pt[0] + 0.5 * ctrl_pt[0] + 0.25 * end_pt[0]
            my_b = 0.25 * start_pt[1] + 0.5 * ctrl_pt[1] + 0.25 * end_pt[1]
            cand = (mx_b - pw / 2.0, my_b - ph / 2.0, pw, ph)
            if any(_box_overlap(cand, pb, eps=0.5) for pb in placed_pills):
                for dy in (-16.0, 16.0, -28.0, 28.0):
                    test_c = (mx_b - pw / 2.0, my_b + dy - ph / 2.0, pw, ph)
                    if not any(_box_overlap(test_c, pb, eps=0.5) for pb in placed_pills):
                        cand = test_c
                        break
            cand = (min(max(m, cand[0]), LW - m - pw), cand[1], pw, ph)
            placed_pills.append(cand)
            pacc = c.tone(lk if lk.get("tone") else "blue", fallback="blue")
            c.rect(cand[0], cand[1], pw, ph, pacc["tint"], pacc["border"], 10.0, sw=1.0)
            c.text(cand[0] + pw / 2.0, cand[1] + 13.8, lbl, MIN_FONT, pacc["text"], 700, anchor="middle", check_overlap=False)

    c_spec = spec["center"] if isinstance(spec["center"], dict) else {"label": str(spec["center"])}
    cacc = c.tone(c_spec, fallback="blue")
    end_hub = c.group("center", c_spec, (cx - center_r, cy - center_r, center_r * 2.0, center_r * 2.0), "card")
    c.circle(cx, cy, center_r, cacc["tint"], cacc["border"], sw=1.8, dash="6 4")
    c.circle(cx, cy, center_r - 13.0, c.surf["card"], cacc["solid"], sw=2.0)
    c_trows = _wrap(c_spec["label"], (center_r - 20.0) * 2.0, 14.5)
    c_sub = str(c_spec.get("sublabel") or c_spec.get("detail") or "")
    c_srows = _wrap(c_sub, (center_r - 22.0) * 2.0, MIN_FONT) if c_sub else []
    ty_c = cy - (len(c_trows) * 19.0 + len(c_srows) * 15.0) / 2.0 + 14.0
    for ti, row in enumerate(c_trows):
        c.text(cx, ty_c + ti * 19.0, row, 14.5, c.surf["ink"], 700, anchor="middle", check_overlap=False)
    for si, row in enumerate(c_srows):
        c.text(cx, ty_c + len(c_trows) * 19.0 + si * 15.0, row, MIN_FONT, cacc["text"], 600, anchor="middle", check_overlap=False)
    end_hub()

    for i, (st, (_, body_lines), box_c) in enumerate(zip(stages, measured_cards, card_boxes)):
        px, py, cw_i, ch = box_c
        sid = ids[i]
        sacc = c.tone(st, fallback=c.pal["sequence"][i % len(c.pal["sequence"])])
        end = c.group(sid, st, (px, py, cw_i, ch), "card")
        c.rect(px, py, cw_i, ch, c.surf["card"], sacc["border"], 8.0, sw=1.1)
        c.rect(px, py, cw_i, 34.0, sacc["solid"], "none", 8.0, sw=0.0)
        c.rect(px, py + 24.0, cw_i, 10.0, sacc["solid"], "none", 0.0, sw=0.0)
        c.text(px + 12.0, py + 22.0, str(st["label"]), 13.5, c.surf["card"], 700)
        tag = st.get("tag") or st.get("header_tag")
        if tag:
            c.text(px + cw_i - 12.0, py + 21.5, str(tag), MIN_FONT, c.surf["card"], 600, anchor="end")
        by = py + 51.0
        for bl in body_lines:
            for line in bl:
                c.text(px + 12.0, by, line, BODY_FONT, c.surf["text"], 400)
                by += 17.5
            by += 4.0
        end()
        c.register_box(sid, px, py, cw_i, ch)

    bottom = loop_bottom
    if guardrails:
        bottom += 18.0
        c.line(m, bottom, LW - m, bottom, c.surf["divider"], 0.9, dash="4 3")
        gtitle = str(spec.get("guardrail_title", "飞轮成立的底层约束 / 护栏"))
        c.text(m, bottom + 18.0, gtitle, MIN_FONT, c.surf["muted"], 700)
        bottom += 26.0
        gw = (c.content_width - 14.0 * (len(guardrails) - 1)) / len(guardrails)
        g_wraps, g_heights = [], []
        for g in guardrails:
            drows = _wrap(g.get("detail") or g.get("text") or "", gw - 24.0, BODY_FONT)
            gh = 34.0 + len(drows) * 17.5 + 8.0
            g_wraps.append(drows)
            g_heights.append(gh)
        max_gh = max(g_heights)
        for gi, (g, drows) in enumerate(zip(guardrails, g_wraps)):
            gx = m + gi * (gw + 14.0)
            gid = str(g.get("id", f"guardrail-{gi}"))
            gacc = c.tone(g, fallback="amber")
            end = c.group(gid, g, (gx, bottom, gw, max_gh), "note")
            c.rect(gx, bottom, gw, max_gh, gacc["tint"], gacc["border"], 7.0, sw=1.0)
            c.rect(gx + 1.0, bottom + 5.0, 3.0, max(4.0, max_gh - 10.0), gacc["solid"], "none", 1.5)
            c.text(gx + 12.0, bottom + 22.0, str(g["label"]), 13.0, gacc["text"], 700)
            for di, drow in enumerate(drows):
                c.text(gx + 12.0, bottom + 42.0 + di * 17.5, drow, BODY_FONT, c.surf["text"], 400)
            end()
            c.register_box(gid, gx, bottom, gw, max_gh)
        bottom += max_gh

    return c.finish(bottom)


BUILDERS = {
    "architecture-blueprint": architecture_blueprint,
    "dashboard": dashboard,
    "panorama-mindmap": panorama_mindmap,
    "flywheel": flywheel,
}
