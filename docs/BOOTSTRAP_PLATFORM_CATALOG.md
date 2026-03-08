# Bootstrap platform catalog

The Manager **Blueprint marketplace** and **App catalog** show "No active blueprint packs" and "No installable apps" until platform data is seeded. Other surfaces (registries, workflow/dashboard packs, portal FAQs/KB, super policies catalog, etc.) can also be empty until their seeds are run. This document describes how to populate **all applicable** catalogs.

## One-command bootstrap

| Command | Purpose |
|--------|--------|
| `python manage.py bootstrap_platform_catalog` | Runs **blueprint packs** and **marketplace apps** only (default; backward compatible). |
| `python manage.py bootstrap_platform_catalog --all` | Runs **every applicable platform seed** in dependency order (global data, registries, palettes, blueprint, workflow/dashboard, capability registry, marketplace, finance defaults, FAQs, KB articles, compliance baseline). Idempotent. |

Use `--all` for a full first-time setup so no catalog surface is left empty. Use default (no `--all`) when you only want Blueprint + App catalog filled (e.g. existing deploy that already has global data).

### Skip flags (with `--all`)

- `--skip-global-data` — Skip `seed_global_data` (regions, country profiles, brand registry).
- `--skip-registries` — Skip `seed_platform_registries`.
- `--skip-palettes` — Skip `seed_admin_dashboard_palettes` (often already run in predeploy).
- `--skip-workflow-dashboard` — Skip `seed_workflow_dashboard_packs`.
- `--skip-capability-registry` — Skip `seed_capability_registry`.
- `--skip-finance-defaults` — Skip `seed_finance_defaults`.
- `--skip-portal` — Skip `seed_faqs` and `seed_kb_articles`.
- `--skip-compliance-baseline` — Skip `seed_compliance_baseline` (requires active schools).

Use `--dry-run` to pass through to commands that support it (e.g. marketplace, capability registry).

## All seed commands (reference)

Every seed listed here is idempotent unless noted. Run individually or via `bootstrap_platform_catalog --all`.

| Command | Purpose |
|--------|--------|
| `seed_global_data` | Orchestrates: seed_global_regions, seed_country_profiles, seed_global_brand_registry. Use `--skip-unesco` to avoid external UNESCO calls. |
| `seed_global_regions` | RegionConfig for all countries from global catalog (pycountry/geonamescache). |
| `seed_country_profiles` | Education system profiles for global country packs. |
| `seed_global_brand_registry` | GlobalBrandRegistry for all countries (optional UNESCO enrichment). |
| `seed_platform_registries` | Countries, subdivisions, education levels, education system types, currencies, etc. (registries app). |
| `seed_admin_dashboard_palettes` | Preset admin dashboard color palettes (Unfold design system). |
| `seed_blueprint_policy_packs` | Active BlueprintPack rows (institution + regional) and PolicyBundle rows. |
| `seed_workflow_dashboard_packs` | Workflow packs and dashboard packs (Phase 4). |
| `seed_capability_registry` | CapabilityRegistry codes (dashboard_widget, workflow_action, etc.). |
| `seed_marketplace_apps` | First-party publisher and approved marketplace apps/listings. |
| `seed_finance_defaults` | Finance compliance profiles (e.g. Cameroon OHADA, Generic) and chart of accounts. |
| `seed_faqs` | Portal FAQ categories and curated questions. |
| `seed_kb_articles` | Portal Knowledge Base articles and categories. |
| `seed_compliance_baseline` | Region feature rules and tenant compliance snapshots for active schools. |
| `seed_regions` | Alternative: default regions and grading scales (smaller set; may overlap with seed_global_regions). |
| `seed_preview_fixtures` | Preview fixtures for documents, widgets, sessions, site settings. |

### Demo / test-only (do not use for production bootstrap)

- `seed_demo` (academics) — Demo data for local/staging.
- `seed_buea_synthetic` — Synthetic Buea dataset (passwords: Test1234).
- `seed_testdata_2425` — 2024/2025 test data (users, academics, evaluations, reports).

### User / deploy-specific

- `seed_render_users` — Super-admin and optional tenant demo users; run in predeploy (see DEPLOY_RENDER.md).

## When to run

- **First deploy or new environment:** Run `python manage.py bootstrap_platform_catalog --all` once so every applicable catalog is populated. On Render, set `RUN_BOOTSTRAP_PLATFORM_CATALOG=1`; optionally set `RUN_FULL_BOOTSTRAP=1` (see below) to use `--all`.
- **Render (Blueprint + App catalog only):** Set `RUN_BOOTSTRAP_PLATFORM_CATALOG=1`; `render_predeploy.sh` runs `bootstrap_platform_catalog` (no `--all`) after `seed_render_users`.
- **Manual:** After migrations, run `bootstrap_platform_catalog` or `bootstrap_platform_catalog --all` (or individual seed commands).

## What gets seeded (default bootstrap)

- **Blueprint packs:** Institution-type packs (Early Learning, Primary, Secondary, K-12, Technical/Vocational, Tertiary, etc.) and regional packs (Cameroon Francophone/Anglophone, UAE MoE+IB, UK GCSE/A-Level, US K-12 District, etc.). All are `is_active=True`.
- **Marketplace apps:** A first-party publisher and several first-party apps with **approved** listings so the App catalog shows installable apps.
