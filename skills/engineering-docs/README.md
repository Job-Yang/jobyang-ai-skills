# 研发技术文档

> 一个入口完成上下文收集、技术决策、协作成文、图示和读者验证。

[English](./README.en.md)

## 它解决什么

AI 很容易生成结构完整、语言流畅的技术方案，却可能认错系统链路、漏掉关键约束，或者把未经确认的推测写成事实。

研发文档技能先组织证据和决定，再写正文。它适用于：

- 技术方案和系统设计。
- RFC 与架构决策。
- 重构、迁移和性能优化方案。
- 跨系统接口、数据或流程改造。
- 读取上下文后直接起草，或与用户分段共创。
- 基于新事实调整已有研发方案，以及评审方案是否成立。
- 团队技术方案模板适配。

它不负责纯措辞润色、教程、操作手册、API 参数全集、技术科普、观点文章或未来畅想。

上下文收集、逐段迭代和独立读者测试都包含在本技能内。上下文充分时默认直接写；只有信息存在关键缺口、方案需要共同取舍，或用户明确要求边聊边写时才进入共创。

内部决策模型与外部正文分开：证据账本和 G0 至 G12 用于自检，默认不会写进给人阅读的文档。正文根据读者的实际问题组织，目标、范围边界、候选比较等内容只在确实需要时出现。

图示也按问题生成，不按模板凑数。技能会在边界、层级、时序、状态、数据关系或排期仅靠文字难以读懂时，选择上下文图、容器图、时序图、状态图、数据流图、ER 图、甘特图或里程碑图，并要求图源可编辑、真实渲染、与正文互相校验。

## 图表覆盖

[查看原有 21 张样例](assets/visual-examples/README.md)及[新增 26 张常用模板](assets/diagram-templates/README.md)。合计 47 张合成示例，均提供 SVG 和 680px PNG。新增模板共用 20 个布局接口；横竖方向和用途变体不计作独立引擎。

| 场景 | 包内画法与样例 |
| --- | --- |
| 架构设计 | 上下文、容器、组件、部署 |
| 运行与协作 | 流程、泳道、时序、状态 |
| 数据设计 | 数据流、ER |
| 排期与交付 | 甘特、里程碑，共用计划数据 |
| 性能与分析 | 趋势、哑铃比较、直方图、ECDF、箱线、散点、热力 |
| 规模与成本 | 堆叠组成、瀑布增减 |
| 整体结构与归属 | 分层系统架构、网格分组、组织树、层次结构、思维导图 |
| 阶段与反馈 | 横竖时间线、阶段里程碑、发布列车、研发并行流程、横竖泳道、循环与飞轮 |
| 定位与交叉核对 | 品牌屋、金字塔列表、网格矩阵、商业模式画布、韦恩与嵌套集合 |
| 比例与多维比较 | 饼图、环图、漏斗、雷达、二维坐标、气泡 |

统一主题采用浅色分组、白色内部实体、深灰正文与细灰关系线，参考飞书画板经典色板。定量线和关键路径保留对比度。形状仍按阅读任务选择，不把不同图型变成同一种卡片。

视觉方法按图型组织层级、重点、分区和标签，数据图保留口径、尺度与复算源。BPMN/DMN 目前提供选型与语义指导，标准模型执行需专用工具；火焰图等专业视图按需使用实际数据与对应工具。样例通过不代表所有输入和平台自动通过。

美化既有图时，先保存基线，再调整信息分组、标签位置和阅读顺序。需要证明效果时，按 [视觉对照方法](references/visual-evaluation.md) 做同尺寸匿名比较，分别记录内容正确性、读图答案和视觉偏好；允许平局和旧版更好。

## 不依赖飞书

普通使用只需要能读取本技能和用户材料的 Agent。默认交付 Markdown、可编辑图源和预览，不需要飞书账号、MindAI、iLoop 或其他绘图技能。机器校验工具需要 Python 3.9+，只用标准库；数据图样例的可选复现脚本另需 Matplotlib 和 NumPy，不影响技能文本与已有图源的使用。图示验收需要本地或宿主提供渲染、查看能力，没有这些能力时明确标注视觉未验收。

图示先确定节点与关系，再选择流程图、泳道图、BPMN、时序图或状态图；多条件规则适合决策表。布局保留并行、汇合和回路，不能为了紧凑改变技术含义。正文、画板、幻灯片和打印分别按最终阅读尺寸验收。

飞书画板和 MindAI 都是可选适配器。用户需要在线协作或指定发布时才启用；跨平台使用同一套判断和图示方法，按平台支持情况交付 SVG/PNG 与原始图源。预览可离线阅读，效果仍需在实际宿主核验，不承诺所有平台自动一致。

## 怎么开口

> 用 engineering-docs 根据这些代码和运行结果写迁移方案，说明为什么迁移、影响谁、如何验证和回退。

> 按这次接口变更更新已有技术方案，先通读正文和图，保留仍然成立的决定。

直接提供材料和希望读者作出的决定即可，不要求先生成 PRD。普通任务交付正文、必要图源及预览；严格模式才增加结构化记录。所有文件写到调用方指定的目录或宿主附件区。

## 核心方法

```text
上下文与读者动作
→ 事实与现状
→ 问题
→ 目标和边界
→ 约束
→ 候选方案
→ 决定与代价
→ 落地设计
→ 影响与风险
→ 验证、发布和回退
→ 未决问题
```

技能把事实、推导、假设、决定和待确认项分开。关键事实缺少证据时停止包装最终结论；高风险方案缺少验证、感知或止损办法时，只能保留为草案。

完整门禁和结构化记录属于严格模式。普通技术文档不要求先生成 JSON，也不默认运行 G0 至 G12。

## 目录

```text
engineering-docs/
├── SKILL.md
├── README.md
├── README.en.md
├── references/
│   ├── decision-model.md
│   ├── collaboration-workflow.md
│   ├── diagram-guidance.md
│   ├── diagram-recipes.md
│   ├── visual-design.md
│   ├── visual-evaluation.md
│   ├── data-charts.md
│   ├── diagram-sources.md
│   ├── process-modeling.md
│   ├── portable-delivery.md
│   ├── handoff.md
│   ├── quality-gates.md
│   └── template-adaptation.md
├── assets/visual-examples/
│   ├── README.md
│   ├── render_diagrams.py
│   ├── render_charts.py
│   ├── plan.json
│   ├── chart-data.json
│   ├── theme.json
│   └── gallery/             # 可编辑 SVG 与正文 PNG
├── assets/diagram-templates/
│   ├── README.md            # 类型映射、输入与边界
│   ├── examples.json
│   └── gallery/
├── templates/
│   ├── decision-record.json
│   └── engineering-doc.md
├── scripts/
│   ├── engineering_docs.py
│   ├── artifact_io.py
│   ├── render_templates.py
│   └── scoring-rules.json
└── tests/
    ├── test_engineering_docs.py
    └── test_render_templates.py
```

## 严格模式

需要机器校验、生命周期状态或审计记录时，再初始化结构化工作区。

### 初始化

```bash
python3 scripts/engineering_docs.py init \
  --title "会话存储迁移方案" \
  --author "作者" \
  --type technical-design \
  --output /tmp/session-storage-design
```

生成两份文件：

- `document.md`：给人阅读和评审。
- `decision-record.json`：记录证据、决定、风险、门禁和状态。

### 校验

校验当前状态：

```bash
python3 scripts/engineering_docs.py validate \
  --record /tmp/session-storage-design/decision-record.json
```

预检是否达到可实施状态：

```bash
python3 scripts/engineering_docs.py validate \
  --record /tmp/session-storage-design/decision-record.json \
  --target implementable
```

脚本会检查：

- 决策记录结构和枚举值。
- G0 至 G12 的门禁状态。
- 关键证据的来源、范围和时间。
- 方案唯一与多候选路径的不同要求。
- 风险触发项对应的控制措施。
- 图示的问题、范围、事实来源和可编辑图源。
- 可实施状态下图示的真实渲染与复核证据。
- 独立读者测试。
- 默认 Markdown 中是否仍有填写提示。
- 默认正文是否泄漏内部证据账本和门禁过程。

脚本不会判断技术事实是否正确，也不会替决定责任人批准方案。

### 状态流转

```bash
python3 scripts/engineering_docs.py transition \
  --record /tmp/session-storage-design/decision-record.json \
  --to in_review \
  --actor "技术负责人" \
  --reason "作者自查完成，进入评审"
```

支持的主要状态：

```text
草案 → 待评审 → 已决定 → 可实施 → 已实施
                   ↓
                 待复核
                ↙      ↘
          恢复原状态   被取代
```

未采纳提案会保留否决或撤回理由。状态变化会写入 `history`。

## 验证

```bash
python3 -m unittest discover -s tests -v
```

## 安装

克隆仓库后，把完整目录复制到目标 Agent 的 Skills 目录，或让支持读取文件的 Agent 读取 `SKILL.md` 并按需加载包内参考。不同宿主的技能目录和召回方式各不相同；下面只展示 TRAE 用户级安装：

```bash
git clone https://github.com/Job-Yang/jobyang-ai-skills.git
cp -R jobyang-ai-skills/skills/engineering-docs ~/.trae/skills/engineering-docs
```
