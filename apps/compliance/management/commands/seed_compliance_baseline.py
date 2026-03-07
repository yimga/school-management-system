"""
Seed minimum compliance baseline data for strict compliance auditor checks.

Use this for fresh/local bootstrap databases where region rules and tenant
policy snapshots are missing.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Seed region feature rules and tenant compliance snapshots for active schools."

    def _core_feature_codes(self) -> list[str]:
        from apps.compliance.middleware import COMPLIANCE_GUARD_PATH_MAP

        return sorted(
            {
                str(code).strip()
                for code in COMPLIANCE_GUARD_PATH_MAP.values()
                if str(code).strip()
            }
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.compliance.models import RegionFeatureCompliance
        from apps.schools.models import School
        from apps.siteconfig.models import RegionConfig

        default_region = RegionConfig.get_default()
        core_features = self._core_feature_codes()
        active_schools = list(School.objects.filter(is_active=True).select_related("default_region"))

        updated_schools = 0
        region_ids: set[str] = set()

        for school in active_schools:
            changed = False
            region = school.default_region or default_region
            if school.default_region_id != region.pk:
                school.default_region = region
                changed = True

            settings = dict(getattr(school, "settings", None) or {})

            if not (settings.get("tenant_policy_pack") or {}).get("code"):
                settings["tenant_policy_pack"] = {
                    "code": region.code,
                    "version": "baseline.1",
                }
                changed = True

            if not settings.get("tenant_compiled_config"):
                settings["tenant_compiled_config"] = {
                    "default_language": region.default_language,
                    "timezone": region.timezone,
                }
                changed = True

            if not settings.get("tenant_config_metadata"):
                settings["tenant_config_metadata"] = {
                    "default_language": {"source": "baseline_seed"},
                    "timezone": {"source": "baseline_seed"},
                }
                changed = True

            if changed:
                school.settings = settings
                school.save(update_fields=["default_region", "settings", "updated_at"])
                try:
                    from apps.policies.policy_registry import invalidate_policy_cache
                    invalidate_policy_cache(school)
                except Exception:
                    pass
                updated_schools += 1

            region_ids.add(region.pk)

        # Ensure at least one region has rules so global rule coverage check passes on fresh DBs.
        if not region_ids:
            region_ids.add(default_region.pk)

        created_rules = 0
        updated_rules = 0
        for region_id in sorted(region_ids):
            region = RegionConfig.objects.get(pk=region_id)
            for feature_code in core_features:
                rule, created = RegionFeatureCompliance.objects.get_or_create(
                    region=region,
                    feature_code=feature_code,
                    defaults={"status": RegionFeatureCompliance.Status.ENABLED},
                )
                if created:
                    created_rules += 1
                elif rule.status != RegionFeatureCompliance.Status.ENABLED:
                    rule.status = RegionFeatureCompliance.Status.ENABLED
                    rule.save(update_fields=["status", "updated_at"])
                    updated_rules += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded compliance baseline: "
                f"schools_updated={updated_schools}, "
                f"rules_created={created_rules}, "
                f"rules_updated={updated_rules}"
            )
        )
