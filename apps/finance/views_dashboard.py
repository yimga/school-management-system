"""
Finance dashboard view (§6.15 app-by-app split — subdomain: dashboard).
"""

from __future__ import annotations

import json

from django.conf import settings
from apps.accounts.decorators import tenant_admin_required
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse

from apps.accounts.utils import get_dashboard_context
from .models import Invoice, Notification
from .views_common import _active_profile
from .services import finance_dashboard_data


@tenant_admin_required
def dashboard(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    dashboard_data = finance_dashboard_data(profile)
    summary = dashboard_data.get("summary", {})
    hero = {
        "tagline": "Finance Dashboard",
        "title": profile.name,
        "subtitle": "Receivables, collections, and alerts",
        "icon": "bi-cash-coin",
        "stats": [
            {
                "label": "Receivables",
                "value": summary.get("receivables"),
                "meta": "Outstanding AR",
            },
            {
                "label": "Collected",
                "value": summary.get("paid"),
                "meta": "YTD payments",
            },
            {
                "label": "Overdue",
                "value": summary.get("overdue"),
                "meta": "Invoices late",
            },
        ],
        "actions": [
            {
                "label": "Overdue list",
                "url": reverse("finance:invoices") + "?status=OVERDUE",
            },
            {"label": "Generate fees", "url": reverse("finance:generate_fees")},
            {"label": "All invoices", "url": reverse("finance:invoices")},
            {
                "label": "Payment setup",
                "url": reverse("finance:payment_readiness_setup"),
            },
            {
                "label": "Payment readiness (tenant)",
                "url": reverse("finance:payment_readiness_dashboard"),
            },
        ],
    }
    dashboard_context = get_dashboard_context(request.user, "finance", request=request)
    dashboard_settings = dashboard_context.get("dashboard_settings", {})
    allow_custom_layout = dashboard_context.get("allow_custom_layout", False)
    dashboard_layout_url = dashboard_context.get("dashboard_layout_url", "")
    widget_meta_json = dashboard_context.get("widget_meta_json", "")
    available_sidebar_items = [
        {
            "id": "finance-home",
            "label": "Finance Home",
            "url": reverse("finance:dashboard"),
            "icon": "bi-cash-stack",
        },
        {
            "id": "finance-invoices",
            "label": "Invoices",
            "url": reverse("finance:invoices"),
            "icon": "bi-receipt",
        },
        {
            "id": "finance-payments",
            "label": "Payments",
            "url": reverse("finance:payments"),
            "icon": "bi-wallet2",
        },
        {
            "id": "finance-suspense",
            "label": "Suspense Queue",
            "url": reverse("finance:suspense_queue"),
            "icon": "bi-exclamation-triangle",
        },
        {
            "id": "finance-trial",
            "label": "Trial Balance",
            "url": reverse("finance:trial_balance"),
            "icon": "bi-bank",
        },
        {
            "id": "finance-reports",
            "label": "Reports",
            "url": reverse("finance:reports"),
            "icon": "bi-graph-up-arrow",
        },
        {
            "id": "finance-payment-setup",
            "label": "Payment setup",
            "url": reverse("finance:payment_readiness_setup"),
            "icon": "bi-geo-alt",
        },
        {
            "id": "finance-payment-readiness",
            "label": "Payment readiness",
            "url": reverse("finance:payment_readiness_dashboard"),
            "icon": "bi-shield-check",
        },
    ]
    # tenant-isolation-allow: recipient-scoped-current-user-owns-notification
    finance_requests_qs = Notification.objects.filter(
        recipient=request.user,
        title__icontains="finance access request",
        is_read=False,
    ).order_by("-created_at")
    finance_request_link = reverse("requests:dashboard")

    status_counts = list(dashboard_data.get("status_counts") or [])
    trend = dashboard_data.get("trend") or []
    status_labels = dict(Invoice.Status.choices)
    chart_status_donut = {
        "type": "doughnut",
        "data": {
            "labels": [
                status_labels.get(sc["status"], sc["status"]) for sc in status_counts
            ],
            "datasets": [
                {
                    "data": [sc["count"] for sc in status_counts],
                    "backgroundColor": [
                        "#6c757d",
                        "#0d6efd",
                        "#ffc107",
                        "#198754",
                        "#dc3545",
                        "#adb5bd",
                    ][: len(status_counts)],
                }
            ],
        },
    }
    chart_trend_area = {
        "type": "line",
        "data": {
            "labels": [t["label"] for t in trend],
            "datasets": [
                {
                    "label": "Invoice total",
                    "data": [float(t["total"]) for t in trend],  # money-float-allow: display-precision-acceptable (chart.js dataset)
                    "fill": True,
                    "borderColor": "#0d6efd",
                    "backgroundColor": "rgba(13, 110, 253, 0.15)",
                    "tension": 0.3,
                }
            ],
        },
    }

    urgent_queue: list[dict] = []
    for n in finance_requests_qs[:4]:
        urgent_queue.append(
            {
                "title": str(getattr(n, "title", "") or "Finance request"),
                "url": finance_request_link,
                "hint": str(getattr(n, "message", "") or "")[:140],
            }
        )
    overdue_n = summary.get("overdue") or 0
    if overdue_n and not urgent_queue:
        urgent_queue.append(
            {
                "title": f"{overdue_n} overdue invoice(s)",
                "url": reverse("finance:invoices") + "?status=OVERDUE",
                "hint": "Collect or follow up on overdue balances.",
            }
        )
    if not urgent_queue:
        urgent_queue.append(
            {
                "title": "No finance inbox items",
                "url": "",
                "hint": "Receivables and payments look quiet.",
            }
        )

    recent_invoices = dashboard_data.get("recent_invoices") or []
    activity_rows: list[dict] = []
    for inv in list(recent_invoices)[:4]:
        try:
            status = inv.get_status_display()  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            status = ""
        ref = getattr(inv, "reference", None) or getattr(inv, "id", "")
        activity_rows.append({"title": str(ref), "meta": str(status)})

    if not activity_rows:
        activity_rows.append(
            {"title": "Finance dashboard", "meta": "Snapshot ready — use next actions."}
        )

    recv = summary.get("receivables")
    finance_metrics = [
        {
            "id": "finance-receivables",
            "label": "Receivables",
            "value": recv,
            "icon": "cash-stack",
        },
        {
            "id": "finance-collected",
            "label": "Collected",
            "value": summary.get("paid"),
            "icon": "wallet2",
            "tone": "success",
        },
        {
            "id": "finance-overdue",
            "label": "Overdue",
            "value": overdue_n,
            "icon": "exclamation-triangle",
            "tone": "warning" if overdue_n else "success",
        },
        {
            "id": "finance-invoices",
            "label": "Recent invoices",
            "value": len(recent_invoices),
            "icon": "receipt",
        },
    ]
    phase7_de = {
        "eyebrow": "Finance home",
        "headline_label": "Outstanding receivables",
        "headline_value": recv,
        "headline_meta": str(profile.name),
        "metrics": list(hero.get("stats") or [])[:4],
        "urgent_queue": urgent_queue,
        "next_actions": list(hero.get("actions") or [])[:3],
        "activity": activity_rows,
    }

    context = {
        "profile": profile,
        "hero": hero,
        "chart_status_donut_json": json.dumps(chart_status_donut),
        "chart_trend_area_json": json.dumps(chart_trend_area),
        "phase7_de": phase7_de,
        "finance_metrics": finance_metrics,
        **dashboard_data,
    }
    from apps.platform_runtime.operational_center_nav import money_center_frame_context

    context.update(
        {
            "allow_custom_layout": allow_custom_layout,
            "dashboard_settings": dashboard_settings,
            "dashboard_layout_url": dashboard_layout_url,
            "available_sidebar_items": available_sidebar_items,
            "widget_meta_json": widget_meta_json,
            "finance_requests_count": finance_requests_qs.count(),
            "finance_request_notifications": finance_requests_qs[:5],
            "finance_request_link": finance_request_link,
            **money_center_frame_context(),
        }
    )
    return render(request, "finance/dashboard.html", context)
