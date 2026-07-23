# DataHub Reflex — Video Storyboard (2:58)

## 0:00–0:20 — Problem & Resolved Incident

**Visual**: DataHub incident screen showing "Duplicate transactions detected in finance.transactions"
**Voiceover**: "Data platforms resolve incidents every day. But the lesson — why it happened and how to prevent it — stays trapped. DataHub Reflex turns resolved incidents into executable preventive controls."

**Show**: Incident URN, title, description. ~340 duplicate transaction IDs found. Root cause: non-idempotent retry logic.

---

## 0:20–0:40 — Human Root-Cause Approval

**Visual**: Approval UI step 2 → "Human-Confirmed Root Cause". Text: "Non-idempotent retry logic in the ingestion pipeline caused duplicate inserts on partial failure." Confirmed by: alice@example.com.
**Voiceover**: "First, a human must confirm the root cause. Reflex never proceeds without explicit approval. This is not self-healing — it's human-augmented prevention."

**Show**: PipelineApprovalRequired exception demo (optional — show that pipeline blocks without approval).

---

## 0:40–1:05 — Lesson & Similar Assets

**Visual**: UI steps 3–5. Structured lesson extracted: failure_pattern="data_quality", confidence="high". Then 5 similar assets discovered with similarity signals: same_domain, shared_tags, compatible_schema, append_only_vulnerability, similar_lineage, no_existing_control.
**Voiceover**: "Reflex extracts a structured lesson from the incident, then discovers similar assets through the DataHub graph using six inspectable signals. Each candidate shows exactly which signals matched and which didn't."

**Show**: A mode badge on similarity data: "LIVE DATAHUB" for the live path or "SYNTHETIC" for the offline path.

---

## 1:05–1:30 — Backtest

**Visual**: UI step 6. Backtest metrics: 8 snapshots, 2 detections, 100% precision, 25% recall, ✅ would have prevented incident.
**Voiceover**: "Before publication, Reflex backtests the control against eight historical snapshots. The control detected duplicates at the exact timestamps where the incident occurred — zero false positives. This is Reflex-owned execution. DataHub OSS stores results but does not execute assertions."

**Show**: "SYNTHETIC HISTORICAL DATA" badge. "Reflex-owned execution" label.

---

## 1:30–1:50 — DataHub Write-Back

**Visual**: UI steps 7–8. Approval: APPROVED after the live human gate. Publication: assertion definitions and run events stored in Reflex, structured properties and tags written to DataHub OSS.
**Voiceover**: "After human approval, Reflex publishes to DataHub: structured properties for coverage metadata, tags for discoverability. Assertion definitions and run events are Reflex-owned in OSS — the endpoints were removed in v1.5.0.6."

**Show**: "REFLEX-OWNED" badge. "DataHub OSS v1.5.0.6 endpoints unavailable" note.

---

## 1:50–2:15 — Analogous Failure Detected

**Visual**: UI step 9. Detection results: 1 asset checked, 3 violations found on finance_monthly_ledger.
**Voiceover**: "The published control now runs on similar assets. On finance_monthly_ledger, it detects three duplicate transaction IDs — the same failure pattern, prevented before it becomes an incident."

**Show**: VIOLATIONS badge. Asset URN with violation count.

---

## 2:15–2:35 — Ownership Scenario

**Visual**: Switch to orphaned_ownership scenario. UI showing ActiveOwnershipControl detecting inactive owner 'bob' on finance.transactions. Domain-based replacement candidates proposed.
**Voiceover**: "Reflex handles more than duplicates. In the orphaned ownership scenario, it detects inactive owners, proposes active domain-based replacements, and preserves historical ownership records. Same loop: incident → lesson → control → backtest → approve → publish → detect."

**Show**: Ownership scenario steps 3–9. "Inactive owners: ['bob']". "Domain fallback: check domain 'finance' for active owners."

---

## 2:35–2:55 — Accurate Conclusion

**Visual**: Show what Reflex IS and IS NOT. Bullet points.
**Voiceover**: "DataHub Reflex is not self-healing. It is not fully autonomous. It is not production-safe. It does not claim zero false positives or universal prevention. What it does: converts human-confirmed operational lessons into backtested, executable preventive controls propagated through the DataHub graph. Two scenarios. Six similarity signals. Mandatory human approval. Reflex-owned execution."

**Show**: Apache 2.0 license badge. Test suite: 137 offline/unit/evaluation/UI tests passing, plus 8 live DataHub integration checks when GMS is running.

---

## 2:55–3:00 — Repository & License

**Visual**: GitHub repository structure. LICENSE file. README.
**Voiceover**: "Apache 2.0 licensed. Clean checkout: pip install, seed history, run demo. UI at localhost:5000. Full test suite with `python -m pytest`."

**Show**: `python -m pytest tests/ -q` output. `python -m ui.app` startup. Final frame: DataHub Reflex logo + repository URL.

---

## Visual Style Notes

- Dark theme throughout (matches DataHub and Reflex UI)
- All synthetic data labeled with amber "SYNTHETIC" badge
- All Reflex-owned execution labeled with purple "Reflex" badge
- All DataHub OSS interactions labeled with blue "DataHub" badge
- Terminal commands shown in split-screen or overlay
- No hidden chain-of-thought — everything visible is real application state
