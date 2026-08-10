"""Seed the module feature registry into siteconfig.FeatureToggleDefinition.

Makes ``FeatureToggleDefinition`` the durable, authoritative source for module
enable/disable + label/description/price by PROACTIVELY upserting one row per
code in ``apps.schools.feature_registry.FEATURE_REGISTRY`` — instead of relying
on the lazy first-render seed that lives inside ``get_available_modules()`` (and
the ``resolve_module_enabled`` fallback that papers over the un-seeded window).

Idempotent: re-running only fills gaps and brings existing definitions up to the
current default-ON baseline (see ``ensure_module_registry_seeded``). Run it in
the PUBLIC / shared schema, where the platform-global FeatureToggleDefinition
rows live (a plain ``manage.py seed_feature_registry`` does exactly that under
django-tenants). Safe to add to the post-deploy step.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.policies_rules.models import FeatureToggleDefinition
from apps.schools.feature_registry import (
    ensure_module_registry_seeded,
    registry_module_codes,
)


class Command(BaseCommand):
    help = (
        "Seed the module feature registry into FeatureToggleDefinition "
        "(idempotent; run in the public/shared schema)."
    )

    def handle(self, *args, **options):
        before = FeatureToggleDefinition.objects.filter(category="modules").count()
        ensure_module_registry_seeded()
        after = FeatureToggleDefinition.objects.filter(category="modules").count()
        created = max(0, after - before)
        self.stdout.write(
            self.style.SUCCESS(
                f"Feature registry seeded: {len(registry_module_codes())} module "
                f"code(s); {created} new definition(s), {after} total 'modules' "
                f"definition(s) now present."
            )
        )
