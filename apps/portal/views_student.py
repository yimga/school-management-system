"""
Portal student-facing and syllabus/preview views (§6.14 role separation).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db import DatabaseError
from django.http import HttpRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.accounts.models import User
from apps.accounts.utils import get_user_role
from apps.accounts.decorators import role_required
from apps.communication.models import Message
from apps.people.models import StudentProfile
from apps.siteconfig.config_service import get_effective_site_settings

from .models import PortalFeatureItem
from .views_common import PORTAL_FEATURES_META


def student_portal_grades(request: HttpRequest):
    """Student role home (Phase 7); other roles use the family dashboard."""
    if not request.user.is_authenticated:
        return redirect_to_login(next=request.get_full_path())
    if get_user_role(request.user) == User.Role.STUDENT:
        return student_learning_home(request)
    return redirect("portal:parent_dashboard")


@login_required
def student_learning_home(request: HttpRequest):
    """
    Phase 7 — Student operating surface: headline state, metrics, queue, next actions.
    """
    if get_user_role(request.user) != User.Role.STUDENT:
        return redirect("portal:parent_dashboard")

    site = get_effective_site_settings(request=request)
    profile = None
    try:
        profile = StudentProfile.objects.filter(
            user=request.user, is_active=True
        ).select_related("classroom").first()
    except (AttributeError, DatabaseError, TypeError, ValueError):
        profile = None

    unread = 0
    try:
        unread = Message.objects.filter(
            recipient=request.user, is_read=False
        ).count()
    except (AttributeError, DatabaseError, TypeError, ValueError):
        pass

    class_label = (
        profile.classroom.name
        if profile and getattr(profile, "classroom", None)
        else "—"
    )
    headline = (
        f"{profile.first_name} {profile.last_name}".strip()
        if profile
        else request.user.get_full_name() or request.user.username
    )

    metrics = [
        {
            "label": "Class",
            "value": class_label,
            "meta": "Current homeroom",
            "status": "ok",
        },
        {
            "label": "Unread messages",
            "value": unread,
            "meta": "From school",
            "status": "warn" if unread else "ok",
        },
    ]

    urgent_queue = []
    if unread:
        urgent_queue.append(
            {
                "title": f"{unread} unread message(s)",
                "url": reverse("accounts:user_messages"),
                "hint": "Open your inbox",
            }
        )
    if profile is None:
        urgent_queue.append(
            {
                "title": "Student profile not linked",
                "url": reverse("accounts:user_profile"),
                "hint": "Ask your school to link your login to a student record.",
            }
        )

    next_actions = [
        {"label": "Messages", "url": reverse("accounts:user_messages")},
        {"label": "Syllabus & resources", "url": reverse("portal:portal_syllabus")},
        {"label": "Account & profile", "url": reverse("accounts:user_profile")},
    ]

    activity = [
        {"title": "Student portal", "meta": "Signed in and ready for school updates."}
    ]

    phase7_de = {
        "eyebrow": "Student home",
        "headline_label": "Learning status",
        "headline_value": "On track" if profile else "Setup needed",
        "headline_meta": headline,
        "metrics": metrics,
        "urgent_queue": urgent_queue
        or [
            {
                "title": "No urgent items",
                "url": "",
                "hint": "Check messages and syllabus for updates.",
            }
        ],
        "next_actions": next_actions,
        "activity": activity,
    }

    _ = site  # reserved for enable_student_portal wiring
    return render(
        request,
        "student/learning_home.html",
        {"phase7_de": phase7_de},
    )


def admissions_application_status(request: HttpRequest):
    """Semantic alias for application status (re-uses parent dashboard context)."""
    if not request.user.is_authenticated:
        return redirect_to_login(next=reverse("portal:parent_dashboard"))
    return redirect("portal:parent_dashboard")


@role_required(User.Role.PARENT, User.Role.TEACHER, User.Role.STUDENT)
def portal_syllabus(request: HttpRequest):
    """Syllabus for parent, teacher, and student; gated by portal toggles."""
    site = get_effective_site_settings(request=request)
    role = get_user_role(request.user)
    if role == User.Role.PARENT and not site.enable_parent_portal:
        return HttpResponseForbidden("Parent portal is disabled.")
    if role == User.Role.TEACHER and not site.enable_teacher_portal:
        return HttpResponseForbidden("Teacher portal is disabled.")

    items = (
        PortalFeatureItem.objects.filter(
            feature=PortalFeatureItem.Feature.SYLLABUS,
            is_active=True,
        )
        .select_related("created_by")
        .order_by("-created_at")
    )

    role = get_user_role(request.user)
    return render(
        request,
        "portal/syllabus.html",
        {
            "feature": {**PORTAL_FEATURES_META["syllabus"], "key": "syllabus"},
            "items": items,
            "is_teacher": role == User.Role.TEACHER,
            "is_student": role == User.Role.STUDENT,
        },
    )


@role_required(User.Role.ADMIN)
@xframe_options_sameorigin
def preview_student_syllabus(request: HttpRequest):
    """Admin-only preview of student syllabus placeholder content."""
    synthetic_items = [
        {
            "title": "Physics Lab Experience",
            "description": "Hands-on labs with sensors and robotics demos.",
            "created_at": timezone.now(),
        },
        {
            "title": "Digital Literacy Week",
            "description": "Interactive lesson on AI safety and documentation sharing.",
            "created_at": timezone.now(),
        },
        {
            "title": "Design & Technology",
            "description": "Project-based curriculum with 2026 compliance mockups.",
            "created_at": timezone.now(),
        },
    ]
    return render(
        request,
        "portal/preview/student_syllabus_preview.html",
        {
            "feature": {**PORTAL_FEATURES_META["syllabus"], "key": "syllabus"},
            "items": synthetic_items,
            "is_preview": True,
        },
    )


@role_required(User.Role.ADMIN)
@require_POST
def preview_communication_test(request: HttpRequest):
    """Admin-only preview: send a test message with token replacement."""
    subject = request.POST.get("subject", "Preview notice for [Student Name]")
    body_template = request.POST.get(
        "body", "Dear [Student Name], this is a preview of your [Specialty] update."
    )
    student = (
        StudentProfile.objects.filter(is_active=True)
        .select_related("classroom")
        .first()
    )
    # Pass 8: previously substituted hardcoded "Sample Learner / Sample Classroom /
    # General Studies" when no student record existed. Those strings then appeared in
    # real previews for tenants pre-roster. Use neutral angle-bracket placeholders that
    # read as "fill this in" rather than as fake student data.
    tokens = {
        "Student Name": f"{student.first_name} {student.last_name}"
        if student
        else "<Student name>",
        "Classroom": student.classroom.name
        if student and hasattr(student, "classroom")
        else "<Classroom>",
        "Specialty": student.specialty.name
        if student and hasattr(student, "specialty")
        else "<Specialty>",
    }

    def fill_template(text):
        output = text
        for key, value in tokens.items():
            output = output.replace(f"[{key}]", value)
        return output

    filled_subject = fill_template(subject)
    filled_body = fill_template(body_template)

    from apps.communication.comms_locale import locale_target_for_user

    Message.objects.create(
        sender=request.user,
        recipient=request.user,
        subject=f"{filled_subject} [Preview]",
        body=filled_body,
        locale_target=locale_target_for_user(request.user),
    )

    return JsonResponse(
        {
            "status": "success",
            "subject": filled_subject,
            "body": filled_body[:200] + ("…" if len(filled_body) > 200 else ""),
        }
    )
