from __future__ import annotations

import re
from datetime import datetime, timedelta

from django.db.models import Count, OuterRef, Q, Subquery
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.models import User
from apps.sales.models import ActivityLog, Lead, PipelineStage
from apps.schools.control_plane import require_control_plane_access

_LEAD_TAG = re.compile(r"\[([a-z_]+):([^\]]*)\]", re.I)

# Lead.email is an EmailField(max_length=254); the create form used to truncate
# at 200, which silently mangled a long-but-legal address into an invalid one.
_LEAD_EMAIL_MAX_LENGTH = 254  # magic-number-allow: mirrors Lead.email max_length


def _clean_lead_email(raw) -> tuple[str, str]:
    """Return ``(email, error)``. Empty input is allowed; garbage is not.

    Returning the error instead of raising keeps both the create form and the
    edit form able to re-render with the operator's typing intact.
    """
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    email = (raw or "").strip()
    if not email:
        return "", ""
    if len(email) > _LEAD_EMAIL_MAX_LENGTH:
        return email, "Email address is too long."
    try:
        validate_email(email)
    except ValidationError:
        return email, "Enter a valid email address."
    return email, ""


# How many staff accounts the deal-owner picker offers. Named, not inlined, so the
# truncation is visible to the code that has to compensate for it.
_OWNER_PICKER_LIMIT = 200  # magic-number-allow: deal-owner picker page size


def _parse_lead_tags(notes: str) -> dict[str, str]:
    return {k.lower(): v.strip() for k, v in _LEAD_TAG.findall(notes or "")}


def _owner_picker(lead) -> list:
    """Staff accounts the deal-owner select offers, current owner included.

    The list is truncated, so the CURRENT owner may not be in it. Append rather
    than widen the query: the cap exists to keep the page fast. An owner with no
    option cannot be marked selected, so the browser posts the blank one.
    """
    owners = list(
        User.objects.filter(is_staff=True).order_by("username", "pk")[
            :_OWNER_PICKER_LIMIT
        ]
    )
    if lead.deal_owner_id and not any(u.pk == lead.deal_owner_id for u in owners):
        if lead.deal_owner is not None:
            owners.append(lead.deal_owner)
    return owners


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
    # The follow-up banner sits directly under the KPI row, and the KPI row is
    # pipeline-wide. Counting these by walking the DISPLAY slice made them agree
    # with the search box and with the 500-row cap instead: typing one school
    # into the filter silently rewrote "N overdue" into that school's number,
    # which reads as "nothing is overdue across the pipeline". Count the table.
    overdue_followups = Lead.objects.filter(next_follow_up__lt=now).count()
    # "Due today" is the remainder of the current day, matching the old
    # `next_follow_up.date() == now.date()` test on the same UTC instant, but
    # expressed as a half-open range so it is index-usable and does not depend
    # on the backend's date-cast timezone.
    day_end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    due_today_followups = Lead.objects.filter(
        next_follow_up__gte=now, next_follow_up__lt=day_end
    ).count()
    stage_stats_rows = (
        Lead.objects.values("stage__key", "stage__label")
        .annotate(total=Count("id"))
        .order_by("stage__key")
    )
    stage_stats = {row["stage__key"]: row["total"] for row in stage_stats_rows}
    total_leads = sum(stage_stats.values())
    # Funnel tiles are CUMULATIVE -- a school that reached Decision has had its
    # demo. They used to be keyed on stage keys ("demo_scheduled", "demo_done",
    # "closed") that no migration seeds, so those terms were a permanent 0 and
    # each tile degraded to current stage OCCUPANCY: ten onboarded schools and
    # none in Pilot rendered "Demos completed: 0" beside "Closed: 10". Count by
    # sort_order instead, which is the ordering the board itself renders.
    stage_order_by_key = {stage.key: stage.sort_order for stage in stages}

    def _reached(stage_key: str) -> int:
        floor = stage_order_by_key.get(stage_key)
        if floor is None:
            return 0
        return sum(
            total
            for key, total in stage_stats.items()
            if stage_order_by_key.get(key, -1) >= floor
        )

    demos_scheduled = _reached("demo")
    demos_completed = _reached("pilot")
    decisions = _reached("decision")
    closed = _reached("onboarded")
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
        email, email_error = _clean_lead_email(request.POST.get("email"))
        error = "School name is required" if not name else email_error
        if error:
            staff_owners = list(
                User.objects.filter(is_staff=True).order_by("username", "pk")[:200]
            )
            return render(
                request,
                "sales/lead_create.html",
                {
                    "error": error,
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
            email=email,
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
        # contact_name / email / phone were writable at creation and nowhere
        # else, so a mistyped prospect address stayed wrong on every sales
        # surface. Each is keyed on PRESENCE in the POST so a partial form
        # cannot blank a field it never carried.
        if "contact_name" in request.POST:
            lead.contact_name = (request.POST.get("contact_name") or "").strip()[:200]
        if "phone" in request.POST:
            lead.phone = (request.POST.get("phone") or "").strip()[:64]
        contact_error = ""
        if "email" in request.POST:
            new_email, contact_error = _clean_lead_email(request.POST.get("email"))
            if not contact_error:
                lead.email = new_email
        # Only touch the owner when the form actually CARRIED the field. A missing
        # key used to mean 'unassign', so any save that did not include the select
        # silently dropped the assignment -- which is what happened whenever the
        # current owner fell outside the truncated picker below, because the
        # template can only mark an option selected if the option exists and the
        # browser then posts the blank one. An explicitly blank value still clears,
        # since unassigning deliberately has to keep working.
        if "deal_owner_id" in request.POST:
            deal_owner_id = (request.POST.get("deal_owner_id") or "").strip()
            if not deal_owner_id:
                # The blank first option -- an explicit, deliberate unassign.
                lead.deal_owner = None
            elif deal_owner_id.isdigit() and int(deal_owner_id) == lead.deal_owner_id:
                # Re-posting the owner the picker rendered means "leave it alone",
                # and it must NOT be re-validated against is_staff. The picker
                # offers the current owner unconditionally (see below), so an
                # owner assigned through LeadAdmin -- which applies no
                # limit_choices_to -- or one who has since lost is_staff comes
                # back on every save; resolving that id through an is_staff
                # filter returned None and wiped them on an unrelated edit.
                pass
            else:
                resolved = (
                    User.objects.filter(pk=int(deal_owner_id), is_staff=True).first()
                    if deal_owner_id.isdigit()
                    else None
                )
                if resolved is not None:
                    lead.deal_owner = resolved
                # An id that resolves to nobody is a stale or tampered option,
                # not an unassign request: keep the existing owner rather than
                # silently dropping one on a value the operator never chose.
        lead.save()
        if contact_error:
            return render(
                request,
                "sales/lead_detail.html",
                {
                    "lead": lead,
                    "activities": list(lead.activity_logs.all()[:200]),
                    "stages": list(
                        PipelineStage.objects.all().order_by("sort_order", "pk")
                    ),
                    "staff_owners": _owner_picker(lead),
                    "error": contact_error,
                    "email_value": (request.POST.get("email") or "").strip(),
                },
                status=400,
            )
        return redirect("sales:lead_detail", pk=lead.pk)
    activities = list(lead.activity_logs.all()[:200])
    stages = list(PipelineStage.objects.all().order_by("sort_order", "pk"))
    staff_owners = _owner_picker(lead)
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
    raw_stage_id = (request.POST.get("stage_id") or "").strip()
    if not raw_stage_id.isdigit():
        # A non-numeric stage_id is a malformed request, not a server fault:
        # the bare int() here raised ValueError straight out of the view.
        return HttpResponseBadRequest("stage_id must be an integer")
    st = get_object_or_404(PipelineStage, pk=int(raw_stage_id))
    lead.stage = st
    lead.save()
    ActivityLog.objects.create(
        lead=lead,
        body=f"Stage moved to {st.label}.",
        created_by=request.user,
    )
    # An ABSENT ``next`` is None, not "", so the old membership test sent the
    # board's own quick-move button to the lead page instead of back to the
    # board. Default to the board and treat "detail" as the opt-out.
    nxt = (request.GET.get("next") or "").strip().lower()
    if nxt == "detail":
        return redirect("sales:lead_detail", pk=lead.pk)
    return redirect("sales:pipeline_board")


@require_control_plane_access
def first_100_schools_dashboard(request: HttpRequest) -> HttpResponse:
    from apps.platform_runtime.pilot_evidence import build_pilot_dashboard_rows, load_raw_scorecard

    stages = list(PipelineStage.objects.all().order_by("sort_order", "pk"))
    leads = list(
        Lead.objects.select_related("stage", "deal_owner")
        .order_by("-updated_at", "-pk")[:100]
    )
    # build_pilot_dashboard_rows returns a DICT (schema_ok / schema_issues /
    # pilots / ...), not rows -- the old ``pilot_rows`` name and its [] default
    # said otherwise, and the template rendered neither, so the redaction pass
    # in platform_runtime.pilot_evidence ran on every request against data no
    # human ever saw. The template now iterates ``pilot_evidence.pilots``.
    pilot_evidence: dict = {}
    scorecard_ok = True
    try:
        scorecard = load_raw_scorecard()
        pilot_evidence = build_pilot_dashboard_rows(scorecard)
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
            "pilot_evidence": pilot_evidence,
            "scorecard_ok": scorecard_ok,
        },
    )
