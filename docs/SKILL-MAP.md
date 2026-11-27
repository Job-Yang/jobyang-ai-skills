# 个人技能库定位与配合图（SKILL MAP）

> 这张图回答三个问题：**每个技能单独解决什么问题、单独装到任意 AI 环境能得到什么、和别的技能怎么配合。**
> 配套可交互关系图：`skill-map.html`。

## 0. 第一原则：技能不绑定任何运行时

- 每个技能都是**自包含的 SKILL.md 文件夹**，只依赖宿主的通用能力（读写、检索、对话）。装到任意宿主、任意 AI 环境都应独立成立。
- 某些宿主提供工程反馈闭环、完成门禁、插件化运行时或流程插点——这些只是**可选增强场景，不是依赖**：技能可被这些流程按需加载，但删掉这些环境后技能依然能用。
- 写技能时：引用同库或外部技能用「该类方法」的中性描述，不写死任何宿主专属技能名、命令或工具；需要外部能力时写「若宿主具备则用」，不具备就降级。
- 技能仓是唯一权威源，分发到各处由 `tools/sync_skills.py` 统一完成（见第 5 节）。

## 1. 这张图怎么用（新增 / 修改技能时先过这里）

每次新增或改技能，对照第 4 节清单检查；技能表与关系图必须同步更新（中英文 README 一致）。单一所有权与双模分层规范见 [架构规范](./SKILL-ARCHITECTURE.md)；七个思维型技能的触发特征与好坏判别统一见 [思维技能质量判别卡](./SKILL-QUALITY-CARD.md)。"还缺什么、能不能补"不凭感觉，走 [缺口体检](./SKILL-GAP-AUDIT.md)。

## 2. 技能总表（按 6 大逻辑分组）

> 说明：物理目录仍保持 `skills/<name>/` 平铺以兼容所有宿主与单包分发；逻辑分组维护在 `tools/skills-manifest.json`（`engineering`、`product-opc`、`thinking`、`writing`、`personal-tools`、`governance`），支持按组同步。

状态：✅ 已有　⏸ 缓建　❌ 裁定不建

### 组 1 · 研发全周期 (`engineering`：方案 → 规格 → 盲审 → 执行 → CR → 排障 → PR → 终审)

| 技能 | 唯一解决的问题 | 输入 → 输出 | 独立收益（任意宿主） | 可选增强场景 |
| --- | --- | --- | --- | --- |
| ✅ engineering-docs | 写研发技术评审文档（RFC/ADR）与工程图 | 上下文 → 文档+图示 | 独立成文 | 下游交 `implement-spec` / `spec-battle` |
| ✅ implement-spec | 把已拍板方案或重构编译为可执行编码 Spec | PRD/RFC/目标 → 深模块接口+1-commit 步骤 | 独立拆出可执行 Spec | 按 `repo` / `local` / `ephemeral` 自动落位 |
| ✅ spec-battle | 开工前跨上下文独立检察对抗盲审 PRD/RFC/Spec | 文档+源码 → 四件套异议+人裁修改清单 | 独立防作者盲区 | 可路由全新只读跨模型子代理 |
| ✅ go-work | 低上下文按 Spec 分步落地、断点续跑并归档 | 开放 Spec → 分步提交+归档配 `.ignore` | 单会话或子代理续跑 | 支持最多 3 路临时 detached worktree |
| ✅ diff-review | 只读深度 CR：分层审查 + Skeptic 证伪去误报 | Diff/PR → Sign-off 报告或审人评论草稿 | 隔离 worktree 验测 | 含多人大仓兼容/并发/回滚检查 |
| ✅ code-bugfix | 红灯驱动根因排障、3 假设停损与回归锁死 | 报错/症状 → 唯一根因+红转绿回归测试 | 10 级复现梯队+脱敏 | 临时 worktree 安全二分与同类清扫 |
| ✅ pr-prep | PR 拆分建议、说明骨架、大改动离线视觉导览与前检 | 本地分支 → PR 说明+`$TMPDIR` 离线 HTML | 拦截泄漏与过大单 PR | 检查兼容混跑与回滚开关预案 |
| ✅ vdd | 宣称完成前的实证门禁与跨轮大重构防漂移 | 完成声明 → 实测证据核验与边界裁决 | 独立防虚报与过度改 | 与 `diff-review`/`code-bugfix` 清晰分流 |

### 组 2 · 产品孵化与原型 (`product-opc`：发现 → 评估 → 定义 → 设计 → 实验 → 拆解)

| 技能 | 唯一解决的问题 | 输入 → 输出 | 独立收益（任意宿主） | 可选增强场景 |
| --- | --- | --- | --- | --- |
| ✅ opportunity-radar | 找「有哪些机会」并带来源证据 | 领域/材料 → 机会候选+证据 | 一次性机会扫描 | 作为产品工作流起点 |
| ✅ opportunity-scorecard | 评「单个想法值不值得做」，脚本打分 | 想法+证据 → 十维评分+结论 | 可独立运行评分 | 作为产品工作流评估节点 |
| ✅ product-brief | 把想法变成 PRD、计划或存量单特性轻卡片 | 需求/评分卡 → PRD/轻卡片+`GLOSSARY.md` | 独立产出需求文档 | 进编码交 `implement-spec` |
| ✅ style-compass | 把需求变成 UI 设计、交互原型与 `DESIGN.md` | 需求 → 线框/原型/规格 | 独立完成设计评审 | 存量迁移切片交 `implement-spec`/`go-work` |
| ✅ minimum-experiment | 用最低成本拿到真实反馈与继续/停止信号 | 待验假设 → 可逆实验+停损阈值 | 独立把空想变试错 | 结论回流 `product-brief` / `scorecard` |
| ✅ reverse-teardown | 从外部优秀成品提炼可迁移规律与练习 | 成品+目标 → 规律/本案/清单/练习 | 任意环境拆解学习 | 喂给链上产品/设计环节 |

### 组 3 · 决策与批判思考 (`thinking`：把问题、选项与证据想清楚)

| 技能 | 唯一解决的问题 | 输入 → 输出 | 独立收益 | 可选增强场景 |
| --- | --- | --- | --- | --- |
| ✅ outside-view | 「决策缺不缺外部证据、信多少、何时停」 | 决定+证据 → 取证与冲突裁决 | 独立做有纪律的检索 | 作为其他技能的取证底座 |
| ✅ steelman-choice 钢人抉择 | 两个方案都讲得通时，先把两边立到最强再抉择 | 两选项+约束 → 最强对立+翻盘一问 | 任意对话里防草率拍板 | 可挂在多方案拍板节点 |
| ✅ claim-check 说法核查 | 判断离散说法/数据可不可信 | 一条说法 → 五级可信度+推理漏洞 | 任意环境验真 | 需联网时复用 outside-view |
| ✅ argument-reading 论证精读 | 重建整篇文章论证链、隐藏前提与失效条件 | 全文 → 论证链+证据分级+谬误定位 | 任意环境做批判阅读 | 离散事实核查交 claim-check |
| ✅ root-rethink 归本重推 | 跳出补丁循环，回到事实与约束重推（含跨域借解） | 卡点 → 事实/假设/约束 → 新路 | 独立重推方案 | 代码缺陷排查让位 `code-bugfix` |
| ⏸ socratic-clarify 问题澄清 (P2) | 我连真正想问什么都说不清 | 困惑 → 多轮一问 → 真问题 | 深度澄清入口 | 与流程自带澄清 gate 互补 |

### 组 4 · 中文写作、调研与信息图 (`writing`)

| 技能 | 唯一解决的问题 | 独立收益 |
| --- | --- | --- |
| ✅ feynman-explainer | 负责对内对外技术调研、机制解读与讲透成稿（逻辑链非清单） | 任意环境完成调研取证并输出报告 |
| ✅ haohao-shuohua | 清洗 AI 中文文本（保事实去 AI 味） | 任意成稿 lint |
| ✅ writing-craft | 表达层三合一写作入口：按分支单读产出分享/复盘/talk/slides（`sharing`）、口语直球观点与 ≤120 字手记（`opinion`）或汤山长评（`tangshan`） | 任意环境写表达型文章与演讲分镜 |
| ✅ sansi-erhouxing | 中大型文档结构级改稿前先读全文骨架（局部微改直通） | 防止补丁式改稿且不卡轻任务 |
| ✅ haohao-eval | 用盲评/召回评测中文改稿质量 | 独立评测台，支撑 haohao 迭代 |
| ✅ content-infographic | 把文章关键道理做成「图自己讲清一件事」的信息图与封面 | 零依赖渲染器出高清 SVG/PNG |

### 组 5 · 个人情报、档案与媒体工具 (`personal-tools`)

| 技能 | 唯一解决的问题 | 独立收益 |
| --- | --- | --- |
| ✅ ai-briefing | 5 分钟读完的 AI/前沿科技日报（事实+判断+机会分卡片） | 任意环境生成情报简报，渠道走 config 适配 |
| ✅ me-context | 「我是谁/要什么/红线」的可移植档案，读写带敏感门禁 | 数据与技能分离，跨宿主携带 |
| ✅ png-compress | 批量压缩工程 PNG（缓存/门禁/回退） | 任意本地工程直接用 |
| ✅ video-reader | 把视频转关键帧+时间线给只读图模型 | 任意环境看懂视频 |

### 组 6 · 库级治理 (`governance`)

| 技能 | 唯一解决的问题 | 独立收益 |
| --- | --- | --- |
| ✅ skill-library-keeper | 在技能库视角决定要不要建新技能、查撞车/孤儿/硬绑定、评估外部技能 | 自动发现技能库位置，零平台绑定直接体检与把关 |

> 规划技能理论出处：`steelman-choice` 出自善意原则与钢人论证；`root-rethink` 出自第一性原理与跨域借解；`claim-check` 脱胎于事实核查与系统怀疑；`argument-reading` 为整篇版批判阅读；`implement-spec` 吸收深模块与表征测试纪律；`spec-battle` 吸收盲审对质与四分法裁决。

## 3. 配合关系（谁在什么时候调谁）

```text
立项前 OPC 孵化（无代码仓）：
  radar → scorecard → product-brief (PRD) → style-compass → engineering-docs
    ↑ 学习外部成品用 reverse-teardown，产出可喂给链上任一环

进代码仓后全周期研发闭环（个人仓 `docs/` | 多人大仓 `.agent-work/` 零污染）：
  1→N 增量需求：product-brief（单特性轻路径）或 engineering-docs（高风险 RFC）
    ↓
  implement-spec（深模块接口 + Source hash 锚点 + 1-commit 步骤）
    ↓（高风险/关键方案可选盲审）
  spec-battle（独立全新子代理四镜起诉 → 辩方四分 → 1 轮追问 → 人裁）
    ↓
  go-work（轻量协调器 + 独立子代理 + worktree 并行 + Git/本地断点续跑 + 完工归档）
    ↓
  diff-review（只读分层 CR + Skeptic 证伪 + 审人评论） / code-bugfix（秒级红灯 + 3 假设停损）
    ↓
  pr-prep（卫生拦截 + 拆分建议 + PR 说明 + 离线视觉导览 HTML + 回滚前检）→ vdd（完成终审门禁）

决策横链（任意一环卡住时进入，用完回到主链）：
  socratic-clarify（问题不清）→ root-rethink（路径失效/在打补丁）
    → steelman-choice（方案对立选不出）→ claim-check（说法要验真）
    → minimum-experiment（要真实反馈）
  其中 claim-check / steelman-choice 需要外部事实时调用 outside-view；
  minimum-experiment 的实验结论回流 product-brief 或 scorecard。

输出横切：
  文章表达统一从 writing-craft 进入，按分支单读唯一主帅（sharing 分享复盘与 talk/slides / opinion 口语直球观点与手记 / tangshan 专栏长评）；
  任何要对外成文 → haohao-shuohua（lint 底座）；结构级改稿前先 sansi-erhouxing（≤3 句局部微改直通）；
  要讲透与做技术调研用 feynman-explainer（直接产研究报告，也被 writing-craft 与 engineering-docs 单向前置调研调用）。
```

关键不重叠约定：

- **steelman-choice vs outside-view**：前者结构化决策（多数纯推理），后者只取证；需要事实裁决才调它。
- **steelman-choice vs scorecard**：两个给定选项的对立论证 vs 单个想法的多维打分。
- **claim-check vs outside-view**：一条说法验真 vs 为决策补证据；触发词与产物不同。
- **claim-check vs argument-reading**：离散说法验真 vs 整篇文章论证重建；前者几分钟验一条，后者输出完整阅读地图。
- **reverse-teardown vs style-compass**：学外部成品 vs 评审/设计自己的页面。
- **root-rethink vs code-bugfix**：通用方案/设计跳出补丁循环用 `root-rethink`；报错、崩溃与性能回归用 `code-bugfix` 先建红灯回路。
- **engineering-docs vs implement-spec**：前者产面向评审人拍板的 RFC/ADR 与工程图；后者产面向编码 Agent 执行的模块签名、接缝替身与 1-commit 步骤。
- **spec-battle vs diff-review vs vdd vs pr-prep**：`spec-battle` 开工前盲审需求或 Spec 文档；`diff-review` 只读逐行审查代码改动并证伪去误报；`vdd` 守宣称完成前的实证门禁与跨轮防漂移；`pr-prep` 做 PR 说明、拆分与离线视觉导览备料。
- **feynman vs writing-craft vs engineering-docs**：三层拆开、单向握手——`feynman-explainer` 管源码/论文调研与客观机制报告（也为上游提供核实原料）；`engineering-docs` 管要评审拍板的研发方案与严谨工程图；`writing-craft` 管写给人看的表达型文章，并靠「一稿一主帅」隔离内部分支。
- **writing-craft 内部分支边界**：不按字数或时间线硬切——经验分享/复盘/实录/安利/talk/slides 选 `sharing`；无花架子、自然口语化的同行直白判断与 `≤120` 字手记选 `opinion`；需要汤山专栏风味剖析激励博弈与历史周期选 `tangshan`。

## 4. 新增 / 修改技能冲突检查清单

1. **一句话唯一性**：能用一句话说出它解决、而现有技能都不解决的问题吗？说不出 → 不建。
2. **触发词不撞车**：列出 8–10 条真实 query，有没有两个技能会同时命中？有 → 合并或重划边界。
3. **同一件事检验**：它和邻居是「同一个问题的不同流程」还是「不同问题」？同问题 → 合并（如 root-rethink 合并第一性原理+跨域借解）。
4. **零环境依赖**：删掉任何特定运行时/平台名后，技能是否仍独立成立？不成立 → 写成「若具备则用，否则降级」。
5. **上游/下游是否存在**：它产出的东西有没有消费者？需要的输入有没有技能/用户能提供？
6. **常驻还是按需**：它是否每次交互、每个工作流都受益且无工具化承载？都满足才考虑进运行时常驻；否则一律独立技能。
7. **反向不污染**：会不会让被引用的老技能改变自己的定位或 gate？会 → 只做单向引用。
8. **可迁移交付（多处双写）**：权威源只在仓库 `skills/<name>/`；改完运行 `python3 tools/sync_skills.py --apply`，按本机 `sync.local.json` 同步到各技能运行目录与发布 zip，同时更新本图与技能表。公司内部/第三方/个人项目技能不在白名单。

## 5. 同步机制（四处一致）

- **唯一权威源**：本仓库 `skills/`。
- **白名单**：`tools/skills-manifest.json`，只含用户自有、可迁移、可公开的技能；排除公司内部技能、第三方安装技能、强个人化项目技能。
- **同步命令**：本机路径写在 git 忽略的 `tools/sync.local.json`；`python3 tools/sync_skills.py` 预览，`--apply` 写入。可移植说明见 [SKILL-SYNC](./SKILL-SYNC.md)。
- **可迁移 `agy` 研发原则插件**：仓库 `plugins/engineering-flow/` 提供 Antigravity 零钩子第一性原则规则插件（`hooks.json` 已禁用、零后台拦截，`rules/AGENTS.md` 引导模型按可逆／不可逆边界自主调技能与 CLI），与宿主演进零耦合；通过 `python3 tools/sync_skills.py --apply --sync-agy-plugin` 幂等注册到 `~/.gemini/config/plugins.json`，不修改用户 `hooks.json`。
- 同步目标：本机配置的各技能运行目录与发布 zip 目录。目标有源外独有改动时标 ALERT；脚本不做自动备份（唯一备份是 Git），请先回灌 Git 或手动备份后再用 `--apply` 覆盖。
- 规则：在权威源改技能后默认跑一次同步，不需要再次提醒。

## 6. 本轮裁定记录（来源：12 个外部 Prompt + 1 个协作指令）

- 独立新建（已通过三关盲测正式发布）：steelman-choice、claim-check、argument-reading、root-rethink、minimum-experiment、reverse-teardown。
- 缓建：socratic-clarify（P2，触发两次真需求再建）；纵横分析法（框架留档，不单建）。
- 不建：专家会诊（通用部分并入 steelman-choice）；乔哈里视窗（常驻姿态，归宿主偏好层）；天赋挖掘/人生设计（用户拍板放弃，意义不大）；双层解释（与 feynman「脚手架不印成品」冲突）。
- 三关盲测与正式发布验收已通过：触发盲测在 `Pro` 与 `Flash` 中立路由下均为 24/24 正例召回、12/12 负例命中、0 抢触发；2 名独立 `Pro` 盲测评审对 6 个技能的真实样本端到端与对抗弱点用例逐项打分，30 项 5 维评分全部 ≥8（最低 8 分，均分 9.23），现已升级为正式发布状态。
