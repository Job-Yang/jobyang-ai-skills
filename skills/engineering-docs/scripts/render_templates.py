#!/usr/bin/env python3
"""Render bounded, data-driven document templates to editable SVG.

Uses the standard library for structural layouts, Matplotlib for quantitative
charts. It does not infer facts or implement an unrestricted graph editor.
"""
import argparse
from copy import deepcopy
import html
import json
import math
from pathlib import Path
import re
import unicodedata
import sys

ASSETS = Path(__file__).resolve().parents[1] / "assets"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from visual_theme import theme_snapshot, layout_tokens, categorical_tone, point_tone, structural_tone, semantic_tone, scheme_tone, colour_scheme, node_surface
THEME = theme_snapshot()
INK, MUTED, LINE = (THEME[k] for k in ("ink", "muted", "line"))
PALETTE = THEME["sequence"]


def tone(index):
    """Compatibility entry for categorical data, not structural node order."""
    return list(categorical_tone(index))


def paint(item):
    """Forward only explicit appearance fields, never labels or ordinal indices."""
    return {k: item[k] for k in ("tone", "status", "emphasis", "role") if k in item} if isinstance(item, dict) else {}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def units(text):
    return sum(1 if unicodedata.east_asian_width(c) in "WF" else .58 for c in str(text))


def wrap(text, width, size):
    lines, line = [], ""
    for char in str(text):
        if char == "\n":
            lines.append(line)
            line = ""
        elif line and units(line + char) * size > width:
            lines.append(line)
            line = char
        else:
            line += char
    return lines + [line]


def _label_left(item):
    """Left edge of a text label for any SVG text-anchor (start/middle/end)."""
    shift = {"middle": item["width"] / 2, "end": item["width"]}.get(item["anchor"], 0)
    return item["x"] - shift


class Canvas:
    """One text budget for measurement, layout and SVG; old 680px calls remain valid."""
    def __init__(self, spec, height=600, width=680):
        check(isinstance(width, (int, float)) and math.isfinite(width) and width >= 320, "Invalid canvas width.")
        self.spec, self.width, self.height, self.parts = spec, width, height, []
        self.tokens = layout_tokens(width)
        self.pad = self.tokens["spacing"]["pad"]
        self.gap = self.tokens["spacing"]["gap"]
        self.section = self.tokens["spacing"]["section"]
        self.margin = self.tokens["spacing"]["margin"]
        self.content_width = width - 2 * self.margin
        self.boxes, self.labels, self.scene_objects = {}, [], {}
        self.scene_graph = {"objects": [], "edges": []}
        y = self.margin + self.size("title")
        y += self.text(self.margin, y, spec["title"], self.size("title"), INK, 600, self.content_width) - self.size("title")
        if spec.get("subtitle"):
            y += self.gap + self.size("body")
            y += self.text(self.margin, y, spec["subtitle"], self.size("body"), MUTED, width=self.content_width) - self.size("body")
        self.content_top = y + self.gap * 2

    def size(self, role):
        return self.tokens["sizes"][role]

    def line_height(self, size):
        role = next((role for role, value in self.tokens["sizes"].items() if math.isclose(value, size)), "body")
        return size * self.tokens["line_height"][role]

    def natural_width(self, title, detail="", *, maximum=None):
        """按已有文字定宽；上限用于长说明换行，不把短标题铺满槽位。"""
        maximum = self.content_width if maximum is None else maximum
        title_width = max((units(line) * self.size("node") for line in str(title).splitlines()), default=0)
        detail_width = max((units(line) * self.size("body") for line in str(detail).splitlines()), default=0)
        minimum = 2 * self.pad + 2 * self.size("node")
        return min(maximum, max(minimum, max(title_width, detail_width) + 2 * self.pad))

    def measure_block(self, title, detail, width):
        """Return the exact rows used by box(), including padding, never truncate."""
        check(width > 2 * self.pad, "Text block too narrow.")
        ts, ds = self.size("node"), self.size("body")
        tr = wrap(title, width - 2 * self.pad, ts)
        dr = wrap(detail, width - 2 * self.pad, ds) if detail else []
        gap = self.gap / 2 if dr else 0
        return {"width": width, "height": 2 * self.pad + len(tr) * self.line_height(ts) + gap + len(dr) * self.line_height(ds),
                "title_rows": tr, "detail_rows": dr, "title_size": ts, "detail_size": ds,
                "line_height": self.tokens["line_height"], "pad": self.pad, "gap": gap}

    def finish(self, bottom):
        note = self.spec.get("note", "")
        reserve = self.gap + self.margin
        if note:
            reserve += len(wrap(note, self.content_width, self.size("caption"))) * self.line_height(self.size("caption")) + self.gap
        if self.spec.get("sample"):
            reserve += self.line_height(self.size("caption")) + self.gap
        self.height = math.ceil(bottom + reserve)
        return self

    def group(self, key, content, geometry, kind="group", members=None):
        key = str(key)
        check(not any(o["id"] == key for o in self.scene_graph["objects"]), f"Duplicate scene ID: {key}")
        self.scene_graph["objects"].append({"id": key, "kind": kind, "geometry": list(geometry), "content": dict(content),
                                           "membership": {"state": "explicit" if members is not None else "unknown", "members": members}})
        label = content.get("title", content.get("label", key))
        self.parts.append(f'<g data-node-id="{html.escape(key, quote=True)}" data-node-label="{html.escape(str(label), quote=True)}">')
        return lambda: self.parts.append('</g>')

    def shape(self, tag, **attrs):
        if tag in {"polygon", "circle", "ellipse"} and attrs.get("stroke") == LINE and attrs.get("fill") not in (None, "none"):
            attrs["stroke"] = THEME["group_border"]
        attrs = {k.replace("_", "-"): v for k, v in attrs.items()}
        self.parts.append("<" + tag + " " + " ".join(
            f'{k}="{html.escape(str(v), quote=True)}"' for k, v in attrs.items()) + "/>")

    def rect(self, x, y, w, h, fill=None, border=LINE, radius=None):
        fill = THEME["paper"] if fill is None else fill
        policy = self.tokens.get("surface_outline", {})
        if policy.get("filled") == "none" and fill not in ("none", "transparent"):
            border = "none"
        border = THEME["group_border"] if border == LINE else border
        semantic = fill in ("none", "transparent")
        width = policy.get("semantic_width" if semantic else "filled_width", self.tokens["line"]["entity"])
        opacity = 1 if semantic else policy.get("filled_opacity", 1)
        self.shape("rect", x=x, y=y, width=w, height=h, rx=self.tokens["radius"]["card"] if radius is None else radius,
                   fill=fill, stroke=border, stroke_width=width, stroke_opacity=opacity)

    def text(self, x, y, value, size=None, color=INK, weight=400, width=None, anchor="start"):
        size = self.size("node") if size is None else size
        width = self.content_width if width is None else width
        rows = wrap(value, width, size)
        for n, row in enumerate(rows):
            yy = y + n * self.line_height(size)
            self.parts.append(f'<text x="{x}" y="{yy}" font-size="{size}" '
                              f'fill="{color}" font-weight="{weight}" text-anchor="{anchor}">'
                              f'{html.escape(row)}</text>')
            self.labels.append({"text": row, "x": x, "y": yy, "size": size,
                                "width": units(row) * size, "anchor": anchor})
        return len(rows) * self.line_height(size)

    def box(self, key, x, y, w, h, title, detail="", index=0, filled=False,
            *, tone=None, status=None, emphasis=False, role=None, default_appearance=None, surface=None):
        appearance = (semantic_tone({"tone": tone, "status": status, "emphasis": emphasis, "role": role})
                      if tone or status or emphasis or role is not None else default_appearance or semantic_tone())
        border = appearance["border"] if emphasis or status or tone in {"success", "warning", "error"} else appearance["entity_border"]
        budget = self.measure_block(title, detail, w)
        h = budget["height"] if h is None else h
        check(h + .5 >= budget["height"], f"Text exceeds box {key}; increase height or split the diagram.")
        self.boxes[str(key)] = (x, y, w, h)
        self.scene_objects[str(key)] = {"title": title, "detail": detail, "tone": tone, "status": status, "emphasis": emphasis, "role": role}
        end = self.group(key, self.scene_objects[str(key)], (x, y, w, h), "card")
        self.rect(x, y, w, h, THEME[surface] if surface is not None else node_surface(appearance), border)
        ty = y + self.pad + budget["title_size"]
        if detail:
            self.text(x + self.pad, ty, title, budget["title_size"], INK, 600, w - 2 * self.pad)
        else:
            self.text(x + w / 2, ty, title, budget["title_size"], INK, 600, w - 2 * self.pad, anchor="middle")
        if detail:
            dy = y + self.pad + len(budget["title_rows"]) * self.line_height(budget["title_size"]) + budget["gap"] + budget["detail_size"]
            self.text(x + self.pad, dy, detail, budget["detail_size"], MUTED, width=w - 2 * self.pad)
        end()
        return h

    def path(self, d, color=LINE, width=None, arrow=False, dash=False, fill="none", *, relation=None):
        width = self.tokens["line"]["normal"] if width is None else width
        attrs = ""
        if relation is not None:
            r = dict(relation)
            r.setdefault("id", f"relation-{len(self.scene_graph['edges'])}")
            r.setdefault("label", "")
            r.setdefault("directed", arrow)
            r["path"] = d
            self.scene_graph["edges"].append(r)
            attrs = " ".join(f'data-edge-{k}="{html.escape(str(v), quote=True)}"' for k, v in
                             {"from": r["from"], "to": r["to"], "key": r["id"], "label": r["label"],
                              "directed": "true" if r["directed"] else "false"}.items())
        self.parts.append(f'<path {attrs} d="{d}" fill="{fill}" stroke="{color}" stroke-width="{width}" '
                          'stroke-linecap="round" stroke-linejoin="round" '
                          + ('marker-end="url(#arrow)" ' if arrow else "")
                          + ('stroke-dasharray="5 4" ' if dash else "") + "/>")

    def label(self, x, y, text, *, width=None):
        size = self.size("caption")
        text_width = max(size, min(units(text) * size, width) if width is not None else units(text) * size)
        rows = wrap(text, text_width, size)
        w = text_width + self.pad
        self.rect(x - w / 2, y - size, w, self.line_height(size) * max(1, len(rows)), THEME["paper"], "none", 3)
        self.text(x, y, text, size, anchor="middle", width=text_width)

    def save(self, path):
        note, caption = self.spec.get("note", ""), self.size("caption")
        y = self.height - self.margin
        if self.spec.get("sample"):
            self.text(self.margin, y, "合成示例", caption, MUTED)
            y -= self.line_height(caption) + self.gap
        if note:
            y -= (len(wrap(note, self.content_width, caption)) - 1) * self.line_height(caption)
            self.text(self.margin, y, note, caption, MUTED, width=self.content_width)
        content_bottom = y - self.gap - caption if note or self.spec.get("sample") else self.height - self.margin
        for key, (x, by, w, h) in self.boxes.items():
            check(x >= self.margin - 8 and x+w <= self.width-self.margin+8 and by >= self.content_top-1 and by+h <= content_bottom+1,
                  f"Box outside content area: {key}")
            for other, (ox, oy, ow, oh) in self.boxes.items():
                if key < other:
                    check(min(x+w, ox+ow) <= max(x, ox) or min(by+h, oy+oh) <= max(by, oy),
                          f"Overlapping boxes: {key}, {other}; split the diagram.")
        for item in self.labels:
            left = _label_left(item)
            check(left >= 8 and left + item["width"] <= self.width-8, f"Label out of bounds: {item['text']}")
            check(0 < item["y"] <= self.height - 5, f"Vertical overflow: {item['text']}")
        for i, a in enumerate(self.labels):
            ax = _label_left(a)
            for b in self.labels[i+1:]:
                bx = _label_left(b)
                check(min(ax+a["width"], bx+b["width"]) <= max(ax,bx)
                      or min(a["y"]+2,b["y"]+2) <= max(a["y"]-a["size"],b["y"]-b["size"]),
                      f"Text labels overlap: {a['text']} / {b['text']}")
        font = html.escape(self.tokens["fonts"]["sans"], quote=True)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
               f'viewBox="0 0 {self.width} {self.height}" role="img"><title>{html.escape(self.spec["title"])}</title>'
               f'<desc>{html.escape(note)}</desc><defs><marker id="arrow" viewBox="0 0 10 10" '
               'refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
               f'<path d="M1 1 L8 5 L1 9" fill="none" stroke="{LINE}" stroke-width="1.5"/>'
               f'</marker></defs><rect width="{self.width}" height="100%" fill="{THEME["canvas_bg"]}"/>'
               f'<g font-family="{font}">' + "".join(self.parts) + "</g></svg>\n")
        path.write_text(svg)
        compiled = {"boxes": self.boxes, "labels": self.labels, "scene_objects": self.scene_objects, "scene_graph": self.scene_graph, "width": self.width, "height": self.height}
        if hasattr(self, "supplemental"):
            compiled["supplemental"] = deepcopy(self.supplemental)
        return compiled


def _canvas(spec):
    return Canvas(spec, width=spec.get("canvas_width", 680))


def _detail(item):
    detail = item.get("detail", "")
    check(isinstance(detail, str), "detail must be text.")
    items = item.get("items", [])
    check(isinstance(items, list) and all(isinstance(v, str) for v in items), "items must be text; use children for nested members.")
    return "\n".join(([detail] if detail else []) + items)


def _members(items, prefix, depth=0, seen=None, budget=None):
    """Bounded explicit containment; string members remain backwards compatible."""
    seen = set() if seen is None else seen
    budget = [0] if budget is None else budget
    check(isinstance(items, list) and 1 <= len(items) <= 9, "Use 1–9 explicit members per group.")
    check(depth <= 2, "Split nesting deeper than three member levels.")
    result = []
    for i, value in enumerate(items):
        check(isinstance(value, (str, dict)), "Members must be text or objects.")
        item = {"label": value} if isinstance(value, str) else dict(value)
        check(isinstance(item.get("label"), str) and item["label"], "Member label required.")
        key = str(item.get("id", f"{prefix}-{i}"))
        check(key not in seen, f"Duplicate member ID: {key}")
        seen.add(key)
        budget[0] += 1
        check(budget[0] <= 54, "Split more than 54 members.")
        item["id"] = key
        if item.get("children"):
            item["children"] = _members(item["children"], key, depth+1, seen, budget)
        else:
            item["children"] = []
        _detail(item)
        result.append(item)
    return result


def _member_rows(c, children, width, compact=False):
    rows, row, occupied = [], [], 0
    for child in children:
        child_width = _member_width(c, child, width, compact)
        if row and (not compact or occupied + c.gap + child_width > width + .01):
            rows.append(row)
            row, occupied = [], 0
        row.append((child, child_width))
        occupied += (c.gap if len(row) > 1 else 0) + child_width
    if row:
        rows.append(row)
    return rows


def _member_width(c, item, maximum, compact=False):
    width = c.natural_width(item["label"], _detail(item), maximum=maximum)
    if item["children"]:
        child_widths = [_member_width(c, child, maximum-2*c.pad, compact) for child in item["children"]]
        needed = sum(child_widths)+c.gap*(len(child_widths)-1) if compact else max(child_widths)
        width = min(maximum, max(width, needed+2*c.pad))
    return width


def _member_height(c, item, width, compact=False):
    h = c.measure_block(item["label"], _detail(item), width)["height"]
    if item["children"]:
        rows = _member_rows(c, item["children"], width-2*c.pad, compact)
        h += sum(max(_member_height(c, child, cw, compact) for child, cw in row) for row in rows)+c.gap*len(rows)+c.pad
    return h


def _draw_member(c, item, x, y, width, inherited=None, default_appearance=None, compact=False):
    detail, children = _detail(item), item["children"]
    appearance = {**(inherited or {}), **paint(item)}
    explicit = any(appearance.get(k) for k in ("tone", "status", "emphasis")) or appearance.get("role") is not None
    if not children:
        natural = c.natural_width(item["label"], detail, maximum=width)
        x, width = x + (width - natural) / 2, natural
        return c.box(item["id"], x, y, width, None, item["label"], detail, **appearance,
                     default_appearance=default_appearance)
    height = _member_height(c, item, width, compact)
    end = c.group(item["id"], item, (x, y, width, height), members=[ch["id"] for ch in children])
    t = semantic_tone(appearance) if explicit else default_appearance or semantic_tone()
    c.rect(x, y, width, height, t["tint"], t["entity_border"])
    yy = y+c.pad+c.size("node")
    c.text(x+c.pad if detail else x+width/2, yy, item["label"], c.size("node"), weight=600,
           width=width-2*c.pad, anchor="start" if detail else "middle")
    if detail:
        yy += len(wrap(item["label"], width-2*c.pad, c.size("node")))*c.line_height(c.size("node"))-c.size("node")+c.gap/2+c.size("body")
        c.text(x+c.pad, yy, detail, c.size("body"), MUTED, width=width-2*c.pad)
    yy = y+c.measure_block(item["label"], detail, width)["height"]
    for row in _member_rows(c, children, width-2*c.pad, compact):
        yy += c.gap
        occupied = sum(cw for _, cw in row)+c.gap*(len(row)-1)
        xx = x+(width-occupied)/2
        for child, child_width in row:
            _draw_member(c, child, xx, yy, child_width, appearance, default_appearance, compact)
            xx += child_width+c.gap
        yy += max(_member_height(c, child, cw, compact) for child, cw in row)
    end()
    return height


def layers(spec):
    groups = spec["groups"]
    check(1 <= len(groups) <= 6, "Use 1–6 layers.")
    c, seen, budget = _canvas(spec), set(), [0]
    prepared = []
    for i, g in enumerate(groups):
        key = str(g.get("id", f"layer{i}"))
        check(key not in seen, f"Duplicate group ID: {key}")
        seen.add(key)
        items = _members(g["items"], f"g{i}", seen=seen, budget=budget)
        nested = [it for it in items if it["children"]]
        leaves = [it for it in items if not it["children"]]
        # Short independent responsibilities get their own cap row, not a tall
        # empty column between child-bearing responsibilities. Membership is unchanged.
        batches = [(leaves, 3), (nested, 2)] if nested and leaves else [(items, 3)]
        rows, widths = [], {}
        for batch, limit in batches:
            cols = min(limit, len(batch))
            maximum = (c.content_width-2*c.pad-c.gap*(cols-1))/cols
            batch_widths = {it["id"]: _member_width(c, it, maximum, True) for it in batch}
            heights = [_member_height(c, it, batch_widths[it["id"]], True) for it in batch]
            if nested and max(heights)-min(heights) > c.section*4:
                # Highly uneven nested content uses full-width responsibility
                # rows, instead of relocating a tall sibling hole to the footer.
                cols, maximum = 1, c.content_width-2*c.pad
                batch_widths = {it["id"]: _member_width(c, it, maximum, True) for it in batch}
            widths.update(batch_widths)
            rows.extend(batch[r:r+cols] for r in range(0, len(batch), cols))
        row_width = max(sum(widths[it["id"]] for it in row)+c.gap*(len(row)-1) for row in rows)
        needed = max(row_width+2*c.pad, c.natural_width(g["label"], g.get("detail", "")))
        prepared.append((key, g, items, rows, widths, needed))
    group_width = min(c.content_width, max(p[-1] for p in prepared))
    x, inner, y = (c.width-group_width)/2, group_width-2*c.pad, c.content_top
    for i, (key, g, items, rows, widths, _) in enumerate(prepared):
        head = c.measure_block(g["label"], g.get("detail", ""), group_width)["height"]
        heights = [max(_member_height(c, it, widths[it["id"]], True) for it in row) for row in rows]
        height = head+sum(heights)+c.gap*len(rows)+c.pad
        default = scheme_tone("layers", "layer", i, item=g)
        dark, light = default["entity_border"], default["tint"]
        end = c.group(key, g, (x, y, group_width, height), members=[it["id"] for it in items])
        c.rect(x, y, group_width, height, light, dark)
        detail = g.get("detail", "")
        c.text(x+c.pad if detail else x+group_width/2, y+c.pad+c.size("node"), g["label"], c.size("node"),
               weight=600, width=inner, anchor="start" if detail else "middle")
        if detail:
            title_h = len(wrap(g["label"], inner, c.size("node")))*c.line_height(c.size("node"))
            c.text(x+c.pad, y+c.pad+title_h+c.gap/2+c.size("body"), detail, c.size("body"), MUTED, width=inner)
        yy = y+head
        for row, rh in zip(rows, heights):
            yy += c.gap
            occupied = sum(widths[it["id"]] for it in row)+c.gap*(len(row)-1)
            xx = x+c.pad+(inner-occupied)/2
            for item in row:
                width = widths[item["id"]]
                _draw_member(c, item, xx, yy, width, paint(g), default, True)
                xx += width+c.gap
            yy += rh
        end()
        y += height+c.gap
    return c.finish(y-c.gap)


def grid(spec):
    groups, columns = spec["groups"], spec.get("columns", 2)
    check(columns in (2, 3) and 1 <= len(groups) <= 12, "Grid supports 2–3 columns and at most 12 groups.")
    c, seen, budget = _canvas(spec), set(), [0]
    width = (c.content_width-c.gap*(columns-1))/columns
    ys = [c.content_top]*columns
    for i, g in enumerate(groups):
        col, key = i % columns, str(g.get("id", f"grid{i}"))
        check(key not in seen, f"Duplicate group ID: {key}")
        seen.add(key)
        items = _members(g["items"], f"grid{i}-member", seen=seen, budget=budget)
        head = c.measure_block(g["label"], g.get("detail", ""), width)["height"]
        height = head + sum(_member_height(c, it, width-2*c.pad) for it in items) + c.gap*len(items)+c.pad
        x, y = c.margin+col*(width+c.gap), ys[col]
        capacity = len(colour_scheme("grid")["module"])
        default = scheme_tone("grid", "module", i, item=g) if i < capacity else scheme_tone("grid", "group", item=g)
        dark, light = default["entity_border"], default["tint"]
        end = c.group(key, g, (x, y, width, height), members=[it["id"] for it in items])
        c.rect(x, y, width, height, light, dark)
        c.text(x+c.pad, y+c.pad+c.size("node"), g["label"], c.size("node"), weight=600, width=width-2*c.pad)
        if g.get("detail"):
            th = len(wrap(g["label"], width-2*c.pad, c.size("node")))*c.line_height(c.size("node"))
            c.text(x+c.pad, y+c.pad+th+c.gap/2+c.size("body"), g["detail"], c.size("body"), MUTED, width=width-2*c.pad)
        yy = y+head
        for item in items:
            yy += c.gap
            yy += _draw_member(c, item, x+c.pad, yy, width-2*c.pad, paint(g), default)
        end()
        ys[col] += height+c.gap
    return c.finish(max(ys)-c.gap)


def tree(spec):
    nodes = spec["nodes"]
    check(1 <= len(nodes) <= 20, "Tree supports 1–20 nodes.")
    lookup = {n["id"]: n for n in nodes}
    check(len(lookup) == len(nodes), "Duplicate tree IDs.")
    children, roots = {key: [] for key in lookup}, []
    for n in nodes:
        if n.get("parent") is None:
            roots.append(n["id"])
        else:
            check(n["parent"] in lookup, "Unknown parent.")
            children[n["parent"]].append(n["id"])
    check(len(roots) == 1, "A hierarchy needs exactly one root.")
    order, visited, leaves = [], set(), {}
    def walk(key, depth):
        check(key not in visited, "Cycle in hierarchy.")
        visited.add(key)
        order.append((key, depth))
        for child in children[key]:
            walk(child, depth+1)
        leaves[key] = sum(leaves[k] for k in children[key]) if children[key] else 1
    walk(roots[0], 0)
    check(len(visited) == len(nodes), "Disconnected hierarchy or cycle.")
    count = leaves[roots[0]]
    check(count <= 6, "More than 6 leaves needs a focused diagram.")
    c = _canvas(spec)
    leaf_width = min(200*c.width/680, (c.content_width-c.gap*(count-1))/count)
    widths, heights, spans = {}, {}, {}
    for key, _ in reversed(order):
        spans[key] = sum(spans[k] for k in children[key])+c.gap*(len(children[key])-1) if children[key] else leaf_width
        widths[key] = min(200*c.width/680, spans[key])
        budget = c.measure_block(lookup[key]["label"], lookup[key].get("detail", ""), widths[key])
        check(len(budget["title_rows"]) <= 12, "Long tree label needs a focused diagram.")
        heights[key] = budget["height"]
    xs = {}
    def place(key, left):
        xs[key] = left+spans[key]/2
        for child in children[key]:
            place(child, left)
            left += spans[child]+c.gap
    place(roots[0], (c.width-spans[roots[0]])/2)
    levels = max(d for _, d in order)+1
    level_h = [max(heights[k] for k, d in order if d == level) for level in range(levels)]
    ys = [c.content_top]
    for height in level_h[:-1]:
        ys.append(ys[-1]+height+c.gap*3)
    for key, depth in order:
        c.box(key, xs[key]-widths[key]/2, ys[depth], widths[key], None, lookup[key]["label"], lookup[key].get("detail", ""), **paint(lookup[key]))
    for key, _ in order:
        for child in children[key]:
            x1, y1, w1, h1 = c.boxes[key]
            x2, y2, w2, _ = c.boxes[child]
            mid = (y1+h1+y2)/2
            c.path(f"M{x1+w1/2} {y1+h1} V{mid} H{x2+w2/2} V{y2}", relation={"from": key, "to": child, "kind": "hierarchy", "directed": False})
    return c.finish(ys[-1]+level_h[-1])


def mindmap(spec):
    groups = spec["groups"]
    check(2 <= len(groups) <= 6, "Mindmap supports 2–6 branches.")
    c = _canvas(spec)
    root = spec["center"] if isinstance(spec["center"], dict) else {"label": spec["center"]}
    rw = min(c.content_width*.29, max(units(root["label"])*c.size("node")+2*c.pad, c.content_width*.20))
    bw = (c.content_width-rw-4*c.gap)/2
    hs = [c.measure_block(g["label"], _detail(g), bw)["height"] for g in groups]
    rh = c.measure_block(root["label"], root.get("detail", ""), rw)["height"]
    side_heights = [sum(hs[j] for j in range(side, len(groups), 2))+c.gap*2*(len(groups[side::2])-1) for side in (0, 1)]
    total = max(rh, *side_heights)
    cy = c.content_top+total/2
    c.box("root", (c.width-rw)/2, cy-rh/2, rw, None, root["label"], root.get("detail", ""), **paint(spec))
    ys = [c.content_top+(total-sh)/2 for sh in side_heights]
    for i, g in enumerate(groups):
        side, height = i % 2, hs[i]
        x, y = (c.width-c.margin-bw if side else c.margin), ys[side]
        c.box(f"branch{i}", x, y, bw, None, g["label"], _detail(g), **paint(g))
        a, b = ((c.width+rw)/2, x) if side else ((c.width-rw)/2, x+bw)
        c.path(f"M{a} {cy} C{(a+b)/2} {cy} {(a+b)/2} {y+height/2} {b} {y+height/2}", relation={"from": "root", "to": f"branch{i}", "kind": "association", "directed": False})
        ys[side] += height+c.gap*2
    return c.finish(c.content_top+total)


def timeline(spec):
    events, vertical = spec["events"], spec.get("orientation") == "vertical"
    check(2 <= len(events) <= (8 if vertical else 4), "Split timeline into readable panels.")
    check(all(isinstance(e.get("at"), (int, float)) and not isinstance(e["at"], bool) for e in events), "Numeric timeline at must be numeric; use typed timeline for ISO dates.")
    values = [float(e["at"]) for e in events]
    check(all(math.isfinite(v) for v in values) and values == sorted(set(values)), "Timeline times must be finite, unique and ascending.")
    c, lo, hi = _canvas(spec), values[0], values[-1]
    unit = spec.get("unit", "")
    check(isinstance(unit, str), "Timeline unit must be text.")
    if vertical:
        bw, cx = (c.content_width-6*c.gap)/2, c.width/2
        hs = [c.measure_block(e["label"], e.get("detail", ""), bw)["height"] for e in events]
        span = max(c.content_width*.6, max((((hs[i]+hs[j])/2+c.gap*2)*(hi-lo)/(values[j]-values[i]) for i in range(len(events)) for j in range(i+1, len(events)) if i%2 == j%2), default=0))
        y0 = c.content_top+max(hs)/2+c.line_height(c.size("caption"))
        c.path(f"M{cx} {y0} V{y0+span}")
        for i, (e, v, h) in enumerate(zip(events, values, hs)):
            y, side = y0+(v-lo)/(hi-lo)*span, i%2
            x = c.width-c.margin-bw if side else c.margin
            c.box(f"event{i}", x, y-h/2, bw, None, e["label"], e.get("detail", ""), **paint(e))
            c.path(f"M{cx} {y} H{x if side else x+bw}")
            c.shape("circle", cx=cx, cy=y, r=5*c.width/680, fill=structural_tone(e)[1], stroke=structural_tone(e)[0])
            c.label(cx, y-c.gap, f"{v:g}{(' '+unit) if unit else ''}")
        bottom = y0+span+max(hs)/2
    else:
        bw = c.content_width*.27
        hs = [c.measure_block(e["label"], e.get("detail", ""), bw)["height"] for e in events]
        upper = max(hs[::2])
        axis = c.content_top+upper+c.gap*3
        positions = [c.margin+bw/2+(v-lo)/(hi-lo)*(c.content_width-bw) for v in values]
        c.path(f"M{positions[0]} {axis} H{positions[-1]}")
        for i, (e, x, h) in enumerate(zip(events, positions, hs)):
            y = axis-c.gap*3-h if i%2 == 0 else axis+c.gap*3
            c.box(f"event{i}", x-bw/2, y, bw, None, e["label"], e.get("detail", ""), **paint(e))
            c.path(f"M{x} {axis} V{y+h if i%2 == 0 else y}")
            c.shape("circle", cx=x, cy=axis, r=5*c.width/680, fill=structural_tone(e)[1], stroke=structural_tone(e)[0])
            c.label(x, axis+c.gap*1.6, f"{values[i]:g}{(' '+unit) if unit else ''}")
        bottom = axis+c.gap*3+max(hs[1::2])
    return c.finish(bottom)


def stages(spec):
    groups = spec["groups"]
    check(2 <= len(groups) <= 6, "Use 2–6 stages.")
    c, y = _canvas(spec), None
    y = c.content_top
    band = c.content_width*.25
    for i, g in enumerate(groups):
        detail = _detail(g)
        h = max(c.measure_block(g["label"], "", band-c.pad)["height"], 2*c.pad+len(wrap(detail, c.content_width-band-c.gap, c.size("body")))*c.line_height(c.size("body")))
        dark, light = structural_tone(g)
        end = c.group(f"stage{i}", g, (c.margin, y, c.content_width, h), "stage")
        c.shape("polygon", points=f"{c.margin},{y} {c.margin+band-c.gap},{y} {c.margin+band},{y+h/2} {c.margin+band-c.gap},{y+h} {c.margin},{y+h}", fill=light, stroke=dark)
        c.text(c.margin+c.pad, y+c.pad+c.size("node"), g["label"], c.size("node"), weight=600, width=band-3*c.pad)
        # Existing outcomes are shown as text, not promoted to a fabricated subtitle.
        if detail:
            c.text(c.margin+band+c.gap, y+c.pad+c.size("body"), detail, c.size("body"), width=c.content_width-band-c.gap)
        end()
        if i+1 < len(groups):
            c.path(f"M{c.margin+band/2} {y+h} V{y+h+c.gap}", arrow=True, relation={"from": f"stage{i}", "to": f"stage{i+1}", "kind": "stage-order"})
        y += h+c.gap
    return c.finish(y-c.gap)


def cycle(spec):
    groups = spec["groups"]
    check(len(groups) in (3, 4), "Cycle supports 3–4 stages; larger cycles should be split.")
    c = _canvas(spec)
    bw = c.content_width*.26
    hs = [c.measure_block(g["label"], _detail(g), bw)["height"] for g in groups]
    radius = c.content_width*.19
    cx = c.width/2
    cy = c.content_top+hs[0]+radius+c.gap*2
    positions = [(cx, c.content_top+hs[0]/2), (c.width-c.margin-bw/2, cy), (cx, cy+radius+c.gap*2+max(hs)/2), (c.margin+bw/2, cy)] if len(groups)==4 else [(cx, c.content_top+hs[0]/2), (c.width-c.margin-bw/2, cy+radius*.8), (c.margin+bw/2, cy+radius*.8)]
    center = spec["center"] if isinstance(spec["center"], dict) else {"label": spec["center"]}
    cw = radius*1.55
    budget = c.measure_block(center["label"], center.get("detail", ""), cw)
    c.text(cx, cy-budget["height"]/2+c.pad+c.size("node"), center["label"], c.size("node"), weight=600, anchor="middle", width=cw-2*c.pad)
    if center.get("detail"):
        yy = cy-budget["height"]/2+c.pad+len(budget["title_rows"])*c.line_height(c.size("node"))+c.gap/2+c.size("body")
        c.text(cx, yy, center["detail"], c.size("body"), MUTED, anchor="middle", width=cw-2*c.pad)
    links = spec.get("links", [])
    check(isinstance(links, list), "Cycle links must be a list.")
    ids = [str(g.get("id", f"cycle{i}")) for i,g in enumerate(groups)]
    check(len(set(ids)) == len(ids), "Duplicate cycle IDs.")
    explicit = {}
    for link in links:
        check(link.get("from") in ids and link.get("to") in ids, "Unknown cycle link endpoint.")
        k = ids.index(link["from"])
        check(link["to"] == ids[(k+1)%len(ids)] and k not in explicit, "Cycle links must describe each next-stage edge once.")
        check(isinstance(link.get("label", ""), str), "Cycle edge label must be text.")
        explicit[k] = link
    for i, g in enumerate(groups):
        angle = -90+i*360/len(groups)
        xy = lambda a, r: (cx+r*math.cos(math.radians(a)), cy+r*math.sin(math.radians(a)))
        stage = scheme_tone("cycle", "stage", i, item=g)
        ring = scheme_tone("cycle", "ring", item=spec)
        thickness = c.pad*1.05
        outer, inner = radius+thickness/2, radius-thickness/2
        start, end_angle = angle+18, angle+360/len(groups)-18
        neck = end_angle-math.degrees(c.pad*1.8/radius)
        point = lambda a, r: " ".join(map(str, xy(a, r)))
        # A closed annular ribbon and its arrowhead are one filled face. The
        # reverse inner arc closes it; no backing stroke or central line remains.
        d = (f"M{point(start, outer)} A{outer} {outer} 0 0 1 {point(neck, outer)} "
             f"L{point(neck, radius+thickness)} L{point(end_angle, radius)} "
             f"L{point(neck, radius-thickness)} L{point(neck, inner)} "
             f"A{inner} {inner} 0 0 0 {point(start, inner)} Z")
        link = explicit.get(i, {})
        c.path(d, "none", fill=ring["solid"], relation={**link, "from": ids[i], "to": ids[(i+1)%len(ids)], "kind": "cycle-next", "directed": True, "label": link.get("label", ""), "assumption": link.get("assumption", spec.get("assumption", False))})
        x,y = positions[i]
        c.box(ids[i], x-bw/2, y-hs[i]/2, bw, None, g["label"], _detail(g), **paint(g), default_appearance=stage)
        if link.get("label"):
            label = ("假设：" if link.get("assumption", spec.get("assumption")) else "")+link["label"]
            label_h = len(wrap(label, bw, c.size("caption")))*c.line_height(c.size("caption"))
            mid = angle+180/len(groups)
            # Reserve the entire rectangular caption outside the ribbon, not
            # just its center. Horizontal extents matter on diagonal segments.
            label_w = min(units(label)*c.size("caption"), bw)+c.pad
            support = abs(math.cos(math.radians(mid)))*label_w/2+abs(math.sin(math.radians(mid)))*label_h/2
            lx,ly = xy(mid, radius+thickness+support+c.gap*2)
            c.label(lx, ly, label, width=bw)
    bottom = max(max(y+h/2 for (x,y),h in zip(positions, hs)), max((l["y"]+c.gap for l in c.labels), default=0))
    return c.finish(bottom)


def pyramid(spec):
    groups = spec["groups"]
    check(3 <= len(groups) <= 6, "Use 3–6 pyramid levels.")
    c, y = _canvas(spec), None
    y = c.content_top
    cx = c.margin+c.content_width*.34
    base = c.content_width*.60
    side_x = c.margin+c.content_width*.68
    side_w = c.width-c.margin-side_x
    half, n = base/2, len(groups)
    budgets = []
    for i,g in enumerate(groups):
        text_w = base*(i+.72)/n+2*c.pad
        detail = _detail(g)
        inline = i > 0 and len(wrap(detail, text_w-2*c.pad, c.size("body"))) <= 2
        budget = c.measure_block(g["label"], detail if inline else "", text_w)
        budgets.append((text_w, inline, budget))
    # Only internal text sets one common tier height. External annotations have
    # a separate column budget and can extend the canvas, never a single tier.
    apex_rows = len(budgets[0][2]["title_rows"])
    h = max(c.size("node")*7, (apex_rows*c.line_height(c.size("node"))+c.pad)/.28,
            max(b["height"]+c.line_height(c.size("caption"))+c.gap for _,_,b in budgets))
    origin_y, total_height = y, h*n
    side_bottom = y
    for i,(g,(text_w,inline,budget)) in enumerate(zip(groups,budgets)):
        top, bottom = half*i/n, half*(i+1)/n
        appearance = scheme_tone("pyramid", "layer", i, item=g)
        dark, light = appearance["entity_border"], appearance["tint"]
        key = str(g.get("id", f"pyramid{i}"))
        end = c.group(key, g, (cx-bottom, y, bottom*2, h), "level")
        c.shape("polygon", points=f"{cx-top},{y} {cx+top},{y} {cx+bottom},{y+h} {cx-bottom},{y+h}", fill=light, stroke=dark)
        detail = _detail(g)
        ty = y+h*.72 if i == 0 else y+(h-budget["height"])/2+c.pad+c.size("node")
        ordinal_y = y+h*.28 if i == 0 else ty-c.size("node")-c.gap
        c.text(cx, ordinal_y, str(i+1), c.size("caption"), MUTED, anchor="middle", width=c.pad*3)
        c.text(cx, ty, g["label"], c.size("node"), weight=600, anchor="middle", width=text_w-2*c.pad)
        if inline and detail:
            dy = ty-c.size("node")+len(budget["title_rows"])*c.line_height(c.size("node"))+c.gap/2+c.size("body")
            c.text(cx, dy, detail, c.size("body"), MUTED, anchor="middle", width=text_w-2*c.pad)
        elif detail:
            side_h = len(wrap(detail, side_w, c.size("body")))*c.line_height(c.size("body"))
            note_top = max(ty-c.size("node"), side_bottom)
            edge_x = cx+half*(ty-origin_y)/total_height
            c.path(f"M{edge_x} {ty} H{side_x-c.gap*2} V{note_top+c.size('body')} H{side_x-c.gap}")
            c.text(side_x, note_top+c.size("body"), detail, c.size("body"), MUTED, width=side_w)
            side_bottom = note_top+side_h+c.gap
        end()
        y += h
    return c.finish(max(y, side_bottom))


def house(spec):
    pillars = spec["pillars"]
    check(2 <= len(pillars) <= 4, "Use 2–4 pillars.")
    c = _canvas(spec)
    roof = spec["roof"] if isinstance(spec["roof"], dict) else {"label":spec["roof"]}
    promise = spec["promise"] if isinstance(spec["promise"], dict) else {"label":spec["promise"]}
    foundation = spec["foundation"] if isinstance(spec["foundation"], dict) else {"label":spec["foundation"]}
    maximum = (c.content_width - c.gap * (len(pillars) - 1)) / len(pillars)
    pillar_width = sum(c.natural_width(p["label"], _detail(p), maximum=maximum) for p in pillars) + c.gap * (len(pillars) - 1)
    w = min(c.content_width, max(pillar_width, *(c.natural_width(p["label"], p.get("detail", "")) for p in (roof, promise, foundation))))
    x, y = (c.width - w) / 2, c.content_top
    roof_w = w*.80
    rb = c.measure_block(roof["label"], roof.get("detail", ""), roof_w)
    roof_h = rb["height"]*1.9
    end = c.group("house-roof", roof, (x,y,w,roof_h), "roof")
    appearance = scheme_tone("house", "roof", item=roof)
    dark,light = appearance["entity_border"], appearance["tint"]
    c.shape("polygon", points=f"{x},{y+roof_h} {x+w/2},{y} {x+w},{y+roof_h}", fill=light, stroke=dark)
    # Text is in the broad lower part of the roof, never near the narrow apex.
    ty = y+roof_h-rb["height"]+c.pad+c.size("node")
    c.text(x+w/2,ty,roof["label"],c.size("node"),weight=600,anchor="middle",width=roof_w-2*c.pad)
    if roof.get("detail"):
        c.text(x+w/2,ty-c.size("node")+len(rb["title_rows"])*c.line_height(c.size("node"))+c.gap/2+c.size("body"),roof["detail"],c.size("body"),MUTED,anchor="middle",width=roof_w-2*c.pad)
    end()
    y += roof_h
    for key,value in (("house-promise",spec["promise"]),):
        item = value if isinstance(value,dict) else {"label":value}
        h = c.box(key,x,y,w,None,item["label"],item.get("detail",""),**paint(item),default_appearance=scheme_tone("house", "claim", item=item))
        y += h+c.gap
    pw = (w-c.gap*(len(pillars)-1))/len(pillars)
    hs = [c.measure_block(p["label"],_detail(p),pw)["height"] for p in pillars]
    ph = max(hs)
    for i,p in enumerate(pillars):
        # Structural columns share a foundation; content occupies its measured cap.
        xx = x+i*(pw+c.gap)
        end = c.group(f"pillar{i}",p,(xx,y,pw,ph),"pillar")
        appearance = scheme_tone("house", "pillar", i, item=p)
        dark,light = appearance["entity_border"], appearance["tint"]
        c.rect(xx,y,pw,ph,light,dark,0)
        budget = c.measure_block(p["label"],_detail(p),pw)
        c.text(xx+pw/2,y+c.pad+c.size("node"),p["label"],c.size("node"),weight=600,anchor="middle",width=pw-2*c.pad)
        if _detail(p):
            detail = _detail(p)
            short = all(units(line)*c.size("body") <= (pw-2*c.pad)*.72 for line in detail.split("\n"))
            c.text(xx+pw/2 if short else xx+c.pad,
                   y+c.pad+len(budget["title_rows"])*c.line_height(c.size("node"))+c.gap/2+c.size("body"),
                   detail,c.size("body"),MUTED,width=pw-2*c.pad,anchor="middle" if short else "start")
        end()
    y += ph+c.gap
    foundation = spec["foundation"] if isinstance(spec["foundation"],dict) else {"label":spec["foundation"]}
    h = c.box("house-foundation",x,y,w,None,foundation["label"],foundation.get("detail",""),**paint(foundation),default_appearance=scheme_tone("house", "foundation", item=foundation))
    return c.finish(y+h)


def matrix(spec):
    rows, cols = spec["rows"], spec["columns"]
    check(1 <= len(rows) <= 8 and 2 <= len(cols) <= 4, "Matrix supports up to 8×4 cells.")
    values = spec["values"]
    check(len(values) == len(rows) and all(len(r) == len(cols) for r in values), "Matrix dimensions do not match.")
    c = _canvas(spec)
    header_size = max(15, c.size("node"))  # Preserve historical 15px headings.
    heading_width = lambda text, maximum: min(maximum, max(c.natural_width(text, maximum=maximum), max(units(row)*header_size for row in str(text).split("\n"))+2*c.pad))
    row_w = max(heading_width(row, c.content_width*.26) for row in rows)
    maximum = (c.content_width-row_w-c.gap*len(cols))/len(cols)
    w = max(max(heading_width(col, maximum) for col in cols), max(c.natural_width(v, maximum=maximum) for row in values for v in row))
    occupied = row_w+len(cols)*(w+c.gap)
    x, y = (c.width-occupied)/2+row_w+c.gap, c.content_top
    head = max(2*c.pad+len(wrap(col, w-2*c.pad, header_size))*c.line_height(header_size) for col in cols)
    header = semantic_tone({"tone": "accent"})
    for j, col in enumerate(cols):
        xx = x+j*(w+c.gap)
        c.rect(xx, y, w, head, header["tint"], header["entity_border"], 4)
        c.text(xx+w/2, y+c.pad+header_size, col, header_size, weight=600, anchor="middle", width=w-2*c.pad)
    y += head+c.gap
    for i, row in enumerate(rows):
        row_h = 2*c.pad+len(wrap(row, row_w-2*c.pad, header_size))*c.line_height(header_size)
        h = max(row_h, *(c.measure_block(v, "", w)["height"] for v in values[i]))
        c.text(x-c.gap-row_w+c.pad, y+c.pad+header_size, row, header_size, weight=600, width=row_w-2*c.pad)
        for j, value in enumerate(values[i]):
            xx = x+j*(w+c.gap)
            end = c.group(f"cell-{i}-{j}", {"title": f"{row} / {cols[j]}", "row": row, "column": cols[j], "value": value},
                          (xx, y, w, h), "cell")
            c.rect(xx, y, w, h, THEME["entity_fill"], THEME["entity_border"], 4)
            c.text(xx+c.pad, y+c.pad+c.size("node"), value, c.size("node"), width=w-2*c.pad)
            end()
        y += h+c.gap
    return c.finish(y-c.gap)


def workflow(spec):
    lanes, nodes, edges = spec["lanes"], spec["nodes"], spec["edges"]
    vertical = spec.get("orientation", "vertical") == "vertical"
    check(bool(nodes), "Workflow needs nodes.")
    check(all(isinstance(n["step"], int) and n["step"] >= 0
              and isinstance(n["lane"], int) for n in nodes), "Invalid lane or step.")
    check(len({(n["lane"], n["step"]) for n in nodes}) == len(nodes),
          "Only one activity is allowed per lane and step.")
    ids = {n["id"] for n in nodes}
    check(len(ids) == len(nodes), "Duplicate workflow IDs.")
    check(all(e["from"] in ids and e["to"] in ids for e in edges), "Dangling workflow edge.")
    steps = 1+max(n["step"] for n in nodes)
    check(all(0 <= n["lane"] < len(lanes) for n in nodes), "Unsupported lane or step.")
    node_by_id = {n["id"]: n for n in nodes}

    def _guard_edges(c, route, e):
        for key, (x, y, w, h) in c.boxes.items():
            if key in (e["from"], e["to"]):
                continue
            for (x1, y1), (x2, y2) in zip(route, route[1:]):
                intersects = ((x1 == x2 and x-1 < x1 < x+w+1 and max(y1, y2) > y+1 and min(y1, y2) < y+h-1)
                              or (y1 == y2 and y-1 < y1 < y+h+1 and max(x1, x2) > x+1 and min(x1, x2) < x+w-1))
                check(not intersects, f"Edge crosses {key}; reflow steps or empty that column.")

    if vertical:
        check(2 <= len(lanes) <= 3, "Use 2–3 lanes.")
        check(steps <= 6, "Vertical lanes support at most six columns.")
        c = _canvas(spec)
        lane_w = (c.content_width-c.gap*(len(lanes)-1))/len(lanes)
        labels = [lane["label"] if isinstance(lane, dict) else lane for lane in lanes]
        heading_size = max(16, c.size("node"))  # Preserve historical lane label size.
        head = max(2*c.pad+len(wrap(label, lane_w-2*c.pad, heading_size))*c.line_height(heading_size) for label in labels)
        widths = {n["id"]: c.natural_width(n["label"], _detail(n), maximum=lane_w-2*c.pad) for n in nodes}
        heights = {n["id"]: c.measure_block(n["label"], _detail(n), widths[n["id"]])["height"] for n in nodes}
        row_h = [max((heights[n["id"]] for n in nodes if n["step"]==step), default=0) for step in range(steps)]
        row_gap = max(c.section, max((len(wrap(e.get("label", ""), c.content_width/2, c.size("caption")))*c.line_height(c.size("caption"))+2*c.gap for e in edges), default=0))
        tops, yy = [], c.content_top+head+c.gap
        for h in row_h:
            tops.append(yy)
            yy += h+row_gap
        bottom = yy-row_gap+c.pad
        for i, (lane, label) in enumerate(zip(lanes, labels)):
            xx = c.margin+i*(lane_w+c.gap)
            c.rect(xx, c.content_top, lane_w, bottom-c.content_top, structural_tone(lane)[1], structural_tone(lane)[0])
            c.text(xx+lane_w/2, c.content_top+c.pad+heading_size, label, heading_size, weight=600, width=lane_w-2*c.pad, anchor="middle")
        for n in nodes:
            w = widths[n["id"]]
            xx = c.margin+n["lane"]*(lane_w+c.gap)+(lane_w-w)/2
            c.box(n["id"], xx, tops[n["step"]], w, None,
                  n["label"], _detail(n), index=n["lane"], **paint(n))
        c.finish(bottom)
        for e in edges:
            a, b = c.boxes[e["from"]], c.boxes[e["to"]]
            ax, ay, aw, ah = a
            bx, by, bw, bh = b
            if by > ay:
                start, end = (ax+aw/2, ay+ah), (bx+bw/2, by)
                my = (start[1]+end[1])/2
                path = f"M{start[0]} {start[1]} V{my} H{end[0]} V{end[1]}"
                route = [start, (start[0], my), (end[0], my), end]
                labelpos = ((start[0]+end[0])/2, my-6)
            else:
                check(False, "Back edges need an explicit focused flow; use the curated retry example.")
            _guard_edges(c, route, e)
            c.path(path, arrow=True, relation=e)
            if e.get("label"):
                c.label(*labelpos, e["label"])
        return c

    # ---- horizontal: compact per-lane heights, content-adaptive cards ----
    check(2 <= len(lanes) <= 6, "Horizontal swimlanes support 2–6 roles.")
    check(steps <= 8, "Horizontal lanes support at most eight columns at 680px.")
    CARD_LEFT, CARD_RIGHT = 130.0, 648.0
    CARD_AREA_W = CARD_RIGHT - CARD_LEFT
    LANE_PAD, LANE_GAP, CELL_GAP = 12.0, 12.0, 12.0
    cell_w = CARD_AREA_W/steps
    card_w = cell_w - CELL_GAP
    check(card_w >= 46, "Too many steps; cards would be too narrow.")

    def card_height(label):
        return 26 + len(wrap(label, card_w-24, 15))*21
    heights = {n["id"]: card_height(n["label"]) for n in nodes}

    lane_max = [0]*len(lanes)
    for n in nodes:
        lane_max[n["lane"]] = max(lane_max[n["lane"]], heights[n["id"]])
    lane_h = [m + 2*LANE_PAD for m in lane_max]
    lane_top = [0]*len(lanes)
    y = 148.0
    for L in range(len(lanes)):
        lane_top[L] = y
        y += lane_h[L] + (LANE_GAP if L+1 < len(lanes) else 0.0)
    bottom = lane_top[-1] + lane_h[-1]
    c = Canvas(spec, int(math.ceil(bottom + 90)))

    # density guards: a lane must hug its tallest card (no big vertical blank)
    for L in range(len(lanes)):
        check(lane_max[L] == 0 or lane_h[L] <= lane_max[L]*1.55 + 6,
              f"Lane {L} carries too much whitespace above its cards.")

    for L, lane in enumerate(lanes):
        c.rect(32, lane_top[L], 616, lane_h[L], structural_tone(lane)[1], structural_tone(lane)[0])
        c.text(46, lane_top[L] + lane_h[L]/2 + 5, lane["label"] if isinstance(lane, dict) else lane, 14, weight=600, width=78)
    for n in nodes:
        x = CARD_LEFT + n["step"]*cell_w + (cell_w-card_w)/2
        h = heights[n["id"]]
        ytop = lane_top[n["lane"]] + (lane_h[n["lane"]]-h)/2
        check(ytop >= lane_top[n["lane"]]+LANE_PAD-1, f"Card {n['id']} overflows its lane top.")
        check(ytop+h <= lane_top[n["lane"]]+lane_h[n["lane"]]-LANE_PAD+1,
              f"Card {n['id']} overflows its lane bottom.")
        c.box(n["id"], x, ytop, card_w, h, n["label"], index=n["lane"], **paint(n))

    # port staggering: spread several shared exits/entries so lines never overlap
    out_total, in_total = {}, {}
    for e in edges:
        a, b = node_by_id[e["from"]], node_by_id[e["to"]]
        if a["lane"] != b["lane"]:
            out_total[e["from"]] = out_total.get(e["from"], 0)+1
            in_total[e["to"]] = in_total.get(e["to"], 0)+1
    out_seen, in_seen = {}, {}
    for e in edges:
        a, b = node_by_id[e["from"]], node_by_id[e["to"]]
        ax, ay, aw, ah = c.boxes[e["from"]]
        bx, by, bw, bh = c.boxes[e["to"]]
        la, lb = a["lane"], b["lane"]
        if la == lb:
            if b["step"] > a["step"]:
                sx, ex = ax+aw, bx
                sy = ey = ay+ah/2
            else:
                sx, ex = ax, bx+bw
                sy = ey = ay+ah/2
            path = f"M{sx} {sy} H{ex}"
            route = [(sx, sy), (ex, ey)]
            labelpos = ((sx+ex)/2, sy-6)
        else:
            out_seen[e["from"]] = out_seen.get(e["from"], 0)+1
            in_seen[e["to"]] = in_seen.get(e["to"], 0)+1
            def frac(total, seen):
                return 0.5 if total <= 1 else 0.3+0.4*(seen-1)/(total-1)
            ef = frac(out_total[e["from"]], out_seen[e["from"]])
            nf = frac(in_total[e["to"]], in_seen[e["to"]])
            if lb > la:  # target lane below: exit source bottom, groove in gap under source
                g = (lane_top[la]+lane_h[la] + lane_top[la+1])/2
                ex, ey = ax+aw*ef, ay+ah
                nx, ny = bx+bw*nf, by
                path = f"M{ex} {ey} V{g} H{nx} V{ny}"
                route = [(ex, ey), (ex, g), (nx, g), (nx, ny)]
                labelpos = (nx, g-7)
            else:        # target lane above: exit source top, groove in gap over source
                g = (lane_top[la-1]+lane_h[la-1] + lane_top[la])/2
                ex, ey = ax+aw*ef, ay
                nx, ny = bx+bw*nf, by+bh
                path = f"M{ex} {ey} V{g} H{nx} V{ny}"
                route = [(ex, ey), (ex, g), (nx, g), (nx, ny)]
                labelpos = (nx, g+14)
        _guard_edges(c, route, e)
        c.path(path, arrow=True, relation=e)
        if e.get("label"):
            c.label(*labelpos, e["label"])
    return c


def release(spec):
    c = Canvas(spec, 780)
    phases = spec["phases"]
    check(len(phases) == 4, "Release overview has four explicit gates.")
    for i, p in enumerate(phases):
        x = 32+i*157
        c.box(f"gate{i}", x, 311, 145, 95, p["label"], p["detail"], i, True, **paint(p))
        if i:
            c.path(f"M{x-12} 358 H{x}", arrow=True, relation={"from": f"gate{i-1}", "to": f"gate{i}"})
    c.box("featureA", 32, 157, 195, 88, "已就绪功能", spec["ready"], 1)
    c.box("featureB", 253, 157, 195, 88, "未就绪功能", spec["deferred"], 4)
    c.path("M129 245 V283 H104 V311", arrow=True, relation={"from": "featureA", "to": "gate0", "label": "满足上车条件"})
    c.label(152, 279, "满足上车条件")
    c.box("next", 479, 157, 169, 88, "下一班列车", "重新满足准入条件", 3, True)
    c.path("M448 201 H479", arrow=True, dash=True, relation={"from": "featureB", "to": "next"})
    c.box("block", 203, 481, 274, 79, "准出失败：阻断本次发布", "修复并重新验证，不自动跳过", 4, True)
    c.path("M418 406 V450 H340 V481", arrow=True, relation={"from": "gate2", "to": "block", "label": "不满足条件"})
    c.label(428, 446, "不满足条件")
    c.box("monitor", 32, 605, 250, 63, "上线后按观测窗口确认", index=1)
    c.box("rollback", 418, 605, 230, 63, "执行预先验证的回退", index=4)
    c.path("M576 406 V584 H178 V605", arrow=True, relation={"from": "gate3", "to": "monitor"})
    c.path("M282 637 H418", arrow=True, relation={"from": "monitor", "to": "rollback", "label": "触发回退条件"})
    c.label(349, 631, "触发回退条件")
    return c


def business(spec):
    cells = spec["cells"]
    check(len(cells) == 9, "Business canvas requires its nine named blocks.")
    c = _canvas(spec)
    available = c.content_width-4*c.gap
    widths = [available*weight/580 for weight in (113,113,128,113,113)]
    xs = [c.margin]
    for width in widths[:-1]:
        xs.append(xs[-1]+width+c.gap)
    column = (0,1,1,2,3,3,4)
    budgets = [c.measure_block(cell["label"], "\n".join(cell["items"]), widths[column[i]])["height"] for i, cell in enumerate(cells[:7])]
    upper, lower = max(budgets[1],budgets[4]), max(budgets[2],budgets[5])
    span = max(upper+lower+c.gap, budgets[0],budgets[3],budgets[6])
    extra = (span-upper-lower-c.gap)/2
    upper, lower = upper+extra, lower+extra
    y = c.content_top
    places = [(xs[column[i]], y+(upper+c.gap if i in (2,5) else 0), widths[column[i]],
               upper if i in (1,4) else lower if i in (2,5) else span) for i in range(7)]
    bottom_w = (c.content_width-c.gap)/2
    bottom_h = max(c.measure_block(cell["label"], "\n".join(cell["items"]), bottom_w)["height"] for cell in cells[7:])
    places += [(c.margin+j*(bottom_w+c.gap), y+span+c.gap, bottom_w, bottom_h) for j in range(2)]
    for i, (cell, (x,y,w,h)) in enumerate(zip(cells, places)):
        c.box(f"cell{i}", x,y,w,h, cell["label"], "\n".join(cell["items"]), i, True, **paint(cell))
    return c.finish(c.content_top+span+c.gap+bottom_h)


def venn(spec):
    groups = spec["groups"]
    check(len(groups) in (2, 3, 4), "Use 2–4 sets.")
    nested = spec.get("nested", False)
    c = Canvas(spec, 630)
    if nested:
        for i, g in enumerate(groups):
            r = 172-i*35
            c.shape("circle", cx=260, cy=340, r=r, fill=structural_tone()[1], stroke=structural_tone()[0])
            yy = 340-r+22
            c.path(f"M260 {yy} H475")
            c.text(490, yy+5, g, 15, width=150)
    else:
        check(len(groups) <= 3, "Overlapping set template supports at most 3 sets.")
        coords = [(260,300), (414,300)] if len(groups)==2 else [(260,290),(420,290),(340,408)]
        for i, (g, (x,y)) in enumerate(zip(groups, coords)):
            c.shape("circle", cx=x, cy=y, r=112, fill=structural_tone()[1], fill_opacity=.65, stroke=structural_tone()[0])
        for i, (g, (x,y)) in enumerate(zip(groups, coords)):
            c.text(x+(-45 if i==0 else 45 if i==1 else 0), y+(40 if i==2 else -40),
                   g, 15, weight=600, anchor="middle", width=140)
        c.label(340, 323 if len(groups)==2 else 348, spec["intersection"])
    return c


def radar(spec, output):
    """Comparable dimensions only; line/marker identity plus a full data table."""
    labels = spec["labels"]
    check(isinstance(labels, list) and 3 <= len(labels) <= 6 and all(isinstance(v,str) and v for v in labels) and len(set(labels)) == len(labels), "Radar needs 3–6 distinct dimensions in one declared order.")
    maximum = spec["maximum"]
    check(isinstance(maximum,(int,float)) and not isinstance(maximum,bool) and math.isfinite(maximum) and maximum > 0, "Radar maximum must be positive and finite.")
    series = spec.get("series")
    if series is None:
        check("values" in spec, "Radar needs values or series; no default data.")
        series = [{"id": "values", "label": spec.get("series_label", spec["title"]), "values": spec["values"]}]
    check(isinstance(series,list) and 1 <= len(series) <= 3, "Radar supports 1–3 series; facet larger comparisons.")
    ids = [v.get("id") for v in series]
    check(all(isinstance(v,str) and v for v in ids) and len(set(ids))==len(ids), "Radar series need unique stable IDs.")
    for item in series:
        check(isinstance(item.get("label"),str) and item["label"], "Radar series label required.")
        check(isinstance(item.get("values"),list) and len(item["values"])==len(labels), "Radar series must share every dimension.")
        check(all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0 <= v <= maximum for v in item["values"]), "Radar values outside declared range.")
        check("labels" not in item or item["labels"]==labels, "Radar series dimension order differs.")
        check("maximum" not in item or item["maximum"]==maximum, "Radar series scale differs.")
        check("unit" not in item or item["unit"]==spec.get("unit",""), "Radar series unit differs.")
    order = spec.get("series_order", sorted(ids))
    check(isinstance(order,list) and len(order)==len(set(order)) and set(ids).issubset(order) and len(order)<=3, "Invalid fixed radar series order; retain at most three identities per comparison.")
    c = _canvas(spec)
    def marker(slot, x, y, color):
        r = c.tokens["marker"]["size"] * c.tokens["design_width"] / c.tokens["document_width"] / 2
        if slot % 3 == 1:
            c.rect(x-r, y-r, 2*r, 2*r, color, THEME["paper"], 0)
        elif slot % 3 == 2:
            c.shape("polygon", points=f"{x},{y-r} {x+r},{y+r} {x-r},{y+r}", fill=color, stroke=THEME["paper"], stroke_width=2)
        else:
            c.shape("circle", cx=x, cy=y, r=r, fill=color, stroke=THEME["paper"], stroke_width=2)
    cx, radius = c.width/2, c.content_width*.25
    legend_h = 0
    if len(series)>1:
        lw = c.content_width/len(series)
        legend_h = max(len(wrap(item["label"],lw-3*c.pad,c.size("body")))*c.line_height(c.size("body")) for item in series)+2*c.gap
        for i,item in enumerate(series):
            xx = c.margin+i*lw
            color = tone(order.index(item["id"]))[0]
            c.path(f"M{xx} {c.content_top+c.size('body')/2} h{c.pad*1.5}", color, c.tokens["line"]["normal"], dash=order.index(item["id"])%2==1)
            marker(order.index(item["id"]), xx+c.pad*.75, c.content_top+c.size("body")/2, color)
            c.text(xx+2*c.pad,c.content_top+c.size("body"),item["label"],c.size("body"),width=lw-3*c.pad)
    label_pad = c.line_height(c.size("body"))*2
    cy = c.content_top+legend_h+radius+label_pad
    angles = [-math.pi/2+2*math.pi*i/len(labels) for i in range(len(labels))]
    point = lambda a,r:(cx+math.cos(a)*r,cy+math.sin(a)*r)
    for fraction in (.25,.5,.75,1):
        points = [point(a,radius*fraction) for a in angles]
        c.shape("polygon",points=" ".join(f"{x},{y}" for x,y in points),fill="none",stroke=THEME["grid"],stroke_width=c.tokens["line"]["entity"])
        x,y = point(angles[0]+math.pi/len(labels),radius*fraction)
        c.text(x+c.pad/2,y+4*c.width/680,f"{maximum*fraction:g}",c.size("caption"),MUTED,width=c.pad*4)
    for label,a in zip(labels,angles):
        x,y = point(a,radius)
        c.path(f"M{cx} {cy} L{x} {y}",THEME["grid"],c.tokens["line"]["entity"])
        lx,ly=point(a,radius+c.gap*2)
        anchor="start" if math.cos(a)>.2 else "end" if math.cos(a)<-.2 else "middle"
        c.text(lx,ly+c.size("body")*.35,label,c.size("body"),anchor=anchor,width=c.content_width*.22)
    for i,item in enumerate(series):
        color = tone(order.index(item["id"]))[0]
        points=[point(a,radius*v/maximum) for a,v in zip(angles,item["values"])]
        end=c.group(item["id"],item,(cx-radius,cy-radius,2*radius,2*radius),"data-series")
        c.path("M"+" L".join(f"{x} {y}" for x,y in points)+" Z",color,c.tokens["line"]["normal"],dash=order.index(item["id"])%2==1)
        for j,((x,y),v) in enumerate(zip(points,item["values"])):
            # Stable shape matches the legend; 8px at the declared document width.
            marker(order.index(item["id"]), x, y, color)
            tooltip=f"{item['label']} · {labels[j]}：{v:g} {spec.get('unit','')}"
            c.parts.append(f'<circle cx="{x}" cy="{y}" r="{12*c.width/680}" fill="transparent" tabindex="0" aria-label="{html.escape(tooltip,quote=True)}"><title>{html.escape(tooltip)}</title></circle>')
        end()
    table_y = cy+radius+label_pad+c.gap
    first = c.content_width*.26
    cell = (c.content_width-first)/len(labels)
    header_h=max(len(wrap(label,cell-c.pad,c.size("caption")))*c.line_height(c.size("caption")) for label in labels)+c.pad
    c.text(c.margin,table_y+c.size("caption"),"数据查看"+(f"（{spec['unit']}）" if spec.get("unit") else ""),c.size("caption"),weight=600,width=first-c.pad)
    for j,label in enumerate(labels):
        c.text(c.margin+first+j*cell,table_y+c.size("caption"),label,c.size("caption"),width=cell-c.pad)
    table_y += header_h
    c.path(f"M{c.margin} {table_y} H{c.width-c.margin}",THEME["grid"])
    for item in series:
        rh=max(c.line_height(c.size("body")),len(wrap(item["label"],first-c.pad,c.size("body")))*c.line_height(c.size("body")))+c.pad
        c.text(c.margin,table_y+c.pad+c.size("body"),item["label"],c.size("body"),width=first-c.pad)
        for j,v in enumerate(item["values"]):
            c.text(c.margin+first+j*cell,table_y+c.pad+c.size("body"),f"{v:g}",c.size("body"),width=cell-c.pad)
        table_y += rh
    result=c.finish(table_y).save(output)
    return {**result,"statistics":{"maximum":maximum,"labels":labels,"unit":spec.get("unit",""),"series":series,"series_order":order}}


def quantitative(spec, output):
    if spec["layout"] == "radar":
        return radar(spec, output)
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from bootstrap import require
    matplotlib = require("matplotlib")[0]
    matplotlib.use("Agg")
    plt = require("matplotlib.pyplot")[0]
    font_manager = require("matplotlib.font_manager")[0]
    from matplotlib.patches import Rectangle
    np = require("numpy")[0]
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    canvas_width = spec.get("canvas_width", 680)
    tokens = layout_tokens(canvas_width)
    dpi = 100
    canvas_height = 590 * canvas_width / 680
    # Matplotlib sizes are points; layout tokens are design pixels at explicit dpi.
    # SVG uses 72 points/inch, so this preserves the 800px document projection.
    pt = lambda role: tokens["sizes"][role] * 72 / dpi
    candidates = [name.strip().strip("\"'") for name in tokens["fonts"]["sans"].split(",")]
    cjk = {ord(ch) for ch in json.dumps(spec, ensure_ascii=False) if 0x3000 <= ord(ch) <= 0x9FFF}
    if spec.get("sample"):
        cjk.update(map(ord, "合成示例"))
    def supported(name):
        if name not in fonts:
            return False
        path = font_manager.findfont(font_manager.FontProperties(family=name))
        return cjk.issubset(font_manager.get_font(path).get_charmap())
    font = next((name for name in candidates if supported(name)), None)
    check(font is not None, "Shared sans font candidates cannot render the supplied CJK text; add an installed CJK fallback to the theme library.")
    with matplotlib.rc_context({"font.family": font, "svg.fonttype": "none", "svg.hashsalt": THEME["name"],
                                "font.size": pt("body"), "text.color": INK, "axes.labelcolor": INK,
                                "axes.labelsize": pt("body"), "xtick.labelsize": pt("caption"), "ytick.labelsize": pt("caption"),
                                "xtick.color": MUTED, "ytick.color": MUTED}):
        fig = plt.figure(figsize=(canvas_width/dpi, canvas_height/dpi), dpi=dpi, facecolor=THEME["paper"])
        margin, gap = tokens["spacing"]["margin"], tokens["spacing"]["gap"]
        content_width = canvas_width-2*margin
        title_rows = wrap(spec["title"], content_width, tokens["sizes"]["title"])
        fig.text(margin/canvas_width, 1-margin/canvas_height, "\n".join(title_rows),
                 fontsize=pt("title"), weight=tokens["weight"]["title"], va="top", linespacing=tokens["line_height"]["title"])
        if spec.get("subtitle"):
            sy = margin+len(title_rows)*tokens["leading"]["title"]+gap
            fig.text(margin/canvas_width, 1-sy/canvas_height,
                     "\n".join(wrap(spec["subtitle"], content_width, tokens["sizes"]["body"])),
                     fontsize=pt("body"), color=MUTED, va="top", linespacing=tokens["line_height"]["body"])
        footer_y = margin
        if spec.get("sample"):
            fig.text(margin/canvas_width, footer_y/canvas_height, "合成示例", fontsize=pt("caption"), color=MUTED)
            footer_y += tokens["leading"]["caption"]+gap
        if spec.get("note"):
            fig.text(margin/canvas_width, footer_y/canvas_height,
                     "\n".join(wrap(spec["note"], content_width, tokens["sizes"]["caption"])),
                     fontsize=pt("caption"), color=MUTED, linespacing=tokens["line_height"]["caption"])
        def text_width(value, role="body"):
            prop = font_manager.FontProperties(family=font, size=pt(role))
            return fig.canvas.get_renderer().get_text_width_height_descent(value, prop, False)[0]
        kind = spec["layout"]
        values = np.asarray(spec.get("values", []), dtype=float)
        check(np.all(np.isfinite(values)), "Values must be finite.")
        stats = {}
        if kind in ("pie", "donut", "funnel"):
            labels = spec["labels"]
            check(len(values)==len(labels) and 2<=len(values)<=8 and np.all(values>=0)
                  and values.sum()>0, "Invalid composition data.")
            if kind == "funnel":
                check(np.all(values[:-1]>=values[1:]) and values[0]>0, "Funnel needs nested nonincreasing counts.")
                ax = fig.add_axes([.23,.22,.67,.49])
                ax.barh(range(len(values)), values, left=-values/2,
                        color=[tone(i)[1] for i in range(len(values))],
                        edgecolor=[tone(i)[0] for i in range(len(values))], height=.7)
                ax.set_yticks(range(len(values)), labels)
                ax.invert_yaxis()
                for i,v in enumerate(values):
                    label = f"{v:g} · {v/values[0]*100:.1f}%"
                    narrow = v/values[0]/1.1*(canvas_width*.67) < text_width(label)+2*tokens["spacing"]["pad"]
                    ax.text(v/2+values[0]*.025 if narrow else 0, i, label,
                            ha="left" if narrow else "center", va="center")
                ax.set_xlim(-values[0]*.55, values[0]*.55)
                ax.set_xticks([])
                stats["overall_conversion"] = float(values[-1]/values[0])
                stats["widths"] = values.tolist()
            else:
                if kind == "donut":
                    # Refined thin-ring donut: largest slice first, muted harmonic
                    # tail, white gaps, centered legend,克制 center typography.
                    order = np.argsort(-values)
                    vals = values[order]
                    labs = [labels[i] for i in order]
                    # Identity follows the input category even when slices are sorted by size.
                    seg_colors = [tone(int(i))[0] for i in order]
                    ax = fig.add_axes([.045,.22,.50,.52])
                    wedges, _ = ax.pie(vals, startangle=90, counterclock=False,
                                       colors=seg_colors,
                                       wedgeprops={"edgecolor":THEME["paper"],"linewidth":2.0,
                                                   "width":.22})
                    total = float(vals.sum())
                    ax.text(0,.10,f"{total:g}",ha="center",va="center",
                            fontsize=pt("title"),weight="bold",color=INK)
                    ax.text(0,-.20,spec["unit"],ha="center",va="center",
                            fontsize=pt("body"),color=MUTED)
                    n = len(vals)
                    row_h = .062 if n <= 4 else (.055 if n <= 6 else .048)
                    top = .485 + (n-1)*row_h/2
                    for i,(name,v) in enumerate(zip(labs,vals)):
                        yy = top - i*row_h
                        fig.patches.append(Rectangle((.635,yy-.011),.018,.022,
                            transform=fig.transFigure,facecolor=seg_colors[i],edgecolor="none"))
                        fig.text(.665,yy,f"{name}  {v:g} · {v/total:.0%}",
                                 fontsize=pt("body"),va="center",color=INK)
                    stats["shares"] = (vals/total).tolist()
                    stats["angles"] = [float(w.theta2-w.theta1) for w in wedges]
                    stats["order"] = [int(i) for i in order]
                    stats["theta1"] = [round(float(w.theta1), 2) for w in wedges]
                    stats["theta2"] = [round(float(w.theta2), 2) for w in wedges]
                    stats["inner_ratio"] = 1-.22
                else:
                    ax = fig.add_axes([.065,.23,.54,.50])
                    wedges, _ = ax.pie(values, startangle=90, counterclock=False,
                                      colors=[tone(i)[0] for i in range(len(values))],
                                      wedgeprops={"edgecolor": LINE, "linewidth": .75})
                    for i, (name,v) in enumerate(zip(labels,values)):
                        yy = .69-i*.074
                        fig.patches.append(Rectangle((.65,yy-.012),.02,.023,
                            transform=fig.transFigure,facecolor=tone(i)[0],edgecolor=tone(i)[0]))
                        fig.text(.686,yy,f"{name}  {v:g}\n{v/values.sum():.1%}",fontsize=pt("body"),va="center",linespacing=tokens["line_height"]["body"])
                    stats["shares"] = (values/values.sum()).tolist()
                    stats["angles"] = [float(w.theta2-w.theta1) for w in wedges]
        elif kind in ("quadrant", "bubble"):
            points = spec["points"]
            check(1 <= len(points) <= 8, "Independent points support 1–8 data items; no data is silently dropped.")
            bounds = spec["bounds"]
            xmin,xmax,ymin,ymax = map(float,bounds)
            check(xmax>xmin and ymax>ymin, "Invalid coordinate limits.")
            mx,my = spec["split"]
            check(xmin<mx<xmax and ymin<my<ymax, "Quadrant split must be inside the axes.")
            panels = [list(range(start, min(start+4, len(points)))) for start in range(0, len(points), 4)]
            for panel, indices in enumerate(panels):
                ax = fig.add_axes([.14,.24,.77,.48] if len(panels)==1 else [.10+panel*.46,.24,.36,.48])
                if len(panels)>1:
                    ax.set_title(f"点 {indices[0]+1}–{indices[-1]+1} · 同一标度", fontsize=pt("caption"), color=INK)
                for i,(x,y,w,h) in enumerate([(xmin,my,mx-xmin,ymax-my),(mx,my,xmax-mx,ymax-my),
                                             (xmin,ymin,mx-xmin,my-ymin),(mx,ymin,xmax-mx,my-ymin)]):
                    ax.add_patch(Rectangle((x,y),w,h,facecolor=point_tone(i)[1],zorder=0))
                for slot,index in enumerate(indices):
                    p=points[index]
                    check(xmin<=p["x"]<=xmax and ymin<=p["y"]<=ymax, "Point outside declared axes.")
                    size = float(p.get("size",1))
                    check(math.isfinite(size) and size>0,"Bubble size must be positive.")
                    colour=point_tone(slot)[0]
                    ax.scatter(p["x"],p["y"],s=45*size if kind=="bubble" else 65,
                               color=colour,edgecolor=colour,zorder=3)
                    ax.annotate(p["label"],(p["x"],p["y"]),xytext=(7,7),textcoords="offset points",fontsize=pt("body"))
                ax.axvline(mx,color=LINE,lw=.8)
                ax.axhline(my,color=LINE,lw=.8)
                ax.set(xlim=(xmin,xmax),ylim=(ymin,ymax),xlabel=spec["x_label"],ylabel=spec["y_label"])
                for spine in ax.spines.values():
                    spine.set_visible(False)
            stats["points"] = points
            stats["panels"] = panels
            stats["colour_scope"] = "all-pairs within explicit panels; shared axes and bubble-area scale"
        else:
            raise ValueError(f"Unknown quantitative template {kind}")
        for spine in ax.spines.values():
            spine.set_visible(False)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        from matplotlib.text import Text
        for text in fig.findobj(match=Text):
            if not text.get_visible() or not text.get_text():
                continue
            bbox = text.get_window_extent(renderer)
            check(bbox.x0 >= 3 and bbox.y0 >= 3
                  and bbox.x1 <= fig.bbox.width-3 and bbox.y1 <= fig.bbox.height-3,
                  f"Chart text outside canvas: {text.get_text()}")
        fig.savefig(output, metadata={"Date": None})
        plt.close(fig)
    svg = output.read_text()
    p = svg.index(">",svg.index("<svg"))+1
    output.write_text(svg[:p]+f'<title>{html.escape(spec["title"])}</title><desc>{html.escape(spec["note"])}</desc>'+svg[p:])
    import xml.etree.ElementTree as ET
    view = list(map(float, ET.fromstring(output.read_text()).get("viewBox").split()))
    supplemental = None
    if kind in ("quadrant", "bubble"):
        supplemental = {"title": "点数据与比较口径", "sections": [
            {"id": "axes", "title": "共同标度", "rows": [{"label": "横轴", "value": spec["x_label"]}, {"label": "纵轴", "value": spec["y_label"]}, {"label": "范围／分界", "value": {"bounds": bounds, "split": spec["split"]}}, {"label": "分面", "value": panels}]},
            {"id": "points", "title": "完整数据", "rows": [{"label": f"{i+1} · {point['label']}", "value": dict(point)} for i,point in enumerate(points)]}]}
    return {"statistics":stats,"font":font,"matplotlib":matplotlib.__version__,
            "width":view[2],"height":view[3],"design_pixels":[canvas_width,canvas_height],
            "text_budget":{"dpi":dpi,"point_per_pixel":72/dpi,"tokens":tokens}, "supplemental": supplemental}


STRUCTURAL = {"layers":layers, "grid":grid, "tree":tree, "mindmap":mindmap,
              "timeline":timeline, "stages":stages, "cycle":cycle, "pyramid":pyramid,
              "house":house, "matrix":matrix, "workflow":workflow, "release":release,
              "business":business, "venn":venn}
QUANTITATIVE = {"pie","donut","funnel","radar","quadrant","bubble"}


def _extra_structural():
    """Lazy accessor for v2.3 structural builders, imported only when requested."""
    global _EXTRA_STRUCTURAL
    try:
        return _EXTRA_STRUCTURAL
    except NameError:
        import structural_extra
        _EXTRA_STRUCTURAL = structural_extra.BUILDERS
        return _EXTRA_STRUCTURAL


def _load_examples():
    """Core examples plus v2.3 extra gold-standard specs (ids stay unique)."""
    items = json.loads((ASSETS/"diagram-templates/examples.json").read_text())
    extra_path = ASSETS/"diagram-templates/examples_extra.json"
    if extra_path.exists():
        items += json.loads(extra_path.read_text())
    stress_path = ASSETS/"diagram-templates/examples_stress.json"
    if stress_path.exists():
        items += json.loads(stress_path.read_text())
    return items


def render(spec, output):
    spec = dict(spec)
    for key in ("id","name","title","layout"):
        check(isinstance(spec.get(key),str) and spec[key], f"Missing field: {key}")
    for key in ("subtitle", "note"):
        check(key not in spec or isinstance(spec[key], str), f"Invalid field: {key}")
        spec.setdefault(key, "")
    check(re.fullmatch(r"[a-z0-9-]+",spec["id"]) is not None,"Invalid template id.")
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    kind = spec["layout"]
    if kind in STRUCTURAL:
        result = STRUCTURAL[kind](spec).save(output)
    elif kind in _extra_structural():
        # v2.3 extra structural layouts (stage_gate/causal_chain/feedback_loop/
        # state_machine/image_annotate); lazy import avoids an import cycle because
        # structural_extra imports symbols back from this module.
        result = _extra_structural()[kind](spec).save(output)
    elif kind in QUANTITATIVE:
        result = quantitative(spec,output)
    else:
        raise ValueError(f"Unsupported layout: {kind}")
    return {"id":spec["id"],"type":spec["name"],"layout":kind,"source":output.name,**result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input",type=Path)
    group.add_argument("--gallery",action="store_true")
    group.add_argument("--example", help="Render one named synthetic example.")
    parser.add_argument("--out",type=Path,required=True)
    args = parser.parse_args()
    if args.input or args.example:
        if args.input:
            item = json.loads(args.input.read_text())
        else:
            examples = _load_examples()
            matching = [s for s in examples if s["id"] == args.example]
            check(bool(matching), f"Unknown example: {args.example}")
            item = {**matching[0], "sample": True}
        result = render(item,args.out)
        print(json.dumps(result,ensure_ascii=False))
    else:
        examples = _load_examples()
        results = [render({**item, "sample": True},args.out/(item["id"]+".svg")) for item in examples]
        (args.out/"templates.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
        print(f"Rendered {len(results)} template examples.")


if __name__ == "__main__":
    main()
