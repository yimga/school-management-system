"""Gear-Up V3 escalation content for orchestrator prompt pack."""

PACK_VERSION = "2026-05-20-orchestrator-v3"

GEAR_UP_UNIVERSAL = """## GEAR-UP V3 — PLATFORM ESCALATION (all agents)

**Pack:** `2026-05-20-orchestrator-v3` — supersedes v2 execution bar. **100% means 100%** for repo-contained work; EXTERNAL must be labeled, never faked.

### Cross-cutting quality bar (every stage)

1. **Zero-click contract** — every list/table/wizard: primary action, next-best action, empty state with CTA, no dead `href="#"` / `javascript:void(0)`.
2. **Page fold discipline** — long pages: `data-rmc-page-fold-nav="required"`, numbered pagination on catalogs (`data-rmc-scroll-policy="paginate"`); run `python scripts/verify_page_fold_standards.py` when templates change.
3. **Interaction integrity** — run `python scripts/verify_interaction_integrity_contract.py` on touched portal/control-plane templates.
4. **Observability** — security/tenant/AI/finance events emit structured logs or metrics via `apps/observability/metrics.py` (no PII in labels).
5. **Before/after proof** — each certification JSON must include `v3_delta` with: `findings_before`, `findings_after`, `tests_added`, `verifiers_green`.
6. **Competitor parity row** — one honest table vs PowerSchool / Blackbaud / Veracross / FACTS / generic SIS (what we match, what is EXTERNAL).
7. **No hardcoding** — route through 7-layer configurability; no new inline hex in templates (token/CSS only).
8. **Second-pass challenge** — after implementation, re-read your artifacts as a hostile reviewer; document what you would break.

### V3 verifier additions (run when in scope)

```bash
python scripts/audit_admin_gravity.py --strict
python scripts/verify_interaction_integrity_contract.py
python scripts/verify_page_fold_standards.py
python scripts/verify_platform_chromatic_compliance.py
```

North Star target: **75/75 ELITE** (not 71/75) before Stage 10 can claim READY.
"""

GEAR_UP_BY_STAGE: dict[str, str] = {
    "stage-00-current-state-validation.md": """### Stage 0 V3 addendum

- Regenerate `orchestrator_prompt_pack_audit.json` after v3 pack write; require `ORCHESTRATOR_PROMPT_PACK_PASS` with v3 version string.
- Add `v3_readiness_delta` block comparing v2 wave completion vs remaining repo gaps.
- Run `python scripts/generate_platform_inventory.py --write` if stale (>7 days).
- Phase 0: require `git commit` plan for staged migrations in readiness JSON (do not commit without user approval).""",
    "stage-01-core-runtime.md": """### Stage 1 V3 addendum

- Add `scripts/generate_core_runtime_slo_contract.py` output: Celery beat entries must list tenant-scoping proof per task.
- Run `bash scripts/release/render_predeploy.sh` dry-run sections that do not need live DB; document exit codes.
- JWT: prove refresh rotation + blacklist with negative test (revoked token → 401).
- API: document per-tenant throttle scopes in `core_runtime_certification.json`.
- **Must pass** `audit_admin_gravity.py --strict` for any template touched (or zero template touches).""",
    "stage-02-tenant-isolation.md": """### Stage 2 V3 addendum

- Add DSAR export path test: tenant A cannot export tenant B rows via management command or API.
- Impersonation: prove session ends on tenant switch; audit row immutable.
- Add `tenant_chaos_scenarios.json` artifact: 5 scripted cross-tenant attack scenarios + expected block.
- Postgres-only tests: document skip reason; add CI note for `tenants-rls` job.""",
    "stage-03-edge-routing-branding.md": """### Stage 3 V3 addendum

- Four-host matrix: extend `edge_surface_browser_qa.json` with required Playwright commands (EXTERNAL run OK).
- Marketing: produce `marketing_min_css_burndown.json` plan for `scan_off_token_colors --strict` (do not claim 0 unless achieved).
- Theme: automated test that `data-theme` is never `system`/`auto` on `<html>` (`scan_theme_attribute_contract.py`).
- Brand cascade: prove tenant `SiteSettings` overrides platform default in one integration test.""",
    "stage-04-policy-entitlements.md": """### Stage 4 V3 addendum

- Wire `can_capability()` into **one** high-traffic view per plane (manager + tenant) with test proving deny path.
- PDP: add test that field-level redaction fires for `sensitivity_tier=restricted`.
- Registry health: every `external_required` registry must have `owner`, `proof`, `test` and pass `test_registry_health_contracts`.
- Metadata: prove DDL guard blocks `RunSQL` on tenant request path.""",
    "stage-05-finance-ledger.md": """### Stage 5 V3 addendum

- Webhook idempotency replay test: duplicate delivery does not double-post ledger.
- Add `ledger_orphan_scan` to certification (zero orphan `PlatformLedgerEntry` without reference).
- Payroll: prove Decimal quantize on all money fields in serializers/responses (`amount_str` pattern).
- PSP: expand EXTERNAL table with exact env vars needed for live settlement proof.""",
    "stage-06-academics-operations.md": """### Stage 6 V3 addendum

- EMIS: prove export schema matches ministry column contract in JSON artifact.
- Offline: stress-test 3 conflicting `offline_action_conflict` resolutions in one test module.
- Reports: `publish_term_results` route must have permission test + tenant scope test.
- Communication: SMS template locale matrix (en/fr/es/pt/ar) char-count gate documented.""",
    "stage-07-migration-cloud.md": """### Stage 7 V3 addendum

- Connector dry-run: `verify_migration_cloud_connectors.py` 8/8 + add per-connector `last_tested_at` in registry JSON.
- Quarantine: test that bad row stays quarantined after re-import (idempotent).
- Operator dashboard: RequestFactory contract for staff-only + 404 cross-tenant.
- Document FACTS/Skyward write-path as counsel EXTERNAL in certification (never stub as done).""",
    "stage-08-workspace-ux.md": """### Stage 8 V3 addendum

- **Mandatory:** `audit_luxury_ui_surface.py` → 15/15 ULTRA-LUXURY.
- Run `npm run sweep:abrupt-end` tier operator+admin OR document EXTERNAL with route list in `workspace_cockpit_browser_qa.json`.
- Extend a11y: confirm manager AI Center + migration routes in axe smoke list.
- Every major hub: `data-page-header` + `ds-action-bar` + `data-rmc-zero-click="1"`.
- Studio OS: `data-rmc-studio-workspace="1"` + fold nav on long launch wizard.""",
    "stage-09-ai-center-expanded.md": """### Stage 9 V3 addendum (beyond 19 phases)

- **Phase 20 — AI Center health SLO:** `/super/ai-center/health/` panel with inventory freshness, index age, gateway circuit state, last error class (no secrets).
- **Phase 21 — RAG freshness beat:** document Celery beat `ENABLE_AI_KNOWLEDGE_INDEX_BEAT` + manual `generate_ai_center_inventory.py --write` procedure.
- **Phase 22 — Live Ollama contract:** add `scripts/verify_ollama_live.py` (non-strict PASS when daemon down); strict only on operator host.
- **Phase 23 — Competitive AI posture:** `ai_center_competitive_posture.json` — honest table vs ChatGPT-in-SIS, PowerSchool AI, etc.
- **Phase 24 — KB vector path:** prove `KBArticle.vector_embedding` tenant-scoped search test (portal batch 1317 extension).
- All paths in `docs/architecture/RUNMYCAMPUS_AI_CENTER.md` and `RUNMYCAMPUS_AI_CENTER_API_CONTRACTS.md` must exist and match routes.""",
    "stage-10-final-certification.md": """### Stage 10 V3 addendum

- **Hard gate:** `audit_admin_gravity.py --strict` → PASS (fixes false-positive `admin:` in non-Django namespaces allowed via template label `(admin)` or auditor fix).
- **Hard gate:** `run_northstar_audit.py` → **75/75** (not 71/75).
- Run **full** extended verifier bundle (v3 list in global rules).
- `ten_x_platform_certification.json` must include `v3_prompt_pack_version` and per-stage `v3_compliance_pct` (0–100 per stage 0–10).
- Verdict **10X PLATFORM READY — REPO SCOPE** only when all repo gates green; never LIVE without EXTERNAL proof.
- Challenge v3 deltas from stages 1–9; list any stage that did not implement v3 addendum → RERUN_REQUIRED.""",
    "00-moderator-chief-orchestrator.md": """### Moderator V3 addendum

1. **Prompt pack:** Run `generate_orchestrator_prompt_pack.py` + `verify_orchestrator_prompt_pack.py --strict` after v3 edits.
2. **Recovery wave (after v3):** Fix admin-gravity blocker → commit SOT batches 1320–1329 + autonomous log → re-run Agent 10.
3. **Second pass:** Assign fresh reviewer agent per stage to challenge v3 `v3_delta` claims.
4. **SOT discipline:** One §11.4 row per batch; run `verify_sot_batch_id_uniqueness.py`; `generate_system_closure_map.py --write`.
5. **Do not stop** at PARTIAL without recovery rerun unless EXTERNAL-only blockers remain.""",
    "phase-0-p0-deploy-gate.md": """### Phase 0 V3 addendum

- Migrations: `git add` + user-approved commit required for READY (not STAGED-only).
- `render_predeploy.sh`: capture last 50 lines of log in `phase0_predeploy_evidence.json`.""",
}
