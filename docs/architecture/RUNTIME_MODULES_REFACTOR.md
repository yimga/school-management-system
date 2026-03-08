# Runtime-driven module refactor (Phase 2–3)

Admissions, Gradebook/Evals, Finance, Communication, and Portal must resolve behavior from `request.tenant_runtime` (or `build_tenant_runtime_for_tenant(tenant)` in jobs). No direct `SiteSettings.get_solo()` or `School.settings`/`School.features` for tenant-varying behavior.

## Admissions

- **Config:** `apps.siteconfig.admissions_services.get_admissions_config(runtime)`, `get_required_documents(runtime)`, `get_numbering_strategy(runtime)`, `get_admissions_workflow(runtime)`.
- **Views:** Pass `request.tenant_runtime` into services; provide `admissions_config` and `required_documents` in context where needed (e.g. backend_applicant_list).
- **Models:** `Applicant`/`StudentProfile` admission number and policy: use `_get_admissions_policy(school=None, policy=request.tenant_runtime.policy)` when called from views; model save() continues to use school and get_effective_policy(school).

## Gradebook / Evals

- **Helpers:** `apps.evals.runtime_helpers.get_effective_grading_policy(request)` — uses `request.tenant_runtime.policy` when available.
- **Views:** Use `get_effective_grading_policy(request)` and runtime for publish workflow and dashboard; no direct SiteSettings for grading scale or pass mark in tenant-facing views.
- **Reference:** apps/evals/runtime_gradebook.py, apps/evals/runtime_helpers.py.

## Finance

- **Helpers:** `apps.finance.runtime_helpers.get_finance_policy(request)` — uses `request.tenant_runtime.policy` when available.
- **Gateways:** `apps.finance.gateways.registry` prefers `policy=request.tenant_runtime.policy` in request context.
- **Views/services:** Use runtime policy for invoice timing, late fees, currency, and notifications; migrate SiteSettings usage to runtime/helpers over time.

## Communication and Portal

- **Helpers:** `apps.portal.runtime_helpers.get_portal_policy(request)` (terminology, labels).
- **Views:** Use `get_site_display_name(request)`, `get_effective_flags(request)`, and portal policy for tenant-facing copy and feature visibility.
- **Dashboard:** `apps.platform_runtime.helpers.get_effective_dashboard(request, role=...)` for role-based dashboard resolution.

## Enforcement

- Lint: `scripts/lint_tenant_settings.py` flags SiteSettings.get_solo() in tenant apps.
- Code review: new code in these modules must use runtime or helpers, not direct singleton reads.

## References

- [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md) (Law 2)
- [RUNTIME_COMPILATION_ORDER.md](RUNTIME_COMPILATION_ORDER.md)
- apps/platform_runtime/helpers.py (get_tenant_runtime, get_site_display_name, get_effective_flags, get_effective_dashboard)
- apps/siteconfig/admissions_services.py
- apps/evals/runtime_helpers.py
- apps/finance/runtime_helpers.py
- apps/portal/runtime_helpers.py
