"""
Tenant-facing payment readiness snapshot (catalog + campus policy).

Read-only helpers for UX and billing posture checks — does not alter installs or entitlements.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.finance.models import ComplianceProfile, TenantPaymentPolicy
from apps.finance.payment_fallback import select_fallback_chain
from apps.finance.payment_fallback_engine import MANUAL_FALLBACK_CODE, select_effective_rail
from apps.finance.regional_payment_profiles import (
    get_normalized_regional_profile,
    list_supported_country_codes,
)


def compute_payment_readiness(
    school,
    compliance_profile: ComplianceProfile | None,
) -> dict[str, Any]:
    """
    Return readiness tier and checklist copy for operators.

    ``READY``: corridor catalog matches campus RegionPaymentProfile linkage.
    ``MISSING_SETUP``: unknown country or missing corridor catalog row.
    ``FALLBACK_ONLY``: catalog guidance exists but campus rails not linked or mismatched ISO.
    """
    cc = (
        str(compliance_profile.country_code).strip().upper()[:8]
        if compliance_profile and compliance_profile.country_code
        else None
    )
    catalog = get_normalized_regional_profile(cc)
    currency = (
        getattr(compliance_profile, "currency_code", None) if compliance_profile else None
    )

    policy = (
        TenantPaymentPolicy.objects.select_related("region_profile").filter(
            school=school
        ).first()
        if school is not None
        else None
    )

    checklist: list[dict[str, Any]] = []

    # Country example list now sourced from CountryRegistry (registry-driven, not hardcoded).
    # Falls back to a translatable generic string when the registry has not been seeded yet.
    if not cc:
        try:
            from apps.registries.models import CountryRegistry

            _sample_country_names = list(
                CountryRegistry.objects.filter(is_active=True)
                .order_by("name")
                .values_list("name", flat=True)[:6]
            )
        except Exception:
            _sample_country_names = []
        if _sample_country_names:
            _country_detail = str(_("Choose your country (e.g. {examples}).").format(
                examples=", ".join(_sample_country_names)
            ))
        else:
            _country_detail = str(_("Choose your country on the compliance profile."))
    else:
        _country_detail = cc
    checklist.append(
        {
            "id": "country",
            "label": "School country on finance profile",
            "done": bool(cc),
            "detail": _country_detail,
        }
    )

    checklist.append(
        {
            "id": "catalog",
            "label": "Regional corridor catalog entry",
            "done": catalog is not None,
            "detail": (
                f"Primary {catalog.get('primary_rail')} · Backup {catalog.get('backup_rail')}"
                if catalog
                else "Country not yet mapped — pick a supported corridor."
            ),
        }
    )

    rp_cc = (
        str(policy.region_profile.country_code).strip().upper()
        if policy and policy.region_profile_id
        else None
    )
    linked_ok = bool(cc and rp_cc and rp_cc == cc)

    checklist.append(
        {
            "id": "rails",
            "label": "Campus rails linked (Region Payment Profile)",
            "done": linked_ok,
            "detail": (
                "Finance admin has linked primary + backup rails for this ISO."
                if linked_ok
                else "Open Tenant Payment Policy and attach the Region Payment Profile."
            ),
        }
    )

    manual_allowed = bool(policy.allow_manual_offline_proof) if policy else True
    checklist.append(
        {
            "id": "manual",
            "label": "Manual / offline receipt capture policy",
            "done": manual_allowed,
            "detail": (
                "Receipt capture enabled for outages."
                if manual_allowed
                else "Manual offline proof disabled — enable if operators expect outages."
            ),
        }
    )

    status = "MISSING_SETUP"
    headline = "Finish payment setup"
    subhead = (
        "Pick a supported country on your compliance profile so guardians see clear instructions."
        if not catalog
        else "Link campus rails so recommended methods match what cashiers collect."
    )

    if not catalog:
        pass
    elif school is None:
        status = "FALLBACK_ONLY"
        headline = "Guidance ready — open from a school workspace"
        subhead = (
            "Corridor hints are available; switch into your tenant admin context "
            "to link rails."
        )
    elif linked_ok:
        status = "READY"
        headline = "Payments ready"
        subhead = (
            f"Recommended methods — primary {catalog.get('primary_rail')}, "
            f"backup {catalog.get('backup_rail')}."
        )
    else:
        status = "FALLBACK_ONLY"
        headline = "Guidance ready — campus rails incomplete"
        subhead = (
            "Families still see corridor hints; finish Tenant Payment Policy linkage "
            "before counting gateways live."
        )

    simulated_chain = select_fallback_chain(cc)
    avail = {r: False for r in simulated_chain} if simulated_chain else {}
    degraded = select_effective_rail(cc, avail)

    return {
        "status": status,
        "headline": headline,
        "subhead": subhead,
        "country_code": cc,
        "currency_code": currency,
        "catalog_label": catalog.get("label") if catalog else None,
        "recommended_primary_rail": catalog.get("primary_rail") if catalog else None,
        "recommended_backup_rail": catalog.get("backup_rail") if catalog else None,
        "provider_notes": catalog.get("provider_notes") if catalog else "",
        "operator_setup_steps": catalog.get("operator_setup_steps") if catalog else [],
        "checklist": checklist,
        "tenant_payment_policy_linked": linked_ok,
        "manual_offline_proof_allowed": manual_allowed,
        "supported_country_codes_sample": list_supported_country_codes(),
        "drill_manual_if_all_rails_down": degraded.get("selected_rail")
        == MANUAL_FALLBACK_CODE,
    }


def readiness_for_marketplace_entitlement_context(
    school,
    compliance_profile: ComplianceProfile | None = None,
) -> dict[str, Any]:
    """
    Narrow snapshot marketplace code may surface alongside entitlements (read-only).

    Does not imply processor onboarding completion — external PSP gaps stay tenant-owned.
    Pass ``compliance_profile`` when known; otherwise first active profile is a weak fallback.
    """
    profile = compliance_profile or ComplianceProfile.objects.filter(is_active=True).first()
    snap = compute_payment_readiness(school, profile)
    return {
        "payment_readiness_status": snap["status"],
        "payment_country_code": snap.get("country_code"),
        "payment_catalog_ready": snap["status"] != "MISSING_SETUP",
    }
