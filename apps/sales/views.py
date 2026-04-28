from __future__ import annotations

from datetime import datetime, timedelta

from django.db.models import Count, OuterRef, Q, Subquery
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.sales.models import ActivityLog, Lead, PipelineStage
from apps.schools.control_plane import require_control_plane_access


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
            return render(
                request,
                "sales/lead_create.html",
                {
                    "error": "School name is required",
                    "school_name": name,
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
        Lead.objects.create(
            school_name=name,
            contact_name=(request.POST.get("contact_name") or "").strip()[:200],
            email=(request.POST.get("email") or "").strip()[:200],
            phone=(request.POST.get("phone") or "").strip()[:64],
            stage=stage,
            created_by=request.user,
        )
        return redirect("sales:pipeline_board")
    return render(request, "sales/lead_create.html", {})


@require_control_plane_access
@require_http_methods(["GET", "POST"])
def lead_detail(request: HttpRequest, pk: int) -> HttpResponse:
    if not request.user.is_authenticated:
        return HttpResponseForbidden("login required")
    lead = get_object_or_404(Lead.objects.select_related("stage"), pk=pk)
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
        lead.save()
        return redirect("sales:lead_detail", pk=lead.pk)
    activities = list(lead.activity_logs.all()[:200])
    stages = list(PipelineStage.objects.all().order_by("sort_order", "pk"))
    return render(
        request,
        "sales/lead_detail.html",
        {
            "lead": lead,
            "activities": activities,
            "stages": stages,
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
