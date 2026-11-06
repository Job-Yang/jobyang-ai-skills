# 信息图 JSON Schema 与布局选型

`render_infographic.py` 只认一份结构化 JSON。它解决的是「多框、多标签、术语/英文原词必须清晰准确」的那类图——
这些图**不要**用文生图（必糊字）。抽象比喻/场景插画才走文生图，见 `prompt-guide.md`。

## 1. 先选布局（按内容的逻辑形态，不按章节数硬凑）

| 内容逻辑 | layout | 典型场景 |
|---|---|---|
| 有先后顺序的步骤链、流水线、生命周期 | `pipeline` | 一次 API 调用的 7 步、请求链路、训练→推理 |
| 同类并列的 2~3 个阶段/方案/派系，要并排讲差异 | `columns` | 预训练/微调/RLHF、三种部署方式 |
| 两个阶段或两个对象对照，各带若干属性 | `two_stage` | Prefill vs Decode、训练 vs 推理 |
| 一个判断，核心是「失衡/追不上/A 大于 B」的对比 | `metaphor` | AI 写得快、人看得慢（文字少、留白大） |
| 多个维度上横向比较 2~3 个对象（表格化差异） | `compare` | 三种量化方案在多个维度上的好坏 |
| 一个中心概念，向外辐射多条要点 | `radial` | 一个机制的 5 个性质、一个方法的 4 个前提 |

选不出来时默认 `pipeline`（过程）或 `columns`（并列）。**一张图只讲一件事**；内容超过 7 个步骤或 4 列，拆成两张。

## 2. 公共字段

```jsonc
{
  "layout": "pipeline",        // 必填，见上表
  "kicker": "可选的小标签（章节归属）",
  "title": "必填，图的大标题，一句话点题",
  "subtitle": "可选，一句补充，说明这张图到底要看什么",
  "footer": "可选，右下角来源/署名，建议放文章名·章节",
  "palette": { },              // 可选，覆盖默认配色，见第 5 节
  "data": { /* 布局专属，见第 3 节 */ }
}
```

- 所有上屏文字都在 JSON 里逐字给定。**术语、英文原词、数字必须和原文一致**，脚本原样输出，不做翻译、不做纠正。
- 长度纪律：`title` ≤ 约 20 字；每张卡片 `title` ≤ 12 字、`desc` ≤ 30 字；compare 单元格 ≤ 24 字。超了脚本会折行，但超太多会挤——先压缩文案，不是调字号硬塞。

## 3. 各布局 data 字段

### pipeline（步骤链）

```jsonc
"data": {
  "icons": ["doc","db","wave","blocks","bars","loop","check_doc"], // 可选，每步一个，缺省 doc
  "steps": [
    {"title": "步骤名（可含英文 Tokenizer）", "desc": "一两句说明"}
  ],                       // 2~9 步
  "span_labels": [          // 可选，在流水线下方画分段括号
    {"from": 0, "to": 3, "label": "Prefill → TTFT 首字延迟", "color": "blue"},
    {"from": 4, "to": 6, "label": "Decode → TPS 吐字速度", "color": "accent"}
  ]
}
```
可用 icon：`doc / db / wave / blocks / bars / loop / check_doc / tag / brain / chip`。

### columns（2~3 栏）

```jsonc
"data": {
  "columns": [
    {"title": "Pretraining\n预训练", "subtitle": "喂海量文本",
     "scene": "可选的中部场景说明", "bullets": ["要点1","要点2","要点3"]}
  ],
  "chain": ["阶段一称呼","阶段二称呼","阶段三称呼"]   // 可选，底部演进链
}
```

### two_stage（两段对照）

```jsonc
"data": {
  "vs_label": "VS",        // 可选，中间圆形标记文字
  "stages": [
    {"title": "训练", "subtitle": "Training",
     "rows": [{"k": "显存", "v": "要保留中间激活，约为推理 4–8 倍"}, {"k": "计算图", "v": "建图"}]},
    {"title": "推理", "subtitle": "Inference",
     "rows": [{"k": "显存", "v": "算完即弃"}, {"k": "计算图", "v": "torch.no_grad()"}]}
  ]
}
```

### metaphor（失衡/对比比喻，确定性几何版）

```jsonc
"data": {
  "point": "这张图要读者接受的那一个判断",
  "note": "可选的一句补充",
  "left_big": "AI 产出", "left_big_sub": "体量大、还在变快",
  "right_small": "人能看懂", "right_small_sub": "带宽就这么多",
  "gap_label": "差距在拉大"
}
```
> 若你要的是更具象的场景插画（机器人追代码山那种），别用这个布局，走 `prompt-guide.md` 的文生图后端。

### compare（多维对照表）

```jsonc
"data": {
  "corner": "对比维度",
  "columns": ["方案 A", "方案 B", "方案 C"],
  "rows": [
    {"label": "精度", "values": ["高", {"text": "中", "tone": "hl"}, {"text": "低", "tone": "bad"}]},
    {"label": "成本", "values": [{"text": "高", "tone": "bad"}, "中", {"text": "低", "tone": "good"}]}
  ]
}
```
`values` 每项是纯字符串，或 `{"text": "...", "tone": "good|bad|hl"}`（绿/红/橙语义色）。行数与列数脚本会校验。

### radial（中心辐射）

```jsonc
"data": { "center": "中心概念", "nodes": ["要点1","要点2","要点3","要点4"] }  // 3~6 个
```

## 4. 运行

```bash
python3 scripts/render_infographic.py examples/api-7steps.json -o out.svg          # 只出 SVG
python3 scripts/render_infographic.py spec.json -o out.svg --png                    # 再出一张 2x PNG
python3 scripts/render_infographic.py spec.json -o out.svg --validate-only          # 只校验 schema
```
- 画布固定 1600×1067（约 3:2，横版，贴飞书正文合适）。
- PNG 转换优先 `rsvg-convert`，没有则回退本机 Chrome headless；两者都没有时只出 SVG 并告警（退出码 3 仅在显式要 PNG 且失败时出现，SVG 始终可用）。
- 退出码：0 成功；1 参数/IO；2 schema 错；3 PNG 失败（SVG 已生成）。

## 5. 配色语义（可被 spec.palette 覆盖键名）

默认键：`accent`(橙=高亮/关键)、`blue`(方法/理性)、`red`(问题/风险)、`green`(通过/安全)、
`ink/ink_soft/line/bg/bg_soft/card`。语义色不要乱用：红色只给「被排除/风险」，绿色只给「通过/坐实」，
橙色给「真正想让读者看的那一处」。整套默认无紫（`purple` 仅第四对象兜底）。

完整样例见 `examples/`：`api-7steps.json`(pipeline)、`training-3stages.json`(columns)、`understanding-debt.json`(metaphor)。
