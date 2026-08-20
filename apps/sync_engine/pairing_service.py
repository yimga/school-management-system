"""The four moves of box<->cloud pairing, with the rules in one place.

``start`` (box, unauthenticated) -> ``approve`` / ``deny`` (cloud, authenticated
admin) -> ``collect`` (box, authenticated by its poll secret).

Every function here returns a plain dict and never raises for an ordinary failure —
an unknown code, a wrong secret, an expired request are all NORMAL outcomes of a
protocol that runs unattended across a bad link, not exceptions. The views turn these
dicts into responses; keeping the decisions here is what lets the tests drive the
protocol without HTTP.

THE ONE RULE WORTH STATING TWICE: ``collect`` mints the machine credential and is the
only place the raw token exists. It is never written to the database, never logged,
and never returned twice — the status transition to ``redeemed`` happens inside the
same locked transaction that mints, so two concurrent polls cannot both walk away with
a credential.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.sync_engine.models_pairing import (
    EdgePairingRequest,
    normalize_user_code,
)

logger = logging.getLogger(__name__)


def _school_for_slug(slug: str):
    from apps.schools.models import School

    slug = (slug or "").strip().lower()
    if not slug:
        return None
    # tenant-isolation-allow: pairing-resolves-which-school-a-box-claims-before-any-tenant-context-exists
    return School.objects.filter(slug=slug).first()


def start_pairing(
    *,
    claimed_slug: str,
    device_id: str = "",
    box_label: str = "",
    box_hostname: str = "",
    box_ip: str | None = None,
    box_version: str = "",
) -> dict:
    """Open a pairing request. Called by an UNAUTHENTICATED box.

    Anonymous by necessity: a box that has never been paired holds no credential, so
    there is nothing to authenticate with. What that buys an attacker is one row in a
    review queue and a code that is useless without an admin approving it — and the
    approval screen shows exactly what the box claimed, so a bogus request is visible
    rather than silent.

    An unrecognised slug is NOT an error. It still opens a request (with
    ``school=None``) so a technician who mistyped a slug sees "waiting for approval"
    and an operator sees a request nobody can approve — a diagnosable state, rather
    than a 404 the box would report as a connectivity failure.
    """
    school = _school_for_slug(claimed_slug)
    request, raw_secret = EdgePairingRequest.open_request(
        school=school,
        claimed_slug=claimed_slug,
        device_id=device_id,
        box_label=box_label,
        box_hostname=box_hostname,
        box_ip=box_ip,
        box_version=box_version,
    )
    logger.info(
        "sync_engine.pairing: request %s opened for slug=%r (school_resolved=%s) device=%r",
        request.user_code,
        claimed_slug,
        bool(school),
        device_id,
    )
    notify_admins_of_pending_pairing(request)
    return {
        "ok": True,
        "request_id": str(request.id),
        "user_code": request.user_code,
        "poll_secret": raw_secret,
        "expires_at": request.expires_at.isoformat(),
        "school_resolved": bool(school),
    }


def collect_pairing(*, request_id: str, poll_secret: str) -> dict:
    """Box asks 'am I approved yet?' — and collects the credential if so.

    Returns ``{"status": ...}``. Only the ``approved`` transition carries a
    ``credential``, and only once.
    """
    from apps.sync_engine.edge_outbox import mint_edge_credential

    # tenant-isolation-allow: pairing-poll-is-keyed-on-an-unguessable-request-id-plus-secret-before-tenant-context
    base = EdgePairingRequest.objects.filter(pk=request_id)
    request = base.select_related("school", "approved_by").first()
    if request is None:
        return {"ok": False, "status": "unknown", "error": "unknown_request"}
    if not request.verify_poll_secret(poll_secret):
        # Deliberately identical to the unknown-request answer. Distinguishing them
        # would turn this endpoint into an oracle for which request ids exist.
        logger.warning(
            "sync_engine.pairing: poll for %s presented a bad secret", request_id
        )
        return {"ok": False, "status": "unknown", "error": "unknown_request"}

    request.touch_poll()
    status = request.effective_status()

    if status == EdgePairingRequest.Status.EXPIRED:
        request.expire_if_due()
        return {"ok": False, "status": "expired", "error": "expired"}
    if status == EdgePairingRequest.Status.DENIED:
        return {
            "ok": False,
            "status": "denied",
            "error": "denied",
            "reason": request.denied_reason,
        }
    if status == EdgePairingRequest.Status.REDEEMED:
        # Already collected. Not an error the box should retry — it means this box (or
        # something holding its secret) already has the credential.
        return {"ok": False, "status": "redeemed", "error": "already_redeemed"}
    if status == EdgePairingRequest.Status.PENDING:
        return {"ok": True, "status": "pending", "user_code": request.user_code}

    # APPROVED — mint and hand over, exactly once.
    with transaction.atomic():
        locked = (
            EdgePairingRequest.objects.select_for_update()  # tenant-isolation-allow: pairing-redeem-locks-the-single-row-by-pk
            .filter(pk=request.pk, status=EdgePairingRequest.Status.APPROVED)
            .select_related("school", "approved_by")
            .first()
        )
        if locked is None:
            # Another poll won the race between the read above and this lock.
            return {"ok": False, "status": "redeemed", "error": "already_redeemed"}
        school = locked.school
        approver = locked.approved_by
        if school is None or approver is None:
            logger.error(
                "sync_engine.pairing: request %s is approved but has no school/approver",
                locked.user_code,
            )
            return {"ok": False, "status": "error", "error": "incomplete_approval"}
        try:
            raw_token, token = mint_edge_credential(
                school,
                approver,
                device_id=locked.device_id or "",
            )
        except ValueError as exc:
            # mint refuses to re-arm a REVOKED device: reinstatement is an explicit
            # operator action, and silently minting around a revocation would undo it.
            logger.warning(
                "sync_engine.pairing: mint refused for %s: %s", locked.user_code, exc
            )
            return {"ok": False, "status": "error", "error": str(exc)}
        locked.status = EdgePairingRequest.Status.REDEEMED
        locked.redeemed_at = timezone.now()
        locked.credential_device_id = getattr(
            getattr(token, "device", None), "device_id", ""
        )
        locked.save(
            update_fields=["status", "redeemed_at", "credential_device_id"]
        )

    logger.info(
        "sync_engine.pairing: request %s redeemed; box paired to %s",
        locked.user_code,
        getattr(school, "slug", "?"),
    )
    return {
        "ok": True,
        "status": "approved",
        "credential": raw_token,
        "school_slug": getattr(school, "slug", "") or "",
        "school_name": getattr(school, "name", "") or "",
        "expires_at": token.expires_at.isoformat(),
    }


def find_pending_by_code(code: str):
    """Look a request up by the code a human typed. None when it cannot be used."""
    normalized = normalize_user_code(code)
    if not normalized:
        return None
    # tenant-isolation-allow: pairing-code-lookup-precedes-tenant-binding-and-is-authorised-by-the-approver-check
    request = EdgePairingRequest.objects.filter(user_code=normalized).select_related(
        "school"
    ).first()
    if request is None:
        return None
    return request


def approve_pairing(*, code: str, approver, school=None) -> dict:
    """A cloud admin says yes. This is the whole authorization decision.

    ``school``, when given, is the tenant the approver is signed in to; the request's
    claimed school must match it. That is what stops an admin of school A approving a
    box that claimed school B — the check is not "is this person an admin" but "is
    this person an admin OF THE SCHOOL THIS BOX ASKED FOR".
    """
    from apps.accounts.decorators import user_is_tenant_admin

    request = find_pending_by_code(code)
    if request is None:
        return {"ok": False, "error": "unknown_code"}

    status = request.effective_status()
    if status == EdgePairingRequest.Status.EXPIRED:
        request.expire_if_due()
        return {"ok": False, "error": "expired", "user_code": request.user_code}
    if status != EdgePairingRequest.Status.PENDING:
        return {"ok": False, "error": f"not_pending:{status}", "user_code": request.user_code}

    target = request.school
    if target is None:
        # Nobody administers a school that does not exist, so there is no one to
        # approve this and no school to bind a credential to. Reported rather than
        # silently dropped so a mistyped slug is diagnosable from the operator side.
        return {
            "ok": False,
            "error": "unknown_school",
            "claimed_slug": request.claimed_slug,
            "user_code": request.user_code,
        }
    if school is not None and str(getattr(school, "pk", "")) != str(target.pk):
        return {"ok": False, "error": "wrong_tenant", "user_code": request.user_code}
    # Platform staff are the backstop for the case this whole deferred-approval design
    # exists to survive: nobody at the school responds. They already hold control-plane
    # access to every tenant, so approving on a school's behalf grants them nothing new
    # -- but it is recorded in ``approved_by``, and the minted credential is bound to
    # THEM, so an operator-approved box is visibly operator-approved forever after.
    is_platform_staff = bool(
        getattr(approver, "is_superuser", False) or getattr(approver, "is_staff", False)
    )
    if not (is_platform_staff or user_is_tenant_admin(approver, target)):
        return {"ok": False, "error": "forbidden", "user_code": request.user_code}

    request.status = EdgePairingRequest.Status.APPROVED
    request.approved_at = timezone.now()
    request.approved_by = approver
    request.save(update_fields=["status", "approved_at", "approved_by"])
    logger.info(
        "sync_engine.pairing: %s approved for %s by %s",
        request.user_code,
        target.slug,
        getattr(approver, "username", "?"),
    )
    return {"ok": True, "user_code": request.user_code, "school_slug": target.slug}


def deny_pairing(*, code: str, approver, school=None, reason: str = "") -> dict:
    """Refuse a request. Terminal — the box is told, and stops polling."""
    from apps.accounts.decorators import user_is_tenant_admin

    request = find_pending_by_code(code)
    if request is None:
        return {"ok": False, "error": "unknown_code"}
    if request.effective_status() != EdgePairingRequest.Status.PENDING:
        return {"ok": False, "error": "not_pending", "user_code": request.user_code}
    target = request.school
    if target is not None:
        if school is not None and str(getattr(school, "pk", "")) != str(target.pk):
            return {"ok": False, "error": "wrong_tenant"}
        if not user_is_tenant_admin(approver, target):
            return {"ok": False, "error": "forbidden"}
    elif not getattr(approver, "is_staff", False):
        # Nobody is an admin of a school that does not exist, so only platform staff
        # can clear an unresolvable request out of the queue.
        return {"ok": False, "error": "forbidden"}

    request.status = EdgePairingRequest.Status.DENIED
    request.denied_reason = (reason or "")[:200]
    request.save(update_fields=["status", "denied_reason"])
    logger.info("sync_engine.pairing: %s denied", request.user_code)
    return {"ok": True, "user_code": request.user_code}


def pending_requests_for_school(school):
    """Open requests an admin of ``school`` could act on, newest first."""
    if school is None:
        return EdgePairingRequest.objects.none()
    return (
        EdgePairingRequest.objects.filter(  # tenant-isolation-allow: explicitly-scoped-to-the-caller-s-own-school
            school=school,
            status=EdgePairingRequest.Status.PENDING,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
    )


def notify_admins_of_pending_pairing(request) -> None:
    """Tell the school's admins a box is waiting, out of band.

    This is the piece that makes deferred approval work in practice: the person who
    can approve is rarely at a console when the technician is at the box. It rides the
    platform's existing queue-and-forward rails, so on an edge deployment with no
    outbound path the message is parked and delivered when connectivity returns rather
    than dropped.

    Never raises. A notification that fails must not fail the pairing — the request is
    already durable and visible in the Sync Center, which is the authoritative surface.
    """
    try:
        school = getattr(request, "school", None)
        if school is None:
            return
        from apps.sync_engine.pairing_notifications import send_pairing_request_alert

        send_pairing_request_alert(request)
    except Exception:  # noqa: BLE001 — notification is best-effort by design
        logger.debug(
            "sync_engine.pairing: notification failed for %s",
            getattr(request, "user_code", "?"),
            exc_info=True,
        )


__all__ = [
    "approve_pairing",
    "collect_pairing",
    "deny_pairing",
    "find_pending_by_code",
    "notify_admins_of_pending_pairing",
    "pending_requests_for_school",
    "start_pairing",
]
