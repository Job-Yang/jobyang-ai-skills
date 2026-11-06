#!/usr/bin/env python3
"""Render two extra synthetic data charts (treemap, sankey) with Matplotlib.

Style, self-checks and artifact conventions mirror render_charts.py:
same masthead layout, document-pastel THEME palette, 200 dpi PNG plus vector
SVG (svg.fonttype=none, metadata Date=None, injected <title>/<desc>), and an
in-canvas text overflow assertion. Dependencies come only from bootstrap.

Layout algorithms are hand-rolled (numpy only): squarified treemap packing
and column-based sankey ribbons. No third-party layout packages.
"""
import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from bootstrap import require

matplotlib = require("matplotlib")[0]
matplotlib.use("Agg")
plt = require("matplotlib.pyplot")[0]
font_manager = require("matplotlib.font_manager")[0]
from matplotlib.colors import to_rgba
from matplotlib.patches import Rectangle, PathPatch
from matplotlib.path import Path as MplPath
from matplotlib.text import Text
np = require("numpy")[0]

THEME = json.loads(Path(__file__).with_name("theme.json").read_text())
INK, MUTED, GRID = THEME["ink"], THEME["muted"], THEME["grid"]
TONES = THEME["sequence"]
FONT_CANDIDATES = ["PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei",
                   "Arial Unicode MS", "Heiti TC", "DejaVu Sans"]


def configure():
    available = {f.name for f in font_manager.fontManager.ttflist}
    font = next((name for name in FONT_CANDIDATES if name in available), "DejaVu Sans")
    matplotlib.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": [font, "DejaVu Sans"],
        "font.size": 10.5, "text.color": INK, "axes.labelcolor": MUTED,
        "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": "#9DAABB",
        "svg.fonttype": "none", "svg.hashsalt": "engineering-docs-extra",
        "axes.unicode_minus": False, "axes.linewidth": .6,
        "lines.solid_capstyle": "round", "lines.solid_joinstyle": "round",
    })
    return font


def base(number, kind, title, subtitle, note, ax_rect=(.14, .20, .79, .51)):
    fig = plt.figure(figsize=(6.8, 5.2), dpi=100, facecolor="white")
    fig.text(.047, .94, f"{number}  /  {kind} · 合成数据", size=9.5, color=MUTED)
    fig.text(.047, .858, title, size=18, weight="bold")
    fig.text(.047, .800, subtitle, size=10.2, color=MUTED)
    fig.add_artist(plt.Line2D([.047, .953], [.106, .106], transform=fig.transFigure,
                             color=GRID, linewidth=.6))
    fig.text(.047, .052, note, size=9.1, color=MUTED)
    ax = fig.add_axes(ax_rect)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    return fig, ax


def check_texts(fig):
    """Reject any text label that crosses the canvas edge (mirrors
    render_templates.quantitative): every visible Text must keep a 3px margin."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for text in fig.findobj(match=Text):
        if not text.get_visible() or not text.get_text():
            continue
        bbox = text.get_window_extent(renderer)
        if not (bbox.x0 >= 3 and bbox.y0 >= 3
                and bbox.x1 <= fig.bbox.width - 3
                and bbox.y1 <= fig.bbox.height - 3):
            raise ValueError(f"Chart text outside canvas: {text.get_text()!r}")


def save(fig, out, key, title, note, kind):
    check_texts(fig)
    fig.savefig(out / f"{key}.png", dpi=200)
    fig.savefig(out / f"{key}.svg", metadata={"Date": None})
    path = out / f"{key}.svg"
    svg = path.read_text()
    root_end = svg.index(">", svg.index("<svg"))
    svg = (svg[:root_end + 1] + f"<title>{html.escape(title)}</title>"
           f"<desc>{html.escape(note)}</desc>" + svg[root_end + 1:])
    path.write_text(svg)
    plt.close(fig)
    return {"id": key, "type": kind, "title": title, "conclusion": note,
            "source": f"{key}.svg", "preview": f"{key}.png"}


# ---------------------------------------------------------------- treemap

def _worst_ratio(row_values, length):
    """Squarified treemap worst aspect ratio of a row (Bruls et al.)."""
    s = sum(row_values)
    mx, mn = max(row_values), min(row_values)
    return max(length ** 2 * mx / s ** 2, s ** 2 / (length ** 2 * mn))


def squarify(values, rect):
    """Squarified layout. values: list[float]; rect=(x, y, w, h) in data units.
    Returns list of (x, y, w, h) aligned with values, area proportional to value."""
    values = [float(v) for v in values]
    if not values or any(v < 0 for v in values) or sum(values) <= 0:
        raise ValueError("Treemap values must be finite, non-negative and positive overall.")
    x, y, w, h = rect
    total = sum(values)
    scale = w * h / total
    order = sorted(range(len(values)), key=lambda i: -values[i])
    out = [None] * len(values)

    def place(row_idx):
        nonlocal x, y, w, h
        rsum = sum(values[i] for i in row_idx)
        if w >= h:
            col_w = rsum * scale / h
            yy = y
            for k in row_idx:
                hh = values[k] * scale / col_w
                out[k] = (x, yy, col_w, hh)
                yy += hh
            x += col_w
            w -= col_w
        else:
            row_h = rsum * scale / w
            xx = x
            for k in row_idx:
                ww = values[k] * scale / row_h
                out[k] = (xx, y, ww, row_h)
                xx += ww
            y += row_h
            h -= row_h

    row, i = [], 0
    while i < len(order):
        k = order[i]
        if not row:
            row.append(k)
            i += 1
            continue
        length = min(w, h)
        if _worst_ratio([values[t] for t in row] + [values[k]], length) <= \
                _worst_ratio([values[t] for t in row], length):
            row.append(k)
            i += 1
        else:
            place(row)
            row = []
    if row:
        place(row)
    return out


def validate_treemap(groups):
    """Children sum equals the declared parent total; values finite and >= 0."""
    leaves = []
    for g in groups:
        children = g.get("children") or []
        if not children:
            raise ValueError(f"Treemap group {g.get('name')!r} has no children.")
        s = 0.0
        for c in children:
            v = float(c["value"])
            if not np.isfinite(v) or v < 0:
                raise ValueError(f"Treemap leaf {c.get('name')!r} has invalid value {v}.")
            s += v
        declared = g.get("total", s)
        if abs(declared - s) > 1e-6:
            raise AssertionError(
                f"Treemap parent {g.get('name')!r}: children sum {s:g} != total {declared:g}.")
        leaves.append({"group": g["name"], "group_total": s,
                       "children": [{"name": c["name"], "value": float(c["value"])}
                                    for c in children]})
    return leaves


def compute_treemap(groups, rect=(2, 2, 74, 96)):
    """Pure geometry: group rects and leaf rects. No drawing side effects."""
    leaves = validate_treemap(groups)
    group_totals = [g["group_total"] for g in leaves]
    group_rects = squarify(group_totals, rect)
    result = []
    for gi, (g, greg) in enumerate(zip(leaves, group_rects)):
        gx, gy, gw, gh = greg
        strip = 4.2
        inner = (gx + .7, gy + .7, gw - 1.4, gh - strip - .7)
        child_vals = [c["value"] for c in g["children"]]
        child_rects = squarify(child_vals, inner)
        result.append({"group": g["group"], "group_total": g["group_total"],
                       "group_rect": greg, "tone": TONES[gi % len(TONES)],
                       "children": [{"name": c["name"], "value": c["value"], "rect": r}
                                    for c, r in zip(g["children"], child_rects)]})
    return result


def render_treemap(data, out, key="22-treemap",
                   title="交易域占四成内存，基础设施合计不足一成",
                   subtitle="运行时堆内存占用（MiB）｜按服务进程聚合，2 层分组",
                   note="合成示例｜数据不代表真实系统；服务相邻不证明因果。"):
    groups = data["treemap"]["groups"]
    unit = data["treemap"].get("unit", "")
    layout = compute_treemap(groups)
    total = sum(g["group_total"] for g in layout)
    fig, ax = base("22", "矩形树图", title, subtitle, note,
                   ax_rect=(.05, .16, .74, .60))
    # Axes data area: x 0..100 over fig .05...79; legend column at data x ~80.
    for g in layout:
        tone = g["tone"]
        stroke, fill = THEME["colors"][tone]
        gx, gy, gw, gh = g["group_rect"]
        ax.add_patch(Rectangle((gx, gy), gw, gh, facecolor=fill,
                               edgecolor=stroke, linewidth=1.3, zorder=1))
        if gw >= 16:
            ax.text(gx + 1.4, gy + gh - 2.2, f"{g['group']} {g['group_total']:g} {unit}",
                    fontsize=9.5, color=stroke, weight="bold", va="center", zorder=4)
        else:
            ax.text(gx + gw / 2, gy + gh / 2, f"{g['group']} {g['group_total']:g}",
                    fontsize=9, color=stroke, weight="bold", va="center",
                    ha="center", rotation=90, zorder=4)
    # Decide in-cell vs legend labels using real pixel measurements.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bb = ax.get_window_extent(renderer)
    px_per_x = bb.width / 100.0
    px_per_y = bb.height / 100.0

    def text_w(text, fontsize):
        return sum(fontsize if ord(ch) > 0x2E7F else fontsize * .58 for ch in text)

    legend = []
    for g in layout:
        tone = g["tone"]
        stroke = THEME["colors"][tone][0]
        for c in g["children"]:
            lx, ly, lw, lh = c["rect"]
            share = c["value"] / total
            lines = [c["name"], f"{c['value']:g} {unit}"]
            need_w = max(text_w(t, 9) for t in lines) + 6
            need_h = 2 * 13 + 3
            fits = (lw * px_per_x >= need_w) and (lh * px_per_y >= need_h)
            c["share"] = share
            if fits:
                ax.text(lx + lw / 2, ly + lh / 2 + 3.4, lines[0], fontsize=9,
                        ha="center", va="center", color=INK, zorder=5)
                ax.text(lx + lw / 2, ly + lh / 2 - 3.6, lines[1], fontsize=8,
                        ha="center", va="center", color=MUTED, zorder=5)
            else:
                legend.append((g, c))
    # Leader-line legend: each entry sits at its own cell's vertical centre
    # (clamped, kept >=5.2 units apart), so lines stay short and horizontal;
    # sorted top->bottom keeps them from crossing each other.
    legend.sort(key=lambda item: -(item[1]["rect"][1] + item[1]["rect"][3] / 2))
    leg_x = 81.5
    prev_slot = 100.0
    for g, c in legend:
        tone = g["tone"]
        stroke = THEME["colors"][tone][0]
        fill = THEME["colors"][tone][1]
        lx, ly, lw, lh = c["rect"]
        cy = ly + lh / 2
        slot_y = min(max(cy, 7.0), 94.0)
        slot_y = min(slot_y, prev_slot - 5.2)
        prev_slot = slot_y
        ax.plot([lx + lw, leg_x - 1.2], [cy, slot_y], color=MUTED, lw=.6, zorder=2)
        ax.add_patch(Rectangle((leg_x - .8, slot_y - 1.0), 1.8, 2.0,
                               facecolor=fill, edgecolor=stroke, linewidth=.9, zorder=4))
        ax.text(leg_x + 1.6, slot_y, f"{c['name']} {c['value']:g} {unit} · {c['share']:.0%}",
                fontsize=8.2, va="center", ha="left", color=INK, zorder=4)
    leaves_stats = [{"group": g["group"], "name": c["name"], "value": c["value"],
                     "area": c["rect"][2] * c["rect"][3], "share": c["share"]}
                    for g in layout for c in g["children"]]
    stats = {"unit": unit, "total": total,
             "group_totals": {g["group"]: g["group_total"] for g in layout},
             "leaves": leaves_stats,
             "legend_count": len(legend)}
    manifest = save(fig, out, key, title, note, "矩形树图")
    return manifest, stats


# ------------------------------------------------------------------ sankey

def validate_sankey(nodes, links):
    """Conservation: internal nodes balance inflow == outflow; references exist;
    values finite and >= 0. Returns per-node flows."""
    names = [n["name"] for n in nodes]
    if len(set(names)) != len(names):
        raise ValueError("Sankey node names must be unique.")
    flow = {n["name"]: {"layer": int(n["layer"]), "in": 0.0, "out": 0.0}
            for n in nodes}
    for lk in links:
        if lk["source"] not in flow or lk["target"] not in flow:
            raise ValueError(f"Sankey link references unknown node: {lk}.")
        v = float(lk["value"])
        if not np.isfinite(v) or v < 0:
            raise ValueError(f"Sankey link {lk['source']}->{lk['target']} invalid: {v}.")
        flow[lk["source"]]["out"] += v
        flow[lk["target"]]["in"] += v
    for name, d in flow.items():
        if d["in"] > 0 and d["out"] > 0:
            assert abs(d["in"] - d["out"]) < 1e-6, \
                f"Sankey node {name!r} not conserved: in={d['in']:g} out={d['out']:g}."
    return flow


def compute_sankey(nodes, links, x_cols=(6, 46, 86), node_w=7.0,
                   y_top=96.0, y_bottom=4.0, gap=1.6):
    """Pure geometry: node rects and link ribbons in data units."""
    flow = validate_sankey(nodes, links)
    layers = sorted({d["layer"] for d in flow.values()})
    xs = {layer: x_cols[li] for li, layer in enumerate(layers)}
    total_h = y_top - y_bottom
    rects = {}
    for layer in layers:
        col = [name for name, d in flow.items() if d["layer"] == layer]
        col_total = sum(max(flow[n]["in"], flow[n]["out"]) for n in col)
        scale = (total_h - gap * (len(col) - 1)) / col_total
        y = y_top
        for name in col:  # stack top -> bottom
            h = max(flow[name]["in"], flow[name]["out"]) * scale
            rects[name] = {"x": xs[layer], "w": node_w, "y_top": y,
                           "y_bot": y - h, "layer": layer,
                           "total": max(flow[name]["in"], flow[name]["out"])}
            y -= h + gap
    # Link slots: sort by counterpart node vertical centre so ribbons don't cross.
    def centre(name):
        r = rects[name]
        return (r["y_top"] + r["y_bot"]) / 2
    out_slots = {n: [] for n in flow}
    in_slots = {n: [] for n in flow}
    ribbons = []
    by_link = [(lk["source"], lk["target"], float(lk["value"])) for lk in links]
    lookup = {(s, t): v for s, t, v in by_link}
    for name in flow:
        # Stack the top-most counterpart on the node's top edge, so ribbons
        # leave/enter in the same vertical order and don't flip mid-stream.
        outs = [t for s, t, v in by_link if s == name]
        outs.sort(key=centre, reverse=True)
        y = rects[name]["y_top"]
        for t in outs:
            v = lookup[(name, t)]
            h = v * (rects[name]["y_top"] - rects[name]["y_bot"]) / rects[name]["total"]
            out_slots[name].append((t, y, y - h))
            y -= h
        ins = [s for s, t, v in by_link if t == name]
        ins.sort(key=centre, reverse=True)
        y = rects[name]["y_top"]
        for s in ins:
            v = lookup[(s, name)]
            h = v * (rects[name]["y_top"] - rects[name]["y_bot"]) / rects[name]["total"]
            in_slots[name].append((s, y, y - h))
            y -= h
    for s, t, v in by_link:
        _, yt0, yt1 = [slot for slot in out_slots[s] if slot[0] == t][0]
        _, ys0, ys1 = [slot for slot in in_slots[t] if slot[0] == s][0]
        ribbons.append({"source": s, "target": t, "value": v,
                        "src_y": (yt0, yt1), "tgt_y": (ys0, ys1),
                        "x0": rects[s]["x"] + node_w, "x1": rects[t]["x"]})
    return {"rects": rects, "ribbons": ribbons, "flow": flow}


def render_sankey(data, out, key="23-sankey",
                  title="入口流量 11% 在降级链路被丢弃",
                  subtitle="请求流向（次/分钟）｜缓存与数据库为汇合点",
                  note="合成示例｜数据不代表真实系统；相邻流带不证明因果。"):
    nodes, links = data["sankey"]["nodes"], data["sankey"]["links"]
    unit = data["sankey"].get("unit", "")
    geom = compute_sankey(nodes, links)
    rects, ribbons, flow = geom["rects"], geom["ribbons"], geom["flow"]
    # Role colors: source blue, services cycle, convergence blue/gray, loss red.
    tone_of = {"入口请求": "blue", "降级丢弃": "red",
               "缓存命中": "teal", "数据库访问": "gray"}
    service_tones = ["purple", "amber", "blue", "gray"]
    si = 0
    fig, ax = base("23", "桑基流向图", title, subtitle, note,
                   ax_rect=(.05, .16, .78, .60))
    # Assign per-node tone deterministically: fixed roles first, then
    # middle-layer services cycle through the remaining document tones.
    node_tone = {n: tone_of[n] for n in tone_of}
    si = 0
    for n in nodes:
        if n["name"] in node_tone:
            continue
        node_tone[n["name"]] = service_tones[si % len(service_tones)]
        si += 1
    for rb in ribbons:
        stroke = THEME["colors"][node_tone[rb["source"]]][0]
        x0, x1 = rb["x0"], rb["x1"]
        xm = (x0 + x1) / 2
        yst, ysb = rb["src_y"]
        ytt, ytb = rb["tgt_y"]
        verts = [(x0, yst), (xm, yst), (xm, ytt), (x1, ytt),
                 (x1, ytb), (xm, ytb), (xm, ysb), (x0, ysb), (x0, yst)]
        codes = [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4,
                 MplPath.LINETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4,
                 MplPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=to_rgba(stroke, .30),
                               edgecolor="none", zorder=1))
    for name, r in rects.items():
        stroke, fill = THEME["colors"][node_tone[name]]
        ax.add_patch(Rectangle((r["x"], r["y_bot"]), r["w"], r["y_top"] - r["y_bot"],
                               facecolor=fill, edgecolor=stroke, linewidth=1.2, zorder=3))
    # Node labels: left source node inside; middle services to the left of their
    # node (white bbox sits above ribbons); right sinks inside except the small
    # loss sink, which gets an external red label.
    for name, r in rects.items():
        cy = (r["y_top"] + r["y_bot"]) / 2
        if name == "入口请求":
            ax.text(r["x"] + r["w"] / 2, cy + 3, name, fontsize=9.5,
                    ha="center", va="center", color=INK, zorder=4)
            ax.text(r["x"] + r["w"] / 2, cy - 3.4, f"{int(r['total']):,}",
                    fontsize=8.5, ha="center", va="center", color=MUTED, zorder=4)
        elif name == "降级丢弃":
            fig.text(.792, (cy / 100.0) * .60 + .16,
                     f"{name}\n{int(r['total']):,} · {r['total']/flow['入口请求']['out']:.0%}",
                     fontsize=8.4, color=THEME["colors"]["red"][0], va="center")
        elif r["layer"] == 1:
            ax.text(r["x"] - 1.5, cy, f"{name}\n{int(r['total']):,}",
                    fontsize=8.6, ha="right", va="center", color=INK, zorder=5,
                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.4})
        else:
            ax.text(r["x"] + r["w"] / 2, cy + 2.6, name, fontsize=9,
                    ha="center", va="center", color=INK, zorder=4)
            ax.text(r["x"] + r["w"] / 2, cy - 3.0, f"{int(r['total']):,}", fontsize=8,
                    ha="center", va="center", color=MUTED, zorder=4)
    # Value labels on wide ribbons only.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bb = ax.get_window_extent(renderer)
    px_per_y = bb.height / 100.0
    labelled = []
    for rb in ribbons:
        mid_h = (rb["src_y"][0] - rb["src_y"][1] + rb["tgt_y"][0] - rb["tgt_y"][1]) / 2
        if mid_h * px_per_y < 26:
            continue
        xm = (rb["x0"] + rb["x1"]) / 2
        ym = (rb["src_y"][0] + rb["src_y"][1] + rb["tgt_y"][0] + rb["tgt_y"][1]) / 4
        ax.text(xm, ym, f"{int(rb['value']):,}", fontsize=8.2, ha="center",
                va="center", color=INK, zorder=5,
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.2})
        labelled.append(rb["source"] + "→" + rb["target"])
    stats = {"unit": unit,
             "entry": flow["入口请求"]["out"],
             "node_flows": {n: {"in": flow[n]["in"], "out": flow[n]["out"]}
                            for n in flow},
             "loss": flow["降级丢弃"]["in"],
             "loss_share": flow["降级丢弃"]["in"] / flow["入口请求"]["out"],
             "ribbon_labels": labelled}
    manifest = save(fig, out, key, title, note, "桑基流向图")
    return manifest, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    configure()
    data = json.loads(Path(__file__).with_name("chart-data-extra.json").read_text())
    manifests, stats = [], {"synthetic": True}

    m_t, s_t = render_treemap(data, out)
    manifests.append(m_t)
    stats["treemap"] = s_t
    m_s, s_s = render_sankey(data, out)
    manifests.append(m_s)
    stats["sankey"] = s_s

    (out / "charts-extra.json").write_text(
        json.dumps(manifests, ensure_ascii=False, indent=2))
    (out / "chart-statistics-extra.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"Rendered {len(manifests)} extra charts in {out}")


if __name__ == "__main__":
    main()
