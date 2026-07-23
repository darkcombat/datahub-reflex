# DataHub Reflex — Issue Register

Generated: 2026-07-22 (updated 2026-07-23)
Current commit: see `git log -1` (updated 2026-07-23)
Branch: `main`
Remote: `https://github.com/darkcombat/datahub-reflex.git`

## Issue classification

- **BLOCKER**: must be fixed before the next milestone
- **HIGH**: threatens demo credibility or reproducibility
- **MEDIUM**: useful improvement but not critical
- **LOW**: cosmetic or future work
- **EXTERNAL**: requires user credentials, public URLs, video recording, or Devpost access

---

## Issues

### EXTERNAL

| ID | Severity | Summary |
|----|----------|---------|
| EXT-01 | EXTERNAL | `<PUBLIC_VIDEO_URL>` placeholder in `docs/devpost_submission.md` |
| EXT-02 | EXTERNAL | 5 unchecked items in `docs/submission_checklist.md` |
| EXT-03 | EXTERNAL | Devpost submission not yet completed |

#### EXT-01 — `<PUBLIC_VIDEO_URL>` placeholder in devpost submission

- **Severity**: EXTERNAL
- **Evidence**: `docs/devpost_submission.md` line contains `Demo video: <PUBLIC_VIDEO_URL>`
- **Affected file**: `docs/devpost_submission.md`
- **Impact**: Devpost submission cannot be finalized without a public video URL
- **Recommended action**: Record the demo video (per 20-day plan Day 18), upload publicly, and replace the placeholder
- **Acceptance criterion**: `docs/devpost_submission.md` contains a valid public video URL; placeholder is gone
- **Critical path**: Yes — blocks Devpost submission

#### EXT-02 — Unchecked submission checklist items

- **Severity**: EXTERNAL
  - **Evidence**: `docs/submission_checklist.md` has 5 unchecked items:
  - Record public demo video under three minutes
  - Verify the video URL is public
  - Confirm Devpost category: `Agents That Do Real Work`
  - Add final repository URL and video URL to the Devpost submission
  - Submit the prepared upstream patches, or document their post-submission status
- **Affected file**: `docs/submission_checklist.md`
- **Impact**: Checklist cannot be fully signed off without video and Devpost submission
- **Recommended action**: Complete video recording (Day 18), then check remaining items
- **Acceptance criterion**: All checklist items marked `[x]`
- **Critical path**: Yes — blocks final submission

#### EXT-03 — Devpost submission not yet submitted

- **Severity**: EXTERNAL
- **Evidence**: `docs/devpost_submission.md` is a draft; 20-day plan Days 19-20 cover submission review and buffer
- **Affected file**: `docs/devpost_submission.md`
- **Impact**: Hackathon entry not yet submitted
- **Recommended action**: After video is recorded and all URLs are final, submit via Devpost
- **Acceptance criterion**: Devpost submission confirmed in category `Agents That Do Real Work`
- **Critical path**: Yes — final deliverable

---

### MEDIUM

| ID | Severity | Summary |
|----|----------|---------|
| MED-01 | MEDIUM | Hardcoded test count in `scripts/demo.py` (resolved) |
| MED-02 | MEDIUM | Pydantic V2 deprecation warning (resolved) |

#### MED-01 — Hardcoded test count in demo script

- **Severity**: MEDIUM
- **Status**: ✅ RESOLVED (2026-07-23, commit `d5c5538`)
- **Evidence**: `scripts/demo.py` line 197 had `"Tests: 86 passing..."`
- **Resolution**: Replaced with descriptive test location references. No hardcoded count.
- **Affected file**: `scripts/demo.py`
- **Acceptance criterion**: Demo output does not contain stale numbers ✅

#### MED-02 — Pydantic V2 deprecation warning

- **Severity**: MEDIUM
- **Status**: ✅ RESOLVED (2026-07-23, commit `e848d2a`)
- **Evidence**: Pytest output: `PydanticDeprecatedSince20: Support for class-based config is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0.`
- **Affected files**: One or more model files using class-based `Config` inner class
- **Impact**: Will break when Pydantic V3 is released; no runtime impact today
- **Recommended action**: Migrate class-based `Config` to `model_config = ConfigDict(...)` per Pydantic V2 migration guide
- **Resolution**: Migrated `LessonExtractionResult` to `ConfigDict(use_enum_values=True)`; the offline and live suites pass without the warning.
- **Acceptance criterion**: No PydanticDeprecatedSince20 warning in test output ✅
- **Critical path**: No — future-proofing, not urgent for hackathon submission

---

### LOW

| ID | Severity | Summary |
|----|----------|---------|
| LOW-01 | LOW | pip upgrade available (25.0.1 → 26.1.2) |
| LOW-02 | LOW | DataHub OSS frontend returns HTTP 500 |

#### LOW-01 — pip upgrade notice

- **Severity**: LOW
- **Evidence**: `pip install` output: `A new release of pip is available: 25.0.1 -> 26.1.2`
- **Affected files**: N/A (environment)
- **Impact**: None — pip is functional
- **Recommended action**: Upgrade pip at convenience: `python -m pip install --upgrade pip`
- **Acceptance criterion**: No pip upgrade notice
- **Critical path**: No

#### LOW-02 — DataHub OSS frontend HTTP 500

- **Severity**: LOW
- **Evidence**: `Invoke-WebRequest http://localhost:8080` returns HTTP 500; health endpoint `/health` returns 200
- **Affected files**: N/A (infrastructure)
- **Impact**: DataHub React frontend is broken; GMS/API works correctly (all 9 integration tests pass). Does not affect Reflex.
- **Recommended action**: Investigate DataHub frontend separately; not a Reflex issue
- **Acceptance criterion**: N/A — Reflex operates entirely through GMS API, not the frontend
- **Critical path**: No
---

## Live DataHub Hardening Findings (2026-07-22)

Findings from the Days 3-6 hardening phase. No BLOCKER or HIGH issues were found in the live DataHub paths.

### MEDIUM

| ID | Severity | Summary |
|----|----------|---------|
| MED-03 | MEDIUM | DataHubReadClient OSS GraphQL schema compatibility |

#### MED-03 — Broken GraphQL queries in DataHubReadClient (resolved)

- **Severity**: MEDIUM
- **Status**: ✅ RESOLVED (2026-07-23, current live schema test)
- **Evidence**: Verified against live DataHub OSS v1.5.0.6. Lineage, tags, structured properties, assertion metadata, and incident status queries now use the tested schema shapes; the live suite includes a dedicated compatibility test.
- **Affected file**: `reflex/datahub/read_client.py`
- **Impact**: These methods are **not called by any live pipeline path** (Phase3Pipeline uses `DataHubSimilarityResolver` which calls `searchAcrossEntities`; Phase4Pipeline uses `search_datasets`, `get_owners`, `get_domain` — all verified working). The broken methods are dead code for MVP flows but exist in the public API surface and would confuse a developer.
- **Recommended action**: Keep the schema compatibility test and preserve the documented caveat for malformed incident search-index entries.
- **Acceptance criterion**: Dataset read methods execute against the live OSS schema ✅
- **Critical path**: No — the two MVP live flows do not call these methods

### LOW

| ID | Severity | Summary |
|----|----------|---------|
| LOW-03 | LOW | Ownership type normalized to NONE by DataHub OSS on read-back |

#### LOW-03 — DataHub OSS normalizes TECHNICAL_OWNER to NONE

- **Severity**: LOW
- **Evidence**: `addOwner` with `TECHNICAL_OWNER` type → `get_owners` returns `type: "NONE"`. Verified against live DataHub OSS v1.5.0.6.
- **Affected files**: `reflex/datahub/write_client.py` (writes TECHNICAL_OWNER), `reflex/datahub/read_client.py` (reads NONE), `reflex/core/phase4_pipeline.py` (documents this in code comments)
- **Impact**: Ownership type fidelity is lost on round-trip through DataHub OSS. Reflex already documents this and treats all owners conservatively.
- **Recommended action**: No code change needed. Already documented in `docs/limits.md` section 4b and in Phase4Pipeline code comments.
- **Acceptance criterion**: Documentation remains accurate
- **Critical path**: No

---

## Summary (updated)

| Severity | Count |
|----------|-------|
| BLOCKER  | 0     |
| HIGH     | 0     |
| MEDIUM   | 0     |
| LOW      | 3     |
| EXTERNAL | 3     |
| **Total** | **6** |

No BLOCKER or HIGH issues found. The live DataHub paths are reliable and inspectable for both MVP scenarios.
---

## Summary

| Severity | Count |
|----------|-------|
| BLOCKER  | 0     |
| HIGH     | 0     |
| MEDIUM   | 0     |
| LOW      | 3     |
| EXTERNAL | 3     |
| **Total** | **6** |

No BLOCKER or HIGH issues found. The baseline is healthy and reproducible from a clean checkout.
