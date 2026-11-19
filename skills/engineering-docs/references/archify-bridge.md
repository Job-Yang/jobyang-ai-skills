# 统一输入、生成与交付

**工程图统一用 `diagram_kit`。** Archify固定版本编译器与查看器是内部组件，不要求作者选后端；随包版本、许可证和本地装配适配记录在回执中。

## 作者输入

```json
{
  "version": 1,
  "type": "workflow",
  "meta": {"title": "核对后才交付"},
  "payload": {
    "schema_version": 2,
    "lanes": [{"id": "review", "label": "核对"}],
    "nodes": [{"id": "check", "lane": "review", "col": 0, "type": "backend", "label": "核对证据"}],
    "edges": []
  }
}
```

- `meta.title`必需；subtitle／note缺省保持缺省，locale默认zh-CN。不要为模板检查补造文案。
- payload仍遵守对应图型Schema，不把时序、状态、实体等压成通用卡片。
- 已有typedJSON或layoutJSON可直接导入，转换仅改变外壳，字段与条件原样保留；混合Schema拒绝。同名不同Schema见 `diagram-capabilities.md`。
- 自由图由已审阅Python内存API `d.to_input()`得到统一JSON；`d.deliver()`与CLI进入相同链路。未知 `.py` 文件不自动执行，也不从SVG反推完整作者源。

## 只读取所选Schema

| 图型 | 依据（vendor/archify内） |
| --- | --- |
| architecture | schemas/architecture.schema.json；examples/web-app.architecture.json |
| workflow | schemas/workflow.schema.json；examples/incident-response.workflow.json |
| sequence／dataflow／lifecycle | 对应同名Schema与随包示例 |
| erd／class／tree／timeline／waterfall | 对应同名Schema与随包示例 |

专用payload参考 `assets/diagram-templates/examples.json`／`examples_extra.json`，只借输入结构，不复制业务事实。自由对象、成员及端点见 `diagram-system.md`。

## 统一命令

```bash
python3 "$SKILL_DIR/scripts/diagram_kit.py" render \
  --input candidate.json --output diagram.html --formats svg,png
python3 "$SKILL_DIR/scripts/diagram_kit.py" check diagram.receipt.json
```

生成source.json＋完整scene.json＋自包含HTML＋最终receipt.json；请求的静态格式一并生成。`--theme light|dark|plain`来自同一v4主题源；默认light。输出已存在须明确 `--overwrite`，拒绝覆盖作者源和软链接；先冻结源、staging检查，回执最后提交。生成或检查失败不换图、不以残留文件报成功。

统一scene是渲染后传输模型，不是第二套作者DSL：保存稳定ID、正文／代码／标签／行、角色／状态、几何、组成员、真实边和注释，另保留图型专属payload。几何来自内存或组件编译结果，不借SVG猜作者源；未声明的包含关系保持unknown。

## 检查、浏览器和静态格式

- 最终页面完成主题／语义／source装配后，运行typed scene与SVG语义检查；适用图型再运行随包 `vendor/archify/scripts/check-render-output.mjs`。容器与卡片区分，不因漏识别错边而放行。
- receipt包含source、scene、组件、主题及每个成品指纹。`check`回读产物和页面内嵌索引，变更即失效；不得用组件原回执证明装配后页面。
- Playwright独立Chromium完成DOM识别、几何与导出观测；不启动系统Chrome。实际读图、正文尺寸、条件／回环、查找／聚焦／路径需独立验收。自动检查不代表用户喜欢；`browser_verified=false`明确尚未独立验收。
- SVG固定主题并解析CSS变量／继承样式，不交付默认dark的auto SVG给rsvg。PNG使用相同清理过的SVG，不能残留查找／聚焦／路径淡化。
- draw.io仅free支持真实可编辑对象与绑定，其余类型先拒绝；XML检查不等于已在draw.io应用导入。HTML交互不会进入SVG／PNG，也不会自动进入飞书正文。

## 依赖与许可

统一交付需要Node.js 18+及Playwright＋匹配Chromium，先复用本机缓存。缺依赖不降级、不自动更新Archify／Node。统计依赖可经用户批准并设置 `ENGINEERING_DOCS_ALLOW_PIP=1` 后用 `bootstrap.py` 隔离到 `.deps/`；`ENGINEERING_DOCS_DEPS_DIR` 指定数据目录内 `.deps`，不写系统 pip 环境。源码brand远程对象默认拒绝，内置品牌名可用；这不是全局网络沙箱。

固定上游来源见 `vendor/archify-version.json`，上游文件及LICENSE／NOTICE不改；`diagram_adapter.mjs`在生成页内装配token、语义和静态导出适配，作为本地适配明确记录，不冒称生成页是上游原生成物。

## 保持兼容的阅读入口

`diagram_kit explain／compare／patch`委托原有实现，参数与写作方法不变；`archify_bridge.py`仍是兼容门面，render／capabilities委托统一系统。解释页、架构前后对照、面板修订的内容方法仍见 `archify-reading.md`，本轮不重写。
