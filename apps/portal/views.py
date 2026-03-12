from django.shortcuts import render, get_object_or_404, redirect
from datetime import timedelta
from django.http import JsonResponse, HttpResponseForbidden, HttpRequest, Http404, HttpResponse, HttpResponseRedirect
from django.utils.safestring import mark_safe
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from collections import Counter
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django import forms
import uuid
from decimal import Decimal
from urllib.parse import quote_plus
import csv
import base64
from io import BytesIO
import logging

from apps.accounts.decorators import (
    role_required,
    parent_portal_required,
    teacher_portal_required,
)
from apps.accounts.utils import get_user_role
from apps.evals.views import (
    teacher_dashboard as evals_teacher_dashboard,
    teacher_workflow_center as evals_teacher_workflow_center,
)
from apps.accounts.models import User
from django.db.models import Q
from apps.people.models import (
    StudentGuardian,
    StudentProfile,
    TeacherProfile,
    TeacherPayRecord,
    TeacherLeaveRequest,
    TeacherAttendance,
    Badge,
    BadgeType,
)
from apps.academics.models import Attendance, Classroom, SubjectAssignment, Term
from apps.academics.services import get_active_year_and_term
from apps.evals.models import Evaluation
from apps.finance.models import Payment, PaymentReminder, Notification
from apps.evals.services import classroom_term_rankings
from apps.reports.services import (
    are_terms_published,
    is_term_published,
    terms_for_student,
    term_report_context,
)
import json

from apps.siteconfig.models import (
    default_portal_features,
    filter_portal_items,
    default_backend_feature_flags,
)
from apps.runtime_blueprints.models import get_dashboard_widget_metadata
from apps.siteconfig.dashboard_resolver import for_role as dashboard_for_role
from apps.siteconfig.dashboard_views import load_dashboard_layout_settings
from apps.platform_runtime.helpers import get_effective_flags, get_effective_site_settings, get_site_display_name
from .runtime_helpers import get_policy_for_request
from apps.siteconfig.dashboard_views import _can_customize
from apps.analytics.services import (
    student_improvements,
    specialty_pass_rates,
    subject_weaknesses,
    term_rankings,
)
from .models import (
    PortalFeatureItem,
    PendingGuardianInvite,
    LessonPlan,
    LessonPlanAttachment,
    TeacherTrainingEntry,
    AttendanceJustification,
    CahierDeTexteEntry,
)
from .services import (
    parent_dashboard_widget_data,
    award_referral_reward,
    link_guardian_via_invite,
    guardian_student_links,
    guardian_students,
    class_announcements_for_parent,
    class_threads_for_parent,
    parent_onboarding_score,
    _merged_upcoming_events,
)
from .parent_portal_helpers import (
    get_active_child_id,
    set_active_child,
    require_parent_child_access,
)
from .forms import (
    LinkChildForm,
    ClaimInviteForm,
    TeacherLeaveForm,
    TeacherOnboardingForm,
    StudentOnboardingForm,
    LessonPlanUploadForm,
    LessonPlanAttachmentForm,
    TeacherTrainingEntryForm,
    AttendanceJustificationForm,
    CahierDeTexteEntryForm,
)
from .views_onboarding import teacher_onboarding_wizard, student_onboarding_wizard
from .views_parent_finance import parent_finance, parent_wallet, parent_feed
from apps.communication.models import Message
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET
from django.db import DatabaseError
from django.urls import NoReverseMatch

logger = logging.getLogger(__name__)

PORTAL_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    NoReverseMatch,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)

# Portal feature metadata for the navigation and UI
PORTAL_FEATURES_META = {
    "messaging": {
        "label": "Messaging",
        "description": "Send broadcasts or targeted notes to teachers, staff, and guardians.",
        "icon": "bi-chat-left-text",
    },
    "forums": {
        "label": "Community Forums",
        "description": "Create topic-driven discussions for parents, teachers, and leadership.",
        "icon": "bi-people",
    },
    "video": {
        "label": "Video Hub",
        "description": "Share announcements, tutorials, or recorded meetings school-wide.",
        "icon": "bi-camera-video",
    },
    "documents": {
        "label": "Document Library",
        "description": "Publish handbooks, timetables, and policy updates for anyone to download.",
        "icon": "bi-file-earmark-text",
    },
    "syllabus": {
        "label": "Class Syllabus",
        "description": "Download lesson plans, term agendas, and curriculum outlines for every specialty.",
        "icon": "bi-journal-text",
    },
}


def _portal_features_status(request=None) -> list[dict]:
    site = get_effective_site_settings(request=request)
    features = site.portal_features or default_portal_features()
    return [
        {
            "key": key,
            "label": meta["label"],
            "description": meta["description"],
            "icon": meta.get("icon"),
            "enabled": bool(features.get(key)),
        }
        for key, meta in PORTAL_FEATURES_META.items()
    ]

@parent_portal_required
@role_required(User.Role.PARENT)
def parent_dashboard(request: HttpRequest):
    """
    Parent dashboard with optimized query loading.
    
    Optimization:
    - Use select_related for related objects (student, classroom, specialty, academic_year)
    - Use prefetch_related for students to make cache more efficient
    - Cache widget data for 5 minutes per student set
    - Single aggregation query for reminders count
    """
    from django.db.models import Prefetch
    
    links = guardian_student_links(request.user, results_only=True).prefetch_related("student__evaluations")

    finance_links = guardian_student_links(request.user, finance_only=True)

    flags = get_effective_flags(request)
    require_finance_opt_in = bool(flags.get("require_guardian_finance_opt_in"))
    finance_link_count = finance_links.count()
    guardian_link_count = links.count()
    can_request_finance_access = require_finance_opt_in and guardian_link_count > finance_link_count

    portal_features = _portal_features_status(request)
    students = [link.student for link in links]
    finance_students = [link.student for link in finance_links]
    can_view_results = bool(students)
    can_view_finance = bool(finance_students)
    
    # Widget data is now cached internally for 5 minutes
    widget_data = parent_dashboard_widget_data(students, school=getattr(request, "school", None))
    if can_view_finance:
        finance_widget = parent_dashboard_widget_data(
            finance_students,
            school=getattr(request, "school", None),
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
    # Align top-bar Dashboard Stats with this view: pass to context processor so Attendance card uses same value
    request.parent_dashboard_attendance_pct = attendance_pct
    finance_total = widget_data["finance"].get("total_due") or Decimal("0.00")
    finance_paid = widget_data["finance"].get("paid") or Decimal("0.00")
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

    # Per-student maps for live cards
    perf_map = {row.get("student_id"): row for row in widget_data.get("performance", {}).get("per_student", [])}
    att_map = {row.get("student_id"): row for row in widget_data.get("attendance", {}).get("per_student", [])}
    fin_map = {row.get("student_id"): row for row in widget_data.get("finance", {}).get("per_student", [])}

    onboarding = parent_onboarding_score(request.user, students)
    # Phase 3: Student 360 – resource return pending count per student
    from django.db.models import Count
    from apps.people.models import StudentResourceReturn
    student_ids = [s.id for s in students] if students else []
    year, _term = get_active_year_and_term()
    resource_pending_map = {}
    if year and student_ids:
        for row in (
            StudentResourceReturn.objects.filter(
                student_id__in=student_ids,
                academic_year=year,
                returned_at__isnull=True,
            ).values("student_id").annotate(cnt=Count("id"))
        ):
            resource_pending_map[row["student_id"]] = row["cnt"]
    # Phase 1: Student badges per child (non-expired, up to 10 per student)
    badges_qs = Badge.objects.none()
    if student_ids:
        badges_qs = (
            Badge.objects.filter(student_id__in=student_ids)
            .filter(
                Q(expiry_at__isnull=True) | Q(expiry_at__gt=timezone.now())
            )
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
    # Per-student missing work (incomplete evaluations this term)
    missing_work_by_student = {}
    if year and _term and student_ids:
        evals_this_term = list(
            Evaluation.objects.filter(
                student_id__in=student_ids,
                academic_year=year,
                term=_term,
            ).select_related("academic_year", "term")
        )
        for e in evals_this_term:
            if not e.is_complete_for_ranking:
                missing_work_by_student[e.student_id] = missing_work_by_student.get(e.student_id, 0) + 1
    # Required before building child_cards (used in each card)
    class_threads = class_threads_for_parent(request.user, limit=3)
    unread_messages_aggregate = sum(t.get("unread_count", 0) for t in class_threads)
    child_cards = []
    for link in links:
        student_id = link.student.id
        perf = perf_map.get(student_id, {})
        att = att_map.get(student_id, {})
        fin = fin_map.get(student_id, {})
        child_cards.append({
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
        })

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
            "done": can_view_finance and (widget_data.get("finance", {}).get("balance") or Decimal("0.00")) <= 0,
            "meta": (
                f"Balance {widget_data.get('finance', {}).get('balance') or Decimal('0.00')}"
                if can_view_finance else "Access needed"
            ),
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
    workflow_completion_pct = int(round((workflow_done_steps / workflow_total_steps) * 100)) if workflow_total_steps else 0
    workflow_open_steps = [step for step in workflow_steps if not step["done"]]
    if workflow_open_steps:
        workflow_focus_step = workflow_open_steps[0]
        workflow_next_actions = [
            {"label": step["action"], "url": step["url"]}
            for step in workflow_open_steps[:2]
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
        dash = runtime.dashboard_for(role=get_user_role(request.user), user=request.user)
    else:
        dash = dashboard_for_role(getattr(request, "school", None), get_user_role(request.user), user=request.user)
    display_widgets = dash["widget_keys"]

    # Get student IDs for queries
    student_ids = [s.id for s in students] if students else []
    
    # Certification stats (if GCE enabled and children are candidates)
    certification_stats = {}
    year, _term = get_active_year_and_term()
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
    portal_upcoming_assessments = filter_portal_items(site.portal_upcoming_assessments, role)
    class_announcements = class_announcements_for_parent(request.user, students)
    # class_threads and unread_messages_aggregate already set before child_cards

    # Single aggregation query for reminders
    if can_view_finance:
        reminders_count = PaymentReminder.objects.filter(
            invoice__student__in=finance_students,
            is_active=True,
        ).count()
    else:
        reminders_count = 0
    
    hero = {
        "tagline": "Student Management Dashboard",
        "title": "Welcome back",
        "subtitle": "Live snapshot of your learners, attendance, and finances",
        "icon": "bi-mortarboard",
        "stats": [
            {"label": "Linked Students", "value": links.count(), "meta": "Active profiles"},
            {"label": "Attendance", "value": f"{widget_data['attendance']['overall']}%", "progress": widget_data['attendance']['overall'], "meta": "Completion"},
        ],
        "actions": [
            {"label": "Link a Child", "url": "#link-child"},
        ],
        "status_pills": [
            {"label": "Active students", "value": links.count(), "meta": "Linked children"},
            {"label": "Tasks", "value": widget_data["tasks"]["pending_evaluations"], "meta": "Eval gaps"},
        ],
    }
    hero["actions"].append({"label": "Contact School", "url": reverse("portal:parent_contact_school")})
    if can_view_results:
        hero["actions"].insert(0, {"label": "View Results", "url": "#children"})
        hero["actions"].insert(1, {"label": "View Attendance", "url": reverse("portal:portal_stats")})
    if can_view_finance:
        hero["stats"].append({"label": "Balance", "value": widget_data["finance"]["balance"], "meta": "Outstanding fees"})
        hero["stats"].append({"label": "Reminders", "value": reminders_count, "meta": "Pending notices"})
        hero["status_pills"].insert(1, {"label": "Reminders", "value": reminders_count, "meta": "Pending notices"})
        hero["actions"].append({"label": "Pay Fees", "url": reverse("portal:parent_finance")})

    from apps.accounts.utils import get_dashboard_context

    # Chart JSON for parent dashboard
    chart_attendance_donut_json = ""
    chart_finance_donut_json = ""
    chart_attendance_trend_json = ""
    att = widget_data.get("attendance") or {}
    if att.get("overall") is not None and can_view_results:
        overall = int(att.get("overall", 0) or 0)
        other = max(0, 100 - overall)
        chart_attendance_donut_json = json.dumps({
            "type": "doughnut",
            "data": {
                "labels": ["Completion", "Pending"],
                "datasets": [{
                    "data": [overall, other],
                    "backgroundColor": ["#198754", "#e2e8f0"],
                }],
            },
        })
    fin = widget_data.get("finance") or {}
    if can_view_finance and (fin.get("paid") or fin.get("balance")):
        paid = float(fin.get("paid") or 0)
        balance = float(fin.get("balance") or 0)
        if paid or balance:
            chart_finance_donut_json = json.dumps({
                "type": "doughnut",
                "data": {
                    "labels": ["Paid", "Balance due"],
                    "datasets": [{
                        "data": [paid, balance],
                        "backgroundColor": ["#198754", "#ffc107"],
                    }],
                },
            })
    trend = widget_data.get("attendance_trend") or []
    if trend and can_view_results:
        chart_attendance_trend_json = json.dumps({
            "type": "line",
            "data": {
                "labels": [t.get("label", "") for t in trend],
                "datasets": [{
                    "label": "Completion %",
                    "data": [t.get("value", 0) for t in trend],
                    "fill": True,
                    "borderColor": "#0d6efd",
                    "backgroundColor": "rgba(13, 110, 253, 0.15)",
                    "tension": 0.3,
                }],
            },
        })

    # Signature stats for parent (forms awaiting signature)
    try:
        from apps.portal.models import FormSignature
        signature_stats = {
            "pending": FormSignature.objects.filter(parent=request.user, status="PENDING").count(),
            "signed": FormSignature.objects.filter(parent=request.user, status="SIGNED").count(),
        }
    except (ImportError, Exception):
        signature_stats = {"pending": 0, "signed": 0}

    dashboard_context = get_dashboard_context(request.user, "parent")
    available_sidebar_items = [
        {"id": "parent-home", "label": "Parent Home", "url": reverse("portal:parent_dashboard"), "icon": "bi-house"},
        {"id": "parent-workflow", "label": "My Workflow", "url": reverse("portal:parent_workflow"), "icon": "bi-diagram-3"},
        {"id": "parent-finance", "label": "Finance", "url": reverse("portal:parent_finance"), "icon": "bi-cash-stack"},
        {"id": "parent-stats", "label": "Portal Stats", "url": reverse("portal:portal_stats"), "icon": "bi-graph-up"},
    ]
    site = get_effective_site_settings(request=request)

    # First-time hint: show when no children and not dismissed (session)
    if request.GET.get("dismiss_hint") == "parent_link_child":
        request.session["hint_parent_link_child_dismissed"] = True
        return redirect("portal:parent_dashboard")
    show_parent_dashboard_hint = not links and not request.session.get("hint_parent_link_child_dismissed")

    finance_balance = widget_data.get("finance", {}).get("balance") or Decimal("0.00")
    has_fees_due = can_view_finance and (finance_balance > 0)

    # Phase 6: Verified Parent pill (e.g. email present and not placeholder)
    parent_verified = bool(
        getattr(request.user, "email", None)
        and str(request.user.email).strip()
        and not str(request.user.email).lower().startswith("pending")
    )
    # unread_messages_aggregate already set before child_cards

    # Phase 8: Latest transactions for parent (recent payments)
    recent_payments = []
    if can_view_finance and finance_students:
        recent_payments = list(
            Payment.objects.filter(invoice__student__in=finance_students)
            .select_related("invoice", "invoice__student")
            .order_by("-paid_at")[:5]
        )

    # Phase F optional: active child for switcher; RTL from school/region
    active_child_id = get_active_child_id(request)
    guardian_students_for_switcher = [
        {"id": s.id, "display_name": (f"{getattr(s, 'first_name', '')} {getattr(s, 'last_name', '')}".strip() or f"Student {s.id}")}
        for s in students
    ]
    if guardian_students_for_switcher and active_child_id not in [s["id"] for s in guardian_students_for_switcher]:
        set_active_child(request, guardian_students_for_switcher[0]["id"])
        active_child_id = guardian_students_for_switcher[0]["id"]
    # RTL from Policy Registry (runtime constitution)
    policy = get_policy_for_request(request)
    is_rtl = bool(policy.get("rtl", False))

    return render(request, "parent/dashboard.html", {
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
        "class_announcements": class_announcements,
        "class_threads": class_threads,
        "attendance_pct": attendance_pct,
        "has_fees_due": has_fees_due,
        "finance_paid_pct": finance_paid_pct,
        "finance_total": finance_total,
        "finance_paid": finance_paid,
        "available_sidebar_items": available_sidebar_items,
        **dashboard_context,  # Unpack dashboard settings, layout URL, widget metadata, etc.
        "finance_access_banner": finance_access_banner,
        "finance_requests_count": finance_requests_qs.count(),
        "finance_request_notifications": finance_requests_qs[:5],
        "finance_request_link": finance_request_link,
        "certification_stats": certification_stats,
        "gce_enabled": year and getattr(year, "enable_gce_registration", False) if year else False,
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
    })


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_set_active_child(request: HttpRequest, child_id: int):
    """Phase F optional: set session active child and redirect to parent dashboard. Verifies parent has access."""
    student, err = require_parent_child_access(request, child_id)
    if err:
        return err
    set_active_child(request, child_id)
    return redirect("portal:parent_dashboard")


def _parent_workflow_link(label: str, url_name: str, *args, **kwargs) -> dict:
    """Build a workflow link dict; return None if URL fails to resolve."""
    try:
        return {"label": label, "url": reverse(url_name, args=args, kwargs=kwargs)}
    except PORTAL_SOFT_FAILURES:
        return None


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
        widget_data["finance"] = {"total_due": Decimal("0.00"), "paid": Decimal("0.00"), "balance": Decimal("0.00"), "overdue": 0}
    attendance_pct = widget_data.get("attendance", {}).get("overall") or 0
    finance_balance = widget_data.get("finance", {}).get("balance") or Decimal("0.00")
    finance_overdue = widget_data.get("finance", {}).get("overdue", 0)

    flags = get_effective_flags(request)
    require_finance_opt_in = bool(flags.get("require_guardian_finance_opt_in"))
    can_request_finance_access = require_finance_opt_in and links.exists() and not can_view_finance

    def _filter_links(link_list):
        return [lnk for lnk in link_list if lnk is not None and lnk.get("url")]

    finance_step_links = (
        [_parent_workflow_link("Finance", "portal:parent_finance")] if can_view_finance
        else ([_parent_workflow_link("Request finance access", "finance:finance_request_access")] if can_request_finance_access else [])
    )

    steps = [
        {
            "title": "1) Link your children",
            "subtitle": "Connect your account to your child's profile to see results and finance.",
            "step_key": "link",
            "icon": "bi-link-45deg",
            "progress_label": f"{links.count()} child(ren) linked" if links.exists() else "No children linked yet",
            "tip": "Use the link-a-child wizard or claim an invite from the school.",
            "links": _filter_links([
                _parent_workflow_link("Link a child", "portal:link_child"),
                _parent_workflow_link("Parent home", "portal:parent_dashboard"),
            ]),
        },
        {
            "title": "2) Results & attendance",
            "subtitle": "View report cards, term results, and attendance.",
            "step_key": "results",
            "icon": "bi-journal-check",
            "progress_label": f"{links.count()} profile(s) · Attendance {attendance_pct}%" if can_view_results else "Link a child first",
            "tip": "Open a child's card on the home page to view results, or go to Portal Stats.",
            "links": _filter_links([
                _parent_workflow_link("Parent home (results)", "portal:parent_dashboard"),
                _parent_workflow_link("Portal stats", "portal:portal_stats"),
            ]),
        },
        {
            "title": "3) Finance",
            "subtitle": "Invoices, payments, and balance.",
            "step_key": "finance",
            "icon": "bi-cash-stack",
            "progress_label": f"Balance: {finance_balance}" if can_view_finance else "Finance access not granted",
            "tip": "Pay fees and view payment history. Request access if you don't see finance.",
            "links": _filter_links(finance_step_links),
        },
        {
            "title": "4) Communication",
            "subtitle": "Contact the school and stay in touch.",
            "step_key": "communication",
            "icon": "bi-chat-dots",
            "progress_label": None,
            "tip": "Send a message or request a callback.",
            "links": _filter_links([
                _parent_workflow_link("Contact school", "portal:parent_contact_school"),
            ]),
        },
        {
            "title": "5) Documents",
            "subtitle": "School handbooks, timetables, and forms.",
            "step_key": "documents",
            "icon": "bi-folder2-open",
            "progress_label": None,
            "tip": "Download documents published by the school.",
            "links": _filter_links([
                _parent_workflow_link("Document library", "portal:portal_feature", kwargs={"feature": "documents"}),
            ]),
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

    return render(request, "parent/workflow_center.html", {
        "active_year": year,
        "active_term": term,
        "steps": steps,
        "workflow_progress": workflow_progress,
    })


def _teacher_feed_school(request: HttpRequest):
    """Resolve school for teacher feed."""
    from apps.schools.models import School, SchoolMembership
    school = getattr(request, "school", None)
    if school is not None:
        return school
    school_id = getattr(request, "session", {}).get("school_id")
    if school_id:
        return School.objects.filter(pk=school_id, is_active=True).first()
    membership = SchoolMembership.objects.filter(user=request.user, school__is_active=True).select_related("school").first()
    return membership.school if membership else None


@role_required(User.Role.TEACHER)
def teacher_feed(request: HttpRequest):
    """Plan VI: Social feed for teachers — school announcements, achievements, interventions."""
    from apps.communication.models import FeedItem
    school = _teacher_feed_school(request)
    if not school:
        messages.info(request, "Select a school to view the feed.")
        return redirect("portal:teacher_dashboard_alias")
    items = FeedItem.objects.filter(school=school).select_related("student", "created_by").order_by("-created_at")[:100]
    return render(request, "teacher/feed.html", {"feed_items": list(items)})


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

        guardian, reward = link_guardian_via_invite(invite, request.user, awarded_by=request.user)
        messages.success(request, f"Invite claimed. You are now linked to {guardian.student}.")
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

    return render(request, "parent/claim_invite.html", {
        "form": form,
        "show_claim_invite_hint": show_claim_invite_hint,
    })


# Per-feature RBAC: permission required to access each portal tool (sidebar + direct URL).
PORTAL_FEATURE_PERMISSIONS = {"forums": "portal.forums", "video": "portal.video", "documents": "portal.documents"}


@login_required
def portal_feature_page(request: HttpRequest, feature: str):
    """Portal tools (Community, Video, Documents): require corresponding portal.* permission and feature enabled."""
    perm_code = PORTAL_FEATURE_PERMISSIONS.get(feature)
    if perm_code and not request.user.has_feature_permission(perm_code):
        return HttpResponseForbidden("You do not have access to this portal feature.")

    available = _portal_features_status(request)
    entry = next((item for item in available if item["key"] == feature), None)
    if not entry:
        raise Http404("Feature not found.")

    if not entry["enabled"]:
        if request.method == "POST":
            from apps.requests.services import create_access_request
            create_access_request(
                request_type="PORTAL_FEATURE_ACCESS",
                requester=request.user,
                title="Portal feature access request",
                summary=f"Requested access to {entry['label']}.",
                details={"feature": entry["key"], "label": entry["label"]},
                school=getattr(request, "school", None),
            )
            messages.success(request, "Access request submitted to the admin team.")
            return redirect("portal:parent_dashboard")
        return render(request, "portal/feature_disabled.html", {
            "feature": entry,
        })

    items = PortalFeatureItem.objects.filter(feature=feature, is_active=True).select_related("created_by")
    return render(request, "portal/feature_page.html", {
        "feature": entry,
        "items": items,
    })


@role_required(User.Role.PARENT, User.Role.TEACHER)
def portal_syllabus(request: HttpRequest):
    site = get_effective_site_settings(request=request)
    role = get_user_role(request.user)
    if role == User.Role.PARENT and not site.enable_parent_portal:
        return HttpResponseForbidden("Parent portal is disabled.")
    if role == User.Role.TEACHER and not site.enable_teacher_portal:
        return HttpResponseForbidden("Teacher portal is disabled.")

    items = PortalFeatureItem.objects.filter(
        feature=PortalFeatureItem.Feature.SYLLABUS,
        is_active=True,
    ).select_related("created_by").order_by("-created_at")

    role = get_user_role(request.user)
    return render(request, "portal/syllabus.html", {
        "feature": {**PORTAL_FEATURES_META["syllabus"], "key": "syllabus"},
        "items": items,
        "is_teacher": role == User.Role.TEACHER,
    })


@never_cache
def badge_verify(request: HttpRequest):
    """
    Public badge verification (Phase 2). GET ?token=... or ?t=...
    Token is a signed payload 'badge:<pk>'. Returns Valid/Invalid page and optional JSON.
    Rate-limited by IP per minute.
    """
    from django.core.signing import Signer, BadSignature
    from django.core.cache import cache

    token = request.GET.get("token") or request.GET.get("t", "").strip()
    want_json = request.GET.get("format") == "json"
    valid = False
    badge = None
    message = "Invalid or missing token."

    if token:
        # Rate limit: 30 requests per IP per minute (tenant-scoped key)
        from apps.siteconfig.cache_utils import tenant_cache_key
        ip = request.META.get("REMOTE_ADDR", "")[:64]
        minute = timezone.now().strftime("%Y%m%d%H%M")
        cache_key = tenant_cache_key(f"badge_verify:{ip}:{minute}", request)
        try:
            count = cache.get(cache_key, 0)
            if count >= 30:
                message = "Too many requests. Try again later."
            else:
                cache.set(cache_key, count + 1, 120)
                signer = Signer(salt="badge.verify")
                payload = signer.unsign(token)
                if payload.startswith("badge:"):
                    pk = int(payload.split(":")[1])
                    badge = Badge.objects.filter(pk=pk).select_related("badge_type", "user", "student").first()
                    if badge:
                        if badge.expiry_at and badge.expiry_at <= timezone.now():
                            message = "Badge has expired."
                        else:
                            valid = True
                            message = f"Valid — {badge.badge_type.label}"
                elif payload.startswith("staff:"):
                    from apps.accounts.models import User
                    uid = int(payload.split(":")[1])
                    user = User.objects.filter(pk=uid).first()
                    if user and getattr(user, "teacher_profile", None):
                        valid = True
                        message = _("Valid — Staff ID")
                        badge = type("IDHolder", (), {"user": user, "student": None, "badge_type": type("BT", (), {"label": "Staff ID"})()})()
                    else:
                        message = _("Staff member not found or inactive.")
                elif payload.startswith("student:"):
                    sid = int(payload.split(":")[1])
                    student = StudentProfile.objects.filter(pk=sid).first()
                    if student and student.is_active:
                        valid = True
                        message = _("Valid — Student ID")
                        badge = type("IDHolder", (), {"user": None, "student": student, "badge_type": type("BT", (), {"label": "Student ID"})()})()
                    else:
                        message = _("Student not found or inactive.")
                # Phase 5: log scan event for valid verifications (attendance / third-party)
                if valid and badge:
                    from apps.people.models import BadgeScanEvent
                    kind = BadgeScanEvent.KIND_STAFF if getattr(badge, "user", None) else BadgeScanEvent.KIND_STUDENT
                    if payload.startswith("badge:"):
                        kind = BadgeScanEvent.KIND_BADGE
                    ip = request.META.get("REMOTE_ADDR", "")[:45] or None
                    try:
                        BadgeScanEvent.objects.create(
                            badge=badge if kind == BadgeScanEvent.KIND_BADGE and getattr(badge, "pk", None) else None,
                            token_kind=kind,
                            user=getattr(badge, "user", None),
                            student=getattr(badge, "student", None),
                            verified=True,
                            ip_address=ip,
                            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
                        )
                    except PORTAL_SOFT_FAILURES:
                        pass
        except (BadSignature, ValueError, IndexError):
            pass

    # Phase 5: JSON response includes role and name for third-party / NFC / access control
    role = None
    name = None
    if valid and badge:
        if getattr(badge, "user", None):
            role = "staff"
            name = getattr(badge.user, "get_full_name", lambda: str(badge.user))() or getattr(badge.user, "username", "")
        elif getattr(badge, "student", None):
            role = "student"
            name = getattr(badge.student, "get_full_name", lambda: str(badge.student))() or getattr(badge.student, "admission_number", "")

    if want_json:
        return JsonResponse({
            "valid": valid,
            "message": message,
            "badge_type": getattr(badge, "badge_type", None) and getattr(badge.badge_type, "label", None),
            "holder": str(badge.user or badge.student) if badge else None,
            "role": role,
            "name": name,
        })

    return render(request, "portal/badge_verify.html", {
        "valid": valid,
        "message": message,
        "badge": badge,
    })


@parent_portal_required
def parent_medal_case(request: HttpRequest):
    """Digital medal case: badges earned by each linked student (non-expired)."""
    from apps.people.models import Badge
    students = list(guardian_students(request.user))
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
            cm = b.criteria_met if isinstance(getattr(b, "criteria_met", None), dict) else {}
            setattr(b, "_evidence_report_term_id", cm.get("report_term_id"))
            setattr(b, "_evidence_syllabus_id", cm.get("syllabus_id"))
        student_badges.append((s, badges))
    return render(request, "parent/medal_case.html", {
        "student_badges": student_badges,
    })


@login_required
def unified_calendar(request: HttpRequest):
    """Phase 9: Unified calendar – school events and grading deadlines for teachers and parents."""
    year, _term = get_active_year_and_term()
    events = _merged_upcoming_events(year, school=getattr(request, "school", None))
    role = get_user_role(request.user)
    return render(request, "portal/unified_calendar.html", {
        "events": events,
        "site": get_effective_site_settings(request=request),
        "is_teacher": role == User.Role.TEACHER,
        "is_parent": role == User.Role.PARENT,
    })


def _qr_png_data_uri(value: str) -> str:
    """Generate an inline PNG data URI for QR rendering without external API calls."""
    try:
        import qrcode
        import qrcode.image.pil
    except ImportError:
        return ""
    image = qrcode.make(value, image_factory=qrcode.image.pil.PilImage)
    stream = BytesIO()
    image.save(stream, "PNG")
    encoded = base64.b64encode(stream.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@teacher_portal_required
@role_required(User.Role.TEACHER)
@login_required
def my_digital_id(request: HttpRequest):
    """Phase 4: Staff digital ID card (My ID) – school branding, photo, name, role, STAFF ID bar, QR."""
    from apps.people.badge_services import get_signed_id_token
    profile = getattr(request.user, "teacher_profile", None)
    name = request.user.get_full_name() or request.user.username
    role_label = "Teacher"
    if profile and profile.department:
        role_label = str(profile.department.name)
    photo = profile.profile_photo if profile and hasattr(profile, "profile_photo") and profile.profile_photo else None
    qr_token = get_signed_id_token("staff", request.user.pk)
    verify_url = request.build_absolute_uri(reverse("portal:badge_verify") + "?token=" + quote_plus(qr_token))
    qr_image_url = _qr_png_data_uri(verify_url)
    return render(request, "portal/digital_id_staff.html", {
        "site_name": get_site_display_name(request),
        "name": name,
        "role_label": role_label,
        "photo": photo,
        "qr_token": qr_token,
        "verify_url": verify_url,
        "qr_image_url": qr_image_url,
    })


@parent_portal_required
@role_required(User.Role.PARENT)
@login_required
def child_digital_id(request: HttpRequest, student_id: int):
    """Phase 4: Child's digital ID card – school branding, photo, name, grade/class, STUDENT ID bar, QR."""
    from apps.people.badge_services import get_signed_id_token
    link = StudentGuardian.objects.filter(
        guardian_user=request.user,
        student_id=student_id,
    ).select_related("student", "student__classroom", "student__academic_year").first()
    if not link:
        return HttpResponseForbidden("You are not authorized to view this student's ID.")
    student = link.student
    site = get_effective_site_settings(request=request)
    classroom = getattr(student, "classroom", None)
    grade_label = classroom.name if classroom else (getattr(student, "academic_year", None) and str(student.academic_year) or "—")
    photo = getattr(student, "profile_photo", None) and student.profile_photo or None
    qr_token = get_signed_id_token("student", student.pk)
    verify_url = request.build_absolute_uri(reverse("portal:badge_verify") + "?token=" + quote_plus(qr_token))
    qr_image_url = _qr_png_data_uri(verify_url)
    return render(request, "portal/digital_id_student.html", {
        "site_name": getattr(site, "site_name", None) or "School",
        "student": student,
        "name": student.get_full_name(),
        "grade_label": grade_label,
        "photo": photo,
        "qr_token": qr_token,
        "verify_url": verify_url,
        "qr_image_url": qr_image_url,
    })


@role_required(User.Role.ADMIN)
@xframe_options_sameorigin
def preview_student_syllabus(request: HttpRequest):
    synthetic_items = [
        {"title": "Physics Lab Experience", "description": "Hands-on labs with sensors and robotics demos.", "created_at": timezone.now()},
        {"title": "Digital Literacy Week", "description": "Interactive lesson on AI safety and documentation sharing.", "created_at": timezone.now()},
        {"title": "Design & Technology", "description": "Project-based curriculum with 2026 compliance mockups.", "created_at": timezone.now()},
    ]
    return render(request, "portal/preview/student_syllabus_preview.html", {
        "feature": {**PORTAL_FEATURES_META["syllabus"], "key": "syllabus"},
        "items": synthetic_items,
        "is_preview": True,
    })


@role_required(User.Role.ADMIN)
@require_POST
def preview_communication_test(request: HttpRequest):
    subject = request.POST.get("subject", "Preview notice for [Student Name]")
    body_template = request.POST.get("body", "Dear [Student Name], this is a preview of your [Specialty] update.")
    student = StudentProfile.objects.filter(is_active=True).select_related("classroom").first()
    tokens = {
        "Student Name": f"{student.first_name} {student.last_name}" if student else "Sample Learner",
        "Classroom": student.classroom.name if student and hasattr(student, "classroom") else "Sample Classroom",
        "Specialty": student.specialty.name if student and hasattr(student, "specialty") else "General Studies",
    }

    def fill_template(text):
        output = text
        for key, value in tokens.items():
            output = output.replace(f"[{key}]", value)
        return output

    filled_subject = fill_template(subject)
    filled_body = fill_template(body_template)

    Message.objects.create(
        sender=request.user,
        recipient=request.user,
        subject=f"{filled_subject} [Preview]",
        body=filled_body,
    )

    return JsonResponse({
        "status": "success",
        "subject": filled_subject,
        "body": filled_body[:200] + ("…" if len(filled_body) > 200 else ""),
    })


@parent_portal_required
@role_required(User.Role.PARENT)
def portal_stats(request: HttpRequest):
    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

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
            # Only show rankings for this parent's children (no other kids' personal info)
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
            specialty_rows = [row for row in specialty_rows if row.specialty.id in specialty_ids]

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
            # Only show improvement for this parent's children
            improvement_rows = [r for r in improvement_rows if r.student.id in parent_student_ids]

    return render(request, "portal/stats.html", {
        "year": year,
        "term": term,
        "top_students": top_students,
        "specialty_rows": specialty_rows,
        "weak_subjects": weak_subjects,
        "improvement_rows": improvement_rows,
        "widget_data": widget_data,
    })


def student_portal_grades(request: HttpRequest) -> HttpResponseRedirect:
    """Semantic alias for parent dashboard (grades overview)."""
    if not request.user.is_authenticated:
        return redirect_to_login(next=reverse("portal:parent_dashboard"))
    return redirect("portal:parent_dashboard")


def admissions_application_status(request: HttpRequest) -> HttpResponseRedirect:
    """Semantic alias for application status (re-uses parent dashboard context)."""
    if not request.user.is_authenticated:
        return redirect_to_login(next=reverse("portal:parent_dashboard"))
    return redirect("portal:parent_dashboard")


@login_required
def teacher_dashboard_alias(request: HttpRequest):
    """Render the teacher dashboard layout under the portal path."""
    return evals_teacher_dashboard(request)


@login_required
def teacher_workflow_alias(request: HttpRequest):
    """Render the teacher workflow center under the portal path."""
    return evals_teacher_workflow_center(request)


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_pay_history(request: HttpRequest):
    # RBAC: only the logged-in teacher's pay history (strict data isolation)
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile or profile.user_id != request.user.id:
        messages.error(request, "No teacher profile found. Ask an admin to complete your profile.")
        return redirect("evals:teacher_dashboard")

    pay_records = profile.pay_records.select_related("created_by").order_by("-effective_date", "-created_at")
    latest_pay = pay_records.filter(record_type=TeacherPayRecord.RecordType.PAY).first()
    raises_count = pay_records.filter(record_type=TeacherPayRecord.RecordType.RAISE).count()
    bonus_count = pay_records.filter(record_type=TeacherPayRecord.RecordType.BONUS).count()
    last_pay_amount = latest_pay.amount if latest_pay else None
    last_pay_date = latest_pay.effective_date if latest_pay else None
    payment_totals = Counter()
    for record in pay_records:
        payment_totals[record.record_type] += record.amount

    total_paid_amount = sum(
        record.amount for record in pay_records if record.record_type == TeacherPayRecord.RecordType.PAY
    )
    raise_total = sum(
        record.amount for record in pay_records if record.record_type == TeacherPayRecord.RecordType.RAISE
    )
    bonus_total = sum(
        record.amount for record in pay_records if record.record_type == TeacherPayRecord.RecordType.BONUS
    )

    attendance_logs = list(profile.attendance_logs.order_by("-date")[:30])
    streak = _compute_attendance_streak(attendance_logs)
    recent_absence = next((entry for entry in attendance_logs if entry.status in {
        TeacherAttendance.Status.ABSENT,
        TeacherAttendance.Status.LATE,
        TeacherAttendance.Status.ON_LEAVE,
    }), None)
    absence_alert = (
        f"Last absence recorded on {recent_absence.date}: {recent_absence.remarks or recent_absence.get_status_display()}."
        if recent_absence else None
    )

    hero = {
        "title": "Pay history",
        "subtitle": "Recent pay, raises, and stipends",
        "actions": [],
        "stats": [
            {"label": "Last pay", "value": last_pay_amount or "-", "meta": last_pay_date or "Not set"},
            {"label": "Next pay date", "value": profile.next_pay_date or "Not set", "meta": profile.pay_grade or "Pay grade"},
            {"label": "Raises", "value": raises_count, "meta": f"Bonuses: {bonus_count}"},
            {"label": "Streak", "value": streak, "meta": "days present"},
        ],
    }
    payment_type_breakdown = [
        {
            "label": TeacherPayRecord.RecordType(record_type).label,
            "amount": amount,
        }
        for record_type, amount in payment_totals.items()
    ]
    return render(request, "teacher/pay_history.html", {
        "hero": hero,
        "pay_records": pay_records,
        "teacher_profile": profile,
        "latest_pay": latest_pay,
        "raises_count": raises_count,
        "bonus_count": bonus_count,
        "payment_type_breakdown": payment_type_breakdown,
        "total_paid_amount": total_paid_amount,
        "raise_total": raise_total,
        "bonus_total": bonus_total,
        "attendance_logs": attendance_logs,
        "attendance_streak": streak,
        "attendance_alert": absence_alert,
    })


def _compute_attendance_streak(logs):
    today = timezone.localdate()
    log_lookup = {entry.date: entry for entry in logs}
    streak = 0
    cursor = today
    while True:
        entry = log_lookup.get(cursor)
        if entry and entry.status == TeacherAttendance.Status.PRESENT:
            streak += 1
            cursor -= timedelta(days=1)
            continue
        break
    return streak


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_leave(request: HttpRequest):
    # RBAC: only the logged-in teacher's leave requests (strict data isolation)
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile or profile.user_id != request.user.id:
        messages.error(request, "No teacher profile found. Ask an admin to complete your profile.")
        return redirect("evals:teacher_dashboard")

    form = TeacherLeaveForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        leave = form.save(commit=False)
        leave.teacher = profile
        leave.status = TeacherLeaveRequest.Status.PENDING
        leave.save()
        messages.success(request, "Leave request submitted for approval.")
        return redirect("portal:teacher_leave")

    leave_requests = profile.leave_requests.select_related("approver")
    hero = {
        "title": "Leave requests",
        "subtitle": "Submit a request and track approvals",
        "actions": [],
    }
    return render(request, "teacher/leave.html", {
        "hero": hero,
        "form": form,
        "leave_requests": leave_requests,
    })


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_attendance_view(request: HttpRequest):
    profile = getattr(request.user, "teacher_profile", None)
    if not profile:
        messages.error(request, "No teacher profile found. Ask an admin to complete your profile.")
        return redirect("evals:teacher_dashboard")

    logs = profile.attendance_logs.all()
    present = logs.filter(status=TeacherAttendance.Status.PRESENT).count()
    absences = logs.filter(status=TeacherAttendance.Status.ABSENT).count()
    late = logs.filter(status=TeacherAttendance.Status.LATE).count()
    hero = {
        "title": "Attendance",
        "subtitle": "Check-ins, check-outs, and leave days",
        "actions": [],
    }
    return render(request, "teacher/attendance.html", {
        "hero": hero,
        "logs": logs,
        "present": present,
        "absences": absences,
        "late": late,
        "export_url": reverse("portal:teacher_attendance_export"),
    })


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_attendance_export(request: HttpRequest):
    profile = getattr(request.user, "teacher_profile", None)
    if not profile:
        messages.error(request, "No teacher profile found. Ask an admin to complete your profile.")
        return redirect("evals:teacher_dashboard")

    logs = profile.attendance_logs.order_by("-date")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="teacher_attendance.csv"'
    writer = csv.writer(response)
    writer.writerow(["Date", "Status", "Check-in", "Check-out", "Remarks"])
    for entry in logs:
        writer.writerow([
            entry.date,
            entry.get_status_display(),
            entry.check_in or "",
            entry.check_out or "",
            entry.remarks or "",
        ])
    return response


@login_required
def take_student_attendance(request: HttpRequest):
    """Student roll call: date + classroom, default present, one save. Requires attendance.manage."""
    if not getattr(request.user, "has_feature_permission", lambda _: False)("attendance.manage"):
        return HttpResponseForbidden("You do not have permission to take student attendance.")
    year, _term = get_active_year_and_term()
    classrooms = list(Classroom.objects.filter(academic_year=year).order_by("name")) if year else []
    today = timezone.localdate()
    date_str = request.GET.get("date") or request.POST.get("date") or today.isoformat()
    classroom_id = request.GET.get("classroom") or request.POST.get("classroom")
    try:
        att_date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        att_date = today
    existing = {}
    students = []
    classroom_obj = None
    if classroom_id and classrooms:
        classroom_obj = next((c for c in classrooms if str(c.id) == str(classroom_id)), None)
        if classroom_obj:
            students = list(classroom_obj.students.filter(status__in=(StudentProfile.Status.NEW, StudentProfile.Status.RETURNING, StudentProfile.Status.PROBATION)).order_by("last_name", "first_name"))
            if students and att_date:
                for a in Attendance.objects.filter(classroom=classroom_obj, date=att_date).select_related("student"):
                    existing[a.student_id] = a.status
    if request.method == "POST" and classroom_obj and students:
        for s in students:
            status = (request.POST.get(f"status_{s.id}") or "").strip() or Attendance.Status.PRESENT
            if status not in {c[0] for c in Attendance.Status.choices}:
                status = Attendance.Status.PRESENT
            Attendance.objects.update_or_create(
                student=s, classroom=classroom_obj, date=att_date,
                defaults={"status": status},
            )
        messages.success(request, f"Attendance saved for {len(students)} students.")
        return redirect(f"{reverse('portal:take_student_attendance')}?date={att_date.isoformat()}&classroom={classroom_obj.id}")
    status_choices = list(Attendance.Status.choices)
    students_with_status = [{"student": s, "status": existing.get(s.id, Attendance.Status.PRESENT)} for s in students]
    hero = {"title": "Take student attendance", "subtitle": "Select date and class, then mark present/absent/late.", "actions": []}
    return render(request, "portal/roll_call_student.html", {
        "hero": hero,
        "classrooms": classrooms,
        "date_value": att_date.isoformat(),
        "classroom_id": classroom_id or "",
        "classroom": classroom_obj,
        "students_with_status": students_with_status,
        "status_choices": status_choices,
        "Attendance": Attendance,
    })


@login_required
def record_teacher_attendance(request: HttpRequest):
    """Teacher roll call: date, list of teachers, default present, one save. Requires attendance.manage."""
    if not getattr(request.user, "has_feature_permission", lambda _: False)("attendance.manage"):
        return HttpResponseForbidden("You do not have permission to record teacher attendance.")
    teachers = list(TeacherProfile.objects.select_related("user").order_by("user__last_name", "user__first_name"))
    today = timezone.localdate()
    date_str = request.GET.get("date") or request.POST.get("date") or today.isoformat()
    try:
        att_date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        att_date = today
    existing = {e.teacher_id: e.status for e in TeacherAttendance.objects.filter(date=att_date)}
    if request.method == "POST" and teachers:
        for t in teachers:
            status = (request.POST.get(f"status_{t.id}") or "").strip() or TeacherAttendance.Status.PRESENT
            if status not in {c[0] for c in TeacherAttendance.Status.choices}:
                status = TeacherAttendance.Status.PRESENT
            TeacherAttendance.objects.update_or_create(
                teacher=t, date=att_date,
                defaults={"status": status},
            )
        messages.success(request, f"Attendance saved for {len(teachers)} teachers.")
        return redirect(f"{reverse('portal:record_teacher_attendance')}?date={att_date.isoformat()}")
    status_choices = list(TeacherAttendance.Status.choices)
    teachers_with_status = [{"teacher": t, "status": existing.get(t.id, TeacherAttendance.Status.PRESENT)} for t in teachers]
    hero = {"title": "Take teacher attendance", "subtitle": "Select date and mark each teacher present, absent, late, or on leave.", "actions": []}
    return render(request, "portal/roll_call_teacher.html", {
        "hero": hero,
        "teachers_with_status": teachers_with_status,
        "date_value": att_date.isoformat(),
        "status_choices": status_choices,
        "TeacherAttendance": TeacherAttendance,
    })


@login_required
def seating_chart_view(request: HttpRequest):
    """W4-2: Seating chart placeholder — view or link for class layout. Optional ?classroom=id."""
    flags = get_effective_flags(request)
    if not flags.get("enable_seating_chart_beta"):
        raise Http404("Seating chart is not enabled.")
    if not getattr(request.user, "has_feature_permission", lambda _: False)("attendance.manage"):
        return HttpResponseForbidden("You do not have permission to view seating chart.")
    year, _term = get_active_year_and_term()
    classrooms = list(Classroom.objects.filter(academic_year=year).order_by("name")) if year else []
    classroom_id = request.GET.get("classroom")
    classroom_obj = None
    if classroom_id and classrooms:
        classroom_obj = next((c for c in classrooms if str(c.id) == str(classroom_id)), None)
    hero = {"title": "Seating chart", "subtitle": "Class layout view for roll call and attendance.", "actions": []}
    return render(request, "portal/seating_chart.html", {
        "hero": hero,
        "classrooms": classrooms,
        "classroom": classroom_obj,
        "classroom_id": classroom_id or "",
    })


def _cahier_enabled(request=None):
    flags = get_effective_flags(request)
    if not flags.get("enable_cahier_de_texte"):
        return False
    # Feature gate via Policy Registry (runtime constitution)
    if request and getattr(request, "school", None):
        from apps.policies.policy_registry import get_effective_policy
        result = get_effective_policy(request.school, user=getattr(request, "user", None), capability="cahier_de_texte")
        if not result.get("enabled", False):
            return False
    return True


@login_required
@teacher_portal_required
@role_required(User.Role.TEACHER)
def cahier_list(request: HttpRequest):
    """List and add Cahier de Texte entries (when feature enabled)."""
    if not _cahier_enabled(request):
        return HttpResponseForbidden("Cahier de Texte is not enabled.")
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile:
        return redirect("portal:teacher_dashboard_alias")
    from apps.evals.models import TeacherAssignment
    year, _ = get_active_year_and_term()
    assignments_qs = SubjectAssignment.objects.none()
    if year:
        sa_ids = TeacherAssignment.objects.filter(
            teacher=profile, is_active=True,
            subject_assignment__academic_year=year,
        ).values_list("subject_assignment_id", flat=True)
        assignments_qs = SubjectAssignment.objects.filter(pk__in=sa_ids).select_related("classroom", "subject", "specialty")
    entries = CahierDeTexteEntry.objects.filter(teacher=profile).select_related("subject_assignment__classroom", "subject_assignment__subject").order_by("-entry_date")[:50]
    form = CahierDeTexteEntryForm(request.POST or None)
    form.fields["subject_assignment"].queryset = assignments_qs
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.teacher = profile
        obj.status = CahierDeTexteEntry.Status.SUBMITTED
        obj.save()
        messages.success(request, "Entry submitted for visa.")
        return redirect("portal:cahier_list")
    flags = get_effective_flags(request)
    curriculum_nodes = []
    if flags.get("cahier_syllabus_integration") == "national_progression":
        from apps.academics.models import CurriculumNode
        curriculum_nodes = list(
            CurriculumNode.objects.filter(level_type=CurriculumNode.LevelType.TOPIC)
            .order_by("standard", "order", "code")
            .values_list("code", "title")[:500]
        )
    hero = {"title": "Cahier de Texte", "subtitle": "Lesson diary entries", "actions": []}
    return render(request, "portal/cahier_list.html", {
        "hero": hero, "entries": entries, "form": form, "curriculum_nodes": curriculum_nodes,
    })


@login_required
def cahier_verify_list(request: HttpRequest):
    """List SUBMITTED entries for supervisor visa (cahier.verify or CENSOR)."""
    if not _cahier_enabled(request):
        return HttpResponseForbidden("Cahier de Texte is not enabled.")
    can_verify = getattr(request.user, "has_feature_permission", lambda _: False)("cahier.verify") or get_user_role(request.user) == "CENSOR"
    if not can_verify:
        return HttpResponseForbidden("You do not have permission to verify Cahier entries.")
    entries = CahierDeTexteEntry.objects.filter(
        status=CahierDeTexteEntry.Status.SUBMITTED,
    ).select_related("teacher__user", "subject_assignment__classroom", "subject_assignment__subject").order_by("entry_date")[:100]
    hero = {"title": "Cahier de Texte – Verification", "subtitle": "Visa or request revisions", "actions": []}
    return render(request, "portal/cahier_verify_list.html", {"hero": hero, "entries": entries})


@require_POST
@login_required
def cahier_visa(request: HttpRequest, entry_id: int):
    """Set entry to VISED."""
    if not _cahier_enabled(request):
        return HttpResponseForbidden("Cahier de Texte is not enabled.")
    if not (getattr(request.user, "has_feature_permission", lambda _: False)("cahier.verify") or get_user_role(request.user) == "CENSOR"):
        return HttpResponseForbidden("You do not have permission to verify.")
    entry = get_object_or_404(CahierDeTexteEntry, pk=entry_id, status=CahierDeTexteEntry.Status.SUBMITTED)
    entry.status = CahierDeTexteEntry.Status.VISED
    entry.verified_by = request.user
    entry.verified_at = timezone.now()
    entry.save(update_fields=["status", "verified_by", "verified_at", "updated_at"])
    messages.success(request, "Entry vised.")
    return redirect("portal:cahier_verify_list")


@require_POST
@login_required
def cahier_request_revisions(request: HttpRequest, entry_id: int):
    """Set entry to REVISIONS_REQUESTED."""
    if not _cahier_enabled(request):
        return HttpResponseForbidden("Cahier de Texte is not enabled.")
    if not (getattr(request.user, "has_feature_permission", lambda _: False)("cahier.verify") or get_user_role(request.user) == "CENSOR"):
        return HttpResponseForbidden("You do not have permission to verify.")
    entry = get_object_or_404(CahierDeTexteEntry, pk=entry_id, status=CahierDeTexteEntry.Status.SUBMITTED)
    entry.status = CahierDeTexteEntry.Status.REVISIONS_REQUESTED
    entry.save(update_fields=["status", "updated_at"])
    messages.success(request, "Revisions requested.")
    return redirect("portal:cahier_verify_list")


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_timetable(request: HttpRequest):
    """Show the logged-in teacher's timetable from published schedule (current term)."""
    from apps.academics.scheduling import Schedule, ScheduleEntry
    year, term = get_active_year_and_term()
    schedule = None
    entries = []
    if year and term:
        schedule = (
            Schedule.objects.filter(academic_year=year, term=term, status="PUBLISHED")
            .order_by("-published_at")
            .first()
        )
        if not schedule:
            schedule = (
                Schedule.objects.filter(academic_year=year, term=term)
                .order_by("-generated_at")
                .first()
            )
        if schedule:
            entries = (
                ScheduleEntry.objects.filter(
                    schedule=schedule, teacher=request.user, is_cancelled=False
                )
                .select_related("classroom", "subject", "room", "time_slot")
                .order_by("time_slot__day_of_week", "time_slot__start_time")
            )
    by_day = {}
    for e in entries:
        day = e.time_slot.get_day_of_week_display()
        by_day.setdefault(day, []).append(e)
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_day_ordered = [(d, by_day.get(d, [])) for d in days_order if by_day.get(d)]
    hero = {
        "title": "My Timetable",
        "subtitle": f"{term.custom_label or term.name if term else 'No term'} – {year.name if year else 'No year'}" if (year and term) else "No active term set.",
        "actions": [],
    }
    return render(
        request,
        "teacher/timetable.html",
        {
            "hero": hero,
            "schedule": schedule,
            "entries": entries,
            "by_day_ordered": by_day_ordered,
            "year": year,
            "term": term,
        },
    )


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_lesson_notes(request: HttpRequest):
    """Lesson notes upload and list. RBAC: current teacher only."""
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.error(request, "No teacher profile found.")
        return redirect("portal:teacher_dashboard_alias")
    plans = LessonPlan.objects.filter(teacher=profile).prefetch_related("attachments").order_by("-week_start_date")[:50]
    form = LessonPlanUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.teacher = profile
        obj.save()
        messages.success(request, "Lesson plan uploaded.")
        return redirect("portal:teacher_lesson_notes")
    hero = {"title": "Lesson Notes", "subtitle": "Upload weekly lesson plans (PDF)", "actions": []}
    return render(request, "teacher/lesson_notes.html", {"hero": hero, "plans": plans, "form": form})


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_lesson_plan_add_attachment(request: HttpRequest, lesson_plan_id: int):
    """Add a resource attachment to an existing lesson plan (Wave 6)."""
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.error(request, "No teacher profile found.")
        return redirect("portal:teacher_dashboard_alias")
    plan = get_object_or_404(LessonPlan, pk=lesson_plan_id, teacher=profile)
    if request.method == "POST":
        form = LessonPlanAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            att = form.save(commit=False)
            att.lesson_plan = plan
            att.save()
            messages.success(request, "Resource attached.")
            return redirect("portal:teacher_lesson_notes")
    else:
        form = LessonPlanAttachmentForm()
    hero = {"title": "Add resource", "subtitle": f"Attach a file to « {plan.title } »", "actions": []}
    return render(request, "teacher/lesson_plan_add_attachment.html", {"hero": hero, "plan": plan, "form": form})


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_wellness(request: HttpRequest):
    """Teacher wellness / wellbeing: reminder and link to resources (Wave 6)."""
    hero = {"title": "Wellness", "subtitle": "Take care of yourself", "actions": []}
    return render(request, "teacher/wellness.html", {"hero": hero})


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_hr_status(request: HttpRequest):
    """HR & Status: employment details and attestation. RBAC: current teacher only."""
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.error(request, "No teacher profile found.")
        return redirect("portal:teacher_dashboard_alias")
    attestation_valid = getattr(profile, "attestation_valid", None)
    if attestation_valid is None:
        attestation_valid = True
    hero = {"title": "HR & Status", "subtitle": "Employment and attestation", "actions": []}
    return render(request, "teacher/hr_status.html", {
        "hero": hero,
        "teacher_profile": profile,
        "attestation_valid": attestation_valid,
    })


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_disciplinary(request: HttpRequest):
    """Disciplinary portal: refer incidents to discipline master. RBAC: teacher only."""
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.error(request, "No teacher profile found.")
        return redirect("portal:teacher_dashboard_alias")
    hero = {"title": "Disciplinary", "subtitle": "Refer incidents to the Discipline Master", "actions": []}
    return render(request, "teacher/disciplinary.html", {"hero": hero, "teacher_profile": profile})


def _can_manage_discipline(user):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = get_user_role(user)
    if role in ("DISCIPLINE_MASTER", "CENSOR"):
        return True
    return getattr(user, "has_feature_permission", lambda _: False)("discipline.manage")


@login_required
def discipline_incidents_list(request: HttpRequest):
    """List disciplinary incidents. RBAC: DISCIPLINE_MASTER, CENSOR, or discipline.manage."""
    if not _can_manage_discipline(request.user):
        return HttpResponseForbidden("You do not have permission to view disciplinary incidents.")
    from apps.academics.models import Incident
    incidents_qs = Incident.objects.select_related("school", "student", "teacher", "created_by")
    school = getattr(request, "school", None)
    if school is not None:
        incidents_qs = incidents_qs.filter(school=school)
    incidents = incidents_qs.order_by("-date", "-created_at")[:100]
    hero = {"title": "Disciplinary Incidents", "subtitle": "View and manage incidents (tardiness, behavior). Parents are notified when requested.", "actions": []}
    return render(request, "staff/discipline_incidents.html", {"hero": hero, "incidents": incidents})


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_training_log(request: HttpRequest):
    """Training log: in-service / professional development. RBAC: current teacher only."""
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.error(request, "No teacher profile found.")
        return redirect("portal:teacher_dashboard_alias")
    entries = TeacherTrainingEntry.objects.filter(teacher=profile).order_by("-date")[:50]
    form = TeacherTrainingEntryForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.teacher = profile
        obj.save()
        messages.success(request, "Training entry added.")
        return redirect("portal:teacher_training_log")
    hero = {"title": "Training Log", "subtitle": "In-service training and professional development", "actions": []}
    return render(request, "teacher/training_log.html", {"hero": hero, "entries": entries, "form": form})


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_attendance_discipline(request: HttpRequest):
    """Attendance & Discipline: list absences/tardies and submit justification. RBAC: linked children only."""
    from apps.academics.models import Attendance
    links = guardian_student_links(request.user, results_only=False)
    student_ids = [link.student_id for link in links]
    absences = []
    if student_ids:
        absences = list(
            Attendance.objects.filter(
                student_id__in=student_ids,
                status__in=[Attendance.Status.ABSENT, Attendance.Status.LATE],
            )
            .select_related("student", "classroom")
            .order_by("-date")[:100]
        )
    justifications = AttendanceJustification.objects.filter(guardian=request.user).select_related("student").order_by("-attendance_date")[:50]
    form = AttendanceJustificationForm(request.POST or None, request.FILES or None)
    form.fields["student"].queryset = StudentProfile.objects.filter(id__in=student_ids)
    form.fields["student"].required = True
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.guardian = request.user
        obj.student = form.cleaned_data["student"]
        if obj.student_id not in student_ids:
            return HttpResponseForbidden("You can only submit for your linked children.")
        obj.save()
        messages.success(request, "Justification submitted.")
        return redirect("portal:parent_attendance_discipline")
    hero = {"title": "Attendance & Discipline", "subtitle": "View absences and submit justifications", "actions": []}
    return render(request, "parent/attendance_discipline.html", {
        "hero": hero,
        "absences": absences,
        "justifications": justifications,
        "form": form,
        "children": [link.student for link in links],
    })


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_child_results(request: HttpRequest, student_id: int):
    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term configured yet.")

    # ensure parent is linked to this student
    link = StudentGuardian.objects.filter(
        guardian_user=request.user,
        student_id=student_id,
        can_view_results=True
    ).select_related("student").first()

    if not link:
        return HttpResponseForbidden("You are not authorized to view this student's results.")

    student = link.student

    # Publish gate: parents only see results if published (school-wide OR class publish)
    published = is_term_published(year.id, term.id, student.classroom_id)
    terms = terms_for_student(year, student.classroom)
    annual_published = are_terms_published(year.id, [t.id for t in terms], student.classroom_id)
    if not published:
        return render(request, "parent/results.html", {
            "student": student,
            "year": year,
            "term": term,
            "published": False,
            "annual_published": annual_published,
            "rows": [],
            "totals": None,
        })

    report_ctx = term_report_context(student, year, term)

    total_coef = sum(row.get("coef") or 0 for row in report_ctx["rows"])
    totals = {
        "total_coef": total_coef,
        "overall": report_ctx["summary"].get("average"),
    }

    completed_count = sum(1 for row in report_ctx["rows"] if row.get("complete"))
    completion_pct = 0
    total_rows = len(report_ctx["rows"])
    if total_rows:
        completion_pct = int(round((completed_count / total_rows) * 100))
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


def _whatsapp_invite_link(request: HttpRequest) -> str | None:
    school = getattr(request, "school", None)
    number = None
    try:
        from apps.siteconfig.integration_registry import resolve_active_integration

        record = resolve_active_integration(school, "whatsapp") if school is not None else None
        if record and record.is_active:
            number = (
                record.config.get("phone")
                or record.config.get("whatsapp_number")
                or record.config.get("support_number")
            )
    except PORTAL_SOFT_FAILURES:
        number = None
    if not number:
        site = get_effective_site_settings(request=request)
        number = getattr(site, "whatsapp_admissions_number", None) or getattr(site, "whatsapp_support_number", None)
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
        student = guardian_link.student
        student_updates = form.student_updates()
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
    
    Steps:
    1. Identify child (admission number + relationship) → shows student confirmation
    2. Contact & permissions (phone, preferred contact, can_view_results/finance)
    3. Optional details (DOB, place of birth, joined term/date, address, referral code)
    
    Uses session to persist form data between steps.
    """
    site = get_effective_site_settings(request=request)
    session_key = "link_child_wizard_data"
    wizard_data = request.session.get(session_key, {})
    step = int(request.GET.get("step", "1"))
    
    # Handle step navigation
    if request.method == "POST":
        action = request.POST.get("action", "next")
        
        if action == "back":
            step = max(1, step - 1)
            request.session[session_key] = wizard_data
            return redirect(f"{request.path}?step={step}")
        
        # Save current step data to session
        for key, value in request.POST.items():
            if key not in ("csrfmiddlewaretoken", "action", "step"):
                wizard_data[key] = value
        
        request.session[session_key] = wizard_data
        
        # Validate current step
        policy = get_policy_for_request(request)
        form = LinkChildForm(
            data=request.POST,
            guardian_user=request.user,
            policy=policy,
            school_code=site.school_code,
        )
        
        if step == 1:
            # Step 1: Validate admission number and relationship
            admission = request.POST.get("admission_number", "").strip()
            relationship = request.POST.get("relationship", "")
            
            has_errors = False
            
            # Basic validation - both fields required
            if not admission:
                form.add_error("admission_number", forms.ValidationError("Admission number is required."))
                has_errors = True
            if not relationship:
                form.add_error("relationship", forms.ValidationError("Relationship is required."))
                has_errors = True
            
            # If we have an admission number, validate it
            if admission and relationship and not has_errors:
                try:
                    student = StudentProfile.objects.select_related(
                        "academic_year", "classroom", "specialty"
                    ).get(admission_number__iexact=admission)
                    if not student.is_active:
                        form.add_error("admission_number", forms.ValidationError("This student profile is inactive."))
                    elif StudentGuardian.objects.filter(
                        guardian_user=request.user,
                        student=student,
                    ).exists():
                        form.add_error("admission_number", forms.ValidationError("You are already linked to this student."))
                    else:
                        # Valid, move to step 2
                        step = 2
                        request.session[session_key] = wizard_data
                        return redirect(f"{request.path}?step={step}")
                except StudentProfile.DoesNotExist:
                    form.add_error("admission_number", forms.ValidationError("No student found with that admission number."))
                except PORTAL_SOFT_FAILURES as e:
                    # Log the error but show a user-friendly message.
                    logger.error(f"Error validating admission number: {e}", exc_info=True)
                    form.add_error("admission_number", forms.ValidationError("An error occurred. Please try again or contact support."))
        elif step == 2:
            # Step 2: Contact & permissions - always valid (fields are optional or have defaults)
            step = 3
            request.session[session_key] = wizard_data
            return redirect(f"{request.path}?step={step}")
        elif step == 3:
            # Step 3: Final step - validate and save
            if form.is_valid():
                guardian_link = form.save()
                student = guardian_link.student
                student_updates = form.student_updates()
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
                
                # Clear wizard session
                if session_key in request.session:
                    del request.session[session_key]
                
                return redirect("portal:parent_dashboard")
    
    # Build form with session data for current step
    form_data = {}
    if wizard_data:
        form_data.update(wizard_data)
    
    policy = get_policy_for_request(request)
    form = LinkChildForm(
        data=form_data if request.method == "GET" else None,
        guardian_user=request.user,
        policy=policy,
        school_code=site.school_code,
    )
    
    # Pre-populate form from session
    if wizard_data:
        for key, value in wizard_data.items():
            if key in form.fields:
                form.fields[key].initial = value
    
    # Get student info if admission number was validated
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
    
    # Auto-fill parent fields from user if not in session
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
