# apps/api/digital_id_api.py
"""
Phase 5: Read-only API for digital ID (wallet / Apple Wallet / Google Pay / partner apps).
Returns photo, name, role/grade, QR payload for authenticated staff or parent (children).
"""
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib.auth.decorators import login_required
from django.db.utils import DatabaseError
from django.urls import reverse
from urllib.parse import quote_plus
from apps.accounts.models import User
from apps.people.models import StudentGuardian
from apps.platform_runtime.helpers import get_site_display_name

logger = __import__("logging").getLogger(__name__)


def _staff_digital_id_payload(request):
    """Build staff digital ID dict for API (same data as portal my_digital_id)."""
    from apps.people.badge_services import get_signed_id_token

    profile = getattr(request.user, "teacher_profile", None)
    name = request.user.get_full_name() or request.user.username
    role_label = "Teacher"
    if profile and profile.department:
        role_label = str(profile.department.name)
    photo_url = None
    if profile and getattr(profile, "profile_photo", None) and profile.profile_photo:
        photo_url = request.build_absolute_uri(profile.profile_photo.url)
    qr_token = get_signed_id_token("staff", request.user.pk)
    verify_url = request.build_absolute_uri(
        reverse("portal:badge_verify") + "?token=" + quote_plus(qr_token)
    )
    return {
        "kind": "staff",
        "site_name": get_site_display_name(request) or "School",
        "name": name,
        "role": role_label,
        "photo_url": photo_url,
        "qr_payload": qr_token,
        "verify_url": verify_url,
    }


def _child_digital_id_payload(request, student):
    """Build one child digital ID dict for API."""
    from apps.people.badge_services import get_signed_id_token

    classroom = getattr(student, "classroom", None)
    grade_label = (
        classroom.name
        if classroom
        else (
            getattr(student, "academic_year", None) and str(student.academic_year) or "—"
        )
    )
    photo_url = None
    if getattr(student, "profile_photo", None) and student.profile_photo:
        photo_url = request.build_absolute_uri(student.profile_photo.url)
    qr_token = get_signed_id_token("student", student.pk)
    verify_url = request.build_absolute_uri(
        reverse("portal:badge_verify") + "?token=" + quote_plus(qr_token)
    )
    return {
        "kind": "student",
        "site_name": get_site_display_name(request) or "School",
        "student_id": student.pk,
        "name": student.get_full_name(),
        "grade": grade_label,
        "photo_url": photo_url,
        "qr_payload": qr_token,
        "verify_url": verify_url,
    }


@method_decorator(login_required, name="dispatch")
class DigitalIDAPI(View):
    """
    GET: Returns current user's digital ID (staff) or 403 for non-teachers.
    For parents use /api/portal/digital-id/children/.
    """

    def get(self, request):
        role_value = (getattr(request.user, "role", "") or "").upper()
        if role_value != User.Role.TEACHER:
            return JsonResponse({"error": "Permission denied. Staff only."}, status=403)
        try:
            payload = _staff_digital_id_payload(request)
            return JsonResponse(payload)
        except (ImportError, AttributeError, TypeError, ValueError, ObjectDoesNotExist, DatabaseError) as e:
            logger.exception("Digital ID API error: %s", e)
            return JsonResponse({"error": "Failed to build digital ID."}, status=500)


@method_decorator(login_required, name="dispatch")
class DigitalIDChildrenAPI(View):
    """
    GET: Returns digital IDs for all linked children (parent only).
    Same scoping as portal: only students where guardian has can_view_results or link.
    """

    def get(self, request):
        role_value = (getattr(request.user, "role", "") or "").upper()
        if role_value != User.Role.PARENT:
            return JsonResponse({"error": "Permission denied. Parent only."}, status=403)
        try:
            links = StudentGuardian.objects.filter(
                guardian_user=request.user,
                student__is_active=True,
            ).select_related("student", "student__classroom", "student__academic_year")
            children = []
            for link in links:
                children.append(_child_digital_id_payload(request, link.student))
            return JsonResponse({"children": children})
        except (ImportError, AttributeError, TypeError, ValueError, ObjectDoesNotExist, DatabaseError) as e:
            logger.exception("Digital ID children API error: %s", e)
            return JsonResponse({"error": "Failed to build children IDs."}, status=500)
