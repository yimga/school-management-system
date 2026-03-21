# Marketing assets — CDN, PNG, video, SVG

## Philosophy

The public site **must not** ship broken image slots. **SVG placeholders** live under `static/images/marketing/` and are used when env URLs are unset (`apps/schools/marketing_ai.py` + `marketing_views._marketing_context`).

For **production polish**, point env vars at your CDN or object storage (HTTPS URLs).

## Hero and video

| Env variable | Purpose |
|--------------|---------|
| `MARKETING_HERO_IMAGE_URL` | Hero / dashboard still (absolute URL) |
| `MARKETING_HERO_VIDEO_URL` | Hero background/overview MP4 (or other) |
| `MARKETING_HERO_VIDEO_POSTER_URL` | Video poster frame |
| `MARKETING_HERO_IMAGE_SRCSET` | Optional responsive srcset string (see `marketing_views` context) |
| `MARKETING_HERO_IMAGE_SIZES` | Optional `sizes` attribute |

## AI governance slots (`get_marketing_ai_asset_url`)

When unset, static SVG fallbacks apply.

| Env variable | Slot |
|--------------|------|
| `MARKETING_MIGRATION_FLOW_IMAGE_URL` | Migration flow visual |
| `MARKETING_SETUP_STUDIO_IMAGE_URL` | Setup studio flow |
| `MARKETING_ECOSYSTEM_IMAGE_URL` | Ecosystem diagram |
| `MARKETING_MARKETPLACE_IMAGE_URL` | Marketplace hero |

Additional diagram URLs are documented in `config/settings.py` comments (migration studio, platform architecture, school-in-a-box, data intelligence loop, etc.) — see **MARKETING_*** keys near the marketing block.

## Where settings are read

- `config/settings.py` — env → `MARKETING_*` settings
- `apps/schools/marketing_ai.py` — governed keys + SVG fallback map
- `apps/schools/marketing_views.py` — landing context, `static()` defaults

## Checklist

1. Set CDN URLs in staging/production env (Render, etc.).
2. Run `python manage.py validate_marketing_urls` after editing `config/marketing_content/*.json`.
3. Optional lab CWV: GitHub **Lighthouse CI** when `vars.LHCI_URL` is set; optional **Marketing N10** PR workflow for server-side `/marketing/` budget.

See [MARKETING_EXECUTION.md](MARKETING_EXECUTION.md) deploy section.
