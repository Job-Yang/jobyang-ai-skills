#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_infographic.py — 内容信息图的「确定性渲染」后端（零三方依赖）。

为什么存在：
  信息图分两种。流程/步骤/对比/分类这类「图上要排很多准确中文 + 术语 + 英文原词」
  的图，交给文生图模型几乎必然糊字、错字、漏框。本脚本用结构化 JSON 直接渲染成
  SVG（文字是真 DOM/SVG text，永远清晰、可改、可复核），需要位图时再用系统转换器
  导出 PNG。抽象比喻/场景插画仍走文生图（见 SKILL.md 后端契约），两条路分工。

输入：一份信息图 JSON（schema 见 references/schema.md，examples/ 有完整样例）。
输出：SVG（必出）；加 --png 时用 rsvg-convert / Chrome headless / qlmanage 之一转 PNG。

用法：
  python3 render_infographic.py spec.json -o out.svg
  python3 render_infographic.py spec.json -o out.svg --png          # 同时出 out.png
  python3 render_infographic.py spec.json --stdin -o out.svg        # 从 stdin 读 JSON
退出码：0 成功；1 参数/IO 错；2 JSON/schema 校验错；3 PNG 转换失败（SVG 仍可用）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

# ---- 设计系统（去品牌化的通用扁平商务风；可用 spec.palette 覆盖）----------------
DEFAULT = {
    "bg": "#FFFFFF",
    "bg_soft": "#F5F7FA",
    "ink": "#1F2329",
    "ink_soft": "#646A73",
    "line": "#DEE0E3",
    "accent": "#F26A1B",      # 橙：高亮 / 真凶 / 关键
    "accent_soft": "#FDEEE3",
    "blue": "#3370FF",        # 方法 / 理性
    "blue_soft": "#EAF1FF",
    "red": "#F54A45",
    "red_soft": "#FEECEB",
    "green": "#34A853",
    "green_soft": "#E8F7ED",
    "purple": "#7F5AF0",      # 仅在明确需要第四语义时，默认不使用
    "card": "#FFFFFF",
}
FONT = '-apple-system, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", "Helvetica Neue", Arial, sans-serif'
MONO = '"SF Mono", "JetBrains Mono", Menlo, Consolas, monospace'


def esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _units(text):
    """拆成不可拆单元：连续 ASCII 词（含 . _ - # / +）整体一个单元，中文逐字，空格为断点。"""
    units, buf, latin = [], "", False

    def flush():
        nonlocal buf
        if buf:
            units.append(buf)
            buf = ""

    for ch in str(text):
        is_lat = ch.isascii() and (ch.isalnum() or ch in "._-#/+%")
        if is_lat:
            if not latin:
                flush(); latin = True
            buf += ch
        else:
            flush(); latin = False
            if ch == " ":
                units.append(" ")  # 可断点
            elif ch == "\n":
                units.append("\n")
            else:
                units.append(ch)
    flush()
    return units


def wrap_cjk(text: str, max_w: float, avg: float) -> list:
    """显示宽度折行：中文按字、拉丁按整词（不把英文单词从中间劈断），空格处可换行。"""
    lines, cur, width = [], "", 0.0
    for u in _units(text):
        if u == "\n":
            lines.append(cur); cur, width = "", 0.0; continue
        if u == " ":
            if cur and not cur.endswith(" "):
                cur += " "; width += avg * 0.3
            continue
        w = avg * (0.58 * len(u) if u.isascii() else 1.0)
        if width + w > max_w and cur.strip():
            lines.append(cur.rstrip()); cur, width = u, w  # 拉丁整词挪到下一行
        else:
            cur += u; width += w
    if cur.strip():
        lines.append(cur.rstrip())
    return lines or [""]


def fit_size(longest: str, max_w: float, start: int, floor: int = 19) -> int:
    """给一个最长拉丁词/串选能塞进 max_w 的字号。"""
    size = start
    while size > floor:
        w = size * 0.58 * len(longest) if longest.isascii() else size * len(longest)
        if w <= max_w:
            break
        size -= 1
    return size


class S:
    """极简 SVG 构造器。坐标单位 px，画布默认 1600×1067（约 3:2）。"""

    def __init__(self, w=1600, h=1067, bg="#FFFFFF"):
        self.w, self.h = w, h
        self.buf = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" font-family=\'{FONT}\'>',
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="{bg}"/>',
        ]

    def text(self, x, y, s, size=28, fill=DEFAULT["ink"], weight=400, anchor="start",
             italic=False, mono=False, spacing=None, opacity=1.0):
        fam = MONO if mono else FONT
        sp = f' letter-spacing="{spacing}"' if spacing is not None else ""
        self.buf.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}" font-family=\'{fam}\''
            f' font-style="{"italic" if italic else "normal"}"{sp} opacity="{opacity}">'
            f'{esc(s)}</text>'
        )

    def multiline(self, x, y, lines, size, lh, **kw):
        for i, ln in enumerate(lines):
            self.text(x, y + i * lh, ln, size=size, **kw)

    def rect(self, x, y, w, h, r=18, fill=DEFAULT["card"], stroke=None, sw=1.5,
             shadow=False, opacity=1.0):
        filt = ' filter="url(#cardShadow)"' if shadow else ""
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.buf.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
            f'fill="{fill}"{st}{filt} opacity="{opacity}"/>'
        )

    def circle(self, cx, cy, r, fill, stroke=None, sw=1.5):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.buf.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}"{st}/>')

    def line(self, x1, y1, x2, y2, stroke=DEFAULT["line"], sw=2, dash=None, marker=False, opacity=1.0):
        da = f' stroke-dasharray="{dash}"' if dash else ""
        mk = ' marker-end="url(#arrow)"' if marker else ""
        self.buf.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linecap="round"{da}{mk} opacity="{opacity}"/>'
        )

    def polyline(self, pts, stroke=DEFAULT["line"], sw=2, fill="none", marker=False, dash=None):
        da = f' stroke-dasharray="{dash}"' if dash else ""
        mk = ' marker-end="url(#arrow)"' if marker else ""
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.buf.append(
            f'<polyline points="{p}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"'
            f' stroke-linejoin="round" stroke-linecap="round"{da}{mk}/>'
        )

    def icon_box(self, cx, cy, kind, color, size_px=34):
        """细描边线性图标，全部几何手绘，不依赖图标库。kind 见函数内。"""
        s = size_px
        x, y = cx - s / 2, cy - s / 2
        c = color
        sw = 2.4
        e = []
        if kind == "doc":
            e.append(f'<rect x="{x+4}" y="{y}" rx="3" width="{s-8}" height="{s}" fill="none" stroke="{c}" stroke-width="{sw}"/>')
            for i, dy in enumerate((-8, 0, 8)):
                e.append(f'<line x1="{x+10}" y1="{cy+dy}" x2="{x+s-10}" y2="{cy+dy}" stroke="{c}" stroke-width="{sw-0.6}" stroke-linecap="round"/>')
        elif kind == "db":
            e.append(f'<ellipse cx="{cx}" cy="{y+8}" rx="{s/2-5}" ry="6" fill="none" stroke="{c}" stroke-width="{sw}"/>')
            e.append(f'<path d="M{cx-(s/2-5)} {y+8} V{cy+8} A{s/2-5} 6 0 0 0 {cx+(s/2-5)} {cy+8} V{y+8}" fill="none" stroke="{c}" stroke-width="{sw}"/>')
            e.append(f'<line x1="{cx-(s/2-5)}" y1="{cy-1}" x2="{cx+(s/2-5)}" y2="{cy-1}" stroke="{c}" stroke-width="{sw-0.8}"/>')
        elif kind == "wave":
            pts = [(x+5,cy),(x+11,cy-9),(x+17,cy+9),(x+23,cy-6),(x+s-5,cy)]
            e.append('<polyline points="'+" ".join(f"{a:.1f},{b:.1f}" for a,b in pts)+
                     f'" fill="none" stroke="{c}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>')
        elif kind == "blocks":
            for i,(dx,dy) in enumerate(((0,0),(11,0),(0,11),(11,11))):
                e.append(f'<rect x="{x+5+dx}" y="{y+5+dy}" width="8" height="8" rx="2" fill="none" stroke="{c}" stroke-width="{sw-0.6}"/>')
        elif kind == "bars":
            for i,bh in enumerate((10,18,26)):
                bx=x+6+i*9
                e.append(f'<rect x="{bx}" y="{y+s-6-bh}" width="6" height="{bh}" rx="2" fill="none" stroke="{c}" stroke-width="{sw-0.6}"/>')
        elif kind == "loop":
            e.append(f'<path d="M{cx-11} {cy-9} a12 12 0 1 1 -3 12" fill="none" stroke="{c}" stroke-width="{sw}" stroke-linecap="round"/>')
            e.append(f'<polyline points="{cx-2},{cy-15} {cx-14},{cy-12} {cx-11},{cy-1}" fill="none" stroke="{c}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>')
        elif kind == "check_doc":
            e.append(f'<rect x="{x+4}" y="{y}" width="{s-8}" height="{s-4}" rx="3" fill="none" stroke="{c}" stroke-width="{sw}"/>')
            e.append(f'<polyline points="{x+10},{cy+1} {x+15},{cy+7} {x+s-9},{cy-7}" fill="none" stroke="{c}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>')
        elif kind == "tag":
            e.append(f'<path d="M{x+5} {y+5} h{14} l8 10 -8 10 h-14 z" fill="none" stroke="{c}" stroke-width="{sw}" stroke-linejoin="round"/>')
            e.append(f'<circle cx="{x+11}" cy="{cy}" r="2.2" fill="{c}"/>')
        elif kind == "brain":
            e.append(f'<path d="M{cx} {y+5} a9 9 0 0 0 -9 9 q-4 0 -2 7 q-3 6 5 7 a9 9 0 0 0 12 0 q8 -1 5 -7 q2 -7 -2 -7 a9 9 0 0 0 -9 -9 z" fill="none" stroke="{c}" stroke-width="{sw-0.4}"/>')
        elif kind == "chip":
            e.append(f'<rect x="{x+8}" y="{y+8}" width="{s-16}" height="{s-16}" rx="3" fill="none" stroke="{c}" stroke-width="{sw}"/>')
            for i in (-1,0,1):
                e.append(f'<line x1="{cx+i*7}" y1="{y+8}" x2="{cx+i*7}" y2="{y+3}" stroke="{c}" stroke-width="{sw-0.6}"/>')
                e.append(f'<line x1="{cx+i*7}" y1="{y+s-8}" x2="{cx+i*7}" y2="{y+s-3}" stroke="{c}" stroke-width="{sw-0.6}"/>')
                e.append(f'<line x1="{x+8}" y1="{cy+i*7}" x2="{x+3}" y2="{cy+i*7}" stroke="{c}" stroke-width="{sw-0.6}"/>')
                e.append(f'<line x1="{x+s-8}" y1="{cy+i*7}" x2="{x+s-3}" y2="{cy+i*7}" stroke="{c}" stroke-width="{sw-0.6}"/>')
        else:  # 兜底：圆角方块
            e.append(f'<rect x="{x+4}" y="{y+4}" width="{s-8}" height="{s-8}" rx="4" fill="none" stroke="{c}" stroke-width="{sw}"/>')
        self.buf.append("".join(e))

    def badge(self, x, y, n, color, r=20, tcolor="#fff"):
        self.circle(x, y, r, color)
        self.text(x, y + r * 0.36, str(n), size=26, fill=tcolor, weight=700, anchor="middle")

    def defs(self, accent):
        self.buf.insert(
            1,
            '<defs>'
            '<filter id="cardShadow" x="-10%" y="-10%" width="120%" height="130%">'
            '<feDropShadow dx="0" dy="6" stdDeviation="10" flood-color="#1F2329" flood-opacity="0.10"/>'
            '</filter>'
            f'<marker id="arrow" markerWidth="12" markerHeight="12" refX="9" refY="6" orient="auto">'
            f'<path d="M1,1 L10,6 L1,11" fill="none" stroke="{accent}" stroke-width="2.4" '
            'stroke-linecap="round" stroke-linejoin="round"/></marker>'
            '</defs>',
        )

    def save(self, path):
        self.buf.append("</svg>")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.buf))


# ---- 公共：页眉 ----------------------------------------------------------------
def draw_header(svg, spec, pal, fs):
    kicker = spec.get("kicker")
    if kicker:
        svg.text(fs, 78, kicker, size=26, fill=pal["accent"], weight=700)
        ty = 132
    else:
        ty = 118
    title_lines = wrap_cjk(spec.get("title", ""), svg.w - 2 * fs, 50)
    svg.multiline(fs, ty, title_lines, 50, 58, fill=pal["ink"], weight=800)
    sub = spec.get("subtitle")
    if sub:
        sy = ty + len(title_lines) * 58 + 6
        for i, ln in enumerate(wrap_cjk(sub, svg.w - 2 * fs, 26)):
            svg.text(fs, sy + i * 34, ln, size=26, fill=pal["ink_soft"])
    return ty + len(title_lines) * 58 + (40 if sub else 24)


def draw_footer(svg, spec, pal, y=None):
    if spec.get("footer"):
        svg.text(svg.w - 60, y or (svg.h - 34), spec["footer"], size=22,
                 fill=pal["ink_soft"], anchor="end", opacity=0.8)


def legend_chips(svg, x, y, chips, pal):
    """chips: [(文字, 颜色)]"""
    cx = x
    for text, color in chips:
        w = 20 + len(text) * 16 + 24
        svg.rect(cx, y, w, 40, r=20, fill="#FFFFFF", stroke=color, sw=1.8)
        svg.circle(cx + 22, y + 20, 6, color)
        svg.text(cx + 36, y + 28, text, size=24, fill=pal["ink_soft"])
        cx += w + 16
    return cx


# ---- 布局 1：横向流水线（步骤链）------------------------------------------------
def layout_pipeline(svg, d, pal, fs, top):
    steps = d["steps"]
    n = len(steps)
    bottom_span = d.get("span_labels") or []
    has_span = bool(bottom_span)
    area_top = top + 10
    area_bot = svg.h - (150 if has_span else 96)
    gap = 22
    cw = (svg.w - 2 * fs - gap * (n - 1)) / n
    card_h = area_bot - area_top
    icon_kind = d.get("icons", [])
    # 内容块在卡片内垂直居中：图标 + 标题（最多2行）+ 描述（最多3行）
    desc_size, t_size = 22, 27
    block_h = 150 + 2 * 36 + 30 + 3 * 31  # 图标 + 标题2行 + 间距 + 描述3行（近似）
    for i, st in enumerate(steps):
        x = fs + i * (cw + gap)
        svg.rect(x, area_top, cw, card_h, r=20, fill=pal["card"], stroke=pal["line"], shadow=True)
        svg.badge(x + 34, area_top + 36, i + 1, pal["accent"], r=18)
        inner_w = cw - 36
        cy0 = area_top + (card_h - block_h) / 2 + 10
        ik = icon_kind[i] if i < len(icon_kind) else "doc"
        svg.icon_box(x + cw / 2, cy0 + 60, ik, pal["blue"], 58)
        # 标题：词感知换行 + 自动缩字号，保证最长拉丁词不被劈断
        title = st.get("title", "")
        longest = max((u for u in _units(title) if u.isascii()), key=len, default="")
        tsize = fit_size(longest, inner_w - 8, t_size, floor=20) if longest else t_size
        tl = wrap_cjk(title, inner_w, tsize)[:2]
        ty = cy0 + 132
        for j, ln in enumerate(tl):
            svg.text(x + cw / 2, ty + j * 36, ln, size=tsize, fill=pal["ink"],
                     weight=700, anchor="middle")
        desc = st.get("desc", "")
        dl = wrap_cjk(desc, inner_w, desc_size)[:3]
        dy = ty + 48
        for j, ln in enumerate(dl):
            svg.text(x + cw / 2, dy + j * 31, ln, size=desc_size, fill=pal["ink_soft"],
                     anchor="middle")
        if i < n - 1:
            svg.line(x + cw + 4, area_top + card_h / 2, x + cw + gap - 4,
                     area_top + card_h / 2, stroke=pal["accent"], sw=3, marker=True)
    if has_span:
        by = area_bot + 44
        for sp in bottom_span:
            x0 = fs + sp.get("from", 0) * (cw + gap) + 20
            x1 = fs + sp.get("to", n - 1) * (cw + gap) + cw - 20
            col = pal.get(sp.get("color", ""), pal["accent"])
            svg.line(x0, by - 16, x1, by - 16, stroke=col, sw=3)
            svg.line(x0, by - 24, x0, by - 8, stroke=col, sw=3)
            svg.line(x1, by - 24, x1, by - 8, stroke=col, sw=3)
            svg.text((x0 + x1) / 2, by + 26, sp["label"], size=26, fill=col, weight=700,
                     anchor="middle")


# ---- 布局 2：三栏卡片（如 预训练 / 微调 / RLHF）--------------------------------
def layout_columns(svg, d, pal, fs, top):
    cols = d["columns"]
    n = len(cols)
    gap = 30
    cw = (svg.w - 2 * fs - gap * (n - 1)) / n
    area_top = top + 6
    area_bot = svg.h - 150
    col_fill = [pal["accent_soft"], pal["blue_soft"], pal["green_soft"]]
    col_col = [pal["accent"], pal["blue"], pal["green"]]
    for i, c in enumerate(cols):
        x = fs + i * (cw + gap)
        col = col_col[i % 3]; soft = col_fill[i % 3]
        svg.rect(x, area_top, cw, area_bot - area_top, r=24, fill=pal["card"],
                 stroke=pal["line"], shadow=True)
        svg.rect(x, area_top, cw, 132, r=24, fill=soft)
        svg.rect(x, area_top + 90, cw, 42, fill=soft)
        svg.badge(x + 44, area_top + 56, i + 1, col, r=24)
        head = c["title"].split("\n")
        svg.multiline(x + 86, area_top + 46, head, 34, 40, fill=col, weight=800)
        if c.get("subtitle"):
            svg.text(x + 28, area_top + 116, c["subtitle"], size=23, fill=pal["ink_soft"])
        iy = area_top + 176
        if c.get("scene"):  # 可选的中部"场景"短句框
            scene_lines = wrap_cjk(c["scene"], cw - 64, 24)
            sh = 22 + len(scene_lines) * 32
            svg.rect(x + 28, iy - 12, cw - 56, sh, r=14, fill=pal["bg_soft"])
            svg.multiline(x + 44, iy + 16, scene_lines, 24, 32, fill=pal["ink_soft"])
            iy += sh + 28
        for j, b in enumerate(c.get("bullets", [])):
            by = iy + j * 78
            svg.circle(x + 40, by - 6, 5, col)
            for k, ln in enumerate(wrap_cjk(b, cw - 80, 25)[:2]):
                svg.text(x + 60, by + k * 33, ln, size=25, fill=pal["ink"])
    # 底部演进链（放在卡片下方留白带内，且整体高于 footer 行）
    chain = d.get("chain") or []
    if chain:
        cy = area_bot + 42
        seg_w = (svg.w - 2 * fs) / max(len(chain), 1)
        for i, node in enumerate(chain):
            cx = fs + seg_w * i + seg_w / 2
            if i > 0:
                svg.line(fs + seg_w * i + 30, cy, fs + seg_w * i + seg_w - 30, cy,
                         stroke=pal["accent"], sw=4, marker=True)
            svg.circle(cx, cy, 10, pal["accent"])
            svg.text(cx, cy + 44, node, size=27, fill=pal["ink"], weight=700,
                     anchor="middle")
        # 有演进链时，footer 压到画布最底一行，避免和第三段链标签同行
        return svg.h - 22
    return None


# ---- 布局 3：两段式（Prefill / Decode 等）--------------------------------------
def layout_two_stage(svg, d, pal, fs, top):
    stages = d["stages"]
    gap = 40
    cw = (svg.w - 2 * fs - gap) / 2
    area_top, area_bot = top + 10, svg.h - 110
    for i, st in enumerate(stages):
        x = fs + i * (cw + gap)
        col = pal["blue"] if i == 0 else pal["accent"]
        soft = pal["blue_soft"] if i == 0 else pal["accent_soft"]
        svg.rect(x, area_top, cw, area_bot - area_top, r=24, fill=pal["card"],
                 stroke=pal["line"], shadow=True)
        svg.rect(x, area_top, 14, area_bot - area_top, r=7, fill=col)
        svg.text(x + 52, area_top + 70, st["title"], size=40, fill=col, weight=800)
        svg.text(x + 52, area_top + 116, st.get("subtitle", ""), size=26,
                 fill=pal["ink_soft"])
        rows = st.get("rows", [])
        ry = area_top + 178
        for r_ in rows:
            svg.text(x + 52, ry, r_.get("k", ""), size=24, fill=pal["ink_soft"])
            for k, ln in enumerate(wrap_cjk(r_.get("v", ""), cw - 110, 30)[:3]):
                svg.text(x + 52, ry + 40 + k * 38, ln, size=30, fill=pal["ink"], weight=600)
            ry += 40 + min(len(wrap_cjk(r_.get("v", ""), cw - 110, 30)), 3) * 38 + 30
    if d.get("vs_label"):
        svg.circle(svg.w / 2, (area_top + area_bot) / 2, 44, pal["ink"])
        svg.text(svg.w / 2, (area_top + area_bot) / 2 + 12, d["vs_label"], size=28,
                 fill="#fff", weight=800, anchor="middle")


# ---- 布局 4：概念比喻（拟人 / 失衡对比；文字少，留白大）--------------------------
def layout_metaphor(svg, d, pal, fs, top):
    # 左标题结论 + 右视觉母题（母题用几何 + 线性图，确定性，不生图）
    area_bot = svg.h - 90
    lx, ly = fs, top + 10
    lw = svg.w * 0.42
    for i, ln in enumerate(wrap_cjk(d.get("point", ""), lw, 40)):
        svg.text(lx, ly + 30 + i * 52, ln, size=40, fill=pal["ink"], weight=800)
    ny = ly + 40 + len(wrap_cjk(d.get("point", ""), lw, 40)) * 52 + 20
    for i, ln in enumerate(wrap_cjk(d.get("note", ""), lw, 25)):
        svg.text(lx, ny + i * 36, ln, size=25, fill=pal["ink_soft"])
    # 右侧"天平/失衡"母题：一大一小 + 追赶箭头
    rx0 = svg.w * 0.48
    cx_big = rx0 + 200
    cx_small = svg.w - 200
    ground = area_bot - 60
    svg.rect(cx_big - 150, ground - 250, 300, 250, r=24, fill=pal["accent_soft"],
             stroke=pal["accent"], sw=2, shadow=True)
    svg.text(cx_big, ground - 150, d.get("left_big", "A"), size=34, fill=pal["accent"],
             weight=800, anchor="middle")
    for i, ln in enumerate(wrap_cjk(d.get("left_big_sub", ""), 260, 23)[:2]):
        svg.text(cx_big, ground - 90 + i * 32, ln, size=23, fill=pal["ink_soft"],
                 anchor="middle")
    svg.rect(cx_small - 90, ground - 110, 180, 110, r=18, fill=pal["bg_soft"],
             stroke=pal["line"], sw=2, shadow=True)
    svg.text(cx_small, ground - 60, d.get("right_small", "B"), size=26,
             fill=pal["ink_soft"], weight=700, anchor="middle")
    for i, ln in enumerate(wrap_cjk(d.get("right_small_sub", ""), 160, 20)[:2]):
        svg.text(cx_small, ground - 24 + i * 26, ln, size=20, fill=pal["ink_soft"],
                 anchor="middle")
    gap_mid = cx_small - 90 - (cx_big + 150)
    arrow_y = ground - 180
    svg.line(cx_big + 160, arrow_y, cx_small - 110, arrow_y, stroke=pal["red"],
             sw=4, dash="2 10", marker=True, opacity=0.8)
    if d.get("gap_label"):
        svg.text((cx_big + cx_small) / 2, arrow_y - 24, d["gap_label"], size=26,
                 fill=pal["red"], weight=700, anchor="middle")
    svg.line(fs + 40, ground, svg.w - fs - 40, ground, stroke=pal["line"], sw=3)


# ---- 布局 5：对比表（两/三列要点对照，强调差异）--------------------------------
def layout_compare(svg, d, pal, fs, top):
    cols = d["columns"]
    rows = d["rows"]
    n = len(cols)
    gap = 24
    label_w = 300
    grid_w = svg.w - 2 * fs - label_w - gap
    cw = (grid_w - gap * (n - 1)) / n
    head_h = 110
    row_h = (svg.h - top - 140 - head_h) / max(len(rows), 1)
    x0 = fs
    svg.rect(x0, top + 6, label_w, head_h, r=18, fill=pal["bg_soft"])
    svg.text(x0 + 28, top + 6 + head_h / 2 + 2, d.get("corner", ""), size=26,
             fill=pal["ink_soft"], weight=700)
    head_colors = [pal["accent"], pal["blue"], pal["green"], pal["purple"]]
    for j, c in enumerate(cols):
        x = x0 + label_w + gap + j * (cw + gap)
        col = head_colors[j % 4]
        svg.rect(x, top + 6, cw, head_h, r=18, fill=col)
        for k, ln in enumerate(wrap_cjk(c, cw - 40, 30)[:2]):
            svg.text(x + cw / 2, top + 6 + head_h / 2 - 12 + k * 38, ln, size=30,
                     fill="#fff", weight=800, anchor="middle")
    for i, row in enumerate(rows):
        y = top + 6 + head_h + 14 + i * row_h
        svg.rect(x0, y, label_w, row_h - 12, r=14, fill=pal["bg_soft"])
        for k, ln in enumerate(wrap_cjk(row["label"], label_w - 44, 24)[:3]):
            svg.text(x0 + 24, y + 40 + k * 32, ln, size=24, fill=pal["ink"], weight=600)
        for j in range(n):
            x = x0 + label_w + gap + j * (cw + gap)
            cell = row["values"][j] if j < len(row["values"]) else ""
            tone = None
            if isinstance(cell, dict):
                tone, cell = cell.get("tone"), cell.get("text", "")
            fill = pal["card"]; stroke = pal["line"]; tcol = pal["ink"]
            if tone == "good":
                fill, stroke, tcol = pal["green_soft"], pal["green"], pal["green"]
            elif tone == "bad":
                fill, stroke, tcol = pal["red_soft"], pal["red"], pal["red"]
            elif tone == "hl":
                fill, stroke, tcol = pal["accent_soft"], pal["accent"], pal["accent"]
            svg.rect(x, y, cw, row_h - 12, r=14, fill=fill, stroke=stroke, sw=1.6)
            for k, ln in enumerate(wrap_cjk(cell, cw - 40, 23)[:3]):
                svg.text(x + 22, y + 40 + k * 31, ln, size=23, fill=tcol)


# ---- 布局 6：中心辐射（一个中心，N 条要点）--------------------------------------
def layout_radial(svg, d, pal, fs, top):
    import math
    cx, cy = svg.w / 2, (top + svg.h - 90) / 2 + 20
    R = min(svg.w, svg.h) * 0.33
    nodes = d["nodes"]
    n = len(nodes)
    # 先画连线
    for i in range(n):
        ang = -math.pi / 2 + i * 2 * math.pi / n
        nx, ny = cx + R * math.cos(ang), cy + R * math.sin(ang)
        svg.line(cx, cy, nx, ny, stroke=pal["line"], sw=2.5)
    # 中心
    cr = 130
    svg.circle(cx, cy, cr, pal["accent"])
    for k, ln in enumerate(wrap_cjk(d.get("center", ""), cr * 1.5, 30)[:3]):
        svg.text(cx, cy - (len(wrap_cjk(d.get("center", ""), cr * 1.5, 30)) - 1) * 19
                 + k * 40, ln, size=30, fill="#fff", weight=800, anchor="middle")
    # 节点
    nw, nh = 280, 132
    for i, node in enumerate(nodes):
        ang = -math.pi / 2 + i * 2 * math.pi / n
        nx, ny = cx + R * math.cos(ang), cy + R * math.sin(ang)
        x, y = nx - nw / 2, ny - nh / 2
        svg.rect(x, y, nw, nh, r=20, fill=pal["card"], stroke=pal["blue"], sw=2, shadow=True)
        for k, ln in enumerate(wrap_cjk(node, nw - 40, 25)[:3]):
            svg.text(x + nw / 2, y + 44 + k * 34, ln, size=25, fill=pal["ink"],
                     weight=600, anchor="middle")


RENDERERS = {
    "pipeline": layout_pipeline,
    "columns": layout_columns,
    "two_stage": layout_two_stage,
    "metaphor": layout_metaphor,
    "compare": layout_compare,
    "radial": layout_radial,
}


def validate(spec):
    errs = []
    if not isinstance(spec, dict):
        return ["根必须是 JSON 对象"]
    if not spec.get("title"):
        errs.append("缺 title")
    layout = spec.get("layout")
    if layout not in RENDERERS:
        errs.append(f"layout 必须是 {sorted(RENDERERS)} 之一，得到 {layout!r}")
        return errs
    data = spec.get("data")
    if not isinstance(data, dict):
        errs.append("缺 data 对象")
        return errs
    need = {
        "pipeline": ("steps",), "columns": ("columns",), "two_stage": ("stages",),
        "metaphor": ("point",), "compare": ("columns", "rows"), "radial": ("center", "nodes"),
    }[layout]
    for k in need:
        if k not in data:
            errs.append(f"data 缺字段 {k}")
    if layout == "pipeline":
        steps = data.get("steps")
        if not isinstance(steps, list) or not (2 <= len(steps) <= 9):
            errs.append("pipeline 的 steps 必须是 2~9 项的数组")
    if layout == "compare":
        ncol = len(data["columns"])
        for i, row in enumerate(data.get("rows", [])):
            if len(row.get("values", [])) != ncol:
                errs.append(f"compare 第 {i+1} 行 values 数量与列数不一致")
    return errs


def render(spec, out_svg, png=False, width=1600, height=1067):
    pal = dict(DEFAULT)
    pal.update(spec.get("palette") or {})
    svg = S(width, height, pal["bg"])
    svg.defs(pal["accent"])
    fs = 64
    top = draw_header(svg, spec, pal, fs)
    footer_y = RENDERERS[spec["layout"]](svg, spec["data"], pal, fs, top)
    draw_footer(svg, spec, pal, y=footer_y)
    svg.save(out_svg)
    if png:
        return export_png(out_svg)
    return None


def export_png(svg_path):
    png_path = os.path.splitext(svg_path)[0] + ".png"
    rsvg = shutil.which("rsvg-convert")
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    try:
        if rsvg:
            subprocess.run([rsvg, "-f", "png", "-o", png_path, svg_path], check=True)
            return png_path
        if os.path.exists(chrome):
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                tmp = tf.name
            url = "file://" + os.path.abspath(svg_path)
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--force-device-scale-factor=2",
                            f"--screenshot={tmp}", "--window-size=1600,1067",
                            "--hide-scrollbars", url],
                           check=True, capture_output=True, timeout=90)
            shutil.move(tmp, png_path)
            return png_path
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[warn] PNG 转换失败（SVG 已生成）：{e}\n")
        return None
    sys.stderr.write("[warn] 未找到 rsvg-convert 或 Chrome，跳过 PNG（SVG 已生成）。\n")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", nargs="?", help="信息图 JSON 路径")
    ap.add_argument("--stdin", action="store_true", help="从标准输入读 JSON")
    ap.add_argument("-o", "--out", required=True, help="输出 SVG 路径")
    ap.add_argument("--png", action="store_true", help="同时导出 PNG")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=1067)
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args()
    try:
        if args.stdin:
            spec = json.load(sys.stdin)
        else:
            if not args.spec:
                ap.error("需要给 spec.json 或 --stdin")
            with open(args.spec, encoding="utf-8") as f:
                spec = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"读 JSON 失败：{e}", file=sys.stderr)
        return 1
    errs = validate(spec)
    if errs:
        print("schema 校验失败：", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 2
    if args.validate_only:
        print("schema OK")
        return 0
    png = render(spec, args.out, png=args.png, width=args.width, height=args.height)
    print(f"OK: {args.out}" + (f" + {png}" if png else "（未导出 PNG）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
