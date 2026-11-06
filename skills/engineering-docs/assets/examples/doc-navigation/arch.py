#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from diagram_kit import Diagram

W = 1240
d = Diagram(
    W,
    700,
    title="从文档总览看全貌，再按问题进入专项文档",
    subtitle="评审先看架构与边界；实施看指南；验收看标准和证据记录",
)
d.legend([("line", "阅读路径", "main"), ("line", "查看验收依据", "normal")])

M, GAP = 40, 86
xs = d.cols(3, M, W - 2 * M, GAP)

rows = [
    [
        ("overview", "文档总览", "范围、当前状态、里程碑、依赖和产物入口", "accent", True),
        ("plan", "总体技术方案", "架构、依赖、构建、测试与观测；方案权衡与代价", "neutral", False),
        ("architecture", "架构与模块边界", "组件职责、依赖关系、运行边界与回退路径", "neutral", False),
    ],
    [
        ("criteria", "验收标准", "样本来源、观测口径、基线与通过条件", "neutral", False),
        ("review", "评审与问题跟踪", "参与角色、待办事项、责任方、交付物与结论", "neutral", False),
        ("change", "变更记录", "代码差异、验证证据与自动化检查状态", "neutral", False),
    ],
    [
        ("guide", "使用指南", "统一入口、环境自检、运行方式、切换与恢复", "neutral", False),
        ("validation", "独立验证", "按步骤完成构建与测试；保留产物、日志与恢复说明", "neutral", False),
        ("collaboration", "协作说明", "设计说明、操作演示、常见问题与反馈记录", "neutral", False),
    ],
]
y = 150
VGAP = 48
placed = {}
for row in rows:
    for (x, width), (cid, title, desc, tone, emph) in zip(xs, row):
        placed[cid] = d.card(cid, x, y, width, title, desc=desc, tone=tone, emphasis=emph)
    y = max(card.bottom for card in placed.values()) + VGAP

# Horizontal reading flow.
d.edge(placed["overview"], placed["plan"], label="看主线", style="main")
d.edge(placed["plan"], placed["architecture"], label="查边界", style="main")
d.edge(placed["criteria"], placed["review"], label="确认口径", style="normal")
d.edge(placed["review"], placed["change"], label="核实变更", style="normal")
d.edge(placed["guide"], placed["validation"], label="独立使用", style="normal")
d.edge(placed["validation"], placed["collaboration"], label="共享经验", style="normal")
d.edge(
    placed["overview"],
    placed["criteria"],
    a_side="bottom",
    b_side="top",
    label="查看验收依据",
    style="normal",
    align=placed["overview"].cx,
)

d.note(
    "reading_note",
    M,
    y + 2,
    W - 2 * M,
    "读图约定",
    "图负责定位，细节进入对应专项文档；总览不重复参数和完整测试表。文档存在不代表实现或验收完成，状态以总览和证据记录为准。",
)
d.H = y + 128

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("arch.svg")
print(d.save(str(OUT), drawio=str(OUT.with_suffix(".drawio"))))
