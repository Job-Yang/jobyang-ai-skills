#!/usr/bin/env python3
"""route_eval.py 的有效性自测（零第三方依赖，临时测试样例，自动清理）。

证明两件事：
1. 合规库与合规活卷必须零误报、脱敏彻底、乱序指纹稳定；
2. 每类预设错误（A001-A007、边界误抢、轻任务误触、幻觉技能、抖动、同义不一致、真实翻车回归）
   都必须被精准命中。

运行：python3 test_route_eval.py
退出码：0 全过；1 有断言失败。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import route_eval as reval  # noqa: E402


def _run_silent(fn, *args, **kwargs):
    buf_out, buf_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        rc = fn(*args, **kwargs)
    return rc, buf_out.getvalue(), buf_err.getvalue()


def write_skill(root: Path, name: str, desc: str, body: str) -> None:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    content = f'---\nname: {name}\ndescription: "{desc}"\n---\n{body}\n'
    (d / "SKILL.md").write_text(content, encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict | str]) -> None:
    lines = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_fixture_library(root: Path) -> None:
    write_skill(
        root,
        "alpha-tool",
        "整理结构化方案文档。适用：写技术设计。触发：「出个方案」「画架构图」。不适用：代码审查（走 beta-tool）。",
        "# Alpha\nSECRET_BODY_MARKER_ALPHA 绝不能泄进中立目录。\n",
    )
    write_skill(
        root,
        "beta-tool",
        "只读审查既有代码变更与差异缺陷。触发：「帮我看看改得行不行」「审一下这次改动」。不适用：写设计文档（走 alpha-tool）。",
        "# Beta\nSECRET_BODY_MARKER_BETA 绝不能泄进中立目录。\n",
    )
    write_skill(
        root,
        "gamma-tool",
        "梳理历史事故原因与定位报错根因。触发：「为什么报错了」「查一下故障源头」。不适用：一般闲聊。",
        "# Gamma\nSECRET_BODY_MARKER_GAMMA。\n",
    )


def verify_blueprint_and_isolation(tmp: Path, failures: list[str]) -> None:
    lib = tmp / "bp" / "skills"
    build_fixture_library(lib)
    catalog = reval.load_neutral_catalog(lib)
    fp = reval.catalog_fingerprint(catalog)

    if len(catalog) != 3:
        failures.append(f"[catalog] 预期 3 个技能，实际 {len(catalog)}")
        return

    dumped = json.dumps(catalog, ensure_ascii=False)
    for marker in ("SECRET_BODY_MARKER_ALPHA", "SECRET_BODY_MARKER_BETA", "SECRET_BODY_MARKER_GAMMA"):
        if marker in dumped:
            failures.append(f"[泄正文] load_neutral_catalog 泄露了正文标记 {marker}")

    cat_a, bp_a = reval.build_blueprint_payload(
        root=lib, catalog=catalog, fp=fp, shuffle=True, seed=101,
        max_pairs=10, neg_count=4, paraphrase_count=2, focus=set(),
    )
    cat_b, _ = reval.build_blueprint_payload(
        root=lib, catalog=catalog, fp=fp, shuffle=True, seed=202,
        max_pairs=10, neg_count=4, paraphrase_count=2, focus=set(),
    )

    if cat_a["catalog_fingerprint"] != fp or cat_b["catalog_fingerprint"] != fp:
        failures.append("[fingerprint] 打乱顺序改变了 catalog_fingerprint")
    names_a = [s["name"] for s in cat_a["skills"]]
    names_b = [s["name"] for s in cat_b["skills"]]
    if sorted(names_a) != ["alpha-tool", "beta-tool", "gamma-tool"]:
        failures.append(f"[shuffle] 技能集合变动：{names_a}")
    if names_a == names_b:
        failures.append(f"[shuffle] seed 101 与 202 顺序完全相同：{names_a}")

    pairs = bp_a["neighbor_pairs"]
    if not any(p["pair"] == ["alpha-tool", "beta-tool"] and p["reason"] == "description-contrast" for p in pairs):
        failures.append(f"[neighbor] 未从 description 互相点名识别 alpha-tool/beta-tool：{pairs}")


def verify_audit_rules(tmp: Path, failures: list[str]) -> None:
    lib = tmp / "au" / "skills"
    build_fixture_library(lib)

    # 1. 合规全量活卷：零告警 + 盲测导出剥离全部标签
    good_cases = [
        {"id": "G1", "category": "positive", "query": "帮我把新模块的接口设计和流转整理成正式文档", "expected": "alpha-tool"},
        {"id": "G2", "category": "boundary", "query": "同事刚提交了一版代码改动，帮我挑挑逻辑和并发漏洞", "expected": "beta-tool", "forbidden": ["alpha-tool"]},
        {"id": "G3", "category": "positive", "query": "线上登录接口突然一直报 502，顺着线索帮我抓出问题所在", "expected": "gamma-tool"},
        {"id": "G4", "category": "negative", "query": "把这句话翻成英文：明天上午十点开会", "expected": "NONE"},
        {"id": "G5", "category": "real-badcase", "query": "看看 beta-tool 这次改动", "expected": "beta-tool", "allow_literal_slug": True},
    ]
    good_file = tmp / "au" / "good.jsonl"
    blind_file = tmp / "au" / "blind.jsonl"
    write_jsonl(good_file, good_cases)

    rc, _out, _err = _run_silent(
        reval.cmd_audit,
        argparse.Namespace(
            cases=str(good_file), root=str(lib), strict=True, allow_partial=False,
            export_blind=str(blind_file), json=False,
        ),
    )
    if rc != 0:
        failures.append(f"[误报] 合规全量活卷 strict 审计返回非零：{rc}")
    if not blind_file.is_file():
        failures.append("[export-blind] 未生成盲测题单")
    else:
        blind_rows = [json.loads(ln) for ln in blind_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if len(blind_rows) != 5:
            failures.append(f"[export-blind] 预期 5 条，实际 {len(blind_rows)}")
        for row in blind_rows:
            if set(row.keys()) != {"id", "query"}:
                failures.append(f"[export-blind] 泄露了答案字段：{row}")

    # 2. 负例夹具逐条命中 A001-A007
    bad_rows = [
        "{bad json",  # A001 JSON 错误
        {"id": "B1", "category": "positive", "query": "整理一下", "expected": "alpha-tool"},
        {"id": "B1", "category": "positive", "query": "重复ID", "expected": "alpha-tool"},  # A001 重复 id
        {"id": "B2", "category": "bogus", "query": "非法分类", "expected": "alpha-tool"},  # A001 非法 category
        {"id": "B3", "category": "positive", "query": "未知技能", "expected": "no-such-skill"},  # A002
        {"id": "B4", "category": "negative", "query": "负例标错", "expected": "alpha-tool"},  # A003 negative != NONE
        {"id": "B5", "category": "boundary", "query": "边界和稀泥", "expected": "alpha-tool", "acceptable": ["beta-tool"]},  # A003
        {"id": "B6", "category": "positive", "query": "用 alpha-tool 写方案", "expected": "alpha-tool"},  # A004 slug 泄题
        {"id": "B7", "category": "positive", "query": "请直接照着 SKILL.md 来做", "expected": "gamma-tool"},  # A004 文件名泄题
        {"id": "B8", "category": "positive", "query": "帮我看看改得行不行啊", "expected": "beta-tool"},  # A005 照抄触发样例
    ]
    bad_file = tmp / "au" / "bad.jsonl"
    write_jsonl(bad_file, bad_rows)
    _, bad_findings = reval.audit_cases(bad_file, lib, allow_partial=False)
    rules_hit = {f["rule"] for f in bad_findings}
    for need in ("A001", "A002", "A003", "A004", "A005", "A007"):
        if need not in rules_hit:
            failures.append(f"[漏报] audit 坏样例未命中 {need}，实际命中 {sorted(rules_hit)}")

    # 单独验证 A006（缺技能覆盖）与 --allow-partial 放行 A006/A007
    partial_file = tmp / "au" / "partial.jsonl"
    write_jsonl(partial_file, [
        {"id": "P1", "category": "real-badcase", "query": "线上又 502 了", "expected": "gamma-tool"},
    ])
    _, f_full = reval.audit_cases(partial_file, lib, allow_partial=False)
    rules_full = {f["rule"] for f in f_full}
    if "A006" not in rules_full or "A007" not in rules_full:
        failures.append(f"[漏报] 局部用例未触发 A006/A007：{sorted(rules_full)}")

    _, f_part = reval.audit_cases(partial_file, lib, allow_partial=True)
    if f_part:
        failures.append(f"[误报] --allow-partial 仍报出：{f_part}")

    # 验证 A008：全长题干提示 low 告警，且不阻断 --strict
    long_q = "这是一道故意写得特别冗长完整而且还把各种背景约束来龙去脉和上下游分工全部铺开说明清楚的保姆式路由题干用来专门测试中位数长度超过五十五字符阈值时的低优先级提醒"
    long_file = tmp / "au" / "long.jsonl"
    write_jsonl(long_file, [
        {"id": "L1", "category": "positive", "query": long_q + "甲", "expected": "alpha-tool"},
        {"id": "L2", "category": "positive", "query": long_q + "乙", "expected": "beta-tool"},
        {"id": "L3", "category": "positive", "query": long_q + "丙", "expected": "gamma-tool"},
        {"id": "L4", "category": "negative", "query": long_q + "丁", "expected": "NONE"},
    ])
    _, f_long = reval.audit_cases(long_file, lib, allow_partial=False)
    if not any(f["rule"] == "A008" and f["sev"] == "low" for f in f_long):
        failures.append(f"[漏报] 全长题干未触发 low 级 A008：{f_long}")
    rc_long, _, _ = _run_silent(
        reval.cmd_audit,
        argparse.Namespace(
            cases=str(long_file), root=str(lib), strict=True, allow_partial=False,
            export_blind="", json=False,
        ),
    )
    if rc_long != 0:
        failures.append(f"[误阻断] 仅含 A008 low 提示时 --strict 不应返回非零：{rc_long}")


def verify_scoring_and_reply_parser(tmp: Path, failures: list[str]) -> None:
    lib = tmp / "sc" / "skills"
    build_fixture_library(lib)
    known = {"alpha-tool", "beta-tool", "gamma-tool"}

    # parse_router_reply 容错
    p1 = reval.parse_router_reply('```json\n{"selected": "alpha-tool", "reason": "ok"}\n```')
    p2 = reval.parse_router_reply('先分析一下…… {"selected": "无需技能", "reason": "闲聊"} 完毕')
    p3 = reval.parse_router_reply("完全不是JSON")
    if p1["selected"] != "alpha-tool" or not p1["parse_ok"]:
        failures.append(f"[parse] 代码围栏 JSON 解析失败：{p1}")
    if p2["selected"] != "NONE" or not p2["parse_ok"]:
        failures.append(f"[parse] NONE 别名归一化失败：{p2}")
    if p3["selected"] != "NONE" or p3["parse_ok"]:
        failures.append(f"[parse] 坏文本处理异常：{p3}")

    cases = [
        {"id": "C1", "category": "positive", "query": "q1", "expected": "alpha-tool", "paraphrase_group": "pg1"},
        {"id": "C2", "category": "positive", "query": "q2", "expected": "alpha-tool", "paraphrase_group": "pg1"},
        {"id": "C3", "category": "boundary", "query": "q3", "expected": "beta-tool", "forbidden": ["alpha-tool"]},
        {"id": "C4", "category": "negative", "query": "q4", "expected": "NONE"},
        {"id": "C5", "category": "handoff", "query": "q5", "expected": "alpha-tool", "acceptable": ["gamma-tool"]},
        {"id": "RB1", "category": "real-badcase", "query": "q6", "expected": "gamma-tool"},
    ]
    cases_file = tmp / "sc" / "cases.jsonl"
    write_jsonl(cases_file, cases)

    # 轮次 1：C1 对、C2 错(同义不一致)、C3 命中 forbidden、C4 误触、C5 acceptable 命中、RB1 回归失败
    pred1 = tmp / "sc" / "pred1.jsonl"
    write_jsonl(pred1, [
        {"id": "C1", "selected": "alpha-tool", "reason": "ok"},
        {"id": "C2", "selected": "beta-tool", "reason": "误选"},
        {"id": "C3", "selected": "alpha-tool", "reason": "边界误抢"},
        {"id": "C4", "selected": "gamma-tool", "reason": "轻任务误触"},
        {"id": "C5", "selected": "gamma-tool", "reason": "acceptable 命中"},
        {"id": "RB1", "selected": "ghost-skill", "reason": "幻觉技能"},
    ])
    # 轮次 2：C1 依然对、C3 改对(造成 C3 抖动 1/2)、RB1 依然错、故意漏掉 C4 测 missing
    pred2 = tmp / "sc" / "pred2.jsonl"
    write_jsonl(pred2, [
        {"id": "C1", "selected": "alpha-tool", "reason": "ok"},
        {"id": "C2", "selected": "alpha-tool", "reason": "本轮对了"},
        {"id": "C3", "selected": "beta-tool", "reason": "本轮对了"},
        {"id": "C5", "selected": "alpha-tool", "reason": "ok"},
        {"id": "RB1", "selected": "alpha-tool", "reason": "仍错"},
    ])

    parsed_cases = reval._load_cases_for_score(cases_file)
    rep = reval.evaluate_runs(parsed_cases, [pred1, pred2], known_skills=known)

    # 确认不输出综合总分字段
    if any(k in rep for k in ("total_score", "overall_score", "weighted_score")):
        failures.append("[score] 不应出现综合总分字段")

    if rep["pass_at_k"] != {"count": 4, "total": 6}:
        failures.append(f"[score] pass@2 预期 4/6（C1/C2/C3/C5），实际 {rep['pass_at_k']}")
    if rep["pass_pow_k"] != {"count": 2, "total": 6}:
        failures.append(f"[score] pass^2 预期 2/6（C1/C5），实际 {rep['pass_pow_k']}")

    alerts = rep["alerts"]
    if len(alerts["forbidden_hits"]) != 1 or alerts["forbidden_hits"][0]["case_id"] != "C3":
        failures.append(f"[score] forbidden_hits 异常：{alerts['forbidden_hits']}")
    if alerts["negative_false_positives"]["by_skill"] != {"gamma-tool": 1}:
        failures.append(f"[score] negative_false_positives 异常：{alerts['negative_false_positives']}")
    jitter_ids = {j["case_id"] for j in alerts["jitter_cases"]}
    if jitter_ids != {"C2", "C3"}:
        failures.append(f"[score] 抖动用例预期 {{'C2', 'C3'}}，实际 {jitter_ids}")
    if not alerts["paraphrase_inconsistencies"] or alerts["paraphrase_inconsistencies"][0]["group"] != "pg1":
        failures.append(f"[score] 未检出同义改写组 pg1 不一致：{alerts['paraphrase_inconsistencies']}")
    if not alerts["real_badcases"] or alerts["real_badcases"][0]["status"] != "REGRESSED":
        failures.append(f"[score] RB1 未标记 REGRESSED：{alerts['real_badcases']}")

    anom = rep["anomalies"]
    if len(anom["missing_predictions"]) != 1 or anom["missing_predictions"][0]["case_id"] != "C4":
        failures.append(f"[score] 未检出缺失预测 C4：{anom['missing_predictions']}")
    if len(anom["hallucinated_skills"]) != 1 or anom["hallucinated_skills"][0]["selected"] != "ghost-skill":
        failures.append(f"[score] 未检出幻觉技能名 ghost-skill：{anom['hallucinated_skills']}")

    # 验证 --fail-on-* 与 --max-miss-rate 退出码
    base_score_ns = dict(
        cases=str(cases_file), preds=[str(pred1)], root=str(lib), model_label="test",
        fail_on_forbidden=False, fail_on_neg_fp=False, fail_on_real_badcase=False,
        max_miss_rate=None, json=True,
    )
    rc_diag, out_diag, _ = _run_silent(reval.cmd_score, argparse.Namespace(**base_score_ns))
    if rc_diag != 0 or '"total_score"' in out_diag:
        failures.append(f"[score] 默认诊断模式应返回 0 且无总分：{rc_diag}")

    for flag in ("fail_on_forbidden", "fail_on_neg_fp", "fail_on_real_badcase"):
        ns = dict(base_score_ns)
        ns[flag] = True
        rc_flag, _, _ = _run_silent(reval.cmd_score, argparse.Namespace(**ns))
        if rc_flag != 1:
            failures.append(f"[score] {flag}=True 应返回 1，实际 {rc_flag}")

    ns_rate = dict(base_score_ns)
    ns_rate["max_miss_rate"] = 0.2
    rc_rate, _, _ = _run_silent(reval.cmd_score, argparse.Namespace(**ns_rate))
    if rc_rate != 1:
        failures.append(f"[score] --max-miss-rate 0.2 应返回 1，实际 {rc_rate}")


def verify_run_missing_env_and_http_mock(tmp: Path, failures: list[str]) -> None:
    cat_file = tmp / "cat.json"
    blind_file = tmp / "blind.jsonl"
    out_file = tmp / "out.jsonl"
    cat_file.write_text('{"skills":[{"name":"alpha-tool","description":"desc"}]}', encoding="utf-8")
    blind_file.write_text('{"id":"1","query":"hi"}\n', encoding="utf-8")

    old_env = {k: os.environ.pop(k, None) for k in ("ROUTE_EVAL_BASE_URL", "ROUTE_EVAL_API_KEY", "ROUTE_EVAL_MODEL")}
    try:
        rc, _, err = _run_silent(
            reval.cmd_run,
            argparse.Namespace(
                catalog=str(cat_file), blind_cases=str(blind_file), out=str(out_file),
                base_url="", api_key_env="ROUTE_EVAL_API_KEY", model="", temperature=0.0, timeout=5,
            ),
        )
        if rc != 2 or "干净上下文子代理" not in err:
            failures.append(f"[run] 缺少环境变量时应以 exit 2 安全退出并给指引，实际 {rc}: {err}")

        os.environ["ROUTE_EVAL_BASE_URL"] = "https://example.invalid/v1"
        os.environ["ROUTE_EVAL_API_KEY"] = "secret-token-never-print"
        os.environ["ROUTE_EVAL_MODEL"] = "mock-model"

        class _FakeResp:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps({
                    "choices": [{"message": {"content": '{"selected":"alpha-tool","reason":"ok"}'}}]
                }).encode("utf-8")

        with mock.patch("urllib.request.urlopen", return_value=_FakeResp()):
            rc2, _, _ = _run_silent(
                reval.cmd_run,
                argparse.Namespace(
                    catalog=str(cat_file), blind_cases=str(blind_file), out=str(out_file),
                    base_url="", api_key_env="ROUTE_EVAL_API_KEY", model="", temperature=0.0, timeout=5,
                ),
            )
        if rc2 != 0 or not out_file.is_file():
            failures.append(f"[run] mock HTTP 执行失败：rc={rc2}")
        else:
            row = json.loads(out_file.read_text(encoding="utf-8").strip())
            if row["selected"] != "alpha-tool" or not row["parse_ok"]:
                failures.append(f"[run] mock HTTP 输出异常：{row}")
    finally:
        for k, v in old_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="route-eval-fixture-"))
    failures: list[str] = []
    try:
        verify_blueprint_and_isolation(tmp, failures)
        verify_audit_rules(tmp, failures)
        verify_scoring_and_reply_parser(tmp, failures)
        verify_run_missing_env_and_http_mock(tmp, failures)

        if failures:
            print("route_eval 自测失败：")
            for msg in failures:
                print("  -", msg)
            return 1

        print("route_eval 自测通过 ✅  中立脱敏、乱序指纹、A001–A007、多轮 pass^k/混淆/抖动/同义/回归告警全通过。")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
