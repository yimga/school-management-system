# Global configuration (grading, terms, locale, regions)

## Education DNA and profiles

- Tenant education alignment uses approved **education profiles** and related siteconfig models (`apps/siteconfig/models_platform_catalog.py` and companions). Operators select profiles that carry grading logic hints, compliance tags, and geography.

## Academic years and terms

- Academic years and term structures are first-class in the academics app; onboarding checklist points operators at **Academic year configured** and related setup evidence routes.

## Locale and language

- Django i18n catalogs live under `locale/`; template context includes `language_context` from `apps.siteconfig.context_processors.language_context`.
- Country/region profiles support primary language codes for market pages (`models_global_experience`).

## Commercial tier vs technical SKUs

- **Commercial ladder** (`free` / `pro` / `enterprise`): `apps/siteconfig/commercial_tiers.py` — used for marketplace minimum-tier gates and billing page copy.
- **BR-10 technical bundles** (`core` / `interop` / `intelligence`): `apps/siteconfig/billing_sku_registry.py` — feature codes on plans and in `/api/v1/manifest.json`.

## Further reading

- `docs/scaling/1000_TENANT_SCALE_CHECKLIST.md`
- `docs/BILLING_SKUS_ENTITLEMENTS.md`
