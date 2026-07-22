#!/usr/bin/env python3
"""Reset the demo state to a clean starting point.

Deletes all Reflex-generated artifacts while preserving the seed data.
Use this to reset between demo runs.

Usage:
    python scripts/reset_demo.py
"""

from __future__ import annotations

import shutil
from pathlib import Path


def reset() -> None:
    """Reset the demo state."""
    print("=" * 60)
    print("DataHub Reflex — Reset Demo State")
    print("=" * 60)

    # Clean artifacts that are generated during a Reflex run
    artifacts = [
        Path("./datasets/approvals"),
        Path("./datasets/output"),
    ]

    for artifact in artifacts:
        if artifact.exists():
            shutil.rmtree(artifact)
            print(f"  Removed: {artifact}")
        else:
            print(f"  Skipped (not found): {artifact}")

    # Clean Python cache
    for cache_dir in Path(".").rglob("__pycache__"):
        shutil.rmtree(cache_dir)
        print(f"  Removed cache: {cache_dir}")

    print("\nReset complete. Seed data preserved.")
    print("Re-run: python scripts/seed_history.py to regenerate history if needed.")


if __name__ == "__main__":
    reset()
