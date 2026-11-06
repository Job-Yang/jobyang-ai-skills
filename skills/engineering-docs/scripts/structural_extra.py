"""Extra structural layouts: stage_gate / causal_chain / feedback_loop /
state_machine / image_annotate / sequence / er.

Each builder takes a spec dict and returns a render_templates.Canvas instance; the
unified wiring layer calls .save(path). Pure standard library; no matplotlib.
"""
import base64
import binascii
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_templates import Canvas, check, tone, wrap, units, THEME, INK, MUTED, LINE, paint
from visual_theme import structural_tone  # noqa: E402

# Retain the historical semantic view; these are not data category colours.
SEM = {key: list(structural_tone({"tone": value})) for key, value in
       {"blue": "accent", "purple": "neutral", "teal": "success", "amber": "warning",
        "red": "error", "gray": "neutral"}.items()}
GREEN, GREEN_BG = SEM["teal"]
RED, RED_BG = SEM["red"]
AMBER, AMBER_BG = SEM["amber"]
GRAY, GRAY_BG = SEM["gray"]
ACCENT, ACCENT_BG = SEM["blue"]


def pill(canvas, cx, cy, text, color=INK):
    """White label pill centered at (cx, cy) text baseline; colored text."""
    w = units(text) * 12 + 12
    canvas.rect(cx - w / 2, cy - 13, w, 18, "white", "none", 3)
    canvas.text(cx, cy, text, 12, color, anchor="middle", width=w)


def manual_box(canvas, key, x, y, w, h, text, fill, border, size=12, color=INK):
    """Small card drawn by hand (below box()'s 42px minimum height), bounds-checked."""
    if border in {LINE, GRAY} and fill in {"white", GRAY_BG, THEME["panel_bg"]}:
        fill, border = THEME["entity_fill"], THEME["entity_border"]
    canvas.rect(x, y, w, h, fill, border, 6)
    canvas.text(x + 10, y + h / 2 + size / 2 - 3, text, size, color, width=w - 18)
    canvas.boxes[key] = (x, y, w, h)


# ---------------------------------------------------------------------------
# 1. stage_gate: 横向阶段 + 阶段间门禁（passed/blocked），blocked 有阻断分支
# ---------------------------------------------------------------------------
def stage_gate(spec):
    stages = spec["stages"]
    gates = spec["gates"]
    check(2 <= len(stages) <= 3, "阶段门横向支持 2–3 个阶段。")
    ids = [s["id"] for s in stages]
    check(len(set(ids)) == len(ids), "阶段 id 重复。")
    check(len(gates) == len(stages) - 1, "相邻阶段之间各需要一个门禁。")
    order = {sid: i for i, sid in enumerate(ids)}
    afters = [g["after"] for g in gates]
    check(len(set(afters)) == len(afters), "门禁 after 重复。")
    for g in gates:
        check(g["after"] in order, f"门禁 after 指向未知阶段：{g['after']}")
        check(g["status"] in ("passed", "blocked"), "门禁 status 只能是 passed/blocked。")
    gates = sorted(gates, key=lambda g: order[g["after"]])

    c = Canvas(spec, 420)
    sw, sh, sy = 150, 86, 140
    gap = (616 - len(stages) * sw) / (len(stages) - 1)
    xs = [32 + i * (sw + gap) for i in range(len(stages))]
    cy = sy + sh / 2
    for i, s in enumerate(stages):
        c.box(f"stage-{s['id']}", xs[i], sy, sw, sh, s["label"],
              f"准入：{s['entry']}\n准出：{s['exit']}", index=i, **paint(s))
    for g in gates:
        i = order[g["after"]]
        cx = xs[i] + sw + gap / 2
        passed = g["status"] == "passed"
        stroke, fill = (GREEN, GREEN_BG) if passed else (RED, RED_BG)
        # Gate = a fully Feishu-editable rounded capsule (rx = h/2), not a polygon
        # diamond (whiteboard-cli freezes <polygon> into an image node).
        gw, gh = 40, 48
        # The Feishu importer treats a rect whose corner radius reaches half its
        # *narrower* side as an ellipse and freezes it to an image node. Keep rx one
        # unit below min(w,h)/2 so the gate still renders as an editable pill.
        c.rect(cx - gw / 2, cy - gh / 2, gw, gh, fill, stroke, radius=min(gw, gh) / 2 - 1)
        c.text(cx, cy + 7, "✓" if passed else "×", 20, GREEN if passed else RED,
               anchor="middle", width=gw)
        c.path(f"M{xs[i]+sw} {cy} H{cx-gw/2}")
        c.path(f"M{cx+gw/2} {cy} H{xs[i+1]}", arrow=True)
        # Gate status label sits ABOVE the capsule (in the inter-card gap) so the
        # blocked branch line that drops from the capsule bottom never crosses the
        # label text, the main horizontal line, or a stage card.
        c.text(cx, cy - gh / 2 - 10, f"{g['label']} · {'通过' if passed else '阻断'}", 12,
               GREEN if passed else INK, anchor="middle", width=112)
        if not passed:
            c.path(f"M{cx} {cy+gh/2} V270", color=RED, arrow=True)
            manual_box(c, f"block-{g['id']}", cx - 65, 270, 130, 44,
                       g.get("note", "阻断：修复后重验"), RED_BG, RED, color=INK)
    return c


# ---------------------------------------------------------------------------
# 2. causal_chain: 左到右因果链，边带极性，可上挂分支，不交叉
# ---------------------------------------------------------------------------
def causal_chain(spec):
    chain = spec["chain"]
    links = spec.get("links", [])
    branches = spec.get("branches", [])
    check(2 <= len(chain) <= 5, "因果链支持 2–5 个节点。")
    ids = [n["id"] for n in chain]
    check(len(set(ids)) == len(chain), "因果节点 id 重复。")
    pos = {sid: i for i, sid in enumerate(ids)}
    for e in links:
        check(e["from"] in pos and e.get("to") in pos, f"悬空边：{e['from']}->{e.get('to')}")
        check(e.get("polarity") in ("+", "-"), "极性只能是 +（增强）或 -（抑制）。")
    for b in branches:
        check(b["from"] in pos, f"分支挂在未知节点：{b['from']}")
        check(b.get("polarity") in ("+", "-"), "极性只能是 +（增强）或 -（抑制）。")
    check(len(branches) <= 2, "最多 2 条分支。")
    used = {}
    for b in branches:
        used[b["from"]] = used.get(b["from"], 0) + 1
        check(used[b["from"]] == 1, "一个节点最多挂一条分支。")

    c = Canvas(spec, 355)
    n = len(chain)
    nw, nh, ny = 110, 58, 210
    pitch = (648 - 32 - nw) / (n - 1)
    xs = [32 + i * pitch for i in range(n)]
    centers = [x + nw / 2 for x in xs]
    for i, node in enumerate(chain):
        c.box(f"cause-{node['id']}", xs[i], ny, nw, nh, node["label"], index=i, **paint(node))
    for e in links:
        a, b = pos[e["from"]], pos[e["to"]]
        check(b > a, "因果链只能从前向节点指向后向节点。")
        color = GREEN if e["polarity"] == "+" else RED
        c.path(f"M{xs[a]+nw} {ny+nh/2} H{xs[b]}", color=color, width=1.4, arrow=True)
        midx = (xs[a] + nw + xs[b]) / 2
        text = ("+ 增强" if e["polarity"] == "+" else "− 抑制") + (f" · {e['note']}" if e.get("note") else "")
        pill(c, midx, ny + nh / 2 + 28, text, color)
    for b in branches:
        a = pos[b["from"]]
        bx = centers[a] - nw / 2
        c.box(f"branch-{b['from']}", bx, 130, nw, 64, b["label"], "", index=0, **paint(b))
        color = GREEN if b["polarity"] == "+" else RED
        c.path(f"M{centers[a]} {ny} V194", color=color, width=1.4, arrow=True)
        pill(c, centers[a], 202, "+ 增强" if b["polarity"] == "+" else "− 抑制", color)
    return c


# ---------------------------------------------------------------------------
# 3. feedback_loop: 主处理节点 + 外围回环边，标注极性与触发条件
# ---------------------------------------------------------------------------
def feedback_loop(spec):
    for key in ("input", "process", "output", "trigger"):
        check(isinstance(spec.get(key), str) and spec[key], f"feedback_loop 缺少字段：{key}")
    check(spec["polarity"] in ("positive", "negative"), "polarity 只能是 positive/negative。")
    negative = spec["polarity"] == "negative"
    color = GREEN if negative else RED

    c = Canvas(spec, 425)
    c.box("fl-process", 240, 165, 200, 90, spec["process"], "", index=1, filled=True)
    c.box("fl-in", 48, 195, 110, 44, spec["input"], "", index=5)
    c.box("fl-out", 520, 195, 110, 44, spec["output"], "", index=5)
    c.path("M158 217 H240", arrow=True)
    c.path("M440 217 H520", arrow=True)
    # 回环走外围底部：输出底部 -> 下 -> 左 -> 输入底部，不穿过任何节点
    c.path("M575 239 V320 H103 V239", color=color, width=1.5, arrow=True, dash=True)
    label = ("负反馈 · 自我收敛" if negative else "正反馈 · 自我放大") + f" · 触发：{spec['trigger']}"
    pill(c, 240, 308, label, color)
    if spec.get("intervention"):
        manual_box(c, "fl-inject", 430, 302, 140, 36, spec["intervention"],
                   AMBER_BG, AMBER, size=12)
    return c


def _polyline_clears_boxes(points, boxes, exclude):
    """Return the first box interior that a polyline segment passes through, else
    None. Used to forbid the retry/back edge from cutting across any state card."""
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        for key, (rx, ry, rw, rh) in boxes.items():
            if key in exclude:
                continue
            tol = 1.0  # tolerate touching a border, only flag crossing the interior
            ix0, iy0, ix1, iy1 = rx + tol, ry + tol, rx + rw - tol, ry + rh - tol
            if abs(y1 - y2) < 0.5:  # horizontal segment
                y = y1
                if iy0 < y < iy1 and min(x1, x2) < ix1 and max(x1, x2) > ix0:
                    return key
            elif abs(x1 - x2) < 0.5:  # vertical segment
                x = x1
                if ix0 < x < ix1 and min(y1, y2) < iy1 and max(y1, y2) > iy0:
                    return key
    return None


def _hv_cross_interior(s1, s2):
    """True if one H and one V segment cross at a point interior to BOTH
    (shared endpoints/card borders are joins, not crossings)."""
    (x1, y1), (x2, y2) = s1
    (x3, y3), (x4, y4) = s2
    h1 = abs(y1 - y2) < 0.5
    if h1 == (abs(y3 - y4) < 0.5):
        return False  # parallel segments never cross
    if h1:
        hx0, hx1, hy = x1, x2, y1
        vx, vy0, vy1 = x3, y3, y4
    else:
        hx0, hx1, hy = x3, x4, y3
        vx, vy0, vy1 = x1, y1, y2
    return (min(hx0, hx1) + 1 < vx < max(hx0, hx1) - 1 and
            min(vy0, vy1) + 1 < hy < max(vy0, vy1) - 1)


# ---------------------------------------------------------------------------
# 4. state_machine: 无交叉布局引擎
#
# 布局契约（算法级，不写死坐标）：
#   1) 主干状态沿一条水平主轴等距排列、共用同一 y 基线；起点为实心圆，
#      主迁移沿主轴直线推进，箭头落在卡片左/右边的规范端口。
#   2) 分叉状态（异常等）从主干节点向上侧或下侧引一条短支线单独放置，
#      进出边短而正交，不横穿其它卡片。
#   3) 所有逆向/回退统一走卡片最外侧的专用通道带：先垂落到通道高度，
#      再水平回到目标上方，再垂直向上，箭头清楚落在起点/目标；多条回退
#      按"源-目标跨度"分到不同通道层，互不重叠；回退一律虚线，标签放
#      通道内（白底 pill 不压线）。
#   4) 渲染期几何硬错误：①任一迁移边不穿过非其端点的节点卡片内部；
#      ②非回退边两两不交叉（回退通道的正交跨越点是唯一被允许的例外）；
#      ③同一对状态之间不得出现多条重叠边；④回退边必须落在声明的外侧
#      通道带内。违反即 raise ValueError。
# ---------------------------------------------------------------------------
def state_machine(spec):
    states = spec["states"]
    trans = spec["transitions"]
    check(2 <= len(states) <= 8, "状态机支持 2–8 个状态。")
    ids = [s["id"] for s in states]
    check(len(set(ids)) == len(states), "状态 id 重复。")
    check("start" in spec and spec["start"] in ids, "start 必须是存在的状态。")
    check(ids[0] == spec["start"], "start 必须是 states 列表的第一个（起点先于一切状态）。")
    for s in states:
        check(s.get("kind", "normal") in ("normal", "end"), "状态 kind 只能是 normal/end。")
    pos = {sid: i for i, sid in enumerate(ids)}
    for t in trans:
        check(t["from"] in pos and t["to"] in pos, f"悬空迁移：{t['from']}->{t['to']}")
    # 硬错误③：同一对状态之间不得出现多条彼此重叠的边。
    check(len({(t["from"], t["to"]) for t in trans}) == len(trans),
          "同一对状态之间出现多条边；合并迁移标签或换图表达。")
    fwd = [t for t in trans if pos[t["to"]] > pos[t["from"]]]
    back = [t for t in trans if pos[t["to"]] < pos[t["from"]]]

    # ---- 1) 布局推导：主干 = 从 start 沿前向边贪心走到的链（每步选序号最
    # 小的下一状态）；其余前向目标一律是挂在父主干节点旁的短分叉。
    spine, branches = [], []
    cur = spec["start"]
    while True:
        outs = sorted([t for t in fwd if t["from"] == cur], key=lambda t: pos[t["to"]])
        if not outs:
            break
        spine.append(outs[0]["to"])
        branches.extend((cur, t) for t in outs[1:])
        cur = outs[0]["to"]
    check(len(spine) >= 1, "至少需要一条从 start 出发的前向迁移。")
    for parent, t in branches:
        check(parent != spec["start"],
              f"分叉 {t['to']} 不能直接挂在起点实心圆上：先经过第一个主干状态。")

    # ---- 2) 坐标：主轴一行等距；分叉按父主干序号奇偶分上/下两侧，同父的
    # 第二条分叉自动分到另一侧。
    nw, nh = 100, 46
    x0, spine_y = 76, 216
    n = len(spine)
    pitch = (648 - x0 - nw) / max(n - 1, 1)
    xs = [x0 + i * pitch for i in range(n)]
    up_y, down_y = 130, 306
    cy = spine_y + nh / 2
    box = {}
    for i, sid in enumerate(spine):
        box[sid] = (xs[i], spine_y, nw, nh)
    spine_idx = {sid: i for i, sid in enumerate(spine)}
    branch_count = {}
    for parent, t in branches:
        sid = t["to"]
        k = branch_count.get(parent, 0)
        branch_count[parent] = k + 1
        base = "down" if spine_idx[parent] % 2 == 0 else "up"
        side = base if k == 0 else ("up" if base == "down" else "down")
        px = box[parent][0]
        box[sid] = (px, up_y if side == "up" else down_y, nw, nh)
    lowest_bottom = max(y + h for (_, y, _, h) in box.values())

    # 回退通道分层：跨度大的回退走更靠外（更下）的层。
    back_sorted = sorted(back, key=lambda t: pos[t["from"]] - pos[t["to"]])
    layer_gap = 26
    channel_top = lowest_bottom + 32
    _bp = {t["to"]: p for p, t in branches}
    n_chan = sum(1 for t in back if _bp.get(t["from"]) != t["to"])
    height = channel_top + max(n_chan - 1, 0) * layer_gap + (110 if n_chan else 60)
    c = Canvas(spec, height)

    # ---- 3) 画状态：起点实心圆；普通状态白卡；终态=两个嵌套可编辑圆角矩形。
    start_cx, start_cy, start_r = 52, cy, 13
    c.shape("circle", cx=start_cx, cy=start_cy, r=start_r, fill=INK)
    by_id = {s["id"]: s for s in states}
    for sid, (x, y, w, h) in box.items():
        c.boxes[f"sm-{sid}"] = (x, y, w, h)
        stroke, fill = structural_tone(by_id[sid])
        if by_id[sid].get("kind") == "end":
            gap = 6
            c.shape("rect", x=x, y=y, width=w, height=h, rx=8, fill=fill,
                    stroke=stroke, stroke_width=2.0)
            c.shape("rect", x=x + gap, y=y + gap, width=w - 2 * gap, height=h - 2 * gap,
                    rx=6, fill=fill, stroke=stroke, stroke_width=1.0)
        else:
            c.rect(x, y, w, h, fill, stroke, 8)
        c.text(x + w / 2, y + h / 2 + 5, by_id[sid]["label"], 13, INK, anchor="middle", width=w - 16)

    routes = []  # (points, is_back)
    # ---- 4) 主干前向边：主轴直线；分叉短正交支线。
    def add_route(pts, is_back=False):
        routes.append((pts, is_back))
        return pts

    first = spine[0]
    fx, fy, fw, fh = box[first]
    add_route([(start_cx + start_r, start_cy), (fx, start_cy)])
    if spec["start"] in [t["from"] for t in fwd]:
        t0 = next(t for t in fwd if t["from"] == spec["start"])
        pill(c, (start_cx + start_r + fx) / 2, start_cy - 15, t0["label"])
    for i in range(n - 1):
        ax, _, aw, _ = box[spine[i]]
        bx = box[spine[i + 1]][0]
        add_route([(ax + aw, cy), (bx, cy)])
        lbl = next((t["label"] for t in fwd
                    if t["from"] == spine[i] and t["to"] == spine[i + 1]), None)
        if lbl:
            pill(c, (ax + aw + bx) / 2, cy - 15, lbl)
    for parent, t in branches:
        px, py, pw, ph = box[parent]
        sid = t["to"]
        bx, by, bw, bh = box[sid]
        cxm = bx + bw / 2
        paired_back = any(tt["from"] == sid and tt["to"] == parent for tt in back)
        # 分叉标签统一放在支线左侧：右侧留给回退边的出入口。
        lx = cxm - (18 if paired_back else 0) - (units(t["label"]) * 12 + 12) / 2 - 6
        if by > py:  # down branch: from parent bottom to branch top
            add_route([(cxm, py + ph), (cxm, by)])
            pill(c, lx, (py + ph + by) / 2, t["label"])
        else:        # up branch: from parent top to branch bottom
            add_route([(cxm, py), (cxm, by + bh)])
            pill(c, lx, (py + by + bh) / 2, t["label"])

    # ---- 5) 回退边。
    # (a) 分叉状态回到自己的父主干状态：画成与分叉边平行的短竖线（左右各偏 18px），
    #     不进外侧通道；这是最常见的「失败→重试」「等待→恢复」形态。
    # (b) 其余回退走外侧通道带：每条回退独占一条竖向走廊和一层通道，目标端口在
    #     卡片底边按序错开，不与其它边共线。
    branch_parent = {t["to"]: parent for parent, t in branches}
    pair_back = [t for t in back if branch_parent.get(t["from"]) == t["to"]]
    chan_back = [t for t in back_sorted if t not in pair_back]
    for t in pair_back:
        bx_, by_, bw_, bh_ = box[t["from"]]
        px_, py_, pw_, ph_ = box[t["to"]]
        xx = bx_ + bw_ / 2 + 18
        if by_ > py_:
            pts = [(xx, by_), (xx, py_ + ph_)]
        else:
            pts = [(xx, by_ + bh_), (xx, py_)]
        add_route(pts, is_back=True)
        c.path(f"M{pts[0][0]:.1f} {pts[0][1]:.1f} L{pts[1][0]:.1f} {pts[1][1]:.1f}", arrow=True, dash=True)
        pill(c, xx + 6 + (units(t["label"]) * 12 + 12) / 2, (pts[0][1] + pts[1][1]) / 2 + 5, t["label"])
    # 前向分叉边让出中线右侧给回退：把这些分叉的前向边左移 18px。
    paired = {t["from"] for t in pair_back}
    for idx, (pts, is_back) in enumerate(routes):
        if is_back or len(pts) != 2 or pts[0][0] != pts[1][0]:
            continue
        for sid in paired:
            bx_, by_, bw_, bh_ = box[sid]
            if abs(pts[0][0] - (bx_ + bw_ / 2)) < 0.5 and (abs(pts[1][1] - by_) < 0.5 or abs(pts[1][1] - (by_ + bh_)) < 0.5):
                routes[idx] = ([(pts[0][0] - 18, pts[0][1]), (pts[1][0] - 18, pts[1][1])], False)

    corr = [(xs[i] + nw + xs[i + 1]) / 2 for i in range(n - 1)] + [xs[-1] + nw + 14]
    used_corr, used_port = set(), {}

    def take_corr(near_x, prefer_right=None):
        cands = [cx_ for cx_ in corr if cx_ not in used_corr]
        if prefer_right is True:
            cands = [cx_ for cx_ in cands if cx_ > near_x] or cands
        elif prefer_right is False:
            cands = [cx_ for cx_ in cands if cx_ < near_x] or cands
        check(cands, "回退边太多，走廊不够：把异常生命周期拆成第二张状态图。")
        got = min(cands, key=lambda cx_: abs(cx_ - near_x))
        used_corr.add(got)
        return got

    def has_down_branch(sid):
        return any(pp == sid and box[tt["to"]][1] > box[sid][1] for pp, tt in branches)

    channel_rows = sorted(chan_back, key=lambda t: pos[t["from"]] - pos[t["to"]])
    for k, t in enumerate(channel_rows):
        channel_y = channel_top + k * layer_gap
        a, b = t["from"], t["to"]
        ax, ay, aw, ah = box[a]
        # 出口：从源卡片底边离开，不沿主轴走（沿主轴会和前向边叠成一条线）。
        is_up_branch = a in branch_parent and ay < box[branch_parent[a]][1]
        if is_up_branch:
            drop_x = take_corr(ax + aw, prefer_right=True)
            head = [(ax + aw, ay + ah / 2), (drop_x, ay + ah / 2), (drop_x, channel_y)]
        elif has_down_branch(a):
            drop_x = take_corr(ax + aw, prefer_right=True)
            sx = ax + aw * 0.82
            jy = ay + ah + 12
            head = [(sx, ay + ah), (sx, jy), (drop_x, jy), (drop_x, channel_y)]
        else:
            sx = ax + aw * 0.82
            head = [(sx, ay + ah), (sx, channel_y)]
        # 入口：从目标卡片底边进入，多条汇入时端口错开。
        if b == spec["start"]:
            tail = [(start_cx, channel_y), (start_cx, start_cy + start_r)]
        else:
            bx, by, bw, bh = box[b]
            slot = used_port.get(b, 0)
            used_port[b] = slot + 1
            if has_down_branch(b):
                fracs = [0.78, 0.9]
                check(slot < len(fracs), f"太多回退边汇入 {b}：拆图或合并迁移。")
                tx = bx + bw * fracs[slot]
                up_x = take_corr(bx + bw, prefer_right=True)
                jog_y = by + bh + 22 + slot * 12
                tail = [(up_x, channel_y), (up_x, jog_y), (tx, jog_y), (tx, by + bh)]
            else:
                fracs = [0.5, 0.32, 0.66]
                check(slot < len(fracs), f"太多回退边汇入 {b}：拆图或合并迁移。")
                tx = bx + bw * fracs[slot]
                tail = [(tx, channel_y), (tx, by + bh)]
        pts = head + tail
        # 合并共线的相邻点
        clean = [pts[0]]
        for p_ in pts[1:]:
            if abs(p_[0] - clean[-1][0]) < 0.5 and abs(p_[1] - clean[-1][1]) < 0.5:
                continue
            clean.append(p_)
        pts = clean
        add_route(pts, is_back=True)
        d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}" + "".join(f" L{p_[0]:.1f} {p_[1]:.1f}" for p_ in pts[1:])
        c.path(d, arrow=True, dash=True)
        # 标签放在通道横段中点
        seg = max(((pts[i], pts[i + 1]) for i in range(len(pts) - 1)
                   if abs(pts[i][1] - channel_y) < 0.5 and abs(pts[i + 1][1] - channel_y) < 0.5),
                  key=lambda sg: abs(sg[1][0] - sg[0][0]), default=None)
        lx = (seg[0][0] + seg[1][0]) / 2 if seg else pts[-1][0]
        pill(c, lx, channel_y - 6, t["label"])

    # ---- 6) 主干/分叉边路径（回退已在上面直接画）。
    drawn = set()
    for pts, is_back in routes:
        if is_back:
            continue
        key = tuple(pts)
        if key in drawn:
            continue
        drawn.add(key)
        d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
        for p in pts[1:]:
            d += f" L{p[0]:.1f} {p[1]:.1f}"
        c.path(d, arrow=True)

    # ---- 7) 渲染期几何硬错误。
    box_full = {f"sm-{sid}": v for sid, v in box.items()}
    for pts, is_back in routes:
        hit = _polyline_clears_boxes(pts, box_full, exclude=set())
        check(hit is None, f"迁移边穿过状态卡 {hit}；端口或通道需要重排。")
    for i in range(len(routes)):
        for j in range(i + 1, len(routes)):
            p1, b1 = routes[i]
            p2, b2 = routes[j]
            if b1 or b2:
                continue  # 回退通道在正交跨越点是被允许的唯一例外
            for s1 in zip(p1, p1[1:]):
                for s2 in zip(p2, p2[1:]):
                    check(not _hv_cross_interior(s1, s2),
                          "两条非回退迁移边发生交叉；调整主干/分叉布局。")
    # 硬错误⑤：任意两条边不得共线重叠（两条线叠成一条，读者分不清走向）。
    def _overlap(s1, s2):
        (x1, y1), (x2, y2) = s1
        (x3, y3), (x4, y4) = s2
        if abs(y1 - y2) < 0.5 and abs(y3 - y4) < 0.5 and abs(y1 - y3) < 0.5:
            return min(max(x1, x2), max(x3, x4)) - max(min(x1, x2), min(x3, x4)) > 2
        if abs(x1 - x2) < 0.5 and abs(x3 - x4) < 0.5 and abs(x1 - x3) < 0.5:
            return min(max(y1, y2), max(y3, y4)) - max(min(y1, y2), min(y3, y4)) > 2
        return False
    for i in range(len(routes)):
        for j in range(i + 1, len(routes)):
            for s1 in zip(routes[i][0], routes[i][0][1:]):
                for s2 in zip(routes[j][0], routes[j][0][1:]):
                    check(not _overlap(s1, s2), "两条迁移边共线重叠；拆图或减少回退边。")
    # 硬错误⑥：回退边不得横穿主干/分叉的前向边（回退之间的正交跨越仍允许）。
    for pb, ib in routes:
        if not ib:
            continue
        for pf, iff in routes:
            if iff:
                continue
            for s1 in zip(pb, pb[1:]):
                for s2 in zip(pf, pf[1:]):
                    check(not _hv_cross_interior(s1, s2), "回退边横穿前向迁移；调整状态顺序或拆图。")
    # 硬错误④：回退边必须真正进入声明的外侧通道带（所有卡片之下、画布之上）。
    band_top = lowest_bottom + 18
    for pts, is_back in routes:
        if not is_back or len(pts) == 2:
            continue  # 父子平行短边不进通道带
        ys = [p[1] for p in pts]
        check(max(ys) >= band_top, "回退边未进入外侧通道带。")
        check(max(ys) <= c.height - 88, "回退边越出画布底部。")
    return c


# ---------------------------------------------------------------------------
# 5. image_annotate: 内嵌 base64 位图 + 框/编号/引导 + 右侧图例表
# ---------------------------------------------------------------------------
def _png_size(data):
    check(data[:8] == b"\x89PNG\r\n\x1a\n", "底图必须是 PNG。")
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def image_annotate(spec):
    markers = spec["markers"]
    check(1 <= len(markers) <= 6, "截图标注支持 1–6 个标记。")
    nums = sorted(m["n"] for m in markers)
    check(nums == list(range(1, len(markers) + 1)), "标记编号必须从 1 连续编号。")
    for m in markers:
        for key in ("problem", "action"):
            check(isinstance(m.get(key), str) and m[key], "标记缺少 problem/action。")
        for key in ("x", "y", "w", "h"):
            check(isinstance(m.get(key), (int, float)) and m[key] > 0, "标记框坐标必须为正数。")
    if spec.get("image_b64"):
        data = base64.b64decode(spec["image_b64"])
    else:
        root = Path(__file__).resolve().parents[1]
        image = Path(spec["image_path"]).expanduser()
        if not image.is_absolute():
            local = Path.cwd() / image
            image = local if local.is_file() else root / image
        data = image.read_bytes()
    iw, ih = _png_size(data)
    for m in markers:
        check(m["x"] + m["w"] + 24 <= iw and m["y"] + m["h"] + 24 <= ih,
              f"标记 #{m['n']} 超出截图边界。")
    b64 = binascii.b2a_base64(data).decode().strip()

    max_w, max_h = 410, 300
    scale = min(max_w / iw, max_h / ih)
    dw, dh = iw * scale, ih * scale
    offx, offy = 32, 150

    c = Canvas(spec, 150 + dh + 95)
    c.shape("image", x=offx, y=offy, width=round(dw, 1), height=round(dh, 1),
            href=f"data:image/png;base64,{b64}")
    for m in markers:
        rx, ry = offx + m["x"] * scale, offy + m["y"] * scale
        rw, rh = m["w"] * scale, m["h"] * scale
        c.rect(rx, ry, rw, rh, "none", RED, 3)
        c.shape("circle", cx=rx + 10, cy=ry + 10, r=9, fill=RED_BG, stroke=RED)
        c.text(rx + 10, ry + 14, str(m["n"]), 11, INK, weight=600, anchor="middle", width=20)
    c.text(462, 158, "问题与动作", 14, INK, weight=600, width=180)
    y = 176
    for m in markers:
        manual_box(c, f"ev-{m['n']}", 462, y, 186, 26, f"问题：{m['problem']}", GRAY_BG, GRAY)
        manual_box(c, f"ac-{m['n']}", 462, y + 30, 186, 26, f"动作：{m['action']}", ACCENT_BG, ACCENT)
        y += 64
    return c


# ---------------------------------------------------------------------------
# 6. sequence: 参与者 + 生命线 + 按先后排列的消息（同步/异步/返回/自调用），可分阶段
#
# 布局契约：参与者横向等距（2–5 个），纵向只表示先后、不表示耗时；每条消息独占一行，
# 标签放在箭头上方且必须放得进两条生命线之间；阶段底色只包住它的消息。
# ---------------------------------------------------------------------------
SEQ_KINDS = ("sync", "async", "reply", "self")


def sequence(spec):
    parts = spec["participants"]
    msgs = spec["messages"]
    groups = spec.get("groups", [])
    check(2 <= len(parts) <= 5, "时序图支持 2–5 个参与者；更多请拆图或合并参与者。")
    check(1 <= len(msgs) <= 16, "时序图支持 1–16 条消息；更多请按阶段拆图。")
    ids = [p["id"] for p in parts]
    check(len(set(ids)) == len(ids), "参与者 id 重复。")
    col = {pid: i for i, pid in enumerate(ids)}
    for m in msgs:
        check(m.get("kind", "sync") in SEQ_KINDS, f"消息 kind 只能是 {'/'.join(SEQ_KINDS)}。")
        check(m["from"] in col and m["to"] in col, f"悬空消息：{m['from']}->{m['to']}")
        if m.get("kind") == "self":
            check(m["from"] == m["to"], "self 消息的 from/to 必须相同。")
        else:
            check(m["from"] != m["to"], "非 self 消息不能自己发给自己；改用 kind=self。")
    for g in groups:
        check(0 <= g["start"] <= g["end"] < len(msgs), f"阶段 {g['label']} 的消息区间越界。")
    starts = {g["start"]: g for g in groups}

    pitch = 616 / len(parts)
    cx = [32 + pitch * (i + 0.5) for i in range(len(parts))]
    bw = min(132, pitch - 14)
    head_y, head_h = 140, 44
    # 先排纵坐标：阶段开头留出阶段名的位置，self 消息多占半行。
    ys, y = [], head_y + head_h + 34
    for i, m in enumerate(msgs):
        if i in starts:
            y += 22
        ys.append(y)
        y += 54 if m.get("kind") == "self" else 40
    bottom = y - 10
    c = Canvas(spec, bottom + 120)

    for gi, g in enumerate(groups):
        top = ys[g["start"]] - 44
        last = msgs[g["end"]]
        end = ys[g["end"]] + (36 if last.get("kind") == "self" else 14)
        c.rect(28, top, 624, end - top, structural_tone(g)[1], "none", 8)
        c.text(36, top + 15, g["label"], 12, MUTED, 500, width=200)
    for i, p in enumerate(parts):
        x = cx[i]
        c.rect(x - bw / 2, head_y, bw, head_h, structural_tone(p)[1], structural_tone(p)[0], 8)
        c.text(x, head_y + 28, p["label"], 14, INK, 600, width=bw - 10, anchor="middle")
        c.boxes[f"seq-{p['id']}"] = (x - bw / 2, head_y, bw, head_h)
        c.path(f"M{x:.1f} {head_y + head_h} V{bottom}", color=LINE, width=1, dash=True)
    for m, y in zip(msgs, ys):
        kind = m.get("kind", "sync")
        a = cx[col[m["from"]]]
        if kind == "self":
            right = col[m["from"]] < len(parts) - 1
            dx = 26 if right else -26
            c.path(f"M{a:.1f} {y} H{a + dx:.1f} V{y + 20} H{a:.1f}", color=INK, width=1.3, arrow=True)
            tx = a + dx + (8 if right else -8)
            c.text(tx, y + 15, m["label"], 12, INK, width=pitch - 40, anchor="start" if right else "end")
            continue
        b = cx[col[m["to"]]]
        color = MUTED if kind == "reply" else INK
        c.path(f"M{a:.1f} {y} H{b:.1f}", color=color, width=1.3, arrow=True, dash=(kind != "sync"))
        span = abs(b - a)
        w = units(m["label"]) * 13 + 10
        check(w <= span - 8, f"消息标签放不下：{m['label']}；缩短标签或调整参与者顺序。")
        c.label((a + b) / 2, y - 7, m["label"])
    legend = "实线：同步调用    虚线：异步消息或返回    折回箭头：自身处理"
    c.text(32, bottom + 22, spec.get("legend", legend), 12, MUTED, width=616)
    return c


# ---------------------------------------------------------------------------
# 7. er: 实体按网格摆放（≤3 列 × ≤4 行），关系标基数；同行/同列直连，其余走 L 形，
#    任何关系线都不得穿过非端点实体（渲染期硬错误）。
# ---------------------------------------------------------------------------
def er(spec):
    ents = spec["entities"]
    rels = spec["relations"]
    check(2 <= len(ents) <= 12, "ER 图支持 2–12 个实体；更多请按领域拆图。")
    cols = max(e["col"] for e in ents) + 1
    rows = max(e["row"] for e in ents) + 1
    check(cols <= 3 and rows <= 4, "ER 网格最多 3 列 × 4 行。")
    by = {e["id"]: e for e in ents}
    check(len(by) == len(ents), "实体 id 重复。")
    check(len({(e["col"], e["row"]) for e in ents}) == len(ents), "两个实体占了同一格。")
    cellw = 616 / cols
    w = min(176, cellw - 52)
    fh = 19

    def eh(e):
        return 32 + max(1, len(e.get("fields", []))) * fh + 8

    row_h = [max([eh(e) for e in ents if e["row"] == r] or [40]) for r in range(rows)]
    row_y, y = [], 150
    for r in range(rows):
        row_y.append(y)
        y += row_h[r] + 66
    c = Canvas(spec, y - 66 + 150)
    box = {}
    for e in ents:
        x = 32 + cellw * e["col"] + (cellw - w) / 2
        yy = row_y[e["row"]]
        h = eh(e)
        box[e["id"]] = (x, yy, w, h)
        c.boxes[f"er-{e['id']}"] = (x, yy, w, h)
        stroke, fill = structural_tone(e)
        c.rect(x, yy, w, h, "white", stroke, 8)
        c.rect(x + 1, yy + 1, w - 2, 28, fill, "none", 7)
        c.text(x + 10, yy + 20, e["label"], 13, INK, 600, width=w - 16)
        for i, f in enumerate(e.get("fields", [])):
            c.text(x + 10, yy + 48 + i * fh, f, 12, MUTED, width=w - 16)
    full = {f"er-{k}": v for k, v in box.items()}
    seen_ports = set()
    for r in rels:
        check(r["from"] in box and r["to"] in box, f"悬空关系：{r['from']}->{r['to']}")
        a, b = box[r["from"]], box[r["to"]]
        ea, eb = by[r["from"]], by[r["to"]]
        ax, ay, aw, ah = a
        bx, by_, bw_, bh = b
        lab, ca, cb = r.get("label", ""), r.get("card_from", ""), r.get("card_to", "")
        if ea["row"] == eb["row"]:
            # 走两张卡片共同高度的中线，基数写在线上方、贴着两端（离卡片 6px）。
            yy = max((max(ay, by_) + min(ay + ah, by_ + bh)) / 2, max(ay, by_) + 46)
            x1, x2 = (ax + aw, bx) if ax < bx else (ax, bx + bw_)
            pts = [(x1, yy), (x2, yy)]
            sgn = 1 if x2 > x1 else -1
            c.text(x1 + 6 * sgn, yy - 6, ca, 12, INK, 600, width=40, anchor="start" if sgn > 0 else "end")
            c.text(x2 - 6 * sgn, yy - 6, cb, 12, INK, 600, width=40, anchor="end" if sgn > 0 else "start")
            if lab:
                c.text((x1 + x2) / 2, yy + 17, lab, 12, MUTED, width=abs(x2 - x1), anchor="middle")
        elif ea["col"] == eb["col"]:
            xx = ax + aw / 2
            y1, y2 = (ay + ah, by_) if ay < by_ else (ay, by_ + bh)
            pts = [(xx, y1), (xx, y2)]
            sgn = 1 if y2 > y1 else -1
            c.text(xx + 7, y1 + 15 * sgn + (0 if sgn > 0 else 10), ca, 12, INK, 600, width=40)
            c.text(xx + 7, y2 - 6 * sgn + (0 if sgn > 0 else 10), cb, 12, INK, 600, width=40)
            if lab:
                c.text(xx - 8, (y1 + y2) / 2 + 4, lab, 12, MUTED, width=120, anchor="end")
        else:
            # L 形：从 a 朝 b 的侧边水平出发，到 b 顶/底边的偏心端口垂直进入。
            going_right = bx > ax
            x1 = ax + aw if going_right else ax
            yy = ay + 22
            off = -bw_ / 4 if going_right else bw_ / 4
            xe = bx + bw_ / 2 + off
            ye = by_ if by_ > ay else by_ + bh
            check((r["to"], round(xe), ye) not in seen_ports, "两条 L 形关系落在同一端口；调整网格。")
            seen_ports.add((r["to"], round(xe), ye))
            pts = [(x1, yy), (xe, yy), (xe, ye)]
            sgn = 1 if going_right else -1
            c.text(x1 + 5 * sgn, yy - 6, ca, 12, INK, 600, width=40, anchor="start" if sgn > 0 else "end")
            down = ye > yy
            c.text(xe + 7, ye - 8 if down else ye + 18, cb, 12, INK, 600, width=40)
            if lab:
                c.text((x1 + xe) / 2, yy + 17, lab, 12, MUTED, width=abs(xe - x1), anchor="middle")
        hit = _polyline_clears_boxes(pts, full, exclude={f"er-{r['from']}", f"er-{r['to']}"})
        check(hit is None, f"关系 {r['from']}->{r['to']} 穿过实体 {hit}；调整 col/row。")
        d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}" + "".join(f" L{p[0]:.1f} {p[1]:.1f}" for p in pts[1:])
        c.path(d, color=MUTED, width=1.3)
    c.text(32, y - 66 + 40, spec.get("legend", "数字为关系两端的基数：1 恰好一个，0..* 零个或多个"),
           12, MUTED, width=616)
    return c


BUILDERS = {
    "stage_gate": stage_gate,
    "causal_chain": causal_chain,
    "feedback_loop": feedback_loop,
    "state_machine": state_machine,
    "image_annotate": image_annotate,
    "sequence": sequence,
    "er": er,
}
