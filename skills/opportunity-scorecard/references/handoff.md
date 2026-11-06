# 独立调用与 OPC 交接（opportunity-scorecard 节点）

本规范和 `scripts/artifact_io.py` 随技能整包交付，Python 3.9+，只用标准库。所有相对路径都相对当前技能目录；不要求访问原机器或安装 iLoop。

## 版本口径

- 信封 `opc_version: 0.2.0` = opc-envelope 的 **schema 版本**，由冻结的 `artifact_io.py` seal 出，代表信封结构，基本不动。score.py 渲染评分卡时也写 0.2.0，不再用旧的 0.2.2。
- 本 kit（流水线技能包）本轮版本为 **0.3.0（2026-10-16）**，见 CHANGELOG.md，不写进信封。两者不要混为一谈。

## 谁控制流程

- 用户明确要求 OPC 或已有 OPC flow 正在执行：OPC 适配器控制输入、输出目录、人审和后续编排。独立技能只执行当前能力，不重新开启问诊或另起流程。用户已确认的需求直接复用。
- 用户直接调用单点能力：独立模式。输入是用户给的文本、附件或显式路径；上游 radar 文件可选，独立评估不要求先跑雷达。输出由宿主附件区或用户指定位置承载。不能因为发现 iLoop 环境变量或旧 PRD 就自动切 OPC。
- 同一任务同时命中两种入口时，明确的 OPC 调用上下文优先于技能默认行为；用户最新明确指令优先。
- 本节点只出评分卡（`assess-<topic>.md`）或定性评估（`evaluation-<topic>.md`），不强制下一节点。缺少材料时可接受直接描述，不强迫用户补跑整条流水线。

## Markdown 信封（本节点实例）

```yaml
---
schema: opc-artifact/v1
opc_node: assess
artifact_kind: assess
opc_version: 0.2.0
topic: watch-sedentary
created: 2026-10-16T10:00:00+00:00
upstream: "radar-2026-10-16.md"
produced_by: standalone
human_review: pending
composite_score: 6.50
verdict: validate
dark_horse: false
---
```

`topic` 是小写 slug（与上游 radar 给的建议 slug 一致，跨节点不改名）。`composite_score`、`verdict`、`dark_horse` 三个字段一律由 `scripts/score.py` 机器产出，禁止手填；artifact_io 会在交接包层面独立复算 JSON 与卡片的一致性，手改这三个字段会被直接拒绝。

## 输出与搬运

有文件能力时交付可下载的 Markdown；评分 JSON、素材等随交接包走。无文件能力时，在一个完整的 Markdown 代码块内输出信封和正文，不混入说明、不省略。

```bash
python3 scripts/score.py --input _scoring-watch-sedentary.json --stdout
python3 scripts/artifact_io.py validate --input assess-watch-sedentary.md
python3 scripts/artifact_io.py pack --input assess-watch-sedentary.md --scoring _scoring-watch-sedentary.json --out result.zip
python3 scripts/artifact_io.py ingest --input result.zip --output-root /explicit/artifacts --dry-run
python3 scripts/artifact_io.py ingest --input result.zip --output-root /explicit/artifacts
```

命令由 Agent 执行。OPC 里通过 `pattern opc.product-pipeline:artifact_io.py -- ingest --input <file>` 接收；适配器负责提供 ILOOP_DATA_ROOT。独立使用始终显式给 --output-root。

pack 必须把 `assess-<topic>.md` 和逐维数据 `_scoring-<topic>.json` 一起带回：校验器会逐维核对 JSON 与卡片是否一致，缺了 JSON 或对不上都会被拒。本地 ingest 按信封生成标准名 `assess-<topic>.md`。

## 导入、校验与审批

导入先校验全部文件和冲突，再落地。原始包保存在 `_handoffs/<摘要>/source.zip`，收据记录缺失上游。新导入正文一律 `human_review: pending`；远端的 approved 仅是原始材料的一部分，不自动授权本地开工。已有同内容的本地审批会保留；同名异内容拒绝覆盖，需要明确新版本或人工解决。

validate 只证明结构与计算合规，不验证证据真伪。`missing_inputs` 非空时不得自动启动下游（如 product-brief）；用户可以明确接受直接输入语义，或补充上游后再验。没有 Python 的评分宿主只能交付完整 `_scoring-<topic>.json` 并标注"待本地复算"，不能自报综合分。

## outside-view 的轻量复用

有可用 outside-view 时，仅在缺少会改变决定的外部信息时调用；已有一手材料足够就 DIRECT。不要求每次检索，不增加人审节点。该技能缺失时仍执行同一判断：先列未知项，再决定检索是否值得；保留不确定性，不阻塞纯本地工作。
