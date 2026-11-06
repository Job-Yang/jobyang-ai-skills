#!/usr/bin/env python3
"""scorecard 回归测试（标准库 unittest，无第三方依赖）。

覆盖原诊断里实锤的四类问题，每条都先构造"旧代码会失败"的输入：
  T1 缺维度/非法输入不再裸 traceback，main() 输出 JSON 错误信封到 stderr、exit 1；
  T2 打分最小步长 0.5，6.75 这类伪精确直接报错；
  T3 topic slug 与冻结版 artifact_io 的 SLUG 逐字一致（watch--sedentary 两边都拒）；
  T4 占位词表是 artifact_io 集合的超集（N/A、TODO 等先在入口被拦）。
另验三个 examples 的确定性输出（synthetic / foundation-reject / dark-horse）。

跑法：python3 -m unittest discover -s tests -v
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import score  # noqa: E402
from artifact_io import SLUG, validate_envelope  # noqa: E402


def _base_input(**overrides):
    """一份完全合法的评分 JSON，调用方按用例覆写局部字段。"""
    dims = [
        {"name": n, "score": 6.5, "evidence": f"真实证据：{n} 的原话引用（示例）"}
        for n, _ in score.DIMENSIONS
    ]
    data = {
        "topic": "watch-sedentary",
        "one_liner": "给久坐白领用 Watch 数据做及时干预（示例）",
        "upstream": None,
        "profile": {"form": "iOS", "endpoint": "iPhone", "market": "出海",
                    "monetization": "订阅", "competitors": []},
        "foundation": {"pass": True, "reason": "命题成立（示例）"},
        "dimensions": dims,
        "diagnosis": "",
        "rebuttal": {"claim": "", "blindspot": ""},
    }
    data.update(overrides)
    return data


class TopicSlugTest(unittest.TestCase):
    def test_slug_regex_matches_artifact_io(self):
        """T3：score.py 的 topic 规则与冻结版 artifact_io.SLUG 逐字同分布。"""
        cases = ["watch-sedentary", "a", "ab-cd-ef", "perimenopause-navigator"]
        for s in cases:
            with self.subTest(s=s):
                self.assertIsNotNone(score.TOPIC_SLUG.fullmatch(s), f"score.py 拒绝合法 slug {s}")
                self.assertIsNotNone(SLUG.fullmatch(s), f"artifact_io 拒绝合法 slug {s}")

    def test_double_hyphen_rejected_by_both(self):
        """T3 回归：watch--sedentary 必须被两边一致拒绝。"""
        bad = ["watch--sedentary", "-watch", "watch-", "Watch", "watch_sedentary", "a--b"]
        for s in bad:
            with self.subTest(s=s):
                self.assertIsNone(score.TOPIC_SLUG.fullmatch(s), f"score.py 漏放了 {s}")
                self.assertIsNone(SLUG.fullmatch(s), f"artifact_io 漏放了 {s}")
        data = _base_input(topic="watch--sedentary")
        with self.assertRaises(ValueError):
            score.evaluate(data)


class StepTest(unittest.TestCase):
    def test_half_step_only(self):
        """T2：6.75 伪精确必须报错；6.5 / 6.0 / 6.5 边界合法。"""
        data = _base_input()
        data["dimensions"][0]["score"] = 6.75
        with self.assertRaises(ValueError) as cm:
            score.evaluate(data)
        self.assertIn("0.5", str(cm.exception))
        for ok in (0, 0.5, 6.0, 9.5, 10.0):
            d = _base_input()
            d["dimensions"][0]["score"] = ok
            self.assertIsNotNone(score.evaluate(d), f"{ok} 应合法")


class PlaceholderTest(unittest.TestCase):
    def test_placeholder_evidence_rejected(self):
        """T4：N/A 家族、TODO、待补、无 一律算没挂证据。"""
        for bad in ["N/A", "n/a", "NA", "TODO", "待补", "无", "...", "—", "<待定>"]:
            d = _base_input()
            d["dimensions"][0]["evidence"] = bad
            with self.assertRaises(ValueError, msg=f"占位证据 {bad} 被漏放"):
                score.evaluate(d)


class ErrorEnvelopeTest(unittest.TestCase):
    def test_missing_dimension_raises(self):
        """T1（内核层）：缺维度一次性汇总报错，而不是算一半崩掉。"""
        data = _base_input()
        data["dimensions"].pop()
        with self.assertRaises(ValueError) as cm:
            score.evaluate(data)
        self.assertIn("缺维度", str(cm.exception))

    def test_main_prints_json_error_envelope(self):
        """T1（进程层）：坏输入的 stderr 是与 artifact_io 同形的 JSON，exit 1。"""
        bad = _base_input()
        bad["dimensions"].pop()
        tmp = ROOT / "tests" / "_tmp_bad_input.json"
        tmp.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "score.py"), "--input", str(tmp)],
                capture_output=True, text=True)
            self.assertEqual(1, proc.returncode, "exit code 必须为 1")
            err = json.loads(proc.stderr)
            self.assertEqual("rejected", err["status"])
            self.assertIn("缺维度", err["error"])
            self.assertNotIn("Traceback", proc.stderr, "不许裸 traceback")
        finally:
            tmp.unlink()


class ExamplesTest(unittest.TestCase):
    def test_synthetic_example(self):
        data = json.loads((ROOT / "examples" / "scoring.synthetic.json").read_text(encoding="utf-8"))
        r = score.evaluate(data)
        self.assertEqual(6.5, r["composite_score"])
        self.assertEqual("validate", r["verdict"])
        self.assertFalse(r["dark_horse"])

    def test_foundation_reject_example(self):
        data = json.loads((ROOT / "examples" / "scoring.foundation-reject.json").read_text(encoding="utf-8"))
        r = score.evaluate(data)
        self.assertEqual("reject", r["verdict"], "地基门否决优先于任何分数")
        self.assertFalse(r["dark_horse"], "地基门否掉不给黑马逃生")

    def test_dark_horse_example(self):
        data = json.loads((ROOT / "examples" / "scoring.dark-horse.json").read_text(encoding="utf-8"))
        r = score.evaluate(data)
        self.assertEqual(5.0, r["composite_score"])
        self.assertEqual("refine", r["verdict"])
        self.assertTrue(r["dark_horse"], "机械分低于 6.5 且申辩有形状必须标黑马")


class CardContractTest(unittest.TestCase):
    def test_rendered_card_passes_frozen_artifact_io(self):
        """契约不变：score.py 出的卡必须被冻结版 artifact_io 完整 validate 通过。"""
        data = json.loads((ROOT / "examples" / "scoring.synthetic.json").read_text(encoding="utf-8"))
        r = score.evaluate(data)
        card = score.render(r, producer="unittest")
        fm, errors = validate_envelope(card)
        self.assertEqual([], errors, f"出卡未过冻结版校验：{errors}")

    def test_card_carries_prior_weight_caveat(self):
        """尺子置信度：先验权重/非统计显著必须写进卡片，防止被当成数据结论。"""
        data = json.loads((ROOT / "examples" / "scoring.synthetic.json").read_text(encoding="utf-8"))
        r = score.evaluate(data)
        self.assertFalse(r["method_caveats"]["statistical_significance"])
        card = score.render(r, producer="unittest")
        self.assertIn("非统计显著", card)


class AdversarialTest(unittest.TestCase):
    """对抗样例：全 10 / 全 1 / 互相矛盾 / 伪造证据 / 同一证据复用。"""

    def test_all_ten_ceiling(self):
        data = json.loads((ROOT / "examples" / "scoring.all-ten.json").read_text(encoding="utf-8"))
        r = score.evaluate(data)
        self.assertEqual(10.0, r["composite_score"])
        self.assertEqual("validate", r["verdict"])

    def test_all_one_floor(self):
        data = json.loads((ROOT / "examples" / "scoring.all-one.json").read_text(encoding="utf-8"))
        r = score.evaluate(data)
        self.assertEqual(1.0, r["composite_score"])
        self.assertEqual("reject", r["verdict"], "地板分必须落 reject，不逃逸")

    def test_contradictory_input_does_not_crash_and_warns(self):
        """互相矛盾的维度 + 同料复用 + 无链接不可验证证据：不崩溃、警告可见、卡仍过冻结校验。"""
        data = json.loads((ROOT / "examples" / "scoring.contradictory.json").read_text(encoding="utf-8"))
        r = score.evaluate(data)
        warns = "\n".join(r["evidence_warnings"])
        self.assertIn("复用", warns, warns)
        self.assertIn("不可验证", warns, warns)
        card = score.render(r, producer="unittest")
        _, errors = validate_envelope(card)
        self.assertEqual([], errors, f"矛盾输入出卡未过冻结校验：{errors}")

    def test_reused_evidence_warning(self):
        d = _base_input()
        d["dimensions"][0]["evidence"] = "假设：同一料喂两维"
        d["dimensions"][1]["evidence"] = "假设：同一料喂两维"
        r = score.evaluate(d)
        self.assertTrue(any("复用" in w for w in r["evidence_warnings"]), r["evidence_warnings"])

    def test_unverifiable_evidence_warning(self):
        d = _base_input()
        d["dimensions"][0]["evidence"] = "内部消息，不便透露"
        r = score.evaluate(d)
        self.assertTrue(any("不可验证" in w for w in r["evidence_warnings"]), r["evidence_warnings"])

    def test_all_hearsay_evidence_lock_blocks_clean(self):
        """复评驳回#3：十维全传闻（无 http）→ evidence_lock 置位 + 卡片强制警告，不得 clean。"""
        d = _base_input()  # 所有维度证据均无链接
        r = score.evaluate(d)
        self.assertEqual("all_unverifiable", r["evidence_lock"], r["evidence_lock"])
        self.assertEqual(0, r["real_evidence_count"])
        card = score.render(r, producer="unittest")
        self.assertIn("evidence_lock: all_unverifiable", card)
        self.assertIn("不可 clean", card)
        # 机器 verdict 档位不变，仍须过冻结校验
        self.assertEqual("validate", r["verdict"])
        _, errors = validate_envelope(card)
        self.assertEqual([], errors, f"带 lock 的卡未过冻结校验：{errors}")

    def test_one_real_evidence_is_clean(self):
        """复评驳回#3 反例：有一条硬 http 证据 → 不 lock，clean validate。"""
        d = _base_input()
        d["dimensions"][0]["evidence"] = "https://reddit.com/r/x 高频原话引用"
        r = score.evaluate(d)
        self.assertIsNone(r["evidence_lock"], r["evidence_lock"])
        self.assertEqual(1, r["real_evidence_count"])
        card = score.render(r, producer="unittest")
        self.assertNotIn("不可 clean", card)


if __name__ == "__main__":
    unittest.main()
