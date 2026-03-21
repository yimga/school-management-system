# SiteSettings → RuntimeDefaults decomposition

**Wave 15 (SOT):** Documents how control-plane `SiteSettings` flows into read-optimized `platform_runtime.RuntimeDefaults` without scattering `get_solo()` outside the allowlist.

## On save

- `SiteSettings.save()` calls `sync_runtime_defaults(owners=...)` so changed ownership domains publish into `RuntimeDefaults.payload` (merge per owner when partial).
- Effective settings resolution (`get_effective_site_settings`) prefers `RuntimeDefaults.payload` keys before legacy singleton fields on `SiteSettings`.

## Backfill / repair

After deploy or schema changes, run:

```bash
python manage.py backfill_runtime_defaults
```

Options:

- `--owner branding` (repeatable) — limit payload keys to one or more domains from `apps.siteconfig.domain_ownership.OWNERSHIP_DOMAINS`.
- `--exclude-owner …` — omit domains from the built payload.

The command uses `get_platform_site_settings_record(create=True)` (allowlisted) and `RuntimeDefaults.sync_from_site_settings`.

## Adding a new owned field

1. Register the field under the correct ownership domain in `SiteSettings` / `owned_payload` / `owned_field_names`.
2. Ensure `RuntimeDefaults.build_payload_from_site_settings` includes it when that owner is synced (or full sync).
3. Run `backfill_runtime_defaults` in staging after migration.

## No `sw.js` fork

Parent/portal PWA continues to use `static/js/service-worker.js` and `manifest-portal.json`; SiteSettings branding does not require a second service worker.
