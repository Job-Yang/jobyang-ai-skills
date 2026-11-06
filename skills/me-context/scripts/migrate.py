#!/usr/bin/env python3
"""me-context 数据仓迁移：把体检指标明细从结论层挪到过程层 journal/。

结论层 profile/health.md 只留做判断要用的：过敏/在服药/诊断/结论/关注项；
「## 最新关键指标」「## 历史快照」两节原样挪到 journal/health-metrics.md，
问具体数值或趋势时才读。迁移时按最新指标生成一节「## 当前状态」（只写偏高/偏低/阳性
等需要留意的项，不写数值），让"尿酸偏高"这类结论留在结论层。

viz/趋势通过 mectx_common.read_health_body 合并两份读取，迁移前后结果一致（脚本自检，
不一致自动回退）。默认 dry-run 不写文件；--apply 才写，写前备份到 .migrate-backup/。

用法：
  python3 migrate.py --data ~/me-context-data            # 预演
  python3 migrate.py --data ~/me-context-data --apply    # 执行
退出码：0=成功或无需迁移；1=数据仓异常或自检失败已回退；2=目标文件已存在（不覆盖）。
"""
import argparse
import datetime
import filecmp
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mectx_common as C  # noqa: E402

METRICS_HEAD = """---
schema: personal-context/v1
entity: me
type: self
layer: L3
domain: health
source: declared
updated: {today}
audience: local
---

# 体检指标明细（过程层，L3，只在本机）

> 做判断时默认不带；问具体数值、"这几年怎么变的"时才读。结论写在 profile/health.md。
> 新体检：先把「最新关键指标」整体追加到「历史快照」，再写新的最新值（只增不改）。

"""
STATUS_HEADING = f"## {C.STATUS_HEADING}（据最新体检，细节见 journal/health-metrics.md）"


def split_sections(text):
    """把正文切成 [(heading_or_None, chunk)]，chunk 含标题行本身。"""
    out = []
    marks = list(re.finditer(r"^##\s+([^\n]+)\n", text, re.M))
    if not marks:
        return [(None, text)]
    if marks[0].start() > 0:
        out.append((None, text[:marks[0].start()]))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(1).strip(), text[m.start():end]))
    return out


def plan(data):
    hp = C.safe_join(data, C.DOMAIN_FILE["health"])
    if not hp or not os.path.isfile(hp) or os.path.islink(hp):
        raise ValueError("没有 profile/health.md，无需迁移")
    text = open(hp, encoding="utf-8").read()
    secs = split_sections(text)
    moved = [c for h, c in secs if h and h.startswith(C.HEALTH_DETAIL_HEADINGS)]
    if not moved:
        raise ValueError("profile/health.md 里没有指标明细小节，无需迁移")
    latest, _hist = C.health_sections(C.parse_frontmatter(text)[1])
    lines = C.health_status_lines(latest)
    status = STATUS_HEADING + "\n" + ("\n".join(lines) if lines else "- 最新一次体检没有标出偏高/偏低/阳性的项") + "\n\n"
    # 当前状态插在「过敏/在服药」之后；没有这一节就放在开头说明之后。其余顺序不变
    out, inserted = [], False
    for h, c in [(h, c) for h, c in secs if not (h and h.startswith(C.HEALTH_DETAIL_HEADINGS))]:
        if not inserted and h is not None and not h.startswith("过敏"):
            if not any(x and x.startswith("过敏") for x, _ in secs):
                out.append(status)
                inserted = True
        out.append(c)
        if not inserted and h and h.startswith("过敏"):
            out.append(status)
            inserted = True
    if not inserted:
        out.append(status)
    new_health = "".join(out).rstrip() + "\n"
    metrics_body = "".join(c.rstrip() + "\n\n" for c in moved).rstrip() + "\n"
    return hp, text, new_health, metrics_body, lines


def fingerprint(body):
    latest, hist = C.health_sections(body)
    key = lambda r: (r["name"], r.get("date"), r.get("raw_value"), r.get("unit"), r.get("lab"))
    return sorted(map(key, latest)), sorted(map(key, hist))


def main():
    ap = argparse.ArgumentParser(description="把体检指标明细从结论层挪到过程层 journal/（默认只预演）。")
    ap.add_argument("--data", required=True, help="数据仓路径")
    ap.add_argument("--apply", action="store_true", help="真正写入（默认只预演、不写文件）")
    args = ap.parse_args()
    data = os.path.abspath(os.path.expanduser(args.data))
    if not os.path.isdir(data):
        print(f"[错误] 数据仓不存在：{data}", file=sys.stderr)
        return 1
    try:
        hp, before, new_health, metrics_body, lines = plan(data)
    except ValueError as e:
        print(f"[跳过] {e}")
        return 0
    jp = C.safe_join(data, C.HEALTH_METRICS_FILE)
    if os.path.exists(jp):
        print(f"[停止] {C.HEALTH_METRICS_FILE} 已存在，不覆盖。请先人工合并再重跑。", file=sys.stderr)
        return 2

    fp0 = fingerprint(C.read_health_body(data))
    print("迁移计划（只挪体检指标明细，其他内容一个字不改）：")
    print(f"  · profile/health.md：{len(before)} → {len(new_health)} 字符（做判断时带的就是这一份）")
    print(f"  · 新建 {C.HEALTH_METRICS_FILE}：最新指标 {len(fp0[0])} 项 + 历史 {len(fp0[1])} 个时间点（L3、只在本机、默认不加载）")
    print(f"  · 结论层新增「当前状态」：{len(lines)} 项需要留意（只写偏高/偏低，不写数值）")
    if not args.apply:
        print("预演结束，未写任何文件。确认后加 --apply 执行。")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    broot = os.path.join(data, C.MIGRATE_BACKUP_DIR)
    had_broot = os.path.isdir(broot)
    bdir = os.path.join(broot, stamp, "profile")
    os.makedirs(bdir, exist_ok=True)
    os.chmod(broot, 0o700)  # 备份是改动前的原文，只给本人看
    bak = os.path.join(bdir, "health.md")
    shutil.copy2(hp, bak)
    today = datetime.date.today().isoformat()

    def rollback(reason):
        if not filecmp.cmp(bak, hp, shallow=False):  # 只读文件根本没写进去，不用也写不了
            shutil.copy2(bak, hp)
        if os.path.exists(jp):
            os.remove(jp)
        # 迁移没成，这次的备份也不留（原文件已恢复）；免得重跑撞上同名的只读备份
        shutil.rmtree(os.path.join(broot, stamp), ignore_errors=True)
        if not had_broot:
            shutil.rmtree(broot, ignore_errors=True)
        print(f"[回退] {reason}，已原样恢复，未做任何改动。", file=sys.stderr)
        return 1

    try:
        os.makedirs(os.path.dirname(jp), exist_ok=True)
        with open(jp, "w", encoding="utf-8") as f:
            f.write(METRICS_HEAD.format(today=today) + metrics_body)
        shutil.copymode(hp, jp)  # 新文件沿用原文件权限，明细挪了位置但不能变得更容易被读
        with open(hp, "w", encoding="utf-8") as f:
            f.write(new_health)
    except OSError as e:
        # 比如 health.md 是只读的：过程层已写出、结论层没改，不回退的话明细会出现两份
        return rollback(f"写入失败（{e.strerror}）")

    if fingerprint(C.read_health_body(data)) != fp0:
        return rollback("合并读取结果与迁移前不一致")
    log = os.path.join(data, "CHANGELOG.md")
    if os.path.isfile(log):
        with open(log, encoding="utf-8") as f:
            tail = f.read()[-1:]
        with open(log, "a", encoding="utf-8") as f:
            f.write(("" if tail in ("", "\n") else "\n")
                    + f"- {today} me        结构迁移：体检指标明细移到 {C.HEALTH_METRICS_FILE}（过程层，默认不加载）；"
                    f"health.md 新增「当前状态」小节；数据未改。\n")
    print(f"[完成] 已迁移；原文件备份在 {os.path.dirname(bdir)}")
    print("  自检通过：合并读取的最新指标与历史时间点，与迁移前逐项一致")
    print(f"  备份不会被导出；确认迁移无误后可以自己删掉 {C.MIGRATE_BACKUP_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
