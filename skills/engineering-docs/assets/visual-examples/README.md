# 可复用技术图样例

这里有 12 种技术视图和 9 种数据图的合成示例。每张图保留可编辑 SVG 和 680px PNG 阅读版，源码用于复现和学习版式；不是任意输入的自动排版引擎。换内容、字体或载体后仍需重新渲染检查。

分层架构、组织树、时间线、发布列车、循环、矩阵、品牌屋与比例图等另见 [26 张常用模板](../diagram-templates/README.md)。两组图共用 [theme.json](theme.json) 的浅色主题；本页保留原有关系与数据示例，新增模板提供有明确范围的 JSON 输入。

复用时同时参考 [视觉设计](../../references/visual-design.md)：分组承担边界和阶段，关键数值就近标注，辅助线保持克制。横向箱线、组成比较、分区流程、分阶段时序和共享时间轴分别展示不同的阅读组织方式，不统一套成一种卡片布局。

## 按问题选样例

| 想表达什么 | 样例 | 图源 |
| --- | --- | --- |
| 系统与外部参与者 | [上下文](gallery/01-context.png) | [SVG](gallery/01-context.svg) |
| 独立运行与存储单元 | [容器](gallery/02-container.png) | [SVG](gallery/02-container.svg) |
| 单个进程内部依赖 | [组件](gallery/03-component.png) | [SVG](gallery/03-component.svg) |
| 副本、故障域和共享依赖 | [部署](gallery/04-deployment.png) | [SVG](gallery/04-deployment.svg) |
| 判断、并行汇合与重试 | [流程](gallery/05-flow.png) | [SVG](gallery/05-flow.svg) |
| 多角色交接与返工 | [泳道](gallery/06-swimlane.png) | [SVG](gallery/06-swimlane.svg) |
| 同步调用、异步消息与回执 | [时序](gallery/07-sequence.png) | [SVG](gallery/07-sequence.svg) |
| 合法状态与恢复路径 | [状态](gallery/08-state.png) | [SVG](gallery/08-state.svg) |
| 原文、转换与报告去向 | [数据流](gallery/09-dataflow.png) | [SVG](gallery/09-dataflow.svg) |
| 实体、键和基数 | [ER](gallery/10-erd.png) | [SVG](gallery/10-erd.svg) |
| 工期、并行和关键路径 | [甘特](gallery/11-gantt.png) | [SVG](gallery/11-gantt.svg) |
| 可验收成果与日期 | [里程碑](gallery/12-milestone.png) | [SVG](gallery/12-milestone.svg) |
| 指标随时间变化 | [趋势](gallery/13-trend.png) | [SVG](gallery/13-trend.svg) |
| 同一输入下的方案差异 | [哑铃比较](gallery/14-comparison.png) | [SVG](gallery/14-comparison.svg) |
| 分布形状与长尾 | [直方图](gallery/15-histogram.png) | [SVG](gallery/15-histogram.svg) |
| 阈值以内的样本比例 | [ECDF](gallery/16-ecdf.png) | [SVG](gallery/16-ecdf.svg) |
| 多组样本的分布差异 | [箱线](gallery/17-boxplot.png) | [SVG](gallery/17-boxplot.svg) |
| 两变量的共同变化 | [散点](gallery/18-scatter.png) | [SVG](gallery/18-scatter.svg) |
| 维度与时段热点 | [热力](gallery/19-heatmap.png) | [SVG](gallery/19-heatmap.svg) |
| 绝对总量的组成 | [堆叠条形](gallery/20-composition.png) | [SVG](gallery/20-composition.svg) |
| 增减贡献与总量闭合 | [瀑布](gallery/21-waterfall.png) | [SVG](gallery/21-waterfall.svg) |

## 示例的事实边界

技术示例以虚构文档检查系统为背景，旨在展示不同视角，不是一个完整产品方案。上下文只展示系统边界；容器图只展开内部处理，省略外部通知；组件图只展开执行器；部署图只展示 HTTP 服务。图的范围差异不代表其他组件被删除。

时序图展示预先订阅队列后的成功场景，省略订阅、持久化确认和存储内部交互。202 回执只表示 API 接收任务；具体消息系统的投递保障不能由这张示意图推断。异常与重试另由流程和状态样例表达，真实方案必须补齐其实际契约。

流程图采用以下固定输入，便于检验改图是否丢失关系：

- 输入目录有效且输出路径未占用，才同时启动源码扫描和配置检查。
- 两项检查各最多 5 秒，等待两项返回；任一失败都不写报告。
- 写入最多尝试 3 次，失败且未满次数时等待 1 秒再写。
- 重试只回写入，不重做扫描；第三次失败结束。输入目录只读。

状态图的简化生命周期仅允许排队时取消；运行成功结束，运行失败按次数进入等待或失败终态。未展示运行中取消，不代表真实系统也应采用这一约束。

ER 图使用数字基数，Document 对 Task、Task 对 Finding 都是一对零到多；每个子实体恰好属于一个父实体。删除策略不在本例范围内。

排期见 [plan.json](plan.json)。A 用时 2 天；B、C 依赖 A，分别 4 天、3 天；D 依赖 B 和 C，用时 3 天；E 依赖 D，用时 1 天。全部按相对工作日及完成后开始依赖计算，资源无冲突。计算结果为 10 天、关键路径 A–B–D–E、C 的总时差为 1 天。里程碑共用这些输入。

数据图的全部数值见 [chart-data.json](chart-data.json)，均为人工构造。直方图、ECDF 和箱线图共享两组各 40 个延迟值；其他图使用各自独立样本，不能互相拼成真实实验结果。统计量由脚本计算，标题、图注和适用结论仍需人工核对。

## 复现与改用

结构图只需要 Python 标准库：

```bash
python3 render_diagrams.py --out /explicit/output
```

数据图示例需要 Matplotlib 与 NumPy（示例使用 NumPy 1.22+ 的分位数参数）：

```bash
python3 render_charts.py --out /explicit/output
```

前者生成 SVG、关系清单与排期计算；后者生成 SVG、高清 PNG、统计量和实际绘图库版本。搬运复现脚本时一并携带 `theme.json`、`plan.json` 和 `chart-data.json`，或直接复制整个技能目录。结构图 PNG 可用现有 SVG 渲染器导出，例如：

```bash
rsvg-convert -w 680 /explicit/output/05-flow.svg -o /explicit/output/05-flow.png
```

不运行脚本也能直接阅读已有图或编辑 SVG。输出目录显式指定，不需要飞书账号、其他技能或网络。脚本会覆盖输出目录中的同名示例文件，应使用专用目录。

复用时先替换关系或原始数据，再调整布局和说明。不要只替换节点名称；关系、图注、重点、单位和结论可能同时变化。SVG 字体保留为文字，接收端会按可用字体回退；跨平台阅读优先使用已渲染 PNG。

这些脚本保留了样例专用的标题、轴范围和坐标。使用新数据时必须重新核对这些内容；复杂或频繁变化的拓扑应采用成熟布局工具。需要评价改版是否有效时，使用 [视觉对照方法](../../references/visual-evaluation.md)，不把成功生成图片当成质量结论。

这些样例验证的是具体输入下的表达与渲染，不能保证所有复杂图、UML 组合框、BPMN/DMN 执行或平台导入都自动通过。
