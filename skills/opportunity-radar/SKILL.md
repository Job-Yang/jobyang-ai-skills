---
name: "opportunity-radar"
description: "检索带来源证据的产品机会候选。用户要扫描机会、找某领域痛点或收集产品线索（如「帮我扫扫这个方向有没有产品机会」）时调用；只发现取证，不打分、不做 PRD。可独立运行，OPC 内服从既有编排。"
---

# Opportunity Radar · 机会雷达

先读包内 `references/handoff.md`：显式 OPC 上下文优先，否则独立运行。输出位置由调用方传入，不扫描本机固定目录。可用 Python 3.9+ 自检，无 Python 时交付完整文本并标注未执行机器校验。

版本口径（2026-10-20 起）：信封 schema 版本 0.2.0，由冻结的 `scripts/artifact_io.py` seal 出，代表信封结构；本 kit（技能包）版本 0.4.1，见 CHANGELOG.md。两者不是一回事。

## 这个 kit 是什么

一个**可移植的机会侦察能力**：每天先由 `scripts/collect.py` 从十六个公开结构化源宽口径采出一张原始机会池（0.4.1 起默认 5 天窗口，实测 480 条以上），再按当天的垂直镜头从中挖**正在变热、还没被大量注意**的产品机会，每条挂真实证据，收敛成一张候选清单。

> **它是自包含的、不绑定任何 harness。** 只需要"能联网搜"这一项能力（WebSearch/WebFetch 或等价物），就能在 Mira、云端 agent、任意 AI 软件里跑。iLoop 只是它的老家之一。
> **输入**（可空）：兴趣领域 / 技能标签 / 一句方向。空则按"solo 可做的 AI 原生小产品"全域扫。
> **输出**：一张候选机会清单。下一步由用户或调用方编排决定。

## 立身前提（决定每一步怎么做）

**机会不是想出来的，是取证取出来的。** 侦察兵的天职是带回情报，不是编故事。所以铁律：

> **每条候选必须挂真实证据（来源链接 + 原话/数据引用）。挖不到证据的臆想，标 `evidence: assumption`，不许伪装成真需求。**

## 只做 / 禁止

- **只做**：定向扫五源 + 全网搜验证、给每条候选挂真实证据、判信号强度、出结构化清单。
- **禁止**：改任何代码；编造证据；只抄热榜不挖 gap；把无证据的臆想当真候选；自己打分（那是 scorecard kit 的活，防止侦察和评估互相污染）。

## 每日运行契约（与 cron / 云电脑的边界）

**调度归宿主，技能只管"扫什么、怎么判、怎么留痕"。** 每日定时由宿主 cron/云电脑拉起本技能；技能不内置 token、不自建 app、不负责定时。一天的固定动作：

0. **采池（0.4.0 新增，入口动作）**：`python3 scripts/collect.py --out <工作目录>`（默认 5 天窗口，可用 --since-days 调） → 多源并发采集，产出 `pool.json`/`pool.md`，并逐源记状态。退出码 4 = 所有源都空，按"失败留痕"处理而不是静默结束。
1. **定镜头**：`python3 scripts/rotate.py --date <今天> [--coverage <历史覆盖.json>]` → 从 v2 池（10 个垂直人群镜头 + 2 个方法道）选今天的 anchor 垂直和补位方向，附 lens/keywords/queries。coverage 由追踪台历史整理，必须传，否则缺扫记录时补位会反复选同一方向。
2. **取证**：先按当天镜头的 keywords 在 pool.json/pool.md 里过滤和归并相关信号；再对最强的 5～8 条用 `references/search-queries.md` 的词做补充网页搜和差评挖（评论原话、付费证据、竞品）。信源可达性见 `references/sources.md`，不可达源（云电脑上的 Reddit JSON/X/即刻/小红书/G2/Trends）不要硬搜。
3. **与历史去重**：把追踪台历史 markdown 拉下来 + 今日候选 JSON，跑 `python3 scripts/dedup.py --history <追踪台.md|目录> --candidates <今日.json>`。每条判 NEW/DUP/RELATED；退出码 4 = 全是 DUP/RELATED（安静日），0 = 有 NEW。跨条目通用词由 df 折扣自动剔除。
4. **证据对抗自检**：`python3 scripts/freshness.py --candidates <今日.json> --dedup <上一步输出>`。**硬旗**（旧证据、未来日期、垃圾源、坏链接、DUP）挡候选；**软旗**（缺日期、付费未验证、RELATED）只提醒补证，不挡新供给。退出码 4 只在全部被硬旗挡住时返回。
5. **进场自诊断 + 留痕分支**：`python3 scripts/preflight.py check --doc-writable <宿主探测> --group-sendable <宿主探测> --group-error <码>`。文档可写+群可发=full（文档留痕+群卡片）；群不可发（如 230002）=degrade-docs（**只文档留痕+回报 blocker，不发群卡片**）；文档不可写=block。这是确定性分支，不临场发挥。
6. **渲染留痕卡片**：`python3 scripts/preflight.py render-card --template no_opportunity|strong_opportunity --data '<json>'` → 产出可直接喂宿主 im 的卡片 JSON。

**召回节奏要求（0.4.1，宽进严出）**：召回端尽量宽——默认 5 天窗口、十六个源、最新流和热门流都采；筛选端严格。目标是每 1～2 个工作日产出一条值得深挖的机会。池子有 480 条左右还判"无强机会"时，必须在条目里写明漏斗各层的数量（采池数、镜头命中数、去重后数、硬旗后数），证明是筛掉的而不是没采到。连续两个工作日无强机会时，下一次自动放宽：镜头扩到相邻垂直、补充网页搜加码，并在条目里标注"连续静默日扩源"。

**无论成功、无机会、失败，追踪台都必须留一条**。

## 执行流程

### 第 1 步 · 先采池，再按镜头取证 —— 见 `references/sources.md`
- **每天先跑 `scripts/collect.py`**：PH/hunted、GitHub Trending 与新高星、Show HN/Ask HN/HN 评论许愿、HF Spaces、DEV、V2EX、Lobsters、Reddit RSS、App Store 畅销榜一次采全，逐源容错。具体源和云电脑不可达清单见 references。
- **当天镜头过滤**：用 rotate.py 给的 keywords 在池子里筛相关信号，按"同一痛点"归并，再人工读最强的十六条。
- **补充网页搜**：对最强候选用 `references/search-queries.md` 的高信号词补差评和付费原话。通用搜只是补充，不再是唯一入口（0.3.x 每天只靠它捞 4 条，召回率必然低）。
- 今天扫哪个垂直由 `scripts/rotate.py` 确定性选出，不凭感觉挑。

### 第 2 步 · 按黄金信号筛 —— 见 `references/golden-signals.md`
- **蓝海判据**（最强 solo 信号）：钱已经在流动（流向医生/补剂/PDF/课程/私教）但**还没流向 app** = 高需求零供给。
- **按范围筛选**：上述蓝海偏好和常见红海是 OPC 一人公司预设，不是所有用户的禁区。用户是团队、或明确不是 AI 原生产品时，按 `references/golden-signals.md` 的"非 solo / 团队用户怎么用这把尺"换判据。用户指定其他领域或研究竞品时遵守其范围，保留差异化证据。
- 重心放"正在慢慢变热、还没被大量注意"，不是已经霸榜的。
- 筛完先过 `scripts/dedup.py`（与历史去重）和 `scripts/freshness.py`（硬旗挡旧愿/垃圾源/DUP；软旗只提醒补付费证据、注明近亲）。

### 第 3 步 · 每条候选落成结构化条目
按下面「输出格式」写。一条候选一个 block，证据必须是真链接+真引用。候选超量（>20 条）时用 `scripts/paginate.py split` 分页分包（manifest + pageNNN），`merge` 还原；每页自身过冻结信封校验。

### 第 4 步 · 收口
交付清单和证据局限。可以建议后续评估，不能自动启动另一个流程。

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
- 来源：<X / GitHub / PH / 差评 / Trends / 全网搜>
- 证据：<链接> — "<原话/数据引用>"
- 信号强度：<强/中/弱> + 理由（按 `references/golden-signals.md` 的映射表定档：强=付费流向+差评量+Trends 斜率三证齐，中=两证，弱=一证）
- evidence: real | assumption
- 建议 topic slug：<如 perimenopause-navigator>（供下游打分沿用）
```

## 何时停手升级用户

- 信息源需要登录态 / 疑似公司内部 URL → 先过环境的 URL 放行 gate（iLoop 里是 `url_capability_gate`），未放行不浏览。
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
│   ├── check_vendored.py        # 公共副本一致性自检
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
│   ├── sources.md              # 五源怎么读、怎么防垃圾站
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
- **独立/别的 harness（如 Mira）→ 交接回本地**：把本 kit 目录整体拷过去当 skill 用。**产出时严格照上面的信封格式**（含 `schema/produced_by`）。交接三步：
  1. 远端**自检**：`python3 scripts/artifact_io.py validate --input <你产的.md>`（或 `--stdin`），不合规时先修正。
  2. 把文件/内容拿回本地（复制、粘贴、下载都行）。
  3. 本地**导入**：`python3 scripts/artifact_io.py ingest --input <文件> --output-root <接收目录>`。工具校验信封，写入显式接收目录，不需要 iLoop。
- **命名规则（消除"随便叫 vs 强制改名"的矛盾）**：远端文件名任意，harness 自己存什么名都可以；本地 ingest 会按元数据强制改名为 canonical 名 `radar-<created 日期>.md`（radar 节点 topic 恒为 null，canonical 名只由日期生成）。**同一天扫两批会撞同名**：同日多份请换不同 `--output-root` 分目录存放；同名异内容会被拒绝覆盖，不会悄悄顶掉旧结果。
- 已明确进入 OPC 时，也可通过 `bash "$ILOOP_HELPER" pattern opc.product-pipeline:artifact_io.py -- ingest --input <文件>` 接入流程；这是可选适配器。导入会留待人审，不自动放行。

## 维护说明

本包自带 opc-envelope 0.2.0 公共文件副本（`scripts/artifact_io.py`、`scripts/scoring-rules.json`，见 `scripts/vendor-manifest.json`），本轮冻结不改内容。发布前跑：
- `python3 scripts/check_vendored.py` 自检冻结副本 sha；
- `python3 -m unittest discover -s tests -v` 跑全部回归（含 dedup/freshness 对 2026-10-16 实跑的复现）；
- `python3 scripts/check_handoff.py <本包> <scorecard包> <brief包>` 确认三包 handoff 示例 opc_node 无 drift；
- 与其他流水线包并排时跑 `python3 scripts/check_vendored.py --drift <各技能根>` 确认无漂移。
