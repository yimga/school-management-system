from django.shortcuts import render, get_object_or_404, redirect
from datetime import timedelta
from django.http import HttpResponseForbidden, HttpRequest, Http404, HttpResponse, HttpResponseRedirect
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
from apps.finance.models import Invoice, PaymentReminder, ReferralReward
from apps.finance.services import generate_payment_link
from apps.reports.services import (
    are_terms_published,
    is_term_published,
    terms_for_student,
    term_report_context,
)
from apps.siteconfig.models import Integration, SiteSettings, default_portal_features, resolve_dashboard_widgets
from apps.analytics.services import (
    student_improvements,
    specialty_pass_rates,
    subject_weaknesses,
    term_rankings,
)
from .models import PortalFeatureItem, PendingGuardianInvite
from .services import parent_dashboard_widget_data, award_referral_reward, link_guardian_via_invite
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
    links = StudentGuardian.objects.filter(
        guardian_user=request.user,
        can_view_results=True
    ).select_related("student", "student__classroom", "student__specialty", "student__academic_year")

    portal_features = _portal_features_status()
    students = [link.student for link in links]
    widget_data = parent_dashboard_widget_data(students)
    preference = getattr(request.user, "preferences", None)
    display_widgets = resolve_dashboard_widgets(getattr(request.user, "role", None), preference)
    reminders_count = PaymentReminder.objects.filter(
        invoice__student__in=students,
        is_active=True,
    ).count()
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
    hero["stats"].append({"label": "Reminders", "value": reminders_count, "meta": "Pending notices"})
    hero["actions"].insert(1, {"label": "View Attendance", "url": reverse("portal:portal_stats")})

    return render(request, "parent/dashboard.html", {
        "links": links,
        "portal_features": portal_features,
        "widget_data": widget_data,
        "display_widgets": display_widgets,
        "hero": hero,
        "reminders_count": reminders_count,
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
        .prefetch_related("payments")
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
        messages.warning(request, f"{entry['label']} is currently disabled.")
        return redirect("portal:parent_dashboard")

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

    students = [link.student for link in StudentGuardian.objects.filter(
        guardian_user=request.user
    ).select_related("student")]
    widget_data = parent_dashboard_widget_data(students)

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

