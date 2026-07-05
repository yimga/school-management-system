"""Auditor magic-link views (Wave E — year-end governance).

- ``auditor_inspect`` — PUBLIC, token-gated, no login. Resolves the grant, logs
  the access, returns the PII-masked read-only roster. The token is the auth.
- ``AuditorGrantConsoleView`` — staff-only operator console (JSON) to create /
  list / revoke grants.
"""

from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from apps.schools.control_plane import require_control_plane_access
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views import View

from apps.compliance import auditor_access


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def _wants_json(request) -> bool:
    """True when the caller is an API client, not a browser.

    Default is HTML (the magic link is clicked in a browser). JSON is opt-in via
    ``?format=json`` or an ``Accept`` header that asks for JSON over HTML.
    """
    if request.GET.get("format") == "json":
        return True
    if request.method == "POST" and request.POST.get("format") == "json":
        return True
    accept = request.META.get("HTTP_ACCEPT", "")
    return "application/json" in accept and "text/html" not in accept


def auditor_inspect(request):
    """Public inspector landing — masked, read-only, access-logged. Token = auth.

    Renders a self-contained HTML page for browsers; returns JSON for API clients
    (``?format=json`` / ``Accept: application/json``). The signed grant is the auth.
    """
    token = request.GET.get("token", "")
    grant = auditor_access.resolve_grant(token)
    if grant is None:
        message = "This inspection link is invalid, expired or revoked."
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": message}, status=403)
        return HttpResponse(
            render_to_string("compliance/auditor/denied.html", {"message": message}),
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
        message = "This inspection link may only be used from an approved network."
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": message}, status=403)
        return HttpResponse(
            render_to_string("compliance/auditor/denied.html", {"message": message}),
            status=403,
        )
    auditor_access.log_access(grant, resource="auditor:roster", ip_address=client_ip)
    inspector = grant.inspector_label or grant.inspector_email or "Inspector"
    scope = grant.scope
    expires_at = grant.expires_at
    students = auditor_access.masked_roster_for_grant(grant)
    if _wants_json(request):
        return JsonResponse(
            {
                "ok": True,
                "inspector": inspector,
                "scope": scope,
                "expires_at": expires_at.isoformat(),
                "read_only": True,
                "pii_masked": True,
                "students": students,
            }
        )
    html = render_to_string(
        "compliance/auditor/inspect.html",
        {
            "inspector": inspector,
            "scope": scope,
            "expires_at": expires_at,
            "students": students,
        },
    )
    return HttpResponse(html)


_GRANTS_PAGE_SIZE = 100  # magic-number-allow: console listing cap
_SCHOOL_PICKER_CAP = 500  # magic-number-allow: school <select> safety cap


@method_decorator(require_control_plane_access, name="dispatch")
class AuditorGrantConsoleView(View):
    """Operator console: create / list / revoke external-auditor grants.

    Renders an HTML console (with the geo-fence IP-allowlist field) for staff;
    returns the same data as JSON for API clients (``?format=json``). Create uses
    Post/Redirect/Get and shows the freshly-minted magic link exactly once.
    """

    def _grant_rows(self, request):
        from apps.compliance.models import AuditorAccessGrant

        school_id = request.GET.get("school")
        qs = AuditorAccessGrant.objects.select_related("school").all()
        if school_id:
            qs = qs.filter(school_id=school_id)
        return [
            {
                "id": str(g.id),
                "inspector": g.inspector_label or g.inspector_email or "Inspector",
                "school": getattr(g.school, "name", ""),
                "expires_at": g.expires_at,
                "valid": g.is_valid(),
                "revoked": g.is_revoked,
                "ip_allowlist": g.ip_allowlist or [],
                "views": g.access_logs.filter(allowed=True).count(),
                "denied_views": g.access_logs.filter(allowed=False).count(),
            }
            for g in qs[:_GRANTS_PAGE_SIZE]
        ]

    def get(self, request, *args, **kwargs):
        rows = self._grant_rows(request)
        if _wants_json(request):
            json_rows = [
                {**r, "expires_at": r["expires_at"].isoformat()} for r in rows
            ]
            return JsonResponse({"ok": True, "grants": json_rows})

        from apps.schools.models import School

        schools = list(
            School.objects.filter(is_active=True).order_by("name")[:_SCHOOL_PICKER_CAP]
        )
        fresh = request.session.pop("auditor_fresh_grant", None)
        return render(
            request,
            "compliance/auditor/console.html",
            {
                "grants": rows,
                "schools": schools,
                "school_filter": request.GET.get("school", ""),
                "fresh_grant": fresh,
            },
        )

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "create")
        wants_json = _wants_json(request)
        if action == "revoke":
            ok = auditor_access.revoke_grant(request.POST.get("grant_id"))
            if wants_json:
                return JsonResponse({"ok": ok})
            return redirect("compliance:auditor_grants_console")
        school_id = request.POST.get("school")
        if not school_id:
            if wants_json:
                return JsonResponse({"ok": False, "error": "school is required."}, status=400)
            return redirect("compliance:auditor_grants_console")
        grant, token = auditor_access.create_grant(
            school_id=school_id,
            inspector_email=request.POST.get("inspector_email", ""),
            inspector_label=request.POST.get("inspector_label", ""),
            created_by_id=getattr(request.user, "id", None),
            ttl_hours=int(request.POST.get("ttl_hours") or 72),
            note=request.POST.get("note", ""),
            ip_allowlist=request.POST.get("ip_allowlist", ""),
        )
        if wants_json:
            return JsonResponse(
                {
                    "ok": True,
                    "grant_id": str(grant.id),
                    "token": token,
                    "expires_at": grant.expires_at.isoformat(),
                }
            )
        # PRG: stash the one-time secret link in the session, show it once on redirect.
        request.session["auditor_fresh_grant"] = {
            "grant_id": str(grant.id),
            "token": token,
            "inspector": grant.inspector_label or grant.inspector_email or "Inspector",
            "ip_allowlist": grant.ip_allowlist or [],
        }
        return redirect("compliance:auditor_grants_console")
