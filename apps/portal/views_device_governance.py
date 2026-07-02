"""Offline-device governance operator UI (9.8 device-governance wave, 2026-07-02).

Before this surface existed, ``DeviceRegistration.revoked_at`` was a field with
no capability behind it: no view could set it, and both mint paths reset it to
``None`` — a stolen device could silently un-revoke itself by re-minting. This
module makes revocation real:

  * ``GET  /portal/super/devices/`` — registry index, filterable by
    ``?school=<id>``, ``?user=<id>``, ``?status=active|revoked``.
  * ``POST /portal/super/devices/revoke/`` — revoke one device AND all of its
    outstanding capability tokens (cascade), audited.
  * ``POST /portal/super/devices/reinstate/`` — the ONLY legitimate un-revoke
    path (explicit, audited operator action; mint paths refuse revoked devices).
"""
from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


def _audit_device_action(request: HttpRequest, action, device, note: str) -> None:
    """Best-effort compliance audit trail — never breaks the operator action."""
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            action=action,
            user=request.user if getattr(request.user, "is_authenticated", False) else None,
            model_name="DeviceRegistration",
            object_id=str(device.pk)[:200],
            object_repr=f"device {device.device_id} ({note})"[:200],
            app_label="accounts",
            new_values={
                "device_id": device.device_id,
                "school_id": str(device.school_id),
                "user_id": device.user_id,
                "revoked_at": device.revoked_at.isoformat() if device.revoked_at else None,
            },
        )
    except Exception:
        logger.warning("device_governance_audit_failed device=%s", device.pk)


@staff_member_required
@require_http_methods(["GET"])
def device_registrations_index(request: HttpRequest):
    from apps.accounts.models_offline_device import DeviceRegistration

    qs = DeviceRegistration.objects.select_related("user", "school").order_by("-created_at")  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    school = (request.GET.get("school") or "").strip()
    user = (request.GET.get("user") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    if school:
        qs = qs.filter(school_id=school)
    if user:
        qs = qs.filter(user_id=user)
    if status_filter == "active":
        qs = qs.filter(revoked_at__isnull=True)
    elif status_filter == "revoked":
        qs = qs.filter(revoked_at__isnull=False)
    rows = list(qs[:500])

    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": True,
            "rows": [
                {
                    "id": str(r.pk),
                    "device_id": r.device_id,
                    "user_id": r.user_id,
                    "username": r.user.get_username() if r.user else "",
                    "school_id": str(r.school_id),
                    "school_name": getattr(r.school, "name", ""),
                    "is_active": r.is_active,
                    "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else "",
                    "revoked_at": r.revoked_at.isoformat() if r.revoked_at else "",
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ],
            "filter": {"school": school, "user": user, "status": status_filter},
        })
    return render(request, "super/devices/registrations_index.html", {
        "rows": rows,
        "filter_school": school,
        "filter_user": user,
        "filter_status": status_filter,
    })


def _resolve_device(request: HttpRequest):
    from apps.accounts.models_offline_device import DeviceRegistration

    device_pk = (request.POST.get("device") or "").strip()
    if not device_pk:
        return None, JsonResponse({"error": "missing_device"}, status=400)
    device = DeviceRegistration.objects.filter(pk=device_pk).select_related("user", "school").first()  # tenant-isolation-allow: operator-device-resolve-by-pk-staff-required
    if device is None:
        return None, JsonResponse({"error": "device_not_found"}, status=404)
    return device, None


def _governance_response(request: HttpRequest, payload: dict):
    if (request.GET.get("format") or "").lower() == "json" or (request.POST.get("format") or "").lower() == "json":
        return JsonResponse(payload)
    return HttpResponseRedirect(reverse("portal:device_registrations_index"))


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def device_registration_revoke(request: HttpRequest):
    """Revoke one device and cascade-revoke its outstanding capability tokens.

    Already-minted signed IAM snapshots keep self-verifying offline until they
    expire (client-side, no server round-trip) — that residual window is bounded
    by the snapshot TTL and documented; what this endpoint guarantees is that
    the device can never mint again and every server-checkable token dies now.
    """
    from apps.accounts.models_offline_device import OfflineCapabilityToken
    from apps.compliance.models_audit import AuditLog

    device, err = _resolve_device(request)
    if err is not None:
        return err
    now = timezone.now()
    if device.revoked_at is None:
        device.revoked_at = now
        device.save(update_fields=["revoked_at"])
    tokens_revoked = OfflineCapabilityToken.objects.filter(
        school=device.school, device=device, revoked_at__isnull=True
    ).update(revoked_at=now)
    _audit_device_action(request, AuditLog.Action.PERMISSION_REVOKE, device, "revoked")
    logger.info(
        "device_governance_revoke device=%s school=%s tokens_revoked=%s",
        device.pk, device.school_id, tokens_revoked,
    )
    return _governance_response(request, {
        "success": True,
        "action": "revoked",
        "device": str(device.pk),
        "tokens_revoked": tokens_revoked,
    })


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def device_registration_reinstate(request: HttpRequest):
    """Explicitly reinstate a revoked device (the only legitimate un-revoke)."""
    from apps.compliance.models_audit import AuditLog

    device, err = _resolve_device(request)
    if err is not None:
        return err
    if device.revoked_at is not None:
        device.revoked_at = None
        device.save(update_fields=["revoked_at"])
    _audit_device_action(request, AuditLog.Action.PERMISSION_GRANT, device, "reinstated")
    logger.info(
        "device_governance_reinstate device=%s school=%s", device.pk, device.school_id,
    )
    return _governance_response(request, {
        "success": True,
        "action": "reinstated",
        "device": str(device.pk),
    })
