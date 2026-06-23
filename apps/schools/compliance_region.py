"""Derive a tenant's data-protection compliance regime from its country (local-first).

``School.compliance_region`` (GDPR / FERPA / NDPR) gates data masking, retention, and
consent flows, but signup never set it — every new tenant defaulted to NONE, so a school
in the EU or Nigeria silently got no regime. This maps a country to the regime we
actually implement; everything else stays unset (the operator can pick one explicitly).

Return values match ``School.ComplianceRegion`` choice values ("EU" / "US" / "NDPR" / "").
"""

from __future__ import annotations

# EU/EEA members + the UK (UK GDPR is GDPR-equivalent) → "EU" (GDPR).
_GDPR_COUNTRIES = frozenset(
    {
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
        "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
        "SI", "ES", "SE",
        "IS", "LI", "NO",  # EEA
        "GB",  # UK GDPR
    }
)
_FERPA_COUNTRIES = frozenset({"US"})
_NDPR_COUNTRIES = frozenset({"NG"})


def derive_compliance_region(country_code: str | None) -> str:
    """Return the ``School.ComplianceRegion`` value for a country, or "" when none applies."""
    cc = (country_code or "").strip().upper()
    if cc in _GDPR_COUNTRIES:
        return "EU"
    if cc in _FERPA_COUNTRIES:
        return "US"
    if cc in _NDPR_COUNTRIES:
        return "NDPR"
    return ""
