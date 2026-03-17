# Runbook: Admin → Super migration (phase-by-phase)

**Purpose:** Execute the full migration so every platform-admin surface is reachable from super; Configuration Engine becomes a hub in super; nothing is missed. Follow phases in order. Each phase has explicit steps, file paths, and verification.

**References:** [ADMIN_TO_SUPER_MIGRATION_ROADMAP.md](ADMIN_TO_SUPER_MIGRATION_ROADMAP.md), [ADMIN_VS_SUPER_RESPONSIBILITY_MATRIX.md](ADMIN_VS_SUPER_RESPONSIBILITY_MATRIX.md), [ADMIN_SUPER_SINGLE_ENTRY_AND_MARKETING_PRODUCT_PAGE.md](ADMIN_SUPER_SINGLE_ENTRY_AND_MARKETING_PRODUCT_PAGE.md).

**Implementation status:** Phases 0–8 implemented. Config hub at `/super/config/`; nav "Configuration Engine" → config hub; Site settings (list + edit), Regions, Grading, Plans, Feature toggles, AI (ai_model_hub), System config, Advanced backoffice; Phase 8 operational links (Schools list, Pulse, Billing, Migration) on hub; Schools list at `/super/schools/` with pagination and filters. **Optional Phase 8 list views:** `/super/incidents/`, `/super/billing-accounts/`, `/super/migration-runs/` (PlatformIncident, BillingAccount, MigrationRun) with "Open in backoffice" and links to Pulse/Billing/Migration cloud. Run final verification checklist before release.

---

## Conventions

- **URL namespace:** All new routes live under `super:` (e.g. `super:config_hub`, `super:site_settings_list`). Base path prefix: `/super/` (from `config.manager_urls`).
- **Templates:** All new super config templates extend `control_plane_base.html`; use `{% block cp_title %}`, `{% block breadcrumbs %}`, `{% block cp_content %}`.
- **Views:** Use `require_super_access_with_host(view_func)` for every new view. Views can live in `apps/schools/super_views.py` or a dedicated module (e.g. `apps/schools/super_views_config.py`); if a new module is created, import it in `super_urls.py`.
- **Context:** Every template that needs dashboard link gets `dashboard_url = reverse("super:dashboard")` in the view context.
- **Admin fallback URLs:** Use `reverse("admin:app_label_modelname_changelist")` for "Open in backoffice" links (e.g. `admin:siteconfig_sitesettings_changelist`). Catch `NoReverseMatch` and set to `None` if the model is not on platform admin.

---

## Phase 0 — No code changes (verification only)

**Goal:** Confirm existing super surfaces; no work.

| Step | Action | Verification |
|------|--------|---------------|
| 0.1 | Confirm `/super/registries/` resolves and renders | Visit on manager host; 200 |
| 0.2 | Confirm `/super/blueprints/`, `/super/policies/`, `/super/workflow-packs/`, `/super/dashboard-packs/` resolve | Same |
| 0.3 | Confirm `/super/migration/` resolves | Same |
| 0.4 | Confirm `/super/billing/` resolves | Same |
| 0.5 | Confirm `/siteconfig/console/` (System config) resolves on manager | Same |
| 0.6 | Confirm "Configuration Engine" in nav points to config hub | Sidebar has Configuration Engine → /super/config/ (`super:config_hub`) |

**Exit:** Phase 0 complete when all above are true. Proceed to Phase 1.

---

## Phase 1 — Configuration hub

**Goal:** One landing at `/super/config/`; nav "Configuration Engine" points here; hub links to Site settings, Regions, Plans, Feature toggles, AI models, System config, Advanced backoffice.

### Step 1.1 — Add view function

- **File:** `apps/schools/super_views.py` (or create `apps/schools/super_views_config.py` and import in `super_urls`).
- **Function name:** `super_config_hub`.
- **Behavior:** GET only; build context with `dashboard_url`, and URLs for:
  - `site_settings_url` → `reverse("super:site_settings_list")` (Phase 2; wrap in try/except, use `None` until Phase 2 exists).
  - `regions_url` → `reverse("super:regions_list")` (Phase 3; or `None`).
  - `grading_url` → `reverse("super:grading_list")` (Phase 3; or `None`).
  - `plans_url` → `reverse("super:plans_list")` (Phase 4; or `None`).
  - `feature_toggles_url` → `reverse("super:feature_toggles_list")` (Phase 5; or `None`).
  - `ai_models_url` → `reverse("super:ai_models_list")` (Phase 6; or `None`); if existing `super:ai_model_hub` is sufficient, use that.
  - `system_config_url` → `reverse("siteconfig:console_domains_hub")`.
  - `admin_index_url` → `reverse("admin:index")`.
- **Return:** `render(request, "schools/super_config_hub.html", context)`.
- **Permission:** View will be wrapped with `require_super_access_with_host` in URLs; no extra check in view.

### Step 1.2 — Add URL route

- **File:** `apps/schools/super_urls.py`.
- **Add:** `path("config/", require_super_access_with_host(super_views.super_config_hub), name="config_hub")`.
- **Place:** With other top-level super paths (e.g. after `path("orchestration/", ...)`).
- **Import:** If view is in a new module, add `from .super_views_config import super_config_hub` (and use that in path).

### Step 1.3 — Create template

- **File:** `templates/schools/super_config_hub.html`.
- **Content:**
  - `{% extends "control_plane_base.html" %}`.
  - `{% load i18n %}`.
  - `{% block cp_title %}{% trans "Configuration" %}{% endblock %}`.
  - `{% block breadcrumbs %}`: breadcrumb to dashboard + "Configuration".
  - `{% block cp_content %}`: container with page title/subtitle (use `studio_os/components/page_header.html` if desired), then a row of cards (same pattern as `super_trust_center.html`):
    - Card "Site settings (platform)": link to `site_settings_url` or "Coming soon" if None; icon bi-gear.
    - Card "Regions & grading": link to `regions_url` or `grading_url` or "Coming soon"; icon bi-globe.
    - Card "Plans & addons": link to `plans_url` or "Coming soon"; icon bi-currency-dollar.
    - Card "Feature toggles": link to `feature_toggles_url` or "Coming soon"; icon bi-toggle-on.
    - Card "AI / model registry": link to `ai_models_url` or `super:ai_model_hub` or "Coming soon"; icon bi-cpu.
    - Card "System config (bounded)": link to `system_config_url`; icon bi-sliders.
    - Card "Advanced backoffice": link to `admin_index_url`; icon bi-gear-wide-connected; text "Full Django admin".
  - Every card: title, short description, primary button/link. Use `dashboard_url` for any "Back" link.

### Step 1.4 — Point nav to hub

- **File:** `apps/schools/control_plane_nav.py`.
- **Find:** In "Platform Settings" group, the item with `"id": "admin_index"`, `"label": "Configuration Engine"`, `"url_name": "admin:index"`.
- **Change:** Set `"url_name"` to `"super:config_hub"` (keep id and label).

### Step 1.5 — Verification

- Visit `/super/config/` on manager host; 200; page shows all seven cards.
- "Configuration Engine" in sidebar goes to `/super/config/` (not `/admin/`).
- "Advanced backoffice" links to `/admin/`.
- "System config (bounded)" links to `/siteconfig/console/`.

**Exit:** Phase 1 complete. Proceed to Phase 2.

---

## Phase 2 — Site settings (platform)

**Goal:** List and edit platform-level SiteSettings in super at `/super/config/site-settings/`.

### Step 2.1 — Resolve model and admin

- **Model:** `apps.siteconfig.models.SiteSettings` (or `siteconfig.SiteSettings`). Platform may have a single default site or multiple; check `Site` and how SiteSettings are scoped (e.g. by Site id or global default).
- **Admin:** `admin:siteconfig_sitesettings_changelist`; change form: `admin:siteconfig_sitesettings_change` with args `[pk]`.

### Step 2.2 — List view

- **View name:** `super_site_settings_list`.
- **URL name:** `super:site_settings_list`; path `config/site-settings/`.
- **Logic:** Query `SiteSettings.objects.all().order_by("id")` (or filter by platform site if applicable). Paginate if count > 20 (e.g. Page 20 per page). Build list of dicts: `id`, `__str__` or `name`/`domain`, link to edit view.
- **Template:** `schools/super_site_settings_list.html`. Extend control_plane_base; breadcrumbs Dashboard → System config (link to siteconfig:console_domains_hub) → Site settings; table or card list with "Edit" link per row to `super:site_settings_edit` with pk.
- **Context:** `site_settings_list`, `dashboard_url`, `system_config_url`, `admin_changelist_url` (for "Open in backoffice").

### Step 2.3 — Edit view

- **View name:** `super_site_settings_edit`.
- **URL name:** `super:site_settings_edit`; path `config/site-settings/<int:pk>/`.
- **Logic:** GET: load `SiteSettings.objects.get(pk=pk)`; render form (reuse SiteSettings form from siteconfig.forms or admin form class). POST: validate and save; redirect to list or back to edit with success message.
- **Form:** Reuse `SiteSettingsForm` or equivalent from `apps/siteconfig.forms`; restrict fields to a safe subset (e.g. site_name, tagline, primary_color, favicon, backend_console_theme) if full form is large. CSRF, method="post", action same URL.
- **Template:** `schools/super_site_settings_edit.html`. Form with submit; breadcrumbs; link back to list and to config hub.
- **Permission:** Same as other super views (require_super_access_with_host); no extra object-level check if only platform staff can access super.

### Step 2.4 — URLs

- In `super_urls.py`:  
  `path("config/site-settings/", require_super_access_with_host(super_views_config.super_site_settings_list), name="site_settings_list")`,  
  `path("config/site-settings/<int:pk>/", require_super_access_with_host(super_views_config.super_site_settings_edit), name="site_settings_edit")`.

### Step 2.5 — Config hub update

- In the view that builds config hub context, set `site_settings_url = reverse("super:site_settings_list")` (no longer None).
- Ensure "Site settings (platform)" card links to `site_settings_url`.

### Step 2.6 — Verification

- `/super/config/site-settings/` lists platform SiteSettings; "Edit" opens edit form; save works; "Back to list" and "Configuration" breadcrumb work.
- Config hub "Site settings (platform)" opens list.

**Exit:** Phase 2 complete. Proceed to Phase 3.

---

## Phase 3 — Regions & grading (platform)

**Goal:** List RegionConfig and GradingScaleConfig at `/super/config/regions/` and `/super/config/grading/`.

### Step 3.1 — Models

- **RegionConfig:** `apps.siteconfig.models.RegionConfig` (or from models that define it). Admin: `admin:siteconfig_regionconfig_changelist`.
- **GradingScaleConfig:** `apps.siteconfig.models.GradingScaleConfig`. Admin: `admin:siteconfig_gradingscaleconfig_changelist`.

### Step 3.2 — Regions list view

- **View:** `super_regions_list`; URL `config/regions/`, name `super:regions_list`.
- **Query:** `RegionConfig.objects.all().order_by("code")` or equivalent; paginate if needed.
- **Template:** `schools/super_regions_list.html`; table columns: code, name, term_count_per_year, etc.; optional "Open in backoffice" link to admin changelist.
- **Context:** `regions`, `dashboard_url`, `system_config_url`, `admin_regions_url`.

### Step 3.3 — Grading list view

- **View:** `super_grading_list`; URL `config/grading/`, name `super:grading_list`.
- **Query:** `GradingScaleConfig.objects.all().order_by("code")` or equivalent.
- **Template:** `schools/super_grading_list.html`; table with code, name, scale summary; optional backoffice link.
- **Context:** `grading_scales`, `dashboard_url`, `system_config_url`, `admin_grading_url`.

### Step 3.4 — URLs

- `path("config/regions/", ..., name="regions_list")`, `path("config/grading/", ..., name="grading_list")`.

### Step 3.5 — Config hub

- Set `regions_url = reverse("super:regions_list")`, `grading_url = reverse("super:grading_list")`. Card "Regions & grading" can link to regions (and from that page add a link to grading) or show two links (Regions | Grading).

### Step 3.6 — Verification

- `/super/config/regions/` and `/super/config/grading/` return 200 and show data; config hub links work.

**Exit:** Phase 3 complete. Proceed to Phase 4.

---

## Phase 4 — Plans & addons (platform)

**Goal:** List Plan and PlanAddon at `/super/config/plans/`.

### Step 4.1 — Models

- **Plan:** `apps.siteconfig.models.Plan` (or from platform catalog). Admin: `admin:siteconfig_plan_changelist`.
- **PlanAddon:** `apps.siteconfig.models.PlanAddon`. Admin: `admin:siteconfig_planaddon_changelist`.

### Step 4.2 — Plans list view

- **View:** `super_plans_list`; URL `config/plans/`, name `super:plans_list`.
- **Query:** `Plan.objects.all().order_by("slug")` (or name); include related addons count if desired.
- **Template:** `schools/super_plans_list.html`; table: slug/name, description snippet, addons count; optional "Open in backoffice".
- **Context:** `plans`, `dashboard_url`, `system_config_url`, `admin_plans_url`, `admin_addons_url`.

### Step 4.3 — URL and hub

- Add path; set `plans_url` in config hub.

### Step 4.4 — Verification

- `/super/config/plans/` returns 200; config hub "Plans & addons" links here.

**Exit:** Phase 4 complete. Proceed to Phase 5.

---

## Phase 5 — Feature toggles (platform)

**Goal:** List FeatureToggleDefinition (and optionally FeatureToggleState) at `/super/config/feature-toggles/`.

### Step 5.1 — Models

- **FeatureToggleDefinition:** `apps.siteconfig.models.FeatureToggleDefinition`. Admin: `admin:siteconfig_featuretoggledefinition_changelist`.
- **FeatureToggleState:** optional; list or link to admin.

### Step 5.2 — List view

- **View:** `super_feature_toggles_list`; URL `config/feature-toggles/`, name `super:feature_toggles_list`.
- **Query:** `FeatureToggleDefinition.objects.all().order_by("name")`.
- **Template:** `schools/super_feature_toggles_list.html`; table: name, key, description, default; optional backoffice link.
- **Context:** `definitions`, `dashboard_url`, `system_config_url`, `admin_url`.

### Step 5.3 — URL and hub

- Add path; set `feature_toggles_url` in config hub.

### Step 5.4 — Verification

- `/super/config/feature-toggles/` returns 200; hub link works.

**Exit:** Phase 5 complete. Proceed to Phase 6.

---

## Phase 6 — AI / model registry (platform)

**Goal:** List AIModelRegistry (and optionally RegionalAIConfig) at `/super/config/ai-models/`, or link hub to existing `super:ai_model_hub`.

### Step 6.1 — Decide

- If `super:ai_model_hub` already lists platform AI models and is sufficient, in config hub set `ai_models_url = reverse("super:ai_model_hub")` and no new view.
- Otherwise add `super_ai_models_list`; URL `config/ai-models/`, name `super:ai_models_list`.

### Step 6.2 — If new view

- **Model:** `apps.siteconfig.models.AIModelRegistry` (or from models_ai). Admin: `admin:siteconfig_aimodelregistry_changelist`.
- **View:** Query `AIModelRegistry.objects.all().order_by("model_id")`; template table; context as above.
- **Template:** `schools/super_ai_models_list.html`.

### Step 6.3 — Config hub

- Set `ai_models_url` to `super:ai_model_hub` or `super:ai_models_list`; card "AI / model registry" links there.

### Step 6.4 — Verification

- Hub "AI / model registry" opens correct page.

**Exit:** Phase 6 complete. Proceed to Phase 7.

---

## Phase 7 — Schools list (platform)

**Goal:** Dedicated school list at `/super/schools/` (paginated, optional filters).

### Step 7.1 — Model

- **School:** `apps.schools.models.School`. Admin: `admin:schools_school_changelist`.

### Step 7.2 — List view

- **View:** `super_schools_list`; URL `schools/`, name `super:schools_list`.
- **Query:** `School.objects.all().order_by("name")`; paginate (e.g. 25 per page). Optional filters: `is_active`, `country_code`, search by name/slug (GET params).
- **Template:** `schools/super_schools_list.html`; table: name, slug, subdomain, country, is_active, created; link to tenant_360 or admin change.
- **Context:** `schools` (page object), `dashboard_url`, `admin_schools_url`, filter form state.

### Step 7.3 — URL

- `path("schools/", require_super_access_with_host(super_views.super_schools_list), name="schools_list")`.
- **Nav:** Optionally add "Schools" under "Platform Overview" or "Schools" group (link to `super:schools_list`) if not redundant with tenant-health.

### Step 7.4 — Verification

- `/super/schools/` returns 200; pagination and optional filters work.

**Exit:** Phase 7 complete. Proceed to Phase 8.

---

## Phase 8 — Observability / Billing / Automation (hub links or list views)

**Goal:** Config hub or nav clearly maps to admin sections; optional list views for key models.

### Step 8.1 — Config hub (optional section)

- Add a second row or section on config hub: "Observability" → link to `super:pulse` or incidents; "Billing (raw)" → `admin:billing_*` changelist if exists; "Automation / Migration runs" → `super:migration_cloud` or admin automation changelist. Or document in hub copy: "For observability see Pulse, Usage, Analytics in sidebar; for billing see Billing; for migration see Migration."

### Step 8.2 — Optional list views

- If desired: `super_incidents_list` (PlatformIncident), `super_billing_accounts_list` (BillingAccount), `super_migration_runs_list` (MigrationRun). Each: view, URL under `super:`, template, link from hub or from existing super page. Follow same pattern as Phase 3/4.

### Step 8.3 — Verification

- No broken links; all admin-backed areas reachable from super (hub or sidebar); "Advanced backoffice" remains for full admin.

**Exit:** Phase 8 complete. Migration runbook complete.

---

## Final verification (all phases)

- [x] Sidebar "Configuration Engine" → `/super/config/` (not `/admin/`).
- [x] Config hub shows all cards; each card either links to a super view or "Coming soon" / backoffice.
- [x] Site settings: list and edit work; breadcrumbs and backoffice link work.
- [x] Regions and Grading lists load; Plans list loads; Feature toggles list loads; AI models (or ai_model_hub) load.
- [x] Schools list loads and paginates.
- [x] System config (bounded) and Advanced backoffice links work.
- [x] No 404 or 500 on any of the new URLs when accessed as superuser on manager host (see automated tests below).
- [x] Run `python manage.py check`; fix any issues.

**Automated verification:** `apps/schools/tests/test_super_config_migration_urls.py` — runs all above URL checks as unit tests. Run: `python manage.py test apps.schools.tests.test_super_config_migration_urls -v 2 --noinput` (optionally `--keepdb` to reuse test DB). All 10 tests pass when portal namespace is missing (context processor and admin app_list guard portal URLs).

---

## File checklist (summary)

| Phase | Files to create/modify |
|-------|------------------------|
| 1 | `apps/schools/super_views.py` (or super_views_config.py): super_config_hub; `apps/schools/super_urls.py`: path config/; `templates/schools/super_config_hub.html`; `apps/schools/control_plane_nav.py`: url_name → super:config_hub |
| 2 | super_views_config: super_site_settings_list, super_site_settings_edit; super_urls: config/site-settings/, config/site-settings/<pk>/; templates: super_site_settings_list.html, super_site_settings_edit.html; config hub context: site_settings_url |
| 3 | super_views_config: super_regions_list, super_grading_list; super_urls: config/regions/, config/grading/; templates: super_regions_list.html, super_grading_list.html; config hub: regions_url, grading_url |
| 4 | super_views_config: super_plans_list; super_urls: config/plans/; template: super_plans_list.html; config hub: plans_url |
| 5 | super_views_config: super_feature_toggles_list; super_urls: config/feature-toggles/; template: super_feature_toggles_list.html; config hub: feature_toggles_url |
| 6 | Config hub: ai_models_url → super:ai_model_hub or new super_ai_models_list + template |
| 7 | super_views: super_schools_list; super_urls: schools/; template: super_schools_list.html; optional nav item |
| 8 | Config hub copy or extra cards; optional list views for incidents/billing/migration |

Use this runbook as the single source of steps; tick off each step as done and run verification at the end of each phase.
