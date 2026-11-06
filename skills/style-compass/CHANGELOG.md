# CHANGELOG

## 4.3.0 — 2026-10-16

本轮按设计节点评审报告逐条修复，行为约定不变，只收紧门禁、统一命名、压缩入口。

- 修复（P1-1 安全）：`review_server.py` 的 POST/PATCH 加 Origin 白名单。只放行 `http://127.0.0.1:<port>`、`http://localhost:<port>`、无 Origin（Agent 脚本）和 `Origin: null`（file:// 直开）；其他来源一律 403。恶意网页不能再往本地评审数据写假评论。
- 修复（P1-3 进程）：`review_server.py` 设 `daemon_threads=True` 并注册 SIGTERM/SIGINT 优雅停机，端口随 `server_close()` 释放；SKILL 写明评审完必须关闭服务。
- 修复（P1-2 命名漂移）：阶段边界键统一为脚本侧的 `direction`/`final`。`examples/stage-contract.example.json` 与 `export_spec.py` 的 `visualDirection`/`visualFinal` 改名；工作台外壳 stage id `visual-final` 统一为 `final`（含 template.html、review-framework.js、校验器）。旧拼写不再通过校验。
- 修复（P0-1 寄生模块）：经静态确认 + 全量测试实证，`scripts/scoring-rules.json` 只被冻结的 `artifact_io.py` 的 assess（机会评分）分支读取，设计流程完全不碰，予以删除。本包只 vendored 交接信封 `artifact_io.py`，不含 OPC 机会评分规则。
- 修复（P0-2 渐进式披露）：`SKILL.md` 从 276 行压缩到约 120 行，首页改为「关卡 → 必读 reference → 必跑脚本 → 产物」路由表，长段细节留在 references，消除概括重复。
- 修复（P2-1）：`compare_variants.py` 变体与输出不同目录时默认拒绝输出（iframe 相对引用会全部空白），确认后果后加 `--allow-cross-dir` 才继续。
- 修复（P2-2）：SKILL 诚实标注 `SMELL-EXAMPLE-COPY` 只拦逐值照抄示例色板，不拦微调照抄；方向必须来自本产品 direction 简报。
- 修复（P2-3）：新增本文件。
- 新增（vendoring）：随包附带 `scripts/check_vendored.py` 与 `scripts/vendor-manifest.json`，发布前跑 `python3 scripts/check_vendored.py` 自检 vendored 文件一致性。
- 修正：`references/handoff.md` 的信封示例从误抄的 `opc_node: prd` 改为本节点的 `opc_node: design`。
- 测试：46 个原有用例全绿；新增命名回归 1 条、评审服务安全/停机回归 5 条。
