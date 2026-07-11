"""Signals that make RBAC / authority changes propagate in real time.

Server-side a change already takes effect on the user's next request
(``has_feature_permission`` reads grants live). These signals close the two
residual gaps:

* the 60s ``get_effective_site_settings`` config cache (feature-flag-derived
  config), by bumping its version key, and
* an already-open browser showing stale nav, by pushing an ``access_changed``
  event to the affected user's own real-time rooms.

Every authority surface is covered: the Django flags + primary role (``User``
post_save, field-diffed so an ordinary ``last_login`` write never fires a push),
the granular AccessRole grants (``User.roles`` m2m_changed), and direct feature
permissions (``User.feature_permissions`` m2m_changed) — the exact fields the
tenant RBAC console (``rbac_dashboard``) and the operator promotion path write.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

User = get_user_model()

# Authority-bearing scalar fields whose change must propagate live.
_AUTHORITY_FIELDS = ("is_superuser", "is_staff", "role")


def _propagate(user, reason: str) -> None:
    """Invalidate derived caches + live-push the access change. Best-effort."""
    try:
        from apps.platform_runtime.helpers import (
            invalidate_effective_site_settings_cache,
        )

        invalidate_effective_site_settings_cache()
    except Exception as exc:  # noqa: BLE001 — cache invalidation is best-effort
        logger.debug("effective-settings invalidation skipped: %s", exc)
    try:
        from apps.accounts.access_realtime import push_access_changed_realtime

        push_access_changed_realtime(user, reason=reason)
    except Exception as exc:  # noqa: BLE001 — realtime push is best-effort
        logger.debug("access-changed push skipped: %s", exc)


@receiver(pre_save, sender=User)
def _snapshot_authority(sender, instance, update_fields=None, **kwargs):
    """Record whether an authority-bearing field changed, for ``post_save``.

    Skips the DB read entirely for an ``update_fields`` write that cannot touch an
    authority field (e.g. Django's ``last_login`` update on every login), so the
    common case adds no query.
    """
    if not instance.pk:
        instance._rbac_authority_changed = True  # new row — nothing to diff
        return
    if update_fields is not None and not (set(update_fields) & set(_AUTHORITY_FIELDS)):
        instance._rbac_authority_changed = False
        return
    try:
        old = (
            sender.objects.filter(pk=instance.pk).values(*_AUTHORITY_FIELDS).first()
        )
    except Exception:  # noqa: BLE001 — diff is best-effort; assume changed
        instance._rbac_authority_changed = True
        return
    if old is None:
        instance._rbac_authority_changed = True
        return
    instance._rbac_authority_changed = any(
        old.get(f) != getattr(instance, f, None) for f in _AUTHORITY_FIELDS
    )


@receiver(post_save, sender=User)
def _on_user_saved(sender, instance, created, **kwargs):
    # A brand-new user has no already-open session to refresh; skip.
    if created:
        return
    if getattr(instance, "_rbac_authority_changed", False):
        _propagate(instance, reason="authority")


def _on_user_m2m_changed(sender, instance, action, **kwargs):
    """Grant/revoke of AccessRole or feature-permission on a User -> propagate.

    Only the forward direction (``user.roles.set(...)`` / the tenant RBAC console's
    write path) is handled: there ``instance`` is the ``User``. A reverse write from
    the AccessRole side sets ``instance`` to the role and is not the console path.
    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if isinstance(instance, User):
        _propagate(instance, reason="roles")


m2m_changed.connect(_on_user_m2m_changed, sender=User.roles.through)
m2m_changed.connect(_on_user_m2m_changed, sender=User.feature_permissions.through)
