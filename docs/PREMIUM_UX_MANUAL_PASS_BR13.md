# Premium UX manual pass (BR-13)

## Repo program checklist — machine-verified (closure)

These items are **closed for the repository program** when the commands below pass on a migrated gate database. Evidence is recorded in [RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md) (wave B2 / final sweep).

- [x] **`data-page-archetype` / shell contract on audited surfaces** — `python scripts/verify_ux_completion.py` (with `DJANGO_UX_AUDIT_USE_GATE_DB=1` and `DJANGO_TEST_DB_FILE` set after `migrate_gate_test_db.py`), bundled inside `python scripts/verify_operator_phase10_11_e2e.py`; plus `python scripts/audit_phase3_phase4_surfaces.py` for template inventory.
- [x] **Studio OS / dashboard / setup product markers** — same `verify_ux_completion.py` checks (`dashboard.*`, `setup.*`, required private templates).
- [x] **No broken placeholder copy on proof / marketing / marketplace surfaces** — static template reads + route marker checks in `verify_ux_completion.py` and Phase 10/11 pytest bundle.
- [x] **Focus-visible / keyboard / a11y baseline** — Phase 2 design-system gate `python scripts/verify_design_system_phase2.py`; Phase H static slice inside `python scripts/verify_phases_3_11_gates.py`; north-star a11y lint where wired in that bundle.
- [x] **Responsive / layout contracts (automated surrogate)** — `platform-fluid-everywhere` and related checks in `verify_phases_3_11_gates.py` where present; dashboard density `python scripts/verify_phase8_dashboard_density.py`.
- [x] **Low-click / role-home spine** — `apps/dashboard/tests/test_role_home_engine.py`; `apps/schools/tests/test_primary_control_plane_nav.py`; `apps/schools/tests/test_control_plane_nav_roles.py`; `verify_ux_completion.py` role-home contract.

**Last full chain PASS:** 2026-03-25 — `verify_operator_phase10_11_e2e.py --ux-db-file .django_test_dbs/rerun_closure_20260325.sqlite3` (51 tests + UX audit **OK**).

## Shell architecture matrix — seven-step pass (P4 evidence)

**Recorded:** **2026-03-28**. **Host:** `127.0.0.1` (local dev). **Automation:** `python scripts/verify_shell_architecture_matrix.py` **PASS** same session. **SOT:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) epic **P4** + Premium maturity **Shell triad** row.

| Step | Surface | Result |
|------|---------|--------|
| 1 | Marketing | Loaded public marketing path; single marketing bundle (no tenant/control-plane CSS in base). |
| 2 | Control plane | `/super/` — no `marketing-shell.css` / `tokens-marketing.css` in template contract (static verifier). |
| 3 | Tenant portal | `portal_base` path — `data-surface="tenant"` + design-system CSS; no control-plane primary nav CSS. |
| 4 | Studio | Studio extends tenant spine per matrix / verifier (no second control-plane header stack in contract). |
| 5 | Admin | Manager/tenant admin: Unfold + admin nav bridge contract unchanged. |
| 6 | Automation | `verify_shell_architecture_matrix.py` executed locally **PASS**. |
| 7 | Duplicate bundles | No duplicate shell CSS tokens in audited bases (verifier + manual spot-check). |

### Staging / production hostname matrix (reference pattern — 2026-03-28)

Use **your** live staging URLs at release time; this table records the **documented** RunMyCampus / Render patterns so P4 evidence is not only localhost.

| Step | Surface | Example hostname (from repo ops docs) | Notes |
|------|---------|----------------------------------------|--------|
| 1 | Marketing / public login | `https://school-management-system-2kzk.onrender.com` | [DEPLOY_RENDER.md](DEPLOY_RENDER.md) — default Render service URL as public/marketing-style host |
| 2 | Control plane | `https://manager.runmycampus.com` + path `/super/` | [RENDER_SHELL_AFTER_DEPLOY.md](RENDER_SHELL_AFTER_DEPLOY.md) — manager custom domain required for `/super/` / `/studio/` on real deploys |
| 3 | Tenant portal | `https://<school-slug>.runmycampus.com` | Same doc — school subdomain on base domain |
| 3b | Tenant (Render subdomain pattern) | `https://<school-slug>.school-management-system-2kzk.onrender.com` | [RENDER_SSL_AND_TENANT_URLS.md](RENDER_SSL_AND_TENANT_URLS.md) — tenant host pattern |
| 4 | Studio | `https://manager.runmycampus.com/studio/` | Manager host (not bare `*.onrender.com` without routing) per [RENDER_SHELL_AFTER_DEPLOY.md](RENDER_SHELL_AFTER_DEPLOY.md) |
| 5 | Admin | Same host as step 2 or 3 + `/admin/` | Tenant vs manager Unfold per matrix |
| 6 | Automation | CI + local `verify_shell_architecture_matrix.py` | [smoke-light.yml](../.github/workflows/smoke-light.yml) runs `test_tenant_settings_lint` bundle |
| 7 | Duplicate bundles | Same checks as dev table | Repeat in browser Network tab on **each** host above |

**Operator action:** Before a **production** tag, replace or extend this table with the **actual** staging hostnames in use and initial the row in the release ticket.

**Append-only evidence for live hosts:** add a row to [SHELL_ARCHITECTURE_MATRIX.md](SHELL_ARCHITECTURE_MATRIX.md) **Operator sign-off log** when steps 1–7 are run on staging/production URLs (keeps P4 proof in one canonical table).

## Touring (product surfaces)

- **Super (control plane):** **Page tour** on `/super/trust/`, `/super/migration/csv-diff/`, `/super/tools/governed-query/` → `siteconfig:tour_steps_api?context=super_trust|super_migration|super_governed` + `static/js/control-plane-tour.js`.
- **Tenant backend:** `tour_steps_api?context=backend_dashboard` + first-login tour (unchanged).
- **Setup Studio** linked from Configuration Control Center outcome banner (`console_domains_hub`).

## Production release sign-off (organizational — not a repo checkbox)

Before tagging a **production** release, product and design record **date + initials** here (or in your release ticket). This is **outside** the autonomous repo gate program and does not block merge when the checklist above is green.

```
Release tag: _______________
Product initials: _______________
Design initials: _______________
```

**Note:** CI and the scripts above do not replace a human walkthrough of live styling and copy on a staging host; they **do** close the **in-repo** BR-13 bar for merge and autonomous execution prompts.
