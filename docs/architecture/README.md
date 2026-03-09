# RunMyCampus Architecture Docs

This folder contains architecture artifacts for the RunMyCampus platform. All core docs below align with **tenant_runtime**, **four planes** (control, tenant, marketing, public), **governed nav**, and **no hardcoding** (see [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md)).

**Completeness:** The core platform-aligned docs are complete. **Plan policy:** Everything is non-negotiable and due now; no deferred, optional, or backlog items (see [../PLAN_POLICY.md](../PLAN_POLICY.md)). Execution plans and gap ledgers track implementation status; all items are required.

---

## Core platform-aligned docs (index)

| Doc | Purpose |
|-----|---------|
| [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md) | Ten laws; override precedence; no hardcoding, runtime source of truth |
| [RUNTIME_COMPILATION_ORDER.md](RUNTIME_COMPILATION_ORDER.md) | How tenant_runtime is built (registry, policy, compliance) |
| [SHELL_IMPLEMENTATION.md](SHELL_IMPLEMENTATION.md) | Shell → template → data-surface mapping |
| [experience_shells.md](experience_shells.md) | Shell taxonomy and responsibilities |
| [sidebar_navigation_taxonomy.md](sidebar_navigation_taxonomy.md) | Nav grouping; data from request.tenant_runtime; control_plane_nav / portal_sidebar_items |
| [page_families.md](page_families.md) | Page family definitions and layout rules |
| [RUNTIME_MODULES_REFACTOR.md](RUNTIME_MODULES_REFACTOR.md) | Evals, Finance, Portal, runtime helpers |
| [PLATFORM_ENGINES.md](PLATFORM_ENGINES.md) | Migration, Marketplace, Observability, engines |
| [SEARCH_ARCHITECTURE.md](SEARCH_ARCHITECTURE.md) | Search and export from runtime/compliance |
| [DOCUMENT_LIFECYCLE_ARCHITECTURE.md](DOCUMENT_LIFECYCLE_ARCHITECTURE.md) | Retention, access from tenant_runtime.compliance |
| [REPORTING_BI_ARCHITECTURE.md](REPORTING_BI_ARCHITECTURE.md) | Reports and BI from runtime |
| [METADATA_CUSTOM_FIELDS_ARCHITECTURE.md](METADATA_CUSTOM_FIELDS_ARCHITECTURE.md) | Custom fields and metadata (Law 2, Law 4) |
| [LOCALIZATION_RTL_ARCHITECTURE.md](LOCALIZATION_RTL_ARCHITECTURE.md) | i18n, RTL, terminology (get_effective_locale, policy) |
| [DEVELOPER_PLATFORM_SDK_ARCHITECTURE.md](DEVELOPER_PLATFORM_SDK_ARCHITECTURE.md) | Developer portal and SDK (Law 6, Law 9) |
| [PERFORMANCE_BUDGETS_ARCHITECTURE.md](PERFORMANCE_BUDGETS_ARCHITECTURE.md) | Performance and cleanup targets |
| [CLEANUP_AND_DELETION_PLAN.md](CLEANUP_AND_DELETION_PLAN.md) | Dead templates, duplicate layout, legacy bypasses |
| [SECURITY_AND_PRODUCTION_MATURITY.md](SECURITY_AND_PRODUCTION_MATURITY.md) | Security context, compliance, production readiness |
| [CUSTOMER_SUCCESS_OPERATIONS.md](CUSTOMER_SUCCESS_OPERATIONS.md) | Customer success, onboarding, support |
| [no_hardcoding_checklist.md](no_hardcoding_checklist.md) | No-hardcoding checklist; CI gate |
| [PAGE_FAMILY_AND_SHELL_MAP.md](PAGE_FAMILY_AND_SHELL_MAP.md) | Page-by-page shell/family map |
| [SIDEBAR_NAV_SURGERY.md](SIDEBAR_NAV_SURGERY.md) | Sidebar nav changes and implementation |
| [SCOPED_WORK_NOT_DONE.md](SCOPED_WORK_NOT_DONE.md) | Scoped work: list, next steps, priority |
| [SCOPED_WORK_VERIFICATION.md](SCOPED_WORK_VERIFICATION.md) | Verification: all items done (code-verified) or required due now; nothing partial. See [../PLAN_POLICY.md](../PLAN_POLICY.md). |

---

## Blueprint E / generated artifacts

| File | Description |
|------|-------------|
| [apps.txt](apps.txt) | List of Django apps (from INSTALLED_APPS) |
| [urls.txt](urls.txt) | URL map (tenant and public roots) |
| [migrations.txt](migrations.txt) | Output of `python manage.py showmigrations` |
| [tenancy.md](tenancy.md) | Where tenant is set, schema switching, shared vs tenant tables, multi-DB routing |
| [policy_injection.md](policy_injection.md) | Where Policy Registry / tenant context is injected |
| [cache_keys.md](cache_keys.md) | Tenant-scoped cache keys (World Engine §8); audit table and intentional globals |
| [platform_north_star.md](platform_north_star.md) | North Star layers: Control plane, Tenant plane, Marketplace, Workflow, Metadata, Observability, Edge, Data plane, Compliance |
| [audit_branching_and_isolation.md](audit_branching_and_isolation.md) | C2/C3: Tenant branching audit and media/cache/tasks/search isolation |
| [dominance_sweep_checklist.md](dominance_sweep_checklist.md) | A3, A5, A6, A7 checklist and references |

See also: [../architecture_map.md](../architecture_map.md) (single map + Mermaid).

To regenerate artifacts (migrations, apps list, URLs) run from repo root:

```bash
bash scripts/regen_architecture_docs.sh
```

Or manually: `python manage.py showmigrations > docs/architecture/migrations.txt`

Optional: model graph with django-extensions + graphviz:  
`python manage.py graph_models -a -o docs/architecture/models.png`
