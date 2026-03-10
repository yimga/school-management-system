# Marketing front plan verification

Verification of the Seed Marketing Front plan (seed_marketing_front_ce217fad.plan.md) against the codebase. All items below are implemented unless noted.

## Target URL structure

| Path | Status | Notes |
|------|--------|--------|
| `/` → marketing_landing | Done | |
| `/education-operating-system/` | Done | Flagship page + diagram |
| `/platform/` + `/platform/education-os/` … `/platform/analytics/` | Done | All 9 routes in public_urls.py and config/urls.py |
| `/solutions/` | Done | Existing |
| `/for/*` or `/roles/*` | Done | roles/ + for/principals, for/district-leaders |
| `/marketplace/` + apps, integrations, templates, blueprints, policy-packs, partners | Done | |
| `/themes/`, `/design-studio/` | Done | |
| `/migrate-from/`, `/migrate-from/<source>/` | Done | Alias to same view as /migrate/ |
| `/getting-started/`, `/product-tour/` | Done | product-tour → interactive-preview |
| Marketing trust page | Done | **`/status/`** on apex (public host); **`/uptime/`** is an alias. For health on apex use **`/health/`** or **`/healthz/`** (not `/status/`). Render uses `healthCheckPath: /health/`. |

## Phase 1: Core narrative and flagship

- **1.1** `platform_headline` = "The Operating System for Modern Schools"; `hero_subheadline` = admissions/academics/… unified; `platform_pillar_grid` = six pillars; `category_claim` = "The Operating System for Modern Education."; hero CTAs include "See How It Works" → `/education-operating-system/`. **Done** (marketing_views.py).
- **1.2** Route `education-operating-system/` in public_urls.py and config/urls.py; content in `MARKETING_PAGE_DEFINITIONS`; diagram via `page_extras.diagram_path`; template uses marketing_page.html with diagram block. **Done.**

## Phase 2: Platform architecture pages

- **2.1** Routes for platform/, platform/education-os/, … platform/analytics/ in both urlconfs; entries in `MARKETING_PAGE_DEFINITIONS`. **Done.**
- **2.2** `diagram_path`, `hero_video_url`, `hero_video_poster_url` in context/extras; real diagram in Phase 7. **Done.**

## Phase 3: Onboarding, themes, trust

- **3.1** Route `getting-started/`; content with 6 steps in `MARKETING_PAGE_DEFINITIONS`. **Done.**
- **3.2** Routes `themes/`, `design-studio/`; content in definitions. **Done.**
- **3.3** Marketing trust at **`/status/`** on public urlconf (`/uptime/` alias). Health on apex: **`/health/`** or **`/healthz/`**; tenant/manager keep `/status/` as health. Links to `MARKETING_STATUS_PAGE_URL`; `MARKETING_PAGE_EXTRAS["uptime"]` with `sla_uptime`. **Done.**

## Phase 4: Migrate-from and personas

- **4.1** Routes `migrate-from/`, `migrate-from/<str:source_slug>/` calling `migrate_marketing_page`. **Done.**
- **4.2** `ROLE_PAGE_DEFINITIONS` includes principals, district-leaders; routes `roles/principals/`, `roles/district-leaders/`, `for/principals/`, `for/district-leaders/`. **Done.**

## Phase 5: Interactive experiences

- **5.1** Route `product-tour/` → same view as interactive-preview. **Done.**
- **5.2** `MIGRATION_SIMULATOR_SOURCES` (PowerSchool, Blackbaud, Infinite Campus, spreadsheets); view `migration_simulator_page`; route `migrate/simulator/`; JSON + HTML; template. **Done.** (Veracross not in MIGRATE_PAGE_DEFINITIONS; can be added later if needed.)
- **5.3** `GETTING_STARTED_SIMULATOR_STEPS`; view `setup_simulator_page`; route `getting-started/simulator/`; template with CTAs. **Done.**

## Phase 6: Content engine and developer extensions

- **6.1** Routes `/research`, `/reports`, `/guides` and definitions. **Done.** (Also added to config/urls.py.)
- **6.2** Marketplace: templates, blueprints, policy-packs in `MARKETING_PAGE_DEFINITIONS` and routes; template shows templates_copy, blueprints_copy, policy_packs_copy. **Done.** Developers: `app-building` in `DEVELOPER_PAGE_DEFINITIONS` and route `developers/app-building/`. **Done.**

## Phase 7: Diagrams, video, data viz

- **Diagrams:** `static/images/marketing/platform-diagram-marketing.svg`; `diagram_path` in MARKETING_PAGE_EXTRAS for education-operating-system and platform; marketing_page.html renders diagram. **Done.**
- **Video:** `MARKETING_HERO_VIDEO_URL`, `MARKETING_HERO_VIDEO_POSTER_URL`; marketing_landing.html uses `hero_video_url` / `hero_video_poster_url`. **Done.**
- **Data viz:** `platform-analytics` has `data_viz_path` (viz-admin.svg) and caption; template block. **Done.**
- **Docs:** `docs/MARKETING_MEDIA.md`. **Done.**

## Phase 8: Tenant and manager host behavior

- **Cross-host links:** `get_canonical_base_domain()` in host_routing.py; context processor `marketing_base_url` adds `MARKETING_BASE_URL`; dashboard_footer uses it for Platform Status (`/status/`), RunMyCampus, Pricing; docs_landing "Back to Marketing" uses it. **Done.**
- **Documentation:** `docs/MARKETING_CROSS_HOST.md`. **Done.**
- **Test:** `test_marketing_base_url_context_processor_uses_canonical_domain` in test_public_access_points.py. **Done.**

## File touchpoints (plan table)

| Area | Status |
|------|--------|
| Routes: public_urls.py, config/urls.py | Done; config/urls.py has core + research/reports/guides (migrate, marketplace, roles, developers subsections live on public_urls when urlconf is switched). |
| Context and definitions: marketing_views.py | Done. |
| Content seed: JSON or code | Using MARKETING_PAGE_DEFINITIONS (Option B); file-based JSON per page supported; both required for full flexibility. |
| Templates: marketing_landing, marketing_page, etc. | Done; diagram and data_viz blocks in marketing_page.html. |
| Static: platform-diagram-marketing.svg | Done. |
| Docs: MARKETING_MEDIA.md, tenant/manager behavior | Done (MARKETING_MEDIA.md, MARKETING_CROSS_HOST.md). |

## In scope (working platform)

- **Real diagrams and video pipeline:** SVG diagram in place; video via settings; documented. **Done.**
- **Backend migration and setup simulators:** Backend config and views; no static-only. **Done.**
- **Tenant/manager behavior:** Cross-host links and docs. **Done.**

---

**Summary:** The plan is fully implemented. The marketing trust page is at **`/status/`** on the public (apex) host (**`/uptime/`** is an alias). For health checks on the apex host use **`/health/`** or **`/healthz/`**; on tenant/manager, **`/status/`** remains the health endpoint. Render uses `healthCheckPath: /health/`.
