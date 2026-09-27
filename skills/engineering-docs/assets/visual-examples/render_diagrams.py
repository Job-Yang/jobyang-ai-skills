#!/usr/bin/env python3
"""Reproduce the curated technical diagrams; this is not a general layout engine.

Python standard library only. SVG text stays editable. The accompanying README
defines synthetic fixtures and the limits of these examples.
"""
import argparse
import html
import json
from pathlib import Path

THEME = json.loads(Path(__file__).with_name("theme.json").read_text())
INK, MUTED, LINE = THEME["ink"], THEME["muted"], THEME["line"]
COLORS = THEME["colors"]


class Figure:
    def __init__(self, key, kind, title, subtitle, height, conclusion):
        self.key, self.kind, self.title = key, kind, title
        self.height, self.conclusion = height, conclusion
        self.nodes, self.edges, self.parts = {}, [], []
        self.rect(0, 0, 680, height, "#FFFFFF", "none", 0)
        self.rect(32, 26, 32, 4, COLORS["blue"][0], "none", 0)
        self.text(76, 33, f"{key[:2]}  /  {kind}", 13, MUTED, 600)
        self.text(32, 74, title, 26, INK, 600)
        self.text(32, 103, subtitle, 14, MUTED)
        self.path(f"M32 {height-76} H648", "#D8E0EA", 1)
        self.text(32, height - 47, conclusion, 14, INK, 500)
        self.text(32, height - 10, "engineering-docs · 合成示例 · 680px 正文版", 12, MUTED)

    def rect(self, x, y, w, h, fill, stroke=MUTED, radius=10, extra=""):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
                          f'rx="{radius}" fill="{fill}" stroke="{stroke}" '
                          f'stroke-width="1.2" {extra}/>')

    def text(self, x, y, value, size=14, color=INK, weight=400, anchor="start"):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
                          f'font-weight="{weight}" text-anchor="{anchor}">'
                          f'{html.escape(str(value))}</text>')

    def path(self, d, color=MUTED, width=1.8, dash=False, marker=None, extra=""):
        dash_attr = 'stroke-dasharray="6 5"' if dash else ""
        end = f'marker-end="url(#{marker})"' if marker else ""
        self.parts.append(f'<path d="{d}" fill="none" stroke="{color}" '
                          f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round" '
                          f'{dash_attr} {end} {extra}/>')

    def section(self, x, y, w, h, title, tone="gray"):
        dark, light = COLORS[tone]
        self.rect(x, y, w, h, light, THEME["border"][tone], 8)
        self.text(x + 16, y + 27, title, 15, INK, 600)

    def node(self, nid, x, y, w, h, name, detail="", tone="blue", solid=False):
        dark, light = COLORS[tone]
        self.nodes[nid] = {"name": name, "detail": detail}
        self.parts.append(f'<g id="{nid}">')
        self.rect(x, y, w, h, light if solid else "#FFFFFF", dark, 8)
        cy = y + h / 2
        tx, anchor = (x + 14, "start") if detail else (x + w / 2, "middle")
        self.text(tx, cy - 3 if detail else cy + 5, name, 16,
                  INK, 600, anchor)
        if detail:
            self.text(tx, cy + 20, detail, 14,
                      MUTED, 400, anchor)
        self.parts.append("</g>")

    def diamond(self, nid, x, y, label, w=146, h=70, tone="amber"):
        dark, light = COLORS[tone]
        self.nodes[nid] = {"name": label}
        self.parts.append(f'<path id="{nid}" d="M{x} {y-h/2} L{x+w/2} {y} '
                          f'L{x} {y+h/2} L{x-w/2} {y} Z" fill="{light}" '
                          f'stroke="{dark}" stroke-width="1.5"/>')
        self.text(x, y + 5, label, 15, INK, 600, "middle")

    def bar(self, nid, x, y, w, label):
        self.nodes[nid] = {"name": label}
        self.rect(x, y, w, 4, INK, "none", 2, f'id="{nid}"')

    def label(self, x, y, value, color=MUTED):
        width = sum(14 if ord(c) > 127 else 7.5 for c in value) + 12
        self.rect(x - width / 2, y - 15, width, 21, "#FFFFFF", "none", 3)
        self.text(x, y, value, 14, color, 400, "middle")

    def edge(self, source, target, d, label="", xy=None, tone="gray",
             dash=False, opened=False):
        dark = LINE
        eid = f"e{len(self.edges) + 1}"
        self.edges.append({"id": eid, "from": source, "to": target, "label": label})
        self.path(d, dark, 1.5, dash, f"{tone}-{'open' if opened else 'arrow'}",
                  f'id="{eid}" data-from="{source}" data-to="{target}"')
        if label and xy:
            self.label(*xy, label, dark)

    def save(self, out):
        for edge in self.edges:
            assert edge["from"] in self.nodes and edge["to"] in self.nodes
        defs = []
        for tone, (dark, _) in COLORS.items():
            dark = LINE
            for opened in (False, True):
                suffix = "open" if opened else "arrow"
                shape = (f'<path d="M1 1 L8 5 L1 9" fill="none" stroke="{dark}" '
                         'stroke-width="1.5"/>' if opened else
                         f'<path d="M1 1 L8 5 L1 9 Z" fill="{dark}"/>')
                defs.append(f'<marker id="{tone}-{suffix}" viewBox="0 0 10 10" '
                            'refX="8" refY="5" markerWidth="7" markerHeight="7" '
                            f'orient="auto">{shape}</marker>')
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="680" '
               f'height="{self.height}" viewBox="0 0 680 {self.height}" role="img">'
               f'<title>{html.escape(self.title)}</title>'
               f'<desc>{html.escape(self.conclusion)}</desc><defs>{"".join(defs)}</defs>'
               '<g font-family="Arial, PingFang SC, Noto Sans CJK SC, sans-serif">'
               + "".join(self.parts) + "</g></svg>\n")
        (out / f"{self.key}.svg").write_text(svg, encoding="utf-8")
        return {"id": self.key, "type": self.kind, "title": self.title,
                "conclusion": self.conclusion, "nodes": self.nodes, "edges": self.edges,
                "source": f"{self.key}.svg", "preview": f"{self.key}.png"}


def context():
    f = Figure("01-context", "上下文图 · 目标", "先看清系统与外部的边界",
               "文档检查系统｜只展示参与者与系统间关系", 570,
               "内容源与通知服务属于外部；检查逻辑归目标系统。")
    f.node("author", 42, 158, 152, 72, "作者", "提交文档 · 看结果", "gray")
    f.node("system", 248, 276, 200, 96, "文档检查系统", "校验材料并生成报告", "blue", True)
    f.node("source", 484, 158, 154, 72, "内容源", "提供文档版本", "teal")
    f.node("reviewer", 42, 395, 152, 72, "评审人", "读取检查报告", "gray")
    f.node("notify", 484, 395, 154, 72, "通知服务", "投递完成通知", "purple")
    f.edge("author", "system", "M118 230 V310 H248", "提交 / 查询", (183, 300), "blue")
    f.edge("system", "source", "M448 303 H562 V230", "读取版本", (513, 291), "teal")
    f.edge("reviewer", "system", "M194 429 H222 V344 H248", "查阅", (215, 409))
    f.edge("system", "notify", "M448 347 H562 V395", "提交通知", (555, 370), "purple")
    return f


def container():
    f = Figure("02-container", "容器图 · 目标", "接入与后台检查分开运行",
               "文档检查系统｜独立运行与存储单元", 652,
               "API 接收任务；执行器通过队列异步获取工作。")
    f.section(32, 139, 616, 411, "文档检查系统", "gray")
    f.node("web", 58, 202, 150, 82, "Web 应用", "浏览器 · 提交任务")
    f.node("api", 286, 202, 150, 82, "任务 API", "HTTP · 管理任务", "blue", True)
    f.node("queue", 486, 202, 136, 82, "任务队列", "消息 · 缓冲任务", "purple")
    f.node("store", 286, 420, 150, 82, "结果存储", "文件 · 保存报告", "teal")
    f.node("worker", 486, 420, 136, 82, "检查执行器", "进程 · 执行规则", "purple")
    f.edge("web", "api", "M208 243 H286", "HTTPS", (246, 229), "blue")
    f.edge("api", "queue", "M436 243 H486", "入队", (461, 229), "purple")
    f.edge("worker", "queue", "M554 420 V284", "订阅消息", (554, 350), "purple")
    f.edge("worker", "store", "M486 461 H436", "写入", (461, 448), "teal")
    f.edge("api", "store", "M361 284 V420", "读取报告", (361, 350), "teal")
    f.text(59, 337, "箭头表示发起动作的方向", 14, MUTED)
    f.text(59, 361, "消息处理次序见时序图", 14, MUTED)
    return f


def component():
    f = Figure("03-component", "组件图 · 目标", "规则通过接口接入检查器",
               "展开检查执行器｜箭头表示代码依赖", 600,
               "适配器实现接口；编排模块不直接依赖具体存储。")
    f.section(32, 138, 616, 361, "检查执行器 · 单个进程内", "gray")
    f.node("entry", 60, 204, 144, 72, "任务入口", "解析消息", "blue")
    f.node("coord", 268, 204, 150, 72, "检查编排", "调度规则", "blue", True)
    f.node("rule", 474, 204, 144, 72, "规则接口", "检查契约", "purple")
    f.node("port", 268, 398, 150, 72, "报告接口", "输出契约", "teal")
    f.node("adapter", 60, 398, 144, 72, "文件适配器", "实现报告接口", "teal")
    f.node("impl", 474, 398, 144, 72, "规则实现", "实现检查契约", "purple")
    f.edge("entry", "coord", "M204 240 H268", "调用", (235, 225), "blue")
    f.edge("coord", "rule", "M418 240 H474", "调用", (446, 225), "purple")
    f.edge("coord", "port", "M343 276 V398", "调用", (343, 342), "teal")
    f.edge("adapter", "port", "M204 434 H268", "实现", (237, 419), "teal", True, True)
    f.edge("impl", "rule", "M546 398 V276", "实现", (546, 342), "purple", True, True)
    f.text(59, 333, "实线：调用依赖", 14, MUTED)
    f.text(59, 357, "虚线：接口实现", 14, MUTED)
    return f


def deployment():
    f = Figure("04-deployment", "部署图 · 目标", "计算副本分布在两个故障域",
               "生产环境示意｜仅展示 HTTP 服务的部署与共享存储", 688,
               "计算层跨域部署；共享存储的容灾仍需单独验证。")
    f.node("lb", 232, 146, 216, 64, "流量入口", "HTTPS · 健康检查", "blue", True)
    f.section(32, 276, 290, 178, "故障域 A", "blue")
    f.section(358, 276, 290, 178, "故障域 B", "purple")
    f.node("a", 62, 342, 230, 76, "任务 API · 副本 A", "独立计算实例", "blue")
    f.node("b", 388, 342, 230, 76, "任务 API · 副本 B", "独立计算实例", "purple")
    f.node("shared", 232, 516, 216, 70, "共享结果存储", "外部托管服务", "teal")
    f.edge("lb", "a", "M274 210 V243 H177 V342", "路由", (177, 262), "blue")
    f.edge("lb", "b", "M406 210 V243 H503 V342", "路由", (503, 262), "purple")
    f.edge("a", "shared", "M177 418 V551 H232", "读取", (177, 487), "teal")
    f.edge("b", "shared", "M503 418 V551 H448", "读取", (503, 487), "teal")
    return f


def flow():
    f = Figure("05-flow", "流程图 · 控制规则", "并行检查，只重试写入",
               "目录有效且输出未占用才开始；输入目录始终只读", 858,
               "等待两项检查返回；任一失败不写报告，写入最多 3 次。")
    # Spatial blocks communicate phases without changing control semantics.
    f.rect(100, 233, 480, 168, COLORS["purple"][1], "none", 8)
    f.text(112, 257, "并行检查", 13, MUTED, 500)
    f.rect(24, 508, 624, 268, COLORS["teal"][1], "none", 8)
    f.text(38, 535, "报告写入", 13, MUTED, 500)
    f.diamond("valid", 340, 170, "输入有效？", 158)
    f.node("reject", 502, 144, 140, 52, "拒绝输入", tone="red")
    f.bar("fork", 205, 245, 270, "同时启动两项检查")
    f.node("scan", 118, 280, 174, 66, "源码扫描", "最多 5 秒", "blue")
    f.node("config", 388, 280, 174, 66, "配置检查", "最多 5 秒", "purple")
    f.bar("join", 205, 383, 270, "等待全部返回")
    f.diamond("passed", 340, 446, "均通过？", 158)
    f.node("checkfail", 502, 420, 140, 52, "检查失败", tone="red")
    f.node("write", 254, 521, 172, 58, "写入报告", "每轮只做写入", "teal")
    f.diamond("written", 340, 635, "写入成功？", 158)
    f.node("done", 264, 715, 152, 52, "报告完成", tone="teal", solid=True)
    f.node("exhausted", 502, 685, 140, 58, "写入失败", "第 3 次仍失败", "red")
    f.node("wait", 38, 605, 150, 64, "等待 1 秒", "未满 3 次", "amber")
    f.edge("valid", "reject", "M419 170 H502", "否", (457, 156), "red")
    f.edge("valid", "fork", "M340 205 V245", "是", (361, 231), "blue")
    f.edge("fork", "scan", "M205 250 V280", tone="blue")
    f.edge("fork", "config", "M475 250 V280", tone="purple")
    f.edge("scan", "join", "M205 346 V383", tone="blue")
    f.edge("config", "join", "M475 346 V383", tone="purple")
    f.text(339, 370, "等待全部", 14, MUTED, anchor="middle")
    f.edge("join", "passed", "M340 388 V411")
    f.edge("passed", "checkfail", "M419 446 H502", "否", (458, 432), "red")
    f.edge("passed", "write", "M340 481 V521", "是", (363, 507), "teal")
    f.edge("write", "written", "M340 579 V600", tone="teal")
    f.edge("written", "done", "M340 670 V715", "是", (363, 697), "teal")
    f.edge("written", "wait", "M261 635 H188", "否", (226, 621), "amber")
    f.edge("wait", "write", "M113 605 V550 H254", "再次写入", (180, 536), "amber")
    f.edge("written", "exhausted", "M419 635 H572 V685", "否，已满 3 次", (555, 623), "red")
    return f


def swimlane():
    f = Figure("06-swimlane", "泳道图 · 协作", "交接物决定下一步由谁接手",
               "作者、检查器、评审人｜时间顺序从上往下", 640,
               "检查通过才交评审；检查失败回到作者修订。")
    for x, name, tone in [(32, "作者", "blue"), (244, "检查器", "purple"), (456, "评审人", "teal")]:
        f.section(x, 142, 192, 392, name, tone)
    f.node("submit", 49, 210, 158, 52, "提交材料")
    f.node("check", 261, 294, 158, 56, "检查并生成报告", tone="purple")
    f.node("revise", 49, 404, 158, 56, "修订材料", tone="amber")
    f.node("review", 473, 404, 158, 56, "评审方案", tone="teal")
    f.edge("submit", "check", "M207 236 H340 V294", "材料版本", (276, 223), "blue")
    f.edge("check", "revise", "M261 322 H232 V432 H207", "不通过", (232, 387), "amber")
    f.edge("check", "review", "M419 322 H552 V404", "通过 · 报告", (531, 309), "teal")
    f.edge("revise", "submit", "M75 404 V262", "新版本", (75, 338), "amber")
    return f


def sequence():
    f = Figure("07-sequence", "时序图 · 成功场景", "任务接收与任务完成分开确认",
               "纵向仅表示先后，不表示耗时；异步投递不等于处理完成", 750,
               "接收回执沿 API 返回；后台完成后由客户端查询结果。")
    positions = {"client": 95, "api": 260, "queue": 425, "worker": 590}
    # Draw phase backgrounds before lifelines; each line is drawn only once.
    for y, h, label, fill in [
        (208, 172, "接收任务", COLORS["blue"][1]),
        (399, 143, "后台处理", COLORS["purple"][1]),
        (546, 88, "查询结果", COLORS["teal"][1]),
    ]:
        f.rect(35, y, 610, h, fill, "none", 9)
        f.text(47, y + 20, label, 12, MUTED, 500)
    for nid, name, tone in [("client", "客户端", "gray"), ("api", "任务 API", "blue"),
                            ("queue", "任务队列", "purple"), ("worker", "执行器", "teal")]:
        x = positions[nid]
        f.node(nid, x - 60, 143, 120, 51, name, tone=tone)
        f.path(f"M{x} 194 V628", COLORS[tone][0], 1.2, True)
    f.edge("client", "api", "M95 238 H260", "提交任务", (177, 224), "blue")
    f.edge("api", "queue", "M260 296 H425", "投递消息", (342, 282), "purple", opened=True)
    f.edge("api", "client", "M260 355 H95", "202 · task_id", (177, 341), "blue", True)
    f.edge("queue", "worker", "M425 459 H590", "交付任务", (507, 445), "purple", opened=True)
    f.edge("worker", "worker", "M590 481 V510 H620 V535 H590", tone="teal")
    f.text(572, 512, "执行并保存结果", 14, INK, anchor="end")
    f.edge("client", "api", "M95 578 H260", "查询 task_id", (177, 569), "blue")
    f.edge("api", "client", "M260 613 H95", "返回结果", (177, 599), "blue", True)
    f.text(280, 576, "API 读取报告", 14, MUTED)
    f.text(280, 600, "省略存储交互", 14, MUTED)
    f.text(37, 648, "实心：同步调用    开口：异步消息    虚线：返回", 14, MUTED)
    return f


def state():
    f = Figure("08-state", "状态图 · 单次任务", "重试必须回到明确状态",
               "图中列出本例全部合法转换；未画出的转换不允许", 610,
               "失败重试受次数约束；取消后结束本次任务。")
    f.node("queued", 46, 201, 144, 62, "排队中", tone="blue")
    f.node("running", 267, 201, 146, 62, "运行中", tone="blue", solid=True)
    f.node("success", 490, 201, 144, 62, "已完成", tone="teal")
    f.node("waiting", 267, 411, 146, 62, "等待重试", tone="amber")
    f.node("failed", 490, 411, 144, 62, "已失败", tone="red")
    f.node("cancel", 46, 411, 144, 62, "已取消", tone="gray")
    f.path("M118 153 V201", INK, marker="gray-arrow")
    f.parts.append(f'<circle cx="118" cy="146" r="6" fill="{INK}"/>')
    f.edge("queued", "running", "M190 232 H267", "领取", (226, 217), "blue")
    f.edge("running", "success", "M413 232 H490", "成功", (450, 217), "teal")
    f.edge("running", "waiting", "M316 263 V411", "失败且可重试", (306, 333), "amber")
    f.edge("waiting", "running", "M390 411 V263", "到期", (398, 371), "amber")
    f.edge("running", "failed", "M413 250 H452 V442 H490", "失败且耗尽", (501, 331), "red")
    f.edge("queued", "cancel", "M118 263 V411", "取消", (118, 333))
    f.text(45, 500, "已完成 / 已失败 / 已取消均为本次任务终态", 14, MUTED)
    return f


def dataflow():
    f = Figure("09-dataflow", "数据流图 · 目标", "原始输入与报告分开保存",
               "箭头表示数据的移动方向；本例为批处理", 650,
               "报告由校验结果生成，原始文档保留独立副本。")
    f.node("input", 46, 158, 168, 72, "原始文档", "输入数据", "gray")
    f.node("parse", 286, 158, 168, 72, "解析", "提取结构", "blue", True)
    f.node("archive", 46, 367, 168, 72, "原文归档", "只读副本", "teal")
    f.node("check", 286, 367, 168, 72, "规则校验", "生成问题列表", "purple")
    f.node("report", 486, 483, 152, 70, "报告文件", "输出数据", "teal")
    f.path("M60 384 H200", COLORS["teal"][0], 1.2)
    f.edge("input", "parse", "M214 194 H286", "文档", (249, 180), "blue")
    f.edge("input", "archive", "M130 230 V367", "原文副本", (130, 302), "teal")
    f.edge("parse", "check", "M370 230 V367", "结构化内容", (370, 302), "purple")
    f.edge("check", "report", "M454 403 H562 V483", "问题列表", (556, 429), "teal")
    f.text(47, 496, "源数据 → 处理 → 输出", 16, INK, 600)
    f.text(47, 523, "保存位置与控制流程分别说明", 14, MUTED)
    return f


def erd():
    f = Figure("10-erd", "ER 图 · 逻辑模型", "一次任务可以产生多条发现",
               "仅保留键与关系；数字表示关系端的可选性与基数", 615,
               "每条发现属于一个任务；任务可以暂时没有发现。")
    entities = [
        ("document", 46, 172, "Document", [("PK", "document_id"), ("", "version")], "blue"),
        ("task", 382, 172, "Task", [("PK", "task_id"), ("FK", "document_id")], "purple"),
        ("finding", 382, 391, "Finding", [("PK", "finding_id"), ("FK", "task_id")], "teal"),
    ]
    for nid, x, y, name, fields, tone in entities:
        dark, light = COLORS[tone]
        f.nodes[nid] = {"name": name, "fields": fields}
        f.rect(x, y, 252, 120, "#FFFFFF", dark, 10, f'id="{nid}"')
        f.rect(x, y, 252, 38, light, "none", 10)
        f.text(x + 16, y + 26, name, 18, INK, 600)
        for i, (flag, field) in enumerate(fields):
            f.text(x + 16, y + 66 + i * 30, flag, 13, INK, 600)
            f.text(x + 62, y + 66 + i * 30, field, 15, INK)
    # ER relationships have no action arrows.
    f.path("M298 241 H382", MUTED)
    f.text(309, 227, "1", 14, INK)
    f.text(347, 227, "0..*", 14, INK)
    f.text(311, 266, "关联", 14, MUTED)
    f.path("M508 292 V391", MUTED)
    f.text(520, 316, "1", 14, INK)
    f.text(520, 382, "0..*", 14, INK)
    f.text(481, 348, "产生", 14, MUTED, anchor="end")
    f.text(46, 396, "1      恰好一个", 15, INK)
    f.text(46, 425, "0..*   零个或多个", 15, INK)
    f.text(46, 470, "逻辑关系不等同于删除策略", 14, MUTED)
    return f


def schedule(plan):
    """CPM for this fixture: finish-to-start DAG, unlimited resources, workdays."""
    result = {}
    tasks = plan["tasks"]
    for task in tasks:
        if any(dep not in result for dep in task["after"]):
            raise ValueError("Fixture tasks must be topologically ordered")
        start = max((result[d]["finish"] for d in task["after"]), default=0)
        result[task["id"]] = {**task, "start": start, "finish": start + task["duration"]}
    end = max(t["finish"] for t in result.values())
    for task in reversed(tasks):
        successors = [t for t in result.values() if task["id"] in t["after"]]
        latest_finish = min((t["latest_start"] for t in successors), default=end)
        item = result[task["id"]]
        item["latest_start"] = latest_finish - task["duration"]
        item["slack"] = item["latest_start"] - item["start"]
        item["critical"] = item["slack"] == 0
    return result, end


def gantt(plan):
    tasks, end = schedule(plan)
    f = Figure("11-gantt", "甘特图 · 相对工作日", "并行实施后，在集成处汇合",
               "合成估算｜完成后开始依赖｜区间 [开始, 结束)", 641,
               f"计算工期为 {end} 个工作日；关键任务以蓝色描边和“关键”标识。")
    x0, unit, row_y = 258, 35, {}
    f.rect(32, 132, 616, 52, "#F4F6FA", "none", 8)
    for i in range(len(tasks)):
        if i % 2 == 0:
            f.rect(32, 187 + i * 61, 616, 57, "#F7F9FB", "none", 0)
    f.text(35, 155, "任务 / 负责人", 14, MUTED, 600)
    f.text(260, 155, "相对工作日", 14, MUTED, 600)
    for day in range(end + 1):
        x = x0 + day * unit
        f.path(f"M{x} 184 V500", "#E4E9EF", .8)
        f.text(x, 177, str(day), 13, MUTED, anchor="middle")
    for i, t in enumerate(tasks.values()):
        y = 212 + i * 61
        row_y[t["id"]] = y
        f.text(35, y + 5, t["name"], 16, INK, 600)
        f.text(35, y + 27, t["owner"], 13, MUTED)
        tone = "blue" if t["critical"] else "teal"
        dark, light = COLORS[tone]
        f.rect(x0 + t["start"] * unit, y - 13, t["duration"] * unit, 32,
               dark if t["critical"] else light, dark, 5)
        f.text(x0 + (t["start"] + t["duration"] / 2) * unit, y + 8,
               "关键" if t["critical"] else f"余量 {t['slack']}d", 13,
               "#FFFFFF" if t["critical"] else dark, 500, "middle")
    for t in tasks.values():
        for dep in t["after"]:
            old = tasks[dep]
            x1, x2 = x0 + old["finish"] * unit, x0 + t["start"] * unit
            y1, y2 = row_y[dep], row_y[t["id"]]
            # Detour only if a task bar actually obstructs the vertical route.
            between = [other for k, other in tasks.items() if y1 < row_y[k] < y2]
            obstructed = any(
                x0 + other["start"] * unit <= x1 <= x0 + other["finish"] * unit
                for other in between)
            if obstructed:
                # Route outside every intervening bar. Choose the shorter side,
                # including when the successor starts later than this task ends.
                left = min(x0 + other["start"] * unit for other in between) - 16
                right = max(x0 + other["finish"] * unit for other in between) + 16
                channel = min((left, right), key=lambda x: abs(x-x1) + abs(x-x2))
                route = (f"M{x1} {y1+19} V{y1+25} H{channel} "
                         f"V{y2-24} H{x2} V{y2-13}")
            else:
                route = f"M{x1} {y1+19} V{y2-24} H{x2} V{y2-13}"
            f.path(route, MUTED, 1.3, marker="gray-arrow")
    f.text(35, 521, "里程碑", 14, MUTED)
    for m in plan["milestones"]:
        day = max(tasks[dep]["finish"] for dep in m["after"])
        x = x0 + day * unit
        f.parts.append(f'<path d="M{x} 507 l6 6 l-6 6 l-6 -6 Z" fill="{INK}"/>')
        f.text(x + 9, 520, f"D{day}", 12, MUTED)
    f.text(35, 542, "资源不冲突；未计节假日、额外等待与估算不确定性", 14, MUTED)
    return f


def milestone(plan):
    tasks, end = schedule(plan)
    f = Figure("12-milestone", "里程碑图 · 同一份计划", "每个节点都对应可验收成果",
               "与甘特图共用任务数据｜横向位置按相对工作日比例", 587,
               "里程碑是零时长成果；日期由前置任务结束时间派生。")
    x0, unit = 50, 56
    f.path(f"M{x0} 322 H{x0+end*unit}", MUTED, 2)
    for day in range(end + 1):
        x = x0 + day * unit
        f.path(f"M{x} 318 V326", MUTED, 1.2)
        f.text(x, 349, str(day), 13, MUTED, anchor="middle")
    f.text(50, 377, "相对工作日", 14, MUTED)
    for i, m in enumerate(plan["milestones"]):
        day = max(tasks[dep]["finish"] for dep in m["after"])
        x = x0 + day * unit
        dark, light = COLORS[["blue", "purple", "teal"][i]]
        f.parts.append(f'<path d="M{x} 313 l9 9 l-9 9 l-9 -9 Z" fill="{dark}"/>')
        y = 171 if i != 1 else 405
        width = 184
        left = max(32, min(x - width / 2, 648 - width))
        f.rect(left, y, width, 100, light, dark)
        f.text(left + 14, y + 26, f"D{day} · {m['name']}", 16, dark, 600)
        f.text(left + 14, y + 53, m["owner"], 14, MUTED)
        f.text(left + 14, y + 78, m["evidence"], 14, INK)
        route = (f"M{x} {y+100} V313" if y < 322 else
                 f"M{x} 331 H{x+18} V{y}")
        f.path(route, dark, 1.5)
    return f


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    plan = json.loads(Path(__file__).with_name("plan.json").read_text())
    figures = [context(), container(), component(), deployment(), flow(), swimlane(),
               sequence(), state(), dataflow(), erd(), gantt(plan), milestone(plan)]
    manifest = [f.save(args.out) for f in figures]
    (args.out / "diagrams.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    tasks, end = schedule(plan)
    (args.out / "schedule-calculation.json").write_text(
        json.dumps({"tasks": tasks, "duration": end}, ensure_ascii=False, indent=2))
    print(f"Generated {len(figures)} editable SVG examples in {args.out}")


if __name__ == "__main__":
    main()
