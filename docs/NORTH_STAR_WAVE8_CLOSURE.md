# North star Wave 8 & Phase I.5 — closure evidence (N1–N29, beyond-reach, competitive bar)

**Authority:** Single place to reconcile RUNMYCAMPUS §0.1.5 Wave 8 and Phase I.5 “Improvements 1–8” with shipped code. The SOT checkboxes that point here are **closed for the scope below**; items marked *ongoing* stay in BACKLOG until the next wave.

## Beyond-reach — advancement (wedge 5)

| Requirement | Evidence |
|---------------|----------|
| Tenant donor/gift CRUD (not super-only) | `apps/schools/views_advancement.py`; URLs `accounts:advancement_donor_list|create|detail|edit`, `accounts:advancement_gift_delete`; templates `schools/advancement_donor_*.html`; migration `schools.0040_advancementgift_campaign_name` (`campaign_name` on gifts). |
| Super hub documents tenant path | `super_advancement_hub.html` + `tenant_donor_crm_path`. |
| Tests | `apps/schools/tests/test_advancement_tenant_crud.py` (school scope, gift flow). |

## N8 — Command palette as primary

| Requirement | Evidence |
|-------------|----------|
| Heavier-flow intents | `get_studio_command_palette_entries`: advancement donors, district interop, publish grades, parent dashboard; existing Studio + analytics entries retained. |
| Role-home / quick links | `BACKEND_QUICK_LINKS`: District & LMS interop, Donors & gifts; `BACKEND_WELCOME_ACTION_GRID`: Donors & gifts tile. |

## N4 — Touch (partial)

| Requirement | Evidence |
|-------------|----------|
| ≥44px targets on key actions | `static/css/north-star-touch-targets.css` (`.min-touch-target`); linked from `portal_base.html`; advancement templates use class on primary buttons. |

## N1 / N27 / Phase I.5 §8.0.7 — Guided “what next”

| Requirement | Evidence |
|-------------|----------|
| First-run paths | Existing: `first_login_checklist_card`, `tour_backend_dashboard`, Setup Studio steps (`views.py` backend_dashboard context). |
| This wave | Palette + quick links surface advancement and interop without extra clicks (click compression). |

## Phase I.5 improvement 6 — Click reduction validation

| Requirement | Evidence |
|-------------|----------|
| Baseline table | `docs/CLICK_REDUCTION_BASELINE.md` updated with **scripted path lengths** (URL hops from dashboard) as proxy until human re-measure. |

## Competitive bar (§0.4) — structural closure

| Checkbox | Evidence |
|----------|----------|
| No NXT-style multi-second waits on critical paths | `scripts/check_performance_budgets.py` + `docs/PERFORMANCE_BUDGETS.md`; role home / Setup Studio / advancement donors budgets; `PERF_BUDGET_STRICT=1` optional in gate. |
| List/detail paginated | Advancement donor list paginated (25/page); student list etc. already paginated. |
| Ctrl+K + role-home reduce clicks | Expanded palette + `BACKEND_QUICK_LINKS` / welcome grid (above). |
| Re-measure after releases | `CLICK_REDUCTION_BASELINE.md` “Re-measure” row. |

## N9 / N10 / Phase I.5 #8 — Performance

| Requirement | Evidence |
|-------------|----------|
| Server-side smoke budgets | `check_performance_budgets.py` paths including advancement list. |
| LCP/FID/CLS in CI | Advisory today; full CWV gate = *ongoing* (Playwright perf hook or Lighthouse CI). |

## N11 / N13 / N14 / N15 / N16 — Trust (living product)

| Requirement | Evidence |
|-------------|----------|
| Trust center | `super_trust_center.html`: compliance, SSO health, API Center, sessions, platform events, **audit export**, data residency, certifications, **SLO (N11)**, **resilience / Bromcom-style (N12)**, **support N26**, **ecosystem N18–N20**. |
| Auditor export | `super:audit_export` linked from trust center. |
| SOC 2 / ISO | Roadmap card (N16) — execution = partnership/legal track, not code-complete. |

## Items intentionally *ongoing* (do not mark SOT [x] without product sign-off)

- **N3** Full WCAG AA audit of every page.
- **N5** Offline PWA depth for timetable/contacts. *Partial (Wave 15):* `manifest-portal.json` shortcuts (calendar + parent home); full offline critical reads still open.
- **N6** Full role/school-type terminology matrix.
- **N7** Every surface one-primary-action audit.
- **N10** Strict LCP/FID/CLS CI failure. *Partial (Wave 16–21):* **`LHCI_AUTO_EXTRAS`** optional same-origin URL bundle in `lighthouserc.cjs` + `vars.LHCI_AUTO_EXTRAS` in Lighthouse workflow; **`LHCI_URLS_EXTRA`**; [LHCI_CI_URLS.md](LHCI_CI_URLS.md). **RUM:** ingest + **staff read** `GET /api/internal/north-star/rum-web-vitals/` (aggregates `PlatformEventLog`); SLO JSON links `rum_web_vitals_summary` ([RUM_HOOK.md](RUM_HOOK.md)). Full CWV on every PR + BI dashboards still open.
- **N12** User-visible retry on all rate-limited APIs. *Partial:* EdFi, school `SchoolConfigAPI`, interop discovery, ministry placeholders, lead capture, **CEDS**, **OneRoster** (token + IP 429 JSON), **SCIM** (detail includes retry hint) include `retry_after` / human guidance where applicable; not every 429 path audited.
- **N14** Per-region legal controls beyond docs.
- **N16** SOC 2 Type II *executed*.
- **N17** Marketplace impact preview + **interactive dependency graph** (pan/zoom). *Waves 10–25:* catalog modal, blueprint, module market, template gallery, brand→gallery, north-star JSON, audit snapshot; **Wave 25:** `package-dependency-graph.js` on gallery, install modal, rollback expanders, Experience Studio pack page. Automation/Output Studio keep their own graph rails.
- **N2** Placeholder / polish sweep. *Partial (Wave 22):* advancement hub copy; portal search + entity console **i18n** on placeholders/ARIA; §8.0.11 full template audit still advisory.
- **N20** Universal pack rollback UX. *Partial (Wave 13–22):* tenant metadata package rollback UI + confirm; blueprint **ROLLBACK** + **`blueprint_rolled_back`**; **learning wedge** **`POST /api/learning/pack-rollback/`** + **`learning_wedge_pack_rolled_back`** + shared-feature-safe unwind (`test_learning_institution_beyond`).
- **N21–N23** Full i18n/RTL/inclusive imagery pipeline. *Partial:* advancement donor list template wrapped with `{% trans %}`; platform-wide i18n ongoing.
- **N24** Full metrics/traces/on-call productization.
- **N28** EWS depth beyond BR-06 stubs. *Partial (Wave 11):* `RiskFactor` post_save → `StudentAtRiskSignal` for portal-linked students (score ≥50); dashboard table; intervention start/resolve/dismiss syncs signal status. Full predictive pipeline still incremental.
- **N29** Measured setup-in-minutes with N≥5 schools.
- **Wave 4** First-party transport/library/inventory/clinic/timetabling modules. *Partial (Wave 12–18):* **POS stub:** `accounts:ops_pos`, `PosSaleLine`, `test_tenant_ops_wave18_pos`; facilities/visitor/substitutes + prior ops; full retail CMMS still open.
- **Wave 6** Mobile bulk capture. *Partial (Wave 14–18):* hub + **seating chart** + **teacher attendance overview** cards, `touch-action: manipulation`, home-screen tip; native app still open.
- **Wave 5** Pre-built competitor packs per vendor.

## Autonomous batch id

Wave 8 execution batch: **2026-03-18** — advancement tenant CRUD + palette + touch targets + perf path + docs.

**Wave 9 (same day):** Teacher/student dashboard API return **404** when `TeacherProfile` / `StudentProfile` missing (not 500). Tests: `apps/api/tests/test_dashboard_api_profile_404.py` (in `pre_deploy_gate.sh`). Rate-limited JSON responses: **EdFi**, **SchoolConfigAPI** (`schools/api_views`), **interop** + **ministry** stubs include `message` + `retry_after`. Advancement donor list: **i18n** (`{% trans %}`).

**Wave 10:** N17 gates (blueprint preview-before-apply; catalog install via impact modal; module market impact ack). **CEDS** 429 JSON `message`/`retry_after`. Vocational verify-skill: **404** for wrong-tenant student. Gate: `apps.marketplace.tests.test_install_impact`, `test_governance`.

**Wave 11:** OneRoster 429 JSON `message`/`retry_after`; SCIM 429 detail improved. **EWS:** `ews_signals` + `StudentAtRiskSignal` sync from `RiskFactor`; at-risk dashboard section; BR-06 intervention updates signal. Tests: `test_ews_signal_sync`, OneRoster 429 assertions.

**Wave 12:** Operations hub + Wave 4 surfaces (`views_tenant_ops`, `apps/schoolops/tests/test_tenant_ops_wave4`); module market entries `inventory`, `clinic`, `timetabling`; command palette “Operations hub”.

**Wave 13:** **N20** `siteconfig:installed_packages_rollback` + tests; **N10** `PERF_BUDGET_STRICT_N10` in `check_performance_budgets.py` + `PERFORMANCE_BUDGETS.md`.

**Wave 14:** **Wave 6** teacher bulk-capture hub + roll-call UX tweak; **N24** tenant activity log + tests + palette/actions.

**Wave 18:** **Wave 6** hub + seating chart + teacher attendance overview + mobile tweaks; **Wave 4** `pos_stub` / `PosSaleLine` / `ops_pos`; **N20** package activity table + actor resolution; **N10** `LHCI_URLS_EXTRA` + workflow vars; tests `test_tenant_ops_wave18_pos`, `test_package_activity_table_after_apply`, bulk hub assertions; doc `LHCI_CI_URLS.md`.

**Wave 19:** POS ↔ `InventoryItem` FK + tests; roll-call **form-draft-save** + SW precache `form-draft-save.js`; blueprint rollback **ROLLBACK** ack + UI; `test_blueprint_rollback_ack`; `LHCI_STAGING_GITHUB_VARS.md`.

**Wave 20:** POS save **atomic inventory decrement** (`quantity__gte` guard) + `test_pos_insufficient_inventory_blocks_sale`; **RUM** ingest + `rum-beacon.js` + `test_rum_ingest`; blueprint **`blueprint_rolled_back`** audit row; expanded **LHCI_URLS_EXTRA** recommendations in `LHCI_STAGING_GITHUB_VARS.md`.

**Wave 21 (N10):** **`LHCI_AUTO_EXTRAS`** in `lighthouserc.cjs` + workflow var; **`GET /api/internal/north-star/rum-web-vitals/`** staff aggregate + `rum_aggregate` tests; SLO **`observability.rum_web_vitals_summary`**; docs [LHCI_CI_URLS.md](LHCI_CI_URLS.md) / [RUM_HOOK.md](RUM_HOOK.md).

**Wave 22:** **N2** partial (advancement hub + portal search + entity console i18n). **N20** learning wedge **rollback** API + **`rollback_single_wedge_pack_slug`** + **`learning_wedge_pack_rolled_back`** event; tests in `test_learning_institution_beyond`; gate includes that module.

**Wave 23:** **N17** **`dependency_graph`** on **`api-north-star-package-impact`** + `list_reverse_dependent_package_ids` / `normalize_declared_dependencies` in package engine; **N20** metadata rollback **parity**: richer **`package_rolled_back`** event, tenant UI **i18n** + **deps column** + impact API hint; tests `PackageDependencyGraphTests`, north-star graph tests, `PlatformEventLog` assertion in `test_tenant_package_rollback_ui`.

**Wave 24:** **N17** tenant **template gallery** impact preview (`metadata_apply_preview_bundle`, `confirm_metadata_apply`, 15m session gate); **`build_tenant_install_impact.dependency_graph`**; **`install_app`** audit **`impact_snapshot`**; **brand import** “apply suggested theme” **redirects** to gallery (`preview_slug`) instead of bypassing preview; tests `test_template_gallery_impact`, `test_install_impact` (graph), `test_governance` (audit snapshot), `test_metadata_apply_preview_bundle_includes_graph`.

**Wave 25:** **N17** **`package-dependency-graph.js`** (`RmcPackageDependencyGraph`) wired to **template gallery**, **install impact modal**, **installed_packages_rollback** (lazy fetch package-impact), **Experience Studio experience packs**. **N20** **`packages.0005`** version on Document/Experience packs; **`tenant_pack_install`** + portal **`document_upload`** hook + studio sync; **`test_tenant_pack_install`**, expanded **`test_experience_packs`** rollback cases.
