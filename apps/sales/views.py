from __future__ import annotations

import re
from datetime import datetime, timedelta

from django.db.models import Count, OuterRef, Q, Subquery
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.models import User
from apps.sales.models import ActivityLog, Lead, PipelineStage
from apps.schools.control_plane import require_control_plane_access

_LEAD_TAG = re.compile(r"\[([a-z_]+):([^\]]*)\]", re.I)


def _parse_lead_tags(notes: str) -> dict[str, str]:
    return {k.lower(): v.strip() for k, v in _LEAD_TAG.findall(notes or "")}


@require_control_plane_access
def pipeline_board(request: HttpRequest) -> HttpResponse:
    stages = list(PipelineStage.objects.all().order_by("sort_order", "pk"))
    latest_activity = Subquery(
        ActivityLog.objects.filter(lead_id=OuterRef("pk"))
        .order_by("-created_at")
        .values("created_at")[:1]
    )
    leads = (
        Lead.objects.select_related("stage", "created_by")
        .annotate(last_contact_at=latest_activity)
        .order_by("-updated_at", "-pk")[:500]
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        leads = (
            Lead.objects.filter(
                Q(school_name__icontains=q)
                | Q(contact_name__icontains=q)
                | Q(email__icontains=q)
                | Q(decision_maker__icontains=q)
            )
            .select_related("stage", "created_by")
            .annotate(last_contact_at=latest_activity)
            .order_by("-updated_at", "-pk")[:200]
        )
    stage_buckets = {stage.pk: [] for stage in stages}
    now = timezone.now()
    overdue_followups = 0
    due_today_followups = 0
    upcoming_window_end = now + timedelta(days=7)
    upcoming_followups = list(
        Lead.objects.select_related("stage")
        .filter(
            next_follow_up__gt=now,
            next_follow_up__lte=upcoming_window_end,
        )
        .order_by("next_follow_up")[:25]
    )
    for lead in leads:
        bucket = stage_buckets.get(lead.stage_id)
        if bucket is not None:
            bucket.append(lead)
        if lead.next_follow_up:
            if lead.next_follow_up < now:
                overdue_followups += 1
            elif lead.next_follow_up.date() == now.date():
                due_today_followups += 1
    stage_stats_rows = (
        Lead.objects.values("stage__key", "stage__label")
        .annotate(total=Count("id"))
        .order_by("stage__key")
    )
    stage_stats = {row["stage__key"]: row["total"] for row in stage_stats_rows}
    total_leads = sum(stage_stats.values())
    demos_scheduled = stage_stats.get("demo_scheduled", 0) + stage_stats.get("demo", 0)
    demos_completed = stage_stats.get("demo_done", 0) + stage_stats.get("pilot", 0)
    decisions = stage_stats.get("decision", 0)
    closed = stage_stats.get("closed", 0) + stage_stats.get("onboarded", 0)
    conversion_rate = round((closed / total_leads) * 100, 1) if total_leads else 0.0
    kanban_columns = [
        {"stage": stage, "leads": stage_buckets.get(stage.pk, [])} for stage in stages
    ]
    return render(
        request,
        "sales/pipeline_board.html",
        {
            "stages": stages,
            "leads": leads,
            "kanban_columns": kanban_columns,
            "total_leads": total_leads,
            "demos_scheduled": demos_scheduled,
            "demos_completed": demos_completed,
            "decisions": decisions,
            "closed": closed,
            "conversion_rate": conversion_rate,
            "overdue_followups": overdue_followups,
            "due_today_followups": due_today_followups,
            "upcoming_followups": upcoming_followups,
            "now": now,
            "query": q,
        },
    )


@require_control_plane_access
@require_http_methods(["GET", "POST"])
def lead_create(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return HttpResponseForbidden("login required")
    if request.method == "POST":
        name = (request.POST.get("school_name") or "").strip()
        if not name:
            staff_owners = list(
                User.objects.filter(is_staff=True).order_by("username", "pk")[:200]
            )
            return render(
                request,
                "sales/lead_create.html",
                {
                    "error": "School name is required",
                    "school_name": name,
                    "staff_owners": staff_owners,
                },
            )
        stage = PipelineStage.objects.filter(key="lead").first() or (
            PipelineStage.objects.order_by("sort_order", "pk").first()
        )
        if not stage:
            return HttpResponse(
                "Pipeline stages missing — run migrations.",
                status=500,
            )
        deal_owner_id = (request.POST.get("deal_owner_id") or "").strip()
        deal_owner = None
        if deal_owner_id.isdigit():
            deal_owner = User.objects.filter(
                pk=int(deal_owner_id), is_staff=True
            ).first()
        Lead.objects.create(
            school_name=name,
            contact_name=(request.POST.get("contact_name") or "").strip()[:200],
            email=(request.POST.get("email") or "").strip()[:200],
            phone=(request.POST.get("phone") or "").strip()[:64],
            decision_maker=(request.POST.get("decision_maker") or "").strip()[:200],
            deal_owner=deal_owner,
            stage=stage,
            created_by=request.user,
        )
        return redirect("sales:pipeline_board")
    staff_owners = list(
        User.objects.filter(is_staff=True).order_by("username", "pk")[:200]
    )
    return render(request, "sales/lead_create.html", {"staff_owners": staff_owners})


@require_control_plane_access
@require_http_methods(["GET", "POST"])
def lead_detail(request: HttpRequest, pk: int) -> HttpResponse:
    if not request.user.is_authenticated:
        return HttpResponseForbidden("login required")
    lead = get_object_or_404(
        Lead.objects.select_related("stage", "deal_owner"), pk=pk
    )
    if request.method == "POST":
        quick_followup_days = (request.POST.get("quick_followup_days") or "").strip()
        if quick_followup_days:
            try:
                days = max(1, min(int(quick_followup_days), 30))
            except (TypeError, ValueError):
                days = 2
            lead.next_follow_up = timezone.now() + timedelta(days=days)
            lead.save(update_fields=["next_follow_up", "updated_at"])
            ActivityLog.objects.create(
                lead=lead,
                body=f"Auto reminder set: follow up in {days} day(s).",
                created_by=request.user,
            )
            return redirect("sales:lead_detail", pk=lead.pk)
        if (request.POST.get("add_activity") or "").strip() == "1":
            body = (request.POST.get("body") or "").strip()
            if body:
                ActivityLog.objects.create(
                    lead=lead, body=body[:10000], created_by=request.user
                )
            return redirect("sales:lead_detail", pk=lead.pk)
        if (request.POST.get("save_lead") or "").strip() != "1":
            return redirect("sales:lead_detail", pk=lead.pk)
        if request.POST.get("stage_id"):
            try:
                st = get_object_or_404(PipelineStage, pk=int(request.POST["stage_id"]))
                lead.stage = st
            except (TypeError, ValueError):
                pass
        nfu = (request.POST.get("next_follow_up") or "").strip()
        if nfu:
            from django.utils.dateparse import parse_date, parse_datetime

            try:
                parsed = parse_datetime(nfu)
                if parsed is None and len(nfu) == 10:
                    d0 = parse_date(nfu)
                    if d0 is not None:
                        parsed = datetime.combine(d0, datetime.min.time())
                if parsed is not None and timezone.is_naive(parsed):
                    parsed = timezone.make_aware(
                        parsed, timezone.get_current_timezone()
                    )
                if parsed is not None:
                    lead.next_follow_up = parsed
            except (ValueError, TypeError, OverflowError):
                pass
        if request.POST.get("notes") is not None:
            lead.notes = (request.POST.get("notes") or "")[:5000]
        lead.decision_maker = (request.POST.get("decision_maker") or "").strip()[:200]
        deal_owner_id = (request.POST.get("deal_owner_id") or "").strip()
        if deal_owner_id.isdigit():
            lead.deal_owner = User.objects.filter(
                pk=int(deal_owner_id), is_staff=True
            ).first()
        else:
            lead.deal_owner = None
        lead.save()
        return redirect("sales:lead_detail", pk=lead.pk)
    activities = list(lead.activity_logs.all()[:200])
    stages = list(PipelineStage.objects.all().order_by("sort_order", "pk"))
    staff_owners = list(
        User.objects.filter(is_staff=True).order_by("username", "pk")[:200]
    )
    return render(
        request,
        "sales/lead_detail.html",
        {
            "lead": lead,
            "activities": activities,
            "stages": stages,
            "staff_owners": staff_owners,
        },
    )


@require_control_plane_access
@require_POST
def update_stage(request: HttpRequest, pk: int) -> HttpResponse:
    if not request.user.is_authenticated:
        return HttpResponseForbidden("login required")
    lead = get_object_or_404(Lead, pk=pk)
    st = get_object_or_404(PipelineStage, pk=int(request.POST.get("stage_id") or 0))
    lead.stage = st
    lead.save()
    nxt = request.GET.get("next")
    if nxt in ("", "list"):
        return redirect("sales:pipeline_board")
    return redirect("sales:lead_detail", pk=lead.pk)


@require_control_plane_access
def first_100_schools_dashboard(request: HttpRequest) -> HttpResponse:
    from apps.platform_runtime.pilot_evidence import build_pilot_dashboard_rows, load_raw_scorecard

    stages = list(PipelineStage.objects.all().order_by("sort_order", "pk"))
    leads = list(
        Lead.objects.select_related("stage", "deal_owner")
        .order_by("-updated_at", "-pk")[:100]
    )
    pilot_rows = []
    scorecard_ok = True
    try:
        scorecard = load_raw_scorecard()
        pilot_rows = build_pilot_dashboard_rows(scorecard)
    except (OSError, ValueError, KeyError):
        scorecard_ok = False
    rows = []
    for lead in leads:
        tags = _parse_lead_tags(lead.notes)
        pilot_flag = tags.get("pilot", "").lower() in ("1", "true", "yes", "y")
        stage_key = (lead.stage.key or "").lower()
        pilot_candidate = pilot_flag or stage_key in ("pilot", "demo_done", "demo")
        readiness = min(
            100, (lead.stage.sort_order + 1) * 12 + (15 if pilot_candidate else 0)
        )
        rows.append(
            {
                "lead": lead,
                "region": tags.get("region") or "",
                "school_type": tags.get("type") or "",
                "readiness_score": readiness,
                "recommended_package": tags.get("package") or "",
                "pilot_candidate": pilot_candidate,
                "external_blockers": tags.get("blocker") or "",
                "pain_point": tags.get("pain") or "",
            }
        )
    return render(
        request,
        "sales/first_100_dashboard.html",
        {
            "stages": stages,
            "rows": rows,
            "pilot_rows": pilot_rows,
            "scorecard_ok": scorecard_ok,
        },
    )
