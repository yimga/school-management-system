from __future__ import annotations


from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from apps.communication.models import Message
from apps.finance.models import Notification

from .models import AccessRequest, RequestDecision


def _resolve_scope(*, school=None, target=None):
    resolved_school = school or getattr(target, "school", None)
    schema_name = ""
    if resolved_school is not None:
        schema_name = (
            getattr(resolved_school, "schema_name", "")
            or getattr(resolved_school, "subdomain", "")
            or getattr(resolved_school, "slug", "")
            or ""
        )
    return resolved_school, schema_name


def _safe_actor_display(user) -> str:
    if not user:
        return "System"
    return user.get_full_name() or user.username


def create_access_request(
    *,
    request_type: str,
    requester,
    title: str,
    summary: str = "",
    details: dict | None = None,
    target=None,
    status: str | None = None,
    school=None,
):
    details = details or {}
    content_type = None
    object_id = None
    if target is not None:
        content_type = ContentType.objects.get_for_model(target)
        object_id = str(target.pk)
    resolved_school, schema_name = _resolve_scope(school=school, target=target)

    req = AccessRequest.objects.create(
        request_type=request_type,
        requester=requester,
        title=title or "",
        summary=summary or "",
        details=details,
        school=resolved_school,
        schema_name=schema_name,
        target_content_type=content_type,
        target_object_id=object_id,
        status=status or AccessRequest.Status.PENDING,
    )
    req.add_audit(
        "created", actor=requester, message="Request created.", details=details
    )
    return req


def sync_request_for_target(
    *,
    request_type: str,
    target,
    requester=None,
    title: str = "",
    summary: str = "",
    details: dict | None = None,
    status: str | None = None,
    school=None,
):
    details = details or {}
    content_type = ContentType.objects.get_for_model(target)
    object_id = str(target.pk)
    resolved_school, schema_name = _resolve_scope(school=school, target=target)

    # school belongs in the LOOKUP. object_id is str(target.pk) and content_type is
    # a GLOBAL row, so (request_type, content_type, object_id) is not unique across
    # tenants: two schools whose targets share a pk collide, and get_or_create then
    # hands the caller the OTHER school's AccessRequest -- whose school_id stays
    # wrong because `school` only ever appears in defaults. Every later decision on
    # that request (approve, deny, audit) then acts on the wrong tenant's row.
    req, created = AccessRequest.objects.get_or_create(
        school=resolved_school,
        request_type=request_type,
        target_content_type=content_type,
        target_object_id=object_id,
        defaults={
            "requester": requester,
            "title": title,
            "summary": summary,
            "details": details,
            "schema_name": schema_name,
            "status": status or AccessRequest.Status.PENDING,
        },
    )
    if not created:
        updates = {}
        if requester and req.requester_id is None:
            updates["requester"] = requester
        if title and req.title != title:
            updates["title"] = title
        if summary and req.summary != summary:
            updates["summary"] = summary
        if details and req.details != details:
            updates["details"] = details
        if resolved_school and req.school_id != getattr(resolved_school, "pk", None):
            updates["school"] = resolved_school
            updates["schema_name"] = schema_name
        if status and req.status != status:
            updates["status"] = status
        if updates:
            for key, value in updates.items():
                setattr(req, key, value)
            req.save(update_fields=list(updates.keys()) + ["updated_at"])
    return req


def notify_requester(
    request: AccessRequest,
    title: str,
    message: str,
    created_by=None,
    severity: str = "INFO",
):
    if not request.requester:
        return None
    Notification.objects.notify_unread(
        recipient=request.requester,
        created_by=created_by,
        title=title,
        message=message,
        severity=severity,
        link=f"/requests/{request.id}/",
    )
    from apps.communication.comms_locale import locale_target_for_user

    Message.objects.create(
        sender=created_by,
        recipient=request.requester,
        subject=title,
        body=message,
        locale_target=locale_target_for_user(request.requester),
    )


# --- target resolution ------------------------------------------------------
#
# `target_object_id` is a plain CharField. It is written by `sync_request_for_target`
# from a server-side signal, but it is ALSO caller data: `create_access_request`
# takes `target=` from any app, and `AccessRequestAdmin` leaves the field editable
# on the tenant admin. The `_apply_*` handlers below turn an approval into a WRITE
# on the row that id names, so resolving it without checking the row belongs to the
# request's school lets one tenant's decision land on another tenant's record.
#
# Two of the three target models also use integer pks, so a request whose type says
# REPORT_REQUEST but whose target is a leave request still resolves a row -- the
# content type is the only thing that tells them apart.


def _target_content_type_matches(request: AccessRequest, model) -> bool:
    """Whether the request's stored content type actually names ``model``.

    Rows written before the generic FK was populated carry no content type; those
    keep the historical behaviour rather than becoming silently un-actionable.
    """
    if not request.target_content_type_id:
        return True
    try:
        expected = ContentType.objects.get_for_model(model).pk
    except (DatabaseError, IntegrityError):
        return False
    return request.target_content_type_id == expected


def _resolve_target(request: AccessRequest, model, *, school_lookup: str = ""):
    """Resolve ``request.target_object_id`` to a row of ``model``, school-scoped.

    ``school_lookup`` is the ORM path from ``model`` to the school column (e.g.
    ``"teacher__school_id"``); pass ``""`` for a model with no path to one.
    Returns ``None`` when the id is absent, malformed, unknown, of the wrong type,
    or belongs to a different school.
    """
    if not request.target_object_id:
        return None
    if not _target_content_type_matches(request, model):
        return None
    qs = model.objects.all()
    if school_lookup and request.school_id:
        qs = qs.filter(**{school_lookup: request.school_id})
    try:
        # A pk of the wrong shape (a UUID string against an AutoField, or the
        # reverse) raises before it reaches the database; that is a mismatch, not
        # a crash the approving admin should have to see.
        return qs.filter(pk=request.target_object_id).first()
    except (DatabaseError, IntegrityError, ValidationError, ValueError, TypeError):
        return None


def _apply_finance_access(request: AccessRequest, decision: str, reason: str, actor):
    from apps.people.models import StudentGuardian

    if decision != RequestDecision.Decision.APPROVED:
        return
    requester = request.requester
    if not requester:
        return
    student_ids = request.details.get("student_ids") or []
    links = StudentGuardian.objects.filter(guardian_user=requester)
    # A guardian can be linked to children at more than one school, and
    # `student_ids` is routinely EMPTY -- finance/offline_workflow_handlers.py
    # creates a FINANCE_ACCESS request with `student_ids: []` whenever the offline
    # payload names no student. Unscoped, that turned one school's approval into
    # finance visibility on every link the guardian holds, at every school.
    if request.school_id:
        links = links.filter(student__school_id=request.school_id)
    if student_ids:
        links = links.filter(student_id__in=student_ids)
    links.update(can_view_finance=True)


def _apply_grade_approval(request: AccessRequest, decision: str, reason: str, actor):
    from apps.evals.models import GradeApprovalRequest

    target = _resolve_target(
        request, GradeApprovalRequest, school_lookup="teacher__school_id"
    )
    if not target:
        return
    if decision == RequestDecision.Decision.APPROVED:
        target.status = GradeApprovalRequest.Status.APPROVED
    elif decision == RequestDecision.Decision.DENIED:
        target.status = GradeApprovalRequest.Status.REJECTED
    else:
        target.status = GradeApprovalRequest.Status.REVISION_REQUESTED
    target.reviewed_by = actor
    target.reviewed_at = timezone.now()
    if reason:
        target.reviewer_notes = reason
    target.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "reviewer_notes"]
    )


def _apply_leave_approval(request: AccessRequest, decision: str, reason: str, actor):
    from apps.people.models import TeacherLeaveRequest

    target = _resolve_target(
        request, TeacherLeaveRequest, school_lookup="teacher__school_id"
    )
    if not target:
        return
    if decision == RequestDecision.Decision.APPROVED:
        target.status = TeacherLeaveRequest.Status.APPROVED
    elif decision == RequestDecision.Decision.DENIED:
        target.status = TeacherLeaveRequest.Status.REJECTED
    else:
        target.status = TeacherLeaveRequest.Status.PENDING
    target.approver = actor
    target.decided_at = timezone.now()
    if reason:
        target.decision_notes = reason
    target.save(update_fields=["status", "approver", "decided_at", "decision_notes"])


def _apply_report_request(request: AccessRequest, decision: str, reason: str, actor):
    from apps.finance.models import ReportRequest

    # finance.ReportRequest carries no path to a school (only `requested_by`, and
    # User has no school column), so the content-type match is the only guard
    # available here. It still stops a REPORT_REQUEST pointed at another model's
    # integer pk from moving an unrelated row.
    target = _resolve_target(request, ReportRequest)
    if not target:
        return
    if decision == RequestDecision.Decision.APPROVED:
        target.status = ReportRequest.RequestStatus.IN_PROGRESS
    elif decision == RequestDecision.Decision.DENIED:
        # No rejected state yet; keep pending but log the reason.
        target.status = ReportRequest.RequestStatus.PENDING
    target.save(update_fields=["status"])


# magic-number-allow: mirrors accounts.Permission.code max_length
_PERMISSION_CODE_MAX_LENGTH = 120


def _apply_module_access(request: AccessRequest, decision: str, reason: str, actor):
    if decision != RequestDecision.Decision.APPROVED:
        return
    if not request.requester:
        return
    module = (request.details.get("module") or "").strip().lower()
    action = (request.details.get("action") or "read").strip().lower()
    if not module:
        return
    if action not in {"read", "write"}:
        action = "read"

    from apps.accounts.models import FeaturePermissionScope, Permission

    code = f"module.{module}.{action}"
    if len(code) > _PERMISSION_CODE_MAX_LENGTH:
        # `module` is a free-text POST field (views.request_module_access) and
        # Permission.code is varchar(120) UNIQUE. An over-long code is a DataError
        # raised INSIDE apply_request_decision's atomic block -- a 500 for the
        # approving admin, and from bulk_decide the whole batch rolls back. Refuse
        # the grant and leave a trail instead of poisoning the decision.
        request.add_audit(
            "module_access_rejected",
            actor=actor,
            message="Module name too long for a permission code; no grant issued.",
            details={"module": module[:200], "action": action},
        )
        return
    perm, _ = Permission.objects.get_or_create(
        code=code,
        defaults={"name": f"{module.title()} {action.title()} Access"},
    )
    requester = request.requester
    # `feature_permissions` is a plain M2M with no tenant column, and the ABSENCE
    # of a FeaturePermissionScope row means the historical PLATFORM-WIDE grant
    # (accounts/models.py::_direct_grant_reaches). Approving here without writing
    # one made School A's approval a grant at every school the requester belongs
    # to; every other production writer routes through
    # accounts.feature_permission_scope::set_direct_permissions for exactly this
    # reason. A code the requester ALREADY holds platform-wide is left alone --
    # narrowing it here would revoke access this school never issued.
    already_platform_wide = (
        requester.feature_permissions.filter(pk=perm.pk).exists()
        and not FeaturePermissionScope.objects.filter(
            user=requester, permission=perm
        ).exists()
    )
    requester.feature_permissions.add(perm)
    if request.school_id and not already_platform_wide:
        FeaturePermissionScope.objects.get_or_create(
            user=requester, permission=perm, school_id=request.school_id
        )


@transaction.atomic
def apply_request_decision(
    *,
    request: AccessRequest,
    decision: str,
    reason: str,
    actor,
):
    status_map = {
        RequestDecision.Decision.APPROVED: AccessRequest.Status.APPROVED,
        RequestDecision.Decision.DENIED: AccessRequest.Status.DENIED,
        RequestDecision.Decision.CLARIFY: AccessRequest.Status.CLARIFICATION_REQUESTED,
    }
    new_status = status_map.get(decision, AccessRequest.Status.PENDING)
    request.status = new_status
    request.save(update_fields=["status", "updated_at"])

    RequestDecision.objects.create(
        request=request,
        decision=decision,
        reason=reason or "",
        decided_by=actor,
    )
    request.add_audit(
        "decision",
        actor=actor,
        message=f"{_safe_actor_display(actor)} set status to {new_status}.",
        details={"decision": decision, "reason": reason or ""},
    )

    if request.request_type == AccessRequest.RequestType.FINANCE_ACCESS:
        _apply_finance_access(request, decision, reason, actor)
    elif request.request_type == AccessRequest.RequestType.MODULE_ACCESS:
        _apply_module_access(request, decision, reason, actor)
    elif request.request_type == AccessRequest.RequestType.GRADE_APPROVAL:
        _apply_grade_approval(request, decision, reason, actor)
    elif request.request_type == AccessRequest.RequestType.LEAVE_APPROVAL:
        _apply_leave_approval(request, decision, reason, actor)
    elif request.request_type == AccessRequest.RequestType.REPORT_REQUEST:
        _apply_report_request(request, decision, reason, actor)

    notify_requester(
        request,
        # The reference belongs in the TITLE, not just the body. Notification's
        # `notify_unread` upserts on (recipient, title, is_read=False), so a title
        # that is constant per status collapsed every decision a requester ever
        # received into ONE unread row -- overwriting its message AND its `link`,
        # so the bell pointed at whichever request was decided last. bulk_decide
        # made that the normal case: twenty approvals, one notification.
        title=f"Request {new_status.replace('_', ' ').title()}: {request.reference}",
        message=reason
        or f"Your request {request.reference} is now {new_status.lower().replace('_', ' ')}.",
        created_by=actor,
        severity="INFO" if new_status == AccessRequest.Status.APPROVED else "WARNING",
    )

    return request
