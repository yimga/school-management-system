"""Scoped API tokens for the Migration Cloud REST API (v3.29).

Three pieces:

  * :class:`MigrationCloudScopedTokenAuthentication` — DRF auth backend
    that recognizes opaque tokens issued by this app's ``POST /tokens/``
    endpoint. We compute ``sha256(received)`` and look up the row;
    plaintext is **never** logged. Expired and revoked tokens are
    rejected.
  * :class:`ScopedTokenViewSet` — mint / list / revoke endpoints.
    Plaintext token appears **only** in the response body of the mint
    call; the listing returns masked metadata only.
  * Scope mapping helpers used by
    :class:`apps.migration_cloud.api.permissions.ScopedAPIPermission`.

Convention:
    Scopes are colon-separated ``<resource>:<action>`` strings. The
    mapping in :data:`ACTION_SCOPE_REQUIREMENTS` is the single source of
    truth — both the auth+permission layer and the docs read from it.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import authentication, exceptions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.migration_cloud.models import MigrationCloudAPIToken
from apps.migration_cloud.reliability import idempotent_post, safe_500

from .auth import migration_cloud_authentication_classes
from .permissions import ScopedAPIPermission

logger = logging.getLogger(__name__)


# ─── Scope catalog ─────────────────────────────────────────────────────────

#: Map of (viewset basename, action method) → required scope string.
#: Read by :class:`ScopedAPIPermission` to gate scoped-token callers.
ACTION_SCOPE_REQUIREMENTS: dict[tuple[str, str], str] = {
    ("bundle", "list"): "bundles:read",
    ("bundle", "retrieve"): "bundles:read",
    ("bundle", "create"): "bundles:write",
    ("bundle", "advance"): "bundles:write",
    ("bundle", "apply_bundle"): "bundles:write",
    ("bundle", "reconcile"): "reconcile:run",
    ("bundle", "artifacts"): "bundles:read",
    ("bundle", "bulk_artifacts"): "artifacts:write",
    ("bundle", "events_stream"): "bundles:read",
    ("bundle", "quarantine_list"): "bundles:read",
    ("bundle", "quarantine_resolve"): "bundles:write",
    ("bundle", "quarantine_export"): "bundles:read",
    ("bundle", "ai_explain_row"): "bundles:read",
    ("template", "list"): "templates:read",
    ("template", "retrieve"): "templates:read",
    ("template", "download"): "templates:read",
    ("token", "list"): "tokens:manage",
    ("token", "create"): "tokens:manage",
    ("token", "destroy"): "tokens:manage",
    ("token", "rotate"): "tokens:manage",
    ("token", "scopes_catalog"): "tokens:manage",
    ("webhook", "list"): "webhooks:manage",
    ("webhook", "create"): "webhooks:manage",
    ("webhook", "retrieve"): "webhooks:manage",
    ("webhook", "destroy"): "webhooks:manage",
}

#: All known scopes — used by the mint validator to reject unknown values.
KNOWN_SCOPES: frozenset[str] = frozenset(ACTION_SCOPE_REQUIREMENTS.values())

#: How long an old token remains usable after rotation (client-rollout grace).
TOKEN_ROTATION_GRACE_DAYS = 7


def _hash_token(plaintext: str) -> str:
    """Return the canonical sha256 hex digest used as the token lookup key."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _generate_token_plaintext() -> str:
    """Return a fresh url-safe opaque token string (256 bits of entropy)."""
    # 32 bytes → 43 chars base64-url; prefix marks it as a Migration Cloud key.
    return "mc_" + secrets.token_urlsafe(32)


# ─── Auth backend ──────────────────────────────────────────────────────────


class MigrationCloudScopedTokenAuthentication(authentication.BaseAuthentication):
    """Authenticate Bearer/Token requests against ``MigrationCloudAPIToken``.

    Recognized header forms (case-insensitive on the keyword):

        Authorization: Token mc_<urlsafe>
        Authorization: Bearer mc_<urlsafe>

    On success returns ``(user, token_row)`` so ``request.auth`` carries
    the row — :class:`ScopedAPIPermission` reads ``request.auth.scopes``
    to gate the call.

    The plaintext token NEVER reaches a log line. Lookup hash is the
    sha256 of the received string; missing / expired / revoked rows
    raise ``AuthenticationFailed`` with a generic message.
    """

    KEYWORDS = ("token", "bearer")

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("latin-1")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2:
            return None
        keyword, plaintext = parts[0].lower(), parts[1]
        if keyword not in self.KEYWORDS:
            return None
        if not plaintext.startswith("mc_"):
            # Not one of OUR scoped tokens — let other auth classes try.
            return None

        token_hash = _hash_token(plaintext)
        try:
            # tenant-isolation-allow: api-token-lookup-keyed-by-hash-not-tenant
            row = MigrationCloudAPIToken.objects.select_related(
                "user", "tenant_scope"
            ).get(token_hash=token_hash)
        except MigrationCloudAPIToken.DoesNotExist:
            # Constant-time-ish failure path: don't reveal whether the
            # hash matched. We do a dummy compare to keep timing flat.
            hmac.compare_digest(token_hash, "0" * 64)
            raise exceptions.AuthenticationFailed("invalid token")

        now = timezone.now()
        if row.revoked_at is not None:
            # v3.32.0 — grace period: a token revoked as part of a
            # rotation can still authenticate until ``grace_until``.
            # The successor token is the recommended path; we log a
            # deprecation hint (no plaintext) on each successful call.
            if (
                row.grace_until is not None
                and row.grace_until > now
            ):
                logger.info(
                    "migration_cloud_token_grace_used token_id=%s "
                    "user_id=%s grace_until=%s rotated_to=%s",
                    row.pk, row.user_id,
                    row.grace_until.isoformat(),
                    row.rotated_to_id,
                )
            else:
                raise exceptions.AuthenticationFailed("token revoked")
        if row.expires_at is not None and row.expires_at <= now:
            raise exceptions.AuthenticationFailed("token expired")
        if not row.user.is_active:
            raise exceptions.AuthenticationFailed("user inactive")

        # Best-effort last_used_at refresh; never block the request on it.
        try:
            row.last_used_at = timezone.now()
            row.save(update_fields=["last_used_at"])
        except Exception:  # pragma: no cover — defensive
            logger.exception("scoped-token last_used_at update failed")

        return (row.user, row)

    def authenticate_header(self, request):
        return 'Token realm="migration-cloud"'


# ─── Serializers ───────────────────────────────────────────────────────────


class _TokenMintRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    scopes = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=False,
    )
    tenant_scope_id = serializers.IntegerField(required=False, allow_null=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_scopes(self, value):
        unknown = [s for s in value if s not in KNOWN_SCOPES]
        if unknown:
            raise serializers.ValidationError(
                f"unknown scopes: {unknown}; known={sorted(KNOWN_SCOPES)}"
            )
        return value


class _TokenMaskedSerializer(serializers.ModelSerializer):
    token_preview = serializers.SerializerMethodField()

    class Meta:
        model = MigrationCloudAPIToken
        fields = [
            "id", "name", "scopes", "tenant_scope_id",
            "expires_at", "last_used_at", "revoked_at", "created_at",
            "grace_until", "rotated_to_id",
            "token_preview",
        ]
        read_only_fields = fields

    def get_token_preview(self, obj) -> str:
        """Return ``mc_...{last4-of-hash}`` so operators can identify rows."""
        return f"mc_...{obj.token_hash[-4:]}"


# ─── Viewset ───────────────────────────────────────────────────────────────


@extend_schema_view(
    list=extend_schema(
        tags=["Migration Cloud Tokens"],
        summary="List the caller's scoped API tokens (masked)",
        description=(
            "Returns token metadata only — plaintext is NEVER served by "
            "this endpoint. Operators identify rows by ``token_preview`` "
            "(``mc_...XXXX`` where XXXX are the last four hex chars of "
            "the sha256 lookup hash)."
        ),
        responses={
            200: _TokenMaskedSerializer(many=True),
            401: OpenApiResponse(description="Authentication required"),
        },
    ),
    retrieve=extend_schema(
        tags=["Migration Cloud Tokens"],
        summary="Get one scoped API token (masked)",
        responses={
            200: _TokenMaskedSerializer,
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Token not found"),
        },
    ),
)
class ScopedTokenViewSet(viewsets.ModelViewSet):
    """REST viewset for ``MigrationCloudAPIToken``.

    Endpoints:

    * ``POST   /tokens/``      — mint; returns plaintext **once**.
    * ``GET    /tokens/``      — list (masked).
    * ``GET    /tokens/<id>/`` — retrieve (masked).
    * ``DELETE /tokens/<id>/`` — revoke (sets ``revoked_at``).

    Scope rules apply via :class:`ScopedAPIPermission` — a caller using
    a scoped token must hold ``tokens:manage`` to mint/list/revoke.
    """

    serializer_class = _TokenMaskedSerializer
    # Token-first auth + scope gate. A caller authenticating with a scoped token
    # must hold ``tokens:manage`` to mint/list/revoke (session/JWT admins are
    # gated by the parent staff-or-tenant check). Previously ``[IsAuthenticated]``
    # only — the docstring's scope contract was not enforced.
    # See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (BLOCKER 5).
    authentication_classes = migration_cloud_authentication_classes()
    permission_classes = [IsAuthenticated, ScopedAPIPermission]
    http_method_names = ["get", "post", "delete", "head", "options"]
    lookup_field = "pk"

    def get_queryset(self):
        """Tokens scoped to the calling user."""
        user = getattr(self.request, "user", None)
        if user is None or not user.is_authenticated:
            # tenant-isolation-allow: scoped-tokens-anonymous-rejected-defense-in-depth
            return MigrationCloudAPIToken.objects.none()
        # tenant-isolation-allow: scoped-tokens-keyed-by-user-not-school
        return MigrationCloudAPIToken.objects.filter(user=user)

    @extend_schema(
        tags=["Migration Cloud Tokens"],
        summary="Mint a new scoped API token",
        description=(
            "Generates a fresh opaque token (256 bits of entropy). The "
            "plaintext is returned **only in this response**; the server "
            "stores ``sha256(token)`` and cannot recover it later. Treat "
            "this response like a credential — copy it into your secret "
            "store immediately."
        ),
        request=_TokenMintRequestSerializer,
        responses={
            201: OpenApiResponse(
                description=(
                    "Plaintext token + metadata. Shape: "
                    "``{token: 'mc_...', id, name, scopes, expires_at}``."
                ),
            ),
            400: OpenApiResponse(description="Invalid scopes or payload"),
            401: OpenApiResponse(description="Authentication required"),
            409: OpenApiResponse(description="Duplicate idempotency key"),
        },
    )
    @idempotent_post
    @safe_500
    def create(self, request, *args, **kwargs):
        serializer = _TokenMintRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        plaintext = _generate_token_plaintext()
        row = MigrationCloudAPIToken.objects.create(
            user=request.user,
            token_hash=_hash_token(plaintext),
            name=validated["name"],
            scopes=validated["scopes"],
            tenant_scope_id=validated.get("tenant_scope_id"),
            expires_at=validated.get("expires_at"),
        )
        logger.info(
            "migration_cloud_api_token_minted user_id=%s token_id=%s scopes=%s",
            request.user.pk, row.pk, row.scopes,
        )
        # Plaintext appears ONLY here — never logged, never stored.
        payload = _TokenMaskedSerializer(row).data
        payload["token"] = plaintext
        payload["warning"] = (
            "This token will not be shown again. Copy it now."
        )
        return Response(payload, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Migration Cloud Tokens"],
        summary="Revoke a scoped API token",
        description=(
            "Sets ``revoked_at = now()``. The row is preserved for audit; "
            "subsequent requests using the token are rejected with 401."
        ),
        responses={
            204: OpenApiResponse(description="Revoked"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Token not found"),
        },
    )
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.revoked_at = timezone.now()
        instance.save(update_fields=["revoked_at"])
        logger.info(
            "migration_cloud_api_token_revoked user_id=%s token_id=%s",
            request.user.pk, instance.pk,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=["Migration Cloud Tokens"],
        summary="Rotate a scoped API token",
        description=(
            "Mints a NEW token row inheriting ``scopes`` / ``tenant_scope`` "
            "/ ``expires_at`` from the source row, revokes the source, and "
            "sets a 7-day ``grace_until`` so the old token still "
            "authenticates while clients roll out the replacement. The "
            "new plaintext is returned **only in this response** "
            "(server stores sha256). The successor's ID is also written "
            "to the source row's ``rotated_to`` FK for audit. "
            "Idempotency-Key header is supported."
        ),
        request=None,
        responses={
            200: OpenApiResponse(
                description=(
                    "{token: 'mc_...', id, name, scopes, expires_at, "
                    "grace_until, rotated_from_id}"
                ),
            ),
            400: OpenApiResponse(description="Source token in a non-rotatable state"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Token not found"),
            409: OpenApiResponse(description="Duplicate idempotency key"),
        },
    )
    @action(detail=True, methods=["post"], url_path="rotate")
    @idempotent_post
    @safe_500
    def rotate(self, request, *args, **kwargs):
        """Mint a successor token + revoke source with a 7-day grace.

        The successor inherits the source's scopes / tenant_scope /
        expires_at. The source's ``revoked_at`` is set immediately, but
        ``grace_until`` keeps it authenticating for
        :data:`TOKEN_ROTATION_GRACE_DAYS` so clients can roll out.
        """
        source = self.get_object()
        if source.revoked_at is not None and (
            source.grace_until is None or source.grace_until <= timezone.now()
        ):
            return Response(
                {"error": "source token is already fully revoked"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plaintext = _generate_token_plaintext()
        now = timezone.now()
        successor = MigrationCloudAPIToken.objects.create(
            user=source.user,
            token_hash=_hash_token(plaintext),
            name=f"{source.name} (rotated {now.strftime('%Y-%m-%d')})"[:128],
            scopes=list(source.scopes or []),
            tenant_scope_id=source.tenant_scope_id,
            expires_at=source.expires_at,
        )
        source.revoked_at = now
        source.grace_until = now + timedelta(days=TOKEN_ROTATION_GRACE_DAYS)
        source.rotated_to = successor
        source.save(update_fields=["revoked_at", "grace_until", "rotated_to"])
        logger.info(
            "migration_cloud_api_token_rotated user_id=%s source_id=%s "
            "successor_id=%s grace_until=%s",
            request.user.pk, source.pk, successor.pk,
            source.grace_until.isoformat(),
        )
        payload = _TokenMaskedSerializer(successor).data
        payload["token"] = plaintext
        payload["rotated_from_id"] = source.pk
        payload["grace_until"] = source.grace_until.isoformat()
        payload["warning"] = (
            "This token will not be shown again. Copy it now. "
            f"The old token continues to authenticate for "
            f"{TOKEN_ROTATION_GRACE_DAYS} days; rotate your clients before "
            "the grace window closes."
        )
        return Response(payload, status=status.HTTP_200_OK)

    # Disable PUT/PATCH — tokens are immutable after mint except via revoke.
    @action(detail=False, methods=["get"], url_path="scopes/catalog")
    @extend_schema(
        tags=["Migration Cloud Tokens"],
        summary="List known scopes (catalog)",
        description="Returns the set of scope strings the API accepts.",
        responses={
            200: OpenApiResponse(description="{'scopes': [...]}"),
            401: OpenApiResponse(description="Authentication required"),
        },
    )
    def scopes_catalog(self, request):
        return Response({"scopes": sorted(KNOWN_SCOPES)})
