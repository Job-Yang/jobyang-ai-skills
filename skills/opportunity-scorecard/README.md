# 机会评分卡

判断一个产品想法值不值得继续验证。直接给一句想法、已有研究或雷达候选都可以，不需要先跑雷达，也不依赖 iLoop。

[English](./README.en.md)

## 怎么开口

> 用 opportunity-scorecard 评估这个想法：为独立咨询师整理客户访谈并生成可追溯的需求摘要。预算和已有材料如下，请先取证，再给评分和主要风险。

> 这份机会清单里选第二条，评估是否值得做一次付费意愿实验。缺证据的地方请明确标出来。

输入最好包含目标用户、问题、产品形态、市场、收费方式、已有替代品及资源限制。不完整也可以开始，只补会影响判断的缺口。

## 为什么分成模型和脚本

模型负责读证据、判断前提、逐维给分；脚本负责检查输入、计算综合分、确定档位和生成 Markdown。每一维为什么得到这个分可以追溯，计算结果也可以复算。

先确认默认个人产品量表是否适合本次决策。若重要维度与实际资源、成功标准无关，就直接给定性评估；不把不适用项记成低分，也不临时换权重。维度相关但缺证据时，仍按原量表明确暂评及未知，不能把资料少当成不适用。

量表适用时，评分分为三层：

- **前提检查**：价值主张自相矛盾、依赖无法满足的前提，或目标市场可证明为空时，结论为 reject。
- **十维评分**：考察痛点、变现、单位经济、个人交付、分发、护城河、趋势、可验证性、时机及 AI 原生契合度。离钱近、单位经济和护城河权重为 1.5，其余为 1.0，权重和为 11.5。
- **非共识复看**：综合分不足 6.5，但有具体、可证伪的判断及认知盲点说明时，标为黑马候选，交人复看。前提不成立时不标黑马。

| 综合分 | 结论 | 含义 |
| --- | --- | --- |
| ≥ 6.5 | validate | 值得开展真实验证 |
| ≥ 5.0 且 < 6.5 | refine | 先补强薄弱环节 |
| ≥ 3.5 且 < 5.0 | caution | 谨慎推进 |
| < 3.5 | reject | 暂不建议直接投入开发，说明可否先补证 |

这是面向个人开发者的默认尺子，不是成功概率。脚本能保证计算按规则执行，不能证明证据真实，也不能替代访谈、付费实验或实际经营。

## 会拿到什么

- `_scoring-<topic>.json`：原始逐维分数、证据、前提判断和非共识说明。
- `assess-<topic>.md`：综合分、档位、黑马标记、逐维依据和主要问题。
- 需要跨环境交接时，提供同时包含这两个文件的 ZIP。

量表不适用或关键适用条件待确认时，改交付 `evaluation-<topic>.md`，包含实际决策建议、证据及反证、成本收益、关键未知和验证条件，不含默认综合分。它可以直接作为文件搬运；当前数值卡校验与导入工具不接收这种材料。OPC 要求标准卡时，应先处理量表不适配，不自动推进。

技能只完成评估，不自动写 PRD、删掉候选或替用户作投资决定。

## 运行要求与可运行样例

数值评分需要 Python 3.9+，只用标准库；定性评估不需要评分脚本。证据可来自用户材料或宿主检索工具；没有网络时写清材料边界。量表适用但没有 Python 时交付完整评分 JSON 和定性分析，标为待复算，不手算后声称通过。

把完整目录复制到 `~/.trae/skills/opportunity-scorecard/`，或其他宿主的技能目录。以下命令从技能目录执行：

```bash
python3 scripts/score.py --input examples/scoring.synthetic.json --out assess-synthetic-example.md --producer standalone
python3 scripts/artifact_io.py validate --input assess-synthetic-example.md
python3 scripts/artifact_io.py pack --input assess-synthetic-example.md --scoring examples/scoring.synthetic.json --out scorecard-result.zip
python3 scripts/artifact_io.py ingest --input scorecard-result.zip --output-root ./received
```

样例十维均为 6.75，证据全部明确标为合成假设，仅用于验证脚本和交接。真实任务由 Agent 填写对应 JSON，并把输出写到调用方指定的位置。`--stdout` 可替代 `--out`，将评分卡直接交给宿主保存。

## 交接与文件设计

[SKILL.md](./SKILL.md) 定义取证和输入结构，[scoring-method.md](./references/scoring-method.md) 解释判据，`scripts/score.py` 是数值规则的来源。[handoff.md](./references/handoff.md) 与 `scripts/artifact_io.py` 负责校验和搬运；`scripts/scoring-rules.json` 从评分内核生成，不另行维护一套权重。

`opc-artifact/v1` 是随包提供的交接格式。独立导入只需显式给出 `--output-root`，不用访问 iLoop。新导入保持待人审，同名异内容拒绝覆盖。

只有用户明确进入 OPC 时，才沿用它的输入、审批和节点编排；单独使用不会启动整条流程。
