# 独立调用与 OPC 交接（product-brief 节点）

本规范和 `scripts/artifact_io.py` 随技能整包交付，Python 3.9+，只用标准库。所有相对路径都相对当前技能目录；不要求访问原机器或安装 iLoop。

## 版本口径

- 信封 `opc_version: 0.2.0` = opc-envelope 的 **schema 版本**，由冻结的 `artifact_io.py` seal 出，代表信封结构，基本不动。本节点过去文档自称"版本 0.2.1"的写法已废弃。
- 本 kit（流水线技能包）本轮版本为 **0.3.0（2026-10-16）**，见 CHANGELOG.md，不写进信封。两者不要混为一谈。

## 谁控制流程

- 用户明确要求 OPC 或已有 OPC flow 正在执行：OPC 适配器控制输入、输出目录、人审和后续编排。独立技能只执行当前能力，不重新开启问诊或另起流程。用户已确认的需求直接复用。
- 用户直接调用单点能力：独立模式。输入是用户给的文本、附件或显式路径；上游评分卡（`assess-<topic>.md`）可选，写 PRD 不强制先评分。输出由宿主附件区或用户指定位置承载。不能因为发现 iLoop 环境变量或旧 PRD 就自动切 OPC。
- 同一任务同时命中两种入口时，明确的 OPC 调用上下文优先于技能默认行为；用户最新明确指令优先。
- 本节点产出 PRD 与计划，不强制下一节点（不自动编码、不自动设计、不自动发布）。

## Markdown 信封（本节点实例）

PRD 与计划同 topic，都在 `opc_node: prd` 节点下，靠 `artifact_kind` 区分：

```yaml
---
# prd-example-product.md
schema: opc-artifact/v1
opc_node: prd
artifact_kind: prd
opc_version: 0.2.0
topic: example-product
created: 2026-10-16T10:00:00+00:00
upstream: "assess-example-product.md"
produced_by: standalone
human_review: pending
---
```

```yaml
---
# plan-example-product.md
schema: opc-artifact/v1
opc_node: prd
artifact_kind: plan
opc_version: 0.2.0
topic: example-product
created: 2026-10-16T10:05:00+00:00
upstream: "prd-example-product.md"
produced_by: standalone
human_review: pending
---
```

直接输入时 `upstream: null`。topic 是小写 slug，下游沿用。正文字段（问题/目标人群/用户旅程/功能范围/验收/平台/未决；里程碑/依赖/验收/估算）由校验器逐节检查，缺节会被拒。

## 输出与搬运

正文写好后用 seal 封装，再打包：

```bash
python3 scripts/artifact_io.py seal --input prd-body.md --node prd --kind prd --topic example-product --upstream assess-example-product.md --producer standalone --out prd-example-product.md
python3 scripts/artifact_io.py seal --input plan-body.md --node prd --kind plan --topic example-product --upstream prd-example-product.md --out plan-example-product.md
python3 scripts/artifact_io.py validate --input prd-example-product.md
python3 scripts/artifact_io.py pack --input prd-example-product.md plan-example-product.md --out result.zip
python3 scripts/artifact_io.py ingest --input result.zip --output-root /explicit/artifacts --dry-run
python3 scripts/artifact_io.py ingest --input result.zip --output-root /explicit/artifacts
```

命令由 Agent 执行。OPC 里通过 `pattern opc.product-pipeline:artifact_io.py -- ingest --input <file>` 接收；适配器负责提供 ILOOP_DATA_ROOT。独立使用始终显式给 --output-root。无文件能力时，在一个完整的 Markdown 代码块内输出信封和正文，不混入说明。

## 导入、校验与审批

导入先校验全部文件和冲突，再落地。原始包保存在 `_handoffs/<摘要>/source.zip`，收据记录缺失上游。新导入正文一律 `human_review: pending`；远端的 approved 仅是原始材料的一部分，不自动授权本地开工。已有同内容的本地审批会保留；同名异内容拒绝覆盖，需要明确新版本或人工解决。

validate 只证明结构合规。`missing_inputs` 非空时（如引用了上游评分卡但包没带）不得自动开工，用户可以明确接受直接输入语义，或补上游后再验。完整计划不是开工授权；已得到的用户授权要在 PRD 里明确记录。

## 关于包内的 scoring-rules.json

本节点不执行评分。`scripts/artifact_io.py` 与 `scripts/scoring-rules.json` 是 opc-envelope 0.2.0 的 vendored 公共副本（见 `scripts/vendor-manifest.json`），只用来给本节点的 prd/plan 产物做信封校验和交接。本包不读评分规则做计算；需要评分时用 opportunity-scorecard 包。

## outside-view 的轻量复用

有可用 outside-view 时，仅在缺少会改变决定的外部信息时调用；已有一手材料足够就 DIRECT。不要求每次检索，不增加人审节点。该技能缺失时仍执行同一判断：先列未知项，再决定检索是否值得；保留不确定性，不阻塞纯本地成文。
