"""Safeguarding concern persistence — producer for the DSL pathway (metric #11).

Kernel + inbox helpers are storage-agnostic; this module is the single place that
writes ``School.settings["safeguarding"]`` for raise → submit → notify.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import DatabaseError, transaction

from apps.safeguarding.concern_kernel import (
    ACKNOWLEDGED,
    CLOSED,
    DRAFT,
    DSLAssignment,
    SUBMITTED,
    ConcernEntry,
    create_concern,
    get_category,
    is_dsl,
    list_categories,
    open_concerns,
    append_to_school_settings,
    transition_concern,
)
from apps.safeguarding.dsl_notify import (
    acknowledge_inbox_entry,
    build_concern_deep_link,
    list_unacknowledged,
    notify_dsl_of_concern,
)

logger = logging.getLogger(__name__)


def school_id_token(school: Any) -> int:
    """Stable int token for kernel school_id fields (UUID pk → int)."""
    return int(school.pk)


def safeguarding_blob(school: Any) -> dict[str, Any]:
    settings = getattr(school, "settings", None) or {}
    blob = settings.get("safeguarding") if isinstance(settings, dict) else None
    return dict(blob) if isinstance(blob, dict) else {}


def load_dsl_assignments(school: Any) -> list[DSLAssignment]:
    """Build DSLAssignment list from wizard stakeholder_pipeline + dsl_user_ids."""
    blob = safeguarding_blob(school)
    sid = school_id_token(school)
    out: list[DSLAssignment] = []
    seen: set[int] = set()

    for raw in blob.get("dsl_user_ids") or []:
        try:
            uid = int(raw)
        except (TypeError, ValueError):
            continue
        if uid in seen:
            continue
        seen.add(uid)
        out.append(DSLAssignment(user_id=uid, school_id=sid, is_active=True))

    for row in blob.get("stakeholder_pipeline") or []:
        if isinstance(row, dict):
            if str(row.get("role") or "").lower() not in {"dsl", "designated_safeguarding_lead", ""}:
                # Accept explicit DSL role; also accept bare user_id rows.
                if "user_id" not in row and "id" not in row:
                    continue
            raw_uid = row.get("user_id") if row.get("user_id") is not None else row.get("id")
        else:
            raw_uid = row
        try:
            uid = int(raw_uid)
        except (TypeError, ValueError):
            continue
        if uid in seen:
            continue
        seen.add(uid)
        out.append(DSLAssignment(user_id=uid, school_id=sid, is_active=True))

    return out


def user_is_dsl(user: Any, school: Any) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = getattr(user, "role", None) or ""
    if str(role).upper() in {"ADMIN", "PRINCIPAL", "OWNER"}:
        # Tenant admins can triage until a dedicated DSL roster is configured.
        assignments = load_dsl_assignments(school)
        if not assignments:
            return True
    return is_dsl(int(user.pk), school_id_token(school), load_dsl_assignments(school))


# Admin-tier roles that may triage safeguarding concerns until a dedicated DSL
# roster is configured (mirrors ``user_is_dsl``'s fallback). Used as the fallback
# recipient pool for the urgent real-time alert.
_DSL_FALLBACK_ROLES = ("ADMIN", "PRINCIPAL", "OWNER")  # role-string-allow: safeguarding-dsl-triage-fallback-pool


def resolve_dsl_recipients(school: Any) -> list:
    """Resolve the ``User`` rows an urgent safeguarding alert must reach.

    Primary pool: the configured DSL roster (``dsl_user_ids`` +
    ``stakeholder_pipeline``). Fallback (no roster yet): admin/principal/owner
    members can triage — so a concern raised at a school that has not named a DSL
    is still delivered to a real person, never dispatched into the void.
    """
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    user_ids = [a.user_id for a in load_dsl_assignments(school) if a.user_id]
    if user_ids:
        # tenant-isolation-allow: recipients-are-this-school's-own-configured-dsl-user-ids
        return list(user_model.objects.filter(pk__in=user_ids, is_active=True))

    from apps.schools.models import SchoolMembership

    # tenant-isolation-allow: safeguarding-dsl-fallback-scoped-to-request-school
    memberships = SchoolMembership.objects.filter(
        school=school, role__in=_DSL_FALLBACK_ROLES
    ).select_related("user")
    out: list = []
    seen: set[int] = set()
    for membership in memberships:
        user = getattr(membership, "user", None)
        if user is None or not getattr(user, "is_active", False) or user.pk in seen:
            continue
        seen.add(user.pk)
        out.append(user)
    return out


def _user_phone(user: Any) -> str:
    """Best-effort phone lookup for a staff recipient.

    DSLs are staff, not guardians, so ``dispatch_event`` reads the SMS number from
    the per-recipient ``context`` rather than a guardian link. Returns "" when no
    number is found — the SMS leg then reports ``no_phone`` honestly (email + the
    in-app bell still carry the alert)."""
    for attr in ("phone", "phone_number", "mobile", "msisdn"):
        val = (getattr(user, attr, "") or "").strip()
        if val:
            return val
    for prof_attr in ("profile", "staff_profile", "teacher_profile"):
        profile = getattr(user, prof_attr, None)
        if profile is None:
            continue
        for attr in ("phone", "phone_number", "mobile"):
            val = (getattr(profile, attr, "") or "").strip()
            if val:
                return val
    return ""


def _dispatch_dsl_alert(*, school: Any, entry: ConcernEntry, category_label: str) -> None:
    """Fire a real-time alert to every DSL the moment a concern is raised.

    Before this, a concern only landed in a poll-only ``dsl_inbox`` bucket — an
    abuse / FGM / self-harm disclosure could sit unseen until a DSL happened to
    open the queue. Now urgent categories escalate to SMS + email + the in-app
    bell; non-urgent concerns still ring the bell + email so nothing waits on a
    poll. PII stays OUT of the payload — the deep link is the only path to the
    narrative (matching the ``dsl_notify`` contract). Best-effort: a dispatch
    failure must never unwind the concern submission itself.
    """
    try:
        from django.db import transaction as _txn

        from apps.communication.dispatch import Channel, dispatch_event
        from apps.finance.models import Notification

        recipients = resolve_dsl_recipients(school)
        if not recipients:
            logger.warning(
                "safeguarding.no_dsl_recipient concern=%s school=%s",
                entry.concern_id,
                getattr(school, "pk", None),
            )
            return

        if entry.is_urgent:
            channels = [Channel.SMS, Channel.EMAIL, Channel.IN_APP]
            severity = Notification.Severity.ALERT
            prefix = "Urgent safeguarding concern"
        else:
            channels = [Channel.EMAIL, Channel.IN_APP]
            severity = Notification.Severity.WARNING
            prefix = "New safeguarding concern"
        # The title has to identify THIS concern. _send_in_app routes through
        # Notification.objects.notify_unread, which update_or_creates on
        # (recipient, title, is_read=False) -- right for "New message from Mr
        # Smith", where the reader wants the latest; wrong here, because a
        # constant title meant the second urgent disclosure of the day OVERWROTE
        # the first one's bell entry and the DSL could no longer reach the
        # earlier child's concern from the queue she works from. The reference is
        # what makes it distinct; the category is what makes it readable.
        reference = str(entry.concern_id)[:8]
        title = f"{prefix}: {category_label} ({reference})"
        message = (
            f"A {category_label} concern needs a Designated Safeguarding Lead. "
            "Open it to review."
        )
        link = build_concern_deep_link(entry.concern_id)

        # SAVEPOINT, and it is what makes the 'never unwind submit' promise in
        # this function's docstring actually true. The caller is
        # @transaction.atomic and dispatch_event writes a Notification row for
        # the in-app bell, so a database error here sets
        # connection.needs_rollback -- and the broad `except` below does NOT
        # clear it. The outer block then rolls back the CONCERN along with the
        # alert: a child-protection disclosure accepted, reported as recorded,
        # and silently gone. Rolling back to a savepoint is what clears the flag.
        with _txn.atomic():
            for user in recipients:
                dispatch_event(
                    "safeguarding.concern_raised",
                    recipient=user,
                    school=school,
                    context={
                        "title": title,
                        "message": message,
                        "link": link,
                        "severity": severity,
                        "phone": _user_phone(user),
                    },
                    channels=channels,
                )
    except Exception:  # noqa: BLE001 — alert must never unwind submit
        logger.warning(
            "safeguarding.dsl_alert_failed concern=%s school=%s",
            getattr(entry, "concern_id", None),
            getattr(school, "pk", None),
            exc_info=True,
        )


def find_concern(school: Any, concern_id: str) -> ConcernEntry | None:
    blob = safeguarding_blob(school)
    for row in blob.get("concerns") or []:
        if not isinstance(row, dict):
            continue
        if row.get("concern_id") != concern_id:
            continue
        return ConcernEntry(
            concern_id=str(row.get("concern_id") or ""),
            school_id=int(row.get("school_id") or school_id_token(school)),
            student_id=row.get("student_id"),
            reporter_user_id=int(row.get("reporter_user_id") or 0),
            category_key=str(row.get("category_key") or "other"),
            stage=str(row.get("stage") or DRAFT),
            narrative=str(row.get("narrative") or ""),
            is_urgent=bool(row.get("is_urgent")),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
            history=list(row.get("history") or []),
            dsl_acknowledged_by=row.get("dsl_acknowledged_by"),
            dsl_acknowledged_at=str(row.get("dsl_acknowledged_at") or ""),
            referral_reference=str(row.get("referral_reference") or ""),
        )
    return None


def _locked_school(school: Any):
    """Re-read the School row under a lock, inside the caller's transaction.

    Both writers below rewrite the WHOLE of ``School.settings``. Starting from
    the caller's in-memory copy means any write that landed since that object
    was loaded is erased -- a second concern raised moments after the first wiped
    it out, and a concern raised while any other tenant setting was being saved
    took that with it. settings is the shared per-tenant blob, not safeguarding's
    own.

    select_for_update is a no-op on SQLite and a real row lock on PostgreSQL; the
    re-read is what fixes the stale-copy half, the lock is what serialises two
    genuinely concurrent submissions. Returns the caller's object unchanged if the
    row cannot be re-read, so this can never be the reason a disclosure is lost.
    """
    from apps.schools.models import School

    pk = getattr(school, "pk", None)
    if pk is None:
        return school
    try:
        # tenant-isolation-allow: re-reads the caller's own school row by pk
        return School.objects.select_for_update().get(pk=pk)
    except (School.DoesNotExist, DatabaseError):
        logger.warning(
            "safeguarding.school_relock_failed school=%s", pk, exc_info=True
        )
        return school


def _persist_audit_row(row) -> None:
    """Write one kernel ``AuditRow`` to the compliance audit trail.

    ``apps/safeguarding/README.md`` states this as an invariant, not a logging
    preference: *every transition writes exactly one CRITICAL-sensitivity audit
    row*. The kernel upholds its half -- ``create_concern`` and
    ``transition_concern`` each return a fully-populated row whose own docstring
    says it mirrors ``apps.compliance.models_audit.AuditLog`` -- and the service
    layer discarded all three of them.

    Deliberately NOT wrapped in a best-effort ``except``, unlike the DSL notify
    and the real-time alert beside it. Those are notifications; this is the audit
    trail. Both callers are ``@transaction.atomic`` and this INSERT rides the same
    connection as the concern write, so letting it raise keeps the pair
    all-or-nothing: there is never a persisted child-protection concern without
    its audit row, and a database that cannot take this row could not have taken
    the concern either.
    """
    from apps.compliance.models_audit import AuditLog

    AuditLog.objects.create(
        user_id=row.user_id,
        action=row.action,
        model_name=row.model_name,
        object_id=row.object_id,
        sensitivity=row.sensitivity,
        # The kernel puts only the SHAPE of the disclosure here -- category, stage,
        # urgency -- never the narrative. Keep it that way.
        new_values=row.new_values,
        reason=row.reason,
        app_label=row.app_label,
    )


@transaction.atomic
def submit_concern_for_school(
    *,
    school: Any,
    reporter_user_id: int,
    category_key: str,
    narrative: str,
    student_id: int | None = None,
) -> ConcernEntry:
    """Create → SUBMITTED → persist ledger + DSL inbox (atomic school.settings write)."""
    entry, created_audit = create_concern(
        school_id=school_id_token(school),
        student_id=student_id,
        reporter_user_id=reporter_user_id,
        category_key=category_key,
        narrative=narrative,
    )
    _persist_audit_row(created_audit)
    entry, submitted_audit = transition_concern(
        concern=entry,
        target_stage=SUBMITTED,
        actor_user_id=reporter_user_id,
    )
    _persist_audit_row(submitted_audit)

    caller_school = school
    school = _locked_school(school)
    settings = dict(getattr(school, "settings", None) or {})
    settings = append_to_school_settings(school_settings=settings, concern=entry)
    blob = dict(settings.get("safeguarding") or {})

    cat = get_category(category_key)
    try:
        result = notify_dsl_of_concern(
            current_inbox=list(blob.get("dsl_inbox") or []),
            concern_id=entry.concern_id,
            category_key=entry.category_key,
            category_label=(cat.label if cat else entry.category_key),
            is_urgent=entry.is_urgent,
            submitted_by_user_id=reporter_user_id,
            student_id=int(student_id or 0) or 1,
        )
        blob["dsl_inbox"] = result.updated_inbox
    except Exception:  # noqa: BLE001 — notify must never unwind submit
        logger.warning(
            "safeguarding.notify_failed concern=%s school=%s",
            entry.concern_id,
            school.pk,
            exc_info=True,
        )

    settings["safeguarding"] = blob
    school.settings = settings
    school.save(update_fields=["settings"])
    # The caller still holds the object it passed in; leaving it stale would make
    # an immediate follow-up call (find_concern, acknowledge) miss what we just
    # wrote.
    if caller_school is not school:
        caller_school.settings = settings

    # Real-time DSL alert (best-effort — never unwinds the persisted concern).
    _dispatch_dsl_alert(
        school=school,
        entry=entry,
        category_label=(cat.label if cat else entry.category_key),
    )
    return entry


@transaction.atomic
def acknowledge_and_transition(
    *,
    school: Any,
    concern_id: str,
    actor_user_id: int,
    target_stage: str,
    note: str = "",
    referral_reference: str = "",
    inbox_entry_id: str = "",
) -> ConcernEntry:
    # Lock and re-read BEFORE looking the concern up: the caller's object may
    # predate the submit that created it, and the whole blob is rewritten below.
    caller_school = school
    school = _locked_school(school)
    concern = find_concern(school, concern_id)
    if concern is None:
        raise ValueError("concern_not_found")
    assignments = load_dsl_assignments(school)
    # If no DSL roster, allow tenant admin actors via synthetic self-assignment.
    if not assignments:
        assignments = [
            DSLAssignment(
                user_id=actor_user_id,
                school_id=school_id_token(school),
                is_active=True,
            )
        ]
    updated, transition_audit = transition_concern(
        concern=concern,
        target_stage=target_stage,
        actor_user_id=actor_user_id,
        dsl_assignments=assignments,
        note=note,
        referral_reference=referral_reference,
    )
    _persist_audit_row(transition_audit)

    settings = dict(getattr(school, "settings", None) or {})
    settings = append_to_school_settings(school_settings=settings, concern=updated)
    blob = dict(settings.get("safeguarding") or {})
    inbox = list(blob.get("dsl_inbox") or [])
    if inbox_entry_id:
        inbox = acknowledge_inbox_entry(
            current_inbox=inbox,
            entry_id=inbox_entry_id,
            acknowledged_by_user_id=actor_user_id,
        )
    elif target_stage in {ACKNOWLEDGED, CLOSED}:
        # Acknowledge matching concern inbox rows when entry_id not supplied.
        for row in inbox:
            if row.get("concern_id") == concern_id and not row.get("acknowledged_at_iso"):
                inbox = acknowledge_inbox_entry(
                    current_inbox=inbox,
                    entry_id=str(row.get("entry_id") or ""),
                    acknowledged_by_user_id=actor_user_id,
                )
                break
    blob["dsl_inbox"] = inbox
    settings["safeguarding"] = blob
    school.settings = settings
    school.save(update_fields=["settings"])
    if caller_school is not school:
        caller_school.settings = settings
    return updated


def maybe_open_concern_from_discipline_incident(
    *,
    school: Any,
    incident: Any,
    recorded_by: Any | None = None,
) -> ConcernEntry | None:
    """Best-effort HIGH-severity discipline → safeguarding concern bridge."""
    from apps.academics.models import Incident

    severity = (getattr(incident, "severity", None) or "").upper()
    if severity != Incident.Severity.HIGH:
        return None
    reporter_id = int(getattr(recorded_by, "pk", None) or getattr(incident, "recorded_by_id", None) or 0)
    if reporter_id <= 0:
        return None
    student_id = getattr(incident, "student_id", None)
    narrative = (getattr(incident, "description", None) or "").strip()
    if len(narrative) < 10:
        narrative = (
            f"High-severity discipline incident "
            f"{getattr(incident, 'incident_type', 'incident')} "
            f"(id={getattr(incident, 'pk', '')}). Staff review required."
        )
    try:
        return submit_concern_for_school(
            school=school,
            reporter_user_id=reporter_id,
            category_key="other",
            narrative=narrative[:4000],
            student_id=int(student_id) if student_id else None,
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "safeguarding.discipline_bridge_failed incident=%s school=%s",
            getattr(incident, "pk", None),
            getattr(school, "pk", None),
            exc_info=True,
        )
        return None


def enabled_categories_for_school(school: Any) -> list:
    blob = safeguarding_blob(school)
    enabled = blob.get("enabled_categories")
    all_cats = list_categories()
    if not enabled:
        return all_cats
    known = {c.key: c for c in all_cats}
    return [known[k] for k in enabled if k in known] or all_cats


def inbox_rows(school: Any) -> list[dict[str, Any]]:
    return list_unacknowledged(safeguarding_blob(school).get("dsl_inbox"))


def open_concern_rows(school: Any) -> list[dict[str, Any]]:
    return open_concerns(getattr(school, "settings", None) or {})
