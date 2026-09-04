"""Record, approve and decline identity provisioning requests.

The rail refuses to create a person who needs a login. This module is where that
refusal turns into a question a human can answer, and where answering it does the
one thing the rail must not: mint the account.

Everything here is deliberately on the CLOUD side of the boundary. The box writes
nothing through this module; it submits an ordinary insert, is refused, and the
refusal is what calls :func:`record_refused_insert`.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

# Fields that must never be copied out of a sync payload into a request, even
# though the rail should already have dropped them. Belt and braces on purpose:
# this is the boundary between "data" and "credential", and it is the one place
# where being wrong means a bundle can set a password.
_NEVER_CARRIED = frozenset(
    {
        "password",
        "is_superuser",
        "is_staff",
        "is_active",
        "user_id",
        "user",
        "last_login",
        "session",
        "mfa_secret",
        "totp",
    }
)

#: Entities whose refusal is worth asking a human about.
SUPPORTED_ENTITIES = frozenset({"teacher", "student_guardian"})

#: Both supported entities can be approved. The guardian case took longer to get
#: right and the reason is worth keeping: a guardian LINK names a student by the
#: BOX's local pk, and the rail's FK remapping never ran because the row was
#: refused before that point. On the cloud that number may name a different
#: child entirely -- a box-created student is assigned a fresh pk up here -- so
#: resolving it in code would be a guess dressed as a lookup.
#:
#: It is not resolved in code. ``approve_provisioning_request`` REQUIRES the
#: caller to name the student, and the queue shows a candidate (looked up by that
#: pk, within the school, by name) for a person to confirm or correct. That is
#: the same principle the whole handshake rests on: the ambiguous half is decided
#: by a human who can see a name, and the machine does the unambiguous half.
APPROVABLE_ENTITIES = frozenset({"teacher", "student_guardian"})


def sanitize_payload(values: Any) -> dict:
    """Keep the portable data, drop anything credential-shaped."""
    if not isinstance(values, dict):
        return {}
    return {
        str(k): v
        for k, v in values.items()
        if str(k).lower() not in _NEVER_CARRIED and not str(k).lower().startswith("password")
    }


def record_refused_insert(
    *,
    school_id,
    entity_type: str,
    client_offline_id: str,
    values: Any,
    requested_role: str = "",
):
    """Turn a held insert into a pending question. Never raises into the rail.

    Returns the request, or ``None`` when there is nothing to record. A sync
    cycle must not fail because the queue could not be written -- the refusal
    itself is still correct and still returned to the box.
    """
    if entity_type not in SUPPORTED_ENTITIES:
        return None
    if not school_id or not client_offline_id:
        return None
    try:
        from apps.people.models_provisioning import ProvisioningRequest

        payload = sanitize_payload(values)
        if entity_type == "student_guardian":
            payload = _attach_student_candidate(payload, school_id)
        with transaction.atomic():
            row, created = ProvisioningRequest.objects.get_or_create(
                school_id=school_id,
                entity_type=entity_type,
                client_offline_id=str(client_offline_id),
                defaults={
                    "payload": payload,
                    "requested_role": str(requested_role or "")[:64],
                },
            )
            if not created:
                # The box re-submits every cycle. Count it and refresh the data,
                # but NEVER reopen a decision a person already made -- an
                # approved row that keeps arriving is normal (the box has not
                # pulled the answer down yet), and a declined one must not
                # silently return to the queue on the next cycle.
                fields = ["times_seen", "last_seen_at"]
                row.times_seen = (row.times_seen or 0) + 1
                if row.status == ProvisioningRequest.Status.PENDING:
                    row.payload = payload
                    row.requested_role = str(requested_role or "")[:64]
                    fields += ["payload", "requested_role"]
                row.save(update_fields=fields)
        return row
    except Exception:  # noqa: BLE001 — a queue write never breaks a sync cycle
        return None


def _attach_student_candidate(payload: dict, school_id) -> dict:
    """Note WHICH child the box's number points at here, for a human to check.

    Stored under ``student_candidate_*`` and never under ``student_id``: the
    naming is the safety. Approval reads neither -- it takes the student from its
    caller -- so a wrong candidate is a wrong suggestion on a screen, not a
    guardian attached to somebody else's child.
    """
    try:
        from apps.people.models import StudentProfile

        raw = payload.get("student_id") or payload.get("student")
        if raw in (None, ""):
            return payload
        student = StudentProfile.objects.filter(
            pk=int(raw), school_id=school_id
        ).first()
        if student is None:
            payload["student_candidate_note"] = (
                "The box referred to student #%s, which does not exist on the cloud. "
                "Choose the student by hand." % raw
            )
            return payload
        payload["student_candidate_pk"] = student.pk
        payload["student_candidate_name"] = " ".join(
            p for p in (student.first_name, student.last_name) if p
        ).strip()
        payload["student_candidate_admission_number"] = student.admission_number or ""
        payload["student_candidate_note"] = (
            "Matched by the box's own id, which is NOT reliable across nodes. "
            "Confirm this is the right child before approving."
        )
    except (TypeError, ValueError, AttributeError):
        return payload
    return payload


def approve_provisioning_request(
    request_row, *, actor, role: str = "", student_id=None
):
    """Mint the account the box asked for, carrying the box's anchor.

    The anchor is the point. A User created here without ``client_offline_id`` on
    the profile would be a SECOND person: the box would keep submitting its own
    row, be refused again, and the queue would fill with a request that approval
    already answered. Carrying it means the next ordinary sync matches the two by
    anchor and converges them.
    """
    from apps.accounts.models import User
    from apps.people.bulk_staff_actions import FORBIDDEN_ROLES
    from apps.people.models import TeacherProfile
    from apps.people.models_provisioning import ProvisioningRequest

    if request_row.status != ProvisioningRequest.Status.PENDING:
        raise ValueError("This request has already been decided.")
    if request_row.entity_type not in APPROVABLE_ENTITIES:
        raise ValueError(
            "%s is not an entity this queue can approve." % request_row.entity_type
        )
    if request_row.entity_type == "student_guardian":
        return _approve_guardian(request_row, actor=actor, student_id=student_id)

    role = (role or request_row.requested_role or User.Role.SUPPORT_STAFF).strip().upper()
    if role in FORBIDDEN_ROLES:
        raise ValueError("%s cannot be granted from a provisioning request." % role)
    if role not in {choice[0] for choice in User.Role.choices}:
        role = User.Role.SUPPORT_STAFF

    payload = request_row.payload or {}
    first = str(payload.get("first_name") or "").strip()
    last = str(payload.get("last_name") or "").strip()
    email = str(payload.get("email") or "").strip()
    staff_id = str(payload.get("staff_id") or "").strip()

    username = _unique_username(first, last, email, request_row.client_offline_id)

    with transaction.atomic():
        user = User(
            username=username,
            first_name=first[:150],
            last_name=last[:150],
            email=email[:254],
            role=role,
        )
        # The account exists and cannot be signed into. Activation is a separate,
        # deliberate act (invite or reset) -- approving a person is not the same
        # decision as handing them a credential, and collapsing the two here
        # would rebuild the exact hole the identity hold exists to prevent.
        user.set_unusable_password()
        user.save()

        profile = TeacherProfile.objects.create(
            user=user,
            school=request_row.school,
            staff_id=staff_id or "",
            phone=str(payload.get("phone") or "")[:50],
            client_offline_id=request_row.client_offline_id,
        )
        request_row.status = ProvisioningRequest.Status.APPROVED
        request_row.decided_by = actor if getattr(actor, "pk", None) else None
        request_row.decided_at = timezone.now()
        request_row.created_user = user
        request_row.save(
            update_fields=["status", "decided_by", "decided_at", "created_user"]
        )
    return profile


def decline_provisioning_request(request_row, *, actor, reason: str = ""):
    """Answer the question with no, so the box stops being told nothing."""
    from apps.people.models_provisioning import ProvisioningRequest

    if request_row.status != ProvisioningRequest.Status.PENDING:
        raise ValueError("This request has already been decided.")
    request_row.status = ProvisioningRequest.Status.DECLINED
    request_row.decided_by = actor if getattr(actor, "pk", None) else None
    request_row.decided_at = timezone.now()
    request_row.decline_reason = str(reason or "")[:2000]
    request_row.save(
        update_fields=["status", "decided_by", "decided_at", "decline_reason"]
    )
    return request_row


def _approve_guardian(request_row, *, actor, student_id):
    """Create the guardian account and link it to the child a PERSON named."""
    from apps.accounts.models import User
    from apps.people.models import StudentGuardian, StudentProfile
    from apps.people.models_provisioning import ProvisioningRequest

    if student_id in (None, ""):
        raise ValueError(
            "Choose which student this guardian belongs to. The box identified the "
            "child by its own record number, which does not name the same child here."
        )
    student = StudentProfile.objects.filter(
        pk=student_id, school=request_row.school
    ).first()
    if student is None:
        # Scoped by school, so a number belonging to another tenant reads as
        # "not found" rather than quietly linking a guardian across schools.
        raise ValueError("That student is not in this school.")

    payload = request_row.payload or {}
    first = str(payload.get("first_name") or "").strip()
    last = str(payload.get("last_name") or "").strip()
    email = str(payload.get("email") or "").strip()

    with transaction.atomic():
        user = User(
            username=_unique_username(first, last, email, request_row.client_offline_id),
            first_name=first[:150],
            last_name=last[:150],
            email=email[:254],
            role=User.Role.PARENT,
        )
        user.set_unusable_password()
        user.save()

        link = StudentGuardian.objects.create(
            guardian_user=user,
            student=student,
            school=request_row.school,
            relationship=str(payload.get("relationship") or "")[:120],
            phone=str(payload.get("phone") or "")[:50],
            email=email[:254],
            client_offline_id=request_row.client_offline_id,
            # Both ride DOWN-ONLY on the rail: authorisation is the cloud's to
            # grant, so a link created from a box's request starts with neither.
            can_view_finance=False,
            can_view_results=False,
        )
        request_row.status = ProvisioningRequest.Status.APPROVED
        request_row.decided_by = actor if getattr(actor, "pk", None) else None
        request_row.decided_at = timezone.now()
        request_row.created_user = user
        request_row.save(
            update_fields=["status", "decided_by", "decided_at", "created_user"]
        )
    return link


def _unique_username(first: str, last: str, email: str, anchor: str) -> str:
    """A username that is stable-ish, readable, and definitely free."""
    from apps.accounts.models import User

    base = (email.split("@")[0] if email else ".".join(p for p in (first, last) if p))
    base = "".join(ch for ch in base.lower() if ch.isalnum() or ch in "._-").strip("._-")
    if not base:
        # slugify-style bases collapse to "" for a non-Latin name, and "" is not
        # a username -- fall back to the anchor, which is unique by construction.
        base = "staff-%s" % str(anchor)[:24]
    candidate = base[:140]
    if not User.objects.filter(username=candidate).exists():
        return candidate
    for n in range(2, 500):
        candidate = "%s%d" % (base[:135], n)
        if not User.objects.filter(username=candidate).exists():
            return candidate
    return "staff-%s" % str(anchor)[:140]
