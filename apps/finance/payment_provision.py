"""
Bind TenantPaymentPolicy from school country at provision time (SFDP 1422).
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

logger = logging.getLogger(__name__)


def _resolve_country_iso2(school) -> str:
    code = ""
    try:
        code = (school.canonical_country_code() or "").strip().upper()
    except (AttributeError, TypeError, ValueError):
        code = str(getattr(school, "country_code", "") or "").strip().upper()
    if len(code) == 2:
        return code
    region_id = str(getattr(school, "default_region_id", "") or "").strip().upper()
    if len(region_id) == 2:
        return region_id
    return ""


def bind_tenant_payment_policy_for_school(school) -> dict[str, Any]:
    """
    Idempotent: ensure RegionPaymentProfile + TenantPaymentPolicy for school's ISO2.
    """
    from apps.finance.models import RegionPaymentProfile, TenantPaymentPolicy
    from apps.finance.payment_region_catalog import (
        CANONICAL_PAYMENT_ORCHESTRATION_ISO2,
        ensure_canonical_region_payment_profiles,
    )

    if school is None or not getattr(school, "pk", None):
        return {"bound": False, "reason": "no_school"}

    iso2 = _resolve_country_iso2(school)
    if not iso2:
        return {"bound": False, "reason": "no_country_iso2"}

    ensure_canonical_region_payment_profiles()

    if iso2 not in CANONICAL_PAYMENT_ORCHESTRATION_ISO2:
        return {"bound": False, "reason": "country_not_in_catalog", "iso2": iso2}

    profile = RegionPaymentProfile.objects.filter(country_code=iso2).first()
    if profile is None:
        return {"bound": False, "reason": "no_region_profile", "iso2": iso2}

    with transaction.atomic():
        policy, created = TenantPaymentPolicy.objects.get_or_create(
            school=school,
            defaults={
                "region_profile": profile,
                "allow_manual_offline_proof": True,
                "simplicity_big_buttons": True,
            },
        )
        if not created and policy.region_profile_id != profile.pk:
            policy.region_profile = profile
            policy.save(update_fields=["region_profile"])

    primary = profile.primary_rail.code if profile.primary_rail_id else ""
    backup = profile.backup_rail.code if profile.backup_rail_id else ""
    return {
        "bound": True,
        "created": created,
        "iso2": iso2,
        "primary_rail": primary,
        "backup_rail": backup,
    }


def bind_tenant_payment_policy_safe(school) -> None:
    """Best-effort wrapper for provisioning — never raises."""
    try:
        result = bind_tenant_payment_policy_for_school(school)
        if result.get("bound"):
            logger.info(
                "TenantPaymentPolicy bound school_id=%s iso2=%s primary=%s",
                getattr(school, "pk", None),
                result.get("iso2"),
                result.get("primary_rail"),
            )
    except Exception:
        logger.exception(
            "bind_tenant_payment_policy_for_school failed school_id=%s",
            getattr(school, "pk", None),
        )
