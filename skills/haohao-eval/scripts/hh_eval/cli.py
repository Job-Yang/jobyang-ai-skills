# -*- coding: utf-8 -*-
"""命令行入口：argparse 与旧 loop.py 的 main 完全一致（25 个子命令一个不少），新增顶层
--data-root（工作区隔离）和 preflight 子命令。Stop → stderr「停下：」+ exit 2。"""
import argparse
import sys

from hh_eval.const import VERSIONS, Stop
from hh_eval.fs import set_data_root
from hh_eval.pipeline import (cmd_accept_manual, cmd_add_items, cmd_anchor, cmd_blind, cmd_calib_score,
                               cmd_check, cmd_decide, cmd_disputes, cmd_doc, cmd_export, cmd_import_clean,
                               cmd_init, cmd_mode, cmd_note, cmd_report, cmd_rollback, cmd_stage, cmd_start,
                               cmd_state, cmd_status, cmd_target, cmd_verify, cmd_version, cmd_writer_view)
from hh_eval.preflight import cmd_preflight


def build_parser():
    ap = argparse.ArgumentParser(description="haohao-eval 每日召回（详见 references/daily-loop.md）")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD（默认今天，测试用）")
    ap.add_argument("--data-root", dest="data_root",
                    help="把 eval 数据目录和发布目录一起放到这个根下面（默认空=用老的 HAOHAO_EVAL_HOME/XDG_DATA_HOME）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="第一次运行：建数据目录、配置和状态")
    p.add_argument("--shuohua-dir")
    p.add_argument("--model")
    p.add_argument("--force", action="store_true")
    sub.add_parser("status", help="看当前模式、版本、问题池和待判断的题")
    p = sub.add_parser("start", help="开今天这一轮：抽体检题、回归题、干净对照，定目标病灶")
    p.add_argument("--model")
    p.add_argument("--force", action="store_true")
    p.add_argument("--manual-seeds", dest="manual_seeds", type=int, default=0,
                   help="从作者手改种子库按天轮转放 N 条进今天的合成题（只给原文，裁判看不到作者动作）；不写就是 0")
    sub.add_parser("calib-score", help="给裁判体检算分")
    p = sub.add_parser("add-items", help="收下今天新出的题（JSON 数组）")
    p.add_argument("file")
    p = sub.add_parser("writer-view", help="列出某个版本还要改写的题")
    p.add_argument("version", choices=VERSIONS)
    sub.add_parser("target", help="看目标病灶的开发组证据")
    p = sub.add_parser("stage", help="冻结候选细则")
    p.add_argument("file", nargs="?", default="")
    p.add_argument("--note")
    p.add_argument("--aa", action="store_true", help="影子期 A/A 自测：候选就是现用版")
    sub.add_parser("check", help="机械检查所有改写")
    sub.add_parser("blind", help="打乱、匿名，生成盲评队列")
    p = sub.add_parser("verify", help="核对裁判答案（格式、引用、旗标）")
    p.add_argument("--partial", action="store_true", help="没判完的按拿不准算（时间不够时用）")
    p = sub.add_parser("decide", help="入池、算指标、建争议、过门禁、发布或回滚")
    p.add_argument("--force", action="store_true")
    sub.add_parser("report", help="生成今天的日报")
    p = sub.add_parser("disputes", help="待判断的题：list / answer")
    p.add_argument("action", choices=["list", "answer"])
    p.add_argument("id", nargs="?")
    p.add_argument("answer", nargs="?")
    p.add_argument("--note")
    p.add_argument("--all", action="store_true")
    p = sub.add_parser("mode", help="切模式：auto / shadow / paused")
    p.add_argument("mode", choices=["auto", "shadow", "paused"])
    p.add_argument("--reason")
    sub.add_parser("anchor", help="把现用版设为锚点")
    p = sub.add_parser("rollback", help="回滚细则")
    p.add_argument("--to")
    p.add_argument("--force", action="store_true", help="文件被手工改过也回滚（手工改动会被覆盖）")
    sub.add_parser("accept-manual", help="把手工改过的 daily-learning.md 记成新版本")
    p = sub.add_parser("import-clean", help="导入人写的干净文本做误改对照")
    p.add_argument("file")
    sub.add_parser("export", help="生成细则合并提案")
    p = sub.add_parser("note", help="记下作者的原话（判断标准、偏好），裁判和写候选时都会看到")
    p.add_argument("action", choices=["add", "list", "drop"])
    p.add_argument("text", nargs="?", help="add 跟作者原话，drop 跟编号")
    p.add_argument("--文体", "--genre", dest="genre", help="只用于哪些文体，逗号隔开；不写就是所有文体")
    sub.add_parser("version", help="看评测技能是第几版")
    fetched = "读回来的文档（docs +fetch 的输出存成的文件）"
    ss = sub.add_parser("state", help="跨天的状态：dump / load / check").add_subparsers(dest="action", required=True)
    p = ss.add_parser("dump", help="生成状态文档的内容（整篇覆盖写进状态文档）")
    p.add_argument("--out", help="写到哪个文件（默认数据目录的 exports/state-doc.xml）")
    p.add_argument("--empty", action="store_true", help="一份空状态，第一次建状态文档时用")
    p = ss.add_parser("load", help="从状态文档恢复数据目录（本地比文档新时不覆盖）")
    p.add_argument("file", help=fetched)
    p.add_argument("--force", action="store_true", help="本地比文档新也用文档覆盖（原来的挪走备份）")
    ss.add_parser("check", help="核对写进状态文档的是不是本地这一份").add_argument("file", help=fetched)
    ds = sub.add_parser("doc", help="召回文档：read / record").add_subparsers(dest="action", required=True)
    p = ds.add_parser("read", help="读作者写在召回文档里的判断和交代，并记下")
    p.add_argument("file", help=fetched)
    p.add_argument("--dry-run", action="store_true", help="只看会记下什么，不改数据")
    p = ds.add_parser("record", help="生成今天的记录（追加到召回文档末尾）")
    p.add_argument("--out", help="写到哪个文件（默认数据目录的 exports/record-日期.xml）")
    p.add_argument("--stopped", help="流程中途停下时写一条停下的记录，跟上原因")
    p.add_argument("--again", action="store_true", help="今天已经生成过、确认没写进文档时重新生成")
    pf = sub.add_parser("preflight", help="开跑前自诊断（--json 供 cron/云电脑判断今天能跑什么）")
    pf.add_argument("--state-doc-file", help="lark-cli docs +fetch 状态文档存成的文件")
    pf.add_argument("--recall-doc-file", help="lark-cli docs +fetch 召回文档存成的文件")
    pf.add_argument("--json", action="store_true", help="机器可读输出")
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if getattr(args, "data_root", None):
        set_data_root(args.data_root)
    fn = {"init": cmd_init, "status": cmd_status, "start": cmd_start, "calib-score": cmd_calib_score,
          "add-items": cmd_add_items, "writer-view": cmd_writer_view, "target": cmd_target, "stage": cmd_stage,
          "check": cmd_check, "blind": cmd_blind, "verify": cmd_verify, "decide": cmd_decide, "report": cmd_report,
          "disputes": cmd_disputes, "mode": cmd_mode, "anchor": cmd_anchor, "rollback": cmd_rollback,
          "accept-manual": cmd_accept_manual, "import-clean": cmd_import_clean, "export": cmd_export,
          "note": cmd_note, "version": cmd_version, "state": cmd_state, "doc": cmd_doc,
          "preflight": cmd_preflight}[args.cmd]
    try:
        try:
            return fn(args) or 0
        except Stop as e:
            print("停下：" + str(e), file=sys.stderr)
            return 2
    finally:
        set_data_root("")  # 内嵌调用（测试）不污染下一个子命令


if __name__ == "__main__":
    sys.exit(main())
