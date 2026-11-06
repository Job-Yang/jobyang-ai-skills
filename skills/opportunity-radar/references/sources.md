# 信息源清单与可达性（2026-10-20 云电脑实测）

> 0.4.0 起分两层：`scripts/collect.py` 每天自动采集的**结构化源**，和 Agent 按需补的**语义搜源**。
> 可达性是在豆包工作云电脑（无浏览器登录态、纯服务端网络）实测的；本地环境可能不同，
> 换环境后先跑一次 `collect.py` 看逐源状态。

## collect.py 自动采集（无需 key、无需登录）

| 源 id | 是什么 | 怎么取 | 看什么 |
| --- | --- | --- | --- |
| hunted | 当日 Product Hunt 榜 | hunted.space 内嵌 JSON，含票数、评论数、话题 | 票数和评论数都高、评论里有「缺 X」的新品 |
| ph_feed | Product Hunt 官方 Atom | producthunt.com/feed，近 50 条发布 | 榜单外的长尾新品 |
| gh_trending | GitHub Trending | trending 页 HTML，daily stars today | 一天涨几百星的新仓=技术能力刚被验证 |
| gh_new | GitHub 新建高星仓 | Search API：近 3 天建、star>100 | 更早期的能力外溢（无 token 限流 10 次/分，脚本只用 1 次查询） |
| hn_show | Show HN | Algolia API，近 3 天、>15 分 | 独立开发者的成品发布和评论反馈 |
| hn_ask | Ask HN | Algolia API，近 7 天、>10 分 | 「我需要/有没有」类真问题 |
| hn_wishes | HN 评论许愿 | Algolia comment 检索，近 14 天 | 评论里「I wish there was / would pay for」原话，按帖聚合 |
| hf_spaces | Hugging Face trending Spaces | HF API | 新模型能力外溢成什么 demo，下一波产品机会跟着能力走 |
| hf_models | Hugging Face trending 模型 | HF API | 最新模型和能力发布，产品机会跟着新能力走（0.4.1） |
| hn_front | Hacker News 首页 | Algolia API | 当天业界最热的事和讨论里的机会线索（0.4.1） |
| devto | DEV.to 最新流加热门流 | 官方 API，最新 40 + 近一周热门 40 | 开发者抱怨、翻车复盘、自建工具；只看热门会漏当天新文（0.4.1 起双流合并） |
| v2ex_create / v2ex_hot | V2EX 创造节点、热门与最新 | V2EX 官方 API | 中文独立开发者当日发布、求反馈和最新讨论；hot + latest 双流合并；需带规范 UA |
| lobsters | Lobsters 热门与最新 | 官方 JSON | hottest + newest 双流，技术社区发布，噪声比 PH 小 |
| reddit_rss | Reddit 公开 RSS | r/SaaS、r/indie 等 top week RSS | 独立开发者和小生意人的真实抱怨；JSON API 被 403，只能走 RSS，各 sub 独立容错 |
| appstore_money | 美区效率类畅销榜 | iTunes RSS topgrossing | 钱正在流向什么 app，是「钱在流动」的对照，不是机会本身 |

逐源状态写在 pool.json 的 sources 字段。单源 blocked 不致命；全部为空 collect.py 退 4，
上层按「失败留痕」处理，不许静默结束。

## 2026-10-20 实测不可达（云电脑，别再白搜）

- **Reddit JSON API**（reddit.com/*.json）：403 Blocked。只能用 RSS（.rss），且偶发 429，脚本里已加 1 秒间隔和逐 sub 容错。
- **X/Twitter**：只有登录空壳，搜不到内容。思潮层改用 HN/Reddit/DEV/V2EX，X 信号靠通用搜拿二手转载，标 assumption。
- **即刻 web 版**：502；**小红书**：JS 空壳。中文信号走 V2EX API 和通用搜（闲鱼/小红书内容转载）。
- **Google Trends 网页**：429。趋势斜率不再强求实时拉，用「多源近期同时出现」当代理证据，并在条目里写明这是代理不是 Trends 实测。
- **G2**：403。竞品差评改用 App Store 评论、PH 评论、Reddit RSS 和 DEV。
- **iwishtherewas.xyz**：页面还在，但最近愿停在 2026 年中，新鲜度不够，降级为偶尔回看。
- **pullpush（Reddit 归档）**：429，不可靠，不进脚本。

## 防噪通则

- 每源至少交叉 2 个角度，别信单条结果。
- 垃圾站（内容农场、SEO 转载，黑名单见 freshness.py）一律筛掉，只认一手来源（原帖、原仓、原评论）。
- PH upvote 高不等于需求强，必须看评论质量；GitHub star 快不等于能收钱，深挖时补付费证据。
