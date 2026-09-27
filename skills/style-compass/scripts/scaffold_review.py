#!/usr/bin/env python3
"""生成设计罗盘固定工作台；项目只需替换画板内容和设计清单。"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from validate_review_workspace import WORKSPACE_LAYOUT, validate_workspace


ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "review-framework"
CONTRACT_TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "stage-contract.example.json"
)
FRAMEWORK_FILES = ("review-framework.css", "review-framework.js")


def validate_template() -> None:
    try:
        validate_workspace(ASSET_DIR / "template.html")
    except (OSError, ValueError) as error:
        raise SystemExit(f"[review-scaffold] 工作台模板校验失败：{error}") from error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prototype_dir", help="原型目录")
    parser.add_argument("--force", action="store_true", help="覆盖已有公共文件")
    args = parser.parse_args()
    validate_template()

    destination = Path(args.prototype_dir).expanduser().resolve() / "review-framework"
    destination.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    for name in FRAMEWORK_FILES:
        source = ASSET_DIR / name
        target = destination / name
        if target.exists() and not args.force:
            print(f"[review-scaffold] 已存在，跳过：{target}")
            skipped += 1
            continue
        shutil.copy2(source, target)
        print(f"[review-scaffold] 已复制：{target}")
        copied += 1

    index_target = destination.parent / "index.html"
    if index_target.exists() and not args.force:
        print(f"[review-scaffold] 已存在，保留项目入口：{index_target}")
        skipped += 1
    else:
        shutil.copy2(ASSET_DIR / "template.html", index_target)
        print(f"[review-scaffold] 已生成起始入口：{index_target}")
        copied += 1

    contract_target = destination.parent / "index.design.json"
    if contract_target.exists() and not args.force:
        print(f"[review-scaffold] 已存在，保留阶段契约：{contract_target}")
        skipped += 1
    else:
        shutil.copy2(CONTRACT_TEMPLATE, contract_target)
        print(f"[review-scaffold] 已生成阶段契约：{contract_target}")
        copied += 1

    try:
        validate_workspace(index_target)
    except (OSError, ValueError) as error:
        raise SystemExit(f"[review-scaffold] 生成结果校验失败：{error}") from error

    print(f"[review-scaffold] 完成：复制 {copied}，跳过 {skipped}")
    print(f"[review-scaffold] 空间画室工作台已生成：{WORKSPACE_LAYOUT}")
    print("[review-scaffold] 下一步：只替换画板和设计清单，并维护 index.design.json。")


if __name__ == "__main__":
    main()
