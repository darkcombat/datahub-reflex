#!/usr/bin/env python3
"""Run deterministic pre-submission checks without changing external state."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REQUIRED_FILES = (
    "LICENSE",
    "README.md",
    ".env.example",
    "docs/scope.md",
    "docs/limits.md",
    "docs/evaluation.md",
    "docs/submission_checklist.md",
    "docs/devpost_submission.md",
    "scripts/seed_live_datahub.py",
    "examples/evaluation/summary.json",
)


def main() -> int:
    failures: list[str] = []

    for relative_path in REQUIRED_FILES:
        if not (ROOT / relative_path).is_file():
            failures.append(f"missing file: {relative_path}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "<YOUR_PUBLIC_REPOSITORY_URL>" in readme:
        # This is a documented placeholder, not a claim that a public URL exists.
        pass
    if "self-healing" not in readme.lower():
        failures.append("README does not document the self-healing limitation")
    if "run_assertion()" not in readme:
        failures.append("README does not document the OSS assertion boundary")

    summary_path = ROOT / "examples/evaluation/summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("overall_go_no_go") is not True:
            failures.append("evaluation summary is not GO")

    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in {".git", ".pytest_cache", ".ruff_cache"} for part in path.parts):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        if path.suffix.lower() not in {".py", ".md", ".json", ".yaml", ".yml", ".env", ".example"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if re.search(r"(?:sk-|ghp_|AKIA[0-9A-Z]{16})", content):
            failures.append(f"possible credential pattern: {path.relative_to(ROOT)}")

    if failures:
        print("SUBMISSION AUDIT: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("SUBMISSION AUDIT: PASS")
    print(f"Checked {len(REQUIRED_FILES)} required repository artifacts")
    print("External publication remains intentionally separate: repository URL, video URL, and Devpost submission.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
