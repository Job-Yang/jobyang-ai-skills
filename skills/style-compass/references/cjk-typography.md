# 中文界面排版

中文产品的页面，最常见的问题不是配色，而是中文本身没排好：字体回退到宋体、行高按英文给、汉字被加了负字距、数字列对不齐。这些都能在 tokens 和 CSS 里一次定好。`export_tokens.py` 会按本页生成中文底线规则，`lint_design.py` 会检查。

## 一、必做的五件事

| 事项 | 做法 | 为什么 |
|---|---|---|
| 声明语言 | `<html lang="zh-CN">` | 汉字统一编码后，同一个字在中日韩有不同字形，浏览器按 lang 选字体。不写 lang，渲染取决于用户系统语言。 |
| 中文字体回退 | 拉丁字体在前，中文字体在后：`'SF Pro Text', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans SC', 'Source Han Sans SC', sans-serif` | 只写 Inter 或 Roboto 时，中文落到浏览器默认字体，部分 Windows 环境是宋体。Ant Design v5、v6 的默认栈就没有写中文字体。 |
| 行高按用途分 | 界面 1.5714（14px 配 22px），中文正文 1.75，标题 1.35，展示 1.2 | 国内设计系统都用 14px 配 22px，这是密集界面的值；连续阅读的中文需要 1.5 到 2.0（W3C clreq）。 |
| 汉字不加负字距 | 中文 `letter-spacing: 0`；负字距只给拉丁标题，用 `:lang(en)` 限定 | 汉字是方块字，负字距会让字挤在一起。 |
| 数字等宽 | 表格、金额、统计值用 `font-variant-numeric: tabular-nums` 并右对齐 | 比例数字的列会左右抖动。Ant Design 规范和阿里云 Vibe Design 手册都这样要求。 |

## 二、建议做的

- **中英文间距交给浏览器**：`html:lang(zh) { text-autospace: normal; }`。三大浏览器都已支持，但默认关闭，必须显式打开。打开后不要再手打空格。
- **行长**：中文正文每行 17 到 40 字，不少于 10 字，横排不超过 48 字（clreq）。CSS 用 `max-inline-size: 40em`。
- **字重只用 400、500、600**：微软雅黑只有细体、常规、粗体三档，540、680 这种中间值在 Windows 上会跳到常规或粗体，层级就塌了。需要每个平台都有真正的 500，用 Noto Sans SC 可变网络字体。
- **标点挤压**：`text-spacing-trim` 目前只有 Chrome 支持，而且要字体带 `halt` 或 `chws` 特性。可以写上，但不要依赖它。
- **长文对齐**：网页上中英混排时两端对齐会出现大空隙，默认左对齐；纯中文长文可以考虑两端对齐。
- **字号底线**：界面最小 12px，正文 14px（工具类）或 16px（阅读和营销）。字阶控制在三到五种。

## 三、字体许可：能不能做成网页字体

| 字体 | 许可 | 网页嵌入 | 子集化/切片 | 注意 |
|---|---|---|---|---|
| 思源黑体、思源宋体（Source Han） | OFL 1.1 | 可以 | 可以 | 改过的版本不能叫 “Source” |
| Noto Sans SC、Noto Serif SC | OFL 1.1 | 可以 | 可以 | Google Fonts 已切成 101 片，只加载用到的 |
| 霞鹜文楷 LXGW WenKai | OFL 1.1 | 可以 | 可以，网页子集可保留原名 | 适合温暖、文艺的标题 |
| 得意黑 Smiley Sans | OFL 1.1 | 可以 | 可以 | 仓库自带 woff2，适合展示标题 |
| 鸿蒙字体 HarmonyOS Sans | 华为专有许可 | 可以 | 不可以修改 | 软件里要显著注明使用了该字体 |
| MiSans | 小米许可 | 可以 | 不可以改编 | 软件里要注明使用了 MiSans |
| OPPO Sans | OPPO 许可 | 可以 | 不可以改编 | 不能提供其他下载渠道 |
| 阿里巴巴普惠体 | 阿里巴巴许可 | 可以 | 未经书面授权不得转换、拆分 | 转 woff2 和切片都算 |

结论：要做网页字体并切片，只用 OFL 那一组。厂商字体可以作为本地字体名写进字体栈（用户装了就用），不要自己切片托管。

## 四、网络字体怎么上

- 默认不用中文网络字体。苹方、微软雅黑、Noto Sans CJK 已经覆盖 macOS、iOS、Windows 和 Android。原型和候选一律用系统字体，评审快，也最接近真实效果。
- 需要统一字重或品牌感时再上。一个完整的中文字体约 18MB，必须切片：用 Google Fonts，或用 `cn-font-split`、`vite-plugin-font` 自己切。
- 自己用 `pyftsubset` 子集化时，加上 `--layout-features+=halt,chws,vhal,vchw,palt,tnum`，否则标点挤压和等宽数字会悄悄失效。
- 在 tokens.json 的 `typography.webfont_cjk` 里记录字体名、许可和加载方式，`enabled` 默认 `false`。

## 五、tokens.json 怎么写

```json
"locale": { "lang": "zh-CN" },
"typography": {
  "latin_body": "'SF Pro Text', 'Segoe UI'",
  "cjk_sans": "'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans SC', 'Source Han Sans SC'",
  "cjk_serif": "'Source Han Serif SC', 'Noto Serif SC', 'Songti SC'",
  "heading_cjk": "sans",
  "weight_regular": 400, "weight_medium": 500, "weight_bold": 600,
  "scale": { "xs": 12, "sm": 13, "base": 14, "md": 16, "lg": 18, "xl": 20, "2xl": 24 },
  "line_height": { "ui": 1.5714, "body": 1.75, "heading": 1.35, "display": 1.2 },
  "letter_spacing": { "cjk": "0", "latin_display": "-0.01em" },
  "measure": { "cjk_max_em": 40 },
  "numerals": { "data": "tabular-nums" }
}
```

`export_tokens.py` 会把 `latin_*` 和 `cjk_*` 拼成完整字体栈；旧版直接写的 `heading_font`、`body_font` 仍然有效，但要自己保证里面有中文字体。

## 来源

- [W3C 中文排版需求 clreq](https://www.w3.org/TR/clreq/)：行长、行距、中西文间距、标点。
- MDN 和 browser-compat-data：`text-autospace`、`text-spacing-trim` 的支持情况与默认值。
- Ant Design、TDesign、Arco Design、Semi Design 的字体与行高 token（14px 配 22px，行高等于字号加 8px）。
- 各字体仓库或官网的许可原文：Source Han、Noto CJK、霞鹜文楷、得意黑、HarmonyOS Sans、MiSans、OPPO Sans、阿里巴巴普惠体（官网无法渲染，读的是第三方转载的法律声明）。
- [fontTools subset 文档](https://fonttools.readthedocs.io/en/latest/subset/index.html)：默认保留的 OpenType 特性列表。
- 阿里云 Vibe Design 手册：中文界面不用 Inter、Roboto 打头的字体栈，“中文行高和标点发飘”。
