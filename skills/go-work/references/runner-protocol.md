# 执行器协议、Worktree 并发与重试规范（按需查阅）

> 仅在 `go-work` 调度执行步骤、拆分并行子任务或处理步骤阻塞时按需查阅。

## 1. 三档执行器选型（首步选定后整轮保持一致）

| 档位 | 适用前提 | 上下文开销控制 |
| --- | --- | --- |
| `Fork` | 宿主支持继承上下文的子代理，且当前会话很短（仅含 Spec 与规则） | 直接复用 prompt cache，工具输出留在子代理内部，不回传主会话 |
| `Fresh` | 宿主支持子代理，但当前会话已很长（经历了需求讨论或写 Spec） | 启动干净全新子代理，仅给 Spec 路径、步骤号与已落地步号 |
| `Inline` | 宿主不支持子代理，或 Spec 只有 1 步 | 主会话亲自按步落地；仅读本步相关行、重定向检查日志，上下文变长时完成当前步后停手提示开新会话续跑 |

## 2. 子代理任务简报模板

```text
落地 <spec_path> 第 <n> 步（并行任务仅在 <worktree_path> 内操作并运行全部命令）。

只读一次 Spec；严格按第 <n> 步指定的接口、数据与测试实现，已完成步骤：<landed_list>，不要重做也不要跨步。
- Spec 全程只读；如遇接口不匹配、测试无法过或需修改 Spec 未提及的模块，不提交并立刻回报阻塞原因。
- 将验证命令输出重定向至临时日志文件，失败时只读最后 40 行。
- 只暂存本步涉及文件，提交一条简洁英文/团队规范 Commit（个人仓附 `Spec-Step: <slug>#<n>` trailer）。不要 push、建多余分支或修改其它 worktree。

回执最多三行：
landed <sha> | blocked: <原因>
check: <command> exit <code>
note: <仅列后续步骤必须知道的命名或细节，没有写 none>
```

## 3. 多步并行与合并规程

1. **并行上限与退避**：同时存在多个 `ready` 步骤（`After` 均已满足且修改不同文件）时，最多同时开 `3` 路临时 detached worktree：
   ```bash
   git worktree add --detach "${TMPDIR:-/tmp}/go-work-<slug>-<n>" HEAD
   ```
   若仓库冷启动构建耗时达分钟级（如大型 Rust / C++ / iOS 工程），直接改为单工作树串行推进，避免每路重复拉依赖与冷编译浪费时间。
2. **收编与冲突处理**：
   - 核对提交摘要：`git show --stat --format='%h %s%n%(trailers:key=Spec-Step,valueonly)' <sha>`；
   - 按步号从小到大 `git cherry-pick <sha>` 回主工作树并重跑该步 `Check`；若遇冲突，立刻 `git cherry-pick --abort` 并在新 `HEAD` 上单独重跑该步，随后 `git worktree remove --force <path>`。
3. **有界重试**：主树验证失败最多带上日志末 40 行打回同一步修复 **1 次**（能继续原上下文则继续，否则新开子代理修并 amend 本步）；第 2 次仍失败立刻阻塞停手，不绕过 Spec 打补丁。
