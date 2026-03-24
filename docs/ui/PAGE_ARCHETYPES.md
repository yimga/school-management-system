# Page Archetypes (9.5/10 Platform Law)

**Rule:** Every major page must fit one archetype. Enforced via `data-page-archetype` and this doc.

| Archetype | Purpose | Examples |
|-----------|---------|----------|
| **role-home** | One clear intent; key metrics; urgent queue; next-best action | Backend dashboard, portal home |
| **setup-studio** | Guided setup; progress rail; live preview; launch checklist | Guided onboarding |
| **decision-console** | Compare, audit, rollback; operator outcomes | Configuration Control Center hub, policy diff |
| **workbench** | Operational list/detail; bulk actions; filters | Student list, finance, admissions |
| **catalog** | Browse, search, install; trust markers; compatibility | Tenant app catalog, control-plane app catalog, blueprint marketplace |
| **record-detail** | Single entity; tabs; related; actions | School 360, student detail |

**Enforcement:** Key templates set `data-page-archetype="<name>"` on the main content container. See `backend_dashboard.html`, `guided_onboarding.html`, `console_domains_hub.html`, `tenant_app_catalog.html`, `app_catalog.html`.
