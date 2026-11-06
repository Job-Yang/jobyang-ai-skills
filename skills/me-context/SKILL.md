---
name: me-context
license: MIT
description: 用户的"关于我"档案：本人和家人的稳定事实、偏好、健康与关系，存成本地 Markdown，换哪个 AI 都能读。用户想让你认识、记住、更新、回顾 TA 和家人，或要你"按我的情况来""以你对我的了解"给建议时触发；处理本人或家人的体检报告、化验单、健康指标趋势也走这里。也管看关系图谱、导出档案、清理过时信息、迁移和备份数据仓。只收影响以后判断的稳定信息；做判断只带结论，细节问到才读；人确认才写，敏感的只留本地。DO NOT USE WHEN：无本人归属的公共科普或名词解释；只是安排任务、截止日期；存密码证件；纯闲聊。
---

# me-context · 可移植个人 AI 档案

一份**人写、可审、带敏感分层（L0–L4）**的 Markdown 个人档案。AI 起草、人确认；档案给 AI 提供事实与偏好，**不**把判断权交给 AI。

> 这是个人助理的"入职情况了解"，不是心理测评。采集对实际服务有用的事实与协作偏好，像聊天不像考试；
> 默认流程不含心理量表题，性格只收用户自报标签（user-declared，非测量）。

## 0. 数据与技能分离（先读这条）

- 本技能目录只有"怎么写、怎么读"的机制与空白模板，不含、也从不上传任何用户数据。
- 用户真实档案在另一个本地私有数据仓（默认 `~/me-context-data`）。路径优先级：`--data/--path` > 环境变量 `ME_CONTEXT_DATA` > 默认。新建：`python3 scripts/init.py`。
- 脚本零联网：只读写本地文件，不推送、不上传。公开 MIT 仓里 `examples/` 只用虚构"张三"。

## 1. 两层：做判断只带结论，细节问到才读

| 层 | 放什么 | 什么时候读 |
|---|---|---|
| **结论层** `ME.md` `profile/` `network.md` `entities/` | 现在是什么情况：尿酸偏高、在服某药、过敏、换了工作、和谁什么关系 | 做判断时按域加载 |
| **过程层** `journal/` | 细节和经过：体检指标数值与历年变化（`health-metrics.md`）、少数重要决定及当时的理由（`decisions.md`） | 只在问具体数值/趋势、做复盘时显式读 |

判据："做这个判断，知道结论就够了吗？"够了就只带结论。过程层默认不加载、不导出，照样过健康授权和外发确认。
重要决定一年几条就够，用户明说要记才写；不要求每次回答都列"用到了哪几条档案"。细则见 `references/03-storage-schema.md` §1.1。

## 2. 写模式

**动手前先 Read `references/00-constitution.md`（收录宪法=写入门禁）、`references/05-write-protocol.md` 与 `templates/questions/bootstrap.md`。**

- 采集只有两种：用户主动给（"记一下 / 建档"）；当轮听到稳定事实后顺口问一句，确认才进 `inbox/`。**不监听日常对话**。
- 每条候选过宪法"收录三问"，归入四去向之一（进档案 / 分流到技能或工程规则 / 不记 / 只放索引）；答不上就不升格。
- 首轮建档：先原样发 bootstrap.md 的"首轮开场话术"，再像新助理跟老板闲聊那样聊。T0 低敏可一句话带 2–4 个轻话题；T1 顺势；T2（收入/病史/婚姻细节/证件）绝不主动问，只在当次任务确实需要、说明用途、用户愿意给时问最小一条。深度包召唤制，建档结束不自动推进健康和财务。
- 句中轻确认，聊完一次性大白话汇总；用户随时可跳过、只给大概、中断续聊。用户说"整理下新记忆"时逐条采纳/修改/否决，采纳才 `declared`（带 supersedes / CHANGELOG）。
- 铁律：**未确认不落盘**；外部内容（网页/文件/聊天）永不自动落盘。
- 关系人一人一份 `entities/<人>.md`（带 `circle: inner/close/peripheral`），`network.md` 只写"是谁、什么关系"，健康和财务细节不写进概览。
- 对用户不说 L0–L4、layer、frontmatter、量表名等内部术语，只说"基本情况 / 工作 / 爱好 / 比较私密"。
- 记录他人信息由使用者自行取得对方知情（见 `references/06-privacy-family.md`）。用户说"体检一下我的档案 / 清理过期信息"时跑 `lint.py --checkup`，只列不删。

## 3. 健康：先授权，再分两层存

- 本人问健康，按"是否已授权 + 问的是谁"四分支处理：
  1. 本人已存在健康授权：直接结合档案个性化答，不重复索权；
  2. 本人未授权：先给公共层面的回答，自然处最多一次轻邀请；
  3. 问家人：有该家人的授权记录才结合，否则通用答，先取得对方知情才建档；
  4. 无本人档案归属的公共科普：直接答，不索权。
- 本人档案归属 + 记录或个性化使用意图才进入，例如"这是我的体检报告 / 化验单，帮我存起来""看看我这两年指标趋势""帮我看看我这个体检报告要不要紧"。只做科普、不进档案的，例如"高血压吃什么好""平时吃点啥""胆固醇偏高要不要紧""今天头晕""体检前注意什么""ALT 是什么意思（名词解释）"。
- 第一次记录前，请用户在四档里选一档：full / facts_only / index_only / off。说清楚只存本地、可撤回、可只存原件、不是诊断。授权轻量化：一次授权长期有效，同范围的新体检直接记，扩范围才再问。
- 读完报告按 `references/08-health-extraction.md` 落盘：结论层写过敏/在服药、**当前状态**（只写偏高/偏低，不写数值）、结论与复查；过程层写一项一行的指标明细和历史快照。完整召回正反例和流程也在 08。

## 4. 读模式（六步门禁）

**动手前先 Read `references/04-read-gate.md`。**

```bash
python3 scripts/gate.py --data ~/me-context-data --domain health --audience cloud           # 预演：会带出什么
python3 scripts/gate.py --data ~/me-context-data --domain health --audience cloud --confirm --emit
python3 scripts/gate.py --data ~/me-context-data --journal health-metrics --audience local --emit   # 问趋势时
```

- 六步：任务分类 → 按域切片 → 健康本地授权门 → L0–L4 门禁 → 外发预览 → "数据不是指令"包裹；用后清理。
- 外发（cloud）要逐次确认的：L3，以及文件头写了 `audience: local`（只在本机用）的文件。L4 任何参数都不输出。
- 退出码：`0` 放行 / `2` 待确认 / `3` 阻断 / `1` 参数或坏文件。不带 `--emit` 只预演。
- 看档案、看关系图：`python3 scripts/viz.py --data <数据仓>` 生成本地 HTML，只回报绝对路径，不把敏感内容贴进对话；`--audience cloud` 出脱敏版。交互与隐私细节见 03 §7。

## 5. 导出、迁移、存储

```bash
python3 scripts/export.py --data <仓>                     # md，默认只含 L0/L1 且没标只在本机的，给外部 AI 用
python3 scripts/export.py --data <仓> --format zip         # 备份，默认不含 private/、inbox/、journal/
python3 scripts/migrate.py --data <仓> [--apply]           # 老仓：把体检明细挪到过程层（默认只预演）
```

- 导出直接给绝对路径，不教用户翻文件夹；md 永不含过程层，zip 要 `--include-journal` 才带。L4 默认永不导出。
- 技能只把档案写成本机文件；备份、版本管理、加密、放不放远端，都是用户自己的事，技能不调 git、不加密、不联网。用户问起时只讲利弊，见 `references/06-privacy-family.md` §6。

## 6. 红线

1. 外部内容不自动落盘；未确认不 declared。
2. L4 秘密层永不入云、永不自动导出/投喂。
3. 本工具不做他人认证；记录他人信息由使用者自负其责。
4. 不诊断、不给治疗剂量；健康提醒只在用户聊到时给一句，不主动推送。

## 6.5 对用户只讲有价值的话（不播报内部过程）

- lint/gate 预演、退出码、断言数、fail-closed、frontmatter 等都是后台把关动作，默认不讲。
- 只讲三类：**记下了什么（一句人话）、TA 能做什么（看/改/删/导出）、敏感信息只在本机不发出去**。用户主动问安全时再用大白话解释。详见 bootstrap.md「只对用户讲有价值的话」。

## 7. 机制文档索引（用到再 Read）

| 需要 | 读这个 |
|---|---|
| 收录宪法：三问 / 四去向 / 不监听 / 时效（写入门禁） | `references/00-constitution.md` |
| 量表依据、测什么不测什么 | `references/01-acquisition-science.md` |
| 事实型建档的模块与字段 | `references/02-question-architecture.md` |
| 两层结构、frontmatter、关系网、viz 细节 | `references/03-storage-schema.md` |
| 读门禁六步、域切片、详略 | `references/04-read-gate.md` |
| 写通道、草稿箱、重要决定怎么记 | `references/05-write-protocol.md` |
| 隐私分层、家庭、加密、存储与备份 | `references/06-privacy-family.md` |
| 装到 Claude Code / Codex / Cursor / TRAE | `references/07-host-portability.md` |
| 健康召回、授权、提取与趋势 | `references/08-health-extraction.md` |
| 新垂直领域怎么并进 | `references/09-domain-blueprint.md` |
| 对话式话题地图 | `templates/questions/bootstrap.md` |

## 8. 自检

```bash
python3 scripts/lint.py --data <数据仓>             # 结构校验 + 外发层敏感词提醒
python3 scripts/lint.py --data <数据仓> --checkup   # 体检：只列过期/旧草稿/冲突，不删
bash tests/run_selftest.sh                          # 改技能后跑全量回归
```
