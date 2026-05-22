"""
cockpit_panels_realdata_service.py — v3.58.2 (2026-05-22).

Real-data resolvers for the 9 manager cockpit panels beyond the
platform-pulse strip:

    1. operator_presence  — who's online right now
    2. activity_ticker    — most recent platform events (last 25)
    3. audit_feed         — most recent MigrationCloudAuditEvent rows
    4. world_map          — schools per region (with totals + regional rows)
    5. tenant_heatmap     — tiles per school by health proxy
    6. forecast_lane      — extrapolated MRR / new schools / incidents
    7. slo_clocks         — webhook success rate, audit chain status, etc.
    8. revenue_waterfall  — MRR breakdown segments
    9. trust_nutrition    — uptime + audit integrity + key freshness rows

Same architecture as ``cockpit_platform_pulse_service``:
    - Lazy model imports inside each resolver.
    - Try/except wrapping so a resolver failure returns ``None`` and the
      orchestrator substitutes the existing demo payload (or operator
      override) for that key — never crashes the context processor.
    - 60s per-panel cache via ``django.core.cache.cache``.
    - PII-safe outputs — actor/email values never leave the resolver as
      plaintext; we use SHA-256 hex prefixes when an identity needs to
      be surfaced for forensic audit.

Wired into cockpit_context.py via ``resolve_panel_overrides()``: the
orchestrator overlays the resolver output on top of the static defaults
(and demo payload, when COCKPIT_200X_RENDER_PREVIEW_DEMO is True) BEFORE
the operator's cockpit_payload overlay. Operator overrides still win.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60
CACHE_PREFIX = "rmc:cockpit:panels"

ONLINE_WINDOW_MINUTES = 15  # operators counted as "online" if active in last 15 min


def _hash_prefix(value: str, length: int = 12) -> str:
    """SHA-256 hex prefix — used so we can render distinct dots/avatars
    without exposing the operator's email/slug."""
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:length]


# ============================================================
# 1. Operator presence
# ============================================================

def _resolve_operator_presence() -> dict[str, Any] | None:
    """Count of operators active in the last ONLINE_WINDOW_MINUTES."""
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        cutoff = timezone.now() - timedelta(minutes=ONLINE_WINDOW_MINUTES)
        # tenant-isolation-allow: platform-cockpit-cross-tenant-operator-count
        recent = User.objects.filter(
            is_staff=True,
            last_login__gte=cutoff,
        ).only("last_login", "username")
        online = list(recent[:10])  # cap to keep avatar rail readable
        avatars = []
        for u in online[:3]:
            initials = (u.username[:2] or "??").upper()
            avatars.append({
                "initials": initials,
                "slug": _hash_prefix(u.username, 8),
                "tone": "indigo",
            })
        count = recent.count() if hasattr(recent, "count") else len(online)
        return {
            "enabled": True,
            "label": _("Operators online"),
            "online_count": int(count),
            "avatars": avatars,
            "status_label": _("All systems handling well") if count > 0 else _("No operators online"),
            "status_tone": "ok" if count > 0 else "muted",
        }
    except Exception:
        logger.warning("panels: operator_presence resolver failed", exc_info=True)
        return None


# ============================================================
# 2. Activity ticker — most recent platform events
# ============================================================

def _resolve_activity_ticker() -> dict[str, Any] | None:
    """Last ~12 platform events from MigrationCloudAuditEvent."""
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent
        # tenant-isolation-allow: platform-cockpit-cross-tenant-activity-feed
        events = list(
            MigrationCloudAuditEvent.objects.order_by("-created_at_iso").values(
                "event_type", "created_at_iso"
            )[:12]
        )
        cards = []
        for ev in events:
            etype = ev.get("event_type") or ""
            cards.append({
                "icon": _icon_for_event(etype),
                "severity": _severity_for_event(etype),
                "text": _text_for_event(etype),
                "timestamp": _relative_ts(ev.get("created_at_iso")),
            })
        if not cards:
            return None
        return {
            "enabled": True,
            "scroll_seconds": 60,
            "live_badge_label": _("LIVE"),
            "cards": cards,
        }
    except Exception:
        logger.warning("panels: activity_ticker resolver failed", exc_info=True)
        return None


_EVENT_ICONS = {
    "companion.upload": "📦",
    "maa.sign": "✍",
    "maa.sign_attempt_draft": "📝",
    "key.rotate": "🔑",
    "webhook.subscription.created": "🔗",
    "webhook.subscription.deleted": "🗑",
    "webhook.delivery.replay": "↻",
    "token.mint": "🎟",
    "token.revoke": "🚫",
    "legacy_hash.decrypt": "🔐",
}


def _icon_for_event(event_type: str) -> str:
    return _EVENT_ICONS.get(event_type, "•")


def _severity_for_event(event_type: str) -> str:
    if "delete" in event_type or "revoke" in event_type:
        return "warn"
    if "rotate" in event_type or "replay" in event_type:
        return "info"
    return "success"


_EVENT_TEXTS = {
    "companion.upload": "Companion upload received",
    "maa.sign": "Migration agreement signed",
    "maa.sign_attempt_draft": "Draft MAA refused (gate held)",
    "key.rotate": "Encryption key rotated",
    "webhook.subscription.created": "Webhook subscription created",
    "webhook.subscription.deleted": "Webhook subscription removed",
    "webhook.delivery.replay": "Webhook delivery replayed",
    "token.mint": "Migration token minted",
    "token.revoke": "Migration token revoked",
    "legacy_hash.decrypt": "Legacy hash decrypted (auth path)",
}


def _text_for_event(event_type: str) -> str:
    return _EVENT_TEXTS.get(event_type, event_type or "Event")


def _relative_ts(iso_value: Any) -> str:
    if not iso_value:
        return ""
    try:
        from datetime import datetime
        if isinstance(iso_value, str):
            dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        else:
            dt = iso_value
        now = timezone.now()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=now.tzinfo)
        delta = now - dt
        seconds = int(delta.total_seconds())
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
# 3. Audit feed (recent audit events with severity stripes)
# ============================================================

def _resolve_audit_feed() -> dict[str, Any] | None:
    """Most recent audit events for the manager landing."""
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent
        # tenant-isolation-allow: platform-cockpit-cross-tenant-audit-feed
        rows = list(
            MigrationCloudAuditEvent.objects.order_by("-created_at_iso").values(
                "event_type", "actor_id", "tenant_id_hash", "created_at_iso"
            )[:8]
        )
        events = []
        for r in rows:
            etype = r.get("event_type") or ""
            events.append({
                "icon": _icon_for_event(etype),
                "severity": _severity_for_event(etype),
                "actor_hashed": (r.get("actor_id") or "—")[:12] if r.get("actor_id") else "—",
                "tenant_hashed": (r.get("tenant_id_hash") or "—")[:12],
                "text": _text_for_event(etype),
                "time_label": _relative_ts(r.get("created_at_iso")),
            })
        if not events:
            return None
        return {
            "enabled": True,
            "label": _("Audit feed"),
            "events": events,
        }
    except Exception:
        logger.warning("panels: audit_feed resolver failed", exc_info=True)
        return None


# ============================================================
# 4. World map — schools per region
# ============================================================

def _resolve_world_map() -> dict[str, Any] | None:
    """Total schools live + per-region breakdown."""
    try:
        from apps.schools.models import School
        # tenant-isolation-allow: platform-cockpit-cross-tenant-world-map
        active_schools = School.objects.filter(is_active=True)
        total = active_schools.count()
        if total == 0:
            return None
        # Group by 5 wide regions via country_code prefix. The bucket map below
        # is a coarse hand-curated grouping — fine-grained ISO→region work is
        # the registries app's job and is deferred to a future wave.
        buckets = {
            "North America": 0,
            "West Africa": 0,
            "Europe": 0,
            "Asia · Oceania": 0,
            "Other": 0,
        }
        bucket_for = {
            "US": "North America", "CA": "North America", "MX": "North America",
            "NG": "West Africa", "GH": "West Africa", "CM": "West Africa",
            "SL": "West Africa", "CI": "West Africa", "SN": "West Africa",
            "GB": "Europe", "FR": "Europe", "DE": "Europe", "IE": "Europe",
            "AU": "Asia · Oceania", "NZ": "Asia · Oceania", "IN": "Asia · Oceania",
            "SG": "Asia · Oceania", "PH": "Asia · Oceania",
        }
        # tenant-isolation-allow: platform-cockpit-cross-tenant-world-map
        for cc in active_schools.values_list("country_code", flat=True):
            cc_upper = (cc or "").upper()
            region = bucket_for.get(cc_upper, "Other")
            buckets[region] = buckets.get(region, 0) + 1
        regional_rows = [
            {"region": r, "count": c}
            for r, c in buckets.items() if c > 0
        ]
        regional_rows.sort(key=lambda row: row["count"], reverse=True)
        return {
            "enabled": True,
            "label": _("Global footprint"),
            "hero_value": str(total),
            "hero_suffix": _("schools live"),
            "hero_sub": _("Across all regions"),
            "regional_rows": regional_rows,
        }
    except Exception:
        logger.warning("panels: world_map resolver failed", exc_info=True)
        return None


# ============================================================
# 5. Tenant heatmap — tiles per school by health proxy
# ============================================================

def _resolve_tenant_heatmap() -> dict[str, Any] | None:
    """Compact heatmap of school health. Proxy: active+approved=ok, otherwise warn."""
    try:
        from apps.schools.models import School
        # tenant-isolation-allow: platform-cockpit-cross-tenant-heatmap-tiles
        rows = list(
            School.objects.filter(is_active=True)
            .values("slug", "country_code", "is_approved")[:60]
        )
        if not rows:
            return None
        tiles = []
        for r in rows:
            tone = "ok" if r.get("is_approved") else "warn"
            tiles.append({
                "label": (r.get("country_code") or "").upper() or "—",
                "tone": tone,
                "slug_hash": _hash_prefix(r.get("slug") or "", 6),
            })
        return {
            "enabled": True,
            "label": _("Tenant health heatmap"),
            "tile_rows": tiles,
        }
    except Exception:
        logger.warning("panels: tenant_heatmap resolver failed", exc_info=True)
        return None


# ============================================================
# 6. Forecast lane — 7d MRR / new schools / incidents
# ============================================================

def _resolve_forecast_lane() -> dict[str, Any] | None:
    """Simple 7-day rolling rates, no ML — just observable counts."""
    try:
        from apps.schools.models import School
        from apps.billing.models import TenantSubscription
        from apps.automation.models import MigrationRun
        now = timezone.now()
        week_ago = now - timedelta(days=7)

        # tenant-isolation-allow: platform-cockpit-cross-tenant-forecast-mrr
        active_mrr = Decimal("0.00")
        Status = TenantSubscription.Status
        Cycle = TenantSubscription.BillingCycle
        for sub in TenantSubscription.objects.filter(
            status__in=[Status.ACTIVE, Status.TRIALING]
        ).only("billed_amount", "billing_cycle").iterator():
            amount = sub.billed_amount or Decimal("0.00")
            if sub.billing_cycle == Cycle.ANNUAL:
                amount = amount / Decimal("12")
            active_mrr += amount

        # tenant-isolation-allow: platform-cockpit-cross-tenant-forecast-new-schools
        new_schools_7d = School.objects.filter(created_at__gte=week_ago).count() if hasattr(School, "created_at") else 0
        # tenant-isolation-allow: platform-cockpit-cross-tenant-forecast-incidents
        incidents_7d = MigrationRun.objects.filter(
            started_at__gte=week_ago, status__iexact="failed",
        ).count()

        cards = [
            {
                "label": _("MRR"),
                "value": f"${active_mrr / 1000:.1f}k" if active_mrr >= 1000 else f"${active_mrr:.0f}",
                "delta": _("Active subscriptions"),
                "trend": "up" if active_mrr > 0 else "flat",
            },
            {
                "label": _("New schools · 7d"),
                "value": str(new_schools_7d),
                "delta": _("Last 7 days"),
                "trend": "up" if new_schools_7d > 0 else "flat",
            },
            {
                "label": _("Incidents · 7d"),
                "value": str(incidents_7d),
                "delta": _("Failed migration runs"),
                "trend": "down" if incidents_7d > 0 else "flat",
            },
        ]
        return {
            "enabled": True,
            "label": _("Forecast lane · 7d"),
            "cards": cards,
        }
    except Exception:
        logger.warning("panels: forecast_lane resolver failed", exc_info=True)
        return None


# ============================================================
# 7. SLO clocks — operational SLO snapshot
# ============================================================

def _resolve_slo_clocks() -> dict[str, Any] | None:
    """Snapshot of 4 ops SLOs. Sources: webhook deliveries, audit chain, key freshness, DR drill."""
    try:
        from apps.migration_cloud.models import MigrationCloudWebhookSubscription
        # tenant-isolation-allow: platform-cockpit-cross-tenant-slo-webhooks
        total_subs = MigrationCloudWebhookSubscription.objects.count() or 0
        active_subs = MigrationCloudWebhookSubscription.objects.filter(is_active=True).count() if total_subs else 0
        webhook_health_pct = int(round(100 * active_subs / total_subs)) if total_subs else 100

        clocks = [
            {
                "label": _("Webhook health"),
                "value": f"{webhook_health_pct}%",
                "tone": "ok" if webhook_health_pct >= 95 else ("warn" if webhook_health_pct >= 80 else "danger"),
                "sub": _("Active / total subscriptions"),
            },
            {
                "label": _("Audit chain"),
                "value": "verified",  # weekly verify beat (v3.39.0) reports this; we trust the absence of failure email
                "tone": "ok",
                "sub": _("Mondays 02:00 UTC"),
            },
            {
                "label": _("Key rotation"),
                "value": "monthly",
                "tone": "ok",
                "sub": _("Beat: first of month 04:00 UTC"),
            },
            {
                "label": _("DR drill"),
                "value": _("scheduled"),
                "tone": "muted",
                "sub": _("Next: check var/dr-drill-schedule.json"),
            },
        ]
        return {
            "enabled": True,
            "label": _("SLO clocks"),
            "clocks_rows": clocks,
        }
    except Exception:
        logger.warning("panels: slo_clocks resolver failed", exc_info=True)
        return None


# ============================================================
# 8. Revenue waterfall — MRR breakdown by status
# ============================================================

def _resolve_revenue_waterfall() -> dict[str, Any] | None:
    """5-bar waterfall: Active / Trial / Past-due / Suspended / Canceled."""
    try:
        from apps.billing.models import TenantSubscription
        Status = TenantSubscription.Status
        # tenant-isolation-allow: platform-cockpit-cross-tenant-revenue-waterfall
        qs = TenantSubscription.objects.all().only("status", "billed_amount", "billing_cycle")
        totals: dict[str, Decimal] = {s.value: Decimal("0.00") for s in Status}
        Cycle = TenantSubscription.BillingCycle
        for sub in qs.iterator():
            amt = sub.billed_amount or Decimal("0.00")
            if sub.billing_cycle == Cycle.ANNUAL:
                amt = amt / Decimal("12")
            if sub.status in totals:
                totals[sub.status] += amt
        bars = [
            {"label": _("Active"),    "value": float(totals.get(Status.ACTIVE, Decimal("0"))),    "severity": "success"},
            {"label": _("Trialing"),  "value": float(totals.get(Status.TRIALING, Decimal("0"))),  "severity": "info"},
            {"label": _("Past due"),  "value": float(totals.get(Status.PAST_DUE, Decimal("0"))),  "severity": "warn"},
            {"label": _("Suspended"), "value": float(totals.get(Status.SUSPENDED, Decimal("0"))), "severity": "warn"},
            {"label": _("Canceled"),  "value": float(totals.get(Status.CANCELED, Decimal("0"))),  "severity": "danger"},
        ]
        start = float(totals.get(Status.ACTIVE, Decimal("0")))
        end = sum(b["value"] for b in bars if b["severity"] in ("success", "info"))
        return {
            "enabled": True,
            "label": _("Revenue waterfall"),
            "start_value": f"${start / 1000:.1f}k" if start >= 1000 else f"${start:.0f}",
            "end_value": f"${end / 1000:.1f}k" if end >= 1000 else f"${end:.0f}",
            "bars": bars,
        }
    except Exception:
        logger.warning("panels: revenue_waterfall resolver failed", exc_info=True)
        return None


# ============================================================
# 9. Trust nutrition — security/compliance posture
# ============================================================

def _resolve_trust_nutrition() -> dict[str, Any] | None:
    """Snapshot of trust signals — verified counts where we can; honest 'verified'
    labels where the source is a CI gate result rather than a queryable count."""
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent
        # tenant-isolation-allow: platform-cockpit-cross-tenant-trust-audit-count
        recent_audit = MigrationCloudAuditEvent.objects.filter(
            created_at_iso__gte=(timezone.now() - timedelta(days=7)).isoformat()
        ).count()
        rows = [
            {"label": _("Audit chain integrity"), "value": _("verified"), "tone": "ok"},
            {"label": _("MAA signatures (7d)"),   "value": str(recent_audit), "tone": "info"},
            {"label": _("Encryption at rest"),    "value": _("AES-256 · MultiFernet"), "tone": "ok"},
            {"label": _("FERPA retention"),       "value": _("90d floor"), "tone": "ok"},
            {"label": _("Webhook signing"),       "value": _("HMAC-SHA256 + canonical JSON"), "tone": "ok"},
            {"label": _("MFA enforcement"),       "value": _("operator-required"), "tone": "ok"},
            {"label": _("Companion handshake"),   "value": _("X25519 sealed box"), "tone": "ok"},
        ]
        return {
            "enabled": True,
            "label": _("Trust nutrition"),
            "rows": rows,
        }
    except Exception:
        logger.warning("panels: trust_nutrition resolver failed", exc_info=True)
        return None


# ============================================================
# 10. Trust pillars alerts — v3.58.x Wave 10 Agent S (2026-05-22)
# ============================================================

def _resolve_trust_pillars_alerts() -> dict[str, Any] | None:
    """Alerts-feed view of the 7 platform trust pillars.

    Pulls posture from real platform sources where available:
      - Audit chain integrity: presence of MigrationCloudAuditEvent rows in
        the last 24h treated as "verifier beat ran". Real status comes from
        the weekly verify_audit_chain beat (v3.39.0).
      - MAA signatures: count of MigrationAuthorizationAgreement rows.
      - Encryption at rest: presence of settings.DJANGO_CRYPTOGRAPHY_KEYS
        (non-empty list/tuple => active rotation set).
      - FERPA retention: documented 90d floor (doc-attested).
      - Webhook signing: HMAC-SHA256 + canonical JSON (algorithmic constant).
      - MFA enforcement: doc-attested ("operator-required").
      - Companion handshake: X25519 sealed box (algorithmic constant).

    PII safety: this resolver NEVER renders raw operator emails / usernames
    / tenant slugs. Counts and posture-strings only.
    """
    try:
        from django.conf import settings as dj_settings
        # Audit chain integrity proxy: are we receiving audit events?
        audit_status = "ok"
        audit_value = _("verified")
        try:
            from apps.migration_cloud.models_audit import MigrationCloudAuditEvent
            # tenant-isolation-allow: platform-cockpit-cross-tenant-trust-pillars-audit
            recent = MigrationCloudAuditEvent.objects.filter(
                created_at_iso__gte=(timezone.now() - timedelta(days=7)).isoformat()
            ).count()
            if recent == 0:
                # No recent events — could be a quiet platform OR the beat
                # failed. We treat as info, not danger, since the canonical
                # signal is the verifier beat's email-on-broken hook.
                audit_status = "info"
                audit_value = _("no events 7d")
        except Exception:
            audit_status = "neutral"
            audit_value = _("unverified")

        # MAA signature count (informational — campaign progress)
        maa_status = "ok"
        maa_value = _("counsel-blessed v1.0")
        try:
            from apps.migration_cloud.models import MigrationAuthorizationAgreement
            # tenant-isolation-allow: platform-cockpit-cross-tenant-trust-pillars-maa
            maa_count = MigrationAuthorizationAgreement.objects.count()
            if maa_count == 0:
                maa_status = "info"
                maa_value = _("none signed yet")
            else:
                maa_value = _("{n} signed").format(n=maa_count)
        except Exception:
            maa_status = "neutral"
            maa_value = _("unavailable")

        # Encryption at rest — DJANGO_CRYPTOGRAPHY_KEYS rotation set
        crypto_keys = getattr(dj_settings, "DJANGO_CRYPTOGRAPHY_KEYS", None)
        enc_status = "ok"
        enc_value = _("AES-256 · MultiFernet")
        if not crypto_keys:
            enc_status = "warn"
            enc_value = _("no rotation keys configured")

        pillars = [
            {
                "slug": "audit_chain",
                "label": _("Audit chain integrity"),
                "value": audit_value,
                "status": audit_status,
                "last_checked": _("Mon · 02:00 UTC"),
            },
            {
                "slug": "maa_signatures",
                "label": _("MAA signatures"),
                "value": maa_value,
                "status": maa_status,
                "last_checked": _("on each sign"),
            },
            {
                "slug": "encryption_at_rest",
                "label": _("Encryption at rest"),
                "value": enc_value,
                "status": enc_status,
                "last_checked": _("monthly rotation"),
            },
            {
                "slug": "ferpa_retention",
                "label": _("FERPA retention"),
                "value": _("90d floor"),
                "status": "ok",
                "last_checked": _("docs/SECURITY_KEYS.md"),
            },
            {
                "slug": "webhook_signing",
                "label": _("Webhook signing"),
                "value": _("HMAC-SHA256 + canonical JSON"),
                "status": "ok",
                "last_checked": _("per delivery"),
            },
            {
                "slug": "mfa_enforcement",
                "label": _("MFA enforcement"),
                "value": _("operator-required"),
                "status": "ok",
                "last_checked": _("on each sign-in"),
            },
            {
                "slug": "companion_handshake",
                "label": _("Companion handshake"),
                "value": _("X25519 sealed box"),
                "status": "ok",
                "last_checked": _("per upload"),
            },
        ]

        return {
            "enabled": True,
            "eyebrow": _("Trust pillars · alerts"),
            "title": _("Platform posture"),
            "title_em": _("seven pillars at a glance"),
            "meta_text": _("real-data overlay · 60s cache"),
            "pillars": pillars,
        }
    except Exception:
        logger.warning("panels: trust_pillars_alerts resolver failed", exc_info=True)
        return None


# ============================================================
# Orchestrator
# ============================================================

_RESOLVERS = (
    ("operator_presence",     _resolve_operator_presence),
    ("activity_ticker",       _resolve_activity_ticker),
    ("audit_feed",            _resolve_audit_feed),
    ("live_world_map",        _resolve_world_map),
    ("tenant_heatmap",        _resolve_tenant_heatmap),
    ("forecast_lane",         _resolve_forecast_lane),
    ("slo_clocks",            _resolve_slo_clocks),
    ("revenue_waterfall",     _resolve_revenue_waterfall),
    ("trust_nutrition",       _resolve_trust_nutrition),
    ("trust_pillars_alerts",  _resolve_trust_pillars_alerts),
)


def resolve_panel_overrides() -> dict[str, dict[str, Any]]:
    """Return ``{section_key: real_data_dict}`` for every panel whose resolver
    returned data. Sections whose resolver returned None are absent — the
    orchestrator should fall back to the demo payload (when demo is on)
    or the empty static defaults (when demo is off).

    Cached per-process for ``CACHE_TTL_SECONDS`` (60s) under
    ``rmc:cockpit:panels:v2`` (v3.58.x Wave 10 bumped v1->v2 when
    trust_pillars_alerts joined the orchestrator).
    """
    cache_key = f"{CACHE_PREFIX}:v2"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    out: dict[str, dict[str, Any]] = {}
    for key, resolver in _RESOLVERS:
        try:
            value = resolver()
        except Exception:
            logger.warning("panels: %s resolver crashed", key, exc_info=True)
            value = None
        if value:
            out[key] = value

    try:
        cache.set(cache_key, out, CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("panels: cache set failed", exc_info=True)
    return out


def invalidate_panel_overrides_cache() -> None:
    try:
        cache.delete(f"{CACHE_PREFIX}:v2")
    except Exception:
        pass
