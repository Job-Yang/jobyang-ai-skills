# 统一绘图能力

**作者只选择图义、Schema和格式，不选择新旧后端。** `diagram_kit` 将成熟编译器、专用布局和自由对象收进同一注册与交付链；未知图型、缺依赖、无效输入或检查失败不换图。

```bash
python3 "$SKILL_DIR/scripts/diagram_kit.py" capabilities
```

清单来自源码注册表：10个typed图型、34个专用layout和自由对象，共45个实现；以运行时 `capabilities` 为准。`component`只用于内部调度，不在公共能力表分类；组件版本和依赖来源仍如实进入回执。

## 按图义选能力

| 要表达 | 注册图型 | 输入约定 |
| --- | --- | --- |
| 高密度架构蓝图（含接口/子模块/横切带） | architecture-blueprint | layers／groups／zones ＋ nodes(code/rows/chips) ＋ connections；见 insight-layouts.md |
| 复合定量数据看板 | dashboard | kpi_badges／kpi_cards ＋ panels(ranked_bars/trend/grouped_bars/drivers)；纯标准库 |
| 三层双翼全景脑图（多分支与明细叶） | panorama-mindmap／mindmap | center ＋ left_groups/right_groups(含 leaves/items) ＋ header；零坐标贝塞尔连线 |
| 带色条头与底部护栏的飞轮 | flywheel／cycle | center ＋ stages(3-4,含 items) ＋ links ＋ guardrails；兼容简单 cycle |
| 阶段×能力类型与共享覆盖带 | capability_map | stages／categories／capabilities／shared；显式归属、测量高度，无调用边；见 capability-map.md |
| 架构、运行单元与部署 | architecture | components／connections；复杂任意分区或draw.io对象用free |
| 跨角色、条件门与回环 | workflow | lanes／nodes／edges，成熟泳道布局 |
| 消息先后与返回 | sequence | participants／messages／activations等图义字段 |
| 状态与事件迁移 | lifecycle | states／transitions／mainPath |
| 数据来源与流向 | dataflow | nodes／flows |
| 实体字段与基数、类关系 | erd／class | entities／relationships或types／relationships |
| 单父级层级 | tree | nodes／parent，不冒充调用图 |
| 真实日期或耗时 | timeline／waterfall | events或spans，保留时间字段 |
| 任务区间与完成后开始依赖 | gantt | 相对工作日估算或给定日期区间分别建模；不假算资源调度 |
| 发布窗口、分支、车票与准出 | release-train | 真实给定窗口／阶段／审批／部署及条件关系；长记录独立详情 |
| 分层、网格、思维导图、阶段与循环 | layers／grid／mindmap／stages／cycle | 对应layout字段进入payload |
| 金字塔、屋形、矩阵、发布、商业、集合 | pyramid／house／matrix／release／business／venn | 对应专用payload，不改画成普通流程 |
| 阶段门、因果、反馈、状态机、图片圈注、ER | stage_gate／causal_chain／feedback_loop／state_machine／image_annotate／er | 复用随包专用Schema和布局 |
| 定量图 | pie／donut／funnel／radar／quadrant／bubble | 数值、单位和来源保留，matplotlib／numpy可选依赖 |
| 任意对象与分区、固定几何、分区端点 | free | `Diagram.to_input()`生成objects／edge_requests／annotations |

## 同名Schema的明确兼容

有些名字相同但图义字段不同。不能把数字时间改成日期，不能把步骤列、消息类型或条件丢掉来适配。

| 既有layout字符串 | 统一注册ID | typed图型ID |
| --- | --- | --- |
| workflow | workflow-steps | workflow |
| sequence | sequence-steps | sequence |
| tree | tree-hierarchy | tree |
| timeline | timeline-stages | timeline |

旧JSON导入按明确layout标记转换外壳，业务字段全部原样进入payload；typedJSON同样只转换外壳。统一输入中不要再塞另一套顶层标记，重名能力用上述ID明确选择。合法的payload.layout配置对象继续保留。

## 查看与格式的真实边界

- 所有成品使用同一中文离线查看器、角色主题、source／scene索引和最终回执。可查找与聚焦已登记的对象；纯统计或形状视图可聚焦完整图与其数据，不伪造卡片／控制流。
- 有真实有向边才启用上下游和路径；层级／关联／实体关系不伪装成调用。组成员与关系边分开；未声明成员保持unknown。
- 所有实现交付HTML，按需导出固定light／dark／plain主题SVG／PNG；交互只在HTML。静态导出复用查看器清理，再解析CSS变量和继承样式。
- draw.io目前仅free支持真实节点、唯一ID和绑定；其他图型请求draw.io在渲染前拒绝，不用嵌SVG冒充可编辑。
- 输入、源和主题变化后重新生成并检查；不能沿用组件原HTML的回执证明后续装配页。
- 未实现的语法转换等不注册；不冒称同输入自动转换。甘特已接入有界任务区间／依赖能力，不提供日历假期或资源调度求解；Explainer阅读能力保持独立原方法。
