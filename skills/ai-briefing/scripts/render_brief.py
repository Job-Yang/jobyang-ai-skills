#!/usr/bin/env python3
"""Render a briefing from structured candidate JSON into the fixed card format.

This script is intentionally a *deterministic renderer*, not an editor: the
agent does selection, fact-checking, judgment and scoring; this tool only
guarantees the output shape is consistent every day and on every platform.
Standard library only (Python 3.7+).

Input JSON schema (see examples/brief_input.example.json):
{
  "date": "2026-10-23", "weekday": "周五", "window_note": "",
  "top3": ["...", "...", "..."],
  "groups": [
    {"emoji": "🧠", "title": "新模型", "items": [
      {"title": "...", "url": "https://...", "fact": "...",
       "judgment": "...", "stars": "⭐4", "stars_reason": "...",
       "source": "来源 · 时间"}
    ]}
  ],
  "weekly_github": [ {same item shape} ],
  "channel_status": ["飞书文档：成功", "X：直连成功"],
  "doc_url": "https://..."
}

Missing / empty groups are rendered as "今日无值得报的".
"""
import argparse
import io
import json
import sys

REQUIRED_ITEM = ("title", "fact", "judgment", "stars", "stars_reason", "source")


def _item(item):
    for k in REQUIRED_ITEM:
        if k not in item:
            raise ValueError("条目缺字段 %s: %r" % (k, item.get("title", "?")))
    title = item["title"].strip()
    if item.get("url"):
        head = "**[%s](%s)**" % (title, item["url"])
    else:
        head = "**%s**" % title
    lines = [
        head + "｜" + item["fact"].strip(),
        "【我的判断】" + item["judgment"].strip(),
        "【机会分】" + item["stars"].strip() + "：" + item["stars_reason"].strip(),
        item["source"].strip(),
        "",
    ]
    return "\n".join(lines)


def render(data):
    out = []
    out.append("# %s %s · AI 早报" % (data.get("date", ""), data.get("weekday", "")))
    if data.get("window_note"):
        out.append("")
        out.append("> " + data["window_note"].strip())
    out.append("")
    out.append("## ⚡ 今日最值得看的 3 条")
    top3 = data.get("top3") or []
    if not top3:
        raise ValueError("top3 不能为空")
    for i, t in enumerate(top3[:3], 1):
        out.append("%d. %s" % (i, t.strip()))
    out.append("")
    for g in data.get("groups", []):
        out.append("## %s %s" % (g.get("emoji", "📌"), g.get("title", "").strip()))
        items = g.get("items") or []
        if not items:
            out.append("今日无值得报的。")
            out.append("")
            continue
        for it in items:
            out.append(_item(it))
    wg = data.get("weekly_github")
    if wg:
        out.append("## 🐙 本周 GitHub Trending 复盘")
        for it in wg:
            out.append(_item(it))
    out.append("对哪条感兴趣，回我编号或名字，我接着深挖。")
    out.append("")
    status = data.get("channel_status") or []
    if status:
        out.append("---")
        out.append("**渠道状态**：" + "；".join(s.strip() for s in status) + "。")
    if data.get("doc_url"):
        out.append("文档：" + data["doc_url"].strip())
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Render a briefing JSON to Markdown.")
    ap.add_argument("--input", default="", help="Input JSON file; default stdin.")
    args = ap.parse_args()
    raw = io.open(args.input, "r", encoding="utf-8").read() if args.input else sys.stdin.read()
    try:
        out = render(json.loads(raw))
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        # Bad candidate input must fail loudly so the agent fixes the data,
        # rather than shipping a malformed briefing.
        sys.stderr.write("渲染失败（候选 JSON 不合格）: %s\n" % e)
        sys.exit(1)
    sys.stdout.write(out)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
