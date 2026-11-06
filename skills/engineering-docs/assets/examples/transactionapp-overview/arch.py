#!/usr/bin/env python3
"""Three-stage software delivery overview generated with diagram_kit.

The diagram keeps configuration, dependency checks, build, test, observation,
and analysis in one reproducible and portable flow.

Run: python3 arch.py
Emits arch.svg and arch.drawio, then prints the checker summary.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from diagram_kit import Diagram

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("arch.svg")

W, H = 1240, 1092
d = Diagram(
    W,
    H,
    title="配置驱动组件装配，测试与观测形成反馈闭环",
    subtitle="通用软件构建总览 · 配置选择组件 → 依赖检查 → 构建 → 测试 → 本地观测 → 聚合分析",
)

d.legend(
    [
        ("card", "输入与产物", "neutral"),
        ("card", "关键步骤", "accent"),
        ("card", "检查与反馈", "orange"),
    ]
)

M, PAD, CW, GAP = 40, 46, 326, 42
X0, X1, X2 = M + PAD, M + PAD + CW + GAP, M + PAD + 2 * (CW + GAP)

# Phase 1: configuration and build.
p1y, p1h = 128, 428
d.zone("phase_build", M, p1y, W - 2 * M, p1h, "")
d.phase_banner(
    "banner_build",
    X0,
    p1y + 12,
    W - M - X0 - 14,
    "01",
    "配置与构建",
    "选择组件、校验依赖并生成可运行产物",
)
y_a = p1y + 62
source = d.card(
    "config_source",
    X0,
    y_a,
    CW,
    "配置入口",
    desc="组件清单、依赖声明、构建参数与资源规则",
)
selection = d.card(
    "component_selection",
    X1,
    y_a,
    CW,
    "配置选择组件",
    desc="按目标环境与功能集合选择需要装配的组件",
    tone="accent",
    emphasis=True,
)
plan = d.card(
    "build_plan",
    X2,
    y_a,
    CW,
    "生成构建计划",
    desc="把组件选择映射为编译单元、资源集合与执行顺序",
)
y_b = y_a + 130 + 52
dependency = d.card(
    "dependency_check",
    X2,
    y_b,
    CW,
    "依赖检查",
    desc="检查缺失依赖、循环依赖与不兼容组合；失败即停止",
    tone="orange",
)
build = d.card(
    "build_execution",
    X1,
    y_b,
    CW,
    "执行构建",
    desc="按计划完成编译、链接与资源处理，并保留诊断日志",
    tone="accent",
    emphasis=True,
)
artifact = d.card(
    "build_artifact",
    X0,
    y_b,
    CW,
    "构建产物",
    desc="输出可运行包与构建清单；保留共享运行时和基础资源",
    chips=[
        ("运行时", "soft", "neutral"),
        ("共享接口", "soft", "neutral"),
        ("基础资源", "soft", "neutral"),
    ],
)
d.edge(source, selection, label="读取配置", style="normal")
d.edge(selection, plan, label="生成选择集", style="main")
d.edge(plan, dependency, a_side="bottom", b_side="top", label="提交检查", style="main")
d.edge(dependency, build, label="检查通过", style="main")
d.edge(build, artifact, label="输出", style="main")

# Phase 2: testing and diagnosis.
p2y, p2h = 572, 184
d.zone("phase_test", M, p2y, W - 2 * M, p2h, "")
d.phase_banner(
    "banner_test",
    X0,
    p2y + 12,
    W - M - X0 - 14,
    "02",
    "自动化测试",
    "验证组件组合与关键运行路径",
)
y2 = p2y + 62
test = d.card(
    "test_execution",
    X0,
    y2,
    CW,
    "测试执行",
    desc="运行单元测试、集成测试与关键路径检查",
    tone="accent",
    emphasis=True,
)
result = d.card(
    "test_result",
    X1,
    y2,
    CW,
    "结果汇总",
    desc="记录通过项、失败项、覆盖场景与可复核产物",
)
diagnosis = d.card(
    "failure_diagnosis",
    X2,
    y2,
    CW,
    "失败诊断",
    desc="关联配置、依赖与构建日志，形成下一轮修正输入",
    tone="orange",
)
gutter_x = M + 22
d.edge(
    artifact,
    test,
    a_side="left",
    b_side="left",
    b_t=0.62,
    via=[(gutter_x, artifact.cy), (gutter_x, test.y + test.h * 0.62)],
    label="进入测试",
    style="main",
)
d.edge(test, result, label="记录", style="main")
d.edge(result, diagnosis, label="定位失败", style="normal")

# Phase 3: local observation and aggregated analysis.
p3y, p3h = 772, 304
d.zone("phase_observation", M, p3y, W - 2 * M, p3h, "")
d.phase_banner(
    "banner_observation",
    X0,
    p3y + 12,
    W - M - X0 - 14,
    "03",
    "本地观测与聚合分析",
    "收集运行信号，汇总趋势并回馈配置",
)
y3 = p3y + 62
observation = d.card(
    "local_observation",
    X0,
    y3,
    CW,
    "本地观测",
    desc="采集构建日志、测试结果、运行日志与性能信号",
    tone="accent",
    emphasis=True,
)
normalization = d.card(
    "signal_normalization",
    X1,
    y3,
    CW,
    "信号整理",
    desc="统一事件结构，关联配置、构建和测试批次",
)
analysis = d.card(
    "aggregate_analysis",
    X2,
    y3,
    CW,
    "聚合分析",
    desc="按组件与阶段汇总趋势、异常和回归线索",
)
d.edge(
    test,
    observation,
    a_side="left",
    b_side="left",
    a_t=0.38,
    via=[(gutter_x, test.y + test.h * 0.38), (gutter_x, observation.cy)],
    label="观测运行",
    style="normal",
)
d.edge(observation, normalization, label="归一化", style="normal")
d.edge(normalization, analysis, label="汇总", style="main")

note_y = y3 + 132
d.note(
    "feedback_note",
    X0,
    note_y,
    CW,
    "异常反馈",
    "把失败信号关联到配置或依赖检查，保留原始证据后再调整。",
    tone="orange",
)
d.note(
    "iteration_note",
    X2,
    note_y,
    CW,
    "迭代闭环",
    "分析结果回到组件选择与测试范围，下一轮沿同一口径复核。",
    tone="accent",
)

print(d.save(str(OUT), drawio=str(OUT.with_suffix(".drawio"))))
