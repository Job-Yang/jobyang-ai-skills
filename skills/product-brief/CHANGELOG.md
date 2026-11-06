# CHANGELOG

## 0.3.2 — 2026-10-16

- 协同：与 radar/scorecard 一起过端到端交接回归（合成 radar 候选 → scorecard 出卡 → 本包 prd/plan seal+validate 全过冻结信封）；handoff 示例 opc_node=prd 经 `check_handoff.py` 确认无 drift。
- 边界：SKILL 补一句——每日定时由宿主 cron/云电脑拉起，本技能只管产出 prd/plan 与信封契约，不负责调度、不内置 token。
- 保留：验收分档、功能编号连续、弱项验证四件套、宽度区间+置信度三档等上轮强项不动。

## 0.3.1 — 2026-10-16

A/B 盲评差距沉淀（radar/scorecard 不参评，本次只改本包）：

- 修复：`templates/prd.md` 验收写法升级。验收按可靠度分档：第一档"可注入/可回放的系统行为用例 + 频次上下限"（注入 50 个应触发用例全过、20 个应抑制事件 0 触发、误触发 ≤ 3 次/设备/天），用户行为指标降为第二档；反例新增"日志留存完整率 = 100%"这类自证型内部指标（只证明系统记了账，连着用户可感知后果才算数）。
- 修复：功能编号连续性写入模板与 SKILL——F1..Fn 必须连续，断号就地说明原因，说不清按漏号处理（盲评新版 F1→F3 跳 F5 无说明被扣分）。
- 新增：`templates/plan.md`"弱项验证四件套"——上游点名弱项时必给：可测假设（把弱项翻译成具体差异化假设）、证伪指标（阈值+观察周期）、止损动作（证伪后退到什么形态）、最小样本量（样本数门槛代替编造行业转化率）；附护城河低分的完整填好示例。SKILL 执行第 2、5 步同步挂接。
- 保留：宽度区间+置信度三档+低置信动作、engineering-docs 交接判据、不替用户批准计划。

## 0.3.0 — 2026-10-16

- 修复：SKILL.md 自称"版本 0.2.1"与信封 `opc_version: 0.2.0` 自相矛盾。版本口径分离：信封 schema 0.2.0（冻结 artifact_io seal 出）与 kit 版本 0.3.0，文档不再混用（原诊断 P1）。
- 修复：`references/handoff.md` 删除 design/prototype 残留（design-spec 打包示例、"设计还要运行工作台"表述），只保留本节点 prd/plan 两个信封示例与 seal/pack/ingest 命令（原诊断 P2）。
- 新增：`templates/prd.md`"可验证验收"补正反例——反例"用户感到满意/体验流畅"，正例"推送后 30 秒内点击查看详情 ≥ 25%"（原诊断 P2）。
- 新增：`templates/plan.md` 估算补强——区间必须有宽度（宽度超一倍要说明）、置信度三档（高/中/低）、低置信度要写"用什么动作把它变中"（原诊断 P2）。
- 新增：SKILL.md 给"交 engineering-docs"的可操作判据（方案取舍影响工期量级、系统集成/合规、需要 Spike 三种情形）（原诊断 P2）。
- 新增：SKILL.md 与 handoff.md 说明 `scripts/artifact_io.py`、`scripts/scoring-rules.json` 是 vendored 公共信封副本（vendor-manifest 解释），本节点不执行评分、不读权重做计算，消除"背负无关评分代码"的困惑（原诊断 P1）。
- 新增：vendoring 落地（check_vendored.py + vendor-manifest.json）；description 重写为前 50 字自包含；frontmatter 只留 name/description。
