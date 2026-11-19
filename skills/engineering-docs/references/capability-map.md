# 阶段×能力覆盖

`capability_map` 回答“哪个阶段具有哪类能力，什么能力覆盖多个阶段”。横轴是明确阶段，纵轴是能力类型；不是数值双轴，也不是消息先后或调用图。

## 统一输入

```json
{
  "version": 1,
  "type": "capability_map",
  "meta": {"title": "校验覆盖准备和运行", "subtitle": "横轴阶段，纵轴能力类型；横带为覆盖，—为未声明"},
  "payload": {
    "layout": {"width": 960},
    "stages": [{"id": "prepare", "label": "准备"}, {"id": "operate", "label": "运行"}],
    "categories": [{"id": "rules", "label": "规则能力"}, {"id": "data", "label": "数据能力"}],
    "capabilities": [
      {"id": "validate", "stage": "prepare", "category": "rules", "label": "校验规则", "detail": "发布前核对字段约束"},
      {"id": "fetch", "stage": "operate", "category": "data", "label": "读取数据", "role": "backend"}
    ],
    "shared": [{"id": "audit", "label": "审计记录", "detail": "保留操作者与版本", "stages": ["prepare", "operate"], "role": "security"}]
  }
}
```

执行仍用 `diagram_kit render --input input.json --output diagram.html --formats svg,png`，得到统一 source／scene／HTML／回执与请求格式。没有 draw.io 支持，不把 SVG 冒称原生可编辑对象。

## 布局和边界

- 支持 2–5 个阶段、1–6 种能力类型；所有阶段、类别、能力、共享带使用全局唯一 ID。单个能力显式指定一个 stage 和 category，重复部署实例使用不同 ID，不复制成虚构调用链。
- 正文仍用既有 15／13 字号；紧凑块按实际标题、说明行数增高，阶段列宽按内容需求分配。预分行文本直接绘制，不再二次换行。不会减少节点、截断内容、缩字号或加入结论装饰卡；长而不可断的词拒绝，不拆开标识符。
- 技术文档明确正文宽度时，在 `payload.layout.width` 显式填写逻辑像素预算，例如 960；阶段列按该预算测量、分配，字体保持 15／13。缺省沿用已测的 680 宽度，不能把放大的 680 图当作 960 原生排版；小于 680、非有限值或非数值预算明确拒绝。本配置仅作用于 capability_map，不改变其他图型的几何；顶标和主题尾标仍是现有保留限制。
- 空单元用“—”表示未声明，不推断为“不支持”。空类别也保留；阶段和类别在 scene 中记录真实成员，没有关系边。
- `shared[].stages` 是显式覆盖范围，覆盖带与对应阶段列对齐，没有箭头。非连续范围拒绝，应拆成多个明确覆盖实例，避免把中间未覆盖阶段画成已覆盖；阶段排序仍由 stages 决定。
- 真实调用、消息或数据流另选关系视图；本视图拒绝非空 edges／connections／flows／messages／relations，不把覆盖伪造为有向边，也不静默忽略已声明的关系。
- 分层系统中的局部流程继续用 `free` 的显式分区、对象、真实端点和共享 bar。不要因为存在局部流程就把整个系统改成流程图，也不改变已有输入的固定几何。

能力数不是强制拆图阈值；保留完整事实，在目标正文宽度检查文字、空格点与覆盖范围。列变窄或正文过长时按实际渲染决定是否拆视图，机械检查通过不代表用户已接受。
