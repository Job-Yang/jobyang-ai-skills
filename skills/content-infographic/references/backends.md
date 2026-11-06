# 跨平台后端：文生图怎么接（适配器口子，核心不动）

确定性渲染器（`render_infographic.py`）只依赖 Python 标准库 + 系统转换器，**任何能跑 Python 3.8+
的环境都能用**——这是本技能跨平台的底盘，也是绝大多数信息图的主路径。真正随平台变化的只有
"文生图"这一下。本文件把它收敛成一个**适配器口子**：换平台只补一个适配器，技能的核心
（中心思想、选后端、图文咬合、视觉语言、渲染器）一律不动，绝不因为换平台推翻架构。

> 进场先跑 `python3 scripts/doctor.py`：它把当前环境的能力和缺口列清楚。

## 设计原则：核心稳定，适配收口

- **平台无关的核心**（不随环境变，别在新平台重写）：① 拎中心思想/该不该出图（selection.md）；
  ② 六类布局 + 确定性渲染器（schema.md / render_infographic.py）；③ 图文咬合（linkage.md / check_linkage.py）；
  ④ 视觉语言（visual-style.md）。
- **唯一随平台变的，是"怎么发起一次文生图、产物怎么落地"**。就这一件事，通过三级后端 + 一张适配器登记表收口。
- **能力缺口必须让用户有感知**：当平台闭环不了文生图时，不静默失败、不假装出图，要明确告诉用户
  缺什么、可以怎么补，并自动降级（见末尾"缺口告知契约"）。

## 三级后端（按优先级，命中即用）

1. **宿主原生文生图**（豆包 `image_gen` / Codex gpt-image / Trae 视觉模型）——平台自带，首选。
2. **文生图 MCP**（Seedream MCP、OpenAI images MCP 等）——平台支持 MCP 时挂一个。
3. **CLI／HTTP 适配器 `scripts/gen_image.py`**——当前宿主没有直接暴露图工具时，可自动调用已配置的 Ferry＋官方 Codex 原生图工具（无需额外图片 API Key），或使用已有 OpenAI 兼容 endpoint＋key。Ferry 适配只负责生成和保存，视觉及文字仍需逐图验收。

三选一即可。一个都没有：**渲染器那条路仍然完整可用**（步骤/对比/多标签图不受影响）；
具象场景图改用渲染器的 `metaphor` 几何版，或只交付提示词让用户自行出图，并按契约告知缺口。

## 各平台现状（2026-10 查证；能力更新快，以当场 doctor + 工具清单为准）

| 平台 | 渲染器 | 原生文生图 | 文生图 MCP/HTTP |
|---|---|---|---|
| **豆包工作** | ✅ | ✅ `image_gen`（Seedream 5.x，已真机验证单标签封面/场景） | 无需 |
| **Claude Code** | ✅（终端可直接出 SVG/HTML） | Claude 本体不生位图；可调用图像工具 | 已验证 `gen_image.py` → Ferry＋官方 Codex 原生图工具；复用本机账号，不必额外图片 API Key；也兼容其它 MCP/HTTP 后端 |
| **Codex（OpenAI）** | ✅ | ✅ Codex app 用 gpt-image-1.5；Responses API 有 image 工具 | API key + gen_image.py 或 MCP |
| **Trae（字节）** | ✅ | 方舟 Agent Plan Medium+ 含图片配额，配视觉模型开通 | ModelArk Seedream MCP（`.trae/mcp.json`）/ 方舟 endpoint |
| Cursor / 其它 Codex 类 | ✅ | 看版本 | 挂 MCP 或配 key |

## gen_image.py（HTTP 适配器，零三方依赖）

只走环境变量，**不把 key 写进命令行或文件**：

```bash
# 火山方舟 Seedream（OpenAI 兼容）
export CI_IMAGE_PROVIDER=ark
export CI_IMAGE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
export CI_IMAGE_API_KEY=<key>
export CI_IMAGE_MODEL=doubao-seedream-4-0
python3 scripts/gen_image.py "提示词" -o out.png
# OpenAI：CI_IMAGE_PROVIDER=openai / BASE https://api.openai.com/v1 / MODEL gpt-image-1
python3 scripts/gen_image.py "..." --dry-run -o out.png   # 不耗额度，验证请求构造
python3 scripts/doctor.py --ping                          # 配了 key 后真发一张最小图端到端验证
```

`provider=generic` 可自定义 `CI_IMAGE_PATH` / `CI_IMAGE_URL_FIELD` 适配非标准但接近 OpenAI 的服务；
`provider=command` 可包任意厂商 CLI（从 stdout 抓图片 URL，支持中文提示词、非 ASCII URL 自动编码）。

## 3 步自接线口子（到任何新平台，照做，核心不改）

1. **盘点**：跑 `doctor.py`；看自己的工具清单有没有原生文生图、有没有图像类 MCP（名含 seedream /
   image / gpt-image / draw）；有没有可用的 OpenAI 兼容 key。
2. **登记适配器**：在下表补一行——①用哪个工具/命令发起；②入参怎么传（提示词、尺寸、数量、
   编辑时的母版 URL）；③产物怎么落地（URL → fetch_image.py，还是直接给本地文件）。
   风格前缀、选后端、图文咬合全部复用，不在适配器里另起一套。
3. **验证**：用一张"单标签"图真机出一次（短中文清晰、无多余乱字、能下载到真 PNG），
   再确认一次多标签图确实糊（坐实多标签走渲染器）。结果写回"已验证"列。

## 适配器登记表（新平台补这里）

| 平台 | 发起方式 | 入参要点 | 产物落地 | 已验证 |
|---|---|---|---|---|
| 豆包工作 | 原生 `image_gen` | `request_list[{prompt,width,height,model_version}]`；编辑用 `image_edit` 传母版 | CDN URL → fetch_image.py | ✅ 2026-10 |
| Claude Code | gen_image.py 自动选择 ferry_codex，调用 Ferry＋官方 Codex 原生图片工具 | 本机既有 Ferry 账号，独立 CODEX_HOME；见 [ferry-codex.md](ferry-codex.md) | 原生缓存图片→格式规范化→本地文件与收据 | ✅ 2026-11-05：真实含字图＋飞书写入＋下载回读 SHA256 一致 |
| Codex | gpt-image / Responses images / MCP | —— | URL/文件 | 未验证 |
| Trae | ModelArk Seedream MCP / 方舟 endpoint | `seedream_generate_image` | URL → fetch_image.py | 未验证 |
| _新平台_ | | | | |

## 缺口告知契约（闭环不了时必须对用户说清楚）

当文生图在当前平台不可用（三级都没有 / 调用失败 / 鉴权缺失）时：

1. **明说缺什么**，例如："当前环境没有原生文生图工具，也没配文生图 MCP 或 CI_IMAGE_API_KEY，
   具象场景图这一步做不了。" 不要静默跳过或谎称已出图。
2. **给出怎么补**：列最小动作——"挂一个 Seedream MCP" 或 "按 backends.md 配 CI_IMAGE_* 后跑 doctor --ping"。
3. **立即降级、保证主目标不塌**：该图改用渲染器（步骤/对比走确定性图；比喻走 `metaphor` 几何版），
   或只把完整提示词交付给用户自行出图；正文理解不依赖那张图也能成立。
4. `doctor.py` 的报告本身就是这份告知的机器版：核心（SVG）不可用=fail；只是文生图缺=warn，
   不影响渲染器正常使用。

不变量：任何后端出的图都要过 check_linkage 对账 + 出图后人工核对；适配器只负责"把提示词变成一张 PNG"。
