#!/usr/bin/env python3
"""Turn an SVG diagram into Feishu whiteboard nodes whose connectors follow their shapes.

Feishu converts SVG paths into connectors that only remember coordinates, so dragging
a card leaves its arrows behind. This script converts the SVG with the official
whiteboard-cli, then:

  1. binds every connector end that touches a shape border to that shape
     (smallest shape wins, so a card beats the zone around it);
  2. turns edge labels that sit on a connector into native connector captions,
     so the label moves with the line.

Output is OpenAPI JSON for `lark-cli whiteboard +update --input_format raw`.

    python3 lark_bind.py arch.svg -o arch.lark.json
    lark-cli whiteboard +update --whiteboard-token <token> --input_format raw \
        --source @arch.lark.json --as user
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

CLI = ["npx", "-y", "@larksuite/whiteboard-cli@^0.2.13"]
SIDES = ("left", "right", "top", "bottom")


def convert(svg_path):
    out = Path(svg_path).with_suffix(".openapi.tmp.json")
    cmd = CLI + ["-i", str(svg_path), "-f", "svg", "--to", "openapi", "--format", "json", "-o", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0 or not out.exists():
        raise SystemExit(f"whiteboard-cli failed ({proc.returncode}): {proc.stdout[-400:]} {proc.stderr[-400:]}")
    data = json.loads(out.read_text(encoding="utf-8"))
    out.unlink()
    return data


def box(n):
    return n["x"], n["y"], n["x"] + n["width"], n["y"] + n["height"]


def touch(shape, p, tol):
    """Side of shape whose border passes within tol of point p, else None."""
    x0, y0, x1, y1 = box(shape)
    px, py = p
    if y0 - tol <= py <= y1 + tol:
        if abs(px - x0) <= tol:
            return "left"
        if abs(px - x1) <= tol:
            return "right"
    if x0 - tol <= px <= x1 + tol:
        if abs(py - y0) <= tol:
            return "top"
        if abs(py - y1) <= tol:
            return "bottom"
    return None


def path_points(c):
    x, y = c["x"], c["y"]
    conn = c["connector"]
    start = conn["start"].get("position")
    end = conn["end"].get("position")
    if not start or not end:
        return None
    mids = [(x + t["x"], y + t["y"]) for t in conn.get("turning_points", [])]
    return [(start["x"], start["y"])] + mids + [(end["x"], end["y"])]


def project(points, p):
    """Distance from p to the polyline and the fraction of length at the closest point."""
    total = sum(math.dist(a, b) for a, b in zip(points, points[1:])) or 1.0
    best, walked, frac = float("inf"), 0.0, 0.5
    for a, b in zip(points, points[1:]):
        seg = math.dist(a, b)
        if seg == 0:
            continue
        t = max(0.0, min(1.0, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / seg ** 2))
        q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        d = math.dist(p, q)
        if d < best:
            best, frac = d, (walked + seg * t) / total
        walked += seg
    return best, frac


def bind(nodes, tol=2.5, caption_tol=2.0):
    shapes = [n for n in nodes if n["type"] == "composite_shape"]
    by_id = {n["id"]: n for n in nodes}
    children = {}
    for n in nodes:
        if n.get("parent_id"):
            children.setdefault(n["parent_id"], []).append(n)

    label_groups = []
    for gid, kids in children.items():
        kinds = sorted(k["type"] for k in kids)
        if kinds == ["composite_shape", "text_shape"]:
            shape = next(k for k in kids if k["type"] == "composite_shape")
            text = next(k for k in kids if k["type"] == "text_shape")
            st = shape.get("style", {})
            if st.get("border_style") == "none" and st.get("fill_color", "").lower() in ("#ffffff", "#fff"):
                label_groups.append((gid, shape, text))
    label_shape_ids = {s["id"] for _, s, _ in label_groups}
    targets = [s for s in shapes if s["id"] not in label_shape_ids]

    report = {"connectors": 0, "bound_connectors": 0, "free_lines": 0, "half_bound": [], "captions": 0}
    removed = set()
    for c in [n for n in nodes if n["type"] == "connector"]:
        report["connectors"] += 1
        conn = c["connector"]
        pts = path_points(c)
        found = {}
        for end_key in ("start", "end"):
            pos = conn[end_key].get("position")
            if not pos:
                continue
            p = (pos["x"], pos["y"])
            hits = [(s["width"] * s["height"], s, touch(s, p, tol)) for s in targets]
            hits = [h for h in hits if h[2]]
            if hits:
                _, s, side = min(hits, key=lambda h: h[0])
                rel = {"x": round(min(1, max(0, (p[0] - s["x"]) / s["width"])), 4),
                       "y": round(min(1, max(0, (p[1] - s["y"]) / s["height"])), 4)}
                found[end_key] = {"id": s["id"], "snap_to": side, "position": rel}
            else:
                found[end_key] = f"({p[0]:.0f},{p[1]:.0f})"
        attached = {k: v for k, v in found.items() if isinstance(v, dict)}
        if not attached:
            report["free_lines"] += 1  # legend samples or decorative strokes
        elif len(attached) < len(found):
            loose = [f"{k} at {v}" for k, v in found.items() if not isinstance(v, dict)]
            report["half_bound"].append(f'{c["id"]}: ' + ", ".join(loose))
        else:
            report["bound_connectors"] += 1
        for end_key, obj in attached.items():
            conn[end_key] = {"attached_object": obj, "arrow_style": conn[end_key].get("arrow_style", "none")}
            conn[f"{end_key}_object"] = dict(obj)
        if not pts:
            continue
        for gid, shape, text in label_groups:
            if gid in removed:
                continue
            center = (shape["x"] + shape["width"] / 2, shape["y"] + shape["height"] / 2)
            dist, frac = project(pts, center)
            if dist <= caption_tol:
                t = dict(text["text"])
                t["horizontal_align"] = "center"
                conn["captions"] = {"data": [t]}
                conn["caption_position"] = round(frac, 4)
                removed.update({gid, shape["id"], text["id"]})
                report["captions"] += 1
                break
    kept = [n for n in nodes if n["id"] not in removed]
    ids = {n["id"] for n in kept}
    for c in kept:
        if c["type"] == "connector":
            for k in ("start_object", "end_object"):
                if k in c["connector"] and c["connector"][k]["id"] not in ids:
                    raise SystemExit(f"internal error: {c['id']} binds to missing {c['connector'][k]['id']}")
    return kept, report


def stack(nodes):
    """Give top-level nodes an explicit z_index in document order (first = bottom).

    whiteboard-cli leaves top-level z_index unset, and the raw update API then stacks
    those nodes in reverse order: the page background ends up covering the whole diagram.
    """
    z = 0
    for n in nodes:
        if not n.get("parent_id"):
            n["z_index"] = z
            z += 1
    return nodes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="diagram .svg (converted with whiteboard-cli) or OpenAPI .json")
    ap.add_argument("-o", "--output", help="output JSON (default: <source>.lark.json)")
    ap.add_argument("--tol", type=float, default=2.5, help="max distance from a connector end to a shape border")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)
    src = Path(args.source)
    data = convert(src) if src.suffix.lower() == ".svg" else json.loads(src.read_text(encoding="utf-8"))
    nodes, report = bind(data["nodes"], tol=args.tol)
    stack(nodes)
    out = Path(args.output) if args.output else src.with_suffix(".lark.json")
    out.write_text(json.dumps({"nodes": nodes}, ensure_ascii=False), encoding="utf-8")
    report["output"] = str(out)
    report["nodes"] = len(nodes)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{out}: {report['nodes']} nodes; connectors {report['connectors']} "
              f"(bound {report['bound_connectors']}, free lines {report['free_lines']}), "
              f"captions {report['captions']}")
        for u in report["half_bound"]:
            print(f"  one end is not touching any shape: {u}")
    return 0 if not report["half_bound"] else 2


if __name__ == "__main__":
    sys.exit(main())
