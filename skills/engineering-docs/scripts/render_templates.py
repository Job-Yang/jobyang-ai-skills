#!/usr/bin/env python3
"""Render bounded, data-driven document templates to editable SVG.

Uses the standard library for structural layouts, Matplotlib for quantitative
charts. It does not infer facts or implement an unrestricted graph editor.
"""
import argparse
import html
import json
import math
from pathlib import Path
import re
import unicodedata

ASSETS = Path(__file__).resolve().parents[1] / "assets"
THEME = json.loads((ASSETS / "visual-examples/theme.json").read_text())
INK, MUTED, LINE = (THEME[k] for k in ("ink", "muted", "line"))
PALETTE = THEME["sequence"]


def tone(index):
    return THEME["colors"][PALETTE[index % len(PALETTE)]]


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


class Canvas:
    def __init__(self, spec, height=600):
        self.spec, self.height, self.parts = spec, height, []
        self.boxes, self.labels = {}, []
        self.text(32, 31, spec["name"], 13, MUTED)
        self.text(32, 74, spec["title"], 26, INK, 600, width=616)
        self.text(32, 105, spec["subtitle"], 14, MUTED, width=616)

    def shape(self, tag, **attrs):
        attrs = {k.replace("_", "-"): v for k, v in attrs.items()}
        self.parts.append("<" + tag + " " + " ".join(
            f'{k}="{html.escape(str(v), quote=True)}"' for k, v in attrs.items()) + "/>")

    def rect(self, x, y, w, h, fill="white", border=LINE, radius=8):
        self.shape("rect", x=x, y=y, width=w, height=h, rx=radius,
                   fill=fill, stroke=border, stroke_width=1.2)

    def text(self, x, y, value, size=15, color=INK, weight=400, width=616, anchor="start"):
        rows = wrap(value, width, size)
        for n, row in enumerate(rows):
            yy = y + n * size * 1.4
            self.parts.append(f'<text x="{x}" y="{yy}" font-size="{size}" '
                              f'fill="{color}" font-weight="{weight}" text-anchor="{anchor}">'
                              f'{html.escape(row)}</text>')
            self.labels.append({"text": row, "x": x, "y": yy, "size": size,
                                "width": units(row) * size, "anchor": anchor})
        return len(rows) * size * 1.4

    def box(self, key, x, y, w, h, title, detail="", index=0, filled=False):
        dark, light = tone(index)
        needed = 26 + len(wrap(title, w - 24, 15)) * 21
        if detail:
            needed += len(wrap(detail, w - 24, 13)) * 18.2 + 5
        check(h >= needed - 5, f"Text exceeds box {key}; increase height or split the diagram.")
        self.boxes[key] = (x, y, w, h)
        self.rect(x, y, w, h, light if filled else "white", dark)
        self.text(x + 12, y + 25, title, 15, INK, 600, w - 24)
        if detail:
            self.text(x + 12, y + 30 + len(wrap(title, w - 24, 15)) * 21,
                      detail, 13, MUTED, width=w - 24)

    def path(self, d, color=LINE, width=1.5, arrow=False, dash=False, fill="none"):
        self.parts.append(f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{width}" '
                          'stroke-linecap="round" stroke-linejoin="round" '
                          + ('marker-end="url(#arrow)" ' if arrow else "")
                          + ('stroke-dasharray="5 4" ' if dash else "") + "/>")

    def label(self, x, y, text):
        w = units(text) * 13 + 10
        self.rect(x - w / 2, y - 14, w, 20, "white", "none", 3)
        self.text(x, y, text, 13, anchor="middle", width=w)

    def save(self, path):
        note = self.spec["note"]
        self.path(f"M32 {self.height-69} H648", THEME["grid"], 1)
        self.text(32, self.height-44, note, 13, MUTED, width=616)
        footer = "合成示例 · document-pastel" if self.spec.get("sample") else "document-pastel"
        self.text(32, self.height-12, footer, 12, MUTED)
        for key, (x, y, w, h) in self.boxes.items():
            check(x >= 24 and x+w <= 656 and y >= 130 and y+h <= self.height-85,
                  f"Box outside content area: {key}")
            for other, (ox, oy, ow, oh) in self.boxes.items():
                if key < other:
                    check(min(x+w, ox+ow) <= max(x, ox) or min(y+h, oy+oh) <= max(y, oy),
                          f"Overlapping boxes: {key}, {other}; split the diagram.")
        for item in self.labels:
            left = item["x"] - (item["width"]/2 if item["anchor"] == "middle" else 0)
            check(left >= 15 and left + item["width"] <= 666, f"Label out of bounds: {item['text']}")
            check(0 < item["y"] <= self.height - 5, f"Vertical overflow: {item['text']}")
        for i, a in enumerate(self.labels):
            ax = a["x"] - (a["width"]/2 if a["anchor"] == "middle" else 0)
            for b in self.labels[i+1:]:
                bx = b["x"] - (b["width"]/2 if b["anchor"] == "middle" else 0)
                check(min(ax+a["width"], bx+b["width"]) <= max(ax,bx)
                      or min(a["y"]+2,b["y"]+2) <= max(a["y"]-a["size"],b["y"]-b["size"]),
                      f"Text labels overlap: {a['text']} / {b['text']}")
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="680" height="{self.height}" '
               f'viewBox="0 0 680 {self.height}" role="img"><title>{html.escape(self.spec["title"])}</title>'
               f'<desc>{html.escape(note)}</desc><defs><marker id="arrow" viewBox="0 0 10 10" '
               'refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
               f'<path d="M1 1 L8 5 L1 9" fill="none" stroke="{LINE}" stroke-width="1.5"/>'
               '</marker></defs><rect width="680" height="100%" fill="white"/>'
               f'<g font-family="{THEME["font"]}">' + "".join(self.parts) + "</g></svg>\n")
        path.write_text(svg)
        return {"boxes": self.boxes, "labels": self.labels, "width": 680, "height": self.height}


def layers(spec):
    groups = spec["groups"]
    check(1 <= len(groups) <= 6, "Use 1–6 layers.")
    heights = [78 + math.ceil(len(g["items"])/3) * 65 for g in groups]
    c = Canvas(spec, 250 + sum(heights) + 16*(len(groups)-1))
    y = 148
    for i, (g, height) in enumerate(zip(groups, heights)):
        check(1 <= len(g["items"]) <= 9, "Split layers with more than 9 items.")
        dark, light = tone(i)
        c.rect(32, y, 616, height, light, dark)
        c.text(50, y + 29, g["label"], 17, weight=600)
        for k, item in enumerate(g["items"]):
            row, col = divmod(k, 3)
            count = min(3, len(g["items"])-row*3)
            w = (580 - 14*(count-1))/count
            c.box(f"g{i}-{k}", 50 + col*(w+14), y+49+row*65, w, 55, item, index=i)
        y += height + 16
    return c


def grid(spec):
    groups = spec["groups"]
    columns = spec.get("columns", 2)
    check(columns in (2, 3) and 1 <= len(groups) <= 12, "Grid supports 2–3 columns and at most 12 groups.")
    w = (616 - 16*(columns-1))/columns
    heights = [70 + sum(22*len(wrap(item, w-32, 14)) + 12 for item in g["items"]) for g in groups]
    row_heights = [max(heights[i:i+columns]) for i in range(0, len(groups), columns)]
    c = Canvas(spec, 250 + sum(row_heights) + 16*(len(row_heights)-1))
    y = 148
    for row, height in enumerate(row_heights):
        for col, g in enumerate(groups[row*columns:(row+1)*columns]):
            i = row*columns+col
            dark, light = tone(i)
            x = 32 + col*(w+16)
            c.rect(x, y, w, height, light, dark)
            c.text(x+16, y+29, g["label"], 17, weight=600, width=w-32)
            yy = y+66
            for item in g["items"]:
                yy += c.text(x+16, yy, item, 14, width=w-32) + 12
        y += height + 16
    return c


def tree(spec):
    nodes = spec["nodes"]
    check(1 <= len(nodes) <= 20, "Tree supports 1–20 nodes.")
    lookup = {n["id"]: n for n in nodes}
    check(len(lookup) == len(nodes), "Duplicate tree IDs.")
    children = {key: [] for key in lookup}
    roots = []
    for n in nodes:
        parent = n.get("parent")
        if parent is None:
            roots.append(n["id"])
        else:
            check(parent in lookup, "Unknown parent.")
            children[parent].append(n["id"])
    check(len(roots) == 1, "A hierarchy needs exactly one root.")
    visited, order, leaves = set(), [], []

    def walk(key, depth):
        check(key not in visited, "Cycle in hierarchy.")
        visited.add(key)
        order.append((key, depth))
        for child in children[key]:
            walk(child, depth+1)
        if not children[key]:
            leaves.append(key)
    walk(roots[0], 0)
    check(len(visited) == len(nodes), "Disconnected hierarchy or cycle.")
    check(len(leaves) <= 6, "More than 6 leaves needs a focused diagram.")
    depth = max(d for _, d in order)
    c = Canvas(spec, 340 + depth*136)
    span = 600/len(leaves)
    xs = {key: 40+(i+.5)*span for i, key in enumerate(leaves)}
    for key, _ in reversed(order):
        if children[key]:
            xs[key] = sum(xs[k] for k in children[key])/len(children[key])
    leaf_counts = {}
    for key, _ in reversed(order):
        leaf_counts[key] = sum(leaf_counts[k] for k in children[key]) if children[key] else 1
    for key, d in order:
        x, y = xs[key], 155+d*136
        width = min(160, span*leaf_counts[key]-12)
        c.box(key, x-width/2, y, width, 83, lookup[key]["label"], index=d, filled=d == 0)
    for key, d in order:
        for child in children[key]:
            x1, y1, w1, h1 = c.boxes[key]
            x2, y2, w2, _ = c.boxes[child]
            mid = (y1+h1+y2)/2
            c.path(f"M{x1+w1/2} {y1+h1} V{mid} H{x2+w2/2} V{y2}")
    return c


def mindmap(spec):
    groups = spec["groups"]
    check(2 <= len(groups) <= 6, "Mindmap supports 2–6 branches.")
    rows = math.ceil(len(groups)/2)
    c = Canvas(spec, 250+rows*144)
    cy = 153 + rows*72
    c.box("root", 247, cy-41, 186, 82, spec["center"], index=0, filled=True)
    for i, g in enumerate(groups):
        side = i % 2
        y = 152+(i//2)*144
        x = 460 if side else 32
        c.box(f"branch{i}", x, y, 188, 110, g["label"], "\n".join(g["items"]), i)
        a, b = (433, x) if side else (247, x+188)
        c.path(f"M{a} {cy} C{(a+b)/2} {cy} {(a+b)/2} {y+55} {b} {y+55}", tone(i)[0])
    return c


def timeline(spec):
    events = spec["events"]
    vertical = spec.get("orientation") == "vertical"
    check(2 <= len(events) <= (8 if vertical else 4), "Split timeline into readable panels.")
    values = [float(e["at"]) for e in events]
    check(all(math.isfinite(v) for v in values) and values == sorted(set(values)), "Timeline times must be finite, unique and ascending.")
    lo, hi = values[0], values[-1]
    c = Canvas(spec, 300+len(events)*144 if vertical else 575)
    if vertical:
        y0, span = 172, len(events)*144-50
        c.path(f"M340 {y0} V{y0+span}", arrow=True)
        used = [[], []]
        for i, (event, value) in enumerate(zip(events, values)):
            y = y0 + (value-lo)/(hi-lo)*span
            side = i % 2
            check(all(abs(y-a) >= 120 for a in used[side]), "Timeline labels collide; split close events.")
            used[side].append(y)
            x = 372 if side else 32
            c.box(f"event{i}", x, y-25, 276, 108, event["label"], event["detail"], i, True)
            c.path(f"M340 {y} H{x if side else x+276}")
            c.shape("circle", cx=340, cy=y, r=5, fill=tone(i)[1], stroke=tone(i)[0])
    else:
        c.path("M64 311 H616", arrow=True)
        positions = [84+(v-lo)/(hi-lo)*512 for v in values]
        for i, (event, x) in enumerate(zip(events, positions)):
            y = 153 if i % 2 == 0 else 358
            left = max(32, min(x-84, 480))
            c.box(f"event{i}", left, y, 168, 110, event["label"], event["detail"], i, True)
            c.path(f"M{x} 311 V{y+110 if i%2 == 0 else y}")
            c.shape("circle", cx=x, cy=311, r=5, fill=tone(i)[1], stroke=tone(i)[0])
            c.label(x, 340, str(event["at"]))
    return c


def stages(spec):
    groups = spec["groups"]
    check(2 <= len(groups) <= 6, "Use 2–6 stages.")
    c = Canvas(spec, 250 + len(groups)*110)
    for i, g in enumerate(groups):
        y = 153 + i*110
        dark, light = tone(i)
        c.shape("polygon", points=f"32,{y} 176,{y} 193,{y+42} 176,{y+84} 32,{y+84} 49,{y+42}",
                fill=light, stroke=dark)
        c.text(114, y+38, g["label"], 15, weight=600, anchor="middle", width=120)
        c.box(f"stage{i}", 220, y, 428, 84, g["items"][0],
              " · ".join(g["items"][1:]), i)
        if i+1 < len(groups):
            c.path(f"M114 {y+84} V{y+109}", arrow=True)
    return c


def cycle(spec):
    groups = spec["groups"]
    check(len(groups) in (3, 4), "Cycle supports 3–4 stages; larger cycles should be split.")
    c = Canvas(spec, 760)
    cx, cy, radius = 340, 390, 114
    c.text(cx, cy-5, spec["center"], 20, weight=600, anchor="middle", width=190)
    c.text(cx, cy+24, "按箭头方向循环", 13, MUTED, anchor="middle", width=190)
    for i, g in enumerate(groups):
        dark, light = tone(i)
        start = -90+i*360/len(groups)+16
        end = -90+(i+1)*360/len(groups)-18
        xy = lambda a, r: (cx+r*math.cos(math.radians(a)), cy+r*math.sin(math.radians(a)))
        x1, y1 = xy(start, radius)
        x2, y2 = xy(end, radius)
        c.path(f"M{x1} {y1} A{radius} {radius} 0 0 1 {x2} {y2}", light, 26)
        c.path(f"M{x1} {y1} A{radius} {radius} 0 0 1 {x2} {y2}", LINE, 1.4, arrow=True)
        positions = ([(340,198),(560,390),(340,582),(120,390)] if len(groups)==4
                     else [(340,198),(532,552),(148,552)])
        x, y = positions[i]
        c.box(f"cycle{i}", x-88, y-45, 176, 90, g["label"], "\n".join(g["items"]), i, True)
    return c


def pyramid(spec):
    groups = spec["groups"]
    check(3 <= len(groups) <= 6, "Use 3–6 pyramid levels.")
    c = Canvas(spec, 260+len(groups)*89)
    for i, g in enumerate(groups):
        y = 158+i*89
        half_width = 160 / len(groups)
        top, bottom = i*half_width, (i+1)*half_width
        dark, light = tone(i)
        c.shape("polygon", points=f"{194-top},{y} {194+top},{y} {194+bottom},{y+84} {194-bottom},{y+84}",
                fill=light, stroke=dark)
        c.text(194, y+61, str(i+1), 15, weight=600, anchor="middle", width=40)
        c.path(f"M{194+(top+bottom)/2} {y+44} H405")
        c.text(422, y+33, g["label"], 17, weight=600, width=218)
        c.text(422, y+60, "\n".join(g["items"]), 13, MUTED, width=218)
    return c


def house(spec):
    pillars = spec["pillars"]
    check(2 <= len(pillars) <= 4, "Use 2–4 pillars.")
    c = Canvas(spec, 665)
    c.shape("polygon", points="50,245 340,149 630,245", fill=tone(0)[1], stroke=tone(0)[0])
    c.text(340, 215, spec["roof"], 20, weight=600, anchor="middle", width=340)
    c.rect(50, 260, 580, 64, tone(1)[1], tone(1)[0], 0)
    c.text(340, 297, spec["promise"], 17, weight=600, anchor="middle", width=548)
    width = (580-12*(len(pillars)-1))/len(pillars)
    for i, p in enumerate(pillars):
        c.box(f"pillar{i}", 50+i*(width+12), 339, width, 146,
              p["label"], "\n".join(p["items"]), i+2, True)
    c.rect(50, 501, 580, 64, tone(3)[1], tone(3)[0], 0)
    c.text(340, 538, spec["foundation"], 16, weight=600, anchor="middle", width=550)
    return c


def matrix(spec):
    rows, cols = spec["rows"], spec["columns"]
    check(1 <= len(rows) <= 8 and 2 <= len(cols) <= 4, "Matrix supports up to 8×4 cells.")
    values = spec["values"]
    check(len(values) == len(rows) and all(len(r) == len(cols) for r in values), "Matrix dimensions do not match.")
    c = Canvas(spec, 290 + len(rows)*88)
    w = 488/len(cols)
    for j, col in enumerate(cols):
        c.rect(160+j*w, 148, w-5, 54, tone(j)[1], tone(j)[0], 4)
        c.text(160+j*w+(w-5)/2, 181, col, 15, weight=600, anchor="middle", width=w-15)
    for i, row in enumerate(rows):
        y = 216+i*88
        c.text(32, y+35, row, 15, weight=600, width=116)
        for j, value in enumerate(values[i]):
            c.rect(160+j*w, y, w-5, 76, tone(j)[1], THEME["grid"], 4)
            c.text(172+j*w, y+28, value, 14, width=w-25)
    return c


def workflow(spec):
    lanes, nodes, edges = spec["lanes"], spec["nodes"], spec["edges"]
    vertical = spec.get("orientation", "vertical") == "vertical"
    check(2 <= len(lanes) <= 3, "Use 2–3 lanes.")
    check(bool(nodes), "Workflow needs nodes.")
    check(all(isinstance(n["step"], int) and n["step"] >= 0
              and isinstance(n["lane"], int) for n in nodes), "Invalid lane or step.")
    check(len({(n["lane"], n["step"]) for n in nodes}) == len(nodes),
          "Only one activity is allowed per lane and step.")
    ids = {n["id"] for n in nodes}
    check(len(ids) == len(nodes), "Duplicate workflow IDs.")
    check(all(e["from"] in ids and e["to"] in ids for e in edges), "Dangling workflow edge.")
    steps = 1+max(n["step"] for n in nodes)
    check(steps <= 6 and all(0 <= n["lane"] < len(lanes) for n in nodes), "Unsupported lane or step.")
    if vertical:
        c = Canvas(spec, 285+steps*107)
        lane_w = 616/len(lanes)
        for i, lane in enumerate(lanes):
            c.rect(32+i*lane_w, 148, lane_w-10, steps*107+55, tone(i)[1], tone(i)[0])
            c.text(48+i*lane_w, 180, lane, 16, weight=600, width=lane_w-32)
        for n in nodes:
            c.box(n["id"], 47+n["lane"]*lane_w, 208+n["step"]*107, lane_w-40, 73,
                  n["label"], index=n["lane"])
    else:
        check(steps <= 4, "Horizontal lanes support at most four columns at 680px.")
        c = Canvas(spec, 256+len(lanes)*125)
        cell_w = 510/steps
        for i, lane in enumerate(lanes):
            c.rect(32, 148+i*125, 616, 112, tone(i)[1], tone(i)[0])
            c.text(45, 183+i*125, lane, 15, weight=600, width=83)
        for n in nodes:
            c.box(n["id"], 132+n["step"]*cell_w, 165+n["lane"]*125,
                  cell_w-24, 76, n["label"], index=n["lane"])
    for e in edges:
        a, b = c.boxes[e["from"]], c.boxes[e["to"]]
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        if vertical and by > ay:
            start, end = (ax+aw/2, ay+ah), (bx+bw/2, by)
            my = (start[1]+end[1])/2
            path = f"M{start[0]} {start[1]} V{my} H{end[0]} V{end[1]}"
            route = [start, (start[0], my), (end[0], my), end]
            labelpos = ((start[0]+end[0])/2, my-6)
        elif not vertical and bx > ax:
            start, end = (ax+aw, ay+ah/2), (bx, by+bh/2)
            mx = (start[0]+end[0])/2
            path = f"M{start[0]} {start[1]} H{mx} V{end[1]} H{end[0]}"
            route = [start, (mx, start[1]), (mx, end[1]), end]
            labelpos = (mx, (start[1]+end[1])/2-6)
        else:
            check(False, "Back edges need an explicit focused flow; use the curated retry example.")
        for key, (x, y, w, h) in c.boxes.items():
            if key in (e["from"], e["to"]):
                continue
            for (x1, y1), (x2, y2) in zip(route, route[1:]):
                intersects = ((x1 == x2 and x < x1 < x+w and max(y1,y2)>y and min(y1,y2)<y+h)
                              or (y1 == y2 and y < y1 < y+h and max(x1,x2)>x and min(x1,x2)<x+w))
                check(not intersects, f"Edge crosses {key}; use a graph layout or split the flow.")
        c.path(path, arrow=True)
        if e.get("label"):
            c.label(*labelpos, e["label"])
    return c


def release(spec):
    c = Canvas(spec, 780)
    phases = spec["phases"]
    check(len(phases) == 4, "Release overview has four explicit gates.")
    for i, p in enumerate(phases):
        x = 32+i*157
        c.box(f"gate{i}", x, 311, 145, 95, p["label"], p["detail"], i, True)
        if i:
            c.path(f"M{x-12} 358 H{x}", arrow=True)
    c.box("featureA", 32, 157, 195, 88, "已就绪功能", spec["ready"], 1)
    c.box("featureB", 253, 157, 195, 88, "未就绪功能", spec["deferred"], 4)
    c.path("M129 245 V283 H104 V311", arrow=True)
    c.label(152, 279, "满足上车条件")
    c.box("next", 479, 157, 169, 88, "下一班列车", "重新满足准入条件", 3, True)
    c.path("M448 201 H479", arrow=True, dash=True)
    c.box("block", 203, 481, 274, 79, "准出失败：阻断本次发布", "修复并重新验证，不自动跳过", 4, True)
    c.path("M418 406 V450 H340 V481", arrow=True)
    c.label(428, 446, "不满足条件")
    c.box("monitor", 32, 605, 250, 63, "上线后按观测窗口确认", index=1)
    c.box("rollback", 418, 605, 230, 63, "执行预先验证的回退", index=4)
    c.path("M576 406 V584 H178 V605", arrow=True)
    c.path("M282 637 H418", arrow=True)
    c.label(349, 631, "触发回退条件")
    return c


def business(spec):
    cells = spec["cells"]
    check(len(cells) == 9, "Business canvas requires its nine named blocks.")
    c = Canvas(spec, 705)
    places = [(32,148,113,350), (154,148,113,170), (154,328,113,170),
              (276,148,128,350), (413,148,113,170), (413,328,113,170),
              (535,148,113,350), (32,513,301,93), (347,513,301,93)]
    for i, (cell, (x,y,w,h)) in enumerate(zip(cells, places)):
        c.box(f"cell{i}", x,y,w,h, cell["label"], "\n".join(cell["items"]), i, True)
    return c


def venn(spec):
    groups = spec["groups"]
    check(len(groups) in (2, 3, 4), "Use 2–4 sets.")
    nested = spec.get("nested", False)
    c = Canvas(spec, 630)
    if nested:
        for i, g in enumerate(groups):
            r = 172-i*35
            c.shape("circle", cx=260, cy=340, r=r, fill=tone(i)[1], stroke=tone(i)[0])
            yy = 340-r+22
            c.path(f"M260 {yy} H475")
            c.text(490, yy+5, g, 15, width=150)
    else:
        check(len(groups) <= 3, "Overlapping set template supports at most 3 sets.")
        coords = [(260,300), (414,300)] if len(groups)==2 else [(260,290),(420,290),(340,408)]
        for i, (g, (x,y)) in enumerate(zip(groups, coords)):
            c.shape("circle", cx=x, cy=y, r=112, fill=tone(i)[1], fill_opacity=.65, stroke=tone(i)[0])
        for i, (g, (x,y)) in enumerate(zip(groups, coords)):
            c.text(x+(-45 if i==0 else 45 if i==1 else 0), y+(40 if i==2 else -40),
                   g, 15, weight=600, anchor="middle", width=140)
        c.label(340, 323 if len(groups)==2 else 348, spec["intersection"])
    return c


def quantitative(spec, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Rectangle
    import numpy as np
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    font = next((x for x in ("PingFang SC", "Noto Sans CJK SC", "Arial Unicode MS") if x in fonts), "DejaVu Sans")
    with matplotlib.rc_context({"font.family": font, "svg.fonttype": "none", "svg.hashsalt": "document-pastel",
                                "font.size": 10.8, "text.color": INK, "axes.labelcolor": MUTED,
                                "xtick.color": MUTED, "ytick.color": MUTED}):
        fig = plt.figure(figsize=(6.8, 5.9), facecolor="white")
        fig.text(.047,.948,spec["name"],fontsize=10,color=MUTED)
        fig.text(.047,.877,spec["title"],fontsize=18,weight="bold")
        fig.text(.047,.823,spec["subtitle"],fontsize=10,color=MUTED)
        fig.text(.047,.09,spec["note"],fontsize=9,color=MUTED)
        footer = "合成示例 · document-pastel" if spec.get("sample") else "document-pastel"
        fig.text(.047,.03,footer,fontsize=8.5,color=MUTED)
        kind = spec["layout"]
        values = np.asarray(spec.get("values", []), dtype=float)
        check(np.all(np.isfinite(values)), "Values must be finite.")
        stats = {}
        if kind in ("pie", "donut", "funnel"):
            labels = spec["labels"]
            check(len(values)==len(labels) and 2<=len(values)<=6 and np.all(values>=0)
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
                    narrow = v/values[0]*414 < len(label)*7+12
                    ax.text(v/2+values[0]*.025 if narrow else 0, i, label,
                            ha="left" if narrow else "center", va="center")
                ax.set_xlim(-values[0]*.55, values[0]*.55)
                ax.set_xticks([])
                stats["overall_conversion"] = float(values[-1]/values[0])
                stats["widths"] = values.tolist()
            else:
                ax = fig.add_axes([.065,.23,.54,.50])
                wedges, _ = ax.pie(values, startangle=90, counterclock=False,
                                  colors=[tone(i)[1] for i in range(len(values))],
                                  wedgeprops={"edgecolor": LINE, "linewidth": .75,
                                              **({"width":.36} if kind=="donut" else {})})
                for i, (name,v) in enumerate(zip(labels,values)):
                    yy = .69-i*.074
                    fig.patches.append(Rectangle((.65,yy-.012),.02,.023,
                        transform=fig.transFigure,facecolor=tone(i)[1],edgecolor=tone(i)[0]))
                    fig.text(.686,yy,f"{name}  {v:g}\n{v/values.sum():.1%}",fontsize=10,va="center")
                if kind == "donut":
                    ax.text(0,.05,f"{values.sum():g}",ha="center",fontsize=24,weight="bold")
                    ax.text(0,-.22,spec["unit"],ha="center",fontsize=10,color=MUTED)
                stats["shares"] = (values/values.sum()).tolist()
                stats["angles"] = [float(w.theta2-w.theta1) for w in wedges]
        elif kind == "radar":
            check(values.ndim==1 and 3<=len(values)<=6 and len(spec["labels"])==len(values), "Radar needs 3–6 dimensions.")
            maximum = float(spec["maximum"])
            check(maximum>0 and np.all((values>=0)&(values<=maximum)), "Radar values outside declared range.")
            ax = fig.add_axes([.20,.22,.6,.50], projection="polar")
            angles = np.linspace(0,2*np.pi,len(values),endpoint=False)
            ax.set_theta_offset(np.pi/2)
            ax.set_theta_direction(-1)
            ax.plot(np.r_[angles,angles[0]],np.r_[values,values[0]],color=tone(0)[0],lw=1.5)
            ax.fill(np.r_[angles,angles[0]],np.r_[values,values[0]],color=tone(0)[1])
            ax.set_xticks(angles,spec["labels"])
            ax.tick_params(pad=12)
            ax.set_ylim(0,maximum)
            ax.set_yticks([maximum*.25,maximum*.5,maximum*.75,maximum])
            ax.grid(color=THEME["grid"],linewidth=.8)
            stats["maximum"] = maximum
        elif kind in ("quadrant", "bubble"):
            ax = fig.add_axes([.14,.24,.77,.48])
            points = spec["points"]
            bounds = spec["bounds"]
            xmin,xmax,ymin,ymax = map(float,bounds)
            check(xmax>xmin and ymax>ymin, "Invalid coordinate limits.")
            mx,my = spec["split"]
            check(xmin<mx<xmax and ymin<my<ymax, "Quadrant split must be inside the axes.")
            for i,(x,y,w,h) in enumerate([(xmin,my,mx-xmin,ymax-my),(mx,my,xmax-mx,ymax-my),
                                         (xmin,ymin,mx-xmin,my-ymin),(mx,ymin,xmax-mx,my-ymin)]):
                ax.add_patch(Rectangle((x,y),w,h,facecolor=tone(i)[1],zorder=0))
            for i,p in enumerate(points):
                check(xmin<=p["x"]<=xmax and ymin<=p["y"]<=ymax, "Point outside declared axes.")
                size = float(p.get("size",1))
                check(math.isfinite(size) and size>0,"Bubble size must be positive.")
                ax.scatter(p["x"],p["y"],s=45*size if kind=="bubble" else 65,
                           color=tone(i)[1],edgecolor=tone(i)[0],zorder=3)
                ax.annotate(p["label"],(p["x"],p["y"]),xytext=(7,7),textcoords="offset points",fontsize=10)
            ax.axvline(mx,color=LINE,lw=.8)
            ax.axhline(my,color=LINE,lw=.8)
            ax.set(xlim=(xmin,xmax),ylim=(ymin,ymax),xlabel=spec["x_label"],ylabel=spec["y_label"])
            stats["points"] = points
        else:
            raise ValueError(f"Unknown quantitative template {kind}")
        if kind not in ("radar",):
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
    return {"statistics":stats,"font":font,"matplotlib":matplotlib.__version__}


STRUCTURAL = {"layers":layers, "grid":grid, "tree":tree, "mindmap":mindmap,
              "timeline":timeline, "stages":stages, "cycle":cycle, "pyramid":pyramid,
              "house":house, "matrix":matrix, "workflow":workflow, "release":release,
              "business":business, "venn":venn}
QUANTITATIVE = {"pie","donut","funnel","radar","quadrant","bubble"}


def render(spec, output):
    for key in ("id","name","title","subtitle","note","layout"):
        check(isinstance(spec.get(key),str) and spec[key], f"Missing field: {key}")
    check(re.fullmatch(r"[a-z0-9-]+",spec["id"]) is not None,"Invalid template id.")
    check(units(spec["title"])*26<=616 and units(spec["subtitle"])*14<=616,
          "Title or subtitle too long; shorten without changing meaning.")
    check(units(spec["note"])*13<=616,"Note too long; put details in the document.")
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    kind = spec["layout"]
    if kind in STRUCTURAL:
        result = STRUCTURAL[kind](spec).save(output)
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
            examples = json.loads((ASSETS/"diagram-templates/examples.json").read_text())
            matching = [s for s in examples if s["id"] == args.example]
            check(bool(matching), f"Unknown example: {args.example}")
            item = {**matching[0], "sample": True}
        result = render(item,args.out)
        print(json.dumps(result,ensure_ascii=False))
    else:
        examples = json.loads((ASSETS/"diagram-templates/examples.json").read_text())
        results = [render({**item, "sample": True},args.out/(item["id"]+".svg")) for item in examples]
        (args.out/"templates.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
        print(f"Rendered {len(results)} template examples.")


if __name__ == "__main__":
    main()
