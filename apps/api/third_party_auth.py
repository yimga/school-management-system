"""Third-party credential authentication for the public API v1 surface.

Program item 4.1 — *A third-party credential must authenticate*.

Before this module the developer platform had every piece except the seam:
``apps.apicenter`` mints credentials (:class:`~apps.apicenter.models.APIKey`,
:class:`~apps.apicenter.models.OAuthTokenPair`), ``apps.marketplace`` governs
installs and resolves granted scopes, and
:data:`apps.api.permissions.V1_TENANT_CRUD_SCOPE_MAP` catalogs the scope
required for every action on the v1 tenant CRUD surface — but **no DRF
authentication class ever turned a presented credential into a principal**.
``AppApiContextMiddleware`` attaches ``request.app_scope`` without touching
``request.user``, so a third-party call arrived as ``AnonymousUser`` and
``IsAuthenticated`` rejected it. Worse, ``JWTAuthentication`` claims any
``Authorization: Bearer …`` header and hard-fails on a non-JWT value, so the
credential was rejected before anything could look at it.

This module supplies the missing seam, modelled directly on the working
precedent in :mod:`apps.migration_cloud.api.scoped_tokens` +
:mod:`apps.migration_cloud.api.permissions`:

  * :class:`ThirdPartyCredentialAuthentication` resolves an
    ``sk_live_…`` tenant API key or an ``rmc_at_…`` OAuth access token to
    ``(user, ThirdPartyCredential)``. ``request.auth`` carries the tenant and
    the granted scope set.
  * :class:`ThirdPartyScopePermission` gates the call against the *existing*
    scope map. Requests authenticated any other way pass straight through, so
    no existing authentication path is weakened.

Security posture (all failures are closed, and 401 — never a partial grant):

  * Secrets are compared against the stored **sha256** digest only; plaintext
    is never logged and never persisted. This follows the
    ``MigrationCloudAPIToken`` precedent.
  * The principal is **tenant-bound**. A credential must name a school, that
    school must equal ``request.school``, and the resolved user must hold a
    live (non-suspended) membership in it. A credential with no tenant binding
    is refused outright rather than floating across tenants.
  * Revoked, expired, inactive-app, inactive-user and uninstalled-app
    credentials all fail authentication.
  * An action with no entry in the scope map is **denied**, not ignored.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from django.utils import timezone
from rest_framework import authentication, exceptions
from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)

#: ``APIKey.PREFIX`` — tenant-issued API key.
API_KEY_PREFIX = "sk_live_"

#: Prefix minted by :func:`apps.apicenter.oauth_service.issue_token_pair`.
OAUTH_ACCESS_PREFIX = "rmc_at_"

#: Generic failure detail. Every rejection reads the same from outside so a
#: caller cannot probe which credential exists, which tenant it belongs to, or
#: whether it merely expired.
_GENERIC_FAILURE = "Invalid or expired credential."


@dataclass(frozen=True)
class ThirdPartyCredential:
    """Resolved third-party principal context — the value of ``request.auth``.

    Immutable on purpose: a view cannot widen its own tenant or scopes.
    """

    #: ``"api_key"`` or ``"oauth_access_token"``.
    kind: str
    #: Primary key of the backing credential row (never the secret).
    credential_id: Any
    #: Tenant this credential is bound to. Always populated — a credential
    #: without a school never authenticates.
    school_id: Any
    #: Effective scopes: credential scopes unioned with the installation's
    #: granted ``ScopeGrant`` rows, per ``apps.marketplace.permissions_runtime``.
    scopes: frozenset[str] = field(default_factory=frozenset)
    #: Marketplace installation backing the grant, when there is one.
    installation_id: Any = None

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def _fail() -> None:
    """Raise the single generic authentication failure."""
    raise exceptions.AuthenticationFailed(_GENERIC_FAILURE)


class ThirdPartyCredentialAuthentication(authentication.BaseAuthentication):
    """Resolve an API key / OAuth access token to a tenant-bound principal.

    Recognized header forms::

        Authorization: Bearer sk_live_<secret>
        Authorization: Bearer rmc_at_<secret>

    Any other header shape returns ``None`` so session / JWT authentication
    still runs exactly as before. Because this class is listed first on the
    views that use it, it claims the two prefixes it owns before
    ``JWTAuthentication`` can reject them as malformed JWTs.

    Returns ``(user, ThirdPartyCredential)``. The user is the human the
    credential acts for — the API key's issuer, or the user who completed the
    OAuth authorization-code grant — mirroring
    ``MigrationCloudScopedTokenAuthentication`` returning ``row.user``. The
    effective access is therefore the *intersection* of that user's own
    authority and the credential's granted scopes; a credential can never
    exceed the person who authorized it.
    """

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("latin-1")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        raw = parts[1]

        if raw.startswith(OAUTH_ACCESS_PREFIX):
            return self._authenticate_oauth(request, raw)
        if raw.startswith(API_KEY_PREFIX):
            return self._authenticate_api_key(request, raw)
        # Not a credential we own — let the next authenticator try.
        return None

    def authenticate_header(self, request):
        # Non-None => DRF renders 401 (not 403) for unauthenticated callers.
        return 'Bearer realm="runmycampus-api"'

    # ─── credential resolvers ──────────────────────────────────────────────

    def _authenticate_api_key(self, request, raw: str):
        from apps.apicenter.models import APIKey
        from apps.marketplace.permissions_runtime import effective_scopes_for_api_key

        school = self._require_request_school(request)

        # ``APIKey.verify`` hashes the presented secret, filters out revoked
        # rows and does a constant-time digest compare. Plaintext never lands
        # in the database or a log line.
        key = APIKey.verify(raw[: len(APIKey.PREFIX) + 8], raw)
        if key is None:
            _fail()

        # Tenant binding is mandatory. A NULL ``school`` on an API key would
        # otherwise authenticate against whichever tenant host it was replayed
        # at — the exact cross-tenant hole this item exists to close.
        if key.school_id is None or str(key.school_id) != str(school.pk):
            _fail()

        user = self._resolve_member(key.created_by_id, school)
        credential = ThirdPartyCredential(
            kind="api_key",
            credential_id=key.pk,
            school_id=school.pk,
            scopes=frozenset(effective_scopes_for_api_key(key)),
            installation_id=key.marketplace_installation_id,
        )
        self._touch_last_used(key)
        return (user, credential)

    def _authenticate_oauth(self, request, raw: str):
        from apps.apicenter.models import OAuthTokenPair, _hash_secret
        from apps.marketplace.models import AppInstallation
        from apps.marketplace.permissions_runtime import (
            effective_scopes_for_oauth_pair,
        )

        school = self._require_request_school(request)
        now = timezone.now()

        # Access tokens are stored as sha256 only; the lookup key IS the digest.
        # tenant-isolation-allow: credential lookup keyed by secret digest; the
        # tenant gate is applied immediately below via the active installation.
        pair = (
            OAuthTokenPair.objects.filter(
                access_token_hash=_hash_secret(raw),
                revoked_at__isnull=True,
                access_expires_at__gt=now,
            )
            .select_related("application")
            .first()
        )
        if pair is None:
            _fail()

        application = pair.application
        if application is None or not application.is_active:
            _fail()
        if not application.marketplace_app_id:
            # No catalog app => no installation => no tenant binding possible.
            _fail()

        installation = AppInstallation.objects.filter(
            school=school,
            app_id=application.marketplace_app_id,
            status=AppInstallation.Status.ACTIVE,
        ).first()
        if installation is None:
            # Not installed (or install suspended/killed) at this tenant.
            _fail()

        user = self._resolve_member(pair.user_id, school)
        credential = ThirdPartyCredential(
            kind="oauth_access_token",
            credential_id=pair.pk,
            school_id=school.pk,
            scopes=frozenset(effective_scopes_for_oauth_pair(pair, installation)),
            installation_id=installation.pk,
        )
        return (user, credential)

    # ─── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _require_request_school(request):
        """Return the request's tenant, failing closed when there is none.

        Without a resolved tenant there is nothing to bind the credential to,
        so there is no safe way to serve the call.
        """
        school = getattr(request, "school", None) or getattr(request, "tenant", None)
        if school is None or getattr(school, "pk", None) is None:
            _fail()
        return school

    @staticmethod
    def _resolve_member(user_id, school):
        """Resolve the acting user, requiring a live membership in ``school``.

        A credential whose issuer has left the school, been suspended or
        deactivated stops working immediately — offboarding a person also
        offboards the integrations they authorized.
        """
        if not user_id:
            # Client-credentials tokens carry no user. There is no service
            # account identity model yet, so there is nobody to act as and no
            # authority to bound the call by. Refuse rather than invent one.
            _fail()

        from apps.schools.models import SchoolMembership

        membership = (
            SchoolMembership.objects.filter(
                user_id=user_id, school=school, suspended_at__isnull=True
            )
            .select_related("user")
            .first()
        )
        if membership is None:
            _fail()
        user = membership.user
        if user is None or not user.is_active:
            _fail()
        return user

    @staticmethod
    def _touch_last_used(key) -> None:
        """Best-effort usage stamp; never block or fail the request on it."""
        try:
            key.last_used_at = timezone.now()
            key.save(update_fields=["last_used_at"])
        except Exception:  # pragma: no cover — defensive
            logger.exception("third-party API key last_used_at update failed")


class ThirdPartyScopePermission(BasePermission):
    """Deny-by-default scope gate for third-party credentials.

    Keyed off ``request.auth`` exactly like
    :class:`apps.migration_cloud.api.permissions.ScopedAPIPermission`: when the
    request was **not** authenticated by
    :class:`ThirdPartyCredentialAuthentication` this returns ``True`` and the
    view's other permission classes decide, so session and JWT callers are
    unaffected.

    For third-party callers the required scope comes from the existing
    :data:`apps.api.permissions.V1_TENANT_CRUD_SCOPE_MAP`. An action absent
    from that map is refused — every reachable action must be cataloged before
    a third party can call it.
    """

    message = "Insufficient scope for this action."

    def has_permission(self, request, view) -> bool:
        credential = getattr(request, "auth", None)
        if not isinstance(credential, ThirdPartyCredential):
            return True
        if not self._tenant_ok(request, credential):
            return False
        return self._scope_ok(view, credential)

    def has_object_permission(self, request, view, obj) -> bool:
        credential = getattr(request, "auth", None)
        if not isinstance(credential, ThirdPartyCredential):
            return True
        if not self._tenant_ok(request, credential):
            return False
        # Defense in depth behind the queryset's own school filter: an object
        # belonging to another tenant is never addressable by this credential.
        obj_school_id = getattr(obj, "school_id", None)
        if obj_school_id is not None and str(obj_school_id) != str(
            credential.school_id
        ):
            self.message = "Credential is bound to a different tenant."
            return False
        return self._scope_ok(view, credential)

    # ─── internals ─────────────────────────────────────────────────────────

    def _tenant_ok(self, request, credential: ThirdPartyCredential) -> bool:
        school = getattr(request, "school", None) or getattr(request, "tenant", None)
        school_pk = getattr(school, "pk", None)
        if school_pk is None or str(school_pk) != str(credential.school_id):
            self.message = "Credential is bound to a different tenant."
            return False
        return True

    def _scope_ok(self, view, credential: ThirdPartyCredential) -> bool:
        # Lazy import keeps module load order safe and avoids a cycle.
        from apps.api.permissions import V1_TENANT_CRUD_SCOPE_MAP

        basename = getattr(view, "basename", None) or ""
        action = getattr(view, "action", None) or ""
        if not basename or not action:
            self.message = "Unmapped action; refused."
            return False
        required = V1_TENANT_CRUD_SCOPE_MAP.get((basename, action))
        if required is None:
            self.message = f"Action {basename}.{action} has no scope mapping; refused."
            return False
        if not credential.has_scope(required):
            self.message = f"Missing required scope '{required}'."
            return False
        return True
