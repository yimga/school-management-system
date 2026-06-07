"""Auditor magic-link views (Wave E — year-end governance).

- ``auditor_inspect`` — PUBLIC, token-gated, no login. Resolves the grant, logs
  the access, returns the PII-masked read-only roster. The token is the auth.
- ``AuditorGrantConsoleView`` — staff-only operator console (JSON) to create /
  list / revoke grants.
"""

from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

from apps.compliance import auditor_access


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def auditor_inspect(request):
    """Public inspector landing — masked, read-only, access-logged. Token = auth."""
    token = request.GET.get("token", "")
    grant = auditor_access.resolve_grant(token)
    if grant is None:
        return JsonResponse(
            {"ok": False, "error": "This inspection link is invalid, expired or revoked."},
            status=403,
        )
    client_ip = _client_ip(request)
    if not auditor_access.ip_is_allowed(grant, client_ip):
        auditor_access.log_access(
            grant,
            resource="auditor:roster",
            ip_address=client_ip,
            allowed=False,
            denied_reason="ip-not-in-allowlist",
        )
        return JsonResponse(
            {
                "ok": False,
                "error": "This inspection link may only be used from an approved network.",
            },
            status=403,
        )
    auditor_access.log_access(grant, resource="auditor:roster", ip_address=client_ip)
    return JsonResponse(
        {
            "ok": True,
            "inspector": grant.inspector_label or grant.inspector_email or "Inspector",
            "scope": grant.scope,
            "expires_at": grant.expires_at.isoformat(),
            "read_only": True,
            "pii_masked": True,
            "students": auditor_access.masked_roster_for_grant(grant),
        }
    )


@method_decorator(staff_member_required, name="dispatch")
class AuditorGrantConsoleView(View):
    """Operator console: create / list / revoke external-auditor grants (JSON)."""

    def get(self, request, *args, **kwargs):
        from apps.compliance.models import AuditorAccessGrant

        school_id = request.GET.get("school")
        qs = AuditorAccessGrant.objects.all()
        if school_id:
            qs = qs.filter(school_id=school_id)
        grants = [
            {
                "id": str(g.id),
                "inspector": g.inspector_label or g.inspector_email,
                "expires_at": g.expires_at.isoformat(),
                "valid": g.is_valid(),
                "revoked": g.is_revoked,
                "ip_allowlist": g.ip_allowlist or [],
                "views": g.access_logs.filter(allowed=True).count(),
                "denied_views": g.access_logs.filter(allowed=False).count(),
            }
            for g in qs[:100]
        ]
        return JsonResponse({"ok": True, "grants": grants})

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "create")
        if action == "revoke":
            ok = auditor_access.revoke_grant(request.POST.get("grant_id"))
            return JsonResponse({"ok": ok})
        school_id = request.POST.get("school")
        if not school_id:
            return JsonResponse({"ok": False, "error": "school is required."}, status=400)
        grant, token = auditor_access.create_grant(
            school_id=school_id,
            inspector_email=request.POST.get("inspector_email", ""),
            inspector_label=request.POST.get("inspector_label", ""),
            created_by_id=getattr(request.user, "id", None),
            ttl_hours=int(request.POST.get("ttl_hours") or 72),
            note=request.POST.get("note", ""),
            ip_allowlist=request.POST.get("ip_allowlist", ""),
        )
        return JsonResponse(
            {"ok": True, "grant_id": str(grant.id), "token": token, "expires_at": grant.expires_at.isoformat()}
        )
