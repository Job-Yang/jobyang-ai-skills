#!/usr/bin/env python3
"""design_memory.py：产品设计档案和个人口味记录。

档案放在产品目录里，跟代码一起提交：
  DESIGN.md              给所有 AI 工具读的设计说明（export_tokens.py --targets design-md 导出）
  design/tokens.json     数值的事实源（行为看原型 HTML）
  design/direction.md    方向简报
  design/decisions.md    决策记录（本脚本 record 追加）

个人口味记录跨产品，默认在 ~/.style-compass/taste.md（可用 STYLE_COMPASS_HOME 或 --taste 改）。
写不写由用户定：还没有这个文件时 record 不写口味，只提示先问用户；同意就加 --remember-taste，
不同意就运行 taste --off，文件里留下关闭标记，以后不再写也不再问。

子命令：
  scan <产品目录>      找档案和代码里的设计信号，给出建议路线：新产品 / 延续 / 补档
  record <产品目录>    追加一条决策到 decisions.md；用户同意过才同时写口味记录
  check <产品目录>     按 tokens.json 重新导出，和档案里的 DESIGN.md、design/ 下的导出产物、
                       prototype/tokens.css 整份比较；缺 DESIGN.md 或有一份对不上就返回 1
  extract <代码目录>   盘点已有代码的颜色、字体、圆角、间距，生成补档草稿
  taste                汇总口味记录：常选坐标、反复否掉的理由、新颖度提醒；--off 关闭，--on 重新开启

只用标准库。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from token_utils import TokenError, is_grayish, iter_colors, load_tokens, oklch, parse_hex, to_hex  # noqa: E402

SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".nuxt", "out", "coverage", "Pods",
             "DerivedData", ".venv", "venv", "__pycache__", ".turbo", ".cache", "vendor", "target"}
CODE_SUFFIXES = {".css", ".scss", ".sass", ".less", ".html", ".vue", ".svelte", ".jsx", ".tsx", ".js",
                 ".ts", ".mjs", ".cjs", ".swift"}
CSSISH = {".css", ".scss", ".sass", ".less", ".html", ".vue", ".svelte"}
UI_SUFFIXES = CSSISH | {".jsx", ".tsx", ".swift"}
HEX_LITERAL_RE = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}(?:[0-9a-fA-F]{2})?\b")
# 技能自己写进产品目录的东西，不算已有界面代码。
OWN_OUTPUT_DIRS = ("design", "prototype")
UI_LIBRARIES = {
    "antd": "Ant Design", "@arco-design/web-react": "Arco Design", "@arco-design/web-vue": "Arco Design",
    "@douyinfe/semi-ui": "Semi Design", "tdesign-react": "TDesign", "tdesign-vue-next": "TDesign",
    "@mui/material": "MUI", "@chakra-ui/react": "Chakra UI", "element-plus": "Element Plus",
    "@radix-ui/react-dialog": "Radix", "@headlessui/react": "Headless UI", "tailwindcss": "Tailwind CSS",
    "@shadcn/ui": "shadcn/ui", "vant": "Vant", "@nutui/nutui": "NutUI",
}
MAX_FILES = 6000
MAX_BYTES = 1_000_000
ENTRY_FIELDS = ("选中", "候选", "否掉", "感受词", "关卡", "备注")


def taste_path(explicit: Optional[str] = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    home = os.environ.get("STYLE_COMPASS_HOME")
    return (Path(home).expanduser() if home else Path.home() / ".style-compass") / "taste.md"


def walk(root: Path):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".") or d == ".stitch"]
        for name in filenames:
            yield Path(dirpath) / name
            count += 1
            if count >= MAX_FILES:
                return


def read_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


# ---------- 决策记录与口味 ----------

def parse_entries(text: str) -> List[dict]:
    entries: List[dict] = []
    current: Optional[dict] = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(\d{4}-\d{2}-\d{2})\s*(?:·\s*(.*))?$", line.strip())
        if m:
            current = {"date": m.group(1), "product": (m.group(2) or "").strip()}
            entries.append(current)
            continue
        m = re.match(r"^-\s*([^：:]+)[：:]\s*(.*)$", line.strip())
        if current is not None and m and m.group(1).strip() in ENTRY_FIELDS:
            current[m.group(1).strip()] = m.group(2).strip()
    return entries


def format_entry(date: str, product: str, fields: Dict[str, str]) -> str:
    lines = [f"## {date}" + (f" · {product}" if product else "")]
    for key in ENTRY_FIELDS:
        if fields.get(key):
            lines.append(f"- {key}：{fields[key]}")
    return "\n".join(lines) + "\n"


def append_entry(path: Path, header: str, entry: str, fields: Dict[str, str], date: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    entries = parse_entries(existing)
    if entries:
        last = entries[-1]
        if last.get("date") == date and all(last.get(k, "") == fields.get(k, "") for k in ENTRY_FIELDS):
            return False
    with path.open("a", encoding="utf-8") as f:
        if not existing:
            f.write(header + "\n")
        elif not existing.endswith("\n\n"):
            f.write("\n" if existing.endswith("\n") else "\n\n")
        f.write(entry)
    return True


def coordinate_of(chosen: str) -> str:
    return re.split(r"[/／（(]", chosen or "", maxsplit=1)[0].strip()


def summarize_taste(entries: List[dict], recent: int = 3) -> dict:
    chosen = [coordinate_of(e.get("选中", "")) for e in entries if e.get("选中")]
    counts = Counter(c for c in chosen if c)
    reasons: Counter = Counter()
    for e in entries:
        for part in re.split(r"[；;]", e.get("否掉", "")):
            m = re.search(r"[（(:：]\s*([^）)]+)", part)
            if m:
                for reason in re.split(r"[，,、]", m.group(1)):
                    if reason.strip():
                        reasons[reason.strip()] += 1
    words: Counter = Counter()
    for e in entries:
        for w in re.split(r"[，,、\s]+", e.get("感受词", "")):
            if w.strip():
                words[w.strip()] += 1
    last = chosen[-recent:]
    streak = len(last) == recent and len(set(last)) == 1 and last[0] != ""
    return {
        "entries": len(entries),
        "chosen": counts.most_common(),
        "recentChosen": last,
        "repeatedRejections": [(r, n) for r, n in reasons.most_common() if n >= 2],
        "words": words.most_common(8),
        "noveltyWarning": (f"最近 {recent} 次都选了 {last[0]}；这次候选里至少放两个其他坐标的方向，它们同样要满足简报的目标感受"
                           if streak else ""),
    }


# ---------- scan ----------

def find_archive(root: Path) -> dict:
    found = {}
    for key, rel in (("designMd", "DESIGN.md"), ("tokens", "design/tokens.json"),
                     ("direction", "design/direction.md"), ("decisions", "design/decisions.md"),
                     ("stitch", ".stitch/DESIGN.md")):
        p = root / rel
        if p.exists():
            found[key] = str(p)
    return found


def code_signals(root: Path) -> dict:
    signals = {"files": [], "libraries": [], "cssVariables": 0, "swiftColors": 0, "uiFiles": 0, "colorLiterals": 0}
    own_dirs = [root / d for d in OWN_OUTPUT_DIRS]
    for path in walk(root):
        if any(d in path.parents for d in own_dirs):
            continue
        name = path.name
        if path.suffix in UI_SUFFIXES:
            signals["uiFiles"] += 1
            if path.suffix != ".swift":
                signals["colorLiterals"] += len(HEX_LITERAL_RE.findall(read_text(path)))
        if re.fullmatch(r"tailwind\.config\.(js|ts|cjs|mjs)", name) or name == "components.json":
            signals["files"].append(str(path.relative_to(root)))
        elif name == "package.json":
            try:
                pkg = json.loads(read_text(path) or "{}")
            except json.JSONDecodeError:
                continue
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            for dep, label in UI_LIBRARIES.items():
                if dep in deps and label not in signals["libraries"]:
                    signals["libraries"].append(label)
        elif path.suffix in (".css", ".scss", ".less"):
            signals["cssVariables"] += len(re.findall(r"--[\w-]+\s*:", read_text(path)))
        elif path.suffix == ".swift":
            signals["swiftColors"] += len(re.findall(r"\bColor\(", read_text(path)))
        elif path.suffix == ".colorset" or path.parent.suffix == ".colorset":
            signals["swiftColors"] += 1
    return signals


def suggest_route(archive: dict, signals: dict) -> Tuple[str, str]:
    if "tokens" in archive or "designMd" in archive:
        return "延续", "读 DESIGN.md、design/direction.md 和最近的决策，新页面直接用现有 token；只有用户要改方向才回到方向关。"
    if (signals["files"] or signals["libraries"] or signals["cssVariables"] >= 10 or signals["swiftColors"] >= 10
            or signals["uiFiles"] >= 3 or signals["colorLiterals"] >= 10):
        return "补档", "先运行 extract 盘点现有代码，把高频值映射成 tokens.json，让用户在渲染页上确认，再写档案。"
    return "新产品", "走完整流程：结构关、交互关、方向关、交付关；交付时写档案。"


def cmd_scan(args) -> int:
    root = Path(args.dir).expanduser().resolve()
    if not root.is_dir():
        print(f"[archive] ERROR 不是目录：{root}", file=sys.stderr)
        return 2
    archive = find_archive(root)
    signals = code_signals(root)
    route, next_step = suggest_route(archive, signals)
    decisions = parse_entries(read_text(Path(archive["decisions"]))) if "decisions" in archive else []
    drift = drift_report(root) if "tokens" in archive else None
    taste_file = taste_path(args.taste)
    taste_mode = taste_state(taste_file)
    taste = summarize_taste(parse_entries(read_text(taste_file))) if taste_mode == "on" else None
    report = {"dir": str(root), "archive": archive, "signals": signals, "route": route, "next": next_step,
              "recentDecisions": decisions[-3:], "drift": drift, "taste": taste, "tasteFile": str(taste_file),
              "tasteState": taste_mode}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"[archive] 产品目录：{root}")
    print("[archive] 档案：" + ("、".join(Path(p).relative_to(root).as_posix() for p in archive.values()) if archive else "没有"))
    if drift is not None:
        print("[archive] 档案与 tokens.json " + ("一致" if not drift["mismatches"] else f"有 {len(drift['mismatches'])} 处对不上，先运行 check"))
    parts = signals["files"][:3] + signals["libraries"]
    if signals["cssVariables"]:
        parts.append(f"{signals['cssVariables']} 个 CSS 变量")
    if signals["swiftColors"]:
        parts.append(f"{signals['swiftColors']} 处 SwiftUI 颜色")
    if signals["uiFiles"]:
        parts.append(f"{signals['uiFiles']} 个界面文件")
    if signals["colorLiterals"]:
        parts.append(f"{signals['colorLiterals']} 处写死的颜色")
    print("[archive] 代码信号：" + ("、".join(parts) if parts else "没有"))
    for e in decisions[-3:]:
        print(f"[archive] 决策 {e['date']}：选中 {e.get('选中', '?')}" + (f"；否掉 {e['否掉']}" if e.get("否掉") else ""))
    if taste:
        common = "、".join(f"{c}({n})" for c, n in taste["chosen"][:3]) or "无"
        print(f"[archive] 口味记录：{taste['entries']} 条；常选 {common}")
        if taste["repeatedRejections"]:
            print("[archive] 反复否掉的理由：" + "、".join(f"{r}({n})" for r, n in taste["repeatedRejections"][:5]))
        if taste["noveltyWarning"]:
            print(f"[archive] 新颖度提醒：{taste['noveltyWarning']}")
    elif taste_mode == "off":
        print("[archive] 口味记录：用户关掉了，不读也不写")
    print(f"[archive] 建议路线：{route}。{next_step}")
    return 0


# ---------- record / taste ----------

TASTE_OFF = "<!-- style-compass: taste off -->"
TASTE_HEADER = ("# 个人口味记录\n\n每次选方向追加一条。只记事实：给了哪些候选、选了哪个、为什么否掉其他的。\n"
                "只存在这台机器上。不想再记就运行 design_memory.py taste --off；删掉本文件就清空了。\n")


def taste_state(tp: Path) -> str:
    """unset：还没问过用户；on：用户同意记；off：用户不让记。"""
    if not tp.exists():
        return "unset"
    return "off" if TASTE_OFF in read_text(tp) else "on"


def set_taste_off(tp: Path, off: bool) -> None:
    text = read_text(tp) if tp.exists() else TASTE_HEADER
    text = text.replace(TASTE_OFF + "\n", "").replace(TASTE_OFF, "")
    tp.parent.mkdir(parents=True, exist_ok=True)
    tp.write_text((TASTE_OFF + "\n" if off else "") + text, encoding="utf-8")


def cmd_record(args) -> int:
    root = Path(args.dir).expanduser().resolve()
    date = args.date or _dt.date.today().isoformat()
    product = args.product or root.name
    fields = {"选中": args.chosen, "候选": args.offered or "", "否掉": "；".join(args.rejected or []),
              "感受词": args.words or "", "关卡": args.stage or "", "备注": args.note or ""}
    entry = format_entry(date, product, fields)
    wrote = append_entry(root / "design" / "decisions.md", "# 设计决策记录\n", entry, fields, date)
    print(("[archive] 已追加：" if wrote else "[archive] 与最后一条相同，跳过：") + str(root / "design" / "decisions.md"))
    if args.no_taste:
        return 0
    tp = taste_path(args.taste)
    state = taste_state(tp)
    if args.remember_taste and state == "off":
        set_taste_off(tp, False)
        state = "on"
    if state == "off":
        print(f"[archive] 口味记录已关闭，没有写：{tp}")
    elif state == "unset" and not args.remember_taste:
        print(f"[archive] 口味记录还没开，这次没写。先问用户一次：要不要在这台机器上记住每次给了哪些方向、选了哪个、"
              f"为什么否掉，下次出候选时参考？只存在 {tp}，不进产品仓库。"
              "同意就加 --remember-taste 重新运行这条 record；不同意就运行 design_memory.py taste --off，以后不再问")
    else:
        wrote = append_entry(tp, TASTE_HEADER, entry, fields, date)
        print(("[archive] 已追加：" if wrote else "[archive] 与最后一条相同，跳过：") + str(tp))
    return 0


def cmd_taste(args) -> int:
    tp = taste_path(args.taste)
    if args.off or args.on:
        set_taste_off(tp, args.off)
        if args.off:
            print(f"[taste] 口味记录已关闭，以后 record 不再写，也不再问：{tp}。已有的记录还在，要清空就删掉这个文件")
        else:
            print(f"[taste] 口味记录已开启：{tp}")
        return 0
    state = taste_state(tp)
    if state == "unset":
        print(f"[taste] 还没有口味记录：{tp}")
        return 0
    if state == "off":
        print(f"[taste] 口味记录已关闭：{tp}")
        return 0
    summary = summarize_taste(parse_entries(read_text(tp)), recent=args.recent)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    print(f"[taste] {tp}：{summary['entries']} 条")
    print("[taste] 常选坐标：" + ("、".join(f"{c}({n})" for c, n in summary["chosen"]) or "无"))
    print("[taste] 最近：" + (" → ".join(summary["recentChosen"]) or "无"))
    if summary["repeatedRejections"]:
        print("[taste] 反复否掉的理由：" + "、".join(f"{r}({n})" for r, n in summary["repeatedRejections"]))
    if summary["words"]:
        print("[taste] 常用感受词：" + "、".join(f"{w}({n})" for w, n in summary["words"]))
    if summary["noveltyWarning"]:
        print(f"[taste] 新颖度提醒：{summary['noveltyWarning']}")
    return 0


# ---------- check ----------

def parse_front_matter(text: str) -> dict:
    """解析 DESIGN.md 的 YAML front matter。只支持规范用到的嵌套映射和标量。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
    if not m:
        return {}
    root: dict = {}
    stack: List[Tuple[int, dict]] = [(-1, root)]
    for raw in m.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, _, value = raw.strip().partition(":")
        key = key.strip().strip("'\"")
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            if value[:1] in "'\"" and value[-1:] == value[:1]:
                value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            parent[key] = value
    return root


def flatten(obj: dict, prefix: str = "") -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in obj.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, path))
        else:
            out[path] = str(v)
    return out


# 档案里由 tokens.json 导出的文件：（相对产品目录的路径，导出 target）。DESIGN.md 必须有，其余有就核对。
ARCHIVE_EXPORTS = (
    ("DESIGN.md", "design-md"),
    ("design/tokens.css", "css"),
    ("design/tailwind.tokens.js", "tailwind"),
    ("design/DesignTokens.swift", "swift"),
    ("design/tokens.dtcg.json", "dtcg"),
    ("design/style-prompt.md", "prompt"),
    ("prototype/tokens.css", "css"),
)
CODE_TARGETS = {"css", "tailwind", "swift", "dtcg"}


def normalized(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip()


def css_vars(text: str) -> Dict[str, str]:
    return {k: v.strip() for k, v in re.findall(r"(--[\w-]+):\s*([^;]+);", text)}


def drift_report(root: Path) -> dict:
    """把档案里每份导出产物按 tokens.json 重新导出一遍，整份比较。"""
    import export_tokens  # noqa: E402

    tokens = load_tokens(str(root / "design" / "tokens.json"))
    brief_file = root / "design" / "direction.md"
    briefs = [export_tokens.read_brief(str(brief_file)) if brief_file.exists() else ""]
    if briefs[0]:
        briefs.append("")
    checked: List[str] = []
    mismatches: List[dict] = []
    for rel, target in ARCHIVE_EXPORTS:
        path = root / rel
        if not path.exists():
            if target == "design-md":
                mismatches.append({"file": rel, "key": None, "problem": "missing"})
            continue
        checked.append(rel)
        actual = read_text(path)
        expected = [export_tokens.render(target, tokens, brief) for brief in (briefs if target in ("design-md", "prompt") else [""])]
        if normalized(actual) in {normalized(text) for text in expected}:
            continue
        details: List[dict] = []
        if target == "design-md":
            want = flatten(export_tokens.design_md_front_matter(tokens))
            have = flatten(parse_front_matter(actual))
            for key, value in want.items():
                if key.startswith(("colors.", "typography.", "rounded.", "spacing.")) and \
                        have.get(key, "").strip().lower() != str(value).strip().lower():
                    details.append({"file": rel, "key": key, "tokens": value, "file_value": have.get(key)})
        elif target == "css":
            want, have = css_vars(expected[0]), css_vars(actual)
            for name, value in want.items():
                if have.get(name, "").lower() != value.lower():
                    details.append({"file": rel, "key": name, "tokens": value, "file_value": have.get(name)})
        mismatches.extend(details or [{"file": rel, "key": None, "problem": "stale"}])

    warnings = []
    if not any(target in CODE_TARGETS and rel in checked and rel.startswith("design/") for rel, target in ARCHIVE_EXPORTS):
        warnings.append("design/ 里没有 tokens.css、tailwind.tokens.js、DesignTokens.swift、tokens.dtcg.json 中的任何一份，"
                        "代码侧的导出这次没有核对；导出到了别的目录的话，那些文件要自己重新导出")
    targets = sorted({target for rel, target in ARCHIVE_EXPORTS if rel in checked and not rel.startswith("prototype/")}
                     | {"design-md"}, key=export_tokens.ALL_TARGETS.index)
    fix = [f"python3 {Path(__file__).resolve().parent / 'export_tokens.py'}", "design/tokens.json",
           "--targets", ",".join(targets), "--design-md", "DESIGN.md"]
    if brief_file.exists():
        fix += ["--brief", "design/direction.md"]
    if "prototype/tokens.css" in checked:
        fix += ["--prototype", "prototype"]
    return {"checked": checked, "mismatches": mismatches, "warnings": warnings, "fix": " ".join(fix)}


def cmd_check(args) -> int:
    root = Path(args.dir).expanduser().resolve()
    if not (root / "design" / "tokens.json").exists():
        print(f"[check] ERROR 没有 {root / 'design' / 'tokens.json'}", file=sys.stderr)
        return 2
    try:
        report = drift_report(root)
    except TokenError as error:
        print(f"[check] ERROR {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("[check] 对照 design/tokens.json 核对了：" + ("、".join(report["checked"]) or "没有找到导出产物"))
        for m in report["mismatches"]:
            if m.get("problem") == "missing":
                print(f"[check] 缺 {m['file']}：档案必须有它，别的 AI 工具靠它读设计")
            elif m.get("problem") == "stale":
                print(f"[check] {m['file']} 和按 tokens.json 重新导出的结果不一样：导出后改过 tokens.json 或简报，或者手改过这个文件")
            else:
                print(f"[check] {m['file']} {m['key']}：tokens.json 是 {m['tokens']}，文件里是 {m['file_value']}")
        for warning in report["warnings"]:
            print(f"[check] 提醒：{warning}")
        if report["mismatches"]:
            print("[check] FAIL 档案和 tokens.json 对不上。改 tokens.json 后重新导出，不要手改导出产物。在产品目录下运行：")
            print(f"  {report['fix']}")
        else:
            print("[check] PASS 档案与 tokens.json 一致")
    return 1 if report["mismatches"] else 0


# ---------- extract ----------

def cmd_extract(args) -> int:
    root = Path(args.dir).expanduser().resolve()
    if not root.is_dir():
        print(f"[extract] ERROR 不是目录：{root}", file=sys.stderr)
        return 2
    colors: Counter = Counter()
    color_files: Dict[str, set] = {}
    fonts: Counter = Counter()
    radius: Counter = Counter()
    spacing: Counter = Counter()
    variables: Dict[str, str] = {}
    scanned = 0
    for path in walk(root):
        if path.suffix not in CODE_SUFFIXES:
            continue
        text = read_text(path)
        if not text:
            continue
        scanned += 1
        for _, rgba, _ in iter_colors(text, include_named=False):
            key = to_hex(rgba) + ("" if rgba[3] >= 1 else f"/{rgba[3]:.2f}")
            colors[key] += 1
            color_files.setdefault(key, set()).add(str(path.relative_to(root)))
        for m in re.finditer(r"font-family\s*:\s*([^;{}\n]+)", text):
            fonts[m.group(1).strip()] += 1
        for m in re.finditer(r"fontFamily\s*[:=]\s*[\[{]?\s*['\"]([^'\"\n]+)['\"]", text):
            fonts[m.group(1).strip()] += 1
        for m in re.finditer(r"\.custom\(\s*\"([^\"]+)\"", text):
            fonts[m.group(1).strip()] += 1
        for m in re.finditer(r"border-radius\s*:\s*([\d.]+)px|borderRadius\s*[:=]\s*['\"]?([\d.]+)", text):
            radius[float(m.group(1) or m.group(2))] += 1
        for m in re.finditer(r"\b(?:padding|margin|gap|row-gap|column-gap)(?:-[a-z]+)?\s*:\s*([^;{}\n]+)", text):
            for n in re.findall(r"([\d.]+)px", m.group(1)):
                spacing[float(n)] += 1
        if path.suffix in CSSISH:
            for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;{}\n]+)", text):
                variables.setdefault(name, value.strip())

    def ranked(counter: Counter, limit: int) -> List[dict]:
        return [{"value": (int(v) if isinstance(v, float) and v.is_integer() else v), "count": n}
                for v, n in counter.most_common(limit)]

    color_list = []
    for value, n in colors.most_common(40):
        rgba = parse_hex(value.split("/")[0])
        color_list.append({"value": value, "count": n, "files": len(color_files[value]),
                           "gray": bool(rgba and is_grayish(rgba)), "lightness": round(oklch(rgba)[0], 3) if rgba else None})
    opaque = [c for c in color_list if "/" not in c["value"]]
    grays = sorted([c for c in opaque if c["gray"]], key=lambda c: c["lightness"])
    chroma = [c for c in opaque if not c["gray"]]
    suggested = {}
    if chroma:
        suggested["accent"] = chroma[0]["value"]
    if grays:
        suggested["text"] = grays[0]["value"]
        suggested["bg"] = grays[-1]["value"]
        if len(grays) >= 3:
            suggested["text_muted"] = grays[1]["value"]
            suggested["border"] = grays[-2]["value"]
    warnings = []
    distinct_chroma = sum(1 for v in colors if "/" not in v and not is_grayish(parse_hex(v)))
    if distinct_chroma > 12:
        warnings.append(f"代码里有 {distinct_chroma} 种不同的彩色；补档前先和用户确认哪些是品牌色，其余收敛到状态色或删掉")
    if len(radius) > 5:
        warnings.append(f"圆角有 {len(radius)} 种取值；收敛到 3 到 4 档")
    draft = {
        "meta": {"name": f"{root.name}（补档草稿）", "generated_by": "style-compass design_memory.py extract",
                 "note": "盘点结果，不是定稿。把高频值映射到角色、补齐 typography 和 locale 后另存为 design/tokens.json，再让用户在渲染页上确认。"},
        "suggested_color": suggested,
        "inventory": {
            "files_scanned": scanned,
            "ui_libraries": code_signals(root)["libraries"],
            "colors": color_list,
            "fonts": ranked(fonts, 10),
            "radius_px": ranked(radius, 10),
            "spacing_px": ranked(spacing, 15),
            "css_variables": [{"name": k, "value": v} for k, v in list(variables.items())[:60]],
        },
        "warnings": warnings,
    }
    text = json.dumps(draft, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"[extract] 扫描 {scanned} 个文件，草稿写入 {out}")
        print(f"[extract] 高频颜色：" + "、".join(f"{c['value']}×{c['count']}" for c in color_list[:6]))
        for w in warnings:
            print(f"[extract] 提醒：{w}")
    else:
        sys.stdout.write(text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="style-compass 设计档案与口味记录")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="找档案和设计信号，给出建议路线")
    scan.add_argument("dir")
    scan.add_argument("--taste", help="口味记录文件路径")
    scan.add_argument("--json", action="store_true")
    rec = sub.add_parser("record", help="追加一条决策")
    rec.add_argument("dir")
    rec.add_argument("--chosen", required=True, help="选中的方向，例如 calm-tech/冷静表格")
    rec.add_argument("--offered", help="给过的候选，逗号分隔")
    rec.add_argument("--rejected", action="append", help="否掉的候选和理由，例如 \"editorial（太像杂志）\"，可多次")
    rec.add_argument("--words", help="用户选的感受词，逗号分隔")
    rec.add_argument("--stage", help="在哪一关做的决定")
    rec.add_argument("--note", help="备注")
    rec.add_argument("--product", help="产品名，默认用目录名")
    rec.add_argument("--date", help="日期 YYYY-MM-DD，默认今天")
    rec.add_argument("--taste", help="口味记录文件路径")
    rec.add_argument("--no-taste", action="store_true", help="只写产品决策，不写个人口味记录")
    rec.add_argument("--remember-taste", action="store_true",
                     help="用户同意在本机记口味时加这个；第一次写口味记录必须有它")
    chk = sub.add_parser("check", help="档案是否与 tokens.json 一致")
    chk.add_argument("dir")
    chk.add_argument("--json", action="store_true")
    ext = sub.add_parser("extract", help="从已有代码盘点设计值")
    ext.add_argument("dir")
    ext.add_argument("--out", help="草稿输出路径，不传则打印到标准输出")
    tst = sub.add_parser("taste", help="汇总口味记录")
    tst.add_argument("--taste", help="口味记录文件路径")
    tst.add_argument("--recent", type=int, default=3, help="新颖度提醒看最近几次，默认 3")
    tst.add_argument("--json", action="store_true")
    switch = tst.add_mutually_exclusive_group()
    switch.add_argument("--off", action="store_true", help="用户不让记：关闭口味记录，以后不再问")
    switch.add_argument("--on", action="store_true", help="重新开启口味记录")
    args = parser.parse_args()
    handlers = {"scan": cmd_scan, "record": cmd_record, "check": cmd_check, "extract": cmd_extract, "taste": cmd_taste}
    try:
        return handlers[args.command](args)
    except TokenError as error:
        print(f"[archive] ERROR {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
