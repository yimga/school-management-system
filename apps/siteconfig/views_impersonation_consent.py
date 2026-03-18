"""
JIT (Just-In-Time): Principal/school admin consent for RunMyCampus support impersonation.
Plan: principal consent before impersonation (195-country governance).
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect

from apps.accounts.decorators import permission_required


@login_required
@permission_required("settings.manage")
@require_POST
@csrf_protect
def grant_impersonation_consent(request):
    """School admin/principal grants consent for RunMyCampus support to impersonate this school."""
    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"ok": False, "error": _("No school context")}, status=400)
    school.impersonation_consent_granted_at = timezone.now()
    school.impersonation_consent_granted_by_id = request.user.id
    school.save(
        update_fields=[
            "impersonation_consent_granted_at",
            "impersonation_consent_granted_by_id",
        ]
    )
    return JsonResponse(
        {
            "ok": True,
            "message": _("Consent granted. Support may impersonate until expiry."),
        }
    )


@login_required
@permission_required("settings.manage")
@require_POST
@csrf_protect
def revoke_impersonation_consent(request):
    """School admin/principal revokes impersonation consent."""
    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"ok": False, "error": _("No school context")}, status=400)
    school.impersonation_consent_granted_at = None
    school.impersonation_consent_granted_by_id = None
    school.save(
        update_fields=[
            "impersonation_consent_granted_at",
            "impersonation_consent_granted_by_id",
        ]
    )
    return JsonResponse({"ok": True, "message": _("Consent revoked.")})
