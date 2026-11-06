#!/usr/bin/env python3
"""me-context 数据仓初始化。

建一个本地私有数据仓（空白模板，不预建真人实体）。
技能目录本身开源、不含数据；数据仓在别处、随文件夹搬移。

用法：
    python3 init.py                 # 默认 ~/me-context-data
    python3 init.py --path /tmp/x   # 指定路径（优先级最高）
环境变量 ME_CONTEXT_DATA 次之。已存在且非空时需 --force 才重建。
"""
import argparse
import os
import shutil
import sys

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")

ROOT_FILES = ["ME.md", "network.md", "relations.md", "CHANGELOG.md"]
PROFILE_FILES = ["work.md", "goals.md", "preferences.md", "decisions.md", "body.md", "health.md", "finance.md"]
# 过程层：细节和经过（体检指标明细、重要决定），默认不加载、不导出
JOURNAL_FILES = ["health-metrics.md", "decisions.md"]
SUBDIRS = ["profile", "entities", "inbox", "journal", "private"]


def resolve_path(cli_path):
    if cli_path:
        return os.path.abspath(os.path.expanduser(cli_path))
    env = os.environ.get("ME_CONTEXT_DATA")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.abspath(os.path.expanduser("~/me-context-data"))


def main():
    ap = argparse.ArgumentParser(description="初始化 me-context 本地私有数据仓（空白模板）。")
    ap.add_argument("--path", help="数据仓路径（最高优先级；其次环境变量 ME_CONTEXT_DATA；默认 ~/me-context-data）")
    ap.add_argument("--force", action="store_true", help="目标已存在且非空时仍重建（覆盖同名模板文件）")
    args = ap.parse_args()

    data_dir = resolve_path(args.path)

    # 已存在且非空 → 拒绝（除非 --force）
    if os.path.isdir(data_dir) and os.listdir(data_dir):
        if not args.force:
            print(f"[拒绝] 目录已存在且非空：{data_dir}", file=sys.stderr)
            print("       若确要重建，加 --force（会覆盖同名模板文件）。", file=sys.stderr)
            return 1
        print(f"[--force] 目录已存在，覆盖同名模板文件：{data_dir}")

    # 建目录
    os.makedirs(data_dir, exist_ok=True)
    for sd in SUBDIRS:
        os.makedirs(os.path.join(data_dir, sd), exist_ok=True)

    # 铺根文件与 profile 模板
    for name in ROOT_FILES:
        shutil.copy2(os.path.join(TEMPLATE_DIR, name), os.path.join(data_dir, name))
    for name in PROFILE_FILES:
        shutil.copy2(os.path.join(TEMPLATE_DIR, "profile", name),
                     os.path.join(data_dir, "profile", name))
    for name in JOURNAL_FILES:
        shutil.copy2(os.path.join(TEMPLATE_DIR, "journal", name),
                     os.path.join(data_dir, "journal", name))

    # 铺 inbox 说明与草稿模板（草稿本身不校验、不投喂）
    shutil.copy2(os.path.join(TEMPLATE_DIR, "inbox", "_README.md"),
                 os.path.join(data_dir, "inbox", "_README.md"))
    # 写 .gitignore（从 templates/data-repo/gitignore.txt）
    gi_src = os.path.join(TEMPLATE_DIR, "data-repo", "gitignore.txt")
    with open(gi_src, "r", encoding="utf-8") as f:
        gi = f.read()
    with open(os.path.join(data_dir, ".gitignore"), "w", encoding="utf-8") as f:
        f.write(gi)

    print(f"[完成] me-context 数据仓已建：{data_dir}")
    print("  - ME.md / network.md（关系网圈层概览）/ relations.md / CHANGELOG.md")
    print("  - profile/{work,goals,preferences,decisions,body,health,finance}.md")
    print("  - entities/（空，不预建真人；关系人按 inner/close/peripheral 三圈写，见 references/03）")
    print("  - inbox/（候选暂存，非正式档案；gate/export 默认不读）")
    print("  - journal/（过程层：体检指标明细、重要决定；默认不加载、不导出）")
    print("  - private/（L4，已 gitignore）")
    print("  - .gitignore（你自己用 git 管理时生效；技能不调 git，见 references/06 §6）")
    print("下一步：按 templates/questions/bootstrap.md 三档题库开始采集（写模式人工确认才落盘）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
