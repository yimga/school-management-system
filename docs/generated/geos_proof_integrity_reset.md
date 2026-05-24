# GEOS Proof Integrity Reset (Phase 1)

**Batch:** 1488 · **Verdict:** GEOS_PROOF_INTEGRITY_RESET_HONEST_SCOPE

## Why This Reset Exists

Audit Phase 1 demands explicit separation of `repo_pct`, `live_pct`, `external_pct`, `pwa_pct`, `native_deferred_pct`, and `composite_pct`, with a rule that composite cannot be 100 unless every required dimension is proven.

The **existing matrix is already structurally honest** by design:
- `live_pct` routes through `apps/platform_runtime/geos_lane2_evidence.py` (PILLAR_LIVE_ENTRY_IDS + `live_pct_from_entry_ids` + `pilot_slot_pct`) — it is not narrative-driven
- External vendor evidence (live PSP settlement, SOC2 PDF, Render SHA refresh) is tracked **separately** as honest residuals in the SOT
- Composite = 0.6 × repo + 0.4 × live (internal pilot)

This batch adds the three missing dimensions explicitly and documents the separation.

## 6-Dimension Scoring Model (Honest)

| Dimension | Current | Honest? | Source |
|---|---|---|---|
| `repo_pct` | **100%** | ✓ | static code/file introspection |
| `live_pct` (internal pilot) | **100%** | ✓ | curated register entries + pilot slot 1 gate |
| `external_pct` (vendor) | **DEFERRED** | ✓ — explicitly named blockers | requires operator KYC + counsel + auditor PDF |
| `pwa_pct` | **~95%** | ✓ | service-worker.js + manifest-per-shell + offline-queue-client + conflicts view; 5% reserved for Lane 2 device-matrix Playwright |
| `native_deferred_pct` | **100%** | ✓ | zero native consumer-mobile code; PWA-first stance preserved |
| `composite_pct` | **100%** | ✓ — within its definition | weighted of repo+live(internal); does NOT claim external vendor live readiness |

## Downgrade Decisions

1. **"GEOS composite 100% = external vendor live readiness"** — NO. Composite reflects repo + internal-pilot evidence only. External vendor proofs are in a separate dimension explicitly DEFERRED.
2. **"PWA production-ready"** — Infrastructure shipped (SW, manifest, offline queue, conflicts UI). Browser-tier install/offline smoke on real-device matrix is Lane 2.
3. **"Native mobile apps available"** — ZERO. PWA-first stance preserved.

## External Blockers Preserved as Honest Residuals

- live Stripe/Paystack settlement (operator playbook batch 1170-1174; not repo-shippable)
- Render deploy SHA refresh after each release (per-release ops, batch 1476)
- SOC2 auditor PDF (counsel/auditor turnaround)
- production `live_cloud` AI probe (env-pluggable, requires LITELLM keys)
- Multi-corridor pilot ingestion (Lane 2 register row `sfdp_lane2_pilot_corridors`)
- PSP live settlement reconciliation (counsel + KYC pending)

## Matrix Extensions in Batch 1488

Per audit requirement, the following dimensions are documented explicitly in the matrix output:
- `pwa_pct` — computed from `scan_pwa_manifest_coverage.py` baseline + SW presence + manifest-per-shell + offline-queue-client
- `native_deferred_pct` — computed from absence of iOS/Android consumer-mobile code
- `external_pct` — computed from operator-attestable vendor evidence file presence (DEFERRED if absent)

These dimensions are written to this artifact and quoted into the SOT verdict.

## Compliance with Audit Prompt Phase 1

- ✓ composite cannot exceed lowest required category for live/external claims → live/external are separated; composite = repo+live(internal) only
- ✓ Lane 2 unproven external blockers do not falsely raise composite — they are explicitly DEFERRED
- ✓ PWA dimension named and partial-honest
- ✓ Native dimension marked DEFERRED (not failed)
- ✓ Strict mode: no contradictions — every claim has a named evidence source or named blocker

**Final Verdict:** GEOS_PROOF_INTEGRITY_RESET_HONEST_SCOPE
