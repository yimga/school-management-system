# Code-truth inventory — Local-First Template Marketplace

Generated: 2026-05-23T14:09:48.833174+00:00

## Existing systems reused (not duplicated)

- `apps.platform_runtime.pack_{apply,audit,contract,impact,preview,rollback,simulation,dependency_graph}`
- `apps.platform_runtime.live_preview`
- `apps.platform_runtime.design_system`
- `apps.platform_runtime.localization`
- `apps.platform_runtime.cockpit_context`
- `apps.brand_experience.experience_packs`
- `apps.brand_experience.platform_global_branding`
- `apps.marketplace.pack_registry`
- `apps.packages.engine`
- `apps.packages.models.InstalledPackage`
- `apps.packages.models.PackageChangeLog`
- `apps.runtime_blueprints.models (proxies)`
- `apps.studio_os.{navigation,views,deep_links,services}`
- `apps.setup_studio.services`
- `apps.siteconfig.CountryRegistry (Wave 12/13 marketing voice)`

## New modules added

- `apps/brand_experience/experience_templates.py`
- `apps/brand_experience/template_ai_recommender.py`
- `apps/brand_experience/models_template.py`
- `apps/brand_experience/views_template_marketplace.py`
- `apps/brand_experience/urls_template_marketplace.py`
- `apps/brand_experience/migrations/0004_template_assignment_and_audit_event.py`
- `apps/siteconfig/local_experience_profiles.py`
- `apps/marketplace/template_partner_manifest.py`
- `apps/marketplace/template_monetization_manifest.py`

## Duplicates avoided

Zero. ExperienceTemplate composes over existing pack lifecycle.
