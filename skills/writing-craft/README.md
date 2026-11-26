# writing-craft · 写作工坊

将原先分散在表达层的 `talk-smith`、`cuihuo` 与 `tangshan-style` 按 **C1 架构（底座与专职分支独立 + 表达层三合一轻路由）** 收口为单一文章写作入口，解决弱路由环境下漏触发裸写及复合型文章多技能打架的问题；同时保留 `haohao-shuohua`（语言清洗底座）、`feynman-explainer`（调研与讲透）、`engineering-docs`（研发方案与工程图）各自独立。

---

## 一、三分支一稿一主帅（先定文体，按分支单读）

| 分支 | 适用写法 | 按需加载文件 | 核心特点 |
|---|---|---|---|
| `sharing` | 经验分享、项目/年度复盘、动手实录、工具安利、方法论传播、talk / slides | `references/sharing.md`（talk/slides 再查 `references/sharing-formats.md`） | 基于 `6` 篇真实标杆文章重炼：真问题发现弧、具象先于抽象、短段同事口吻、如实亮边界，去除固定五字段 TL;DR 与八股配额 |
| `opinion` | 无花架子、偏自然口语化的同行直白观点硬文，及 `≤ 120` 字锻造手记 | `references/opinion.md` | 继承原 `cuihuo` 核武器（直给判断、零门槛比喻、反车轱辘话、因果环不许砍），进一步加强自然口语化直说口吻 |
| `tangshan` | 带公众号专栏风味的激励博弈、制度结构与历史周期深度长评与推演 | `references/tangshan.md`（轻模型/卡壳按需查 `tangshan-thinking.md`、`tangshan-voice.md`、`tangshan-fidelity.md`） | 完整无损继承 `tangshan-style v1.1.0` 双模松绑内核与跨题材保真锚点 |

---

## 二、复合型文章怎么解（三步不打架）

1. **前置取证拆出去**：需要查源码、仓库、论文或黑盒原理时，先由独立的 `feynman-explainer` 产出核实事实与机理结论，再进本技能成稿。
2. **只立一个主帅**：进 `SKILL.md` 后只按选定分支打开对应的 `1` 份模块文件，其余两套风格规则物理上不进上下文；文章里的复合需求（如在分享文里顺带讲两段原理或吐槽误区）直接按人话和证据写，不再叠挂第二套模板。
3. **底座统一洗净**：成稿后交独立的 `haohao-shuohua` 守保真并去 AI 味（`tangshan` 轻模型按 `tangshan-thinking.md` 第零节自检免压缩），并遵守主帅的标题与版式豁免。

---

## 三、确定性字面自检（可选 L1）

```bash
python3 scripts/writing_check.py <稿子.md> --mode sharing|opinion|note|tangshan
python3 tests/test_writing_check.py
```

只检查前 3 段禁用空导语、未闭合代码围栏、中文正文夹半角标点、未核实残留标记（ERROR）以及手记超 120 字/段落墙等提示（WARN）。
