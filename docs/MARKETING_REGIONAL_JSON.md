# Regional and campaign marketing JSON

## Purpose

Ship different headlines, SEO, segments, and `extras` (FAQs, diagrams) per **region** or **campaign variant** without code changes.

## Environment

| Variable | Example | Effect |
|----------|---------|--------|
| `MARKETING_CONTENT_REGION` | `eu` | Prefer `compare_eu.json` over `compare.json` |
| `MARKETING_CONTENT_VARIANT` | `q1` | Prefer `compare_eu_q1.json` when region is also set, or `compare_q1.json` when region is unset |

Empty or unset → only `{slug}.json` is used.

## Examples in repo

- **`config/marketing_content/compare_eu.json`** — EU/GDPR-oriented compare copy when `MARKETING_CONTENT_REGION=eu`.

## Precedence

See `apps/schools/marketing_views._load_marketing_page_from_file`:

1. `{slug}_{region}_{variant}.json`
2. `{slug}_{region}.json`
3. `{slug}_{variant}.json`
4. `{slug}.json`

## Validation

`python manage.py validate_marketing_urls` parses **all** `*.json` files here and enforces non-empty `label`, `seo_title`, and `headline`.

## Related

- [MARKETING_EXECUTION.md](MARKETING_EXECUTION.md) — deploy checklist
- [MARKETING_SEEDING.md](MARKETING_SEEDING.md) — DB CMS vs file overrides
