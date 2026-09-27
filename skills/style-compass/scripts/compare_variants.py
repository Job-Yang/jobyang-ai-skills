#!/usr/bin/env python3
"""
compare_variants.py — 把模型自由渲染的多个 HTML 变体,并排装订成一页对比页,供截图评审。

为什么不是"套模板":
  Token 只能约束一致性，不能完整表达构图、密度、层次和动效。
  所以渲染质量必须归模型——每个变体都是模型针对某个 archetype 独立、完整写出的 HTML。
  这个脚本只做脚手架:把这些独立 HTML 用 iframe 并排装订 + 标注来源,方便一眼对比和截图。

零第三方依赖(仅标准库)。

用法:
  # 每个变体一个独立 html 文件,文件名或 --labels 指明它是哪个风格
  python3 compare_variants.py a.html b.html c.html --labels "克制工程感,温暖清爽,极简禅意" -o compare.html
  # 或直接读目录下所有 *.html(排除自己的输出)
  python3 compare_variants.py --dir ./variants -o compare.html
"""
import argparse
import glob
import os


def build(items):
    """items: list of (label, abs_path)"""
    cols = []
    for label, path in items:
        # 用 file:// 绝对路径塞进 iframe;截图时本地起 http server 也能用相对路径
        src = os.path.basename(path)
        cols.append(f"""
    <div class="col">
      <div class="col-label">{label}</div>
      <iframe class="frame" src="{src}" loading="lazy"></iframe>
    </div>""")
    joined = "\n".join(cols)
    n = len(items)
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Style Compass — 变体对比</title>
<style>
  body {{ margin:0; padding:24px; background:#e9eaec; font-family:system-ui; }}
  h1 {{ font-size:18px; margin:0 0 4px; }}
  .hint {{ color:#666; font-size:13px; margin-bottom:20px; }}
  /* 上下堆叠:宽幅页面不缩水,一版一版纵向看,不用左右滚 */
  .stack {{ display:flex; flex-direction:column; gap:32px; }}
  .col {{ display:flex; flex-direction:column; }}
  .col-label {{ font-size:15px; font-weight:600; margin-bottom:10px;
                position:sticky; top:0; background:#e9eaec; padding:6px 0; z-index:1; }}
  .frame {{ width:100%; height:760px; border:1px solid #ccc; border-radius:8px;
            background:#fff; }}
</style></head>
<body>
  <h1>变体对比 · 每一版都是模型针对该风格独立渲染的成品</h1>
  <div class="hint">纵向逐版对比(宽幅不缩水)。选你最顺眼的一版,或说"要第 2 个""融合 1 和 3 的某处"。内容一致,只比风格与手艺。</div>
  <div class="stack">{joined}
  </div>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("variants", nargs="*", help="各变体的 html 文件")
    ap.add_argument("--dir", help="改为读取该目录下所有 *.html(排除输出文件)")
    ap.add_argument("--labels", help="逗号分隔的标签,顺序对应各变体;省略则用文件名")
    ap.add_argument("-o", "--out", default="compare.html", help="输出对比页路径")
    args = ap.parse_args()

    paths = args.variants
    out_base = os.path.basename(args.out)
    if args.dir:
        paths = [p for p in sorted(glob.glob(os.path.join(args.dir, "*.html")))
                 if os.path.basename(p) != out_base]
    if not paths:
        ap.error("至少给一个变体 html,或用 --dir")

    labels = None
    if args.labels:
        labels = [x.strip() for x in args.labels.split(",")]
        if len(labels) != len(paths):
            ap.error(f"--labels 数量({len(labels)})与变体数量({len(paths)})不一致")

    items = []
    for i, p in enumerate(paths):
        label = labels[i] if labels else os.path.splitext(os.path.basename(p))[0]
        items.append((label, os.path.abspath(p)))

    # 对比页必须和各变体 html 放在同一目录(iframe 用相对文件名),这里做个校验提醒
    out_dir = os.path.dirname(os.path.abspath(args.out))
    for label, p in items:
        if os.path.dirname(p) != out_dir:
            print(f"⚠️ 提醒:变体 {p} 与输出目录 {out_dir} 不同目录,"
                  f"iframe 可能加载不到。建议把变体和 compare.html 放同一目录。")

    html = build(items)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已生成对比页: {args.out}  (含 {len(items)} 个变体)")
    print("提示:本地起 http server 后用浏览器打开截图评审,例如:")
    print(f"  cd {out_dir} && python3 -m http.server 8799  →  http://127.0.0.1:8799/{out_base}")


if __name__ == "__main__":
    main()
