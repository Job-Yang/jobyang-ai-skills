---
name: "style-compass"
description: "把需求或 PRD 做成带动效的可交互 UI 原型、tokens 与设计规格（覆盖单页直出、多风格画廊直选、页面评审与 OPC 四关全流程）。用户说「做个可点原型」「出几套风格给我选」时用；不做纯落地页、通用出图或需求发现。"
---

# 设计罗盘 · UI/UX 审美与动效引擎

给有代码能力或不懂专业审美术语的人做产品界面：把“高级感、好看一点”先编译成具体的视觉工艺包与动效手感，默认直接做出高完成度可点网页；需要对齐品味时直接出 2–3 套高定样板让用户点选，不靠枯燥问卷和丑灰阶线框锁死创意。

- **quick / explore 输出**：高定可交互 HTML prototype（内置细线 SVG 图标与物理动效）＋实际使用的 tokens＋必要说明与假设（`explore` 额外附带轻量对比画廊 `gallery.html`）。
- **full 输出**：`prototype/`＋`design-spec-<topic>.md`＋设计档案（`DESIGN.md`、`design/tokens.json`，见 `references/design-archive.md`）。
- 脚本只依赖 Python 3.9+ 标准库；视觉验收通过 `scripts/capture_preview.mjs` 驱动宿主 Chromium 完成，缺少时明确标注“未视觉验收”。
- 明确作为 OPC 设计节点（`.design`）运行时一律走 full，契约、门禁和输出目录服从适配器，不重开问诊；交接见 `references/handoff.md`。
- 与 `engineering-docs` 的分工：工程技术评审方案（RFC/ADR）、严谨工程架构与时序图及技术速读页走 `engineering-docs`；交互式产品 UI 原型、工艺视觉与前端设计系统走本技能。

## 入场先选路径

| 路径 | 何时选择 | 核心方法 |
|---|---|---|
| `quick`（默认） | 基础单页、简单组件、需求已明确，或用户说“直接做一版” | 按页面类型按需查阅 `references/craft-packs.md`、`references/craft-genome.md`、`references/motion-craft.md` 与 `references/quick-ui.md`，直出高定可点页并实测截屏挑刺 |
| `explore`（高定直选） | 用户说不清风格，或新产品重要首屏想看不同气质挑定方向（无需重量级线框评审） | 跳过问卷与灰阶线框，拉开正交轴挑 2–4 套迥异流派或混搭配方（液态玻璃/双态雾面/触感硬件/便当展厅等）并行做可点关键屏，用 `scripts/build_gallery.py` 装进画廊直选；支持选中后一句 Remix 并锁定 tokens 扩全页 |
| `audit` | 任务只是评审现有页面 | 读 `references/audit-guide.md`；若随后要产出改版，再按复杂度进入 quick 或 full |
| `full` | 多页面跨角色复杂流程、新设计系统、用户明确要完整评审，或 OPC | 保留四关、固定工作台、阶段契约和正式交付；第 3 关视觉突破直接挂载工艺包＋自由基因轴，不为填线框外壳牺牲表现力 |

已有品牌、已确认行为和上游约束在全部路径都继承。不要只按页数分流：单页若要定义支付规则、改变权限模型、设计不可逆写入、跨角色交接或复杂异常恢复，也应走 full；仅展示现有规则或无外部副作用的本地演示，不因出现这些词自动升档。只有真实业务歧义会改变任务或验收时才追问；内容充分时直接做。

## quick / explore：高质感直出与画廊直选

1. 按任务按需读取：定视觉锚点与动效先看 `references/craft-packs.md`（及 `assets/craft-packs/<id>.png`）与 `references/motion-craft.md`；需要跨轴混搭、版面构图、交互链路、多候选拉开或中文排版细则时，再按需查阅 `references/craft-genome.md`、`references/design-kernel.md`、`references/interaction-craft.md`、`references/visual-craft.md` 与 `references/cjk-typography.md`。
2. `quick` 不把 9 套工艺包当死板模板，可按五轴（表面物理、空间隐喻、色温、字形、动效）与三旋钮（`VARIANCE / MOTION / DENSITY`）自由合成适配当前产品的独特表面与交互；`explore` 挑 2–4 套在明暗双态、材质物理、空间构图与动效节奏上真正拉开的流派（独立上下文分别生成，不互相抄表面），用 `python3 scripts/build_gallery.py` 生成交互画廊（`单看 / 并排 / 桌面 / 手机 / 重播动效`，支持方向键与 `1–9` 切案），支持用户直选或一句跨案 Remix 混搭后再锁定 tokens 展开全应用。
3. 不强制固定“空间画室”工作台、持久评论服务、全量 `DESIGN.md` 建档或导出全部平台 tokens；prototype 按页面体量搭载 `1–3` 项清晰交互反馈与动效（小部件 `1` 处到位即可，不为凑数堆动画）、按需配细线 SVG 图标且关键操作真实可点，tokens 必须是页面实际使用值。
4. 交付独立 HTML 页面时用实际 tokens 跑 final lint；完整页面或高交互原型的桌面与移动宽度优先运行 `node scripts/capture_preview.mjs`（或独立 Playwright）对照 `references/craft-packs.md` 六点清单核查截图后集中修复一轮（简单单部件或无浏览器时按需跳过并标“未视觉验收”）。
5. 个人口味持久写入、外部发布和危险动作仍按原授权边界执行；quick／explore 稿在明确归档前不得称为正式审批通过。

## full：四关与正式门禁

| 关卡 | 按阶段查阅 reference | 必跑脚本 | 产物 |
|---|---|---|---|
| 入场分流 | `references/design-archive.md` | `design_memory.py scan <产品目录>` | 新做／延续／补档／评审 |
| 理结构 | `references/structure-guide.md` | —（画完自查每个需求有落点） | 灰阶线框 HTML |
| 问诊 | `references/intake-questions.md` | `design_memory.py taste` | `design/direction.md`（3–4 个风格坐标，含反向候选） |
| 确认 UX | `references/interaction-guide.md`＋`references/interaction-craft.md` | —（灰阶交互走查，不混入视觉色值） | 灰阶可点原型 |
| 视觉定稿 | `references/craft-packs.md`＋`references/craft-genome.md`＋`references/motion-craft.md`＋`references/design-kernel.md`＋`references/visual-craft.md`＋`references/cjk-typography.md` | `lint_design.py diverge prototype/directions.json`；`lint_design.py check <页面>.html --phase direction`；`validate_stage_contract.py --phase direction`；`capture_preview.mjs` 截屏验收；选定后 `--phase final --tokens design/tokens.json` | tokens.json＋高定高保真页 |
| 交付 | `references/prototype-guide.md`＋`references/handoff.md` | `validate_stage_contract.py --phase final` → `export_spec.py` → `export_tokens.py design/tokens.json --out design --targets all --prototype prototype --design-md DESIGN.md` → `design_memory.py check <目录>` | spec＋DESIGN.md＋档案 |

四关确认边界、`R/P/J/A/S` 编号和危险动作字段见 `references/stage-contracts.md`。full 的原多方向协议、正式阶段校验和固定工作台全部保留。多版并排仍用 `compare_variants.py`，不改变原跨目录限制。

## quick 与 full 共用的设计内核

视觉创作先按 `references/craft-packs.md` 与 `references/craft-genome.md`（9 套视觉锚点＋五轴自由基因混搭＋`VARIANCE / MOTION / DENSITY` 三旋钮）锁定表面光学与材质上限，再用 `references/design-kernel.md` 决定主对象、主动作与非对称空间分配，接着套用 `references/motion-craft.md` 物理动效（原生 CSS `linear()` 弹簧、Blur-Replace、频率分级与微交互工艺）与 CJK 规则；代表性任务用 `references/interaction-craft.md` 检查动作、状态、反馈、恢复和上下文。这些是创作与提交前自查，不新增用户审批关卡，也不改变 full／OPC 原评审决策链路；full 在视觉定稿关应直接用工艺基因重构关键屏质感，不被线框 DOM 框住上限。

内部方向最多五行：流派锚点或跨轴混搭、首屏非对称构图、字阶反差角色、表面光影与强调色、默认搭载的物理微动效亮点。用户要求更有表现力时，要落实到表面层级、尺度对比、色面、形状、内容和物理动势，不能惯性回到灰白中性；对比度和可用性是底线，但“只能一个强调色”“全局禁某字体”“全页面禁止回弹曲线”不是默认规则。

quick 只有在用户明确要多方案或存在真正设计分歧时才转 `explore` 出 2–4 个高定候选（用 `scripts/build_gallery.py` 收口切换，并支持跨案 Remix），缩略图与首屏构图必须一眼可区分，不为凑标签差异而做同构卡片。每案先达到同一视觉与动效底线，再判断差异；full 仍按 `references/visual-craft.md` 的多方向协议执行。

## 固定工作台（仅 full／OPC）

```bash
python3 scripts/scaffold_review.py <prototype目录>
python3 scripts/validate_review_workspace.py <prototype>/index.html
python3 scripts/review_server.py --root <prototype目录>
```

评论写入 `review-data/comments.json`，状态写入 `review-data/workflow.json`；评审后必须关闭服务。工作台与数据协议见 `references/review-framework.md`。

## 关键约定

- 视觉决策必须渲染后再判断；lint 只守确定性底线，不证明审美质量。
- full 展示候选前过 direction 门禁，选定后过 final 门禁；语义变化退回原关卡。
- spec 从选定 HTML 自动导出，数值以实际 `design/tokens.json` 为准。
- `SMELL-` 是提示，不是审美结论；接受默认长相时记录规则编号和理由。
- 口味记录存在本机 `~/.style-compass/taste.md`，第一次写入前必须征得用户同意。

## 边界

- 不做需求发现和需求正确性；不做纯落地页和通用创意出图。
- 不替代一次性页面工具；这里交付的是可点 prototype、实际 tokens 与可复用规格。
- 既定 `DESIGN.md` 与 `tokens.json` 向存量代码仓分批迁移时，按页面或组件切片后交由 `implement-spec` 与 `go-work` 分步落地并逐批截屏回归。
