---
name: product-brief
description: "把一句需求、已有材料或机会评分卡转成可验收的 PRD 和执行计划。用户要写产品需求、界定 MVP、做平台取舍或拆里程碑时调用。OPC 内复用已确认输入，独立调用不要求先评分。"
license: MIT
---

# 产品需求与计划

版本 0.2.1。先读包内 `references/handoff.md`。本技能只写产品产物；不自动编码、不自动发布，也不替用户批准计划。

## 输入与范围

接受直接描述、附件、显式文件路径或已批准的上游工件。主题明确即可开始，不强迫独立用户先跑雷达或评分。OPC 模式由当前 flow 明确指定，复用其输入、审批和输出目录；不重复询问已确认事项。

先提取目标人群、待解决问题、使用频率、关键场景、资源限制和已有决定。把事实、用户确认与假设分开。缺输入时先完成可独立推进的部分，只询问会改变实现范围的关键歧义。

## 执行

1. **界定问题。** 写清谁在什么场景遇到什么障碍、目前怎么解决、成功后如何变化。避免从功能清单倒推问题。
2. **明确 MVP。** 给每个功能稳定的 F 标识，记录触发条件、预期结果和可验证的验收条件。列出 out-of-scope，核心旅程只保留证明目标所必需的能力。
3. **提出平台建议。** 结合用户、使用频率和资源给推荐与替代方案，说明利弊。用户已决定则复用；不能擅自更换 Web、移动端、桌面端等形态。没有依据的收益、周期和流量数字标为待测目标。
4. **整理 PRD。** 使用 `templates/prd.md` 的字段，不机械套未相关章节。数据模型保持产品层面；技术选型和架构需要展开时交 engineering-docs。
5. **整理计划。** 使用 `templates/plan.md`。写里程碑、依赖、估算依据与不确定区间、交付物、验收责任及回退范围。设计和技术研究可以并行，不默认所有工作串行。
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
- engineering-docs 负责工程取舍与技术方案；方案改变工作量后更新计划版本及变更原因。
- 流程或用户决定下一步；本技能不强制生成新会话、调用下游或操作项目审批。
