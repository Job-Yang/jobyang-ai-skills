# -*- coding: utf-8 -*-
"""常量与 Stop 异常。从 scripts/loop.py 原样搬来，一个字没动（门禁语义就靠这些数）。"""
import re

CODES = {
    "A1": "编数字", "A2": "编承诺", "A3": "编因果场景", "A4": "编身份经历",
    "B": "丢信息", "G": "删了功能件",
    "C1": "程度范围模态漂移", "C2": "术语通俗化", "C3": "主被动调换", "C4": "抬头语气降格",
    "D": "场合错配",
    "E1": "破折号硬接", "E2": "自造黑话", "E3": "绕口不通",
    "F": "冗余没删", "H": "无必要改动", "U": "原句不清没提醒", "M": "正文里自加免责", "R": "AI味残留",
    "P": "作者判定有问题",
}
FAB = {"A1", "A2", "A3", "A4"}
HARM = FAB | {"B", "G", "C1", "C2", "C3", "C4", "D", "P"}
MINOR = {"E1", "E2", "E3", "H", "M"}
RESIDUE = {"R", "F"}
R_LABELS = ["翻案体", "三连排比", "量词标题", "名词化", "万能动词", "元话语", "段末拔高", "翻译腔句式",
            "空心比喻", "车轱辘", "半角标点", "套话", "被字句", "造词", "词不配位", "姿态", "标题"]
SEVERITY = ["A1", "A2", "A3", "A4", "C2", "B", "G", "C1", "C3", "C4", "D", "E1", "E2", "E3", "H", "M", "U", "F", "R"]
REGISTERS = ["官方对外", "敬语", "要气势", "私人软场合", "技术议论"]
VERDICTS = ["改坏了", "没改好", "合格", "不确定"]
VERSIONS = ["current", "cand", "rc", "anchor"]
FLAG_NEED = {  # 需要裁判逐条回应的机器旗标，以及「确认」时必须有的问题编码
    "新数字": FAB | {"C1"}, "新英文词": FAB | {"C2", "D"}, "承诺时间词新增": FAB | {"C1"},
    "确定性加强": {"C1"} | FAB, "模态变化": {"C1"}, "术语丢失": {"C2", "B"}, "术语替换": {"C2"},
    "事实关键词缺失": {"B", "G", "C1", "C2", "C3", "C4"}, "长度异常": set(), "自加免责": {"M"},
}
MODAL = ["可能", "也许", "或许", "大概", "大约", "估计", "预计", "初步", "疑似", "似乎", "应该", "倾向",
         "计划", "打算", "有望", "争取", "暂定", "原则上", "考虑", "尝试"]
CERTAIN = ["一定", "肯定", "必然", "确定是", "确保", "保证", "大概率", "绝对", "必定", "务必", "彻底"]
PROMISE = ["第一时间", "马上", "立刻", "尽快", "随时", "保证", "一定会", "下周", "明天", "今天", "今晚",
           "下午", "上午", "稍后", "回头", "改天", "请客", "时间点", "工作日", "小时内", "当天"]
SAME_TIME = [("今日", "今天"), ("明日", "明天"), ("即刻", "立刻"), ("立即", "立刻"), ("午后", "下午")]
# 正文里自己加的免责说法（与 haohao-shuohua/scripts/quick_scan.py 的 disclaim 检查同一份正则）。
DISCLAIM_RX = re.compile(
    r"(?:以上|上述)[^。！？\n]{0,15}(?:仅|只)(?:依据|根据|基于)"
    r"|(?:以上|上述)[^。！？\n]{0,15}按(?:你|您)的"
    r"|未(?:做|经过?)?(?:额外|进一步|实际)?的?(?:核验|核实|核查|查证)(?!的)"
    r"|(?:无法|没法|没有|尚未|还没)(?:核验|核实|查证)(?!的)"
    r"|还(?:得|要|需要)看[^。！？\n]{0,15}(?:什么时候|何时)")
TECH_TERMS = ["重构", "解耦", "横向扩展", "纵向扩展", "幂等", "回滚", "灰度", "降级", "熔断", "限流",
              "缓存", "分布式", "连接池", "消息队列", "可扩展", "高可用", "可观测", "容灾", "鉴权", "索引",
              "分库分表", "异步", "并发", "线程", "进程", "协程", "死锁", "事务", "一致性", "吞吐",
              "召回", "准确率", "埋点", "告警", "链路", "微服务", "容器", "脏读", "慢查询", "压测"]
TERM_SWAPS = {"重构": ["重写"], "解耦": ["拆开", "分开"], "横向扩展": ["加机器"], "幂等": ["重复"],
              "回滚": ["退回", "撤回"], "灰度": ["小范围"], "降级": ["关掉"], "熔断": ["断开"]}
FORBIDDEN_RULE = re.compile(
    r"忽略|无视|不必遵守|可以不管|优先于底线|覆盖底线|放宽保真|不用管保真|"
    r"允许.{0,6}(补|编|加|添)|可以.{0,4}(补充|补上|加上|编|添上)|适当(补充|增加|添加|加入)|"
    r"合理(推测|想象|补充|发挥)|自行(补充|发挥)|更像人|人味|加点(细节|场景|口吻)|一律口语|全部口语")
HEADER_RX = re.compile(r"^\s*(<!--.*?-->\s*)+", re.S)
MARK_START, MARK_END = "<!-- 底线条款:开始", "<!-- 底线条款:结束"
VERSION = "3"
SNAP_KEYS = ("任务", "文体", "力度", "原文", "上下文", "事实", "要求")
STATE_TAG = "haohao_eval_state"
STATE_DOC_TITLE = "好好说话每日召回 · 运行状态"
SECTION_TITLE = "每日迭代日志"
NOTES_TITLE = "你的交代"
SLOT, BLANK = "你的判断", "＿＿"

DEFAULTS = {
    "shuohua_skill_dir": "",
    "model_name": "",
    "shadow_days": 14,
    "auto_switch": True,
    "daily": {"synthetic": 8, "drafting": 2, "real_max": 3, "regression": 5, "clean": 3, "probes": 6,
              "manual_seeds": 3,
              "calib_red": 3, "calib_orange": 2, "calib_green": 4},
    "cluster": {"min_findings": 6, "min_spread": 2, "cooldown_days": 7, "stuck_after": 3, "stuck_window_days": 14},
    "gates": {"calib_min_catch": 0.8, "calib_max_false_alarm": 0.25, "max_uncertain": 0.2,
              "target_min_discordant": 5, "target_alpha": 0.05, "clean_edit_slack": 0.05,
              "clean_edit_alarm": 0.3, "overlay_max_chars": 6000, "overlay_max_rules": 30,
              "rule_max_chars": 400, "max_rules_changed": 2},
    "monitor": {"window_days": 7, "harm_rate_margin": 0.10, "min_days_after_release": 2, "min_harm_items": 3},
    "disputes": {"max_per_day": 3, "default_after_days": 3, "audit_weekday": 1, "audit_count": 3,
                 "auto_match_similarity": 0.75, "audit_miss_pause": 0.1, "audit_min_answered": 5},
    "sources": {"badcase_base": "YClTbfJYHa8u6MsAI6IcoUZunle", "badcase_table": "tblQwBoiuetAOo4T",
                "read_new_badcases": True},
    "retain": {"pool_days": 30, "snapshots_per_cluster": 8, "disputes_days": 30, "precedents_max": 300,
               "notes_dropped_days": 30, "inbox_days": 14, "metrics_days": 120, "regression_extra_max": 30,
               "history_max": 60, "seen_days": 45, "runs_days": 14},
}

REQUIRED_FACT_KINDS = {"synthetic", "probe", "drafting"}

STATE_LINE_MAX, STATE_BLOCK_MAX = 3000, 10000

ANSWER_WORDS = {"有问题": "有", "有": "有", "是": "有", "没问题": "没有", "没有": "没有", "不是": "没有", "否": "没有",
                "跳过": "跳过", "不确定": "跳过", "说不清": "跳过", "拿不准": "跳过"}
SLOT_RX = re.compile(r"(?<![A-Za-z0-9])(D\d+)\s*" + SLOT + r"\s*[:：]\s*(.*)$")
ANSWER_RX = re.compile("^(" + "|".join(sorted(ANSWER_WORDS, key=len, reverse=True)) + ")(.*)$")
ONLY_RX = re.compile(r"[（(【\[]\s*只用于\s*[:：]?\s*([^）)】\]]+)[）)】\]]")


class Stop(Exception):
    """流程必须停下来的情况：给出中文原因，退出码 2。"""


__all__ = [
    "CODES", "FAB", "HARM", "MINOR", "RESIDUE", "R_LABELS", "SEVERITY", "REGISTERS", "VERDICTS",
    "VERSIONS", "FLAG_NEED", "MODAL", "CERTAIN", "PROMISE", "SAME_TIME", "DISCLAIM_RX", "TECH_TERMS", "TERM_SWAPS",
    "FORBIDDEN_RULE", "HEADER_RX", "MARK_START", "MARK_END", "VERSION", "SNAP_KEYS", "STATE_TAG",
    "STATE_DOC_TITLE", "SECTION_TITLE", "NOTES_TITLE", "SLOT", "BLANK", "DEFAULTS",
    "REQUIRED_FACT_KINDS", "STATE_LINE_MAX", "STATE_BLOCK_MAX", "ANSWER_WORDS", "SLOT_RX", "ONLY_RX",
    "Stop",
]
