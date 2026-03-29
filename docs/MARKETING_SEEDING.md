# Marketing site seeding

## Command

```bash
python manage.py seed_marketing_cms
```

**Idempotent** (`update_or_create`). Safe on local, staging, and production.

## What it fills

| Data | Purpose |
|------|---------|
| **BlogPost** (4 rows, `is_published=True`) | `/blog/` lists posts; each links to `/blog/<slug>/`. |
| **MarketingContent** | `landing_hero_headline`, `landing_hero_subheadline`, `landing_hero_ai_line` override the home hero after geo/channel logic; `blog_list_intro` HTML on the blog index. |

## Bootstrap

`bootstrap_platform_catalog --all` and `bootstrap_runmycampus_platform` now run **`seed_marketing_cms`** as the final step. See [BOOTSTRAP_PLATFORM_CATALOG.md](BOOTSTRAP_PLATFORM_CATALOG.md).

## Other marketing content

- **JSON pages:** `config/marketing_content/*.json` override or extend specific slugs (see `marketing_views._load_marketing_page_from_file`). Run `python manage.py validate_marketing_urls` to verify all JSON files parse and include required keys (`label`, `seo_title`, `headline`).
- **In-code definitions:** `MARKETING_PAGE_DEFINITIONS` in `apps/schools/marketing_views.py` for slugs without JSON.
- **Tenant example links:** set `TENANT_EXAMPLE_SLUG` (e.g. `demo-school`) in env so marketing copy can link to a real subdomain. If `MARKETING_DEMO_TENANT_URL` is empty, settings derive `https://{TENANT_EXAMPLE_SLUG}.{MULTI_TENANT_BASE_DOMAIN}/` for the “Try demo” CTA. Seed users with `python manage.py seed_demo_tenant_users`.
- **Hero / AI visuals:** optional `MARKETING_HERO_IMAGE_URL`, `MARKETING_HERO_VIDEO_URL`, `MARKETING_HERO_VIDEO_POSTER_URL`, and per-key `MARKETING_*_IMAGE_URL` vars in `config/settings.py`. When unset, `apps/schools/marketing_ai.get_marketing_ai_asset_url` returns static SVGs under `static/images/marketing/` (PNG/video remain env/CDN when you add them). **Env table:** [MARKETING_ASSETS.md](MARKETING_ASSETS.md). **Release checklist:** [MARKETING_EXECUTION.md](MARKETING_EXECUTION.md) § Deploy / release checklist.
- **Regional JSON:** `MARKETING_CONTENT_REGION` / `MARKETING_CONTENT_VARIANT` — see [MARKETING_REGIONAL_JSON.md](MARKETING_REGIONAL_JSON.md).
