# SiteSettings → RuntimeDefaults decomposition

**Wave 15 (SOT):** Documents how control-plane `SiteSettings` flows into read-optimized `platform_runtime.RuntimeDefaults` without scattering `get_solo()` outside the allowlist.

**Bounded contexts (target end state):** Long-term, behavioral keys belong under the ownership domains in `apps/siteconfig/domain_ownership.py` (brand_experience, runtime_blueprints, policies_rules, plans_entitlements, global_registries, marketplace_integrations, metadata_governance, preview_platform, etc.), implemented as **dedicated surfaces or tables** where volume warrants it — not as infinite growth on the `siteconfig` app as UX gravity. Phase B already moves truth to `RuntimeDefaults`, per-domain `PlatformPhaseBDomainSnapshot`, and `PlatformGlobalBranding`; migration `platform_runtime.0009_runtimedefaults_preview_integration_columns` adds **first-class columns** on `RuntimeDefaults` for preview + non-secret integration fields (see `apps/platform_runtime/runtime_defaults_first_class.py`).

## On save

- `SiteSettings.save()` calls `sync_runtime_defaults(owners=...)` so changed ownership domains publish into `RuntimeDefaults.payload` (merge per owner when partial), plus **first-class** `RuntimeDefaults` columns for keys in `RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES` (stripped from JSON payload on sync).
- Effective settings resolution (`get_effective_site_settings`) merges domain snapshots, then `RuntimeDefaults.payload`, then **typed columns** overriding overlapping payload keys, then `PlatformGlobalBranding` (see `apps/platform_runtime/helpers.py`).

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
