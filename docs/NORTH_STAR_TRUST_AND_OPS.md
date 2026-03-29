# North star — Trust, compliance, and operational excellence

**Purpose:** Single reference for North star items **N9–N10** (performance), **N11–N16**, **N24–N26**, plus **§0.4 LMS / SSO & federation** and **§0.4 UK / international packs** (competitive depth — in-repo contracts below). Execution and status stay in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md); this doc is the implementation and runbook anchor.

## Trust center and compliance (N13–N16)

- **Trust center:** `super:trust_center` → `/super/trust/`. Security, compliance, data handling, retention, breach response. Keep copy and links current; audit periodically.
- **Compliance overview:** `super:compliance_overview`. Link from trust center and nav.
- **Data residency (N14):** Document in trust center and tenant config where data lives; region-specific compliance (GDPR, FERPA) in REGIONAL_POLICY_PACKS and compliance docs.
- **Audit (N15):** Sensitive actions logged; audit export at `/super/trust/` (audit export); retention and access controls in compliance docs.
- **Certifications (N16):** SOC 2 / ISO roadmap and trust signals for marketplace; document in trust center when available.

## Uptime and resilience (N11)

- **SLO/SLA:** Target uptime 99.9%; document in trust center (SLO & uptime card) and ops runbook; health checks at `/health/`, `/healthz/`.
- **Runbooks:** Common incidents and escalation; "another Bromcom-style outage" designed against (redundancy, health, observability). **Index:** [RUNBOOKS_INDEX.md](RUNBOOKS_INDEX.md).
- **References:** `scripts/phase_h_audit.py`, observability app, control plane Pulse.

## Graceful degradation (N12)

- **Rate limits:** Apply rate limits on critical APIs (e.g. auth, audit export, create-school); return **429 Too Many Requests** with `Retry-After` or a JSON body `{"error": "rate_limit", "retry_after_seconds": N}` so clients can implement "try again" flows.
- **Try again:** No silent failures or white screens under load; user-facing "Try again" or "Service busy" messaging when rate-limited or degraded.
- **Queue depth and timeouts:** Document for async jobs (Celery, outbox); user-facing messaging when services are degraded. See RUNBOOKS_INDEX and observability app.

## Performance targets (N9 / N10)

- **N9 (experience):** Critical tenant and staff paths should feel responsive; smoke budgets in code catch gross regressions on role home, Setup Studio, metadata catalog, advancement donors, etc.
- **N10 (measurable):** Server-side smoke budgets, optional **strict** failure in CI/release, optional Lighthouse lab CWV when wired, RUM read path for staff — see below.

### Performance targets (operator contract — in-repo)

1. **Definitions and rows:** [PERFORMANCE_BUDGETS.md](PERFORMANCE_BUDGETS.md) — targets, `PERF_BUDGET_STRICT`, `PERF_BUDGET_STRICT_N10`, and **`PERF_BUDGET_STRICT_GATE_ROWS=n10_public`** for marketing-only CI enforcement.
2. **Smoke script:** `python scripts/check_performance_budgets.py` — warns by default; with **`PERF_BUDGET_STRICT=1`** fails when **enforce** rows exceed time/query ceilings (`pre_deploy_gate.sh` runs warn-only unless strict).
3. **Lab CWV (optional):** `.github/workflows/lighthouse-ci.yml` when repository **`LHCI_URL`** (and extras) are set — [LHCI_CI_URLS.md](LHCI_CI_URLS.md), `lighthouserc.cjs`.
4. **RUM summary (staff):** `GET /api/internal/north-star/rum-web-vitals/` — [RUM_HOOK.md](RUM_HOOK.md); ties to observability SLO JSON where configured.
5. **Marketing PR lane:** [MARKETING_EXECUTION.md](MARKETING_EXECUTION.md) — N10 workflow + `n10_public` gate rows.

**Verifier:** `python scripts/verify_performance_targets_doc_discipline.py` (anchors this section to the files and env flags above).

## Observability and runbooks (N24)

- Metrics, traces, logs: observability app and platform runtime; structured logging.
- Runbooks for common incidents; on-call and escalation path in ops docs.

## Rollout and migration playbooks (N25)

- Documented migration, validation, rollback, phased rollout; no go-live disasters (§0.4.3).
- **References:** [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), RUNBOOK_ADMIN_TO_SUPER_MIGRATION.md, launch_studio_checklist.md. Runbooks index: [RUNBOOKS_INDEX.md](RUNBOOKS_INDEX.md).
- **Migration safety (summary):** Validate migration in sandbox; rollback path per migration run; phased rollout (no big-bang). See `super:migration_cloud` and `super:migration_rollback`.

### Migration safety (operator contract — in-repo)

Use this sequence for **schema** and **data** changes; do not skip staging for tenant-affecting migrations.

1. **Authoring:** Follow resolver-first ordering — [RESOLVER_MIGRATE_DELETE_ORDERING.md](RESOLVER_MIGRATE_DELETE_ORDERING.md). Siteconfig / Phase B discipline — [SITECONFIG_OWNERSHIP_MIGRATION.md](SITECONFIG_OWNERSHIP_MIGRATION.md).
2. **Repo gate:** `python manage.py makemigrations --check --dry-run` must be clean before merge (also inside `scripts/pre_deploy_gate.sh`).
3. **Sandbox / CI DB:** Apply migrations on a **disposable** DB; run `python scripts/verify_phase_b_execution.py` when `platform_runtime` / Phase B snapshots are in scope.
4. **Staging:** Apply migrations on **staging first**; smoke critical paths; record hostname + migrate output in the release ticket ([RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) — migrations row).
5. **Control plane:** Use **Migration cloud** (`super:migration_cloud`) for import/playbook operations; use **rollback** views when the product runbook requires it (`super:migration_rollback`). Automation runs are visible under **MigrationRun** in admin when enabled.
6. **Production:** Apply only after staging sign-off; keep a **rollback plan** (previous image + backward-compatible migrations, or explicit data migration) documented in the ticket—not ad-hoc.
7. **Data cutover / shadow:** Large SIS moves follow [MIGRATION_SHADOW_RUNBOOK.md](MIGRATION_SHADOW_RUNBOOK.md) (BR-04) in addition to Django migrate.

**Verifier:** `python scripts/verify_migration_safety_doc_discipline.py` (keeps this section linked to gates and paths above).

## LMS / SSO and federation (§0.4 competitive depth)

Schools expect **SAML2 / OIDC** staff sign-in, optional **district interop** surfaces, and marketplace **Clever / ClassLink**-class connectors. In-repo code covers protocols, health telemetry, and tests; **live vendor partnership + district endpoint sign-off** stays external ([SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md)).

### LMS / SSO (operator contract — in-repo)

1. **SAML2 ACS:** `apps/accounts/views_saml.py` — IdP POST callback; CSRF posture documented in `scripts/allowlists/csrf_exempt_allowlist.json`; metadata refresh via `python manage.py refresh_saml_idp_metadata`.
2. **OIDC broker:** `apps/accounts/views_oidc.py` — OIDC flows with federation health hooks.
3. **Federation health:** `apps/accounts/federation_sso_health.py` — `record_sso_success` / `record_sso_failure`; persisted rows power trust / interop dashboards (e.g. control-plane trust center SSO tile, district interop context).
4. **Regression tests:** `apps/accounts/tests/test_saml_views.py`, `apps/accounts/tests/test_federation_sso_health.py`; release train runs `apps.accounts.tests.test_federation_sso_health` via `scripts/pre_deploy_gate.sh` (Phase checks slice).
5. **Clever / ClassLink production:** Readiness is **code-gated** (`scripts/release_readiness_check.sh`, interop client tests); **district + vendor live sign-off** is **OPEN** in the backlog doc above — do not treat merge-green as partnership-complete.

**Verifier:** `python scripts/verify_lms_sso_doc_discipline.py` (anchors this section to the paths and gates above).

## UK / international packs (§0.4 competitive depth)

**UK** and **international** go-to-market depth is expressed as **installable regional policy packs**, **RTL-aware UX (N22)**, **localized catalogs**, and **marketing regional JSON**—not a single “UK checkbox.” Statutory sign-off per jurisdiction remains **product + legal** work outside pure merge gates.

### UK / international packs (operator contract — in-repo)

1. **Regional policy packs:** `apps/siteconfig/tenant_config.py` — `REGIONAL_POLICY_PACKS` and `get_regional_policy_pack`; **GBR** (UK), **EU**, **US**, **MENA**, **WAEC**, **LCA**, **ASIA**, and related keys are defined in code and extended via sequenced §11.4 slices. Geography wedge map: [WEDGES_7_13_GEOGRAPHY_PLAN.md](WEDGES_7_13_GEOGRAPHY_PLAN.md).
2. **RTL / regional UX (N22):** [N22_RTL_AND_REGIONAL_UX.md](N22_RTL_AND_REGIONAL_UX.md) — `RegionConfig.is_rtl`, `region_settings` in `apps/siteconfig/context_processors.py`, `portal_base.html` `dir=rtl` wiring; tests `apps/siteconfig/tests/test_n22_region_settings_rtl.py`.
3. **Marketing regional payloads:** [MARKETING_REGIONAL_JSON.md](MARKETING_REGIONAL_JSON.md) — JSON contract for localized marketing surfaces.
4. **i18n catalog discipline:** `locale/**` message catalogs; merge train runs `python scripts/verify_i18n_catalog_fresh.py` (see `scripts/pre_deploy_gate.sh`). Refresh with `python manage.py sync_i18n_catalog --compile` when templates add `{% trans %}` strings.
5. **North star i18n lint:** `python scripts/lint_north_star_i18n.py --strict` (bundled in `scripts/verify_phases_3_11_gates.py`) keeps key shells honest for load/trans usage.

**Verifier:** `python scripts/verify_uk_international_packs_doc_discipline.py` (anchors this section to the paths and gates above).

## Advancement CRM depth (§0.4 competitive depth)

**Advancement** is expressed as **tenant-scoped donor and gift records**, **staff CRUD on the school subdomain**, and **super-shell entry points**—not a full third-party CRM replacement. Deeper pipeline analytics, wealth integrations, and formal gift accounting remain **product + finance** work sequenced as §11.4 slices when scoped.

### Advancement CRM depth (operator contract — in-repo)

1. **Tenant staff CRUD:** `apps/schools/views_advancement.py` — donor list/create/detail/edit and gift delete; guarded by login, staff-only, `@require_school`, and structured logging via `log_view_exception`.
2. **URL wiring:** `apps/accounts/urls.py` — named routes `advancement_donor_list`, `advancement_donor_create`, `advancement_donor_detail`, `advancement_donor_edit`, `advancement_gift_delete` under `/backend/advancement/...`.
3. **Data model:** `apps/schools/models.py` — `AdvancementDonor`, `AdvancementGift`; schema slices include `apps/schools/migrations/0038_advancement_donor_gift.py` and `apps/schools/migrations/0040_advancementgift_campaign_name.py`.
4. **Super shell entry points:** `apps/schools/super_urls.py` — `advancement_hub`, `advancement_phase2_placeholder`; handlers in `apps/schools/super_views_wedge.py` (`super_advancement_hub`, `super_advancement_phase2_placeholder`).
5. **Tests:** `apps/schools/tests/test_advancement_tenant_crud.py`, `apps/schools/tests/test_super_advancement_phase2_uuid_school.py`; wedge URL reverse for `super:advancement_hub` is exercised in `apps/schools/tests/test_wedge_world_class_implemented.py`.
6. **Gates:** `scripts/pre_deploy_gate.sh` and `scripts/verify_phases_3_11_gates.py` run `python scripts/verify_advancement_crm_doc_discipline.py` so this contract cannot drift silently.

**Verifier:** `python scripts/verify_advancement_crm_doc_discipline.py` (anchors this section to the paths and gates above).

## Support and onboarding as product (N26)

- Training and post-go-live support; "day two" experience; guided onboarding and Setup Studio as proven path.
- **References:** Phase I.5 guided onboarding, siteconfig guided_onboarding, first-run tours.
