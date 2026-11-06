---
name: "opportunity-scorecard"
description: "为产品想法取证并评分，判断值不值得继续验证。用户要评判想法、打分或判断机会（如「帮我给这个想法打个分」「这个机会值不值得做」）时调用；不发现机会、不写 PRD。综合分一律脚本机器产出。"
---

# Opportunity Scorecard · 机会评估

先读包内 `references/handoff.md`。数值评分需要 Python 3.9+，无第三方依赖。独立调用不要求雷达文件，也不自动启动 PRD。

版本口径（2026-10-16 起）：信封 schema 版本 0.2.0，由冻结的 `scripts/artifact_io.py` seal 出，代表信封结构；本 kit（技能包）版本 0.3.0，见 CHANGELOG.md。score.py 渲染卡片时信封写 0.2.0，不再用旧的 0.2.2——信封版本和 kit 版本不是一回事。

## 这个 kit 是什么

评估一个机会（雷达候选，或用户直给的一句话），把证据转成当前可执行的投入建议。默认十维量表面向个人产品；先判断适用性，再选择数值评分或定性评估。

> **AI 干语义活，脚本干确定性活。** AI 负责取证、判地基门、逐维给分、写申辩；`scripts/score.py` 负责校验契约、算加权综合分、定档、判黑马、渲染成卡。**综合分/verdict/dark_horse 一律脚本产出，禁止手心算**——这三个是下游机器读的接口。
> **它是自包含、可移植的**：支持用户材料或联网取证。独立数值评分显式使用 `--out` 或 `--stdout`，不因宿主恰有 iLoop 环境变量改变模式。量表适用但无 Python 时交付完整 JSON、等待本地复算。
> **输入**：雷达候选 `radar-<date>.md` 里的某条，或用户直给的机会描述。
> **输出**：量表适用时为 `assess-<topic>.md` 评分卡；不适用时为 `evaluation-<topic>.md` 定性评估。

## 立身前提

**既守地板，又不扼杀天花板。** 逻辑不成立的机会救不活（地基门否掉）；但被低估、踩中时机的黑马别被机械分一票否（逃生舱救回交人复看）。**只排序不淘汰，最后人拍板。**

## 只做 / 禁止

- **只做**：取证、评估前提与投入建议；量表适用时逐维打分、写非共识申辩、跑脚本出卡。
- **禁止**：改代码；跳过取证拍脑袋给分；增删或改名那 10 个维度；把地基门否决的机会硬洗成高分；擅自删除命中硬门的机会（标注即可，去留人定）；手写综合分/verdict/dark_horse。

## 执行步骤（不可跳过，顺序照走）

**第 0 步 · 定 topic、决策范围与量表适用性**：给机会起小写 slug，上游有就沿用。确认用户是在决定补证、小试点、投入开发还是扩大投入；记录已知团队、资源和成功标准，不补造人数。对照 `references/scoring-method.md` 判断十维能否回答本次决策，正文说明理由。

- **适用**：个人产品的交付、经营和技术适应性确实影响本次决定，按下列步骤出卡。缺成本、需求或趋势证据属于未知，不能仅因资料少就跳过评分。
- **不适用或关键适用条件待确认**：重要维度与实际成功标准无关，或给分会惩罚用户已明确且合理的组织、产品约束。完成第 1 步后转入「定性评估」，不执行第 2～4 步，不算默认总分。不能靠卡后免责声明补救，也不临时删维度、改权重或拿 0／中间分填不适用项。

团队人数、是否使用 AI 都不能单独决定成败或适用性；要解释维度与当前决策的关系。用户明确只想看默认个人产品视角时，可以给该视角的卡，但不能把它充当实际组织决策的结论。

**第 1 步 · 地基层硬门（极窄，命中即否）** —— 判据见 `references/scoring-method.md`：只问"这命题本身立不立得住"。三条任一命中 `pass=false`：价值主张自相矛盾 / 依赖做不到的前提 / 目标市场可证明为空。⚠️"一个人扛不动""要牌照""变现绕远"是**程度问题不进这层**，留到潜力层扣分。

**第 2 步 · 潜力层 10 维取证打分** —— 维度/权重/判据/锚点见 `references/scoring-method.md`：对每维**先取证再给分，无证据不给分**。取证复用手头联网能力（去 Reddit、G2/App Store 差评、PH、Trends 现拉），不打包爬虫。每维证据落成"链接+原话/数据"。取不到真证据的维度：继续找，或写清"暂无公开证据，属假设"并压低分——**不许留空/TODO/占位**（脚本会打回）。

**第 3 步 · 非共识逃生舱**：写一句"为什么它看起来平庸/疯狂，但其实踩中了别人没看到的点"。合格申辩 = **一个可被证伪的具体判断(claim) + 别人为什么没看到(blindspot)**，两者都要。空泛的"我觉得会火"不算，留空即可。

**第 4 步 · 收敛成 JSON，交脚本出卡**：填成下面的 schema，落成 `_scoring-<topic>.json`，然后跑脚本（见「怎么跑」）。

**交付先回答本次决策。** 用一句话写明“建议做哪一级行动、暂缓什么、什么证据会改变建议”，再附脚本原样生成的卡。低分若主要来自缺资料，应明确它是保守暂评，不代表已证明机会差；补证或低成本试验可以成立。分档标签、诊断和开头建议若看似冲突，解释各自针对的行动，不能让用户靠后文猜。评分维度、权重和阈值不变。

## 定性评估

交付 `evaluation-<topic>.md`，首段说明本次建议及默认量表不适用或待确认的原因。围绕实际决策写：已知证据及反证、前提是否成立、相关成本与收益、关键未知、下一步验证及改变建议的条件。可复核的经营算式照常计算，建议的试验门槛标为建议，不冒称已获用户确认。没有支撑就保留未知，不另造一套分数。

此文件是独立评估材料，不含默认综合分、verdict 或 dark_horse，也不伪装成 `opc-artifact/v1` 的 assess 卡。可随来源文件直接搬运；现有数值卡的 validate/pack/ingest 不接收它。已进入 OPC 且节点要求标准评分卡时，将量表不适配及待决条件交回适配器，保留材料，等待调整输入或确认适用量表；不得伪造合规卡或自动推进。

## 输出 JSON schema（score.py 的输入契约）

```json
{
  "topic": "watch-sedentary",
  "one_liner": "给久坐白领，用 Watch 数据在压力/久坐时给一次恰到好处的干预提醒",
  "upstream": "radar-2026-09-20.md",
  "profile": {
    "form": "iOS + Apple Watch", "endpoint": "iPhone",
    "market": "出海优先", "monetization": "免费+订阅",
    "competitors": ["Bend：拉伸提醒，弱在无生理数据", "Stretchly：桌面端，不懂身体状态"]
  },
  "foundation": { "pass": true, "reason": "命题成立：Watch 生理数据+及时干预无逻辑矛盾" },
  "dimensions": [
    { "name": "痛点强度", "score": 8, "evidence": "reddit.com/... 「wish my watch told me to move」高频抱怨" },
    { "name": "离钱近", "score": 5, "evidence": "..." },
    { "name": "单位经济健康度", "score": 7, "evidence": "..." },
    { "name": "一人可交付", "score": 7, "evidence": "..." },
    { "name": "自然分发", "score": 6, "evidence": "..." },
    { "name": "护城河", "score": 5, "evidence": "..." },
    { "name": "市场趋势", "score": 7, "evidence": "..." },
    { "name": "可验证性", "score": 8, "evidence": "..." },
    { "name": "时机(Why now)", "score": 7, "evidence": "..." },
    { "name": "AI-native契合度", "score": 6, "evidence": "..." }
  ],
  "diagnosis": "强在痛点/可验证；凹陷在护城河、离钱近；补强方向：靠专有健康数据做个性化干预。",
  "rebuttal": { "claim": "", "blindspot": "" }
}
```
- `dimensions` 必须正好 10 条、名称与 schema 完全一致（多/少/改名都被脚本打回）。
- `evidence` 每条必填，禁止空/TODO/占位。`diagnosis` 可空（脚本按最高/最低分兜底）。`rebuttal` 无非共识点则两字段留空字符串。

## 怎么跑

**① iLoop 流程内**（注入 `ILOOP_DATA_ROOT`）——落盘 `assess-<topic>.md`：
```bash
bash "$ILOOP_HELPER" pattern opc.product-pipeline:score.py -- --input "$ILOOP_DATA_ROOT/analysis/opc.product-pipeline/_scoring-<topic>.json"
```

**② 独立/别的 harness（Mira 等）**——把渲染好的卡打到 stdout，让那个环境自己存：
```bash
python3 scripts/score.py --input _scoring-<topic>.json --stdout
python3 scripts/score.py --input _scoring-<topic>.json --out assess-<topic>.md --producer mira
```

**③ 量表适用但没有 Python**——只交付完整 JSON 和定性分析，标“待本地复算”。以下公式供解释，不授权模型输出已验证的计算结果：
> 综合分 = Σ(维度分 × 权重) ÷ 11.5。权重：离钱近/单位经济健康度/护城河 = 1.5，其余 7 维（含时机、AI-native）= 1.0。
> 四档：≥6.5 validate🟢 · ≥5.0 且 <6.5 refine🟡 · ≥3.5 且 <5.0 caution🟠 · <3.5 reject🔴。
> 地基门 pass=false → 直接 reject（否决优先于分数，不给黑马）。
> dark_horse = (地基没否 且 综合分<6.5 且 申辩 claim/blindspot 都填了)。
> 本地 Agent 收到 JSON 后调用 score.py 出卡，再校验和导入；不可把手算标成通过。

## 何时停手升级用户

- 证据不足以支撑打分 → 定向补证或向用户索取材料；雷达可选，不是独立评估的前置依赖。
- 命中地基层硬门 → 标 `pass=false`，但不擅自删除，去留交用户。
- 输入既没有雷达候选、用户也没给机会描述 → 先问，别空跑。

## 诚实边界

- 评估只判"值不值得去验"，**天花板是"值得去验"不是"确定能做"**——分发这种胜负手要真碰市场才知道，最终靠落地页验证拍板。
- 它不做发现（那是雷达）、不做 PRD/设计/编码。

## 目录结构

```
opportunity-scorecard/
├── SKILL.md                    # 本文件：方法论 + JSON 契约 + 怎么跑
├── CHANGELOG.md                # 版本记录
├── references/
│   └── scoring-method.md       # 三层尺子的判据/权重/锚点（可移植方法论）
├── examples/
│   ├── scoring.synthetic.json        # 中性合成样例（全维 6.5）
│   ├── scoring.foundation-reject.json # 边界：地基门命中，分数再高也 reject
│   └── scoring.dark-horse.json        # 边界：机械分低但申辩有形状，dark_horse=true
├── tests/test_scorecard_regression.py # 回归测试（python3 -m unittest discover -s tests -v）
└── scripts/
    ├── score.py                # 确定性打分内核（本包唯一可执行算法）
    ├── artifact_io.py          # opc-envelope 0.2.0 公共副本：校验、整包交接（冻结）
    ├── scoring-rules.json      # opc-envelope 0.2.0 公共副本（冻结）
    ├── check_vendored.py       # 公共副本一致性自检
    └── vendor-manifest.json    # 本包携带的公共副本清单
```
> 评分算法只维护 `scripts/score.py` 的 DIMENSIONS 常量。`scoring-rules.json` 是冻结的公共副本，artifact_io 的交接包复算读它；改 DIMENSIONS 后必须由 canonical 统一重新生成并同步全部 5 个包，不能在本包手改第二份数值（本轮它冻结，不生成）。

`examples/` 都是可运行的合成样例，所有证据均标假设，仅供检查脚本和交接，不能作为市场建议：`scoring.synthetic.json`（中性）、`scoring.foundation-reject.json`（地基门）、`scoring.dark-horse.json`（黑马逃生舱），以及三个对抗样例 `scoring.all-ten.json`（全 10 分不溢出）、`scoring.all-one.json`（全 1 分落 reject）、`scoring.contradictory.json`（维度矛盾+证据复用，验证不崩溃）。打分最小步长 0.5，6.75 这类小数会被脚本打回（见 `references/scoring-method.md`）。

出卡末尾固定带"尺子置信度声明"：权重/档位/地基门/dark_horse 是先验经验判断、非统计显著，composite 只辅助排序——不要把它当数据结论引用。证据被脚本发现"同料复用"或"无链接不可验证措辞"时，卡片会列"证据警告"，需人复核真伪（脚本不判断真伪，只抓结构异常）。

## 维护说明

本包自带 opc-envelope 0.2.0 公共文件副本（`scripts/artifact_io.py`、`scripts/scoring-rules.json`，见 `scripts/vendor-manifest.json`），本轮冻结不改内容。发布前跑 `python3 scripts/check_vendored.py` 和 `python3 -m unittest discover -s tests -v`；与其他流水线包并排时跑 `python3 scripts/check_vendored.py --drift <各技能根>` 确认无漂移。

## 在不同环境怎么跑

- **iLoop 流程内**：由 `opc.product-pipeline.assess` 调用；产物和审批归适配器，下一步归编排。
- **独立数值评分 → 交接回本地**：整个 assess-kit 目录拷过去当 skill。`scripts/score.py --stdout` 跑（它已自动带 `schema/produced_by` 信封；想标产地设 `OPC_PRODUCED_BY=mira`）。交接三步：
  1. 远端**自检**：`python3 scripts/artifact_io.py validate --input assess-<topic>.md`，再用 `pack --input assess-<topic>.md --scoring _scoring-<topic>.json --out result.zip` 带回原始逐维数据。
  2. 拿回本地。
  3. 本地**导入**：`python3 scripts/artifact_io.py ingest --input <文件> --output-root <接收目录>`。按信封生成标准名 `assess-<topic>.md`，写到指定目录，不需要 iLoop。
- 已明确进入 OPC 时，可选用 `bash "$ILOOP_HELPER" pattern opc.product-pipeline:artifact_io.py -- ingest --input <文件>` 接入流程。
- 完整标准见包内 `references/handoff.md`。导入只验证结构和计算，不验证证据真伪；远端审批不自动转换为本地开工许可。
