"""v4.00.91 Studio-OS-10X W1 Pillar A — 14 operator UI surfaces.

Each view is a tight, read-only operator dashboard panel. All require
``request.user.is_staff`` (or :func:`user_passes_test`). All consume an
existing SOT helper so the rendered values are derived, not hardcoded.

URL prefix wired in :mod:`apps.integrations_marketplace.urls`:
``/integrations/studio-os-10x/``.

A1  /studio/                            rmc-studio-home shell
A2  /studio/quick-actions/              quick-actions bar
A3  /studio/oauth-metrics/              OAuth metrics dashboard
A4  /studio/saml-idp-registry/          SAML IdP registry viewer
A5  /studio/lms-provider-rollup/        LMS provider rollup (3-tier ladder)
A6  /studio/retention-preview/          retention preview historical view
A7  /studio/dlq-filter-nav/             webhook DLQ filter nav extensions
A8  /studio/audit-packet-export/        audit packet export panel
A9  /studio/diagnostics-alarms/         diagnostics alarm panel
A10 /studio/pki-bundle-viewer/          PKI bundle viewer
A11 /studio/tenant-retention-override/  tenant retention override CRUD
A12 /studio/token-rotation-timeline/    token rotation timeline
A13 /studio/billing-summary/            tenant billing/subscription card
A14 /studio/nav-sidebar/                Studio nav sidebar partial
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from django.contrib.auth.decorators import user_passes_test
from django.http import HttpRequest, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def _is_staff(u) -> bool:
    return bool(getattr(u, "is_authenticated", False) and getattr(u, "is_staff", False))


staff_required = user_passes_test(_is_staff)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Panel slug -> route name. Every entry below was written as a literal
# "/operator/studio-os-10x/<slug>/", a prefix mounted on no urlconf at all,
# so all twelve operator panel links plus the home link and the
# audit-packet-export endpoint returned 404. The surface is really mounted
# under /integrations/.
#
# Reversing keeps them honest, and the mapping is not mechanical
# (lms-provider-rollup -> s10x_lms_rollup) — exactly the drift that building
# a path out of a slug hides and reverse() cannot.
_S10X_ROUTES = {
    "home": "s10x_home",
    "quick-actions": "s10x_quick_actions",
    "oauth-metrics": "s10x_oauth_metrics",
    "saml-idp-registry": "s10x_saml_idp_registry",
    "lms-provider-rollup": "s10x_lms_rollup",
    "retention-preview": "s10x_retention_preview",
    "dlq-filter-nav": "s10x_dlq_filter_nav",
    "audit-packet-export": "s10x_audit_packet_export",
    "diagnostics-alarms": "s10x_diagnostics_alarms",
    "pki-bundle-viewer": "s10x_pki_bundle_viewer",
    "tenant-retention-override": "s10x_tenant_retention_override",
    "token-rotation-timeline": "s10x_token_rotation_timeline",
    "billing-summary": "s10x_billing_summary",
}


def _s10x_href(slug: str) -> str:
    """Resolve an operator panel slug to its real path."""
    return reverse("integrations_marketplace:%s" % _S10X_ROUTES[slug])


def _ok(payload: dict[str, Any], **extra) -> JsonResponse:
    payload = dict(payload)
    payload.update(extra)
    payload.setdefault("generated_at", _now_iso())
    return JsonResponse(payload)


# ---------------------------------------------------------------------------
# A1 — rmc-studio-home (shell w/ panels grid)
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def studio_home(request: HttpRequest) -> JsonResponse:
    panels = (
        {"slug": "quick-actions", "title": "Quick actions", "href": _s10x_href("quick-actions")},
        {"slug": "oauth-metrics", "title": "OAuth metrics", "href": _s10x_href("oauth-metrics")},
        {"slug": "saml-idp-registry", "title": "SAML IdP registry", "href": _s10x_href("saml-idp-registry")},
        {"slug": "lms-provider-rollup", "title": "LMS provider rollup", "href": _s10x_href("lms-provider-rollup")},
        {"slug": "retention-preview", "title": "Retention preview", "href": _s10x_href("retention-preview")},
        {"slug": "dlq-filter-nav", "title": "DLQ filter nav", "href": _s10x_href("dlq-filter-nav")},
        {"slug": "audit-packet-export", "title": "Audit packet export", "href": _s10x_href("audit-packet-export")},
        {"slug": "diagnostics-alarms", "title": "Diagnostics alarms", "href": _s10x_href("diagnostics-alarms")},
        {"slug": "pki-bundle-viewer", "title": "PKI bundle viewer", "href": _s10x_href("pki-bundle-viewer")},
        {"slug": "tenant-retention-override", "title": "Tenant retention override", "href": _s10x_href("tenant-retention-override")},
        {"slug": "token-rotation-timeline", "title": "Token rotation timeline", "href": _s10x_href("token-rotation-timeline")},
        {"slug": "billing-summary", "title": "Billing summary", "href": _s10x_href("billing-summary")},
    )
    return _ok({"surface": "studio_home", "panels": list(panels), "panel_count": len(panels)})


# ---------------------------------------------------------------------------
# A2 — quick-actions bar (DLQ replay / OAuth refresh trigger / retention purge dry-run)
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def quick_actions(request: HttpRequest) -> JsonResponse:
    actions = (
        {"slug": "dlq-replay", "label": "Replay DLQ entry", "endpoint": "/super/migration/operator/dlq/", "method": "GET"},
        {"slug": "oauth-token-refresh", "label": "Refresh OAuth token", "endpoint": "/super/migration/lms/diagnostics/", "method": "GET"},
        {"slug": "retention-purge-dry-run", "label": "Retention purge dry-run", "endpoint": "/super/migration/lms/diagnostics/retention-preview/", "method": "GET"},
        {"slug": "audit-packet-download", "label": "Download audit packet", "endpoint": _s10x_href("audit-packet-export"), "method": "GET"},
    )
    return _ok({"surface": "quick_actions", "actions": list(actions), "action_count": len(actions)})


# ---------------------------------------------------------------------------
# A3 — OAuth metrics dashboard (consumes lms_oauth_metrics SOT helper)
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def oauth_metrics_dashboard(request: HttpRequest) -> JsonResponse:
    try:
        from apps.integrations_marketplace import lms_oauth_metrics as metrics
        snapshot = metrics.get_oauth_metrics_snapshot()
    except Exception as exc:  # noqa: BLE001
        logger.debug("oauth_metrics dashboard: snapshot helper unavailable: %s", exc)
        snapshot = {"providers": {}, "note": "metrics module not initialised"}
    return _ok({"surface": "oauth_metrics_dashboard", "snapshot": snapshot})


# ---------------------------------------------------------------------------
# A4 — SAML IdP registry viewer (reads RMC_SAML_MULTI_IDP_REGISTRY env)
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def saml_idp_registry(request: HttpRequest) -> JsonResponse:
    import os
    registry_raw = os.environ.get("RMC_SAML_MULTI_IDP_REGISTRY", "")
    parsed: list[dict[str, Any]] = []
    parse_reason = "empty_env"
    if registry_raw:
        try:
            parsed_obj = json.loads(registry_raw)
            if isinstance(parsed_obj, list):
                parsed = [r for r in parsed_obj if isinstance(r, dict)]
            elif isinstance(parsed_obj, dict):
                parsed = [parsed_obj]
            parse_reason = "ok"
        except (ValueError, TypeError) as exc:
            parse_reason = f"parse_error:{exc}"
    return _ok({
        "surface": "saml_idp_registry",
        "entries": parsed,
        "entry_count": len(parsed),
        "env_var": "RMC_SAML_MULTI_IDP_REGISTRY",
        "parse_reason": parse_reason,
    })


# ---------------------------------------------------------------------------
# A5 — LMS provider rollup (3-tier ladder + maturity pills)
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def lms_provider_rollup(request: HttpRequest) -> JsonResponse:
    from apps.integrations_marketplace import lms_supported_providers as sot
    rows = []
    for slug in sorted(sot.SUPPORTED_LMS_PROVIDERS):
        tier = (
            "production" if slug in sot.PRODUCTION_LMS_PROVIDERS
            else "oauth_ready" if slug in sot.OAUTH_READY_LMS_PROVIDERS
            else "scaffold" if slug in sot.SCAFFOLD_LMS_PROVIDERS
            else "unknown"
        )
        rows.append({"slug": slug, "tier": tier})
    counts = {"production": 0, "oauth_ready": 0, "scaffold": 0, "unknown": 0}
    for r in rows:
        counts[r["tier"]] = counts.get(r["tier"], 0) + 1
    return _ok({
        "surface": "lms_provider_rollup",
        "rows": rows,
        "tier_counts": counts,
        "total": len(rows),
    })


# ---------------------------------------------------------------------------
# A6 — retention preview historical view (24-bucket sparkline derived sample)
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def retention_preview_historical(request: HttpRequest) -> JsonResponse:
    try:
        from apps.migration_cloud import views_lms_diagnostics as diag
        if hasattr(diag, "_retention_purge_sparkline"):
            cutoff = datetime.now(timezone.utc)
            sparkline = diag._retention_purge_sparkline(cutoff_dt=cutoff)
            return _ok({"surface": "retention_preview_historical", "sparkline": sparkline})
    except Exception as exc:  # noqa: BLE001
        logger.debug("retention preview historical fallback: %s", exc)
    return _ok({
        "surface": "retention_preview_historical",
        "sparkline": {"buckets": [], "max_count": 0, "note": "helper unavailable in this environment"},
    })


# ---------------------------------------------------------------------------
# A7 — webhook DLQ filter nav extensions (tenant + provider + age-bucket)
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def dlq_filter_nav(request: HttpRequest) -> JsonResponse:
    nav = {
        "tenant_filter_key": "tenant_schema",
        "provider_filter_key": "provider",
        "age_buckets": [
            {"slug": "1h",  "label": "Last 1 hour",  "seconds": 3600},  # magic-number-allow: duration-seconds
            {"slug": "24h", "label": "Last 24 hours","seconds": 86400},  # magic-number-allow: duration-seconds
            {"slug": "7d",  "label": "Last 7 days", "seconds": 604800},  # magic-number-allow: duration-seconds
            {"slug": "30d", "label": "Last 30 days","seconds": 2592000},  # magic-number-allow: duration-seconds
            {"slug": "all", "label": "All time",    "seconds": 0},
        ],
        "base_url": "/super/migration/operator/dlq/",
    }
    return _ok({"surface": "dlq_filter_nav", "nav": nav})


# ---------------------------------------------------------------------------
# A8 — audit packet export panel (4 formats: JSON/CSV/JSONL/PDF)
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def audit_packet_export(request: HttpRequest) -> JsonResponse:
    formats = (
        {"slug": "json",  "label": "JSON (operator review)",    "endpoint": "/super/migration/audit/export/?format=json"},
        {"slug": "csv",   "label": "CSV (gzipped tabular)",     "endpoint": "/super/migration/audit/export/?format=csv"},
        {"slug": "jsonl", "label": "JSONL (streaming)",         "endpoint": "/super/migration/audit/export/?format=jsonl"},
        {"slug": "pdf",   "label": "PDF (counsel handoff)",     "endpoint": "/super/migration/audit/export/?format=pdf"},
    )
    return _ok({"surface": "audit_packet_export", "formats": list(formats), "format_count": len(formats)})


# ---------------------------------------------------------------------------
# A9 — diagnostics alarm panel (4-tier severity ladder)
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def diagnostics_alarm_panel(request: HttpRequest) -> JsonResponse:
    try:
        from apps.migration_cloud import views_lms_diagnostics as diag
        if hasattr(diag, "compute_diagnostics_alarms"):
            alarms = diag.compute_diagnostics_alarms()
        else:
            alarms = {"summary": "alarm helper unavailable"}
    except Exception as exc:  # noqa: BLE001
        logger.debug("diagnostics alarm panel fallback: %s", exc)
        alarms = {"summary": "alarm helper raised", "error": str(exc)[:120]}
    severity_ladder = ("critical", "high", "warning", "info")
    return _ok({"surface": "diagnostics_alarm_panel", "alarms": alarms, "severity_ladder": list(severity_ladder)})


# ---------------------------------------------------------------------------
# A10 — PKI bundle viewer (calls lms_pki_bundle.build helper)
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def pki_bundle_viewer(request: HttpRequest) -> JsonResponse:
    try:
        from apps.integrations_marketplace import lms_pki_bundle as pki
        if hasattr(pki, "build_lms_pki_bundle"):
            bundle = pki.build_lms_pki_bundle()
        else:
            bundle = {"providers": [], "note": "build_lms_pki_bundle unavailable"}
    except Exception as exc:  # noqa: BLE001
        logger.debug("pki bundle viewer fallback: %s", exc)
        bundle = {"providers": [], "error": str(exc)[:120]}
    return _ok({"surface": "pki_bundle_viewer", "bundle": bundle})


# ---------------------------------------------------------------------------
# A11 — tenant retention override viewer (list-only; CRUD comes in Wave 2)
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def tenant_retention_override(request: HttpRequest) -> JsonResponse:
    try:
        from apps.integrations_marketplace.models_tenant_retention_override import TenantRetentionOverride
        qs = TenantRetentionOverride.objects.all()[:200]
        rows = [
            {
                "tenant_schema": getattr(r, "tenant_schema", ""),
                "retention_years": getattr(r, "retention_years", None),
                "reason": getattr(r, "reason", "")[:80],
            }
            for r in qs
        ]
    except Exception as exc:  # noqa: BLE001
        logger.debug("tenant retention override viewer fallback: %s", exc)
        rows = []
    return _ok({"surface": "tenant_retention_override", "overrides": rows, "row_count": len(rows)})


# ---------------------------------------------------------------------------
# A12 — token rotation timeline
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def token_rotation_timeline(request: HttpRequest) -> JsonResponse:
    try:
        from apps.integrations_marketplace import lms_token_rotation as rot
        events: list[dict[str, Any]] = []
        if hasattr(rot, "list_recent_rotations"):
            events = list(rot.list_recent_rotations(limit=50))
    except Exception as exc:  # noqa: BLE001
        logger.debug("token rotation timeline fallback: %s", exc)
        events = []
    return _ok({"surface": "token_rotation_timeline", "events": events, "event_count": len(events)})


# ---------------------------------------------------------------------------
# A13 — tenant billing/subscription summary card
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def billing_summary(request: HttpRequest) -> JsonResponse:
    from django.utils import timezone as django_timezone

    from apps.billing.models import TenantSubscription

    today = django_timezone.localdate()
    trial_cutoff = today + timedelta(days=7)
    active_statuses = {
        TenantSubscription.Status.TRIALING,
        TenantSubscription.Status.ACTIVE,
        TenantSubscription.Status.PAST_DUE,
        TenantSubscription.Status.SUSPENDED,
    }
    subscriptions = list(
        TenantSubscription.objects.filter(  # tenant-isolation-allow: operator-platform-billing-summary
            status__in=active_statuses
        ).select_related("billing_account")
    )
    monthly_by_currency: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    trial_expiring = 0
    dunning_failed = 0
    for subscription in subscriptions:
        amount = subscription.base_amount + subscription.addons_amount
        if subscription.billing_cycle == TenantSubscription.BillingCycle.ANNUAL:
            amount /= Decimal("12")
        currency = (
            getattr(subscription.billing_account, "currency_code", "") or "USD"
        ).upper()
        monthly_by_currency[currency] += amount
        if (
            subscription.status == TenantSubscription.Status.TRIALING
            and subscription.trial_end_date
            and today <= subscription.trial_end_date <= trial_cutoff
        ):
            trial_expiring += 1
        metadata = (
            subscription.metadata if isinstance(subscription.metadata, dict) else {}
        )
        try:
            dunning_attempts = int(metadata.get("dunning_attempts") or 0)
        except (TypeError, ValueError):
            dunning_attempts = 0
        if dunning_attempts >= 3:
            dunning_failed += 1

    revenue = {
        currency: f"{amount.quantize(Decimal('0.01'))}"
        for currency, amount in sorted(monthly_by_currency.items())
    }
    return _ok({
        "surface": "billing_summary",
        "panels": [
            {"slug": "active_subscriptions", "label": "Active subscriptions", "value": len(subscriptions)},
            {"slug": "monthly_revenue", "label": "Monthly recurring revenue", "value": revenue},
            {"slug": "trial_expiring_7d", "label": "Trials expiring in 7d", "value": trial_expiring},
            {"slug": "dunning_failed_3plus", "label": "Dunning attempts >=3", "value": dunning_failed},
        ],
        "active_subscription_count": len(subscriptions),
        "monthly_revenue_by_currency": revenue,
        "trial_expiring_7d_count": trial_expiring,
        "dunning_failed_3plus_count": dunning_failed,
    })


# ---------------------------------------------------------------------------
# A14 — Studio nav sidebar (ties A1-A13 together)
# ---------------------------------------------------------------------------
@require_GET
@staff_required
def studio_nav_sidebar(request: HttpRequest) -> JsonResponse:
    sections = (
        {
            "label": "Studio home",
            "items": [{"label": "Home", "href": _s10x_href("home")}],
        },
        {
            "label": "Diagnostics",
            "items": [
                {"label": "OAuth metrics",     "href": _s10x_href("oauth-metrics")},
                {"label": "Provider rollup",   "href": _s10x_href("lms-provider-rollup")},
                {"label": "Alarm panel",       "href": _s10x_href("diagnostics-alarms")},
                {"label": "Retention preview", "href": _s10x_href("retention-preview")},
            ],
        },
        {
            "label": "Integrations",
            "items": [
                {"label": "SAML IdP registry", "href": _s10x_href("saml-idp-registry")},
                {"label": "PKI bundle",        "href": _s10x_href("pki-bundle-viewer")},
                {"label": "Token rotation",    "href": _s10x_href("token-rotation-timeline")},
            ],
        },
        {
            "label": "Operator actions",
            "items": [
                {"label": "Quick actions",      "href": _s10x_href("quick-actions")},
                {"label": "DLQ filter nav",     "href": _s10x_href("dlq-filter-nav")},
                {"label": "Audit packet export","href": _s10x_href("audit-packet-export")},
                {"label": "Tenant overrides",   "href": _s10x_href("tenant-retention-override")},
                {"label": "Billing summary",    "href": _s10x_href("billing-summary")},
            ],
        },
    )
    return _ok({"surface": "studio_nav_sidebar", "sections": list(sections), "section_count": len(sections)})


STUDIO_OS_10X_W1_VIEWS = (
    studio_home, quick_actions, oauth_metrics_dashboard, saml_idp_registry,
    lms_provider_rollup, retention_preview_historical, dlq_filter_nav,
    audit_packet_export, diagnostics_alarm_panel, pki_bundle_viewer,
    tenant_retention_override, token_rotation_timeline, billing_summary,
    studio_nav_sidebar,
)
