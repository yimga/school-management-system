# App structure in this repository

## First-party marketplace apps

- Defined as `MarketplaceApp` rows with `AppKind.FIRST_PARTY` (or equivalent) and a `PublisherOrganization` (e.g. `runmycampus-first-party`).
- Seeded idempotently by `python manage.py seed_marketplace_apps` (`apps/marketplace/management/commands/seed_marketplace_apps.py`).
- Each app includes a `manifest` JSON; listings add compatibility, screenshots, and governance metadata.

## Platform pack catalog

- Workflow/dashboard/theme packs: `apps/marketplace/data/platform_pack_catalog.json`, loaded by `apps/marketplace/pack_registry.py` (discovery/validation only; apply paths are governed elsewhere).

## Django apps

Bounded contexts live under `apps/<name>/` (e.g. `academics`, `people`, `marketplace`, `siteconfig`). New surface code should follow existing URL namespaces (`config.tenant_urls`, `config.manager_urls`) and permission decorators.

## Internal “seed” apps for demos

The seed command adds internal catalog entries (e.g. `enterprise-governance-console`, `global-readiness-starter`) so empty environments still show governed first-party listings. Re-run the command after resetting a database.
