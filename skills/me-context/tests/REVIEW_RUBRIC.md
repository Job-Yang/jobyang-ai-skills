# REVIEW_RUBRIC · me-context 外部评审打分表（百分制）

供独立红队 agent 按表复现检验。每个维度：满分标准 / 如何复现 / 扣分点 / 反例命令。
外部评审对 v1 给 6.8 / C 线；本表固化为可重复 rubric。

## 等级线
≥9.0 优秀 · ≥8.0 良好 · 7.0 一般（C 线）· <7.0 不合格。

---

## 1. 安全默认值：fail-open vs fail-closed（25）
- **满分标准**：解析不出合法 layer 的文件，绝不静默当 L1 导出；未知/异常一律不导出或不加载，须显式 flag 才放开。
- **如何复现**：
  - `export.py --data <仓>` 对一个无 frontmatter 的枚举文件应非 0 退出并列"未分级/头部异常已跳过"。
  - `gate.py --data <仓> --domain <切到坏头部文件>` 应非 0 且不加载。
- **扣分点**：任何 `or "L1"`、缺层默认放行、坏 frontmatter 被当合法层。
- **反例命令**：去掉 examples/profile/work.md 的 `---` 头尾再 `export.py`。

## 2. 是否真实强制而非仅打印（15）
- **满分标准**：cloud 触达 L3 未 `--confirm`，`--emit` 输出里**真的没有** L3 正文（不是只打印一句提醒）；L4 任何参数组合都不输出正文。
- **如何复现**：
  - `gate.py --domain health --audience cloud --emit` 应 rc=2，stdout grep "高血压" 计数=0。
  - `gate.py --layer L4 --emit` 应 rc=3，无正文。
- **扣分点**：HOLD/BLOCK 只打印却仍把内容吐进 stdout。

## 3. 负面测试覆盖（15）
- **满分标准**：tests/ 里有反面 fixture 覆盖——无头部、小写层、缺结尾 ---、错位 L4、未知 domain、L3 未 confirm、L4 任意参数。
- **如何复现**：`tests/fixtures/neg/`；`run_selftest.sh` 每步自动判 PASS/FAIL，set -e 失败即非零。
- **扣分点**：只有正向用例、靠人眼读输出。

## 4. lint/gate/export 三工具一致性（15）
- **满分标准**：同一份坏 frontmatter，三工具结论一致（lint ERROR / gate 不加载非 0 / export 跳过非 0）；公共逻辑集中 `scripts/mectx_common.py`。
- **如何复现**：对 neg/bad-noend.md 分别跑 lint、gate 切片命中、export，三者都判异常。
- **扣分点**：一个判 L3、一个判无头部；重复实现漂移。

## 5. 跨平台可移植 / 零第三方依赖（10）
- **满分标准**：纯 Python3 标准库（`import mectx_common` 同目录），无 pip 依赖；md 目录随走随拷。
- **如何复现**：`grep -rE "^import (yaml|requests)" scripts/` 为空。
- **扣分点**：引入第三方包、写死绝对路径。

## 6. 文档与代码一致（10）
- **满分标准**：SKILL.md / references 描述的退出码、flag、domain 与脚本 argparse 一致；无 `--domain family` 残留。
- **如何复现**：`grep -rn "family\|drafts" scripts/ SKILL.md` 仅剩文件名 `06-privacy-family`。
- **扣分点**：文档写 dry-run、代码已 --emit；flag 名对不上。

## 7. DRY / 公共模块（5）
- **满分标准**：frontmatter 解析/layer 规范化/domain 映射/路径安全只在 `mectx_common.py` 一份。
- **扣分点**：三个脚本各写一份 parse_frontmatter。

## 8. 触发与加载开销（5）
- **满分标准**：无关任务零加载；默认 md 只含 L0/L1；inbox 永不被 gate/export 读取。
- **如何复现**：`gate.py --task "红烧肉怎么做"` 零加载；默认 md grep 敏感串=0。
- **扣分点**：闲聊也读画像、inbox 被打包。

---

## 速查反例命令清单
```
python3 scripts/gate.py --data examples --domain family            # 应 rc=1 未知 domain
python3 scripts/gate.py --data examples --domain health --audience cloud --emit   # 应 rc=2 无正文
python3 scripts/gate.py --data examples --layer L4 --emit          # 应 rc=3
python3 scripts/export.py --data examples                          # 默认仅 L0/L1，敏感串 0
python3 scripts/lint.py --data tests/fixtures/neg                  # 应 rc=1
```

---

## 关系网专项验收（不复用历史评分）

| 必查项 | 可复现检查 | 失败判定 |
|---|---|---|
| 多人、多层 | 虚构 48 人 4 跳，图模型 180 人 6 跳；全部显示和逐层展开 | 缺实体、重复实体、死循环、自动造边 |
| 图而非平铺列表 | 选中人物→路径→关联人→换中心→返回；全图仍保留跨分支边 | 只换文本，不能探索真实邻居，亲疏圈冒充距离 |
| 可读性 | 桌面/390px 真实矩形、中文完整姓名、初态可见；放大工作区 | 节点重叠、姓名被缩到不可读、页面横向溢出、中心藏在长列底下 |
| 关系语义 | parent_of/child_of 从两端各走一次，断连/同名/多边反例 | 父母子女颠倒、无关系假连接、路径被当作亲密度/影响力 |
| 安全和回归 | 同一过滤 payload 导航；off/facts/full/cloud 各检查；既有健康回归 | 通过搜索/展开绕过隐私过滤、夹带 inbox/L4、改动真实健康事实 |

## 固有边界（不算扣分，须在报告里声明）

工具只按 frontmatter `layer` 元数据做确定性过滤，**不做正文语义分级**：用户把高敏内容写错层级、或
写进低层文件，工具不识别（调用方显式 `--layer` 覆盖时责任在调用方）。写入协议与 lint 提醒错位，
但不能替代正确标注。宿主绕过本技能直接读文件不受 gate 约束（见能力包 vs Harness 边界）。
