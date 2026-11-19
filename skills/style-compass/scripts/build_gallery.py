#!/usr/bin/env python3
"""build_gallery.py：生成轻量高定多方案切换/并排画廊，不引入重型评审外壳。

用法：
  python3 scripts/build_gallery.py --out <dir/gallery.html> \
    --item "方案名|流派标签|一句话亮点|variant-a.html" \
    [--item ...] [--title "视觉与动效方案对比"] [--allow-cross-dir]
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path
from typing import List, Tuple


def parse_item(raw: str, index: int) -> Tuple[str, str, str, str]:
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 2:
        raise ValueError(f"--item 格式应为 '名字|流派|亮点|页面路径' 或 '名字|页面路径'：{raw!r}")
    if len(parts) == 2:
        name, href = parts
        return name, f"方案 {chr(65 + index)}", "", href
    if len(parts) == 3:
        name, style, href = parts
        return name, style, "", href
    name, style, note = parts[0], parts[1], parts[2]
    href = "|".join(parts[3:]).strip()
    return name, style, note, href


def safe_rel_href(href: str, out_dir: Path, allow_cross_dir: bool) -> str:
    if href.startswith(("http://", "https://", "data:")):
        raise ValueError(f"画廊只接受本地相对页面，不支持外链：{href}")
    target = (out_dir / href).resolve()
    if not allow_cross_dir:
        try:
            rel = target.relative_to(out_dir.resolve())
        except ValueError as exc:
            raise ValueError(
                f"文件 {href} 不在输出目录 {out_dir} 内（独立交接后 iframe 会空白）；"
                "把候选放进同一目录，或确认后果后加 --allow-cross-dir"
            ) from exc
        return rel.as_posix()
    return Path(os.path.relpath(target, out_dir.resolve())).as_posix()


def build_html(title: str, items: List[dict]) -> str:
    escaped_title = html.escape(title)
    payload_json = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    :root {{
      --g-bg: #0D0F14;
      --g-bar: rgba(20, 23, 30, 0.92);
      --g-surface: #171B24;
      --g-border: rgba(255, 255, 255, 0.1);
      --g-ink: #F4F5F7;
      --g-muted: #9BA3B4;
      --g-accent: #10B981;
      --g-font: 'SF Pro Text', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans SC', sans-serif;
      --g-ease: cubic-bezier(0.22, 1, 0.36, 1);
      --g-spring: linear(
        0, 0.0677, 0.2181, 0.3941, 0.5621, 0.7053, 0.8177, 0.8999,
        0.9559, 0.9912, 1.011, 1.02, 1.023, 1.021, 1.018, 1.014,
        1.01, 1.007, 1.004, 1.002, 1
      );
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: var(--g-bg);
      color: var(--g-ink);
      font-family: var(--g-font);
      font-size: 14px;
      line-height: 1.5;
      letter-spacing: 0;
    }}
    button {{
      font: inherit;
      color: inherit;
      cursor: pointer;
    }}
    button:focus-visible {{
      outline: 2px solid var(--g-accent);
      outline-offset: 2px;
    }}
    .shell {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: 54px minmax(0, 1fr);
      width: 100%;
      max-width: 100vw;
      height: 100vh;
      overflow: hidden;
    }}
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 0 16px;
      width: 100%;
      min-width: 0;
      background: var(--g-bar);
      border-bottom: 1px solid var(--g-border);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 0 1 200px;
      min-width: 0;
      overflow: hidden;
      white-space: nowrap;
    }}
    .brand-dot {{
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--g-accent);
      box-shadow: 0 0 10px rgba(16, 185, 129, 0.55);
      flex: none;
    }}
    .brand strong {{
      font-size: 13px;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .tabs {{
      position: relative;
      display: flex;
      align-items: center;
      flex: 1 1 0%;
      min-width: 0;
      gap: 3px;
      padding: 3px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--g-border);
      border-radius: 11px;
      overflow-x: auto;
      scrollbar-width: none;
    }}
    .tabs::-webkit-scrollbar {{
      display: none;
    }}
    .tab-btn {{
      position: relative;
      display: inline-flex;
      align-items: center;
      flex: none;
      gap: 6px;
      height: 30px;
      padding: 0 10px;
      border: 0;
      border-radius: 8px;
      background: transparent;
      color: var(--g-muted);
      font-size: 12.5px;
      white-space: nowrap;
      transition: color 180ms var(--g-ease), background-color 180ms var(--g-ease), transform 320ms var(--g-spring);
    }}
    .tab-btn:hover {{
      color: var(--g-ink);
    }}
    .tab-btn:active {{
      transform: scale(0.97);
    }}
    .tab-btn[aria-selected="true"] {{
      background: rgba(255, 255, 255, 0.11);
      color: var(--g-ink);
      font-weight: 500;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.14);
    }}
    .tab-badge {{
      display: inline-grid;
      place-items: center;
      width: 18px;
      height: 18px;
      border-radius: 5px;
      background: rgba(255, 255, 255, 0.08);
      font-size: 11px;
      font-weight: 600;
    }}
    .tab-btn[aria-selected="true"] .tab-badge {{
      background: var(--g-accent);
      color: #062118;
    }}
    .controls {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex: none;
    }}
    .seg {{
      display: inline-flex;
      padding: 3px;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--g-border);
      gap: 2px;
    }}
    .ctrl-btn {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      height: 28px;
      padding: 0 10px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: var(--g-muted);
      font-size: 12px;
      white-space: nowrap;
      transition: color 160ms var(--g-ease), background-color 160ms var(--g-ease);
    }}
    .ctrl-btn:hover {{
      color: var(--g-ink);
    }}
    .ctrl-btn[aria-pressed="true"] {{
      background: rgba(255, 255, 255, 0.12);
      color: var(--g-ink);
      font-weight: 500;
    }}
    .action-btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      height: 32px;
      padding: 0 11px;
      border-radius: 8px;
      border: 1px solid var(--g-border);
      background: rgba(255, 255, 255, 0.05);
      color: var(--g-ink);
      font-size: 12px;
      transition: background-color 160ms var(--g-ease), transform 140ms var(--g-ease);
    }}
    .action-btn:hover {{
      background: rgba(255, 255, 255, 0.1);
    }}
    .action-btn:active {{
      transform: scale(0.97);
    }}
    .stage {{
      position: relative;
      min-height: 0;
      display: flex;
      align-items: stretch;
      justify-content: center;
      padding: 10px 14px 14px;
      gap: 14px;
      overflow: auto;
    }}
    .stage[data-device="mobile"] .frame-card {{
      width: min(406px, 100%);
      flex: none;
    }}
    .stage[data-layout="single"] .frame-card {{
      flex: 1 1 auto;
      max-width: 100%;
    }}
    .stage[data-layout="single"][data-device="mobile"] .frame-card {{
      flex: none;
      width: min(406px, 100%);
    }}
    .stage[data-layout="split"] {{
      justify-content: flex-start;
    }}
    .stage[data-layout="split"] .frame-card {{
      flex: 1 0 min(420px, 100%);
      min-width: min(420px, 100%);
    }}
    .frame-card {{
      display: flex;
      flex-direction: column;
      min-height: 0;
      background: var(--g-surface);
      border: 1px solid var(--g-border);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.45);
      transition: opacity 220ms var(--g-ease), transform 220ms var(--g-ease);
    }}
    .frame-card[hidden] {{
      display: none;
    }}
    .frame-meta {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 7px 14px;
      border-bottom: 1px solid var(--g-border);
      background: rgba(255, 255, 255, 0.02);
      font-size: 12px;
      flex: none;
    }}
    .frame-meta-left {{
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      flex: 1 1 auto;
    }}
    .frame-meta-left strong {{
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .style-pill {{
      padding: 2px 8px;
      border-radius: 999px;
      background: rgba(16, 185, 129, 0.14);
      color: #6EE7B7;
      font-size: 11px;
      font-weight: 500;
      white-space: nowrap;
    }}
    .frame-note {{
      color: var(--g-muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    iframe {{
      width: 100%;
      flex: 1 1 auto;
      min-height: 0;
      border: 0;
      background: #fff;
    }}
    @media (max-width: 960px) {{
      .topbar {{ padding: 0 10px; gap: 8px; }}
      .brand {{ display: none; }}
      .frame-note {{ display: none; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">
        <span class="brand-dot" aria-hidden="true"></span>
        <strong>{escaped_title}</strong>
      </div>
      <div class="tabs" role="tablist" aria-label="视觉方案切换" data-role="tabs"></div>
      <div class="controls">
        <div class="seg" role="group" aria-label="视图模式">
          <button type="button" class="ctrl-btn" data-layout-opt="single" aria-pressed="true">单看</button>
          <button type="button" class="ctrl-btn" data-layout-opt="split" aria-pressed="false">并排</button>
        </div>
        <div class="seg" role="group" aria-label="视口宽度">
          <button type="button" class="ctrl-btn" data-device-opt="desktop" aria-pressed="true">桌面</button>
          <button type="button" class="ctrl-btn" data-device-opt="mobile" aria-pressed="false">手机</button>
        </div>
        <button type="button" class="action-btn" data-action="replay" aria-label="重播当前方案动效">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>
          </svg>
          <span>重播动效</span>
        </button>
      </div>
    </header>
    <section class="stage" data-role="stage" data-layout="single" data-device="desktop"></section>
  </main>
  <script>
    const ITEMS = {payload_json};
    const tabsEl = document.querySelector('[data-role="tabs"]');
    const stageEl = document.querySelector('[data-role="stage"]');
    let activeIdx = 0;
    let layoutMode = 'single';

    function esc(text) {{
      return String(text ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }}

    function render() {{
      tabsEl.innerHTML = '';
      stageEl.innerHTML = '';
      ITEMS.forEach((item, idx) => {{
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'tab-btn';
        btn.setAttribute('role', 'tab');
        btn.setAttribute('aria-selected', idx === activeIdx ? 'true' : 'false');
        btn.innerHTML = `<span class="tab-badge">${{esc(item.code)}}</span><span>${{esc(item.name)}}</span>`;
        btn.addEventListener('click', () => {{
          activeIdx = idx;
          if (layoutMode !== 'single') {{
            layoutMode = 'single';
            syncControls();
          }}
          updateVisibility();
        }});
        tabsEl.appendChild(btn);

        const card = document.createElement('section');
        card.className = 'frame-card';
        card.dataset.index = String(idx);
        card.innerHTML = `
          <header class="frame-meta">
            <div class="frame-meta-left">
              <span class="style-pill">${{esc(item.style)}}</span>
              <strong>${{esc(item.name)}}</strong>
            </div>
            <span class="frame-note">${{esc(item.note || '')}}</span>
          </header>
          <iframe src="${{esc(item.href)}}" title="${{esc(item.name)}} 交互预览"></iframe>
        `;
        stageEl.appendChild(card);
      }});
      updateVisibility();
    }}

    function updateVisibility() {{
      const buttons = tabsEl.querySelectorAll('.tab-btn');
      buttons.forEach((btn, idx) => {{
        const selected = idx === activeIdx;
        btn.setAttribute('aria-selected', selected ? 'true' : 'false');
        if (selected && typeof btn.scrollIntoView === 'function') {{
          btn.scrollIntoView({{ inline: 'nearest', block: 'nearest', behavior: 'smooth' }});
        }}
      }});
      stageEl.dataset.layout = layoutMode;
      const cards = stageEl.querySelectorAll('.frame-card');
      cards.forEach((card, idx) => {{
        if (layoutMode === 'single') {{
          card.hidden = idx !== activeIdx;
        }} else {{
          card.hidden = false;
        }}
      }});
    }}

    document.addEventListener('keydown', (e) => {{
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const tag = (document.activeElement?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      if (e.key === 'ArrowRight') {{
        activeIdx = (activeIdx + 1) % ITEMS.length;
        if (layoutMode !== 'single') {{
          layoutMode = 'single';
          syncControls();
        }}
        updateVisibility();
      }} else if (e.key === 'ArrowLeft') {{
        activeIdx = (activeIdx - 1 + ITEMS.length) % ITEMS.length;
        if (layoutMode !== 'single') {{
          layoutMode = 'single';
          syncControls();
        }}
        updateVisibility();
      }} else if (e.key >= '1' && e.key <= '9') {{
        const nextIdx = Number(e.key) - 1;
        if (nextIdx < ITEMS.length) {{
          activeIdx = nextIdx;
          if (layoutMode !== 'single') {{
            layoutMode = 'single';
            syncControls();
          }}
          updateVisibility();
        }}
      }}
    }});

    function syncControls() {{
      document.querySelectorAll('[data-layout-opt]').forEach((btn) => {{
        btn.setAttribute('aria-pressed', btn.dataset.layoutOpt === layoutMode ? 'true' : 'false');
      }});
    }}

    document.querySelectorAll('[data-layout-opt]').forEach((btn) => {{
      btn.addEventListener('click', () => {{
        layoutMode = btn.dataset.layoutOpt;
        syncControls();
        updateVisibility();
      }});
    }});

    document.querySelectorAll('[data-device-opt]').forEach((btn) => {{
      btn.addEventListener('click', () => {{
        stageEl.dataset.device = btn.dataset.deviceOpt;
        document.querySelectorAll('[data-device-opt]').forEach((b) => {{
          b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
        }});
      }});
    }});

    document.querySelector('[data-action="replay"]').addEventListener('click', () => {{
      const selector = layoutMode === 'single'
        ? `.frame-card[data-index="${{activeIdx}}"] iframe`
        : '.frame-card iframe';
      stageEl.querySelectorAll(selector).forEach((frame) => {{
        const src = frame.getAttribute('src');
        frame.setAttribute('src', src);
      }});
    }});

    render();
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="生成高定多方案快速对比画廊")
    parser.add_argument("--out", required=True, help="输出画廊 HTML 路径")
    parser.add_argument("--item", action="append", required=True, help="格式：'方案名|流派|亮点|page.html'")
    parser.add_argument("--title", default="视觉与动效方案对比", help="画廊标题")
    parser.add_argument("--allow-cross-dir", action="store_true", help="允许引用输出目录之外的页面")
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(args.item) < 2 or len(args.item) > 12:
        print("[gallery] ERROR 候选数量建议在 2 到 12 个之间", file=sys.stderr)
        return 2

    items = []
    try:
        for idx, raw in enumerate(args.item):
            name, style, note, raw_href = parse_item(raw, idx)
            rel_href = safe_rel_href(raw_href, out_path.parent, args.allow_cross_dir)
            items.append({
                "code": chr(65 + idx),
                "name": name,
                "style": style,
                "note": note,
                "href": rel_href,
            })
    except ValueError as err:
        print(f"[gallery] ERROR {err}", file=sys.stderr)
        return 2

    out_path.write_text(build_html(args.title, items), encoding="utf-8")
    print(f"[gallery] 生成 {out_path}（{len(items)} 个可交互方案）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
