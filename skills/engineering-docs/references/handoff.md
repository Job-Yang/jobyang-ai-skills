# 独立调用与 OPC 交接

本规范和 `scripts/artifact_io.py` 随技能整包交付，Python 3.9+，只用标准库。所有相对路径都相对当前技能目录；不要求访问原机器或安装 iLoop。

## 谁控制流程

- 用户明确要求 OPC 或已有 OPC flow 正在执行：OPC 适配器控制输入、输出目录、人审和后续编排。独立技能只执行当前能力，不重新开启问诊或另起流程。用户已确认的需求直接复用。
- 用户直接调用单点能力：独立模式。输入是用户给的文本、附件或显式路径；输出由宿主附件区或用户指定位置承载。不能因为发现 iLoop 环境变量或旧 PRD 就自动切 OPC。
- 同一任务同时命中两种入口时，明确的 OPC 调用上下文优先于技能默认行为；用户最新明确指令优先。不修改宿主全局入口来实现优先级。
- 技能声明输入输出，不强制选择下一节点。缺少材料时可接受直接描述，不强迫用户补跑整条流水线。

## Markdown 信封

```yaml
---
schema: opc-artifact/v1
opc_node: prd
artifact_kind: prd
opc_version: 0.2.0
topic: example-product
created: 2026-09-25T10:00:00+00:00
upstream: null
produced_by: standalone
human_review: pending
---
```

`opc_node` 是能力；`artifact_kind` 是产物类型，例如同一个 prd 节点输出 prd 和 plan。兼容已有 v1 中没有 artifact_kind 的文件。`topic` 使用小写 slug；多候选雷达可为 null，每条候选要给自己的 slug。`created` 为带时区的真实生成时间。

直接输入的 upstream 为 null。多个上游写 `inputs: '["prd-example-product.md", "assess-example-product.md"]'`，使用工件相对路径，不使用远端绝对路径。并行实例使用不同 topic（如 example-product-ios、example-product-web），或由编排为实例分配不同数据根；不允许把两份同名产物挤进一个路径。可附 `node_run_id` 记录实例，但本版本不实现调度引擎。

原有 v1 缺必填字段时应显式补全，不猜时间、来源或审批。正文最低结构由工具检查，正文中证据的真实性、设计质量和需求价值仍需领域验证。

## 输出与搬运

有文件能力时交付可下载的 Markdown；涉及评分 JSON、原型、素材、阶段契约和评论时打包。无文件能力时，在一个完整的 Markdown 代码块内输出信封和正文，不混入说明、不省略。本地 Agent 接收该块后用 `--stdin` 校验。

```bash
python3 scripts/artifact_io.py validate --input artifact.md
python3 scripts/artifact_io.py pack --input prd-example-product.md plan-example-product.md --out result.zip
python3 scripts/artifact_io.py pack --input assess-example-product.md --scoring _scoring-example-product.json --out result.zip
python3 scripts/artifact_io.py pack --input design-spec-example-product.md --attach prototype --out result.zip
python3 scripts/artifact_io.py ingest --input result.zip --output-root /explicit/artifacts --dry-run
python3 scripts/artifact_io.py ingest --input result.zip --output-root /explicit/artifacts
```

命令由 Agent 执行，用户只需把附件交给本地 Agent。OPC 里通过 `pattern opc.product-pipeline:artifact_io.py -- ingest --input <file>` 接收；适配器负责提供 ILOOP_DATA_ROOT。独立使用始终显式给 --output-root。

包是 `opc-bundle/v1`，包含 manifest.json 和逐文件摘要。支持一个 topic 的多个 Markdown、评分 JSON 和 prototype 整目录。附件需自包含；必须把引用的图片、字体、页面和评论文件一起交付，清楚标注仍依赖网络的资源。工具校验文件完整性，不代替浏览器检查引用和交互。禁止附带凭证、缓存和符号链接。

## 导入、校验与审批

导入先校验全部文件和冲突，再落地。原始包保存在 `_handoffs/<摘要>/source.zip`，收据记录缺失上游。新导入正文一律 `human_review: pending`；远端的 approved 仅是原始材料的一部分，不自动授权本地开工。已有同内容的本地审批会保留；同名异内容拒绝覆盖，需要明确新版本或人工解决。

validate 只证明结构与评分计算合规。`missing_inputs` 非空时不得自动启动下游；用户可以明确接受直接输入语义，或补充上游后再验。评分 JSON 带回后必须用 score.py 复算，与评分卡对照。设计还要运行工作台、阶段契约和浏览器验收；工程方案仍需验证关键约束。

无 Python 的评分宿主交付完整 `_scoring-<topic>.json`，标注“待本地复算”，不能自报确定的综合分。没有浏览器时，设计只能声明“待运行态验证”。没有外网时，使用用户材料并说明未知，不生成虚假来源。

## outside-view 的轻量复用

有可用 outside-view 时，仅在缺少会改变决定的外部信息时调用；已有一手材料足够就 DIRECT。不要求每次检索，不增加人审节点。该技能缺失时仍执行同一判断：先列未知项，再决定检索是否值得；保留不确定性，不阻塞纯本地工作。
