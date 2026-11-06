---
name: png-compress
description: App 工程 PNG 批量压缩（pngquant 量化 + oxipng 无损收尾）。要求包体积优化、批量压 PNG 时使用，用户说「帮我把这个工程的 PNG 批量压一下」「减小图片资源体积」时触发；非 git 目录原地覆盖需显式放行或改 --output-dir 输出副本。不适用：JPG/WebP 等非 PNG 格式、单张图片精修调色、要肉眼控制画质的设计稿导出。
---

# PNG 批量压缩

## 这个技能能做什么

给它一个 App 工程或普通图片目录,它会:

1. **自动递归**找出所有 PNG(顶层构建产物目录自动排除,见下)
2. **自动判断压没压过**——用文件内容 hash 存本地缓存,压过的直接跳过,绝不二次量化毁图
3. **自动压缩**新增/改动的图,增量持续可用(缓存可提交进仓库,团队/CI 共享)
4. **小图友好**——20K 以下 icon 用更保守的质量下限,避免糊
5. **变大回退**——压完比原图还大就丢弃,保留原图(icon 常见)
6. **压后自检**——默认校验可解码/宽高不变/alpha 不丢,再用 PSNR/SSIM/MAE 做自动质量门禁;不通过就回退原图
7. **动图保护**——检测到 APNG 直接保留原图,不把动画误压成单帧
8. **原地覆盖有护栏**——见下,默认不允许在不可恢复的位置乱改用户文件

内核 = `pngquant`(有损量化,24/32bit → 8bit 调色板)+ `oxipng`(无损重编码和元数据清理)。这条路线与 TinyPNG 官方公开的"颜色量化 + 元数据清理"原理一致,但不声称复刻其未公开实现。

## ⚠️ 原地覆盖护栏(Agent 必须知道)

原地覆盖是有损重编码,**不在 git 里时原图永久不可恢复**。脚本的默认行为:

| 场景 | 行为 |
|---|---|
| 目标在 git 工作树内 | 正常原地覆盖,无需额外参数 |
| 目标**不在** git 工作树 | **拒绝并 exit 1**,先 dry-run 预估"将改动 N 张",提示三选一 |
| 任何情况加 `--output-dir DIR` | 压缩产物按相对路径写到 DIR,**原图零改动**(推荐给不确定的目录用) |
| 非 git 目录加 `--allow-non-git` | 显式接受不可恢复,执行原地覆盖 |

拒绝信息里已列出将要改动的文件数;确认闸门不靠交互 prompt,而是 `--allow-non-git` / `--output-dir` 这两个显式参数。

## 退出码语义(Agent/CI 据此判断成败)

| exit code | 含义 |
|---|---|
| 0 | 全部成功(含门禁回退、已知坏图跳过——这些是正常业务结果) |
| 1 | 参数/路径错误、缺依赖、护栏拒绝原地覆盖 |
| 2 | 有图真失败(解码失败、pngquant/oxipng 报错);硬门禁/质量门禁回退**不计入**失败 |

## 怎么用

```bash
# git 工程内:一键跑(原地覆盖)
./compress.sh /path/to/iOSProject

# 只看效果不改文件(先预估收益)
./compress.sh /path/to/iOSProject --dry-run

# 不确定目录是否安全:输出副本,原图不动
python3 compress_images.py /path/to/proj --output-dir /tmp/compressed

# 非 git 目录、确认已备份:显式放行原地覆盖
python3 compress_images.py /path/to/proj --allow-non-git

# 指定并行数
./compress.sh /path/to/iOSProject -j 8
```

`compress.sh` 只是加了依赖自检 + brew 自动安装的一层壳,实际引擎是 `compress_images.py`。

### 坏图与缓存

- 解码失败的坏图,其内容 hash 会持久化进缓存(`errors` 字段),下次运行**默认跳过**并在汇总单列"已知坏图(跳过)",不再每次刷 stderr。
- 修好图后加 `--retry-errors` 重检。
- 缓存文件损坏(非法 JSON/合并冲突)不会崩溃:警告一句、改名为 `.png_compress_cache.json.bak`、按空缓存重建。

### 目录排除规则

- `.git` 任意层级跳过。
- `Pods`/`Carthage`/`build`/`DerivedData`/`node_modules`/`.build`/`fastlane` **只在工程顶层直接子目录命中时排除**——`Resources/build_icons/`、`Resources/build/` 这类嵌套同名目录视为用户资产照常处理。
- 需要按名字在任意层级排除自定义目录:`--exclude NAME`(可重复,如 `--exclude build_assets`)。

## 输出长啥样

```
扫描到 PNG: 1234 张 | 缓存已记录: 0 张 | 已知坏图: 1 张 | 并行: 8 | 原地覆盖
自检门禁: hard=on | quality=on | ssim=on
===== 完成 =====
压缩: 900  跳过(缓存): 0  已知坏图(跳过): 1  保留原图(压不动): 330  跳过(APNG): 4  硬门禁回退: 0  质量门禁回退: 2  失败: 0
本轮压缩前: 45.2MB  压缩后: 12.8MB  节省: 32.4MB (71.7%)
耗时: 38.5s
```

再跑第二次,压过的全部走"跳过(缓存)",秒回。

---

## 实现细节(感兴趣再看)

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

> 这套自动门禁只负责拦"坏图/尺寸变了/alpha 丢了/明显灾难性劣化"。"到底糊不糊"仍然有主观性,建议每轮再按体积下降最大、压缩比例最高、AppIcon/launchscreen、透明 icon 等维度做肉眼抽检。

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

**依赖与跨平台注意:**

- macOS:`brew install pngquant oxipng`
- Ubuntu:`sudo apt-get install pngquant` + `cargo install oxipng`(或下 GitHub release 二进制)
- **Linux 没有 macOS `sips` 兜底**:Pillow 缺失时硬门禁和质量门禁会同时整体失效,需要 `python3 -m pip install Pillow`,或同时加 `--no-hard-gate --no-quality-gate` 才能跑通(只加 `--no-quality-gate` 会让每张图都报解码失败)。
- 测试:`python3 -m unittest discover -s tests -v`(全部在 /tmp 临时目录造素材,不碰用户文件)。
