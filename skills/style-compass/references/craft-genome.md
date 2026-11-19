# 自由工艺基因引擎（Craft Genome & Remix）

> **9 套工艺包是视觉质量锚点与起跳板，绝不是只能 9 选 1 的固定模板。**
> 无论遇到新产品想法，还是觉得某个已有版本差点意思，都可以沿着下面的 **5 条正交工艺轴 + 3 根创作旋钮** 自由拆解、重组或当场合成第 10 种、第 N 种流派。

---

## 一、三条创作路径（按需求自由组合）

| 路径 | 适用时机 | 怎么动笔 |
| --- | --- | --- |
| **A. 单锚点直出 + 业务定色** | 场景与 9 套工艺包某一项高度吻合 | 先看 `assets/craft-packs/<id>.png` 定表面精度，再按业务领域重选主色、字体比例与真实内容，不原样照搬样板主题 |
| **B. 跨流派基因混搭（Remix）** | 用户喜欢 A 的材质但想要 B 的骨架，或现有方案略显单调 | 从不同工艺包里各自抽取「表面材质」「构图隐喻」「色温」「字体」「动效」，按五轴重组 |
| **C. 从零合成新流派** | 全新品类、特殊硬件/空间展示或明确要脱颖而出 | 设定 `VARIANCE / MOTION / DENSITY` 三旋钮读数，再从五条正交轴各择其一现场拼装 |

---

## 二、五条正交可混搭工艺轴

任意界面都可以拆成彼此独立调音的 5 条轴（混搭时**保持同屏只选 1 种核心物理材质**，避免风格打架）：

### 轴 1 · 表面与光学物理（Surface Physics）
1. **液态折射玻璃（Liquid Glass · Apple WWDC25/26 规范）**：
   - **唯一职责**：只用作**悬浮于内容之上的导航岛、工具栏、胶囊控制条与播放器 Dock**；列表卡片、正文行与数据表本身保持干净实底或微染色实面，**严禁玻璃叠玻璃（Never glass on glass）**。
   - **光学四要素**：高饱和模糊底（`backdrop-filter: blur(22px) saturate(190%)`）、`135deg` Fresnel 镜面亮边（`::before` 配合 `mask-composite: exclude`）、顶缘 `inset 0 1px 0 rgba(255,255,255,0.75)` 高光、与容器间距严格匹配的同心圆角（`R_inner = R_outer - padding`），以及滚动内容进入浮栏下方的渐变柔和边缘（`mask-image` / 渐变遮罩）。
   - **背景对比前提**：必须配合柔和干净、局部色彩丰富的景深环境画或浅影，但严禁紫色/紫蓝 AI 默认渐变，优先海洋天青、晨光暖金、冰川极光冷色。
2. **双态大气雾面（Atmospheric Frost · 浅/深双态分离工作台）**：
   - 背景铺开极轻柔的极光/深海/冷雾径向大气底光，侧栏与主工作区**物理分离为带 `16px–20px` 圆角的微透雾面板**（`backdrop-filter: blur(16px)` + `1px` 微弱半透明顶边），支持一键「深空雾暗 ↔ 冰川浅雾」无缝切换，适合每天长时间停驻的 AI 工作台与协同工具。
3. **阳极精密暗金属（Obsidian Anodized）**：深碳底配高半档操作面与内凹日志槽，顶缘 `0.08` 白色发丝微光模拟硬件倒角。
4. **温润瓷纸（Porcelain Mineral）**：浅矿石底托起大圆角纯白瓷纸，多层极柔暖影取代生硬灰框。
5. **哑光工业聚合硬件（Tactile Hardware）**：ENGINEERING / BRAUN 质感——工程灰白哑光机身 + 真实可塌陷 3D 物理键帽（`0 3px 0` → `0 1px 0`）+ 内凹高对比深碳 OLED 仪器窗 + 国际信号橙重点键。
6. **典藏印刷纸（Archival Paper & Ink）**：`1px` 细栏线 + 朱砂/暖黄批注，零浮夸投影，纯粹靠版心与字距定神。
7. **强对比便当展厅（Bento Contrast Stage）**：暖灰白展台托起纯黑、深森绿、暖陶土与纯白的强烈材质拼贴，主模块带指针跟随径向光斑。

### 轴 2 · 空间构图隐喻（Spatial Metaphor）
- **悬浮胶囊岛 ＋ 全屏内容流**（`liquid-glass`）
- **分离式圆角雾面侧栏 ＋ 节点流舞台**（`nordic-frost`）
- **实体仪器面板 ＋ 中央凹陷 OLED 视窗**（`tactile-hardware`）
- **12 列非对称便当展示矩阵**（`kinetic-bento`）
- **58px 图标轨 ＋ 主执行舞台 ＋ 并发辅助轨**（`obsidian-precision`）
- **单张圆角瓷纸呼吸流 ＋ 滑入详情抽屉**（`porcelain-craft`）
- **64/36 不对称主栏 ＋ 粘性实证边注**（`editorial-ink`）
- **64/36 主走势大卡 ＋ 满轨排名榜 ＋ 健康账本**（`executive-telemetry`）

### 轴 3 · 色彩温度与光氛自合成
- 不死守单一色板：**主中性灰也要带 `2%–4%` 轻微色温偏向**（冷雾偏青灰、暖瓷偏砂灰、暗台偏曜石蓝灰），比纯 `#808080` 高出一个维度。
- 强调色聚焦为 **1 个主情绪/动作色 ＋ 1–2 个语义辅助色**，严禁全屏彩虹标签和 Tailwind 默认靛紫蓝渐变。

### 轴 4 · 字体气质配对
- **精密仪器风**：无衬线黑体（`PingFang SC / SF Pro`）配真等宽数字（`JetBrains Mono` / `tabular-nums`）。
- **人文编辑风**：思源宋体 / 系统宋体（`700` 大标题 `28px–34px`）配克制黑体正文（`15px–16px`, `line-height: 1.75`）。
- **视觉展厅风**：超大 Display 粗体主标题（`32px–40px`）配极简等宽标签标尺与清晰层级副标题，**中文绝不加负字距**。

### 轴 5 · 动效性格档位
直接从 `references/motion-craft.md` 选取：**精密干脆** / **温润跟手** / **灵动微弹** / **精密数据** / **从容印刷**，按频率铁律配置 `--spring-snappy / --spring-smooth / --spring-bouncy`、`Blur-Replace`、景深堆叠浮条或指针跟随镜面光泽。

---

## 三、三根创作旋钮（Taste Dials）

内部构思或接收用户风格微调时，先标出三个 `1–10` 读数再动手写 CSS：

| 旋钮 | `1–3`（稳健实用） | `4–6`（现代高定 · 推荐默认） | `7–10`（大胆破格） |
| --- | --- | --- | --- |
| **`VARIANCE`（构图突破度）** | 熟悉后台/日常工具骨架，低学习成本 | 明显非对称主舞台，破除均分网格 | 强烈雕塑感便当矩阵 / 硬件机身 / 悬浮空间岛 |
| **`MOTION`（动效表现力）** | `120–160ms` 极简色变＋按压缩放 | 滑动胶囊＋物理弹簧抽屉＋SVG 描绘／数字计数 | 首屏错峰 ＋ Blur-Replace ＋ 指针跟随微光 ＋ 堆叠浮条 |
| **`DENSITY`（信息密度）** | 极简呼吸感，大量留白，单焦展示 | 首屏一眼主次兼顾可点详情，透气不空 | 高密研发控制台 / 仪器面板 / 多维度数据账本 |

> **典型读数速配**：
> - 日常 SaaS 工作台：`VARIANCE 5 / MOTION 5 / DENSITY 6`
> - 液态玻璃 / 消费端概念首屏：`VARIANCE 7 / MOTION 7 / DENSITY 3`
> - 专业 AI / 研发诊断仪器台：`VARIANCE 5 / MOTION 4 / DENSITY 8`

---

## 四、Go Wide → Remix 混搭闭环

做 `explore` 多方向探索时：
1. **真正拉开正交轴**：2–3 个候选不能只换主题色，必须在**表面物理、空间构图、明暗双态、字体/动效性格**至少三个维度明显不同（推荐组合示例：`liquid-glass` 空间通透 ＋ `nordic-frost` 双态雾面工作台 ＋ `kinetic-bento` 或 `tactile-hardware` 破格方案）。
2. **自然语言一句 Remix**：用户看过画廊说「**要方案 A 的液态玻璃胶囊导航 + 方案 B 的深空雾工作区结构 + 更干脆少回弹的动效**」时，直接把 5 条轴的新取值写入设计备忘并重新合成单稿与新 tokens，不再强迫走重型问卷或四关流程。

---

## 五、Web 原型 ↔ Apple 原生（SwiftUI）动效材质映射表

当产物随后要交付给 iOS / macOS 原生工程落地时，按以下等效关系标注开发规格：

| Web 高定原型工艺（HTML/CSS） | Apple 原生等效 API（SwiftUI / iOS & macOS 26+） |
| --- | --- |
| 悬浮液态玻璃岛（`blur + 135deg Fresnel + 同心圆角`） | `.glassEffect(.regular.interactive(), in: .rect(corner: .containerConcentric))` ＋ `GlassEffectContainer` |
| 滚动进入浮栏柔和渐隐边缘 | `.scrollEdgeEffectStyle(.soft, for: .top)` / `.hard` |
| 原生 CSS `--spring-snappy / --smooth / --bouncy` | `.snappy` / `.smooth` / `.bouncy`（`.spring(duration:bounce:)`） |
| Blur-Replace 内容切换 | `.transition(.blurReplace)` |
| 分段胶囊滑动高亮 | `@Namespace` ＋ `.matchedGeometryEffect(id:in:)` ＋ `.glassEffectID` |
| 等宽数字跳动计数（`tabular-nums`） | `.contentTransition(.numericText())` ＋ `.monospacedDigit()` |
| SVG 路径描绘 / 状态反馈 | `SymbolEffect`（`.drawOn` / `.bounce` / `.pulse`）＋ `.animation(..., value:)` |
