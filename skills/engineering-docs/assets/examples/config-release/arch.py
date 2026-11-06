#!/usr/bin/env python3
"""Example: a left-to-right pipeline with a feedback loop (config release platform).

Columns follow the path of one change: entry, orchestration (new in this release,
the only accent), storage and push, clusters. Metrics come back along the bottom
and trigger rollback, drawn in the risk colour because it is the failure path.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from diagram_kit import Diagram  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("arch.svg")
W, M = 1200, 40
ROW_GAP, CARD_GAP, ZONE_TOP, ZONE_PAD = 36, 32, 46, 16

d = Diagram(W, 900, title="配置变更先灰度再全量，指标异常时自动回滚",
            subtitle="配置发布平台目标架构（示例）",
            summary="变更从入口进入发布编排，校验后存为不可变版本，按四个批次推送到集群；集群指标回到观测，异常时回滚控制切回上一版本。")
d.legend([("zone", "本次新增", "accent", True), ("line", "调用 / 下发", "main"),
          ("line", "指标上报", "dash"), ("line", "异常回滚", "alert")], x=M, y=112)

# Four lanes, left to right, in the order a change travels; gaps leave room for edge labels.
widths, gaps = [160, 250, 220, 240], [56, 100, 70]
xs = [M]
for w, g in zip(widths, gaps):
    xs.append(xs[-1] + w + g)
assert xs[-1] + widths[-1] <= W - M
y0 = 160
cy = y0 + ZONE_TOP
lanes = [
    [("console", "控制台", "人工提交与审批"), ("openapi", "OpenAPI", "CI 流水线调用")],
    [("validate", "校验", "Schema、权限与冲突检查"), ("plan", "灰度计划", "内部 → 1% → 10% → 全量"),
     ("rollback", "回滚控制", "一键切回上一版本")],
    [("store", "版本库", "每次变更一个不可变版本"), ("push", "推送通道", "长连接推送，断连时客户端用旧值")],
    [("c1", "内部集群", "第 1 批"), ("c2", "灰度集群", "第 2、3 批：1% 与 10%"), ("c3", "全量集群", "第 4 批")],
]
card_h = max(d.measure_card(w - 2 * ZONE_PAD, t, s) for w, lane in zip(widths, lanes) for _, t, s in lane)
N = {}
for x, w, lane in zip(xs, widths, lanes):
    for i, (cid, t, s) in enumerate(lane):
        kw = {}
        if cid in ("c1", "c2", "c3"):
            kw["badge"] = cid[1]
        if cid == "rollback":
            kw.update(tone="accent", emphasis=True)
        N[cid] = d.card(cid, x + ZONE_PAD, cy + i * (card_h + CARD_GAP), w - 2 * ZONE_PAD, t, desc=s, h=card_h, **kw)
zone_h = ZONE_TOP + 3 * card_h + 2 * CARD_GAP + ZONE_PAD
labels = ["变更入口", "发布编排 · 本次新增", "存储与下发", "业务集群 · 按批次生效"]
Z = [d.zone(f"z{i}", x, y0, w, zone_h, lab, tone="accent" if i == 1 else "neutral", dashed=i == 1)
     for i, (x, w, lab) in enumerate(zip(xs, widths, labels))]

d.edge(N["console"], N["validate"], label="提交", style="main")
d.edge(N["openapi"], N["validate"], b_t=0.75, style="main")
d.edge(N["validate"], N["store"], label="存为新版本", style="main")
d.edge(N["validate"], N["plan"], "bottom", "top", style="main")
d.edge(N["plan"], N["push"], label="按批次下发", style="main")
d.edge(N["store"], N["push"], "bottom", "top", style="main")
for cid in ("c1", "c2", "c3"):
    d.edge((N["push"].right, N["push"].cy), N[cid], "right", "left", style="main")

# Metrics come back along the bottom and close the loop through rollback control.
y = Z[0].bottom + ROW_GAP + 20
obs_x = xs[1]
obs = d.bar("obs", obs_x, y, W - M - obs_x, "观测", ["错误率", "延迟 P99", "配置生效率"], h=48)
d.edge(Z[3], obs, "bottom", "top", align=Z[3].cx, label="上报指标", style="dash")
d.edge(obs, N["rollback"], "top", "bottom", align=N["rollback"].cx, label="超过阈值", style="alert")
d.edge(N["rollback"], N["push"], "right", "bottom", label="切回上一版本", style="alert")

y = obs.bottom + ROW_GAP
n1, n2, n3 = d.cols(3, M, W - 2 * M)
notes = [d.note("t1", n1[0], y, n1[1], "版本不可变", "回滚就是切回旧版本，不重新生成配置", tone="neutral"),
         d.note("t2", n2[0], y, n2[1], "逐批放量", "每批观察 10 分钟，指标正常才进下一批", tone="neutral"),
         d.note("t3", n3[0], y, n3[1], "本次只加编排层", "入口、版本库和推送通道不改接口", tone="accent")]
d.H = max(n.bottom for n in notes) + M

report = d.save(str(OUT), drawio=str(OUT.with_suffix(".drawio")), strict=False)
print(report)
