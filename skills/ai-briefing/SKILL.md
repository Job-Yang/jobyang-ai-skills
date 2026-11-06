---
name: ai-briefing
description: 生成一份 5 分钟可读完、宁缺毋滥的 AI/前沿科技每日早报。当用户要求做 AI 日报/早报/情报简报、每日科技大事汇总、按固定卡片格式（事实+判断+机会分）筛选 AI 新闻、或按周复盘 GitHub Trending 时使用，用户说「出今天的 AI 早报」「今天 AI 圈有什么大事」时触发。平台、读者画像、信息渠道、文档交付全部走 config 适配，技能本体不含任何公司内部端点、密钥或个人信息，可整体迁移到新公司/新 Agent 平台。
---

# ai-briefing · 可迁移的 AI 每日早报技能

把"每天做一份高质量 AI 早报"固化成一条**不绑定平台**的情报流水线：采集 → 交叉验证 → 按读者画像做判断和打分 → 固定卡片渲染 → 双保险交付。读者是谁、X 怎么读、写进哪个文档，全部在 `config.json` 里适配，换公司只改配置和两个适配点，不改方法论。

## 输入

- 触发方：人工说"出今天的 AI 早报"，或任意定时/调度系统。**本技能不含调度**，由宿主平台的 cron/计划任务负责（迁移示例见 `MIGRATION.md`）。
- 配置：先找 `config.json`（与 SKILL.md 同目录）；没有就用默认通用配置（匿名技术读者、中文、GitHub/PH/公开媒体、Markdown 交付）。从 `config.example.json` 复制生成。

## 硬规则（任何平台都不变）

1. **必须交付**：渠道失败不能导致当天没有早报；拿到多少可靠信息报多少，缺的渠道在文末如实标注；文档写不进去就把完整正文直接输出。绝不空手结束、不只报错误不交付内容。
2. **事实纪律**：每条有真实可点的来源链接和发布时间；重要事实至少两个来源交叉确认；单一来源/传闻标"未证实"；拿不准不写；**绝不编造推文**。
3. **宁缺毋滥**：全文控制在读者 5 分钟读完的密度（通常 8–14 条）；没有料的组写"今日无值得报的"，不许凑数。
4. **时间窗**：工作日收过去 24h；周一覆盖整个周末约 72h 并标注"周末合并版"；配置里 `weekly_recap_weekday` 指定的那天，额外做整周 GitHub Trending 复盘。不做跨天去重，不读历史早报比对。
5. **判断和打分锚定读者**：每条必须有观点，不复述事实；机会分回答"对这位读者有没有用、本周该不该动手"，不是新闻热度。
6. **去个人化**：技能本体不出现任何真实姓名、公司名、内部系统名、内部 URL、密钥。这些只存在于读者自己的 `config.json`。

## 执行流程

1. **加载配置**：读 `config.json`，确定读者画像、时间窗、今日星期、是否周复盘日。
2. **采集**：按 `references/channels.md` 逐渠道取数。X 按配置的四档（host_read 直读主页 / http 走 `x_provider.py` / stdin 宿主喂入 / none）取数，失败逐档降级并记录，不硬刷。周复盘日用 `scripts/github_trending.py --range weekly` 拿真实"本周新增 star"。
3. **核验与筛选**：交叉验证、剔除营销软文/无关消费工具/标题党；按 `references/coverage.md` 的 7 个边界归类。
4. **写判断与打分**：按 `references/card-format.md` 的三行卡片写事实、判断、机会分；工具类条目必须回答"该不该用、怎么接入、增量是什么"。中文先过 `config.optional_skills.style_polish`（若配了），否则用 `references/style-fallback.md`。
5. **渲染**：把候选条目整理成 `examples/brief_input.example.json` 的结构，用 `scripts/render_brief.py` 确定性产出 Markdown，保证每天版式一致。
6. **交付**：按 `references/delivery.md` 写入配置指定的文档（最新在最上、历史只读）；写不进去就降级 Markdown 文件 + 本次输出回显全文。文末给"3 条头条一句话 + 文档链接 + 各渠道真实状态"。

## 脚本（Python 3.7+，仅标准库）

- `scripts/github_trending.py`：抓/解析 GitHub Trending，输出每个仓库的总数与区间新增 star；支持 `--html` 离线解析（测试用）。
- `scripts/x_provider.py`：可移植 X 数据客户端，按 provider profile 适配任意 X 数据服务（端点/字段映射在配置里、密钥走环境变量），把不同后端归一化成统一结构；也支持 host 读到数据后 `--stdin` 喂入。
- `scripts/render_brief.py`：把结构化候选 JSON 渲染成固定卡片 Markdown，只做版式、不替你做判断。

## 文件

- `references/coverage.md`：7 类覆盖范围与不收录清单。
- `references/channels.md`：各渠道怎么取、X 的四档适配与统一数据结构、失败降级。
- `references/card-format.md`：卡片三行结构、机会分 rubric、周复盘格式。
- `references/style-fallback.md`：没有中文清洗技能时的最小写作规则。
- `references/adapters.md`：平台适配契约（X 后端 / 文档写入）与密钥纪律。
- `references/delivery.md`：双保险交付与文档占位规则。
- `examples/`：渲染输入示例、X provider profile 模板（通用 HTTP 风格、X API v2 风格）。
- `MIGRATION.md`：搬到新公司/新平台的落地步骤、调度示例、依赖盘点。
- `tests/`：真实 GitHub HTML fixture + 本地假 X 服务的解析/归一化/渲染测试（`python3 -m unittest discover -s tests`）。

## 边界

- 不负责调度（cron/定时器由宿主管）。
- 不内置任何需要付费密钥或公司内网的数据源；这些都通过 config 注入，缺失时降级到公开渠道，不报错停工。
- 不做投顾、不做标题党流量稿、不自动外发任何消息。
- **不裸写"从某条早报深挖出来的长文档"**：早报只产卡片式简报。读者看完某条想"深入调研/讲透/写成稿/做方案"时，
  这是另一个任务，先提醒一句：**深度调研建议新开一个干净窗口再做，别在这个塞满新闻采集的简报窗口里展开**
  （简报上下文会把研究节奏带快、带浅）；也不要沿用简报文风把卡片直接拉长成裸文档。若读者坚持就在本窗口做，
  至少先停下确认，不默认拿简报直接扩写。本技能不绑定具体研究/写作技能，按宿主环境自然路由即可。
