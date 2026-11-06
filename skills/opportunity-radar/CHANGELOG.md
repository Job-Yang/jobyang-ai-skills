# CHANGELOG

## 0.4.1 — 2026-10-20（宽召回，抓最新动态）

> 用户反馈：要「尽可能宽召回，严格筛选」，重点抓最新数据和业界动态。0.4.0 解决了
> 「没有召回」，0.4.1 解决「召回还不够宽、不够新」。

- 默认采集窗口从 3 天放宽到 5 天；每源容量 40 → 60。
- 新增三个「最新动态」源：`hf_models`（Hugging Face trending 模型，新能力发布）、
  `hn_front`（Hacker News 首页热议）、DEV/V2EX/Lobsters 改为「最新流 + 热门流」合并
  （DEV 最新 40 + 近一周热门 40；V2EX hot + latest；Lobsters hottest + newest）。
- 2026-10-20 实测：16 个源全部有数据，入池 486 条（0.4.0 为 339 条）。
- 筛选端不变：宽进严出仍由 dedup（硬重复）+ freshness（硬旗）+ 垂直镜头 + scorecard 把关。

## 0.4.0 — 2026-10-20（召回复盘驱动，大版本）

> 背景：连续多个工作日判「无强机会」。复查发现不是市场没机会，是漏斗入口太窄：
> 每天靠通用网页搜临时捞 4 条候选，GitHub/HF/HN/V2EX 等结构化源没有真正采集；
> freshness 把「无付费信号」「近亲」当硬旗一票否决；dedup 的 RELATED 阈值（0.18/4 词）
> 被「钱在流动/付费」这类跨条目通用词打穿，候选被判成历史近亲；轮换池 6 个方向里
> 3 个锚在云电脑不可达的信源，补位算法在缺 coverage 时天天补同一个方向。

- 新增 `scripts/collect.py`：14 个公开源的每日结构化采集（PH/hunted、GitHub Trending+新高星、
  Show HN/Ask HN/HN 评论许愿、HF Spaces、DEV、V2EX、Lobsters、Reddit RSS、App Store 畅销榜），
  纯标准库、并发、逐源容错，产出 pool.json + pool.md。2026-10-20 实测稳定采集 250 条上下，
  原始候选量从约 4 条提到 200+ 条。
- `scripts/dedup.py`：RELATED 阈值 0.18/4 词收紧到 0.25/8 词；新增中文停用词表和
  df 折扣（≥40% 历史条目出现的词不计交集）；同域名判 DUP 的重合线从 0.18 提到 0.40，
  避免同一网站的不同文章被当重复。修复「闲鱼/知识付费」这类不同方向被通用词误判近亲。
- `scripts/freshness.py`：旗分软硬两层。硬旗（旧证据、未来日期、垃圾源、坏链接、DUP）
  挡候选；软旗（无日期、付费信号未验证、RELATED）只提醒补证，不再埋掉新供给。
  新上的 Show HN/GitHub 项目天然没付费信号，过去被这一条团灭。
- `references/rotation-pool.json` 升 v2：从 6 个方法/痛点主题改成 10 个垂直人群镜头
  （开发者、知识工作、创作者、本地小生意、财税法务、健康家庭、教育、电商、个人大事、
  中文代服务）+ 2 个方法道（许愿原话、新发布差评），每个镜头带 lens/keywords/queries。
- `references/sources.md`：重写为「自动采集源 + 云电脑实测不可达源」两张表，
  Reddit JSON/X/即刻/小红书/G2/Google Trends 的坑写死，不再每天白搜。
- rotate.py 输出带 lens/keywords，兼容 v2 池（sources 字段可选）。
- 测试：全部 30 条通过（2 条历史遗留 skip）。dedup/freshness 断言按新契约更新，
  09-28/10-12 近亲用例仍判 RELATED，10-16 旧愿仍被硬旗挡住，幂等 DUP 行为不变。

## 0.3.1 — 2026-10-16

> 本轮由 2026-10-16 真实每日运行驱动（结论：无强机会；文档留痕成功；群卡片被 im scope/bot 不在群 230002 挡掉）。把运行经验从"靠 Agent 自觉"变成脚本契约。

- 新增 `scripts/dedup.py`：与历史追踪台去重脚本化。输入历史 markdown + 今日候选 JSON，每条判 NEW/DUP/RELATED 并给出命中历史条目；退出码 4 = 全 DUP/RELATED（安静日信号）。fixture 三条历史（2026-09-28 语音直达 / 2026-10-12 浏览器 Agent 确认层 / 2026-10-16 无强机会记录）+ 今日候选，回归 6 条：proactive 助手判 RELATED→09-28、MGX 烧积分判 RELATED→10-12，次日再扫同一信号判 DUP（幂等）。
- 新增 `scripts/freshness.py`：证据对抗自检。半年前旧愿（>180 天）降级、无付费信号降标题党、垃圾源（imtqy.com）换源、接 dedup 的近亲不深挖；回归 4 条，合跑复现"今天无一条可立"。
- 新增 `scripts/paginate.py`：候选超量分页分包。manifest + pageNNN（每页 ≤20），split/merge，每页过冻结版信封校验；回归 3 条。
- 新增 `scripts/rotate.py` + `references/rotation-pool.json`：方向轮换确定性算法，按日期+历史覆盖选今天扫哪两个方向，周期内覆盖不重复；回归 5 条。
- 新增 `scripts/preflight.py` + `references/cards.json`：进场自诊断与留痕三分支——文档可写+群可发=full；群不可发（230002）=degrade-docs（只文档留痕+回报 blocker，确定性分支不临场发挥）；文档不可写=block。无强机会/强机会卡片模板渲染校验；回归 6 条。
- 新增 `scripts/check_handoff.py`：三包 handoff 示例 opc_node drift 检查（防 radar 写成 prd 复发）。
- 新增端到端回归 `tests/test_e2e_handoff.py`：合成 radar 候选 → scorecard 出卡 → brief 模板渲染，全过冻结信封。
- 文档：SKILL.md 加"每日运行契约"节（调度归宿主，技能只管产出与留痕契约）；目录结构与维护说明同步。

## 0.3.0 — 2026-10-16

- 修复：`references/handoff.md` 信封示例误写 `opc_node: prd`，改为本节点 `opc_node: radar`、`artifact_kind: radar`、`topic: null`（原诊断 P1：按旧示例产的雷达文档会被当成 prd 校验并拒）。
- 修复：SKILL.md"文件名随便叫"与 artifact_io ingest 强制 canonical 命名自相矛盾。现在写明远端文件名任意、本地 ingest 强制 `radar-<created 日期>.md`；radar topic 恒为 null，同日多份靠不同 `--output-root` 分目录区分，同名异内容拒绝覆盖（原诊断 P1）。
- 新增：`references/golden-signals.md` 补"信号强/中/弱"映射表（强=付费流向+差评量+Trends 斜率三证齐，中=两证，弱=一证）、非 solo/团队用户适配段、蓝海陷阱反例 3 条（单事件驱动、无人付钱的无人区、无具体场景的泛抱怨）（原诊断 P1/P2）。
- 新增：vendoring 落地。`scripts/check_vendored.py` 与 `scripts/vendor-manifest.json`（opc-envelope 0.2.0），SKILL.md 维护说明加发布前自检与 `--drift` 跨包无漂移检查。
- 重构：版本口径分离。信封 schema 版本 0.2.0（冻结 artifact_io seal 出）与 kit 版本 0.3.0 不再混用；description 重写为前 50 字自包含（做什么+何时用+边界）；frontmatter 只留 name/description。
