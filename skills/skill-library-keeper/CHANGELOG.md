# Changelog · skill-library-keeper

## 0.2.0 — 2026-11-20

将技能管家从单纯静态格式体检升级为**强弱双模适配与跨技能冲突治理**尺子：

- 新增 `references/dual-model-design.md`：沉淀 L1–L4 四层物理分层法、强模型消融+弱模型底线回归双模验证、跨技能唯一主责协议与生命周期退场门禁。
- 升级 `scripts/library_doctor.py`：移除外部白名单宿主专名硬编码（改用 `--external-skills`），新增 `--max-desc-total`、`--strict`、`compute_metrics` 双模看板，新增 `B001–B005`（description 预算、隐形前置必读税、强模型拐杖密度、维护泄露）与 `X001–X004`（跨技能串联与单向豁免、极性规则打架、同技能内部矛盾、全域触发风险）共 9 条规则及对应夹具测试。
- 瘦身 `SKILL.md` description（466 字压至约 187 字），扩展 `references/health-check.md`、`admission-gate.md` 与 `README.md`。

## 0.1.2 — 2026-10-23

技术写作域静态守卫补充：检查费曼描述前置、短调研不被快答排除、方法到发布的顺序、兄弟技能上游取证与结果复用。保留正反场景，明确这些测试只验证规则文本，不是提示词路由器，也不证明真实会话召回。

## 0.1.1 — 2026-10-22

误触发收紧（bad case：调研一篇关于提示词/Agent 的外部文章时被当成技能治理调用）：明确去读、clone、解读外部 GitHub 仓库/论文/提示词实践，哪怕研究对象本身就是“技能/提示词怎么写”，也归 `feynman-explainer`；本技能只在动作对象是“用户自己这套已安装技能集合”时启用。新增跨技能路由守护测试 `tests/test_routing.py`。
