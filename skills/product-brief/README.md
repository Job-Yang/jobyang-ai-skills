# 产品需求与计划

把一句需求或已有材料整理成能评审、能验收的 PRD 和执行计划。适合确定 MVP、比较产品平台、拆里程碑；可以独立使用，不需要 iLoop、雷达或评分卡。

[English](./README.en.md)

## 怎么开口

> 用 product-brief 把这个想法整理成 PRD 和计划：做一个面向自由职业者的项目收款提醒工具。先定义最小范围和验收，周期没有依据的地方标为待估。

> 根据这份用户访谈写 MVP 需求。平台已经确定为 Web，请沿用这个决定。

可直接提供描述、附件、访谈、现有产品材料、显式文件路径或评分卡。技能先提取人群、问题、使用场景、资源限制和已确认决定，只追问会改变范围的歧义。

## 核心设计

先说清用户要完成什么，再确定功能。每个功能使用稳定的 F 标识，写出触发条件、预期结果和可验证的验收条件，便于设计、技术方案和测试沿用。

PRD 负责产品范围，计划负责交付安排。两份文件相互引用，避免计划遗漏需求，也避免凭空多出功能。计划会区分前置依赖、可并行工作和合流条件，估算注明依据和不确定性。

平台未定时给出推荐及取舍；用户已决定时沿用。技术架构需要深入讨论或要画界面时，可以把产物交给相应技能，但完成当前 PRD 和计划不要求安装其他技能。

## 会拿到什么

| 文件 | 内容 |
| --- | --- |
| `prd-<topic>.md` | 问题、人群、旅程、功能范围、验收、平台、成功指标与未决项 |
| `plan-<topic>.md` | 里程碑、交付物、依赖与并行安排、估算依据、资源和范围调整 |

直接输入不要求上游文件。两份文件使用同一个主题，计划可以引用本次 PRD。未知收益、工期和指标写为假设或待测目标，不伪造用户确认。

交付计划不会自动触发编码或发布；已获得的开工授权会明确记录，用户仍决定下一步。

## 安装与运行要求

把完整目录复制到 `~/.trae/skills/product-brief/` 或宿主规定的技能目录。成文只需要 Agent 能读取材料和输出文本。

Python 3.9+ 用于封装、校验和打包，只有标准库依赖。没有 Python 时，按包内交接规范输出完整 Markdown，标注尚未机器校验；没有文件能力时输出完整代码块。

## 文件怎么交接

Agent 按 [PRD 模板](./templates/prd.md) 和 [计划模板](./templates/plan.md) 填好正文后，从技能目录执行：

```bash
python3 scripts/artifact_io.py seal --input prd-body.md --node prd --kind prd --topic example-product --producer standalone --out prd-example-product.md
python3 scripts/artifact_io.py seal --input plan-body.md --node prd --kind plan --topic example-product --upstream prd-example-product.md --out plan-example-product.md
python3 scripts/artifact_io.py pack --input prd-example-product.md plan-example-product.md --out product-result.zip
python3 scripts/artifact_io.py ingest --input product-result.zip --output-root ./received
```

`prd-body.md` 和 `plan-body.md` 是填好的正文，不能拿空模板冒充完整需求。实际任务使用调用方指定的产物目录。

包内 [handoff.md](./references/handoff.md)、`scripts/artifact_io.py` 和共享规则文件一起提供 `opc-artifact/v1` 交接能力。独立使用不需要安装 OPC；新导入仍为待人审，同名异内容拒绝覆盖。格式通过也不代表范围合理或需求已经批准。

明确进入 OPC 时，技能复用它传入的材料、输出位置和审批记录，不重新开启一轮产品澄清。其他情况下，只完成当前请求。

## Agent 入口

[SKILL.md](./SKILL.md) 包含执行规则。两份模板提供正文骨架，交接脚本只处理文件，不替模型生成产品判断。
