## 0.5.0 — 2026-10-31

新增病灶编码 M「正文里自加免责」，`loop version` 仍第 3 版（答案格式、状态文档格式不变，只多认一个编码）：
- 来源：同事在 Codex 上的加载/消融实验，GPT-6 Astra 加载 haohao-shuohua 时 12 条回答里 7 条在正文后面加了「以上仅依据……未做额外核验」这类话，不加载时 0 条。原来的病灶谱只有 U 罚「该提醒没提醒」，没有反方向的编码，每日召回抓不到这种病。
- `const.py`：CODES 加 M，归入 MINOR（没改好，门禁里「新毛病不许变多」一并管）；SEVERITY 排在 H 之后；新增机器旗标「自加免责」，用与 haohao-shuohua `quick_scan.py --checks disclaim` 同一份正则，只查正文、只报原文和上下文里没有的说法。
- `judge.py`：M 必须带改写引用；引用的是原文本来就有的话时作废。
- 文档：badcase-taxonomy、judge-protocol、gates-and-release、item-sources（新增两种陷阱）、SKILL.md、README 同步。
- 新增测试 `test_self_added_disclaimer_is_m`：流程/单元 22 个 + 对抗 11 个，全部通过。

## 0.4.8 — 2026-10-24

不改协议（`loop version` 仍第 3 版）。三个改进都针对每日召回里暴露的机制问题，保持多人扩展兼容：

- **体检题自动去重。** `start` 处理开着的重复题，`decide` 处理新软分歧。
  同一历史材料、文体、问题编码、原文和改写片段全部一致才沿用作者亲口回答；
  跨工具仅沿用「有」，不把局部「没有」推成另一份整稿全绿。D22 与 D16 符合；
  D23 与 D5 改法不同，不自动套。冲突的最新人工判断、相似原句、超时和自动答案均不作依据。
  自动处理不复制进判例库，保留可追溯的 auto 记录。普通争议匹配规则未改。
- **手改稿字面对照。** 新增 `scripts/hh_eval/manualdiff.py`：核对作者纯删除片段、
  完整保留句和替换新片段，记录我们是否纯删除、是否改动保留句、是否命中新片段。
  不把低相似度当删除，不把原样不改的高相似度当「跟上」，不计作废或不可出题种子。
  聚合进当天 metrics、日报及记录表；只是文字动作观察，不代表改对、学会或规则效果，不进门禁。
- **盲测护栏写进 daily-loop。** 改写阶段不许打开 `data/manual_edits.json` 和 `target.json`
  （种子题只给原文，作者动作和「改成」不能看）；裁判阶段不许回 items/private/种子库/target 翻答案。
- 顺带修一处口径不一致：召回文档「待你判断」表里的「先看」以前按「今天新问」标，
  跟日报按争议类型排序的前 3 条对不上；现在两处统一按争议优先级取前 N 条。
- 顺带补一个指纹漏洞：`eval_skill` 指纹以前只算 `scripts/*.py`（薄入口），漏了 `scripts/hh_eval/` 包里
  的实现模块，包内代码被改 decide 的中途漂移检测发现不了；现在包内 `.py` 一并入指纹。
- 份数口径拆清：实际改写份数与纳入主指标份数分列。主指标只含 fresh/regression，
  探针、留出题和干净对照另有用途，不再把指标分母误写成总工作量。
- 测试：新增 2 个端到端测试（体检去重两条路径、手改稿对照端到端+句级口径）、1 个指纹单元测试，
  记录排序口径测试扩展；21 个流程/单元测试 + 11 个对抗测试全部通过，无跳过。
  对抗反例含：同句不同改法不套判、跨工具绿判断不外推、不动稿不计跟改、无关重写不计全删。
  缺 scipy 分支使用隔离 site-packages 的子进程实际覆盖；测试文件资源警告已修复。

## 0.4.7 — 2026-10-24

不改协议（`loop version` 仍第 3 版），不改代码：

- 合并 Mac 侧新加的 `README.md`（技能来历、判法、怎么迭代、自知的边界）和 `assets/daily-loop.{svg,png}`、`daily-loop-narrow.png`（每日召回闭环图）。
- README 里两处跟现状对不上的说法顺手改正：手改种子从「首批 13 条」改为写明 0.4.5 的作废与重建（17 条，10 条进题、7 条只作边界）；测试口径从「16+9（0.4.3 记）」改为「18+9（0.4.7 记）」。
- 背景同 0.4.6：Mac 侧同步上来的包仍是 0.4.3 代码（只多了 README 和图），云电脑开机又被解包回旧版，不认 `--manual-seeds`。本版 = 0.4.6 + Mac 新增文件，合回 Mac 权威仓后四处才能一致。

## 0.4.6 — 2026-10-23

不改协议（`loop version` 仍第 3 版），不改代码：

- 合并 Mac 侧对 SKILL.md 描述的改动（加两句触发示例：「跑一轮好好说话召回」「今天的召回结果怎么样」）。
- 背景：云电脑开机按技能包最新版本解包。Mac 侧同步上来的包还是 0.4.3（只多了这句描述），盖掉了云端已提交的 0.4.4/0.4.5，
  当天召回差点用旧代码跑（旧代码不认 `--manual-seeds`，也没有作废种子驱逐）。本版 = 0.4.5 全部改动 + 这句描述，
  需要合回 Mac 权威仓后再同步，四处才能一致。

## 0.4.5 — 2026-10-22

手改种子库勘误重建，不改协议（`loop version` 仍第 3 版）：
- 首批 M001–M013 是从修订模式截图转录的，多处把删除线+插入的改前改后并排误读成错别字或段内重复，
  M007/M010/M013 把作者新增/删除方向记反（「振聋发聩」段实为作者回源新增；
  「把我值多少钱拿回自己手里」整段实为作者删除）。全部标记作废并写明原因。
- 新种子 M014–M030 以文档历史版本逐字 diff 为准（洗稿后 rev20/29 → 作者定稿 rev399），
  洗稿原句、改成、上文全部逐字断言在对应版本里。其中可复制的 10 条（M014–M023）进每日题；
  作者回源原话、内容取舍、观点强弱调整 7 条（M024–M030）标「可出题：false」，只作边界输入。
- `manual_seed_pool` 只取 seed 且可出题 true、完整段落、无省略号；出题透传种子的「上下文」（跨段重复题裁判需要上文）。
- `decide` 增加作废种子召回驱逐：库里作废或可出题 false 的种子，其历史召回（题号 mNN 或来源标注）自动移出问题池，
  新入池也拦截，并在作者日志留痕。10-22 由作废 M007 误产的 R·套话 召回据此撤销。
- 测试同步更新（含逐字断言与驱逐端到端测试），18+9 测试全绿。

## 0.4.4 — 2026-10-21

不改协议（`loop version` 仍第 3 版）：
- 手改种子库接进每日出题：`loop start --manual-seeds N` 从 `data/manual_edits.json` 按天轮转取 N 条，
  作为普通 fresh 合成题进当天改写和盲评；题面只有「洗稿原句」，作者动作、rule_signal 不带入，
  裁判看不到答案。N 默认 0，云端每日召回固定传 3（`daily.manual_seeds` 配置项）。
  种子标「可出题：false」不参与（M009/M011 是元描述，没有可用原句）。
- 新增端到端测试 1 个（轮转、不泄露答案、可出题开关、不带参数不加题），17+9 测试全绿。

## 0.4.3 — 2026-10-20

只改文案，不改协议（`loop version` 仍第 3 版）：
- 召回文档最后一节标题「每日召回记录」→「每日迭代日志」（const.SECTION_TITLE 及测试、
  daily-loop.md、SKILL.md 同步；线上文档 H1 已改名，旧名零残留）。
- 各分支 headline/提示去机器话：体检没过、规则被作者改过、病灶不够数，都改成
  「今天照常召回 / 你的改动原样保留 / 先攒着不出新规则」这类人话，不再出现
  「只召回不出候选」「daily-learning.md 指纹」等内部词。16+9 测试全绿。

## 0.4.2 — 2026-10-20

新增数据资产，不改代码、不改协议（`loop version` 仍第 3 版）：
- `data/manual_edits.json`：作者手工批改种子库（首批 13 条，来自《孙学、薄肌、黄毛、大水》
  一轮真实批改）。每条含病灶码、洗稿原句、作者动作、作者理由、**去场景化的通用 rule_signal**
  与反例风险；强制规则信号不得含任何只对本文体有效的词。
- 明确边界：只在已有文本上清洗，不回源、不考据；材料本身只有二手信息时不新增一手引语。
- 转化路径：同类 signal 跨文体跨天攒证据 → 进每日召回出题/盲评 → 胜出且作者拍板后
  才进细则/判据。未验证前不改主技能。

# CHANGELOG

## 0.4.1 — 2026-10-20

流程文档更新，不改代码、不改门禁：
- daily-loop.md 新增「汇报节奏（长期项目，作者是老板）」：每日四段式播报固定回答
  「技能有没有变好/我做了什么/需要你做什么/明天做什么」，只说确定的事；
  攒够一类问题就带具体方案找作者拍板，作者 OK 直接改，手工改动并入同批方案；
  每周一补周度汇报（数字+案例+待拍板清单+下周计划）。
- 作者随手发的片段和手写改动：先体会修改意图、原话进判例库，再说明吸收后的后续动作
  （变候选细则 / 判例 / 扩题池），不许只回"收到"。

## 0.4.0 — 2026-10-20

向后兼容：`loop version` 输出逐字不变（仍是第 3 版协议）；状态文档/召回文档读写协议、
`state dump/load/check` 数据格式、门禁语义与默认阈值全部不变；16 个 unittest + 9 个对抗测试通过
（其中 fit_weights 缺依赖用例在已装 scipy 的环境改为跳过——它验的是「没装 scipy 时给人话提示」）。

改的是「给作者看的层」，不动召回判定逻辑：
- 每日记录（doc record 产出）从一大段段落改成四张飞书表格：①今天的数据（改写份数/改坏/编造/
  残留/干净稿误改/裁判体检）；②新召回（类型×数量、文体、原文、改成、裁判说明）；
  ③今天记下的回话（编号/原话两列，不再截断成 80 字挤成一段）；
  ④待你判断：一张表列全部 open 的题，今天新问的标「先看」、其余标「排队」，
  题号、类型、原文、改写、拿不准的点、是非题、判断槽位各占一列。
  历史「Dxx 你的判断：＿＿」槽位格式一字未改，doc read 对表格槽位和旧段落槽位都认；
  已验证：空白槽不被误解析、填「有/没有/跳过+理由」往返解析正确。
- 「细则被手工改过：今天只召回，等你确认」这条内部标题改成作者看得懂的话：
  「发现你手工改过细则：今天只做召回，改动已保留，等你下次确认」；start 的注意事项同步说清
  为什么不出候选、改动不会被盖掉、怎么确认。判定逻辑（哈希对不上就不出候选、不发布）不变。
- daily-loop.md 第九步「在任务对话里说一声」重写为四段式播报：结论（大白话）/ 你今天要做什么
  （几条、先看哪几条、可直接在对话回 Dxx 有）/ 我今天做了什么（份数与新召回类型）/ 状态
  （只说跟作者有关的）。不再向作者发「状态已存：第 N 份」、revision、sha、运行目录。

修复：
- test_adversarial.py 的 fit_weights 用例在云端（已装 scipy 1.x）必失败：用 importlib.util.find_spec
  判环境，装了就跳过，缺依赖时仍跑原断言。

## 0.2.0 — 2026-10-16

向后兼容：状态文档数据格式与跨天状态机读写不变，`loop version` 输出逐字不变（第 3 版协议），
线上 Mira 定时任务无需改配置即可继续跑；15 个既有 unittest 全部继续通过，另新增 1 个回归测试。

修复：
- 废弃统一分管线拆净：scorer.py 文件头与「合成统一分」段落加醒目废弃横幅；`--unified` / `--calibrate`
  改为打印废弃提示不再出分；fit_weights.py 缺 scipy 时给人话报错而不是裸 ModuleNotFoundError。
  （对应诊断 P1：废弃未执行干净、依赖零声明。）
- build_labels.py 去掉硬编码的宿主会话绝对路径：默认输出定位到本包 data/labels.json，
  支持 `HAOHAO_EVAL_LABELS_OUT` 环境变量与 `--out` 参数覆盖；该脚本是离线构建脚本，不进每日流程。
  （对应诊断 P0：他机绝对路径。）
- BadCase 母表 token 不再只靠硬编码：新增 `badcase_source()`，环境变量
  `HAOHAO_EVAL_BADCASE_BASE` / `HAOHAO_EVAL_BADCASE_TABLE` 优先；都没配置时 `loop start` 打印
  明确提示（不阻断当天流程）。默认配置值不变，线上任务行为不变。
- state.json 损坏时退出码 2 加人话报错，不再抛 traceback，也不自动删文件。

新增：
- `requirements-optional.txt`：注明 scipy/numpy 只有已废弃的 fit_weights.py 需要，每日 loop 纯标准库。
- `data/archive/README.md`：fitted_weights.json 移入归档，写明为什么禁止重跑拟合。
- references/daily-loop.md 新增「离线降级」一节：无飞书/lark-cli 时哪些当天功能可跑、哪些跨天功能不可用。
- references/gates-and-release.md 新增小样本诚实声明：clean_seed 仅 5 条、clean_edit_slack=0.05 是启发式
  粗闸不是统计检验；sign test 适用前提写清；体检题池约 17 天重复的事实写明。
- scripts/test_loop.py 新增 test_corrupt_state_file_stops_cleanly。

重构：
- find_shuohua_dir：环境变量 `HAOHAO_SHUOHUA_DIR` 兜底 + 从技能目录逐级向上找兄弟目录，应对包结构搬家；
  原有候选根目录保留。
- Lock 加注释：mtime 6 小时粗判是有意为之（平台数据目录每天是新容器，fcntl 锁跨不住昨天）。
- SKILL.md：description 前 50 字自包含（做什么+何时用+不适用）；「历史评分尺」补「为什么废弃」方法论说明
  （循环自证：单人 50 标签 / 自评赢 70% / 自洽率 48%）；frontmatter 只留 name/description。

## 0.3.0 — 2026-10-16

向后兼容（红线全部守住）：`loop version` 输出逐字不变（仍是「haohao-eval 第 3 版：……」）；
飞书状态文档/召回文档的 XML 格式与读写协议零改动；旧数据目录布局逐字节兼容；
`python3 loop.py <旧命令>` 全部照旧。16 个既有 unittest 一个字没改继续全绿，
另新增 9 个对抗式回归测试。

重构（最大工程债）：
- 3035 行单文件 `scripts/loop.py` 拆成 `scripts/hh_eval/` 包（13 个模块：const/fs/judge/seed/
  fp/rules/gates/statedoc/docdoc/pipeline/preflight/cli），`loop.py` 薄化为 30 行兼容入口
  （全量再导出 + main）。拆分前后用同一组 fixture 在新旧两棵树上逐命令比对
  stdout/exit/产物 sha256，全部一致。

新增：
- `loop preflight`：进场结构化自诊断——版本不是第 3 版就停；技能目录缺失给
  `--shuohua-dir` 提示；状态/召回文档文件坏 JSON 或无权限时按「数据没接上：原始报错」
  停，绝不 init；`--json` 输出机器可判的 ready/offline_ok/online_ok（便于 cron/云电脑）。
- `--data-root` / `HAOHAO_EVAL_DATA_ROOT`：测试与云电脑隔离用——设了它，eval 数据目录和
  细则发布目录一起挪到根下；不设时一切照旧。修掉一个真 bug：旧版只重设
  `HAOHAO_EVAL_HOME` 不设 `XDG_DATA_HOME` 时，`state load` 仍会把用户全局
  `~/.local/share/haohao-shuohua/daily-learning.md` 改名 .bak。
- `HAOHAO_EVAL_LARK`（飞书 CLI 命令名）与 `HAOHAO_EVAL_SKILL_DIR`（技能根目录）可配置，
  默认值与线上不变。
- `scripts/label_agreement.py`：多人标注一致性工具（CSV 长表 → pairwise 一致率 + Cohen
  kappa + 分歧导出模板），为「50 条单人标签」的扩样打底；诚实声明印在文件头。
- 门禁小样本结论显式降级：clean n<10 或 discordant<10 时，相关比较结果作为「观察项」
  写进 decision.json 的 `observations` 字段并在日报打印，不进 pass/fail 判定。门禁门槛
  与判定逻辑一字未动。
- `scripts/test_adversarial.py`：9 个对抗测试——损坏状态 JSON、sha 对不上、召回文档缺节、
  裁判引用找不到/伪造引用、同一天重复跑幂等、data-root 不碰全局目录、preflight 坏文档
  即停、observations 落盘、fit_weights 缺 scipy 人话提示。

## 0.4.4 — 2026-10-21

不改协议（`loop version` 仍第 3 版）：
- 手改种子库接进每日出题：`loop start --manual-seeds N` 从 `data/manual_edits.json` 按天轮转取 N 条，
  作为普通 fresh 合成题进当天改写和盲评；题面只有「洗稿原句」，作者动作、rule_signal 不带入，
  裁判看不到答案。N 默认 0，云端每日召回固定传 3（`daily.manual_seeds` 配置项）。
  种子标「可出题：false」不参与（M009/M011 是元描述，没有可用原句）。
- 新增端到端测试 1 个（轮转、不泄露答案、可出题开关、不带参数不加题），17+9 测试全绿。

## 0.4.3 — 2026-10-20

只改文案，不改协议（`loop version` 仍第 3 版）：
- 召回文档最后一节标题「每日召回记录」→「每日迭代日志」（const.SECTION_TITLE 及测试、
  daily-loop.md、SKILL.md 同步；线上文档 H1 已改名，旧名零残留）。
- 各分支 headline/提示去机器话：体检没过、规则被作者改过、病灶不够数，都改成
  「今天照常召回 / 你的改动原样保留 / 先攒着不出新规则」这类人话，不再出现
  「只召回不出候选」「daily-learning.md 指纹」等内部词。16+9 测试全绿。

## 0.4.2 — 2026-10-20

新增数据资产，不改代码、不改协议（`loop version` 仍第 3 版）：
- `data/manual_edits.json`：作者手工批改种子库（首批 13 条，来自《孙学、薄肌、黄毛、大水》
  一轮真实批改）。每条含病灶码、洗稿原句、作者动作、作者理由、**去场景化的通用 rule_signal**
  与反例风险；强制规则信号不得含任何只对本文体有效的词。
- 明确边界：只在已有文本上清洗，不回源、不考据；材料本身只有二手信息时不新增一手引语。
- 转化路径：同类 signal 跨文体跨天攒证据 → 进每日召回出题/盲评 → 胜出且作者拍板后
  才进细则/判据。未验证前不改主技能。

# CHANGELOG

## 0.4.1 — 2026-10-20

流程文档更新，不改代码、不改门禁：
- daily-loop.md 新增「汇报节奏（长期项目，作者是老板）」：每日四段式播报固定回答
  「技能有没有变好/我做了什么/需要你做什么/明天做什么」，只说确定的事；
  攒够一类问题就带具体方案找作者拍板，作者 OK 直接改，手工改动并入同批方案；
  每周一补周度汇报（数字+案例+待拍板清单+下周计划）。
- 作者随手发的片段和手写改动：先体会修改意图、原话进判例库，再说明吸收后的后续动作
  （变候选细则 / 判例 / 扩题池），不许只回"收到"。

## 0.4.0 — 2026-10-20

向后兼容：`loop version` 输出逐字不变（仍是第 3 版协议）；状态文档/召回文档读写协议、
`state dump/load/check` 数据格式、门禁语义与默认阈值全部不变；16 个 unittest + 9 个对抗测试通过
（其中 fit_weights 缺依赖用例在已装 scipy 的环境改为跳过——它验的是「没装 scipy 时给人话提示」）。

改的是「给作者看的层」，不动召回判定逻辑：
- 每日记录（doc record 产出）从一大段段落改成四张飞书表格：①今天的数据（改写份数/改坏/编造/
  残留/干净稿误改/裁判体检）；②新召回（类型×数量、文体、原文、改成、裁判说明）；
  ③今天记下的回话（编号/原话两列，不再截断成 80 字挤成一段）；
  ④待你判断：一张表列全部 open 的题，今天新问的标「先看」、其余标「排队」，
  题号、类型、原文、改写、拿不准的点、是非题、判断槽位各占一列。
  历史「Dxx 你的判断：＿＿」槽位格式一字未改，doc read 对表格槽位和旧段落槽位都认；
  已验证：空白槽不被误解析、填「有/没有/跳过+理由」往返解析正确。
- 「细则被手工改过：今天只召回，等你确认」这条内部标题改成作者看得懂的话：
  「发现你手工改过细则：今天只做召回，改动已保留，等你下次确认」；start 的注意事项同步说清
  为什么不出候选、改动不会被盖掉、怎么确认。判定逻辑（哈希对不上就不出候选、不发布）不变。
- daily-loop.md 第九步「在任务对话里说一声」重写为四段式播报：结论（大白话）/ 你今天要做什么
  （几条、先看哪几条、可直接在对话回 Dxx 有）/ 我今天做了什么（份数与新召回类型）/ 状态
  （只说跟作者有关的）。不再向作者发「状态已存：第 N 份」、revision、sha、运行目录。

修复：
- test_adversarial.py 的 fit_weights 用例在云端（已装 scipy 1.x）必失败：用 importlib.util.find_spec
  判环境，装了就跳过，缺依赖时仍跑原断言。

## 0.2.0 — 2026-10-16

向后兼容：状态文档数据格式与跨天状态机读写不变，`loop version` 输出逐字不变（第 3 版协议），
线上 Mira 定时任务无需改配置即可继续跑；15 个既有 unittest 全部继续通过，另新增 1 个回归测试。

修复：
- 废弃统一分管线拆净：scorer.py 文件头与「合成统一分」段落加醒目废弃横幅；`--unified` / `--calibrate`
  改为打印废弃提示不再出分；fit_weights.py 缺 scipy 时给人话报错而不是裸 ModuleNotFoundError。
  （对应诊断 P1：废弃未执行干净、依赖零声明。）
- build_labels.py 去掉硬编码的宿主会话绝对路径：默认输出定位到本包 data/labels.json，
  支持 `HAOHAO_EVAL_LABELS_OUT` 环境变量与 `--out` 参数覆盖；该脚本是离线构建脚本，不进每日流程。
  （对应诊断 P0：他机绝对路径。）
- BadCase 母表 token 不再只靠硬编码：新增 `badcase_source()`，环境变量
  `HAOHAO_EVAL_BADCASE_BASE` / `HAOHAO_EVAL_BADCASE_TABLE` 优先；都没配置时 `loop start` 打印
  明确提示（不阻断当天流程）。默认配置值不变，线上任务行为不变。
- state.json 损坏时退出码 2 加人话报错，不再抛 traceback，也不自动删文件。

新增：
- `requirements-optional.txt`：注明 scipy/numpy 只有已废弃的 fit_weights.py 需要，每日 loop 纯标准库。
- `data/archive/README.md`：fitted_weights.json 移入归档，写明为什么禁止重跑拟合。
- references/daily-loop.md 新增「离线降级」一节：无飞书/lark-cli 时哪些当天功能可跑、哪些跨天功能不可用。
- references/gates-and-release.md 新增小样本诚实声明：clean_seed 仅 5 条、clean_edit_slack=0.05 是启发式
  粗闸不是统计检验；sign test 适用前提写清；体检题池约 17 天重复的事实写明。
- scripts/test_loop.py 新增 test_corrupt_state_file_stops_cleanly。

重构：
- find_shuohua_dir：环境变量 `HAOHAO_SHUOHUA_DIR` 兜底 + 从技能目录逐级向上找兄弟目录，应对包结构搬家；
  原有候选根目录保留。
- Lock 加注释：mtime 6 小时粗判是有意为之（平台数据目录每天是新容器，fcntl 锁跨不住昨天）。
- SKILL.md：description 前 50 字自包含（做什么+何时用+不适用）；「历史评分尺」补「为什么废弃」方法论说明
  （循环自证：单人 50 标签 / 自评赢 70% / 自洽率 48%）；frontmatter 只留 name/description。

## 0.3.0 — 2026-10-16

向后兼容（红线全部守住）：`loop version` 输出逐字不变（仍是「haohao-eval 第 3 版：……」）；
飞书状态文档/召回文档的 XML 格式与读写协议零改动；旧数据目录布局逐字节兼容；
`python3 loop.py <旧命令>` 全部照旧。16 个既有 unittest 一个字没改继续全绿，
另新增 9 个对抗式回归测试。

重构（最大工程债）：
- 3035 行单文件 `scripts/loop.py` 拆成 `scripts/hh_eval/` 包（13 个模块：const/fs/judge/seed/
  fp/rules/gates/statedoc/docdoc/pipeline/preflight/cli），`loop.py` 薄化为 30 行兼容入口
  （全量再导出 + main）。拆分前后用同一组 fixture 在新旧两棵树上逐命令比对
  stdout/exit/产物 sha256，全部一致。

新增：
- `loop preflight`：进场结构化自诊断——版本不是第 3 版就停；技能目录缺失给
  `--shuohua-dir` 提示；状态/召回文档文件坏 JSON 或无权限时按「数据没接上：原始报错」
  停，绝不 init；`--json` 输出机器可判的 ready/offline_ok/online_ok（便于 cron/云电脑）。
- `--data-root` / `HAOHAO_EVAL_DATA_ROOT`：测试与云电脑隔离用——设了它，eval 数据目录和
  细则发布目录一起挪到根下；不设时一切照旧。修掉一个真 bug：旧版只重设
  `HAOHAO_EVAL_HOME` 不设 `XDG_DATA_HOME` 时，`state load` 仍会把用户全局
  `~/.local/share/haohao-shuohua/daily-learning.md` 改名 .bak。
- `HAOHAO_EVAL_LARK`（飞书 CLI 命令名）与 `HAOHAO_EVAL_SKILL_DIR`（技能根目录）可配置，
  默认值与线上不变。
- `scripts/label_agreement.py`：多人标注一致性工具（CSV 长表 → pairwise 一致率 + Cohen
  kappa + 分歧导出模板），为「50 条单人标签」的扩样打底；诚实声明印在文件头。
- 门禁小样本结论显式降级：clean n<10 或 discordant<10 时，相关比较结果作为「观察项」
  写进 decision.json 的 `observations` 字段并在日报打印，不进 pass/fail 判定。门禁门槛
  与判定逻辑一字未动。
- `scripts/test_adversarial.py`：9 个对抗测试——损坏状态 JSON、sha 对不上、召回文档缺节、
  裁判引用找不到/伪造引用、同一天重复跑幂等、data-root 不碰全局目录、preflight 坏文档
  即停、observations 落盘、fit_weights 缺 scipy 人话提示。
