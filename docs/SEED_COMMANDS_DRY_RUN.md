# Seed Commands and --dry-run (Wave 6.1)

**Purpose:** All seed/bootstrap commands are idempotent and support `--dry-run` where it makes sense. This doc lists commands and dry-run support.

## Bootstrap umbrella

| Command | --dry-run | Notes |
|---------|-----------|--------|
| `bootstrap_platform_catalog` | Yes | Passes `--dry-run` to child seeds that support it. |
| `bootstrap_runmycampus_platform` | Via env | See BOOTSTRAP_PLATFORM_CATALOG.md. |

## Seed commands (platform catalog)

| Command | --dry-run | Idempotent |
|---------|-----------|------------|
| `seed_global_data` | No (--skip-unesco) | Yes (get_or_create/update_or_create) |
| `seed_platform_registries` | No | Yes |
| `seed_admin_dashboard_palettes` | No | Yes |
| `seed_blueprint_policy_packs` | Yes | Yes |
| `seed_workflow_dashboard_packs` | Yes | Yes |
| `seed_capability_registry` | Yes | Yes |
| `seed_marketplace_apps` | Yes | Yes |
| `seed_provider_registry` | Yes | Yes |
| `seed_migration_profiles` | Yes | Yes |
| `seed_finance_defaults` | No | Yes |
| `seed_faqs` | Yes | Yes |
| `seed_kb_articles` | Yes | Yes |
| `seed_compliance_baseline` | Yes | Yes |
| `seed_terminology_registry` | No | Yes (delegates to seed_platform_registries) |

## Recommendation

- Commands without `--dry-run`: add it when the command performs writes (e.g. seed_global_data, seed_platform_registries) so operators can preview.
- All seeds must remain idempotent (update_or_create/get_or_create).

## Verification

Run after deploy or locally:

```bash
python manage.py bootstrap_platform_catalog --all --dry-run
python manage.py bootstrap_runmycampus_platform  # when RUN_BOOTSTRAP_PLATFORM_CATALOG=1
```
