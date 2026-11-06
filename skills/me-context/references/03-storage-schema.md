# 03 · 存储 schema：双仓分离、两层结构、frontmatter v1、关系网圈层、relations、冲突规则

---

## 1. 双仓分离 + 数据仓两层

```text
me-context-data/                 # 私有数据仓：只在本机；备份由用户自己管，见 06 §6
├── ME.md                         # 本人画像梗概 = L0/L1 摘要 + 索引（默认投喂层）
├── network.md                    # 关系网圈层概览（只写"是谁、什么关系"）
├── profile/                      # ── 结论层：做判断时按域加载 ──
│   ├── work.md                   # 职业/能力/当前项目（L1）
│   ├── goals.md                  # 短长期目标、可执行小步（L1~L2，纯事实）
│   ├── preferences.md            # 沟通/输出/语言/do-not（L1~L2）
│   ├── decisions.md              # 决策时希望怎么配合（L2；只记偏好，不记某次决定）
│   ├── body.md                   # 身体与作息（L2）
│   ├── health.md                 # 健康结论：过敏/在服药/当前状态/诊断/结论（L3）
│   └── finance.md                # 财务事实/约束（L3，逐次确认）
├── entities/                     # 关系人一人一文件，带 circle 三圈
├── relations.md                  # 关系边集合（10 词）
├── journal/                      # ── 过程层：细节和经过，默认不加载、不导出 ──
│   ├── health-metrics.md         # 体检指标明细：最新值 + 历史快照（L3）
│   └── decisions.md              # 重要决定：日期/决定/理由/放弃了什么/回看日期（L3）
├── inbox/                        # 候选草稿暂存（非正式档案，gate/export 不读）
├── CHANGELOG.md                  # 全局留痕
└── private/                      # L4：本地静态、不投喂、永不入云
```

能力/模板/机制在公开技能仓（本目录）；"谁是谁"的真实内容只在私有数据仓。

### 1.1 结论层和过程层怎么分

| | 结论层（profile/ 等） | 过程层（journal/） |
|---|---|---|
| 回答什么 | 现在是什么情况：尿酸偏高、在服某药、对某物过敏、换了工作 | 细节和经过：每次体检的数值、某个大决定当时为什么这么选 |
| 什么时候读 | 做判断时按域加载 | 只在问具体数值/趋势、做复盘时显式读（`gate.py --journal`） |
| 怎么更新 | 事实变了直接改（supersede 留痕） | 只增不改，按时间往后追加 |
| 导出 | md/zip 按层导出 | md 永不导出；zip 要 `--include-journal` |

- 判据：**"做这个判断，知道结论就够了吗？"** 够了，结论进结论层；要看数字或经过才进过程层。例：知道"尿酸偏高"就能决定少吃海鲜（结论层）；问"这三年尿酸怎么变的"才读明细（过程层）。
- 重要决定只收改变人生走向的少数几条（换工作、搬家、大额花钱、家里大事），一年几条就够；日常选择、一次性任务仍按 00 宪法不记。
- 过程层同样过健康授权门与外发确认：`health-metrics.md` 只有健康授权为 full 才输出，外发前逐次确认。
- 老数据仓的 `health.md` 若还带「最新关键指标」「历史快照」两节，lint 会提醒，`scripts/migrate.py` 预演后 `--apply` 一键挪过去，并在结论层补一节「当前状态」（只写偏高/偏低，不写数值）。

---

## 2. frontmatter v1 字段逐个解释

每个 md 文件开头一段 `---` 包裹的元数据。**schema 版本固定为 `personal-context/v1`。**

| 字段 | 含义 | 取值 | 必填 |
|---|---|---|---|
| `schema` | schema 版本 | 固定 `personal-context/v1` | 是 |
| `entity` | 实体 id | `me` 或 slug（如 `spouse-li`） | 是 |
| `type` | 实体种类 | `self/person`（关系人统一 `person`） | 是 |
| `layer` | 敏感分层 | `L0/L1/L2/L3/L4` | 是 |
| `domain` | 所属域 | `work/goals/preferences/decisions/health/finance/network/relations/identity` | 是 |
| `circle` | 关系网圈层 | `inner/close/peripheral`（仅 entities/<人>.md） | 关系人必填 |
| `confidence` | 该条置信度 | `high/med/low` | 是 |
| `source` | 来源 | `declared/inferred/observed` | 是 |
| `updated` | 最近更新 | ISO 8601 日期 `YYYY-MM-DD` | 是 |
| `review_cycle` | 复核周期（可选） | 数字+d 天，如 `15d/60d/180d`（代码只解析 `Nd`，1–3650）；一次性/不重复的事件类事实不需要周期，留空即可，**不要写 `event`**（会被静默回退默认） | 否 |
| `supersedes` / `superseded_by` | 留痕链接 | 条目 id | 否 |
| `audience` | 允许投喂对象 | `local/cloud-low/cloud-all`；**`local` 会被 gate 强制执行**：外发（cloud）时与 L3 一样要逐次确认 | 建议填 |
| `scope` | 作用域（仅 inbox 草稿记账） | `general/engineering`，默认 general；engineering 不升格 profile | 否 |
| `decision` | 当时分流去向（仅 inbox 草稿记账，可选） | `A` 进 context / `B` 分流技能 harness / `C` 不记 / `D` 只放索引；便于回看，缺省不强制 | 否 |
| `freshness` | 时效稳定度（v11，可选） | `stable`（身份/禁忌/长期偏好，基本不变）/ `current`（在做什么/近期目标/当前方向，易过期）；缺省按域默认（见下表） | 否 |
| `stale` | 已归档标记（v11，可选） | `true` = 已归档/转历史，不再当现行事实；读取只显"已归档"，不参与层门禁 | 否 |
| `provenance` | 来源预留（v11，可选） | `建档/当轮对话/公开主页刷新/文件导入`；配 `provenance_date: YYYY-MM-DD`，只记录不判层 | 否 |

### freshness 默认表（缺省按 domain，保守兜底 stable，不误报稳定身份）

| domain | 默认 freshness | 复核周期 |
|---|---|---|
| identity / preferences / decisions / body / health / finance / network / relations | `stable` | 180 天 |
| work / goals | `current` | 60 天 |

显式 `freshness:` 覆盖默认。**只有 `current` 按龄判过期**：超 60 天未复核 → 读取/展示"可能过期（N 天未更新，上次更新 X）"弱提示；超 180 天体检建议"还成立吗？不成立就清/转历史"。`stable`（身份/禁忌/长期偏好）基本不变，**不因文件年老而误报过期**，180 天仅作可选年度轻拣。**提示只做提醒，绝不改变 L0–L4 层门禁与 fail-closed。**

> `scope` 只在 inbox 草稿用，可选；正式 profile frontmatter 不要求。lint 不因缺 scope 报错；
> gate/export 不读 scope，切片/层级/导出行为不变。

> 本技能不做他人认证：非 self 实体不需要认证块。记录他人信息由使用者自行取得对方知情（见 `06-privacy-family.md`）。

---

## 3. 关系网三圈（network）

数据仓关系侧 = `network.md`（概览索引）+ `entities/<人>.md`（详情）+ `relations.md`（边）。

### 圈层定义

| 圈 | 范围 | 详略 |
|---|---|---|
| **inner** | 用户明确最亲密、最重要的人（配偶/孩子/父母仅是常见例子，不自动归类） | 详写喜好/禁忌/关键事实（单文件核心 ≤约 1500 字） |
| **close** | 用户明确的重要联系（密友/关键同事等，具体按本人描述） | 记主要事实（更短） |
| **peripheral** | 仅"是谁/什么关系" | 梗概一行，不记细节 |

理论依据（自我中心社交网；精确出处见 `_白皮书研究笔记/10_竞品实测与记忆理论.md`）：
- 费孝通《乡土中国》「差序格局」1947（上海观察社初版；「1948 年正式印行」说并存，投稿前核）：以己为中心按亲疏向外推的同心圆波纹。
- Kahn, R. L., & Antonucci, T. C. (1980). Convoys over the life course. In Baltes & Brim (Eds.), *Life-Span Development and Behavior* Vol. 3, pp. 254–283, Academic Press（页码二手有出入，**投稿前核原书**）：关系画成同心圈，内圈最亲密。
- Dunbar, R. I. M. (1992). *J. Hum. Evol.* 22(6):469–493, DOI 10.1016/0047-2484(92)90081-J；(1998). *Evol. Anthropol.* 6(5):178–190：新皮层约束稳定关系数，关系按嵌套层级组织（内密外疏）。
- Granovetter, M. S. (1973). *Am. J. Sociol.* 78(6):1360–1380, DOI 10.1086/225469：弱关系跨群体信息桥接，外圈薄边也要留梗概。
- Wegner, D. M. (1987). Transactive memory. In Mullen & Goethals (Eds.), *Theories of Group Behavior* pp. 185–208, Springer：记「找谁问什么」本身就是记忆。

读取时按圈层切片：inner 实体可整份加载；peripheral 默认只引用 `network.md` 梗概、不整份加载，除非显式点名。

---

## 4. relations.md：10 词关系词汇表

边 = 一条 bullet：

```yaml
- from: me
  type: spouse_of          # 10 词之一
  to: spouse-li
  direction: symmetric     # directed | symmetric
  since: 2020-05-01
  until: null              # 空 = 至今
  confidence: high
  source: declared
```

**10 词**：`self` · `spouse_of` · `partner_of` · `parent_of` · `child_of` · `sibling_of` · `lives_with` · `knows` · `works_with` · `related_to`。

- 对称关系写一条、读取双向展开；有向关系必须有方向。
- lint 校验：边里 `to` 指向的实体必须存在于 `entities/<to>.md`，或标 `external: true`。

---

## 5. 冲突更新四规则（故意简单，零黑盒）

| # | 规则 |
|---|---|
| 1 | **declared > inferred**：每条带 source；声明永远压过推断。 |
| 2 | **新声明 supersede 旧声明但留痕**：不删旧条目，旧条目标 `superseded_by`，CHANGELOG 记一笔。 |
| 3 | **冲突转人工**：两条 declared 矛盾 → 标 `conflict: needs_review`，等用户裁决。 |
| 4 | **时间衰减只作用 inferred，永不作用 declared**。 |

---

## 6. 存储分层演进

- **结论层 = 核心总结**：profile/ 等 md，是做判断时唯一常驻的部分。对应 Conway & Pleydell-Pearce (2000) 自我记忆系统（SMS）三层中的 lifetime periods / general events 两层——压缩过、可审、人写的总结（Conway, M. A., & Pleydell-Pearce, C. W. (2000). *Psychological Review*, 107(2), 261–288, DOI 10.1037/0033-295X.107.2.261）。
- **过程层 = 事件细节**：`journal/`（已实现，见 §1.1），对应 SMS 第三层 event-specific knowledge。纯 Markdown、只增不改、默认不加载不导出；不做事件流水账，只收体检明细与少数重要决定。
- "自传体记忆是重构不是录像 / 巩固再巩固"仅作类比：Dudai, Y. (2004). *Annual Review of Psychology*, 55, 51–86, DOI 10.1146/annurev.psych.55.090902.142050。**这只是类比，绝不暗示 LLM 具备人脑式海马体/突触巩固**；本工程的"巩固"指人在周期复盘里确认/改写/取舍，不是生物过程。不建数据库、不做向量检索。

---

## 7. 个人知识图谱可视化（scripts/viz.py）

- **IA：本人中心关系网与人物详情并排**。本人固定圆心，`circle` 决定内外亲疏，不由配偶/父母等称谓自动评分。首屏按容量先呈现亲近的人（桌面最多 9、窄屏最多 5 个记录），点击 `+人数` 展开；搜索覆盖完整已过滤数据，详情可逐个跳到关联人。查看他人关联仍保留本人及连接路径，不将他人置换为主人。
- **两种距离分开**：空间半径表达已声明的亲疏；几跳仅表示按真实边计算的最短连接链。不补不存在的辐射线。真实交叉边、循环、多条关系和群组仍是网，不拆成树节点。同圈人多时扩大半径，姓名保持可读；用区域平移/缩放、放大工作区和可点击缩略导航找人，而非缩成小点。无连接的人可搜索，明示连接尚未记录。三圈是本工具的实用粗分，不是精确心理测量；未明确的人默认放外围，不臆测亲密度。
- 详情呈现一条最短已记录连接路径，亲子关系按行走方向读作父母/子女；路径不证明亲密度、权力或决策影响。只在已过滤的 payload 中查询，不加载额外敏感原文、不产生写入。`scripts/graph_model.js` 作为确定性图模型，在生成时内联入单文件，运行不用 Node、框架或 CDN。
- **阅读布局**：桌面默认左 40%、右 60%，中间分隔条可拖动（左右键微调、双击/Home 复位）；窄屏自动上下排列。图只通过拖拽/按钮缩放/缩略导航移动，滚轮滚整页，不在图内滚动或缩放；操作不改档案、不存用户布局数据。
- URL hash 保留 `#view=network|profile|all`、`#person=<id>`、`#dim=<id>`、`#expand=all`。首字头像仅作辅助，中文全名才是主要标签；人物详情维度与健康表保持原有结构，窄屏转单列。
- 头像首字取真名回退链：独立本名/姓名/真名 → 任意字段内嵌"本名 X" → 称呼分号后段真名 → 去称谓词（老婆/宝贝/师傅…）首字；**加粗**/链接由前端 md() 渲染成 `<strong>`/`<a>`（仅 http/https），Python 只清模板占位/示例行/引用说明，不吞正常 markdown。
- **分区级隐私（Python 端过滤后才注入 JSON，不靠前端藏）**：`--audience cloud` 时 ≥L3（L3/L4）分片整块锁，标了 `audience: local` 的 L0–L2 分片按 L3 对待、同样整块锁（与 gate、md 导出同一条规则）；人物不整人隐藏，基本/职业/喜好/非敏感关系照常显示，身体/病史/财务/共同计划/私密备注分区只出锁块、过敏/禁忌/密码等敏感条目注入前剔除。`local` 可显示 L3 明文，`--layers` 仅 local 同时过滤分片与实体；L4 默认不注入，仅 local+`--show-l4` 展开并红警示。cloud 永远 ≥L3 锁，即便传 L3/L4 也不出明文。缺文件/坏头/坏关系/幽灵边/空仓均 fail-closed 占位或提示，ME 坏头/未分级在 cloud 同样锁占位，不崩。
- inbox 草稿永不入图；唯一最新产物写 `exports/我的个人图谱.html`，脱敏版为固定的 `我的个人图谱-脱敏版.html`，均不进默认导出/zip。
- 何时生成：用户说"看看我的档案 / 人物关系图 / 我的画像"时生成，**只回报本地绝对路径**，不把敏感内容贴进对话；正式档案写入后，若已有图谱就重新生成这一份。健康表通过 `read_health_body` 合并结论层与过程层读取。
- 健康被动式：只在用户主动聊到忌口/营养/复查时，结合已授权的健康事实给一句必要提醒，不主动推送、不做临床营养治疗、不给治疗剂量。

---

## 8. 健康本地授权门与健康分片结构（v12 MVP）

### 8.1 `CONSENT-health.md`（数据仓根，人可读可删的纯 Markdown 授权记录）

独立于 L3 云门的**第一道本地开关**。frontmatter：

| 字段 | 取值 |
|---|---|
| `scope` | `full`（完整记录+解读）/ `facts_only`（只记事实，不做趋势/风险计数）/ `index_only`（只存原件本地索引，不出指标/结论/趋势）/ `off`（暂不记录） |
| `granted` | `true/false` |
| `granted_date` / `updated` | ISO 日期 |
| `source` | `user_session`（本轮仅此） |

缺文件 / `granted!=true` / `scope=off` = fail-closed：local 也不输出结构化健康。撤回（granted=false/off）立即生效、**不删除历史**，只停后续记录。`gate.py --check-consent` 只读回 scope/日期，不打印健康细节。

**读取侧裁剪契约（gate / viz / export 三条路径一致执行）**：
- `full`：完整输出。
- `facts_only`：只披露**安全事实小节**（过敏 / 在服药 / 慢病禁忌 / 饮食忌口，原文事实不加解读）；**剔除**最新指标表、趋势标签、机械计数/风险、结论与医嘱解读、历史快照、变化里程碑、原件索引。facts_only 的安全事实本身仍是 L3 敏感，cloud 未 `--confirm` 仍走 L3 HOLD（rc2、0 明文），只在 local 完整给安全事实。
- `index_only`：不出指标/结论/正文，仅留"仅存原件本地索引"提示。
- `off`/无授权：不含健康正文，仅一句未授权说明。优先级 `index_only < facts_only < full`。
- 健康授权只约束健康内容，**不是整份人物档案的白名单**：无健康内容的职业、爱好、称呼与非敏感关系，在 `off/index_only/facts_only` 下仍保留。首个分区前的简介和无分区扁平写法也保留；frontmatter 不因裁剪丢失。夹带健康信息的同一行仍保守裁剪，`facts_only` 只留下允许的安全子句；这不是通用语义识别，写入时应把非健康事实与健康事实分开行、分开区。
- 统一由 `mectx_common.consent_filtered_body(rel, body, cc)` 一道裁剪，**gate emit、export md、export zip 三条路径复用同一函数**，避免各写一套；scope≠full 时不仅裁剪 `profile/health.md`，也剔除 `entities/<人>.md` 的身体/备孕分区与 `network.md` 概览夹带的健康句（off/index_only 脱敏或省略），堵住"换 domain / 换导出路径绕过授权"。

### 8.2 health.md 结构（结论层，L3 / domain health / audience local）

免责语 → 授权状态指引 → **过敏/在服药/慢病禁忌（最高优先，用药前当次确认）** → **当前状态**（只写偏高/偏低/阳性等需要留意的项，不写数值）→ 明示诊断/既往 → 结论区（总检结论/医嘱/异常项 A·B 类/`followup_due`）→ 变化里程碑（confirmed 人话）→ 关注因子 → 体检原件本地路径索引（不进 cloud/导出）。

指标明细在过程层 `journal/health-metrics.md`：**最新关键指标表**（主表永远最新权威值；指标/数值/单位/本院参考区间/日期/机构/方法/采血条件/provenance）→ **历史快照（append-only，只增不改不覆盖）**。看板与趋势用 `read_health_body` 合并两份读取，结果与放在一个文件里时一致。

- 趋势标签（new/improved/worsened/persistent/fluctuating/resolved/followup_due）**读时由"最近一次 vs 本次"派生、不写死**，**三级置信**：
  - **high**：同院 + 同方法 + 同单位且两点可信（confirmed/doctor_diagnosed/imported_report；single_measurement/inferred 不驱动方向）→ improved/worsened；
  - **mid（跨院·仅供参考软方向）**：不同机构但标准化项（血脂/血糖/尿酸/肌酐/转氨酶/血压/体测）单位可换算或同单位、方法相容（含报告未写方法）→ 归一后仍给大致方向；跨院各自回到本院区间 → resolved·mid；
  - **none（不判方向）**：单位无法归一（μmol/L↔mg/dL 无换算表的项）/两方写明方法明显不同/非标准化项方法缺失（HbA1c·CK）/单次不可信。
  - 历史快照按日期排序，**比较基准取最近一次**（三年比最近两年），历点保留全部年份。练后高强度/脱水的 CK、ALT、AST、肌酐、UA 任何置信档都不标 worsened（两点静息的真持续升高仍正常判方向）。
- provenance 枚举预留：`imported_report | imported_ocr | declared_interview | doctor_diagnosed`（本轮无 PDF 自动导入，imported_report 由手填/人工录入携带）。
- 家人健康在各自 `entities/<id>.md` 独立小节，一人一份、各自 L3/provenance，不合并家庭总表。
