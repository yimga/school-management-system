"""Wave E scaffold — partner-published ExperienceTemplate manifest schema.

NOT a live partner-publishing pipeline. This module declares the SHAPE a
third-party-published ExperienceTemplate manifest MUST satisfy when Wave E+
counsel signoff unblocks the publishing pipeline. The validator here lets
partners self-check manifests today; the publishing surface itself is gated
behind ``RMC_TEMPLATE_PARTNER_PUBLISH_ENABLED`` (default False; counsel-pending).

See docs/TEMPLATE_MARKETPLACE_WAVE_E_COUNSEL_PENDING.md for the gates that
must clear before the gate flips.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


REQUIRED_FIELDS = (
    "manifest_version",
    "key",
    "name",
    "publisher",
    "publisher_verified_at",
    "category",
    "layout_family",
    "palette_family",
    "supported_countries",
    "supported_languages",
    "accessibility_level",
    "mobile_level",
    "version",
    "license",
    "preview_url",
    "code_signature",
)

ALLOWED_CATEGORIES = {
    "tenant-admin", "teacher", "parent", "student", "staff",
    "specialized", "local-first",
}

ALLOWED_LICENSES = {"MIT", "Apache-2.0", "BSD-3-Clause", "RMC-Partner-1.0"}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    findings: tuple[str, ...]
    manifest_version: str
    publisher: str
    key: str


def validate_partner_template_manifest(manifest: dict[str, Any]) -> ValidationResult:
    """Validate a partner-published ExperienceTemplate manifest.

    Partners ship a JSON manifest declaring the template metadata + a code
    signature. This function returns a typed ValidationResult — the publishing
    surface (Wave E+) refuses any manifest with findings.
    """
    findings: list[str] = []
    if not isinstance(manifest, dict):
        return ValidationResult(
            ok=False,
            findings=("manifest must be a JSON object",),
            manifest_version="",
            publisher="",
            key="",
        )

    for field in REQUIRED_FIELDS:
        if not manifest.get(field):
            findings.append(f"missing required field: {field}")

    category = str(manifest.get("category") or "").strip()
    if category and category not in ALLOWED_CATEGORIES:
        findings.append(
            f"category '{category}' not allowed for partner publish "
            f"(operator category reserved for platform-only templates)"
        )

    license_ = str(manifest.get("license") or "").strip()
    if license_ and license_ not in ALLOWED_LICENSES:
        findings.append(
            f"license '{license_}' not in approved set {sorted(ALLOWED_LICENSES)}"
        )

    layout_family = manifest.get("layout_family")
    if layout_family is not None and not (isinstance(layout_family, int) and 1 <= layout_family <= 10):
        findings.append("layout_family must be int in [1, 10]")

    countries = manifest.get("supported_countries")
    if countries is not None and not isinstance(countries, list):
        findings.append("supported_countries must be a list")

    accessibility = str(manifest.get("accessibility_level") or "").strip()
    if accessibility and accessibility not in {"AA", "AAA"}:
        findings.append(f"accessibility_level must be 'AA' or 'AAA' (partner floor); got {accessibility}")

    code_signature = str(manifest.get("code_signature") or "").strip()
    if code_signature and len(code_signature) < 64:
        findings.append("code_signature must be at least 64 hex chars (sha256 + sig material)")

    publisher_verified_at = str(manifest.get("publisher_verified_at") or "").strip()
    if publisher_verified_at and "T" not in publisher_verified_at:
        findings.append("publisher_verified_at must be ISO-8601 timestamp")

    # v4.00.12: wire the monetization sub-manifest validator. When the partner
    # manifest carries a top-level ``monetization`` object, validate it through
    # the dedicated kernel and merge findings. ``RMC_TEMPLATE_MONETIZATION_ENABLED``
    # remains the platform-level gate; this just guarantees that bad shapes
    # never sneak through as "valid" partner manifests.
    monetization_payload = manifest.get("monetization")
    if monetization_payload is not None:
        try:
            from apps.marketplace.template_monetization_manifest import (
                validate_monetization_manifest,
            )

            mz_result = validate_monetization_manifest(monetization_payload)
            if not mz_result.ok:
                for f in mz_result.findings:
                    findings.append(f"monetization: {f}")
        except Exception as exc:  # noqa: BLE001 — surface as a normal finding, never crash
            findings.append(f"monetization: validator unavailable ({exc})")

    return ValidationResult(
        ok=len(findings) == 0,
        findings=tuple(findings),
        manifest_version=str(manifest.get("manifest_version") or ""),
        publisher=str(manifest.get("publisher") or ""),
        key=str(manifest.get("key") or ""),
    )


def example_manifest() -> dict[str, Any]:
    """Return a worked-example manifest a partner can adapt.

    Useful as a doctest target and as developer-facing reference at
    docs/TEMPLATE_MARKETPLACE_WAVE_E_COUNSEL_PENDING.md.
    """
    return {
        "manifest_version": "1.0",
        "key": "partner-example-bilingual-private-secondary",
        "name": "Partner Example — Bilingual Private Secondary",
        "publisher": "example-partner.example.com",
        "publisher_verified_at": "2026-05-23T00:00:00Z",
        "category": "specialized",
        "layout_family": 10,
        "palette_family": "editorial-cream",
        "supported_countries": ["FR", "DE"],
        "supported_languages": ["fr", "de", "en"],
        "accessibility_level": "AA",
        "mobile_level": "responsive",
        "version": "1.0.0",
        "license": "Apache-2.0",
        "preview_url": "https://example-partner.example.com/rmc/templates/bilingual-private-secondary/preview",
        "code_signature": "a" * 128,
    }
