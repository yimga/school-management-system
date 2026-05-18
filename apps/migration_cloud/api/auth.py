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

    Inherits the standard ``rest_framework.authtoken`` model lookup.
    Scoping (capability + tenant binding) is currently enforced by the
    companion permission class; future work moves that down into a
    scoped-token model so capability checks are O(1) and audit logs
    carry the scope identifier.
    """

    # The marker string is read by the OpenAPI bearer auth scheme to
    # produce a clean ``securitySchemes`` entry instead of the default
    # "Token" label, which can collide with other Token-style schemes.
    keyword = "Token"
