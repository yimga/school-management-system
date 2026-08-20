"""Ensure Gilead-Tech tenant has full platform entitlements (sovereignty showcase).

Scoped to slug ``gilead-tech`` only — do not run for other tenants.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

GILEAD_SLUGS = ("gilead-tech", "gilead_tech", "gilead-tech-high")


def _collect_platform_feature_codes() -> set[str]:
    """Union EVERY feature/module source the platform exposes.

    gilead-tech is the "la crème" sovereignty showcase — it must hold literally
    every feature the platform can offer, so we union three sources rather than
    two: the plan-catalog feature lists, the STATIC module registry
    (``FEATURE_REGISTRY``), AND the LIVE DB-seeded module registry
    (``get_available_modules`` reads ``FeatureToggleDefinition`` rows, which can
    carry modules that never made it into the static list). Missing the DB
    source is exactly how a "give it everything" grant silently omits a module.
    """
    from apps.billing.management.commands.seed_subscription_catalog import PLAN_CATALOG
    from apps.schools.feature_registry import FEATURE_REGISTRY, get_available_modules

    codes: set[str] = set()
    for row in PLAN_CATALOG:
        for feat in row.get("features") or []:
            if feat:
                codes.add(str(feat))
    for module in FEATURE_REGISTRY:
        code = (module.get("code") or "").strip()
        if code:
            codes.add(code)
    try:
        # Live DB module registry (may exceed the static FEATURE_REGISTRY).
        for module in get_available_modules():
            code = (module.get("code") or "").strip()
            if code:
                codes.add(code)
    except Exception:  # noqa: BLE001 — the DB registry is a bonus source, never fatal
        pass
    return codes


class Command(BaseCommand):
    help = "Bind gilead-tech to sovereign-self-hosted and materialize all platform features."

    def handle(self, *args, **options):
        from apps.billing.models import Entitlement, TenantSubscription
        from apps.billing.services import (
            ensure_subscription_for_school,
            reconcile_subscription_entitlements,
        )
        from apps.schools.models import School
        from apps.siteconfig.models_platform_catalog import Plan

        school = None
        for slug in GILEAD_SLUGS:
            school = School.objects.filter(slug=slug).first()
            if school is not None:
                break
        if school is None:
            self.stderr.write(
                self.style.ERROR(
                    "Gilead-Tech school not found (tried: %s)" % ", ".join(GILEAD_SLUGS)
                )
            )
            return

        plan = Plan.objects.filter(slug="sovereign-self-hosted").first()
        if plan is None:
            self.stderr.write(
                self.style.ERROR(
                    "Plan sovereign-self-hosted missing — run seed_subscription_catalog first."
                )
            )
            return

        all_features = _collect_platform_feature_codes()

        with transaction.atomic():
            school.plan = plan
            school.billing_type = "COMPLIMENTARY"
            school.save(update_fields=["plan", "billing_type", "updated_at"])

            features = dict(getattr(school, "features", None) or {})
            for code in sorted(all_features):
                features[code] = True
            school.features = features
            school.save(update_fields=["features", "updated_at"])

            account, subscription, _created = ensure_subscription_for_school(school)
            if subscription.plan_id != plan.pk:
                subscription.plan = plan
                subscription.status = TenantSubscription.Status.ACTIVE
                subscription.save(update_fields=["plan", "status", "updated_at"])
            reconcile_subscription_entitlements(subscription, as_of=timezone.now())
            now = timezone.now()
            for code in sorted(all_features):
                Entitlement.objects.update_or_create(
                    school=school,
                    code=code,
                    defaults={
                        "subscription": subscription,
                        "kind": Entitlement.Kind.FEATURE,
                        "source": Entitlement.Source.MANUAL,
                        "is_enabled": True,
                        "limit_value": None,
                        "effective_from": now,
                        "effective_until": None,
                        "metadata": {"gilead_sovereignty_showcase": True},
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Gilead-Tech (%s) on sovereign-self-hosted with %d feature entitlements "
                "(billing_type=COMPLIMENTARY, modules enabled)."
                % (school.slug, len(all_features))
            )
        )
