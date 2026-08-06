"""v3.38.0 Agent 5 — operator dashboard + JSONL export for the audit log.

Two staff-only views:

  * :class:`MigrationCloudAuditView` — renders the last 200 events
    filterable by ``event_type`` + ``date_from`` / ``date_to``. Hash
    columns rendered as truncated hex (first 12 chars) so the
    operator UI never displays the full 64-char identifiers.
  * :class:`MigrationCloudAuditExportView` — streams a JSONL response
    (`application/x-ndjson`) of all events matching ``?tenant=`` +
    ``?from=`` + ``?to=`` filters. When ``?verify_chain=1`` is set,
    each line carries an extra ``_chain_verified`` boolean computed
    by re-deriving the integrity hash (without modifying the stored
    value).

Both views are staff-only and emit ``# rbac-allow`` markers on the
URL patterns themselves (see ``urls.py``).
"""
from __future__ import annotations

import hmac
import json
import logging
from datetime import datetime, time

from apps.schools.control_plane import require_control_plane_access
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseBadRequest, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.decorators import method_decorator
from django.views import View

from apps.migration_cloud.models_audit import (
    GENESIS_SENTINEL,
    MigrationCloudAuditEvent,
    MigrationCloudAuditEventType,
    _sanitize_payload,
)

logger = logging.getLogger(__name__)


def _parse_iso_or_date(value: str, *, date_only_end: bool = False) -> datetime | None:
    """Parse either ``YYYY-MM-DD`` or full ISO-8601 datetime; None on bad."""
    if not value:
        return None
    d = parse_date(value)
    if d is not None:
        bound = time.max if date_only_end else time.min
        dt = datetime.combine(d, bound)
        if timezone.is_aware(timezone.now()):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    dt = parse_datetime(value)
    if dt is not None:
        if timezone.is_naive(dt) and timezone.is_aware(timezone.now()):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    return None


# rbac-allow: super-staff-audit-event-dashboard
@method_decorator(require_control_plane_access, name="dispatch")
class MigrationCloudAuditView(View):
    """GET /super/migration/audit/ — staff-only audit dashboard.

    Renders the last 200 events. Filters: ``?event_type=<t>`` exact,
    ``?date_from=<iso-or-date>``, ``?date_to=<iso-or-date>``,
    ``?tenant=<hash>`` (12-hex prefix; partial match prefix-only).

    Hash columns are truncated to 12 chars in the template. Payload
    summary is re-sanitized via ``_sanitize_payload`` before render
    as defense-in-depth.
    """

    template_name = "migration_cloud/operator/audit_dashboard.html"
    PAGE_SIZE = 50
    WINDOW_LIMIT = 200

    def get(self, request, *args, **kwargs):
        event_type = (request.GET.get("event_type") or "").strip()
        date_from_raw = (request.GET.get("date_from") or "").strip()
        date_to_raw = (request.GET.get("date_to") or "").strip()
        tenant_filter = (request.GET.get("tenant") or "").strip().lower()
        page_no_raw = request.GET.get("page") or "1"
        try:
            page_no = int(page_no_raw)
        except (TypeError, ValueError):
            page_no = 1

        # tenant-isolation-allow: audit-dashboard-staff-cross-tenant-forensic-view
        qs = MigrationCloudAuditEvent.objects.all().order_by("-created_at")

        valid_types = {c.value for c in MigrationCloudAuditEventType}
        if event_type and event_type in valid_types:
            qs = qs.filter(event_type=event_type)

        df = _parse_iso_or_date(date_from_raw)
        dt = _parse_iso_or_date(date_to_raw, date_only_end=True)
        if df is not None:
            qs = qs.filter(created_at__gte=df)
        if dt is not None:
            qs = qs.filter(created_at__lte=dt)
        if tenant_filter and all(c in "0123456789abcdef" for c in tenant_filter):
            qs = qs.filter(tenant_id_hash__startswith=tenant_filter[:12])

        qs = qs[: self.WINDOW_LIMIT]
        materialized = list(qs)
        paginator = Paginator(materialized, self.PAGE_SIZE)
        page = paginator.get_page(page_no)

        rows = []
        for row in page.object_list:
            try:
                clean_payload = _sanitize_payload(row.payload_summary or {})
            except ValueError:
                clean_payload = {"_error": "payload_rejected_at_render"}
            rows.append({
                "id": str(row.id),
                "tenant_id_hash": row.tenant_id_hash,
                "event_type": row.event_type,
                "actor_id_truncated": (row.actor_id or "")[:12],
                "event_subject_hash_truncated": (
                    row.event_subject_hash or ""
                )[:12],
                "payload_json": json.dumps(
                    clean_payload, sort_keys=True, indent=2,
                ),
                "created_at_iso": row.created_at_iso,
                "integrity_hash_truncated": row.integrity_hash[:12],
                "prev_event_hash_truncated": row.prev_event_hash[:12],
            })

        context = {
            "page_title": "Migration Cloud — audit log",
            "shell": kwargs.get("shell", "super"),
            "rows": rows,
            "page_obj": page,
            "valid_types": sorted(valid_types),
            "event_type_filter": event_type,
            "date_from": date_from_raw,
            "date_to": date_to_raw,
            "tenant_filter": tenant_filter,
        }
        return render(request, self.template_name, context)


def _verify_chain_state(
    events_in_order: list[MigrationCloudAuditEvent],
) -> dict[str, bool]:
    """Return {event_id: verified_bool} for a per-tenant-ordered list.

    Walks forward in time. ``hmac.compare_digest`` for the chain hash
    comparison.
    """
    state: dict[str, bool] = {}
    prev_hash = GENESIS_SENTINEL
    for ev in events_in_order:
        expected = ev.recompute_integrity_hash()
        own_ok = hmac.compare_digest(
            expected.encode("ascii"), ev.integrity_hash.encode("ascii"),
        )
        link_ok = hmac.compare_digest(
            prev_hash.encode("ascii"), ev.prev_event_hash.encode("ascii"),
        )
        state[str(ev.id)] = bool(own_ok and link_ok)
        prev_hash = ev.integrity_hash
    return state


# rbac-allow: super-staff-audit-event-export
@method_decorator(require_control_plane_access, name="dispatch")
class MigrationCloudAuditExportView(View):
    """GET /super/migration/audit/export/ — JSONL stream.

    Query parameters:

      * ``?tenant=<hash>``     12-hex prefix (required for tenant-scoped
                                exports; omit for cross-tenant).
      * ``?from=<iso-or-date>`` lower bound on ``created_at``.
      * ``?to=<iso-or-date>``   upper bound on ``created_at``.
      * ``?verify_chain=1``    additionally include ``_chain_verified``
                                bool per line.

    Response is ``application/x-ndjson`` streamed in 100-row pages.
    Each line is a JSON object; the entire response is parseable
    line-by-line.
    """

    PAGE_SIZE = 100

    def get(self, request, *args, **kwargs):
        tenant = (request.GET.get("tenant") or "").strip().lower()
        date_from_raw = (request.GET.get("from") or "").strip()
        date_to_raw = (request.GET.get("to") or "").strip()
        verify_chain = (request.GET.get("verify_chain") or "").strip() in (
            "1", "true", "True", "yes",
        )
        # v3.39.0 Agent 2 — opt-in root-key signature verification.
        # Adds ``_root_signature_verified: true|false|null`` to each
        # line. ``null`` means the event was written before the signing
        # key was provisioned (legacy event, NOT a tamper signal).
        verify_root_signature_flag = (
            request.GET.get("verify_root_signature") or ""
        ).strip() in ("1", "true", "True", "yes")

        # Validate tenant prefix shape if supplied.
        if tenant and (
            len(tenant) > 12 or any(c not in "0123456789abcdef" for c in tenant)
        ):
            return HttpResponseBadRequest(
                "tenant must be a 1-12 hex char prefix"
            )

        df = _parse_iso_or_date(date_from_raw) if date_from_raw else None
        dt = (
            _parse_iso_or_date(date_to_raw, date_only_end=True)
            if date_to_raw
            else None
        )

        # tenant-isolation-allow: audit-export-staff-cross-tenant-forensic-export
        qs = MigrationCloudAuditEvent.objects.all().order_by("created_at", "id")
        if tenant:
            qs = qs.filter(tenant_id_hash__startswith=tenant)
        if df is not None:
            qs = qs.filter(created_at__gte=df)
        if dt is not None:
            qs = qs.filter(created_at__lte=dt)

        logger.info(
            "migration_cloud.audit_export user_id=%s tenant_prefix=%s "
            "from=%s to=%s verify_chain=%s verify_root_signature=%s",
            getattr(request.user, "pk", None),
            tenant or "",
            date_from_raw or "",
            date_to_raw or "",
            verify_chain,
            verify_root_signature_flag,
        )

        # Resolve the root-signature verifier once (lazy import — the
        # service module is imported only when the operator opts in).
        _verify_root_signature = None
        if verify_root_signature_flag:
            from apps.migration_cloud.services.audit_root_signing import (
                verify_root_signature as _verify_root_signature,
            )

        def _stream():
            page_no = 0
            # Pre-compute per-tenant chain state when verify_chain is on.
            # We page through the qs to keep memory bounded; verification
            # needs in-order events per tenant, which the qs already
            # provides because we filter by tenant prefix when present.
            per_tenant_prev_hash: dict[str, str] = {}

            def _previous_hash_for(ev: MigrationCloudAuditEvent) -> str:
                # Date-filtered exports may start mid-chain. Seed from
                # the prior persisted event for that tenant so clean
                # rows do not get marked broken just because their
                # predecessor is outside the export window.
                # tenant-isolation-allow: audit-export-chain-seed-prev-event
                prev = (
                    MigrationCloudAuditEvent.objects
                    .filter(tenant_id_hash=ev.tenant_id_hash)
                    .filter(
                        Q(created_at__lt=ev.created_at)
                        | Q(created_at=ev.created_at, id__lt=ev.id)
                    )
                    .order_by("-created_at", "-id")
                    .only("integrity_hash")
                    .first()
                )
                return prev.integrity_hash if prev is not None else GENESIS_SENTINEL

            while True:
                start = page_no * self.PAGE_SIZE
                stop = start + self.PAGE_SIZE
                page = list(qs[start:stop])
                if not page:
                    break
                for ev in page:
                    line_dict = ev.to_export_dict()
                    if verify_chain:
                        expected = ev.recompute_integrity_hash()
                        own_ok = hmac.compare_digest(
                            expected.encode("ascii"),
                            ev.integrity_hash.encode("ascii"),
                        )
                        prev_known = per_tenant_prev_hash.get(ev.tenant_id_hash)
                        if prev_known is None:
                            prev_known = _previous_hash_for(ev)
                        link_ok = hmac.compare_digest(
                            prev_known.encode("ascii"),
                            ev.prev_event_hash.encode("ascii"),
                        )
                        line_dict["_chain_verified"] = bool(own_ok and link_ok)
                        per_tenant_prev_hash[ev.tenant_id_hash] = (
                            ev.integrity_hash
                        )
                    if verify_root_signature_flag:
                        # ``_root_signature_verified`` is tri-valued
                        # to preserve the "unsigned legacy" signal
                        # distinct from "tampered" — None for legacy
                        # rows, True/False for present-and-checked.
                        try:
                            line_dict["_root_signature_verified"] = (
                                _verify_root_signature(ev)
                            )
                        except NotImplementedError:
                            # HSM backend reserved but not implemented —
                            # surface to consumer as null so they don't
                            # over-trust silent verification.
                            line_dict["_root_signature_verified"] = None
                    yield (
                        json.dumps(
                            line_dict, sort_keys=True, ensure_ascii=False,
                        )
                        + "\n"
                    ).encode("utf-8")
                page_no += 1
                if len(page) < self.PAGE_SIZE:
                    break

        response = StreamingHttpResponse(
            _stream(),
            content_type="application/x-ndjson",
        )
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


__all__ = [
    "MigrationCloudAuditView",
    "MigrationCloudAuditExportView",
]
