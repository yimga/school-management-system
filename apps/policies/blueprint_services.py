"""
Phase 6: Blueprint pack apply service.
Applying a BlueprintPack to a school creates a PolicyBundle and sets TenantBlueprint.active_bundle.
24.15: preview_blueprint_pack for preview/validation without apply; apply validates pack active.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, IntegrityError

from apps.platform_runtime.structured_logging import log_exception_with_context

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Blanket grant: entitles a school to every premium commercial pack.
PREMIUM_BLUEPRINT_ENTITLEMENT_CODE = "premium_blueprints"


class EntitlementRequired(ValueError):
    """A premium commercial pack was applied without a commercial entitlement.

    Subclasses ValueError on purpose: every existing caller of apply_blueprint_pack
    already handles ValueError (the pack-not-active refusal has always been one), so
    a refused premium apply degrades to "skipped and logged" rather than a 500.
    """


def premium_entitlement_codes(pack) -> list[str]:
    """Entitlement codes that satisfy this pack, most specific first."""
    slug = (getattr(pack, "slug", "") or "").strip().lower()
    codes = []
    if slug:
        codes.append(f"blueprint_pack:{slug}")
    codes.append(PREMIUM_BLUEPRINT_ENTITLEMENT_CODE)
    return codes


def has_premium_entitlement(school, pack) -> bool:
    """True when this school holds an in-window billing grant for this pack.

    Deliberately reads the billing ``Entitlement`` table directly rather than going
    through ``entitlements.can`` / ``is_feature_enabled``: those resolve a UNION of
    plan features, add-ons, the module manifest and an operator floor, and grant
    everything outright for COMPLIMENTARY/MANUAL_OVERRIDE billing. A commercial gate
    a module manifest can open is not a commercial gate -- this one wants an explicit,
    auditable row. Fails CLOSED.
    """
    if school is None or not getattr(school, "pk", None):
        return False
    try:
        from django.db.models import Q
        from django.utils import timezone

        from apps.billing.models import Entitlement

        now = timezone.now()
        return (
            Entitlement.objects.filter(
                school=school,
                code__in=premium_entitlement_codes(pack),
                kind=Entitlement.Kind.FEATURE,
                is_enabled=True,
            )
            .filter(Q(effective_from__isnull=True) | Q(effective_from__lte=now))
            .filter(Q(effective_until__isnull=True) | Q(effective_until__gt=now))
            .exists()
        )
    except (ImportError, LookupError, AttributeError, TypeError, ValueError) as e:
        logger.warning(
            "apply_blueprint_pack: premium entitlement lookup failed for "
            "school=%s pack=%s; failing closed: %s",
            getattr(school, "pk", None),
            getattr(pack, "slug", None),
            e,
        )
        return False

# Do not fail blueprint apply if package engine is unavailable (§2.4 allowlist 0).
_BLUEPRINT_PACKAGE_ENGINE_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    DatabaseError,
    IntegrityError,
    ObjectDoesNotExist,
)
# Per-school apply failure in update_bundle_for_schools (log and continue).
_BLUEPRINT_APPLY_ERRORS = _BLUEPRINT_PACKAGE_ENGINE_ERRORS


def preview_blueprint_pack(school, pack) -> dict[str, Any]:
    """
    24.15: Preview what would be applied (policy keys, pack summary). No DB write.
    Returns dict with pack slug/name, policy_keys, current_bundle_id (if any).
    """
    from apps.policies.models import BlueprintPack, TenantBlueprint

    if not isinstance(pack, BlueprintPack):
        pack = (
            BlueprintPack.objects.get(slug=pack)
            if isinstance(pack, str)
            else BlueprintPack.objects.get(pk=pack)
        )
    snapshot = getattr(pack, "policy_snapshot", None) or {}
    policy_keys = list(snapshot.keys()) if isinstance(snapshot, dict) else []
    current_bundle_id = None
    if school:
        tb = (
            TenantBlueprint.objects.filter(school=school)
            .select_related("active_bundle")
            .first()
        )
        if tb and tb.active_bundle_id:
            current_bundle_id = tb.active_bundle_id
    # A premium pack previews normally but says so, so the caller can render
    # "requires entitlement" rather than offering an apply that will be refused.
    requires_entitlement = bool(getattr(pack, "is_premium_commercial", False))
    return {
        "pack_slug": getattr(pack, "slug", ""),
        "pack_name": getattr(pack, "name", ""),
        "pack_version": getattr(pack, "version", ""),
        "policy_keys": policy_keys,
        "current_bundle_id": current_bundle_id,
        "requires_entitlement": requires_entitlement,
        "entitlement_codes": premium_entitlement_codes(pack)
        if requires_entitlement
        else [],
        "entitlement_satisfied": (
            has_premium_entitlement(school, pack) if requires_entitlement else True
        ),
    }


def apply_blueprint_pack(school, pack, *, applied_by=None):
    """
    Apply a BlueprintPack to a school: create a PolicyBundle from pack.policy_snapshot,
    set TenantBlueprint.active_bundle to it, invalidate policy cache.
    Returns the created/updated PolicyBundle.
    """
    from apps.policies.models import BlueprintPack, PolicyBundle, TenantBlueprint
    from apps.policies.policy_registry import invalidate_policy_cache

    if not isinstance(pack, BlueprintPack):
        pack = (
            BlueprintPack.objects.get(slug=pack)
            if isinstance(pack, str)
            else BlueprintPack.objects.get(pk=pack)
        )
    if not pack.is_active:
        raise ValueError(f"Blueprint pack {pack.slug} is not active.")
    # Commercial gate. is_premium_commercial + list_price existed on the model with
    # no reader, so a self-signup POST of a paid pack's slug provisioned the tenant
    # onto it with no entitlement and no billing record. Refuse BEFORE any write.
    if getattr(pack, "is_premium_commercial", False) and not has_premium_entitlement(
        school, pack
    ):
        raise EntitlementRequired(
            f"Blueprint pack {pack.slug} is premium commercial and requires one of "
            f"{premium_entitlement_codes(pack)} for this school."
        )

    bundle = PolicyBundle.objects.create(
        school=school,
        name=f"{pack.name} (applied)",
        policy_snapshot=dict(pack.policy_snapshot),
        version=1,
        applied_pack_version=getattr(pack, "version", "") or "",
        is_active=True,
        created_by=applied_by,
    )
    tb, _ = TenantBlueprint.objects.get_or_create(
        school=school,
        defaults={"active_bundle": bundle, "applied_pack": pack},
    )
    if tb.active_bundle_id != bundle.pk or tb.applied_pack_id != pack.pk:
        tb.active_bundle = bundle
        tb.applied_pack = pack
        tb.save(update_fields=["active_bundle", "applied_pack", "updated_at"])
    invalidate_policy_cache(school)
    # PackageEngine keeps Setup Studio and blueprint applies auditable.
    try:
        from apps.packages.engine import PackageEngine

        PackageEngine.apply_package(
            tenant_id=getattr(school, "id", None),
            package_id=getattr(pack, "slug", "") or str(pack.pk),
            version=getattr(pack, "version", "") or "1",
            payload_sections={
                "policy": dict(getattr(pack, "policy_snapshot", None) or {})
            },
            mode="production",
            actor_id=getattr(applied_by, "id", None) if applied_by else None,
        )
    except _BLUEPRINT_PACKAGE_ENGINE_ERRORS:
        log_exception_with_context(
            "apply_blueprint_pack: PackageEngine.apply_package skipped (do not fail blueprint apply)",
            school_id=getattr(school, "id", None),
            actor_id=getattr(applied_by, "id", None) if applied_by else None,
            extra={"pack_slug": getattr(pack, "slug", None)},
        )
    return bundle


def update_bundle_for_schools(pack, *, school_ids=None, applied_by=None):
    """
    Re-apply a BlueprintPack to schools that use it (e.g. when pack version increased).
    If school_ids is None, applies to all schools that have this pack applied and need update
    (active_bundle.applied_pack_version != pack.version).
    Returns list of (school, bundle) for each updated school.

    A school whose premium entitlement has lapsed raises ``EntitlementRequired``
    (a ValueError, so it is in ``_BLUEPRINT_APPLY_ERRORS``) and is skipped and logged
    rather than silently upgraded onto the paid pack again.
    """
    from apps.policies.models import BlueprintPack

    if not isinstance(pack, BlueprintPack):
        pack = (
            BlueprintPack.objects.get(slug=pack)
            if isinstance(pack, str)
            else BlueprintPack.objects.get(pk=pack)
        )
    if school_ids is not None:
        schools = pack.get_schools_using_this_pack().filter(pk__in=school_ids)
    else:
        schools = pack.get_schools_needing_update()
    result = []
    for school in schools:
        try:
            bundle = apply_blueprint_pack(school, pack, applied_by=applied_by)
            result.append((school, bundle))
        except _BLUEPRINT_APPLY_ERRORS as e:
            log_exception_with_context(
                "update_bundle_for_schools: apply_blueprint_pack skipped for school",
                school_id=getattr(school, "id", None),
                actor_id=getattr(applied_by, "id", None) if applied_by else None,
                extra={"pack_slug": getattr(pack, "slug", None), "error": str(e)},
            )
            continue
    return result
