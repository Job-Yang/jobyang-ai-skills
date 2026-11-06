# 迁移指南：到新公司 15 分钟把这套 AI 早报跑起来

这套技能刻意做成"方法论自带、平台能力靠配置注入"。换公司时，**技能目录原样带走，只改 config 和两个接缝**。

## 一、依赖盘点（技能本体零硬绑定）

| 能力 | 实现在哪 | 是否需要某家公司 | 迁移后怎么办 |
|---|---|---|---|
| 情报方法论（覆盖/筛选/卡片/机会分/周复盘） | `references/` | 否，纯文本 | 直接带走 |
| GitHub Trending + 真实 star | `scripts/github_trending.py`（标准库） | 否 | Python 3.7+、能访问公网即可 |
| X 情报能力 | `scripts/x_provider.py`（标准库） | 否 | 端点/字段映射靠 provider profile，密钥走环境变量；不配也能用宿主网页直读 |
| 卡片渲染 | `scripts/render_brief.py`（标准库） | 否 | 直接带走 |
| 中文清洗 | `style-fallback.md` 内置规则；haohao-shuohua 是可选增强 | 否 | 不装任何技能也有兜底；装了更好 |
| 文档写入 | `references/delivery.md` 定义的弱依赖 | 否 | 默认 Markdown 文件+对话全文；有任意云文档再配 `write_command` |
| 定时调度 | 不在技能内 | 否 | 用新平台自己的定时器（任何 harness 都有） |
| 读者画像 | `config.json` | 个人信息，可随人迁移 | 只放本地不入库的 config，技能本体匿名 |

**结论**：技能本体不依赖任何一家公司的服务、域名或密钥。X 数据服务和云文档都是"有更好、没有也能降级"的弱接缝；只有"读网页的 Agent 宿主 + Python + 定时器"是真正的最小前提，任何 harness 都具备。

## 二、落地步骤

1. **拷贝目录**：把整个 `ai-briefing/` 放到新平台的技能目录（或任何 Agent 可读取目录）。
2. **建配置**：`cp config.example.json config.json`，填读者画像、关注账号、媒体。`config.json` 已 gitignore。
3. **自检环境**：
   - `python3 --version`（≥3.7）；
   - `python3 scripts/github_trending.py --range weekly --top 3` 返回真实 star；
   - `python3 -m unittest discover -s tests` 全绿（含一个本地假 X 服务的归一化测试，不依赖外网）。
4. **接 X（四选一，不接也能跑）**：
   - 零配置：保持 `mode: host_read`，让宿主网页读取能力直读 `watch_handles` 主页；
   - 有 X 数据服务（官方 API / 网关 / 自建采集器 / 新公司情报服务）：`cp examples/x-provider.example.json x-provider.json`，改 url、请求体、字段映射，密钥用 `$X_API_KEY` 占位并在环境变量里给值，然后把 config 的 `mode` 改 `http`、`x_provider_profile` 指向它；
   - 宿主自己能登录读 X：让宿主读到帖子 JSON 后 `--stdin` 喂入；
   - 都不通：`mode: none`，二手报道并标注。
5. **接交付**：默认 `doc_kind: markdown_or_host_doc` 即可每天拿到 `ai-daily-YYYY-MM-DD.md` + 对话全文；有云文档再实现 `write_command`（插到顶部、历史只读）并填 doc_url。
6. **（可选）中文清洗**：把 haohao-shuohua 一起拷到技能目录，名字填进 `config.optional_skills.style_polish`。

## 三、定时（任何 harness 都支持，各写各的）

定时 prompt 一句话：
`按 ai-briefing 技能执行今天的 AI 早报；先加载 config.json，遵守双保险交付，文末给渠道状态。`

- **cron**：`0 9 * * 1-5`（工作日 9 点），在能跑 Python、能联网的机器上调起宿主 agent。
- **GitHub Actions**：`cron: '0 1 * * 1-5'`（UTC 1:00 = 北京 9:00），凭证放 secrets，不写进仓库。
- **平台工作流**：用它自己的计划任务节点按工作日触发；调度器只负责唤起，方法论都在技能里。

周复盘日默认周五（`weekly_recap_weekday: 5`），可改。

## 四、验证清单（上线前过一遍）

- [ ] 脚本在新环境直接运行，全部单测绿。
- [ ] 不配置任何密钥也能出一版报（GitHub + 公开媒体 + X 主页直读）。
- [ ] 配一个 X provider profile，`x_provider.py search_posts/user_posts/post_detail` 三个动作都能返回归一化结果。
- [ ] 故意断网 / 给失效 X 凭证：任务仍交付完整早报，文末正确标注失败渠道（exit 2 被捕获并降档）。
- [ ] 写文档失败时自动降级为 Markdown + 对话全文。
- [ ] 技能本体无公司名、内网 URL、密钥（见 README 的自检命令）。
- [ ] `config.json`、`x-provider.json` 都不在版本控制里。
