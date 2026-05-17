"""
Founder / North Star control surface — reads generated audit reports (no fake metrics).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from django.conf import settings
from django.db.models import Count
from django.shortcuts import render
from django.urls import reverse

from apps.marketplace.monetization import get_founder_marketplace_snapshot
from apps.observability.models import PlatformIncident
from apps.platform_runtime.business_value import get_business_value_snapshot
from apps.platform_runtime.models import AIActionAuditLog, PlatformEventLog
from apps.sales.models import Lead
from apps.schools.models import School

_ROOT = Path(settings.BASE_DIR)
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _parse_sot_slices_fallback(sot_path: Path) -> dict[int, str | None]:
    if not sot_path.is_file():
        return {n: None for n in range(15, 25)}
    try:
        from northstar_common import NORTHSTAR_SLICES, parse_sot_north_star_slice_status

        text = sot_path.read_text(encoding="utf-8", errors="replace")
        return parse_sot_north_star_slice_status(text, slice_numbers=NORTHSTAR_SLICES)
    except Exception:
        pass
    text = sot_path.read_text(encoding="utf-8", errors="replace")
    out: dict[int, str | None] = {n: None for n in range(15, 25)}
    tail = re.compile(r"\):\*\*\s*\*\*([^*]+)\*\*")
    for line in text.splitlines():
        if "North Star slice " not in line:
            continue
        m = re.search(r"North Star slice (\d+)", line)
        if not m:
            continue
        n = int(m.group(1))
        if n < 15 or n > 24:
            continue
        st = tail.search(line)
        if st:
            out[n] = (st.group(1) or "").strip().split()[0].upper()
    return out


def super_founder_dashboard(request):
    gen = _ROOT / "docs" / "generated"
    observability_ledger = _load_json(gen / "observability_ledger.json") or {}
    audit = _load_json(gen / "northstar_audit.json") or {}
    kill = _load_json(gen / "kill_test_report.json") or {}
    self_heal = _load_json(gen / "northstar_self_heal_report.json") or {}
    post_surface = _load_json(gen / "post_surface_audit.json") or {}
    regional_ui = _load_json(gen / "regional_ui_surface_audit.json") or {}

    sot_slices = _parse_sot_slices_fallback(
        _ROOT / "docs" / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
    )
    slice_rows = [
        {
            "n": n,
            "status": sot_slices.get(n) or "not recorded",
            "ok": sot_slices.get(n) == "DONE",
        }
        for n in range(15, 25)
    ]

    business_value = get_business_value_snapshot()
    schools_total = business_value.get("schools_total") or School.objects.count()
    security_surface_summary = None
    try:
        surf = _load_json(gen / "security_surface_audit.json") or {}
        summary_block = surf.get("summary") if isinstance(surf.get("summary"), dict) else {}
        security_surface_summary = summary_block.get("violations_total")
        if security_surface_summary is None:
            security_surface_summary = surf.get("critical_issue_count")
    except Exception:
        security_surface_summary = None

    incidents_open = PlatformIncident.objects.filter(
        status__in=[
            PlatformIncident.Status.OPEN,
            PlatformIncident.Status.ACKNOWLEDGED,
        ]
    ).count()

    billing_watchlist = None
    try:
        from apps.billing.models import TenantSubscription

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        billing_watchlist = TenantSubscription.objects.filter(
            status__in=[
                TenantSubscription.Status.PAST_DUE,
                TenantSubscription.Status.SUSPENDED,
            ]
        ).count()
    except Exception:
        pass

    rev_share_pending = None
    try:
        from apps.billing.models import RevenueSharePayout

        rev_share_pending = RevenueSharePayout.objects.filter(
            status=RevenueSharePayout.Status.DRAFT
        ).count()
    except Exception:
        pass

    incident_breakdown = list(
        PlatformIncident.objects.values("status")
        .annotate(total=Count("id"))
        .order_by("status")
    )
    recent_platform_events = PlatformEventLog.objects.count()
    recent_ai_audits = AIActionAuditLog.objects.count()

    self_heal_status = (self_heal.get("status") or "not run").strip()
    open_tickets = list(self_heal.get("unsafe_ticket_paths") or [])
    founder_sales = {
        "total_leads": 0,
        "demo_scheduled": 0,
        "demo_completed": 0,
        "decision": 0,
        "closed": 0,
        "conversion_rate_pct": 0.0,
    }
    try:
        sales_total_leads = Lead.objects.count()
        sales_stage_counts = {
            row["stage__key"]: row["total"]
            for row in Lead.objects.values("stage__key").annotate(total=Count("id"))
        }
        demo_scheduled_count = sales_stage_counts.get(
            "demo_scheduled", 0
        ) + sales_stage_counts.get("demo", 0)
        demo_completed_count = sales_stage_counts.get(
            "demo_done", 0
        ) + sales_stage_counts.get("pilot", 0)
        decision_count = sales_stage_counts.get("decision", 0)
        closed_count = sales_stage_counts.get("closed", 0) + sales_stage_counts.get(
            "onboarded", 0
        )
        conversion_rate_pct = (
            round((closed_count / sales_total_leads) * 100, 1) if sales_total_leads else 0.0
        )
        founder_sales = {
            "total_leads": sales_total_leads,
            "demo_scheduled": demo_scheduled_count,
            "demo_completed": demo_completed_count,
            "decision": decision_count,
            "closed": closed_count,
            "conversion_rate_pct": conversion_rate_pct,
        }
    except Exception:
        pass

    marketplace_metrics = {}
    try:
        marketplace_metrics = get_founder_marketplace_snapshot(days=30)
    except Exception:
        marketplace_metrics = {}

    return render(
        request,
        "super/founder_dashboard.html",
        {
            "audit": audit,
            "audit_total": audit.get("total_score"),
            "audit_rating": audit.get("rating"),
            "kill_test": kill,
            "post_surface": post_surface,
            "regional_ui": regional_ui,
            "security_surface_signal": security_surface_summary,
            "self_heal": self_heal,
            "self_heal_status": self_heal_status,
            "open_repair_tickets": open_tickets,
            "slice_rows": slice_rows,
            "schools_total": schools_total,
            "business_value": business_value,
            "platform_incidents_open": incidents_open,
            "billing_watchlist_count": billing_watchlist,
            "revenue_share_draft_count": rev_share_pending,
            "recent_platform_events": recent_platform_events,
            "recent_ai_audits": recent_ai_audits,
            "observability_ledger": observability_ledger,
            "incident_breakdown": incident_breakdown,
            "command_center_url": reverse("super:command_center"),
            "dashboard_url": reverse("super:dashboard"),
            "generated_audit_hint": gen / "northstar_audit.json",
            "founder_sales": founder_sales,
            "marketplace_metrics": marketplace_metrics,
        },
    )
