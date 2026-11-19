# 动效工艺库（Motion Craft）

动效在界面里的作用不是炫技，而是**说明空间关系、确认手指操作已被接收、消除状态突兀跳变**。没有动效的现代网页，哪怕颜色对、排版齐，用户第一眼也会觉得“像静态 HTML 草稿”。而做错的动效（起步拖沓的 `ease-in`、每下都弹的廉价反弹、连按锁死）比没有动效更伤手感。

除极简编辑类纯静态提示外，每个由 `style-compass` 产出的高定原型，**默认至少搭载 3 类以上符合流派气质的微交互**，并无条件遵守 `@media (prefers-reduced-motion: reduce)`。

---

## 一、动效决策四问与频率铁律

写任何 `transition` 或 `@keyframes` 之前，先过四问：

1. **使用频率该不该动？** 高频操作加动画会瞬间积累疲劳感，按日常频次分级控制：

| 交互频次与场景 | 典型案例 | 动效策略 | 时长上限 |
| --- | --- | --- | --- |
| 极高频（100+ 次/天） | `⌘K` 命令呼出、快捷键切换、表格上下选行 | **零动画或瞬切**，绝不让动画抢在思维前面 | `0ms–60ms` |
| 较频繁（数十次/天） | 悬停底色、列表勾选、切换侧栏菜单、同类连续 Tooltip | **轻微色变或零延迟热切换**，不做大幅位移 | `80ms–140ms` |
| 偶发切换（几次/天） | 分段药丸切换、标签页内容替换、抽屉展开、撤销浮条 | **标准物理过渡或轻量弹簧** | `160ms–320ms` |
| 低频仪式（首屏/完成） | 首屏错峰入场、目标达成圆环扫动、里程碑状态确认 | **带方向节奏的物理弹簧与错峰** | `360ms–560ms` |

2. **它解决了什么空间或认知问题？** 能指出“来自哪个触发点 / 去往哪一层级 / 确认哪步操作”，才值得动。
3. **应该配什么曲线？**
   - **严禁把 `ease-in` 用作 UI 交互曲线**：起步慢会让按键感觉“卡了半拍”。入场、弹出与状态展开一律用 `ease-out` 族或物理弹簧，把加速度放在第 1 帧响应手指。
   - **严禁从 `scale(0)` 凭空缩放**：现实世界没有物体从零体积炸出来；弹层、菜单与浮窗须从 `scale(0.94–0.97) + opacity: 0` 起步。
   - **同组连续热切换**：首次悬停触发 Tooltip 可留短延迟防误触，一旦组内任一项已激活，相邻项之间切换延迟归零。
4. **全程是否可打断？** 状态切换优先 CSS `transition` 或 Web Animations API（WAAPI），允许用户中途连点折返并直接沿当前位置平滑归位，绝不用计时器锁死按钮点击。

**性能底线：** 只对 `transform`、`opacity`、`filter`、`clip-path`、`stroke-dashoffset`、`background-color`、`border-color`、`grid-template-rows` 等显式属性写过渡；**禁止 `transition: all`**。

---

## 二、物理缓动与原生 CSS `linear()` 弹簧库

### 1. 五套流派缓动性格表

| 动效档位 | 适用流派 / 工艺包 | 缓动曲线 | 默认时长区间 | 体感特征 |
| --- | --- | --- | --- | --- |
| 精密干脆 | `obsidian-precision` / `tactile-hardware` | `cubic-bezier(0.16, 1, 0.3, 1)` | `140ms–200ms` | 迅捷落位、几乎无拖尾，强调精密仪器确定性 |
| 温润跟手 | `porcelain-craft` / `nordic-frost` | `cubic-bezier(0.22, 1, 0.36, 1)` | `200ms–280ms` | 平顺轻柔，像瓷片滑动与雾面抽屉轻合 |
| 灵动微弹 | `tactile-mobile` / `kinetic-bento` / 游戏消费端 | `var(--spring-bouncy)` 或 `(0.34, 1.35, 0.64, 1)` | `240ms–560ms` | 真实过冲与微回弹，给指尖明快的触觉确认 |
| 精密数据 | `executive-telemetry` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | `200ms–360ms` | 匀减速收敛，适合数字滚动与图条长度变化 |
| 从容印刷 | `editorial-ink` / `liquid-glass` | `cubic-bezier(0.25, 1, 0.5, 1)` | `240ms–360ms` | 温和淡入、镜面通透与边注洗亮，不打断连续阅读 |

### 2. 三套零 JS 原生 CSS `linear()` 真物理弹簧

现代 CSS `linear()` 可直接运行弹簧微分方程的采样点，真实表达过冲、阻尼与重力收敛（零 JS 负担，且全部控制在 `700ms` 内，不触发慢动作告警）：

```css
:root {
  /* 对应 SwiftUI .snappy：高刚度、2.3% 极微过冲，适合胶囊滑块、开关、小弹层 */
  --spring-snappy: linear(
    0, 0.0677, 0.2181, 0.3941, 0.5621, 0.7053, 0.8177, 0.8999,
    0.9559, 0.9912, 1.011, 1.02, 1.023, 1.021, 1.018, 1.014,
    1.01, 1.007, 1.004, 1.002, 1
  );

  /* 对应 SwiftUI .smooth：临界阻尼零过冲，适合右侧抽屉、工作区切换、液态玻璃变形 */
  --spring-smooth: linear(
    0, 0.0539, 0.1705, 0.3058, 0.437, 0.5536, 0.6521, 0.7325,
    0.7965, 0.8466, 0.8852, 0.9147, 0.9369, 0.9536, 0.966,
    0.9751, 0.9819, 0.9869, 0.9905, 0.9931, 1
  );

  /* 对应 SwiftUI .bouncy：11.8% 明快弹性过冲，只用在开关滑块、底部速记板、完成奖赏 */
  --spring-bouncy: linear(
    0, 0.1029, 0.3304, 0.5864, 0.8104, 0.974, 1.072, 1.115,
    1.118, 1.097, 1.067, 1.037, 1.013, 0.997, 0.9883, 0.9856,
    0.9867, 0.9898, 0.9936, 0.9969, 1
  );
}
```

**分轨过渡铁律：** `opacity` 和颜色在 `1.0` 处会硬截断，绝不能直接吃过冲弹簧（会导致半段死区）。必须采用**双轨拆写**：`transform` 走 `--spring-snappy`（`420ms`）或 `--spring-bouncy`（`560ms`），而 `opacity` 单独走 `180ms cubic-bezier(0.22, 1, 0.36, 1)`。

---

## 三、十二类高定微交互配方（按需直接取用）

### 1. 首屏错峰入场（Staggered Reveal）
让标题、主卡、次要队列按 `0ms / 50ms / 100ms` 依次轻落，既树立阅读节奏又不拖慢首屏可用性：
```css
@keyframes panel-rise {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.panel { animation: panel-rise 360ms var(--ease-out) both; }
.panel:nth-child(2) { animation-delay: 50ms; }
.panel:nth-child(3) { animation-delay: 100ms; }
```

### 2. 滑动指示胶囊（Sliding Segmented Indicator）
用于顶部视角切换（如 `近 7 天 / 近 30 天`、`深空雾暗 / 冰川浅雾`）：用绝对定位的 `.seg-indicator` 配合 `transform: translateX(...)` 与 `420ms var(--spring-snappy)` 平移，比直接闪变底色高出一个档次。

### 3. 零回流手风琴展开（`0fr -> 1fr` Accordion）
展开日志、执行详情、高级配置时，**不要写 `height: auto`（不支持平滑过渡）或猜测固定 `max-height`**，改用现代 CSS Grid 行高过渡：
```css
.drawer { display: grid; grid-template-rows: 0fr; transition: grid-template-rows 240ms var(--ease-out); }
.card[data-open="true"] .drawer { grid-template-rows: 1fr; }
.drawer-inner { overflow: hidden; }
```

### 4. 空间抽屉与毛玻璃模态框（Drawer & Backdrop）
右侧详情抽屉、移动端底部加账面板、`⌘K` 指令框必须带遮罩模糊淡入（`backdrop-filter: blur(...)`）与面板位移动效，同时绑定 `Escape` 关闭与点击遮罩关闭。

### 5. 物理按压感（Tactile Press Feedback）
核心按钮、胶囊筛选、列表主操作给轻微而清晰的按压缩放（`scale(0.97)`）或工业键帽阴影塌陷（常态 `0 3px 0` → `:active` 时 `translateY(2px)` ＋ `0 1px 0`）：
```css
.btn { transition: transform 140ms var(--ease-out), background-color 160ms var(--ease-out); }
.btn:active { transform: scale(0.97); }
```

### 6. SVG 路径描绘与圆环扫描（Path & Ring Sweep）
用于任务勾选对勾（`stroke-dasharray: 24` → `stroke-dashoffset: 0`）或移动端环形进度条（修改 `stroke-dashoffset` 让环弧滑行更新），反馈感远胜于静默切换图片或 emoji。

### 7. 等宽数字动态计数（Tabular Count-up）
切换时间窗口或增减金额时，配合 `font-variant-numeric: tabular-nums` 用 `requestAnimationFrame` 在 `260ms–360ms` 内完成数字滚动过渡，防止数值宽度左右抖动。

### 8. 即时撤销浮条（Undo Toast）
可逆的删除、归档、完成操作直接执行并在底部浮出药丸撤销条，比每次打断用户的“确定 / 取消”弹窗更高级、节奏更流畅。

### 9. CSS `linear()` 分轨物理弹簧
开关滑块、底部抽屉与胶囊选中高亮用分轨写法：
```css
.spring-sheet {
  transition:
    transform 460ms var(--spring-smooth),
    opacity 180ms cubic-bezier(0.22, 1, 0.36, 1);
}
```

### 10. Blur-Replace 模糊桥接替换
切换子视图、多维灵感卡片、核心能力演示内容时，在入场节点叠加极短 `filter: blur(4px) -> blur(0)`＋`4px` 微位移＋透明度淡入（总长 `220ms–260ms`），利用视觉暂留抹平结构突变，产生原生 iOS 的顺滑切换感：
```css
@keyframes blur-replace-in {
  from { opacity: 0; filter: blur(4px); transform: translateY(4px) scale(0.99); }
  to { opacity: 1; filter: blur(0); transform: translateY(0) scale(1); }
}
.view-pane[data-entering="true"] {
  animation: blur-replace-in 240ms cubic-bezier(0.22, 1, 0.36, 1) both;
}
```

### 11. 指针跟随镜面光泽（Specular Pointer Sheen）
对液态玻璃导航岛或旗舰深色主卡，用极轻量的 `pointermove` 更新容器 CSS 变量 `--mx` / `--my`，叠加极淡 `rgba(255,255,255,0.12)` 径向镜面高光（不用重阴影，离开时平滑复位）。

### 12. 景深堆叠通知 & 起源点缩放浮层（Stacked Toast + Origin-Aware Popover）
- **Sonner 式景深堆叠通知**：连续完成多个审批/任务时，最新 1 条全宽浮在最前，后 2 条向内缩小 `scale(0.95) / scale(0.90)` 并上抬 `translateY(-10px) / -18px` 叠在下方，悬停时整体展开，均配真实“撤销”动作。
- **起源点缩放浮层**：Popover 与右键菜单绝不死板地从屏幕正中心放大，用 `transform-origin: bottom right`（或指向触发钮方位）配 `scale(0.94) -> 1`＋`opacity: 0 -> 1` 从按钮边角生长而出。

---

## 四、隐形交互微工艺

1. **同心圆角数学律**：外框圆角为 $R_{outer}$、内边距为 $P$（当 $P \le 24\text{px}$ 时），内部子元素圆角严格取 $R_{inner} = \max(6\text{px}, R_{outer} - P)$，消除视觉夹角突兀感。
2. **光学对齐与热区扩展**：
   - 图标与文字并排的按钮，图标那一侧内边距视觉上减 `2px`（`padding-left: 12px; padding-right: 14px`）才真正对称。
   - 图标按钮视觉直径哪怕只有 `28px–32px`，也通过 `.icon-btn::after { content: ''; position: absolute; inset: -6px; }` 扩展出至少 `40×40px` 的不重叠触摸/点击热区。
   - 线性 SVG 图标描边跟随相邻字重：`400` 正文旁用 `1.5px`，`600` 标题或按钮旁用 `1.75px–2px`；同一界面只用一套图标画风。
3. **软边界与 10% 慢放验收**：超出滑动边界或开关推到头时给 `delta * 0.25` 柔性阻力而非生硬卡死；在开发者工具中把动画降速到 `10%` 通检入场/切换/关闭三态，任何文字抖动、圆角裁切或层级穿透都要修平。

---

## 五、减弱动态与无障碍底线

所有带动画或平滑过渡的页面，尾部必须保留以下标准降级段，剥离大位移、缩放过冲与模糊脉冲（可保留微秒级透明度切换维持状态语义），保障眩晕敏感用户与自动化截图一致性：

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

## 方法来源

- Emil Kowalski（`animations.dev` / `emil-design-eng`）：频率分级决策、禁用 `ease-in` 与 `scale(0)`、起源点缩放、Blur-Replace、景深堆叠 Toast 与 `<300ms` 响应规范。
- Apple Human Interface Guidelines & WWDC 设计工程演讲（`Designing Fluid Interfaces` / SwiftUI `linear()` 与 `Core Animations`）：全程可打断、速度收敛、分轨弹簧与无障碍减动规范。
- Jakub Krehel（`make-interfaces-feel-better`）& Rauno Freiberg（`rauno.me/craft`）：同心圆角、光学内边距、`40px+` 热区扩展、图标描边匹配与 10% 慢放验收法。
