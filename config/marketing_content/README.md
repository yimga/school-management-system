# Marketing page JSON overrides

Files here override `MARKETING_PAGE_DEFINITIONS` in `apps/schools/marketing_views.py` for matching URL slugs.

## File naming (precedence)

For slug `compare`, loader tries (first hit wins):

1. `{slug}_{region}_{variant}.json` — e.g. `compare_eu_q1.json`
2. `{slug}_{region}.json` — e.g. `compare_eu.json` (see repo example for EU copy)
3. `{slug}_{variant}.json` — campaign/A-B file without region, e.g. `compare_secondary.json`
4. `{slug}.json` — default

Set **`MARKETING_CONTENT_REGION`** and optionally **`MARKETING_CONTENT_VARIANT`** in the environment (see `config/settings.py`).

Full reference: [docs/MARKETING_REGIONAL_JSON.md](../docs/MARKETING_REGIONAL_JSON.md).

Validation: `python manage.py validate_marketing_urls` checks every `*.json` in this directory.
