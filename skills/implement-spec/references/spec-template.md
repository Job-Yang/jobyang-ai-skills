# 实现 Spec 模板与双形态示例（按需查阅）

> 输出 `docs/spec/<slug>.md`（个人仓）或 `.agent-work/spec/<slug>.md`（大仓 `local` 模式）时照此骨架组织，无关小节省略。

## 1. 标准 Spec 骨架

````markdown
# <特性或重构标题>：implement spec

Source: `<上游文档路径或 none>` @ `<git-blob-sha>`

本 Spec 写定后保持只读，交由 `go-work` 分步落地。开工及续跑前用 `workspace_guard.py verify-hash` 核对上游摘要；若上游变更则先重新生成本文件。个人仓每步附加 `Spec-Step: <slug>#<n>` trailer，大仓兼容记录于 `.agent-work/state/<slug>.json`，完工后归档至 `archived/<YYYY-MM-DD>-<slug>.md`。

<一两句说清整体代码交付思路。>

## Behavior map

| 上游条目 / 需求行 | 负责模块 | 验收测试名 |
| --- | --- | --- |
| Entry：…… | `module::entry` | `test_entry_happy_path` |
| Fails：…… | `module::guard` | `test_rejects_invalid_input` |

Replaces: <被新接口级测试取代的冗余浅层单测，若无则写 none>

## Modules

### `<module>` (new | changed)

```<language>
// 真实调用方可见类型、函数签名与错误类型
```

- Invariants: <始终成立的不变量>
- Ordering: <前置/顺序约束>
- Errors: <各错误态及调用方观测结果>
- Configuration: <配置项与默认值，无合理拆分则不设>
- Performance: <复杂度或延迟边界>

Behind the seam: <模块内部替调用方藏住了什么复杂决策>

Call site:

```<language>
// 最常见调用方的使用代码
```

## Data

- Stored: <持久化结构、唯一写者>
- Existing records: <Expand-and-Contract 迁移策略、失败留下的状态> | none | reset (startup)

## Dependencies

| 依赖 | 类别 | 生产适配器 | 测试替身 |
| --- | --- | --- | --- |
| 主数据库 | local-substitutable | 连接池实例 | 本地内存/临时库 |
| 外部支付网关 | true-external | `PaymentClient` | `FakePayment` |

## Steps

1. <一提交可落地的逻辑单元，含新建或扩展测试>. After: none. Check: `<模块精确测试命令>`
2. <下一步逻辑单元>. After: 1. Check: `<模块精确测试命令>`
3. <收口接线或清理>. After: 1, 2. Check: `<受影响范围全量检查命令>`

## Not this

- <本次明确不做、不顺手重构的范围>
````

## 2. 存量安全重构示例差异（`Source: none`）

- 头部写 `Source: none`，无需上游哈希检查，完工仅归档 Spec。
- `Behavior map` 改为映射「保留的既有外部不变量 → 目标模块 → 表征测试名」。
- **`Steps` 第 1 步固定用于补齐表征测试（Characterization Tests）**并验证全绿，第 2 步起才拆模块、换实现与清理旧代码，最后一步再做等价测试迁移或清理旧冗余入口。
