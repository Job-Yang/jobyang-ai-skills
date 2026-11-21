---
name: "opportunity-radar"
description: "检索带来源证据的产品机会候选。用户要扫描机会、找某领域痛点或收集产品线索（如「帮我扫扫这个方向有没有产品机会」）时调用；只发现取证，不打分、不做 PRD。可独立运行，OPC 内服从既有编排。"
---

# Opportunity Radar · 机会雷达

进入 OPC 流程或需要跨环境信封打包交接时按需读包内 `references/handoff.md`：显式 OPC 上下文优先，否则独立运行。输出位置由调用方传入，不扫描本机固定目录。可用 Python 3.9+ 自检，无 Python 时交付完整文本并标注未执行机器校验。

信封 schema 版本 0.2.0 由包内 `scripts/artifact_io.py` 封装校验。

## 这个 kit 是什么

一个**可移植的机会侦察能力**：支持按用户指定方向做**即时定向扫描**，也支持在无人调度环境里先由 `scripts/collect.py` 从公开结构化源采出原始机会池，再按垂直镜头挖掘**正在变热、还没被大量注意**的产品机会，每条挂真实证据，收敛成候选清单。

> **自包含、不绑定特定 harness。** 只需具备公开网页检索能力，就能在任意 AI 宿主或定时任务中运行。
> **输入**（可空）：兴趣领域 / 技能标签 / 一句方向；留空时按「个人可做的 AI 原生小产品」全域扫描。
> **输出**：带真实证据和信号定档的候选机会清单。下一步由用户或调用方编排决定。

## 立身前提（决定每一步怎么做）

**机会不是想出来的，是取证取出来的。** 侦察兵的天职是带回可靠线索，不是编故事：

> **每条候选挂真实证据（来源链接 + 原话/数据引用）。挖不到证据的臆想标 `evidence: assumption`，不伪装成真需求。**

## 只做 / 禁止

- **只做**：发现问题线索、交叉检索证据、用公开信号判强度、输出结构化候选清单。
- **禁止**：改代码；编造证据；只抄热榜不挖 gap；把无证据臆想写成实证候选；替下游做评分排序（评分归 `opportunity-scorecard`）。

## 执行路径（按触发方式二选一）

先判断当前是**用户点名方向即时扫描**，还是**定时无人巡检**，不把每日后台批处理动作硬塞给交互式单题扫描：

### 路径 A · 指定方向即时扫描（默认交互提问）

1. **跳过每日轮换与追踪台留痕脚本**：直接围绕用户给出的方向检索痛点、付费流向、差评与替代方案；不运行 `rotate.py` 另换方向，也不运行 `dedup.py` 或 `preflight.py` 群发卡片（仅在用户明确要求与既有追踪台对比时才调用去重）。需要宽口径底池作补充时，可选跑一次 `python3 scripts/collect.py --out <工作目录>`。
2. **用可达公共信源取证**：配合 `references/search-queries.md` 做公开网页搜与商店/社区差评挖掘；无浏览器登录态环境默认跳过 `references/sources.md` 标为不可达的源（如 Reddit JSON / X / 即刻 / 小红书 / G2 / Trends 直连），用可读公开源与多源近期同现作代理，不空转重试。
3. **按黄金信号筛与定档**：对照 `references/golden-signals.md` 过滤红海与伪蓝海；团队或非 AI 原生方向按其中的「非 solo / 团队适配」换尺。直接按下方「输出格式」输出候选清单与局限说明（对话直答可省略外围打包，仅落盘或进 OPC 时带信封并走 `artifact_io.py`）。

### 路径 B · 每日定时无人巡检（调度驱动）

**调度归宿主，技能只管「扫什么、怎么判、怎么留痕」。** 详细步骤与排障见 `references/daily-runbook.md`：

0. **采池**：`python3 scripts/collect.py --out <工作目录>`（默认 `5` 天窗口，可用 `--since-days` 调）产出 `pool.json`/`pool.md`；退出码 `4` = 全源为空，按失败留痕记录而非静默结束。
1. **定镜头**：`python3 scripts/rotate.py --date <今天> [--coverage <历史覆盖.json>]` 选出当日垂直与补位方向（`coverage` 应传入历史覆盖统计）。
2. **滤池与补搜**：按当天 keywords 过滤 `pool.json` 归并信号，再用 `references/search-queries.md` 对强候选补搜可达源。
3. **与历史去重**：`python3 scripts/dedup.py --history <追踪台.md|目录> --candidates <今日.json>`（退出码 `4` = 全为 DUP/RELATED 安静日，`0` = 有 NEW）。
4. **证据对抗自检**：`python3 scripts/freshness.py --candidates <今日.json> --dedup <上一步输出>`；硬旗挡候选，软旗仅提示补证（退出码 `4` = 全部命中硬旗）。
5. **留痕分支与卡片**：`python3 scripts/preflight.py check --doc-writable <bool> --group-sendable <bool> --group-error <码>` 决定 `full / degrade-docs / block`，再调 `preflight.py render-card` 渲染留痕卡片 JSON。

池子充足仍判「无强机会」时记录各层筛选计数；连续两个工作日无强机会则扩大至相邻垂直并加码补搜。无论结果如何，无人巡检都应在追踪台留痕。

### 收口输出

交付结构化候选条目和证据局限；候选超 `20` 条且需分包交接时用 `scripts/paginate.py split/merge`。只建议后续评估方向，不自动启动下游流程。

## 输出格式（下游打分 kit 的输入契约）

文件顶部带 front-matter（完整标准在包内 `references/handoff.md`）：
```yaml
---
schema: opc-artifact/v1   # 信封版本，导入方据此判能否处理
opc_node: radar
artifact_kind: radar
opc_version: 0.2.0
topic: null          # 雷达阶段还没定 topic，逐条候选各自起
created: <ISO8601>
upstream: null
produced_by: <mira|iloop|...>   # 哪个环境产的，留痕
human_review: pending
---
```

每条候选一个 block：
```markdown
## 候选：<一句话机会>
- 领域：<健康/效率/女性健康/...>
- 来源：<GitHub / PH / HN / App Store / 社区公开讨论 / 全网搜（不可达源按 sources.md 标注代理或二手）>
- 证据：<链接> — "<原话/数据引用>"
- 信号强度：<强/中/弱> + 理由（按 `references/golden-signals.md` 定档：强=付费流向+差评痛点+需求上升证据[可用 Trends 斜率或多源同期热度代理，代理需注明]三证齐，中=两证，弱=一证）
- evidence: real | assumption
- 建议 topic slug：<如 perimenopause-navigator>（供下游打分沿用）
```

## 何时停手升级用户

- 信息源需要登录态或受限于内网 URL 门禁 → 先经宿主的 URL 放行检查，未放行不浏览。
- 需要付费数据源 → 停并问用户。
- **宿主没有联网检索能力 → 降级为请用户贴链接/原始材料，就着材料做取证与筛选，不硬编造。** 这是保证"哪都能跑"的兜底路径。

## 诚实边界

- 雷达只负责"发现+取证候选"，**不判断值不值得做**（那是打分 kit）、更不做需求/设计/编码。
- 它给的是"有证据的线索"，不是"确定的机会"——去留由打分和人拍板。

## 目录结构

```
opportunity-radar/
├── SKILL.md                    # 本文件：方法论 + 契约
├── CHANGELOG.md                # 版本记录
├── scripts/
│   ├── artifact_io.py          # opc-envelope 0.2.0 公共副本：校验、打包、导入（冻结）
│   ├── scoring-rules.json      # opc-envelope 0.2.0 公共副本（冻结；本节点不读它做评分）
│   ├── vendor-manifest.json    # 本包携带的公共副本清单
│   ├── collect.py              # 0.4.0 新增、0.4.1 加宽：16 源采集（pool.json/pool.md）
│   ├── rotate.py               # 每日镜头轮换（v2：10 垂直 + 2 方法道）
│   ├── dedup.py                # 与历史追踪台去重（NEW/DUP/RELATED，幂等核心）
│   ├── freshness.py             # 证据对抗自检（硬旗/软旗分层，软旗不挡候选）
│   ├── paginate.py             # 候选超量分页分包（manifest + pageNNN，split/merge）
│   ├── preflight.py            # 进场自诊断 + 留痕三分支 + 卡片渲染
│   └── check_handoff.py        # handoff 示例 opc_node drift 检查
├── references/
│   ├── handoff.md              # 包内完整交接协议（radar 节点定制）
│   ├── sources.md              # 十六个结构化采集源、可达性与防垃圾站规则
│   ├── search-queries.md       # 高信号搜索词库
│   ├── golden-signals.md       # 蓝海/红海判据、信号分档、非 solo 适配、蓝海陷阱反例
│   ├── rotation-pool.json      # 方向池（rotate.py 的数据源）
│   └── cards.json              # 留痕卡片模板（无强机会/强机会）
└── tests/                      # 全部回归（python3 -m unittest discover -s tests -v）
    ├── fixtures/               # 三条历史记录 + 今日候选 JSON（2026-10-16 实跑归档）
    ├── test_dedup.py  test_freshness.py  test_paginate.py
    ├── test_rotate.py  test_preflight.py  test_e2e_handoff.py
```

## 在不同环境怎么跑

- **iLoop 流程内**：由 `opc.product-pipeline.radar` 调用，按适配器传入的目录交付；由当前编排决定后续节点。
- **独立或云端 Agent 宿主 → 交接回本地**：把本 kit 目录整体拷过去当 skill 用。**产出时严格照上面的信封格式**（含 `schema/produced_by`）。交接三步：
  1. 远端**自检**：`python3 scripts/artifact_io.py validate --input <你产的.md>`（或 `--stdin`），不合规时先修正。
  2. 把文件/内容拿回本地（复制、粘贴、下载都行）。
  3. 本地**导入**：`python3 scripts/artifact_io.py ingest --input <文件> --output-root <接收目录>`。工具校验信封，写入显式接收目录，不需要 iLoop。
- **命名规则（消除"随便叫 vs 强制改名"的矛盾）**：远端文件名任意，harness 自己存什么名都可以；本地 ingest 会按元数据强制改名为 canonical 名 `radar-<created 日期>.md`（radar 节点 topic 恒为 null，canonical 名只由日期生成）。**同一天扫两批会撞同名**：同日多份请换不同 `--output-root` 分目录存放；同名异内容会被拒绝覆盖，不会悄悄顶掉旧结果。
- 已明确进入 OPC 时，也可通过 `bash "$ILOOP_HELPER" pattern opc.product-pipeline:artifact_io.py -- ingest --input <文件>` 接入流程；这是可选适配器。导入会留待人审，不自动放行。
