"""
Portal parent-facing views (§6.14 role separation — Phase 2).
Parent-only dashboard, workflow, claim invite, medal case, set active child, workflow center,
child_digital_id, portal_stats, parent_attendance_discipline, parent_child_results,
parent_dashboard, link_child, link_child_wizard.
"""

from __future__ import annotations

import json
from decimal import Decimal
from urllib.parse import quote_plus

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import render, redirect
from django.urls import reverse

from apps.compliance.decorators import audit_pii_view
from django.utils import timezone

from apps.accounts.decorators import parent_portal_required, role_required
from apps.accounts.models import User
from apps.observability.tracing import trace_view
from apps.accounts.utils import get_user_role, get_dashboard_context
from apps.people.models import (
    StudentGuardian,
    Badge,
    StudentProfile,
)
from apps.academics.models import Attendance, Term
from apps.academics.services import get_active_year_and_term
from apps.evals.models import Evaluation
from apps.evals.services import classroom_term_rankings
from apps.finance.models import Payment, PaymentReminder, Notification
from apps.analytics.services import (
    student_improvements,
    specialty_pass_rates,
    subject_weaknesses,
)
from apps.reports.services import (
    are_terms_published,
    is_term_published,
    terms_for_student,
    term_report_context,
)
from apps.portal.parent_portal_helpers import (
    require_parent_child_access,
    set_active_child,
    get_active_child_id,
)
from apps.portal.services import (
    guardian_student_links,
    guardian_students,
    parent_dashboard_widget_data,
    link_guardian_via_invite,
    award_referral_reward,
    parent_onboarding_score,
    class_threads_for_parent,
    class_announcements_for_parent,
)
from django import forms
from apps.portal.forms import (
    ClaimInviteForm,
    AttendanceJustificationForm,
    LinkChildForm,
)
from apps.portal.models import AttendanceJustification
from apps.platform_runtime.helpers import (
    get_effective_support_contact_settings,
    get_site_display_name,
)
from apps.siteconfig.config_service import (
    get_effective_flags,
    get_effective_site_settings,
)
from apps.platform_runtime.structured_logging import log_view_exception
from apps.siteconfig.models_support import filter_portal_items
from apps.portal.tenant_role_home import build_tp_hero_context
from apps.portal.tenant_workflow_portal import build_tenant_workflow_portal
from apps.siteconfig.dashboard_resolver import for_role as dashboard_for_role
from .runtime_helpers import get_policy_for_request
from .views_common import (
    PORTAL_SOFT_FAILURES,
    _qr_png_data_uri,
    _portal_features_status,
)


def _parent_workflow_link(label: str, url_name: str, *args, **kwargs) -> dict | None:
    """Build a workflow link dict; return None if URL fails to resolve."""
    try:
        return {"label": label, "url": reverse(url_name, args=args, kwargs=kwargs)}
    except PORTAL_SOFT_FAILURES:
        return None




@parent_portal_required
@role_required(User.Role.PARENT)
def parent_set_active_child(request: HttpRequest, child_id: int):
    """Phase F optional: set session active child and redirect to parent dashboard. Verifies parent has access."""
    student, err = require_parent_child_access(request, child_id)
    if err:
        return err
    set_active_child(request, child_id)
    return redirect("portal:parent_dashboard")


@parent_portal_required
@role_required(User.Role.PARENT)
def claim_invite(request: HttpRequest, token: str | None = None):
    """
    Claim a pending guardian invite using a token and link the student to the logged-in parent.
    """
    if request.GET.get("dismiss_hint") == "claim_invite":
        request.session["hint_claim_invite_dismissed"] = True
        return redirect(reverse("portal:claim_invite"))
    show_claim_invite_hint = not request.session.get("hint_claim_invite_dismissed")

    initial = {"token": token} if token else None
    form = ClaimInviteForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        invite = form.invite
        student = invite.student

        exists = StudentGuardian.objects.filter(
            guardian_user=request.user,
            student=student,
        ).exists()
        if exists:
            messages.info(request, "You are already linked to this student.")
            return redirect("portal:parent_dashboard")

        guardian, reward = link_guardian_via_invite(
            invite, request.user, awarded_by=request.user
        )
        messages.success(
            request, f"Invite claimed. You are now linked to {guardian.student}."
        )
        messages.info(
            request,
            "What's next: You can view their attendance, grades, and fees on your dashboard.",
        )
        if reward and reward.amount > Decimal("0.00"):
            messages.info(
                request,
                f"Referral bonus of {reward.amount:.2f} will be reviewed by finance.",
            )
        return redirect("portal:parent_dashboard")

    return render(
        request,
        "parent/claim_invite.html",
        {
            "form": form,
            "show_claim_invite_hint": show_claim_invite_hint,
        },
    )


def _guardian_students_for_medal_case(user):
    """Return list of students linked to this guardian (for parent_medal_case)."""
    links = guardian_student_links(user, results_only=False)
    return [link.student for link in links]


@parent_portal_required
def parent_medal_case(request: HttpRequest):
    """Digital medal case: badges earned by each linked student (non-expired)."""
    students = _guardian_students_for_medal_case(request.user)
    student_badges = []
    now = timezone.now()
    for s in students:
        badges = list(
            Badge.objects.filter(student=s)
            .filter(Q(expiry_at__isnull=True) | Q(expiry_at__gt=now))
            .select_related("badge_type")
            .order_by("-issued_at")
        )
        for b in badges:
            cm = (
                b.criteria_met
                if isinstance(getattr(b, "criteria_met", None), dict)
                else {}
            )
            setattr(b, "_evidence_report_term_id", cm.get("report_term_id"))
            setattr(b, "_evidence_syllabus_id", cm.get("syllabus_id"))
        student_badges.append((s, badges))
    return render(
        request,
        "parent/medal_case.html",
        {
            "student_badges": student_badges,
        },
    )


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_workflow_center(request: HttpRequest):
    """
    Parent Workflow Center: steps with progress (what you've done → where you are → what's next).
    RBAC: parent only; data scoped to linked children.
    """
    links = guardian_student_links(request.user, results_only=True)
    finance_links = guardian_student_links(request.user, finance_only=True)
    students = [link.student for link in links]
    finance_students = [link.student for link in finance_links]
    can_view_results = bool(students)
    can_view_finance = bool(finance_students)

    widget_data = parent_dashboard_widget_data(students)
    if can_view_finance:
        fw = parent_dashboard_widget_data(finance_students).get("finance", {})
        widget_data["finance"] = fw or widget_data.get("finance", {})
    else:
        widget_data["finance"] = {
            "total_due": Decimal("0.00"),
            "paid": Decimal("0.00"),
            "balance": Decimal("0.00"),
            "overdue": 0,
        }
    attendance_pct = widget_data.get("attendance", {}).get("overall") or 0
    finance_balance = widget_data.get("finance", {}).get("balance") or Decimal("0.00")
    finance_overdue = widget_data.get("finance", {}).get("overdue", 0)

    flags = get_effective_flags(request)
    require_finance_opt_in = bool(flags.get("require_guardian_finance_opt_in"))
    can_request_finance_access = (
        require_finance_opt_in and links.exists() and not can_view_finance
    )

    def _filter_links(link_list):
        return [lnk for lnk in link_list if lnk is not None and lnk.get("url")]

    finance_step_links = (
        [_parent_workflow_link("Finance", "portal:parent_finance")]
        if can_view_finance
        else (
            [
                _parent_workflow_link(
                    "Request finance access", "finance:finance_request_access"
                )
            ]
            if can_request_finance_access
            else []
        )
    )

    steps = [
        {
            "title": "1) Link your children",
            "subtitle": "Connect your account to your child's profile to see results and finance.",
            "step_key": "link",
            "icon": "bi-link-45deg",
            "done": bool(students),
            "progress_label": f"{links.count()} child(ren) linked"
            if links.exists()
            else "No children linked yet",
            "tip": "Use the link-a-child wizard or claim an invite from the school.",
            "links": _filter_links(
                [
                    _parent_workflow_link("Link a child", "portal:link_child"),
                    _parent_workflow_link("Parent home", "portal:parent_dashboard"),
                ]
            ),
        },
        {
            "title": "2) Results & attendance",
            "subtitle": "View report cards, term results, and attendance.",
            "step_key": "results",
            "icon": "bi-journal-check",
            "done": can_view_results,
            "progress_label": f"{links.count()} profile(s) · Attendance {attendance_pct}%"
            if can_view_results
            else "Link a child first",
            "tip": "Open a child's card on the home page to view results, or go to Portal Stats.",
            "links": _filter_links(
                [
                    _parent_workflow_link(
                        "Parent home (results)", "portal:parent_dashboard"
                    ),
                    _parent_workflow_link("Portal stats", "portal:portal_stats"),
                ]
            ),
        },
        {
            "title": "3) Finance",
            "subtitle": "Invoices, payments, and balance.",
            "step_key": "finance",
            "icon": "bi-cash-stack",
            "done": can_view_finance and finance_balance <= Decimal("0.00"),
            "progress_label": f"Balance: {finance_balance}"
            if can_view_finance
            else "Finance access not granted",
            "tip": "Pay fees and view payment history. Request access if you don't see finance.",
            "links": _filter_links(finance_step_links),
        },
        {
            "title": "4) Communication",
            "subtitle": "Contact the school and stay in touch.",
            "step_key": "communication",
            "icon": "bi-chat-dots",
            "done": can_view_results,
            "progress_label": None,
            "tip": "Send a message or request a callback.",
            "links": _filter_links(
                [
                    _parent_workflow_link(
                        "Contact school", "portal:parent_contact_school"
                    ),
                ]
            ),
        },
        {
            "title": "5) Documents",
            "subtitle": "School handbooks, timetables, and forms.",
            "step_key": "documents",
            "icon": "bi-folder2-open",
            "done": can_view_results,
            "progress_label": None,
            "tip": "Download documents published by the school.",
            "links": _filter_links(
                [
                    _parent_workflow_link(
                        "Document library",
                        "portal:portal_feature",
                        kwargs={"feature": "documents"},
                    ),
                ]
            ),
        },
    ]
    total_steps = len(steps)
    for i, s in enumerate(steps, start=1):
        s["step_index"] = i
        s["total_steps"] = total_steps

    workflow_progress = {
        "children_linked": links.count(),
        "attendance_pct": attendance_pct,
        "can_view_finance": can_view_finance,
        "finance_balance": finance_balance,
        "finance_overdue": finance_overdue,
    }

    year, term = get_active_year_and_term()

    return render(
        request,
        "parent/workflow_center.html",
        {
            **build_tp_hero_context(
                request,
                role=User.Role.PARENT,
                children_names=", ".join(
                    s.get_full_name() or s.first_name or "" for s in students[:3] if s
                ),
                has_fees_due=can_view_finance and finance_balance > Decimal("0.00"),
                attendance_pct=int(attendance_pct) if attendance_pct is not None else None,
            ),
            "active_year": year,
            "active_term": term,
            "steps": steps,
            "workflow_progress": workflow_progress,
            "workflow_portal": build_tenant_workflow_portal(
                request,
                role=User.Role.PARENT,
                steps=steps,
                workflow_progress=workflow_progress,
                active_year=year,
                active_term=term,
                empty_state=not bool(students),
            ),
        },
    )



@parent_portal_required
@role_required(User.Role.PARENT)
@login_required
def child_digital_id(request: HttpRequest, student_id: int):
    """Phase 4: Child's digital ID card – school branding, photo, name, grade/class, STUDENT ID bar, QR."""
    from apps.people.badge_services import get_signed_id_token

    link = (
        StudentGuardian.objects.filter(
            guardian_user=request.user,
            student_id=student_id,
        )
        .select_related("student", "student__classroom", "student__academic_year")
        .first()
    )
    if not link:
        return HttpResponseForbidden(
            "You are not authorized to view this student's ID."
        )
    student = link.student
    site = get_effective_site_settings(request=request)
    classroom = getattr(student, "classroom", None)
    grade_label = (
        classroom.name
        if classroom
        else (
            getattr(student, "academic_year", None)
            and str(student.academic_year)
            or "—"
        )
    )
    photo = getattr(student, "profile_photo", None) and student.profile_photo or None
    qr_token = get_signed_id_token("student", student.pk)
    verify_url = request.build_absolute_uri(
        reverse("portal:badge_verify") + "?token=" + quote_plus(qr_token)
    )
    qr_image_url = _qr_png_data_uri(verify_url)
    return render(
        request,
        "portal/digital_id_student.html",
        {
            "site_name": getattr(site, "site_name", None) or "School",
            "student": student,
            "name": student.get_full_name(),
            "grade_label": grade_label,
            "photo": photo,
            "qr_token": qr_token,
            "verify_url": verify_url,
            "qr_image_url": qr_image_url,
        },
    )


@parent_portal_required
@role_required(User.Role.PARENT)
def portal_stats(request: HttpRequest):
    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    terms = list(Term.objects.filter(academic_year=year).order_by("start_date"))
    prev_term = None
    if term in terms:
        idx = terms.index(term)
        if idx > 0:
            prev_term = terms[idx - 1]

    site = get_effective_site_settings(request=request)
    pass_mark = site.pass_mark
    weak_threshold = site.weak_subject_threshold
    improvement_delta = site.improvement_delta_threshold

    students = guardian_students(request.user, results_only=True)
    widget_data = parent_dashboard_widget_data(students)

    top_students = []
    specialty_rows = []
    weak_subjects = []
    improvement_rows = []

    parent_student_ids = {s.id for s in students} if students else set()
    if students:
        classrooms = []
        specialty_ids = set()
        for s in students:
            if getattr(s, "classroom", None):
                classrooms.append(s.classroom)
            if getattr(s, "specialty_id", None):
                specialty_ids.add(s.specialty_id)

        seen_classrooms = set()
        for classroom in classrooms:
            if classroom.id in seen_classrooms:
                continue
            seen_classrooms.add(classroom.id)
            class_ranks = classroom_term_rankings(classroom, term)
            for agg in class_ranks:
                if agg.student.id in parent_student_ids:
                    top_students.append(agg)
        top_students.sort(key=lambda a: a.average, reverse=True)
        top_students = top_students[:10]

        specialty_rows = specialty_pass_rates(
            academic_year=year,
            term=term,
            pass_mark=pass_mark,
            use_promotion_rule=site.use_promotion_rule_for_pass,
        )
        if specialty_ids:
            specialty_rows = [
                row for row in specialty_rows if row.specialty.id in specialty_ids
            ]

        classroom_scope = classrooms[0] if classrooms else None
        weak_subjects = subject_weaknesses(
            academic_year=year,
            term=term,
            classroom=classroom_scope,
            specialty=None,
            threshold=weak_threshold,
        )
        if prev_term:
            improvement_rows = student_improvements(
                academic_year=year,
                from_term=prev_term,
                to_term=term,
                classroom=classroom_scope,
                min_delta=improvement_delta,
            )
            improvement_rows = [
                r for r in improvement_rows if r.student.id in parent_student_ids
            ]

    return render(
        request,
        "portal/stats.html",
        {
            "year": year,
            "term": term,
            "top_students": top_students,
            "specialty_rows": specialty_rows,
            "weak_subjects": weak_subjects,
            "improvement_rows": improvement_rows,
            "widget_data": widget_data,
        },
    )


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_attendance_discipline(request: HttpRequest):
    """Attendance & Discipline: list absences/tardies and submit justification. RBAC: linked children only."""
    links = guardian_student_links(request.user, results_only=False)
    student_ids = [link.student_id for link in links]
    absences = []
    if student_ids:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        absences = list(
            Attendance.objects.filter(
                student_id__in=student_ids,
                status__in=[Attendance.Status.ABSENT, Attendance.Status.LATE],
            )
            .select_related("student", "classroom")
            .order_by("-date")[:100]
        )
    justifications = (
        AttendanceJustification.objects.filter(guardian=request.user)
        .select_related("student")
        .order_by("-attendance_date")[:50]
    )
    form = AttendanceJustificationForm(request.POST or None, request.FILES or None)
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    form.fields["student"].queryset = StudentProfile.objects.filter(id__in=student_ids)
    form.fields["student"].required = True
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.guardian = request.user
        obj.student = form.cleaned_data["student"]
        if obj.student_id not in student_ids:
            return HttpResponseForbidden(
                "You can only submit for your linked children."
            )
        obj.save()
        messages.success(request, "Justification submitted.")
        return redirect("portal:parent_attendance_discipline")
    hero = {
        "title": "Attendance & Discipline",
        "subtitle": "View absences and submit justifications",
        "actions": [],
    }
    return render(
        request,
        "parent/attendance_discipline.html",
        {
            "hero": hero,
            "absences": absences,
            "justifications": justifications,
            "form": form,
            "children": [link.student for link in links],
        },
    )


@parent_portal_required
@role_required(User.Role.PARENT)
@audit_pii_view(model_name="StudentProfile", object_id_kwarg="student_id", sensitivity="HIGH", reason="Parent viewing child results")
def parent_child_results(request: HttpRequest, student_id: int):
    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    link = (
        StudentGuardian.objects.filter(
            guardian_user=request.user, student_id=student_id, can_view_results=True
        )
        .select_related("student")
        .first()
    )

    if not link:
        return HttpResponseForbidden(
            "You are not authorized to view this student's results."
        )

    student = link.student

    published = is_term_published(year.id, term.id, student.classroom_id)
    terms = terms_for_student(year, student.classroom)
    annual_published = are_terms_published(
        year.id, [t.id for t in terms], student.classroom_id
    )
    if not published:
        return render(
            request,
            "parent/results.html",
            {
                "student": student,
                "year": year,
                "term": term,
                "published": False,
                "annual_published": annual_published,
                "rows": [],
                "totals": None,
            },
        )

    report_ctx = term_report_context(student, year, term)

    total_coef = sum(row.get("coef") or 0 for row in report_ctx["rows"])
    totals = {
        "total_coef": total_coef,
        "overall": report_ctx["summary"].get("average"),
    }

    completed_count = sum(1 for row in report_ctx["rows"] if row.get("complete"))
    completion_pct = (
        int(round((completed_count / len(report_ctx["rows"])) * 100))
        if report_ctx["rows"]
        else 0
    )
    context = {
        "student": student,
        "year": year,
        "term": term,
        "published": True,
        "annual_published": annual_published,
        "rows": report_ctx["rows"],
        "summary": report_ctx["summary"],
        "weights": report_ctx["weights"],
        "totals": totals,
        "completed_count": completed_count,
        "completion_pct": completion_pct,
    }
    return render(request, "parent/results.html", context)


@parent_portal_required
@role_required(User.Role.PARENT)
@trace_view("parent.dashboard.render", op="view.hot_path")
def parent_dashboard(request: HttpRequest):
    """
    Parent dashboard with optimized query loading.
    Use select_related/prefetch_related; cache widget data; single aggregation for reminders.
    """
    links = guardian_student_links(request.user, results_only=True).prefetch_related(
        "student__evaluations"
    )
    finance_links = guardian_student_links(request.user, finance_only=True)
    flags = get_effective_flags(request)
    require_finance_opt_in = bool(flags.get("require_guardian_finance_opt_in"))
    finance_link_count = finance_links.count()
    guardian_link_count = links.count()
    can_request_finance_access = (
        require_finance_opt_in and guardian_link_count > finance_link_count
    )
    portal_features = _portal_features_status(request)
    students = [link.student for link in links]
    finance_students = [link.student for link in finance_links]
    can_view_results = bool(students)
    can_view_finance = bool(finance_students)
    widget_data = parent_dashboard_widget_data(
        students, school=getattr(request, "school", None)
    )
    if can_view_finance:
        finance_widget = parent_dashboard_widget_data(
            finance_students, school=getattr(request, "school", None)
        ).get("finance", {})
        widget_data["finance"] = finance_widget or widget_data.get("finance", {})
    else:
        widget_data["finance"] = {
            "total_due": Decimal("0.00"),
            "paid": Decimal("0.00"),
            "balance": Decimal("0.00"),
            "overdue": 0,
            "label": "Finance access not granted",
        }
    attendance_pct = widget_data["attendance"].get("overall") or 0
    request.parent_dashboard_attendance_pct = attendance_pct
    finance_total = widget_data["finance"].get("total_due") or Decimal("0.00")
    finance_paid = widget_data["finance"].get("paid") or Decimal("0.00")
    finance_balance = widget_data.get("finance", {}).get("balance") or Decimal("0.00")
    finance_paid_pct = int((finance_paid / finance_total) * 100) if finance_total else 0
    missing_work_count = widget_data.get("tasks", {}).get("pending_evaluations", 0)
    finance_request_url = reverse("finance:finance_request_access")
    finance_summary = (
        f"{finance_paid_pct}% paid ({finance_paid} settled of {finance_total})"
        if finance_total
        else "No invoices recorded yet."
    )
    finance_access_banner = {
        "text": (
            "Finance access is granted for your linked students."
            if can_view_finance
            else "Finance details are hidden until access is granted."
        ),
        "summary": finance_summary,
        "level": "success" if can_view_finance else "warning",
        "request_url": finance_request_url if can_request_finance_access else None,
        "cta": "Request finance access" if can_request_finance_access else None,
    }
    finance_requests_qs = Notification.objects.filter(
        recipient=request.user,
        title__icontains="finance access request",
    ).order_by("-created_at")
    finance_request_link = reverse("requests:dashboard")
    perf_map = {
        row.get("student_id"): row
        for row in widget_data.get("performance", {}).get("per_student", [])
    }
    att_map = {
        row.get("student_id"): row
        for row in widget_data.get("attendance", {}).get("per_student", [])
    }
    fin_map = {
        row.get("student_id"): row
        for row in widget_data.get("finance", {}).get("per_student", [])
    }
    onboarding = parent_onboarding_score(request.user, students)
    student_ids = [s.id for s in students] if students else []
    school = getattr(request, "school", None)
    year, _term = get_active_year_and_term(school=school)
    resource_pending_map = {}
    if year and student_ids:
        from apps.people.models import StudentResourceReturn

        for row in (
            StudentResourceReturn.objects.filter(
                student_id__in=student_ids,
                academic_year=year,
                returned_at__isnull=True,
            )
            .values("student_id")
            .annotate(cnt=Count("id"))
        ):
            resource_pending_map[row["student_id"]] = row["cnt"]
    badges_qs = Badge.objects.none()
    if student_ids:
        badges_qs = (
            Badge.objects.filter(student_id__in=student_ids)
            .filter(Q(expiry_at__isnull=True) | Q(expiry_at__gt=timezone.now()))
            .select_related("badge_type")
            .order_by("-issued_at")
        )
    badges_by_student = {}
    for b in badges_qs:
        sid = b.student_id
        if sid not in badges_by_student:
            badges_by_student[sid] = []
        if len(badges_by_student[sid]) < 10:
            badges_by_student[sid].append(b)
    missing_work_by_student = {}
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    if year and _term and student_ids:
        evals_this_term = list(
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            Evaluation.objects.filter(
                student_id__in=student_ids,
                academic_year=year,
                term=_term,
            ).select_related("academic_year", "term")
        )
        for e in evals_this_term:
            if not e.is_complete_for_ranking:
                missing_work_by_student[e.student_id] = (
                    missing_work_by_student.get(e.student_id, 0) + 1
                )
    parent_upcoming_events: list = []
    if year and school:
        from apps.portal.services import _merged_upcoming_events

        parent_upcoming_events = _merged_upcoming_events(year, school=school)[:10]
    class_threads = class_threads_for_parent(request.user, limit=3)
    unread_messages_aggregate = sum(t.get("unread_count", 0) for t in class_threads)
    child_cards = []
    for link in links:
        student_id = link.student.id
        perf = perf_map.get(student_id, {})
        att = att_map.get(student_id, {})
        fin = fin_map.get(student_id, {})
        child_cards.append(
            {
                "link": link,
                "attendance": att.get("overall", 0),
                "average": perf.get("average"),
                "rank": perf.get("rank"),
                "finance_total": fin.get("total_due"),
                "finance_paid": fin.get("paid"),
                "finance_balance": fin.get("balance"),
                "resource_pending": resource_pending_map.get(student_id, 0),
                "badges": badges_by_student.get(student_id, []),
                "missing_work": missing_work_by_student.get(student_id, 0),
                "unread_messages": unread_messages_aggregate,
            }
        )
    workflow_steps = [
        {
            "label": "Link children",
            "done": bool(students),
            "meta": f"{len(students)} linked",
            "action": "Link a child",
            "url": reverse("portal:link_child"),
        },
        {
            "label": "Review results and attendance",
            "done": can_view_results,
            "meta": f"Attendance {attendance_pct}%",
            "action": "Open results",
            "url": reverse("portal:parent_dashboard"),
        },
        {
            "label": "Clear follow-up work",
            "done": missing_work_count == 0,
            "meta": f"{missing_work_count} pending",
            "action": "Open workflow",
            "url": reverse("portal:parent_workflow"),
        },
        {
            "label": "Review finance",
            "done": can_view_finance
            and (widget_data.get("finance", {}).get("balance") or Decimal("0.00")) <= 0,
            "meta": f"Balance {widget_data.get('finance', {}).get('balance') or Decimal('0.00')}"
            if can_view_finance
            else "Access needed",
            "action": "Open finance",
            "url": reverse("portal:parent_finance"),
        },
        {
            "label": "Respond to school messages",
            "done": unread_messages_aggregate == 0,
            "meta": f"{unread_messages_aggregate} unread",
            "action": "Contact school",
            "url": reverse("portal:parent_contact_school"),
        },
    ]
    workflow_total_steps = len(workflow_steps)
    workflow_done_steps = sum(1 for step in workflow_steps if step["done"])
    workflow_completion_pct = (
        int(round((workflow_done_steps / workflow_total_steps) * 100))
        if workflow_total_steps
        else 0
    )
    workflow_open_steps = [s for s in workflow_steps if not s["done"]]
    if workflow_open_steps:
        workflow_focus_step = workflow_open_steps[0]
        workflow_next_actions = [
            {"label": s["action"], "url": s["url"]} for s in workflow_open_steps[:2]
        ]
    else:
        workflow_focus_step = {
            "label": "All core parent tasks completed",
            "meta": "You're up to date. Open workflow for detailed planning.",
        }
        workflow_next_actions = [
            {"label": "Open workflow", "url": reverse("portal:parent_workflow")},
            {"label": "View calendar", "url": reverse("portal:unified_calendar")},
        ]
    workflow_summary = {
        "total_steps": workflow_total_steps,
        "done_steps": workflow_done_steps,
        "completion_pct": workflow_completion_pct,
        "focus_label": workflow_focus_step["label"],
        "focus_meta": workflow_focus_step.get("meta", ""),
        "next_actions": workflow_next_actions,
    }
    runtime = getattr(request, "tenant_runtime", None)
    if runtime is not None and getattr(runtime, "_school", None):
        dash = runtime.dashboard_for(
            role=get_user_role(request.user), user=request.user
        )
    else:
        dash = dashboard_for_role(
            getattr(request, "school", None),
            get_user_role(request.user),
            user=request.user,
        )
    display_widgets = dash["widget_keys"]
    certification_stats = {}
    if year and getattr(year, "enable_gce_registration", False) and students:
        from apps.academics.models import CertificationCandidate

        candidates = CertificationCandidate.objects.filter(
            session__academic_year=year,
            student_id__in=student_ids,
        ).select_related("session", "student")
        if candidates.exists():
            certification_stats = {
                "total_candidates": candidates.count(),
                "draft_candidates": candidates.filter(status="DRAFT").count(),
                "verified_candidates": candidates.filter(status="VERIFIED").count(),
                "candidates_by_student": {
                    c.student_id: {
                        "status": c.status,
                        "session_name": c.session.name,
                        "session_id": c.session.id,
                    }
                    for c in candidates
                },
            }
    site = get_effective_site_settings(request=request)
    role = get_user_role(request.user)
    portal_quick_actions = filter_portal_items(site.portal_quick_actions, role)
    portal_announcements = filter_portal_items(site.portal_announcements, role)
    portal_recent_grades = filter_portal_items(site.portal_recent_grades, role)
    portal_upcoming_assessments = filter_portal_items(
        site.portal_upcoming_assessments, role
    )
    class_announcements = class_announcements_for_parent(request.user, students)
    if can_view_finance:
        reminders_count = PaymentReminder.objects.filter(
            invoice__student__in=finance_students, is_active=True
        ).count()
    else:
        reminders_count = 0
    parent_metrics = [
        {
            "id": "parent-linked-students",
            "label": "Linked students",
            "value": links.count(),
            "icon": "people",
        },
        {
            "id": "parent-attendance",
            "label": "Attendance",
            "value": f"{attendance_pct}%",
            "icon": "calendar-check",
            "tone": "success" if attendance_pct >= 90 else "warning",
        },
        {
            "id": "parent-missing-work",
            "label": "Pending work",
            "value": missing_work_count,
            "icon": "clipboard-x",
            "tone": "warning" if missing_work_count else "success",
        },
        {
            "id": "parent-balance",
            "label": "Balance",
            "value": finance_balance,
            "icon": "wallet2",
            "tone": (
                "warning" if can_view_finance and finance_balance > 0 else "success"
            ),
        },
    ]
    hero = {
        "tagline": "Student Management Dashboard",
        "title": "Welcome back",
        "subtitle": "Live snapshot of your learners, attendance, and finances",
        "icon": "bi-mortarboard",
        "stats": [
            {
                "label": "Linked Students",
                "value": links.count(),
                "meta": "Active profiles",
            },
            {
                "label": "Attendance",
                "value": f"{widget_data['attendance']['overall']}%",
                "progress": widget_data["attendance"]["overall"],
                "meta": "Completion",
            },
        ],
        "actions": [{"label": "Link a Child", "url": "#link-child"}],
        "status_pills": [
            {
                "label": "Active students",
                "value": links.count(),
                "meta": "Linked children",
            },
            {
                "label": "Tasks",
                "value": widget_data["tasks"]["pending_evaluations"],
                "meta": "Eval gaps",
            },
        ],
    }
    hero["actions"].append(
        {"label": "Contact School", "url": reverse("portal:parent_contact_school")}
    )
    if can_view_results:
        hero["actions"].insert(0, {"label": "View Results", "url": "#children"})
        hero["actions"].insert(
            1, {"label": "View Attendance", "url": reverse("portal:portal_stats")}
        )
    if can_view_finance:
        hero["stats"].append(
            {
                "label": "Balance",
                "value": widget_data["finance"]["balance"],
                "meta": "Outstanding fees",
            }
        )
        hero["stats"].append(
            {"label": "Reminders", "value": reminders_count, "meta": "Pending notices"}
        )
        hero["status_pills"].insert(
            1,
            {"label": "Reminders", "value": reminders_count, "meta": "Pending notices"},
        )
        hero["actions"].append(
            {"label": "Pay Fees", "url": reverse("portal:parent_finance")}
        )
    chart_attendance_donut_json = ""
    chart_finance_donut_json = ""
    chart_attendance_trend_json = ""
    att = widget_data.get("attendance") or {}
    if att.get("overall") is not None and can_view_results:
        overall = int(att.get("overall", 0) or 0)
        other = max(0, 100 - overall)
        chart_attendance_donut_json = json.dumps(
            {
                "type": "doughnut",
                "data": {
                    "labels": ["Completion", "Pending"],
                    "datasets": [
                        {
                            "data": [overall, other],
                            "backgroundColor": ["#198754", "#e2e8f0"],
                        }
                    ],
                },
            }
        )
    fin = widget_data.get("finance") or {}
    if can_view_finance and (fin.get("paid") or fin.get("balance")):
        paid, balance = float(fin.get("paid") or 0), float(fin.get("balance") or 0)
        if paid or balance:
            chart_finance_donut_json = json.dumps(
                {
                    "type": "doughnut",
                    "data": {
                        "labels": ["Paid", "Balance due"],
                        "datasets": [
                            {
                                "data": [paid, balance],
                                "backgroundColor": ["#198754", "#ffc107"],
                            }
                        ],
                    },
                }
            )
    trend = widget_data.get("attendance_trend") or []
    if trend and can_view_results:
        chart_attendance_trend_json = json.dumps(
            {
                "type": "line",
                "data": {
                    "labels": [t.get("label", "") for t in trend],
                    "datasets": [
                        {
                            "label": "Completion %",
                            "data": [t.get("value", 0) for t in trend],
                            "fill": True,
                            "borderColor": "#0d6efd",
                            "backgroundColor": "rgba(13, 110, 253, 0.15)",
                            "tension": 0.3,
                        }
                    ],
                },
            }
        )
    try:
        from apps.portal.models import FormSignature

        signature_stats = {
            "pending": FormSignature.objects.filter(
                parent=request.user, status="PENDING"
            ).count(),
            "signed": FormSignature.objects.filter(
                parent=request.user, status="SIGNED"
            ).count(),
        }
    except (ImportError, Exception) as e:
        if not isinstance(e, ImportError):
            log_view_exception(
                request,
                "parent_dashboard: FormSignature stats failed",
                extra={"widget": "signature_stats"},
            )
        signature_stats = {"pending": 0, "signed": 0}
    dashboard_context = get_dashboard_context(request.user, "parent", request=request)
    available_sidebar_items = [
        {
            "id": "parent-home",
            "label": "Parent Home",
            "url": reverse("portal:parent_dashboard"),
            "icon": "bi-house",
        },
        {
            "id": "parent-workflow",
            "label": "My Workflow",
            "url": reverse("portal:parent_workflow"),
            "icon": "bi-diagram-3",
        },
        {
            "id": "parent-finance",
            "label": "Finance",
            "url": reverse("portal:parent_finance"),
            "icon": "bi-cash-stack",
        },
        {
            "id": "parent-stats",
            "label": "Portal Stats",
            "url": reverse("portal:portal_stats"),
            "icon": "bi-graph-up",
        },
    ]
    if request.GET.get("dismiss_hint") == "parent_link_child":
        request.session["hint_parent_link_child_dismissed"] = True
        return redirect("portal:parent_dashboard")
    show_parent_dashboard_hint = not links and not request.session.get(
        "hint_parent_link_child_dismissed"
    )
    finance_balance = widget_data.get("finance", {}).get("balance") or Decimal("0.00")
    has_fees_due = can_view_finance and (finance_balance > 0)
    parent_verified = bool(
        getattr(request.user, "email", None)
        and str(request.user.email).strip()
        and not str(request.user.email).lower().startswith("pending")
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    )
    recent_payments = []
    if can_view_finance and finance_students:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        recent_payments = list(
            Payment.objects.filter(invoice__student__in=finance_students)
            .select_related("invoice", "invoice__student")
            .order_by("-paid_at")[:5]
        )
    active_child_id = get_active_child_id(request)
    guardian_students_for_switcher = [
        {
            "id": s.id,
            "display_name": (
                f"{getattr(s, 'first_name', '')} {getattr(s, 'last_name', '')}".strip()
                or f"Student {s.id}"
            ),
        }
        for s in students
    ]
    if guardian_students_for_switcher and active_child_id not in [
        s["id"] for s in guardian_students_for_switcher
    ]:
        set_active_child(request, guardian_students_for_switcher[0]["id"])
        active_child_id = guardian_students_for_switcher[0]["id"]
    policy = get_policy_for_request(request)
    is_rtl = bool(policy.get("rtl", False))
    parent_simplified = str(request.GET.get("simple") or "").lower() in (
        "1",
        "true",
        "yes",
    )
    q = request.GET.copy()
    q.pop("simple", None)
    parent_full_dashboard_url = request.path
    if q:
        parent_full_dashboard_url = f"{request.path}?{q.urlencode()}"

    return render(
        request,
        "parent/dashboard.html",
        {
            "links": links,
            "show_parent_dashboard_hint": show_parent_dashboard_hint,
            "can_view_results": can_view_results,
            "can_view_finance": can_view_finance,
            "chart_attendance_donut_json": chart_attendance_donut_json,
            "chart_finance_donut_json": chart_finance_donut_json,
            "chart_attendance_trend_json": chart_attendance_trend_json,
            "portal_features": portal_features,
            "widget_data": widget_data,
            "onboarding": onboarding,
            "child_cards": child_cards,
            "display_widgets": display_widgets,
            "portal_quick_actions": portal_quick_actions,
            "portal_announcements": portal_announcements,
            "portal_recent_grades": portal_recent_grades,
            "portal_upcoming_assessments": portal_upcoming_assessments,
            "hero": hero,
            "reminders_count": reminders_count,
            "parent_metrics": parent_metrics,
            "class_announcements": class_announcements,
            "class_threads": class_threads,
            "attendance_pct": attendance_pct,
            "has_fees_due": has_fees_due,
            "finance_paid_pct": finance_paid_pct,
            "finance_total": finance_total,
            "finance_paid": finance_paid,
            "available_sidebar_items": available_sidebar_items,
            **dashboard_context,
            "finance_access_banner": finance_access_banner,
            "finance_requests_count": finance_requests_qs.count(),
            "finance_request_notifications": finance_requests_qs[:5],
            "finance_request_link": finance_request_link,
            "certification_stats": certification_stats,
            "gce_enabled": year and getattr(year, "enable_gce_registration", False)
            if year
            else False,
            "signature_stats": signature_stats,
            "site": site,
            "parent_verified": parent_verified,
            "unread_messages_aggregate": unread_messages_aggregate,
            "missing_work_count": missing_work_count,
            "recent_payments": recent_payments,
            "workflow_summary": workflow_summary,
            "active_child_id": active_child_id,
            "guardian_students_for_switcher": guardian_students_for_switcher,
            "is_rtl": is_rtl,
            "parent_upcoming_events": parent_upcoming_events,
            "parent_simplified": parent_simplified,
            "parent_full_dashboard_url": parent_full_dashboard_url,
            "parent_show_legacy_dashboard": parent_simplified,
            **build_tp_hero_context(
                request,
                role=role,
                children_names=", ".join(
                    s.get_full_name() or s.first_name or ""
                    for s in students[:3]
                    if s
                ),
                has_fees_due=has_fees_due,
                pending_signatures=int(signature_stats.get("pending") or 0),
                unread_messages=int(unread_messages_aggregate or 0),
                attendance_pct=int(attendance_pct) if attendance_pct is not None else None,
            ),
        },
    )


def _whatsapp_invite_link(request: HttpRequest) -> str | None:
    """Build WhatsApp invite URL for link-child flow if integration/support number is configured."""
    school = getattr(request, "school", None)
    number = None
    try:
        from apps.siteconfig.integration_registry import resolve_active_integration

        record = (
            resolve_active_integration(school, "whatsapp")
            if school is not None
            else None
        )
        if record and record.is_active:
            number = (
                record.config.get("phone")
                or record.config.get("whatsapp_number")
                or record.config.get("support_number")
            )
    except PORTAL_SOFT_FAILURES:
        number = None
    if not number:
        contact_settings = get_effective_support_contact_settings(request=request)
        number = contact_settings.get(
            "whatsapp_admissions_number"
        ) or contact_settings.get("whatsapp_support_number")
    if not number:
        return None
    digits = "".join(ch for ch in number if ch.isdigit())
    if not digits:
        return None
    site_name = get_site_display_name(request)
    message = quote_plus(f"Hi, I'd like to claim a portal invite for {site_name}.")
    return f"https://wa.me/{digits}?text={message}"


@parent_portal_required
@role_required(User.Role.PARENT)
def link_child(request: HttpRequest):
    """
    Legacy single-page form view (kept for backwards compatibility).
    New users should use link_child_wizard for a better experience.
    """
    site = get_effective_site_settings(request=request)
    policy = get_policy_for_request(request)
    form = LinkChildForm(
        request.POST or None,
        guardian_user=request.user,
        policy=policy,
        school_code=site.school_code,
    )
    if request.method == "POST" and form.is_valid():
        guardian_link = form.save()
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        student = guardian_link.student
        student_updates = form.student_updates()
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        if student_updates:
            StudentProfile.objects.filter(pk=student.pk).update(**student_updates)
            student.refresh_from_db()
        parent_updates = form.parent_updates()
        if parent_updates:
            changed = []
            for attr, value in parent_updates.items():
                setattr(request.user, attr, value)
                changed.append(attr)
            if changed:
                request.user.save(update_fields=changed)
        messages.success(
            request,
            f"Linked {guardian_link.student} successfully. Results and finance access will reflect your choices.",
        )
        referral_code = form.cleaned_data.get("referral_code", "").strip()
        reward = award_referral_reward(guardian_link, referral_code, request.user)
        if reward and reward.amount > Decimal("0.00"):
            messages.info(
                request,
                f"Referral bonus of {reward.amount:.2f} will appear in your finance view once approved.",
            )
        return redirect("portal:parent_dashboard")
    return render(
        request,
        "parent/link_child.html",
        {
            "form": form,
            "school_code": site.school_code,
            "completeness_pct": form.completeness_score(),
            "referral_bonus": site.referral_bonus_amount,
            "support_email": site.company_email,
            "support_phone": site.company_phone,
            "whatsapp_invite_link": _whatsapp_invite_link(request),
        },
    )


@parent_portal_required
@role_required(User.Role.PARENT)
def link_child_wizard(request: HttpRequest):
    """
    Multi-step wizard for linking a child (mobile-friendly, progressive disclosure).
    Steps: 1) Identify child (admission number + relationship); 2) Contact & permissions; 3) Optional details.
    Uses session to persist form data between steps.
    """
    site = get_effective_site_settings(request=request)
    session_key = "link_child_wizard_data"
    wizard_data = request.session.get(session_key, {})
    step = int(request.GET.get("step", "1"))
    if request.method == "POST":
        action = request.POST.get("action", "next")
        if action == "back":
            step = max(1, step - 1)
            request.session[session_key] = wizard_data
            return redirect(f"{request.path}?step={step}")
        for key, value in request.POST.items():
            if key not in ("csrfmiddlewaretoken", "action", "step"):
                wizard_data[key] = value
        request.session[session_key] = wizard_data
        policy = get_policy_for_request(request)
        form = LinkChildForm(
            data=request.POST,
            guardian_user=request.user,
            policy=policy,
            school_code=site.school_code,
        )
        if step == 1:
            admission = request.POST.get("admission_number", "").strip()
            relationship = request.POST.get("relationship", "")
            has_errors = False
            if not admission:
                form.add_error(
                    "admission_number",
                    forms.ValidationError("Admission number is required."),
                )
                has_errors = True
            if not relationship:
                form.add_error(
                    "relationship", forms.ValidationError("Relationship is required.")
                )
                has_errors = True
            if admission and relationship and not has_errors:
                try:
                    student = StudentProfile.objects.select_related(
                        "academic_year", "classroom", "specialty"
                    ).get(admission_number__iexact=admission)
                    if not student.is_active:
                        form.add_error(
                            "admission_number",
                            forms.ValidationError("This student profile is inactive."),
                        )
                    elif StudentGuardian.objects.filter(
                        guardian_user=request.user, student=student
                    ).exists():
                        form.add_error(
                            "admission_number",
                            forms.ValidationError(
                                "You are already linked to this student."
                            ),
                        )
                    else:
                        step = 2
                        request.session[session_key] = wizard_data
                        return redirect(f"{request.path}?step={step}")
                except StudentProfile.DoesNotExist:
                    form.add_error(
                        "admission_number",
                        forms.ValidationError(
                            "No student found with that admission number."
                        ),
                    )
                except PORTAL_SOFT_FAILURES as e:
                    log_view_exception(
                        request,
                        "portal.views_parent: error validating admission number",
                        extra={"error": str(e)},
                    )
                    form.add_error(
                        "admission_number",
                        forms.ValidationError(
                            "An error occurred. Please try again or contact support."
                        ),
                    )
        elif step == 2:
            step = 3
            request.session[session_key] = wizard_data
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            return redirect(f"{request.path}?step={step}")
        elif step == 3 and form.is_valid():
            guardian_link = form.save()
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            student = guardian_link.student
            student_updates = form.student_updates()
            if student_updates:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                StudentProfile.objects.filter(pk=student.pk).update(**student_updates)
                student.refresh_from_db()
            parent_updates = form.parent_updates()
            if parent_updates:
                for attr, value in parent_updates.items():
                    setattr(request.user, attr, value)
                request.user.save(update_fields=list(parent_updates.keys()))
            messages.success(
                request,
                f"Linked {guardian_link.student} successfully. Results and finance access will reflect your choices.",
            )
            referral_code = form.cleaned_data.get("referral_code", "").strip()
            reward = award_referral_reward(guardian_link, referral_code, request.user)
            if reward and reward.amount > Decimal("0.00"):
                messages.info(
                    request,
                    f"Referral bonus of {reward.amount:.2f} will appear in your finance view once approved.",
                )
            if session_key in request.session:
                del request.session[session_key]
            return redirect("portal:parent_dashboard")
    form_data = wizard_data if request.method == "GET" else None
    policy = get_policy_for_request(request)
    form = LinkChildForm(
        data=form_data,
        guardian_user=request.user,
        policy=policy,
        school_code=site.school_code,
    )
    if wizard_data:
        for key, value in wizard_data.items():
            if key in form.fields:
                form.fields[key].initial = value
    student_info = None
    if hasattr(form, "student"):
        student_info = form.student
    elif "admission_number" in wizard_data:
        try:
            student_info = StudentProfile.objects.select_related(
                "academic_year", "classroom", "specialty"
            ).get(admission_number__iexact=wizard_data["admission_number"])
        except StudentProfile.DoesNotExist:
            pass
    if not wizard_data.get("parent_first_name") and request.user.first_name:
        form.fields["parent_first_name"].initial = request.user.first_name
    if not wizard_data.get("parent_last_name") and request.user.last_name:
        form.fields["parent_last_name"].initial = request.user.last_name
    if not wizard_data.get("parent_email") and request.user.email:
        form.fields["parent_email"].initial = request.user.email
    total_steps = 3
    progress_pct = int((step / total_steps) * 100)
    return render(
        request,
        "parent/link_child_wizard.html",
        {
            "form": form,
            "step": step,
            "total_steps": total_steps,
            "progress_pct": progress_pct,
            "student_info": student_info,
            "school_code": site.school_code,
            "completeness_pct": form.completeness_score() if wizard_data else 0,
            "referral_bonus": site.referral_bonus_amount,
            "support_email": site.company_email,
            "support_phone": site.company_phone,
            "whatsapp_invite_link": _whatsapp_invite_link(request),
        },
    )
