<!-- 虚构示例数据，非真人。 -->
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

# 关系边集合（张三，虚构）

- from: me
  type: spouse_of
  to: spouse-li
  direction: symmetric
  since: 2020-05-01
  until: null
  confidence: high
  source: declared

- from: me
  type: parent_of
  to: child-1
  direction: directed
  since: 2018-05-01
  until: null
  confidence: high
  source: declared

- from: spouse-li
  type: parent_of
  to: child-1
  direction: directed
  since: 2018-05-01
  until: null
  confidence: high
  source: declared

- from: me
  type: works_with
  to: colleague-wang
  direction: symmetric
  since: 2023-03-01
  until: null
  confidence: med
  source: observed

- from: me
  type: knows
  to: barber-liu
  direction: directed
  since: 2024-01-01
  until: null
  confidence: low
  source: observed
