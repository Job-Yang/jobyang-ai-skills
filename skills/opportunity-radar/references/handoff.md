# 独立调用与 OPC 交接（opportunity-radar 节点）

本规范和 `scripts/artifact_io.py` 随技能整包交付，Python 3.9+，只用标准库。所有相对路径都相对当前技能目录；不要求访问原机器或安装 iLoop。

## 版本口径

- 信封 `opc_version: 0.2.0` = opc-envelope 的 **schema 版本**，由冻结的 `artifact_io.py` seal 出，代表信封结构，基本不动。
- 本 kit（流水线技能包）本轮版本为 **0.3.0（2026-10-16）**，见 CHANGELOG.md，不写进信封。两者不要混为一谈。

## 谁控制流程

- 用户明确要求 OPC 或已有 OPC flow 正在执行：OPC 适配器控制输入、输出目录、人审和后续编排。独立技能只执行当前能力，不重新开启问诊或另起流程。用户已确认的需求直接复用。
- 用户直接调用单点能力：独立模式。输入是用户给的文本、附件或显式路径；输出由宿主附件区或用户指定位置承载。不能因为发现 iLoop 环境变量或旧 PRD 就自动切 OPC。
- 同一任务同时命中两种入口时，明确的 OPC 调用上下文优先于技能默认行为；用户最新明确指令优先。不修改宿主全局入口来实现优先级。
- 本节点只产候选清单，声明输入输出，不强制下一节点。缺少材料时可接受直接描述，不强迫用户补跑整条流水线。

## Markdown 信封（本节点实例）

```yaml
---
schema: opc-artifact/v1
opc_node: radar
artifact_kind: radar
opc_version: 0.2.0
topic: null
created: 2026-10-16T10:00:00+00:00
upstream: null
produced_by: standalone
human_review: pending
---
```

radar 节点 `topic` 恒为 null：候选清单还没定单一 topic，每条候选在正文里给自己的 slug（供下游 scorecard 沿用）。`created` 为带时区的真实生成时间。正文中证据的真实性仍需领域验证，validate 只证明结构合规。

正文最低结构：至少一个 `## 候选：<一句话机会>` 条目；每条候选必须写 `evidence: real | assumption`；`evidence: real` 的候选必须挂真实 URL。

## 输出与搬运

有文件能力时交付可下载的 Markdown；无文件能力时，在一个完整的 Markdown 代码块内输出信封和正文，不混入说明、不省略。本地 Agent 接收该块后用 `--stdin` 校验。

```bash
python3 scripts/artifact_io.py validate --input radar-2026-10-16.md
python3 scripts/artifact_io.py pack --input radar-2026-10-16.md --out result.zip
python3 scripts/artifact_io.py ingest --input result.zip --output-root /explicit/artifacts --dry-run
python3 scripts/artifact_io.py ingest --input result.zip --output-root /explicit/artifacts
```

命令由 Agent 执行，用户只需把附件交给本地 Agent。OPC 里通过 `pattern opc.product-pipeline:artifact_io.py -- ingest --input <file>` 接收；适配器负责提供 ILOOP_DATA_ROOT。独立使用始终显式给 --output-root。

**命名规则**：远端（别的 harness 产文件时）文件名任意；本地 `ingest` 会按元数据强制改名 `radar-<created 日期>.md`，写到显式接收目录。radar 产物 `topic=null`，canonical 名由 created 日期生成：同一天扫两批会撞同名。同日多份的区分办法是换输出目录，或在交接时说明批次（同名异内容会被拒绝覆盖，不会悄悄顶掉旧结果）。

## 导入、校验与审批

导入先校验全部文件和冲突，再落地。原始包保存在 `_handoffs/<摘要>/source.zip`，收据记录缺失上游。新导入正文一律 `human_review: pending`；远端的 approved 仅是原始材料的一部分，不自动授权本地开工。已有同内容的本地审批会保留；同名异内容拒绝覆盖，需要明确新版本或人工解决。

validate 只证明结构合规。`missing_inputs` 非空时不得自动启动下游；用户可以明确接受直接输入语义，或补充上游后再验。本节点不打分、不产出评分 JSON；候选是否值得验交给下游 scorecard。没有外网时，使用用户给的材料并说明未知，不生成虚假来源。

## outside-view 的轻量复用

有可用 outside-view 时，仅在缺少会改变决定的外部信息时调用；已有一手材料足够就 DIRECT。不要求每次检索，不增加人审节点。该技能缺失时仍执行同一判断：先列未知项，再决定检索是否值得；保留不确定性，不阻塞纯本地工作。
