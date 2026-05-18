"""Move 2 follow-up — accept JWT in addition to session auth.

The orchestration JSON API was originally session-only. For third-party callers
(school IT leads building integrations without a browser session) we accept
`Authorization: Bearer <jwt>` and resolve a user via the project's existing
SimpleJWT setup. SessionAuthentication callers continue to work unchanged.

Safety rules:

  - This helper authenticates the request but does NOT bypass any view's
    authorization checks. Tenant-scope filtering in `apps.orchestration.api`
    still runs on `request.user` and `request.school`.
  - JWT tokens are issued via the project's existing /api/auth/token/ endpoint
    (SimpleJWT) — no new credential storage.
"""

from __future__ import annotations

import functools
import logging

from django.http import JsonResponse

logger = logging.getLogger(__name__)


def _try_jwt_user(request):
    """Return a User if the request carries a valid JWT Authorization header."""

    header = (request.META.get("HTTP_AUTHORIZATION") or "").strip()
    if not header.lower().startswith("bearer "):
        return None
    try:
        from rest_framework_simplejwt.authentication import JWTAuthentication

        authenticator = JWTAuthentication()
        validated = authenticator.authenticate(request)
    except Exception as exc:
        logger.debug("JWT authenticate failed: %s", exc)
        return None
    if not validated:
        return None
    user, _token = validated
    return user


def accept_session_or_jwt(view_fn):
    """View decorator: if request.user is anonymous but a JWT is present, hydrate.

    Cheap and idempotent. Use BEFORE @login_required so login_required sees the
    JWT-resolved user. Returns 401 JSON if neither path produces an
    authenticated user.
    """

    @functools.wraps(view_fn)
    def wrapped(request, *args, **kwargs):
        if not getattr(request.user, "is_authenticated", False):
            jwt_user = _try_jwt_user(request)
            if jwt_user is not None and getattr(jwt_user, "is_authenticated", False):
                request.user = jwt_user
        if not getattr(request.user, "is_authenticated", False):
            return JsonResponse({"error": "authentication_required"}, status=401)
        return view_fn(request, *args, **kwargs)

    return wrapped
