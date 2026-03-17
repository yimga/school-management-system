# Admin → Super migration roadmap

Logical order so we can start the work slice by slice. Each phase is implementable without blocking the next. Reference: [ADMIN_VS_SUPER_RESPONSIBILITY_MATRIX.md](ADMIN_VS_SUPER_RESPONSIBILITY_MATRIX.md), [ADMIN_SUPER_SINGLE_ENTRY_AND_MARKETING_PRODUCT_PAGE.md](ADMIN_SUPER_SINGLE_ENTRY_AND_MARKETING_PRODUCT_PAGE.md).

**Status:** Phases 1–8 implemented per [RUNBOOK_ADMIN_TO_SUPER_MIGRATION.md](RUNBOOK_ADMIN_TO_SUPER_MIGRATION.md). Config hub at `/super/config/`; optional list views for incidents, billing accounts, and migration runs added.

---

## Phase 0 — Already in super (no work)

These already have super views; admin is only for raw CRUD fallback.

| Area | Super URL/name | Admin equivalent |
|------|----------------|-------------------|
| System config (bounded) | `/siteconfig/console/` — System config | siteconfig console domains |
| Registries | `/super/registries/` | registries.* |
| Blueprints | `/super/blueprints/` | policies.BlueprintPack, etc. |
| Policies | `/super/policies/` | policies.* (platform) |
| Workflow/Dashboard packs | `/super/workflow-packs/`, `/super/dashboard-packs/` | catalog models |
| Migration | `/super/migration/` | automation.MigrationRun, MigrationProfile |
| Marketplace | `/super/marketplace/*` | marketplace.* |
| Billing (dashboard) | `/super/billing/` | billing.* (raw in admin) |
| Schools (high level) | `/super/` dashboard, tenant-health, create wizard | schools.School, etc. |

---

## Phase 1 — Configuration hub (first slice to implement)

**Goal:** One landing page in super for “configuration”. Configuration Engine link points here instead of directly to admin.

- [x] Add view `super_config_hub` (e.g. in `apps/schools/super_views.py` or `apps/siteconfig/views_super_config.py`).
- [x] Add URL `super:config_hub` → e.g. `/super/config/`.
- [x] Template: control_plane_base, card grid or list of sections:
  - **Site settings (platform)** → link to Phase 2 (or “Coming soon”).
  - **Regions & grading** → link to Phase 3 (or admin for now).
  - **Plans & addons** → link to Phase 4 (or admin for now).
  - **Feature toggles** → link to Phase 5 (or admin for now).
  - **AI / model registry** → link to Phase 6 (or admin for now).
  - **System config (bounded)** → existing `siteconfig:console_domains_hub`.
  - **Advanced backoffice** → `admin:index` (full Django admin).
- [ ] In `control_plane_nav.py`, change “Configuration Engine” from `admin:index` to `super:config_hub`.

**Outcome:** Clicking “Configuration Engine” opens the hub in super; admin still reachable via “Advanced backoffice”. No models migrated yet.

---

## Phase 2 — Site settings (platform)

**Goal:** List and edit platform-level SiteSettings (or default site) in super.

- [ ] Add `super_site_settings_list` (and optionally single default “edit” if platform has one site).
- [x] URL e.g. `/super/config/site-settings/` (list or single form).
- [x] Reuse existing SiteSettings form / ModelForm; render in control_plane_base.
- [ ] Add “Site settings” card/link on config hub pointing here.

**Admin:** Can keep `siteconfig.SiteSettings` in admin for raw edit; super becomes the preferred path.

---

## Phase 3 — Regions & grading (platform)

**Goal:** List (and optionally edit) RegionConfig, GradingScaleConfig in super.

- [x] Add `/super/config/regions/` list view.
- [x] Add `/super/config/grading/` list view (or combined “Regions & grading” page).
- [x] Links from config hub.

**Admin:** regionconfig, GradingScaleConfig remain in admin as fallback.

---

## Phase 4 — Plans & addons (platform)

**Goal:** List Plan, PlanAddon (read-only or simple edit) in super.

- [x] Add `/super/config/plans/` list view.
- [x] Link from config hub.

---

## Phase 5 — Feature toggles & flags (platform)

**Goal:** List/edit FeatureToggleDefinition, FeatureToggleState (or key flags) in super.

- [x] Add `/super/config/feature-toggles/` (or reuse existing feature-control UI if it’s manager-scoped).
- [ ] Link from config hub.

---

## Phase 6 — AI / model registry (platform)

**Goal:** List AIModelRegistry, RegionalAIConfig in super.

- [x] Add `/super/config/ai-models/` (or link to existing super AI view if it covers this).
- [x] Link from config hub.

---

## Phase 7 — Schools (platform) list

**Goal:** Explicit school list in super (dashboard/tenant-health already show schools; this is a dedicated list if needed).

- [x] Add `/super/schools/` list view (paginated, filter by status/region).
- [x] Optional: link to admin changelist for School for “full backoffice” for that model.

---

## Phase 8 — Observability / Billing / Automation (optional)

**Goal:** Either add super list views for key models (e.g. PlatformIncident, BillingAccount, MigrationRun) or rely on “Advanced backoffice” + existing super dashboards.

- [x] Decide per area: super list view vs admin link from hub.
- [x] Document in config hub which admin sections map to which super area. Implemented: `/super/incidents/`, `/super/billing-accounts/`, `/super/migration-runs/` list views; linked from config hub operational section.

---

## Implementation notes

- **URL namespace:** All new super config views live under `super:` (e.g. `super:config_hub`, `super:site_settings_list`). Add routes in `apps/schools/super_urls.py` under a `config/` prefix.
- **Templates:** Extend `control_plane_base.html`; use existing card/table/form patterns from other super pages.
- **Permissions:** Reuse `require_super_access_with_host`; only superuser/staff on manager host.
- **Forms:** Reuse ModelForms or form logic from admin where possible; only the view and template change.

---

## Order to start

1. **Phase 1** — Implement config hub and switch nav “Configuration Engine” to it. No model migration; immediate single entry in super for configuration.
2. **Phase 2** — Site settings in super; add link from hub.
3. Then Phase 3 → 4 → 5 → 6 as needed; Phase 7 and 8 can run in parallel or later.
