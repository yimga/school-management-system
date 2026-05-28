from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseForbidden, HttpRequest, Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.views.decorators.cache import never_cache
from urllib.parse import quote_plus
import base64
from io import BytesIO
import logging

from apps.accounts.decorators import (
    role_required,
    teacher_portal_required,
)
from apps.accounts.utils import get_user_role
from apps.accounts.models import User
from apps.people.models import (
    StudentProfile,
    Badge,
)
from apps.academics.services import get_active_year_and_term

from apps.platform_runtime.helpers import get_site_display_name
from apps.siteconfig.config_service import get_effective_site_settings
from .models import (
    PortalFeatureItem,
)
from .services import (
    _merged_upcoming_events,
)

from .views_common import (
    PORTAL_SOFT_FAILURES,
    PORTAL_FEATURE_PERMISSIONS,
    _portal_features_status,
)

# Re-export for urlconf (apps.portal.urls)
from .views_student import (
    student_portal_grades,  # noqa: F401
    student_workflow_center,  # noqa: F401
    admissions_application_status,  # noqa: F401
    portal_syllabus,  # noqa: F401
    preview_student_syllabus,  # noqa: F401
    preview_communication_test,  # noqa: F401
)

# Re-export §6.14 Phase 2 parent views
from .views_parent import (
    parent_set_active_child,  # noqa: F401
    parent_workflow_center,  # noqa: F401
    claim_invite,  # noqa: F401
    parent_medal_case,  # noqa: F401
    child_digital_id,  # noqa: F401
    portal_stats,  # noqa: F401
    parent_attendance_discipline,  # noqa: F401
    parent_child_results,  # noqa: F401
    parent_dashboard,  # noqa: F401
    link_child,  # noqa: F401
    link_child_wizard,  # noqa: F401
    parent_settings_security,  # noqa: F401
    _whatsapp_invite_link,  # noqa: F401
    _parent_workflow_link,  # noqa: F401
)
from .views_attendance_export import (
    student_attendance_export,  # noqa: F401
    student_attendance_export_csv,  # noqa: F401
)
from .views_teacher import (
    teacher_feed,  # noqa: F401
    teacher_dashboard_alias,  # noqa: F401
    teacher_workflow_alias,  # noqa: F401
    teacher_pay_history,  # noqa: F401
    teacher_leave,  # noqa: F401
    teacher_attendance_view,  # noqa: F401
    teacher_attendance_export,  # noqa: F401
    take_student_attendance,  # noqa: F401
    record_teacher_attendance,  # noqa: F401
    seating_chart_view,  # noqa: F401
    cahier_list,  # noqa: F401
    cahier_verify_list,  # noqa: F401
    cahier_visa,  # noqa: F401
    cahier_request_revisions,  # noqa: F401
    teacher_timetable,  # noqa: F401
    teacher_lesson_notes,  # noqa: F401
    teacher_lesson_plan_add_attachment,  # noqa: F401
    teacher_wellness,  # noqa: F401
    teacher_hr_status,  # noqa: F401
    teacher_disciplinary,  # noqa: F401
    teacher_training_log,  # noqa: F401
    discipline_incidents_list,  # noqa: F401
)

logger = logging.getLogger(__name__)


@login_required
def portal_feature_page(request: HttpRequest, feature: str):
    """Portal tools (Community, Video, Documents): require corresponding portal.* permission and feature enabled."""
    if feature == "forums":
        from apps.portal.views_forums import forum_home

        return forum_home(request)
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
        return render(
            request,
            "portal/feature_disabled.html",
            {
                "feature": entry,
            },
        )

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    items = PortalFeatureItem.objects.filter(
        feature=feature, is_active=True
    ).select_related("created_by")
    return render(
        request,
        "portal/feature_page.html",
        {
            "feature": entry,
            "items": items,
        },
    )


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
                    badge = (
                        Badge.objects.filter(pk=pk)
                        .select_related("badge_type", "user", "student")
                        .first()
                    )
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
                        badge = type(
                            "IDHolder",
                            (),
                            {
                                "user": user,
                                "student": None,
                                "badge_type": type("BT", (), {"label": "Staff ID"})(),
                            },
                        )()
                    else:
                        message = _("Staff member not found or inactive.")
                elif payload.startswith("student:"):
                    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                    sid = int(payload.split(":")[1])
                    student = StudentProfile.objects.filter(pk=sid).first()
                    if student and student.is_active:
                        valid = True
                        message = _("Valid — Student ID")
                        badge = type(
                            "IDHolder",
                            (),
                            {
                                "user": None,
                                "student": student,
                                "badge_type": type("BT", (), {"label": "Student ID"})(),
                            },
                        )()
                    else:
                        message = _("Student not found or inactive.")
                # Phase 5: log scan event for valid verifications (attendance / third-party)
                if valid and badge:
                    from apps.people.models import BadgeScanEvent

                    kind = (
                        BadgeScanEvent.KIND_STAFF
                        if getattr(badge, "user", None)
                        else BadgeScanEvent.KIND_STUDENT
                    )
                    if payload.startswith("badge:"):
                        kind = BadgeScanEvent.KIND_BADGE
                    ip = request.META.get("REMOTE_ADDR", "")[:45] or None
                    try:
                        BadgeScanEvent.objects.create(
                            badge=badge
                            if kind == BadgeScanEvent.KIND_BADGE
                            and getattr(badge, "pk", None)
                            else None,
                            token_kind=kind,
                            user=getattr(badge, "user", None),
                            student=getattr(badge, "student", None),
                            verified=True,
                            ip_address=ip,
                            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[
                                :255
                            ],
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
            name = getattr(
                badge.user, "get_full_name", lambda: str(badge.user)
            )() or getattr(badge.user, "username", "")
        elif getattr(badge, "student", None):
            role = "student"
            name = getattr(
                badge.student, "get_full_name", lambda: str(badge.student)
            )() or getattr(badge.student, "admission_number", "")

    if want_json:
        return JsonResponse(
            {
                "valid": valid,
                "message": message,
                "badge_type": getattr(badge, "badge_type", None)
                and getattr(badge.badge_type, "label", None),
                "holder": str(badge.user or badge.student) if badge else None,
                "role": role,
                "name": name,
            }
        )

    return render(
        request,
        "portal/badge_verify.html",
        {
            "valid": valid,
            "message": message,
            "badge": badge,
        },
    )


@login_required
def unified_calendar(request: HttpRequest):
    """Phase 9: Unified calendar – school events and grading deadlines for teachers and parents."""
    year, _term = get_active_year_and_term()
    events = _merged_upcoming_events(year, school=getattr(request, "school", None))
    role = get_user_role(request.user)
    return render(
        request,
        "portal/unified_calendar.html",
        {
            "events": events,
            "site": get_effective_site_settings(request=request),
            "is_teacher": role == User.Role.TEACHER,
            "is_parent": role == User.Role.PARENT,
        },
    )


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
    photo = (
        profile.profile_photo
        if profile and hasattr(profile, "profile_photo") and profile.profile_photo
        else None
    )
    qr_token = get_signed_id_token("staff", request.user.pk)
    verify_url = request.build_absolute_uri(
        reverse("portal:badge_verify") + "?token=" + quote_plus(qr_token)
    )
    qr_image_url = _qr_png_data_uri(verify_url)
    return render(
        request,
        "portal/digital_id_staff.html",
        {
            "site_name": get_site_display_name(request),
            "name": name,
            "role_label": role_label,
            "photo": photo,
            "qr_token": qr_token,
            "verify_url": verify_url,
            "qr_image_url": qr_image_url,
        },
    )


# _whatsapp_invite_link, link_child, link_child_wizard: see views_parent (re-exported above). §6.14
