#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from diagram_kit import Diagram, LayoutError

W = 1240
d = Diagram(W, 900,
            title="已有产物继续验证，四项目标尚未全部达标",
            subtitle="2026-09-28 至 11-27 · 本轮更新 · 上排为现有产物，下排为下一项验收")
d.legend([("line", "实施与验收顺序", "main"), ("card", "仍需完成", "accent")])

M, GAP = 40, 28
xs = d.cols(4, M, W - 2 * M, GAP)
CW = xs[0][1]

top = [
    ("a1", "指标与基线", "10 张正式图可查询；七日参考报告已具备", ["日／周分位", "部门过滤"]),
    ("a2", "架构与裁剪", "三 Profile、插件保护及 98 个声明 Pod 清单", ["总方案", "机制图"]),
    ("a3", "开发与功能", "三实体本轮构建通过；真机业务仍待验收", ["3 份新 App", "待真机连接"]),
    ("a4", "使用与推广", "手册、独立试跑模板和宣讲材料已具备", ["FAQ ≥ 5", "单一入口"]),
]
bot = [
    ("b1", "完整基线与稳定标签", "确认完整 Debug 样本；同 track_id 通过跨日对照", ["10/17 看板确认", "10/24 基线"]),
    ("b2", "组织真实技术评审", "满足角色与人数；问题由提出人确认关闭", ["10/17 评审会", "10/21 正式通过"]),
    ("b3", "业务与 18 项性能判定", "三实体核心链路录屏；五工作日 P75/P90", ["11/10 功能性能", "11/10–27 可用性"]),
    ("b4", "试跑、宣讲与周活", "独立同学 30 分钟构建；实际参会与使用记录", ["11/13 试跑宣讲", "11/21–27 周活"]),
]
y1 = 158
T, B = {}, {}
for (x, w), (cid, t, desc, chips) in zip(xs, top):
    T[cid] = d.card(cid, x, y1, w, t, desc=desc, chips=chips)
maxb = max(c.bottom for c in T.values())
y2 = maxb + 58
for (x, w), (cid, t, desc, chips) in zip(xs, bot):
    B[cid] = d.card(cid, x, y2, w, t, desc=desc, chips=chips, tone="accent")
for a, b in zip("1234", "1234"):
    d.edge(T["a"+a], B["b"+b], a_side="bottom", b_side="top",
           label="下一项验收", style="main", align=T["a"+a].cx)

yn = max(c.bottom for c in B.values()) + 44
nw = (W - 2 * M - GAP) / 2
d.note("n1", M, yn, nw, "性能采样前提",
       "完整基线、业务范围和标签跨日一致性先确认；缺任一条件不判 50% 达标。", tone="orange")
d.note("n2", M + nw + GAP, yn, nw, "实际依赖",
       "评审与业务验收需要真实人员参与；11 月主干、周活和问题响应按实际窗口统计。", tone="accent")
d.H = yn + 130

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("arch.svg")
out = OUT
print(d.save(str(out), drawio=str(out.with_suffix(".drawio"))))
