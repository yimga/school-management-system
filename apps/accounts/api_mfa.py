"""Machine-readable MFA-enrolment gate for the JSON API surface.

WHY THIS MODULE EXISTS
----------------------
``RequireMFAMiddleware`` walls a principal whose role requires MFA and who has
enrolled no TOTP device / passkey. It did that by 302-redirecting to the
enrolment page -- an HTML answer -- and it carried ``"/api/"`` in
``BYPASS_PREFIXES``, so that redirect never reached an API client. Every other
entry in that tuple carried a comment saying what it bought. ``"/api/"`` did not.

Measured on 2026-08-31 against a SCHOOL_ADMIN school-owner with a live session
and no MFA device (see ``apps/accounts/tests/test_api_mfa_gate_2026_08_31.py``)::

    GET  /dashboard/             302 -> /authentication/mfa/setup/   (walled)
    GET  /finance/               302 -> /authentication/mfa/setup/   (walled)
    GET  /api/auth/profile/      200  {"username": ..., "email": ...}
    GET  /api/entities/students/ 200  {"results": [{"first_name": "Ada", ...}]}
    POST /api/auth/token/        200  {"access": "<JWT>"}
    GET  /api/auth/profile/      200  with that Bearer JWT

The wall was an HTML formality. Closing only the cookie door would have left the
remedy "exchange the same password for a JWT", so this gate covers both doors.

WHAT IT DOES
------------
It asks the SAME policy question the HTML wall asks -- through
``evaluate_mfa_enrollment``, the single implementation both callers share, so the
two can never drift -- and renders the answer as ``403`` with an
``application/json`` body that names MFA enrolment as the remedy and carries the
enrolment URL. A 302 to an HTML page is useless to an API client: it cannot act
on it, and a client that follows redirects blindly gets a login page with a
``200`` on it.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It gates ENROLMENT only -- ``decision.action == "enforce"``: MFA is required for
this principal and no device exists. It does NOT extend the middleware's
per-session *re-verify* gate (``session["mfa_verified"]``) to the API. A bearer
client has no Django session and can never carry that flag, so gating on it would
``403`` every API call made by a correctly enrolled admin. Per-session
re-verification for API clients needs an MFA claim carried in the token itself;
that is separate work and is NOT closed here.

WHY EDGE-BOX / DEVICE CREDENTIALS ARE NOT BROKEN BY THIS
--------------------------------------------------------
Machines authenticate here with an ``Authorization: Bearer`` opaque token
resolved by a DRF authentication class:

  * ``apps.api.edge_auth.EdgeCredentialAuthentication`` -- the sovereign edge
    box's sync rails (bundle upload/download/receipt, changes feed, file and
    upgrade manifests/chunks),
  * ``apps.api.third_party_auth.ThirdPartyCredentialAuthentication``
    (``sk_live_`` API keys, ``rmc_at_`` OAuth access tokens),
  * ``apps.migration_cloud.api`` auth + scoped tokens (Migration Cloud).

Every one of them resolves to a HUMAN row -- ``token.user`` -- and on a real
deployment that row is routinely a superuser or SCHOOL_ADMIN who owns no phone,
because a box does not enrol in TOTP. (``apps/api/tests/test_edge_credential_auth``
mints exactly that shape: ``User.objects.create_superuser`` plus an ADMIN
membership.) Asking "does ``request.user`` require MFA?" AFTER DRF authentication
would therefore have 403'd the entire edge sync rail. That is the single most
likely way to get this change wrong.

This gate runs in MIDDLEWARE, before DRF authentication runs. At that point
``request.user`` is populated only by Django's session backend, so a box's bearer
request is anonymous here and passes straight through. That is not an allowlist
that can rot as rails are added -- it is the shape of the request stack, and
``test_api_mfa_gate_2026_08_31`` drives a real minted edge credential through the
full middleware stack to hold it there.

The one bearer token that IS a human password sign-in in disguise is the
SimpleJWT access token from ``/api/auth/token/``. ``jwt_bearer_principal``
resolves that and nothing else: its pre-filter requires three dot-separated JWT
segments, and no machine credential has any dots at all -- edge and offline
device tokens are ``secrets.token_urlsafe(32)``, third-party keys carry
``sk_live_`` / ``rmc_at_`` prefixes.
"""

from __future__ import annotations

import logging
from collections import namedtuple

from django.core.exceptions import ImproperlyConfigured
from django.http import JsonResponse

# Bound at MODULE scope on purpose. Both are named in ``except`` tuples below, and
# an ``except`` tuple is evaluated only when something is raised -- so a class
# imported lazily inside the very ``try`` it guards would be UNBOUND on the failure
# path and turn a handled error into a NameError.
from django.urls.exceptions import NoReverseMatch

logger = logging.getLogger(__name__)

#: The error code an API client branches on. Stable; part of the contract.
MFA_ENROLLMENT_REQUIRED_CODE = "mfa_enrollment_required"

#: Paths under ``/api/`` this gate must never wall. Kept deliberately SHORT:
#: everything not listed here is protected by the structural property described
#: in the module docstring (a machine credential is anonymous in middleware), not
#: by being named. A short list cannot silently un-gate a rail added later.
API_MFA_EXEMPT_PREFIXES: tuple[str, ...] = (
    # --- the way IN for a client that holds no credential yet -----------------
    # Walling the token endpoints would be a lockout with no way out: a client
    # that cannot obtain a token cannot do anything at all, enrolment included.
    "/api/auth/token",               # SimpleJWT obtain + refresh
    "/api/v1/oauth/token",           # API-center OAuth2 token endpoint
    "/api/roster/v1p2/oauth/token",  # OneRoster OAuth2 client_credentials grant
    "/api/.well-known",              # OAuth authorization-server metadata
    # --- discovery / liveness: no tenant data, and a monitor holds no TOTP ----
    "/api/schema",                   # + /api/schema/ui
    "/api/openapi.json",
    "/api/openapi.yaml",
    "/api/docs",
    "/api/redoc",
    "/api/health",
    "/api/ai/health",
    "/api/system/version",
    "/api/csrf-token",
    # --- box pairing: credential-free BY DEFINITION ---------------------------
    # PairingStartView / PairingPollView declare ``authentication_classes = []``
    # and ``AllowAny`` because an UNPAIRED box holds no credential at all. Driven
    # by the box (apps/sync_engine/cloud_endpoints.py), never by a browser.
    "/api/sync/pair",
)

# NOTE on what is deliberately ABSENT: the edge sync RAILS (/api/sync/bundle/,
# /api/sync/changes/, /api/sync/files/, /api/sync/upgrade/) are NOT exempt by
# path. They do not need to be -- the box is anonymous in middleware -- and
# exempting them by path would have re-opened this very hole for a walled HUMAN
# with a session cookie, because SyncBundleUploadView / SyncBundleDownloadView
# splat the default authentication classes and therefore DO accept a session.

#: Bearer prefixes owned by machine credentials. Cheap negative pre-filter so a
#: box's token never reaches SimpleJWT's validator.
_MACHINE_BEARER_PREFIXES: tuple[str, ...] = ("sk_live_", "sk_test_", "rmc_at_")

#: (must_have_mfa, has_device, decision); ``decision`` is an
#: ``mfa_defaults.MfaEnforcementDecision``.
MfaEnrollmentVerdict = namedtuple(
    "MfaEnrollmentVerdict", ("must_have_mfa", "has_device", "decision")
)


def _normalize(path):
    return (path or "").rstrip("/") or "/"


def is_api_path(path) -> bool:
    """True for ``/api`` and anything beneath it (trailing slash irrelevant)."""
    norm = _normalize(path)
    return norm == "/api" or norm.startswith("/api/")


def api_gate_applies(path) -> bool:
    """True when this path is API surface that the MFA-enrolment gate protects."""
    if not is_api_path(path):
        return False
    norm = _normalize(path)
    for prefix in API_MFA_EXEMPT_PREFIXES:
        pref = prefix.rstrip("/")
        if norm == pref or norm.startswith(pref + "/"):
            return False
    return True


def evaluate_mfa_enrollment(request, user, site) -> MfaEnrollmentVerdict:
    """The MFA-enrolment policy verdict for ``user`` on ``request``.

    The ONE implementation. ``RequireMFAMiddleware`` uses it for the HTML wall
    and this module uses it for the API gate, so a policy change lands on both or
    neither. ``site`` is passed in rather than resolved here because the MFA
    enforcement tests patch ``apps.accounts.middleware.get_effective_site_settings``
    and drive that exact call path; moving the resolver into this module would
    silently unhook them.
    """
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from apps.accounts.mfa_defaults import (
        effective_required_roles,
        principal_requires_strict_mfa,
        resolve_mfa_enforcement,
        resolve_operator_mfa,
    )
    from apps.accounts.utils import get_user_role

    school = getattr(request, "school", None)
    require_all_staff = getattr(site, "require_mfa_all_staff", False)
    required_roles = getattr(site, "require_mfa_roles", None) or []

    # Operator + tenant, with floor: the operator's per-tenant policy is OR-ed
    # into "all staff" and unioned into the required roles above the tenant's own
    # settings; a tenant can only tighten, never weaken, and neither can drop
    # below the baseline floor in apps/accounts/mfa_defaults.py.
    operator_policy = resolve_operator_mfa(school, request=request)
    role = get_user_role(user, school)
    must_have_mfa = False
    if (require_all_staff or operator_policy.require_all_staff) and user.is_staff:
        must_have_mfa = True
    else:
        required_normalized = effective_required_roles(
            required_roles, operator_required=operator_policy.required_roles
        )
        if role and str(role).strip().upper() in required_normalized:
            must_have_mfa = True

    # Only a confirmed TOTP device or a passkey counts as configured MFA. NOT
    # django_otp's user_has_device(confirmed=True): that also counts a
    # StaticDevice (backup codes), and a backup-codes-only user cannot complete
    # mfa_verify, so counting it would wall them in a verify<->setup bounce.
    has_device = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
    if not has_device:
        from apps.accounts.models import UserPasskey

        has_device = UserPasskey.objects.filter(user=user).exists()

    decision = resolve_mfa_enforcement(
        must_have_mfa=must_have_mfa,
        has_device=has_device,
        mode=(
            "strict"
            if principal_requires_strict_mfa(user, school)
            else getattr(site, "mfa_enforcement_mode", None)
        ),
        grace_period_days=getattr(site, "mfa_grace_period_days", None),
        user=user,
    )
    return MfaEnrollmentVerdict(must_have_mfa, has_device, decision)


def deferral_downgrades_enforcement(request, user) -> bool:
    """True when a granted "skip MFA for N days" deferral softens the hard wall.

    Only for principals who MAY be softened: a superuser / platform admin /
    active school owner is pinned to strict by ``principal_requires_strict_mfa``,
    so re-checking it here keeps a deferral from ever letting an owner skip
    enrolment. Shared with the HTML wall so the two answer identically.
    """
    from apps.accounts.mfa_defaults import principal_requires_strict_mfa
    from apps.accounts.mfa_deferral import mfa_setup_deferral_active

    return bool(mfa_setup_deferral_active(user)) and not principal_requires_strict_mfa(
        user, getattr(request, "school", None)
    )


def mfa_setup_url() -> str:
    """The enrolment page.

    ``legacy=1`` routes to the branded enrolment body rather than the bare studio
    wizard, matching the HTML wall's redirect exactly.
    """
    try:
        from django.urls import reverse

        return reverse("accounts:mfa_setup") + "?legacy=1"
    except (ImportError, NoReverseMatch, ImproperlyConfigured):
        # The three ways this can actually fail, and no wider: ``django.urls`` not
        # importable, the route not registered on the active urlconf
        # (NoReverseMatch), and settings/ROOT_URLCONF not available yet or any more
        # (ImproperlyConfigured) -- the mid-teardown case. A NameError or an
        # AttributeError here would be a typo in this function, and it must not be
        # able to hide behind a hardcoded fallback that still renders.
        return "/authentication/mfa/setup/?legacy=1"


def mfa_enrollment_required_response(request) -> JsonResponse:
    """The refusal: 403 + JSON, never a redirect an API client cannot follow."""
    return JsonResponse(
        {
            "detail": (
                "Multi-factor authentication is required for this role and this "
                "account has no MFA device enrolled. Enrol a TOTP authenticator "
                "or a passkey, then retry this request."
            ),
            "code": MFA_ENROLLMENT_REQUIRED_CODE,
            "remedy": "enroll_mfa",
            "mfa_setup_url": mfa_setup_url(),
            "path": getattr(request, "path", ""),
        },
        status=403,
    )


def jwt_bearer_principal(request):
    """The user behind a SimpleJWT ``Authorization: Bearer`` header, else ``None``.

    Session authentication has already run by the time middleware sees the
    request; DRF's has not. A JWT is a human password sign-in wearing a bearer
    header (``/api/auth/token/`` takes a username and a password), so it has to
    be resolved here or the fix is only half a fix. Every failure mode -- absent
    header, machine credential, malformed or expired token, deleted user --
    returns ``None`` and the request proceeds exactly as it did before.
    """
    header = request.META.get("HTTP_AUTHORIZATION") or ""
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    raw = parts[1]
    if raw.startswith(_MACHINE_BEARER_PREFIXES):
        return None
    segments = raw.split(".")
    if len(segments) != 3 or not all(segments):
        # Not JWT-shaped. Edge + offline device credentials are
        # secrets.token_urlsafe(32) -- no dots -- so they stop here and never
        # reach SimpleJWT's validator.
        return None
    try:
        from rest_framework.exceptions import APIException
        from rest_framework_simplejwt.authentication import JWTAuthentication
        from rest_framework_simplejwt.exceptions import TokenError
    except ImportError:
        # DRF / SimpleJWT absent from this deploy: there is no JWT principal to
        # resolve. This is a ``try`` of its own because the classes named in the
        # tuple below come FROM these imports -- guarding both in one block would
        # leave them unbound exactly when the tuple is evaluated.
        return None
    try:
        resolved = JWTAuthentication().authenticate(request)
    except (APIException, TokenError, UnicodeError):
        # Every refusal ``JWTAuthentication.authenticate`` raises is an
        # AuthenticationFailed / InvalidToken -- both APIException subclasses:
        # malformed header, unparseable or expired token, no matching token class,
        # deleted or inactive user. TokenError is the contract SimpleJWT's own token
        # classes are documented to raise. UnicodeError is ``get_header``
        # re-encoding the Authorization header to latin-1. A NameError or an
        # AttributeError from a typo in this module now reaches the caller instead
        # of silently downgrading every bearer request to anonymous.
        return None
    if not resolved:
        return None
    user = resolved[0]
    return user if getattr(user, "is_authenticated", False) else None


__all__ = [
    "MFA_ENROLLMENT_REQUIRED_CODE",
    "API_MFA_EXEMPT_PREFIXES",
    "MfaEnrollmentVerdict",
    "is_api_path",
    "api_gate_applies",
    "evaluate_mfa_enrollment",
    "deferral_downgrades_enforcement",
    "mfa_setup_url",
    "mfa_enrollment_required_response",
    "jwt_bearer_principal",
]
