# 信息渠道与降级纪律

中英文都要搜。优先一手，其次可靠媒体。每个渠道结束后记录"成功 / 失败原因"，文末汇总。

## X / Twitter（速度最快，优先）

**技能本体不含任何固定 X 端点、内网域名或密钥**，也不依赖任何公司内部技能。X 能力拆成"取数后端（可换）+ 统一数据结构（不变）"，四档按可用性降级：

1. **host_read（默认，零依赖）**：让宿主 Agent 的网页读取能力直接打开 `watch_handles` 里的个人主页（`https://x.com/<handle>`），提取最近推文、时间、互动量。X **搜索页**常对非登录访问关闭，不要硬刷；主页读到登录壳就视为失败并降档。
2. **http**：用 `scripts/x_provider.py`（纯标准库）调你有权使用的 X 数据服务。端点、请求体、字段映射全在一个 provider profile JSON 里（`examples/x-provider.example.json`、`examples/x-provider.twitterv2.json`），凭证只从环境变量注入（`"Authorization":"Bearer $X_API_KEY"`）。动作：
   - `search_posts --query ... [--after/--before/--count]`
   - `user_posts --handle ... [--count]`
   - `post_detail --post 123 或 status URL`
3. **stdin**：宿主用自己的浏览器/登录态读到帖子后，`... | x_provider.py <action> --stdin` 做归一化。
4. **none**：只用媒体转载/聚合交叉验证，文末写"今日 X 直连不可用，X 消息来自二手报道"。

所有后端归一化成同一结构：`items[].{id,url,text,created_at,author{handle,name},metrics{likes,reposts,replies,views}}`。详见脚本与 `examples/`。429/5xx 自动退避；其它错误结构化报错（exit 2）后降档，不刷失败请求。**绝对不要编造推文**，引用必须来自真实读到的页面/接口/报道并附链接。

## GitHub

- 日常：看 trending 日榜、相关项目 release/讨论；引用给区间新增 star，拿不到给总数并标注。
- **周复盘日**（默认周五）：`python3 scripts/github_trending.py --range weekly [--language typescript]` 取真实"stars this week"；可对全部/typescript/python 分别取。只挑 AI/Agent/harness/逆向/开发方式相关，跳过纯消费工具。
- 离线/复现：`--html tests/fixtures/trending_weekly.html`。
- 网络失败：降级到宿主搜索/GitHub 页面读取，标注"star 为抓取时总数，未取到区间新增"。

## Product Hunt

- 源：官方 leaderboard（`https://www.producthunt.com/leaderboard/daily/<日期>`）或宿主可读的聚合镜像（官方页不可达就换镜像并标注）。
- 只选 2–3 个真正有含金量的，给链接、面向人群、收费、一句判断；没有就不凑。

## 媒体（中英文）

- 英文：Hacker News、The Information、Bloomberg、TechCrunch、The Verge、Ars Technica 等。
- 中文：量子位、机器之心、36氪、钛媒体、财联社等。
- 重要事实至少两个独立来源；公司官方博客/X 算一手，媒体报道算佐证。

## 每条都要记的取数字段

来源链接、发布时间、作者/机构、关键数字（价格/star/融资额/参数规模）、是否单源/传闻。渲染前据此决定"正常收录 / 标未证实 / 放弃"。
