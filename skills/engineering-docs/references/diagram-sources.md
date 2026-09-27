# 图示方法的公开依据

以下原文用于校准方法。规范保证表达含义，设计系统提供视觉经验，样例验证当前实现；三者不能互相替代。查阅日期：2026-09-26。

| 来源 | 采用的方法 | 适用边界 |
| --- | --- | --- |
| [C4 notation](https://c4model.com/diagrams/notation) | 抽象层次、元素类型、职责、关系、图例；符号与工具独立 | C4 不要求所有图都是同一套蓝灰方框 |
| [Carbon chart anatomy](https://carbondesignsystem.com/data-visualization/chart-anatomy/) | 标题、轴、标注、图例构成明确阅读层级 | 根据图的任务裁剪，不复制仪表盘全部控件 |
| [Carbon palettes](https://carbondesignsystem.com/data-visualization/color-palettes/) | 分类、顺序、发散与告警颜色分开使用 | 具体色值是设计选择，不是通用正确答案 |
| [Carbon Gantt](https://carbondesignsystem.com/data-visualization/gantt-charts/) | 左侧任务信息与右侧时间条对齐 | 该规范页并不表示 carbon-charts 已有甘特组件 |
| [Mermaid sequence](https://mermaid.js.org/syntax/sequenceDiagram.html) | 生命线、箭头、alt/opt/loop/par 等交互表达 | 当前文档含版本限定语法；实际渲染版本必须核对 |
| [Mermaid Gantt](https://mermaid.js.org/syntax/gantt.html) | after、时间区间、milestone、crit 与 excludes | crit 不计算关键路径，排除日期会影响显示跨度 |
| [WCAG text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) | 常规文字 4.5:1、大字 3:1 的对比要求 | 大字按规范字号定义，不把所有加粗文字都算大字 |
| [WCAG non-text contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html) | 理解内容所必需图形的相邻色对比通常至少 3:1 | 装饰线条与承载语义的边界分开判断 |
| [NIST histogram](https://www.itl.nist.gov/div898/handbook/eda/section3/histogra.htm) | 分布、偏度、离群、多峰及频数/密度 | 不等宽 bin 时不能直接用高度比较频数 |
| [NIST box plot](https://www.itl.nist.gov/div898/handbook/eda/section3/boxplot.htm) | 中位数、四分位、须线与离群点 | 须线存在不同约定，必须说明采用哪一种 |
| [Matplotlib cumulative distributions](https://matplotlib.org/stable/gallery/statistics/histogram_cumulative.html) | 精确 ECDF 与累计直方图的区别 | 累计直方图受分箱影响，只是近似 |
| [Matplotlib colormap reference](https://matplotlib.org/stable/gallery/color/colormap_reference.html) | 感知亮度、分类/顺序/发散/循环色图 | 不用彩虹色制造不存在的断层或热点 |
| [Datawrapper：图中的文字](https://blog.datawrapper.de/text-in-data-visualizations/) | 直接标注、单位就近、文字层级、减少多行居中与旋转标签 | 新闻图的语气不直接套给工程图；精确术语与条件仍需保留 |
| [Seaborn aesthetics](https://seaborn.pydata.org/tutorial/aesthetics.html) | 分离样式与载体尺寸，弱化辅助轴线与网格 | 默认主题不替代图型选择、标注和语义验证 |
| [Seaborn 0.13.2 rcmod 源码](https://github.com/mwaskom/seaborn/blob/v0.13.2/seaborn/rcmod.py) | style、context、palette 分别映射到 Matplotlib rcParams | 采用分层配置思路，不把调用同一底座说成自研统计渲染 |
| [Graphviz clusters 样例](https://www.graphviz.org/Gallery/directed/cluster.html) | 用真实分组参与自动布局，样式与节点关系分开 | 一个默认布局不代表该引擎的最佳效果，仍需端口、层级与渲染核对 |
| [Heer 与 Bostock，CHI 2010](https://idl.cs.washington.edu/papers/crowdsourcing-graphical-perception/) | 用受控任务评估视觉编码，并研究尺寸与网格影响 | 人类实验结论不能用作模型审美评分的效度认证 |

流程语义的 BPMN、DMN、Camunda 与布局工具依据沿用 `process-modeling.md`。

## 如何把经验变成能力

先保留数据与关系，再选择版式和视觉编码；同一图源局部迭代，最终在实际载体渲染。样例库用于展示可复现做法，不把某家绘图服务的输出效果误当成其内部模型或算法的证据。

自动生成不是自动正确。保留源文件、数据和复现方式，校验关键条件与数字，再看实际图。依赖关系变多、字段变长或换字体后，要重新验证；样例通过不代表任意输入已经通过。
