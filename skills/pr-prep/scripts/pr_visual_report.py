#!/usr/bin/env python3
"""生成 PR Markdown 说明骨架与离线自包含 HTML 视觉导览页（写入系统临时目录，绝不污染代码仓）。

用法：
  python3 pr_visual_report.py [--root .] [--base <ref>] [--out-dir <dir>] [--json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

RISK_PATTERNS = {
    "auth": re.compile(r"(?:^|/)(?:auth|oauth|jwt|session|acl|rbac|perm|permission|login|token|security)(?:[/_.-]|$)", re.I),
    "billing": re.compile(r"(?:^|/)(?:pay|payment|billing|invoice|order|wallet|ledger|refund|license|pricing)(?:[/_.-]|$)", re.I),
    "migration": re.compile(r"(?:^|/)(?:migrat(?:ion|e)s?|schema|alembic|flyway|prisma|ddl)(?:[/_.-]|$)", re.I),
    "ci": re.compile(r"(?:^\.github/workflows/|^\.gitlab-ci\.yml$|Makefile$|Dockerfile$|scripts/(?:deploy|release|build|publish))", re.I),
    "lockfile": re.compile(r"(?:package-lock\.json|pnpm-lock\.yaml|yarn\.lock|Cargo\.lock|poetry\.lock|uv\.lock|go\.sum)$"),
}
TEST_PATH_RE = re.compile(
    r"(?:^|/)(?:tests?|__tests__|spec|specs|fixtures?)(?:/|$)|(?:^|/)test_[^/]+$|(?:_test|\.test|\.spec)\.[^/]+$",
    re.I,
)
CODE_SUFFIXES = (
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".swift", ".m", ".mm",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php",
    ".sql", ".sh", ".bash", ".zsh",
)
RENAME_BRACE_RE = re.compile(r"^(.*)\{([^{}]*)\s+=>\s+([^{}]*)\}(.*)$")
MAX_DIFF_BYTES = 2 * 1024 * 1024
MAX_HYGIENE_WARNINGS = 50
MAX_HTML_FILES = 200
MAX_COMMITS = 100

DEBUG_LINE_RE = re.compile(r"^\+.*(?:pdb\.set_trace\(|breakpoint\(|dbg!\(|console\.log\()")
SECRET_LINE_RE = re.compile(
    r"(?:"
    r"(?:api[_-]?key|secret|access[_-]?token|auth[_-]?token|private[_-]?key|password|passwd|client[_-]?secret|bearer)\s*[:=]\s*[\"'`][A-Za-z0-9_\-./+=]{12,}[\"'`]"
    r"|bearer\s+[A-Za-z0-9_\-./+=]{12,}"
    r"|[a-z][a-z0-9+.-]*://[^\s/@\"'`]*:[^\s/@\"'`]{4,}@"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r"|-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
    r"|(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|sk_(?:live|test)_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}"
    r")",
    re.I,
)
DEBUG_LITERAL_RE = re.compile(
    r'"(?:\\.|[^"\\]){4,}"|\'(?:\\.|[^\'\\]){4,}\'|`(?:\\.|[^`\\]){4,}`'
)
URL_CRED_RE = re.compile(r"([a-z][a-z0-9+.-]*://)[^\s/@\"'`<>]*:[^\s/@\"'`<>]+@", re.I)
KV_TOKEN_RE = re.compile(
    r"(\b(?:api[_-]?key|secret|access[_-]?token|auth[_-]?token|private[_-]?key|password|passwd|client[_-]?secret|token|bearer)\s*[:=]\s*)([^\s,;)\]}]+)",
    re.I,
)


def sanitize_debug_snippet(line_body: str) -> str:
    """对调试残留行做字面量、URL 凭据与 key=val 兜底脱敏，并截断到安全摘要长度。"""
    s = DEBUG_LITERAL_RE.sub(lambda m: f"{m.group(0)[0]}<REDACTED>{m.group(0)[0]}", line_body.strip())
    s = URL_CRED_RE.sub(r"\1<REDACTED>@", s)
    s = KV_TOKEN_RE.sub(
        lambda m: m.group(0) if "<REDACTED>" in m.group(2) else f"{m.group(1)}<REDACTED>",
        s,
    )
    return s[:80]


def _clean_rel_path(p: str) -> str:
    return re.sub(r"/+", "/", p.strip()).strip("/")


def expand_numstat_path(raw_path: str) -> tuple[str, list[str]]:
    """展开 git diff --numstat 中的重命名语法 `{old => new}` / `old => new`。"""
    m = RENAME_BRACE_RE.match(raw_path)
    if m:
        prefix, old_seg, new_seg, suffix = m.groups()
        old_p = _clean_rel_path(prefix + old_seg + suffix)
        new_p = _clean_rel_path(prefix + new_seg + suffix)
        paths = [p for p in dict.fromkeys((old_p, new_p)) if p]
        return new_p or old_p, paths
    if " => " in raw_path:
        old_seg, new_seg = raw_path.split(" => ", 1)
        old_p = _clean_rel_path(old_seg)
        new_p = _clean_rel_path(new_seg)
        paths = [p for p in dict.fromkeys((old_p, new_p)) if p]
        return new_p or old_p, paths
    p = _clean_rel_path(raw_path)
    return p, [p] if p else []


def run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    r = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return r.returncode, r.stdout, r.stderr.strip()


def resolve_base(repo: Path, explicit_base: str | None, current_branch: str | None = None) -> str:
    if explicit_base:
        if explicit_base.startswith("-"):
            raise RuntimeError(f"非法的基线参数：{explicit_base!r}")
        rc, _, err = run_git(["rev-parse", "--verify", explicit_base], repo)
        if rc != 0:
            raise RuntimeError(f"基线 {explicit_base} 无效：{err}")
        return explicit_base
    for cand in ("origin/main", "origin/master", "main", "master"):
        if current_branch and cand == current_branch:
            continue
        rc, _, _ = run_git(["rev-parse", "--verify", cand], repo)
        if rc == 0:
            return cand
    rc, _, _ = run_git(["rev-parse", "--verify", "HEAD~1"], repo)
    if rc == 0:
        return "HEAD~1"
    return "HEAD"


def collect_pr_data(root: Path, explicit_base: str | None = None) -> dict:
    rc, top, err = run_git(["rev-parse", "--show-toplevel"], root.resolve())
    if rc != 0 or not top.strip():
        raise RuntimeError(f"非 Git 仓库：{root}（{err}）")
    repo = Path(top.strip()).resolve()
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo)[1].strip() or "HEAD"
    head_sha = run_git(["rev-parse", "--short", "HEAD"], repo)[1].strip() or "HEAD"
    base = resolve_base(repo, explicit_base, branch)

    diff_spec = f"{base}...HEAD" if base != "HEAD" else "HEAD"
    rc_n, numstat, err_n = run_git(["diff", "--no-ext-diff", "--numstat", diff_spec, "--"], repo)
    if rc_n != 0:
        raise RuntimeError(f"git diff 失败：{err_n}")

    files: list[dict] = []
    added_total, deleted_total = 0, 0
    modules: dict[str, dict] = defaultdict(lambda: {"files": 0, "added": 0, "deleted": 0})
    risk_hits: dict[str, list[str]] = defaultdict(list)
    hygiene_warnings: list[str] = []

    for ln in numstat.splitlines():
        parts = ln.split("\t")
        if len(parts) < 3:
            continue
        add_s, del_s, raw_path = parts[0], parts[1], parts[2]
        path, all_paths = expand_numstat_path(raw_path)
        add_n = int(add_s) if add_s.isdigit() else 0
        del_n = int(del_s) if del_s.isdigit() else 0
        added_total += add_n
        deleted_total += del_n
        top_mod = path.split("/", 1)[0] if "/" in path else "(root)"
        modules[top_mod]["files"] += 1
        modules[top_mod]["added"] += add_n
        modules[top_mod]["deleted"] += del_n

        prod_paths = [cp for cp in all_paths if not TEST_PATH_RE.search(cp)]
        file_tags: list[str] = []
        for cp in prod_paths:
            for tag, pat in RISK_PATTERNS.items():
                if pat.search(cp):
                    file_tags.append(tag)
        if del_n > 0 and add_n == 0 and any(cp.lower().endswith(CODE_SUFFIXES) for cp in prod_paths):
            file_tags.append("delete")
        file_tags = sorted(set(file_tags))
        for t in file_tags:
            risk_hits[t].append(path)
        for cp in all_paths:
            if ".agent-work/" in cp or ".agent-work" in Path(cp).parts:
                hygiene_warnings.append(f"禁止入库路径进入 diff：{cp}")
        files.append({"path": path, "module": top_mod, "added": add_n, "deleted": del_n, "tags": file_tags})

    patch_chunks: list[bytes] = []
    total_bytes = 0
    patch_truncated = False
    proc = subprocess.Popen(
        [
            "git",
            "-c",
            "core.quotePath=false",
            "diff",
            "--no-ext-diff",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            diff_spec,
            "--",
        ],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            remain = MAX_DIFF_BYTES - total_bytes
            if remain <= 0:
                patch_truncated = True
                proc.terminate()
                break
            if len(chunk) > remain:
                patch_chunks.append(chunk[:remain])
                total_bytes += remain
                patch_truncated = True
                proc.terminate()
                break
            patch_chunks.append(chunk)
            total_bytes += len(chunk)
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        try:
            rc_p = proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc_p = proc.wait()

    if patch_truncated:
        hygiene_warnings.append("diff 体积超过 2MB 上限，内容扫描已截断")
    if rc_p == 0 or patch_truncated:
        patch_text = b"".join(patch_chunks).decode("utf-8", errors="replace")
        cur_file = ""
        for ln in patch_text.splitlines():
            if ln.startswith("+++ b/"):
                cur_file = ln[6:]
            elif ln.startswith("+") and not ln.startswith("+++"):
                body = ln[1:]
                if SECRET_LINE_RE.search(body):
                    hygiene_warnings.append(f"疑似硬编码凭证 ({cur_file}): <已脱敏>")
                elif DEBUG_LINE_RE.match(ln):
                    safe_snippet = sanitize_debug_snippet(body)
                    hygiene_warnings.append(f"疑似调试残留 ({cur_file}): {safe_snippet}")

    commits: list[dict] = []
    if base != "HEAD":
        rc_c, c_out, _ = run_git(["log", "-n", str(MAX_COMMITS), "--format=%h\t%ad\t%s", "--date=short", f"{base}..HEAD"], repo)
        if rc_c == 0:
            for ln in c_out.splitlines():
                ps = ln.split("\t", 2)
                if len(ps) == 3:
                    commits.append({"sha": ps[0], "date": ps[1], "subject": ps[2]})

    total_lines = added_total + deleted_total
    split_advised = total_lines > 600 or len(modules) >= 4
    visual_recommended = total_lines >= 150 or len(files) >= 5

    return {
        "repo": repo.name,
        "repo_path": str(repo),
        "branch": branch,
        "base": base,
        "head": head_sha,
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "file_count": len(files),
        "added": added_total,
        "deleted": deleted_total,
        "total_lines": total_lines,
        "modules": [
            {"name": k, **v}
            for k, v in sorted(modules.items(), key=lambda kv: (-(kv[1]["added"] + kv[1]["deleted"]), kv[0]))
        ],
        "files": files,
        "commits": commits,
        "risk_tags": {k: sorted(set(v)) for k, v in sorted(risk_hits.items())},
        "hygiene_warnings": sorted(set(hygiene_warnings)),
        "split_advised": split_advised,
        "visual_recommended": visual_recommended,
    }


def render_markdown(data: dict) -> str:
    lines = [
        f"## 变更说明（`{data['branch']}` ← `{data['base']}`）",
        "",
        "### 背景与目标",
        "- <补充一句说明本次改动解决什么问题或对应哪个需求>",
        "",
        "### 模块变更摘要",
    ]
    if data["modules"]:
        for m in data["modules"]:
            lines.append(f"- `{m['name']}`：{m['files']} 个文件（+{m['added']} / -{m['deleted']}）")
    else:
        lines.append("- （当前基线与 HEAD 之间无已提交 diff）")

    lines.extend(["", "### 重点人工审阅风险"])
    if data["risk_tags"]:
        for tag, paths in data["risk_tags"].items():
            more = f" 等共 {len(paths)} 个文件" if len(paths) > 6 else ""
            lines.append(f"- **{tag}**：{', '.join(f'`{p}`' for p in paths[:6])}{more}")
    else:
        lines.append("- 无特定高危路径标记")

    if data["hygiene_warnings"]:
        lines.extend(["", "### 合入前拦截提醒"])
        for w in data["hygiene_warnings"][:MAX_HYGIENE_WARNINGS]:
            lines.append(f"- ⚠️ {w}")
        if len(data["hygiene_warnings"]) > MAX_HYGIENE_WARNINGS:
            lines.append(f"- ……其余 {len(data['hygiene_warnings']) - MAX_HYGIENE_WARNINGS} 条告警已截断")

    lines.extend([
        "",
        "### 验证证据",
        "- <填入实际执行的测试命令、范围及退出码>",
        "",
        "### 灰度与回滚预案",
        "- 灰度开关 / 影响面：<说明是否带配置开关及影响范围>",
        "- 回滚步骤：<说明直接回滚提交或需配套回滚的顺序>",
    ])
    return "\n".join(lines) + "\n"


def render_html(data: dict) -> str:
    esc = html.escape
    max_mod_lines = max((m["added"] + m["deleted"] for m in data["modules"]), default=1) or 1

    mod_rows = []
    for m in data["modules"]:
        tot = m["added"] + m["deleted"]
        pct = max(4, int(100 * tot / max_mod_lines))
        mod_rows.append(
            f"<div class='mod-row'>"
            f"<div class='mod-name'><code>{esc(m['name'])}</code></div>"
            f"<div class='mod-bar-wrap'><div class='mod-bar' style='width:{pct}%'></div></div>"
            f"<div class='mod-stat'>{m['files']} 文件 · +{m['added']} / -{m['deleted']}</div>"
            f"</div>"
        )
    mod_html = "\n".join(mod_rows) or "<p class='muted'>当前无已提交文件改动。</p>"

    risk_badges = []
    for tag, paths in data["risk_tags"].items():
        more = f" 等共 {len(paths)} 个文件" if len(paths) > 6 else ""
        risk_badges.append(
            f"<div class='risk-card'><span class='badge warn'>{esc(tag)}</span> "
            f"{', '.join(f'<code>{esc(p)}</code>' for p in paths[:6])}{esc(more)}</div>"
        )
    if data["hygiene_warnings"]:
        for w in data["hygiene_warnings"][:MAX_HYGIENE_WARNINGS]:
            risk_badges.append(f"<div class='risk-card'><span class='badge danger'>卫生警告</span> {esc(w)}</div>")
        if len(data["hygiene_warnings"]) > MAX_HYGIENE_WARNINGS:
            risk_badges.append(
                f"<div class='risk-card muted'>其余 {len(data['hygiene_warnings']) - MAX_HYGIENE_WARNINGS} 条告警已截断</div>"
            )
    risk_html = "\n".join(risk_badges) or "<p class='ok'>未检测到高危路径标记或卫生泄露项。</p>"

    commit_rows = "\n".join(
        f"<li><code>{esc(c['sha'])}</code> <span class='muted'>{esc(c['date'])}</span> {esc(c['subject'])}</li>"
        for c in data["commits"]
    ) or "<li class='muted'>当前基线区间无新提交。</li>"

    file_rows = []
    for f in data["files"][:MAX_HTML_FILES]:
        tags_html = " ".join(f"<span class='badge warn'>{esc(t)}</span>" for t in f["tags"])
        file_rows.append(
            f"<tr><td><input type='checkbox'/></td>"
            f"<td><code>{esc(f['path'])}</code> {tags_html}</td>"
            f"<td class='num'>+{f['added']} / -{f['deleted']}</td></tr>"
        )
    if len(data["files"]) > MAX_HTML_FILES:
        file_rows.append(
            f"<tr><td colspan='3' class='muted'>其余 {len(data['files']) - MAX_HTML_FILES} 个文件已截断，完整列表请查看 JSON/Git</td></tr>"
        )
    files_html = "\n".join(file_rows) or "<tr><td colspan='3' class='muted'>无改动文件</td></tr>"

    split_banner = (
        "<div class='banner warn'><strong>拆分建议：</strong>"
        f"本次改动合计 {data['total_lines']} 行、覆盖 {len(data['modules'])} 个顶层模块，建议按结构重组/迁移/特性拆分为独立小 PR。</div>"
        if data["split_advised"] else ""
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>PR 视觉导览 · {esc(data['repo'])} ({esc(data['branch'])})</title>
<style>
  :root {{ --bg:#f7f8fa; --card:#fff; --ink:#1f2328; --muted:#59636e; --line:#d0d7de; --accent:#0969da; --warn:#9a6700; --warn-bg:#fff8c5; --danger:#cf222e; --danger-bg:#ffebe9; --ok:#1a7f37; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:24px; background:var(--bg); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; line-height:1.55; }}
  .wrap {{ max-width:980px; margin:0 auto; display:grid; gap:16px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px 20px; }}
  h1 {{ margin:0 0 6px; font-size:20px; }}
  h2 {{ margin:0 0 12px; font-size:15px; border-bottom:1px solid var(--line); padding-bottom:6px; }}
  .muted {{ color:var(--muted); font-size:13px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-top:12px; }}
  .kpi {{ background:#f6f8fa; border:1px solid var(--line); border-radius:8px; padding:10px 12px; }}
  .kpi .v {{ font-size:20px; font-weight:700; }}
  .kpi .k {{ font-size:12px; color:var(--muted); }}
  .mod-row {{ display:grid; grid-template-columns:180px 1fr 160px; align-items:center; gap:10px; margin:6px 0; font-size:13px; }}
  .mod-bar-wrap {{ background:#eaeef2; border-radius:4px; height:10px; overflow:hidden; }}
  .mod-bar {{ background:var(--accent); height:100%; }}
  .badge {{ display:inline-block; padding:1px 7px; border-radius:999px; font-size:11px; font-weight:600; }}
  .badge.warn {{ background:var(--warn-bg); color:var(--warn); }}
  .badge.danger {{ background:var(--danger-bg); color:var(--danger); }}
  .banner {{ padding:12px 14px; border-radius:8px; font-size:13px; border:1px solid #d4a72c; background:var(--warn-bg); }}
  .risk-card {{ margin:6px 0; font-size:13px; }}
  .ok {{ color:var(--ok); font-size:13px; margin:0; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:7px 8px; border-bottom:1px solid #eaeef2; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; color:var(--muted); white-space:nowrap; }}
  ul {{ margin:0; padding-left:18px; font-size:13px; }}
  li {{ margin:4px 0; }}
  code {{ background:#eff1f3; padding:1px 5px; border-radius:4px; font-size:12px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>PR 视觉导览 · {esc(data['repo'])}</h1>
    <div class="muted">分支 <code>{esc(data['branch'])}</code> ← 基线 <code>{esc(data['base'])}</code> · HEAD <code>{esc(data['head'])}</code> · 生成于 {esc(data['generated_at'])}</div>
    <div class="kpis">
      <div class="kpi"><div class="v">{data['file_count']}</div><div class="k">变更文件</div></div>
      <div class="kpi"><div class="v">+{data['added']} / -{data['deleted']}</div><div class="k">净行变动</div></div>
      <div class="kpi"><div class="v">{len(data['commits'])}</div><div class="k">区间提交</div></div>
      <div class="kpi"><div class="v">{len(data['risk_tags'])}</div><div class="k">风险类型</div></div>
    </div>
  </div>
  {split_banner}
  <div class="card"><h2>模块影响分布</h2>{mod_html}</div>
  <div class="card"><h2>高危路径与合入前拦截</h2>{risk_html}</div>
  <div class="card"><h2>提交时间线</h2><ul>{commit_rows}</ul></div>
  <div class="card">
    <h2>逐文件走查清单</h2>
    <table><thead><tr><th style="width:28px">审</th><th>文件与标记</th><th style="text-align:right">行数</th></tr></thead>
    <tbody>{files_html}</tbody></table>
  </div>
  <div class="card">
    <h2>上线与回滚自检</h2>
    <ul>
      <li>是否确认未混入 <code>.agent-work/</code> 与调试残留</li>
      <li>高危或 Schema 变更是否支持滚动期混跑与一键回滚</li>
      <li>PR 说明是否写清实测范围与未覆盖部分</li>
    </ul>
  </div>
</div>
</body>
</html>
"""


def write_reports(data: dict, out_dir: Path | None = None) -> tuple[Path, Path]:
    target_dir = out_dir.resolve() if out_dir else Path(tempfile.gettempdir())
    repo_root = Path(data["repo_path"]).resolve()
    try:
        target_dir.relative_to(repo_root)
        raise RuntimeError(f"禁止将临时视觉报告写入业务仓内部：{target_dir}")
    except ValueError:
        pass
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_branch = re.sub(r"[^A-Za-z0-9._-]+", "-", data["branch"]).strip("-") or "head"
    stamp = dt.date.today().isoformat()
    html_path = target_dir / f"{stamp}-{data['repo']}-{safe_branch}-pr-visual.html"
    md_path = target_dir / f"{stamp}-{data['repo']}-{safe_branch}-pr-summary.md"
    html_path.write_text(render_html(data), encoding="utf-8")
    md_path.write_text(render_markdown(data), encoding="utf-8")
    return html_path, md_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成 PR Markdown 说明骨架与离线视觉导览页")
    ap.add_argument("--root", default=".")
    ap.add_argument("--base", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        data = collect_pr_data(Path(args.root), args.base)
        out_dir = Path(args.out_dir) if args.out_dir else None
        html_path, md_path = write_reports(data, out_dir)
    except RuntimeError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({**data, "html_path": str(html_path), "md_path": str(md_path)}, ensure_ascii=False, indent=2))
    else:
        print(f"HTML 视觉导览: {html_path}")
        print(f"PR 说明骨架:   {md_path}")
        print(f"概览: {data['file_count']} 文件 (+{data['added']}/-{data['deleted']}), 拆分建议={data['split_advised']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
