# DataHub Reflex — Baseline Issue Register

Generated: 2026-07-22
Baseline commit: `9f0fe9f605592ecdd6878a47e9ae9d18df45152b`
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
  - Re-run the full test commands and record outputs
  - Confirm Devpost category: `Agents That Do Real Work`
  - Add final repository URL and video URL to the Devpost submission
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
| MED-01 | MEDIUM | Hardcoded test count in `scripts/demo.py` |
| MED-02 | MEDIUM | Pydantic V2 deprecation warning |

#### MED-01 — Hardcoded test count in demo script

- **Severity**: MEDIUM
- **Evidence**: `scripts/demo.py` line 197: `print("  Tests: 86 passing (offline/UI/evaluation), 8 require live DataHub")`
- **Affected file**: `scripts/demo.py`
- **Impact**: If tests are added or removed during hardening (Days 3-6), the demo will report a stale count, reducing credibility
- **Recommended action**: Replace the hardcoded string with a dynamic count (e.g., run `pytest --collect-only -q` and parse output) or remove the exact number and state the test locations instead
- **Acceptance criterion**: Demo output matches actual test count, verified by running `python -m pytest --collect-only -q tests/unit tests/evaluation tests/ui`
- **Critical path**: No — cosmetic, but should be fixed before demo recording (Day 18)

#### MED-02 — Pydantic V2 deprecation warning

- **Severity**: MEDIUM
- **Evidence**: Pytest output: `PydanticDeprecatedSince20: Support for class-based config is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0.`
- **Affected files**: One or more model files using class-based `Config` inner class
- **Impact**: Will break when Pydantic V3 is released; no runtime impact today
- **Recommended action**: Migrate class-based `Config` to `model_config = ConfigDict(...)` per Pydantic V2 migration guide
- **Acceptance criterion**: No PydanticDeprecatedSince20 warning in test output
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
- **Impact**: DataHub React frontend is broken; GMS/API works correctly (all 8 integration tests pass). Does not affect Reflex.
- **Recommended action**: Investigate DataHub frontend separately; not a Reflex issue
- **Acceptance criterion**: N/A — Reflex operates entirely through GMS API, not the frontend
- **Critical path**: No

---

## Summary

| Severity | Count |
|----------|-------|
| BLOCKER  | 0     |
| HIGH     | 0     |
| MEDIUM   | 2     |
| LOW      | 2     |
| EXTERNAL | 3     |
| **Total** | **7** |

No BLOCKER or HIGH issues found. The baseline is healthy and reproducible from a clean checkout.
