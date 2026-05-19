"""AppVersion service helpers.

Publish a new version of a MarketplaceApp, list available versions, and
resolve a tenant's install target ("latest stable", a pinned semver, etc).
"""

from __future__ import annotations


from django.db import transaction
from django.utils import timezone

from apps.marketplace.models import AppVersion, MarketplaceApp
from functools import cmp_to_key

from apps.marketplace.semver_utils import compare_semver, parse_semver


def list_versions(
    app: MarketplaceApp,
    *,
    channel: str | None = None,
    include_yanked: bool = False,
) -> list[AppVersion]:
    qs = AppVersion.objects.filter(app=app, is_published=True)
    if channel:
        qs = qs.filter(channel=channel)
    if not include_yanked:
        qs = qs.filter(is_yanked=False)
    rows = list(qs)
    rows.sort(
        key=cmp_to_key(lambda a, b: compare_semver(a.version, b.version)),
        reverse=True,
    )
    return rows


def latest_stable(app: MarketplaceApp) -> AppVersion | None:
    rows = list_versions(app, channel=AppVersion.Channel.STABLE)
    return rows[0] if rows else None


@transaction.atomic
def publish_version(
    app: MarketplaceApp,
    *,
    version: str,
    channel: str = AppVersion.Channel.STABLE,
    changelog: str = "",
    manifest_snapshot: dict | None = None,
    migration_ref: str = "",
    published_by=None,
) -> AppVersion:
    """Publish a new version. Marks the AppVersion row as published and updates
    `MarketplaceApp.version` to this string when the new version is the highest
    stable release."""

    if not parse_semver(version):
        raise ValueError(f"Invalid semver: {version!r}")
    av, _ = AppVersion.objects.update_or_create(
        app=app,
        version=version,
        defaults={
            "channel": channel,
            "changelog": changelog,
            "manifest_snapshot": manifest_snapshot or dict(app.manifest or {}),
            "migration_ref": migration_ref,
            "is_published": True,
            "published_at": timezone.now(),
            "published_by": published_by if (published_by and getattr(published_by, "is_authenticated", False)) else None,
        },
    )
    # Update MarketplaceApp.version if this is the new highest stable.
    if channel == AppVersion.Channel.STABLE:
        latest = latest_stable(app)
        if latest and latest.version != app.version:
            app.version = latest.version
            app.save(update_fields=["version", "updated_at"])
    return av


def yank_version(av: AppVersion, *, reason: str = "") -> AppVersion:
    av.is_yanked = True
    av.yanked_reason = reason[:255]
    av.save(update_fields=["is_yanked", "yanked_reason"])
    return av


def resolve_install_version(
    app: MarketplaceApp,
    *,
    requested: str | None = None,
) -> AppVersion | None:
    """Return the AppVersion that should be installed.

    If `requested` is given, return that exact version (must be published, not yanked).
    Otherwise return the latest_stable.
    """

    if requested:
        return (
            AppVersion.objects.filter(
                app=app, version=requested, is_published=True, is_yanked=False
            )
            .first()
        )
    return latest_stable(app)
