# RunMyCampus Master Platform Checklist

**Repo truth date:** March 10, 2026
**Rule:** Nothing is optional or deferred. This file is the single live execution ledger. If another document claims completion, treat it as historical until it is revalidated here.
**Hardening freeze:** Active. No unrelated feature work should bypass the gates listed below.

## Current baseline

| Signal | Current state |
|-------|----------------|
| `apps/siteconfig` Python files | 318 after deleting six unused legacy wrapper shims |
| `csrf_exempt` decorator hits | 13 total matches across 7 files; machine-classified by allowlist |
| `cursor.execute(` hits | 349 total matches across 89 files; non-migration usage is machine-classified by allowlist |
| Broad `except Exception` hits | 1,025 total matches across 333 files; high-risk files are baseline-enforced and ratcheted down |
| `gilead` references | 54 files / 177 matches, now concentrated in docs, migrations, and approved residue paths |
| Client secret leak | Previously present via `GEMINI_API_KEY` in template context; removed in this hardening pass |
| Tracked repo-root files | 21 allowlisted operational files; historical root docs moved to `docs/archive/root_history/` |
| Root DB/runtime artifacts | Root SQLite snapshots moved to `artifacts/db_snapshots/`; `celerybeat-schedule` and tracked SBOM moved under `artifacts/` |

## Verification commands

| Check | Command | Status |
|-------|---------|--------|
| Root clutter gate | `python scripts/check_root_clutter.py` | Passing |
| Secret exposure gate | `python scripts/lint_secret_exposure.py` | Passing |
| CSRF allowlist gate | `python scripts/lint_csrf_exempt_usage.py` | Passing |
| Raw SQL allowlist gate | `python scripts/lint_raw_sql_usage.py` | Passing |
| Legacy siteconfig import gate | `python scripts/lint_siteconfig_legacy_imports.py` | Passing |
| Broad exception baseline gate | `python scripts/lint_broad_except.py --allowlist scripts/allowlists/broad_except_allowlist.json --strict` | Passing |
| Full Git Bash gate | `bash scripts/pre_deploy_gate.sh` | Passing |
| AI secret regression | `python manage.py test apps.siteconfig.tests.test_ai_copilot_context -v 1` | Passing |
| Runtime metadata regression | `python manage.py test apps.siteconfig.tests.test_metadata_catalog -v 1` | Passing |
| Package lineage regression | `python manage.py test apps.packages.tests.test_engine -v 1` | Passing |
| Setup Studio persistence | `python manage.py test apps.setup_studio.tests -v 1` | Passing |

## Phase ledger

| Phase | Scope | Status | Exit criteria |
|------|-------|--------|---------------|
| 0 | Truth reset and gate tightening | In progress | Master checklist reset, stale-doc bannering started, new gates committed and wired into `pre_deploy_gate` |
| 1 | Security boundary hardening | In progress | No provider secret reaches HTML, CSRF inventory enforced, raw SQL inventory enforced, broad exceptions reduced in top-risk paths |
| 2 | Bounded-context completion | In progress | Ownership moved out of `siteconfig`, compatibility shims temporary, legacy paths deleted |
| 3 | Metadata brain completion | In progress | Catalog covers layouts, dashboards, workflows, APIs, templates, policies, packages, impact and lineage |
| 4 | Package engine deployment semantics | In progress | Structured validation/preview/apply/rollback/promotion live, apply state persisted, impact preview stored |
| 5 | Setup Studio productization | In progress | Guided onboarding backed by `setup_studio` state, recommendations, role previews, blockers, launch readiness |
| 6 | Repo cleanup and de-branding | In progress | Root clutter removed, generated artifacts relocated/ignored, active `gilead` references reduced to approved historical usage |
| 7 | Final deletion and verification | In progress | Legacy paths deleted, stale docs corrected, full gate and security baseline green on `main` |
| 8 | UI/UX, dashboards, and marketing completion | In progress | Role-native dashboard homes, contextual action engine, premium Setup Studio flow, marketplace trust UX, command-first navigation, and proof-driven marketing surfaces enforced as platform law |

## Implemented in this pass

### Phase 0
- [x] Added tracked-root clutter enforcement: `scripts/check_root_clutter.py`
- [x] Replaced the loose root clutter scan with a strict tracked-root allowlist in `scripts/allowlists/tracked_root_allowlist.json`
- [x] Added CSRF allowlist enforcement: `scripts/lint_csrf_exempt_usage.py`
- [x] Added raw SQL allowlist enforcement: `scripts/lint_raw_sql_usage.py`
- [x] Added legacy siteconfig import enforcement: `scripts/lint_siteconfig_legacy_imports.py`
- [x] Added a strict broad-exception baseline for the highest-risk files: `scripts/lint_broad_except.py --allowlist ... --strict`
- [x] Added provider secret exposure enforcement: `scripts/lint_secret_exposure.py`
- [x] Wired the new gates into `scripts/pre_deploy_gate.sh`
- [x] Archived root historical reports and phase summaries into `docs/archive/root_history/`
- [x] Bannered the highest-traffic stale completion docs under `docs/`, including verification and scoped-work records, so `MASTER_PLATFORM_CHECKLIST.md` is the only live ledger

### Phase 1
- [x] Removed `GEMINI_API_KEY` from template context
- [x] Replaced it with `AI_BACKEND_ENABLED`, `AI_PROVIDER_NAME`, and existing `AI_PERMISSIONS`
- [x] Added a regression test proving provider secrets do not render into `components/ai_copilot.html`
- [x] Added a secret exposure gate that blocks provider-secret identifiers in client assets and tracked config files
- [x] Removed unnecessary `csrf_exempt` from `apps/siteconfig/views_verify.py`
- [x] Removed `csrf_exempt` from `apps/api/views_v1.EnrollmentApplyView`; browser-facing POST aliases now require CSRF
- [x] Removed redundant GET-only `csrf_exempt` usage from CEDS, Ed-Fi, OneRoster, and selected SCIM/LTI discovery endpoints
- [x] Removed browser-facing `csrf_exempt` usage from self-service trial signup and brand import flows
- [x] Enforced a strict broad-exception baseline for the highest-risk files while remediation continues
- [x] Reduced `apps/portal/views_ai_copilot.py` broad exception usage from 17 to 3, reduced `apps/api/views_v1.py` from 18 to 6, reduced `apps/siteconfig/context_processors.py` from 23 to 22, and corrected the gate to count `except Exception as e` forms too
- [ ] Replace or narrow the remaining `csrf_exempt` usage, which is now concentrated in SAML, SCIM mutation/detail flows, LTI callbacks, GraphQL, and webhook endpoints
- [ ] Replace broad `except Exception` in the highest-risk files until the baseline can ratchet downward

### Phase 2
- [x] Turned the bounded-context shell apps into real import surfaces for brand, runtime, plans, registries, marketplace, and policies
- [x] Added a CI gate blocking new imports from legacy `apps.siteconfig.models_*` domain wrappers
- [x] Expanded the bounded-context surfaces and cut live app/test imports over from direct `apps.siteconfig.models*` usage to brand, runtime, plans, registries, marketplace, and policies surfaces
- [x] Deleted six unused legacy `apps/siteconfig/models_*` compatibility shims after confirming no app code still imported them
- [ ] Move database ownership out of `siteconfig` with state-safe migrations and delete the remaining legacy ownership paths

### Phase 3
- [x] Fixed runtime metadata to use real bounded-context pack models instead of the broken legacy `Blueprint` import
- [x] Extended runtime metadata output with workflow pack, dashboard pack, and policy bundle catalogs
- [x] Extended package preview/apply to register metadata dependencies for dashboards, templates, APIs, workflows, policies, and package ownership when payload fields are declared
- [x] Added runtime lineage registries for dashboards, workflows, policies, APIs, and templates plus package rollout/rollback metadata in the catalog
- [x] Added rollback blast radius summaries to package validation, preview, apply, rollback, and catalog registry output
- [ ] Extend automatic lineage registration to more runtime API/template call sites beyond package-driven declarations

### Phase 4
- [x] Expanded `apps.packages.engine` to return structured validation, compatibility, dependency, impact, rollback, and promotion data
- [x] Added persisted package dependency, impact, apply-stage, and reconciliation metadata
- [x] Added package registry visibility for active installs, rollback events, and rollback blast radius
- [x] Added package tests for validation, incompatibility, promotion, rollback, and tenant scoping
- [ ] Wire staged rollout and promotion into UI and operator workflows

### Phase 5
- [x] Expanded `SetupProgress` to persist step state, recommendations, role previews, launch checklist, blockers, health score, and readiness
- [x] Added `apps.setup_studio.services.get_setup_studio_payload`
- [x] Re-backed guided onboarding to use `setup_studio` instead of ad hoc customer-success heuristics
- [x] Updated the Setup Studio UI to show blockers, role previews, and recommendations
- [x] Changed Setup Studio’s dominant next action to follow ranked recommendations/blockers instead of blindly choosing the first incomplete step
- [x] Added a live preview workspace, ranked blueprint recommendations, and explicit launch-orchestration stages to Setup Studio
- [ ] Continue expanding Setup Studio with deeper preview fidelity and operator-triggered launch execution

### Phase 8
- [x] Unified backend next-action ranking so the recommendation service and contextual action registry now prioritize the same setup, workflow, finance, and academic actions
- [ ] Split the backend experience into role-native default homes with one dominant purpose per dashboard instead of relying on one overloaded super-dashboard
- [ ] Replace generic quick actions with a contextual next-action engine that is role-aware, state-aware, urgency-aware, and recommendation-first
- [ ] Finish Setup Studio as a true launch product with left-rail progress/health, centered guided tasks, right-rail live preview, and preview-by-role before launch
- [ ] Enforce page archetypes across the platform: role home, setup studio, decision console, workbench, catalog, and record detail
- [ ] Upgrade marketplace UX with richer cards, verification/compatibility trust signals, preview-before-install, and clearer rollback expectations
- [ ] Upgrade marketing surfaces such as migrate, setup simulator, compare, developer, and marketplace pages with proof visuals, replacement messaging, ecosystem framing, and conversion-grade storytelling
- [ ] Promote command palette and search to primary workflow navigation, with the sidebar reduced to orientation and fallback navigation

### Phase 6
- [x] Removed tracked malformed/backed-up SQLite debris from the repo
- [x] Moved tracked root SQLite snapshots to `artifacts/db_snapshots/` and moved tracked runtime/security artifacts under `artifacts/`
- [x] Removed active `gilead` references from runtime code paths in `apps/` and `config/`
- [x] Finished tracked-root cleanup for historical reports, duplicate phase summaries, generated artifacts, and root database snapshots

## Must close today

- Broad exception volume is still high; the corrected high-risk baseline is enforced, but counts in `accounts/views.py`, `api/views_v1.py`, `schools/middleware.py`, `schools/super_views.py`, and `siteconfig/context_processors.py` still need to be driven down.
- `siteconfig` remains the dominant domain gravity well; import surfaces now exist, but ownership migrations have not landed yet.
- Metadata lineage now covers registered dashboards, workflows, policies, APIs, templates, package ownership, and rollback blast radius, but more runtime call sites still need automatic registration.
- CSRF and raw SQL are now inventoried and locked, but most legacy entries are still present.
- Repo de-branding is still incomplete; `gilead` references remain outside approved archive paths.
- UI/UX closure is still incomplete: dashboard intent needs role-native homes, Setup Studio still lacks live preview and launch orchestration, quick actions are not yet a contextual action engine, marketplace install UX is still too utility-first, and marketing pages still need proof-rich product storytelling.

## Historical-doc banner

Any document that still claims "all phases complete", "no backlog remains", or equivalent is **historical-only** until its claims are rechecked and copied into this file. Start with:

- `docs/WHERE_TO_SEE_MASTER_CHECKLIST_AFTER_DEPLOY.md`
- `docs/VERIFICATION_CHECKLIST.md`
- `docs/architecture/SCOPED_WORK_VERIFICATION.md`
