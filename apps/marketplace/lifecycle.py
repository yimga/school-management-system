"""
Install / upgrade / downgrade / rollback using semver ordering on ``MarketplaceApp.version``.
Hooks append audit rows; HTTP hook URLs are recorded but not fetched here (async delivery later).
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.marketplace.models import (
    AppAuditLog,
    AppInstallation,
    AppScope,
    MarketplaceApp,
    ScopeGrant,
)
from apps.marketplace.semver_utils import compare_semver


def missing_dependencies(
    school_id: Any, app: MarketplaceApp
) -> list[str]:
    """Return ``app_key`` list from ``required_apps`` not installed (active) on this tenant."""
    required = list(app.required_apps or [])
    if not required:
        return []
    installed = set(
        AppInstallation.objects.filter(
            school_id=school_id,
            status=AppInstallation.Status.ACTIVE,
        ).values_list("app__app_key", flat=True)
    )
    missing = []
    for key in required:
        k = str(key).strip()
        if k and k not in installed:
            missing.append(k)
    return missing


@transaction.atomic
def install_app(
    *,
    school,
    app: MarketplaceApp,
    actor=None,
    grant_scope_codes: list[str] | None = None,
) -> AppInstallation:
    """Create installation, optional scope grants, semver stamp, install hooks audit."""
    missing = missing_dependencies(school.id, app)
    if missing:
        raise ValueError(f"Missing required apps: {missing}")

    from apps.marketplace.extension_registry import validate_marketplace_app_manifest

    manifest = app.manifest if isinstance(app.manifest, dict) else {}
    ok, manifest_errors = validate_marketplace_app_manifest(manifest)
    if not ok:
        raise ValueError(
            "Invalid marketplace extension manifest: " + "; ".join(manifest_errors)
        )

    inst, created = AppInstallation.objects.get_or_create(
        school=school,
        app=app,
        defaults={
            "status": AppInstallation.Status.ACTIVE,
            "installed_version": app.version,
            "config": {},
        },
    )
    if not created:
        raise ValueError("App already installed; use upgrade_app instead.")

    codes = grant_scope_codes or []
    for code in codes:
        scope, _ = AppScope.objects.get_or_create(
            app=app,
            scope_code=code,
            defaults={"description": ""},
        )
        ScopeGrant.objects.get_or_create(
            installation=inst,
            scope=scope,
            defaults={
                "status": ScopeGrant.GrantStatus.GRANTED,
                "granted_by": actor,
            },
        )

    from apps.marketplace.install_hook_delivery import dispatch_install_hooks

    dispatch_install_hooks(inst, app, "install", app.install_hooks or [], actor=actor)
    AppAuditLog.objects.create(
        school=school,
        app=app,
        installation=inst,
        action="marketplace.install",
        payload={"version": app.version},
        actor=actor,
    )
    # Align with services.install_app: billing account + TenantMarketplaceSubscription + ledger
    from apps.marketplace.services import ensure_marketplace_listing
    from apps.marketplace.monetization import apply_marketplace_install_monetization

    listing = ensure_marketplace_listing(app)
    apply_marketplace_install_monetization(
        school=school, app=app, installation=inst, listing=listing
    )
    return inst


@transaction.atomic
def upgrade_app(
    *,
    installation: AppInstallation,
    target: MarketplaceApp,
    actor=None,
) -> AppInstallation:
    if installation.app_id != target.id:
        raise ValueError("target MarketplaceApp must match installation.app")
    cur = installation.installed_version or ""
    nxt = target.version
    if compare_semver(nxt, cur) < 0:
        raise ValueError("upgrade requires semver greater than installed_version")

    installation.installed_version = nxt
    installation.status = AppInstallation.Status.ACTIVE
    installation.save(update_fields=["installed_version", "status"])
    from apps.marketplace.install_hook_delivery import dispatch_install_hooks

    dispatch_install_hooks(
        installation, target, "upgrade", target.install_hooks or [], actor=actor
    )
    AppAuditLog.objects.create(
        school=installation.school,
        app=target,
        installation=installation,
        action="marketplace.upgrade",
        payload={"from": cur, "to": nxt},
        actor=actor,
    )
    return installation


@transaction.atomic
def downgrade_app(
    *,
    installation: AppInstallation,
    target_version: str,
    actor=None,
) -> AppInstallation:
    cur = installation.installed_version or installation.app.version
    if compare_semver(target_version, cur) >= 0:
        raise ValueError("downgrade target must be semver lower than current")
    installation.installed_version = target_version
    installation.save(update_fields=["installed_version"])
    AppAuditLog.objects.create(
        school=installation.school,
        app=installation.app,
        installation=installation,
        action="marketplace.downgrade",
        payload={"from": cur, "to": target_version},
        actor=actor,
    )
    return installation


@transaction.atomic
def rollback_app(
    *,
    installation: AppInstallation,
    previous_version: str,
    actor=None,
) -> AppInstallation:
    """Restore ``installed_version`` to a prior semver (operator-selected)."""
    installation.installed_version = previous_version
    installation.save(update_fields=["installed_version"])
    AppAuditLog.objects.create(
        school=installation.school,
        app=installation.app,
        installation=installation,
        action="marketplace.rollback",
        payload={"restored": previous_version, "at": timezone.now().isoformat()},
        actor=actor,
    )
    return installation


def _record_hooks(
    installation: AppInstallation,
    app: MarketplaceApp,
    phase: str,
    hooks: list[Any],
) -> None:
    if not hooks:
        return
    AppAuditLog.objects.create(
        school=installation.school,
        app=app,
        installation=installation,
        action=f"marketplace.hook.{phase}",
        payload={"hooks": hooks},
        actor=None,
    )


def emit_webhook_audit(
    installation: AppInstallation,
    event_type: str,
    payload: dict,
    *,
    actor=None,
) -> AppAuditLog:
    """Simulate webhook trigger recording (delivery pipeline can consume audit rows)."""
    return AppAuditLog.objects.create(
        school=installation.school,
        app=installation.app,
        installation=installation,
        action=f"marketplace.webhook.{event_type}",
        payload=payload,
        actor=actor,
    )
