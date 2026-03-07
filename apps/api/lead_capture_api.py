"""
Admissions CRM (Phase 5): Lead Capture API.
Public POST by school_slug (or subdomain); creates Applicant with abuse controls.
"""

import json
import logging

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.people.models import Applicant
from apps.schools.models import School

logger = logging.getLogger(__name__)

# Public endpoint: conservative fixed-window throttles.
LEAD_CAPTURE_WINDOW_SECONDS = 60 * 15
LEAD_CAPTURE_IP_MAX = 30
LEAD_CAPTURE_SCHOOL_MAX = 200


def _client_ip(request) -> str:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.META.get("REMOTE_ADDR") or "unknown").strip()


def _incr_with_limit(key: str, max_count: int, window_seconds: int) -> tuple[bool, int]:
    """
    Increment key counter with fixed window.
    Returns (allowed, retry_after_seconds).
    """
    try:
        if cache.add(key, 1, timeout=window_seconds):
            return True, 0
        try:
            count = cache.incr(key)
        except Exception:
            count = int(cache.get(key, 0) or 0) + 1
            cache.set(key, count, timeout=window_seconds)
        if int(count) > int(max_count):
            return False, window_seconds
        return True, 0
    except Exception:
        # Fail-open if cache is unavailable; do not block admissions.
        logger.debug("Lead capture rate-limit cache failure for key=%s", key)
        return True, 0


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class LeadCaptureAPI(View):
    """
    POST body (JSON): school_slug, first_name, last_name, email, lead_source (optional).
    Resolves school by slug; creates Applicant. Duplicate check by (email, school).
    """

    def post(self, request):
        try:
            body = json.loads(request.body) if request.body else {}
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        school_slug = (body.get("school_slug") or "").strip() or request.GET.get("school_slug", "").strip()
        if not school_slug:
            return JsonResponse({"error": "school_slug required"}, status=400)

        school = School.objects.filter(slug=school_slug, is_active=True).first()
        if not school:
            return JsonResponse({"error": "School not found"}, status=404)

        ip = _client_ip(request)
        allowed_ip, retry_ip = _incr_with_limit(
            f"lead_capture:ip:{ip}",
            LEAD_CAPTURE_IP_MAX,
            LEAD_CAPTURE_WINDOW_SECONDS,
        )
        if not allowed_ip:
            return JsonResponse(
                {
                    "error": "Rate limit exceeded for this IP.",
                    "retry_after": retry_ip,
                },
                status=429,
            )

        allowed_school, retry_school = _incr_with_limit(
            f"lead_capture:school:{school.pk}",
            LEAD_CAPTURE_SCHOOL_MAX,
            LEAD_CAPTURE_WINDOW_SECONDS,
        )
        if not allowed_school:
            return JsonResponse(
                {
                    "error": "Rate limit exceeded for this school.",
                    "retry_after": retry_school,
                },
                status=429,
            )

        # Basic bot trap.
        if (body.get("website") or "").strip():
            return JsonResponse({"error": "Invalid payload"}, status=400)

        first_name = (body.get("first_name") or "").strip()
        last_name = (body.get("last_name") or "").strip()
        email = (body.get("email") or "").strip().lower()

        if not email or not first_name or not last_name:
            return JsonResponse({"error": "first_name, last_name, and email required"}, status=400)

        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse({"error": "Invalid email"}, status=400)

        extra_data = body.get("extra_data") or {}
        if not isinstance(extra_data, dict):
            return JsonResponse({"error": "extra_data must be an object"}, status=400)

        existing = Applicant.objects.filter(school=school, email__iexact=email).first()
        if existing:
            return JsonResponse(
                {
                    "ok": True,
                    "applicant_id": existing.pk,
                    "message": "Applicant already exists for this school/email",
                },
                status=200,
            )

        applicant = Applicant.objects.create(
            school=school,
            first_name=first_name,
            last_name=last_name,
            email=email,
            lead_source=(body.get("lead_source") or "").strip() or "api",
            stage=Applicant.Stage.LEAD,
            extra_data=extra_data,
        )
        return JsonResponse({"ok": True, "applicant_id": applicant.pk}, status=201)
