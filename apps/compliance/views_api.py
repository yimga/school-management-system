"""
API endpoints for compliance dashboard actions.
"""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, IntegrityError, OperationalError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.compliance.models_audit import ThreatDetectionConfig
from apps.platform_runtime.structured_logging import log_view_exception
from apps.schools.control_plane import require_control_plane_access


@require_POST
@login_required
@require_control_plane_access
@ratelimit(key="user", rate="10/m", method="POST", block=True)
def mute_threats(request):
    """
    Mute threat detection for a specified duration.

    POST parameters:
        - duration: '1h', '4h', '24h', or 'clear' to unmute

    OPERATOR-ONLY. ThreatDetectionConfig is a platform singleton (no school FK,
    ``is_active`` is unique) and ``detect_threats`` returns nothing for EVERY
    school while it is muted. This route is mounted on the tenant urlconf, so
    the previous ``is_admin_or_staff`` gate -- which admits any school ADMIN or
    LEADERSHIP user -- let one tenant suppress brute-force and after-hours
    alerting for the whole platform. The admin surface for the same model is
    kept off the tenant site the same way (config/admin.py
    TENANT_ADMIN_OPERATOR_ONLY).
    """
    duration_str = request.POST.get("duration", "1h")

    try:
        config = ThreatDetectionConfig.get_active()
    except (
        AttributeError,
        TypeError,
        ValueError,
        DatabaseError,
        OperationalError,
        IntegrityError,
    ):
        log_view_exception(
            request,
            "mute_threats threat config get/create failed",
            extra={"section": "mute_threats", "duration": duration_str},
        )
        config = ThreatDetectionConfig.objects.create()

    now = timezone.now()

    if duration_str == "clear":
        config.mute_until = None
        config.save()
        return JsonResponse(
            {
                "success": True,
                "message": "Threat detection unmuted",
                "muted_until": None,
            }
        )

    # Parse duration
    duration_map = {
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "24h": timedelta(hours=24),
    }

    duration = duration_map.get(duration_str)
    if not duration:
        return JsonResponse(
            {
                "success": False,
                "error": f"Invalid duration: {duration_str}. Use 1h, 4h, 24h, or clear.",
            },
            status=400,
        )

    config.mute_until = now + duration
    config.save()

    return JsonResponse(
        {
            "success": True,
            "message": f"Threat detection muted until {config.mute_until.strftime('%Y-%m-%d %H:%M')}",
            "muted_until": config.mute_until.isoformat(),
        }
    )
