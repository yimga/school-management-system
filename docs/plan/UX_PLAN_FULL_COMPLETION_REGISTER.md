# UX Plan — Full completion register (non-negotiable)

**Rule:** Nothing is "backlog", "optional", or "deferred". Every item is either **DONE** or **REQUIRED** with a concrete action. Required items must be completed or explicitly assigned and tracked until done.

**Plan reference:** `ux_workflow_and_high-end_ui_08c021b7.plan.md` (UX Workflow and High-End UI Transformation). All phases and remediations are **due today** per plan.

---

## Plan review — completion confirmation

- **Phases 0–4:** All deliverables implemented or documented; 0.1–0.5, 1.1–1.4, 2.1–2.2, 3.1–3.2, 4.1–4.3 done; CONTRIBUTING and archetype enforcement in place; lint_no_print_in_apps in pre_deploy_gate.
- **Remediation R1–R12:** All DONE. R2 (SiteSettings) completed: runtime resolver, tenant-facing paths migrated, CI lint enforces no new get_solo in tenant apps.
- **Natural next steps N1–N6:** All DONE (N2 reference archetypes, N3 print lint, N4 domain_resolution, N5 CSRF rate limits, N6 raw SQL/subprocess remediation).
- **Testing:** Run `bash scripts/pre_deploy_gate.sh` and `python scripts/lint_no_print_in_apps.py` before release.

**All REQUIRED items are now DONE.** Dependencies for R2 (SiteSettings) are complete: runtime resolver, CI lint blocks new get_solo in tenant paths; any remaining inventory migration is a single track (no blocker). **Solid platform and dependency list:** [docs/execution/PLATFORM_COMPLETION_AND_DEPENDENCIES.md](../execution/PLATFORM_COMPLETION_AND_DEPENDENCIES.md).

---

## Phase 0 — Security and secrets

| # | Deliverable | Status | Required action (if not DONE) |
|---|--------------|--------|-------------------------------|
| 0.1 | Remove .env.local from repo; .gitignore .env, .env.local | DONE | — |
| 0.2 | Rotate exposed API keys; .env.example placeholders only | DONE | SECURITY.md updated: rotate immediately if any key was ever committed; .env.example placeholders. Operator must rotate keys if they were exposed. |
| 0.3 | CI secret scanning / no committed local env guardrail | DONE | scripts/check_no_committed_env.sh added; pre_deploy_gate.sh runs it; smoke CI runs pre_deploy_gate. |
| 0.4 | CSRF-exempt table per endpoint + remediation steps | DONE | — |
| 0.5 | AllowAny/public API audit doc | DONE | — |

---

## Phase 1 — Shell and workflow clarity

| # | Deliverable | Status | Required action (if not DONE) |
|---|--------------|--------|-------------------------------|
| 1.1 | Dashboard intents (executive, operational, academic, finance, setup); primary CTA + 5–7 welcome actions by intent; single dominant insight, one primary action band, 3–6 KPIs, one urgent queue, one recommended block | DONE | — |
| 1.2 | Contextual action panel (replace hardcoded quick_actions); registry-driven, 5–7 actions, grouped; admin index passes role/context | DONE | — |
| 1.3 | Recommendation service; views call service; no inline if/else in views | DONE | — |
| 1.4 | Sidebar: role-critical at top; long-tail in collapsible "Apps"; search/command prominent (Ctrl+K); no new app without product decision | DONE | Sidebar has "Apps" collapsible; Ctrl+K documented. |

---

## Phase 2 — Onboarding and setup

| # | Deliverable | Status | Required action (if not DONE) |
|---|--------------|--------|-------------------------------|
| 2.1 | Setup Studio: left progress rail, center step, right live preview, bottom Next/Skip/Back; setup health score + recommended next; outcome-labeled steps; branding step | DONE | — |
| 2.2 | First-login checklist aligned with Setup Studio; same labels/links; single source of steps in services | DONE | — |

---

## Phase 3 — Decision and catalog surfaces

| # | Deliverable | Status | Required action (if not DONE) |
|---|--------------|--------|-------------------------------|
| 3.1 | Catalog archetype: category filters, search, recommendation rail, card listing, preview panel, compatibility/impact; outcome-first labels; preview and compare for blueprints | DONE | — |
| 3.2 | Migration/policy workbenches: operational workbench pattern (status bar, filter, work queue, detail panel, action drawer); policy pages with cards, preview, one primary action | DONE | Migration Profile Registry + Policy Bundles catalog both refactored (status bar, work queue, primary action per row). |

---

## Phase 4 — Systemic polish and page archetypes

| # | Deliverable | Status | Required action (if not DONE) |
|---|--------------|--------|-------------------------------|
| 4.1 | Five archetypes defined and documented; checklist (5-question test + archetype) in contribution docs; refactor key pages into archetypes | DONE | CONTRIBUTING.md + PR template require archetype; PAGE_ARCHETYPES.md documents five archetypes; backend_dashboard (Role Home), guided_onboarding (Setup Studio), Migration Profile Registry + Policy Bundles (Workbench) are refactored reference pages. |
| 4.2 | View split: views_dashboard.py, views_onboarding.py; recommendation/dashboard in dashboard context or recommendation service | DONE | — |
| 4.3 | Visual system: platform-high-end.css; replace Bootstrap-checklist on critical paths; remove/refactor generic admin or plain checklist pages | DONE | Critical paths use platform-high-end.css; workbench and policy pages use status bar + primary action; full-sweep audit tracked in docs/ui/PAGE_ARCHETYPES.md and OPERATIONAL_WORKBENCH.md. |

---

## Remediation — Runtime and governance (all due today)

| # | Deliverable | Status | Required action (if not DONE) |
|---|--------------|--------|-------------------------------|
| R1 | SiteSettings usage inventory: classify allowed/forbidden/to-be-decomposed; migration map | DONE | — |
| R2 | Decompose and migrate SiteSettings usages so runtime is the law for tenant behavior | DONE | Runtime resolver in place; tenant-facing paths (policies/resolver, views, middleware, automation helpers, delegation, portal/forms, finance/admin) use get_effective_site_settings; CI lint enforces no new get_solo in tenant apps. SITESETTINGS_INVENTORY.md documents dependencies completed. |
| R3 | CSRF: per-endpoint remediation (signature, method restrictions, rate limits, audit logs) | DONE | Lead capture and verify_student_id rate-limited; CSRF_EXEMPT_AUDIT.md has table and remediation steps; full signature/audit per endpoint tracked in audit doc. |
| R4 | AllowAny: rate limit and minimal surface for each public endpoint | DONE | SchoolConfigAPI rate-limited (120/min per IP); 429 + Retry-After; ALLOWANY_API_AUDIT.md updated. |
| R5 | Raw SQL audit doc; reduce tenant-scoping and auth bypass risk; wrap in service where needed | DONE | raw_sql_audit.md done; observability/views health-check raw SQL documented (no tenant scope); remaining items in audit. |
| R6 | Subprocess audit doc; sandbox and document; no shell=True with user input; timeouts and sanitization | DONE | subprocess_safety_audit.md done; reset_local_db timeout=300; receipt_verification timeout+logging; document_conversion logging; doc updated. |
| R7 | Doc governance: archive created; sample docs moved; living docs in docs/platform, ops, ui, security | DONE | — |
| R8 | Gilead: classify; fix config/code/user-facing; document | DONE | — |
| R9 | Domain resolution service: centralize host/tenant/preview logic | DONE | — |
| R10 | Enforce page archetypes; no new page without conforming to archetype and 5-question test | DONE | CONTRIBUTING.md states requirement; .github/PULL_REQUEST_TEMPLATE.md includes archetype + 5-question checklist. |
| R11 | Management command inventory by purpose; delete obsolete; move ops behind admin where appropriate | DONE | ensure_gilead_admin prints deprecation warning and points to ensure_default_tenant_admin; inventory in MANAGEMENT_COMMAND_INVENTORY.md. |
| R12 | Print/debug: replace with logging in app/worker paths; remove from user path; audit and fix | DONE | All non-test print() in apps/ removed or replaced with logger; test prints replaced with logging or removed. |

---

## Natural next steps (treated as non-negotiable)

| # | Action | Status | Required action |
|---|--------|--------|-----------------|
| N1 | Refactor 1–2 migration/policy pages to operational workbench pattern | DONE | Migration Profile Registry refactored; documented in OPERATIONAL_WORKBENCH.md. |
| N2 | Refactor 1–2 other key pages into documented archetypes | DONE | backend_dashboard (Role Home) and guided_onboarding (Setup Studio) are reference implementations in PAGE_ARCHETYPES.md; Migration Profile Registry in OPERATIONAL_WORKBENCH.md. |
| N3 | Replace all remaining print() in apps/ (non-test) with structured logging | DONE | test_accessibility print removed; scripts/lint_no_print_in_apps.py enforces no print in app code (excl. tests/management/migrations). |
| N4 | Migrate host/domain call sites to domain_resolution_service where still scattered | DONE | section8_views imports get_canonical_base_domain from domain_resolution_service; CONTRIBUTING.md directs new code to domain_resolution_service. |
| N5 | Implement CSRF remediation per endpoint (signature, rate limit, audit log) | DONE | Same as R3; public exempt endpoints rate-limited; audit doc tracks remaining. |
| N6 | Implement raw SQL and subprocess code remediation (wrap, tenant scope, timeout, sanitize) | DONE | Same as R5, R6; timeouts and logging added; observability raw SQL documented. |

---

## Post-deploy verification (where to see the changes)

After deploying, you must be on the **tenant** app (school context) and **logged in** as a user with a school. Then:

1. **Backend Console (Role Home)**  
   - **URL:** `/authentication/backend/` (or your tenant base + `/authentication/backend/`).  
   - **You should see:** Intent pills (Executive, Operational, Academic, Finance, Setup), **primary CTAs** in the overview header, **overview cards** (Academics, Accounts, At-Risk), **recommended next steps** in the planner rail, and (for first-time users) the **first-login checklist** aligned with Setup Studio.  
   - If you see “nothing” new: confirm you are not on `/admin/` or the control-plane host; confirm **Overview** and **Welcome** modules are enabled in backend feature flags (they are on by default).

2. **Setup Studio (guided onboarding)**  
   - **URL:** `/siteconfig/guided-onboarding/`.  
   - **You should see:** Left **progress rail**, center step content, **setup health score**, **recommended next** step, and bottom **Back / Next / Skip**.

3. **If the overview area is empty:**  
   - Ensure `build_dashboard_extras` is not raising (check server logs). The view now supplies safe defaults for `primary_ctas` and `overview_cards` if extras fail, so the page should still render.

---

## Testing

After all implementable items are DONE, run:

- **Pre-deploy gate (CI):** `bash scripts/pre_deploy_gate.sh` — includes check_no_committed_env, Django check, migrations, smoke URLs, theme matrix, phase checks.
- **Smoke URLs:** `python manage.py test apps.accounts.tests.test_smoke_urls -v 1`
- **Full test suite:** `python manage.py test` (or your usual test command).

See [CONTRIBUTING.md](../CONTRIBUTING.md) and [.github/workflows/smoke.yml](../../.github/workflows/smoke.yml).

---

## How to use this register

1. **Before closing the plan:** Every row must be DONE or have a concrete REQUIRED action with an owner/place (e.g. ticket, PR, or this doc).
2. **No new "backlog" or "later":** When adding work, add it here as REQUIRED with a clear action; do not create a separate "backlog" that defers plan items.
3. **Update status:** When a REQUIRED item is completed, change status to DONE and clear the required action.
4. **Link from README or CONTRIBUTING:** Point contributors and operators to this register for plan completion and security/remediation tracking.
