#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_integrity.py — 好好说话 · 宪法（底线条款）完整性校验（纯标准库）。

单一事实源写死在哪：
  SKILL.md 里有三段用 HTML 注释包住的「底线条款」块（<!-- 底线条款:开始 ... -->
  ... <!-- 底线条款:结束 -->）。这几段是稳定宪法：
    - 只有作者本人能手工改；
    - haohao-eval 的每日召回一个字都不许动它，只能往 daily-learning.md 发增量细则；
    - 细则跟宪法冲突时，宪法赢。
  haohao-eval 靠对宪法块算 sha256 来发现它有没有被悄悄动过（loop.py 里已有 constitution_text
  抽取与校验）。本脚本把同一件事在技能自带一份：不依赖 eval 的环境，
  进场就能自检「标记配对没配对、宪法块是不是还是那一块」。

它做什么：
  1. 找到 SKILL.md 里所有「底线条款:开始 / 结束」注释块；
  2. 校验开始/结束标记配对完整（不能落单、不能错位）；
  3. 给每个块算 sha256（内容哈希），打印块序号、预览、哈希、字符数；
  4. 传 --expect <hash,...> 时，逐个块比对哈希（支持前缀匹配），任一不符即非 0 退出。

退出码：
  0 = 标记配对完整，且（若给了 --expect）哈希全部对得上
  1 = 标记落单/错位，或某块哈希与 --expect 不符
  2 = SKILL.md 找不到 / 读不了
"""

import argparse
import hashlib
import os
import re
import sys

OPEN_MARK = "底线条款:开始"
CLOSE_MARK = "底线条款:结束"

RE_OPEN = re.compile(r"<!--\s*" + re.escape(OPEN_MARK))
RE_CLOSE = re.compile(r"<!--\s*" + re.escape(CLOSE_MARK))


def find_skill_md(explicit=None):
    if explicit:
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(os.path.dirname(here), "SKILL.md")
    return candidate


def parse_blocks(text):
    """返回 (blocks, errors)。blocks: list[(idx, preview, content, sha16)]。
    errors: list[str]（标记配对问题）。"""
    blocks = []
    errors = []
    stack = []  # 每个元素: dict(start_line, content_lines)
    for lineno, line in enumerate(text.split("\n"), 1):
        if RE_OPEN.search(line):
            if stack:
                errors.append("第 %d 行出现第二个「开始」，前一个块（第 %d 行开始）尚未闭合"
                              % (lineno, stack[-1]["start_line"]))
            stack.append({"start_line": lineno, "lines": []})
        elif RE_CLOSE.search(line):
            if not stack:
                errors.append("第 %d 行出现「结束」，但没有对应的「开始」" % lineno)
            else:
                blk = stack.pop()
                content = "\n".join(blk["lines"]).strip("\n")
                sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
                preview = content.strip().replace("\n", " ")[:30]
                blocks.append((len(blocks) + 1, blk["start_line"], preview, content, sha))
        elif stack:
            stack[-1]["lines"].append(line)
    for blk in stack:
        errors.append("第 %d 行开始的「底线条款」块缺少对应的「结束」标记" % blk["start_line"])
    return blocks, errors


def main(argv=None):
    p = argparse.ArgumentParser(description="好好说话 · 宪法（底线条款）注释块完整性校验")
    p.add_argument("--skill", default=None, help="SKILL.md 路径（默认取脚本上级目录的 SKILL.md）")
    p.add_argument("--expect", default=None,
                   help="逗号分隔的期望哈希（支持前缀）。给了就逐个块比对，任一不符退出1")
    args = p.parse_args(argv)

    path = find_skill_md(args.skill)
    if not os.path.exists(path):
        print("[!] 找不到 SKILL.md: %s" % path, file=sys.stderr)
        return 2
    with open(path, encoding="utf-8") as f:
        text = f.read()

    blocks, errors = parse_blocks(text)

    print("SKILL.md: %s" % path)
    print("找到宪法块 %d 个：" % len(blocks))
    for idx, start_line, preview, content, sha in blocks:
        print("  #%d (L%d 起)  %d 字  sha256=%s…" % (idx, start_line, len(content), sha[:16]))
        print("       「%s…」" % preview)

    if errors:
        print("\n[!] 标记配对错误：")
        for e in errors:
            print("  - %s" % e)
        return 1

    if args.expect:
        wanted = [w.strip() for w in args.expect.split(",") if w.strip()]
        if len(wanted) != len(blocks):
            print("\n[!] --expect 给了 %d 个哈希，但宪法块有 %d 个，数量对不上"
                  % (len(wanted), len(blocks)))
            return 1
        bad = False
        for (idx, _, _, content, sha), exp in zip(blocks, wanted):
            if not sha.startswith(exp):
                print("[!] 宪法块 #%d 哈希变了：期望前缀 %s，实际 %s…" % (idx, exp, sha[:16]))
                bad = True
        if bad:
            print("    → 这说明宪法被改过（若是作者有意改，请重新发布 --expect 的哈希；"
                  "若是意外改动，请回滚）。")
            return 1
        print("\n宪法块哈希全部与 --expect 一致。")

    print("OK：底线条款注释块配对完整，未被破坏。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
