"""
cockpit_activity_ticker_realdata.py — v3.58.x Wave 10 Agent Q (2026-05-22).

Real-data resolvers for the GLOBAL live activity ticker that renders on every
authenticated page across both the operator (manager) shell and the tenant
portal shell.

Architecture mirrors ``cockpit_panels_realdata_service`` + the
``cockpit_platform_pulse_service`` precedent:

  * Two host-routed resolver groups:
      - ``resolve_manager_ticker_cards()`` — platform-wide events, sourced from
        models that exist on the operator-platform schema (EmailDeliveryEvent,
        MigrationCloudAuditEvent, School provisioning, TenantSubscription).
        Cross-tenant aggregation is by design and marked accordingly.
      - ``resolve_tenant_ticker_cards(request)`` — tenant-scoped events,
        sourced from the active tenant's own audit log + attendance + finance
        rows. NEVER reads from operator-platform models so platform data
        cannot leak onto a tenant subdomain.

  * Lazy model imports inside each resolver — context processor on every
    request, so a missing model never breaks page load.

  * Per-source try/except wrapping — one failed source returns 0 cards from
    that source; the others still contribute. A total resolver failure
    returns an empty list and the caller falls back to operator-published
    seed cards (or the demo payload, when COCKPIT_200X_RENDER_PREVIEW_DEMO).

  * 30s cache — the ticker is supposed to feel "live", so we use a SHORTER
    TTL than the 60s panels cache. Cache key includes the host kind +
    (when tenant) the tenant slug HASH so cross-tenant cache pollution is
    impossible.

  * PII safety — raw school names, emails, tokens NEVER appear in resolver
    output. Identifiers are SHA-256 hex prefixes when surfaced at all.
    Numeric counts + relative timestamps are the primary signal.

The orchestrator wires this in via ``cockpit_context.py``: when the operator
hasn't published their own ``cockpit.activity_ticker.cards`` (manager) or
``cockpit.tenant_activity_ticker.cards`` (tenant), we attempt to populate
them from the live platform/tenant state. Operator overrides ALWAYS win
because ``_deep_merge`` is called with the resolver output as the BASE
and the cockpit_payload as the OVERRIDE downstream.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 30  # Shorter than panels (60s) — ticker should feel live.
CACHE_PREFIX = "rmc:cockpit:activity_ticker:v2"

# Hard cap on cards emitted per resolver pass — protects the partial from
# emitting a 200-event scroll on a busy day.
MAX_CARDS_TOTAL = 16
MAX_AUDIT_EVENT_CARDS = 6


# ============================================================
# Helpers
# ============================================================

def _hash_prefix(value: str, length: int = 8) -> str:
    """SHA-256 hex prefix for forensic-correlatable IDs that aren't PII."""
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:length]


def merge_activity_ticker_card_lists(
    *card_lists: list[dict[str, Any]] | None,
    max_total: int = MAX_CARDS_TOTAL,
) -> list[dict[str, Any]]:
    """Combine ticker card lists without duplicates; preserve first-seen order."""
    seen: set[tuple[str, str]] = set()
    merged: list[dict[str, Any]] = []
    for card_list in card_lists:
        for card in card_list or []:
            if not isinstance(card, dict):
                continue
            text = str(card.get("text") or "").strip()
            if not text:
                continue
            key = (text, str(card.get("timestamp") or ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(card)
            if len(merged) >= max_total:
                return merged
    return merged


def merge_activity_ticker_sections(
    cockpit: dict[str, Any],
    ticker_real: dict[str, Any],
) -> dict[str, Any]:
    """Merge resolver output onto existing ticker sections without wiping demo cards."""
    for section_key, overlay in ticker_real.items():
        if not isinstance(overlay, dict):
            continue
        base_section = dict(cockpit.get(section_key) or {})
        overlay_cards = overlay.get("cards")
        if isinstance(overlay_cards, list) and overlay_cards:
            base_cards = base_section.get("cards")
            if not isinstance(base_cards, list):
                base_cards = []
            base_section["cards"] = merge_activity_ticker_card_lists(
                base_cards,
                overlay_cards,
            )
            for field, value in overlay.items():
                if field != "cards":
                    base_section[field] = value
            if base_section.get("enabled") is not False:
                base_section["enabled"] = True
        else:
            base_section = {**base_section, **overlay}
        cockpit[section_key] = base_section
    return cockpit


def _relative_ts(iso_value: Any) -> str:
    """Format an ISO timestamp or datetime as a 'NN[s|m|h|d] ago' string."""
    if not iso_value:
        return ""
    try:
        from datetime import datetime
        if isinstance(iso_value, str):
            dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        else:
            dt = iso_value
        now = timezone.now()
        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=now.tzinfo)
        delta = now - dt
        seconds = int(delta.total_seconds())
        if seconds < 0:
            return ""
        if seconds < 60:
            return f"{seconds}s ago"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"
    except Exception:
        return ""


# ============================================================
# Manager / operator-platform sources
# ============================================================

def _source_migration_audit_events() -> list[dict[str, Any]]:
    """Pull recent platform-wide audit events (last 24h, capped to 4)."""
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent
        cutoff_iso = (timezone.now() - timedelta(hours=24)).isoformat()
        # tenant-isolation-allow: platform-activity-ticker-cross-tenant-aggregate-by-design
        rows = list(
            MigrationCloudAuditEvent.objects.filter(
                created_at_iso__gte=cutoff_iso,
            ).order_by("-created_at_iso").values(
                "event_type", "created_at_iso",
            )[:MAX_AUDIT_EVENT_CARDS]
        )
        cards = []
        for r in rows:
            etype = r.get("event_type") or ""
            cards.append({
                "icon": _icon_for_audit(etype),
                "severity": _severity_for_audit(etype),
                "text": _text_for_audit(etype),
                "timestamp": _relative_ts(r.get("created_at_iso")),
            })
        return cards
    except Exception:
        logger.warning("ticker: manager audit source failed", exc_info=True)
        return []


_AUDIT_ICONS = {
    "companion.upload": "📦",
    "maa.sign": "✍",
    "key.rotate": "🔑",
    "webhook.subscription.created": "🔗",
    "webhook.subscription.deleted": "🗑",
    "webhook.delivery.replay": "↻",
    "token.mint": "🎟",
    "token.revoke": "🚫",
}
_AUDIT_TEXTS = {
    "companion.upload": "Companion upload received",
    "maa.sign": "Migration agreement signed",
    "maa.sign_attempt_draft": "Draft MAA signature blocked",
    "key.rotate": "Encryption key rotated",
    "webhook.subscription.created": "Webhook subscription created",
    "webhook.subscription.deleted": "Webhook subscription removed",
    "webhook.delivery.replay": "Webhook delivery replayed",
    "token.mint": "Migration token minted",
    "token.revoke": "Migration token revoked",
    "legacy_hash.decrypt": "Legacy hash upgraded on login",
    "lifecycle.offboarding.export": "Tenant offboarding export generated",
    "lifecycle.offboarding.deactivated": "School deactivated (offboarding)",
    "lifecycle.offboarding.purge_requested": "Offboarding purge requested",
    "lifecycle.offboarding.purge_completed": "Offboarding purge completed",
    "audit.retention_purge_applied": "Audit retention purge applied",
}


def _icon_for_audit(event_type: str) -> str:
    return _AUDIT_ICONS.get(event_type, "•")


def _severity_for_audit(event_type: str) -> str:
    if "delete" in event_type or "revoke" in event_type:
        return "warn"
    if "rotate" in event_type or "replay" in event_type:
        return "info"
    return "success"


def _text_for_audit(event_type: str) -> str:
    return _AUDIT_TEXTS.get(event_type, event_type or "Platform event")


def _source_school_provisioning() -> list[dict[str, Any]]:
    """Count of new schools provisioned in the last 24h.

    NEVER surfaces the school name — only an aggregate count + the hash
    prefix of the newest entry's slug for forensic correlation.
    """
    try:
        from apps.schools.models import School
        cutoff = timezone.now() - timedelta(hours=24)
        # tenant-isolation-allow: platform-activity-ticker-cross-tenant-aggregate-by-design
        qs = School.objects.filter(date_joined__gte=cutoff) if hasattr(School, "date_joined") else \
             School.objects.filter(created_at__gte=cutoff) if hasattr(School, "created_at") else None
        if qs is None:
            return []
        count = qs.count()
        if count == 0:
            return []
        return [{
            "icon": "🆕",
            "severity": "success",
            "text": f"{count} new {'school' if count == 1 else 'schools'} provisioned",
            "timestamp": _("24h"),
        }]
    except Exception:
        logger.warning("ticker: school provisioning source failed", exc_info=True)
        return []


def _source_email_delivery_events() -> list[dict[str, Any]]:
    """Aggregate count of email delivery events in the last 24h.

    Surfaces the count + bounce rate hint only — never recipient addresses.
    """
    try:
        from apps.communications.models import EmailDeliveryEvent  # noqa: F401
    except Exception:
        # Model not present on this deploy — silently no-op.
        return []
    try:
        from apps.communications.models import EmailDeliveryEvent
        cutoff = timezone.now() - timedelta(hours=24)
        # tenant-isolation-allow: platform-activity-ticker-cross-tenant-aggregate-by-design
        recent_count = EmailDeliveryEvent.objects.filter(
            created_at__gte=cutoff,
        ).count()
        if recent_count == 0:
            return []
        return [{
            "icon": "✉",
            "severity": "info",
            "text": f"{recent_count} platform emails delivered today",
            "timestamp": _("24h"),
        }]
    except Exception:
        logger.warning("ticker: email delivery source failed", exc_info=True)
        return []


def _source_schools_pending_approval() -> list[dict[str, Any]]:
    """Schools awaiting operator approval — aggregate only."""
    try:
        from apps.schools.models import School

        cutoff = timezone.now() - timedelta(hours=24)
        ts_field = (
            "created_at"
            if hasattr(School, "created_at")
            else "date_joined"
            if hasattr(School, "date_joined")
            else None
        )
        # tenant-isolation-allow: platform-activity-ticker-cross-tenant-aggregate-by-design
        qs = School.objects.filter(is_approved=False)
        if ts_field:
            qs = qs.filter(**{f"{ts_field}__gte": cutoff})
        pending = qs.count()
        if pending == 0:
            return []
        return [{
            "icon": "⏳",
            "severity": "warn",
            "text": f"{pending} school{'s' if pending != 1 else ''} pending approval",
            "timestamp": _("24h"),
        }]
    except Exception:
        logger.warning("ticker: pending approval source failed", exc_info=True)
        return []


def _source_webhook_delivery_failures() -> list[dict[str, Any]]:
    """Failed or exhausted webhook deliveries in the last 24h."""
    try:
        from apps.migration_cloud.models import MigrationCloudWebhookDelivery
    except Exception:
        return []
    try:
        cutoff = timezone.now() - timedelta(hours=24)
        # tenant-isolation-allow: platform-activity-ticker-cross-tenant-aggregate-by-design
        failed = MigrationCloudWebhookDelivery.objects.filter(
            created_at__gte=cutoff,
            status__in=("failed", "exhausted"),
        ).count()
        if failed == 0:
            return []
        return [{
            "icon": "🔗",
            "severity": "danger",
            "text": f"{failed} webhook deliver{'y' if failed == 1 else 'ies'} need attention",
            "timestamp": _("24h"),
        }]
    except Exception:
        logger.warning("ticker: webhook failure source failed", exc_info=True)
        return []


def _source_migration_run_failures() -> list[dict[str, Any]]:
    """Failed migration runs in the last 24h (platform pulse incident proxy)."""
    try:
        from apps.automation.models import MigrationRun
    except Exception:
        return []
    try:
        cutoff = timezone.now() - timedelta(hours=24)
        ts_field = "started_at" if hasattr(MigrationRun, "started_at") else "created_at"
        if not hasattr(MigrationRun, ts_field):
            return []
        # tenant-isolation-allow: platform-activity-ticker-cross-tenant-aggregate-by-design
        failed = MigrationRun.objects.filter(
            **{f"{ts_field}__gte": cutoff},
            status=MigrationRun.Status.FAILED,
        ).count()
        if failed == 0:
            return []
        return [{
            "icon": "⚠",
            "severity": "danger",
            "text": f"{failed} migration run{'s' if failed != 1 else ''} failed today",
            "timestamp": _("24h"),
        }]
    except Exception:
        logger.warning("ticker: migration run failure source failed", exc_info=True)
        return []


def _source_offboarding_activity() -> list[dict[str, Any]]:
    """Recent lifecycle offboarding audit events (distinct from generic audit cap)."""
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent

        cutoff_iso = (timezone.now() - timedelta(hours=48)).isoformat()
        # tenant-isolation-allow: platform-activity-ticker-cross-tenant-aggregate-by-design
        rows = list(
            MigrationCloudAuditEvent.objects.filter(
                created_at_iso__gte=cutoff_iso,
                event_type__startswith="lifecycle.offboarding.",
            ).order_by("-created_at_iso").values("event_type", "created_at_iso")[:3]
        )
        cards = []
        for row in rows:
            etype = row.get("event_type") or ""
            cards.append({
                "icon": "🏁",
                "severity": "warn",
                "text": _text_for_audit(etype),
                "timestamp": _relative_ts(row.get("created_at_iso")),
            })
        return cards
    except Exception:
        logger.warning("ticker: offboarding activity source failed", exc_info=True)
        return []


def _source_tenant_subscription_changes() -> list[dict[str, Any]]:
    """Count of new tenant subscriptions started in the last 24h."""
    try:
        from apps.billing.models import TenantSubscription  # noqa: F401
    except Exception:
        return []
    try:
        from apps.billing.models import TenantSubscription
        cutoff = timezone.now() - timedelta(hours=24)
        # tenant-isolation-allow: platform-activity-ticker-cross-tenant-aggregate-by-design
        new_subs = TenantSubscription.objects.filter(
            created_at__gte=cutoff,
        ).count() if hasattr(TenantSubscription, "created_at") else 0
        if new_subs == 0:
            return []
        return [{
            "icon": "↗",
            "severity": "success",
            "text": f"{new_subs} new subscription{'s' if new_subs != 1 else ''} today",
            "timestamp": _("24h"),
        }]
    except Exception:
        logger.warning("ticker: tenant subscription source failed", exc_info=True)
        return []


def resolve_manager_ticker_cards() -> list[dict[str, Any]]:
    """Aggregate platform-wide ticker cards from all manager sources.

    Returns at most ``MAX_CARDS_TOTAL`` cards. Cache key is host-scoped
    (``:manager``) so this never overlaps a tenant cache entry.

    Empty return → caller falls back to operator-published seed cards.
    """
    cache_key = f"{CACHE_PREFIX}:manager:v1"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    cards = merge_activity_ticker_card_lists(
        _source_migration_audit_events(),
        _source_offboarding_activity(),
        _source_school_provisioning(),
        _source_schools_pending_approval(),
        _source_email_delivery_events(),
        _source_tenant_subscription_changes(),
        _source_webhook_delivery_failures(),
        _source_migration_run_failures(),
        max_total=MAX_CARDS_TOTAL,
    )

    try:
        cache.set(cache_key, cards, CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("ticker: manager cache set failed", exc_info=True)
    return cards


# ============================================================
# Tenant-scoped sources
# ============================================================

def _resolve_tenant_slug(request: Any) -> str:
    """Best-effort tenant slug for cache scoping. Returns "" when unresolvable."""
    site = getattr(request, "site_settings", None) or getattr(request, "SITE", None)
    if site is None:
        return ""
    slug = (
        getattr(site, "slug", None)
        or getattr(site, "schema_name", None)
        or getattr(site, "site_name", None)
        or ""
    )
    return str(slug or "")


def _source_tenant_attendance_milestones(request: Any) -> list[dict[str, Any]]:
    """Best-effort: surface a single 'attendance streak' card when the model exists."""
    try:
        from apps.attendance.models import AttendanceRecord  # noqa: F401
    except Exception:
        return []
    try:
        # Lightweight signal: count attendance rows in the last 24h. No row-level
        # PII surfaced — just an aggregate "attendance recorded today" line.
        from apps.attendance.models import AttendanceRecord
        cutoff = timezone.now() - timedelta(hours=24)
        if not hasattr(AttendanceRecord, "created_at") and not hasattr(AttendanceRecord, "date"):
            return []
        ts_field = "created_at" if hasattr(AttendanceRecord, "created_at") else "date"
        # The tenant-scoped manager isolates this query — by-design when the
        # tenant has the school FK on AttendanceRecord; no cross-tenant aggregate.
        recent = AttendanceRecord.objects.filter(**{f"{ts_field}__gte": cutoff}).count()
        if recent == 0:
            return []
        return [{
            "icon": "📋",
            "severity": "info",
            "text": f"{recent} attendance records logged today",
            "timestamp": _("24h"),
        }]
    except Exception:
        logger.warning("ticker: tenant attendance source failed", exc_info=True)
        return []


def _source_tenant_new_enrollments(request: Any) -> list[dict[str, Any]]:
    """New student profiles in the last 24h — count only."""
    try:
        from apps.people.models import StudentProfile
    except Exception:
        return []
    try:
        cutoff = timezone.now() - timedelta(hours=24)
        ts_field = "created_at" if hasattr(StudentProfile, "created_at") else None
        if ts_field is None:
            return []
        count = StudentProfile.objects.filter(**{f"{ts_field}__gte": cutoff}).count()
        if count == 0:
            return []
        return [{
            "icon": "🎓",
            "severity": "success",
            "text": f"{count} new enrollment{'s' if count != 1 else ''} today",
            "timestamp": _("24h"),
        }]
    except Exception:
        logger.warning("ticker: tenant enrollment source failed", exc_info=True)
        return []


def _source_tenant_communication_activity(request: Any) -> list[dict[str, Any]]:
    """Recent outbound messages — aggregate count only."""
    try:
        from apps.communication.models import Message
    except Exception:
        return []
    try:
        cutoff = timezone.now() - timedelta(hours=24)
        ts_field = "created_at" if hasattr(Message, "created_at") else "sent_at"
        if not hasattr(Message, ts_field):
            return []
        count = Message.objects.filter(**{f"{ts_field}__gte": cutoff}).count()
        if count == 0:
            return []
        return [{
            "icon": "💬",
            "severity": "info",
            "text": f"{count} message{'s' if count != 1 else ''} sent today",
            "timestamp": _("24h"),
        }]
    except Exception:
        logger.warning("ticker: tenant communication source failed", exc_info=True)
        return []


def _source_tenant_fee_receipts(request: Any) -> list[dict[str, Any]]:
    """Aggregate fee receipts in the last 24h. NEVER surfaces parent name or amount."""
    try:
        from apps.finance.models import Payment  # noqa: F401
    except Exception:
        return []
    try:
        from apps.finance.models import Payment
        cutoff = timezone.now() - timedelta(hours=24)
        ts_field = "created_at" if hasattr(Payment, "created_at") else (
            "paid_at" if hasattr(Payment, "paid_at") else None
        )
        if ts_field is None:
            return []
        # tenant-isolation-allow: tenant-schema-scoped-via-django-tenants-default-isolation
        count = Payment.objects.filter(**{f"{ts_field}__gte": cutoff}).count()
        if count == 0:
            return []
        return [{
            "icon": "💳",
            "severity": "success",
            "text": f"{count} fee payment{'s' if count != 1 else ''} received today",
            "timestamp": _("24h"),
        }]
    except Exception:
        logger.warning("ticker: tenant fee source failed", exc_info=True)
        return []


def resolve_tenant_ticker_cards(request: Any) -> list[dict[str, Any]]:
    """Aggregate tenant-scoped ticker cards from all tenant sources.

    Cache key includes the tenant slug HASH so a cache-set on one tenant
    can never contaminate another tenant's render.

    Empty return → caller falls back to operator-published seed cards
    (or the static helper defaults). Never returns operator-platform data.
    """
    tenant_slug = _resolve_tenant_slug(request)
    tenant_hash = _hash_prefix(tenant_slug) if tenant_slug else "anon"
    cache_key = f"{CACHE_PREFIX}:tenant:{tenant_hash}:v1"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    cards = merge_activity_ticker_card_lists(
        _source_tenant_attendance_milestones(request),
        _source_tenant_fee_receipts(request),
        _source_tenant_new_enrollments(request),
        _source_tenant_communication_activity(request),
        max_total=MAX_CARDS_TOTAL,
    )

    try:
        cache.set(cache_key, cards, CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("ticker: tenant cache set failed", exc_info=True)
    return cards


# ============================================================
# Orchestrator entry point
# ============================================================

def resolve_activity_ticker_cards(request: Any) -> dict[str, list[dict[str, Any]]]:
    """Return ``{section_key: cards_list}`` for whichever host applies.

    Manager host returns ``{"activity_ticker": [...]}``.
    Tenant host returns ``{"tenant_activity_ticker": [...]}``.
    Other hosts (auth / marketing / base) return ``{}`` — the partial
    handles the silent case via its early-exit gate.

    Total wall-clock budget: each source has its own try/except; an
    individual model-missing scenario adds zero cards but doesn't poison
    the rest of the call. A catastrophic failure returns ``{}``.
    """
    try:
        host_kind = getattr(request, "public_host_kind", None)
        if host_kind == "manager":
            cards = resolve_manager_ticker_cards()
            if cards:
                return {"activity_ticker": {"cards": cards}}
            return {}
        # Anything other than manager that has an authenticated user is treated
        # as tenant for ticker purposes. The partial gates rendering on
        # `request.user.is_authenticated` so anonymous/marketing/auth shells
        # stay silent regardless.
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return {}
        cards = resolve_tenant_ticker_cards(request)
        if cards:
            return {"tenant_activity_ticker": {"cards": cards}}
        return {}
    except Exception:
        logger.warning("ticker: resolve_activity_ticker_cards crashed", exc_info=True)
        return {}


def invalidate_activity_ticker_cache(request: Any | None = None) -> None:
    """Clear ticker cache keys. Safe to call from a signal handler."""
    try:
        cache.delete(f"{CACHE_PREFIX}:manager:v1")
        if request is not None:
            tenant_slug = _resolve_tenant_slug(request)
            tenant_hash = _hash_prefix(tenant_slug) if tenant_slug else "anon"
            cache.delete(f"{CACHE_PREFIX}:tenant:{tenant_hash}:v1")
    except Exception:
        pass


__all__ = [
    "merge_activity_ticker_card_lists",
    "merge_activity_ticker_sections",
    "resolve_activity_ticker_cards",
    "resolve_manager_ticker_cards",
    "resolve_tenant_ticker_cards",
    "invalidate_activity_ticker_cache",
    "MAX_CARDS_TOTAL",
]
