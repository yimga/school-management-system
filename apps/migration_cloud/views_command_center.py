"""v3.40.0 Agent 6 — Migration Cloud Command Center operator dashboard.

Single staff-only GET surface at ``/super/migration/command-center/``
aggregating a **read-only snapshot** of every Migration Cloud pillar
in one screen. Designed for operator situational awareness — answers
"is the platform healthy *right now*" in <500ms aggregate query time.

Eight sections, each computed by an isolated ``_section_<name>()``
helper that wraps its queries in ``try/except`` and returns a dict.
On failure the helper returns ``{"error": "<exc-type-name>"}`` so one
broken section does not 500 the whole page.

Sections:

  1. Audit chain health (event totals + last verify + chain status)
  2. Webhook fleet (active subs + 24h success rate + top-3 failure tenants
     + stale subscriptions)
  3. Token fleet (active count + rotating-soon + rotation-overdue)
  4. Companion fleet (per-tenant active keypair count + 30d uploads +
     MAA signature coverage)
  5. Rate-limit + REST API health (top throttled buckets + SSE transport)
  6. Signed-release status (SW cache key + last tag + audit-root backend)
  7. Observability status (metrics backend + /metrics/ availability)
  8. Counsel / compliance (MAA active version + draft set + DSAR)

Hard contract:

  * Staff-only via ``@method_decorator(staff_member_required, "dispatch")``.
  * Every cross-tenant queryset carries the 5-part-hyphenated marker
    ``# tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only``.
  * Defensive ``getattr(obj, "field", default)`` so sibling-agent
    field renames don't break this view.
  * Response carries ``Cache-Control: no-store`` to avoid stale operator
    views being served from any intermediate cache.
  * NO logging of: PII, ciphertext, signatures, tokens, slugs.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)


# Status pill semantics (rendered in the template):
#   * ok      — green; nominal
#   * info    — blue; informational only
#   * warn    — amber; attention soon
#   * alert   — red; act now
STATUS_OK = "ok"
STATUS_INFO = "info"
STATUS_WARN = "warn"
STATUS_ALERT = "alert"


# ─── Helpers ────────────────────────────────────────────────────────────


def _var_dir() -> Path:
    """Resolve the ``var/`` directory under ``BASE_DIR`` defensively."""
    base = getattr(settings, "BASE_DIR", None)
    if base is None:
        return Path("var")
    return Path(base) / "var"


def _read_text_first_line(path: Path) -> str:
    """Best-effort read of the first non-empty line of a small text file."""
    try:
        if not path.exists():
            return ""
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if line:
                    return line
    except (OSError, ValueError):
        return ""
    return ""


def _service_worker_cache_key() -> str:
    """Extract the SW ``CACHE_VERSION`` from ``static/js/service-worker.js``.

    Format: ``const CACHE_VERSION = "sms-vX.Y.Z-<slug>-YYYY-MM-DD";``
    Returns empty string if the file cannot be parsed.
    """
    base = getattr(settings, "BASE_DIR", None)
    if base is None:
        return ""
    sw_path = Path(base) / "static" / "js" / "service-worker.js"
    import re

    try:
        if not sw_path.exists():
            return ""
        with open(sw_path, "r", encoding="utf-8") as fh:
            for raw in fh:
                # Match the actual ``CACHE_VERSION = "…"`` DECLARATION only.
                # A plain substring test ("CACHE_VERSION" in line and "=" and
                # '"') also matched changelog COMMENT lines that merely mention
                # CACHE_VERSION and happen to carry an "=" and a quote (e.g. the
                # multi-paragraph v4.00.0 comment block), returning a giant
                # garbage value into the operator command center. Anchoring on
                # ``CACHE_VERSION =`` plus a single quoted token means only the
                # real declaration line wins.
                m = re.search(r'CACHE_VERSION\s*=\s*"([^"]+)"', raw)
                if m:
                    return m.group(1)
    except (OSError, ValueError):
        return ""
    return ""


# ─── Section 1: Audit chain health ──────────────────────────────────────


def _section_audit_chain() -> dict[str, Any]:
    try:
        from apps.migration_cloud.models_audit import (
            MigrationCloudAuditEvent,
        )
    except Exception as exc:  # broad-by-design — section degrades gracefully
        return {"error": type(exc).__name__}

    try:
        ninety_days_ago = timezone.now() - timedelta(days=90)
        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        all_count = MigrationCloudAuditEvent.objects.count()
        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        recent_count = MigrationCloudAuditEvent.objects.filter(
            created_at__gte=ninety_days_ago,
        ).count()

        # Verify-event lookup. v3.39 introduced
        # ``audit.chain.verified`` / ``audit.chain.broken`` — neither is
        # in the canonical TextChoices yet (Agent 1 of v3.39 emits the
        # retention-purge meta event under AUDIT_RETENTION_PURGE_APPLIED;
        # the verify beat MAY emit a custom event). We tolerate both by
        # looking at the most-recent event whose event_type starts with
        # ``audit.``.
        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        last_audit_meta = (
            MigrationCloudAuditEvent.objects
            .filter(event_type__startswith="audit.")
            .order_by("-created_at")
            .only("event_type", "created_at", "payload_summary")
            .first()
        )

        # Determine chain status. Defensive — we never re-walk the full
        # chain here (could be O(million); the dashboard target is
        # <500ms). Instead surface the *last reported* state from the
        # weekly beat's audit event, falling back to "never-verified".
        chain_status = "never-verified"
        last_verified_at = None
        if last_audit_meta is not None:
            last_verified_at = getattr(last_audit_meta, "created_at", None)
            payload = getattr(last_audit_meta, "payload_summary", {}) or {}
            if isinstance(payload, dict):
                # Conservative tri-key lookup: agents may write any of
                # ``status`` / ``result`` / ``chain_status``.
                status_val = (
                    payload.get("status")
                    or payload.get("result")
                    or payload.get("chain_status")
                    or ""
                )
                status_val = str(status_val).lower()
                if status_val in ("ok", "clean", "verified"):
                    chain_status = "ok"
                elif status_val in ("broken", "chain-broken"):
                    chain_status = "broken"
                elif status_val in ("sig-mismatch", "signature-mismatch"):
                    chain_status = "sig-mismatch"
                else:
                    # The meta event exists but doesn't report status —
                    # treat as info-only rather than alarm.
                    chain_status = "ok"

        # Last 5 events for at-a-glance recency.
        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        recent_events = list(
            MigrationCloudAuditEvent.objects
            .order_by("-created_at")
            .only("event_type", "event_subject_hash", "created_at")[:5]
        )
        recent_rows = [
            {
                "event_type": getattr(ev, "event_type", ""),
                "subject_truncated": (
                    getattr(ev, "event_subject_hash", "") or ""
                )[:12],
                "created_at": getattr(ev, "created_at", None),
            }
            for ev in recent_events
        ]

        # Pill status from chain status.
        if chain_status == "ok":
            pill = STATUS_OK
        elif chain_status == "never-verified":
            pill = STATUS_INFO
        elif chain_status == "broken":
            pill = STATUS_ALERT
        elif chain_status == "sig-mismatch":
            pill = STATUS_ALERT
        else:
            pill = STATUS_INFO

        return {
            "error": None,
            "pill": pill,
            "all_count": all_count,
            "recent_count": recent_count,
            "last_verified_at": last_verified_at,
            "chain_status": chain_status,
            "recent_rows": recent_rows,
            "drill_url_name": "audit_dashboard",
        }
    except Exception as exc:  # broad-by-design
        return {"error": type(exc).__name__}


# ─── Section 2: Webhook fleet ───────────────────────────────────────────


def _section_webhook_fleet() -> dict[str, Any]:
    try:
        from apps.migration_cloud.models import (
            MigrationCloudWebhookDelivery,
            MigrationCloudWebhookSubscription,
            WebhookDeliveryStatus,
        )
    except Exception as exc:
        return {"error": type(exc).__name__}

    try:
        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        active_subs = MigrationCloudWebhookSubscription.objects.filter(
            active=True,
        ).count()

        twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
        seven_days_ago = timezone.now() - timedelta(days=7)

        # Aggregate delivery counts by (tenant, status) in ONE query so we
        # don't N+1 the loop.
        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        agg = (
            MigrationCloudWebhookDelivery.objects
            .filter(created_at__gte=twenty_four_hours_ago)
            .values("subscription__tenant_id", "status")
            .annotate(n=Count("id"))
        )
        per_tenant: dict[Any, dict[str, int]] = {}
        delivered_status = getattr(
            WebhookDeliveryStatus, "DELIVERED", "delivered",
        )
        delivered_value = getattr(delivered_status, "value", "delivered")
        failed_status = getattr(WebhookDeliveryStatus, "FAILED", "failed")
        exhausted_status = getattr(
            WebhookDeliveryStatus, "EXHAUSTED", "exhausted",
        )
        failed_value = getattr(failed_status, "value", "failed")
        exhausted_value = getattr(exhausted_status, "value", "exhausted")
        for row in agg:
            tid = row["subscription__tenant_id"]
            status = row["status"]
            n = int(row["n"] or 0)
            bucket = per_tenant.setdefault(
                tid, {"delivered": 0, "failed": 0, "total": 0},
            )
            bucket["total"] += n
            if status == delivered_value:
                bucket["delivered"] += n
            elif status in (failed_value, exhausted_value):
                bucket["failed"] += n

        delivered_24h = sum(b["delivered"] for b in per_tenant.values())
        failed_24h = sum(b["failed"] for b in per_tenant.values())
        total_24h = sum(b["total"] for b in per_tenant.values())
        success_rate = (
            (100.0 * delivered_24h / total_24h) if total_24h else 100.0
        )

        top_failures = sorted(
            (
                {"tenant_id": tid, **bucket}
                for tid, bucket in per_tenant.items()
            ),
            key=lambda r: (-int(r["failed"]), int(r.get("tenant_id") or 0)),
        )[:3]
        # Drop zero-failure rows from the top-3 display.
        top_failures = [r for r in top_failures if r["failed"] > 0]

        # Stale subscriptions — active sub w/ no delivery in 7d.
        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        recent_sub_ids = set(
            MigrationCloudWebhookDelivery.objects
            .filter(created_at__gte=seven_days_ago)
            .values_list("subscription_id", flat=True)
            .distinct()
        )
        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        stale_count = (
            MigrationCloudWebhookSubscription.objects
            .filter(active=True)
            .exclude(id__in=recent_sub_ids)
            .count()
        )

        # Pill semantics — fail rate >5% in 24h is warn; >20% is alert;
        # all-zero deliveries is info.
        if total_24h == 0:
            pill = STATUS_INFO
        elif success_rate >= 95.0:
            pill = STATUS_OK
        elif success_rate >= 80.0:
            pill = STATUS_WARN
        else:
            pill = STATUS_ALERT

        return {
            "error": None,
            "pill": pill,
            "active_subscriptions": active_subs,
            "delivered_24h": delivered_24h,
            "failed_24h": failed_24h,
            "total_24h": total_24h,
            "success_rate_pct": round(success_rate, 1),
            "top_failures": top_failures,
            "stale_count": stale_count,
            "drill_url_name": "operator_webhook_list",
        }
    except Exception as exc:
        return {"error": type(exc).__name__}


# ─── Section 3: Token fleet ─────────────────────────────────────────────


def _section_token_fleet() -> dict[str, Any]:
    try:
        from apps.migration_cloud.models import MigrationCloudAPIToken
    except Exception as exc:
        return {"error": type(exc).__name__}

    try:
        now = timezone.now()
        two_weeks = now + timedelta(days=14)

        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        active_count = MigrationCloudAPIToken.objects.filter(
            revoked_at__isnull=True,
        ).count()
        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        rotating_soon = MigrationCloudAPIToken.objects.filter(
            grace_until__isnull=False,
            grace_until__gte=now,
            grace_until__lte=two_weeks,
        ).count()
        # Overdue — grace_until in the past AND not yet linked to a
        # successor row.
        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        overdue = MigrationCloudAPIToken.objects.filter(
            grace_until__isnull=False,
            grace_until__lt=now,
            rotated_to__isnull=True,
        ).count()

        if overdue > 0:
            pill = STATUS_ALERT
        elif rotating_soon > 0:
            pill = STATUS_WARN
        else:
            pill = STATUS_OK

        return {
            "error": None,
            "pill": pill,
            "active_count": active_count,
            "rotating_soon": rotating_soon,
            "overdue": overdue,
            "drill_url_name": "operator_token_list",
        }
    except Exception as exc:
        return {"error": type(exc).__name__}


# ─── Section 4: Companion fleet ─────────────────────────────────────────


def _section_companion_fleet() -> dict[str, Any]:
    try:
        from apps.migration_cloud.models import (
            CompanionUploadReceipt,
            MigrationAuthorizationAgreement,
            MigrationCloudCompanionKeypair,
        )
    except Exception as exc:
        return {"error": type(exc).__name__}

    try:
        thirty_days_ago = timezone.now() - timedelta(days=30)

        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        keypair_tenants = (
            MigrationCloudCompanionKeypair.objects
            .filter(is_active=True)
            .values_list("tenant_id", flat=True)
            .distinct()
            .count()
        )

        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        receipts_30d_qs = CompanionUploadReceipt.objects.filter(
            received_at__gte=thirty_days_ago
        )
        upload_count_30d = receipts_30d_qs.count()
        from django.db.models import Sum

        bytes_total_30d = int(
            receipts_30d_qs.aggregate(total=Sum("plaintext_byte_size"))["total"] or 0
        )

        # MAA signature coverage — distinct tenants w/ an active signed
        # MAA vs total tenants with any keypair.
        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        signed_tenants = (
            MigrationAuthorizationAgreement.objects
            .filter(signed_at__isnull=False, revoked_at__isnull=True)
            .values_list("tenant_id", flat=True)
            .distinct()
            .count()
        )

        # Pill: warn when uploads happened but signed-tenants==0 (legal
        # gap), else ok.
        if upload_count_30d > 0 and signed_tenants == 0:
            pill = STATUS_ALERT
        elif keypair_tenants > 0 and signed_tenants == 0:
            pill = STATUS_WARN
        else:
            pill = STATUS_OK

        return {
            "error": None,
            "pill": pill,
            "keypair_tenants": keypair_tenants,
            "upload_count_30d": upload_count_30d,
            "bytes_total_30d": bytes_total_30d,
            "signed_tenants": signed_tenants,
            "drill_url_name": "companion_upload",
        }
    except Exception as exc:
        return {"error": type(exc).__name__}


# ─── Section 5: Rate-limit + REST API health ────────────────────────────


def _section_api_health() -> dict[str, Any]:
    sse_transport = getattr(
        settings, "MIGRATION_CLOUD_SSE_TRANSPORT", "wsgi-fallback",
    )
    # Throttled-buckets snapshot — defensive. If the rate-limiting
    # module ever exposes a public snapshot function, we use it. If not,
    # surface "no data" rather than fabricating numbers.
    snapshot_rows: list[dict[str, Any]] = []
    snapshot_available = False
    try:
        from apps.migration_cloud.api import rate_limiting as _rl
        for name in ("get_throttled_buckets_snapshot", "snapshot_top_throttled"):
            fn = getattr(_rl, name, None)
            if callable(fn):
                try:
                    raw = fn()
                except TypeError:
                    raw = fn(top=5)
                if isinstance(raw, list):
                    snapshot_rows = raw[:5]
                    snapshot_available = True
                break
    except Exception:  # broad-by-design — section degrades
        snapshot_available = False

    return {
        "error": None,
        "pill": STATUS_INFO,
        "sse_transport": sse_transport,
        "snapshot_available": snapshot_available,
        "snapshot_rows": snapshot_rows,
        "drill_url_name": None,
    }


# ─── Section 6: Signed-release status ───────────────────────────────────


def _section_signed_release() -> dict[str, Any]:
    cache_key = _service_worker_cache_key()
    last_tag = _read_text_first_line(_var_dir() / "last-release-tag.txt") \
        or "unknown — check git tags"
    signing_backend = getattr(
        settings, "MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND", "local-env-key",
    )
    # Memory snapshot also documents the older
    # ``MIGRATION_CLOUD_AUDIT_ROOT_SIGNING_BACKEND`` name — read both
    # defensively so the dashboard surfaces whichever the live settings
    # use.
    fallback_backend = getattr(
        settings, "MIGRATION_CLOUD_AUDIT_ROOT_SIGNING_BACKEND", None,
    )
    if fallback_backend and signing_backend == "local-env-key":
        signing_backend = fallback_backend

    pill = STATUS_OK if cache_key else STATUS_WARN
    return {
        "error": None,
        "pill": pill,
        "cache_key": cache_key or "unavailable",
        "last_tag": last_tag,
        "signing_backend": signing_backend,
        "drill_url_name": None,
    }


# ─── Section 7: Observability status ────────────────────────────────────


def _section_observability() -> dict[str, Any]:
    backend = getattr(settings, "OBSERVABILITY_METRICS_BACKEND", "noop")
    metrics_url_registered = False
    try:
        # ``/metrics/`` is lazy-included only when the prometheus backend
        # is selected (v3.39.0 Agent 4). ``reverse`` will raise
        # NoReverseMatch when the URL isn't registered.
        reverse("prometheus_metrics")
        metrics_url_registered = True
    except NoReverseMatch:
        metrics_url_registered = False
    except Exception:  # broad-by-design — degrade silently
        metrics_url_registered = False

    if backend == "noop":
        pill = STATUS_INFO
    elif backend == "prometheus-client" and metrics_url_registered:
        pill = STATUS_OK
    elif backend == "prometheus-client" and not metrics_url_registered:
        pill = STATUS_WARN
    else:
        pill = STATUS_INFO

    return {
        "error": None,
        "pill": pill,
        "backend": backend,
        "metrics_url_registered": metrics_url_registered,
        "drill_url_name": None,
    }


# ─── Section 8: Counsel / compliance ────────────────────────────────────


def _section_counsel() -> dict[str, Any]:
    try:
        from apps.migration_cloud.models import MigrationAuthorizationAgreement
    except Exception as exc:
        return {"error": type(exc).__name__}

    try:
        # v3.40.0 Agent 15 — prefer the DB-persisted active version
        # (MAAActiveVersionState singleton) over the env default, with
        # defensive fallback to the env setting on import / read failure.
        active_version = getattr(
            settings, "MIGRATION_CLOUD_MAA_DEFAULT_VERSION", "v1.0",
        )
        draft_versions: set[str] = set()
        try:
            from apps.migration_cloud.models_maa_state import (
                MAAActiveVersionState,
            )
            from apps.migration_cloud.services.maa_text import (
                get_draft_versions,
            )
            db_active = (MAAActiveVersionState.get_active_version() or "").strip()
            if db_active:
                active_version = db_active
            draft_versions = set(get_draft_versions())
        except Exception:  # noqa: BLE001 — defensive
            settings_drafts = getattr(
                settings, "MAA_TEXT_DRAFT_VERSIONS", set(),
            )
            if isinstance(settings_drafts, (set, list, tuple)):
                draft_versions = set(settings_drafts)
        v2_draft = "v2.0" in draft_versions

        # tenant-isolation-allow: command-center-cross-tenant-snapshot-staff-only
        active_signed = (
            MigrationAuthorizationAgreement.objects
            .filter(
                agreement_version=active_version,
                revoked_at__isnull=True,
            )
            .values_list("tenant_id", flat=True)
            .distinct()
            .count()
        )

        dsar_last_run = _read_text_first_line(
            _var_dir() / "dsar-last-run.txt"
        ) or "no log file"

        # Pill: warn if v2.0 still draft AND active is v1.0 (the
        # counsel-signoff backlog), else ok.
        if active_version == "v1.0" and v2_draft:
            pill = STATUS_WARN
        else:
            pill = STATUS_OK

        return {
            "error": None,
            "pill": pill,
            "active_version": active_version,
            "active_signed_tenants": active_signed,
            "v2_draft": v2_draft,
            "draft_versions": sorted(set(draft_versions)),
            "dsar_last_run": dsar_last_run,
            "drill_url_name": "maa_v2_promotion_dashboard",
        }
    except Exception as exc:
        return {"error": type(exc).__name__}


# ─── View ───────────────────────────────────────────────────────────────


@method_decorator(staff_member_required, name="dispatch")
class MigrationCloudCommandCenterView(View):
    """GET ``/super/migration/command-center/`` — operator command center.

    Read-only snapshot. Eight sections; one broken section never
    cascades — each returns ``{"error": <exc-type>}`` instead.
    """

    template_name = "migration_cloud/operator/command_center.html"

    def get(self, request, *args, **kwargs):
        sections = {
            "audit_chain": _section_audit_chain(),
            "webhook_fleet": _section_webhook_fleet(),
            "token_fleet": _section_token_fleet(),
            "companion_fleet": _section_companion_fleet(),
            "api_health": _section_api_health(),
            "signed_release": _section_signed_release(),
            "observability": _section_observability(),
            "counsel": _section_counsel(),
        }

        # Logging discipline — emit ONLY error-keys present per section,
        # never any PII / tenant slug / count details.
        broken = [k for k, v in sections.items() if v.get("error")]
        logger.info(
            "migration_cloud_command_center_rendered user_id=%s broken=%s",
            getattr(request.user, "pk", None),
            ",".join(broken) if broken else "none",
        )

        context = {
            "page_title": "Migration Cloud — Command Center",
            "shell": kwargs.get("shell", "super"),
            "sections": sections,
        }
        response = render(request, self.template_name, context)
        # Operator dashboards should never be served from intermediate
        # caches; surface the freshest snapshot every refresh.
        response["Cache-Control"] = "no-store"
        return response


__all__ = [
    "MigrationCloudCommandCenterView",
    "STATUS_OK",
    "STATUS_INFO",
    "STATUS_WARN",
    "STATUS_ALERT",
    "_section_audit_chain",
    "_section_webhook_fleet",
    "_section_token_fleet",
    "_section_companion_fleet",
    "_section_api_health",
    "_section_signed_release",
    "_section_observability",
    "_section_counsel",
    "_service_worker_cache_key",
]
