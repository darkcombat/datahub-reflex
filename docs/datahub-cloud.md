# DataHub Cloud Integration

Reflex is designed for **DataHub OSS v1.5.0.6+** with a clear migration path to **DataHub Cloud (SaaS)**. This document explains the differences, benefits, and migration steps.

## Quick comparison

| Capability | OSS (v1.5.0.6) | Cloud (SaaS) | Reflex behavior |
|---|---|---|---|
| Incident CRUD (`raiseIncident`) | ✅ | ✅ | Used directly in both modes |
| Search across entities | ✅ | ✅ | 6-signal similarity resolution |
| Ownership updates | ✅ | ✅ | Written after approval |
| Structured properties | ✅ (>= 0.14) | ✅ | Coverage metadata |
| Tags & glossary terms | ✅ | ✅ | Control propagation markers |
| Assertion definition storage (`upsertAssertion`) | ⚠️ Removed in 1.5 | ✅ | Reflex-owned in OSS; Cloud-native in SaaS |
| Assertion run events | ⚠️ REST 404s | ✅ | Reflex-owned in OSS; Cloud-native in SaaS |
| Assertion execution (`runAssertion`) | ❌ | ✅ | Reflex-owned execution engine |
| Acryl Observe (anomaly detection) | ❌ | ✅ | Complementary to Reflex controls |
| SaaS SLAs & support | ❌ | ✅ | Enterprise-grade |
| Managed upgrades | ❌ | ✅ | Auto-patched |

## Migration path: OSS → Cloud

### 1. Connection string change

```bash
# OSS (default)
DATAHUB_GMS_URL=http://localhost:8080

# Cloud
DATAHUB_GMS_URL=https://<tenant>.acryl.io/gms
DATAHUB_GMS_TOKEN=eyJhbGciOi...  # Personal Access Token
```

### 2. Assertion ownership transfer

When migrating to Cloud, Reflex can optionally hand off assertion definitions and run events to DataHub's native infrastructure:

```python
# In reflex/datahub/__init__.py or via config
REFLEX_ASSERTION_BACKEND = "datahub-cloud"  # default: "reflex-owned"
```

With `datahub-cloud`, Reflex writes assertion definitions via `upsertAssertion` and reports run events via the assertion platform APIs — maintaining the same approval gates and control logic.

### 3. What stays the same

- **Control logic**: `UniquenessControl` and `ActiveOwnershipControl` are unchanged
- **Approval gates**: Root cause + publication approval remain mandatory
- **Pipeline steps**: All 9 steps execute identically
- **Backtesting**: Reflex-owned execution engine still validates controls against history
- **Similarity resolution**: `searchAcrossEntities` works in both modes

### 4. What improves with Cloud

| Feature | Benefit |
|---|---|
| **Acryl Observe** | ML-based anomaly detection complements Reflex's deterministic controls |
| **Assertion history** | Native time-series view of control execution in the DataHub UI |
| **SaaS SLAs** | 99.9% uptime, managed infrastructure |
| **Auto-upgrades** | Always on latest DataHub version |
| **SSO / RBAC** | Enterprise identity integration |
| **Support** | Acryl support team for incident resolution |

## Running Reflex against Cloud

```bash
# Set connection variables
export DATAHUB_GMS_URL="https://your-tenant.acryl.io/gms"
export DATAHUB_GMS_TOKEN="your-personal-access-token"

# Optional: use Cloud-native assertion storage
export REFLEX_ASSERTION_BACKEND="datahub-cloud"

# Run Reflex normally — same commands, same pipeline
python -m ui.app
```

## Authentication

Reflex uses DataHub Personal Access Tokens for Cloud authentication. Generate one at `https://your-tenant.acryl.io/settings/tokens`.

The token is passed via `DATAHUB_GMS_TOKEN` environment variable and included as a bearer token in all GMS GraphQL requests.

## Limitations in OSS mode (documented for Cloud migration context)

These are **automatically resolved** when switching to Cloud:

1. Assertion definitions are stored locally (JSON files), not in DataHub
2. Assertion run events are stored locally, not queryable via DataHub UI
3. No native time-series view of control execution history

These limitations are **by design** — Reflex owns what DataHub OSS cannot do, and defers to DataHub Cloud when available.

## Verification

```bash
# Test live DataHub connectivity (works for both OSS and Cloud)
python -m pytest tests/integration/ -v -m requires_datahub

# 9 integration tests verify:
# - GraphQL connectivity
# - Incident CRUD operations
# - searchAcrossEntities queries
# - Ownership read/write
# - Structured property read/write
# - Tag management
```
