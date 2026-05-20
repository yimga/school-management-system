"""One-page country annex for security packet requests (procurement preview)."""

from __future__ import annotations

from typing import Any

from django.apps import apps as django_apps

# Static fallbacks when finance.ComplianceProfile rows are absent (e.g. fresh dev DB).
_COUNTRY_ANNEX_PRESETS: dict[str, dict[str, str]] = {
    "CM": {
        "profile_name": "Cameroon — OHADA baseline",
        "currency_code": "XAF",
        "timezone": "Africa/Douala",
        "retention_summary": "Student records retained per school policy; export and DSAR workflows documented in security packet.",
        "calendar_note": "Francophone term structures and ministry reporting rhythms supported via tenant configuration.",
    },
    "CA": {
        "profile_name": "Canada — provincial baseline",
        "currency_code": "CAD",
        "timezone": "America/Toronto",
        "retention_summary": "PIPEDA-oriented processor posture; provincial variance called out in contract addenda.",
        "calendar_note": "Province-aligned report cards and academic calendars configure per campus.",
    },
    "NG": {
        "profile_name": "Nigeria — regional baseline",
        "currency_code": "NGN",
        "timezone": "Africa/Lagos",
        "retention_summary": "NDPR-aligned data-handling notes; retention schedules configurable per tenant.",
        "calendar_note": "WAEC-oriented grading and bursar workflows supported without a separate product fork.",
    },
    "GB": {
        "profile_name": "United Kingdom — academy baseline",
        "currency_code": "GBP",
        "timezone": "Europe/London",
        "retention_summary": "UK GDPR processor posture; retention and subject-access workflows documented.",
        "calendar_note": "UK term dates and assessment scales configure per school or trust.",
    },
    "US": {
        "profile_name": "United States — FERPA baseline",
        "currency_code": "USD",
        "timezone": "America/New_York",
        "retention_summary": "FERPA school-as-controller framing; state privacy addenda (e.g. NY Ed Law § 2-d) available on request.",
        "calendar_note": "District calendars and grading scales configure per campus.",
    },
    "ZA": {
        "profile_name": "South Africa — POPIA baseline",
        "currency_code": "ZAR",
        "timezone": "Africa/Johannesburg",
        "retention_summary": "POPIA-aware defaults; cross-border transfers documented when groups span regions.",
        "calendar_note": "Multi-campus groups keep local fee and calendar rules per campus.",
    },
    "GH": {
        "profile_name": "Ghana — regional baseline",
        "currency_code": "GHS",
        "timezone": "Africa/Accra",
        "retention_summary": "Retention and export tooling aligned to school-as-controller operations.",
        "calendar_note": "Local academic calendar and fee models per campus.",
    },
    "KE": {
        "profile_name": "Kenya — regional baseline",
        "currency_code": "KES",
        "timezone": "Africa/Nairobi",
        "retention_summary": "Retention schedules and audit exports configurable per tenant.",
        "calendar_note": "CBC-oriented operations supported via tenant grading configuration.",
    },
}


def _lookup_compliance_profile(country_code: str) -> dict[str, Any] | None:
    code = (country_code or "").strip().upper()[:2]
    if not code:
        return None
    try:
        ComplianceProfile = django_apps.get_model("finance", "ComplianceProfile")
    except LookupError:
        return None
    try:
        profile = (
            ComplianceProfile.objects.filter(country_code=code, is_active=True)
            .order_by("name")
            .first()
        )
    except Exception:
        return None
    if not profile:
        return None
    return {
        "compliance_profile_id": profile.pk,
        "profile_name": profile.name,
        "currency_code": profile.currency_code,
        "timezone": profile.timezone,
        "retention_summary": (
            f"Active finance.ComplianceProfile #{profile.pk} — "
            "retention and export follow tenant policy plus processor DPA."
        ),
        "calendar_note": (
            f"Chart template {profile.chart_template}; "
            "academic calendar lands in tenant SiteSettings."
        ),
    }


def build_country_annex(*, country_code: str, compliance_profile_id: str = "") -> dict[str, Any]:
    """
    Build a one-page annex dict for procurement preview.

    Prefer live ComplianceProfile row when present; otherwise static preset.
    Optional ``compliance_profile_id`` from form overrides lookup when valid.
    """
    code = (country_code or "").strip().upper()[:2]
    annex: dict[str, Any] = {
        "country_code": code or "",
        "compliance_profile_id": "",
        "profile_name": "Global platform defaults",
        "currency_code": "USD",
        "timezone": "UTC",
        "retention_summary": (
            "Retention schedules are tenant-configurable; "
            "processor DPA and subprocessors listed in the full security packet."
        ),
        "calendar_note": (
            "Academic calendar, grading model, and fee rules configure per campus—"
            "no per-country product fork."
        ),
        "data_residency_note": (
            "Deployment region and subprocessors are confirmed in the signed security packet "
            "and contract—not inferred from marketing pages."
        ),
        "illustrative": False,
    }

    profile_row = None
    if compliance_profile_id:
        try:
            pk = int(str(compliance_profile_id).strip())
            ComplianceProfile = django_apps.get_model("finance", "ComplianceProfile")
            profile_row = ComplianceProfile.objects.filter(pk=pk, is_active=True).first()
        except (TypeError, ValueError, LookupError):
            profile_row = None
        if profile_row:
            annex.update(
                {
                    "country_code": profile_row.country_code,
                    "compliance_profile_id": str(profile_row.pk),
                    "profile_name": profile_row.name,
                    "currency_code": profile_row.currency_code,
                    "timezone": profile_row.timezone,
                    "retention_summary": (
                        f"Selected profile #{profile_row.pk} ({profile_row.country_code}) — "
                        "retention/export in full packet."
                    ),
                    "calendar_note": f"Chart template {profile_row.chart_template}.",
                }
            )
            return annex

    if code:
        live = _lookup_compliance_profile(code)
        if live:
            annex.update(live)
            return annex
        preset = _COUNTRY_ANNEX_PRESETS.get(code)
        if preset:
            annex.update(preset)
            annex["illustrative"] = True
            return annex

    annex["illustrative"] = True
    return annex


def jurisdiction_choices() -> list[dict[str, str]]:
    """Options for security packet + demo forms (value, label)."""
    return [
        {"value": "ferpa-us", "label": "FERPA (United States)", "country_code": "US"},
        {"value": "gdpr-uk", "label": "UK GDPR", "country_code": "GB"},
        {"value": "gdpr-eu", "label": "GDPR (EU/EEA)", "country_code": ""},
        {"value": "popia-za", "label": "POPIA (South Africa)", "country_code": "ZA"},
        {"value": "ndpr-ng", "label": "Nigeria NDPR", "country_code": "NG"},
        {"value": "pipeda-ca", "label": "PIPEDA / Canada", "country_code": "CA"},
        {"value": "cm-francophone", "label": "Cameroon / Francophone Africa", "country_code": "CM"},
        {"value": "gh", "label": "Ghana", "country_code": "GH"},
        {"value": "ke", "label": "Kenya", "country_code": "KE"},
        {"value": "other", "label": "Other / multiple jurisdictions", "country_code": ""},
    ]


def country_code_for_jurisdiction(value: str) -> str:
    token = (value or "").strip().lower()
    for row in jurisdiction_choices():
        if row["value"] == token:
            return (row.get("country_code") or "").upper()[:2]
    return ""
