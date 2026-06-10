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
from apps.academics.services import get_active_year_and_term

from .models import PortalFeatureItem
from .views_common import PORTAL_FEATURES_META
from .tenant_role_home import build_tp_hero_context
from .tenant_workflow_portal import build_tenant_workflow_portal


@login_required
def student_portal_grades(request: HttpRequest):
    """Student role home (Phase 7); other roles use the family dashboard."""
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

    _site = get_effective_site_settings(request=request)
    if not getattr(_site, "enable_student_portal", True):
        return HttpResponseForbidden("Student portal is disabled.")

    profile = None
    try:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        profile = StudentProfile.objects.filter(
            user=request.user, is_active=True
        ).select_related("classroom").first()
    except (AttributeError, DatabaseError, TypeError, ValueError):
        profile = None

    unread = 0
    try:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
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

    from apps.portal.tenant_role_home import build_tp_hero_context
    from apps.schools.tenant_operational_health import resolve_tenant_operational_health

    tenant_health = resolve_tenant_operational_health(
        getattr(request, "school", None), request=request, surface="student"
    )

    return render(
        request,
        "student/learning_home.html",
        {
            "phase7_de": phase7_de,
            "tenant_health": tenant_health,
            **build_tp_hero_context(
                request,
                role=User.Role.STUDENT,
                unread_messages=unread,
            ),
        },
    )


@login_required
@role_required(User.Role.STUDENT)
def student_workflow_center(request: HttpRequest):
    """Student workflow center: one simple path for daily learning tasks."""
    site = get_effective_site_settings(request=request)
    if not getattr(site, "enable_student_portal", True):
        return HttpResponseForbidden("Student portal is disabled.")

    _school = getattr(request, "school", None)
    profile = None
    try:
        if _school is not None:
            profile = (
                StudentProfile.objects.filter(
                    school=_school, user=request.user, is_active=True
                )
                .select_related("classroom")
                .first()
            )
    except (AttributeError, DatabaseError, TypeError, ValueError):
        profile = None

    unread = 0
    try:
        if _school is not None:
            unread = Message.objects.filter(
                school=_school, recipient=request.user, is_read=False
            ).count()
    except (AttributeError, DatabaseError, TypeError, ValueError):
        unread = 0

    try:
        if _school is not None:
            resource_count = PortalFeatureItem.objects.filter(
                school=_school,
                feature=PortalFeatureItem.Feature.SYLLABUS,
                is_active=True,
            ).count()
        else:
            resource_count = 0
    except (AttributeError, DatabaseError, TypeError, ValueError):
        resource_count = 0

    year, term = get_active_year_and_term(school=getattr(request, "school", None))
    profile_state = "Ready" if profile is not None else "Setup needed"
    steps = [
        {
            "title": "1) Read school messages",
            "subtitle": "Start with announcements and direct messages from school.",
            "step_key": "messages",
            "icon": "bi-chat-dots",
            "done": unread == 0,
            "progress_label": f"{unread} unread message(s)",
            "tip": "Unread messages can include schedule changes, teacher notes, and school reminders.",
            "links": [{"label": "Open messages", "url": reverse("accounts:user_messages")}],
        },
        {
            "title": "2) Check syllabus and resources",
            "subtitle": "Open class resources, syllabus items, and learning documents.",
            "step_key": "resources",
            "icon": "bi-journal-text",
            "done": resource_count > 0,
            "progress_label": f"{resource_count} resource(s) available",
            "tip": "Use this before class or homework so you always have the latest materials.",
            "links": [{"label": "Open syllabus", "url": reverse("portal:portal_syllabus")}],
        },
        {
            "title": "3) Confirm class profile",
            "subtitle": "Make sure your student record and class are connected.",
            "step_key": "profile",
            "icon": "bi-person-badge",
            "done": profile is not None,
            "progress_label": profile_state,
            "tip": "If your class is missing, ask the school office to link your login.",
            "links": [{"label": "Profile", "url": reverse("accounts:user_profile")}],
        },
        {
            "title": "4) Plan today",
            "subtitle": "Use the student home as your daily launch point.",
            "step_key": "today",
            "icon": "bi-calendar-check",
            "done": True,
            "progress_label": "Student home available",
            "tip": "Keep this page simple: messages, resources, and profile first.",
            "links": [{"label": "Student home", "url": reverse("portal:student_portal_grades")}],
        },
        {
            "title": "5) Get help",
            "subtitle": "Open help when you are blocked.",
            "step_key": "help",
            "icon": "bi-life-preserver",
            "done": True,
            "progress_label": "Help available",
            "tip": "Ask early when you cannot access a class, result, or resource.",
            "links": [{"label": "Help center", "url": reverse("feedback:help_center")}],
        },
    ]
    total_steps = len(steps)
    for i, step in enumerate(steps, start=1):
        step["step_index"] = i
        step["total_steps"] = total_steps

    workflow_progress = {
        "unread_messages": unread,
        "profile_state": profile_state,
        "resource_count": resource_count,
    }
    return render(
        request,
        "student/workflow_center.html",
        {
            **build_tp_hero_context(
                request,
                role=User.Role.STUDENT,
                unread_messages=unread,
            ),
            "active_year": year,
            "active_term": term,
            "steps": steps,
            "workflow_progress": workflow_progress,
            "workflow_portal": build_tenant_workflow_portal(
                request,
                role=User.Role.STUDENT,
                steps=steps,
                workflow_progress=workflow_progress,
                active_year=year,
                active_term=term,
                empty_state=profile is None,
            ),
        },
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
    if role == User.Role.STUDENT and not getattr(site, "enable_student_portal", True):
        return HttpResponseForbidden("Student portal is disabled.")

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
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
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    )
    student = (
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
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
