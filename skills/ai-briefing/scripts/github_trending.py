#!/usr/bin/env python3
"""Fetch and parse GitHub Trending without any third-party dependency.

Standard library only (Python 3.7+). Works offline with --html (a saved
GitHub trending page), which the test suite uses for deterministic checks.

Usage:
  python3 github_trending.py --range weekly --language typescript
  python3 github_trending.py --range weekly --html fixtures/trending_weekly.html
  python3 github_trending.py --range weekly --json < trending.html

Output: JSON on stdout:
  {"range":"weekly","fetched":true,"repos":[{"repo":...,"url":...,
    "description":...,"language":...,"stars_total":...,"stars_gained":...,
    "gained_label":"201,065 stars this week"}]}
"""
import argparse
import gzip
import html as html_mod
import io
import json
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch_html(language: str = "", range_: str = "daily") -> str:
    url = "https://github.com/trending"
    if language:
        url += "/" + language.strip("/")
    url += "?since=" + range_
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="ignore")


def _clean_text(node: str) -> str:
    node = re.sub(r"<[^>]+>", "", node)
    return html_mod.unescape(node).strip()


def _to_int(s):
    if not s:
        return None
    try:
        return int(s.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def parse_trending(doc: str, range_: str = "daily"):
    repos = []
    for block in doc.split("<article"):
        if "Box-row" not in block[:200]:
            continue
        head = block[: block.find("</article>")] if "</article>" in block else block
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', head)
        if not m:
            continue
        repo = re.sub(r"\s+", "", m.group(1)).strip("/")
        d = re.search(r'<p class="col-9[^"]*">(.*?)</p>', head, re.S)
        desc = _clean_text(d.group(1)) if d else ""
        lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', head)
        total = re.search(r'/stargazers"[^>]*>.*?</svg>\s*([\d,]+)', head, re.S)
        period_word = {"daily": "today", "weekly": "this week", "monthly": "this month"}.get(range_, "today")
        gained = re.search(r'([\d,]+)\s+stars\s+' + period_word.replace(" ", r"\s+"), head)
        repos.append({
            "repo": repo,
            "url": "https://github.com/" + repo,
            "description": desc,
            "language": lang.group(1).strip() if lang else None,
            "stars_total": _to_int(total.group(1)) if total else None,
            "stars_gained": _to_int(gained.group(1)) if gained else None,
            "gained_label": (gained.group(1) + " stars " + period_word) if gained else "",
        })
    # GitHub lists trending rows in descending popularity; keep that order.
    return repos


def _fail(msg):
    # Structured failure instead of a raw traceback: the calling agent can
    # detect this and degrade to another source rather than crashing.
    sys.stderr.write(json.dumps({"error": msg}, ensure_ascii=False) + "\n")
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description="GitHub Trending parser (stdlib only).")
    ap.add_argument("--range", default="weekly", choices=["daily", "weekly", "monthly"])
    ap.add_argument("--language", default="", help="Optional language path, e.g. typescript / python.")
    ap.add_argument("--html", default="", help="Parse a saved HTML file instead of fetching.")
    ap.add_argument("--stdin", action="store_true", help="Read HTML from stdin instead of fetching.")
    ap.add_argument("--top", type=int, default=0, help="Keep only the first N repos (0 = all).")
    args = ap.parse_args()

    fetched = False
    if args.html:
        try:
            with io.open(args.html, "r", encoding="utf-8", errors="ignore") as f:
                doc = f.read()
        except OSError as e:
            _fail("读取本地 HTML 失败: %s" % e)
    elif args.stdin:
        doc = sys.stdin.read()
    else:
        try:
            doc = fetch_html(args.language, args.range)
        except Exception as e:  # network/DNS/TLS/HTTP — all degrade, never crash silently
            _fail("实时抓取 GitHub Trending 失败（可能无公网或被限流）: %s" % e)
        fetched = True

    repos = parse_trending(doc, args.range)
    if not repos:
        _fail("解析到 0 个仓库：GitHub 页面结构可能已改版，或提供的 HTML 不是 trending 页")
    if args.top > 0:
        repos = repos[: args.top]
    json.dump({"range": args.range, "language": args.language or None,
               "fetched": fetched, "count": len(repos), "repos": repos},
              sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
