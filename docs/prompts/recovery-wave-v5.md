# Recovery Wave — Post V5 Gear-Up (all bases)

**Pack:** `2026-05-20-orchestrator-v5`  
**SOT batches:** 1330 (v4 recovery), 1354 (v5 transformational)  
**Runs after:** prompt pack regeneration with v3 + v4 + v5 on every stage and worker paste

## Mission

Close remaining gaps blocking **10X PLATFORM READY — REPO SCOPE** at **100%** across `v3_compliance_pct`, `v4_compliance_pct`, `v5_compliance_pct`, and `journey_coverage_pct`.

## Mandatory repo-side fixes

1. `python scripts/generate_orchestrator_prompt_pack.py` → all stages include **GEAR-UP V3/V4/V5**
2. `python scripts/verify_orchestrator_prompt_pack.py --strict` → **ORCHESTRATOR_PROMPT_PACK_PASS**
3. `python scripts/verify_orchestrator_v5_bundle.py` → **ORCHESTRATOR_V5_BUNDLE_PASS**
4. `python scripts/generate_orchestrator_journey_manifest.py --write` → **27** journeys
5. `python scripts/verify_stage_journey_coverage.py` → **JOURNEY_COVERAGE_PASS**
6. `python scripts/verify_nav_resolves_to_named_route.py --strict` → **NAV_LEDGER_PASS**
7. `python scripts/verify_help_center_tiers.py` → **HELP_CENTER_TIERS_PASS**
8. `python scripts/verify_five_pillar_platform_completion.py` → **FIVE_PILLAR_PLATFORM_PASS**
9. `python scripts/generate_v4_recovery_certification.py` → cert JSON with v5 gates (no `repo_gaps`)
10. `python scripts/audit_admin_gravity.py --strict` + North Star **75/75**

## Lane 2 (honest EXTERNAL — do not fake)

- Render live SHA parity (`render_live_sha`)
- Live PSP settlement (`live_psp_settlement`)
- SOC2/PCI attestation (`soc2_pci`)
- Full Playwright dual-host sweep with production hosts (optional repo proof on localhost:8000)

## Verdict

`10X PLATFORM READY — REPO SCOPE` only when recovery cert + v5 bundle + prompt pack strict are green. Otherwise `10X PLATFORM PARTIAL — REPO SCOPE` with `RERUN_REQUIRED: yes`.

## REPORT BACK

Use standard A–L footer to Orchestrator; include `journey_coverage_pct` and all three compliance pct maps.
