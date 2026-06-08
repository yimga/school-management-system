"""
RLS-first JWT tenant binding middleware (v4.00.0).

Mandate: bind every request to ``app.current_school_id`` via the existing
``apps.schools.rls_context.rls_school`` mechanic when a signed session JWT
asserts a tenant_id. This makes the database's FORCE ROW LEVEL SECURITY
policies (shipped in migrations 0002, 0026, 0048) the load-bearing
isolation contract — not application-layer ``WHERE school_id=...`` filters.

Anti-pattern killed:
  * Schema-per-tenant routing churn for the JWT-authenticated request path.
  * Trusting ``request.session`` to carry tenant id without a cryptographic seal.

Wire order (config/settings.py MIDDLEWARE):
  Place AFTER ``apps.schools.middleware.SessionSchoolBindingMiddleware`` and
  BEFORE any view-layer middleware that may issue DB reads
  (``apps.compliance.middleware.AuditLoggingMiddleware`` etc.).

When the JWT is absent or invalid, this middleware is a no-op — the existing
session-based binding remains in force. It NEVER raises into the request path.

Honest-deferred: HSM-backed signing key rotation (lives in v4.01+; today the
signing secret is ``settings.RMC_RLS_JWT_SIGNING_KEY`` env var, HMAC-SHA256).
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Callable
from time import time
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from apps.schools.rls_context import (
    reset_rls_school_id,
    set_rls_school_id,
)

logger = logging.getLogger(__name__)

_RLS_JWT_HEADER = "HTTP_X_RMC_RLS_JWT"
_RLS_JWT_COOKIE = "rmc_rls_jwt"
_RLS_JWT_ALG = "HS256"
_RLS_JWT_MAX_AGE_SECONDS = 60 * 60 * 8  # 8h


def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def _verify_jwt(token: str) -> dict[str, Any] | None:
    """Return decoded claims dict on success, None on any failure.

    Failures are silent by design: a bad JWT must NEVER 5xx the request.
    The caller falls back to the existing session-based RLS binding.

    Cryptographic verify dispatches to ``services.rls_jwt_signing.verify`` so
    HSM-backed signing backends are honored transparently.
    """
    if not token or token.count(".") != 2:
        return None
    header_b64, payload_b64, sig_b64 = token.split(".", 2)
    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(header, dict) or header.get("alg") != _RLS_JWT_ALG:
        return None
    if header.get("typ", "JWT") != "JWT":
        return None
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    try:
        given_sig = _b64url_decode(sig_b64)
    except (ValueError, TypeError):
        return None
    try:
        from services.rls_jwt_signing import HSMBackendNotConfigured, verify as _verify

        if not _verify(signing_input, given_sig):
            return None
    except HSMBackendNotConfigured:
        # Operator selected an HSM backend but didn't wire it up. We must NOT
        # fall back to the local key — that would silently defeat HSM intent.
        # Surface as a verification failure (silent at middleware layer; the
        # WARNING below shows in logs).
        logger.warning("rls_jwt.hsm_not_configured — refusing to verify token")
        return None
    try:
        claims = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(claims, dict):
        return None
    iat = claims.get("iat")
    if not isinstance(iat, (int, float)):
        return None
    if (time() - float(iat)) > _RLS_JWT_MAX_AGE_SECONDS:
        return None
    return claims


def _extract_token(request: HttpRequest) -> str:
    header = request.META.get(_RLS_JWT_HEADER, "") or ""
    if header:
        return header.strip()
    cookie = request.COOKIES.get(_RLS_JWT_COOKIE, "") or ""
    return cookie.strip()


def _request_school_id(request: HttpRequest) -> str:
    """The host/session-resolved tenant id (set + GUC-bound by TenantMiddleware).

    This is the authoritative tenant for the request — it is congruence-enforced
    upstream by ``SessionSchoolBindingMiddleware`` (realign-or-logout) and drives
    both app-layer authorization and ``RegionalDatabaseMiddleware`` DB routing.
    Returns "" when no host tenant is resolved (e.g. a pure API request that is
    authenticated only by the RLS-JWT itself).
    """
    school = getattr(request, "school", None)
    if school is None:
        return ""
    sid = getattr(school, "pk", None) or getattr(school, "id", None)
    return str(sid) if sid else ""


class RLSJWTBindingMiddleware:
    """Bind ``app.current_school_id`` from a signed JWT when present.

    Behavior matrix
    ---------------
    * Not Postgres or USE_DJANGO_TENANTS=True  -> pass-through.
    * No JWT on request                        -> pass-through (session binding wins).
    * Invalid / expired JWT                    -> pass-through + structured-log warn.
    * Valid JWT carrying ``school_id``         -> set_rls_school_id; reset in finally.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self._enabled = (
            not getattr(settings, "USE_DJANGO_TENANTS", False)
            and bool(getattr(settings, "DATABASES", {}).get("default", {}).get("ENGINE", "").endswith("postgresql"))
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not self._enabled:
            return self.get_response(request)
        token = _extract_token(request)
        if not token:
            response = self.get_response(request)
            if getattr(request, "_rls_jwt_clear", False):
                clear_rls_jwt_cookie(response)
            else:
                self._maybe_mint_handoff_cookie(request, response)
            return response
        claims = _verify_jwt(token)
        if claims is None:
            logger.warning(
                "rls_jwt.invalid",
                extra={"path": request.path, "host": request.get_host()},
            )
            response = self.get_response(request)
            if getattr(request, "_rls_jwt_clear", False):
                clear_rls_jwt_cookie(response)
            else:
                # On invalid token, give the response middleware a chance to
                # mint a fresh one if the session itself is still valid.
                self._maybe_mint_handoff_cookie(request, response)
            return response
        school_id = claims.get("school_id") or claims.get("tenant_id")
        if not school_id:
            return self.get_response(request)
        request.rls_jwt_claims = claims  # downstream observability

        # BENCHMARK 1 congruence guard (Routing vs RLS): TenantMiddleware has
        # already bound app.current_school_id to the host/session-resolved
        # ``request.school``. When that tenant is resolved AND the JWT cookie
        # asserts a DIFFERENT school, the cookie is stale — the RLS-JWT cookie is
        # host-scoped and only re-mints when absent, so an operator who switches
        # tenants on the shared manager host keeps a cookie pinned to the first
        # school. Binding the GUC to that stale value would silently diverge the
        # RLS context from request.school and the DB router (cross-tenant read on
        # the wrong tenant's connection). Bind to the AUTHORITATIVE host school
        # instead and drop the stale cookie so the next response re-mints it.
        host_school_id = _request_school_id(request)
        clear_stale_cookie = False
        if host_school_id and str(school_id) != host_school_id:
            logger.warning(
                "rls_jwt.school_divergence",
                extra={
                    "jwt_school_id": str(school_id),
                    "host_school_id": host_school_id,
                    "path": request.path,
                },
            )
            authoritative_id = host_school_id
            clear_stale_cookie = True
        else:
            authoritative_id = school_id

        bound = False
        try:
            set_rls_school_id(authoritative_id)
            bound = True
            response = self.get_response(request)
            if clear_stale_cookie:
                clear_rls_jwt_cookie(response)
            return response
        except (ValueError, TypeError) as exc:
            logger.warning("rls_jwt.bind_failed: %s", exc)
            return self.get_response(request)
        finally:
            if bound:
                try:
                    reset_rls_school_id()
                except Exception as exc:  # noqa: BLE001 — finally must never raise
                    logger.debug("rls_jwt.reset_failed: %s", exc)
                    from apps.schools.rls_context import quarantine_rls_connection

                    quarantine_rls_connection(str(exc))

    @staticmethod
    def _maybe_mint_handoff_cookie(request: HttpRequest, response: HttpResponse) -> None:
        """If the session is authenticated and bound to a school, mint the cookie.

        This is the auth-handoff path. After a user logs in (Django's session
        middleware sets ``request.user`` + ``request.school`` is resolved by
        upstream tenant middleware), the FIRST authenticated response stamps
        an HS256 JWT cookie. Subsequent requests carry it via ``_extract_token``
        and the middleware binds ``app.current_school_id`` via the GUC path.

        Cookie is HttpOnly + SameSite=Lax + Secure (when request is HTTPS).
        Lifetime matches ``_RLS_JWT_MAX_AGE_SECONDS`` (8h).
        """
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return
        school = getattr(request, "school", None)
        if school is None:
            return
        school_id = getattr(school, "id", None) or getattr(school, "pk", None)
        if not school_id:
            return
        # Don't re-mint if the request already had a valid cookie/header.
        if _extract_token(request):
            return
        try:
            role = _resolve_user_role(user, school)
            token = mint_rls_jwt(
                school_id=str(school_id),
                user_id=user.pk,
                role=role,
            )
        except Exception as exc:  # noqa: BLE001 — minting failure must never break the response
            logger.warning("rls_jwt.mint_failed: %s", exc)
            return
        response.set_cookie(
            _RLS_JWT_COOKIE,
            token,
            max_age=_RLS_JWT_MAX_AGE_SECONDS,
            secure=request.is_secure(),
            httponly=True,
            samesite="Lax",
        )


def _resolve_user_role(user, school) -> str:
    """Best-effort role resolution. Falls back to ``user`` when nothing fits.

    The role lands in the JWT as a transparency claim. Downstream code that
    needs RBAC still uses the regular ``request.user`` machinery — this is not
    an authorization channel.
    """
    for attr in ("active_role", "primary_role", "role"):
        v = getattr(user, attr, None)
        if isinstance(v, str) and v:
            return v
    if getattr(user, "is_superuser", False):
        return "superuser"
    if getattr(user, "is_staff", False):
        return "staff"
    return "user"


def clear_rls_jwt_cookie(response: HttpResponse) -> None:
    """Used by logout views (or a user_logged_out signal receiver) to drop the cookie."""
    response.delete_cookie(_RLS_JWT_COOKIE, samesite="Lax")


def mint_rls_jwt(*, school_id: str, user_id: str | int, role: str) -> str:
    """Helper for tests + the future auth-handoff view.

    Emits a short-lived HS256 JWT carrying the three claims the middleware
    consumes. Cryptographic sign dispatches to ``services.rls_jwt_signing``
    so HSM backends are honored. NEVER use this to bypass real auth — the
    auth layer signs the token only after a successful login.
    """
    from services.rls_jwt_signing import sign as _sign

    header = {"alg": _RLS_JWT_ALG, "typ": "JWT"}
    payload = {
        "school_id": str(school_id),
        "user_id": str(user_id),
        "role": str(role),
        "iat": int(time()),
    }
    header_b64 = base64.urlsafe_b64encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = _sign(signing_input)
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return f"{header_b64}.{payload_b64}.{sig_b64}"
