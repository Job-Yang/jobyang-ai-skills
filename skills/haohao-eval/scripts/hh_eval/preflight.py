# -*- coding: utf-8 -*-
"""开跑前的自诊断。机器可读（--json），cron / 云电脑拿退出码和 JSON 判断今天能跑什么。

红线语义（和 daily-loop.md 一致）：
- 数据没接上（两篇飞书文档读不下来、读不懂、没权限）→ 按「数据没接上：原始报错」停下，绝不 init。
- 当天流程不碰飞书：数据目录可写、技能是第 3 版、技能目录在，就能从 start 跑起。
"""
import json
import os
import shutil

from hh_eval.const import VERSION, Stop
from hh_eval.docdoc import doc_lines, recall_section
from hh_eval.fp import find_shuohua_dir
from hh_eval.fs import eval_home, lark_cmd, load_config, skill_dir
from hh_eval.statedoc import doc_content, state_from_doc


def _check(name, ok, detail, *, blocking=True):
    return {"name": name, "ok": ok, "detail": detail, "blocking": blocking}


def run_preflight(args):
    checks = []
    # 1 技能版本：不是第 3 版结构化停下
    version_ok = VERSION == "3"
    checks.append(_check("version", version_ok,
                         f"haohao-eval 第 {VERSION} 版" + ("" if version_ok else "（不是第 3 版，旧版不认识状态文档，硬跑会把数据弄丢）"),
                         blocking=True))
    # 2 技能目录
    sd = skill_dir()
    skill_ok = os.path.exists(os.path.join(sd, "SKILL.md"))
    checks.append(_check("skill_dir", skill_ok, sd, blocking=True))
    # 3 数据目录可写
    try:
        home = eval_home()
        os.makedirs(home, exist_ok=True)
        probe = os.path.join(home, ".preflight-write-test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        checks.append(_check("data_dir", True, home, blocking=True))
    except OSError as e:
        checks.append(_check("data_dir", False, str(e), blocking=True))
    # 4 被测技能（haohao-shuohua）在不在：找不到只是底线哈希跳过，不 block，但给人话提示
    cfg = load_config()
    shuohua = find_shuohua_dir(cfg)
    checks.append(_check("shuohua_dir", bool(shuohua), shuohua or
                         "没找到 haohao-shuohua 技能目录：底线哈希先跳过，不影响当天流程；"
                         "换机器跑用 --shuohua-dir 或环境变量 HAOHAO_SHUOHUA_DIR 指定。",
                         blocking=False))
    # 5 lark-cli 在不在
    lark = lark_cmd()
    checks.append(_check("lark_cli", bool(shutil.which(lark)), lark or "（没配置）", blocking=False))
    # 6 状态文档（给了文件才查）：读不下来/读不懂 → 数据没接上
    if args.state_doc_file:
        try:
            header, body = state_from_doc(doc_content(args.state_doc_file))
            checks.append(_check("state_doc", True, f"第 {header['seq']} 份 · {header.get('date')}", blocking=True))
        except Stop as e:
            checks.append(_check("state_doc", False, "数据没接上：" + str(e), blocking=True))
    else:
        checks.append(_check("state_doc", None, "没给文件（今天不走跨天流程就不用查）", blocking=False))
    # 7 召回文档（给了文件才查）
    if args.recall_doc_file:
        try:
            sec, status = recall_section(doc_lines(doc_content(args.recall_doc_file)))
            checks.append(_check("recall_doc", True, "可以读" + ("" if status == "ok" else f"（{status}）"), blocking=True))
        except Stop as e:
            checks.append(_check("recall_doc", False, "数据没接上：" + str(e), blocking=True))
    else:
        checks.append(_check("recall_doc", None, "没给文件", blocking=False))

    blocked = [c["detail"] for c in checks if c["ok"] is False and c["blocking"]]
    warnings = [c["detail"] for c in checks if c["ok"] is None and c["blocking"] is False]
    offline_ok = all(c["ok"] is not False for c in checks if c["blocking"] and c["name"] in
                     ("version", "skill_dir", "data_dir"))
    given = [c for c in checks if c["name"] in ("state_doc", "recall_doc") and c["ok"] is not None]
    online_ok = None if not given else all(c["ok"] for c in given)
    result = {
        "ready": offline_ok and online_ok is not False,
        "offline_ok": offline_ok,
        "online_ok": online_ok,
        "blocked": blocked,
        "warnings": warnings,
        "checks": [{k: c[k] for k in ("name", "ok", "detail")} for c in checks],
    }
    return result


def cmd_preflight(args):
    result = run_preflight(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        for c in result["checks"]:
            mark = {"true": "OK  ", "false": "停下", "none": "跳过"}[str(c["ok"]).lower()]
            print(f"[{mark}] {c['name']}：{c['detail']}")
        print("今天可以从 start 跑当天流程：" + ("能" if result["offline_ok"] else "不能"))
        print("跨天数据接得上（状态+召回文档）："
              + {True: "能", False: "不能", None: "没给文档文件，没检查"}[result["online_ok"]])
        if result["blocked"]:
            for b in result["blocked"]:
                print("停下：" + b)
    if result["blocked"]:
        raise Stop(result["blocked"][0])
    return 0


__all__ = ["run_preflight", "cmd_preflight"]
