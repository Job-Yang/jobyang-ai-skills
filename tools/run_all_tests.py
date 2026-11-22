#!/usr/bin/env python3
"""全仓统一验证入口：一键运行静态门禁、宪法校验、半角标点、OPC 漂移及技能测试套件（纯标准库）。"""
from __future__ import annotations

import concurrent.futures
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / "skills"
EXPECTED_CONSTITUTION = "90f73c003c272371,74820e83cbe08119,6754cf0458fd910c"
OPC_PACKAGES = [
    "opportunity-radar",
    "opportunity-scorecard",
    "product-brief",
    "style-compass",
    "engineering-docs",
]


def pick_media_python() -> str:
    """为 png-compress / video-reader 优先挑选同时装有 PIL 与 cv2 的 Python 解释器。"""
    candidates = [sys.executable, "/usr/bin/python3", shutil.which("python3") or ""]
    best = sys.executable
    best_score = -1
    seen = set()
    for py in candidates:
        if not py or py in seen or not Path(py).exists():
            continue
        seen.add(py)
        probe = subprocess.run(
            [py, "-c", "import importlib.util; print(int(bool(importlib.util.find_spec('PIL'))) + int(bool(importlib.util.find_spec('cv2'))))"],
            capture_output=True, text=True,
        )
        if probe.returncode == 0 and probe.stdout.strip().isdigit():
            score = int(probe.stdout.strip())
            if score > best_score:
                best_score = score
                best = py
    return best


def run_step(name: str, cmd: list[str], cwd: Path = REPO_ROOT) -> tuple[bool, float, str]:
    t0 = time.monotonic()
    env = {**os.environ, "PYTHONPATH": str(cwd)}
    r = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True)
    dt = time.monotonic() - t0
    out = (r.stdout + "\n" + r.stderr).strip()
    return r.returncode == 0, dt, out


def run_phase(checks: list[tuple[str, list[str], Path]], max_workers: int = 4) -> list[tuple[str, str]]:
    failures: list[tuple[str, str]] = []
    results: dict[int, tuple[bool, float, str]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(run_step, name, cmd, cwd): idx for idx, (name, cmd, cwd) in enumerate(checks)}
        for fut in concurrent.futures.as_completed(futs):
            idx = futs[fut]
            results[idx] = fut.result()

    for idx, (name, _, _) in enumerate(checks):
        ok, dt, out = results[idx]
        tail = ""
        for line in reversed(out.splitlines()):
            if line.strip():
                tail = line.strip()[:120]
                break
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name:<36} ({dt:5.2f}s) {tail}", flush=True)
        if not ok:
            failures.append((name, out))
    return failures


def main() -> int:
    all_md = sorted(
        [str(s / "SKILL.md") for s in SKILLS_ROOT.iterdir() if s.is_dir() and (s / "SKILL.md").is_file()]
        + [
            str(rf)
            for s in SKILLS_ROOT.iterdir()
            if s.is_dir() and (s / "references").is_dir()
            for rf in (s / "references").rglob("*.md")
        ]
    )
    opc_dirs = [str(SKILLS_ROOT / p) for p in OPC_PACKAGES]
    media_py = pick_media_python()

    repo_checks: list[tuple[str, list[str], Path]] = [
        ("doctor:test_doctor", [sys.executable, str(SKILLS_ROOT / "skill-library-keeper/scripts/test_doctor.py")], REPO_ROOT),
        ("doctor:library_doctor --strict", [sys.executable, str(SKILLS_ROOT / "skill-library-keeper/scripts/library_doctor.py"), str(SKILLS_ROOT), "--strict"], REPO_ROOT),
        ("haohao:check_integrity", [sys.executable, str(SKILLS_ROOT / "haohao-shuohua/scripts/check_integrity.py"), "--expect", EXPECTED_CONSTITUTION], REPO_ROOT),
        ("haohao:quick_scan --checks half", [sys.executable, str(SKILLS_ROOT / "haohao-shuohua/scripts/quick_scan.py"), *all_md, "--checks", "half", "--fail-on", "half"], REPO_ROOT),
        ("opc:check_vendored --drift", [sys.executable, str(SKILLS_ROOT / "opportunity-radar/scripts/check_vendored.py"), "--drift", *opc_dirs], REPO_ROOT),
        ("opc:check_handoff", [sys.executable, str(SKILLS_ROOT / "opportunity-radar/scripts/check_handoff.py"), *opc_dirs], REPO_ROOT),
    ]

    unittest_skills = [
        "ai-briefing",
        "engineering-docs",
        "haohao-shuohua",
        "me-context",
        "opportunity-radar",
        "opportunity-scorecard",
        "product-brief",
        "skill-library-keeper",
        "style-compass",
        "talk-smith",
    ]
    skill_checks: list[tuple[str, list[str], Path]] = [
        (f"tests:{s}", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "tests"], SKILLS_ROOT / s)
        for s in unittest_skills
    ]
    skill_checks.extend([
        ("tests:haohao-eval", [sys.executable, "-m", "unittest", "discover", "-s", "scripts", "-t", "scripts"], SKILLS_ROOT / "haohao-eval"),
        ("tests:me-context:selftest", ["bash", "tests/run_selftest.sh"], SKILLS_ROOT / "me-context"),
        ("tests:png-compress", [media_py, "-m", "unittest", "discover", "-s", "tests", "-t", "tests"], SKILLS_ROOT / "png-compress"),
        ("tests:video-reader", [media_py, "-m", "unittest", "discover", "-s", "tests", "-t", "tests"], SKILLS_ROOT / "video-reader"),
        ("tests:content-infographic:render", [sys.executable, "tests/test_render.py"], SKILLS_ROOT / "content-infographic"),
        ("tests:content-infographic:linkage", [sys.executable, "tests/test_linkage.py"], SKILLS_ROOT / "content-infographic"),
        ("tests:content-infographic:backends", [sys.executable, "tests/test_backends.py"], SKILLS_ROOT / "content-infographic"),
    ])

    total = len(repo_checks) + len(skill_checks)
    t_all = time.monotonic()
    print(f"repo={REPO_ROOT} | media_python={media_py}\n", flush=True)
    failures = run_phase(repo_checks, max_workers=4)
    failures.extend(run_phase(skill_checks, max_workers=4))

    total_dt = time.monotonic() - t_all
    print(f"\n总计 {total} 项检查，通过 {total - len(failures)}，失败 {len(failures)}（耗时 {total_dt:.2f}s）", flush=True)
    if failures:
        print("\n=== 失败详情 ===", flush=True)
        for name, out in failures:
            print(f"\n--- {name} ---\n{out}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
