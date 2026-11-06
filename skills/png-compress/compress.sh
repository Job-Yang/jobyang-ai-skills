#!/usr/bin/env bash
# =============================================================
# 一键 PNG 压缩 (对齐 TinyPNG) —— 无脑版
# 用法:
#   ./compress.sh                              压当前目录
#   ./compress.sh /path/to/AppProject          正式压缩
#   ./compress.sh /path/to/AppProject --dry-run 只看效果不改文件
# 依赖(缺则自动尝试用 brew 安装): pngquant  oxipng
# =============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$SCRIPT_DIR/compress_images.py"

if [ $# -eq 0 ]; then
  set -- "."
fi

# ---- 依赖自检 & 自动安装 ----
need_install=()
for bin in pngquant oxipng; do
  command -v "$bin" >/dev/null 2>&1 || need_install+=("$bin")
done

if [ ${#need_install[@]} -gt 0 ]; then
  echo "缺少依赖: ${need_install[*]}"
  if command -v brew >/dev/null 2>&1; then
    echo "→ 用 brew 自动安装中..."
    brew install "${need_install[@]}"
  else
    echo "未检测到 brew。请手动安装后重试:"
    echo "  macOS:  brew install ${need_install[*]}"
    echo "  Ubuntu: sudo apt-get install pngquant && cargo install oxipng"
    exit 1
  fi
fi

# ---- 跑 ----
python3 "$PY" "$@"
