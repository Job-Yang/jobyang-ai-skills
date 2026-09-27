---
name: "opportunity-radar"
description: "检索并筛选带来源证据的产品机会。用户要扫描机会、寻找某领域痛点或收集产品线索时调用。可独立运行；已进入 OPC 时服从其输入、审批和编排，不另起流程。"
license: MIT
---

# Opportunity Radar · 机会雷达

先读包内 `references/handoff.md`：显式 OPC 上下文优先，否则独立运行。输出位置由调用方传入，不扫描本机固定目录。版本 0.2.0；可用 Python 3.9+ 自检，无 Python 时交付完整文本并标注未执行机器校验。

## 这个 kit 是什么

一个**可移植的机会侦察能力**：给定一个方向（或空着全域扫），从五个锁定信息源 + 全网搜里，挖出**正在变热、还没被大量注意**的产品机会，每条挂真实证据，收敛成一张候选清单。

> **它是自包含的、不绑定任何 harness。** 只需要"能联网搜"这一项能力（WebSearch/WebFetch 或等价物），就能在 Mira、云端 agent、任意 AI 软件里跑。iLoop 只是它的老家之一。
> **输入**（可空）：兴趣领域 / 技能标签 / 一句方向。空则按"solo 可做的 AI 原生小产品"全域扫。
> **输出**：一张候选机会清单。下一步由用户或调用方编排决定。

## 立身前提（决定每一步怎么做）

**机会不是想出来的，是取证取出来的。** 侦察兵的天职是带回情报，不是编故事。所以铁律：

> **每条候选必须挂真实证据（来源链接 + 原话/数据引用）。挖不到证据的臆想，标 `evidence: assumption`，不许伪装成真需求。**

## 只做 / 禁止

- **只做**：定向扫五源 + 全网搜验证、给每条候选挂真实证据、判信号强度、出结构化清单。
- **禁止**：改任何代码；编造证据；只抄热榜不挖 gap；把无证据的臆想当真候选；自己打分（那是 scorecard kit 的活，防止侦察和评估互相污染）。

## 执行流程

### 第 1 步 · 双管齐下取证 —— 见 `references/sources.md`
复用手头联网能力（WebSearch/WebFetch，**不打包爬虫**）：
- **定向扫五源**：X（思潮）· GitHub Trending/Show HN（技术→商业化）· Product Hunt（分类页 AI 汇总+评论看 gap）· 竞品差评 G2/App Store（1-3 星=最强付费信号）· Google Trends（看斜率不看绝对值）。每源怎么读、怎么防垃圾站抢占，见 references。
- **全网搜验证**：用高信号搜索词挖真实抱怨 —— 见 `references/search-queries.md` 的词库。

### 第 2 步 · 按黄金信号筛 —— 见 `references/golden-signals.md`
- **蓝海判据**（最强 solo 信号）：钱已经在流动（流向医生/补剂/PDF/课程/私教）但**还没流向 app** = 高需求零供给。
- **按范围筛选**：上述蓝海偏好和常见红海是 OPC 一人公司预设，不是所有用户的禁区。用户指定其他领域或研究竞品时遵守其范围，保留差异化证据。
- 重心放"正在慢慢变热、还没被大量注意"，不是已经霸榜的。

### 第 3 步 · 每条候选落成结构化条目
按下面「输出格式」写。一条候选一个 block，证据必须是真链接+真引用。

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
- 信号强度：<强/中/弱> + 理由（斜率？差评量？demand-supply gap？讨论热度？）
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
├── scripts/artifact_io.py      # 独立校验、打包、导入
└── references/
    ├── handoff.md              # 包内完整交接协议
    ├── sources.md              # 五源怎么读、怎么防垃圾站
    ├── search-queries.md       # 高信号搜索词库
    └── golden-signals.md       # 蓝海/红海判据
```

## 在不同环境怎么跑

- **iLoop 流程内**：由 `opc.product-pipeline.radar` 调用，按适配器传入的目录交付；由当前编排决定后续节点。
- **独立/别的 harness（如 Mira）→ 交接回本地**：把本 kit 目录整体拷过去当 skill 用。**产出时严格照上面的信封格式**（含 `schema/produced_by`），文件名随便叫。交接三步：
  1. 远端**自检**：`python3 scripts/artifact_io.py validate --input <你产的.md>`（或 `--stdin`），不合规时先修正。
  2. 把文件/内容拿回本地（复制、粘贴、下载都行）。
  3. 本地**导入**：`python3 scripts/artifact_io.py ingest --input <文件> --output-root <接收目录>`。工具校验信封，按元数据生成标准文件名，写入显式接收目录，不需要 iLoop。
- 已明确进入 OPC 时，也可通过 `bash "$ILOOP_HELPER" pattern opc.product-pipeline:artifact_io.py -- ingest --input <文件>` 接入流程；这是可选适配器。
- 同日期的不同扫描使用不同 topic 或不同输出目录；同名异内容不会覆盖旧结果。导入会留待人审，不自动放行。
