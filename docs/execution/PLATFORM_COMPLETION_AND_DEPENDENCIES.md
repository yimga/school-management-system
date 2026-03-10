# Platform completion and dependencies — solid, non-negotiable

**Purpose:** One place that confirms all plan dependencies are satisfied, the platform is solid, and the only remaining work is a single tracked migration path. Nothing is deferred by dependency; everything that can be enforced is enforced in CI.

---

## 1. Plan status (both plans complete)

| Plan | Checklist | Status |
|------|-----------|--------|
| **Metadata-driven platform** (Codex, Gap Closure) | [docs/execution/NEXT_PHASE_BACKLOG.md](NEXT_PHASE_BACKLOG.md) | 100% [x]; all workstreams A–I, H1–H5 done. |
| **UX Workflow and High-End UI** | [docs/plan/UX_PLAN_FULL_COMPLETION_REGISTER.md](../plan/UX_PLAN_FULL_COMPLETION_REGISTER.md) | All phases 0–4 and remediations R1–R12, N1–N6 done. |

**No REQUIRED item is blocked by a missing dependency.** The only remaining track is incremental migration of existing SiteSettings usages per inventory (see §3).

---

## 2. Dependencies — all satisfied

For the platform to stay **solid** and **non-negotiable**, the following are in place:

| Dependency | Where | Status |
|------------|--------|--------|
| **No get_solo in tenant paths** | `scripts/lint_tenant_settings.py --check-get-solo-only` in pre_deploy_gate | CI fails if violated; allowlist documented in script. |
| **Runtime resolver for tenant config** | `apps/platform_runtime/helpers.get_effective_site_settings(request=request)` | Canonical path for tenant-facing code. |
| **SiteSettings inventory and migration map** | [docs/security/SITESETTINGS_INVENTORY.md](../security/SITESETTINGS_INVENTORY.md) | Classification and migration map; per-usage migration is the single follow-on track. |
| **No print() in application code** | `scripts/lint_no_print_in_apps.py` in pre_deploy_gate | CI fails if print in apps/ (excl. tests, management, migrations). |
| **No committed secrets** | `scripts/check_no_committed_env.sh` in pre_deploy_gate | CI fails if .env / .env.local tracked. |
| **Django and migrations** | `manage.py check`, `makemigrations --check --dry-run` in pre_deploy_gate | No unapplied migrations; no system errors. |
| **Tenant model audit** | `manage.py audit_tenant_models --strict` in pre_deploy_gate | Tenant model consistency. |
| **Smoke and phase tests** | pre_deploy_gate runs smoke URLs, theme matrix, phase checks, workflow regression | Core flows and multi-tenant coverage. |
| **Page archetypes and 5-question test** | [CONTRIBUTING.md](../../CONTRIBUTING.md), [docs/ui/PAGE_ARCHETYPES.md](../ui/PAGE_ARCHETYPES.md) | New pages must conform; PR checklist. |
| **Security and runtime rules** | [SECURITY.md](../../SECURITY.md), CSRF/AllowAny/raw_sql/subprocess audits | Documented; rate limits and remediation done where required. |

**Conclusion:** All dependencies needed for a solid platform are satisfied. CI enforces the non-negotiables; no remaining plan item is blocked by a missing dependency.

---

## 3. Single remaining track (no blocker)

**Track:** Migrate remaining **Forbidden** and **To-be-decomposed** SiteSettings usages to runtime resolver or domain models, per [docs/security/SITESETTINGS_INVENTORY.md](../security/SITESETTINGS_INVENTORY.md).

- **Dependency:** None. Inventory exists; migration map exists; runtime resolver exists; CI already blocks *new* get_solo in tenant paths.
- **Work:** Per-file migration (use `get_effective_site_settings(request=request)` or the appropriate domain module). Add each completed file to the inventory table and mark classification as "Allowed" or remove the row.
- **Non-negotiable:** New tenant-facing code must not add get_solo (enforced by lint). Existing usages are migrated incrementally; the platform is already solid because no new violations can land.

---

## 4. Pre-deploy gate (single source of truth)

The following must pass before deploy. All are in **scripts/pre_deploy_gate.sh** unless noted.

1. **Secrets:** `scripts/check_no_committed_env.sh`
2. **Print:** `python scripts/lint_no_print_in_apps.py`
3. **Django:** `python manage.py check`
4. **Hardcoding:** `python scripts/check_no_hardcoding.py --allow-tests`
5. **SiteSettings in tenant paths:** `python scripts/lint_tenant_settings.py --check-get-solo-only`
6. **Codex (mega-files, broad except):** `scripts/lint_mega_files.py`; `scripts/lint_broad_except.py` (strict if CODEX_STRICT=1)
7. **Migrations:** `python manage.py makemigrations --check --dry-run`
8. **Tenant models:** `python manage.py audit_tenant_models --strict`
9. **Smoke URLs:** `python manage.py test apps.accounts.tests.test_smoke_urls -v 1`
10. **Theme matrix:** `python manage.py test apps.siteconfig.tests.test_theme_visibility_matrix -v 1`
11. **Phase checks:** `python manage.py test apps.siteconfig.tests.test_admin_ui_smoke apps.api.tests.test_dashboard_api_rbac -v 1`
12. **Core workflows:** `python manage.py test_core_workflows`
13. **Multi-tenant coverage:** `python manage.py test apps.siteconfig.tests.test_education_profile_engine apps.schools.tests.test_feature_registry apps.schools.tests.test_tenant_isolation_and_provisioning -v 1`
14. **Render/Procfile:** render.yaml and Procfile reference scripts/release/render_start_web.sh

Optional: `POWERHOUSE_WAVE0_STRICT=1` and `CODEX_STRICT=1` for stricter gates.

---

## 5. Definition of “solid platform”

The platform is **solid** when:

- Both plans (metadata-driven + UX) are complete per their checklists.
- All dependencies above are satisfied and enforced in CI.
- No new violations of get_solo in tenant paths, print in app code, or committed secrets can be merged.
- The only remaining work is the single track in §3 (inventory migration), which is not a dependency for anything else.

**Current status:** Solid. All dependencies are in place; pre_deploy_gate enforces them; remaining work is incremental migration from the inventory.
