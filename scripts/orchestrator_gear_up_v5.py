"""Gear-Up V5 — transformational journeys, dual-host proof, nav ledger."""

PACK_VERSION = "2026-05-20-orchestrator-v5"

GEAR_UP_V5_UNIVERSAL = """## GEAR-UP V5 — TRANSFORMATIONAL BAR (mandatory)

**Pack:** `2026-05-20-orchestrator-v5` — supersedes v4. Repo proof = **journeys + verifiers**, not narrative.

### Non-negotiables

1. **Journey coverage** — `docs/generated/orchestrator_journey_manifest.json` lists **27** journeys (3 per stage 1–9). Stage ACCEPTED only when its journeys are `PASS` in `orchestrator_journey_coverage.json`.
2. **Dual-host contract** — manager chrome on `manager.runmycampus.com`; tenant on `{slug}.runmycampus.com` or `/t/{slug}/`. `verify_platform_abrupt_end_sweep.mjs` uses `TENANT_BASE_URL` for tenant context.
3. **Nav ledger** — `verify_nav_resolves_to_named_route.py` → **0** lazy dashboard-root fallbacks in operator sidebar chrome.
4. **Pixel-perfect bundle** — interaction integrity, dead hrefs, page fold, chromatic (Stage 8+ cross-cutting).
5. **Continuous cert** — append `journeys` block to stage certification JSON; Agent 10 requires `journey_coverage_pct: 100`.
6. **v5_measurable_wins[]** — each stage cert adds ≥1 metric `{name, baseline, after, competitor}` (honest numbers only).
7. **Git truth** — Stage 0 records `uncommitted_files_count`; wave cannot claim READY if critical paths are only local.

### V5 verifier bundle

```bash
python scripts/generate_orchestrator_journey_manifest.py --write
python scripts/verify_stage_journey_coverage.py
python scripts/verify_nav_resolves_to_named_route.py --strict
python scripts/verify_interaction_integrity_contract.py
python scripts/verify_orchestrator_v5_bundle.py
python scripts/verify_orchestrator_prompt_pack.py --strict
```

### Proof artifact (every agent)

```json
"v5": {
  "prompt_pack_version": "2026-05-20-orchestrator-v5",
  "journeys_pass": 3,
  "journeys_total": 3,
  "measurable_wins": [],
  "nav_ledger_pass": true
}
```
"""

GEAR_UP_V5_BY_STAGE: dict[str, str] = {
    "stage-00-current-state-validation.md": """### Stage 0 V5
- `python scripts/generate_orchestrator_journey_manifest.py --write`
- Readiness JSON: `uncommitted_files_count`, `journey_manifest_version`, `persona_cred_matrix`.""",
    "stage-01-core-runtime.md": """### Stage 1 V5
- Journeys: session/BOLA/idempotency proofs in manifest (verifier + django tests).""",
    "stage-02-tenant-isolation.md": """### Stage 2 V5
- Journeys: cross-tenant deny + queryset 0 + penetration tests.""",
    "stage-03-edge-routing-branding.md": """### Stage 3 V5
- Journeys: route audit + chromatic + nav ledger subset.""",
    "stage-04-policy-entitlements.md": """### Stage 4 V5
- Journeys: entitlement gate + PDP/permission banner paths.""",
    "stage-05-finance-ledger.md": """### Stage 5 V5
- Journeys: money_float 0 + webhook dedupe test module exists.""",
    "stage-06-academics-operations.md": """### Stage 6 V5
- Journeys: academics workflow audit + page-fold on task tables.""",
    "stage-07-migration-cloud.md": """### Stage 7 V5
- Journeys: connector 8/8 + migration-cloud.spec.js present.""",
    "stage-08-workspace-ux.md": """### Stage 8 V5
- Journeys: interaction integrity + dead hrefs + operator sweep critical paths.
- `ORCHESTRATOR_JOURNEY_E2E=1` optional Playwright critical spec.""",
    "stage-09-ai-center-expanded.md": """### Stage 9 V5
- Journeys: ai engine room + ollama live + ai-center.spec.js present.""",
    "stage-10-final-certification.md": """### Stage 10 V5
- `journey_coverage_pct` must be **100** in `ten_x_platform_certification.json`.
- `repo_readiness_pct` vs `live_readiness_pct` split (Render/PSP/SOC2 EXTERNAL).
- Run `python scripts/verify_orchestrator_v5_bundle.py` before verdict.""",
    "00-moderator-chief-orchestrator.md": """### Moderator V5
- Regenerate prompt pack after gear-up edits: `generate_orchestrator_prompt_pack.py --write`.
- Reject stage if prior stage journey regression (manifest diff).""",
    "phase-0-p0-deploy-gate.md": """### Phase 0 V5
- Journey manifest + nav ledger generated before Stage 1 agents start.""",
}
