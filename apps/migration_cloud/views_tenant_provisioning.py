"""Tenant-admin SELF-SERVE Migration Cloud API-token + webhook provisioning.

Audit item **G-4**. Minting a scoped Migration Cloud API token and registering
an outbound webhook were OPERATOR-ONLY (staff, ``/super/migration/operator/…``),
so a partner / district could not self-provision — breaking the "integrate by
contract" model. The scoped-token AUTH is already enforced on the REST viewsets
(``MigrationCloudTokenAuthentication`` + ``ScopedAPIPermission``); this module is
the missing self-serve UI.

Security posture (mirrors :mod:`views_tenant_upload`):

* **Gate** — every view is a WRITE surface, gated by
  :class:`~apps.migration_cloud.views_tenant_upload._TenantAdminWriteRequiredMixin`
  (authenticated AND tenant-admin tier for ``request.school`` — owner /
  ``role=ADMIN`` / ``settings.manage`` + audited superuser break-glass). NOT
  ``is_staff`` (the platform mints tenant admins WITH ``is_staff``, so that would
  be exactly the wrong gate) and NOT the operator staff surface.
* **Tenant binding is FORCED** — a minted token's ``tenant_scope`` and a
  subscription's ``tenant`` are set to ``request.school`` server-side and are
  NEVER read from the request. A tenant admin cannot provision for another tenant.
* **Scope allowlist** — the caller may only grant the NON-operator scopes in
  :data:`TENANT_GRANTABLE_SCOPES`. ``tokens:manage`` (operator-only) is
  structurally ungrantable from here.
* **IDOR-safe** — list/revoke/deactivate resolve rows with the school in the
  WHERE clause, so a cross-tenant or unknown id is a 404 (never 403); id
  enumeration cannot distinguish "exists elsewhere" from "doesn't exist".

Every URL is pre-resolved in the view via ``_connector_reverse`` and passed to
the template as a context var, so the templates carry no cross-host ``{% url %}``
reverse (the connector namespace is nested under super / portal too, so a
hardcoded reverse would ``NoReverseMatch`` → 500 on the other mounts).
"""

from __future__ import annotations

import hashlib
import logging
import secrets

from django.contrib import messages
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from .api.scoped_tokens import (
    KNOWN_SCOPES,
    _generate_token_plaintext,
    _hash_token,
)
from .models import (
    MigrationCloudAPIToken,
    MigrationCloudWebhookSubscription,
)
from .views_connectors import _connector_reverse, _request_school
from .views_tenant_upload import _TenantAdminWriteRequiredMixin

logger = logging.getLogger(__name__)

# Scopes a TENANT ADMIN may self-grant from this surface. Deliberately EXCLUDES
# the operator-only ``tokens:manage`` — a partner managing its own school's data
# never needs to mint/rotate/revoke OTHER tokens programmatically (that stays an
# operator action). Kept in sync with the REST scope catalog by intersecting
# with ``KNOWN_SCOPES`` below, so an unknown value can never slip through.
TENANT_GRANTABLE_SCOPES: frozenset[str] = frozenset(
    {
        "bundles:read",
        "bundles:write",
        "artifacts:write",
        "reconcile:run",
        "templates:read",
        "webhooks:manage",
    }
)
# Defense-in-depth effective allowlist: must be a real catalog scope AND must
# never include the operator-only mint/manage scope, whatever the literal above
# says. This is the single value the POST handler validates against.
_EFFECTIVE_GRANTABLE_SCOPES: frozenset[str] = (
    TENANT_GRANTABLE_SCOPES & KNOWN_SCOPES
) - {"tokens:manage"}

# Sourced from the model field so no integer literal lives here (and the cap
# always matches the column).
_TOKEN_NAME_MAX: int = MigrationCloudAPIToken._meta.get_field("name").max_length

# Bound how many of the caller's OWN rows a list view renders. Their own school
# will never approach this; it just keeps the page finite.
_LIST_LIMIT = 50


def _safe_audit(school, event_type: str, **kwargs) -> None:
    """Best-effort append to the tamper-evident audit log; never break the view."""
    try:
        from .models_audit import MigrationCloudAuditEvent

        slug = getattr(school, "slug", "") or ""
        MigrationCloudAuditEvent.objects.record(slug, event_type, **kwargs)
    except Exception as exc:  # broad-by-design — audit must never fail the caller
        logger.error(
            "mc_tenant_provisioning_audit_emit_failed event=%s err=%s",
            event_type,
            type(exc).__name__,
        )


def _generate_webhook_secret() -> tuple[str, bytes, str]:
    """Return ``(plaintext, ciphertext_bytes, sha256_hex)`` for a fresh secret.

    Same wire shape as the operator subscribe surface — ``whsec_`` prefix,
    plaintext returned ONCE, only the sha256 preview + encrypted ciphertext
    persist.
    """
    plaintext = "whsec_" + secrets.token_urlsafe(32)
    ciphertext = plaintext.encode("utf-8")
    digest = hashlib.sha256(ciphertext).hexdigest()
    return plaintext, ciphertext, digest


def _token_row(request, row: MigrationCloudAPIToken) -> dict:
    """Mask a token row for the list template — NEVER includes plaintext."""
    return {
        "id": row.pk,
        "name": row.name,
        "scopes": list(row.scopes or []),
        "preview": f"mc_...{row.token_hash[-4:]}",
        "created_at": row.created_at,
        "last_used_at": row.last_used_at,
        "revoked_at": row.revoked_at,
        "is_active": row.is_active,
        "revoke_url": _connector_reverse(
            request, "provisioning-token-revoke", token_id=row.pk
        ),
    }


def _webhook_row(request, row: MigrationCloudWebhookSubscription) -> dict:
    """Mask a subscription row for the list template — NEVER includes the secret."""
    return {
        "id": row.pk,
        "url": row.url,
        "event_types": list(row.event_types or []),
        "active": row.active,
        "preview": f"whsec_...{row.secret_hash[-4:]}" if row.secret_hash else "",
        "created_at": row.created_at,
        "deactivate_url": _connector_reverse(
            request, "provisioning-webhook-deactivate", sub_id=row.pk
        ),
    }


class TenantTokenListView(_TenantAdminWriteRequiredMixin, View):
    """GET — list the caller's OWN school's scoped API tokens (masked)."""

    template_name = "migration_cloud/connector/provisioning_tokens.html"

    def get(self, request):
        school = _request_school(request)
        if school is None:
            raise Http404()
        # tenant-isolation-allow: mc-api-tokens-listed-scoped-to-request-school-tenant-scope-fk
        rows = MigrationCloudAPIToken.objects.filter(
            tenant_scope=school
        ).order_by("-created_at")[:_LIST_LIMIT]
        context = {
            "page_title": "API tokens",
            "school": school,
            "rows": [_token_row(request, r) for r in rows],
            "mint_url": _connector_reverse(request, "provisioning-token-mint"),
            "webhooks_url": _connector_reverse(request, "provisioning-webhooks"),
            "home_url": _connector_reverse(request, "connector-home"),
        }
        return render(request, self.template_name, context)


class TenantTokenMintView(_TenantAdminWriteRequiredMixin, View):
    """GET mint form + POST mints a token FORCE-BOUND to ``request.school``.

    The plaintext is rendered ONCE on the result page; the server stores only
    ``sha256(token)``. Scopes are restricted to :data:`TENANT_GRANTABLE_SCOPES`.
    """

    template_name = "migration_cloud/connector/provisioning_token_mint.html"
    result_template = "migration_cloud/connector/provisioning_token_result.html"

    def _form_context(self, request, school) -> dict:
        return {
            "page_title": "Mint an API token",
            "school": school,
            "grantable_scopes": sorted(_EFFECTIVE_GRANTABLE_SCOPES),
            "mint_url": _connector_reverse(request, "provisioning-token-mint"),
            "tokens_url": _connector_reverse(request, "provisioning-tokens"),
        }

    def get(self, request):
        school = _request_school(request)
        if school is None:
            raise Http404()
        return render(request, self.template_name, self._form_context(request, school))

    def post(self, request):
        school = _request_school(request)
        if school is None:
            raise Http404()
        name = (request.POST.get("name") or "").strip()
        scopes_raw = request.POST.getlist("scopes")
        mint_url = _connector_reverse(request, "provisioning-token-mint")

        if not name:
            messages.error(request, "Give the token a name so you can identify it later.")
            return HttpResponseRedirect(mint_url)
        if not scopes_raw:
            messages.error(request, "Choose at least one permission scope.")
            return HttpResponseRedirect(mint_url)
        # Reject anything outside the tenant allowlist — this is what makes
        # ``tokens:manage`` (and any future operator-only scope) ungrantable here.
        disallowed = [s for s in scopes_raw if s not in _EFFECTIVE_GRANTABLE_SCOPES]
        if disallowed:
            messages.error(
                request,
                "One or more selected permissions can't be granted from here.",
            )
            return HttpResponseRedirect(mint_url)

        plaintext = _generate_token_plaintext()
        # tenant_scope is FORCE-BOUND to the caller's OWN school — never read
        # from the request, so a tenant admin cannot mint for another tenant.
        row = MigrationCloudAPIToken.objects.create(
            user=request.user,
            token_hash=_hash_token(plaintext),
            name=name[:_TOKEN_NAME_MAX],
            scopes=scopes_raw,
            tenant_scope=school,
        )
        logger.info(
            "mc_tenant_token_minted user_id=%s school_id=%s token_id=%s scopes=%s",
            getattr(request.user, "pk", None),
            school.pk,
            row.pk,
            row.scopes,
        )
        _safe_audit(
            school,
            "token.mint",
            actor=request.user,
            subject=str(row.pk),
            payload_summary={
                "scopes_count": len(scopes_raw),
                "self_serve": True,
                "tenant_scoped": True,
            },
        )
        context = {
            "page_title": "Token created",
            "school": school,
            "row": _token_row(request, row),
            "plaintext": plaintext,
            "tokens_url": _connector_reverse(request, "provisioning-tokens"),
        }
        return render(request, self.result_template, context)


class TenantTokenRevokeView(_TenantAdminWriteRequiredMixin, View):
    """POST — revoke one of the caller's OWN school's tokens (IDOR-safe 404)."""

    def post(self, request, token_id: int):
        school = _request_school(request)
        if school is None:
            raise Http404()
        # School in the WHERE clause — a cross-tenant / unknown id is a 404, not
        # a 403, so id-enumeration can't distinguish "exists elsewhere".
        # tenant-isolation-allow: mc-api-token-revoke-scoped-to-request-school-tenant-scope-fk
        row = get_object_or_404(
            MigrationCloudAPIToken, pk=token_id, tenant_scope=school
        )
        if row.revoked_at is None:
            row.revoked_at = timezone.now()
            row.grace_until = None  # explicit revoke clears any rotation grace
            row.save(update_fields=["revoked_at", "grace_until"])
        logger.info(
            "mc_tenant_token_revoked user_id=%s school_id=%s token_id=%s",
            getattr(request.user, "pk", None),
            school.pk,
            row.pk,
        )
        _safe_audit(
            school,
            "token.revoke",
            actor=request.user,
            subject=str(row.pk),
            payload_summary={"self_serve": True},
        )
        messages.success(request, "Token revoked.")
        return HttpResponseRedirect(_connector_reverse(request, "provisioning-tokens"))


class TenantWebhookView(_TenantAdminWriteRequiredMixin, View):
    """GET create-form + list; POST creates a subscription bound to the school.

    The signing secret is rendered ONCE on the create response (via the
    ``result`` context var); only its sha256 preview + encrypted ciphertext
    persist.
    """

    template_name = "migration_cloud/connector/provisioning_webhooks.html"

    def _list_context(self, request, school, result: dict | None = None) -> dict:
        # tenant-isolation-allow: mc-webhook-subscriptions-listed-scoped-to-request-school-tenant-fk
        rows = MigrationCloudWebhookSubscription.objects.filter(
            tenant=school
        ).order_by("-created_at")[:_LIST_LIMIT]
        return {
            "page_title": "Webhook subscriptions",
            "school": school,
            "rows": [_webhook_row(request, r) for r in rows],
            "result": result,
            "webhooks_url": _connector_reverse(request, "provisioning-webhooks"),
            "tokens_url": _connector_reverse(request, "provisioning-tokens"),
            "home_url": _connector_reverse(request, "connector-home"),
        }

    def get(self, request):
        school = _request_school(request)
        if school is None:
            raise Http404()
        return render(request, self.template_name, self._list_context(request, school))

    def post(self, request):
        school = _request_school(request)
        if school is None:
            raise Http404()
        url = (request.POST.get("url") or "").strip()
        event_types_raw = (request.POST.get("event_types") or "").strip()
        webhooks_url = _connector_reverse(request, "provisioning-webhooks")

        if not url.lower().startswith("https://"):
            messages.error(request, "The endpoint URL must start with https://")
            return HttpResponseRedirect(webhooks_url)
        event_types = [s.strip() for s in event_types_raw.split(",") if s.strip()]

        plaintext, ciphertext, digest = _generate_webhook_secret()
        # tenant is FORCE-BOUND to the caller's OWN school — never read from the
        # request, so a tenant admin cannot subscribe on behalf of another tenant.
        row = MigrationCloudWebhookSubscription.objects.create(
            tenant=school,
            url=url,
            event_types=event_types,
            secret_hash=digest,
            secret_ciphertext=ciphertext,
            created_by=request.user,
        )
        logger.info(
            "mc_tenant_webhook_created user_id=%s school_id=%s sub_id=%s url_host=%s",
            getattr(request.user, "pk", None),
            school.pk,
            row.pk,
            url.split("/", 3)[2],
        )
        _safe_audit(
            school,
            "webhook.subscription.created",
            actor=request.user,
            subject=str(row.pk),
            payload_summary={
                "event_types_count": len(event_types),
                "self_serve": True,
            },
        )
        messages.success(request, "Webhook subscription created.")
        result = {"row": _webhook_row(request, row), "plaintext": plaintext}
        return render(
            request, self.template_name, self._list_context(request, school, result=result)
        )


class TenantWebhookDeactivateView(_TenantAdminWriteRequiredMixin, View):
    """POST — deactivate one of the caller's OWN subscriptions (IDOR-safe 404)."""

    def post(self, request, sub_id: int):
        school = _request_school(request)
        if school is None:
            raise Http404()
        # School in the WHERE clause — cross-tenant / unknown id → 404, not 403.
        # tenant-isolation-allow: mc-webhook-deactivate-scoped-to-request-school-tenant-fk
        row = get_object_or_404(
            MigrationCloudWebhookSubscription, pk=sub_id, tenant=school
        )
        if row.active:
            row.active = False
            row.updated_at = timezone.now()
            row.save(update_fields=["active", "updated_at"])
        logger.info(
            "mc_tenant_webhook_deactivated user_id=%s school_id=%s sub_id=%s",
            getattr(request.user, "pk", None),
            school.pk,
            row.pk,
        )
        _safe_audit(
            school,
            "webhook.subscription.deleted",
            actor=request.user,
            subject=str(row.pk),
            payload_summary={"action": "deactivated", "self_serve": True},
        )
        messages.success(request, "Webhook subscription deactivated.")
        return HttpResponseRedirect(_connector_reverse(request, "provisioning-webhooks"))
