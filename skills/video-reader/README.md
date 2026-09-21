# Video Reader

> An **agent Skill** that gives LLMs (which can only see images) a pair of "video-watching glasses".

**English** · [简体中文](./README.zh-CN.md)

> [!IMPORTANT]
> **This is an agent Skill, not a standalone CLI tool.** It's meant to be installed as a Skill (via [`SKILL.md`](./SKILL.md)) and driven by an AI agent. The `scripts/video_frames.py` inside is called *by the Skill* — it's the Skill's internal engine, not something an end user runs by hand. To use it, drop this repo into your agent's skills directory and just say "look at this video" in natural language.

LLMs can read images but can't watch videos. Video Reader uses pure code (frame-differencing) to turn a video into **timestamped keyframes + a motion timeline**, so the agent can tell you **"what happened at second X"** — especially useful for debugging App scrolling / interaction issues.

It automatically skips the still parts and only picks the frames where the picture is actually changing, so it's fast, cheap on tokens, and you don't have to screenshot frame by frame.

## Install as a Skill

This repo *is* a Skill. Choose one of these three installation methods.

### Method 1: Clone this Skill index (recommended)

```bash
git clone https://github.com/Job-Yang/jobyang-ai-skills.git
cp -R jobyang-ai-skills/skills/video-reader ~/.claude/skills/video-reader
```

For other agents, replace the destination with that agent's skills directory.

### Method 2: Legacy repository

`video-reader` has moved into the `Job-Yang/jobyang-ai-skills` Skill index. The old repository is kept only as a migration notice.

### Method 3: Install manually

1. Download this repository as a ZIP file from GitHub and extract it.
2. Copy the `skills/video-reader` folder into your agent's skills directory.
3. Restart the agent or reload its skills.

Default Claude Code locations:

- macOS / Linux: `~/.claude/skills/`
- Windows: `%USERPROFILE%\.claude\skills\`

Keep the complete repository structure. Do not copy only `SKILL.md`: the Skill calls `scripts/video_frames.py` at runtime.

The agent reads [`SKILL.md`](./SKILL.md) to know when to trigger and how to call the engine. You then just talk to the agent in natural language ("look at this video, what's wrong at what second?") — the sections below explain the mechanics the Skill uses under the hood.

## Table of Contents

- [Why](#why)
- [Features](#features)
- [Install as a Skill](#install-as-a-skill)
- [Quick Start](#quick-start)
- [The Four Subcommands](#the-four-subcommands)
- [Core Workflow: Coarse → Fine](#core-workflow-coarse--fine)
- [When Upload Is Blocked](#when-upload-is-blocked)
- [How It Works](#how-it-works)
- [Command Reference](#command-reference)
- [Design Decisions](#design-decisions)
- [Limitations](#limitations)
- [License](#license)

## Why

You've got a video — a scrolling-bug screen recording from a teammate, a user complaint, a hand-held clip of some operation — and you want an LLM to tell you what's going on inside it. But LLMs can only see images, not videos.

That's exactly what this tool does: **you hand it a video, it tells you "what happened at second X"**, and it's especially good at App scrolling / interaction problems (how a panel moves, how state changes, whether a navigation is correct).

| Good for | Not for |
|---|---|
| Scrolling, gestures, state transitions, page navigation — **interaction logic** issues | Frame-rate / jank — **performance** issues (screenshots can't show jank; use logs / Perfetto) |
| "What happened at second X, and is it right?" | Pixel-precise touch-point localization (especially in re-shot videos) |

## Features

- 🎯 **Zero-token frame selection** — frame-differencing runs on CPU, the model only looks at the picked result.
- ✂️ **Auto-skips still segments** — no information in a frozen frame; it gets folded away entirely.
- 🔍 **Coarse-to-fine drill-down** — `scan` the whole clip, then `zoom` into the suspicious range (multi-round).
- 🗺️ **Nine-grid overview** — one big image to grasp the rhythm of the whole video at a glance.
- 🎙️ **Optional transcription** — pull in narration / spoken complaints / error audio the picture can't show.
- 📦 **No system ffmpeg required** — OpenCV decodes video on its own; dependencies self-heal on first run.

## Quick Start

### Dependencies

- Python3 + `opencv-python-headless` + `numpy` (OpenCV decodes video itself, **no system ffmpeg needed**)
- `matplotlib` (only for the `--debug` motion-curve plot)

**Self-healing deps**: on startup the script auto-detects missing dependencies and tries to install them (`pip install --user --break-system-packages`, no system pollution). You normally don't need to prepare anything. Only if auto-install fails will it print a manual command:

```bash
pip install --user --break-system-packages opencv-python-headless numpy matplotlib
```

### Under the hood: how the Skill calls the engine

You normally won't run this yourself — the agent does. But for reference, this is the call the Skill makes to coarse-scan a clip:

```bash
# Coarse-scan the whole clip: get a motion timeline + keyframes
python3 scripts/video_frames.py scan your_video.mp4
```

`stdout` is structured JSON (`timeline`, `active_segments`, `frames[]` with each frame's path and second); `stderr` is a human-readable motion-timeline summary. Read the timeline first, then decide whether to drill down.

## The Four Subcommands

Think about which one you need before starting — don't always default to `scan`:

| Subcommand | When to use | In one line |
| --- | --- | --- |
| `scan` | Default starting point; locate "which seconds are moving / buggy" | Frame-diff pre-filter + motion timeline + sparse sampling |
| `zoom` | You know the suspicious range and want detail | High-density sampling over a given range |
| `grid` | You want a **whole-clip overview** first, or the video is long | Even sampling stitched into a nine-grid image |
| `transcribe` | The picture isn't enough — you **need to hear** (narration / speech / error audio) | Speech-to-text with timestamps (optional, needs ffmpeg + whisper) |

Common combo: **long/uncertain video → `grid` for the rhythm → `scan` for the motion timeline → `zoom` into the suspicious part**; anything about "what was said" → add `transcribe` and align it with the visual timeline.

## Core Workflow: Coarse → Fine

Don't densely sample the whole video up front — that's slow and blows up the context. The standard play is two steps:

```
Step 1  scan (coarse)
  └─ Script outputs: motion timeline (text) + a few sparse frames from active segments
  └─ You read the timeline + frames, judge "the problem is roughly at X–Y seconds"
        ↓
Step 2  zoom (drill-down)
  └─ Script densely samples X–Y seconds
  └─ You inspect the detail; if not enough, keep zooming into a smaller range (multi-round)
```

Key mindset: **read the timeline first, then decide whether to look at frames and which segment.** Often `scan`'s text timeline alone is enough to know where to drill — that's the most token-efficient way.

## When Upload Is Blocked

Many platforms (e.g. Mira) **outright reject video / audio formats** on upload — a `.mp4` / `.mov` gets "unsupported file type" and can't get in. **This isn't a dead end; two workarounds:**

1. **Rename the extension**: rename `xxx.mp4` to an allowed extension (e.g. `.txt` / `.bin`) and upload. Don't be fooled by the extension afterward — it's still a video; rename it back to `.mp4` (or use the original path) before feeding it to the script. OpenCV decodes by file content, not extension, so even a `.txt` reads fine as long as the content is video.
2. **Zip it**: compress the video into a `.zip` (zip usually isn't blocked), then unzip to get the video before feeding the script.

> In short: the platform blocks the "extension / format", not the "content". Rename it or wrap it in a zip shell to get through, then `scan` / `zoom` as usual once you have the real file.

## How It Works

### The core insight

A video is just a string of images ordered by time. So-called "native video" LLMs (Gemini, GPT-4o, etc.) also do frame extraction under the hood — splitting the video into frames at some rate and feeding them as images. Given that, we can move the "frame extraction" step outside and do it ourselves, controlling which and how many frames — often cheaper and more precise than the generic approach.

### Two key problems it solves

| Problem | Naive approach | This tool's solution |
|---|---|---|
| **Context explosion**: a 20s video evenly sampled into 20 images, all stuffed in, is expensive and overwhelming | Stuff it in and rely on a big window | Only sample where there's motion; still segments are folded away, zero frames |
| **Who picks the keyframes**: making the model look at every frame first to know which matters saves nothing | Model reviews frame by frame | **Pure code picks frames via frame-diff, zero tokens**; model only sees the result |

"Frame-diff" means computing how much two adjacent frames differ — pure math on CPU, no LLM involved. No change means no operation, skip it; a changing picture means scrolling / interaction, sample densely.

> In one line: **generic LLMs rely on "fitting it in", we rely on "picking well" — and picking well is free.**

### Overall flow

```
                    a video file
                        │
        ┌───────────────┴───────────────┐
        │   pure code (no tokens)         │
        │  1. frame-diff → motion timeline│
        │  2. fold still, sample active   │
        └───────────────┬───────────────┘
                        │
              keyframes + motion timeline
                        │
        ┌───────────────┴───────────────┐
        │      LLM (see + judge)          │
        │  read frames, locate, compare   │
        └────────────────────────────────┘
```

## Command Reference

### scan — coarse-scan the whole clip

```bash
python3 scripts/video_frames.py scan <video>
```

| Option | Effect | Default |
|---|---|---|
| `--start / --end` | Scan only a segment (when you know the rough range) | whole clip |
| `--density` | Frames per second in active segments | 2 |
| `--max-width` | Max frame width (saves tokens), 0 = no resize | 900 |
| `--threshold` | Motion threshold | auto-estimated |

> Performance: scan seeks once at the segment start, then sequentially skips frames (decoding only sampled frames), so long videos won't stall from per-frame random seeking; a progress line prints to stderr about every 5 seconds.

### zoom — high-density sampling over a suspicious range

```bash
python3 scripts/video_frames.py zoom <video> --start 10.0 --end 12.0 --density 8
```

To catch a specific instant (e.g. the moment a finger lifts), push `--density` to 12–15 and narrow the range to under 0.5s.

### grid — nine-grid overview

Evenly samples the whole clip (or a range) into one big image, each cell labeled with its second in the top-left. One Read of one image captures the whole video's rhythm — token-cheap, easy to locate; then `zoom` into the suspicious cell.

```bash
python3 scripts/video_frames.py grid <video>
python3 scripts/video_frames.py grid <video> --rows 4 --cols 4 --start 0 --end 30
```

- `--rows / --cols`: grid rows/cols, default 3×3; `--cell-width` per-cell width, default 320.
- Output JSON's `grid_path` is the stitched image, `cells[]` gives each cell's second / row-col.
- Complements scan: scan's motion timeline is good at "which seconds move", grid is good at "what the whole thing looks like".

### transcribe — speech-to-text (optional)

For info the picture can't show but you can hear (narration, spoken complaints, error audio). **An optional soft capability — if deps are missing it just warns and skips, without affecting scan / zoom.**

```bash
python3 scripts/video_frames.py transcribe <video> --model turbo
```

- Deps: system `ffmpeg` (extract audio track) + `openai-whisper` (pip package, torch is heavy, installed on-demand). Either missing prints an install method and exits with code 4 to skip.
- Output: `stdout` is JSON (`text` full text + `segments` timestamped), `stderr` is per-segment timestamped text.
- Usage: align the transcription timestamps with `scan`'s visual motion timeline to say more precisely "at second X the picture is doing this while saying that". Audio-less recordings are skipped automatically.

### --debug — debug mode (off by default)

Usually not needed. Turn it on to debug the tool itself, or to figure out "why this segment was judged still / moving":

```bash
python3 scripts/video_frames.py scan <video> --debug
```

- Frames go to **`video_reader_debug/<name>_<mode>/` in the current directory**, stable and inspectable (default is a random temp dir, read-and-discard).
- Extra outputs: `_debug/motion_data.json` (each sample point's time + motion score, threshold, segments) and `_debug/motion_curve.png` (frame-diff curve with threshold line and active-segment shading) — one look tells you whether the threshold is right, then tune `--threshold`.

### Common gotcha: "installed but can't be used"

On startup the script prints which interpreter it's using to stderr:

```
[video-reader] Interpreter self-check (look here for 'installed but unusable'):
  - python   : /usr/bin/python3
  - version  : 3.13.5
  - user-site: <user-site>/python3.13/site-packages
```

> **Symptom**: `pip` installed `opencv`, but the script reports a missing dep / can't import.
> **Root cause**: a machine often has several `python3` (system `/usr/bin`, Homebrew, pyenv), and `pip --user` stores packages in per-version dirs. You installed with interpreter A but the script ran with interpreter B — B's package dir doesn't have it.
> **Fix** (pick one):
> - Easiest: run the script with the **absolute path** of the interpreter that has the packages;
> - Cleanest: create a venv to lock "one interpreter + one set of packages" — `python3.x -m venv .venv`, then always run with `.venv/bin/python`.

## Design Decisions

- **Why still segments are dropped**: screenshots don't "jank"; still segments carry no info for interaction debugging and only waste the model's attention and context.
- **Why timestamps are text, not burned into the picture**: models read text 100% accurately; making them read text burned into a frame risks blur, occlusion, or misreads. So timestamps live in the filename and returned data, matched up when reading frames.
- **Why frames are compressed**: models internally resize images to a fixed size anyway — ultra-HD pixels never make it in. So frames default to width 900, JPEG quality 70 — clear enough for UI, cheap on tokens and bandwidth.
- **How re-shot videos (hand, glare, shake) are handled**: frame-diff uses "shrink + blur + block" to absorb noise and slight shake, so re-shot videos still roughly locate motion. But finger-position detail is limited under re-shooting — only directional judgments.
- **Why no reliance on the "screen-recording white dot"**: many videos are real user complaints or hand-held clips with no dot and no way to enforce it. So the tool is designed to work with or without it.
- **Why no business logic in the tool**: it doesn't know what "jank", "panel", or "follow-the-finger" mean — it only produces frames. Judgment is left to the upstream model, making it a general foundation for any "let the model watch a video" scenario.

## Limitations

- **Judging right/wrong needs context**: without knowing the user's intent, the tool only describes objectively and won't guess. Feed it the complaint / expected behavior for a more precise diagnosis.
- **Not for frame-rate / jank**: the jank signal lives in "how long between frames"; sampling flattens that away. For performance jank use logs / systrace / Perfetto. This tool is for **interaction logic** problems.
- **Limited finger precision in re-shot videos**: it can see direction, but can't pin the touch point precisely.

## License

Released under the [MIT License](./LICENSE).
