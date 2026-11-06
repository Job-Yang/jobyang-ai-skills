# 平台适配契约（换公司只改这里）

技能本体只认两类"接缝"。到新平台时，只需要实现这两个接缝，方法论、卡片、脚本、rubric、X 归一化全部原样带走。

## 接缝 A：X / 信息源

X 已内建可移植 provider（`scripts/x_provider.py`，纯标准库），**不依赖任何公司内部服务**。四档见 `references/channels.md`，要点：

- **默认零依赖**：宿主网页读取直读 X 主页 + 公开媒体 + GitHub Trending，不配置任何东西就能出报。
- **有 X 数据服务**（官方 API、RapidAPI 类网关、自建采集器，或新公司的内部情报服务）：复制一份 provider profile，填它的 `url`/请求体/字段映射；凭证用 `$ENV_VAR` 占位。不同后端只是 JSON 配置不同，脚本和早报流程一行不改。
- **宿主自己读到数据**：`--stdin` 喂入，走同一套归一化。
- **完全拿不到 X**：`mode: none`，二手报道并显式标注。

> 反例（迁移时不要做）：把某个内网域名、API key、个人 cookie 写死进脚本或 profile 提交进库。本技能已刻意不含这些——这正是把"能力"炼化进来、把"具体服务"留给配置的区别。

## 接缝 B：文档写入（弱依赖，可选）

`config.delivery`：

- `doc_kind: markdown_or_host_doc`（默认）：没有云文档时产出 Markdown 文件 + 在任务结果回显全文，这就是完整交付，不强依赖任何文档平台。
- 新公司有任意云文档（飞书/Notion/Google Docs/Confluence/语雀……）：填 `write_command`，约定输入是 标题 + 正文 + "插到最顶部、历史只读"的位置语义 + doc_url；技能只调用并判断成败，不绑定某个平台的私有结构。
- 写文档失败：自动降级为"Markdown 文件 + 对话全文"，文末说明，早报不中断。文档永远是弱依赖，不是出报的前置条件。

## 凭证纪律（硬规则）

- 密钥/cookie/token 只放环境变量或宿主密钥管理，**绝不进 SKILL.md / config / 脚本 / git**。
- `config.json`、`x-provider.json` 含个人/凭证信息，均已 `.gitignore`；仓库只提交 `.example` 模板。
- 定时 prompt 里也不写凭证（调度日志通常可见）。

## 最小可移植单元

带走整个 `ai-briefing/` 目录：**Python 3.7+ 标准库 + 一个能读网页的 Agent 宿主 + 任意平台的定时器**，即可每天出报。X 搜索和云文档都是"有更好、没有也能降级跑"，没有任何一项是硬绑定。
