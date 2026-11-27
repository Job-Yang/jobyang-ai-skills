---
name: implement-spec
description: "新功能开发、跨文件改造或代码重构动工前的设计与拆步：定模块接口、测试接缝、兼容迁移与分步计划。触发：「开发这个功能先规划下」「重构这块怎么改」「帮我拆下实现步骤」。不适用：几十行单文件微改、需求拍板（product-brief）或直接编码（go-work）。"
---

# Implement Spec · 可执行实现规格设计

将已确认的需求或安全重构目标，拆解为编码阶段可直接照做的深模块接口、接缝替身、兼容迁移与 1-commit 步骤。

## 1. 先定工作区与范围门槛

1. **自动判定落位**：运行 `python3 scripts/workspace_guard.py detect`（不在目标仓根目录时加 `--root <仓库路径>`；多仓细则与个人仓 `docs/` 规范按需查阅 [工程工作区契约](references/engineering-workspace.md)）：
   - 已有 `docs/spec` 或 `docs/feature` 的个人仓用 `repo`（`docs/spec/<slug>.md`）；
   - 多人协作大仓默认用 `local`（执行 `python3 scripts/workspace_guard.py init-local` 初始化 `.agent-work/` 并仅写入 `.git/info/exclude`，零污染共享仓）；
   - 开发期范围清晰、可随时 Git 回退的中小改动或非 Git 目录走 `ephemeral`，直接编码验证或在对话内给简短步骤，不强行建重文档。
2. **上游版本锚定**：有上游文档（PRD、单特性卡片或 RFC）时，在 Spec 前 25 行写 `Source: `<path>` @ `<hash>``（摘要由 `python3 scripts/workspace_guard.py hash <file>` 生成）；纯架构重构写 `Source: none`。
3. **术语一致**：专有概念与 `GLOSSARY.md` 保持一词一义，不在 Spec 内重新推翻上游产品裁定（要改需求回到 `product-brief`）。

## 2. 摸清代码现状与选择模式

- **读热区与调用方**：改存量代码前，先用 `git log --since='6 months ago' --name-only --format= | sort | uniq -c | sort -rn | head -20` 看高频改动热区，追读目标模块真实调用链。若面对完全陌生的复杂旧系统，先补一次源码机理调研再动手拆步骤。
- **新功能模式**：逐行把上游需求映射为「模块归属 → 真实接口代码 → 验证测试」三列对照表。
- **存量安全重构模式（`Source: none`）**：**第 1 步先补表征测试（Characterization Tests）锁住当前外部行为**，后续每步做保持行为等价的小步迁移，杜绝一边重构一边偷改业务逻辑。

## 3. 深模块设计与大仓兼容原则

- **深模块与删减检验**：把复杂度向下压进模块实现里，对外暴露小而稳的接口；写完接口先做删除检验——若删掉某层后复杂度并没有扩散回调用方，说明只是多余透传层，直接合并。详细依赖分层、测试替身策略与多方案对比（Design-it-Twice）按需查阅 [深模块设计与接缝指南](references/deep-module-design.md)。
- **多人大仓向后兼容**：涉及接口字段、消息协议、缓存结构或数据库 Schema 变更时，按需查阅 [多人大仓生产安全清单](references/big-repo-safety.md)，按 Expand → Backfill/Dual-Write → Contract 分期拆步，确保新老版本混跑与在线回滚安全。

## 4. 输出 Spec 契约与交接边界

按需查阅 [实现 Spec 模板](references/spec-template.md) 写出完整 `spec/<slug>.md`（留空无关节）：

- 包含核心节：`Behavior map`、`Modules`（真实语言接口签名、不变量、顺序、错误模式、隐藏实现细节、典型调用例）、`Data`（唯一写者与迁移方式）、`Dependencies`（真实外部依赖与本地替身）、`Steps`（每步含 `After:` 依赖与非空可运行 `Check:`，**并行步绝不碰同一文件**）、`Not this`。
- **定位与交接**：Spec 落盘后作为执行基线；高风险或陌生模块可按需用 `spec-battle` 盲审，跨模块多步任务交给 `go-work` 落地（执行期细小实现偏差可直接修正并说明）。
