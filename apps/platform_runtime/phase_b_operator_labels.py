"""
Operator copy for Phase B snapshot diff (control plane).

Keys must match ``PHASE_B_SNAPSHOT_DOMAINS`` in ``phase_b_domain_snapshots`` (parity tests).
This module imports Django i18n; do not import it from ``verify_siteconfig_decomposition_depth``
(static loader).
"""

from __future__ import annotations

from typing import Any, Final

from django.utils.translation import gettext_lazy as _

from apps.platform_runtime.phase_b_domain_snapshots import PHASE_B_SNAPSHOT_DOMAINS

PHASE_B_DOMAIN_OPERATOR_LABELS: Final[dict[str, tuple[Any, Any]]] = {
    "design_studio": (
        _("Design Studio"),
        _("Studio themes, tokens, and authoring inputs mirrored from the slim tenant settings row."),
    ),
    "documents": (
        _("Documents"),
        _("Library defaults, media tagging, and document-adjacent integration hooks."),
    ),
    "global_registries": (
        _("Global registries"),
        _("Country, region, ministry, grading defaults, and locale anchors."),
    ),
    "marketplace_integrations": (
        _("Marketplace integrations"),
        _("SMS, email, WhatsApp, and related provider fields — snapshot JSON omits secrets."),
    ),
    "metadata_governance": (
        _("Metadata governance"),
        _("Field catalog and governance keys classified under this ownership slice."),
    ),
    "plans_entitlements": (
        _("Plans and entitlements"),
        _("Plan, billing, and currency-related defaults routed through this payload."),
    ),
    "preview_platform": (
        _("Preview platform"),
        _("Preview mode, tours, and staging-safe presentation toggles."),
    ),
    "reports": (
        _("Report platform"),
        _("Default report styles, PDF gates, grade-publish alignment, and download toggles."),
    ),
    "runtime_blueprints": (
        _("Runtime blueprints"),
        _("Dashboards, portal blocks, admission numbering, and blueprint-facing defaults."),
    ),
    "policies_rules": (
        _("Policies and features"),
        _("Portal flags, MFA, feature toggles, and compliance profile pointers — merged last."),
    ),
}


def phase_b_operator_card_text(domain: str) -> tuple[str, str]:
    """Resolve lazy labels for the active locale."""
    pair = PHASE_B_DOMAIN_OPERATOR_LABELS.get(domain)
    if not pair:
        return domain, ""
    return str(pair[0]), str(pair[1])


def assert_operator_labels_align_with_snapshot_domains() -> None:
    """Fail fast if snapshot domain list and label map drift."""
    snap = set(PHASE_B_SNAPSHOT_DOMAINS)
    labels = set(PHASE_B_DOMAIN_OPERATOR_LABELS)
    if snap != labels:
        missing = snap - labels
        extra = labels - snap
        raise AssertionError(
            f"PHASE_B_DOMAIN_OPERATOR_LABELS out of sync with PHASE_B_SNAPSHOT_DOMAINS: "
            f"missing={sorted(missing)!r} extra={sorted(extra)!r}"
        )
