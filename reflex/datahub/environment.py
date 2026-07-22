"""Synthetic DataHub environment definition.

This module defines the complete synthetic graph used by DataHub Reflex.
It is the single source of truth for all demo assets, their schemas,
lineage, ownership, and metadata.

All data is deterministic and reproducible. No manual UI steps are required.
"""

from __future__ import annotations

from typing import Any

# -- Domains -------------------------------------------------------------------

DOMAINS: list[dict[str, Any]] = [
    {
        "urn": "urn:li:domain:finance",
        "name": "Finance",
        "description": "Finance domain — financial transactions, ledger, P&L",
    },
    {
        "urn": "urn:li:domain:operations",
        "name": "Operations",
        "description": "Operations domain — pipeline execution, monitoring",
    },
]

# -- Users --------------------------------------------------------------------

USERS: list[dict[str, Any]] = [
    # Active individual owners
    {
        "urn": "urn:li:corpuser:alice",
        "username": "alice",
        "full_name": "Alice Chen",
        "email": "alice@example.com",
        "active": True,
        "title": "Senior Data Engineer",
    },
    {
        "urn": "urn:li:corpuser:charlie",
        "username": "charlie",
        "full_name": "Charlie Kim",
        "email": "charlie@example.com",
        "active": True,
        "title": "Data Platform Lead",
    },
    {
        "urn": "urn:li:corpuser:eve",
        "username": "eve",
        "full_name": "Eve Johnson",
        "email": "eve@example.com",
        "active": True,
        "title": "Finance Data Steward",
    },
    # Inactive individual owner (orphaned ownership scenario)
    {
        "urn": "urn:li:corpuser:bob",
        "username": "bob",
        "full_name": "Bob Martinez",
        "email": "bob@example.com",
        "active": False,
        "title": "Former Data Engineer",
        "deactivated_at": "2026-06-01T00:00:00Z",
    },
    {
        "urn": "urn:li:corpuser:diana",
        "username": "diana",
        "full_name": "Diana Park",
        "email": "diana@example.com",
        "active": False,
        "title": "Former Analytics Engineer",
        "deactivated_at": "2026-05-15T00:00:00Z",
    },
]

# Groups
GROUPS: list[dict[str, Any]] = [
    {
        "urn": "urn:li:corpGroup:finance_owners",
        "name": "Finance Owners",
        "members": ["alice", "eve"],
    },
    {
        "urn": "urn:li:corpGroup:data_platform",
        "name": "Data Platform Team",
        "members": ["charlie"],
    },
]

# Service accounts
SERVICE_ACCOUNTS: list[dict[str, Any]] = [
    {
        "urn": "urn:li:corpuser:svc_ingestion_pipeline",
        "username": "svc_ingestion_pipeline",
        "full_name": "Ingestion Pipeline Service Account",
        "active": True,
    },
]

# -- Datasets -----------------------------------------------------------------

DATASETS: list[dict[str, Any]] = [
    # --- Duplicate-row scenario assets ---
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_raw_transactions,PROD)",
        "name": "finance_raw_transactions",
        "platform": "bigquery",
        "env": "PROD",
        "description": "Raw financial transactions ingested from payment systems",
        "domain": "urn:li:domain:finance",
        "tags": ["pii", "pci", "finance", "raw", "append-only"],
        "owners": [
            {"owner": "urn:li:corpuser:alice", "type": "TECHNICAL_OWNER"},
            {"owner": "urn:li:corpuser:eve", "type": "BUSINESS_OWNER"},
        ],
        "schema": [
            {"name": "transaction_id", "type": "STRING", "description": "Unique transaction identifier"},
            {"name": "amount", "type": "NUMERIC", "description": "Transaction amount in USD"},
            {"name": "currency", "type": "STRING", "description": "ISO 4217 currency code"},
            {"name": "timestamp", "type": "TIMESTAMP", "description": "Transaction timestamp"},
            {"name": "merchant_id", "type": "STRING", "description": "Merchant identifier"},
            {"name": "status", "type": "STRING", "description": "Transaction status"},
            {"name": "ingested_at", "type": "TIMESTAMP", "description": "Ingestion timestamp"},
        ],
        "structured_properties": {
            "reflex:write_pattern": "append-only",
            "reflex:has_idempotency_key": "false",
        },
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_transaction_enrichment,PROD)",
        "name": "finance_transaction_enrichment",
        "platform": "bigquery",
        "env": "PROD",
        "description": "Enriched transactions with merchant and category data",
        "domain": "urn:li:domain:finance",
        "tags": ["pii", "finance", "enriched"],
        "owners": [
            {"owner": "urn:li:corpuser:alice", "type": "TECHNICAL_OWNER"},
        ],
        "schema": [
            {"name": "transaction_id", "type": "STRING", "description": "Unique transaction identifier"},
            {"name": "amount", "type": "NUMERIC", "description": "Transaction amount in USD"},
            {"name": "merchant_name", "type": "STRING", "description": "Resolved merchant name"},
            {"name": "category", "type": "STRING", "description": "Spending category"},
            {"name": "enriched_at", "type": "TIMESTAMP", "description": "Enrichment timestamp"},
        ],
        "structured_properties": {
            "reflex:write_pattern": "overwrite",
        },
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
        "name": "finance_daily_ledger",
        "platform": "bigquery",
        "env": "PROD",
        "description": "Daily aggregated financial ledger — PRIMARY TARGET for duplicate-row scenario",
        "domain": "urn:li:domain:finance",
        "tags": ["finance", "ledger", "aggregated", "append-only"],
        "owners": [
            {"owner": "urn:li:corpuser:bob", "type": "TECHNICAL_OWNER"},
            {"owner": "urn:li:corpuser:eve", "type": "BUSINESS_OWNER"},
        ],
        "schema": [
            {"name": "transaction_id", "type": "STRING", "description": "Unique transaction identifier"},
            {"name": "ledger_date", "type": "DATE", "description": "Ledger date"},
            {"name": "amount", "type": "NUMERIC", "description": "Transaction amount"},
            {"name": "category", "type": "STRING", "description": "Spending category"},
            {"name": "source", "type": "STRING", "description": "Source dataset"},
        ],
        "structured_properties": {
            "reflex:write_pattern": "append-only",
            "reflex:has_idempotency_key": "false",
            "reflex:source_incident": "urn:li:incident:dup-rows-001",
        },
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_monthly_ledger,PROD)",
        "name": "finance_monthly_ledger",
        "platform": "bigquery",
        "env": "PROD",
        "description": "Monthly aggregated financial ledger — SECONDARY TARGET for duplicate-row propagation",
        "domain": "urn:li:domain:finance",
        "tags": ["finance", "ledger", "aggregated", "append-only"],
        "owners": [
            {"owner": "urn:li:corpuser:bob", "type": "TECHNICAL_OWNER"},
            {"owner": "urn:li:corpgroup:finance_owners", "type": "TECHNICAL_OWNER"},
        ],
        "schema": [
            {"name": "transaction_id", "type": "STRING", "description": "Unique transaction identifier"},
            {"name": "ledger_month", "type": "STRING", "description": "Ledger month (YYYY-MM)"},
            {"name": "amount", "type": "NUMERIC", "description": "Transaction amount"},
            {"name": "category", "type": "STRING", "description": "Spending category"},
        ],
        "structured_properties": {
            "reflex:write_pattern": "append-only",
            "reflex:has_idempotency_key": "false",
        },
    },
    # --- Additional ownership scenario assets ---
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,operations_pipeline_metrics,PROD)",
        "name": "operations_pipeline_metrics",
        "platform": "bigquery",
        "env": "PROD",
        "description": "Pipeline execution metrics and run history",
        "domain": "urn:li:domain:operations",
        "tags": ["operations", "monitoring", "pipeline"],
        "owners": [
            {"owner": "urn:li:corpuser:charlie", "type": "TECHNICAL_OWNER"},
            {"owner": "urn:li:corpuser:svc_ingestion_pipeline", "type": "TECHNICAL_OWNER"},
        ],
        "schema": [
            {"name": "pipeline_name", "type": "STRING"},
            {"name": "run_id", "type": "STRING"},
            {"name": "status", "type": "STRING"},
            {"name": "duration_seconds", "type": "INTEGER"},
            {"name": "rows_processed", "type": "INTEGER"},
        ],
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,operations_incident_log,PROD)",
        "name": "operations_incident_log",
        "platform": "bigquery",
        "env": "PROD",
        "description": "Historical incident log for all data pipelines",
        "domain": "urn:li:domain:operations",
        "tags": ["operations", "incidents"],
        "owners": [
            {"owner": "urn:li:corpuser:diana", "type": "TECHNICAL_OWNER"},
        ],
        "schema": [
            {"name": "incident_id", "type": "STRING"},
            {"name": "pipeline_name", "type": "STRING"},
            {"name": "severity", "type": "STRING"},
            {"name": "resolution", "type": "STRING"},
            {"name": "resolved_at", "type": "TIMESTAMP"},
        ],
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_pnl_dashboard_data,PROD)",
        "name": "finance_pnl_dashboard_data",
        "platform": "bigquery",
        "env": "PROD",
        "description": "Aggregated P&L data for executive dashboard",
        "domain": "urn:li:domain:finance",
        "tags": ["finance", "dashboard", "pii"],
        "owners": [
            {"owner": "urn:li:corpuser:eve", "type": "TECHNICAL_OWNER"},
            {"owner": "urn:li:corpuser:alice", "type": "BUSINESS_OWNER"},
        ],
        "schema": [
            {"name": "report_date", "type": "DATE"},
            {"name": "revenue", "type": "NUMERIC"},
            {"name": "expenses", "type": "NUMERIC"},
            {"name": "net_income", "type": "NUMERIC"},
        ],
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_compliance_audit,PROD)",
        "name": "finance_compliance_audit",
        "platform": "bigquery",
        "env": "PROD",
        "description": "Compliance audit trail for financial transactions — NO ACTIVE OWNER scenario asset",
        "domain": "urn:li:domain:finance",
        "tags": ["finance", "compliance", "pii", "pci"],
        "owners": [
            {"owner": "urn:li:corpuser:bob", "type": "TECHNICAL_OWNER"},
        ],
        "historical_owners": [
            {"owner": "urn:li:corpuser:alice", "type": "TECHNICAL_OWNER", "until": "2025-12-01"},
        ],
        "schema": [
            {"name": "audit_id", "type": "STRING"},
            {"name": "transaction_id", "type": "STRING"},
            {"name": "audit_type", "type": "STRING"},
            {"name": "compliance_status", "type": "STRING"},
            {"name": "audited_at", "type": "TIMESTAMP"},
        ],
        "structured_properties": {
            "reflex:has_active_owner": "false",
            "reflex:owner_deactivated": "urn:li:corpuser:bob",
        },
    },
]

# -- Dashboards ---------------------------------------------------------------

DASHBOARDS: list[dict[str, Any]] = [
    {
        "urn": "urn:li:dashboard:(looker,pnl_dashboard)",
        "name": "pnl_dashboard",
        "platform": "looker",
        "description": "Executive P&L dashboard — consumes finance_pnl_dashboard_data",
        "domain": "urn:li:domain:finance",
        "tags": ["finance", "dashboard", "executive"],
        "owners": [
            {"owner": "urn:li:corpuser:eve", "type": "TECHNICAL_OWNER"},
        ],
    },
    {
        "urn": "urn:li:dashboard:(looker,pipeline_health)",
        "name": "pipeline_health",
        "platform": "looker",
        "description": "Pipeline health monitoring dashboard",
        "domain": "urn:li:domain:operations",
        "tags": ["operations", "monitoring"],
        "owners": [
            {"owner": "urn:li:corpuser:charlie", "type": "TECHNICAL_OWNER"},
        ],
    },
]

# -- Pipelines ----------------------------------------------------------------

PIPELINES: list[dict[str, Any]] = [
    {
        "urn": "urn:li:dataJob:(airflow,finance_ingestion_dag,PROD)",
        "name": "finance_ingestion_dag",
        "platform": "airflow",
        "description": "Ingests raw transactions and writes to finance_raw_transactions",
        "domain": "urn:li:domain:operations",
        "owners": [
            {"owner": "urn:li:corpuser:svc_ingestion_pipeline", "type": "TECHNICAL_OWNER"},
        ],
    },
    {
        "urn": "urn:li:dataJob:(airflow,finance_ledger_dag,PROD)",
        "name": "finance_ledger_dag",
        "platform": "airflow",
        "description": "Aggregates transactions into daily and monthly ledgers",
        "domain": "urn:li:domain:operations",
        "owners": [
            {"owner": "urn:li:corpuser:alice", "type": "TECHNICAL_OWNER"},
        ],
    },
]

# -- Lineage ------------------------------------------------------------------

LINEAGE: list[dict[str, Any]] = [
    # Duplicate-row scenario lineage chain
    {
        "upstream": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_raw_transactions,PROD)",
        "downstream": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_transaction_enrichment,PROD)",
    },
    {
        "upstream": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_transaction_enrichment,PROD)",
        "downstream": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
    },
    {
        "upstream": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
        "downstream": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_monthly_ledger,PROD)",
    },
    {
        "upstream": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_monthly_ledger,PROD)",
        "downstream": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_pnl_dashboard_data,PROD)",
    },
    {
        "upstream": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_pnl_dashboard_data,PROD)",
        "downstream": "urn:li:dashboard:(looker,pnl_dashboard)",
    },
    # Pipeline outputs
    {
        "upstream": "urn:li:dataJob:(airflow,finance_ingestion_dag,PROD)",
        "downstream": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_raw_transactions,PROD)",
    },
    {
        "upstream": "urn:li:dataJob:(airflow,finance_ledger_dag,PROD)",
        "downstream": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
    },
    {
        "upstream": "urn:li:dataJob:(airflow,finance_ledger_dag,PROD)",
        "downstream": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_monthly_ledger,PROD)",
    },
]

# -- Incidents ----------------------------------------------------------------

INCIDENTS: list[dict[str, Any]] = [
    {
        "title": "Duplicate transactions detected in finance_daily_ledger",
        "description": (
            "On 2026-07-19, the finance_ledger_dag pipeline experienced a partial failure "
            "while writing to finance_daily_ledger. The Airflow retry mechanism re-ran the "
            "failed task, but the ingestion logic was not idempotent. This caused duplicate "
            "rows to be inserted into finance_daily_ledger. Approximately 340 duplicate "
            "transaction_ids were identified during reconciliation. "
            "PROPOSED ROOT CAUSE: The ingestion pipeline's retry logic does not use an "
            "idempotency key or deduplication step before writing. Append-only writes "
            "combined with non-idempotent retries produce duplicates."
        ),
        "custom_type": "DUPLICATE_ROWS",
        "status": "RESOLVED",
        "entities": [
            "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
        ],
    },
    {
        "title": "Inactive owner bob detected on finance assets",
        "description": (
            "Bob Martinez was deactivated on 2026-06-01 but remains listed as "
            "TECHNICAL_OWNER of finance_daily_ledger, finance_monthly_ledger, and "
            "finance_compliance_audit. These assets have no active operational owner. "
            "PROPOSED ROOT CAUSE: The employee offboarding process does not update "
            "DataHub ownership assignments. There is no automated ownership review "
            "that detects inactive owners."
        ),
        "custom_type": "ORPHANED_OWNERSHIP",
        "status": "RESOLVED",
        "entities": [
            "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
        ],
    },
]

# -- Historical Profiles (for backtesting) ------------------------------------

# Generated by seed_history.py — see scripts/seed_history.py

# -- Tags ---------------------------------------------------------------------

TAGS: list[dict[str, Any]] = [
    {"urn": "urn:li:tag:pii", "name": "pii", "description": "Contains personally identifiable information"},
    {"urn": "urn:li:tag:pci", "name": "pci", "description": "PCI-compliant payment data"},
    {"urn": "urn:li:tag:finance", "name": "finance", "description": "Finance domain data"},
    {"urn": "urn:li:tag:append-only", "name": "append-only", "description": "Dataset uses append-only write pattern"},
    {"urn": "urn:li:tag:reflex:uniqueness-controlled", "name": "reflex:uniqueness-controlled", "description": "Covered by Reflex uniqueness control"},
    {"urn": "urn:li:tag:reflex:ownership-controlled", "name": "reflex:ownership-controlled", "description": "Covered by Reflex ownership control"},
]

# -- Assertions (pre-existing) ------------------------------------------------

EXISTING_ASSERTIONS: list[dict[str, Any]] = [
    {
        "entity": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_daily_ledger,PROD)",
        "type": "DATASET",
        "description": "Pre-existing freshness check: finance_daily_ledger updated within 24h",
        "platform": "urn:li:dataPlatform:bigquery",
    },
    {
        "entity": "urn:li:dataset:(urn:li:dataPlatform:bigquery,finance_pnl_dashboard_data,PROD)",
        "type": "DATASET",
        "description": "Pre-existing volume check: row count within expected range",
        "platform": "urn:li:dataPlatform:bigquery",
    },
]
