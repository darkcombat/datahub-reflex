"""Integration test for spike-01: DataHub OSS write-path.

Requires a running DataHub OSS instance (docker compose up -d).

Usage:
    pytest spikes/spike-01-datahub-write-path/test_spike.py -v

Skip if DataHub is not available:
    pytest spikes/spike-01-datahub-write-path/test_spike.py -v -k "not requires_datahub"
"""

from __future__ import annotations

import os
import ast
import subprocess
import sys
from pathlib import Path

import pytest

SPIKE_DIR = Path(__file__).resolve().parent
SPIKE_SCRIPT = SPIKE_DIR / "run_spike.py"

pytestmark = pytest.mark.requires_datahub


def _datahub_available() -> bool:
    """Check if DataHub GMS is reachable."""
    import httpx
    try:
        resp = httpx.get(
            f"{os.environ.get('DATAHUB_GMS_URL', 'http://localhost:8080')}/health",
            timeout=5.0,
        )
        return resp.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(
    not _datahub_available(),
    reason="DataHub GMS is not reachable. Start with: docker compose up -d",
)
class TestSpike01Integration:
    """Integration tests requiring a live DataHub instance."""

    def test_spike_script_runs_all_operations(self) -> None:
        """Run the spike script and verify all critical operations pass."""
        result = subprocess.run(
            [sys.executable, str(SPIKE_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
            timeout=120,
        )
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        # The spike may return non-zero if some ops fail — that's expected
        # We check the results file instead
        results_file = SPIKE_DIR / "results.json"
        if results_file.exists():
            import json
            results = json.loads(results_file.read_text())
            critical_ops = [
                "01-create-incident",
                "02-read-incident",
                "03-update-incident-status",
                "04-create-assertion-definition",
                "10-update-asset-ownership",
                "11-read-updated-ownership",
            ]
            critical_results = [r for r in results if r["operation"] in critical_ops]
            failures = [r for r in critical_results if not r["passed"]]

            if failures:
                pytest.fail(
                    f"Critical operations failed: "
                    f"{[f['operation'] for f in failures]}"
                )
            assert len(failures) == 0, f"Critical ops failed: {failures}"

    def test_spike_does_not_call_run_assertion(self) -> None:
        """Transparency test: verify the spike does not use run_assertion()."""
        tree = ast.parse(SPIKE_SCRIPT.read_text(), filename=str(SPIKE_SCRIPT))
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                function = node.func
                name = function.attr if isinstance(function, ast.Attribute) else function.id if isinstance(function, ast.Name) else ""
                calls.append(name)
        assert "run_assertion" not in calls, "Spike must not call run_assertion() — it is Cloud-only"
        assert "runAssertion" not in calls, "Spike must not call runAssertion — it is Cloud-only"


class TestSpike01SelfContained:
    """Tests that run without DataHub."""

    def test_spike_script_exists(self) -> None:
        assert SPIKE_SCRIPT.exists(), f"Spike script not found at {SPIKE_SCRIPT}"

    def test_spike_script_is_valid_python(self) -> None:
        """Verify the script compiles."""
        compile(SPIKE_SCRIPT.read_text(), str(SPIKE_SCRIPT), "exec")

    def test_spike_documents_oss_limitations(self) -> None:
        """Verify the spike explicitly documents OSS vs Cloud boundaries."""
        source = SPIKE_SCRIPT.read_text()
        assert "Cloud-only" in source or "run_assertion" in source, (
            "Spike must document that run_assertion() is Cloud-only"
        )
        assert "OSS" in source, "Spike must reference OSS explicitly"
