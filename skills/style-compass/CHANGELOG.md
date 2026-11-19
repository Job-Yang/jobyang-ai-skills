# CHANGELOG

## 4.7.0 — 2026-11-19

拓展多流派审美库、引入自由基因混搭引擎，并炼化业界顶尖动效与交互细节规范（完全保留 `4.6.0`、`4.5.0-candidate` 与既有 `full`/OPC 全套契约）：

- **新增 4 套高风格反差工艺包（扩展至 9 套）**：新增 Apple 液态磨砂玻璃 `liquid-glass`（悬浮岛折射＋135° Fresnel 亮边＋严禁玻璃叠玻璃）、极光雾面双态工作台 `nordic-frost`（分离式圆角雾面侧栏＋深空雾暗/冰川浅雾切换＋Sonner 堆叠撤销）、精密触感工业 `tactile-hardware`（哑光阳极铝机身＋凹陷 OLED 示波窗＋3D 塌陷机械键帽）与灵动便当展厅 `kinetic-bento`（12 列高反差材质拼贴＋指针跟随微光）。
- **自由工艺基因混搭引擎（`references/craft-genome.md`）**：打破“固定风格 9 选 1”限制，提出五条正交工艺轴（表面物理、空间构图、色温光氛、字形配对、动效性格）、三根创作旋钮（`VARIANCE / MOTION / DENSITY`）与跨案 Remix 协议，以及 Web 工艺到 Apple 原生 SwiftUI API 的映射表。
- **业界顶尖动效与隐形交互工艺炼化（`references/motion-craft.md`）**：吸收 Emil Kowalski / animations.dev（频率分级、禁 `ease-in` 与 `scale(0)`、起源点缩放浮层、Blur-Replace 模糊桥接、景深堆叠 Toast）、Apple Fluid Interfaces（全程可打断、原生 `linear()` 三套物理弹簧与分轨过渡）、Jakub Krehel 与 Rauno Freiberg（同心圆角数学律、光学内边距、`40×40px` 热区扩展、10% 慢放验收法）。
- **画廊升级（`scripts/build_gallery.py`）**：候选上限扩至 12 个以容纳多流派完整展廊，优化多标签横滑排版与同心圆角，补充 `--spring-snappy` 按压回弹与 `ArrowLeft / ArrowRight`、`1–9` 键盘快切。

## 4.6.0 — 2026-11-19

升级为高审美下限与物理动效驱动的 UI 生成引擎（兼容保留 `4.5.0-candidate` 与既有 `full`/OPC 全套契约）：

- **5 套高定视觉工艺包（`assets/craft-packs/*.html` + `*.png` + `references/craft-packs.md`）**：内置精密暗色仪器 `obsidian-precision`、温润瓷感节奏 `porcelain-craft`、纸墨编辑专栏 `editorial-ink`、精密数据驾驶舱 `executive-telemetry` 与灵动消费端 `tactile-mobile`，将普通用户的日常意图直接翻译为带视觉锚点图、表面光影配方、强字阶反差、细线 SVG 图标和可点样本的起点。
- **物理动效体系（`references/motion-craft.md`）**：补全 5 套流派缓动性格与 8 类微交互配方（首屏错峰、滑动分段胶囊、`0fr -> 1fr` 零回流手风琴、空间抽屉、按压反馈、SVG 对勾/圆环扫描、等宽滚动计数、即时撤销浮条），统一保留 `prefers-reduced-motion` 降级底线。
- **高定直选路径 `explore` 与极简画廊（`scripts/build_gallery.py`）**：需求模糊或关键新品可跳过灰阶线框，直接用 2–3 个不同工艺包并行产出可点关键屏并装入单页切换/并排画廊直选，选定后再锁 tokens 扩全页；同时保留 `full` 正式四关工作台。
- **独立双端截屏与审美自查（`scripts/capture_preview.mjs` + 六点审视清单）**：零额外依赖自动发现本机 Playwright Chromium，一键捕捉 1440×900 桌面图、390×844 移动图及点击交互态，测量横向溢出与控制台报错。
- **放宽半透明物理光影误报（`scripts/lint_design.py` + `references/cjk-typography.md`）**：允许低彩度半透明阴影/顶部高光及基于已注册 token 色推导的半透明光晕通过 `TOKEN-COLOR` 检查；放开主标题与英雄指标 `700` 粗体字重，继续严守中文字体回退、正文字号行高与 `tabular-nums` 等宽底线。

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
