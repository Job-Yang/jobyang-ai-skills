# 高密度图型参考（零坐标 JSON Schema）

当模型需要生成高信息密度的系统架构蓝图、复合数据看板、双翼三层全景脑图或带护栏飞轮时，优先使用下列声明式 JSON 图型交由 `diagram_kit.py render` 自动排版，禁止手写上百行像素坐标 SVG 脚本。

完整可直接复制的黄金样例位于 `assets/diagram-templates/insight/`：

- [architecture-blueprint.json](../assets/diagram-templates/insight/architecture-blueprint.json)
- [composite-dashboard.json](../assets/diagram-templates/insight/composite-dashboard.json)
- [panorama-mindmap.json](../assets/diagram-templates/insight/panorama-mindmap.json)
- [guardrail-flywheel.json](../assets/diagram-templates/insight/guardrail-flywheel.json)

## 1. `architecture-blueprint`（高密度系统架构蓝图）

- **默认主题**：`preset: "document-roles"`（工程默认低饱和色面；对外分享或分析报告可显式传 `"preset": "insight"`）。
- **核心结构**：支持 `layers + groups + nodes`（多层横向/纵向分栏），或 `zones`（`orientation: "horizontal"` 横向分区或 `"vertical"` 纵向层级）+ `components`/`nodes` + `connections`/`relations` + `shared_coverage` + `notes`。
- **防空心框约定**：每张核心卡片建议至少填充 `code`（接口或协议标识）、`desc`（职责一句）、`rows`（内部子模块或成员，如 `[["主写存储", "唯一写源"], ["待发队列", "同事务"]]`）或 `chips`（如 `[["强一致写入", "filled", "teal"], "P99 < 45ms"]`）之一，每条重要连线写 `label`。
- **自动能力**：按内容测量卡片高度、在层间/区外走廊自动正交走线避让非端点卡片，支持 `shared_coverage` 横切带并保留显式 `members` 与完整 `scene`。

## 2. `dashboard`（复合定量数据看板）

- **默认主题**：`preset: "insight"`（白卡灰底与高辨识语义色；同样支持 `light` / `dark` / `plain` 导出）。
- **顶层字段**：`layout: {"width": 1360}`、`kpi_badges`（右上角胶囊指标）、`kpi_cards`（顶部 2–5 张摘要 KPI 卡）、`columns`（`1` 或 `2`）、`panels`。
- **支持的面板 `type`**：
  - `ranked_bars`：水平背景轨 + 比例柱 + 数值直标 + 行级 `highlight` 高亮 + 分组分隔线 `divider_before` + 右侧 `delta` 徽章或 `reason` 说明列 + 底部 `takeaway` 结论条。
  - `trend` / `grouped_bars`：折线/面积/柱图或双轴组合图（`kind: "line" | "area" | "bar"`、`axis: "left" | "right"`），支持 `split_after` 区分历史实线与预测虚线阴影区，支持 `annotations` 事件标注点与防碰撞标签。
  - `drivers` / `cards`：多列驱动因素与关键结论摘要卡。

## 3. `panorama-mindmap`（三层全景脑图，或传 `mindmap` 扩展字段）

- **默认主题**：`preset: "insight"`，推荐画布宽度 `1440`。
- **核心字段**：`center`（对象或字符串）、`left_header` / `right_header`（左右翼标题）、`left_groups` + `right_groups`（或统一 `groups`，共 2–12 个分支）。
- **三级叶子**：每个分支下传 `leaves`（或 `items`），支持 `{"id": "...", "label": "标题", "detail": "一句机制说明"}` 或 `"标题：说明"` 字符串，引擎自动测量高度、居中对齐枝干、绘制贝塞尔曲线。

## 4. `flywheel`（带护栏与色条头的闭环飞轮，或传 `cycle` 扩展字段）

- **默认主题**：`preset: "insight"`，推荐画布宽度 `1320`。
- **核心字段**：`center`（双环核心）、`stages`（3–4 个阶段，每张带纯色标题栏 `label` + 右标 `tag` + 多条 `items` 列表）、`links`（顺时针外弧及胶囊关系标签 `label`）、`guardrails`（底部 1–3 张前提约束卡 + `guardrail_title`）。
