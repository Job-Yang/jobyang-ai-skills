# PNG Compress

> Turn TinyPNG-style PNG compression into a local, batchable, repeatable Agent Skill.

[简体中文](./README.md) · **English**

This started with a simple need: compress every PNG in an App project. TinyPNG works well for individual files, but uploading an entire project is slow, repeated automation requires a paid or quota-limited API, and the images must leave the machine.

We broke the published technique into two stages: reduce the color palette first, then optimize the remaining PNG encoding without changing pixels.

```text
lossy quantization with pngquant
              ↓
lossless optimization with oxipng
              ↓
decode / dimensions / alpha / quality gates
              ↓
replace on success, keep the original on failure
```

This is not a reverse-engineered TinyPNG implementation and does not claim to reproduce its private algorithm. It uses the same public class of techniques, then adds project scanning, incremental caching, safety gates, and automatic fallback. Public comparisons show that a properly tuned `pngquant` pipeline can match or exceed TinyPNG's compression ratio on tested image sets. Results still vary by image, so validate against your own assets.

## What It Solves

- Processes a whole App project recursively instead of uploading files one by one.
- Runs locally after dependencies are installed; project images are not uploaded.
- Uses content hashes to avoid repeated lossy compression.
- Applies a more conservative quality range to small icons.
- Keeps the original if output grows, fails to decode, changes dimensions, loses alpha, or fails a quality gate.
- Skips APNG files so animation is not flattened into one frame.
- Uses multiple processes for large repositories.

## Project Independence

The Skill does not inspect `.xcodeproj`, schemes, bundle IDs, targets, or application source code. It has no dependency on any product-specific project or private build system. It only receives a directory and recursively finds PNG files.

It therefore works with:

- `Assets.xcassets` and regular resource folders in any iOS App;
- static PNG assets in other App projects;
- standalone image directories.

By default it skips `.git`, `Pods`, `Carthage`, `build`, `DerivedData`, `node_modules`, `.build`, and `fastlane`.

## Install as a Skill

Clone the Skill repository and copy the complete directory into your agent's Skills directory:

```bash
git clone https://github.com/Job-Yang/jobbyang-ai-skills.git
cp -R jobbyang-ai-skills/skills/png-compress-skill ~/.claude/skills/png-compress-skill
```

Then tell the agent:

```text
Compress the PNG assets in this iOS project: /path/to/MyApp
```

The agent confirms the target directory before invoking the bundled script.

## Run Directly

From this Skill directory:

```bash
# Compress the current directory
./compress.sh

# Compress a specific project
./compress.sh /path/to/MyApp

# Estimate only; do not change files or write the cache
./compress.sh /path/to/MyApp --dry-run

# Control parallelism
./compress.sh /path/to/MyApp -j 8
```

Successful candidates replace their source files in place. The cache is written to `.png_compress_cache.json` at the target root.

> Start from a clean or committed Git worktree. Commit the cache if your team and CI should share it; otherwise add it to `.gitignore`.

## Why Two Tools

| Tool | Responsibility | Lossy |
| --- | --- | --- |
| `pngquant` | Reduces colors and converts true-color PNGs to smaller 8-bit palette PNGs | Yes |
| `oxipng` | Re-selects PNG filters, recompresses DEFLATE data, and removes metadata | No |

`pngquant` produces most of the reduction. `oxipng` tightens the encoded result afterward.

Default settings:

```text
normal image: quality 65-85
small image:  quality 70-90
pngquant speed: 1
dithering: 1.0
oxipng: -o max
```

## Safety Boundaries

This is lossy compression, so successful decoding alone does not prove visual quality. The Skill applies several safeguards:

1. The result must decode as PNG.
2. Dimensions must remain unchanged.
3. Alpha must not disappear.
4. APNG files are skipped.
5. PSNR, SSIM, MAE, and alpha MAE must stay within configured limits.
6. The result must be smaller than the original.

Automated gates catch obvious failures, not every subjective artifact. Before shipping, visually sample:

- App icons and launch images;
- large gradients;
- translucent shadows and glass-like assets;
- files with the largest absolute or percentage reduction.

## Dependencies

- `pngquant`
- `oxipng`
- Python 3
- `Pillow` for the default quality gate
- `numpy` optionally enables SSIM

On macOS:

```bash
brew install pngquant oxipng
python3 -m pip install Pillow numpy
```

## About TinyPNG

TinyPNG publicly describes its PNG optimization as combining similar colors, converting 24-bit images into smaller 8-bit indexed PNGs, and removing unnecessary metadata. The author of `pngquant` also names TinyPNG and similar services as applications of this quantization approach.

A published comparison by the QQ Music engineering team found TinyPNG smaller with default `pngquant` settings, while tuned `pngquant` settings could surpass it on their test set. They chose the local pipeline for batch processing and build automation.

The reusable part is therefore not a particular website. It is the compression technique plus the caching, fallback, and verification required to make it dependable inside an engineering workflow.

References:

- [TinyPNG: How does PNG compression work?](https://tinypng.com/)
- [pngquant](https://pngquant.org/)
- [Using pngquant in PHP](https://pngquant.org/php.html)
- [Oxipng](https://github.com/shssoichiro/oxipng)
- [QQ Music engineering: PNG compression comparison](https://cloud.tencent.com/developer/article/1034208)

## License

Repository code is licensed under MIT. `pngquant` / `libimagequant` and `oxipng` are independent third-party projects with their own licenses. This Skill invokes them during development or builds to produce ordinary PNG files; it does not embed their code into the App.
