# CHANGELOG

## 0.2.0 — 2026-10-16

Agent 场景防呆改造：假视频输入校验、临时目录治理、装包确认闸门、文档去重。

### 修复
- **P1-2 假视频不再静默"成功"**：`open_video` 在校验 frame_count≤0 / 宽高为 0 / duration≤0 时输出人话错误并 exit 2；PNG 改名 mp4 这类文件不再被当成"全静止视频" exit 0。
- **P1-1 临时目录治理**：新增 `--max-frames`（默认 300）限制 scan/zoom 抽帧上限，超限截断并 warn；退出时 atexit 在 stderr 打印"可删除 <dir>"提示（不自动删，防止模型 Read 滞后）；新增 `--cleanup`（成功退出才删自动临时目录，`--outdir` 指定位置绝不删）与 `--keep-frames`（默认行为显式写法）。
- **P1-3 装包确认闸门**：未设 `VIDEO_READER_YES_PIP=1` 时，首次缺 cv2/numpy 不再静默 pip install（exit 3）；transcribe 缺 whisper（约 2GB torch）同样先预告再决定（exit 4）；打印体量预告与手动命令，保留原有解释器三件套诊断。
- **P2-1 性能文档如实化**：README/SKILL 明确 zoom/grid 逐帧随机 seek 在长视频上慢于 scan 的顺序抽帧，请收窄区间。
- **P2-2 文档去重**：删除 README 里指向不存在英文版的死链 `[English](./README.md)`；SKILL.md 精简为触发路由+调用契约（退出码/装包闸门/帧目录治理/假视频防呆），完整使用参考留在 README.zh-CN.md，消除双份漂移。
- **P2-3 上传绕过加边界**：改后缀/压 zip 仅适用于用户自有、有权处置且目标平台规则允许的内容。

### 新增
- `tests/test_video_reader.py`：9 项回归测试（真视频 ffmpeg testsrc 生成 + 伪造后缀样本；假视频 exit 2、--max-frames 截断、--cleanup 删除、默认保留+提示、--outdir 不被误删、装包闸门未放行 exit 3/4 且不触发 pip）。
