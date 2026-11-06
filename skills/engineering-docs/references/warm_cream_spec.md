# warm-cream 兼容说明

**暖米色板已于 2026-11-04 退役。** `theme="warm-cream"`、`palette="warm"` 等旧参数保留为兼容入口，渲染时使用统一色板，不再恢复奶油底和旧五色配色。

- 当前基础色及使用规则：`visual-design.md`。
- 当前颜色数据：`assets/visual-examples/theme.json`。
- 豆包可视化设计原则的采用边界：`doubao_style_tokens.md`。

## 历史来源

旧暖米主题曾参考 Excalidraw/open-color、D2 的暖中性视觉方向，由自定色值实现；没有复制 D2 主题文件或云厂商图标。具体旧色值与生成代码留在版本历史，不再作为新图的配色规范。

## 不变的边界

保留旧绘图 API、节点和连线，不为换色改变业务含义。SVG/draw.io 的可编辑性、端口绑定和平台限制仍按 `portable-delivery.md` 验证，主题名不构成可编辑性保证。
