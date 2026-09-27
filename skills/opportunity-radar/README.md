# 机会雷达

给一个方向，收集真实需求和产品线索，整理成带来源的候选清单。可以单独装到 TRAE、Mira 或其他能读取技能文件的 Agent，不需要 iLoop，也不要求安装评分卡。

[English](./README.en.md)

## 怎么开口

> 用 opportunity-radar 扫一下个人知识管理领域。重点找用户反复抱怨、现有产品还没解决的问题，每条保留原始链接和引用。

> 根据这批用户访谈和评论整理机会清单，只用我提供的材料，别联网。

可以提供兴趣领域、目标人群、技能和资源限制、竞品链接或原始材料。没有指定方向时，默认寻找个人开发者可做的 AI 原生小产品；这个默认范围可以改。

## 它怎么判断

先从讨论、开源项目、产品发布、竞品差评和趋势数据里找信号，再用独立来源核实。每条候选要回答：谁遇到什么问题、已有做法哪里不足、什么证据支持这个判断。

候选保留来源链接、原话或数据、信号强度及理由。无法证实的内容明确标为假设。热度只能说明有人关注，不能直接证明付费需求；同一原文的转载也不能当成多份证据。

雷达负责发现线索和筛选证据。是否值得投入，可以由人直接判断，也可以另行交给评分卡；本技能不会自动启动后续流程。

## 会拿到什么

一个带元数据的 Markdown 候选清单。每条包含领域、来源、证据、信号强度、事实或假设标记，以及便于后续沿用的主题标识。

元数据使用包内的 `opc-artifact/v1` 格式。这个名称表示交接格式，使用它不需要安装 OPC。标准文件名由日期和主题生成，下载时改过名字也可以导入。

## 运行要求

- Agent 能读取技能和材料。扫描当前公开信息还需要宿主提供搜索或网页读取能力；技能不附带爬虫、账号或付费数据源。
- 没有网络时，可以分析用户提供的材料，并写清覆盖范围。
- Python 3.9+ 只用于文件校验、打包和导入，全部使用标准库。没有 Python 时仍可交付完整文本，标注尚未机器校验。

## 安装与交接

把整个 `opportunity-radar/` 复制到 `~/.trae/skills/`，或目标宿主规定的技能目录。不能只复制 `SKILL.md`。

下面的命令在本技能目录执行，由 Agent 完成。`candidates.md` 是本次生成的完整清单，接收目录由调用方指定：

```bash
python3 scripts/artifact_io.py validate --input candidates.md
python3 scripts/artifact_io.py pack --input candidates.md --out radar-result.zip
python3 scripts/artifact_io.py ingest --input radar-result.zip --output-root ./received --dry-run
python3 scripts/artifact_io.py ingest --input radar-result.zip --output-root ./received
```

云端支持附件时交付 Markdown 或 ZIP；只支持聊天时交付完整 Markdown 代码块。本地 Agent 用包内工具接收即可。新导入的材料保持待人审，同名异内容会拒绝覆盖。

明确进入 OPC 时，沿用调用方传入的范围、输出位置和审批，由编排决定下一步。独立调用不查找 iLoop 目录。

## 包内内容

| 文件 | 用途 |
| --- | --- |
| [SKILL.md](./SKILL.md) | Agent 入口、取证步骤与输出格式 |
| [sources.md](./references/sources.md) | 信息源及读取方法 |
| [search-queries.md](./references/search-queries.md) | 高信号检索词 |
| [golden-signals.md](./references/golden-signals.md) | 候选筛选依据 |
| [handoff.md](./references/handoff.md) | 独立调用和跨平台交接规范 |
| `scripts/artifact_io.py`、`scripts/scoring-rules.json` | 自包含的工件工具和共享校验规则 |

格式校验只能证明文件合规；来源是否真实、线索是否有价值，仍要回到原始材料判断。
