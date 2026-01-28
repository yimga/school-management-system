from django.shortcuts import render, get_object_or_404, redirect
from datetime import timedelta
from django.http import JsonResponse, HttpResponseForbidden, HttpRequest, Http404, HttpResponse, HttpResponseRedirect
from django.utils.safestring import mark_safe
from collections import Counter
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse
import uuid
from decimal import Decimal
from django.db.models import Sum
from urllib.parse import quote_plus
import csv

from apps.accounts.decorators import (
    role_required,
    parent_portal_required,
    teacher_portal_required,
)
from apps.evals.views import teacher_dashboard as evals_teacher_dashboard
from apps.accounts.models import User
from apps.people.models import (
    StudentGuardian,
    StudentProfile,
    TeacherProfile,
    TeacherPayRecord,
    TeacherLeaveRequest,
    TeacherAttendance,
)
from apps.academics.models import Term
from apps.academics.services import get_active_year_and_term
from apps.evals.models import Evaluation
from apps.finance.models import Invoice, PaymentReminder, ReferralReward, Notification
from apps.finance.services import generate_payment_link
from apps.reports.services import (
    are_terms_published,
    is_term_published,
    terms_for_student,
    term_report_context,
)
import json

from apps.siteconfig.models import (
    Integration,
    SiteSettings,
    default_portal_features,
    resolve_dashboard_widgets,
    filter_portal_items,
    default_backend_feature_flags,
)
from apps.siteconfig.models_dashboard import get_dashboard_widget_metadata
from apps.siteconfig.dashboard_views import load_dashboard_layout_settings
from apps.siteconfig.dashboard_views import _can_customize
from apps.analytics.services import (
    student_improvements,
    specialty_pass_rates,
    subject_weaknesses,
    term_rankings,
)
from .models import PortalFeatureItem, PendingGuardianInvite
from .services import (
    parent_dashboard_widget_data,
    award_referral_reward,
    link_guardian_via_invite,
    guardian_student_links,
    guardian_students,
    class_announcements_for_parent,
    class_threads_for_parent,
)
from .forms import LinkChildForm, ClaimInviteForm, TeacherLeaveForm
from apps.communication.models import Message
from django.views.decorators.http import require_POST

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


def _portal_features_status() -> list[dict]:
    site = SiteSettings.get_solo()
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

    flags = {**default_backend_feature_flags(), **(SiteSettings.get_solo().backend_feature_flags or {})}
    require_finance_opt_in = bool(flags.get("require_guardian_finance_opt_in"))
    finance_link_count = finance_links.count()
    guardian_link_count = links.count()
    can_request_finance_access = require_finance_opt_in and guardian_link_count > finance_link_count

    portal_features = _portal_features_status()
    students = [link.student for link in links]
    finance_students = [link.student for link in finance_links]
    can_view_results = bool(students)
    can_view_finance = bool(finance_students)
    
    # Widget data is now cached internally for 5 minutes
    widget_data = parent_dashboard_widget_data(students)
    if can_view_finance:
        finance_widget = parent_dashboard_widget_data(finance_students).get("finance", {})
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
    finance_total = widget_data["finance"].get("total_due") or Decimal("0.00")
    finance_paid = widget_data["finance"].get("paid") or Decimal("0.00")
    finance_paid_pct = int((finance_paid / finance_total) * 100) if finance_total else 0

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
        })
    
    preference = getattr(request.user, "preferences", None)
    display_widgets = resolve_dashboard_widgets(getattr(request.user, "role", None), preference)

    site = SiteSettings.get_solo()
    role = getattr(request.user, "role", None)
    portal_quick_actions = filter_portal_items(site.portal_quick_actions, role)
    portal_announcements = filter_portal_items(site.portal_announcements, role)
    portal_recent_grades = filter_portal_items(site.portal_recent_grades, role)
    portal_upcoming_assessments = filter_portal_items(site.portal_upcoming_assessments, role)
    class_announcements = class_announcements_for_parent(request.user, students)
    class_threads = class_threads_for_parent(request.user, limit=3)
    
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
    if can_view_results:
        hero["actions"].insert(0, {"label": "View Results", "url": "#children"})
        hero["actions"].insert(1, {"label": "View Attendance", "url": reverse("portal:portal_stats")})
    if can_view_finance:
        hero["stats"].append({"label": "Balance", "value": widget_data["finance"]["balance"], "meta": "Outstanding fees"})
        hero["stats"].append({"label": "Reminders", "value": reminders_count, "meta": "Pending notices"})
        hero["status_pills"].insert(1, {"label": "Reminders", "value": reminders_count, "meta": "Pending notices"})
        hero["actions"].append({"label": "Pay Fees", "url": reverse("portal:parent_finance")})

    dashboard_settings = load_dashboard_layout_settings(request.user, "parent")
    available_sidebar_items = [
        {"id": "parent-home", "label": "Parent Home", "url": reverse("portal:parent_dashboard"), "icon": "bi-house"},
        {"id": "parent-finance", "label": "Finance", "url": reverse("portal:parent_finance"), "icon": "bi-cash-stack"},
        {"id": "parent-stats", "label": "Portal Stats", "url": reverse("portal:portal_stats"), "icon": "bi-graph-up"},
        {"id": "parent-links", "label": "Link a Child", "url": reverse("portal:link_child"), "icon": "bi-link-45deg"},
    ]
    dashboard_layout_url = reverse("api:dashboard-layout", kwargs={"page": "parent"})
    allow_custom_layout = _can_customize(request.user)

    return render(request, "parent/dashboard.html", {
        "links": links,
        "can_view_results": can_view_results,
        "can_view_finance": can_view_finance,
        "portal_features": portal_features,
        "widget_data": widget_data,
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
        "finance_paid_pct": finance_paid_pct,
        "finance_total": finance_total,
        "finance_paid": finance_paid,
        "allow_custom_layout": allow_custom_layout,
        "dashboard_settings": dashboard_settings,
        "dashboard_layout_url": dashboard_layout_url,
        "available_sidebar_items": available_sidebar_items,
        "widget_meta_json": mark_safe(json.dumps(get_dashboard_widget_metadata())),
        "finance_access_banner": finance_access_banner,
        "finance_requests_count": finance_requests_qs.count(),
        "finance_request_notifications": finance_requests_qs[:5],
        "finance_request_link": finance_request_link,
    })


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_finance(request: HttpRequest):
    all_links = guardian_student_links(request.user)
    finance_links = guardian_student_links(request.user, finance_only=True)

    if not all_links.exists():
        messages.info(request, "Link a student first to view finance details.")
        return redirect("portal:link_child")

    flags = {**default_backend_feature_flags(), **(SiteSettings.get_solo().backend_feature_flags or {})}
    require_finance_opt_in = bool(flags.get("require_guardian_finance_opt_in"))
    finance_link_count = finance_links.count()
    guardian_link_count = all_links.count()
    finance_access_granted = finance_link_count > 0
    can_request_finance_access = require_finance_opt_in and guardian_link_count > finance_link_count
    finance_request_url = reverse("finance:finance_request_access")
    links = finance_links if (finance_access_granted or not require_finance_opt_in) else all_links

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

    if require_finance_opt_in and not finance_access_granted:
        students = []
        invoices_qs = Invoice.objects.none()
        aggregates = {"total_due": Decimal("0.00"), "balance": Decimal("0.00")}
        overdue_count = 0
    else:
        students = guardian_students(request.user, finance_only=True)
        invoices_qs = (
            Invoice.objects.filter(student__in=students)
            .exclude(status=Invoice.Status.DRAFT)
            .select_related("student", "academic_year")
            .prefetch_related("payments")
            .order_by("-issued_date")
        )
        aggregates = invoices_qs.aggregate(
            total_due=Sum("total_amount"),
            balance=Sum("balance_amount"),
        )
        overdue_count = invoices_qs.filter(status=Invoice.Status.OVERDUE).count()

    total_due = aggregates.get("total_due") or Decimal("0.00")
    balance = aggregates.get("balance") or Decimal("0.00")
    paid = total_due - balance

    payment_method_counts = Counter()
    invoice_rows = []
    reminders = []
    for inv in invoices_qs:
        link = generate_payment_link(inv)
        payments = list(inv.payments.all())
        receipt = payments[0] if payments else None
        if payments:
            for payment in payments:
                payment_method_counts[payment.get_method_display()] += 1
        invoice_rows.append(
            {
                "invoice": inv,
                "payment_link": link,
                "receipt_url": reverse("finance:invoice_receipt", args=(inv.id, receipt.id)) if receipt else None,
                "preferred_method": inv.get_preferred_payment_method_display() or "Any",
                "attachment_url": inv.attachment.url if inv.attachment else None,
                "recent_payment": receipt,
            }
        )
        reminder = getattr(inv, "reminder", None)
        if reminder and reminder.is_active:
            reminders.append(
                {
                    "invoice": inv,
                    "reminder": reminder,
                    "payment_link": link,
                }
            )

    referral_qs = ReferralReward.objects.filter(guardian__guardian_user=request.user)
    referral_total = referral_qs.filter(status=ReferralReward.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    referral_pending = referral_qs.filter(status=ReferralReward.Status.PENDING).count()
    hero = {
        "title": "Finances",
        "subtitle": "Balances, invoices, and secure payment links",
        "stats": [
            {"label": "Total due", "value": total_due},
            {"label": "Paid", "value": paid},
            {"label": "Outstanding", "value": balance},
            {"label": "Overdue", "value": overdue_count},
            {"label": "Reminders", "value": len(reminders), "meta": "Queued notices"},
            {"label": "Referral credits", "value": f"{referral_total:.2f}", "meta": "Approved bonuses"},
        ],
    }

    attachment_count = invoices_qs.filter(attachment__isnull=False).count()
    payment_method_summary = [
        {"method": method, "count": count}
        for method, count in payment_method_counts.most_common()
    ]

    return render(
        request,
        "parent/finance.html",
        {
            "links": links,
            "hero": hero,
            "invoice_rows": invoice_rows,
            "total_due": total_due,
            "balance": balance,
            "paid": paid,
            "overdue_count": overdue_count,
            "reminders": reminders,
            "attachment_count": attachment_count,
            "payment_method_summary": payment_method_summary,
            "referral_total": referral_total,
            "referral_pending": referral_pending,
            "finance_access_required": require_finance_opt_in,
            "finance_access_granted": finance_access_granted,
            "guardian_link_count": guardian_link_count,
            "finance_guardian_count": finance_link_count,
            "can_request_finance_access": can_request_finance_access,
            "finance_request_url": finance_request_url,
        },
    )


@parent_portal_required
@role_required(User.Role.PARENT)
def claim_invite(request: HttpRequest, token: str | None = None):
    """
    Claim a pending guardian invite using a token and link the student to the logged-in parent.
    """
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
        if reward and reward.amount > Decimal("0.00"):
            messages.info(
                request,
                f"Referral bonus of {reward.amount:.2f} will be reviewed by finance.",
            )
        return redirect("portal:parent_dashboard")

    return render(request, "parent/claim_invite.html", {"form": form})


@parent_portal_required
@role_required(User.Role.PARENT)
def portal_feature_page(request: HttpRequest, feature: str):
    available = _portal_features_status()
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
    site = SiteSettings.get_solo()
    role = getattr(request.user, "role", None)
    if role == User.Role.PARENT and not site.enable_parent_portal:
        return HttpResponseForbidden("Parent portal is disabled.")
    if role == User.Role.TEACHER and not site.enable_teacher_portal:
        return HttpResponseForbidden("Teacher portal is disabled.")

    items = PortalFeatureItem.objects.filter(
        feature=PortalFeatureItem.Feature.SYLLABUS,
        is_active=True,
    ).select_related("created_by").order_by("-created_at")

    return render(request, "portal/syllabus.html", {
        "feature": {**PORTAL_FEATURES_META["syllabus"], "key": "syllabus"},
        "items": items,
    })


@role_required(User.Role.ADMIN)
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

    site = SiteSettings.get_solo()
    pass_mark = site.pass_mark
    weak_threshold = site.weak_subject_threshold
    improvement_delta = site.improvement_delta_threshold

    students = guardian_students(request.user, results_only=True)
    widget_data = parent_dashboard_widget_data(students)

    top_students = []
    specialty_rows = []
    weak_subjects = []
    improvement_rows = []

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
            top_students.extend(classroom_term_rankings(classroom, term)[:3])

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
    return redirect("portal:parent_dashboard")


def admissions_application_status(request: HttpRequest) -> HttpResponseRedirect:
    """Semantic alias for application status (re-uses parent dashboard context)."""
    return redirect("portal:parent_dashboard")


def teacher_dashboard_alias(request: HttpRequest):
    """Render the teacher dashboard layout under the portal path."""
    return evals_teacher_dashboard(request)


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_pay_history(request: HttpRequest):
    profile = getattr(request.user, "teacher_profile", None)
    if not profile:
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
    profile = getattr(request.user, "teacher_profile", None)
    if not profile:
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


def _whatsapp_invite_link() -> str | None:
    whatsapp = (
        Integration.objects.filter(enabled=True, name__icontains="whatsapp")
        .order_by("-updated_at")
        .first()
    )
    if not whatsapp:
        return None
    number = whatsapp.config.get("phone") or whatsapp.config.get("whatsapp_number")
    if not number:
        return None
    digits = "".join(ch for ch in number if ch.isdigit())
    if not digits:
        return None
    site_name = SiteSettings.get_solo().site_name or "Gilead School System"
    message = quote_plus(f"Hi, I'd like to claim a portal invite for {site_name}.")
    return f"https://wa.me/{digits}?text={message}"


@parent_portal_required
@role_required(User.Role.PARENT)
def link_child(request: HttpRequest):
    site = SiteSettings.get_solo()
    form = LinkChildForm(
        request.POST or None,
        guardian_user=request.user,
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
            "whatsapp_invite_link": _whatsapp_invite_link(),
        },
    )

