---
name: engineering-docs
description: "写、改、评审研发技术文档（技术方案、系统设计、RFC、ADR、重构迁移），主次分明、结论先行；并用 diagram_kit 统一画工程图，不手写 mermaid。触发：「帮我写个技术方案」「把架构图重画一下」「评审下 RFC」。不适用：纯润色、教程、API 手册、非技术文档、产品原型（style-compass）。"
license: MIT
---

# 研发技术文档

读者先看到结论和全貌，再按需进入细节；图让人一眼看出重点，并且以后能直接改。下面先说交付物长什么样，再说怎么做。

## 触发与归属：只要在技术文档里画工程图，就是本技能

不需要用户点名“用 engineering-docs 画图”。命中下面任一情况，走本技能的内容判断与绘图桥接，哪怕当前任务只是“更新文档、回评论、补一张图”。**全部图型统一用 `diagram_kit render`；按图义、Schema和实际格式选注册能力，不让作者判断新旧。维护已审阅 `.py` API 可用 `Diagram.deliver()`，不自动执行未知 Python。**

- 在技术方案/系统设计/RFC/ADR/设计评审/迁移方案里**新增、修改、重画**一张图。
- 图里出现的是**服务、模块、组件、容器、节点、角色、阶段、状态、表实体、数据存储、上下游**及其调用/数据/时序关系。
- 已经有一张 mermaid 流程图、或在飞书画板上手摆的结构图，需要改、替换、统一风格。

归属优先级（高到低）：

1. 工程结构图/流程图/泳道/时序/状态/数据流/ER/部署/里程碑/复合看板/高密度脑图/飞轮 → **本技能**组织事实和关系，由 `scripts/diagram_kit.py render` 按图义与Schema选择注册实现，共享 `meta＋payload`、完整 scene、主题、查看器与回执。缺能力在渲染前拒绝，输入／生成／检查错误不能自动换图。
2. 需要独立散点/定制统计可视化（且 `dashboard` / `render_templates` 无法覆盖）→ 才用通用可视化能力（ECharts 等）。
3. 飞书画板 / 其他平台 → 只是**发布适配器**，把已生成、已检查的成品写进去，不负责从零构图。

判据是图表达的核心语义：工程关系、复合看板、三层脑图与飞轮优先用 `diagram_kit.py render` 声明式 JSON 生成，不手写 mermaid 或临时 SVG 脚本。

**他技能只借图、不抢正文**：`feynman-explainer`、`writing-craft` 与分析复盘稿需画 `architecture-blueprint`／`dashboard`／`panorama-mindmap`／`flywheel` 时，可直接调 `scripts/diagram_kit.py render`（可选 `"preset": "insight"`）独立出图；正文归原技能，**不强制套用 RFC 的 `doc_check.py` 门禁**。需要一页式讲解或速读页时，可用 Explainer 联动图表。

## 绘图边界：内容归本技能，绘制归后端，平台只发布

- **画图先判能力**：确需画图或改图时再按需读取 `references/diagram-capabilities.md`，运行 `diagram_kit capabilities` 查询图型、Schema、格式与依赖。缺能力先拒绝，不只看图型重名。
- **统一输入**：采用 `version=1、type、meta＋payload`，payload保留图型专属字段；副标题／说明可省略，不补造文案。既有JSON明确兼容导入，同名不同Schema采用语义明确的注册ID。
- **完整场景**：保留正文、code／chips／rows、角色／状态、几何、稳定ID、标签、真实边与自由注释。分区成员显式声明；未声明保持unknown，不根据视觉包含猜调用。
- **检查后交付**：统一终稿装配后再检查scene、SVG语义和适用的组件规则，出自己的源／组件／主题／成品指纹回执。浏览器DOM／导出观测不代替独立视觉验收；`browser_verified=false` 不得包装成已认可。
- **平台只做承载**：不手写 mermaid 充结构／流程图，不在飞书画板 DSL 中从零摆节点。发布到哪里不决定内容方法，也不保证 HTML 能在该平台直接运行；需要静态图时从成品导出 PNG／SVG。
- **可修改源**：所有图保留统一JSON与scene；已有Python源保留不覆盖，SVG不能反推完整作者源。draw.io目前仅自由对象图支持真实节点／绑定，其余格式明确拒绝，不能嵌SVG冒称可编辑。一页式讲解仍保留 `.archify.md`。

## 交付物

### 正文：三层

| 层 | 位置 | 内容 |
| --- | --- | --- |
| 首屏 | H1 到第一个 H2 | 结论、要读者做的决定、范围、Level 1 总览图。≤ 450 字 |
| 章节 | H2 和它的第一段 | H2 对应总览节点，3–7 个；第一段一两句给本章结论 |
| 细节 | H3、表格、列表、引用块、附录、折叠块 | 依据、参数、接口、推导、测试矩阵。长于 6000 字必须有附录 |

只读首屏、H2 和每章第一段，读者就能说出：做什么、为什么现在、主干怎么做、代价和风险、要他决定什么。写法、预算和改写示例见 `references/writing-contract.md`。

### 正文格式：结构优先，段落是例外

读者是扫读的。**大段文字是本技能最常见的失败**，必须主动避免：

- **先判形状再落笔**：对比/风险/多对象多属性 → 表格；步骤 → 有序列表；并列要点、属性 → 无序列表（`- **标签**：内容`）；结论、待拍板、前提与待确认项 → `>` 引用块加粗标签（飞书发布为高亮块）；只有因果推理才写短段落。
- **硬线**：段落 ≤ 120 字；纯段落不连排超过 2 段；超过 300 字的章节至少一个表格或列表；加粗只加粗关键词或数字（≤ 16 字）。
- 写完每章自查：**只看加粗、表头、列表标签和引用块，能否读出本章要点？** 不能就重排格式。

形状对照表、强调层级和改写示例见 `references/formatting.md`（版式形状拿不准时按需查阅，核心硬线已列于上方）。若仓库同源存在 `haohao-shuohua/references/reader-layout.md`，本技能是其共用版式底线里密度最高的一档；独立安装本技能时直接按本节执行。

### 图：先选图型，再画

**卡片图不是默认图型。** 最常见的失败是每张图都画成「分区 + 白卡片 + 折线 + 结论卡」。画之前先认关系的形状：

| 关系形状 | 统一图型 |
| --- | --- |
| 运行单元、接口、子模块与部署边界 | `architecture`／`architecture-blueprint` |
| 多角色交接、条件门、闭环 | `workflow` |
| 消息的先后与返回 | `sequence` |
| 状态与事件迁移 | `lifecycle` |
| 实体、字段与基数 | `erd`／`class` |
| 数据的来源、转换与落点 | `dataflow` |
| 单父级包含 / 多维全景拆解 | `tree`／`panorama-mindmap` |
| 阶段×能力类型、横切覆盖 | `capability_map` |
| 正反馈飞轮与底层护栏 | `flywheel` |
| KPI、排名对比、预测趋势与驱动拆解 | `dashboard` |
| 日期、耗时与重叠 | `timeline`／`waterfall`／`gantt` |

- 先明确读者要回答的问题，再定主路径、归属、条件与图型，不用卡片数量、步数硬判图型。
- **信息密度**：图补充正文/表格未直接呈现的关系；高密度架构优先用 `architecture-blueprint` 填实 `code`/`rows`/`chips` 与连线动词，不画空心框。
- 选型见 `references/diagram-selection.md`，能力见 `references/diagram-capabilities.md`，高密度 Schema 见 `references/insight-layouts.md`，覆盖矩阵见 `references/capability-map.md`，执行见 `references/archify-bridge.md`。

### 图与阅读页的交付

| 产物 | 修改源 | 展示 |
| --- | --- | --- |
| 全部工程图与专用视图 | 统一JSON＋scene；兼容既有JSON／Python API | 同一自包含中文HTML，按实际能力导出固定主题SVG／PNG |
| 自由对象图 | 同上；已有 `.py` 保留 | 另支持真实节点与绑定的draw.io |
| 一页式讲解 | `.archify.md` 与引用数据 | Explainer HTML，图表、步骤、来源联动 |

全部绘图以 `theme.json` 为唯一色源：默认 `document-roles` 低饱和色面，分析看板、脑图与飞轮默认或以 `"preset": "insight"` 启用洞察风（均支持 `light`／`dark`／`plain`）。角色、分类、重点、状态分开，规则见 `references/visual-design.md`。

**额外阅读能力按需用**：技术方案的速读页、机制讲解、分享稿可以借用 Explainer 的一页图文组合、步骤定位、来源和代码片段、面板局部修订。它不替作者取证，不改变原文体，也不把所有正文强制改成网页；说明见 `references/archify-reading.md`。

平台无关交付见 `references/portable-delivery.md`，飞书发布读 `references/lark-publish.md`。静态图与正文默认分发，交互页按平台能力作独立附件或链接。

自由对象／Python API读 `references/diagram-system.md`；统一输入与执行读 `references/archify-bridge.md`。已审阅脚本示例为 `assets/examples/personal-harness/arch.py`。

## 工作流

1. **确认任务（新建或更新技术方案）**：谁读，读完做什么决定或动作，依据什么，覆盖什么范围。模式：新建 / 更新已有文档（先通读全文和图；涉及删节、并节或大改既有章节骨架时先过 `sansi-erhouxing`）/ 评审 / 模板适配。
2. **收集上下文，默认直接推进**：先读用户给的文件、链接、代码、配置、日志、历史决定；涉及仓库、源码、论文或技术机制调研时，在检索与分析前读取 `feynman-explainer` 正文与同水位核实范例（写给研发同行的工程方案跳过纯入门科普类比示例，只取核实结论与机制），研究清楚再回到本技能形成工程方案；已有核实结果直接复用。上下文已经充分时直接起草，不搞固定问答；只追问会改变核心决定的缺口。读取材料所需的平台技能可以先加载，但不能代替内容方法；写入前完成内容检查与中文收尾。边聊边写见 `references/collaboration-workflow.md`。
3. **建立工程判断**：现状事实、问题、目标约束、候选、决定与代价、落地设计、风险、验证发布回退、未决问题。这是检查顺序不是目录。完整模型见 `references/decision-model.md`。
4. **先写速读层**：标题、首屏、总览图草稿与 H2/H3 + 每章第一段。**标题写短关键词、模块或方向**（“聚合校验”“发布与回退”“数据采集”），不写成一句判断、不写具体作用域或结论、不编号，结论与作用域放首段；正文不写对话来源和手机号/邮箱/姓名称谓；输入材料未给出的具体专有选型、重试次数、保留天数、阈值与回退时长，一律列为待拍板或待确认项，不凭空编造内部既定默认值（若补充公开行业工程参考值，需明标「参考建议，待评审确认」）；未决参数与待拍板项只在首屏（或文末）集中列一次，不在各章节反复复读，且正文各节描述的恢复、截断或回退动作须与首屏「待拍板」口径严格一致（不把待拍板策略在后文写成既定动作），正文里不写「输入未指定」「材料未提供」等过程词。跑 `python3 scripts/doc_check.py doc.md --skim --source <材料>`，只读速读层确认五问答得上。
5. **填细节**：每段自检“删掉它，结论、职责、失败处理或验收会不会变”，会变的留正文，实现细节进附录，其余删；默认用表格/列表/引用块（形状拿不准时按需查 `references/formatting.md`），不默认写长段。
6. **设计必要的图**：定问题、主路径、归属与条件，查能力表后以 `meta＋payload` 调 `diagram_kit render`；错误不换图，无有向边不画假路径，用独立 Playwright 核对关键信息；已有 Python API 用 `to_input()`/`deliver()`，未知脚本不执行。
7. **检查与交付**：再跑两个 check；锁定事实后过 `haohao-shuohua` 洗 AI 味（只改语言不改技术含义，**不把表格、列表、引用块改回段落，不把 H2 短关键词改成论点句**，不把修改报告写进正文；若同步运行 `quick_scan.py` 体检，传放宽的 `--para-max` / `--run-max` 并遵守 `doc_check.py` 的结构判定；改后复跑 `doc_check.py`）。高风险方案做独立读者测试，走 `references/quality-gates.md` 与 `references/human-reading.md` 四层；先交付平台通用源与静态图，再按指定平台发布（发布到某个平台只是可选的最后一步，平台只承载成文，缺权不阻塞并写明阻塞项）。

复杂流程读 `references/process-modeling.md`，数据图读 `references/data-charts.md`，图型内容要求读 `references/diagram-guidance.md`，团队模板读 `references/template-adaptation.md`。

## 依赖原则：核心零依赖，可选自动补

- Python内存API／SVG兼容save仍只靠标准库；统一交付需要Node.js 18+及独立Playwright＋匹配Chromium。编译器随包固定版本，不安装／升级Node或Archify，缺依赖明确拒绝。
- 定量图需要matplotlib／numpy，先查已有依赖；仅在获准时通过 `bootstrap.py` 隔离到 `.deps`。`ENGINEERING_DOCS_DEPS_DIR` 可指定本次数据目录，不动系统环境。
- 平台SVG固化light／dark／plain，解析CSS变量与继承样式，PNG使用同一清理过的SVG。HTML交互不进入静态图；目标平台原生导入／连线绑定另按实际环境验证。

| 脚本 | 用途 |
| --- | --- |
| `scripts/archify_bridge.py` | 兼容门面；render委托统一交付，explain／compare／patch保留原方法 |
| `scripts/doc_check.py` | 三层结构、预算、速读层、段落墙与格式密度、套话检查 |
| `scripts/diagram_kit.py` | 唯一公共CLI／Python门面：render／capabilities／check；兼容save／svg／drawio |
| `scripts/diagram_check.py` | SVG 格式/字号/色系/比例检查；`--board` 加飞书兼容检查 |
| `scripts/bootstrap.py` | 可选依赖自动安装与失败提示 |
| `scripts/lark_bind.py` | 可选适配器：连线绑定节点的飞书画板数据 |
| `scripts/engineering_docs.py` | 严格模式：`init`/`validate`/`readability`/`transition` |
| `scripts/diagram_runtime.py`／`diagram_scene.py`／`diagram_adapter.mjs` | 内部注册、Schema适配、完整scene、查看器装配与统一检查／交付 |
| `scripts/render_templates.py`／`insight_layouts.py`／`planning_layouts.py` | 专用布局、高密度蓝图/看板/脑图/飞轮与有界排期 |

## 使用边界

使用：技术方案、系统设计、RFC、ADR、重构、迁移、性能方案；把代码、接口、运行证据和讨论整理成可评审文档；评审方案是否可信、可实施、可验证、可回退；画各类技术图；映射团队模板。

不用：纯润色、教程、API 手册、未形成工程决定的调研、技术观点文章和非技术文档不用；面向读者的技术分享文/talk/slides 与观点/长评（不形成评审决策）走 `writing-craft`，本技能只接需要评审/拍板的方案与配套架构图。

与 `content-infographic`（缺失可跳过）的分工：本技能出**严谨结构图**（可编辑可评审）；`content-infographic` 出**直观记忆图**（步骤链/对比/比喻）。同一机制可成对不互替。

与 `style-compass` 分工：交互式产品界面原型与视觉系统走 `style-compass`；本技能专注工程评审方案、严谨工程图与速读页。

下游编码交接：方案 RFC/ADR 评审拍板后，如需进一步编译为编码阶段逐提交落地的深模块接口与步骤，可由 `implement-spec` 承接；若要在动工前做跨上下文独立盲审挑刺，可交 `spec-battle`。

OPC 独立交接：复用用户材料和指定输出位置，不依赖 iLoop；需要信封封装或打包时读 `references/handoff.md`。
