# 设计档案、入场分流和口味记录

每次从零开始有三个代价：同一个产品的新页面和旧页面对不上；每次都要重新问一遍；Cursor、Claude Code 这些写代码的工具不知道这个产品的设计。业界的做法是把设计上下文存成仓库里的文件：Google Stitch 和 Replit 用 `DESIGN.md`，Replit 另存 `tokens.json`，Figma Make 用 `Guidelines.md`，Lovable 用项目知识。本技能用同样的思路，并且直接导出 Google DESIGN.md 格式，别的工具也能读。

## 一、入场分流：每次开工先跑

```bash
python3 scripts/design_memory.py scan <产品目录>
```

| 路线 | 判断依据 | 怎么走 |
|---|---|---|
| 新产品 | 没有档案，也没有界面代码 | 完整四关；交付时写档案 |
| 延续 | 有 `DESIGN.md` 或 `design/tokens.json` | 读档案和最近三条决策，不重新问诊。新功能照常过结构关和交互关（简单的一版过）；视觉关只做一个沿用现有方向的版本，检查时带 `--tokens`。用户明确要换方向才回到方向候选 |
| 补档 | 没有档案，但有界面代码 | 运行 `design_memory.py extract`，把高频颜色、字体、圆角、间距映射成 tokens 草稿；做一页“现状整理”渲染给用户看（颜色、字体、按钮、表格、表单样例），用户确认或点选微调后写档案。方向简报从现状反推，标“推断” |
| 评审 | 用户要“看看哪里不好”“优化现有页面” | 按 `audit-guide.md`，可以和上面任一路线叠加 |

scan 给的是建议，用户的意图优先：有档案但用户说“这次想换个样子”，就走方向候选，旧档案作为“不像什么”的一条参考。

## 二、档案里有什么

```
<产品仓库>/
├── DESIGN.md              给所有 AI 工具读的设计说明（导出，不手改）
└── design/
    ├── tokens.json        数值的事实源（行为看原型 HTML）
    ├── direction.md       方向简报（问诊产出，见 intake-questions.md）
    ├── decisions.md       决策记录（design_memory.py record 追加）
    ├── tokens.css         Web 变量和中文排版底线（导出）
    ├── tailwind.tokens.js
    ├── DesignTokens.swift
    ├── tokens.dtcg.json   W3C 设计 token 格式，给 Figma 插件、Style Dictionary
    └── style-prompt.md    给后续写 UI 的模型读的风格提示
```

- **什么时候写**：第 4 关交付时；补档确认后；方向变更后。
- **怎么导出**：`python3 scripts/export_tokens.py design/tokens.json --targets all --brief design/direction.md --design-md DESIGN.md --prototype prototype`。`--prototype` 往原型目录里再写一份 `tokens.css`，定稿页引用这一份，交接包里的原型才带得上样式。
- **怎么检查**：`python3 scripts/design_memory.py check <产品目录>`。脚本按 tokens.json 重新导出一遍，和 DESIGN.md、`design/` 里的每份导出产物、`prototype/tokens.css` 整份比较。缺 DESIGN.md 或任何一份对不上都返回 1，并打印重新导出的命令；`design/` 里一份代码侧导出都没有时会提醒，因为导出到别的目录的文件核对不到。数值只改 tokens.json，方向判断只改 direction.md，然后重新导出；导出产物整份会被覆盖，手改会丢。
- **第一次在产品仓库里建档案前**，列出要写的文件请用户确认。之后的更新随交付进行。没有产品仓库时（自由模式的临时探索），档案写进输出目录。OPC 标准道下，档案位置服从适配器。

## 三、让别的工具也用上

- **Cursor、Claude Code、Codex**：在仓库的 `AGENTS.md`（或 `CLAUDE.md`、`.cursor/rules`）里加一句：“写 UI 前读 DESIGN.md 和 design/style-prompt.md，写完运行 lint_design.py check”。
- **Google Stitch**：读仓库根目录的 `DESIGN.md`。导出的文件能通过官方检查 `npx @google/design.md lint DESIGN.md`。
- **Figma**：用 Tokens Studio 等插件导入 `tokens.dtcg.json`。
- **代码**：引入 `tokens.css`、Tailwind 片段或 `DesignTokens.swift`。

## 四、个人口味记录（跨产品）

- **位置**：`~/.style-compass/taste.md`，可以用环境变量 `STYLE_COMPASS_HOME` 或 `--taste` 改。
- **先问再记**：口味记录存的是用户个人的选择习惯，第一次写之前要征得同意。这台机器上还没有 taste.md 时，`record` 只写产品决策，并提示先问用户。用一个点选问题问一次：“要不要在这台机器上记住你每次给了哪些方向、选了哪个、为什么否掉，下次出候选时参考？只存在本机，不进产品仓库。”
  - 同意：在 record 后面加 `--remember-taste` 重新运行，之后的 record 自动追加。
  - 不同意：运行 `python3 scripts/design_memory.py taste --off`，文件里留下关闭标记，以后不写也不问。
  - 改主意：运行 `taste --on`，或下次 record 时加 `--remember-taste`。要清空就删掉这个文件。
  - 只问一次：每次都问会打断选方向的节奏，答案记在文件里就够了。
- **写**：用户同意后，每次选定方向运行一次，产品决策和口味记录同时追加；同一天同样的内容重复运行会被跳过。

```bash
python3 scripts/design_memory.py record <产品目录> \
  --chosen "calm-tech/冷静表格" --offered "calm-tech,cn-enterprise,warm-clarity" \
  --rejected "warm-clarity（太松散，不像工具）" --words "可靠,高效,有条理" --stage 方向关
```

- **读**：问诊和写方向卡之前运行 `python3 scripts/design_memory.py taste`。
- **只用来做两件事**：
  1. 反复否掉的理由，写方向卡时主动避开。比如连续几次因为“太冷”否掉深色方案，下次深色候选要先解决“冷”。
  2. 新颖度预算：最近三次都选同一个坐标时，候选里至少放两个其他坐标。换来的坐标同样要满足简报的目标感受，不为换而换。
- **不做的事**：不把口味记录当默认答案直接套用；不跨用户共享；保持短小，只记事实（给了什么、选了什么、为什么否掉）。

为什么要有新颖度预算：AI 帮助让个人产出更好，但让所有人的产出更像（Doshi 和 Hauser，2024）；趋同主要来自工具给不同的人推荐相似的东西（Anderson 等，2024）。口味记录如果只做“投其所好”，一个人的所有产品会越做越像。

## 五、组件库什么时候做

会方便，但顺序是先档案、后组件库：

1. 方向没定之前不做组件库。换方向时，提前做的组件会全部作废。
2. 两三个页面复用同一份 tokens.json 而没有再改时，说明方向稳定了。这时由写代码的节点把高频组件（按钮、表单、表格、空状态、确认与撤销）沉淀进代码里的组件库，比如 shadcn/ui 的本地组件或项目自己的 `components/`。
3. 组件的用法写进 DESIGN.md 的 Components 一节（改 tokens.json 和 direction.md 后重新导出），这样新页面的模型知道“删除用撤销，不用确认框”这类约定。
4. 组件库和 tokens 都在产品仓库里，跟代码一起评审和版本管理。

## 来源

- [Google DESIGN.md 规范（alpha）](https://stitch.withgoogle.com/docs/design-md/specification/) 和官方检查工具 `@google/design.md`。
- [Replit：DESIGN.md 与 tokens.json](https://docs.replit.com/design/design-md)。
- [W3C 设计 token 格式（2025.10）](https://www.designtokens.org/)。
- [Doshi 和 Hauser（2024）](https://www.science.org/doi/10.1126/sciadv.adn5290)、[Anderson 等（2024）](https://arxiv.org/abs/2402.01536)：AI 辅助与趋同。
