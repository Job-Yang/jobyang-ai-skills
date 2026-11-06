#!/usr/bin/env python3
"""Lint an SVG diagram for portability, editability and readability at document width.

Platform-neutral core; only --board and --png are optional adapters.

    python3 diagram_check.py arch.svg                 # static checks (stdlib only)
    python3 diagram_check.py arch.svg --board         # + Feishu whiteboard check/census (optional)
    python3 diagram_check.py arch.svg --png arch.png  # + PNG preview (rsvg-convert or node+resvg)
    python3 diagram_check.py arch.svg --doc doc.md    # + names the document keeps using but the figure never shows
    python3 diagram_check.py a.svg b.svg --json

Errors: the file will not import or display correctly. Warnings: it will import,
but readers will struggle (tiny text, rainbow colours, tall strips) or an editable
whiteboard (e.g. Feishu) will turn parts into non-editable images.
"""
import argparse
import colorsys
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DOC_WIDTH = 800
LARK_CLI = ["npx", "-y", "@larksuite/whiteboard-cli@^0.2.13"]
NS = "{http://www.w3.org/2000/svg}"
RENDER_JS = r"""
const {Resvg} = require('@resvg/resvg-js'); const fs = require('fs');
const [,, input, output, width] = process.argv;
const r = new Resvg(fs.readFileSync(input), {fitTo: {mode: 'width', value: Number(width)}, background: '#ffffff',
  font: {loadSystemFonts: true, defaultFontFamily: 'Noto Sans CJK SC'}});
fs.writeFileSync(output, r.render().asPng());
"""


def num(v):
    m = re.match(r"\s*(-?[\d.]+)", str(v)) if v is not None else None
    return float(m.group(1)) if m else None


def style_of(el):
    out = {}
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def rgb(c):
    c = (c or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", c):
        return tuple(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
    if re.fullmatch(r"#[0-9a-f]{3}", c):
        return tuple(int(ch * 2, 16) / 255 for ch in c[1:])
    m = re.fullmatch(r"rgba?\(([^)]+)\)", c)
    if m:
        parts = [float(x) for x in m.group(1).split(",")[:3]]
        return tuple(p / 255 for p in parts)
    return None


def _group_boxes(root, ns):
    """Parse <g data-kind="zone|card"> into {id: bbox, fill, focal, labeled}.

    A card group's largest rect is the body; a second thin rect inside it is the
    focal left bar. A zone group carries its title as a text child."""
    zones, cards = [], []
    for g in root.findall(f".//{ns}g"):
        kind = g.get("data-kind")
        if kind not in ("zone", "card", "note"):
            continue
        rects = g.findall(f"{ns}rect")
        if not rects:
            continue
        main = max(rects, key=lambda r: (num(r.get("width")) or 0) * (num(r.get("height")) or 0))
        x, y = num(main.get("x")) or 0, num(main.get("y")) or 0
        w, h = num(main.get("width")) or 0, num(main.get("height")) or 0
        entry = {"id": g.get("data-id"), "box": (x, y, x + w, y + h),
                 "fill": (main.get("fill") or "").lower()}
        if kind == "zone":
            entry["labeled"] = any((t.text or "").strip() for t in g.findall(f"{ns}text"))
            zones.append(entry)
        else:
            entry["focal"] = any(
                r is not main and (num(r.get("width")) or 0) < 0.18 * max(w, 1)
                for r in rects)
            cards.append(entry)
    return zones, cards


def _lightness(c):
    v = rgb(c)
    if not v:
        return None
    return (max(v) + min(v)) / 2.0


def _layout_rules(root, ns, w, h, errors, warns):
    """Static (model-free) version of the engine's zone/layout checks.
    Hard errors: a card that does not sit inside its zone, or any shape that
    crosses the declared canvas edge (this is what made the doc show a scrollbar).
    Soft warnings: title-band crowding, identical zone/card fill, sparse or
    lopsided canvas, long detour edges."""
    zones, cards = _group_boxes(root, ns)
    eps = 1.0
    # 1) every shape must stay inside the declared canvas with a breathing margin.
    margin = max(8.0, 0.02 * min(w, h))
    for z in zones:
        zb = z["box"]
        if zb[0] < -eps or zb[1] < -eps or zb[2] > w + eps or zb[3] > h + eps:
            errors.append(f"区域 {z['id']} 超出画布（{w:.0f}×{h:.0f}）：内容包围盒或画布 H/W 没收敛")
    for c in cards:
        cb = c["box"]
        if cb[0] < margin - eps or cb[1] < margin - eps or cb[2] > w - margin + eps or cb[3] > h - margin + eps:
            errors.append(f"卡片/便签 {c['id']} 超出画布边距：{tuple(round(v) for v in cb)} 应落在 "
                          f"[{margin:.0f},{w-margin:.0f}]×[{margin:.0f},{h-margin:.0f}] 内")
    # 7) text must keep an inner padding from its own card/note container (runs even
    # when there is no zone, e.g. a standalone card).
    def _tw(s, fs):
        return sum(1.0 if ord(c) > 0x2E80 else 0.58 for c in s) * fs
    for g in root.iter(f"{ns}g"):
        if g.get("data-kind") not in ("card", "note"):
            continue
        rid = g.get("data-id")
        rect = next((c for c in g if c.tag == f"{ns}rect"), None)
        if rect is None:
            continue
        rx, ry = float(rect.get("x")), float(rect.get("y"))
        rw, rh = float(rect.get("width")), float(rect.get("height"))
        for t in g.findall(f"{ns}text"):
            s = (t.text or "").strip()
            if not s:
                continue
            fs = float(t.get("font-size", 13))
            tx, ty = float(t.get("x")), float(t.get("y"))
            gaps = {
                "左": tx - rx,
                "右": rx + rw - (tx + _tw(s, fs)),
                "上": (ty - fs * 0.85) - ry,
                "下": (ry + rh) - (ty + fs * 0.25),
            }
            for side, gv in gaps.items():
                if gv < 0:
                    errors.append(f"文字“{s[:14]}”{side}侧穿出容器 {rid}：正文行数/高度估算不足，加高卡片或缩短文字")
                elif gv < 6:
                    warns.append(f"文字“{s[:14]}”{side}侧距容器 {rid} 仅 {gv:.0f}px（<6px）：内边距不足")
    if not zones or not cards:
        return

    def inside(card, zone):
        cx = (card["box"][0] + card["box"][2]) / 2
        cy = (card["box"][1] + card["box"][3]) / 2
        return zone["box"][0] - eps <= cx <= zone["box"][2] + eps and \
            zone["box"][1] - eps <= cy <= zone["box"][3] + eps

    for c in cards:
        z = min([z for z in zones if inside(c, z)],
                key=lambda z: (z["box"][2]-z["box"][0])*(z["box"][3]-z["box"][1]), default=None)
        if z is None:
            continue
        zb, cb = z["box"], c["box"]
        if cb[0] < zb[0]-eps or cb[2] > zb[2]+eps or cb[1] < zb[1]-eps or cb[3] > zb[3]+eps:
            errors.append(f"卡片 {c['id']} 没有完整落在区域 {z['id']} 内：撑高/加宽区域或把卡片收进边距")
        elif z["labeled"] and cb[1] < zb[1] + 40:
            warns.append(f"卡片 {c['id']} 与区域 {z['id']} 标题贴得太近：卡片顶部应在标题带（约40px）之下")
        else:
            lz, lc = _lightness(z["fill"]), _lightness(c["fill"])
            if lz is not None and lc is not None and not c["focal"] and abs(lz-lc) < 0.02:
                warns.append(f"卡片 {c['id']} 填充与区域 {z['id']} 底色几乎相同：卡片改白底、区域用更浅的底或加描边")
    # content footprint = cards only (zones are containers), like the engine check.
    x0 = min(c["box"][0] for c in cards)
    x1 = max(c["box"][2] for c in cards)
    y0 = min(c["box"][1] for c in cards)
    y1 = max(c["box"][3] for c in cards)
    coverage = (x1-x0)*(y1-y0) / (w*h) if w and h else 1
    margin = 32 * (w/960.0 if w else 1)
    left_gap, right_gap = x0-margin, w-margin-x1
    if coverage < 0.42:
        warns.append(f"内容只占画布 {coverage:.0%}：右侧/上下大片空白，按内容收紧画布或均衡铺开")
    elif right_gap > left_gap*2.2 and right_gap > 3.5*margin:
        warns.append(f"右侧空白（{right_gap:.0f}px）远大于左侧（{left_gap:.0f}px）：重心偏左，裁掉空白或均衡列")


def _edge_polylines(root, ns):
    """Orthogonal H/V segments of every path plus its data-points waypoints (if present)."""
    out = []
    for el in root.findall(f".//{ns}path"):
        d = el.get("d") or ""
        pts = [(float(x), float(y)) for x, y in re.findall(r"(?:M|L)\s*([-\d.]+)\s+([-\d.]+)", d)]
        # Only true axis-aligned segments count for crossing checks: a segment between two
        # waypoints that differ on BOTH axes is a rounded-elbow diagonal (Q control point) and
        # must be reconstructed with the intermediate waypoint, not tested as-is.
        def ortho(points):
            out = []
            for p, q in zip(points, points[1:]):
                if abs(p[0] - q[0]) < .01 or abs(p[1] - q[1]) < .01:
                    out.append((p, q))
                else:
                    mid = (q[0], p[1])
                    out.extend([(p, mid), (mid, q)])
            return out
        segs = ortho(pts)
        dp_pts = []
        dp = el.get("data-points")
        if dp:
            for pair in dp.split():
                parts = pair.split(",")
                if len(parts) == 2:
                    try:
                        dp_pts.append((float(parts[0]), float(parts[1])))
                    except ValueError:
                        pass
        out.append((el, segs, dp_pts or pts))
    return out


def _hv_cross(p, q, r, s):
    h1, h2 = abs(p[1] - q[1]) < .01, abs(r[1] - s[1]) < .01
    if h1 == h2:
        return None
    (hx0, hy), (hx1, _) = (p, q) if h1 else (r, s)
    (vx, vy0), (_, vy1) = (r, s) if h1 else (p, q)
    if min(hx0, hx1) + .5 < vx < max(hx0, hx1) - .5 and \
            min(vy0, vy1) + .5 < hy < max(vy0, vy1) - .5:
        return vx, hy
    return None


def _shared_joint(points1, points2, x, y, tol=.5):
    """True when (x,y) is a waypoint of BOTH routes (a fan-out bus join, not a crossing)."""
    def has(points):
        return any(abs(px - x) < tol and abs(py - y) < tol for px, py in points)
    return has(points1) and has(points2)


def static_check(path, standard_svg=False):
    raw = Path(path).read_text(encoding="utf-8")
    errors, warns = [], []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return {"file": str(path), "ok": False, "errors": [f"不是合法 XML：{e}"], "warnings": [], "metrics": {}}
    if not root.tag.endswith("svg") or "http://www.w3.org/2000/svg" not in root.tag:
        errors.append("根元素不是带 xmlns 的 <svg>")
    vb = root.get("viewBox")
    if vb:
        _, _, w, h = [float(x) for x in re.split(r"[\s,]+", vb.strip())]
    else:
        errors.append("缺少 viewBox：嵌入文档后无法按宽度缩放")
        w, h = num(root.get("width")) or 0, num(root.get("height")) or 0

    for tag, why in (("foreignObject", "HTML 片段在画板导入器（飞书等）和多数渲染器里会丢失"),
                     ("pattern", "pattern 填充在部分画板（飞书等）不支持"),
                     ("clipPath", "clipPath 裁剪在部分画板（飞书等）不支持"),
                     ("mask", "mask 蒙版在部分画板（飞书等）不支持"),
                     ("script", "脚本会被所有文档环境拦截")):
        n = len(root.findall(f".//{NS}{tag}"))
        if n:
            if standard_svg and tag in {"pattern", "clipPath", "mask"}:
                warns.append(f"包含 <{tag}> ×{n}：标准SVG可显示，画板导入需另行验证")
            else:
                errors.append(f"使用了 <{tag}> ×{n}：{why}")
    for img in root.findall(f".//{NS}image"):
        href = img.get("href") or img.get("{http://www.w3.org/1999/xlink}href") or ""
        if not href.startswith("data:"):
            errors.append("引用了外部图片：换平台后会丢失，内联或改成矢量")
        else:
            warns.append("内嵌了位图：这部分在画板（飞书等）里不可编辑")
    for f in root.findall(f".//{NS}filter"):
        kinds = {c.tag.replace(NS, "") for c in f}
        if kinds - {"feDropShadow", "feOffset", "feGaussianBlur", "feMerge", "feMergeNode", "feFlood",
                    "feComposite", "feColorMatrix", "feBlend"} or "feDropShadow" not in kinds:
            warns.append(f"滤镜 {f.get('id')} 不是单纯投影：飞书画板只保留 feDropShadow，其它导入器可能整条丢弃")
    drawn = [c for c in root if c.tag.replace(NS, "") not in ("defs", "title", "desc", "style", "metadata")]
    if len(drawn) == 1 and drawn[0].tag == f"{NS}g" and len(list(drawn[0])) > 1:
        warns.append("整张图包在一个 <g> 里：导入画板后是一个整体组，改成每个组件一个 <g>")
    for g in root.findall(f".//{NS}linearGradient") + root.findall(f".//{NS}radialGradient"):
        if g.get("gradientUnits") == "userSpaceOnUse":
            warns.append(f"渐变 {g.get('id')} 使用 userSpaceOnUse：飞书等导入器会丢掉，改用 objectBoundingBox")
    reverse = sum(1 for m in root.findall(f".//{NS}marker") if m.get("orient") == "auto-start-reverse")
    if reverse:
        warns.append(f"箭头标记用了 orient=\"auto-start-reverse\" ×{reverse}：resvg 等渲染器不旋转它，"
                     "竖向连线的箭头会横着画；终点箭头改用 orient=\"auto\"")

    # Edge geometry: edge-edge crossings and too many bends are soft warnings. A crossing at a
    # shared fan-out/fan-in waypoint is a bus join (both routes turn there), not a crossing.
    edge_routes = _edge_polylines(root, NS)

    def _ortho(points, fallback):
        out = []
        for p, q in zip(points, points[1:]):
            if abs(p[0] - q[0]) < .01 or abs(p[1] - q[1]) < .01:
                out.append((p, q))
            else:
                mid = (q[0], p[1])
                out.extend([(p, mid), (mid, q)])
        return out or fallback

    for i in range(len(edge_routes)):
        _, segs_i, dp_i = edge_routes[i]
        route_i = _ortho(dp_i, segs_i)
        for j in range(i + 1, len(edge_routes)):
            _, segs_j, dp_j = edge_routes[j]
            route_j = _ortho(dp_j, segs_j)
            for p, q in route_i:
                for r, ss in route_j:
                    hit = _hv_cross(p, q, r, ss)
                    if hit and not _shared_joint(dp_i, dp_j, *hit):
                        warns.append(
                            f"两条不相关连线在 ({hit[0]:.0f},{hit[1]:.0f}) 附近交叉：这是对理解影响最大的问题，"
                            "重排节点顺序或让其中一条走外侧通道")
                        break
                else:
                    continue
                break
    for _, _, dp in edge_routes:
        bends = len(dp) - 2
        if bends > 2:
            warns.append(f"一条连线有 {bends} 个拐点：拆图或走外侧通道（前向连线建议 ≤1 个 90° 拐点）")

    # Zone integrity / layout density / long-edge detour (model-free static mirrors).
    _layout_rules(root, NS, w, h, errors, warns)
    for el, segs, dp in edge_routes:
        if len(dp) < 2:
            continue
        (x0, y0), (x1, y1) = dp[0], dp[-1]
        manhattan = abs(x1 - x0) + abs(y1 - y0)
        if manhattan < 1:
            continue
        route = sum(abs(q[0]-p[0]) + abs(q[1]-p[1]) for p, q in zip(dp, dp[1:]))
        if route > 60 and route / manhattan > 2.1:
            warns.append(f"连线 {el.get('data-from') or '?'}→{el.get('data-to') or '?'} 路由长 {route:.0f}px，"
                         f"是两端直线距离的 {route/manhattan:.1f} 倍：长边绕远，改就近通道或贴标注")

    sizes, texts, colors = [], [], set()

    def walk(el, fs):
        tag = el.tag.replace(NS, "")
        st = style_of(el)
        size = num(el.get("font-size") or st.get("font-size")) or fs
        if tag == "text":
            content = "".join(el.itertext()).strip()
            if content:
                texts.append(content)
                sizes.append(size or 16)
        for attr in ("fill", "stroke"):
            v = el.get(attr) or st.get(attr)
            if v and v != "none" and tag in ("rect", "circle", "ellipse", "polygon", "path", "line", "polyline"):
                colors.add(v.lower())
        for ch in el:
            walk(ch, size)

    walk(root, None)
    scale = DOC_WIDTH / w if w else 1.0
    if not texts:
        errors.append("没有 <text>：文字被转成路径或图片后无法编辑和检索")
    at_doc = sorted(s * scale for s in sizes)
    font_min = round(at_doc[0], 1) if at_doc else None
    font_median = round(at_doc[len(at_doc) // 2], 1) if at_doc else None
    if font_min is not None and font_min < 8:
        errors.append(f"最小字号在 {DOC_WIDTH}px 文档宽度下只有 {font_min}px：放大画布字号或减少内容")
    elif font_min is not None and font_min < 9:
        warns.append(f"最小字号在 {DOC_WIDTH}px 宽度下 {font_min}px，辅助文字建议 ≥9px")
    if font_median is not None and font_median < 10.5:
        warns.append(f"正文字号中位数在 {DOC_WIDTH}px 宽度下 {font_median}px，建议 ≥10.5px：图太挤，拆图或把同类部件并成标签")
    hues = set()
    for c in colors:
        v = rgb(c)
        if not v:
            continue
        hh, l, s = colorsys.rgb_to_hls(*v)
        if s > 0.3 and 0.15 < l < 0.92:
            hues.add(int((hh * 360 + 15) // 30) % 12)
    if len(hues) > 3:
        warns.append(f"用了 {len(hues)} 个色系：颜色应表达含义（重点、风险、规划），不要给每组换一种颜色")
    aspect = round(h / w, 2) if w else None
    if aspect and aspect > 1.3:
        warns.append(f"高宽比 {aspect}：在文档里要滚动才能看完，改横向排布或拆成两张图")
    if len(texts) > 140:
        warns.append(f"{len(texts)} 段文字：图承担了正文的工作，把细节移回正文或表格")
    has_title = root.find(f"{NS}title") is not None
    metrics = {"width": w, "height": h, "aspect_h_over_w": aspect, "texts": len(texts),
               "font_min_at_800": font_min, "font_median_at_800": font_median, "hue_families": len(hues),
               "colors": len(colors), "has_title_element": has_title}
    return {"file": str(path), "ok": not errors, "errors": errors, "warnings": warns, "metrics": metrics,
            "texts": texts}


def doc_coverage(doc, fig_texts, r, min_count=4):
    """List component-like names the document uses often but the figure never shows.

    Names are Latin proper names and plain code spans (`Gateway`, `config-sync`); API paths and
    calls stay in the text. Only names that also head a non-appendix H2/H3 become warnings.
    """
    body = re.sub(r"```.*?```", "", Path(doc).read_text(encoding="utf-8"), flags=re.S)
    counts = {}
    for pat in (r"`([A-Za-z][A-Za-z0-9_-]{1,39})`",
                r"(?<![A-Za-z0-9_./`-])([A-Z][A-Za-z]+(?:[ -][A-Z][A-Za-z]+)*)(?![A-Za-z0-9_`])"):
        for m in re.finditer(pat, body):
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    fig = " ".join(fig_texts)
    missing = sorted(((n, c) for n, c in counts.items() if c >= min_count and n not in fig), key=lambda x: -x[1])
    heads = " ".join(h for h in re.findall(r"(?m)^#{2,3} (.+)$", body) if not re.match(r"(附录|Appendix)", h))
    r["metrics"]["doc_names_missing"] = [f"{n}×{c}" for n, c in missing[:12]]
    for n, _ in missing:
        if n in heads:
            r["warnings"].append(f"正文标题里的 {n} 在图里没有出现：总览要让读者找到它，至少作为一个标签")


def board_check(path, r):
    """Optional Feishu whiteboard compatibility check (platform-specific adapter)."""
    def run(args):
        p = subprocess.run(LARK_CLI + args, capture_output=True, text=True, timeout=240)
        out = p.stdout
        return json.loads(out[out.find("{"):]) if "{" in out else {}
    try:
        j = run(["-i", str(path), "-f", "svg", "--check"])
        chk = (j.get("data") or {}).get("check") or j.get("check") or {}
        issues = chk.get("issues") or []
        for it in issues:
            (r["errors"] if it.get("severity") == "error" else r["warnings"]).append(
                f"飞书画板检查 {it.get('type')}: {it.get('message')}")
        tmp = Path(path).with_suffix(".check.openapi.json")
        run(["-i", str(path), "-f", "svg", "--to", "openapi", "--format", "json", "-o", str(tmp)])
        nodes = json.loads(tmp.read_text(encoding="utf-8")).get("nodes", [])
        tmp.unlink()
        census = {}
        for n in nodes:
            census[n.get("type")] = census.get(n.get("type"), 0) + 1
        frozen = census.get("svg", 0) + census.get("image", 0)
        if frozen:
            r["warnings"].append(f"{frozen} 个元素在飞书画板里会变成图片节点（不可编辑）：常见原因是圆角大于高度一半、"
                                 "复杂路径或不支持的属性")
        editable = sum(v for k, v in census.items() if k not in ("svg", "image"))
        r["metrics"]["board_nodes"] = census
        r["metrics"]["board_editable_ratio"] = round(editable / max(1, editable + frozen), 3)
    except Exception as e:  # network or npx missing: report, do not crash
        r["warnings"].append(f"飞书画板检查未运行（不影响 SVG/PNG 交付）：{str(e)[:160]}")
    r["ok"] = not r["errors"]


def render_png(path, png, width=1600):
    """Best-effort platform-neutral PNG preview, tried in order:
    rsvg-convert (system binary) -> node + @resvg/resvg-js -> whiteboard-cli.
    None return means the PNG was written; a string is a human-readable skip reason.
    """
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        p = subprocess.run([rsvg, "-w", str(width), "-b", "white", "-o", str(png), str(path)],
                           capture_output=True, text=True, timeout=120)
        if p.returncode == 0 and Path(png).exists():
            return None
    node = shutil.which("node")
    if not node:
        return ("未找到 PNG 渲染工具，跳过预览：安装 librsvg（brew install librsvg）或 Node 后可生成；"
                "SVG 本身已生成，不影响交付")
    p = subprocess.run([node, "-e", RENDER_JS, str(path), str(png), str(width)], capture_output=True, text=True,
                       timeout=120)
    if p.returncode != 0:
        p = subprocess.run(LARK_CLI + ["-i", str(path), "-f", "svg", "-o", str(png)], capture_output=True, text=True,
                           timeout=240)
        if p.returncode != 0:
            return "PNG 预览失败：需要 librsvg（rsvg-convert）、@resvg/resvg-js 或 whiteboard-cli 之一"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("svg", nargs="+")
    ap.add_argument("--board", "--lark", dest="board", action="store_true",
                    help="optional Feishu whiteboard compatibility check and editable-node census "
                         "(platform adapter; never required for the SVG/PNG deliverable)")
    ap.add_argument("--png", help="write a PNG preview (single input only)")
    ap.add_argument("--doc", help="the document the figure belongs to; lists names it uses but the figure omits")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="fail on warnings too")
    ap.add_argument("--standard-svg", action="store_true", help="allow standard SVG clipping/pattern/mask for data charts; not a whiteboard compatibility claim")
    args = ap.parse_args(argv)
    if args.standard_svg and args.board:
        ap.error("--standard-svg 与 --board 不能同时使用；标准SVG展示和画板兼容需要分别验证。")
    results = []
    for f in args.svg:
        r = static_check(f, standard_svg=args.standard_svg)
        if args.standard_svg:
            r["validation_mode"] = "standard-svg"
        texts = r.pop("texts", [])
        if args.doc and r["metrics"]:
            doc_coverage(args.doc, texts, r)
        if args.board and r["metrics"]:
            board_check(f, r)
        if args.png and len(args.svg) == 1:
            msg = render_png(f, args.png)
            if msg:
                r["warnings"].append(msg)
        results.append(r)
    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False, indent=2))
    else:
        for r in results:
            m = r["metrics"]
            extra = f"，飞书画板可编辑 {m['board_editable_ratio']:.0%}" if "board_editable_ratio" in m else ""
            print(f"{r['file']}: {m.get('width', 0):.0f}×{m.get('height', 0):.0f}，最小字号@800 "
                  f"{m.get('font_min_at_800')}px，色系 {m.get('hue_families')}{extra}")
            for e in r["errors"]:
                print(f"  错误：{e}")
            for w in r["warnings"]:
                print(f"  提醒：{w}")
            if m.get("doc_names_missing"):
                print(f"  正文常用、图里没有：{'、'.join(m['doc_names_missing'])}（逐个确认总览上要不要出现）")
            if not r["errors"] and not r["warnings"]:
                print("  检查通过")
    failed = any(r["errors"] or (args.strict and r["warnings"]) for r in results)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
