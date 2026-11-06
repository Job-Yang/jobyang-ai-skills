---
name: haohao-eval
description: 给好好说话（haohao-shuohua）做每日改写打分与 badcase 回归闭环：每天出题盲评、攒病类、过门禁才改规则、变差自动回滚。每天定时跑召回，或要做比稿、比工具、回归测试时用；也接作者在召回文档/会话里的回话（D12 有、开启自动发布、回滚细则等）。不适用：只是写或润色一段中文（那是 haohao-shuohua 本体）。触发词：每日召回、跑召回、召回日报、评测好好说话、比稿、回归测试、BadCase、记录判断、D12 有、D12 没有、开启自动发布、保持影子、暂停发布、回滚细则、接受手工修改、召回现在怎么样；用户说「跑一轮好好说话召回」「今天的召回结果怎么样」时触发。
---

# 好好说话 · 评测与每日召回

这个技能管两件事：每天自动召回，把 `haohao-shuohua` 在新题上犯的错找出来、攒够了再改、改了要验证；另外，需要时做一次性的评测。

召回的标准只有一个：**技能在完整的任务里，有没有把原文改坏，有没有没改好。** 改坏指失真：编了原文没有的东西、丢了信息、改了程度范围模态、术语通俗化、场合错配。没改好指 AI 味还在、新添了病句、没毛病的句子也动了手、正文里自己加了免责说明。分数和正则只当提示，不当结论。

---

## 铁律（每一步都不许破）

1. **保真第一。** 判改坏只看原文和上下文：改写里每条信息都要找得到出处，原文每条信息都要找得到下落。改写得再顺，失真就是改坏了。口语不等于自然。
2. **裁判只核对，不打总分。** 每条问题都要引用原句，交给 `loop.py` 逐字核对，对不上的作废。拿不准就判「不确定」并给出争议片段，不硬判。
3. **评测时不改被测版本。** 改进只写进候选细则；候选冻结以后才改写、才判。判完不许回头改候选、放宽门槛、重试到过为止。
4. **发不发布只看 `loop.py` 算出来的门禁。** 拿不准就不发，不许每天必须发布，不许手动改判或跳步骤。
5. **底线条款只有作者能改。** 自动流程只动 `daily-learning.md`，不碰 `haohao-shuohua` 的技能文件，也不读不写作者的 `style.md`。召回文档是作者的文档，只在最后「每日迭代日志」这一节末尾追加，前面的内容一个字不改。
6. **没跑的步骤写「没跑」。** 不许编结果，不许凭记忆汇总。命令报错就停下，把原始报错写进日报。
7. **材料和凭证守规矩。** 真实材料只用作者明确给的来源，不自动扫描私人文档；个人信息、财务、公司敏感内容不用。凭证靠环境变量或平台密钥注入，不打印，不写进任何文件。
8. **问作者要省着问。** 每天最多 3 条，每条只给一句原文、一句改写、一个是非题；不回就按保守默认处理，流程不等人。

---

## 每日召回

定时任务每天跑一轮，完整步骤和命令在 `references/daily-loop.md`，照着做就行。一轮的骨架：

0. 接上昨天：`loop.py state load` 从状态文档恢复数据，`loop.py doc read` 读作者在召回文档里填的判断和交代，再处理作者在对话里说的。
1. `loop.py start`：记下版本指纹，抽裁判体检题、回归题、干净对照，定今天的目标病灶。
2. 裁判体检：用作者判过的历史样本考裁判，没过就只召回、不出候选。
3. 出题：合成改写题（先有事实清单再有稿）、起草题、针对目标病灶的探针，外加作者给的真实材料。
4. 现用版改写全部题目；有目标病灶时写候选细则，冻结后用候选版改写验证题。
5. 机械检查、打乱匿名、逐份裁判、逐字核对引用。
6. `loop.py decide`：召回入池、算指标、建待判断的题、过门禁、预发布或发布，发布后变差自动回滚。
7. `loop.py report`：生成日报。
8. 收尾：`loop.py doc record` 生成今天的记录，追加到召回文档末尾；`loop.py state dump` 生成新的状态，整篇覆盖写回状态文档，读回来 `state check` 核对。

头 14 天是影子运行：流程全跑，只记录「本来会发布什么」，不真发布。影子期结束时，如果裁判体检稳定、抽查漏判不超过一成，自动切到自动发布，日报里会说一声。

相关细则：出题看 `references/item-sources.md`，判法看 `references/judge-protocol.md`，写候选看 `references/fix-proposal.md`，门禁和发布看 `references/gates-and-release.md`，问作者看 `references/disputes.md`，问题编码看 `references/badcase-taxonomy.md`。

---

## 作者回话时怎么办

作者回话有两个地方：

- **召回文档**：在「每日迭代日志」里把「Dxx 你的判断：＿＿」填上有、没有或跳过，后面可以跟一句为什么；在「你的交代」里加一行就是一条作者说明，删掉一行就作废那一条。这些不用你执行命令，定时任务开跑时 `loop.py doc read` 自动读、自动记。
- **会话里说一句**：照下表执行，执行完把命令输出原样告诉作者。命令都在本技能目录下跑。

数据目录留不住的平台（比如 Mira），数据要先从状态文档接上才能执行下表的命令。所以不在定时任务里的时候，作者的回话只回一句「收到，下次开跑时处理」，别的不做；定时任务开轮前会处理（见 `references/daily-loop.md` 第零步）。

| 作者说 | 执行 |
|---|---|
| 「D12 有」「D12 没有」「D12 跳过」（也认 是/否），可能带一句理由 | `python3 scripts/loop.py disputes answer D12 有 --note "理由原话"`，一次回好几条就逐条执行 |
| 不针对哪道题的交代，比如「感谢信里的客套别删」「技术名词别换」「slogan 要有气势」 | `python3 scripts/loop.py note add "作者原话"`，原话照抄，一句一条；作者点了文体就加 `--文体 感谢信,寄语` |
| 「N003 不算了」「那条作废」 | `python3 scripts/loop.py note drop N003` |
| 丢来一段材料：「这段也改坏了：……」，可能带着他对改写的评价 | 按 `references/item-sources.md` 当真实材料，今天出题时交，来源写「作者回话 日期」；他对改写的评价写进 `作者评价` |
| 「开启自动发布」 | `python3 scripts/loop.py mode auto` |
| 「保持影子」「先别发布」 | `python3 scripts/loop.py mode shadow` |
| 「暂停」 | `python3 scripts/loop.py mode paused --reason "作者原话"` |
| 「回滚」 | `python3 scripts/loop.py rollback`（回到上一版） |
| 「确认现在这版」 | `python3 scripts/loop.py anchor`（设为锚点，以后发布都不许比它差） |
| 「接受手工修改」 | `python3 scripts/loop.py accept-manual` |
| 「召回现在怎么样」 | `python3 scripts/loop.py status`；数据没接上的时候，读状态文档开头「现在的情况」那一段来回答 |
| 「合并一下细则」 | `python3 scripts/loop.py export`，把生成的合并提案给作者 |

作者的回答原样存进判例库，以后裁判遇到相似的情况会读到；作者说明每份相关的盲评都带着，写候选时也会列出来。作者说的话只改评判标准，不直接改 `haohao-shuohua`：技能要变，还是得召回攒够、候选过门禁。作者改底线、门槛或数据来源的要求，照做之前先复述一遍确认。

---

## 一次性评测

比稿、比工具、给技能做回归，都用同一套裁判协议（`references/judge-protocol.md`），但不走发布：

- 每份改写逐份判，不放在一起比着判；多份改写先打乱、去掉来源再判。
- 结论按「改坏了 > 没改好 > 合格」排；同是改坏，编造比丢信息重。不给总分，也不把几份改写的分数加减比较。
- 一字不差的两份改写只能判平。
- 结果写清楚每份的问题清单和引用，让人能逐条复核。

---

## 数据在哪

技能目录只读，所有运行数据写在数据目录：`$HAOHAO_EVAL_HOME`，没设就是 `$XDG_DATA_HOME/haohao-eval`，再没有就是 `~/.local/share/haohao-eval`。

```
config.json          门槛和每天的题量，作者可以改
state.json           模式、现用版本、预发布、锚点、冷却中的病灶
pool.jsonl           召回到的问题，一行一条，带引用和原题快照
disputes.jsonl       待你判断的题和回答
precedents.jsonl     作者的回答，裁判当判例读
notes.jsonl          作者说明：不针对某道题的交代，原话保存
inbox.jsonl          作者回话的执行记录，日报据此列出当天记下了什么
metrics.jsonl        每天的改坏率、残留率、误改率
releases/            每个版本的细则（v0000 起），预发布是 rc0001 起
runs/<日期>/          当天的题、改写、检查、盲评队列、裁判答案、决策、日报，只留 14 天
exports/             要写进飞书文档的内容：state-doc.xml、record-<日期>.xml
```

细则发布在 `$XDG_DATA_HOME/haohao-shuohua/daily-learning.md`（没有 `XDG_DATA_HOME` 就是 `~/.local/share/haohao-shuohua/daily-learning.md`），`haohao-shuohua` 干活前会读它。

本地文件留不住的平台（比如 Mira 定时任务），数据目录只当当天的工作区，跨天靠两篇飞书文档：

- **状态文档**：除了 `runs/`、`exports/` 以外的数据目录全部内容，加上已发布的细则，按行存成 JSON，放在文档的代码块里，头一行记着第几份、多少行和 sha256。开头有一段「现在的情况」和「现用细则」给人看。`state load` 恢复时校验不过就停下；本地比文档新时不覆盖，覆盖前把原来的挪走备份。`state check` 核对写进去的跟本地是不是同一份。
- **召回文档**：作者的文档，最后一节「每日迭代日志」由 `doc record` 每天追加一条，作者在这一节里填判断、写交代，`doc read` 读回来。

数据不会越攒越多：问题池只留 30 天、每类问题最多留 8 道原题快照，判例、作者说明、指标、运行目录都按天数或条数封顶（`config.json` 的 `retain`）。题号、说明编号只增不减，删掉旧的也不会重号。

## 文件

```
scripts/loop.py          薄入口：从 hh_eval 包再导出全部旧名字并接 main（30 行，行为与单文件版逐字节一致）
scripts/hh_eval/        实现包：const(常量/Stop)、fs(路径/IO/配置/状态/Lock/data-root)、judge(裁判核对)、
                         seed(出题种子/抽样)、fp(底线指纹)、rules(细则)、gates(门禁/指标/发布回滚/体检题去重)、
                         manualdiff(手改稿对照：作者删的我们跟删、作者留的我们越动)、
                         statedoc(状态文档)、docdoc(召回文档)、pipeline(各日命令)、preflight(进场自诊断)、cli
scripts/test_loop.py     原有端到端测试（22 个，python3 scripts/test_loop.py）
scripts/test_adversarial.py  对抗式回归：坏 JSON/校验不符/缺节/伪造引用/幂等/数据隔离/误套判例/指标虚高等 11 个
scripts/scorer.py        残留正则和新数字预筛，给机械检查当提示；统一分已废弃，只留历史对照
scripts/label_agreement.py  多人标注一致性（离线工具：CSV 长表 → pairwise 一致率/Cohen kappa/分歧导出）
scripts/build_seed.py    从 50 条历史材料生成判例、回归题和干净对照
data/cases50.json        50 条历史材料（原文、三版改写、作者意见），不许删
data/labels.json         50 条的保真/通顺档，裁判体检用
data/precedents.json     判例：作者意见按工具切开，原话保留
data/regression_seed.json、data/clean_seed.json   回归题和干净对照
data/manual_edits.json          作者手改种子库；start --manual-seeds N 按天轮转取 N 条当 fresh 题（只给原文，裁判看不到作者动作和规则信号）
scripts/fit_weights.py、scripts/build_labels.py、data/archive/   历史离线工具，不进每日流程；fit_weights 需要 scipy（见 requirements-optional.txt）
```

BadCase 母表：飞书多维表 `YClTbfJYHa8u6MsAI6IcoUZunle`，table `tblQwBoiuetAOo4T`（作者自己的表）。表里的 BadCase 默认当真实材料用，一天最多 3 条，行里的「人工评价」跟着题走、当判例；不想让召回读这张表，把 `config.json` 的 `sources.read_new_badcases` 改成 false。在别人机器上跑、不想把作者的表 ID 写进配置时，用环境变量 `HAOHAO_EVAL_BADCASE_BASE` / `HAOHAO_EVAL_BADCASE_TABLE` 指定；都没配置时 `loop start` 会提示「今天不从母表新增材料」，不影响当天流程。

---

## 历史评分尺

旧的统一分 `保真系数 ×（0.7157 × 通顺分 + 0.2843 × 残留分）` 不再用来判断技能有没有变好：原样不改的「改写」平均能拿 94.5 分，高过我们和两个竞品，50 条里有 27 条它排第一。它奖励的是「不动」和「没命中正则」，量不出失真。

**为什么废弃（循环自证，诚实记录）**：这套分的地基是作者一个人标的 50 条标签——作者自己赢了 70%（35/50），用这批标签拟合出来的权重自述自洽率只有 24/50（48%）。单人标注、自评占优、拟合复现不了自己的标签，三个事实合起来说明它是循环论证，不是尺。所以统一分从「功能」降级为「历史对照」：`scorer.py` 文件头和合成分段都有废弃横幅，跑 `--unified` / `--calibrate` 只打印废弃提示，`data/fitted_weights.json` 已移到 `data/archive/`。**任何人不要为单条 BadCase 去重跑拟合，也不要据此调任何规则。**

保留下来的用处：

- `scorer.py` 的残留正则进了机械检查，命中只当提示，裁判复核后才算数。
- `new_number_prescreen` 进了机械检查，抓改写里新冒出来的数字。
- 单段看残留：`echo "一段中文" | python3 scripts/scorer.py`；声明名家风格时加 `--style 鲁迅`，只豁免破折号、三连、分号排比这类疑似项，翻译腔、翻案体、半角标点、元话语照扣。风格盖得住中性口味，盖不住硬病红线。
