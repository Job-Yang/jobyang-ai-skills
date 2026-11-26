# Changelog · writing-craft

## 1.0.0 — 2026-11-25

依据「底座与专职分支全独立 + 文章表达层三合一（C1 架构）」正式建立统一写作入口 `writing-craft`，退役独立的 `talk-smith`、`cuihuo`、`tangshan-style` 三技能：

- **统一路由与防打架机制**：`SKILL.md` 精简为 50 余行极瘦总路由，确立「一稿一主帅（按分支单读 1 份模块文件）」与「复合型文章三步解耦（先 `feynman-explainer` 取证 → 本技能单主帅成稿 → 最后 `haohao-shuohua` 去 AI 味）」规则，消除弱路由 Harness 漏触发裸写与多技能并发规则互搏。
- **重炼 `sharing` 分支（基于 6 篇真实标杆飞书文稿）**：彻底去除原 `talk-smith` 过拟合单篇复盘的固定五字段 TL;DR、八拍戏服、`O(·)` 公式判定、问句 H2 禁令、固定 `2000–5000` 字卡线与幽默按字数配额，凝练真问题发现弧、具象现场先于抽象、短段视觉间歇、工位同事口吻与灵活小标题、真诚亮边界与外部锚点等六条核心准则，并按 4 类真实题材与 `talk`/`slides`（`sharing-formats.md`）分离按需披露。
- **升级 `opinion` 分支（原 `cuihuo`）**：在完整保留平视姿态、标题直给、零降门槛生活比喻、用词配位、反车轱辘话与 `≤120` 字锻造手记「因果环不许砍」的基础上，明确强化「无花架子、自然口语化同行直说」口吻，精简合并原多文件冗余束缚。
- **无损迁入 `tangshan` 分支（原 `tangshan-style v1.1.0`）**：完整保留经三档模型盲评验证的 `tangshan-style v1.1.0` 双模松绑正文及 `tangshan-thinking.md`（含轻模型第零节 5 步自检）、`tangshan-voice.md`、`tangshan-fidelity.md`，明确定位为带一点公众号专栏风味的激励博弈与历史周期深度长评。
- **重写 `writing_check.py`**：替换旧版过度检查，只做精准 L1 字面门禁与轻量 WARN 提示，配套完整单元测试 `tests/test_writing_check.py`。
