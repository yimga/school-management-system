"""Shared helpers for the Migration Cloud REST API.

The viewsets here delegate to the existing wizard view classes in
``apps.migration_cloud.views`` so we don't duplicate business logic.
The pattern: instantiate the wizard view, swap the URL kwarg ``shell``
to "super" for staff or "portal" for tenant callers, and call the
view's ``post`` method directly.

This module owns the thin composition surface. Wizard views stay
untouched (per file-boundary directive in the agent brief).
"""

from __future__ import annotations

import logging

from django.http import HttpRequest

logger = logging.getLogger(__name__)


def shell_for_request(request: HttpRequest) -> str:
    """Return the wizard ``shell`` kwarg matching this request.

    Only a GENUINE platform operator (control-plane access on the manager/local
    host) lands in the cross-tenant operator shell ("super"); everyone else —
    including an ``is_staff=True`` tenant admin on their own subdomain — lands in
    the tenant shell ("portal"), which forces the underlying view to match the
    bundle to the caller's own school. Keying "super" on bare ``is_staff`` let a
    tenant admin drive a cross-tenant apply/advance/reconcile; use the same
    predicate the API permission class enforces so all three agree.
    """
    from .permissions import _is_operator_shell_request

    if _is_operator_shell_request(request):
        return "super"
    return "portal"


def delegate_to_view(view_cls, request, **kwargs):
    """Instantiate the wizard view class and call its ``post`` method.

    Centralizes the delegation pattern so the action methods on the
    viewset stay one-liners. The wizard view's own decorators
    (``@idempotent_post`` + ``@safe_500``) still fire inside the call,
    so reliability semantics carry through to the API layer without
    re-wiring.

    DRF passes a ``rest_framework.request.Request`` wrapping the underlying
    Django ``HttpRequest``. The wizard view + reliability decorators are
    Django-native and key on ``isinstance(_, HttpRequest)``, so we unwrap
    via ``request._request`` when present.
    """
    inner_request = getattr(request, "_request", request)
    instance = view_cls()
    return instance.post(inner_request, **kwargs)
