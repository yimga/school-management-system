"""Pillar 3 — Verified Communications: institutional stamp tag.

Renders a small "Verified <tenant>" badge next to a notification
when — and only when — the notification's owning tenant matches the
authenticated tenant on the current request. The check is structural
(``notification.school_id == request.school.id``), not cryptographic;
the value is in eliminating the visual ambiguity that today lets a
cross-tenant push or a renderer-side injection masquerade as an
admin alert.

Failure modes the tag must handle gracefully (return empty string,
never raise):

* ``request`` missing from the template context (e.g. tag rendered
  in an email or background-task render).
* ``request.school`` is ``None`` (anonymous user, login page,
  marketing surface).
* ``notification`` lacks a ``school_id`` (legacy rows or models
  without a school FK — the platform's
  ``apps.finance.models.Notification`` is one such case).
* ``notification`` is ``None`` (defensive: regroup loops can hand a
  null group head).
"""

from __future__ import annotations

from typing import Any

from django import template
from django.template.loader import render_to_string

register = template.Library()


def _safe_attr(obj: Any, name: str) -> Any:
    """getattr that swallows AttributeError + DoesNotExist style misses."""
    try:
        return getattr(obj, name, None)
    except Exception:  # noqa: BLE001 — defensive template-time access
        return None


def _tenant_id_from_request(request: Any) -> Any:
    """Resolve the active tenant id from request.school (preferred) or request.tenant."""
    if request is None:
        return None
    school = _safe_attr(request, "school")
    if school is not None:
        sid = _safe_attr(school, "id") or _safe_attr(school, "pk")
        if sid is not None:
            return sid
    # Fallback: some surfaces stash the tenant on request.tenant.
    tenant = _safe_attr(request, "tenant")
    if tenant is not None:
        return _safe_attr(tenant, "id") or _safe_attr(tenant, "pk")
    return None


def _tenant_name_from_request(request: Any) -> str:
    school = _safe_attr(request, "school") or _safe_attr(request, "tenant")
    if school is None:
        return ""
    for attr in ("display_name", "name", "site_name", "short_name"):
        val = _safe_attr(school, attr)
        if val:
            return str(val)
    return ""


def _notification_school_id(notification: Any) -> Any:
    if notification is None:
        return None
    sid = _safe_attr(notification, "school_id")
    if sid is not None:
        return sid
    school = _safe_attr(notification, "school")
    if school is not None:
        return _safe_attr(school, "id") or _safe_attr(school, "pk")
    return None


@register.simple_tag(takes_context=True)
def institutional_stamp(context, notification) -> str:
    """Render the inline "Verified <tenant>" stamp, or empty string.

    The tag MUST never raise — notifications loops render dozens of
    rows, and a single broken row would blow up the entire inbox.
    """
    try:
        request = context.get("request") if hasattr(context, "get") else None
        tenant_id = _tenant_id_from_request(request)
        if tenant_id is None:
            return ""
        notif_school_id = _notification_school_id(notification)
        if notif_school_id is None:
            return ""
        # Compare as strings so int / UUID / str FKs all match cleanly.
        if str(tenant_id) != str(notif_school_id):
            return ""
        tenant_name = _tenant_name_from_request(request)
        # Intentionally NOT passing ``request=request`` — the partial
        # consumes only ``tenant_name``, and threading the request would
        # re-trigger every context processor (DB hits, locale resolve,
        # etc.) once per notification row in the inbox loop.
        return render_to_string(
            "partials/notifications/_institutional_stamp.html",
            {"tenant_name": tenant_name},
        )
    except Exception:  # noqa: BLE001 — never break a notification row
        return ""
