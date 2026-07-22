"""CLI entry point for DataHub Reflex."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import typer

from reflex.core.pipeline import ReflexPipeline

app = typer.Typer(
    name="reflex",
    help="DataHub Reflex — Convert resolved incidents into executable preventive controls.",
)


@app.command()
def run(
    scenario: str = typer.Option(
        ...,
        "--scenario",
        "-s",
        help="Scenario to run: duplicate_rows | orphaned_ownership",
    ),
    incident_urn: str = typer.Option(
        ...,
        "--incident-urn",
        help="URN of the resolved incident",
    ),
    root_cause: str = typer.Option(
        ...,
        "--root-cause",
        help="Human-confirmed root cause",
    ),
    confirmed_by: str = typer.Option(
        ...,
        "--confirmed-by",
        help="Identity of the human confirming the root cause",
    ),
    target_asset: str = typer.Option(
        ...,
        "--target-asset",
        help="Target asset URN",
    ),
    history_file: Path | None = typer.Option(
        None,
        "--history-file",
        help="Path to historical snapshots JSON file",
    ),
    lessons_dir: Path = typer.Option(
        Path("./datasets"),
        "--lessons-dir",
        help="Directory for Reflex artifacts",
    ),
) -> None:
    """Run the Reflex pipeline for a given scenario."""
    # Load historical data
    if history_file is None:
        history_file = Path(f"./datasets/history/{scenario}/historical_snapshots.json")

    if not history_file.exists():
        typer.echo(f"ERROR: Historical data not found at {history_file}", err=True)
        typer.echo("Run: python scripts/seed_history.py", err=True)
        raise typer.Exit(code=1)

    snapshots_raw = json.loads(history_file.read_text())

    if scenario == "duplicate_rows":
        historical_data = [
            (datetime.fromisoformat(s["timestamp"]), s["rows"])
            for s in snapshots_raw
        ]
        scenario_params = {"uniqueness_columns": ["transaction_id"]}
    elif scenario == "orphaned_ownership":
        historical_data = [
            (datetime.fromisoformat(s["timestamp"]), s["assets"])
            for s in snapshots_raw
        ]
        scenario_params = {}
    else:
        typer.echo(f"ERROR: Unknown scenario: {scenario}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Running Reflex pipeline for scenario: {scenario}")
    typer.echo(f"Historical snapshots: {len(historical_data)}")

    pipeline = ReflexPipeline(lessons_dir=lessons_dir)

    async def _run():
        return await pipeline.run(
            incident_urn=incident_urn,
            scenario=scenario,
            human_confirmed_root_cause=root_cause,
            confirmed_by=confirmed_by,
            target_asset_urn=target_asset,
            historical_data=historical_data,
            **scenario_params,
        )

    result = asyncio.run(_run())

    # Print summary
    summary = result["backtest_summary"]
    typer.echo(f"\nLesson: {result['lesson'].lesson_id}")
    typer.echo(f"Control: {result['control'].control_id}")
    typer.echo(f"Backtest: {summary.detections}/{summary.total_snapshots} snapshots detected")
    typer.echo(f"Would have prevented: {summary.would_have_prevented}")

    # Save result
    output_dir = lessons_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{scenario}_result.json"

    # Serialize results (simplified for CLI output)
    serializable = {
        "lesson_id": result["lesson"].lesson_id,
        "control_id": result["control"].control_id,
        "control_type": result["control"].control_type.value,
        "backtest_summary": {
            "total_snapshots": summary.total_snapshots,
            "detections": summary.detections,
            "detection_rate": summary.detection_rate,
            "precision": summary.precision,
            "would_have_prevented": summary.would_have_prevented,
        },
        "similar_assets_count": len(result["similar_assets"]),
        "detection_results_count": len(result["detection_results"]),
    }
    output_file.write_text(json.dumps(serializable, indent=2, default=str))
    typer.echo(f"\nResult saved to: {output_file}")


@app.command()
def seed_history() -> None:
    """Seed historical data for backtesting."""
    from scripts.seed_history import main as seed_main
    seed_main()


@app.command()
def seed_datahub() -> None:
    """Seed DataHub with demo assets."""
    from scripts.seed_datahub import main as seed_main
    asyncio.run(seed_main())


@app.command()
def reset() -> None:
    """Reset demo state."""
    from scripts.reset_demo import reset as reset_main
    reset_main()


if __name__ == "__main__":
    app()
