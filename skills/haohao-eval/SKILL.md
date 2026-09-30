---
name: haohao-eval
description: 评测 haohao-shuohua，运行每日召回、盲评、候选门禁与自动回滚。用户要比稿、跑回归、处理 BadCase 或控制每日优化时使用；普通润色不用。
---

# 好好说话 · 评测与每日召回

这个技能管两件事：每天自动召回，把 `haohao-shuohua` 在新题上犯的错找出来、攒够了再改、改了要验证；另外，需要时做一次性的评测。

召回的标准只有一个：**技能在完整的任务里，有没有把原文改坏，有没有没改好。** 改坏指失真：编了原文没有的东西、丢了信息、改了程度范围模态、术语通俗化、场合错配。没改好指 AI 味还在、新添了病句、没毛病的句子也动了手。分数和正则只当提示，不当结论。

---

## 铁律（每一步都不许破）

1. **保真第一。** 判改坏只看原文和上下文：改写里每条信息都要找得到出处，原文每条信息都要找得到下落。改写得再顺，失真就是改坏了。口语不等于自然。
2. **裁判只核对，不打总分。** 每条问题都要引用原句，交给 `loop.py` 逐字核对，对不上的作废。拿不准就判「不确定」并给出争议片段，不硬判。
3. **评测时不改被测版本。** 改进只写进候选细则；候选冻结以后才改写、才判。判完不许回头改候选、放宽门槛、重试到过为止。
4. **发不发布只看 `loop.py` 算出来的门禁。** 拿不准就不发，不许每天必须发布，不许手动改判或跳步骤。
5. **底线条款只有作者能改。** 自动流程只动 `daily-learning.md`，不碰 `haohao-shuohua` 的技能文件，也不读不写作者的 `style.md`。
6. **没跑的步骤写「没跑」。** 不许编结果，不许凭记忆汇总。命令报错就停下，把原始报错写进日报。
7. **材料和凭证守规矩。** 真实材料只用作者明确给的来源，不自动扫描私人文档；个人信息、财务、公司敏感内容不用。凭证靠环境变量或平台密钥注入，不打印，不写进任何文件。
8. **问作者要省着问。** 每天最多 3 条，每条只给一句原文、一句改写、一个是非题；不回就按保守默认处理，流程不等人。

---

## 每日召回

定时任务每天跑一轮，完整步骤和命令在 `references/daily-loop.md`，照着做就行。一轮的骨架：

1. `loop.py start`：记下版本指纹，抽裁判体检题、回归题、干净对照，定今天的目标病灶。
2. 裁判体检：用作者判过的历史样本考裁判，没过就只召回、不出候选。
3. 出题：合成改写题（先有事实清单再有稿）、起草题、针对目标病灶的探针，外加作者给的真实材料。
4. 现用版改写全部题目；有目标病灶时写候选细则，冻结后用候选版改写验证题。
5. 机械检查、打乱匿名、逐份裁判、逐字核对引用。
6. `loop.py decide`：召回入池、算指标、建待判断的题、过门禁、预发布或发布，发布后变差自动回滚。
7. `loop.py report`：生成日报，原样发给作者。

头 14 天是影子运行：流程全跑，只记录「本来会发布什么」，不真发布。影子期结束时，如果裁判体检稳定、抽查漏判不超过一成，自动切到自动发布，日报里会说一声。

相关细则：出题看 `references/item-sources.md`，判法看 `references/judge-protocol.md`，写候选看 `references/fix-proposal.md`，门禁和发布看 `references/gates-and-release.md`，问作者看 `references/disputes.md`，问题编码看 `references/badcase-taxonomy.md`。

---

## 作者回话时怎么办

作者可能在任何会话里回一句话，照下表执行，执行完把命令输出原样告诉作者。命令都在本技能目录下跑。定时任务里，作者的回话在开轮前处理（见 `references/daily-loop.md` 第零步）。

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
| 「召回现在怎么样」 | `python3 scripts/loop.py status` |
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
runs/<日期>/          当天的题、改写、检查、盲评队列、裁判答案、决策、日报
```

细则发布在 `$XDG_DATA_HOME/haohao-shuohua/daily-learning.md`（没有 `XDG_DATA_HOME` 就是 `~/.local/share/haohao-shuohua/daily-learning.md`），`haohao-shuohua` 干活前会读它。

每次开新环境、本地文件留不住的平台（比如 Mira 定时任务），用数据包跨天：云空间里放一个固定的数据包文件，开跑先下载它跑 `loop.py unpack`，收尾 `loop.py pack` 再覆盖上传回去。包里有清单和校验和；本地比包新时不覆盖，覆盖前把原来的挪走备份。还没存过数据时，那个文件是 `loop.py pack --empty` 打的空包，`unpack` 读到它会提示先 init。最近 14 天的运行目录进包，更早的只留汇总（`config.json` 的 `pack.keep_runs_days`）。

## 文件

```
scripts/loop.py          每日召回的确定性部分：落盘、检查、盲评、核对、门禁、发布、回滚、争议、日报
scripts/test_loop.py     loop.py 的端到端测试（python3 scripts/test_loop.py）
scripts/scorer.py        残留正则和新数字预筛，给机械检查当提示；统一分只留作历史对照
scripts/build_seed.py    从 50 条历史材料生成判例、回归题和干净对照
data/cases50.json        50 条历史材料（原文、三版改写、作者意见），不许删
data/labels.json         50 条的保真/通顺档，裁判体检用
data/precedents.json     判例：作者意见按工具切开，原话保留
data/regression_seed.json、data/clean_seed.json   回归题和干净对照
scripts/fit_weights.py、scripts/build_labels.py、data/fitted_weights.json   历史工具，不参与每日判断
```

外部 BadCase 数据源默认关闭。作者明确提供数据源后，在运行目录的 `config.json` 中填写 `sources.badcase_base`、`sources.badcase_table`，再把 `sources.read_new_badcases` 改为 `true`。真实材料一天最多 3 条，人工评价跟着题走、当判例；技能包不保存账号、内部链接或平台凭证。

---

## 历史评分尺

旧的统一分 `保真系数 ×（0.7157 × 通顺分 + 0.2843 × 残留分）` 不再用来判断技能有没有变好：原样不改的「改写」平均能拿 94.5 分，高过我们和两个竞品，50 条里有 27 条它排第一。它奖励的是「不动」和「没命中正则」，量不出失真。

保留下来的用处：

- `scorer.py` 的残留正则进了机械检查，命中只当提示，裁判复核后才算数。
- `new_number_prescreen` 进了机械检查，抓改写里新冒出来的数字。
- 单段看残留：`echo "一段中文" | python3 scripts/scorer.py`；声明名家风格时加 `--style 鲁迅`，只豁免破折号、三连、分号排比这类疑似项，翻译腔、翻案体、半角标点、元话语照扣。风格盖得住中性口味，盖不住硬病红线。
- 权重拟合和 50 条自洽性校准只做历史对照，别为单条 BadCase 改权重。
