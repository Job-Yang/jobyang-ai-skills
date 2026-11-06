# Ferry＋Codex 原生文生图适配器

当前 Claude Code 没有暴露图像生成工具时，可通过同一技能脚本调用已配置的 Ferry＋官方 Codex 原生图片工具。不是 SVG 渲染，不要求把图片手工转交，也不要求额外方舟 API Key。

## 前提

- 此原生 CLI 适配器需要 Python 3.11＋；原有渲染器和其它后端仍按其原兼容范围使用。
- 已安装并登录 Ferry，网关在本机运行。登录与模型权限仍须实际核对，不能继承别的 IDE 身份。
- Ferry 文档要求图片功能版本不低于 0.1.43；本次验证为 Ferry 0.1.98。
- 官方 Codex 客户端已按 SHA256 校验并缓存至 `~/.cache/content-infographic/ferry-codex/codex`。本次验证为官方 `rust-v0.166.0`、macOS ARM64。
- 客户端配置从 `ferry config codex` 获得。图片身份头为 `x-openai-actor-authorization = ferry`，只用明确的 Ferry 提供方，不冒用官方订阅。

本适配器每次创建独立 `CODEX_HOME`，不复制、退出或改动用户已有 ChatGPT／Codex 登录，不修改当前 Claude Code、TRAE CLI 配置。只缓存已校验客户端，不安装持续监控。

## 使用

```bash
python3 scripts/doctor.py
python3 scripts/gen_image.py --stdin -o new-figure.png < figure-prompt.txt
```

若没有显式配置其他 HTTP 后端，且本机 Ferry 与缓存客户端就绪，`gen_image.py` 会自动选择 `ferry_codex`。也可显式设置 `CI_IMAGE_PROVIDER=ferry_codex`。用户明确要求文生图与既有风格时，不因标签较多而静默改用 SVG／工程流程图。

输出是新文件，已有文件不会被覆盖；包括原生图片、PNG（必要时转换编码）和 `.receipt.json`。收据保留原生来源路径、原始与最终 SHA256、输入提示词 SHA256、尺寸；`.events.jsonl` 保留客户端执行证据。日志与提示词仅留本机。

## 什么才算成功

- 不凭 CLI 退出 0 或模型自述判断。
- 必须在这一次隔离会话的原生 `generated_images` 缓存找到实际图片，检查魔数与大小，再保存指定输出。
- 原生 JPEG 可能被工具命名为 `.png`；本适配器识别真实格式并在必要时转为 PNG，不更改画面内容。
- JSONL 事件可能不完整列出图像工具；因此保留原始原生图片、工具缓存来源和最终图片，而不只按某个事件名计数。
- `native_image_saved` 只证明生成与本地保存，**不代表文字、关系、风格已验收**。须检查主副标题、标签、连接关系、比例，再决定是否发布。

## 失败处理

无真实原生产物、配置不匹配或超时时，返回失败／未验证，不伪造成功，不自动用绘图代码生成占位 PNG，不盲目重发尚未确认的生成请求。若模型在一次已确认产图后又生成修订候选，保存全部原始候选及哈希，默认取最后一张；候选数量如实留在收据中，仍须人工选择和校图。多张真实图片不应被误报为“完全没有出图”。

## 文档更新

使用飞书文档现有读取／图片更新流程，或 `scripts/lark_image_replace.py` 薄适配器。默认只读预演；只有用户明确授权更新原文时才加 `--apply`。更新前查图块 ID、旧 token 与版本；更新后下载回读并对 SHA256。现场截图、照片、录屏和真实产物不替换为合成图片。

## 本次实际验证

2026-11-05：同一账号经官方 ARM64 Codex＋Ferry 生成包含九节点文字的立体信息图，原生图片保存到客户端工具缓存，并复制／规范化为本地 PNG。已用技能统一 `gen_image.py` 入口再次生成真实图像。视觉检查发现第一张连接线错误，拒绝发布并重新按文字生成；不将“后端能出图”当作“图内容正确”。

客户端版本参见[官方 Codex 发行](https://github.com/openai/codex/releases/tag/rust-v0.166.0)。后端配置由使用者本机提供，不依赖内部文档；其他平台与账号未据此宣称验证通过。
