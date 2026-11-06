---
schema: personal-context/v1
entity: me
type: self
layer: L3
domain: health
source: declared
updated: 2026-10-31
audience: local
---

# 体检指标明细（过程层，L3，只在本机）

> 做判断时默认不带；问具体数值、"这几年怎么变的"时才读。结论写在 `profile/health.md` 的「当前状态」。
> 新体检：先把「最新关键指标」整体追加到「历史快照」，再写新的最新值（只增不改）。

## 最新关键指标（主表永远是最新权威值；只跟踪决策相关一小撮）
> **一项一行，不合并字段**。列：指标 | 数值 | 单位 | 本院参考区间 | 日期 | 机构 | 方法 | 标本/采血条件 | provenance | confidence。
> 指标使用 canonical code（见 `references/08-health-extraction.md`）；数值/单位/参考区间必须原样抄报告。定性结果写 `阴性 / ± / + / ++ / 阳性`，不要把它改成 0/1。
> provenance: imported_report | imported_ocr | declared_interview | doctor_diagnosed；confidence: confirmed | single_measurement | inferred。
- 指标 ldl_c | 数值 <v> | 单位 mmol/L | 参考 <本院原文> | 日期 YYYY-MM-DD | 机构 <院> | 方法 <报告未标就留空> | 标本 血清 | 采血条件 空腹 | provenance imported_report | confidence confirmed

## 历史快照（append-only，只增不改不覆盖；更新前先把上一份整体追加到这里）
> 每个历史点也必须使用与“最新关键指标”相同的**一项一行**格式，并带 日期/机构/方法/标本/采血条件/provenance/confidence。
> 趋势标签读时从规范时间点派生，不写死箭头；只有条件可比时才给方向。
