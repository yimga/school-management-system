"""Separated fee label keys for platform vs tuition vs marketplace (SFDP 1467)."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

FEE_LABEL_KEYS = {
    "platform_saas": _("Platform software fee"),
    "tenant_tuition": _("Tuition and school fees"),
    "marketplace_split": _("Marketplace publisher share"),
    "processing": _("Payment processing"),
    "application_fee": _("Platform application fee"),
}


def fee_labels_for_locale(profile: dict | None) -> dict[str, str]:
    """Return str labels for templates (lazy translated at render time)."""
    _ = profile  # future: profile-specific vocabulary
    return {k: str(v) for k, v in FEE_LABEL_KEYS.items()}
