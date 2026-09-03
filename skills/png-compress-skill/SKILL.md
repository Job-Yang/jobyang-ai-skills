---
name: png-compress
description: App 工程 PNG 批量压缩。用 pngquant 量化、oxipng 无损收尾，并通过内容缓存和质量门禁避免重复压缩与明显劣化。给出工程或图片目录、要求包体积优化或批量压 PNG 时使用。
---

# PNG 批量压缩

## 这个技能能做什么

给它一个 App 工程或普通图片目录,它会:

1. **自动递归**找出所有 PNG(自动跳过 Pods / Carthage / build / DerivedData 等目录)
2. **自动判断压没压过**——用文件内容 hash 存本地缓存,压过的直接跳过,绝不二次量化毁图
3. **自动压缩**新增/改动的图,增量持续可用(缓存可提交进仓库,团队/CI 共享)
4. **小图友好**——20K 以下 icon 用更保守的质量下限,避免糊
5. **变大回退**——压完比原图还大就丢弃,保留原图(icon 常见)
6. **压后自检**——默认校验可解码/宽高不变/alpha 不丢,再用 PSNR/SSIM/MAE 做自动质量门禁;不通过就回退原图
7. **动图保护**——检测到 APNG 直接保留原图,不把动画误压成单帧
8. **原地覆盖**,不依赖具体 App、Target 或构建系统;多进程跑满 CPU

内核 = `pngquant`(有损量化,24/32bit → 8bit 调色板)+ `oxipng`(无损重编码和元数据清理)。这条路线与 TinyPNG 官方公开的“颜色量化 + 元数据清理”原理一致,但不声称复刻其未公开实现。

## 适用范围

- 不读取 `.xcodeproj`、Scheme、Bundle ID 或业务源码,不依赖任何特定业务工程或私有构建设施。
- 只要目录里有 PNG 就能运行;默认排除依赖目录和构建产物。
- 目标是 iOS App 源码资源,同样可以用于其他 App 或独立图片目录。
- 只处理静态 PNG;检测到 APNG 会保留原图。

## 怎么用

### 最简单:一键跑当前目录

```bash
./compress.sh
```

不传目录 = 默认当前目录递归。依赖(pngquant / oxipng)缺失时会自动尝试用 brew 安装。

### 指定工程目录

```bash
./compress.sh /path/to/iOSProject
```

### 只看效果不改文件(先预估收益)

```bash
./compress.sh /path/to/iOSProject --dry-run
```

### 指定并行数

```bash
./compress.sh /path/to/iOSProject -j 8
```

## 输出长啥样

```
扫描到 PNG: 1234 张 | 缓存已记录: 0 张 | 并行: 8
自检门禁: hard=on | quality=on | ssim=on
===== 完成 =====
压缩: 900  跳过(缓存): 0  保留原图(压不动): 330  跳过(APNG): 4  硬门禁回退: 0  质量门禁回退: 2  失败: 0
本轮压缩前: 45.2MB  压缩后: 12.8MB  节省: 32.4MB (71.7%)
耗时: 38.5s
```

再跑第二次,压过的全部走"跳过(缓存)",秒回。

---

## 实现细节(感兴趣再看)

脚本本体是 `compress_images.py`,`compress.sh` 只是加了依赖自检 + 自动安装的一层壳,两个交付形态(纯脚本 / 技能)复用同一份 `compress_images.py`。

**核心命令(每张图):**

```bash
# ① 有损量化,达不到质量或变大就放弃(退出码 98/99 视为正常)
pngquant --quality 65-85 --speed 1 --floyd=1.0 --strip --skip-if-larger \
         --force --output out.png  input.png
# ② 无损收尾:榨 DEFLATE + 删所有元数据
oxipng -o max --strip all -q out.png
```

**压后自检(默认开启):**

1. 硬门禁: 用 Pillow(没有则退到 macOS `sips`)解码原图和候选图,要求候选图可解码、宽高不变、原图有 alpha 时候选图不能丢 alpha、动画帧数不能变化。
2. 质量门禁: 用 Pillow 计算 before/after 像素差异。默认阈值是 `PSNR >= 28`、`SSIM >= 0.95`(有 numpy 时启用)、`MAE <= 12`、`alpha MAE <= 3`。透明图会分别垫白底/黑底对比,避免只看透明像素导致误判。
3. 动图保护: APNG 不进入有损量化,直接保留并写入缓存。
4. 回退策略: 任何门禁不通过都保留原图,并把原图 hash 记入缓存,下次不再重复尝试。输出会打印 `[HARD-GATE]` 或 `[QUALITY-GATE]` 的文件清单。

> 这套自动门禁只负责拦“坏图/尺寸变了/alpha 丢了/明显灾难性劣化”。“到底糊不糊”仍然有主观性,建议每轮再按体积下降最大、压缩比例最高、AppIcon/launchscreen、透明 icon 等维度做肉眼抽检。

**可调参数(在 `compress_images.py` 顶部):**

| 参数 | 默认值 | 说明 |
|---|---|---|
| `QUALITY_NORMAL` | `65-85` | 普通图质量区间,上限对齐 TinyPNG 观感 |
| `QUALITY_SMALL` | `70-90` | 小图/icon 区间,下限抬高防糊 |
| `SMALL_THRESHOLD` | `20*1024` | 20KB 以下算小图 |
| `DITHER` | `1.0` | 抖动强度,TinyPNG 默认开启 |
| `OXIPNG_LEVEL` | `max` | 无损级别,嫌慢可改 `4` |
| `CACHE_NAME` | `.png_compress_cache.json` | 缓存文件,建议提交进仓库 |
| `QUALITY_MIN_PSNR` | `28.0` | 自动质量门禁最低 PSNR |
| `QUALITY_MIN_SSIM` | `0.95` | 自动质量门禁最低 SSIM(有 numpy 时启用) |
| `QUALITY_MAX_MAE` | `12.0` | 自动质量门禁最大平均绝对误差 |
| `QUALITY_ALPHA_MAX_MAE` | `3.0` | 透明通道最大平均绝对误差 |

**Python 直接调用:**

```bash
python3 compress_images.py                       # 当前目录递归
python3 compress_images.py /path/to/iOSProject   # 指定目录
python3 compress_images.py /path/to/proj --dry-run
python3 compress_images.py /path/to/proj -j 8
python3 compress_images.py /path/to/proj --no-quality-gate       # 关闭质量门禁(不建议)
python3 compress_images.py /path/to/proj --quality-min-ssim 0.98  # 调高质量阈值
```

**依赖手动安装:**

- macOS:`brew install pngquant oxipng`
- Ubuntu:`sudo apt-get install pngquant` + `cargo install oxipng`(或下 GitHub release 二进制)
- 自检: 硬门禁可用 macOS 自带 `sips`;质量门禁默认开启且需要 Python `Pillow`,有 `numpy` 时会额外启用 SSIM 指标。缺 Pillow 时脚本会报错,除非显式加 `--no-quality-gate`。
