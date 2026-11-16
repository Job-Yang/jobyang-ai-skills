---
name: "style-compass"
description: "把已有 PRD 或一句需求做成可交互 UI 原型、设计 tokens 与开发规格。做产品界面设计、视觉方向选择、页面加改版、现有页面评审（如「帮我把这个页面做个可点原型」）时用；基础单页、简单组件和明确需求默认快速交付，复杂流程与正式评审走完整流程。纯落地页和通用出图不走这里，也不做需求发现。可独立使用；明确进入 OPC 时服从其输入、审批和编排。"
---

# 设计罗盘 · UI/UX 设计节点

给有代码能力、缺设计经验的人做产品界面：按任务风险选择 quick、audit 或 full，不让基础 UI 被完整评审流程拖住，也不把高风险流程误判成“小页面”。

- **quick 输出**：完整可交互 prototype 代码＋实际使用的 tokens＋简短使用说明与假设。
- **full 输出**：`prototype/`＋`design-spec-<topic>.md`＋设计档案（`DESIGN.md`、`design/tokens.json`，见 `references/design-archive.md`）。
- 脚本只依赖 Python 3.9+ 标准库；视觉验收需要宿主浏览器，缺少时明确标注“未视觉验收”。
- 明确作为 OPC 设计节点（`.design`）运行时一律走 full，契约、门禁和输出目录服从适配器，不重开问诊；交接见 `references/handoff.md`。

## 入场先选路径

| 路径 | 何时选择 | 核心方法 |
|---|---|---|
| `quick`（默认） | 基础单页、简单组件、需求已明确，或用户说“直接做一版” | 合并结构、交互和视觉，一次做成并批量验证；读 `references/quick-ui.md` |
| `audit` | 任务只是评审现有页面 | 读 `references/audit-guide.md`；若随后要产出改版，再按风险进入 quick 或 full |
| `full` | 多页面跨角色复杂流程、新设计系统、用户明确要完整评审，或 OPC | 保留四关、固定工作台、阶段契约和正式交付 |

已有品牌、已确认行为和上游约束在三条路径都继承。不要只按页数分流：单页若要定义支付规则、改变权限模型、设计不可逆写入、跨角色交接或复杂异常恢复，也应走 full；仅展示现有规则或无外部副作用的本地演示，不因出现这些词自动升档。只有真实业务歧义会改变任务或验收时才追问；内容充分时直接做。

## quick：直接做成

1. 读取 `references/quick-ui.md`、`references/design-kernel.md`、`references/interaction-craft.md`、`references/visual-craft.md` 和 `references/cjk-typography.md`。
2. 合并结构、交互和视觉，不重新做口味问诊，不要求先列 8–12 个想法或制作 2–4 个候选。
3. 不强制固定工作台、持久评论服务、全量 `DESIGN.md` 建档或导出全部平台 tokens；但 prototype 必须完整可点，tokens 必须是页面实际使用值。
4. 交付前用实际 tokens 跑 final lint，再由独立 Playwright 在桌面、移动宽度走关键操作；集中修复最多一轮，不逐个样式向用户提问。浏览器不可用时标“未视觉验收”，不能以测试通过代替好看。
5. 个人口味持久写入、外部发布和危险动作仍按原授权边界执行；quick 稿不得称为正式审批通过。

## full：四关与正式门禁

| 关卡 | 必读 reference | 必跑脚本 | 产物 |
|---|---|---|---|
| 入场分流 | `references/design-archive.md` | `design_memory.py scan <产品目录>` | 新做／延续／补档／评审 |
| 理结构 | `references/structure-guide.md` | —（画完自查每个需求有落点） | 灰阶线框 HTML |
| 问诊 | `references/intake-questions.md` | `design_memory.py taste` | `design/direction.md`（3–4 个风格坐标，含反向候选） |
| 确认 UX | `references/interaction-guide.md`＋`references/interaction-craft.md` | `validate_stage_contract.py --phase direction` | 灰阶可点原型 |
| 视觉定稿 | `references/design-kernel.md`＋`references/visual-craft.md`＋`references/cjk-typography.md` | `lint_design.py diverge prototype/directions.json`；`lint_design.py check <页面>.html --phase direction`；选定后 `--phase final --tokens design/tokens.json` | tokens.json＋高保真页 |
| 交付 | `references/prototype-guide.md`＋`references/handoff.md` | `export_spec.py` → `export_tokens.py design/tokens.json --out design --targets all --design-md DESIGN.md` → `design_memory.py check <目录>` | spec＋DESIGN.md＋档案 |

四关确认边界、`R/P/J/A/S` 编号和危险动作字段见 `references/stage-contracts.md`。full 的原多方向协议、正式阶段校验和固定工作台全部保留。多版并排仍用 `compare_variants.py`，不改变原跨目录限制。

## quick 与 full 共用的设计内核

视觉创作先用 `references/design-kernel.md` 决定主对象、主动作、构图和产品重点，再读 visual-craft 与 CJK 规则；代表性任务用 `references/interaction-craft.md` 检查动作、状态、反馈、恢复和上下文。这些是创作与提交前自查，不新增用户审批关卡，也不改变 full／OPC 原评审决策链路。

内部方向最多五行：任务、首屏构图、字体角色、颜色分工、一个产品专属视觉或互动亮点。用户要求更有表现力时，要落实到比例、色面、形状、内容和动势，不能惯性回到灰白中性；对比度和可用性是底线，但“只能一个强调色”“全局禁某字体”不是默认规则。

quick 只有在用户明确要多方案或存在真正设计分歧时才给 2–3 个候选，缩略图必须一眼可区分，不为凑标签差异而做卡片。每案先达到同一视觉与 UX 底线，再判断差异；full 仍按 `references/visual-craft.md` 的多方向协议执行。

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

## 边界与维护

- 不做需求发现和需求正确性；不做纯落地页和通用创意出图。
- 不替代一次性页面工具；这里交付的是可点 prototype、实际 tokens 与可复用规格。
- `scripts/artifact_io.py` 是 opc-envelope 的 vendored 副本；本技能只产 `design` 类型。
- 发布前跑 `python3 scripts/check_vendored.py` 和 `python3 -m unittest discover -s tests -v`。
- 版本见 `CHANGELOG.md`；行为用例见 `evals/evals.json`。
