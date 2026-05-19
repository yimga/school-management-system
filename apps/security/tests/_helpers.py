"""Shared helpers for security enforcement tests (avoid SQLite lock on get_or_create)."""

from __future__ import annotations

from apps.accounts.models import Permission as FeaturePermission


def settings_manage_permission() -> FeaturePermission:
    """Read-first to avoid concurrent get_or_create locks on keepdb runs."""
    perm = FeaturePermission.objects.filter(code="settings.manage").only("pk").first()
    if perm is not None:
        return perm
    return FeaturePermission.objects.create(
        code="settings.manage",
        name="Manage settings",
    )
