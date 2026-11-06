---
name: "style-compass"
description: "把已有 PRD 或一句需求做成可交互 UI 原型、设计 tokens 与开发规格。做产品界面设计、视觉方向选择、页面加改版、现有页面评审（如「帮我把这个页面做个可点原型」）时用；纯落地页和通用出图不走这里，也不做需求发现。可独立使用；明确进入 OPC 时服从其输入、审批和编排。"
---

# 设计罗盘 · UI/UX 设计节点

给有代码能力、缺设计经验的人做产品界面：从一句需求到可点原型 + 设计 tokens + 开发规格。每关都渲染出来给用户看/给用户玩，不让人在文字里想象风格。

- **输入**：PRD（可选）或一句需求/现有工程材料。**输出**：`prototype/`（可交互 HTML，核心旅程能点通）＋ `design-spec-<topic>.md` ＋ 设计档案（`DESIGN.md`、`design/tokens.json`，见 `references/design-archive.md`）。
- 脚本只依赖 Python 3.9+ 标准库；正式视觉验收需要宿主浏览器，缺少时明确标注"未验收"。
- 明确作为 OPC 设计节点（`.design`）运行时，契约、门禁和输出目录服从适配器，不重开问诊；交接规范见 `references/handoff.md`。

## 关卡路由（每关只读这一份 reference + 跑这一条脚本）

| 关卡 | 必读 reference | 必跑脚本 | 产物 |
|---|---|---|---|
| 入场分流 | `references/design-archive.md` | `design_memory.py scan <产品目录>` | 路线判定：新做/延续/补档/评审 |
| 理结构 | `references/structure-guide.md` | —（画完自查每个需求有落点） | 灰阶线框 HTML |
| 问诊 | `references/intake-questions.md` | `design_memory.py taste` | `design/direction.md` 方向简报（3~4 个风格坐标，含一个反向候选） |
| 确认 UX | `references/interaction-guide.md` | `validate_stage_contract.py --phase direction` | 灰阶可点原型（真点动线，不问"看着怎么样"） |
| 视觉定稿 | `references/visual-craft.md` + `cjk-typography.md` | `lint_design.py diverge prototype/directions.json`；`lint_design.py check <页面>.html --phase direction`；选定后 `--phase final --tokens design/tokens.json` | tokens.json + 高保真页 |
| 交付 | `references/prototype-guide.md` + `handoff.md` | `export_spec.py` → `export_tokens.py design/tokens.json --out design --targets all --design-md DESIGN.md` → `design_memory.py check <目录>` | design-spec.md + DESIGN.md |

- 评审/优化现有页面不进四关，走 `references/audit-guide.md`。
- 四关的确认边界、`R/P/J/A/S` 编号、异步/危险动作行为字段，全在 `references/stage-contracts.md`。
- 多版并排装订：`compare_variants.py`（变体必须与输出同目录，跨目录默认拒绝，确认后加 `--allow-cross-dir`）。

## 固定工作台（从理结构关起强制复用，不另起外壳）

```bash
python3 scripts/scaffold_review.py <prototype目录>                       # 生成 spatial-studio/v1 工作台+契约示例；之后只替换画板和设计清单
python3 scripts/validate_review_workspace.py <prototype>/index.html      # 每次正式评审前跑；外壳被项目改坏必须失败
python3 scripts/review_server.py --root <prototype目录>                  # 起本地评审服务（默认 http://127.0.0.1:8833）
```

评论写入 `review-data/comments.json`，关卡状态写入 `review-data/workflow.json`。**评审完必须关闭服务**（SIGTERM/Ctrl+C 优雅停机释放端口）。写接口只放行同源请求；只用浏览器本地存储不算正式交付。工作台细节与数据协议见 `references/review-framework.md`。

## 关键约定（细节见对应 reference，不在此重复展开）

- 视觉决策（颜色/密度/间距/字体）一律渲染出来给用户看；只有产品判断问用户。完整方法见 `references/visual-craft.md`。
- 展示视觉候选前过 `--phase direction` 门禁；选定方向过 `--phase final` 门禁后才称"视觉定稿"。语义变化退回原关卡，不在视觉关静默改。
- spec 必须从选定 HTML 自动导出（`export_spec.py`），不两头手写；数值以 `design/tokens.json` 为准。
- `SMELL-` 规则只是提示，不是审美结论：`SMELL-EXAMPLE-COPY` 只拦逐值照抄示例色板，微调照抄拦不住——方向要来自本产品 direction 简报，跑过 lint 不等于不抄。确实要用默认长相时，在 tokens 的 `guardrails.accepted_defaults` 写规则编号和理由。
- 口味记录存在本机 `~/.style-compass/taste.md`，第一次记之前必须征得用户同意。

## 边界（这个节点不做什么）

- 不做需求发现和需求正确性——那是上游产品节点的事；不做纯落地页和通用创意出图（走 creative-design）。
- 不替代 html skill 做一次性页面；这里产出的是带阶段契约和评审记录、可复用的设计档案。
- `scripts/artifact_io.py` 是 opc-envelope 公共信封的 vendored 副本，内含 radar/assess 等多类型支持；本技能只产 `design` 类型，那些分支在本包内不会被触发。

## 目录

```
references/   design-archive / structure-guide / intake-questions / style-library.yaml
              visual-craft / cjk-typography / interaction-guide / stage-contracts
              audit-guide / visual-evaluation / review-framework / prototype-guide / handoff
scripts/      lint_design / design_memory / token_utils / compare_variants / export_spec
              export_tokens / validate_review_workspace / validate_stage_contract
              scaffold_review / review_server / artifact_io / check_vendored / vendor-manifest.json
examples/     tokens.example.json（数值不是配方） stage-contract.example.json
assets/       review-framework/（工作台模板、样式、脚本）
tests/        python3 -m unittest discover -s tests
```

## 维护

- 发布前跑 `python3 scripts/check_vendored.py`（校验 vendored 文件哈希）和全量测试。
- 版本与更新点见 `CHANGELOG.md`；行为用例见 `evals/evals.json`。
