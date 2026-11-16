# CHANGELOG

## 4.5.0-candidate — 2026-11-07

本候选只升级提交给既有评审链路的视觉与交互方法；4.4 quick 分流、full／OPC 阶段契约、固定工作台、服务器、runtime、vendored 脚本和用户批准边界均未改变。

- 新增 `design-kernel.md`：从任务与真实内容选择主对象／主动作，连续决定主体尺度与位置、辅助阅读顺序、字形角色、色面层次和一处产品专属重点，并给出大工作区与小弹层示例。
- 参考校准改为从一至两个适用正向样例抽取比例、密度、字体角色、组件和真实内容，记录适用与差异；高上限页面可 comp-led，操作型 UI 可 code-led，图像差异不充当交互证据。
- `visual-craft.md` 增加逐案质量底线：主对象、明确动作、协调字形／色面、真实内容和完整组件／状态全部成立后，才比较候选差异；名称和说明拿掉后仍须辨认主次与方向。
- 新增 `interaction-craft.md`：按目标、动作、前置条件、状态、反馈、恢复和上下文组织路径；区分排队、运行、等待输入、失败与验收，并明确动画可打断不等于业务任务可取消。
- 补充成熟 primitive、焦点初始与归还、Esc、键盘／拖拽替代、触控、极端内容、响应式、减少动态与动效节制；Web／React 特例不升格为 native 约束。
- 新增方法契约回归，固定入口引用、来源版本、逐案质量顺序与平台边界。方法参考 heydamir/unslop（CC BY 4.0，Damir Sokolovsky）、pbakaus/impeccable（Apache 2.0）及 design／interaction 内核列出的固定 commit。

## 4.4.0 — 2026-11-07

本轮新增按风险分流的 quick 路径，降低基础 UI 的流程成本；full／OPC 的阶段契约、固定工作台和正式门禁保持不变。

- 入场先选 quick／audit／full：基础单页、简单组件、明确需求和“直接做一版”默认 quick；仅现有页面评审走 audit；多页面跨角色复杂流程、新设计系统、明确完整评审与 OPC 走 full。分流同时检查行为风险，不只按页数。
- quick 合并结构、交互与视觉，免重复口味问诊、8–12 想法、2–4 候选、固定工作台、持久评论服务、全量 DESIGN 建档和全部平台 tokens 导出；仍交付完整 prototype、实际 tokens、简短说明与假设。
- quick 使用实际 tokens 跑 final lint，并要求独立 Playwright 点验桌面、移动与关键操作；集中修复最多一轮。浏览器不可用时必须标“未视觉验收”，测试通过不作为审美证明。
- quick 与 full 共用五行以内的整页视觉方向和表现力原则；quick 多方案只在明确要求或真实分歧时给 2–3 个可见差异候选，full 原多方向协议不变。
- stage-contracts 与 review-framework 明确仅适用于 full／OPC；个人口味持久化、外部发布与危险动作授权边界不变。
- 方法参考 heydamir/unslop（commit `a6f121eee5f29c2f74976b75456feae8b66afb3a`，CC BY 4.0，Damir Sokolovsky）与 pbakaus/impeccable（commit `687bc381bc9091bf252c0a05303640561014a425`，Apache 2.0），仅吸收原则并自主表述。

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
