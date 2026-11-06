#!/usr/bin/env python3
"""进场自诊断 + 留痕分支决策 + 卡片渲染（纯 stdlib）。

背景：雷达每日跑（cron/云电脑调度，调度本身不归技能管）。今天（2026-10-16）真实
跑过一次：飞书文档留痕成功，但群卡片被挡——im scope 缺失 / bot 不在群（飞书
错误 230002）。临场处理靠记忆不是契约，本脚本把它写成确定性分支：

  check：进场探测。
    1. 技能目录自检（冻结信封文件在位、vendor-manifest 可读、Python≥3.9）；
    2. 通道探测结果由宿主传入（飞书读写能力归宿主/lark-cli，技能不内置 token）：
       --doc-writable yes/no   追踪台文档能不能写；
       --group-sendable yes/no 群能不能发；
       --group-error <code>     群发失败时的错误码（如 230002）。

  decide：三分支（确定性，不是临场发挥）：
    doc 不可写            → branch=block           ：无法留痕，停。回报用户"飞书文档不可写"。exit 7
    doc 可写 + 群可发      → branch=full            ：文档留痕 + 群卡片。exit 0
    doc 可写 + 群不可发     → branch=degrade-docs   ：降级"文档留痕 + 回报 blocker"，
                          不发群卡片，blocker 写明错误码（今天 230002 的走法）。exit 6

  render-card：按 references/cards.json 渲染留痕卡片（no_opportunity /
    strong_opportunity），required_fields 缺一即拒。产物 JSON 可直接喂宿主 im。

退出码：0=可跑（full）；6=可跑但降级（只文档留痕）；7=阻断（留痕通道挂了）；2=参数错。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "references" / "cards.json"


def _bool(s: str) -> bool:
    return str(s).strip().lower() in {"yes", "y", "true", "1"}


def skill_probe(root: Path) -> list:
    """技能目录自检：冻结信封文件在位、vendor-manifest 可读。返回问题清单（空=过）。"""
    issues = []
    for rel in ("scripts/artifact_io.py", "scripts/scoring-rules.json",
                "scripts/vendor-manifest.json"):
        if not (root / rel).exists():
            issues.append(f"缺文件：{rel}")
    if sys.version_info < (3, 9):
        issues.append(f"Python {sys.version_info.major}.{sys.version_info.minor} 低于 3.9")
    return issues


def decide(doc_writable: bool, group_sendable: bool, group_error: str) -> dict:
    """确定性留痕分支。今天 im scope/bot 不在群（230002）走 degrade-docs。"""
    if not doc_writable:
        return {
            "branch": "block", "exit": 7,
            "actions": ["不在任何地方留痕（写不进追踪台，别处也不补）",
                        "回报用户：飞书追踪台文档不可写，今日雷达结果未留痕，请先修文档权限"],
            "blocker": "doc_not_writable",
        }
    if not group_sendable:
        blocker = f"group_channel_unavailable: {group_error or 'unknown'}"
        return {
            "branch": "degrade-docs", "exit": 6,
            "actions": ["追踪台文档留痕（与成功日同一份格式，写明'无强机会'或'强机会清单'）",
                        "不发群卡片，把 blocker 写进文档：群通道不可发",
                        "回报调用方 blocker：今日降级为纯文档留痕"],
            "blocker": blocker,
        }
    return {
        "branch": "full", "exit": 0,
        "actions": ["追踪台文档留痕", "发群卡片（render-card 渲染的 JSON 喂宿主 im）"],
        "blocker": None,
    }


def render_card(template: str, data: dict) -> dict:
    cards = json.loads(CARDS.read_text(encoding="utf-8"))
    tpl = cards.get(template)
    if tpl is None:
        raise ValueError(f"未知卡片模板：{template}（可选：{', '.join(k for k in cards if k not in ('cards_version','note'))}）")
    missing = [f for f in tpl["required_fields"] if not data.get(f)]
    if missing:
        raise ValueError(f"卡片缺必填字段：{missing}")
    out = {"template": template, "title": tpl["title"].format(**data),
           "elements": [e.format(**data) for e in tpl["elements"]]}
    return out


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="雷达进场自诊断 + 留痕分支 + 卡片渲染")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ck = sub.add_parser("check")
    ck.add_argument("--doc-writable", required=True)
    ck.add_argument("--group-sendable", required=True)
    ck.add_argument("--group-error", default="")
    rc = sub.add_parser("render-card")
    rc.add_argument("--template", required=True, choices=["no_opportunity", "strong_opportunity"])
    rc.add_argument("--data", required=True, help='JSON：{"date":...} 填入卡片字段')
    args = ap.parse_args(argv)

    if args.cmd == "render-card":
        try:
            data = json.loads(args.data)
            out = render_card(args.template, data)
        except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
            print(json.dumps({"status": "rejected", "error": str(e)}, ensure_ascii=False),
                  file=sys.stderr)
            return 2
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    issues = skill_probe(ROOT)
    branch = decide(_bool(args.doc_writable), _bool(args.group_sendable), args.group_error)
    payload = {"skill_dir": "ok" if not issues else "bad", "skill_issues": issues, **branch}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return branch["exit"] if not issues else 7


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
