---
schema: personal-context/v1
entity: me
type: self
layer: L1
domain: identity
confidence: high
source: declared
updated: 2026-10-15
review_cycle: 90d
audience: cloud-low
---

# ME · 本人画像梗概（L0/L1 摘要 + 索引）

> 默认投喂层。只放名片级事实与各分片索引；敏感细节在对应 profile/ 分片里，按门禁按需加载。

## 名片（L0）
- 称呼：<怎么称呼我>
- 城市/时区：<城市，可只给时区 Asia/Shanghai>
- 协作语言：中文 / English
- 性别 / 年龄段：<可留空、可只给区间>

## 自我标签（user-declared self-tag，非测量）
> 这是**你自己给我的标签**，方便我快速对齐风格；不是测评、随时可改。
- <例：ENTP、急脾气、选择困难>

## 索引
> 索引只写"哪类信息在哪个文件"，不写里面记了什么——ME.md 会默认带给外部 AI，写进来就跟着出去了。
- 工作与方向 → `profile/work.md`（L1）
- 目标 → `profile/goals.md`（L1~L2）
- 协作/生活偏好 → `profile/preferences.md`（L1~L2）
- 决策风格 → `profile/decisions.md`（L2）
- 身体与作息 → `profile/body.md`（L2）
- 关系网圈层概览 → `network.md`（L2）
- 健康结论 → `profile/health.md`（L3，逐次确认）；体检数值明细 → `journal/health-metrics.md`（问到才读）
- 财务约束 → `profile/finance.md`（L3，逐次确认）
- 重要决定的经过 → `journal/decisions.md`（复盘时才读）
- 各关系人详情 → `entities/`（inner/close/peripheral 三圈）；候选草稿 → `inbox/`
