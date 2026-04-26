from __future__ import annotations

from datetime import datetime

from django.db.models import Q
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.sales.models import ActivityLog, Lead, PipelineStage
from apps.schools.control_plane import require_control_plane_access


@require_control_plane_access
def pipeline_board(request: HttpRequest) -> HttpResponse:
    stages = list(PipelineStage.objects.all().order_by("sort_order", "pk"))
    leads = Lead.objects.select_related("stage", "created_by").order_by(
        "-updated_at", "-pk"
    )[:500]
    q = (request.GET.get("q") or "").strip()
    if q:
        leads = (
            Lead.objects.filter(
                Q(school_name__icontains=q)
                | Q(contact_name__icontains=q)
                | Q(email__icontains=q)
            )
            .select_related("stage", "created_by")
            .order_by("-updated_at", "-pk")[:200]
        )
    return render(
        request,
        "sales/pipeline_board.html",
        {
            "stages": stages,
            "leads": leads,
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
