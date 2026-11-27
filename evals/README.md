# 路由评测数据仓（仅收真实翻车案例）

本目录随仓库版本管理，**故意不固化 AI 编造的静态考卷**，避免技能 `description` 演化成讨好固定题目的“背题专家”。

## 目录定位

- `real-badcases.jsonl`：**唯一长期留存的静态用例文件**。只收你在真实对话里确实踩过的漏触发、乱触发、相邻技能误抢或覆盖真空，只做「旧坑防复发」，不作刷分 KPI。
- `ablation/`（二期预留）：核心技能大改减负或模型换代时的 `bare vs old vs new` 盲评记录。

## 日常使用方式

### 1. 随手往真实翻车池加一条

遇到「该触发没触发」「不该触发乱触发」「两个技能抢活」时，在 `evals/real-badcases.jsonl` 追加一行（`query` 尽量保留当时自然口语原话；若原话恰巧点出了英文技能名，可加 `"allow_literal_slug": true`）：

```json
{"id": "RB002", "category": "real-badcase", "query": "原始口语请求", "expected": "期望技能或NONE", "forbidden": ["曾误抢的技能"], "source": "2026-11-27-对话原例", "note": "一句现象说明"}
```

单独校验真翻车池格式与技能存在性：

```bash
python3 skills/skill-library-keeper/scripts/route_eval.py audit evals/real-badcases.jsonl skills --allow-partial --strict
```

### 2. 全库活卷盲测（现出活卷、考完即弃、改后换卷）

```bash
python3 skills/skill-library-keeper/scripts/route_eval.py blueprint skills --shuffle --out-catalog /tmp/cat-a.json --out-blueprint /tmp/bp.json
# 按 /tmp/bp.json 现场生成临时口语活卷 /tmp/probe.jsonl，合并 real-badcases.jsonl 后审计并导出盲测题单：
python3 skills/skill-library-keeper/scripts/route_eval.py audit /tmp/run-cases.jsonl skills --strict --export-blind /tmp/blind.jsonl
# 由干净上下文子代理盲选后输出体检雷达（不打综合总分）：
python3 skills/skill-library-keeper/scripts/route_eval.py score /tmp/run-cases.jsonl /tmp/pred-a.jsonl /tmp/pred-b.jsonl --root skills --model-label Pro
```
