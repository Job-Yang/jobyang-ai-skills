---
schema: personal-context/v1
entity: me
type: self
layer: L3
domain: health
confidence: high
source: declared
freshness: stable
updated: 2026-10-22
review_cycle: 180d
audience: local
---

# 健康结论（L3，本地；逐次确认、用完不留）

> 本文件只做信息组织，**不做诊断、不给治疗剂量**；医学判断以医生为准。
> 这是只存在你电脑上的个人记录，不是诊断。云端宿主逐次确认后才暴露，用后清理会话记忆。
> **本地授权门**：先有根目录 `CONSENT-health.md`（本人显式选 full/facts_only/index_only/off），
> 本分片才被读取/结构化使用；未授权时本地也不输出结构化健康。撤回不删历史，只停后续记录。
> **详略分层**：这里只放做判断要用的结论；具体数值和历年变化在 `journal/health-metrics.md`，问到才读。

## 授权状态指引
- 首次进入健康任务时，由本人显式选择四档之一后才生成 `CONSENT-health.md`；未开启时本节留空。

## 过敏 / 在服药 / 慢病禁忌（最高优先，用药前当次重新确认，不自动给药）
- <例：青霉素过敏；或无>
- 在服药/补剂：<例：或无>
- 慢病/长期禁忌：<例：或无>
- 饮食忌口（与健康相关）：<例：服药期间忌西柚；或无>

## 当前状态（据最新体检，细节见 journal/health-metrics.md）
> 只写需要留意的项和方向（偏高/偏低/阳性），不写数值。例：`- 尿酸：偏高（2026-10-01）`。
- <例：尿酸：偏高；或最新一次体检没有需要留意的项>

## 关注因子（watchlist）
> 只改变呈现重点，不诊断、不因在清单就说有病。三条来源：auto（既往/用药自动关联）、stated（本人明说）、proposed_confirmed（AI 提议经本人确认）。
> 每条：`- <关注项> <analyte> | 来源 auto|stated|proposed_confirmed | 原因 一句话`；AI 未确认的提议先写 `来源 proposed`，不置顶不生效。删一项用 `~~…~~` 或标删除，删后不再自动重加。
- <例：尿酸 ua | 来源 auto | 原因 痛风史继续盯；或留空>

## 结论区（报告结论/医嘱原文全量保留，不改写不压缩）
- 总检结论：<原文照录，或无>
- 医生建议/医嘱：<原文，逐条>
- 异常项（A/B 类，以报告为准）：<或无>
- 复查计划 followup_due: YYYY-MM-DD（到期仅提醒，非诊断）

## 变化里程碑（confirmed 人话注解，declared 才落）
- <例：脂肪肝健身后持续好转（本人确认）；或无>

## 体检原件索引（本地路径，不进 cloud、不进导出正文）
- <例：private/health/2025_checkup.pdf｜XX医院｜2025-xx-xx；或无>

## do-not
- 不要在未问过敏/在服药时给用药建议；不主动全面盘点、不推送监督。
