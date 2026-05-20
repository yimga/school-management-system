"""Gear-Up V4 — category-defining bar (supersedes v3)."""

PACK_VERSION = "2026-05-20-orchestrator-v4"

GEAR_UP_V4_UNIVERSAL = """## GEAR-UP V4 — CATEGORY-DEFINING BAR (mandatory)

**Pack:** `2026-05-20-orchestrator-v4` — supersedes v3. Compete with PowerSchool + Blackbaud + Veracross + Shopify-grade ops UX.

### Non-negotiables (repo-contained)

1. **All gaps CLOSED** — every OPEN row in `orchestrator_gap_burndown.json` fixed or reclassified with proof.
2. **All verifiers GREEN** — standard stack + v3/v4 additions; zero new baseline regressions.
3. **Security** — `audit_security_surface.py`, `audit_tenant_isolation.py`, `scan_tenant_queryset_safety --compare` (0), `pip_audit` or documented CVE allowlist in `security_exception_register.json`.
4. **Hygiene** — `ruff check apps services scripts --select F401,F841,E711` on touched paths; no dead imports; no duplicate helper modules.
5. **Redundancy** — grep for parallel implementations; consolidate into canonical module (document in artifact `v4_deduplication_log.json`).
6. **Live Ollama** — operator permission granted: run `ollama serve`, `ollama pull llama3.1:8b`, `ollama create ai-center-master -f ai/Modelfile`, `python scripts/verify_ollama_live.py --strict --invoke`; artifact `docs/generated/ollama_live_proof.json`.
7. **Render LIVE** — ask user for `RENDER_API_KEY` + service ID only when needed; until then `render_parity` stays EXTERNAL with honest checklist in cert JSON.
8. **North Star** — `run_northstar_audit.py` → **75/75 DOMINANT** (hard gate).
9. **Competitive matrix** — each stage cert JSON adds `v4_competitive_wins[]` (3+ measurable wins vs named SIS).

### V4 verifier bundle (run all applicable)

```bash
python scripts/audit_admin_gravity.py --strict
python scripts/run_northstar_audit.py
python scripts/verify_ollama_live.py --strict --invoke
python scripts/verify_ai_engine_room.py
python scripts/verify_interaction_integrity_contract.py
python scripts/verify_page_fold_standards.py
python scripts/scan_money_float.py --compare
python scripts/scan_tenant_queryset_safety.py --compare
python scripts/scan_pii_logging_smell.py --compare
python scripts/verify_orchestrator_prompt_pack.py --strict
```

### Proof artifact (every agent)

Add to certification JSON:

```json
"v4": {
  "prompt_pack_version": "2026-05-20-orchestrator-v4",
  "gaps_closed": [],
  "verifiers_all_green": true,
  "hygiene_ruff_exit": 0,
  "security_audit_exit": 0,
  "competitive_wins": []
}
```
"""

GEAR_UP_V4_BY_STAGE: dict[str, str] = {
    "stage-00-current-state-validation.md": """### Stage 0 V4
- Delta audit: v2→v3→v4 prompt versions in readiness JSON.
- Close every stale OPEN gap in burndown (re-verify file existence).
- `pip_audit -r requirements.txt` summary in readiness (honest CVE list).""",
    "stage-01-core-runtime.md": """### Stage 1 V4
- Celery beat: every task has `tenant_id` or documented platform-global allow.
- Rate limits: prove 429 on burst via test.
- `render_predeploy.sh` log excerpt in `core_runtime_certification.json` (dry-run OK).""",
    "stage-02-tenant-isolation.md": """### Stage 2 V4
- 10-attack penetration matrix all BLOCKED with test names.
- DSAR + impersonation + RLS in one `tenant_isolation_v4_suite` run.""",
    "stage-03-edge-routing-branding.md": """### Stage 3 V4
- Playwright four-host script documented; run if `E2E_LOGIN_USER` set.
- `scan_theme_attribute_contract.py` PASS on touched CSS.""",
    "stage-04-policy-entitlements.md": """### Stage 4 V4
- PDP deny path on restricted field in live view test.
- Entitlement cache invalidation integration test.""",
    "stage-05-finance-ledger.md": """### Stage 5 V4
- Ledger replay + webhook dedupe in one test module.
- `scan_money_float` 0 with no new allows.""",
    "stage-06-academics-operations.md": """### Stage 6 V4
- EMIS schema JSON locked to ministry columns.
- Offline conflict 5-case stress test.""",
    "stage-07-migration-cloud.md": """### Stage 7 V4
- Connector gate 8/8 + 30 tests on fresh SQLite DB.
- Quarantine never promotes bad rows (test).""",
    "stage-08-workspace-ux.md": """### Stage 8 V4
- Luxury 15/15 + abrupt-end sweep tier operator+admin.
- axe smoke on `/super/ai-center/` added if missing.""",
    "stage-09-ai-center-expanded.md": """### Stage 9 V4
- **Live Ollama required:** `verify_ollama_live.py --strict --invoke` PASS.
- `ollama_live_proof.json` with model, latency_ms, FEATURE/DATA fallback sample outputs.
- Phases 20–24 from v3 + vector KB tenant isolation test.
- No duplicate `services/ai` vs `services/ai_center` gateways.""",
    "stage-10-final-certification.md": """### Stage 10 V4
- Verdict `10X PLATFORM READY — REPO SCOPE` only when: North Star 75/75, admin_gravity strict PASS, ollama live proof exists, all stage certs have `v4` block, zero OPEN repo gaps.
- `v4_competitive_readiness_score` 1–10 with evidence (honest ≤8 until LIVE Render+PSP).
- Full verifier table in `ten_x_platform_certification.json`.
- Include `v3_compliance_pct` and `v4_compliance_pct` per stage 0–10 in certification JSON.""",
    "00-moderator-chief-orchestrator.md": """### Moderator V4
- Gear-up v4 pack green before any new agent wave.
- **Recovery wave** closes ALL repo gaps; user commits SOT 1320–1334 when approved.
- Render: request `RENDER_API_KEY` only when user opts into LIVE wave.""",
    "phase-0-p0-deploy-gate.md": """### Phase 0 V4
- Migrations committed (user-approved) OR explicit BLOCKED in JSON with reason.
- `render_predeploy.sh` full green log captured.""",
}
