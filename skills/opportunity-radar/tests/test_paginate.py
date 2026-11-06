#!/usr/bin/env python3
"""paginate.py 回归：候选超量分页/合并（标准库 unittest）。

验收：
  - 25 条候选按每页 10 条切成 3 页，manifest 计数正确；
  - 每一页单独过冻结版 artifact_io.validate_envelope（分页不破坏信封契约）；
  - merge 后还原 25 条候选且合并件仍过冻结校验；
  - 候选不足一页时只有 1 页，不硬拆。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "paginate.py"
sys.path.insert(0, str(ROOT / "scripts"))
from artifact_io import validate_envelope  # noqa: E402


def make_radar(n: int) -> str:
    fm = ["---", "schema: opc-artifact/v1", "opc_node: radar", "artifact_kind: radar",
          "opc_version: 0.2.0", "topic: null", "created: 2026-10-16T10:00:00+00:00",
          "upstream: null", "produced_by: unittest", "human_review: pending", "---", ""]
    body = ["# 今日候选\n", "前言：扫了一圈。\n"]
    for i in range(n):
        body += [
            f"## 候选：机会编号{i:02d}",
            f"- 领域：效率{i}",
            f"- 证据：https://example.com/e{i} — 原话引用",
            f"- 信号强度：中 + 理由",
            "evidence: real",
            "",
        ]
    return "\n".join(fm + body)


class PaginateTest(unittest.TestCase):
    def run_cmd(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True, text=True)

    def test_split_merge_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "radar-2026-10-16.md"
            src.write_text(make_radar(25), encoding="utf-8")
            out_dir = td / "pages"
            proc = self.run_cmd("split", "--input", str(src), "--out-dir", str(out_dir),
                                "--page-size", "10")
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
            manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(25, manifest["candidate_count"])
            self.assertEqual(3, manifest["page_count"])
            counts = [(out_dir / n).read_text(encoding="utf-8").count("## 候选：")
                      for n in manifest["pages"]]
            self.assertEqual([10, 10, 5], counts, "每页不超过 page-size，尾页装剩余")
            # 每一页单独过冻结信封校验
            for name in manifest["pages"]:
                md = (out_dir / name).read_text(encoding="utf-8")
                _, errors = validate_envelope(md)
                self.assertEqual([], errors, f"{name} 未过冻结校验：{errors}")
            # merge 还原
            merged = td / "merged.md"
            proc = self.run_cmd("merge", "--manifest", str(out_dir / "manifest.json"),
                                "--out", str(merged))
            self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
            text = merged.read_text(encoding="utf-8")
            self.assertEqual(25, text.count("## 候选："), "合并后候选数必须还原")
            _, errors = validate_envelope(text)
            self.assertEqual([], errors, f"合并件未过冻结校验：{errors}")

    def test_small_set_not_split(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "r.md"
            src.write_text(make_radar(5), encoding="utf-8")
            out_dir = td / "pages"
            proc = self.run_cmd("split", "--input", str(src), "--out-dir", str(out_dir))
            self.assertEqual(0, proc.returncode, proc.stderr)
            manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["page_count"], "不足一页不硬拆")
            self.assertEqual(5, manifest["candidate_count"])

    def test_rejects_non_radar_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "bad.md"
            src.write_text("没有信封的纯文本", encoding="utf-8")
            proc = self.run_cmd("split", "--input", str(src), "--out-dir", str(td / "p"))
            self.assertEqual(2, proc.returncode)
            self.assertIn("rejected", json.loads(proc.stderr)["status"])


if __name__ == "__main__":
    unittest.main()
