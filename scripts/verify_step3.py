#!/usr/bin/env python3
"""Step 3 verification script for DataHub Reflex.

Runs the complete test suite and reports on the verified live Reflex/DataHub lifecycle.

Usage:
    python scripts/verify_step3.py              # Run all tests
    python scripts/verify_step3.py --live-only  # Only live DataHub tests
    python scripts/verify_step3.py --unit-only  # Only unit tests

Environment:
    DATAHUB_GMS_URL    — DataHub GMS endpoint (default: http://localhost:8080)
    DATAHUB_GMS_TOKEN  — DataHub auth token
    REFLEX_TEST_PREFIX — Prefix for isolated test URNs (default: reflex-test)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

STEPS = {
    1: "Incident creation (raiseIncident)",
    2: "Incident status update (ACTIVE → RESOLVED)",
    3: "Root-cause approval in Reflex",
    4: "Lesson extraction",
    5: "Candidate discovery from DataHub (searchAcrossEntities)",
    6: "Control synthesis",
    7: "Reflex-owned historical backtest",
    8: "Human control approval",
    9: "Assertion definition write-back (SYNTHETIC/Reflex-owned on OSS)",
    10: "Structured-property coverage write-back (SYNTHETIC/Reflex-owned on OSS)",
    11: "Assertion run-event write-back (Reflex-owned execution)",
    12: "Analogous duplicate detection",
    13: "New incident creation (raiseIncident for detections)",
    14: "Complete reset and rerun",
}

UP = "\u2713"  # ✓
DOWN = "\u2717"  # ✗
WARN = "\u26a0"  # ⚠


def run_pytest(args: list[str]) -> subprocess.CompletedProcess:
    """Run pytest with given arguments and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "pytest"] + args,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )


def check_datahub() -> bool:
    """Check if DataHub GMS is reachable."""
    try:
        import httpx
        gms_url = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")
        resp = httpx.get(f"{gms_url}/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Verify Step 3 integration tests")
    parser.add_argument("--live-only", action="store_true", help="Only live DataHub tests")
    parser.add_argument("--unit-only", action="store_true", help="Only unit/evaluation tests")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet output")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)

    print("=" * 60)
    print("DataHub Reflex — Step 3 Verification")
    print(f"Project: {project_root}")
    print(f"DataHub GMS: {os.environ.get('DATAHUB_GMS_URL', 'http://localhost:8080')}")
    print(f"Test prefix: {os.environ.get('REFLEX_TEST_PREFIX', 'reflex-test')}")
    print("=" * 60)

    datahub_available = check_datahub()
    print(f"\nDataHub available: {'YES' if datahub_available else 'NO (live tests will skip)'}")

    # -------------------------------------------------------------------
    # 1. Unit + evaluation tests (always run)
    # -------------------------------------------------------------------
    if not args.live_only:
        print("\n--- Unit & Evaluation Tests ---")
        result = run_pytest([
            "tests/unit/", "tests/evaluation/",
            "-v" if not args.quiet else "-q",
            "--tb=short",
        ])
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
            print(f"\n{DOWN} Unit tests FAILED")
        else:
            print(f"{UP} Unit & evaluation tests PASSED")

    # -------------------------------------------------------------------
    # 2. Spike tests
    # -------------------------------------------------------------------
    if not args.live_only:
        print("\n--- Spike Tests ---")
        result = run_pytest([
            "spikes/",
            "-v" if not args.quiet else "-q",
            "--tb=short",
        ])
        print(result.stdout)
        if result.returncode != 0:
            print(f"\n{DOWN} Spike tests FAILED")
        else:
            print(f"{UP} Spike tests PASSED")

    # -------------------------------------------------------------------
    # 3. Live integration tests
    # -------------------------------------------------------------------
    if not args.unit_only:
        print("\n--- Live DataHub Integration Tests ---")
        if not datahub_available:
            print(f"{WARN} DataHub not available — skipping live tests")
        else:
            result = run_pytest([
                "tests/integration/",
                "-v" if not args.quiet else "-q",
                "--tb=short",
                "-m", "requires_datahub",
            ])
            print(result.stdout)
            if result.returncode != 0:
                print(f"\n{DOWN} Live integration tests FAILED (some may have timed out)")
            else:
                print(f"{UP} Live integration tests PASSED")

    # -------------------------------------------------------------------
    # 4. Summary
    # -------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Step 3 — 14-Step Lifecycle Coverage:")
    print("=" * 60)
    for num, desc in STEPS.items():
        synthetic = "SYNTHETIC" if "SYNTHETIC" in desc else ""
        reflex_owned = "Reflex-owned" if "Reflex-owned" in desc else ""
        marker = ""
        if synthetic:
            marker = f" [{synthetic}]"
        elif reflex_owned:
            marker = f" [{reflex_owned}]"
        print(f"  {num:2d}. {desc}{marker}")

    print("\nRun individual test files:")
    print("  python -m pytest tests/integration/test_reflex_loop.py -v")
    print("  python -m pytest tests/integration/test_reset_and_rerun.py -v")
    print("  python -m pytest tests/ -v -m requires_datahub")
    print("  python -m pytest tests/ -v -m \"not requires_datahub\"")

    if not datahub_available:
        print(f"\n{WARN} Start DataHub with: python -m datahub docker quickstart")
        print("     Then seed with: python scripts/seed_datahub.py")
        print("     Then re-run: python scripts/verify_step3.py")


if __name__ == "__main__":
    main()
