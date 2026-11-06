#!/usr/bin/env python3
"""handoff 示例 opc_node drift 检查（纯 stdlib）。

历史事故：radar 包的 references/handoff.md 信封示例一度写成 opc_node: prd
（通用模板直抄），按它操作的雷达产物会被冻结 artifact_io 当成 prd 校验并拒。
本脚本让这类 drift 可被自动发现：

  每个包的 handoff.md 里出现的 opc_node 必须全部是本节点自己：
    opportunity-radar    → 只能出现 opc_node: radar
    opportunity-scorecard → 只能出现 opc_node: assess
    product-brief       → 只能出现 opc_node: prd

用法：python3 scripts/check_handoff.py [skill_root ...]
退出码：0=无 drift；1=发现 drift；2=参数/文件错误。
"""
import re
import sys
from pathlib import Path

EXPECTED = {
    "opportunity-radar": "radar",
    "opportunity-scorecard": "assess",
    "product-brief": "prd",
}
_NODE_LINE = re.compile(r"opc_node:\s*([a-z][a-z0-9_-]*)")


def check_root(root: Path) -> int:
    expected = EXPECTED.get(root.name)
    if expected is None:
        print(f"[handoff] SKIP 未知包：{root.name}（不检查）")
        return 0
    hf = root / "references" / "handoff.md"
    if not hf.exists():
        print(f"[handoff] MISSING {hf}")
        return 1
    drift = 0
    for i, line in enumerate(hf.read_text(encoding="utf-8").splitlines(), 1):
        m = _NODE_LINE.search(line)
        if m and m.group(1) != expected:
            drift += 1
            print(f"[handoff] DRIFT {root.name}:{i} opc_node={m.group(1)}"
                  f"（本节点应为 {expected}）")
    if drift == 0:
        print(f"[handoff] OK {root.name}（opc_node 全部为 {expected}）")
    return drift


def main(argv) -> int:
    roots = [Path(a) for a in argv] or [Path(__file__).resolve().parent.parent]
    total = 0
    for r in roots:
        total += check_root(r.resolve())
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
