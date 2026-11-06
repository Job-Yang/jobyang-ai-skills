#!/usr/bin/env python3
"""Golden example: redraw of the Personal Harness 0.4.0 / 0.5.0 architecture overview.

Main components and relations of the original stacked diagram, reorganised by message: host on top,
portable core in the middle, replaceable periphery on the right, and the 0.5.0
governance as the only accent colour because it is what this release adds.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from diagram_kit import Diagram  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("arch.svg")
W, M = 1200, 40
ROW_GAP, CARD_GAP, ZONE_TOP, ZONE_PAD = 36, 14, 46, 18

d = Diagram(W, 1230, title="稳定核心随仓库迁移，模型、工具与公司能力从外围插拔",
            subtitle="Personal Harness 0.4.0 架构总览，含 0.5.0 规划",
            summary="宿主 DSH Runtime 在上，可迁移核心居中，可替换外围在右；0.5.0 在社区插件与事件接缝之间加一层组合治理。")
d.legend([("zone", "0.5.0 规划", "accent", True),
          ("line", "调用 / 加载", "main"), ("line", "规划中的挂载", "planned"), ("line", "验证与回滚反馈", "dash")],
         x=M, y=112)

# Row 1: user and host runtime
y = 158
rt_x = 270
cols = d.cols(4, rt_x + 20, W - M - rt_x - 40)
rt_items = [("Agent Loop", "界面与回合循环"), ("Session / Trace", "会话与轨迹记录"),
            ("Sandbox", "沙箱执行与审批"), ("Plugin Lifecycle", "Cordis 插件加载")]
rt_h = max(d.measure_card(w, t, s) for (x, w), (t, s) in zip(cols, rt_items))
rt_cards = [d.card(f"rt{i}", x, y + ZONE_TOP, w, t, desc=s, h=rt_h)
            for i, ((x, w), (t, s)) in enumerate(zip(cols, rt_items))]
seams = d.bar("seams", rt_x + 20, rt_cards[0].bottom + CARD_GAP, W - M - rt_x - 40, "事件接缝 ×12",
              ["组装提示", "每步请求", "模型流", "工具前后", "审批", "回合结束"], tone="accent", h=50)
rt = d.zone("runtime", rt_x, y, W - M - rt_x, seams.bottom + ZONE_PAD - y,
            "DSH Runtime · 通用 Agent 宿主，不承载个人方法和公司账号")
user = d.card("user", M, rt_cards[0].y, 170, "用户与团队", desc="发起、审批、验收", h=rt_h)
d.edge(user, rt_cards[0], label="使用", style="main")

# Row 2: 0.5.0 governance gate between community plugins and the seams
y = rt.bottom + ROW_GAP
plug = d.card("plugins", 470, y, 300, "社区插件候选", desc="按接缝登记，分四类", dashed=True, tone="accent",
              chips=["上下文与成本", "验证与评审", "安全与回滚", "记忆与经验"])
gov = d.card("gov", 820, y, W - M - 820, "组合治理", desc="插件先过准入，再按接缝所有权挂载", tone="accent",
             emphasis=True, dashed=True,
             chips=[("接缝所有权清单", "filled", "accent"), ("准入流水线", "filled", "accent"),
                    ("Profile 分层", "outline", "accent"), ("本机度量", "outline", "accent")])
d.edge(plug, gov, label="准入", style="planned")
d.edge(gov, seams, "top", "bottom", align=gov.cx, label="按所有权挂载", style="planned")

# Row 3: portable core (left, 2 x 3 grid) and replaceable periphery (right)
y = max(plug.bottom, gov.bottom) + ROW_GAP
core_x, core_w = M, 760
per_x = core_x + core_w + 40
per_w = W - M - per_x
cy = y + ZONE_TOP
core_items = [("wb", "Personal Workbench", "组合 Prompt、目标、计划、会话与工具"),
              ("iloop", "iLoop + VDD", "证据闭环、任务恢复、独立验收"),
              ("opc", "OPC + Personal Skills", "需求、设计、文档、调研与表达"),
              ("ws", "工作区与交付", "Sidebar、Worktree、Market"),
              ("ci", "代码智能", "LSP、Graph、Subagent"),
              ("auto", "自动化与创作", "Computer Use、Blender")]
per_items = [("prov", "Provider Adapter", "公共、本地、公司模型；失败切换"),
             ("mcp", "MCP Packs", "Browser、Apple，后续接工具链"),
             ("comp", "Company Overlay", "SSO、内部代理、飞书审批")]
g1, g2 = d.cols(2, core_x + 18, core_w - 36)
card_h = max([d.measure_card(g1[1], t, s) for _, t, s in core_items] +
             [d.measure_card(per_w - 36, t, s) for _, t, s in per_items])
for i, (cid, t, s) in enumerate(core_items):
    x, w = (g1, g2)[i % 2]
    d.card(cid, x, cy + (i // 2) * (card_h + CARD_GAP), w, t, desc=s, h=card_h)
per_cards = [d.card(cid, per_x + 18, cy + i * (card_h + CARD_GAP), per_w - 36, t, desc=s, h=card_h)
             for i, (cid, t, s) in enumerate(per_items)]
zone_h = ZONE_TOP + 3 * card_h + 2 * CARD_GAP + ZONE_PAD
core = d.zone("core", core_x, y, core_w, zone_h, "Personal Harness 可迁移核心 · 仓库存定义，本机存状态")
d.zone("periphery", per_x, y, per_w, zone_h, "外围适配 · 换环境只换这一层")

d.edge(seams, core, "bottom", "top", align=360, label="按 profile 加载", style="main")
for n in per_cards:
    d.edge((core.right, n.cy), n, "right", "left", style="main")

# Row 4: installer with the feedback loop into the core
y = core.bottom + ROW_GAP
inst = d.bar("inst", M, y, W - 2 * M, "Installer", ["版本锁定", "所有权记录", "回滚", "Doctor", "本机状态"], h=48)
d.edge(inst, core, "top", "bottom", align=core.cx, label="验证与回滚反馈", style="dash")

# Row 5: takeaways
y = inst.bottom + ROW_GAP
n1, n2, n3 = d.cols(3, M, W - 2 * M)
notes = [d.note("t1", n1[0], y, n1[1], "核心随仓库迁移", "方法与工作台在仓库定义，本机只存状态", tone="neutral"),
         d.note("t2", n2[0], y, n2[1], "外围按环境替换", "换环境只换三个适配器，凭证不进迁移包", tone="neutral"),
         d.note("t3", n3[0], y, n3[1], "0.5.0 只加治理", "插件先过准入再按接缝挂载，核心不改", tone="accent")]
d.H = max(n.bottom for n in notes) + M

report = d.save(str(OUT), drawio=str(OUT.with_suffix(".drawio")), strict=False)
print(report)
