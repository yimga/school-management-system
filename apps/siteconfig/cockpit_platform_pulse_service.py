"""
cockpit_platform_pulse_service.py — v3.58.0 (2026-05-22).

Real-data resolver for the 6 platform-pulse KPI cards rendered on the
manager landing page (schools/super_dashboard.html and the two landing
peers). Replaces the hard-coded ``_DEFAULT_PULSE_CARDS`` constant in
``cockpit_context.py`` so operators see actual platform state instead of
v8 200x preview demo values.

Honest empty-state contract:
    Every resolver is wrapped in try/except. On ANY error (model missing,
    migration not applied on this environment, DB unreachable, etc.) the
    resolver returns ``None`` and the card renders with ``value="—"`` /
    ``label=""`` / ``delta=""``. The card stays visible so the layout
    holds, but it is honestly empty — no mock numbers.

Demo override:
    When ``settings.COCKPIT_200X_RENDER_PREVIEW_DEMO`` is True, the
    orchestrator in ``cockpit_context.py`` keeps the demo cards from
    ``_DEFAULT_PULSE_CARDS`` instead of calling this service. That keeps
    the preview HTML demos working byte-for-byte while production
    deployments get real numbers by default.

Architectural posture:
    - Lazy model imports inside each resolver so a missing app or
      unmigrated model never breaks the cockpit context processor for
      every page on the platform.
    - Per-resolver caching (60s TTL) via ``django.core.cache.cache`` to
      keep dashboard renders snappy even when these queries hit the DB
      on every request.
    - Locale-aware label strings via ``django.utils.translation`` so
      tenant locales render the right copy.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

PULSE_CACHE_TTL_SECONDS = 60
PULSE_CACHE_PREFIX = "rmc:cockpit:pulse"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _empty_card(head: str, label_when_empty: str = "") -> dict[str, Any]:
    """Honest empty-state card shape — no mock value, no fake delta."""
    return {
        "head": head,
        "severity": "muted",
        "value": "—",
        "label": label_when_empty,
        "delta": "",
        "delta_direction": None,
    }


# ============================================================
# Card resolvers — one per slot. Each MUST tolerate missing models,
# unmigrated DBs, and unrelated import failures. Return None on any
# failure path so the orchestrator can substitute an empty-state card.
# ============================================================

def _resolve_schools_card() -> dict[str, Any] | None:
    """Active + approved schools across the platform."""
    try:
        from apps.schools.models import School  # local import
        total = School.objects.filter(is_active=True, is_approved=True).count()
        if total is None:
            return None
        return {
            "head": _("Schools"),
            "severity": "ok",
            "value": str(total),
            "label": _("Healthy"),
            "delta": "",  # delta vs last week requires a snapshot table; deferred
            "delta_direction": None,
        }
    except Exception:
        logger.warning("pulse: schools resolver failed", exc_info=True)
        return None


def _resolve_incidents_card() -> dict[str, Any] | None:
    """Open operational incidents in the last 24h.

    Today this counts FAILED MigrationRun rows in the last 24h as the
    closest platform-wide proxy for "things that need operator attention."
    When a dedicated incident model lands, swap this resolver to query it.
    """
    try:
        from datetime import timedelta
        from django.utils import timezone
        from apps.automation.models import MigrationRun  # local import
        cutoff = timezone.now() - timedelta(hours=24)
        # The MigrationRun status field stores lowercase per its model — be
        # permissive and accept both cases so the query is robust.
        # tenant-isolation-allow: platform-pulse-cross-tenant-incident-count-by-design
        open_count = MigrationRun.objects.filter(
            created_at__gte=cutoff,
            status__iexact="failed",
        ).count()
        if open_count is None:
            return None
        severity = "ok" if open_count == 0 else "warn"
        return {
            "head": _("Incidents"),
            "severity": severity,
            "value": str(open_count),
            "label": _("Open · 24h"),
            "delta": "",
            "delta_direction": None,
        }
    except Exception:
        logger.warning("pulse: incidents resolver failed", exc_info=True)
        return None


def _resolve_countries_card() -> dict[str, Any] | None:
    """Distinct country_code values across active schools.

    Denominator is 249 — the ISO 3166-1 alpha-2 count operators expect on
    a "live coverage" card. Hardcoded because it's not a runtime value.
    """
    try:
        from apps.schools.models import School  # local import
        countries = (
            School.objects.filter(is_active=True)
            .exclude(country_code="")
            .values_list("country_code", flat=True)
            .distinct()
            .count()
        )
        if countries is None:
            return None
        return {
            "head": _("Countries"),
            "severity": "info",
            "value": f"{countries} / 249",
            "label": _("Live coverage"),
            "delta": "",
            "delta_direction": None,
        }
    except Exception:
        logger.warning("pulse: countries resolver failed", exc_info=True)
        return None


def _resolve_mrr_card() -> dict[str, Any] | None:
    """Monthly Recurring Revenue across active tenant subscriptions.

    ANNUAL subscriptions divide by 12 for the monthly-equivalent contribution.
    MONTHLY contribute their full billed amount. MANUAL / inactive statuses
    are excluded.
    """
    try:
        from apps.billing.models import TenantSubscription  # local import
        Status = TenantSubscription.Status
        Cycle = TenantSubscription.BillingCycle
        # tenant-isolation-allow: platform-pulse-cross-tenant-mrr-aggregate-by-design
        active = TenantSubscription.objects.filter(
            status__in=[Status.ACTIVE, Status.TRIALING]
        )
        # Avoid Sum() to keep this resolver tolerant of decimal/null edge cases
        # — iterate in Python so a single malformed row doesn't fail the aggregate.
        monthly_total = Decimal("0.00")
        for sub in active.only("billed_amount", "billing_cycle").iterator():
            amount = sub.billed_amount or Decimal("0.00")
            if sub.billing_cycle == Cycle.ANNUAL:
                amount = amount / Decimal("12")
            monthly_total += amount
        # Format: $42k for 4-digit-plus, $1.2k for thousands, $850 below.
        if monthly_total >= 1000:
            value = f"${(monthly_total / 1000):.1f}k".replace(".0k", "k")
        else:
            value = f"${monthly_total:.0f}"
        return {
            "head": _("MRR"),
            "severity": "ok" if monthly_total > 0 else "muted",
            "value": value,
            "label": _("Recurring"),
            "delta": "",
            "delta_direction": None,
        }
    except Exception:
        logger.warning("pulse: mrr resolver failed", exc_info=True)
        return None


def _resolve_webhooks_card() -> dict[str, Any] | None:
    """Webhook drift count — subscriptions with recent delivery failures.

    Today this counts inactive/disabled Migration Cloud webhook subscriptions
    as the proxy for "drift". A future iteration can join WebhookDelivery to
    surface subscriptions whose last N deliveries failed.
    """
    try:
        from apps.migration_cloud.models import MigrationCloudWebhookSubscription
        drift = MigrationCloudWebhookSubscription.objects.filter(
            is_active=False,
        ).count()
        if drift is None:
            return None
        return {
            "head": _("Webhooks"),
            "severity": "ok" if drift == 0 else "warn",
            "value": str(drift),
            "label": _("Drift"),
            "delta": "",
            "delta_direction": None,
        }
    except Exception:
        logger.warning("pulse: webhooks resolver failed", exc_info=True)
        return None


def _resolve_pipeline_card() -> dict[str, Any] | None:
    """Schools currently in the onboarding pipeline (pending approval)."""
    try:
        from apps.schools.models import School  # local import
        pipeline = School.objects.filter(
            is_active=False, is_approved=False,
        ).count()
        if pipeline is None:
            return None
        return {
            "head": _("Pipeline"),
            "severity": "info" if pipeline > 0 else "muted",
            "value": str(pipeline),
            "label": _("Onboarding"),
            "delta": "",
            "delta_direction": None,
        }
    except Exception:
        logger.warning("pulse: pipeline resolver failed", exc_info=True)
        return None


# Ordered resolvers — order MUST match the 6-slot layout in the v8 preview.
_PULSE_RESOLVERS: tuple[tuple[str, callable], ...] = (
    ("schools", _resolve_schools_card),
    ("incidents", _resolve_incidents_card),
    ("countries", _resolve_countries_card),
    ("mrr", _resolve_mrr_card),
    ("webhooks", _resolve_webhooks_card),
    ("pipeline", _resolve_pipeline_card),
)

# Empty-state shells used when a resolver returns None — keeps the layout
# stable (6 cards always rendered, even when DB is silent).
_EMPTY_SHELLS: dict[str, dict[str, Any]] = {
    "schools":   _empty_card(_("Schools"),   _("Healthy")),
    "incidents": _empty_card(_("Incidents"), _("Open")),
    "countries": _empty_card(_("Countries"), _("Live coverage")),
    "mrr":       _empty_card(_("MRR"),       _("Recurring")),
    "webhooks":  _empty_card(_("Webhooks"),  _("Drift")),
    "pipeline":  _empty_card(_("Pipeline"),  _("Onboarding")),
}


def resolve_pulse_cards() -> list[dict[str, Any]]:
    """Resolve all 6 pulse cards with live data, falling back to empty-state.

    Cached per-process for ``PULSE_CACHE_TTL_SECONDS`` (60s) under
    ``rmc:cockpit:pulse:v1`` so the dashboard render stays snappy when many
    operators hit /super/ around the same minute.
    """
    cache_key = f"{PULSE_CACHE_PREFIX}:v1"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    cards: list[dict[str, Any]] = []
    for slot, resolver in _PULSE_RESOLVERS:
        try:
            card = resolver()
        except Exception:
            logger.warning("pulse: %s resolver crashed", slot, exc_info=True)
            card = None
        cards.append(card if card else _EMPTY_SHELLS[slot])

    try:
        cache.set(cache_key, cards, PULSE_CACHE_TTL_SECONDS)
    except Exception:
        # Cache backend unavailable (uncommon — defensive). Render anyway.
        logger.warning("pulse: cache set failed", exc_info=True)

    return cards


def invalidate_pulse_cards_cache() -> None:
    """Call from signal handlers to force a fresh render."""
    try:
        cache.delete(f"{PULSE_CACHE_PREFIX}:v1")
    except Exception:
        pass
