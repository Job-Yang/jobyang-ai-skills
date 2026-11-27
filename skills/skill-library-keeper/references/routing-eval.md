# 活卷路由盲测与真实翻车回归指南

> **定位：** 路由评测只做「分诊台体检雷达」——只查漏触、边界互抢、轻任务误触与双模抖动，不替代真实任务端到端体验判断。
> **核心反刷分纪律：** 只存考纲（`blueprint`）与真实翻车池，不固化 AI 批量编造的死题库；改完技能后必须换全新活卷与新随机序复验。

## 一、四条反刷分铁律

1. **只存考纲，不存 AI 死卷：** 不把模型一次编出来的几十道“测试题”固化成长期跑分题库。每次由 `route_eval.py blueprint` 根据当前技能库实时抽出中立索引与抽考蓝图，考完即弃。
2. **出题与答题严格隔离：** 出题代理只能看见蓝图与防泄题约束，生成自然口语活题后先过 `route_eval.py audit --export-blind`（去掉全部标签，拦截 `SKILL.md`、英文 slug 与原样照抄引号样例），答题代理只看纯中立 `name + description` 与盲测题单。
3. **改后换卷 + 双序盲测：** 根据体检雷达修完技能描述后，严禁拿上一轮原卷复跑验收；必须用新随机种子打乱目录顺序并重新出一批新口语活题。同一技能集同时在强/弱两档模型、不同目录排序下盲测，暴露位置偏置与抖动。
4. **不输出综合总分：** `score` 故意不计算加权总分或 GPA，防止优化目标退化成“把通过率刷到 100%”而往 `description` 里堆砌关键词（同时受 `library_doctor.py` 的 `B001/B002` 字数预算限制）。

## 二、标准操作流（零配置宿主子代理为主，可选 HTTP）

### 1. 先证尺子，再生成中立目录与蓝图

```bash
python3 scripts/test_route_eval.py
python3 scripts/route_eval.py blueprint <技能库目录> --shuffle --seed 101 --out-catalog /tmp/cat-a.json --out-blueprint /tmp/bp.json
python3 scripts/route_eval.py blueprint <技能库目录> --shuffle --seed 202 --out-catalog /tmp/cat-b.json
```

`blueprint` 导出目录时彻底剥离 `SKILL.md` 正文与参考文件，仅保留 `name` 与 `description`，并自动识别三类高风险邻居对：描述中互相点名的边界对、同组技能（若仓内存在可选分组配置）以及描述文本高重合技能对。

### 2. 现出活卷并审计脱敏

让独立出题代理（或人工）按 `/tmp/bp.json` 生成临时活卷（`positive`、`boundary`、`negative`、`handoff`），注意：
- 每个 `target_skills` 至少 1 条日常口语正例；
- `neighbor_pairs` 挑高频混淆对写 `boundary` 用例，显式列出 `forbidden`，不填 `acceptable`；
- `negative` 必须 `expected: "NONE"`，覆盖闲聊、短译、单句微改、基础名词解释等轻任务；
- 为 `paraphrase_targets` 配 2 种截然不同口语说法（填同一 `paraphrase_group`）；
- 活卷须掺入 ≤35 字真实短口语题，避免保姆式长题干失真（中位数 >55 字会触发 `A008` 低优提醒）。

把临时活卷与仓库自维护的 `real-badcases` 合并后跑强审计并导出盲测题单：

```bash
python3 scripts/route_eval.py audit /tmp/probe-cases.jsonl <技能库目录> --strict --export-blind /tmp/blind.jsonl
```

审计规则 `A001–A008` 拦截格式错误、悬空技能名、负例/边界标错、`query` 含目标 slug/内部文件名（`A004`）、原样照抄 `description` 引号触发样例（`A005`）、覆盖缺口（`A006`）、缺少轻任务负例（`A007`），并对保姆式长题干给出 `A008` 低优提醒。

### 3. 双模盲选与体检雷达

**方式 A（推荐，零配置）：** 在当前宿主开 2–3 个干净上下文只读子代理（分别用强模型跑 A/B 两份不同乱序目录，用较弱模型跑 A 目录），只允许读取各自 `cat-*.json` 与 `/tmp/blind.jsonl`，逐题输出 `{"id", "selected", "reason"}`。

**方式 B（可选命令行批量 Runner）：** 配置 `ROUTE_EVAL_BASE_URL`、`ROUTE_EVAL_API_KEY`、`ROUTE_EVAL_MODEL` 后执行（缺配置时安全退出提示改用方式 A）：

```bash
python3 scripts/route_eval.py run /tmp/cat-a.json /tmp/blind.jsonl --out /tmp/pred-a.jsonl
```

最后聚合输出五类体检警报：

```bash
python3 scripts/route_eval.py score /tmp/probe-cases.jsonl /tmp/pred-pro-a.jsonl /tmp/pred-pro-b.jsonl --root <技能库目录> --model-label Pro
python3 scripts/route_eval.py score /tmp/probe-cases.jsonl /tmp/pred-flash-a.jsonl --root <技能库目录> --model-label Flash
```

重点盯五类信号：**漏触清单**、**边界互抢混淆矩阵（尤其 `forbidden` 误抢）**、**轻任务误触源**、**多轮 `pass^k` 抖动与同义改写不一致**、**真实翻车回归状态**。

## 三、真实翻车回流池维护规则

- 仓库可单独维护一份精简的真实病例文件（如仓库根 `evals/real-badcases.jsonl`），**只收真实会话里确实踩过的错路由/漏触发/覆盖真空**，严禁由 AI 为凑覆盖率编造静态假题写入。
- 每条记录使用 `category: "real-badcase"` 与真实来源 `source`；若历史真实用户原话恰巧点出了某个英文技能名，仅可在该类记录显式加 `"allow_literal_slug": true`。
- 日常单独回归真翻车池时加 `--allow-partial` 跳过全库覆盖告警：

```bash
python3 scripts/route_eval.py audit <真实翻车jsonl> <技能库目录> --allow-partial --strict
```

## 四、职责边界与二期预留

- **单技能日更调优**（如特定写作风格每天盲评、攒细则、自动发版）仍归单技能专用评测台，不由本引擎越权接管。
- **线上真实运行态埋点**（真实会话命中率、实际文件读取顺序、端到端产出采纳率）归宿主 Harness，不由本离线路由工具伪造。
- **二期预留（双模消融编排器）：** 核心技能做结构减负或主力模型升级时，再补轻量 `bare vs old vs new` 盲评编排器，与本路由工具形成「入口不选错 + 进门不退化」两段检验。
