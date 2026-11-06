---
name: product-brief
description: "把一句需求或评分卡转成可验收的 PRD 与执行计划。用户要写产品需求、界定 MVP、拆里程碑（如「帮我把这个需求写成 PRD」）时调用；不打分、不编码、不替用户批准。"
---

# 产品需求与计划

版本口径（2026-10-16 起）：信封 schema 版本 0.2.0，由冻结的 `scripts/artifact_io.py` seal 出，代表信封结构；本 kit（技能包）版本 0.3.1，见 CHANGELOG.md。过去本文档自称"版本 0.2.1"的写法已废弃，不再与信封版本混用。先读包内 `references/handoff.md`。本技能只写产品产物；不自动编码、不自动发布，也不替用户批准计划。

关于包内 `scripts/artifact_io.py` 和 `scripts/scoring-rules.json`：它们是 opc-envelope 0.2.0 的 vendored 公共副本（见 `scripts/vendor-manifest.json`），作用只是给本节点的 prd/plan 产物做信封校验、打包和导入。本节点**不执行评分**，不读 scoring-rules.json 的权重做计算；需要评分时用 opportunity-scorecard 包。

## 输入与范围

接受直接描述、附件、显式文件路径或已批准的上游工件。主题明确即可开始，不强迫独立用户先跑雷达或评分。OPC 模式由当前 flow 明确指定，复用其输入、审批和输出目录；不重复询问已确认事项。

先提取目标人群、待解决问题、使用频率、关键场景、资源限制和已有决定。把事实、用户确认与假设分开。缺输入时先完成可独立推进的部分，只询问会改变实现范围的关键歧义。

## 执行

1. **界定问题。** 写清谁在什么场景遇到什么障碍、目前怎么解决、成功后如何变化。避免从功能清单倒推问题。
2. **明确 MVP。** 给每个功能稳定的 F 标识（F1、F2……编号必须连续，断号就地说明），记录触发条件、预期结果和可验证的验收条件。验收优先写"可注入/可回放的系统行为用例 + 频次上下限"（如"注入 20 个应抑制事件 0 触发"），用户行为指标次之；"日志留存完整率=100%"这类自证型内部指标不当验收，除非连着用户可感知后果。列出 out-of-scope，核心旅程只保留证明目标所必需的能力。
3. **提出平台建议。** 结合用户、使用频率和资源给推荐与替代方案，说明利弊。用户已决定则复用；不能擅自更换 Web、移动端、桌面端等形态。没有依据的收益、周期和流量数字标为待测目标。
4. **整理 PRD。** 使用 `templates/prd.md` 的字段，不机械套未相关章节。数据模型保持产品层面（有哪些实体、各是什么），不写存储选型、接口契约、并发方案。"需要展开时交 engineering-docs"的可操作判据：出现下列任一情况，技术展开交该技能——① 要在两个技术方案间取舍（自建 vs 第三方、是否迁移旧系统），且结果影响工期量级；② 涉及系统间集成、数据迁移或合规约束；③ 计划里必须先做技术探查（Spike）才能估算。只是把需求翻译成页面字段和流程步骤的，留在本 PRD 内。
5. **整理计划。** 使用 `templates/plan.md`。写里程碑、依赖、估算依据与不确定区间、交付物、验收责任及回退范围。上游点名的弱项（如评分卡低维）必须按 plan.md"弱项验证四件套"落地：可测假设、证伪指标、止损动作、最小样本量（用样本数门槛，不编行业转化率）。设计和技术研究可以并行，不默认所有工作串行。
6. **检查并交付。** 每个 F 都有验收，计划引用的 F 存在。沿核心旅程检查会影响用户结果的输入规则：必填、格式、单位与精度、边界值、无效输入；已明确的写入验收，缺依据的列为待决或明确建议，不替用户拍板。只展开本任务相关项，局部改动不强加整套产品规划。未决问题要有解决方式。输出 PRD 与计划，均为待人审。完整计划不是开工授权，已得到的用户授权则明确记录。

如果需要外部信息才能选择方案，按需复用 outside-view；现有证据足够则直接工作。没有该技能也不能伪造行业共识或阻塞本地成文。

## 输出

`prd-<topic>.md` 与 `plan-<topic>.md` 使用同一 topic。两者 `opc_node: prd`，分别 `artifact_kind: prd`、`artifact_kind: plan`。直接输入的 upstream 为 null；计划可以引用本次 PRD。保留确认记录，不在机器自生成的头里写 approved。

正文完成后，用包内脚本封装与校验：

```bash
python3 scripts/artifact_io.py seal --input prd-body.md --node prd --kind prd --topic example-product --producer standalone --out prd-example-product.md
python3 scripts/artifact_io.py seal --input plan-body.md --node prd --kind plan --topic example-product --upstream prd-example-product.md --out plan-example-product.md
python3 scripts/artifact_io.py pack --input prd-example-product.md plan-example-product.md --out result.zip
```

无 Python 时按 `references/handoff.md` 手工输出完整信封与正文，注明结构尚未机验。示例值不能冒充真实调研、工期或用户确认。

## 与相邻能力的边界

以下技能均为可选的后续能力，不是本技能的前置依赖。未安装时仍独立交付 PRD 和计划，展开到界面或工程实现之外的问题则标明交接范围。

- opportunity-scorecard 判断潜力，本技能定义交付范围；不重复打分。
- style-compass 负责界面结构、交互与视觉；本技能提供稳定需求和旅程，允许设计反馈修订。
- engineering-docs 负责工程取舍与技术方案；交接判据见执行第 4 步。方案改变工作量后更新计划版本及变更原因。
- 流程或用户决定下一步；本技能不强制生成新会话、调用下游或操作项目审批。

## 维护说明

本包自带 opc-envelope 0.2.0 公共文件副本（`scripts/artifact_io.py`、`scripts/scoring-rules.json`，见 `scripts/vendor-manifest.json`），本轮冻结不改内容。发布前跑 `python3 scripts/check_vendored.py` 自检；与其他流水线包并排时跑 `python3 scripts/check_vendored.py --drift <各技能根>` 确认无漂移，跑 `opportunity-radar/scripts/check_handoff.py <三包根>` 确认 handoff 示例 opc_node 无 drift。

每日定时由宿主 cron/云电脑拉起本技能；本技能只管产出 prd/plan 与信封契约，不负责调度、不内置 token、不自动发布。
