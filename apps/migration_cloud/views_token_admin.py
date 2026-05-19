"""Operator-shell screens for Migration Cloud scoped API tokens.

NOT a DRF surface — these are staff-only Django views rendered into the
control-plane skeleton. The REST endpoints at
``/super/migration/api/v1/tokens/`` cover programmatic use; this module
covers point-and-click operator workflows (the partner-success team
needs to mint / rotate / revoke without curl).

Permission model: ``request.user.is_staff`` everywhere. The URL patterns
themselves are marked with ``# rbac-allow: staff-only-operator-token-and-webhook-management``
so ``audit_role_permission_matrix`` records the intentional staff-only
gate.

Plaintext token discipline: ``token_mint_result.html`` is the ONLY view
that renders the plaintext, and only on the synchronous POST response.
The list view shows ``mc_...XXXX`` (last-4 of sha256 hash) only.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from apps.migration_cloud.api.scoped_tokens import (
    KNOWN_SCOPES,
    TOKEN_ROTATION_GRACE_DAYS,
    _generate_token_plaintext,
    _hash_token,
)
from apps.migration_cloud.models import MigrationCloudAPIToken

logger = logging.getLogger(__name__)


def _token_row_for_table(row: MigrationCloudAPIToken) -> dict:
    """Mask a token row to the dict shape used by the list template.

    Crucially: NO plaintext (never persisted, can't recover). The preview
    is ``mc_…XXXX`` — the last 4 hex chars of the sha256 lookup hash.
    Operators identify tokens via this + the name + the user.
    """
    return {
        "id": row.pk,
        "name": row.name,
        "user_label": getattr(row.user, "get_username", lambda: f"user#{row.user_id}")(),
        "tenant_id": row.tenant_scope_id,
        "scopes": list(row.scopes or []),
        "preview": f"mc_...{row.token_hash[-4:]}",
        "created_at": row.created_at,
        "last_used_at": row.last_used_at,
        "revoked_at": row.revoked_at,
        "grace_until": row.grace_until,
        "rotated_to_id": row.rotated_to_id,
        "is_active": row.is_active,
    }


@method_decorator(staff_member_required, name="dispatch")
class MigrationCloudTokenListView(View):
    """GET /super/migration/operator/tokens/ — staff-only token table."""

    template_name = "migration_cloud/operator/token_list.html"

    def get(self, request, *args, **kwargs):
        tenant_filter = request.GET.get("tenant_id")
        user_filter = request.GET.get("user_id")
        # tenant-isolation-allow: operator-shell-staff-cross-tenant-token-administration
        qs = MigrationCloudAPIToken.objects.select_related("user", "tenant_scope").all()
        try:
            if tenant_filter:
                qs = qs.filter(tenant_scope_id=int(tenant_filter))
            if user_filter:
                qs = qs.filter(user_id=int(user_filter))
        except (TypeError, ValueError):
            pass
        rows = [_token_row_for_table(r) for r in qs[:500]]
        context = {
            "page_title": "Migration Cloud — scoped API tokens",
            "shell": kwargs.get("shell", "super"),
            "rows": rows,
            "filter_tenant_id": tenant_filter or "",
            "filter_user_id": user_filter or "",
        }
        return render(request, self.template_name, context)


@method_decorator(staff_member_required, name="dispatch")
class MigrationCloudTokenMintView(View):
    """GET form + POST creates a token; plaintext shown ONCE."""

    template_name = "migration_cloud/operator/token_mint.html"
    result_template = "migration_cloud/operator/token_mint_result.html"

    def get(self, request, *args, **kwargs):
        context = {
            "page_title": "Mint a Migration Cloud API token",
            "shell": kwargs.get("shell", "super"),
            "known_scopes": sorted(KNOWN_SCOPES),
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        name = (request.POST.get("name") or "").strip()
        scopes_raw = request.POST.getlist("scopes")
        tenant_scope_id = (request.POST.get("tenant_scope_id") or "").strip()
        if not name:
            messages.error(request, "Token name is required.")
            return HttpResponseRedirect(request.path)
        if not scopes_raw:
            messages.error(request, "Pick at least one scope.")
            return HttpResponseRedirect(request.path)
        unknown = [s for s in scopes_raw if s not in KNOWN_SCOPES]
        if unknown:
            messages.error(request, f"Unknown scopes: {unknown}")
            return HttpResponseRedirect(request.path)

        plaintext = _generate_token_plaintext()
        tenant_scope_pk = None
        if tenant_scope_id:
            try:
                tenant_scope_pk = int(tenant_scope_id)
            except (TypeError, ValueError):
                tenant_scope_pk = None
        row = MigrationCloudAPIToken.objects.create(
            user=request.user,
            token_hash=_hash_token(plaintext),
            name=name[:128],
            scopes=scopes_raw,
            tenant_scope_id=tenant_scope_pk,
        )
        logger.info(
            "migration_cloud_operator_token_minted user_id=%s token_id=%s scopes=%s",
            request.user.pk, row.pk, row.scopes,
        )
        context = {
            "page_title": "Token minted",
            "shell": kwargs.get("shell", "super"),
            "row": _token_row_for_table(row),
            "plaintext": plaintext,
        }
        return render(request, self.result_template, context)


@method_decorator(staff_member_required, name="dispatch")
class MigrationCloudTokenRevokeView(View):
    """POST /super/migration/operator/tokens/<id>/revoke/ — immediate revoke."""

    def post(self, request, *args, **kwargs):
        token_id = kwargs.get("token_id")
        # tenant-isolation-allow: operator-shell-staff-cross-tenant-token-administration
        row = get_object_or_404(MigrationCloudAPIToken, pk=token_id)
        row.revoked_at = timezone.now()
        row.grace_until = None  # explicit revoke clears any grace
        row.save(update_fields=["revoked_at", "grace_until"])
        logger.info(
            "migration_cloud_operator_token_revoked user_id=%s token_id=%s",
            request.user.pk, row.pk,
        )
        messages.success(request, f"Token #{row.pk} revoked.")
        shell = kwargs.get("shell", "super")
        namespace = (
            "migration_cloud_portal" if shell == "portal" else "migration_cloud_super"
        )
        return HttpResponseRedirect(reverse(f"{namespace}:operator_token_list"))


@method_decorator(staff_member_required, name="dispatch")
class TokenRotationChainView(View):
    """GET /super/migration/operator/tokens/<id>/chain/ — walk the rotation chain.

    Each :class:`MigrationCloudAPIToken` may carry a ``rotated_to`` FK
    pointing at the successor minted by a previous Rotate operation. We
    walk that chain forwards from the requested anchor (most recent →
    successor) AND backwards to the original ancestor so the operator
    sees the entire lineage at a glance.

    Grace-window status: each row reports ``in_grace`` (revoked but
    successor's grace window is still active) so a partner-success rep
    can answer "is the old token still usable?" without SQL.

    Paginated when the combined chain exceeds 20 rows.
    """

    template_name = "migration_cloud/operator/token_rotation_chain.html"
    PAGE_SIZE = 20
    MAX_WALK_DEPTH = 200  # safety belt against pathological cycles

    def _walk_forward(self, anchor: MigrationCloudAPIToken) -> list:
        """Return [anchor, successor, successor-of-successor, ...]."""
        chain = []
        seen_ids = set()
        cursor = anchor
        depth = 0
        while cursor is not None and depth < self.MAX_WALK_DEPTH:
            if cursor.pk in seen_ids:
                break  # cycle defense
            seen_ids.add(cursor.pk)
            chain.append(cursor)
            successor_id = getattr(cursor, "rotated_to_id", None)
            if not successor_id:
                break
            try:
                # tenant-isolation-allow: operator-shell-staff-cross-tenant-token-administration
                cursor = MigrationCloudAPIToken.objects.get(pk=successor_id)
            except MigrationCloudAPIToken.DoesNotExist:
                break
            depth += 1
        return chain

    def _walk_backward(self, anchor: MigrationCloudAPIToken) -> list:
        """Return [ancestor-N, ..., parent, anchor's-parent] (excludes anchor)."""
        ancestors = []
        seen_ids = {anchor.pk}
        depth = 0
        while depth < self.MAX_WALK_DEPTH:
            # tenant-isolation-allow: operator-shell-staff-cross-tenant-token-administration
            parent_qs = MigrationCloudAPIToken.objects.filter(
                rotated_to_id=(ancestors[0].pk if ancestors else anchor.pk)
            )
            parent = parent_qs.first()
            if parent is None or parent.pk in seen_ids:
                break
            seen_ids.add(parent.pk)
            ancestors.insert(0, parent)
            depth += 1
        return ancestors

    def _row_for_chain(self, row: MigrationCloudAPIToken, anchor_pk: int) -> dict:
        """Project one token into the chain template's row shape."""
        now = timezone.now()
        in_grace = (
            row.revoked_at is not None
            and row.grace_until is not None
            and row.grace_until > now
        )
        return {
            "id": row.pk,
            "name": row.name,
            "preview": f"mc_...{row.token_hash[-4:]}",
            "scopes": list(row.scopes or []),
            "created_at": row.created_at,
            "revoked_at": row.revoked_at,
            "grace_until": row.grace_until,
            "rotated_to_id": row.rotated_to_id,
            "is_active": row.is_active,
            "in_grace": in_grace,
            "is_anchor": row.pk == anchor_pk,
        }

    def get(self, request, *args, **kwargs):
        token_id = kwargs.get("token_id")
        # tenant-isolation-allow: operator-shell-staff-cross-tenant-token-administration
        anchor = get_object_or_404(MigrationCloudAPIToken, pk=token_id)

        ancestors = self._walk_backward(anchor)
        forward = self._walk_forward(anchor)
        # Combined timeline: oldest ancestor → ... → anchor → ... → latest successor.
        full_chain = ancestors + forward

        page_param = request.GET.get("page", "1")
        try:
            page_num = max(int(page_param), 1)
        except (TypeError, ValueError):
            page_num = 1

        total = len(full_chain)
        page_count = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        page_num = min(page_num, page_count)
        start = (page_num - 1) * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        page_rows = [
            self._row_for_chain(r, anchor.pk) for r in full_chain[start:end]
        ]

        logger.info(
            "migration_cloud_operator_token_chain_viewed user_id=%s anchor_id=%s "
            "chain_len=%s page=%s",
            request.user.pk, anchor.pk, total, page_num,
        )

        context = {
            "page_title": f"Token rotation chain — token #{anchor.pk}",
            "shell": kwargs.get("shell", "super"),
            "anchor_id": anchor.pk,
            "rows": page_rows,
            "chain_total": total,
            "page_num": page_num,
            "page_count": page_count,
            "page_size": self.PAGE_SIZE,
            "has_prev": page_num > 1,
            "has_next": page_num < page_count,
        }
        return render(request, self.template_name, context)


@method_decorator(staff_member_required, name="dispatch")
class MigrationCloudTokenRotateView(View):
    """POST /super/migration/operator/tokens/<id>/rotate/ — same logic as API rotate."""

    template_name = "migration_cloud/operator/token_mint_result.html"

    def post(self, request, *args, **kwargs):
        token_id = kwargs.get("token_id")
        # tenant-isolation-allow: operator-shell-staff-cross-tenant-token-administration
        source = get_object_or_404(MigrationCloudAPIToken, pk=token_id)
        if source.revoked_at is not None and (
            source.grace_until is None or source.grace_until <= timezone.now()
        ):
            messages.error(request, "Source token is already fully revoked.")
            shell = kwargs.get("shell", "super")
            namespace = (
                "migration_cloud_portal" if shell == "portal"
                else "migration_cloud_super"
            )
            return HttpResponseRedirect(reverse(f"{namespace}:operator_token_list"))

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
            "migration_cloud_operator_token_rotated user_id=%s source_id=%s "
            "successor_id=%s grace_until=%s",
            request.user.pk, source.pk, successor.pk,
            source.grace_until.isoformat(),
        )
        context = {
            "page_title": "Token rotated",
            "shell": kwargs.get("shell", "super"),
            "row": _token_row_for_table(successor),
            "plaintext": plaintext,
            "rotated_from_id": source.pk,
            "grace_until": source.grace_until,
        }
        return render(request, self.template_name, context)
