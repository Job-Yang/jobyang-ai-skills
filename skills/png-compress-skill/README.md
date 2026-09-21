# PNG Compress

> 把 TinyPNG 式的 PNG 压缩做成本地、可批量、可重复执行的 Agent Skill。

**简体中文** · [English](./README.en.md)

我们最初只是想批量压一遍 App 工程里的 PNG。TinyPNG 单张处理很好用，但一旦要处理整个工程、反复处理增量资源，网页上传太慢，API 又有额度和费用，图片还必须离开本机。

于是我们顺着它公开的原理往下拆：PNG 压缩的大头来自颜色量化，把 24/32 位真彩色收敛成更小的索引色；剩下的空间再通过无损重编码和元数据清理继续压缩。最终得到这套完全在本地运行的流水线：

```text
pngquant 有损量化
        ↓
oxipng 无损收尾
        ↓
解码 / 尺寸 / alpha / 质量门禁
        ↓
通过则覆盖，失败则保留原图
```

它不是 TinyPNG 的逆向实现，也不声称复刻其未公开算法。它复用了同一类公开技术路线，并把批处理、增量缓存、质量回退和工程目录扫描补齐。公开对比也表明，`pngquant` 在合适参数下可以做到不逊于 TinyPNG 的压缩率；但不同图片差异很大，最终仍应以自己项目的素材做 A/B 验证。

## 它解决什么

- 递归处理整个 App 工程，不用逐张上传。
- 全程本地运行，图片不需要上传到第三方服务。
- 用内容 hash 识别已经处理过的图片，避免重复有损压缩。
- 小图使用更保守的质量区间，降低 icon 发糊的风险。
- 压缩后变大、无法解码、尺寸变化、alpha 丢失或质量门禁失败时，自动保留原图。
- APNG 原样跳过，避免动画被压成单帧。
- 多进程并行，适合上千张资源的工程。

## 不绑定具体工程

这个 Skill 不读取 `.xcodeproj`、Scheme、Bundle ID、Target 或业务源码，也不依赖任何特定业务工程或私有构建系统。它只接收一个目录，递归查找其中的 PNG。

因此它可以用于：

- 任意 iOS App 的 `Assets.xcassets` 和普通资源目录；
- 其他 App 工程中的静态 PNG；
- 单独整理出来的图片目录。

默认会跳过 `.git`、`Pods`、`Carthage`、`build`、`DerivedData`、`node_modules`、`.build` 和 `fastlane`。

## 作为 Skill 安装

克隆技能总仓后，把完整目录复制到 Agent 的 Skills 目录：

```bash
git clone https://github.com/Job-Yang/jobyang-ai-skills.git
cp -R jobyang-ai-skills/skills/png-compress-skill ~/.claude/skills/png-compress-skill
```

之后直接告诉 Agent：

```text
帮我压一下这个 iOS 工程里的 PNG：/path/to/MyApp
```

Agent 会先确认目标目录，再调用本目录里的脚本。

## 直接运行

进入技能目录后：

```bash
# 压当前目录
./compress.sh

# 压指定工程
./compress.sh /path/to/MyApp

# 只估算，不修改文件、不写缓存
./compress.sh /path/to/MyApp --dry-run

# 指定并行数
./compress.sh /path/to/MyApp -j 8
```

脚本会原地替换通过门禁的 PNG，并在目标根目录生成 `.png_compress_cache.json`。

> 建议先确保 Git 工作区干净或已有提交，再执行正式压缩。缓存可以提交进仓库供团队和 CI 共享；如果不希望提交，请自行加入 `.gitignore`。

## 为什么是两个工具

| 工具 | 负责什么 | 是否有损 |
| --- | --- | --- |
| `pngquant` | 减少颜色数量，把真彩色 PNG 转为更小的 8 位调色板 PNG | 是 |
| `oxipng` | 重新选择 PNG filter、重压 DEFLATE、清理元数据 | 否 |

`pngquant` 负责主要收益，`oxipng` 负责把量化后的文件再收紧一点。顺序不能反过来。

默认参数：

```text
普通图：quality 65-85
小图：  quality 70-90
pngquant speed：1
抖动：1.0
oxipng：-o max
```

## 安全边界

这是一套有损压缩方案，因此“能打开”不等于“视觉一定没问题”。脚本做了几层保护：

1. PNG 必须仍能解码。
2. 宽高不能变化。
3. 原图有 alpha 时，结果不能丢 alpha。
4. APNG 不压缩。
5. PSNR、SSIM、MAE 和 alpha MAE 超过阈值时回退。
6. 压完不比原图小时回退。

自动门禁只负责拦明显问题。正式交付前仍建议抽检：

- AppIcon 和启动图；
- 大面积渐变；
- 半透明阴影和毛玻璃素材；
- 带 ICC / Display P3 色彩配置的素材，元数据清理后的显示效果要在设备上确认；
- 体积下降最多、压缩比例最高的图片。

## 依赖

- `pngquant`
- `oxipng`
- Python 3
- `Pillow`，用于默认质量门禁
- `numpy`，可选；安装后会额外启用 SSIM

macOS：

```bash
brew install pngquant oxipng
python3 -m pip install Pillow numpy
```

## 关于 TinyPNG

TinyPNG 官方说明其 PNG 压缩会合并相近颜色，将 24 位 PNG 转成更小的 8 位索引色，并移除不必要的元数据。`pngquant` 作者也明确把 TinyPNG、Kraken 等服务列为这类量化方案的应用。

一份 QQ 音乐团队的公开对比显示：默认参数下 TinyPNG 的压缩率更高，但调整 `pngquant` 品质后，压缩率可以反超 TinyPNG。他们最终也选择了本地 `pngquant` 方案，用于批量处理和工程自动化。

这说明真正值得复用的不是某个在线入口，而是背后的压缩路线，以及把它变成工程能力所需的缓存、回退和验证。

参考资料：

- [TinyPNG: How does PNG compression work?](https://tinypng.com/)
- [pngquant](https://pngquant.org/)
- [Using pngquant in PHP](https://pngquant.org/php.html)
- [Oxipng](https://github.com/shssoichiro/oxipng)
- [QQ 音乐技术团队：PNG 图片压缩对比分析](https://cloud.tencent.com/developer/article/1034208)

## License

本仓库代码使用 MIT License。`pngquant` / `libimagequant` 和 `oxipng` 是独立的第三方项目，使用时同时遵守各自许可证。本 Skill 仅在开发或构建阶段调用它们生成普通 PNG，不把其代码打进 App。
