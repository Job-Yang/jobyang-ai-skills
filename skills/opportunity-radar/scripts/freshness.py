#!/usr/bin/env python3
"""证据对抗式自检（纯 stdlib，离线判定；联网探测可选）。

雷达的反例库——构造反例来证伪自己：证据 URL 404 / 日期是半年前 / 标题党无付费信号 /
与历史同方向换皮 / 搜索源被污染。本脚本把这些反例写成确定性检查。

0.4.0 召回改造（2026-10-20 复盘）：检查项分成硬旗（hard）和软旗（soft）两层。
旧版所有旗都让 deep_dig=False，导致"没有付费信号"和"近亲方向"被一票否决，
原始候选只剩 4 条时几乎必空。新契约：

硬旗（证据本身不成立，不允许进深挖）：
  - stale_evidence：证据日期早于 --max-age-days（默认 180 天），时间窗不成立。
  - future_evidence：证据日期在未来，物理上不可能是已发生的一手证据。
  - polluted_source：证据 URL 命中已知垃圾源黑名单，必须换一手源。
  - bad_url：证据 URL 不是 http(s)。
  - already_logged:DUP：与历史同一件事换皮（幂等红线，不能再立条）。

软旗（证据偏弱，提醒 Agent 深挖时先补证；不单独挡候选）：
  - undated：没给证据日期，要求人补日期。
  - payment_unverified：payment_signal 里看不到明确花钱/差评信号词。
    新供给（Show HN、GitHub 新项目）天然没有付费信号，不该因此被埋没；
    缺付费证据意味着打分时「离钱近」保守给分，而不是不允许深挖。
  - already_logged:RELATED：近亲方向。记录并在条目里注明即可，
    同一大主题的新切面（比如 agent 管控的不同环节）允许再看一次。

deep_dig = 没有任何硬旗。退出码 4 只在全部候选被硬旗挡住时返回。

用法：
  python3 freshness.py --candidates today.json [--today 2026-10-16] [--dedup dedup.json]

退出码：0=至少一条可立（deep_dig=True）；4=全部被硬旗挡住；2=参数错误。
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

MAX_AGE_DAYS = 180
# 花钱/差评信号词：说不出有人在付钱的"机会"，多半是标题党——0.4.0 起这是软旗。
_MONEY = re.compile(r"pay|paid|subscription|付费|订阅|花|烧|差评|星|退款|退订|\\\$|\$\d", re.I)
# 已知被通用搜索污染的垃圾源（references/sources.md 真踩过：imtqy.com）。
_POLLUTED = {"imtqy.com", "content-farm.example.com"}

# 硬旗集合：命中任意一条，候选不允许进深挖。
HARD_FLAGS = {
    "stale_evidence", "future_evidence", "polluted_source", "bad_url",
    "already_logged:DUP",
}


def host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", (url or "").strip().lower())
    return m.group(1) if m else ""


def check_candidate(c: dict, today: dt.date, dedup_verdict: str | None) -> dict:
    hard, soft, actions = [], [], []
    # 1. 时效
    date_str = (c.get("evidence_date") or "").strip()
    if not date_str:
        soft.append("undated")
        actions.append("补证据日期；日期不明不许默认它新鲜（软警告，不单独挡候选）")
    else:
        try:
            age = (today - dt.date.fromisoformat(date_str)).days
            if age < 0:
                # 未来日期在物理上不可能已发生 → 硬旗。
                hard.append("future_evidence")
                actions.append(f"证据日期 {date_str} 在未来：尚未发生，不是 real 证据，退回重取")
            elif age > MAX_AGE_DAYS:
                hard.append("stale_evidence")
                actions.append(f"证据是 {age} 天前（>{MAX_AGE_DAYS}）：时间窗不成立，降级 assumption，不立条")
        except ValueError:
            soft.append("undated")
            actions.append(f"evidence_date 不是合法日期：{date_str}（补日期前按弱证据处理）")
    # 2. 付费信号（软旗）
    sig = c.get("payment_signal") or ""
    if not _MONEY.search(sig):
        soft.append("payment_unverified")
        actions.append("看不到明确花钱/差评信号：深挖时优先补「谁在付钱」，打分「离钱近」保守给分")
    # 3. 源污染（硬旗）
    host = host_of(c.get("evidence_url", ""))
    if not host:
        hard.append("bad_url")
        actions.append("证据 URL 不是 http(s)：退回真链接")
    elif any(p in host for p in _POLLUTED):
        hard.append("polluted_source")
        actions.append(f"{host} 是已知垃圾源：换一手源重取，这条不算证据")
    # 4. 去重结论：DUP 硬挡，RELATED 软提醒
    if dedup_verdict == "DUP":
        hard.append("already_logged:DUP")
        actions.append("历史已 triage 过的同一件事：不重复立条")
    elif dedup_verdict == "RELATED":
        soft.append("already_logged:RELATED")
        actions.append("历史有近亲方向：可再看新切面，条目里注明近亲是谁")
    deep_dig = not hard
    if hard:
        status = "assumption" if "stale_evidence" in hard else "rejected"
    else:
        status = "real" if not soft else "weak"
    return {
        "title": c.get("title", ""),
        "evidence_status": status,
        "hard_flags": hard,
        "soft_flags": soft,
        # 保留 flags 为并集，兼容只认旧字段的下游（新代码请读 hard_flags/soft_flags）。
        "flags": hard + soft,
        "deep_dig": deep_dig,
        "actions": actions,
    }


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="雷达证据对抗式自检（硬旗挡候选，软旗提醒补证）")
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--today", default=None, help="默认今天 YYYY-MM-DD")
    ap.add_argument("--dedup", help="dedup.py 的输出 JSON（用于换皮降级）")
    args = ap.parse_args(argv)
    try:
        today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
        cands = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
        verdict_by_title = {}
        if args.dedup:
            dedup = json.loads(Path(args.dedup).read_text(encoding="utf-8"))
            verdict_by_title = {r["title"]: r["verdict"] for r in dedup.get("results", [])}
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(json.dumps({"status": "rejected", "error": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        return 2
    results = [check_candidate(c, today, verdict_by_title.get(c.get("title", ""))) for c in cands]
    deep = sum(1 for r in results if r["deep_dig"])
    payload = {
        "today": today.isoformat(),
        "policy": "hard_flags block; soft_flags warn only",
        "deep_dig": deep,
        "downgraded": len(results) - deep,
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if deep > 0 else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
