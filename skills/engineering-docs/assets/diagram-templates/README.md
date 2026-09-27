# 常用图示模板

26 张合成示例由 20 个布局接口生成，与[原有 21 张技术及数据图](../visual-examples/README.md)共用一份浅色主题。模板覆盖结构、时间、协作、定位和比例表达；横竖方向及用途不同的示例不算独立绘图引擎。

先按读者问题选图，再填真实事实。模板借用形状与布局，不替你确认关系、补写发布制度或评估业务效果。超出布局边界时拆图或使用成熟图布局工具，不能删真实节点和边来迁就模板。

## 选择模板

每个预览同目录下都有同名 SVG；输入集中在 [examples.json](examples.json)。

| 阅读问题 | 模板预览 | 输入 ID |
| --- | --- | --- |
| 整体系统分哪些职责层 | [系统架构](gallery/system-architecture.png) | `system-architecture` |
| 哪些能力并列归组 | [网格分组](gallery/capability-grid.png) | `capability-grid` |
| 谁向谁汇报 | [组织架构](gallery/organization.png) | `organization` |
| 内容如何逐级包含 | [层次结构](gallery/hierarchy.png) | `hierarchy` |
| 一个主题可拆成哪些方面 | [思维导图](gallery/mind-map.png) | `mind-map` |
| 事件发生在什么时间 | [水平时间线](gallery/horizontal-timeline.png) | `horizontal-timeline` |
| 处置过程如何沿时间展开 | [垂直时间线](gallery/vertical-timeline.png) | `vertical-timeline` |
| 每阶段交付什么结果 | [阶段里程碑](gallery/milestone-roadmap.png) | `milestone-roadmap` |
| 哪些阶段构成循环 | [循环图](gallery/cycle.png) | `cycle` |
| 正反馈假设如何连接 | [增长飞轮](gallery/growth-flywheel.png) | `growth-flywheel` |
| 层级和基础如何支撑 | [金字塔列表](gallery/pyramid.png) | `pyramid` |
| 产品主张依靠哪些支撑 | [品牌屋](gallery/brand-house.png) | `brand-house` |
| 两组维度如何交叉核对 | [网格矩阵](gallery/grid-matrix.png) | `grid-matrix` |
| 候选在两个维度如何分布 | [二维坐标](gallery/two-axis.png) | `two-axis` |
| 同时比较位置和规模 | [四象限气泡](gallery/bubble-quadrant.png) | `bubble-quadrant` |
| 功能如何随窗口发布 | [发布列车](gallery/release-train.png) | `release-train` |
| 研发中的并行何时汇合 | [产品研发流程](gallery/product-development.png) | `product-development` |
| 谁负责各个动作 | [垂直泳道](gallery/vertical-swimlane.png) | `vertical-swimlane` |
| 责任方之间如何交接 | [水平泳道](gallery/horizontal-swimlane.png) | `horizontal-swimlane` |
| 一个总量由哪些部分组成 | [饼图](gallery/pie.png) | `pie` |
| 总量与各类占比是多少 | [环形图](gallery/donut.png) | `donut` |
| 同一批对象逐层转化多少 | [漏斗图](gallery/funnel.png) | `funnel` |
| 多维度表现如何分布 | [雷达图](gallery/radar.png) | `radar` |
| 业务假设是否互相支撑 | [商业模式画布](gallery/business-canvas.png) | `business-canvas` |
| 哪些条件同时成立 | [韦恩图](gallery/venn.png) | `venn` |
| 范围如何逐级收窄 | [嵌套集合](gallery/nested-sets.png) | `nested-sets` |

流程、时序、甘特、带日期里程碑、C4 架构、状态、数据流和 ER 沿用原有样例。UML 类图、用例图、复杂网络拓扑和服务蓝图可按语义选择 Mermaid、PlantUML 或图布局工具，当前包没有它们各自经过验收的模板。海报、界面原型和 3D 场景不属于本模板集。

## 运行

从技能目录执行，输出到调用方指定的产物目录：

```bash
# 单张合成示例
python3 scripts/render_templates.py --example system-architecture --out /output/structure.svg

# 使用自己的完整输入
python3 scripts/render_templates.py --input /input/structure.json --out /output/structure.svg

# 重现全部 26 张合成示例
python3 scripts/render_templates.py --gallery --out /output/templates
```

结构模板只依赖 Python 3.9+ 标准库；比例、雷达和二维坐标图另需 Matplotlib 与 NumPy。没有这些库仍可使用结构模板和已有图源。PNG 可由当前可用的 SVG 渲染器导出，例如 `rsvg-convert -w 680 structure.svg -o structure.png`。不自动安装工具，不需要平台账号。

每个输入都要包含 `id`、`name`、`title`、`subtitle`、`note`、`layout`。`id` 只含小写字母、数字与连字符。`sample: true` 会显示“合成示例”；真实输入默认不加。单位、来源、状态和适用范围写入副标题或图注。脚本检查布局，不能判断这些声明是否属实。

最小结构输入：

```json
{
  "id": "service-layers",
  "name": "系统架构图",
  "title": "服务按职责分层",
  "subtitle": "目标结构 · 包围关系表示归属",
  "note": "本图不表达调用方向和部署数量。",
  "layout": "layers",
  "groups": [
    {"label": "接入", "items": ["客户端", "开放接口"]},
    {"label": "服务", "items": ["请求处理", "数据存储"]}
  ]
}
```

## 输入边界

以下为正文宽度 680px 下的保守范围。长度检查使用估算字宽；正式交付还要检查实际字体渲染，不能拿校验成功替代看图。

| `layout` | 专属字段与范围 |
| --- | --- |
| `layers` | `groups[{label, items}]`，1～6 层，每层 1～9 项，每行最多 3 项；只表达归属 |
| `grid` | 同上，`columns` 为 2 或 3，最多 12 组 |
| `tree` | `nodes[{id,label,parent?}]`，唯一根，1～20 节点、最多 6 叶；拒绝环、断连和重复 ID |
| `mindmap` | `center`、`groups[{label,items}]`，2～6 分支，左右分列 |
| `timeline` | `orientation` 为 horizontal 或 vertical；`events[{at,label,detail}]`，`at` 用同一单位、有限且严格递增；水平 2～4 点，垂直 2～8 点 |
| `stages` | `groups[{label,items}]`，2～6 阶段，等距表达顺序，不能声称表示工期 |
| `cycle` | `center`、`groups[{label,items}]`，3～4 阶段，顺时针；飞轮的因果仍需证据 |
| `pyramid` | `groups[{label,items}]`，3～6 层，从顶到底，面积不编码数量 |
| `house` | `roof`、`promise`、`foundation`、`pillars[{label,items}]`，2～4 支柱 |
| `matrix` | `rows`、`columns`、二维 `values`，最多 8 行×4 列，至少 2 列 |
| `workflow` | `lanes`、`nodes[{id,lane,step,label}]`、`edges[{from,to,label?}]`；2～3 泳道，每格一个节点；垂直最多 6 步，水平最多 4 步；只支持前向边 |
| `release` | `ready`、`deferred`、四项 `phases[{label,detail}]`；固定为入列、构建、准出、上线概览，准出失败阻断，上线后按条件回退 |
| `business` | 九项 `cells[{label,items}]`；按示例中的九格顺序，不可随意删格后仍称商业模式画布 |
| `venn` | `groups` 为集合名称，2～3 重叠集合及 `intersection`；或 `nested:true` 的 2～4 嵌套集合；面积不编码数量 |
| `pie`、`donut` | `labels`、`values`，2～6 类，非负且总和大于零；环形另有 `unit` |
| `funnel` | 同上，数量必须非递增，首层大于零；条宽对应数量，占比以首层为分母 |
| `radar` | `labels`、`values`、`maximum`，3～6 维，统一 0～maximum；面积不作为综合分 |
| `quadrant`、`bubble` | `bounds:[xmin,xmax,ymin,ymax]`、`split:[x,y]`、`x_label`、`y_label`、`points[{x,y,label,size?}]`；点在轴内，气泡面积线性对应正值 `size` |

泳道模板不是 BPMN 引擎。并行分支要明确写出 AND 和汇合条件；复杂网关、回边、事件竞赛使用相应标准图型。脚本会拒绝重叠节点及穿过其他活动的已知路线，不保证任意前向图都能自动排好。

时间线按 `at` 计算真实间隔，说明文字过近会拒绝绘制。不要通过篡改 `at` 来分开标签。事件很多时分段；想表达等距阶段就选 `stages`。

系统分层图补齐了整体结构表达，但没有替代容器调用图和部署图。层位靠上不表示一定调用下一层；需要这种判断时必须补实际边。

## 样式与验收

共享主题为 [theme.json](../visual-examples/theme.json)：浅紫、浅绿、浅黄、浅蓝、浅红分区，白底内部实体，深灰正文和细灰关系线。参考飞书画板经典色板；语义描边适度加深，以适应正文阅读。它是本技能的默认主题，不代表飞书全部产品的官方标准。

每次换输入后核对语义和数量，再实际渲染：树的归属、泳道的责任、箭头条件、时间比例、图表分母都要对上。模板仅验证了合成示例和部分变化输入，不能承诺任意内容、字体和平台自动通过。
