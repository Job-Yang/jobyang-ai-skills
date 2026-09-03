#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
App 工程 PNG 批量压缩
=====================
算法思路:
    pngquant (有损量化, 24/32bit -> 8bit 调色板)  →  oxipng (无损榨 DEFLATE + 删元数据)
这条路线与 TinyPNG 官方描述的“颜色量化 + 元数据清理”一致,但不声称复刻其未公开实现。

核心特性:
    1. 不重复压   —— 用「文件内容 hash」做缓存 key, 压过的最终态直接跳过, 绝不二次量化毁图
    2. 增量持续压 —— 新增/改动的图自动识别并压缩, 缓存共享可提交进仓库/团队复用
    3. 小图友好   —— 20K 以下 icon 用更保守的质量下限, 避免小图糊掉
    4. 变大回退   —— 压完比原图大就丢弃, 保留原图 (icon 常见)
    5. 动图保护   —— APNG 原样保留, 避免动画被压成单帧
    6. 原地覆盖   —— 直接改工程里的图, 不依赖具体 App 或构建系统
    7. 并行       —— 多进程跑满 CPU
    8. 无脑       —— 一个参数(工程根目录)即可, 其余全自动

用法:
    python3 compress_images.py /path/to/AppProject           # 正式压缩
    python3 compress_images.py /path/to/AppProject --dry-run # 只统计不改文件
    python3 compress_images.py /path/to/AppProject -j 8      # 指定并行数
"""

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageStat
    Image.MAX_IMAGE_PIXELS = None
except Exception:  # Pillow 缺失时仍保留 sips 硬门禁
    Image = ImageChops = ImageStat = None

try:
    import numpy as np
except Exception:
    np = None

# ------------------------- 可调参数(已对齐 TinyPNG) -------------------------

# 普通图片(>= SMALL_THRESHOLD)的 pngquant 质量区间 [min-max]
#   min 是"低于此质量宁可放弃量化", max 是目标质量。85 上限接近 TinyPNG 观感。
QUALITY_NORMAL = "65-85"

# 小图/icon(< SMALL_THRESHOLD)的质量区间, 下限抬高避免小图糊
QUALITY_SMALL = "70-90"

# 小图阈值(字节):20KB 以下按 icon 场景使用更保守的质量下限
SMALL_THRESHOLD = 20 * 1024

# pngquant 抖动(0.0-1.0), 越高越接近原图渐变但体积略增; TinyPNG 默认开启抖动
DITHER = "1.0"

# oxipng 优化级别: max 最狠; 若嫌慢可改 "4"
OXIPNG_LEVEL = "max"

# 缓存文件名(存工程根目录, 建议提交进仓库让团队/CI 共享)
CACHE_NAME = ".png_compress_cache.json"

# 排除目录(Pods/第三方/构建产物等, 按需增删)
EXCLUDE_DIRS = {
    ".git", "Pods", "Carthage", "build", "DerivedData",
    "node_modules", ".build", "fastlane",
}

# 默认自检门禁。硬门禁防坏图；质量门禁只做“灾难保护”，主观糊不糊仍建议肉眼抽检。
QUALITY_MIN_PSNR = 28.0
QUALITY_MIN_SSIM = 0.95
QUALITY_MAX_MAE = 12.0
QUALITY_ALPHA_MAX_MAE = 3.0
QUALITY_SAMPLE_MAX_SIDE = 256

# --------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def which_or_die(names):
    """检查依赖是否安装, 缺失则报错退出。"""
    missing = [n for n in names if shutil.which(n) is None]
    if missing:
        sys.exit(
            "缺少依赖: {}\n请先安装:\n  brew install {}".format(
                ", ".join(missing), " ".join(missing)
            )
        )


def find_pngs(root: Path):
    """递归找出所有 .png, 跳过排除目录。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn.lower().endswith(".png"):
                yield Path(dirpath) / fn


def apng_frame_count(path: Path) -> int:
    """读取 APNG 的 acTL 块；普通 PNG 返回 1。"""
    try:
        with open(path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return 1
            while True:
                raw_length = f.read(4)
                if len(raw_length) != 4:
                    return 1
                length = struct.unpack(">I", raw_length)[0]
                chunk_type = f.read(4)
                if len(chunk_type) != 4:
                    return 1
                if chunk_type == b"acTL":
                    data = f.read(length)
                    return max(1, struct.unpack(">I", data[:4])[0]) if len(data) >= 4 else 1
                f.seek(length + 4, os.SEEK_CUR)  # data + CRC
                if chunk_type == b"IEND":
                    return 1
    except (OSError, struct.error):
        return 1


def probe_png(path: Path):
    """
    返回 PNG 的可解码信息。优先 Pillow, 缺失时退到 macOS sips。
    ok=false 表示这张图本身无法被系统/Pillow 解码。
    """
    if Image is not None:
        try:
            with Image.open(path) as im:
                im.load()
                bands = im.getbands()
                has_alpha = "A" in bands or "transparency" in im.info
                return {
                    "ok": True,
                    "width": im.width,
                    "height": im.height,
                    "mode": im.mode,
                    "has_alpha": has_alpha,
                    "frame_count": max(getattr(im, "n_frames", 1), apng_frame_count(path)),
                    "source": "pillow",
                }
        except Exception as e:
            return {"ok": False, "msg": f"Pillow decode failed: {str(e)[:160]}"}

    if shutil.which("sips"):
        r = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight",
             "-g", "hasAlpha", str(path)],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            return {"ok": False, "msg": r.stderr.strip()[:160] or "sips decode failed"}
        info = {}
        for line in r.stdout.splitlines():
            if ":" in line:
                k, v = line.strip().split(":", 1)
                info[k.strip()] = v.strip()
        try:
            return {
                "ok": True,
                "width": int(info.get("pixelWidth", "0")),
                "height": int(info.get("pixelHeight", "0")),
                "mode": "",
                "has_alpha": info.get("hasAlpha", "").lower() in {"yes", "true", "1"},
                "frame_count": apng_frame_count(path),
                "source": "sips",
            }
        except Exception as e:
            return {"ok": False, "msg": f"sips parse failed: {str(e)[:160]}"}

    return {"ok": False, "msg": "no Pillow or sips available for PNG validation"}


def hard_gate(original_probe, candidate_probe):
    """硬门禁：必须可解码、宽高不变、alpha 通道存在性不丢。"""
    if not original_probe.get("ok"):
        return False, f"source decode failed: {original_probe.get('msg', '')}"
    if not candidate_probe.get("ok"):
        return False, f"candidate decode failed: {candidate_probe.get('msg', '')}"
    if (original_probe["width"], original_probe["height"]) != (
        candidate_probe["width"], candidate_probe["height"]
    ):
        return False, (
            "dimension changed: "
            f"{original_probe['width']}x{original_probe['height']} -> "
            f"{candidate_probe['width']}x{candidate_probe['height']}"
        )
    if original_probe.get("has_alpha") and not candidate_probe.get("has_alpha"):
        return False, "alpha channel lost"
    if original_probe.get("frame_count", 1) != candidate_probe.get("frame_count", 1):
        return False, (
            "animation frames changed: "
            f"{original_probe.get('frame_count', 1)} -> "
            f"{candidate_probe.get('frame_count', 1)}"
        )
    return True, "ok"


def resize_for_quality(im):
    im = im.copy()
    if max(im.size) > QUALITY_SAMPLE_MAX_SIDE:
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        im.thumbnail((QUALITY_SAMPLE_MAX_SIDE, QUALITY_SAMPLE_MAX_SIDE), resampling)
    return im


def psnr_from_rmse(rmse):
    if rmse <= 0:
        return 99.0
    return 20 * math.log10(255.0 / rmse)


def global_ssim(gray_a, gray_b):
    if np is None:
        return None
    a = np.asarray(gray_a, dtype=np.float32)
    b = np.asarray(gray_b, dtype=np.float32)
    if a.size == 0:
        return 1.0
    mean_a = float(a.mean())
    mean_b = float(b.mean())
    var_a = float(a.var())
    var_b = float(b.var())
    cov = float(((a - mean_a) * (b - mean_b)).mean())
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    den = (mean_a * mean_a + mean_b * mean_b + c1) * (var_a + var_b + c2)
    if den == 0:
        return 1.0
    return ((2 * mean_a * mean_b + c1) * (2 * cov + c2)) / den


def image_metrics(a, b):
    diff = ImageChops.difference(a, b)
    stat = ImageStat.Stat(diff)
    channels = max(1, len(stat.mean))
    mae = sum(stat.mean) / channels
    rmse = math.sqrt(sum(v * v for v in stat.rms) / channels)
    ssim = global_ssim(a.convert("L"), b.convert("L"))
    return {"mae": mae, "rmse": rmse, "psnr": psnr_from_rmse(rmse), "ssim": ssim}


def composite_on_bg(rgba, color):
    bg = Image.new("RGBA", rgba.size, color)
    return Image.alpha_composite(bg, rgba).convert("RGB")


def quality_gate(original_path: Path, candidate_path: Path, cfg):
    """
    自动质量门禁：用 before/after 像素指标拦住灾难性劣化。
    这不是主观视觉验收的替代；它只负责“明显坏/明显糊”的自动回退。
    """
    if not cfg.get("quality_gate"):
        return True, "disabled"
    if Image is None or ImageChops is None or ImageStat is None:
        return True, "skipped: Pillow unavailable"

    with Image.open(original_path) as im_a, Image.open(candidate_path) as im_b:
        im_a.load()
        im_b.load()
        if im_a.size != im_b.size:
            return False, f"dimension changed: {im_a.size} -> {im_b.size}"

        has_alpha = "A" in im_a.getbands() or "transparency" in im_a.info
        a_rgba = resize_for_quality(im_a.convert("RGBA"))
        b_rgba = resize_for_quality(im_b.convert("RGBA"))

        if has_alpha:
            metric_sets = [
                image_metrics(composite_on_bg(a_rgba, (255, 255, 255, 255)),
                              composite_on_bg(b_rgba, (255, 255, 255, 255))),
                image_metrics(composite_on_bg(a_rgba, (0, 0, 0, 255)),
                              composite_on_bg(b_rgba, (0, 0, 0, 255))),
            ]
            alpha_metrics = image_metrics(
                a_rgba.getchannel("A").convert("L"),
                b_rgba.getchannel("A").convert("L"),
            )
        else:
            metric_sets = [image_metrics(a_rgba.convert("RGB"), b_rgba.convert("RGB"))]
            alpha_metrics = None

    min_psnr = min(m["psnr"] for m in metric_sets)
    max_mae = max(m["mae"] for m in metric_sets)
    ssim_values = [m["ssim"] for m in metric_sets if m["ssim"] is not None]
    min_ssim = min(ssim_values) if ssim_values else None
    alpha_mae = alpha_metrics["mae"] if alpha_metrics else 0.0

    bad = min_psnr < cfg["quality_min_psnr"] or max_mae > cfg["quality_max_mae"]
    if min_ssim is not None and min_ssim < cfg["quality_min_ssim"]:
        bad = True
    if alpha_mae > cfg["quality_alpha_max_mae"]:
        bad = True

    ssim_text = "n/a" if min_ssim is None else f"{min_ssim:.4f}"
    msg = (
        f"psnr={min_psnr:.2f} ssim={ssim_text} "
        f"mae={max_mae:.2f} alpha_mae={alpha_mae:.2f}"
    )
    return (not bad), msg


def compress_one(png_path: Path, cache_hashes: set, dry_run: bool, gate_cfg: dict):
    """
    压缩单张图。返回 dict: {status, path, before, after}
    status ∈ skip_cached / compressed / kept_original / kept_animated / kept_hard_gate /
              kept_quality_gate / error
    """
    try:
        before = png_path.stat().st_size
        cur_hash = sha256_of(png_path)

        # 缓存命中 → 说明这张图已是我处理过的最终态, 直接跳过, 绝不二次压缩
        if cur_hash in cache_hashes:
            return {"status": "skip_cached", "path": png_path,
                    "before": before, "after": before, "hash": cur_hash}

        quality = QUALITY_SMALL if before < SMALL_THRESHOLD else QUALITY_NORMAL
        if apng_frame_count(png_path) > 1:
            return {"status": "kept_animated", "path": png_path,
                    "before": before, "after": before, "hash": cur_hash}

        original_probe = probe_png(png_path) if gate_cfg.get("hard_gate") else None
        if gate_cfg.get("hard_gate") and not original_probe.get("ok"):
            return {"status": "error", "path": png_path,
                    "before": before, "after": before,
                    "msg": original_probe.get("msg", "source decode failed")[:200]}

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "out.png"

            # ① pngquant 有损量化。--skip-if-larger: 量化后变大就报错(非0)不产出。
            r1 = subprocess.run(
                ["pngquant", "--quality", quality, "--speed", "1",
                 f"--floyd={DITHER}", "--strip", "--skip-if-larger",
                 "--force", "--output", str(tmp), str(png_path)],
                capture_output=True,
            )
            # pngquant 退出码 98/99 = 达不到质量或变大, 属正常"放弃", 用原图继续
            if r1.returncode not in (0, 98, 99):
                return {"status": "error", "path": png_path,
                        "before": before, "after": before,
                        "msg": r1.stderr.decode(errors="ignore")[:200]}

            # 若 pngquant 放弃了(没产出 tmp), 用原图拷进去让 oxipng 走无损那道
            if not tmp.exists():
                shutil.copyfile(png_path, tmp)

            # ② oxipng 无损收尾: 榨 DEFLATE + 删所有元数据
            r2 = subprocess.run(
                ["oxipng", "-o", OXIPNG_LEVEL, "--strip", "all",
                 "-q", str(tmp)],
                capture_output=True,
            )
            if r2.returncode != 0:
                return {"status": "error", "path": png_path,
                        "before": before, "after": before,
                        "msg": r2.stderr.decode(errors="ignore")[:200]}

            after = tmp.stat().st_size

            # 变大回退: 压完 >= 原图, 保留原图。但仍把"原图 hash"记入缓存, 下次不再尝试
            if after >= before:
                return {"status": "kept_original", "path": png_path,
                        "before": before, "after": before, "hash": cur_hash}

            if gate_cfg.get("hard_gate"):
                candidate_probe = probe_png(tmp)
                ok, msg = hard_gate(original_probe, candidate_probe)
                if not ok:
                    return {"status": "kept_hard_gate", "path": png_path,
                            "before": before, "after": before, "hash": cur_hash,
                            "candidate_after": after, "msg": msg[:200]}

            ok, msg = quality_gate(png_path, tmp, gate_cfg)
            if not ok:
                return {"status": "kept_quality_gate", "path": png_path,
                        "before": before, "after": before, "hash": cur_hash,
                        "candidate_after": after, "msg": msg[:200]}

            if not dry_run:
                shutil.copymode(png_path, tmp)  # 保留原文件权限
                shutil.move(str(tmp), str(png_path))
                new_hash = sha256_of(png_path)
            else:
                new_hash = cur_hash  # dry-run 不改文件, 缓存不写实

            return {"status": "compressed", "path": png_path,
                    "before": before, "after": after, "hash": new_hash}
    except Exception as e:  # noqa
        return {"status": "error", "path": png_path,
                "before": 0, "after": 0, "msg": str(e)[:200]}


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def main():
    ap = argparse.ArgumentParser(description="App 工程 PNG 批量压缩")
    ap.add_argument("root", nargs="?", default=".",
                    help="App 工程或图片目录 (不传则默认当前目录, 递归查找)")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 4,
                    help="并行进程数, 默认=CPU核数")
    ap.add_argument("--dry-run", action="store_true", help="只统计不修改文件")
    ap.add_argument("--no-hard-gate", action="store_true",
                    help="关闭硬门禁(解码/宽高/alpha 校验), 不建议")
    ap.add_argument("--no-quality-gate", action="store_true",
                    help="关闭自动质量门禁(PSNR/SSIM/MAE), 不建议")
    ap.add_argument("--quality-min-psnr", type=float, default=QUALITY_MIN_PSNR,
                    help=f"质量门禁最低 PSNR, 默认 {QUALITY_MIN_PSNR}")
    ap.add_argument("--quality-min-ssim", type=float, default=QUALITY_MIN_SSIM,
                    help=f"质量门禁最低 SSIM(有 numpy 时启用), 默认 {QUALITY_MIN_SSIM}")
    ap.add_argument("--quality-max-mae", type=float, default=QUALITY_MAX_MAE,
                    help=f"质量门禁最大平均绝对误差, 默认 {QUALITY_MAX_MAE}")
    ap.add_argument("--quality-alpha-max-mae", type=float, default=QUALITY_ALPHA_MAX_MAE,
                    help=f"透明通道最大平均绝对误差, 默认 {QUALITY_ALPHA_MAX_MAE}")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"目录不存在: {root}")

    which_or_die(["pngquant", "oxipng"])
    gate_cfg = {
        "hard_gate": not args.no_hard_gate,
        "quality_gate": not args.no_quality_gate,
        "quality_min_psnr": args.quality_min_psnr,
        "quality_min_ssim": args.quality_min_ssim,
        "quality_max_mae": args.quality_max_mae,
        "quality_alpha_max_mae": args.quality_alpha_max_mae,
    }
    if gate_cfg["quality_gate"] and Image is None:
        sys.exit("质量门禁需要 Python Pillow。请先安装: python3 -m pip install Pillow；"
                 "或显式加 --no-quality-gate 关闭质量门禁。")

    cache_path = root / CACHE_NAME
    if cache_path.exists():
        cache_hashes = set(json.loads(cache_path.read_text()).get("hashes", []))
    else:
        cache_hashes = set()

    pngs = list(find_pngs(root))
    print(f"扫描到 PNG: {len(pngs)} 张 | 缓存已记录: {len(cache_hashes)} 张 | "
          f"并行: {args.jobs}{' | DRY-RUN' if args.dry_run else ''}")
    quality_state = "off" if not gate_cfg["quality_gate"] else (
        "on" if Image is not None else "skipped(Pillow missing)"
    )
    ssim_state = "on" if np is not None else "skipped(numpy missing)"
    print(f"自检门禁: hard={'on' if gate_cfg['hard_gate'] else 'off'} | "
          f"quality={quality_state} | ssim={ssim_state}")
    if not pngs:
        return

    t0 = time.time()
    tot_before = tot_after = 0
    n_comp = n_skip = n_kept = n_animated = n_hard_gate = n_quality_gate = n_err = 0
    n_gate_logs = 0
    new_hashes = set(cache_hashes)

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(compress_one, p, cache_hashes, args.dry_run, gate_cfg): p
                for p in pngs}
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            done += 1
            st = r["status"]
            if st == "compressed":
                n_comp += 1
                tot_before += r["before"]
                tot_after += r["after"]
                new_hashes.add(r["hash"])
            elif st == "skip_cached":
                n_skip += 1
            elif st == "kept_original":
                n_kept += 1
                new_hashes.add(r["hash"])
            elif st == "kept_animated":
                n_animated += 1
                new_hashes.add(r["hash"])
            elif st == "kept_hard_gate":
                n_hard_gate += 1
                new_hashes.add(r["hash"])
                if n_gate_logs < 50:
                    print(f"  [HARD-GATE] {r['path']}: {r.get('msg','')}")
                    n_gate_logs += 1
            elif st == "kept_quality_gate":
                n_quality_gate += 1
                new_hashes.add(r["hash"])
                if n_gate_logs < 50:
                    print(f"  [QUALITY-GATE] {r['path']}: {r.get('msg','')}")
                    n_gate_logs += 1
            elif st == "error":
                n_err += 1
                print(f"  [ERR] {r['path']}: {r.get('msg','')}")
            if done % 500 == 0:
                print(f"  ...进度 {done}/{len(pngs)}")

    # 写回缓存(dry-run 不写, 避免污染)
    if not args.dry_run:
        cache_path.write_text(json.dumps(
            {"hashes": sorted(new_hashes)}, ensure_ascii=False))

    dt = time.time() - t0
    saved = tot_before - tot_after
    ratio = (saved / tot_before * 100) if tot_before else 0
    print("\n===== 完成 =====")
    print(f"压缩: {n_comp}  跳过(缓存): {n_skip}  保留原图(压不动): {n_kept}  "
          f"跳过(APNG): {n_animated}  硬门禁回退: {n_hard_gate}  "
          f"质量门禁回退: {n_quality_gate}  失败: {n_err}")
    print(f"本轮压缩前: {human(tot_before)}  压缩后: {human(tot_after)}  "
          f"节省: {human(saved)} ({ratio:.1f}%)")
    print(f"耗时: {dt:.1f}s")
    if args.dry_run:
        print("(DRY-RUN: 未修改任何文件, 未更新缓存)")


if __name__ == "__main__":
    main()
