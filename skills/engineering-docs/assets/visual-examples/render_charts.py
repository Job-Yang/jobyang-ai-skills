#!/usr/bin/env python3
"""Render nine synthetic statistical examples with Matplotlib, preserving data.

Optional example dependency: matplotlib and numpy. These are not required for
the documentation skill or its metadata validator.
"""
import argparse
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager, ticker
from matplotlib.colors import Normalize, LinearSegmentedColormap
from matplotlib.patches import Rectangle
import numpy as np

THEME = json.loads(Path(__file__).with_name("theme.json").read_text())
INK, MUTED = THEME["ink"], THEME["muted"]
BLUE, TEAL, PURPLE, AMBER = [THEME["colors"][c][0] for c in ("blue", "teal", "purple", "amber")]
GRID = THEME["grid"]
FONT_CANDIDATES = ["PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei",
                   "Arial Unicode MS", "Heiti TC", "DejaVu Sans"]


def configure():
    available = {f.name for f in font_manager.fontManager.ttflist}
    font = next((name for name in FONT_CANDIDATES if name in available), "DejaVu Sans")
    matplotlib.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": [font, "DejaVu Sans"],
        "font.size": 10.5, "text.color": INK, "axes.labelcolor": MUTED,
        "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": "#9DAABB",
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "svg.fonttype": "none", "svg.hashsalt": "engineering-docs-examples",
        "axes.unicode_minus": False, "axes.linewidth": .6,
        "lines.solid_capstyle": "round", "lines.solid_joinstyle": "round",
        "lines.dash_capstyle": "round", "lines.dash_joinstyle": "round",
    })
    return font


def base(number, kind, title, subtitle, note):
    fig = plt.figure(figsize=(6.8, 5.2), dpi=100, facecolor="white")
    fig.text(.047, .94, f"{number}  /  {kind} · 合成数据", size=9.5, color=MUTED)
    fig.text(.047, .858, title, size=18, weight="bold")
    fig.text(.047, .800, subtitle, size=10.2, color=MUTED)
    fig.add_artist(plt.Line2D([.047, .953], [.106, .106], transform=fig.transFigure,
                             color=GRID, linewidth=.6))
    fig.text(.047, .052, note, size=9.1, color=MUTED)
    ax = fig.add_axes([.14, .20, .79, .51])
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=.6)
    ax.tick_params(length=0, pad=7)
    return fig, ax


def horizontal_unit(ax, text):
    """Keep units close to the scale without rotating the reader's head."""
    ax.set_ylabel("")
    ax.text(0, 1.05, text, transform=ax.transAxes, color=MUTED, fontsize=9.5)


def direct_label(ax, text, xy, xytext, color, **kwargs):
    return ax.annotate(text, xy, xytext=xytext, color=color, fontsize=10,
                       va="center", bbox={"facecolor": "white", "edgecolor": "none", "pad": 2},
                       arrowprops={"arrowstyle": "-", "color": color, "lw": .8},
                       **kwargs)


def save(fig, out, key, title, note, kind):
    fig.savefig(out / f"{key}.png", dpi=200)
    fig.savefig(out / f"{key}.svg", metadata={"Date": None})
    path = out / f"{key}.svg"
    svg = path.read_text()
    root_end = svg.index(">", svg.index("<svg"))
    svg = (svg[:root_end+1] + f"<title>{html.escape(title)}</title>"
           f"<desc>{html.escape(note)}</desc>" + svg[root_end+1:])
    path.write_text(svg)
    plt.close(fig)
    return {"id": key, "type": kind, "title": title, "conclusion": note,
            "source": f"{key}.svg", "preview": f"{key}.png"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    font = configure()
    data = json.loads(Path(__file__).with_name("chart-data.json").read_text())
    manifests, stats = [], {"synthetic": True}

    def finish(fig, key, title, note, kind):
        manifests.append(save(fig, out, key, title, note, kind))

    t = data["trend"]
    title = "变更后延迟下降，缺测仍保留"
    note = "样例数据｜1 分钟 P95，UTC；缺测不补零，时间相邻不证明因果。"
    fig, ax = base("13", "趋势图", title, "P95 延迟（ms）｜10:00–10:09", note)
    y = np.array([np.nan if v is None else v for v in t["p95"]])
    x = np.arange(len(y))
    ax.axvspan(t["event_index"] - .18, t["event_index"] + .18,
               color=THEME["colors"]["amber"][1], zorder=0)
    ax.plot(x, y, color=BLUE, marker="o", linewidth=1.8, markersize=3.6,
            solid_capstyle="round", solid_joinstyle="round", antialiased=True)
    ax.axvline(t["event_index"], color=AMBER, linestyle="--", linewidth=1.2)
    ax.text(t["event_index"] + .2, 250, t["event"] + " / 缺测",
            color=AMBER, fontsize=10)
    direct_label(ax, f"{y[-1]:.0f} ms", (x[-1], y[-1]),
                 (x[-1] - 1.2, y[-1] - 42), BLUE)
    ax.set(ylim=(0, 280), xlim=(-.3, 9.6), yticks=[0, 100, 200])
    horizontal_unit(ax, "P95 延迟 · ms")
    ax.set_xticks([0, 2, 4, 6, 8], [t["time"][i] for i in [0, 2, 4, 6, 8]])
    finish(fig, "13-trend", title, note, "折线图")

    c = data["comparison"]
    title = "规则检查贡献最大的耗时差"
    note = "独立合成测量｜同一示例输入；这是点估计，没有置信区间。"
    fig, ax = base("14", "哑铃比较", title, "空心圆：基线    实心圆：候选    单位：ms", note)
    ax.grid(False)
    ax.grid(axis="x", color=GRID, linewidth=.6)
    differences = np.asarray(c["baseline"]) - np.asarray(c["candidate"])
    focus = int(np.argmax(differences))
    ax.axhspan(focus - .42, focus + .42, color=THEME["colors"]["teal"][1], zorder=0)
    for i, (old, new) in enumerate(zip(c["baseline"], c["candidate"])):
        ax.plot([new, old], [i, i], color=TEAL if i == focus else "#B1BDCA",
                linewidth=2 if i == focus else 1.2, zorder=1)
        ax.scatter([old], [i], color="white", edgecolor=BLUE, s=65, linewidth=1.6, zorder=2)
        ax.scatter([new], [i], color=TEAL, s=65, zorder=3)
        ax.text(old + 3, i + .06, str(old), fontsize=10, color=BLUE)
        ax.text(new - 3, i + .06, str(new), fontsize=10, color=TEAL, ha="right")
        ax.text(113, i + .06, f"{new-old:+} ms", fontsize=10,
                color=TEAL if i == focus else MUTED, ha="right",
                weight="bold" if i == focus else "normal")
    ax.set_yticks(range(4), c["labels"])
    ax.set(xlim=(0, 116), ylim=(3.6, -.6), xlabel="耗时（ms）", xticks=[0, 25, 50, 75, 100])
    ax.text(113, -.65, "变化", ha="right", fontsize=9.5, color=MUTED)
    ax.spines["left"].set_visible(False)
    finish(fig, "14-comparison", title, note, "哑铃图")

    old = np.asarray(data["latency_ms"]["baseline"], dtype=float)
    new = np.asarray(data["latency_ms"]["candidate"], dtype=float)
    bins = np.arange(0, 401, 50)
    title = "集中区间之外，仍存在长尾"
    note = "合成延迟样本｜每组 n=40；共同 bin 宽度 50ms，全部样本均保留。"
    fig, ax = base("15", "直方图", title, "同一组边界比较计数，空心与实心柱区分类别", note)
    counts_old, _ = np.histogram(old, bins)
    counts_new, _ = np.histogram(new, bins)
    # Adjacent bars share identical bin boundaries; group width is visual offset.
    centers = (bins[:-1] + bins[1:]) / 2
    ax.bar(centers - 10, counts_old, width=19, facecolor="white", edgecolor=BLUE,
           linewidth=1.4, label="基线")
    ax.bar(centers + 10, counts_new, width=19, color=THEME["colors"]["teal"][1],
           edgecolor=TEAL, linewidth=1.2, label="候选")
    ax.set(xlim=(0, 400), xlabel="延迟（ms）", ylabel="请求数")
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.legend(frameon=False, loc="upper right", ncol=2, handlelength=1.2,
              columnspacing=1.2)
    horizontal_unit(ax, "请求数")
    ax.spines["bottom"].set_color("#7A8797")
    stats["histogram"] = {"bins": bins.tolist(), "baseline": counts_old.tolist(),
                          "candidate": counts_new.tolist()}
    finish(fig, "15-histogram", title, note, "直方图")

    threshold = 150
    old_pct, new_pct = np.mean(old <= threshold), np.mean(new <= threshold)
    title = f"150ms 内的比例为 {old_pct:.0%} 与 {new_pct:.1%}"
    note = "同一组延迟样本｜F(x)=样本中不超过 x 的比例；阶梯不做平滑。"
    fig, ax = base("16", "ECDF", title, "基线：虚线    候选：实线    每组 n=40", note)
    for values, color, style in [(old, BLUE, "--"), (new, TEAL, "-")]:
        ordered = np.sort(values)
        # Step-post makes F(x) right-continuous, including repeated observations.
        ax.step(np.r_[0, ordered, 370], np.r_[0, np.arange(1, len(values)+1)/len(values), 1],
                where="post", color=color, linestyle=style, linewidth=1.6,
                solid_capstyle="round", solid_joinstyle="round",
                dash_capstyle="round", dash_joinstyle="round", antialiased=True)
    ax.axvline(threshold, color=AMBER, linewidth=1.2, linestyle=":")
    ax.scatter([threshold, threshold], [old_pct, new_pct], color=[BLUE, TEAL], s=40)
    direct_label(ax, f"候选  {new_pct:.1%}", (threshold, new_pct),
                 (205, .83), TEAL)
    direct_label(ax, f"基线  {old_pct:.0%}", (threshold, old_pct),
                 (205, .62), BLUE)
    ax.text(150, .05, "150 ms", ha="center", color=AMBER, fontsize=10,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 2})
    ax.set(xlim=(0, 370), ylim=(0, 1.05), xlabel="延迟（ms）", ylabel="累计比例")
    horizontal_unit(ax, "累计比例")
    ax.set_yticks([0, .25, .5, .75, 1])
    ax.yaxis.set_major_formatter(ticker.PercentFormatter(1))
    stats["ecdf"] = {"threshold": threshold, "baseline": float(old_pct), "candidate": float(new_pct)}
    finish(fig, "16-ecdf", title, note, "ECDF")

    title = "候选的中位数更低，尾部仍需观察"
    note = "同一组延迟样本｜箱体 Q1–Q3；须为 1.5 IQR 内最远观测值；每组 n=40。"
    fig, ax = base("17", "箱线图", title, "圆点展示全部观测值；两组共用延迟尺度", note)
    box = ax.boxplot([old, new], positions=[1, 2], widths=.4, patch_artist=True,
                     whis=1.5, showfliers=False, vert=False,
                     medianprops={"color": INK, "linewidth": 1.5},
                     whiskerprops={"color": MUTED, "linewidth": 1},
                     capprops={"color": MUTED, "linewidth": 1})
    for i, (values, patch, color) in enumerate(zip([old, new], box["boxes"], [BLUE, TEAL]), 1):
        patch.set_facecolor(color + "22")
        patch.set_edgecolor(color)
        jitter = np.random.default_rng(40 + i).uniform(-.1, .1, len(values))
        ax.scatter(values, i + jitter, color=color, s=12, alpha=.6, zorder=3)
        q1, median, q3 = np.percentile(values, [25, 50, 75], method="linear")
        ax.text(median, i - .32, f"中位数 {median:.0f} ms",
                va="center", ha="center", color=color, weight="bold", fontsize=10)
        stats[f"box_{i}"] = {"q1": float(q1), "median": float(median), "q3": float(q3)}
    ax.set_yticks([1, 2], ["基线", "候选"])
    ax.set(xlim=(0, 370), ylim=(2.65, .4), xlabel="延迟（ms）")
    ax.grid(False)
    ax.grid(axis="x", color=GRID, linewidth=.6)
    finish(fig, "17-boxplot", title, note, "箱线图")

    s = data["scatter"]
    title = "输入更大时，耗时通常也更高"
    note = "独立合成样本 n=12｜每点为一次任务；共变关系不能证明因果。"
    fig, ax = base("18", "散点图", title, "输入大小与任务耗时｜保留全部点，不连接无序观测", note)
    ax.scatter(s["payload"], s["duration"], s=65, color=BLUE, edgecolor="white", linewidth=.7)
    ax.set(xlim=(0, 130), ylim=(0, 115), xlabel="输入大小（KiB）", ylabel="耗时（ms）")
    horizontal_unit(ax, "任务耗时 · ms")
    ax.annotate("120 KiB / 99ms", (120, 99), xytext=(57, 102), color=BLUE,
                arrowprops={"arrowstyle": "-", "color": BLUE}, fontsize=10)
    finish(fig, "18-scatter", title, note, "散点图")

    h = data["heatmap"]
    title = "区域 B 在中段出现更高利用率"
    note = "独立合成数据｜5 分钟均值；全图共享 0–100% 色标，NA 表示缺测。"
    fig, ax = base("19", "热力图", title, "计算资源利用率（%）｜09:00–09:25 UTC", note)
    ax.set_position([.14, .30, .79, .40])
    values = np.array([[np.nan if v is None else v for v in row] for row in h["values"]])
    cmap = LinearSegmentedColormap.from_list(
        "document_blue", [THEME["colors"]["blue"][1], "#B8C9E8", BLUE, "#243C70"])
    cmap.set_bad("#E3E8EF")
    # Vector cells keep the exported SVG editable; imshow embeds a bitmap.
    im = ax.pcolormesh(np.ma.masked_invalid(values), cmap=cmap,
                       norm=Normalize(0, 100), shading="flat", rasterized=False,
                       edgecolors="white", linewidth=2)
    ax.invert_yaxis()
    for r in range(4):
        for col in range(6):
            value = values[r, col]
            rgba = cmap(im.norm(value)) if not np.isnan(value) else (0.89, 0.91, 0.94, 1)
            # Choose the higher WCAG contrast text color for each cell.
            rgb = np.array(rgba[:3])
            linear = np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)
            lum = float(linear @ np.array([.2126, .7152, .0722]))
            color = "#000000" if (lum+.05)/.05 >= 1.05/(lum+.05) else "#FFFFFF"
            ax.text(col + .5, r + .5, "NA" if np.isnan(value) else f"{value:.0f}",
                    ha="center", va="center", color=color, fontsize=10.5)
    ax.set_xticks(np.arange(6) + .5, h["columns"])
    ax.xaxis.tick_top()
    ax.set_yticks(np.arange(4) + .5, h["rows"])
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    bar_ax = fig.add_axes([.56, .19, .37, .025])
    colorbar = fig.colorbar(im, cax=bar_ax, ticks=[0, 50, 100], orientation="horizontal")
    colorbar.solids.set_rasterized(False)
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(length=0, labelsize=9)
    peak_row, peak_col = np.unravel_index(np.nanargmax(values), values.shape)
    ax.add_patch(Rectangle((peak_col, peak_row), 1, 1, fill=False,
                           edgecolor=INK, linewidth=1.2))
    fig.text(.14, .205, f"边框：最高 {np.nanmax(values):.0f}%   NA：缺测",
             fontsize=9.5, color=MUTED)
    finish(fig, "19-heatmap", title, note, "热力图")

    comp = data["composition"]
    totals = np.sum(comp["values"], axis=1)
    title = f"总量从 {totals[0]} 降至 {totals[1]} MiB"
    note = "独立合成数据｜类别互斥，堆叠长度为绝对量；段内直接标值。"
    fig, ax = base("20", "组成图", title, "左→右：代码 / 资源 / 运行库｜以相同尺度比较", note)
    bottom = np.zeros(2)
    for i, tone in enumerate(["blue", "teal", "purple"]):
        color, fill = THEME["colors"][tone]
        vals = np.array(comp["values"])[:, i]
        ax.barh([0, 1], vals, height=.45, left=bottom, color=fill,
                edgecolor=color, linewidth=1.0)
        for j, val in enumerate(vals):
            ax.text(bottom[j] + val/2, j, f"{comp['components'][i]}\n{val}",
                    color=INK, ha="center", va="center", fontsize=10)
        bottom += vals
    for i, total in enumerate(totals):
        ax.text(total + 2, i, f"{total} MiB", va="center", weight="bold", fontsize=10)
    ax.set_yticks([0, 1], comp["groups"])
    ax.set(xlim=(0, 119), ylim=(1.65, -.6), xlabel="MiB", xticks=[0, 25, 50, 75, 100])
    ax.grid(False)
    ax.grid(axis="x", color=GRID, linewidth=.6)
    stats["composition_totals"] = totals.tolist()
    finish(fig, "20-composition", title, note, "堆叠条形图")

    w = data["waterfall"]
    assert w["start"] + sum(w["deltas"]) == w["end"]
    title = "三个增减项解释净减少 25 MiB"
    note = "独立合成数据｜100 − 20 − 8 + 3 = 75 MiB；负值减少，正值增加。"
    fig, ax = base("21", "瀑布图", title, "初值、增减项与终值使用同一单位", note)
    ax.bar(0, w["start"], color=THEME["colors"]["blue"][1], edgecolor=BLUE, width=.55)
    running = w["start"]
    ax.text(0, running + 3, str(running), ha="center", weight="bold")
    for i, delta in enumerate(w["deltas"], 1):
        target = running + delta
        color = TEAL if delta < 0 else AMBER
        ax.plot([i - 1 + .275, i - .275], [running, running], color=MUTED,
                linewidth=1, linestyle=":")
        fill = THEME["colors"]["teal" if delta < 0 else "amber"][1]
        ax.bar(i, abs(delta), bottom=min(running, target), color=fill, edgecolor=color, width=.55)
        ax.text(i, max(running, target) + 3, f"{delta:+}", ha="center", color=color, weight="bold")
        running = target
    ax.plot([3.275, 3.725], [running, running], color=MUTED, linewidth=1, linestyle=":")
    ax.bar(4, w["end"], color=THEME["colors"]["blue"][1], edgecolor=BLUE, width=.55)
    ax.text(4, w["end"] + 3, str(w["end"]), ha="center", weight="bold")
    ax.set_xticks(range(5), ["初值", *w["labels"], "终值"])
    ax.set(ylim=(0, 120), ylabel="MiB")
    horizontal_unit(ax, "包体积 · MiB")
    stats["waterfall_end"] = running
    finish(fig, "21-waterfall", title, note, "瀑布图")

    (out / "charts.json").write_text(json.dumps(manifests, ensure_ascii=False, indent=2))
    (out / "chart-statistics.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2))
    (out / "renderer.json").write_text(json.dumps({
        "matplotlib": matplotlib.__version__, "numpy": np.__version__, "font": font,
        "png_width": 1360, "reading_width": 680, "quantile_method": "linear",
        "data_kind": data["kind"],
    }, ensure_ascii=False, indent=2))
    print(f"Rendered {len(manifests)} chart examples in {out}; font={font}")


if __name__ == "__main__":
    main()
