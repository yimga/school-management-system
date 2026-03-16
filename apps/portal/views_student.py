"""
Portal student-facing and syllabus/preview views (§6.14 role separation).
"""
from __future__ import annotations

from django.contrib.auth.views import redirect_to_login
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
from apps.platform_runtime.helpers import get_effective_site_settings

from .models import PortalFeatureItem
from .views_common import PORTAL_FEATURES_META


def student_portal_grades(request: HttpRequest):
    """Semantic alias for parent dashboard (grades overview)."""
    if not request.user.is_authenticated:
        return redirect_to_login(next=reverse("portal:parent_dashboard"))
    return redirect("portal:parent_dashboard")


def admissions_application_status(request: HttpRequest):
    """Semantic alias for application status (re-uses parent dashboard context)."""
    if not request.user.is_authenticated:
        return redirect_to_login(next=reverse("portal:parent_dashboard"))
    return redirect("portal:parent_dashboard")


@role_required(User.Role.PARENT, User.Role.TEACHER)
def portal_syllabus(request: HttpRequest):
    """Syllabus view for parent and teacher roles; access gated by site and role."""
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


@role_required(User.Role.ADMIN)
@xframe_options_sameorigin
def preview_student_syllabus(request: HttpRequest):
    """Admin-only preview of student syllabus placeholder content."""
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
    """Admin-only preview: send a test message with token replacement."""
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
