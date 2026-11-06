# 绘图桥接：原生优先，旧专用能力兜底

**我们的技能负责图讲什么；Archify 负责如何绘制。** 不递归调用两套写作技能，不把 Archify 的图重新套成旧卡片风格。

## 先明确输入与能力

画之前确定：读者的问题、抽象层、主路径、分组归属、关系方向与条件。数量不是图型判据，源码或材料没证明的边不能补画。先按 `diagram-capabilities.md` 查新旧差集，必要时运行：

```bash
python3 "$SKILL_DIR/scripts/archify_bridge.py" capabilities
```

清单直接读取旧注册表，不加载数据绘图库。原生适用时按下面的Schema准备输入；需要思维导图、矩阵、图片圈注等旧专用视图时，按 `assets/diagram-templates/examples.json`／`examples_extra.json` 的旧layout准备完整输入。不要拿原生JSON直接互塞或丢字段。

阅读顺序：

1. `vendor/archify/references/authoring-defaults.md`：信息取舍、主路径、布局责任。
2. 选定图型的 Schema；新字段或枚举先查 `vendor/archify/schemas/common.schema.json`。
3. 对应 JSON 示例只看输入形式，不借用其业务节点、固定坐标或数据。

| 图型 | Schema／示例（均在 vendor/archify 内） |
| --- | --- |
| architecture | `schemas/architecture.schema.json`；`examples/web-app.architecture.json` |
| workflow | `schemas/workflow.schema.json`；`examples/agent-tool-call.workflow.json` |
| sequence | `schemas/sequence.schema.json`；`examples/cache-miss-request.sequence.json` |
| dataflow | `schemas/dataflow.schema.json`；`examples/product-analytics.dataflow.json` |
| lifecycle | `schemas/lifecycle.schema.json`；`examples/agent-run.lifecycle.json` |
| erd | `schemas/erd.schema.json`；`examples/orders.erd.json` |
| class／tree | 同名 Schema；`examples/payments.class.json`／`payment-platform.tree.json` |
| timeline／waterfall | 同名 Schema；`examples/payment-incident.timeline.json`／`checkout-request.waterfall.json` |

原生路径默认保留Classic视觉，用户明确选其他预设时才指定。不要覆盖为旧色板。旧专用路径使用已改良的浅色面／轻轮廓主题，静态产物不冒充Archify交互。固定版本记录在 `vendor/archify-version.json`，运行依赖随技能分发，不读 Trae 或其他平台的技能目录。

## 生成与检查

`SKILL_DIR` 表示当前实际加载的 engineering-docs 目录，工作材料与输出放在用户工程或本次独立产物目录，不放进 vendor。

```bash
python3 "$SKILL_DIR/scripts/archify_bridge.py" render \
  --type lifecycle --input candidate.json --output task-flow.html
```

`render` 默认 `--backend auto`：有原生Schema标记的输入走Archify；完整旧layout输入走旧模板，报告实际后端和兜底理由。同名图型按输入族区分，原生合法的 `layout` 配置对象不算旧字符串。可显式 `--backend native|legacy`，但不转换或混用输入。

原生路径执行官方 `deliver` 与 `check`，旧路径调用模板与 `diagram_check`，检查通过后才提交输出。旧定量图使用 `--standard-svg` 检查标准展示，允许合法裁剪／蒙版；脚本和HTML片段仍拒绝，也不据此声称画板原生兼容。原生默认showcase，密集图可明确standard；不得为通过检查删事实。

```bash
# 旧专用视图的自动能力兜底，输入必须是完整旧layout
python3 "$SKILL_DIR/scripts/archify_bridge.py" render \
  --type mindmap --input mindmap.json --output mindmap.html
```

旧layout需要id、name、title、subtitle、note、layout及该类型的业务字段；其SVG／静态HTML保留JSON源。维护自由 `.py`／draw.io仍按既有diagram_kit流程，桥接不自动执行任意Python文件。

- 需要仓库证据时传 `--repo-root`，按费曼方法先核对实际源码。
- 输出已存在时默认拒绝覆盖；检查旧产物并明确更新后传 `--overwrite`。
- 能力缺口允许走明确支持的旧专用类型；未知图型、原生缺Node、无效输入、几何／生成／检查失败不触发偷偷换图。旧后端也失败就明确报错，不能用残留旧文件伪装成功。
- 不自动更新依赖、不打开系统浏览器；直接JSON输入默认拒绝远程品牌抓取对象，内置品牌名仍可使用。Explainer引用的图源和其他资源也要先读取核对，未经授权不加入远程抓取；这不是全局网络沙箱。

## 浏览器验证不是可省略的一步

桥接成功只证明生成与来源检查通过，报告中的 `browser_verified=false` 是正常且明确的边界。

生成后用独立 Playwright 打开本地 HTML，按正常阅读尺寸检查：

- 主对象、入口、主路径、分支、回退与边界是否可辨。
- 所有关键条件和标签是否可见，文字是否过小、裁切或压线。
- Node Finder、聚焦、路径或步骤等实际使用的交互是否正常。
- 初始状态能否独立说明核心问题，不能全靠鼠标悬停才读懂。

无浏览器时交付源文件与“尚未验证”状态，不说图已好看或已完整验收。不要调用会自动找系统 Chrome 的入口代替独立 Playwright。

## 交付和静态文档

- JSON 是新图的可修改源，HTML 是原生交互阅读产物，必须一起保留。
- 飞书等静态正文优先使用浏览器中原生“导出图表 → PNG”。该路径已实际验证保留颜色、文字与完整条件，不要对新图沿用旧 `diagram_check --png` 的转换路径。
- 原生SVG含CSS变量等样式；本机 `rsvg-convert` 实测会将该SVG渲成黑块。SVG需要支持这些样式的浏览器或经验证的导入器，不把它当成所有转换器都兼容的普通SVG。
- 需要矢量交付时在目标环境实际打开，核对颜色、完整节点、条件和标签；不兼容时交付原生PNG与JSON／HTML，不伪称SVG静态转换通过。
- HTML 的交互不自动进入 PNG／SVG，也不保证在飞书正文里直接运行；发布独立页面只在用户要求时做。
- Archify SVG 不等于 draw.io 原生节点绑定。需要原生 draw.io 或维护旧 `.py` 时仍用改良后的旧引擎。

## 其他已桥接的入口

```bash
# 一页式图文讲解，先读 archify-reading.md
python3 "$SKILL_DIR/scripts/archify_bridge.py" explain \
  --input candidate.archify.md --output answer.html

# 两份架构输入的增删／变更对照
python3 "$SKILL_DIR/scripts/archify_bridge.py" compare \
  --base base.json --head head.json --output delta.html

# 保持面板ID，仅替换一页式讲解中的局部面板
python3 "$SKILL_DIR/scripts/archify_bridge.py" patch \
  --artifact answer.html --panel-id release \
  --replacement replacement.md --output revised.html
```

前后对照需要两份完整、可核验的输入，不是推测代码实际影响。局部面板替换只适用于 Explainer 页面；修改共享来源、结论或全文结构时，重建完整草稿并检查，不把局部修订当成全文一致性保证。
