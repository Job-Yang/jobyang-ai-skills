# 设计全过程工作台

这不是某个项目的评审页面，而是设计罗盘自己的固定交互框架。以后无论做网站、应用还是工具，结构线框、交互原型、视觉方案和最终高保真稿都放进同一套“空间画室”工作台。新项目只替换画板内容和设计清单，不重新编写导航、资源面板、上下文对象坞、评审检查器和关卡流转。

## 固定部分与可变部分

### 技能固定维护

- 顶部：项目身份、结构／交互／视觉定稿／设计交付四关和全局动作。
- 中央：占据主体空间的画板。支持缩放、复位和适应窗口；触控板双指直接平移，鼠标可拖动画布空白处，按住空格、中键拖动或启用手形工具时可从页面上平移。
- 左侧“项目内容”：按需展开，统一管理页面、状态、素材和产物。
- 画布工具：常驻体验、讲解、评论、对比四个入口。
- 右侧“上下文检查器”：按需展开，随当前工具显示体验提示、模块讲解、区域评论、对比选择、方案选择和融合意见。
- 底部“上下文对象坞”：随关卡显示页面、旅程与状态、视觉方案或交付物；关卡确认和导出动作放在同一区域。
- 窄屏策略：左右面板互斥。打开一侧时自动关闭另一侧，保证画布和主要操作始终可见。
- 数据：评论、关卡状态、已选方案和补充意见的本地持久化。

这些交互只在 `assets/review-framework/` 中实现。项目原型不得复制一套相似导航，也不得自行改写评论协议。

### 每个需求只提供

- 产品名、版本和当前关卡。
- 四个关卡的名称、说明和确认标准。
- 页面与方案清单。
- 画板中的真实 HTML。
- 每个大模块的五项说明。
- `index.design.json` 中的需求、页面、旅程、动作、状态和阶段边界。

换句话说，外层是设计罗盘，画板里才是当前产品。“空间画室”是唯一默认外壳，不是视觉候选，也不是项目可以自行替换的主题。

## 怎样比较多个页面和多个方案

工作台仍使用两个互相独立的筛选维度：

- 左侧“项目内容”的页面页签选择页面。
- 底部上下文对象坞在视觉定稿关选择方案；其他关卡显示该关真正需要评审的对象。

四种组合覆盖常见评审：

| 左侧 | 底部 | 画板结果 |
| --- | --- | --- |
| 全部页面 | 某一方案 | 查看这一套方案的所有页面 |
| 某一页面 | 全部方案 | 横向比较同一页面的多个方案 |
| 全部页面 | 全部方案 | 查看当前关卡全部画板 |
| 某一页面 | 某一方案 | 聚焦一张画板做细节评审 |

结构关的对象坞显示页面，交互关显示旅程和状态，视觉定稿显示候选方案或融合稿，设计交付显示网页原型、设计规格、设计令牌和评审记录。项目不需要为这些情况分别写一套导航。

## 四个关卡使用同一个网站

1. **结构**：画板放灰阶页面，确认有什么、放在哪、页面怎么连接。
2. **交互**：仍然灰阶，但核心旅程可以真实点击，确认步骤、反馈和状态。
3. **视觉定稿**：先用覆盖全部核心旅程的高保真方向候选选向；选择或融合后继续在本关打磨全部页面和关键状态。
4. **设计交付**：冻结最终网页原型，回看已解决意见，并导出设计规格和设计令牌。

关卡不是四套网站。顶部四关和所有评审能力不动，只切换中央画板、左右面板内容和底部对象坞。

## 四种工具必须直接可见

### 体验模式

- 按真实产品逻辑操作原型。
- 点击“显示可操作位置”可短暂高亮交互热区。
- 不显示模块说明，也不创建评论。

### 讲解模式

- 所有大模块显示边界和顺序编号。
- 点击模块后，右侧显示完整说明，模块附近显示简要提示。
- 支持从头讲解、上一个和下一个。
- 不触发产品业务动作。

每个大模块必须登记五项：

| 字段 | 要回答的问题 |
| --- | --- |
| `what` | 这是什么 |
| `why` | 为什么放在这里 |
| `actions` | 用户可以做什么 |
| `states` | 有哪些状态和边界 |
| `confirm` | 这一轮需要确认什么 |

### 评论模式

- 单击放置评论钉。
- 拖动框选区域。
- 不触发产品业务动作。
- 意见分为疑问、建议、必须修改。
- 还有未解决的“必须修改”时，确认关卡按钮不能进入下一关。

### 对比模式

- 右侧列出当前关卡所有页面或方案，可勾选二至四张画板。
- 画板按 A、B、C、D 标记并排显示，自动适应窗口。
- 结构和交互关用来比较页面体系；视觉定稿关用来比较同一任务的高保真方案。

四个入口常驻画布左侧。点击讲解、评论或对比时，右侧检查器自动展开；窄屏下同时收起左侧项目内容。用户进入工作台就能看见这些入口，不能要求用户先发现顶部小按钮或阅读说明。

## 新项目的接入方式

先生成固定工作台：

```bash
python3 scripts/scaffold_review.py <prototype目录>
```

生成后只编辑 `index.html` 中两个有明确注释的区域：

1. `可替换画板`：放当前产品的页面和方案。
2. `可替换设计清单`：登记关卡、页面、方案和模块说明。

其他工作台结构保持不动。

每次替换画板或设计清单后，先校验固定外壳：

```bash
python3 scripts/validate_review_workspace.py <prototype目录>/index.html
```

只有看到 `PASS layout=spatial-studio/v1` 才能启动正式评审。缺少四关、左右面板、对象坞、评审模式或画板清单不一致时，校验器会直接失败。

### 画板标识

每张画板必须同时标明关卡、页面和方案：

```html
<article
  class="rf-page"
  data-review-artboard="visual-home-a"
  data-review-stage="visual"
  data-review-page="home"
  data-review-variant="direction-a"
>
  <header data-review-module="home-header">...</header>
  <main data-review-module="home-content">...</main>
</article>
```

- `data-review-artboard`：整张画板的唯一标识。
- `data-review-stage`：属于哪个关卡。
- `data-review-page`：代表哪个产品页面。
- `data-review-variant`：属于哪个设计方案。
- `data-review-module`：页面中的大模块。

同一页面的不同方案使用相同 `data-review-page`，不同 `data-review-variant`。这样工作台才能自动完成横向对比。

业务交互热区使用：

```html
<button data-prototype-action="state:saved">保存</button>
<button data-prototype-action="page:settings">进入设置页</button>
```

画板内部有页签时，使用同一套原型动作，不为单个项目另写脚本：

```html
<button
  data-prototype-tab-group="resources"
  data-prototype-action="tab:resources:pages"
>页面</button>
<section
  data-prototype-panel-group="resources"
  data-prototype-panel="pages"
>...</section>
```

视觉候选必须使用 `data-design-journey`、`data-design-action`、`data-design-result`、`data-design-state` 和 `data-design-page` 标出自己承载的交互语义。编号来自 `index.design.json`，不能在视觉关另起一套。一个元素可以承载多个编号，属性值用空格分隔；`data-design-action` 所在元素必须同时具备真实的 `data-prototype-action`。

### 设计清单

`review-manifest` 是工作台唯一的数据入口：

```json
{
  "workspace": {
    "layout": "spatial-studio/v1",
    "leftResources": ["pages", "states", "assets", "outputs"],
    "reviewModes": ["experience", "explain", "comment", "compare"],
    "narrowPanelPolicy": "exclusive",
    "contextDock": true
  },
  "project": {
    "id": "product-topic",
    "title": "产品名",
    "subtitle": "设计全过程工作台",
    "version": "0.1"
  },
  "activeStageId": "structure",
  "stages": [
    {
      "id": "structure",
      "title": "结构",
      "summary": "页面和功能位置",
      "confirm": "确认页面是否齐全、信息层级和跳转关系是否正确。",
      "status": "active",
      "defaultPageId": "all",
      "defaultVariantId": "all"
    }
  ],
  "artboards": [
    {
      "id": "structure-home",
      "stageId": "structure",
      "pageId": "home",
      "pageTitle": "首页",
      "variantId": "base",
      "variantTitle": "结构基线",
      "title": "结构 · 首页",
      "summary": "首页的功能和信息层级。",
      "modules": [
        {
          "id": "home-header",
          "title": "首页顶栏",
          "what": "这是什么",
          "why": "为什么放在这里",
          "actions": "用户可以做什么",
          "states": "有哪些状态和边界",
          "confirm": "这一轮需要确认什么"
        }
      ]
    }
  ]
}
```

`workspace` 是公共外壳协议。新项目保留 `spatial-studio/v1`，不得删除左右资源、改变窄屏互斥策略或关闭上下文对象坞。公共脚本读取清单后，会自动生成四关导航、左侧资源、右侧检查器、上下文对象坞、确认文案和模块讲解。新增页面或方案时，只新增画板和清单记录。

旧版只有 `stage + pages` 的清单仍可打开，但新项目统一使用 `stages + artboards`。

## 持久化协议

评论写入：

```text
review-data/comments.json
```

格式：

```text
design-review-comments/v1
```

每条评论至少保存：

```json
{
  "id": "唯一标识",
  "projectId": "项目标识",
  "stageId": "当前关卡",
  "artboardId": "画板标识",
  "pageId": "页面标识",
  "variantId": "方案标识",
  "moduleId": "模块标识；自选区域可为空",
  "anchor": {
    "type": "pin 或 region",
    "x": 0.1,
    "y": 0.2,
    "w": 0.3,
    "h": 0.1
  },
  "prototypeState": "评论发生时的页面状态",
  "version": "原型版本",
  "severity": "question、suggestion 或 must",
  "status": "open、processing 或 resolved",
  "text": "用户意见",
  "reply": "处理说明",
  "createdAt": "创建时间",
  "updatedAt": "更新时间"
}
```

坐标使用画板内部的归一化比例，窗口缩放后仍能回到原位置。

关卡状态、已选方案和融合意见写入：

```text
review-data/workflow.json
```

格式：

```text
design-review-workflow/v1
```

页面刷新或重新打开后，工作台会恢复当前关卡、已确认关卡、选定方案和补充意见。

## 启动方式

正式评审统一使用：

```bash
python3 scripts/review_server.py --root <prototype目录> --port <空闲端口>
```

服务提供：

- `GET /api/health`
- `GET /api/comments`
- `POST /api/comments`
- `PATCH /api/comments/<id>`
- `GET /api/workflow`
- `PATCH /api/workflow`

浏览器本地存储只能作为服务不可写时的临时降级。正式交付必须看到两个 JSON 文件真实写入。

## 验收

每次升级公共工作台，至少验证：

1. 新建原型时脚手架明确生成 `spatial-studio/v1`，无需手写关卡栏、资源面板、评审检查器和对象坞。
2. `validate_review_workspace.py` 对完整模板通过；把布局改成旧版或删除任一固定区域时失败。
3. 四个关卡由设计清单驱动切换。
4. 左侧页面和视觉定稿关的底部方案可以交叉筛选；其他关卡的对象坞显示页面、旅程／状态或交付物。
5. 画板支持双指直接平移、空白处拖动平移、空格或手形工具从页面平移，以及直接缩放、复位和适应窗口。
6. 体验、讲解、评论和对比入口常驻画布，四种工具互不误触。
7. 点评论和区域评论能够落盘并回跳。
8. 方案选择和融合意见能够落盘并恢复。
9. 未解决的“必须修改”会阻止进入下一关。
10. 桌面和窄屏均无主要操作遮挡；窄屏左右面板互斥，顶部四关名称完整。
11. `validate_stage_contract.py --phase direction` 能证明每个方向候选覆盖全部方向必需 `J/A/S`。
12. 选定方向全量展开后，`validate_stage_contract.py --phase final` 能证明全部 `P/J/A/S` 覆盖完整。
