"""Persistence layer for DataHub Reflex.

Provides SQLite-backed storage for runs, approvals, incidents, lessons,
controls, backtests, and audit trails. Replaces the in-memory _runs dict.

Uses Python's built-in sqlite3 — no additional dependencies required.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional


def _get_db_path() -> Path:
    return Path(os.environ.get("REFLEX_DB_PATH", "./datasets/reflex.db"))


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Connection management (thread-safe)
# ---------------------------------------------------------------------------

_local = threading.local()


def get_db() -> sqlite3.Connection:
    """Get a thread-local database connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        db_path = _get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def init_db() -> None:
    """Initialize database schema (idempotent)."""
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            scenario TEXT NOT NULL DEFAULT 'duplicate_rows',
            status TEXT NOT NULL DEFAULT 'active',
            current_step INTEGER NOT NULL DEFAULT 0,
            is_complete INTEGER NOT NULL DEFAULT 0,
            mode_label TEXT NOT NULL DEFAULT 'SYNTHETIC MODE',
            error TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS incidents (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            urn TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            affected_asset_urn TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'RESOLVED',
            root_cause TEXT DEFAULT '',
            root_cause_approved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lessons (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            incident_id TEXT NOT NULL,
            title TEXT NOT NULL,
            failure_category TEXT NOT NULL,
            failure_pattern TEXT NOT NULL DEFAULT '',
            trigger TEXT DEFAULT '',
            vulnerable_characteristics TEXT NOT NULL DEFAULT '[]',
            control_type TEXT NOT NULL DEFAULT '',
            target_field TEXT DEFAULT '',
            propagation_scope TEXT NOT NULL DEFAULT '[]',
            assumptions TEXT NOT NULL DEFAULT '[]',
            limitations TEXT NOT NULL DEFAULT '[]',
            confidence TEXT NOT NULL DEFAULT 'medium',
            extraction_mode TEXT NOT NULL DEFAULT 'deterministic',
            model_identifier TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS controls (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            lesson_id TEXT NOT NULL,
            control_type TEXT NOT NULL,
            control_definition TEXT NOT NULL DEFAULT '',
            target_field TEXT DEFAULT '',
            version TEXT NOT NULL DEFAULT '1.0.0',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS backtests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL ,
            control_id TEXT NOT NULL,
            total_snapshots INTEGER NOT NULL DEFAULT 0,
            detections INTEGER NOT NULL DEFAULT 0,
            true_positives INTEGER NOT NULL DEFAULT 0,
            false_positives INTEGER NOT NULL DEFAULT 0,
            true_negatives INTEGER NOT NULL DEFAULT 0,
            false_negatives INTEGER NOT NULL DEFAULT 0,
            precision REAL NOT NULL DEFAULT 1.0,
            recall REAL NOT NULL DEFAULT 0.0,
            false_positive_rate REAL NOT NULL DEFAULT 0.0,
            f1_score REAL NOT NULL DEFAULT 0.0,
            execution_failures INTEGER NOT NULL DEFAULT 0,
            would_have_prevented INTEGER NOT NULL DEFAULT 0,
            can_recommend INTEGER NOT NULL DEFAULT 0,
            blockers TEXT NOT NULL DEFAULT '[]',
            data_provenance TEXT NOT NULL DEFAULT 'SYNTHETIC',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL ,
            approval_type TEXT NOT NULL,
            state TEXT NOT NULL,
            approver TEXT NOT NULL DEFAULT '',
            notes TEXT DEFAULT '',
            test_mode INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL ,
            status TEXT NOT NULL DEFAULT 'reflex-owned',
            published_assets TEXT NOT NULL DEFAULT '[]',
            count INTEGER NOT NULL DEFAULT 0,
            reflex_owned TEXT NOT NULL DEFAULT '[]',
            datahub_owned TEXT NOT NULL DEFAULT '[]',
            cloud_skipped TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL ,
            control_id TEXT NOT NULL DEFAULT '',
            detected INTEGER NOT NULL DEFAULT 0,
            asset_urn TEXT NOT NULL DEFAULT '',
            violation_count INTEGER NOT NULL DEFAULT 0,
            evidence TEXT DEFAULT '',
            new_incident_urn TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT NOT NULL DEFAULT '{}',
            actor TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
        CREATE INDEX IF NOT EXISTS idx_approvals_run ON approvals(run_id);
        CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_log(run_id);
    """)
    db.commit()


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def create_run(
    run_id: str,
    scenario: str = "duplicate_rows",
    mode_label: str = "SYNTHETIC MODE",
) -> str:
    db = get_db()
    db.execute(
        "INSERT INTO runs (id, scenario, status, mode_label, started_at) VALUES (?, ?, 'active', ?, ?)",
        (run_id, scenario, mode_label, _now()),
    )
    _audit(run_id, "run.created", {"scenario": scenario, "mode": mode_label})
    db.commit()
    return run_id


def update_run(run_id: str, **kwargs: Any) -> None:
    db = get_db()
    allowed = {"status", "current_step", "is_complete", "error", "completed_at"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if updates:
        if "is_complete" in updates and updates["is_complete"]:
            updates["completed_at"] = _now()
            updates["status"] = "completed"
        sets = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [run_id]
        db.execute(f"UPDATE runs SET {sets} WHERE id = ?", values)
        _audit(run_id, "run.updated", updates)
        db.commit()


def get_run(run_id: str) -> Optional[dict[str, Any]]:
    db = get_db()
    row = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        "SELECT id, scenario, status, current_step, is_complete, mode_label, started_at FROM runs ORDER BY started_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def save_incident(run_id: str, **kwargs: Any) -> str:
    db = get_db()
    incident_id = kwargs.pop("id", run_id)
    db.execute(
        """INSERT OR REPLACE INTO incidents (id, run_id, urn, title, description, affected_asset_urn, status, root_cause, root_cause_approved, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (incident_id, run_id, kwargs.get("urn", ""), kwargs.get("title", ""),
         kwargs.get("description", ""), kwargs.get("affected_asset_urn", ""),
         kwargs.get("status", "RESOLVED"), kwargs.get("root_cause", ""),
         1 if kwargs.get("root_cause_approved") else 0, _now()),
    )
    _audit(run_id, "incident.saved", {"urn": kwargs.get("urn", "")})
    db.commit()
    return incident_id


def save_lesson(run_id: str, **kwargs: Any) -> str:
    db = get_db()
    lesson_id = kwargs.pop("id", "")
    db.execute(
        """INSERT OR REPLACE INTO lessons (id, run_id, incident_id, title, failure_category, failure_pattern, trigger,
           vulnerable_characteristics, control_type, target_field, propagation_scope,
           assumptions, limitations, confidence, extraction_mode, model_identifier, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (lesson_id, run_id, kwargs.get("incident_id", ""), kwargs.get("title", ""),
         kwargs.get("failure_category", ""), kwargs.get("failure_pattern", ""),
         kwargs.get("trigger", ""), json.dumps(kwargs.get("vulnerable_characteristics", [])),
         kwargs.get("control_type", ""), kwargs.get("target_field", ""),
         json.dumps(kwargs.get("propagation_scope", [])),
         json.dumps(kwargs.get("assumptions", [])), json.dumps(kwargs.get("limitations", [])),
         kwargs.get("confidence", "medium"), kwargs.get("extraction_mode", "deterministic"),
         kwargs.get("model_identifier", ""), _now()),
    )
    _audit(run_id, "lesson.saved", {"lesson_id": lesson_id})
    db.commit()
    return lesson_id


def save_control(run_id: str, **kwargs: Any) -> str:
    db = get_db()
    control_id = kwargs.pop("id", "")
    db.execute(
        """INSERT OR REPLACE INTO controls (id, run_id, lesson_id, control_type, control_definition, target_field, version, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (control_id, run_id, kwargs.get("lesson_id", ""), kwargs.get("control_type", ""),
         kwargs.get("control_definition", ""), kwargs.get("target_field", ""),
         kwargs.get("version", "1.0.0"), _now()),
    )
    _audit(run_id, "control.saved", {"control_id": control_id})
    db.commit()
    return control_id


def save_backtest(run_id: str, **kwargs: Any) -> int:
    db = get_db()
    cursor = db.execute(
        """INSERT INTO backtests (run_id, control_id, total_snapshots, detections, true_positives, false_positives,
           true_negatives, false_negatives, precision, recall, false_positive_rate, f1_score,
           execution_failures, would_have_prevented, can_recommend, blockers, data_provenance, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, kwargs.get("control_id", ""), kwargs.get("total_snapshots", 0),
         kwargs.get("detections", 0), kwargs.get("true_positives", 0), kwargs.get("false_positives", 0),
         kwargs.get("true_negatives", 0), kwargs.get("false_negatives", 0),
         kwargs.get("precision", 1.0), kwargs.get("recall", 0.0), kwargs.get("false_positive_rate", 0.0),
         kwargs.get("f1_score", 0.0), kwargs.get("execution_failures", 0),
         1 if kwargs.get("would_have_prevented") else 0, 1 if kwargs.get("can_recommend") else 0,
         json.dumps(kwargs.get("blockers", [])), kwargs.get("data_provenance", "SYNTHETIC"), _now()),
    )
    _audit(run_id, "backtest.saved", {"control_id": kwargs.get("control_id", "")})
    db.commit()
    return cursor.lastrowid


def save_approval(run_id: str, **kwargs: Any) -> int:
    db = get_db()
    cursor = db.execute(
        """INSERT INTO approvals (run_id, approval_type, state, approver, notes, test_mode, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (run_id, kwargs.get("approval_type", "control"), kwargs.get("state", "pending"),
         kwargs.get("approver", ""), kwargs.get("notes", ""),
         1 if kwargs.get("test_mode") else 0, _now()),
    )
    _audit(run_id, f"approval.{kwargs.get('state', 'pending')}",
           {"type": kwargs.get("approval_type", ""), "approver": kwargs.get("approver", "")})
    db.commit()
    return cursor.lastrowid


def save_publication(run_id: str, **kwargs: Any) -> int:
    db = get_db()
    cursor = db.execute(
        """INSERT INTO publications (run_id, status, published_assets, count, reflex_owned, datahub_owned, cloud_skipped, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, kwargs.get("status", "reflex-owned"),
         json.dumps(kwargs.get("published_assets", [])), kwargs.get("count", 0),
         json.dumps(kwargs.get("reflex_owned", [])), json.dumps(kwargs.get("datahub_owned", [])),
         json.dumps(kwargs.get("cloud_skipped", [])), _now()),
    )
    _audit(run_id, "publication.saved", {"status": kwargs.get("status", "reflex-owned")})
    db.commit()
    return cursor.lastrowid


def save_detection(run_id: str, **kwargs: Any) -> int:
    db = get_db()
    cursor = db.execute(
        """INSERT INTO detections (run_id, control_id, detected, asset_urn, violation_count, evidence, new_incident_urn, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, kwargs.get("control_id", ""), 1 if kwargs.get("detected") else 0,
         kwargs.get("asset_urn", ""), kwargs.get("violation_count", 0),
         kwargs.get("evidence", ""), kwargs.get("new_incident_urn", ""), _now()),
    )
    _audit(run_id, "detection.saved", {"detected": kwargs.get("detected", False)})
    db.commit()
    return cursor.lastrowid


def get_run_approvals(run_id: str) -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM approvals WHERE run_id = ? ORDER BY created_at", (run_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_run_audit_log(run_id: str) -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM audit_log WHERE run_id = ? ORDER BY created_at", (run_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _audit(run_id: str, event_type: str, data: dict, actor: str = "") -> None:
    db = get_db()
    db.execute(
        "INSERT INTO audit_log (run_id, event_type, event_data, actor, created_at) VALUES (?, ?, ?, ?, ?)",
        (run_id, event_type, json.dumps(data), actor, _now()),
    )
