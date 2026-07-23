#!/usr/bin/env python3
"""Run the reproducible checks required before recording the judge demo.

This command is intentionally read-only with respect to tracked project
artifacts. It validates the already-recorded evaluation evidence instead of
rerunning the evaluation writer, which keeps a clean checkout reproducible.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run(label: str, command: list[str]) -> bool:
    print(f"\n== {label} ==")
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        print(f"FAILED: {label} (exit {result.returncode})")
        return False
    print(f"PASS: {label}")
    return True


def git_status() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="also run the live DataHub integration suite",
    )
    args = parser.parse_args()

    failures: list[str] = []
    initial_status = git_status()
    if initial_status:
        failures.append("working tree is not clean before preflight")
        for line in initial_status:
            print(f"  {line}")

    required_files = [
        ROOT / "docs" / "demo_script.md",
        ROOT / "docs" / "submission_checklist.md",
        ROOT / "examples" / "evaluation" / "summary.json",
    ]
    for path in required_files:
        if not path.is_file():
            failures.append(f"missing required file: {path.relative_to(ROOT)}")

    summary_path = ROOT / "examples" / "evaluation" / "summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("overall_go_no_go") is not True:
            failures.append("recorded evaluation summary is not GO")

    checks = [
        ("submission audit", [sys.executable, "scripts/audit_submission.py"]),
        (
            "offline test suite",
            [sys.executable, "-m", "pytest", "-q", "tests/unit", "tests/evaluation", "tests/ui"],
        ),
    ]
    if args.live:
        checks.append(
            (
                "live DataHub integration suite",
                [sys.executable, "-m", "pytest", "-q", "tests/integration/test_live_datahub.py"],
            )
        )

    for label, command in checks:
        if not run(label, command):
            failures.append(label)

    final_status = git_status()
    if final_status:
        failures.append("preflight changed the working tree")
        for line in final_status:
            print(f"  {line}")

    print("\n" + ("RECORDING PREFLIGHT: PASS" if not failures else "RECORDING PREFLIGHT: FAIL"))
    if failures:
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("The repository is ready for a clean judge-demo rehearsal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
