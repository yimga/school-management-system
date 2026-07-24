"""Authentication classes for the Migration Cloud public REST API.

MVP scope (v3.27 alpha):
  - Subclass DRF's ``TokenAuthentication`` so the existing per-user
    ``authtoken`` rows work out of the box. Operators issue a token via
    the standard ``drf_create_token`` flow; partners pass it as
    ``Authorization: Token <hex>``.
  - Future work (deferred — see docket): scoped API tokens carrying an
    explicit ``capabilities`` set (read-only / bundle-write / apply-only)
    + tenant binding so a partner key bound to School A cannot drive
    School B's migrations. The MVP relies on the per-bundle tenant check
    in :class:`apps.migration_cloud.api.permissions.MigrationCloudAPIPermission`.

We extend rather than ship a brand-new auth model so adoption is
incremental — partners onboard against the standard token table today,
and we layer scoped tokens on top once the alpha graduates.
"""

from __future__ import annotations

import logging

from rest_framework.authentication import TokenAuthentication

logger = logging.getLogger(__name__)


class MigrationCloudTokenAuthentication(TokenAuthentication):
    """Token auth for the Migration Cloud public REST API.

    Recognizes BOTH:

      * Legacy DRF ``authtoken`` rows (single-scope, per-user) for
        backwards compatibility with v3.27 alpha clients.
      * v3.29 ``MigrationCloudAPIToken`` scoped tokens (prefix ``mc_``)
        — delegated to
        :class:`apps.migration_cloud.api.scoped_tokens.MigrationCloudScopedTokenAuthentication`.

    Scoped tokens are recognized by the ``mc_`` prefix on the credential
    string; anything else falls through to the legacy DRF authtoken
    lookup. The scoped-token branch sets ``request.auth`` to the
    ``MigrationCloudAPIToken`` row so
    :class:`apps.migration_cloud.api.permissions.ScopedAPIPermission`
    can read ``request.auth.scopes`` and gate the action.
    """

    # The marker string is read by the OpenAPI bearer auth scheme to
    # produce a clean ``securitySchemes`` entry instead of the default
    # "Token" label, which can collide with other Token-style schemes.
    keyword = "Token"

    def authenticate(self, request):
        # Dual-path: scoped tokens carry an ``mc_`` prefix.
        header = self.get_authorization_header_value(request)
        if header and header.startswith("mc_"):
            # Delegate to the scoped-token backend — lazy import keeps
            # the module-level cycle clean during Django app load.
            from .scoped_tokens import MigrationCloudScopedTokenAuthentication
            return MigrationCloudScopedTokenAuthentication().authenticate(request)
        return super().authenticate(request)

    @staticmethod
    def get_authorization_header_value(request) -> str:
        """Return the credential portion of the Authorization header, or ''.

        Handles both ``Token <x>`` and ``Bearer <x>`` forms. Returns the
        empty string when the header is absent or malformed.
        """
        from rest_framework.authentication import get_authorization_header

        raw = get_authorization_header(request).decode("latin-1")
        if not raw:
            return ""
        parts = raw.split()
        if len(parts) != 2:
            return ""
        return parts[1]


def migration_cloud_authentication_classes() -> list:
    """Auth classes for every Migration Cloud API viewset.

    Token-first: the scoped ``mc_`` token backend runs before the project
    defaults (session + JWT). WITHOUT this on the viewset, ``mc_`` tokens never
    authenticate (401) and the only working machine path is JWT — which carries
    FULL user privilege with no scope and no tenant binding, the inverse of the
    least-privilege contract the API advertises. Evaluated once at class-def time
    so it is a plain list DRF can consume. Pairs with ``ScopedAPIPermission``.
    See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (BLOCKER 5).
    """
    from rest_framework.settings import api_settings

    return [MigrationCloudTokenAuthentication, *api_settings.DEFAULT_AUTHENTICATION_CLASSES]
