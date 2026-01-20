from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseForbidden, HttpRequest, Http404
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.urls import reverse
import uuid
from decimal import Decimal
from django.db.models import Sum

from apps.accounts.decorators import (
    role_required,
    parent_portal_required,
    teacher_portal_required,
)
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
from apps.finance.models import Invoice
from apps.finance.services import generate_payment_link
from apps.reports.services import (
    are_terms_published,
    is_term_published,
    terms_for_student,
    term_report_context,
)
from apps.siteconfig.models import SiteSettings, default_portal_features
from apps.analytics.services import (
    student_improvements,
    specialty_pass_rates,
    subject_weaknesses,
    term_rankings,
)
from .models import PortalFeatureItem, PendingGuardianInvite
from .services import parent_dashboard_widget_data
from .forms import LinkChildForm, ClaimInviteForm, TeacherLeaveForm

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
    links = StudentGuardian.objects.filter(
        guardian_user=request.user,
        can_view_results=True
    ).select_related("student", "student__classroom", "student__specialty", "student__academic_year")

    portal_features = _portal_features_status()
    widget_data = parent_dashboard_widget_data([link.student for link in links])
    hero = {
        "tagline": "Student Management Dashboard",
        "title": "Welcome back",
        "subtitle": "Live snapshot of your learners, attendance, and finances",
        "icon": "bi-mortarboard",
        "stats": [
            {"label": "Linked Students", "value": links.count(), "meta": "Active profiles"},
            {"label": "Attendance", "value": f"{widget_data['attendance']['overall']}%", "progress": widget_data['attendance']['overall'], "meta": "Completion"},
            {"label": "Balance", "value": widget_data["finance"]["balance"], "meta": "Outstanding fees"},
        ],
        "actions": [
            {"label": "View Results", "url": "#children"},
            {"label": "Link a Child", "url": "#link-child"},
            {"label": "Pay Fees", "url": reverse("portal:parent_finance")},
        ],
    }

    return render(request, "parent/dashboard.html", {
        "links": links,
        "portal_features": portal_features,
        "widget_data": widget_data,
        "hero": hero,
    })


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_finance(request: HttpRequest):
    links = StudentGuardian.objects.filter(
        guardian_user=request.user,
        can_view_finance=True,
    ).select_related("student", "student__classroom", "student__specialty", "student__academic_year")

    if not links:
        messages.info(request, "Link a student first to view finance details.")
        return redirect("portal:link_child")

    students = [link.student for link in links]
    invoices_qs = (
        Invoice.objects.filter(student__in=students)
        .exclude(status=Invoice.Status.DRAFT)
        .select_related("student", "academic_year")
        .order_by("-issued_date")
    )
    aggregates = invoices_qs.aggregate(
        total_due=Sum("total_amount"),
        balance=Sum("balance_amount"),
    )
    total_due = aggregates.get("total_due") or Decimal("0.00")
    balance = aggregates.get("balance") or Decimal("0.00")
    paid = total_due - balance
    overdue_count = invoices_qs.filter(status=Invoice.Status.OVERDUE).count()

    invoice_rows = []
    for inv in invoices_qs:
        invoice_rows.append(
            {
                "invoice": inv,
                "payment_link": generate_payment_link(inv),
            }
        )

    hero = {
        "title": "Finances",
        "subtitle": "Balances, invoices, and secure payment links",
        "stats": [
            {"label": "Total due", "value": total_due},
            {"label": "Paid", "value": paid},
            {"label": "Outstanding", "value": balance},
            {"label": "Overdue", "value": overdue_count},
        ],
    }

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

        # Prevent duplicate links
        exists = StudentGuardian.objects.filter(
            guardian_user=request.user,
            student=student,
        ).exists()
        if exists:
            messages.info(request, "You are already linked to this student.")
            return redirect("portal:parent_dashboard")

        guardian = StudentGuardian.objects.create(
            guardian_user=request.user,
            student=student,
            relationship=invite.relationship,
            phone=invite.invited_phone,
            preferred_contact=invite.preferred_contact,
            receives_email=True,
            receives_sms=False,
            receives_whatsapp=False,
            can_view_results=True,
            can_view_finance=True,
        )

        invite.guardian_user = request.user
        invite.claimed_at = timezone.now()
        invite.save(update_fields=["guardian_user", "claimed_at"])

        if invite.referral_code and not student.referral_code:
            student.referral_code = invite.referral_code
            student.save(update_fields=["referral_code"])

        # If student missing parent phone, reuse invited phone
        if not student.parent_phone and guardian.phone:
            student.parent_phone = guardian.phone
            student.save(update_fields=["parent_phone"])

        messages.success(request, f"Invite claimed. You are now linked to {student}.")
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
        messages.warning(request, f"{entry['label']} is currently disabled.")
        return redirect("portal:parent_dashboard")

    items = PortalFeatureItem.objects.filter(feature=feature, is_active=True).select_related("created_by")
    return render(request, "portal/feature_page.html", {
        "feature": entry,
        "items": items,
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

    class_rankings = term_rankings(term)
    top_students = class_rankings[:5]
    specialty_rows = specialty_pass_rates(
        academic_year=year,
        term=term,
        pass_mark=pass_mark,
        use_promotion_rule=site.use_promotion_rule_for_pass,
    )
    weak_subjects = subject_weaknesses(
        academic_year=year,
        term=term,
        classroom=None,
        specialty=None,
        threshold=weak_threshold,
    )
    improvement_rows = []
    if prev_term:
        improvement_rows = student_improvements(
            academic_year=year,
            from_term=prev_term,
            to_term=term,
            classroom=None,
            min_delta=improvement_delta,
        )

    return render(request, "portal/stats.html", {
        "year": year,
        "term": term,
        "top_students": top_students,
        "specialty_rows": specialty_rows,
        "weak_subjects": weak_subjects,
        "improvement_rows": improvement_rows,
    })


def student_portal_grades(request: HttpRequest) -> HttpResponseRedirect:
    """Semantic alias for parent dashboard (grades overview)."""
    return redirect("portal:parent_dashboard")


def admissions_application_status(request: HttpRequest) -> HttpResponseRedirect:
    """Semantic alias for application status (re-uses parent dashboard context)."""
    return redirect("portal:parent_dashboard")


def teacher_dashboard_alias(request: HttpRequest) -> HttpResponseRedirect:
    """Alias for the teacher dashboard path so legacy links don't 404."""
    return redirect("evals:teacher_dashboard")


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
    hero = {
        "title": "Pay history",
        "subtitle": "Recent pay, raises, and stipends",
        "actions": [],
        "stats": [
            {"label": "Last pay", "value": last_pay_amount or "—", "meta": last_pay_date or "Not set"},
            {"label": "Next pay date", "value": profile.next_pay_date or "Not set", "meta": profile.pay_grade or "Pay grade"},
            {"label": "Raises", "value": raises_count, "meta": f"Bonuses: {bonus_count}"},
        ],
    }
    return render(request, "teacher/pay_history.html", {
        "hero": hero,
        "pay_records": pay_records,
        "teacher_profile": profile,
        "latest_pay": latest_pay,
        "raises_count": raises_count,
        "bonus_count": bonus_count,
    })


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
        messages.success(
            request,
            f"Linked {guardian_link.student} successfully. Results and finance access will reflect your choices.",
        )
        return redirect("portal:parent_dashboard")

    return render(
        request,
        "parent/link_child.html",
        {
            "form": form,
            "school_code": site.school_code,
        },
    )

