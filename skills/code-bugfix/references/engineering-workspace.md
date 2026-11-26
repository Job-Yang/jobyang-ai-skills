# 工程工作区与多技能交接契约（唯一事实源）

> 本文件定义研发类技能进代码仓后的统一工作区落位、上游锚点、进度状态与前后交接契约，按需查阅。

## 一、三态工作区自动适配

研发技能同时服务**个人独立仓**与**多人协作公司大仓**，按仓库现状自动选择落位（支持人工显式指定 `--mode` 覆盖）：

| 模式 | 适用场景 | 文档与Spec落位 | 进度与归档机制 | 对共享仓影响 |
| --- | --- | --- | --- | --- |
| `repo` | 个人项目或团队允许工作流文档入仓（已存在 `docs/spec` 或 `docs/feature`） | `docs/feature/<slug>.md`、`docs/spec/<slug>.md`、`docs/GLOSSARY.md`、`AGENTS.md` | 1 步 1 提交并附带 `Spec-Step: <slug>#<n>` trailer；完工用 `git mv` 移入 `docs/spec/archived/<YYYY-MM-DD>-<slug>.md` 并配 `.ignore`（内容 `*`） | 入库随项目演进 |
| `local` | **多人公司大仓默认**（常规 Git 仓且无 `docs/spec`） | `.agent-work/feature/<slug>.md`、`.agent-work/spec/<slug>.md`、`.agent-work/GLOSSARY.md` | 把 `.agent-work/` 仅追加进本机私有 `.git/info/exclude`（用 `git rev-parse --git-path info/exclude` 兼容 worktree）；进度记于 `.agent-work/state/<slug>.json` 或按步提交；完工归档至 `.agent-work/spec/archived/<YYYY-MM-DD>-<slug>.md` 配 `.ignore` | **零污染**：不改共享 `.gitignore`，不混入 PR diff |
| `ephemeral` | 非 Git 目录、一次性提问或极小单文件修改 | 对话内直接交付，不建持久化工作目录 | 对话内完成即止 | 无磁盘残留 |

可用内置的 `workspace_guard.py detect` 自动识别模式，用 `init-local` 初始化零污染隐藏工作区（携带该脚本的技能位于其 `scripts/` 目录）。

## 二、当前态原则与防污染纪律

- **只写现在为真**：`feature/`、`spec/` 与 `GLOSSARY.md` 只记录当前有效定义与规格，不写变更日志、辩论史或过程 TODO；历史留在 Git 与归档目录。
- **归档隔离检索**：`archived/` 目录下放 `.ignore` 文件（内容为单行 `*`），把 `ripgrep` 等搜索工具挡在过期方案之外；任何新开发、盲审与排查均不读取归档 Spec。
- **Spec 写定后只读**：在执行阶段不得一边写代码一边私改 Spec；遇到步内无法按 Spec 落地时立即停下汇报，回到 Spec 设计环节重算。

## 三、上游漂移熔断（Git Blob 摘要锚点）

- `implement-spec` 生成开放 Spec 时，必须在文件前 25 行记录上游来源与内容摘要：
  - 有上游需求/方案文件时：`Source: `<path>` @ `<git-blob-sha>``（`workspace_guard.py hash <file>` 与 `git hash-object <file>` 逐字节等价，对已跟踪与未跟踪文件通用）；
  - 无上游文档的纯重构或直起 Spec：`Source: none`。
- 盲审开工前与分步实现开工/续跑前，先运行 `verify-hash` 校验上游摘要：
```bash
python3 scripts/workspace_guard.py verify-hash --spec <spec.md>
```
若摘要失配（退出码 `2`），说明上游需求或方案已变更，立即熔断并退回更新 Spec。

## 四、双轨进度与跨会话无损续跑

- **提交规范自适应**：个人仓推荐 1 步 1 提交并在提交说明末段附加 `Spec-Step: <slug>#<n>` trailer；团队大仓若有严格 Commit 模板或要求 Squash 合并，改用 `workspace_guard.py record-step` 将已完成步号与 SHA 写入 `.agent-work/state/<slug>.json`，遵循团队提交规范而不强行篡改 Commit Message。
- **统一进度计算**：`workspace_guard.py progress --spec <spec.md>` 会同时合并 Git trailer 与 `state/<slug>.json`，依据 `After:` 依赖图算出当前可并行/可执行的 `ready` 步骤；任意时刻上下文中断，新会话都能无损接续。

## 五、项目阶段、术语表与上游桥接

- **Project status 三档约束**（可写于 `AGENTS.md` 或 `.agent-work/PROJECT.md`）：
  - `startup`：允许破兼容以换取长期更好设计，持久化数据可重置。
  - `release-solo`：接口可重构，但既有持久化数据需给出迁移策略、不随便重置。
  - `release`（大仓默认）：兼顾长期设计与向后兼容、灰度共存及数据迁移。
- **单页术语表（`GLOSSARY.md`）**：一词一义，每条只用 1–2 句定义概念本身并列 `_Avoid_` 禁用近义词，不写实现细节或决策理由；重命名术语时同步更新所有未归档文档。
- **仓规准入模板**：若项目尚无 `AGENTS.md`（或团队 `CLAUDE.md`），新建规则只收 6 类过不过都会踩坑的硬事实：常用构建/单测/检查命令、非显而易见目录布局、Project status、易踩 Gotchas、代码架构底线、禁碰边界。
- **前段 OPC 产物无缝接入**：前端 `product-brief`（PRD 或单特性轻卡片）、`style-compass`（`DESIGN.md` / `tokens.json`）与 `engineering-docs`（RFC/ADR）落盘后，直接作为 `implement-spec` 的 `Source:` 输入，不再重复打包信封。
