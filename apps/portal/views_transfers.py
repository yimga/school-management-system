"""Operator transfer console — /portal/super/transfers/ (Wave B).

Mirrors the device-governance / sync-health console pattern: staff-only,
JSON+HTML off one view (``?format=json``), 500-row cap, best-effort
compliance audit on every mutation. The console drives the TransferCase
FSM: open a case → request guardian consent (token minted ONCE, shown to
the operator exactly once for delivery) → after consent, run the case.
"""

from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

_ROW_CAP = 500
_CONSENT_TEXT_VERSION = "v1"


def _wants_json(request) -> bool:
    source = request.GET if request.method == "GET" else request.POST
    return (source.get("format") or request.GET.get("format") or "").lower() == "json"


def _case_row(case) -> dict:
    return {
        "id": str(case.pk),
        "status": case.status,
        "source_school": getattr(case.source_school, "name", ""),
        "target_school": getattr(case.target_school, "name", ""),
        "source_profile_pk": case.source_profile_pk,
        "domains": case.domains or [],
        "envelope_checksum": (case.envelope_checksum or "")[:12],
        "target_bundle_id": case.target_bundle_id,
        "created_at": case.created_at.isoformat() if case.created_at else "",
    }


def _respond(request, payload: dict, ok: bool = True, status: int = 200):
    if _wants_json(request):
        return JsonResponse({"ok": ok, **payload}, status=status)
    return HttpResponseRedirect(reverse("portal:transfer_cases_index"))


def _audit_transfer_action(request, action: str, case, note: str) -> None:
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            action=action,
            user=request.user if request.user.is_authenticated else None,
            model_name="TransferCase",
            object_id=str(case.pk)[:200],
            object_repr=f"transfer case ({note})"[:200],
            app_label="people",
            new_values={"status": case.status},
        )
    except Exception:  # noqa: BLE001 — audit must never block the console
        logger.warning("transfer_console_audit_failed case=%s", case.pk)


@staff_member_required
@require_http_methods(["GET"])
def transfer_cases_index(request):
    """List transfer cases (platform scope — operator console)."""
    from apps.people.models_transfer import TransferCase

    qs = TransferCase.objects.select_related("source_school", "target_school").order_by("-created_at")  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    status = (request.GET.get("status") or "").strip()
    if status:
        qs = qs.filter(status=status)
    rows = list(qs[:_ROW_CAP])
    if _wants_json(request):
        return JsonResponse({"ok": True, "count": len(rows), "cases": [_case_row(c) for c in rows]})
    return render(
        request,
        "super/transfers/cases_index.html",
        {"cases": rows, "status_filter": status},
    )


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def transfer_case_create(request):
    """Open a draft case for one student → target school."""
    from apps.people.models import StudentProfile
    from apps.people.models_transfer import TransferCase
    from apps.schools.models import School

    student_pk = (request.POST.get("student_pk") or "").strip()
    target_school_id = (request.POST.get("target_school_id") or "").strip()
    profile = StudentProfile.objects.filter(pk=student_pk).select_related("school").first()  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    target = School.objects.filter(pk=target_school_id, is_active=True).first()  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    if profile is None or target is None:
        return _respond(request, {"error": "student or target school not found"}, ok=False, status=404)
    if profile.school_id == target.pk:
        return _respond(request, {"error": "target school must differ from source"}, ok=False, status=400)

    case = TransferCase.objects.create(
        source_school=profile.school,
        target_school=target,
        source_profile_pk=str(profile.pk),
        created_by=request.user if request.user.is_authenticated else None,
    )
    _audit_transfer_action(request, "CREATE", case, "case opened")
    return _respond(request, {"case": _case_row(case)}, status=201)


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def transfer_case_request_consent(request):
    """Mint the guardian consent token; the case blocks until decided.

    The raw token is returned EXACTLY ONCE in this response — the operator
    delivers the consent URL to the guardian (email wiring is a follow-up).
    """
    from django.template.loader import render_to_string

    from apps.people.models_transfer import TransferCase
    from apps.people.models_transfer_consent import TransferConsent

    case_pk = (request.POST.get("case_id") or "").strip()
    guardian_name = (request.POST.get("guardian_name") or "").strip()
    guardian_email = (request.POST.get("guardian_email") or "").strip()
    case = TransferCase.objects.filter(pk=case_pk).first()  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    if case is None:
        return _respond(request, {"error": "case not found"}, ok=False, status=404)
    if not guardian_email:
        return _respond(request, {"error": "guardian_email required"}, ok=False, status=400)
    if case.status != TransferCase.Status.DRAFT:
        return _respond(request, {"error": f"case is {case.status}, not draft"}, ok=False, status=400)

    consent_text = render_to_string(
        "people/transfer_consent/_consent_text_v1.html",
        {"case": case},
    )
    raw_token, consent = TransferConsent.mint(
        case=case,
        guardian_name=guardian_name,
        guardian_email=guardian_email,
        consent_text_version=_CONSENT_TEXT_VERSION,
        consent_text=consent_text,
    )
    case.advance(TransferCase.Status.CONSENT_PENDING, note=f"consent requested ({guardian_email})")
    _audit_transfer_action(request, "UPDATE", case, "consent requested")
    consent_path = reverse("people_transfer_consent_landing") + f"?token={raw_token}"
    return _respond(
        request,
        {
            "case": _case_row(case),
            "consent_id": str(consent.pk),
            # Shown once; only the sha256 is stored.
            "consent_url_path": consent_path,
        },
        status=201,
    )


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def transfer_case_run(request):
    """Execute an APPROVED case (synchronous; the runner covers background ops)."""
    from apps.people.models_transfer import TransferCase
    from apps.people.transfer_service import TransferBlockedError, run_transfer_case

    case_pk = (request.POST.get("case_id") or "").strip()
    case = TransferCase.objects.filter(pk=case_pk).first()  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    if case is None:
        return _respond(request, {"error": "case not found"}, ok=False, status=404)
    try:
        summary = run_transfer_case(case, actor=request.user)
    except TransferBlockedError as exc:
        return _respond(request, {"error": str(exc), "case": _case_row(case)}, ok=False, status=409)
    except Exception as exc:  # noqa: BLE001 — surface, never 500 the console
        logger.exception("transfer_console_run_failed case=%s", case.pk)
        case.refresh_from_db()
        return _respond(
            request,
            {"error": f"{type(exc).__name__}: {exc}", "case": _case_row(case)},
            ok=False,
            status=500,
        )
    _audit_transfer_action(request, "UPDATE", case, "case executed")
    return _respond(request, {"case": _case_row(case), "summary": summary})
