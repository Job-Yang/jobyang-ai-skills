#!/usr/bin/env python3
"""方向轮换：每天确定性地选今天扫哪几个方向（纯 stdlib）。

背景：长期每天扫容易重复盯同一批源。本脚本把"今天扫什么"变成确定性算法：
  方向池 = references/rotation-pool.json（方向 id + 源 + 查询词）。
  anchor = 按日期在池里轮转的主方向（days_since_epoch mod len(pool)），
           保证日期驱动、可复算，不凭感觉挑。
  补位方向 = 除 anchor 外，"最久没被扫过"的方向（按历史覆盖记录）。
  每天选 anchor + 1 个补位 = 2 个方向；周期内覆盖全池，不天天重复。

用法：
  python3 rotate.py --date 2026-10-16
  python3 rotate.py --date 2026-10-16 --coverage coverage.json
      coverage.json: {"2026-10-15": ["wishes"], "2026-10-14": ["voice-direct"]}

输出 stdout JSON：{"date","anchor","selected":[ids],"sources":[...],"queries":[...],"coverage":{...}}
退出码：0=成功；2=参数/文件错误。
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POOL = ROOT / "references" / "rotation-pool.json"
EPOCH = dt.date(2026, 1, 1)  # 轮转基准日（固定，改了全历史锚点会变，不要动）


def load_pool() -> list:
    data = json.loads(POOL.read_text(encoding="utf-8"))
    return data["pool"]


def select(today: dt.date, coverage: dict) -> dict:
    pool = load_pool()
    n = len(pool)
    anchor_idx = (today - EPOCH).days % n
    anchor = pool[anchor_idx]
    # 每个方向距今天几天没被扫过；从没扫过 = 9999。
    recency = {}
    for d in pool:
        recency[d["id"]] = 9999
    for date_str, ids in (coverage or {}).items():
        try:
            scanned = (dt.date.fromisoformat(date_str) - today).days
        except ValueError:
            continue
        for i in ids:
            if i in recency:
                recency[i] = min(recency[i], -scanned)
    # 补位：除 anchor 外，最久没扫的（recency 最大），同分时按 id 字典序。
    rest = [d for d in pool if d["id"] != anchor["id"]]
    rest.sort(key=lambda d: (-recency[d["id"]], d["id"]))
    picked = [anchor] + rest[:1]
    return {
        "date": today.isoformat(),
        "anchor": anchor["id"],
        "selected": [d["id"] for d in picked],
        "directions": [{"id": d["id"], "label": d["label"], "lens": d.get("lens", ""),
                        "keywords": d.get("keywords", []), "queries": d.get("queries", [])}
                       for d in picked],
        "sources": sorted({s for d in picked for s in d.get("sources", [])}),
        "queries": [q for d in picked for q in d.get("queries", [])],
        "coverage": recency,
    }


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="每日雷达方向轮换（确定性）")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--coverage", help="历史覆盖 JSON：{date: [direction_id...]}")
    args = ap.parse_args(argv)
    try:
        today = dt.date.fromisoformat(args.date)
        coverage = json.loads(Path(args.coverage).read_text(encoding="utf-8")) if args.coverage else {}
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(json.dumps({"status": "rejected", "error": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        return 2
    print(json.dumps(select(today, coverage), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
