---
schema: personal-context/v1
entity: me
type: self
layer: L1
domain: relations
confidence: high
source: declared
updated: 2026-10-15
review_cycle: 180d
audience: cloud-low
---

# 关系边集合

> 10 词：self / spouse_of / partner_of / parent_of / child_of / sibling_of / lives_with / knows / works_with / related_to。
> 对称关系写一条、读取双向展开；有向关系必须有方向。
> 加他人后再取消注释下面的示例边；to 必须对应 entities/<id>.md，或标 external: true。
> 读取这些边时只过 L0–L4 / audience 门禁，本技能不做他人认证。

<!--
- from: me
  type: spouse_of
  to: spouse-li
  direction: symmetric
  since: 2020-05-01
  until: null
  confidence: high
  source: declared
-->
