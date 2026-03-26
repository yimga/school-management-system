# Page Archetypes (platform shell law)

**Rule:** Every major page must fit one archetype. Enforced via `data-page-archetype` and this doc.

| Archetype | Purpose | Examples |
|-----------|---------|----------|
| **role-home** | One clear intent; key metrics; urgent queue; next-best action | Backend dashboard, portal home |
| **setup-studio** | Guided setup; progress rail; live preview; launch checklist | Guided onboarding; Create School wizard (`setup-studio` marker) |
| **setup-flow** | Linear or staged operator steps (non-portal) | Advancement phase placeholders, narrow config wizards |
| **studio-workspace** | Studio OS shell outside Control mode; mode rail + canvas | `shell_main_content.html` when not `current_mode == control` (manager Studio) |
| **decision-console** | Compare, audit, rollback; operator outcomes; Control Studio | `/studio/control/`, Configuration Control Center, feature control, super `/super/config/*` grids with operator strip |
| **operational-workbench** | Operator list / queue / triage (control plane) | Schools list, platform incidents, legacy SIS preview |
| **workbench** | Operational list/detail; bulk actions; filters | Student list, finance, admissions (tenant / school workflows) |
| **catalog** | Browse, search, install; trust markers; compatibility | Tenant app catalog, control-plane app catalog, blueprint marketplace |
| **record-detail** | Single entity; tabs; related; actions | School 360, student detail |

**Enforcement:** Key templates set `data-page-archetype="<name>"` on the main content container. See `backend_dashboard.html`, `guided_onboarding.html`, `console_domains_hub.html`, `tenant_app_catalog.html`, `app_catalog.html`, `studio_os/partials/shell_main_content.html` (manager Studio: `studio-workspace` / `decision-console` by mode).

**Shell default (tenant portal):** `templates/portal_base.html` sets `data-page-archetype` on `.page-wrap` via `{% block page_archetype %}operational-workbench{% endblock %}`. Override in a child with `{% block page_archetype %}decision-console{% endblock %}` (for example `siteconfig/feature_control_panel.html`, `console_domains_hub.html`). **Django admin (Unfold):** `templates/admin/base.html` sets `data-page-archetype="decision-console"` on `#content` for every authenticated model surface; tenant hosts also get `admin/includes/tenant_admin_decision_banner.html`. **Outcome deck (every app/model):** `apps/siteconfig/admin_model_outcomes.py` maps `app_label` (and optional model overrides) to one of the nine Phase 3 outcome groups; `config.admin.BaseRunMyCampusAdminSite.each_context` injects `admin_outcome_deck`, rendered by `admin/includes/admin_operator_outcome_deck.html` above changelist/form content. **Manager control plane:** `control_plane_base.html` sets `data-page-archetype` on `#cp-main-content` (default `decision-console`, overridable via `{% block cp_page_archetype %}`).

**Inventory:** `python scripts/audit_phase3_phase4_surfaces.py --write docs/phase_audit/PHASE_3_4_SURFACE_SCAN.md`
