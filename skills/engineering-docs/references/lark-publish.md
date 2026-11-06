# 发布到飞书（可选适配器）与其他平台

本地文件是源：`arch.py` / `arch.svg` / `seq.mmd` / `arch.drawio`。飞书、GitHub、draw.io 都是发布目标，任何一个不可用都不影响交付和后续修改。**本文档描述的是"发布"动作，不是"画图"动作**：图必须先用 `diagram_kit`/Mermaid 在本地生成并通过通用检查，飞书画板 DSL 只用于把成品写进去，不用它从零构图。

## 飞书

发布前先跑 `python3 scripts/diagram_check.py arch.svg --board`（`--lark` 是等价旧名）：飞书画板检查 0 个错误，可编辑节点比例 100%。这一步依赖 Node，Node 不可用时跳过并在交付说明里写明，不阻塞 SVG 交付。

| 目的 | 做法 |
| --- | --- |
| 新建文档时带图 | `docs +create` 的 XML 里写 `<whiteboard type="svg" path="@arch.svg"></whiteboard>`，飞书把 SVG 转成原生画板节点 |
| 往已有文档加图 | `docs +update --command append`（或 `block_insert_after`）写同样的 `<whiteboard>` 块 |
| Mermaid 图 | `<whiteboard type="mermaid" path="@seq.mmd"></whiteboard>`，画板内仍可改源码 |
| 更新已有画板 | `whiteboard +update --whiteboard-token <token> --input_format svg --source @arch.svg` |
| 拖动卡片时连线跟着走 | `python3 scripts/lark_bind.py arch.svg -o arch.lark.json`，再 `whiteboard +update --input_format raw --source @arch.lark.json`；画板里已有这张图时加 `--overwrite`，否则会叠出两份 |

说明：

- `path="@..."`、`--source @...` 用相对当前目录的路径。
- 每张卡片在 SVG 里是一个 `<g>`，导入后是一个组合，文字跟着方框移动。不要把整张图包进一个 `<g>`：导入后整张图是一个组，要先解组才能改。
- SVG 直接导入时，连线只记坐标，拖动卡片后要手动调整连线。需要反复编辑的画板用 `lark_bind.py` 的输出写入：连线两端绑定到卡片，线上的标签变成连线自带的文字。离开连线的标签保持为普通文字。
- `--overwrite` 会清空画板。更新用户已有的画板前，先 `whiteboard +export --output-type raw` 备份，并征得用户同意。不覆盖用户手工画的画板。
- 同一次写入重试时复用同一个 `--idempotent-token`。
- 写入后读回核对：`whiteboard +export --output-type raw` 看连线两端是否带 `attached_object`，再导出预览看画面。预览全白时检查层级，背景形状应在最底层（`z_index` 为 0）。
- 绑定版的主连线可能比直接导入版粗一档：whiteboard-cli 把 2.5～4px 的线转成 `medium`，飞书服务端把 2.5px 转成 `narrow`。`diagram_kit` 的主连线宽度是 2px × 图宽 / 960，图宽 960 时两种写入方式一致；更宽的图需要一致时，在画板里框选连线统一改线宽。

### 权限不足时怎么说

| 报错 | 含义 | 告诉用户 |
| --- | --- | --- |
| `99991672`，缺 `board:whiteboard:node:create` 或 `:read` | 应用身份没有开通画板权限 | 需要应用管理员在开发者后台开通该权限；或改用用户身份 |
| `20038`，refresh_token 被拒 | 用户授权过期 | 请用户打开 lark-cli 输出的授权链接重新登录 |
| 无文档权限（如 `3380004`） | 当前身份不是文档协作者 | 请文档所有者添加协作者，或让用户提供可编辑副本 |

权限问题不阻塞交付：照常交付本地 SVG、draw.io 和预览，并写明哪一步没有发布、需要谁做什么。

### 在飞书里改过之后

飞书画板里的修改不会自动回到本地源文件。约定一个唯一的源：

- 以本地脚本为源（推荐）：改 `arch.py`，重新生成并发布，画板里只做临时标注。
- 以飞书画板为源：在文档里注明，之后的修改都在画板里做；需要本地副本时用 `whiteboard +export --output-type svg` 导出。

## 其他平台

| 平台 | 怎么放 | 能否编辑 |
| --- | --- | --- |
| GitHub、GitLab、Gitee 等 Markdown | `![说明](arch.svg)`；Mermaid 用代码块 | 改源文件后重新生成 |
| draw.io / diagrams.net、VS Code 插件、Confluence draw.io | 打开 `arch.drawio` | 可以，连线绑定在节点上 |
| Figma、Sketch、Illustrator | 导入 `arch.svg` | 可以，文字和形状都是矢量 |
| PowerPoint、Keynote | 插入 SVG；PowerPoint 可“转换为形状” | 可以 |
| Notion、语雀、Confluence 附件 | 上传 SVG 或 PNG 预览，源文件放在仓库 | 在源文件里改 |

没有渲染工具时，照常交付 SVG 和源脚本，并在交付说明里写明“视觉未验收”。
