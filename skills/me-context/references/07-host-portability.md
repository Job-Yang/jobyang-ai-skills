# 07 · 宿主可移植性：安装、降级、本地/云差异

---

## 1. 安装到支持 skill 的宿主

整目录 `cp -R` 即可（对齐仓根 README 惯例）：

```bash
# Claude Code
mkdir -p ~/.claude/skills
cp -R skills/me-context ~/.claude/skills/me-context

# TRAE
mkdir -p ~/.trae/skills
cp -R skills/me-context ~/.trae/skills/me-context
```

Codex / Cursor 等支持 Agent Skills（SKILL.md 形态，已被 30+ 平台采用）的宿主同理，复制整个目录（含 references/scripts/templates），别只拷 SKILL.md。

---

## 2. 不支持 skill 的宿主：三级降级

1. **粘贴 `ME.md` 全文**到对话开头。
2. 在 `CLAUDE.md / AGENTS.md / .cursor/rules` 放一行索引，指向本地档案位置：
   ```markdown
   # 我的个人档案在 ~/me-context-data/，需要时按 me-context 门禁读取。
   ```
3. 无文件能力时，附一段纯文本个人上下文片段。

---

## 3. 本地模型 vs 云宿主的默认 layer 差异

| 数据层 | 本地模型宿主 | 云端模型宿主 |
|---|---|---|
| L0/L1 | 可读全层 | 默认可读（经暴露预览） |
| L2 | 可读 | 按需解锁 |
| L3（健康/财务/家庭） | 可读（可配默认，仍打预览） | **逐次确认、用完不留** |
| L4（秘密） | 仅本地静态 | **永不发送** |

`gate.py --audience local|cloud` 就是模拟这个差异：本地对 L3 可配置默认读取，云端 L3 必须逐次确认。

---

## 4. 零联网声明

本技能（含 scripts/）**不含任何上传/联网能力**：init/lint/gate 三个脚本只用 Python 标准库读写本地文件，零网络请求、零外部依赖。数据自产生、自消费，随数据仓文件夹整体搬移。真实个人数据绝不进本开源仓。

---

## 5. 与 Claude Code / Codex / Cursor 原生记忆对比（实测，截至 2026-10）

> 事实来源：`_白皮书研究笔记/10_竞品实测与记忆理论.md`（官方文档 + 本机结构只读勘察）。不夸大。

| 维度 | Claude Code | Codex CLI（2026 实测） | Cursor | me-context |
|---|---|---|---|---|
| 存什么 | CLAUDE.md 人工指令 + auto memory 经验型 md（user/feedback/project/reference） | AGENTS.md 人工指令 + 从 rollout 抽的 TEXT 记忆摘要（预览） | rules（项目 mdc / 用户云同步） | 纯 md 显式档案 + inbox + L0–L4 |
| 格式/DB | 纯 Markdown，**无 sqlite/向量/全量 RAG** | Markdown + `memories_1.sqlite`（TEXT 摘要，**无 embedding/向量列**，两阶段抽取） | Markdown/`.mdc`，无独立记忆库 | 纯 Markdown（刻意无 DB） |
| 人可改/迁移 | 人可改；但 auto memory machine-local、按 repo 分目录，**迁移弱** | AGENTS.md 可；**SQLite 记忆人不可直接编辑、锁本机不可迁移** | 用户 rules 云同步；项目 mdc 随 git | **强迁移：纯 md 目录随走随拷** |
| 关系网 | 无 | 无 | 无 | **inner/close/peripheral 三圈** |

**三者共同缺**：科学采集法、主动取舍/人裁决、自我中心关系网、读侧敏感分层预览。

**诚实定位**：me-context 运行优先级不高于宿主 harness，定位互补；无感常驻抓取不如原生（Codex 后台抽取 / Claude auto memory），靠宿主常驻指令或用户唤起补。Codex 已有自动摘要记忆，不能说"它们完全没有自动记忆"；它们的纯文本指令层与人可编辑和本技能同向，差异在分层、关系网、敏感预览与可移植。

---

## 6. 能力包 vs Harness 边界（一句话）

me-context 是能力包：fail-closed 规则、可被程序调用的 gate/export、可移植 md 格式。
它管不住宿主自己伸手读文件——硬拦截要靠 Harness 层（personal-harness / Claude Code hooks），
hook 调 `gate.py --emit`，按退出码 0/2/3/1 决定放行/要确认/阻断/报错。本技能不绑定宿主，
也不复制 iLoop（研发闭环框架）的职责。

## 7. 固有边界（再强调）

按 frontmatter `layer` 元数据过滤、不做正文语义分级；写错层级工具不识别，调用方显式覆盖时责任在调用方。
硬拦截靠 Harness，本能力包管不住宿主直接 cat 数据文件。
