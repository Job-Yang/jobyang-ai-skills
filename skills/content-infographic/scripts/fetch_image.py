#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_image.py — 下载文生图服务返回的签名图片 URL（平台无关）。

为什么需要它：图片 URL 的 query 里常含 %2F / %2B / %3D 等转义字符，在 shell 里
手拼 curl 极易被二次转义，下回来的是 4KB 的 HTML/XML 错误页而不是图。
本脚本用 urllib 原样请求，并用文件魔数校验确实是图片，失败明确报错。

用法：
    python3 fetch_image.py "<完整图片URL>" <输出路径.png>
退出码：0 成功；1 下载失败或拿到的不是图片；2 参数错。
"""
import sys
import urllib.request


def is_image(head: bytes):
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def main() -> int:
    if len(sys.argv) != 3:
        print("用法: python3 fetch_image.py '<URL>' <输出路径>", file=sys.stderr)
        return 2
    url, out = sys.argv[1], sys.argv[2]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
    except Exception as e:  # noqa: BLE001
        print(f"下载失败: {e}", file=sys.stderr)
        return 1

    kind = is_image(data[:16])
    if kind is None:
        preview = data[:200].decode("utf-8", "replace")
        print(
            "下载到的不是图片（可能签名转义错误或链接已过期）。前 200 字节：\n" + preview,
            file=sys.stderr,
        )
        return 1

    with open(out, "wb") as f:
        f.write(data)
    print(f"OK: 已保存 {kind} 图片 -> {out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
