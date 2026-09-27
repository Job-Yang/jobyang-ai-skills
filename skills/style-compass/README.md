# 设计罗盘

把需求变成可交互的 UI/UX 原型和可供开发的设计规格。适合能写代码、但难以描述视觉偏好的开发者。它能单独运行，不需要 iLoop、Figma、Superdesign 或其他设计技能。

[English](./README.en.md)

## 怎么开口

> 用 style-compass 设计这个产品。我有需求但没有视觉参考，请给我能直接操作的高保真候选，再在选定方向上打磨。

> 这是现有界面和使用流程。帮我调整交互，保留每次候选、选择理由和区域评论，最后交付原型与设计规格。

输入可以是 PRD、一句话需求、已有产品或代码与截图。没有 PRD 时，技能先在当前任务内整理最小需求，不要求另装产品技能。

## 设计怎么推进

先确认页面结构和交互语义，再呈现接近成品的视觉候选，选定后展开所有页面、状态和细节。结构与交互探索可以使用灰阶原型；视觉选择必须看高保真结果，不能只给线框换色。

需求、页面、旅程、动作和状态分别使用稳定的 `R/P/J/A/S` 标识。视觉可以重做构图和控件，但不能悄悄丢掉已经确认的功能或改变结果状态。

各阶段共用包内的“空间画室”工作台：顶部切换阶段，左侧管理页面和产物，中央体验设计，右侧讲解或评论，底部选择当前对象。画布支持双指或拖动空白处直接平移，也能并排比较方案。

模型负责设计质量；脚本负责复用工作台、检查结构和导出规格。脚手架本身是起点，不能当成已经完成的产品设计。

## 会留下什么

| 产物 | 用途 |
| --- | --- |
| `prototype/index.html` | 统一评审入口和可交互画板 |
| `prototype/index.design.json` | 各阶段确认边界、语义标识和覆盖关系 |
| `prototype/review-framework/` | 随包携带的工作台样式与脚本 |
| `prototype/review-data/comments.json` | 绑定具体页面、模块和区域的评论 |
| `prototype/review-data/workflow.json` | 阶段状态、选择和融合意见 |
| 结构稿、交互稿、视觉候选与定稿 | 保留在原型目录，可回看各阶段 |
| `design-spec-<topic>.md` | 从 HTML 与阶段契约导出的开发规格 |

评论和选择记录由评审服务持久化，不能只留在聊天或浏览器缓存中。导出设计规格前，要补齐页面、组件、状态、交互及原型索引；导出器不会自动理解所有业务语义。

## 安装与运行要求

把完整目录复制到 `~/.trae/skills/style-compass/` 或宿主规定的技能目录，保留 `assets/`、`examples/`、`references/` 和 `scripts/`。

包内脚本使用 Python 3.9+ 和标准库。正式完成设计还需要浏览器渲染、截图查看和实际操作能力。在线研究、字体服务及外部画布都是可选项；引用外部资源时，应随交付包提供可分发文件或写清网络依赖。

云端宿主能运行 Python 和网页预览时，可使用同一套文件。只支持文本时，可交付草案和完整代码，但要标明运行态未验证；无法持久化评论时，也不能声称已完成正式评审。

## 本地起步

以下命令在技能目录执行，`design-output` 代表调用方指定的产物位置：

```bash
python3 scripts/scaffold_review.py ./design-output/prototype
python3 scripts/validate_review_workspace.py ./design-output/prototype/index.html
python3 scripts/review_server.py --root ./design-output/prototype --port 8823
```

评审页为 `http://127.0.0.1:8823/index.html`。Agent 替换画板和设计清单，保留公共工作台，并维护阶段契约。

视觉候选展示前做结构覆盖检查；定稿交付时将 `direction` 换成 `final`，再进行浏览器验收：

```bash
python3 scripts/validate_stage_contract.py --contract ./design-output/prototype/index.design.json --html ./design-output/prototype/index.html --phase direction
python3 scripts/export_spec.py ./design-output/prototype/index.html --meta ./design-output/prototype/index.design.json --topic example-product --producer standalone -o ./design-output/design-spec-example-product.md
python3 scripts/artifact_io.py pack --input ./design-output/design-spec-example-product.md --attach ./design-output/prototype --out ./design-output/design-result.zip
python3 scripts/artifact_io.py ingest --input ./design-output/design-result.zip --output-root ./received
```

打包包含原型、候选、阶段契约和已保存的评论。导入后原型位于 `<topic>/prototype/`，工具不自动重写正文相对链接，需按收据和原型索引定位。机器校验通过不能替代真实渲染、交互检查和用户确认。

## 包内方法与可选集成

[SKILL.md](./SKILL.md) 是 Agent 入口。`references/` 分别说明结构、问诊、交互、视觉参考、固定工作台、阶段契约和交付；`scripts/` 提供生成、校验、规格与 Token 导出、候选对比和评审服务。具体项目从 `assets/review-framework/` 的公共工作台起步。

明确进入 OPC 时，由设计适配器传入需求、输出位置和审批要求；单独使用直接接受用户材料，不查找 iLoop 固定目录。需要外部依据时可选用 outside-view，缺少它仍可按已有材料完成设计。

本技能交付设计原型与规格。生产代码、部署和市场验证需要后续任务完成。
