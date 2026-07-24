"""Webhook subscription REST surface for the Migration Cloud API (v3.29).

Endpoints:

  * ``POST   /webhooks/``       — register; secret is returned ONCE.
  * ``GET    /webhooks/``       — list subscriptions for the caller's tenant.
  * ``GET    /webhooks/<id>/``  — retrieve.
  * ``DELETE /webhooks/<id>/``  — deactivate (sets ``active=False``).

Secret handling:
    The platform generates the HMAC secret at creation time and returns
    it **once** in the response. ``secret_ciphertext`` stores the secret
    encrypted at rest via :class:`EncryptedBinaryField`
    (Fernet AES-128-CBC + HMAC-SHA256 — see
    :mod:`apps.accounts.legacy_hashes.encryption`), used by
    :mod:`apps.migration_cloud.api.webhook_dispatch` to sign outbound
    deliveries (reads transparently decrypt). ``secret_hash`` (sha256
    of the plaintext) is also stored as a verification aid for operator
    support workflows.

Tenant isolation: list/retrieve filter on ``request.school``; staff see
all rows.
"""

from __future__ import annotations

import hashlib
import logging
import secrets

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import serializers, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.migration_cloud.models import (
    MigrationCloudWebhookSubscription,
)
from apps.migration_cloud.reliability import idempotent_post, safe_500

from .auth import migration_cloud_authentication_classes
from .permissions import ScopedAPIPermission

logger = logging.getLogger(__name__)


def _generate_secret() -> tuple[str, bytes, str]:
    """Return ``(plaintext, ciphertext_bytes, sha256_hex)`` for a fresh secret.

    Plaintext is base64-url over 32 random bytes (256 bits). The platform
    treats the secret as opaque material; receivers HMAC-sign request
    bodies with it to verify provenance.
    """
    plaintext = "whsec_" + secrets.token_urlsafe(32)
    # v3.32.0: the field descriptor (EncryptedBinaryField) Fernet-wraps
    # this value on save and transparently unwraps at read time, so we
    # hand it raw plaintext bytes here. The sha256 digest still covers
    # the plaintext so support-flow verification matches the secret the
    # caller copies down.
    ciphertext = plaintext.encode("utf-8")
    digest = hashlib.sha256(ciphertext).hexdigest()
    return plaintext, ciphertext, digest


# ─── Serializers ───────────────────────────────────────────────────────────


class _WebhookCreateSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=512)
    event_types = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=True,
        required=False,
    )

    def validate_url(self, value):
        if not value.lower().startswith("https://"):
            raise serializers.ValidationError(
                "webhook URL must be https:// — refuse cleartext delivery"
            )
        # SSRF guard: a tenant must not register a delivery target that resolves
        # to a private / loopback / link-local (cloud-metadata) address.
        from apps.security.ssrf import is_safe_public_url

        safe, _reason = is_safe_public_url(value, allow_http=False)
        if not safe:
            raise serializers.ValidationError(
                "webhook URL must be a public address (private/internal hosts are refused)"
            )
        return value


class _WebhookMaskedSerializer(serializers.ModelSerializer):
    tenant_id = serializers.IntegerField(source="tenant.pk", read_only=True)
    created_by_id = serializers.IntegerField(
        source="created_by.pk", read_only=True, allow_null=True,
    )
    secret_preview = serializers.SerializerMethodField()

    class Meta:
        model = MigrationCloudWebhookSubscription
        fields = [
            "id", "tenant_id", "url", "event_types", "active",
            "created_by_id", "last_delivery_status",
            "created_at", "updated_at", "secret_preview",
        ]
        read_only_fields = fields

    def get_secret_preview(self, obj) -> str:
        return f"whsec_...{obj.secret_hash[-4:]}" if obj.secret_hash else ""


# ─── Viewset ───────────────────────────────────────────────────────────────


@extend_schema_view(
    list=extend_schema(
        tags=["Migration Cloud Webhooks"],
        summary="List webhook subscriptions visible to the caller",
        description=(
            "Tenant callers see their own school's subscriptions; staff "
            "callers see all. Secret material is NEVER returned — only "
            "the last 4 hex chars of ``sha256(secret)`` as a preview."
        ),
        responses={
            200: _WebhookMaskedSerializer(many=True),
            401: OpenApiResponse(description="Authentication required"),
        },
    ),
    retrieve=extend_schema(
        tags=["Migration Cloud Webhooks"],
        summary="Get one webhook subscription (masked)",
        responses={
            200: _WebhookMaskedSerializer,
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Subscription not found"),
        },
    ),
)
class WebhookSubscriptionViewSet(viewsets.ModelViewSet):
    """REST viewset for ``MigrationCloudWebhookSubscription``."""

    serializer_class = _WebhookMaskedSerializer
    authentication_classes = migration_cloud_authentication_classes()
    permission_classes = [IsAuthenticated, ScopedAPIPermission]
    http_method_names = ["get", "post", "delete", "head", "options"]
    lookup_field = "pk"

    def get_queryset(self):
        user = getattr(self.request, "user", None)
        if user is None or not user.is_authenticated:
            # tenant-isolation-allow: webhooks-anonymous-rejected-defense-in-depth
            return MigrationCloudWebhookSubscription.objects.none()
        if user.is_staff:
            # tenant-isolation-allow: webhooks-staff-operator-shell-cross-tenant-by-design
            return MigrationCloudWebhookSubscription.objects.all()
        school = getattr(self.request, "school", None) or getattr(
            self.request, "tenant", None,
        )
        school_pk = getattr(school, "pk", None)
        if school_pk is None:
            # tenant-isolation-allow: webhooks-no-tenant-binding-deny-by-default
            return MigrationCloudWebhookSubscription.objects.none()
        # tenant-isolation-allow: webhooks-scoped-via-request-user-school
        return MigrationCloudWebhookSubscription.objects.filter(tenant_id=school_pk)

    @extend_schema(
        tags=["Migration Cloud Webhooks"],
        summary="Register a new webhook subscription",
        description=(
            "Returns the HMAC secret **only in this response**. Future "
            "delivery payloads are signed with this secret; the receiver "
            "verifies via ``X-RunMyCampus-Signature: sha256=<hex>``. "
            "Copy the secret into your secret store immediately."
        ),
        request=_WebhookCreateSerializer,
        responses={
            201: OpenApiResponse(
                description=(
                    "{id, url, event_types, secret, secret_preview, "
                    "active, created_at}"
                ),
            ),
            400: OpenApiResponse(description="Invalid URL or payload"),
            401: OpenApiResponse(description="Authentication required"),
            409: OpenApiResponse(description="Duplicate idempotency key"),
        },
    )
    @idempotent_post
    @safe_500
    def create(self, request, *args, **kwargs):
        serializer = _WebhookCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        # Resolve tenant from the request (staff may register on behalf
        # of a school passed as ?tenant_id=).
        user = request.user
        school = getattr(request, "school", None) or getattr(request, "tenant", None)
        target_tenant_id = getattr(school, "pk", None)
        if user.is_staff:
            # Allow staff to pass ?tenant_id=N explicitly
            try:
                explicit = request.query_params.get("tenant_id")
                if explicit:
                    target_tenant_id = int(explicit)
            except (ValueError, TypeError, AttributeError):
                pass
        if target_tenant_id is None:
            return Response(
                {"error": "no tenant binding for caller"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plaintext, ciphertext, digest = _generate_secret()

        row = MigrationCloudWebhookSubscription.objects.create(
            tenant_id=target_tenant_id,
            url=validated["url"],
            event_types=validated.get("event_types") or [],
            secret_hash=digest,
            secret_ciphertext=ciphertext,
            created_by=user if user.is_authenticated else None,
        )
        logger.info(
            "migration_cloud_webhook_subscribed user_id=%s sub_id=%s tenant_id=%s url_host=%s",
            user.pk, row.pk, target_tenant_id, validated["url"].split("/", 3)[2],
        )
        payload = _WebhookMaskedSerializer(row).data
        payload["secret"] = plaintext
        payload["warning"] = (
            "This secret will not be shown again. Copy it now. "
            "Use it to verify the X-RunMyCampus-Signature header on "
            "incoming webhook deliveries."
        )
        return Response(payload, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Migration Cloud Webhooks"],
        summary="Deactivate a webhook subscription",
        description="Sets ``active=False``; the dispatcher stops enqueueing new deliveries.",
        responses={
            204: OpenApiResponse(description="Deactivated"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Subscription not found"),
        },
    )
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        was_active = bool(instance.active)
        instance.active = False
        instance.updated_at = timezone.now()
        instance.save(update_fields=["active", "updated_at"])
        logger.info(
            "migration_cloud_webhook_deactivated user_id=%s sub_id=%s",
            request.user.pk, instance.pk,
        )
        # v3.39.0 Agent 2 — emit reserved ``webhook.subscription.deleted``.
        # Best-effort; never breaks the API path. We hash the subscription
        # id into the payload prefix instead of writing the raw integer so
        # the audit log never accumulates raw FK identifiers.
        try:
            from apps.migration_cloud.models_audit import (
                MigrationCloudAuditEvent as _AuditEvent,
            )

            def _slug_for_tenant_id(tenant_id) -> str:
                if tenant_id in (None, ""):
                    return ""
                try:
                    from apps.schools.models import School
                    # tenant-isolation-allow: audit-slug-lookup-cross-tenant-staff-view
                    school = School.objects.filter(
                        pk=tenant_id,
                    ).only("slug").first()
                    return getattr(school, "slug", "") or ""
                except Exception:  # broad-by-design — audit must never fail caller
                    return ""

            _AuditEvent.objects.record(
                _slug_for_tenant_id(instance.tenant_id) or "",
                "webhook.subscription.deleted",
                actor=request.user if request.user.is_authenticated else None,
                subject=str(instance.pk),
                payload_summary={
                    "action": "deactivated",
                    "subscription_id_hash_prefix": hashlib.sha256(
                        str(instance.pk).encode("utf-8")
                    ).hexdigest()[:12],
                    "was_active": was_active,
                    "via": "api",
                },
            )
        except Exception as exc:  # broad-by-design
            logger.error(
                "migration_cloud.audit: emit failed event_type=%s err=%s",
                "webhook.subscription.deleted", type(exc).__name__,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
