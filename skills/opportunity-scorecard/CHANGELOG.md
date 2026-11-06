# CHANGELOG

## 0.3.1 — 2026-10-16

- 新增：`scripts/score.py` 结果与卡片加"尺子置信度声明"——先验权重/档位/地基门/dark_horse 在 `method_caveats` 与卡片末尾显式标注 `statistical_significance: false`（非统计显著），composite 两位小数仅为交接复算对齐。防把先验尺子当成数据结论。
- 新增：证据对抗自检（不阻断，只警告）——`evidence_warnings`：同一证据被多个维度复用、或证据无链接且含"内部消息/据传/听说"等不可验证措辞，出卡时列在"证据警告"节，需人复核。
- 新增：`examples/` 三个对抗样例——`scoring.all-ten.json`（全 10 分，composite=10 不溢出）、`scoring.all-one.json`（全 1 分，落 reject 不逃逸）、`scoring.contradictory.json`（维度互相矛盾 + 同料复用 + 无链接证据，不崩溃、警告可见、卡仍过冻结校验）。
- 新增：回归 6 条（全 10/全 1/矛盾输入/复用警告/不可验证警告/卡片含非统计显著声明），全套回归 16 条通过。

## 0.3.0 — 2026-10-16

- 修复：`scripts/score.py` 的 main() 包 try/except。输入缺维度/非法/JSON 坏掉时，不再抛裸 traceback，改为输出与 artifact_io 同形的 JSON 错误信封（`{"status": "rejected", "error": ...}`）到 stderr 并 exit 1；同时修掉尾部 `main()` 丢弃返回值导致错误时 exit 0 的问题（原诊断 P1/T1）。
- 修复：打分最小步长 0.5。每维分数必须是 0.5 的整数倍，6.75 这类伪精确小数直接打回；`examples/scoring.synthetic.json` 同步改为全维 6.5 的合法值（原诊断 P1）。
- 修复：topic slug 正则收紧到与冻结版 artifact_io 的 SLUG 逐字一致（不允许连续/前导/尾部连字符），新增回归用例 `watch--sedentary` 两边一致拒绝（原诊断 P2）。
- 修复：placeholder 拦截词表与 artifact_io 对齐并做超集（N/A 家族、TODO、待补、无、省略号等入口先拦）（原诊断 P2）。
- 修复：score.py 渲染卡片的信封 `opc_version` 从 0.2.2 改为 schema 0.2.0，与冻结 seal 口径统一，不再把 kit 版本写进信封。
- 新增：`examples/` 两个边界用例——`scoring.foundation-reject.json`（地基门命中，综合分 7.11 仍 reject）、`scoring.dark-horse.json`（composite 5.0、申辩有形状、dark_horse=true）；`tests/test_scorecard_regression.py` 共 10 条回归（原诊断 P2）。
- 重构：`references/scoring-method.md` 权重口径诚实化——写明三组权重是先验权重、没有经验来源，结论靠档位判断、composite 只辅助排序，临时改权重是自欺；保留地基门与 dark_horse 逃生舱（原诊断 P1）。
- 新增：vendoring 落地（check_vendored.py + vendor-manifest.json）；description 重写为前 50 字自包含；frontmatter 只留 name/description。
