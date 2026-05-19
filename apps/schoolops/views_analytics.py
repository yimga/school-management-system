"""v3.33.0 — Schoolops operator analytics dashboard for low-balance trends.

Endpoint:
    GET /super/schoolops/meal-plan-analytics/   — staff-only

Aggregates from :class:`MealPlanBalance` notification-tracking fields
added in v3.32 (``last_low_balance_notification_sent_at`` /
``low_balance_notification_count``) and joins guardian-side preferred
language for per-locale breakdown.

Permission model: ``staff_member_required``. The URL pattern carries
``# rbac-allow: staff-only-meal-plan-analytics-dashboard`` so
:mod:`audit_role_permission_matrix` records the intentional gate.

Defensive invariants:
  * `# tenant-isolation-allow:` markers on every queryset, 5-part
    hyphenated reasons.
  * NEVER log PII (balance, names, emails).
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, F, Q, Sum
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View


logger = logging.getLogger(__name__)


_ROLLING_WINDOW_DAYS = 30
_TOP_TENANTS_LIMIT = 10
_SUPPORTED_LOCALES = ("en", "fr", "es", "pt", "ar")


@method_decorator(staff_member_required, name="dispatch")
class MealPlanAnalyticsView(View):
    """Operator dashboard: low-balance notification trends platform-wide.

    Renders four panels:
      1. Last 30 days rolling count of low-balance events per tenant
      2. Top 10 tenants by notification volume
      3. Notification cooldown effectiveness
         (notifications sent / total transitions)
      4. Per-locale breakdown (en/fr/es/pt/ar)
    """

    template_name = "schoolops/operator/meal_plan_analytics.html"

    def get(self, request, *args, **kwargs):  # noqa: ARG002
        ctx = _build_analytics_context()
        return render(request, self.template_name, ctx)


def _build_analytics_context() -> dict[str, Any]:
    """Assemble the operator-dashboard context dict.

    Defensive: every aggregation tolerates the analytics-time DB being
    empty (e.g. fresh test fixture) and returns zeros rather than crashing.
    """
    from apps.schoolops.models import MealPlanBalance

    now = timezone.now()
    window_start = now - _dt.timedelta(days=_ROLLING_WINDOW_DAYS)

    # Panel 1 + 2: per-tenant counts in the 30-day window.
    #
    # tenant-isolation-allow: operator-analytics-dashboard-cross-tenant-by-design-staff-only-view
    qs_window = MealPlanBalance.objects.filter(
        last_low_balance_notification_sent_at__gte=window_start,
    )
    per_tenant_window = list(
        qs_window.values("school_id", "school__name")
        .annotate(count=Count("pk"))
        .order_by("-count")
    )
    top_tenants = per_tenant_window[:_TOP_TENANTS_LIMIT]

    # Panel 3: cooldown effectiveness.
    # total notifications = sum of low_balance_notification_count
    # total transitions (proxy) = number of rows currently low or that
    # have ever been notified, since the model doesn't keep a discrete
    # transition log. notifications/transitions <= 1.0 means the cooldown
    # is working (sends are below raw transition rate).
    # tenant-isolation-allow: operator-analytics-dashboard-cross-tenant-by-design-staff-only-view
    total_notifs_row = MealPlanBalance.objects.aggregate(
        total=Sum("low_balance_notification_count"),
    )
    total_notifs = int(total_notifs_row.get("total") or 0)
    # tenant-isolation-allow: operator-analytics-dashboard-cross-tenant-by-design-staff-only-view
    total_transitions = MealPlanBalance.objects.filter(
        Q(low_balance_notification_count__gt=0)
        | Q(balance__lte=F("low_balance_threshold")),
    ).count()
    if total_transitions:
        # Float ratio is acceptable here — this is display precision for
        # a percent metric, not a money path.
        ratio = float(total_notifs) / float(total_transitions)  # money-float-allow: ratio-not-money
    else:
        ratio = 0.0
    cooldown_pct = round(ratio * 100.0, 1)

    # Panel 4: per-locale breakdown.
    # Join MealPlanBalance -> student -> guardian_links -> guardian_user
    # -> preferred_language. We materialize rows then bucket by
    # _normalize_locale() so unknown values still fall into 'en'.
    locale_buckets: dict[str, int] = {k: 0 for k in _SUPPORTED_LOCALES}
    try:
        # tenant-isolation-allow: operator-analytics-dashboard-cross-tenant-by-design-staff-only-view
        rows = MealPlanBalance.objects.filter(
            low_balance_notification_count__gt=0,
        ).values_list(
            "low_balance_notification_count",
            "student__guardian_links__guardian_user__preferred_language",
        )
        for count, pref in rows:
            base = (pref or "en").lower().split("-", 1)[0].split("_", 1)[0]
            if base not in locale_buckets:
                base = "en"
            locale_buckets[base] += int(count or 0)
    except Exception:  # noqa: BLE001
        logger.exception("schoolops.meal_plan_analytics_locale_join_failed")
    locale_breakdown = [
        {"locale": code, "count": locale_buckets[code]}
        for code in _SUPPORTED_LOCALES
    ]

    return {
        "page_title": "Meal plan low-balance analytics",
        "window_days": _ROLLING_WINDOW_DAYS,
        "window_start": window_start,
        "now": now,
        "per_tenant_window": per_tenant_window,
        "top_tenants": top_tenants,
        "total_notifs": total_notifs,
        "total_transitions": total_transitions,
        "cooldown_pct": cooldown_pct,
        "locale_breakdown": locale_breakdown,
    }
