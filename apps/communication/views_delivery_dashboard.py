"""Operator delivery-receipt dashboard (audit residual closeout).

Single staff-only HTML surface aggregating SMS / WhatsApp / push delivery
receipts (:class:`apps.communication.models_delivery_receipt.MessageDeliveryReceipt`)
so an operator can see what actually reached recipients — the cross-channel
analogue of the email-health dashboard.

Panels: 24h/7d totals, a channel × status matrix (7d), and the most recent
terminal failures (failed / undelivered) with their provider error codes.

Permission: ``staff_member_required``. The view NEVER renders raw recipients —
only the hashed ``recipient_hash`` the webhook stored. Cross-tenant
aggregation is intentional (operator incident response) and each query carries
an explicit tenant-isolation-allow marker.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import timedelta
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)

_RECENT_FAILURE_LIMIT = 25


@method_decorator(staff_member_required, name="dispatch")
class MessageDeliveryDashboardView(View):
    """GET-only staff dashboard for SMS/WhatsApp/push delivery receipts."""

    http_method_names = ["get"]

    def get(self, request, *args: Any, **kwargs: Any):
        context = {
            "page_title": "Message delivery receipts",
            "totals": {"last_24h": 0, "last_7d": 0, "terminal_7d": 0, "failed_7d": 0},
            "matrix": [],
            "recent_failures": [],
            "load_error": False,
        }
        try:
            from apps.communication.models_delivery_receipt import (
                MessageDeliveryReceipt,
            )

            now = timezone.now()
            since_24h = now - timedelta(hours=24)
            since_7d = now - timedelta(days=7)

            # tenant-isolation-allow: platform-wide-delivery-receipt-health-aggregation
            qs7 = MessageDeliveryReceipt.objects.filter(updated_at__gte=since_7d)
            context["totals"]["last_7d"] = qs7.count()
            # tenant-isolation-allow: platform-wide-delivery-receipt-health-aggregation
            context["totals"]["last_24h"] = MessageDeliveryReceipt.objects.filter(
                updated_at__gte=since_24h
            ).count()
            context["totals"]["terminal_7d"] = qs7.filter(terminal=True).count()
            context["totals"]["failed_7d"] = qs7.filter(
                status__in=("failed", "undelivered", "rejected")
            ).count()

            # Channel × status matrix (7d).
            matrix: Counter[tuple[str, str]] = Counter()
            # tenant-isolation-allow: platform-wide-delivery-receipt-health-aggregation
            for channel, status in qs7.values_list("channel", "status"):
                matrix[(channel or "?", status or "?")] += 1
            context["matrix"] = sorted(
                (
                    {"channel": ch, "status": st, "count": n}
                    for (ch, st), n in matrix.items()
                ),
                key=lambda r: (r["channel"], -r["count"]),
            )

            # Recent terminal failures.
            # tenant-isolation-allow: platform-wide-delivery-receipt-health-aggregation
            fails = (
                MessageDeliveryReceipt.objects.filter(
                    status__in=("failed", "undelivered", "rejected")
                )
                .order_by("-updated_at")[:_RECENT_FAILURE_LIMIT]
            )
            context["recent_failures"] = [
                {
                    "channel": r.channel,
                    "provider": r.provider,
                    "status": r.status,
                    "error_code": r.error_code or "—",
                    "recipient_hash": r.recipient_hash or "—",
                    "provider_message_id": (r.provider_message_id or "")[:24],
                    "updated_at": r.updated_at,
                }
                for r in fails
            ]
        except Exception as exc:  # noqa: BLE001 — dashboard never 500s
            logger.warning(
                "communication.delivery_dashboard.load_failed err_type=%s",
                type(exc).__name__,
            )
            context["load_error"] = True

        return render(
            request, "communication/super/delivery_receipts.html", context,
        )


__all__ = ["MessageDeliveryDashboardView"]
