---
name: go-work
description: "按已确认方案分步写代码并落地：轻量协调、独立上下文提交与并行 worktree，支持断点续跑和归档。触发：「方案没问题了开始写代码」「按计划分步实现」「接着上次继续做」。不适用：无方案微改或设计拆步（implement-spec）。"
---

# Go Work · 低上下文分步编码执行

主会话只做轻量调度、不囤源码和冗长日志；每步独立上下文落地、进度交由 Git 或本地状态持久化，随时跨会话无损续跑。

## 1. 开工检查与状态熔断

1. **定位 Spec 与工作区**：按 [工程工作区契约](references/engineering-workspace.md) 锁定唯一开放 Spec（个人仓 `docs/spec/<slug>.md`；大仓 `.agent-work/spec/<slug>.md`）；若无开放 Spec，停下来指引先用 `implement-spec`。
2. **上游漂移与进度核验**：
   - 运行 `python3 scripts/workspace_guard.py verify-hash --spec <spec.md>`（不在目标仓根目录时加 `--root <仓库路径>`），返回 `2` 说明上游需求已改动，立即停止并指回 `implement-spec` 重算；
   - 运行 `python3 scripts/workspace_guard.py progress --spec <spec.md>` 算出 `landed` 与 `ready` 步骤；若发现其他分支存在同 slug 未合入提交，先汇报给用户裁决，不覆盖并行工作。
3. **只读 Spec 铁律**：整轮执行**读完一次 Spec 后不再修改它**；遇到某一步因接口/依赖不符无法按 Spec 落地时，立刻停止并阻塞汇报，绝不私自改 Spec 硬凑。

## 2. 轻量协调与步步落地

- **控制主上下文膨胀**：主协调会话只持有 Spec 全文、步骤状态与每步 ≤ 3 行的结果简报；**不在主会话大段读业务源码，也不直接打印完整构建/测试日志**（验证命令输出重定向到临时日志文件，仅失败时 `tail -40` 排障）。
- **执行器选型与子代理简报**：`Fork / Fresh / Inline` 选型、子代理 3 行回执模板、临时 detached worktree 并行（无 `After` 冲突步最多 3 路，遇 Rust/C++/iOS 等冷构建耗分钟级大仓自动降级串行）与失败至多重试 1 次规则，按需查阅 [执行器协议与并发规范](references/runner-protocol.md)。
- **双轨进度落盘**：
  - 个人仓（`repo`）：1 步 1 提交并在 Commit 正文末附加 `Spec-Step: <slug>#<n>` trailer（仅暂存本步文件）；
  - 多人公司大仓（`local`）：尊重团队 Commit 规范（不强塞 trailer），每步提交或验证通过后运行 `python3 scripts/workspace_guard.py record-step --slug <slug> --step <n> --sha <sha>` 写入 `.agent-work/state/<slug>.json`。如需 `rebase`，先记录原分支 SHA 以便 `reflog` 撤回。

## 3. 完工检查、归档与收口

1. **全树/受影响校验**：所有步骤落地后跑通全套受影响检查（含个人仓特性文档 `Status: shipped` 更新）；未通过时带最后 40 行日志报障停手。
2. **归档 Spec 防搜索污染**：运行 `python3 scripts/workspace_guard.py archive --spec <spec.md>`（个人仓且已入库自动 `git mv`，同步写好 `archived/.ignore` 含 `*`）；若用 `repo` 模式且尚未推送，可合并进最后一步或补充收尾提交。
3. **清理临时树与交接**：执行 `git worktree list` 确认无遗留临时工作树；汇总 `git log --oneline <start>..HEAD` 与验证结果。**绝不擅自执行 `git push`**；建议下一步按需走 `diff-review` 审阅全套改动及 `pr-prep` 备料发 PR。
