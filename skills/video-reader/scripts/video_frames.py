#!/usr/bin/env python3
"""
video_frames.py — 把视频翻译成"带时间戳的关键帧 + 运动时间线",喂给看不了视频的大模型。

本脚本不含任何业务逻辑(不懂"卡顿""面板""手势"),只做一件纯粹的事:
用帧差(相邻帧像素差异)找出"哪几秒画面在动",据此智能抽帧。

两个子命令:
  scan  —— 粗扫全片(或某段):算运动时间线、折叠静止段、在有动作处稀疏抽帧。
           先看时间线决定哪里有问题,再用 zoom 下钻。
  zoom  —— 对指定区间高密度抽帧,看细节。

帧差用"分块"方式(把帧缩小成网格逐块比),对翻拍视频的轻微抖动更稳。
帧不落盘到用户可见目录,只写临时目录供模型 Read 后即弃。
"""

import argparse
import atexit
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

# 本次运行自动创建的临时帧目录(用户显式 --outdir / --debug 指定的目录不入列)。
# --cleanup 只清理这个列表里的目录, 绝不碰用户自己指定的输出位置。
TEMP_DIRS = []

# 未设此环境变量=1 时, 不静默 pip 装包(cv2/numpy 约 90MB, whisper 含 torch 约 2GB)。
PIP_GATE_ENV = "VIDEO_READER_YES_PIP"


def _pip_allowed():
    return os.environ.get(PIP_GATE_ENV) == "1"

# 在受限/沙箱环境里,OpenCV/FFmpeg 默认开大量线程会触发 "Can't spawn new thread"。
# 必须在 import cv2 之前把相关线程数压到 1,保证可移植。
os.environ.setdefault("OPENCV_FFMPEG_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")


def _interpreter_id():
    """返回当前解释器的"身份三件套",用于自报家门和错配诊断。
    一台 Mac 上常并存好几个 python3(系统/homebrew/pyenv),
    pip --user 又是按版本号分目录存包的。装包和跑脚本只要不是同一个解释器,
    就会出现"装了却 import 不到"。所以脚本必须一启动就说清楚"我是谁、我认哪个包目录"。"""
    try:
        import site
        usersite = site.getusersitepackages()
    except Exception:
        usersite = "(无法获取)"
    ver = sys.version.split()[0]
    return sys.executable, ver, usersite


def _print_banner():
    """启动即自报家门:打到 stderr,不污染 stdout 的 JSON。
    错配时(TRAE 喊'装了却用不了'),看这三行就能一眼定位是哪个 python3 在跑。"""
    exe, ver, usersite = _interpreter_id()
    print("[video-reader] 解释器自检 (排查'装了却用不了'看这里):", file=sys.stderr, flush=True)
    print(f"  - python   : {exe}", file=sys.stderr, flush=True)
    print(f"  - version  : {ver}", file=sys.stderr, flush=True)
    print(f"  - user-site: {usersite}", file=sys.stderr, flush=True)


def _ensure_deps():
    """依赖自检 + 自愈。
    先尝试导入;缺了就自动 pip 装(--user --break-system-packages,不污染系统);
    装不动就打印一句人话提示让用户手动装,然后退出,绝不抛一堆栈让人懵。

    关键:无论成败都先 _print_banner() 自报家门。因为最常见的坑不是"没装",
    而是"装在解释器 A、跑在解释器 B"——这种情况下报错信息必须带上"我是谁",
    否则用户得自己敲 which -a / import site 三条命令才能定位,排查成本全甩给人。

    matplotlib 是软依赖:只有 --debug 画曲线图才用,这里不强制,缺了到时再提示。
    """
    required = {
        "cv2": "opencv-python-headless",   # import 名 -> pip 包名
        "numpy": "numpy",
    }
    # 用 find_spec 判断包是否可用,而不是真的 import_module 把模块执行进来:
    # ① 依赖自检只关心"装没装/找不找得到",不需要执行模块副作用;
    # ② 避免动态导入(import_module/__import__),模块来源更可控、静态可审计。
    missing = [(mod, pkg) for mod, pkg in required.items()
               if importlib.util.find_spec(mod) is None]

    if not missing:
        return

    pkgs = [pkg for _, pkg in missing]
    # 装包确认闸门: Agent 场景下"首次跑就静默装 90MB"不可接受。
    # 未设 VIDEO_READER_YES_PIP=1 → 打印体量预告+手动命令, exit 3, 不动用户环境。
    if not _pip_allowed():
        exe, ver, _ = _interpreter_id()
        print(
            f"[video-reader] 检测到缺少依赖: {', '.join(pkgs)}(opencv 约 90MB)。\n"
            "  为避免 Agent 静默修改用户 Python 环境, 未设放行变量前不执行安装。\n"
            f"  放行(本次允许自动装): {PIP_GATE_ENV}=1 python3 {sys.argv[0]} ...\n"
            f"  或手动安装到当前解释器: {exe} -m pip install --user --break-system-packages {' '.join(pkgs)}",
            file=sys.stderr, flush=True)
        sys.exit(3)

    print(f"[video-reader] 检测到缺少依赖: {', '.join(pkgs)},尝试用上面这个解释器自动安装…",
          file=sys.stderr, flush=True)
    cmd = [sys.executable, "-m", "pip", "install",
           "--user", "--break-system-packages", "--quiet"] + pkgs
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        exe, ver, _ = _interpreter_id()
        print(
            f"\n[video-reader] 自动安装失败。当前跑脚本的解释器是: {exe} (Python {ver})\n"
            "  排查思路: 一台机器常有多个 python3(系统/homebrew/pyenv)。\n"
            "  ① 若依赖其实装在'别的' python 上,直接换那个解释器跑脚本即可,例如:\n"
            f"       /opt/homebrew/opt/python@{ver.rsplit('.', 1)[0]}/bin/python{ver.rsplit('.', 1)[0]} <本脚本> ...\n"
            "  ② 若确实没装,手动执行下面这条(注意开头就是当前这个解释器)后重试:\n"
            f"       {exe} -m pip install --user --break-system-packages {' '.join(pkgs)}\n"
            f"  (失败原因: {e})",
            file=sys.stderr, flush=True)
        sys.exit(3)

    # 装完重新校验,确认真的能找到。先清 import 缓存,否则刚装的包 find_spec 可能看不到。
    importlib.invalidate_caches()
    still = [pkg for mod, pkg in missing
             if importlib.util.find_spec(mod) is None]
    if still:
        exe, ver, usersite = _interpreter_id()
        print(
            "\n[video-reader] 依赖已装但仍 import 不到——典型的'装在 A、跑在 B'解释器错配。\n"
            f"  当前解释器 : {exe} (Python {ver})\n"
            f"  它只认的包目录: {usersite}\n"
            "  也就是说包大概率装到了'另一个 python'的目录里,当前这个看不见。\n"
            "  解法(任选一): \n"
            "    ① 找到真正装了包的那个 python,用它的绝对路径跑本脚本(最省事);\n"
            f"    ② 或强制给当前解释器再装一遍: {exe} -m pip install --user --break-system-packages {' '.join(still)}\n"
            "    ③ 最干净: 建个 venv 锁死解释器+包(python3.x -m venv .venv,再用 .venv/bin/python 跑)。",
            file=sys.stderr, flush=True)
        sys.exit(3)
    print("[video-reader] 依赖安装完成(已装到上面这个解释器)。", file=sys.stderr, flush=True)


_print_banner()
_ensure_deps()

import cv2
import numpy as np

cv2.setNumThreads(1)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def open_video(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        log(f"ERROR: 无法打开视频: {path}")
        sys.exit(2)
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if fps <= 0 or fps > 240:
        fps = 30.0  # 兜底:有些视频元数据缺失/异常
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration = total / fps if total > 0 else 0.0
    # 防呆: "能打开但不是视频"的文件(PNG 改名 mp4、损坏/截断文件)
    # 不得静默当成"全静止视频" exit 0 —— 那会让 Agent 一本正经回复"视频里没有动作"。
    if total <= 0 or duration <= 0 or w == 0 or h == 0:
        log(f"ERROR: 文件能打开但不含可解码视频流"
            f"(total_frames={total}, {w}x{h}, duration={duration:.2f}s)。\n"
            f"  常见原因: 改后缀上传时传错了文件(如 PNG 改名 mp4)、文件损坏或截断。\n"
            f"  请确认文件内容真的是视频: {path}")
        sys.exit(2)
    return cap, fps, total, duration, w, h


def motion_signature(frame, grid=16, blur=3):
    """把一帧压成 grid×grid 的灰度小图,作为运动比对的指纹。
    缩小 + 模糊能吸收翻拍噪点和编码块效应,只留下"大块画面变化"。"""
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if blur > 0:
        g = cv2.GaussianBlur(g, (blur * 2 + 1, blur * 2 + 1), 0)
    small = cv2.resize(g, (grid, grid), interpolation=cv2.INTER_AREA)
    return small.astype(np.float32)


def analyze_motion(cap, fps, t_start, t_end, analyze_fps=10.0, grid=16):
    """在 [t_start, t_end] 区间按 analyze_fps 采样,算每个采样点相对上一个的运动分。
    返回 [(t, score), ...]。score = 分块平均绝对差(0~255),越大动得越凶。

    性能关键:绝不在循环里逐帧 cap.set(POS_FRAMES) 随机 seek——OpenCV 的随机定位
    对长视频/B 帧多的编码极慢(反复回退到关键帧重解码),长录屏会慢到像卡死。
    这里只在区间起点 seek 一次,之后用 grab() 顺序跳帧(grab 只取不解码,很便宜),
    仅在命中目标采样帧时才 retrieve() 解码,把解码次数降到最低。"""
    step = max(1, int(round(fps / analyze_fps)))
    f0 = int(round(t_start * fps))
    f1 = int(round(t_end * fps))
    samples = []
    prev = None
    cap.set(cv2.CAP_PROP_POS_FRAMES, f0)  # 全程只 seek 这一次
    fidx = f0
    next_proc = f0          # 下一个要解码处理的帧号
    last_log_t = -1e9       # 进度日志节流
    span = max(1e-6, (f1 - f0) / fps)
    while fidx <= f1:
        if not cap.grab():  # 顺序推进一帧(不解码),失败说明读到尾了
            break
        if fidx >= next_proc:
            ok, frame = cap.retrieve()  # 只解码命中帧
            if not ok or frame is None:
                break
            sig = motion_signature(frame, grid=grid)
            t = fidx / fps
            score = 0.0 if prev is None else float(np.mean(np.abs(sig - prev)))
            samples.append((round(t, 3), round(score, 3)))
            prev = sig
            next_proc += step
            # 长视频进度提示:每处理约 5s 内容打一行,避免"看起来卡死"
            if t - last_log_t >= 5.0:
                log(f"  分析中… {t - t_start:.0f}s / {span:.0f}s")
                last_log_t = t
        fidx += 1
    return samples


def auto_threshold(scores):
    """自动定"动/不动"的分界线。用非零运动分的中位数做基准,
    避免写死阈值在不同亮度/不同录制方式的视频上失灵。"""
    nz = [s for s in scores if s > 0.01]
    if not nz:
        return 0.5
    med = float(np.median(nz))
    # 阈值取中位数的一半,且设一个地板防止纯静态视频里噪点被当成运动
    return max(0.8, med * 0.5)


def segment_motion(samples, thr):
    """把采样点按"静止段 / 活动段"合并成连续区间。
    返回 [(t0, t1, 'static'|'active', peak_score), ...]"""
    if not samples:
        return []
    segs = []
    cur_kind = None
    cur_t0 = samples[0][0]
    cur_peak = 0.0
    prev_t = samples[0][0]
    for t, s in samples:
        kind = "active" if s >= thr else "static"
        if cur_kind is None:
            cur_kind = kind
            cur_t0 = t
            cur_peak = s
        elif kind != cur_kind:
            segs.append((cur_t0, prev_t, cur_kind, round(cur_peak, 2)))
            cur_kind = kind
            cur_t0 = t
            cur_peak = s
        else:
            cur_peak = max(cur_peak, s)
        prev_t = t
    segs.append((cur_t0, prev_t, cur_kind, round(cur_peak, 2)))
    return segs


def merge_short(segs, min_static=0.4):
    """太短的静止段(比手势中途的一瞬停顿)不值得单列,并入相邻活动段,
    免得时间线被切得太碎。"""
    if not segs:
        return segs
    out = [segs[0]]
    for seg in segs[1:]:
        t0, t1, kind, peak = seg
        if kind == "static" and (t1 - t0) < min_static and out:
            pt0, pt1, pkind, ppeak = out[-1]
            if pkind == "active":
                out[-1] = (pt0, t1, "active", ppeak)
                continue
        out.append(seg)
    # 合并相邻同类
    merged = [out[0]]
    for seg in out[1:]:
        if seg[2] == merged[-1][2]:
            p = merged[-1]
            merged[-1] = (p[0], seg[1], p[2], max(p[3], seg[3]))
        else:
            merged.append(seg)
    return merged


def resolve_outdir(args, mode):
    """决定帧存哪。
    - 显式 --outdir:用它(稳定、可复查, 不入自动清理名单)。
    - --debug 但没给 --outdir:存到当前目录下 video_reader_debug/<视频名>_<mode>/,稳定可见。
    - 都没有:随机临时目录;记入 TEMP_DIRS, 退出时打印删除提示, --cleanup 时自动删。"""
    if args.outdir:
        return args.outdir, False
    if getattr(args, "debug", False):
        base = os.path.splitext(os.path.basename(args.video))[0]
        d = os.path.join(os.getcwd(), "video_reader_debug", f"{base}_{mode}")
        return d, True
    d = tempfile.mkdtemp(prefix=f"vframes_{mode}_")
    TEMP_DIRS.append(d)
    return d, False


def register_frame_dir_hint(outdir):
    """退出时在 stderr 打印删除提示(不自动删——模型 Read 帧可能滞后, 自动删会读空)。
    若 --cleanup 已在 main() 里把目录删了, 检查 isdir 后不打陈旧提示。"""
    def _hint():
        if os.path.isdir(outdir):
            log(f"[video-reader] 帧目录保留在 {outdir}; 确认模型读完后可删除: rm -rf {outdir}")
    atexit.register(_hint)


def truncate_times(times, max_frames, what):
    """抽帧上限保护: zoom 宽区间 × 高 density 可能静默产生数千帧、数百 MB。"""
    if len(times) > max_frames:
        log(f"  [warn] {what}将抽 {len(times)} 帧, 超过 --max-frames={max_frames}, "
            f"已截断到前 {max_frames} 个时间点; 区间过宽或 density 过高时请收窄区间。")
        return times[:max_frames]
    return times


def dump_debug(outdir, samples, thr, segs, extra=None):
    """调试模式:把运动分析的原始数据 + 一张帧差曲线图落盘,方便肉眼复查阈值/分段是否合理。"""
    debug_dir = os.path.join(outdir, "_debug")
    os.makedirs(debug_dir, exist_ok=True)
    # 1. 原始采样数据(每个采样点的时间+运动分)
    data = {
        "threshold": round(thr, 4),
        "samples": [{"t": t, "score": s} for t, s in samples],
        "segments": [{"start": t0, "end": t1, "kind": k, "peak": peak}
                     for t0, t1, k, peak in segs],
    }
    if extra:
        data.update(extra)
    with open(os.path.join(debug_dir, "motion_data.json"), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # 2. 运动曲线可视化(看帧差曲线 + 阈值线 + 活动段底纹)
    #    matplotlib 是 --debug 专用软依赖:缺了先尝试自动装,装不动再降级为只出 JSON。
    if importlib.util.find_spec("matplotlib") is None:
        log("  [debug] 未检测到 matplotlib,尝试自动安装(仅用于画曲线图)…")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install",
                 "--user", "--break-system-packages", "--quiet", "matplotlib"],
                check=True)
        except Exception as e:
            log(f"  [debug] matplotlib 自动安装失败,跳过曲线图(不影响主流程): {e}")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ts = [t for t, _ in samples]
        ss = [s for _, s in samples]
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(ts, ss, color="#2c7fb8", lw=1.2, label="motion score")
        ax.axhline(thr, color="#d95f0e", ls="--", lw=1, label=f"threshold={thr:.2f}")
        for t0, t1, k, _ in segs:
            if k == "active":
                ax.axvspan(t0, t1, color="#fdae6b", alpha=0.3)
        ax.set_xlabel("time (s)")
        ax.set_ylabel("motion score (0-255)")
        ax.set_title("Frame-diff motion curve (shaded = active segments)")
        ax.legend(loc="upper right")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(debug_dir, "motion_curve.png"), dpi=90)
        plt.close(fig)
        curve = os.path.join(debug_dir, "motion_curve.png")
    except Exception as e:
        curve = None
        log(f"  (调试曲线图生成跳过: {e})")
    log(f"  [debug] 运动数据 -> {os.path.join(debug_dir, 'motion_data.json')}")
    if curve:
        log(f"  [debug] 运动曲线 -> {curve}")
    return debug_dir


def save_frame(cap, fps, t, outdir, quality, max_w):
    fidx = int(round(t * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
    ok, frame = cap.read()
    if not ok or frame is None:
        return None
    h, w = frame.shape[:2]
    if max_w and w > max_w:
        nh = int(h * max_w / w)
        frame = cv2.resize(frame, (max_w, nh), interpolation=cv2.INTER_AREA)
    fn = os.path.join(outdir, f"t{t:07.2f}s.jpg")
    cv2.imwrite(fn, frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return fn


def pick_scan_frames(segs, density):
    """scan 模式:静止段一帧不抽(只在时间线里报),活动段按密度抽几帧。
    density = 活动段每秒抽几帧(粗扫,默认低)。每个活动段至少抽首/中/尾。"""
    times = []
    for t0, t1, kind, peak in segs:
        if kind != "active":
            continue
        dur = t1 - t0
        n = max(3, int(round(dur * density)))
        if dur <= 0:
            times.append(round(t0, 3))
            continue
        for i in range(n):
            t = t0 + dur * i / (n - 1) if n > 1 else t0
            times.append(round(t, 3))
    # 去重排序
    return sorted(set(times))


def fmt_timeline(segs):
    lines = []
    for t0, t1, kind, peak in segs:
        tag = "运动" if kind == "active" else "静止"
        extra = f" (峰值{peak})" if kind == "active" else ""
        lines.append(f"  {t0:6.2f}s - {t1:6.2f}s  [{tag}]{extra}")
    return "\n".join(lines)


def cmd_scan(args):
    cap, fps, total, duration, w, h = open_video(args.video)
    t_start = args.start if args.start is not None else 0.0
    t_end = args.end if args.end is not None else duration
    if t_end <= 0:
        t_end = duration if duration > 0 else 1e9

    log(f"视频: {args.video}")
    log(f"  分辨率 {w}x{h}, fps {fps:.2f}, 时长 {duration:.2f}s, 总帧 {total}")
    log(f"  扫描区间 {t_start:.2f}s - {t_end:.2f}s")

    samples = analyze_motion(cap, fps, t_start, t_end,
                             analyze_fps=args.analyze_fps, grid=args.grid)
    scores = [s for _, s in samples]
    thr = args.threshold if args.threshold is not None else auto_threshold(scores)
    segs = merge_short(segment_motion(samples, thr))

    active = [s for s in segs if s[2] == "active"]
    static_total = sum(t1 - t0 for t0, t1, k, _ in segs if k == "static")

    outdir, _ = resolve_outdir(args, "scan")
    os.makedirs(outdir, exist_ok=True)
    register_frame_dir_hint(outdir)

    if getattr(args, "debug", False):
        dump_debug(outdir, samples, thr, segs,
                   extra={"scan_range": [round(t_start, 3), round(t_end, 3)],
                          "fps": round(fps, 3)})

    times = pick_scan_frames(segs, args.density)
    times = truncate_times(times, args.max_frames, "scan")
    frames = []
    for t in times:
        fn = save_frame(cap, fps, t, outdir, args.quality, args.max_width)
        if fn:
            frames.append({"t": t, "path": fn})
    cap.release()

    result = {
        "mode": "scan",
        "video": os.path.abspath(args.video),
        "fps": round(fps, 3),
        "duration": round(duration, 3),
        "resolution": [w, h],
        "scan_range": [round(t_start, 3), round(t_end, 3)],
        "motion_threshold": round(thr, 3),
        "static_seconds_total": round(static_total, 2),
        "active_segments": [
            {"start": t0, "end": t1, "peak": peak}
            for t0, t1, k, peak in active
        ],
        "timeline": [
            {"start": t0, "end": t1, "kind": k, "peak": peak}
            for t0, t1, k, peak in segs
        ],
        "frames": frames,
        "outdir": outdir,
        "debug": bool(getattr(args, "debug", False)),
    }

    # 给人/给模型看的概要走 stderr,结构化 JSON 走 stdout
    log("\n=== 运动时间线 ===")
    log(fmt_timeline(segs))
    log(f"\n静止总时长 {static_total:.2f}s 已折叠(未抽帧)。")
    log(f"活动段 {len(active)} 个,共抽 {len(frames)} 帧 -> {outdir}")
    log("下一步:看上面时间线,挑可疑活动段用 zoom 下钻。\n")

    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_transcribe(args):
    """可选子命令:把视频/音频里的语音转成带时间戳的文字。
    画面看不出来的信息(旁白、客诉口述、报错语音提示)靠它补。

    这是软能力,缺依赖不报错只提示并跳过,绝不影响 scan/zoom 主流程:
      - 需要系统 ffmpeg(抽音轨)。OpenCV 自带的解码不暴露音频,所以这里只能依赖 ffmpeg。
      - 需要 openai-whisper(pip 包,会顺带拉 torch,较重,故设计成"用到才装")。
    任一缺失 → 打印安装方法 + 退出码 4(区别于硬错误),让上层据此决定降级。
    """
    video = args.video
    if not os.path.exists(video):
        log(f"ERROR: 文件不存在: {video}")
        sys.exit(2)

    # 1) ffmpeg 是硬前置(抽音轨),缺了直接提示装,不自动装系统级工具。
    if shutil.which("ffmpeg") is None:
        log("[transcribe] 需要系统 ffmpeg 抽音轨,但未找到。\n"
            "  安装: brew install ffmpeg (macOS) / apt-get install ffmpeg (Linux)。\n"
            "  装好重试;或本次跳过语音转写,只用 scan/zoom 看画面。")
        sys.exit(4)

    # 2) whisper 是 pip 软依赖,体积大(带 torch 约 2GB),所以"用到才按需装"。
    #    同样受 PIP_GATE_ENV 闸门: 未放行不静默装大包。
    if importlib.util.find_spec("whisper") is None:
        if not _pip_allowed():
            exe, ver, _ = _interpreter_id()
            log("[transcribe] 未检测到 openai-whisper, 自动安装会顺带拉约 2GB 的 torch。\n"
                "  为避免 Agent 静默装大包, 未设放行变量前不执行安装。\n"
                f"  放行(本次允许自动装): {PIP_GATE_ENV}=1 python3 {sys.argv[0]} transcribe ...\n"
                f"  或手动安装: {exe} -m pip install --user --break-system-packages openai-whisper\n"
                "  本次跳过语音转写。")
            sys.exit(4)
        log("[transcribe] 未检测到 openai-whisper,尝试按需安装(较大,含 torch)…")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install",
                            "--user", "--break-system-packages", "--quiet",
                            "openai-whisper"], check=True)
            importlib.invalidate_caches()
        except Exception as e:
            exe, ver, _ = _interpreter_id()
            log(f"[transcribe] 自动安装 openai-whisper 失败。\n"
                f"  手动装: {exe} -m pip install --user --break-system-packages openai-whisper\n"
                f"  (失败原因: {e})  本次跳过语音转写。")
            sys.exit(4)
    if importlib.util.find_spec("whisper") is None:
        log("[transcribe] openai-whisper 装了仍 import 不到(多解释器错配),本次跳过。")
        sys.exit(4)

    # 3) 抽音轨到临时 wav(16k 单声道,whisper 的标准输入)。无音轨则提示并跳过。
    tmp_wav = tempfile.mktemp(suffix=".wav", prefix="vr_audio_")
    rc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", video, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", tmp_wav],
        capture_output=True, text=True)
    if rc.returncode != 0 or not os.path.exists(tmp_wav) or os.path.getsize(tmp_wav) == 0:
        log("[transcribe] 抽音轨失败或视频无音轨,跳过语音转写(画面分析不受影响)。")
        if os.path.exists(tmp_wav):
            os.remove(tmp_wav)
        sys.exit(4)

    try:
        import whisper
        log(f"[transcribe] 加载 whisper 模型: {args.model} (首次会下载模型,稍候)…")
        model = whisper.load_model(args.model)
        log("[transcribe] 转写中…")
        res = model.transcribe(tmp_wav, language=(args.language or None), verbose=False)
    except Exception as e:
        log(f"[transcribe] whisper 转写失败,跳过: {e}")
        sys.exit(4)
    finally:
        if os.path.exists(tmp_wav):
            os.remove(tmp_wav)

    segments = [
        {"start": round(float(s.get("start", 0)), 2),
         "end": round(float(s.get("end", 0)), 2),
         "text": s.get("text", "").strip()}
        for s in res.get("segments", [])
    ]
    result = {
        "mode": "transcribe",
        "video": os.path.abspath(video),
        "model": args.model,
        "language": res.get("language", args.language or ""),
        "text": res.get("text", "").strip(),
        "segments": segments,
    }

    log("\n=== 语音转写(带时间戳) ===")
    for s in segments:
        log(f"  {s['start']:7.2f}s - {s['end']:7.2f}s  {s['text']}")
    log(f"\n共 {len(segments)} 段。把它和画面时间线(scan)对齐,能更准定位'第几秒说了/做了什么'。\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_zoom(args):
    cap, fps, total, duration, w, h = open_video(args.video)
    if args.start is None or args.end is None:
        log("ERROR: zoom 必须指定 --start 和 --end")
        sys.exit(2)
    t_start = max(0.0, args.start)
    t_end = min(args.end, duration if duration > 0 else args.end)

    log(f"视频: {args.video}  (fps {fps:.2f}, 时长 {duration:.2f}s)")
    log(f"  zoom 区间 {t_start:.2f}s - {t_end:.2f}s @ {args.density} fps")

    outdir, _ = resolve_outdir(args, "zoom")
    os.makedirs(outdir, exist_ok=True)
    register_frame_dir_hint(outdir)

    # 密集均匀抽帧(zoom 是看细节,不折叠)
    dur = max(0.0, t_end - t_start)
    n = max(2, int(round(dur * args.density)) + 1)
    times = sorted(set(round(t_start + dur * i / (n - 1), 3) for i in range(n)))
    times = truncate_times(times, args.max_frames, "zoom")

    frames = []
    for t in times:
        fn = save_frame(cap, fps, t, outdir, args.quality, args.max_width)
        if fn:
            frames.append({"t": t, "path": fn})
    cap.release()

    result = {
        "mode": "zoom",
        "video": os.path.abspath(args.video),
        "fps": round(fps, 3),
        "zoom_range": [round(t_start, 3), round(t_end, 3)],
        "density_fps": args.density,
        "frames": frames,
        "outdir": outdir,
        "debug": bool(getattr(args, "debug", False)),
    }
    log(f"抽了 {len(frames)} 帧 -> {outdir}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_grid(args):
    """把全片(或区间)均匀取 rows×cols 帧拼成一张"九宫格"大图,每格左上角标时间戳。
    用途:一次 Read 一张图就能看全片节奏/概貌,省 token、好定位;
    看完再用 zoom 对可疑那一格的时间段下钻。它是 scan 之外的另一种概览入口,
    不替代帧差初筛——scan 擅长'哪几秒在动',grid 擅长'整段长啥样'。
    时间戳烧在格子角上是概览的必要折中(否则不知每格第几秒);精确定位仍靠 scan/zoom。"""
    cap, fps, total, duration, w, h = open_video(args.video)
    t_start = args.start if args.start is not None else 0.0
    t_end = args.end if args.end is not None else duration
    if t_end <= 0:
        t_end = duration if duration > 0 else 1e9
    rows, cols = max(1, args.rows), max(1, args.cols)
    n = rows * cols
    span = max(0.0, t_end - t_start)
    if n > 1 and span > 0:
        times = [round(t_start + span * i / (n - 1), 3) for i in range(n)]
    else:
        times = [round(t_start, 3)] * n
    # grid 的单元格数由 rows×cols 显式指定, 不受 --max-frames 约束(它是 scan/zoom 抽帧上限)

    log(f"视频: {args.video}  (fps {fps:.2f}, 时长 {duration:.2f}s)")
    log(f"  九宫格 {rows}x{cols}={n} 格, 区间 {t_start:.2f}s-{t_end:.2f}s, 每格宽 {args.cell_width}px")

    cell_w = max(80, args.cell_width)
    imgs, cells = [], []
    for i, t in enumerate(times):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
        ok, frame = cap.read()
        if not ok or frame is None:
            frame = np.zeros((max(1, int(cell_w * h / max(1, w))), cell_w, 3), np.uint8)
        fh, fw = frame.shape[:2]
        cell = cv2.resize(frame, (cell_w, max(1, int(fh * cell_w / fw))),
                          interpolation=cv2.INTER_AREA)
        label = f"{t:.1f}s"  # 白字黑边,深浅背景都看得清
        cv2.putText(cell, label, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(cell, label, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        imgs.append(cell)
        cells.append({"idx": i, "t": t, "row": i // cols, "col": i % cols})
    cap.release()

    # 各格统一到相同高度(取最小高,裁掉多余),保证 hstack/vstack 不报错。
    cell_h = min(im.shape[0] for im in imgs)
    imgs = [im[:cell_h] for im in imgs]
    grid_img = np.vstack([np.hstack(imgs[r * cols:(r + 1) * cols]) for r in range(rows)])

    outdir, _ = resolve_outdir(args, "grid")
    os.makedirs(outdir, exist_ok=True)
    register_frame_dir_hint(outdir)
    grid_path = os.path.join(outdir, "grid.jpg")
    cv2.imwrite(grid_path, grid_img, [cv2.IMWRITE_JPEG_QUALITY, args.quality])

    result = {
        "mode": "grid",
        "video": os.path.abspath(args.video),
        "fps": round(fps, 3),
        "duration": round(duration, 3),
        "range": [round(t_start, 3), round(t_end, 3)],
        "rows": rows, "cols": cols,
        "grid_path": grid_path,
        "cells": cells,
        "outdir": outdir,
    }
    log(f"\n九宫格已生成 -> {grid_path}")
    log("阅读顺序: 从左到右、从上到下,每格左上角是该帧的秒数。")
    log("先看这张图把握全片节奏,再用 zoom 对可疑那一格的时间段下钻。\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description="把视频变成关键帧+运动时间线,喂给大模型")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("video", help="视频文件路径")
    common.add_argument("--start", type=float, default=None, help="起始秒")
    common.add_argument("--end", type=float, default=None, help="结束秒")
    common.add_argument("--outdir", default=None, help="帧输出目录(默认临时目录)")
    common.add_argument("--quality", type=int, default=70, help="JPEG质量1-100,默认70")
    common.add_argument("--max-width", type=int, default=900,
                        help="帧最大宽度(超过则缩放,省token),默认900,0=不缩")
    common.add_argument("--debug", action="store_true",
                        help="调试模式:帧存到当前目录 video_reader_debug/ 下(可复查),"
                             "并额外输出运动数据JSON与帧差曲线图。默认关闭。")
    common.add_argument("--max-frames", type=int, default=300,
                        help="scan/zoom 抽帧上限(帧), 超限截断并 warn; "
                             "防 zoom 宽区间×高 density 静默产出数千帧, 默认 300")
    cleanup_g = common.add_mutually_exclusive_group()
    cleanup_g.add_argument("--keep-frames", action="store_true",
                           help="保留临时帧目录(默认行为), 退出时在 stderr 打印删除提示")
    cleanup_g.add_argument("--cleanup", action="store_true",
                           help="成功退出时自动删除本次自动创建的临时帧目录; "
                                "--outdir/--debug 指定的目录不删")

    ps = sub.add_parser("scan", parents=[common], help="粗扫:运动时间线+稀疏抽帧")
    ps.add_argument("--analyze-fps", type=float, default=10.0,
                    help="运动分析采样率(只用于算时间线,不输出帧),默认10")
    ps.add_argument("--grid", type=int, default=16, help="帧差分块网格数,默认16")
    ps.add_argument("--threshold", type=float, default=None,
                    help="运动阈值,默认自动估算")
    ps.add_argument("--density", type=float, default=2.0,
                    help="活动段每秒抽几帧(粗扫),默认2")
    ps.set_defaults(func=cmd_scan)

    pz = sub.add_parser("zoom", parents=[common], help="下钻:指定区间高密度抽帧")
    pz.add_argument("--density", type=float, default=8.0,
                    help="每秒抽几帧(细看),默认8")
    pz.set_defaults(func=cmd_zoom)

    pg = sub.add_parser("grid", parents=[common],
                        help="九宫格概览:全片均匀取帧拼成一张大图,一次看全片节奏")
    pg.add_argument("--rows", type=int, default=3, help="行数,默认3")
    pg.add_argument("--cols", type=int, default=3, help="列数,默认3(3x3=9格)")
    pg.add_argument("--cell-width", type=int, default=320, help="每格宽度px,默认320")
    pg.set_defaults(func=cmd_grid)

    # transcribe 不复用 common(它不抽帧,只要 video+模型参数),独立一套参数。
    pt = sub.add_parser("transcribe",
                        help="(可选)语音转写:把视频/音频里的话转成带时间戳文字,需 ffmpeg+whisper")
    pt.add_argument("video", help="视频/音频文件路径")
    pt.add_argument("--model", default="turbo",
                    help="whisper 模型: tiny/base/small/medium/large/turbo,默认 turbo(快且准)")
    pt.add_argument("--language", default=None,
                    help="语言代码(如 zh/en),默认自动检测")
    pt.set_defaults(func=cmd_transcribe)

    args = p.parse_args()
    args.func(args)
    # 走到这里说明命令成功结束(失败路径都已 sys.exit)。
    # --cleanup 只删本次自动创建的临时目录; 用户显式 --outdir/--debug 目录绝不动。
    if getattr(args, "cleanup", False):
        for d in TEMP_DIRS:
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
                log(f"[video-reader] 已按 --cleanup 删除临时帧目录: {d}")


if __name__ == "__main__":
    main()
