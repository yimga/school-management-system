from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.evals.models import GradeApprovalRequest
from apps.finance.models import ReportRequest
from apps.people.models import TeacherLeaveRequest

from .models import AccessRequest
from .services import sync_request_for_target


@receiver(post_save, sender=GradeApprovalRequest)
def sync_grade_approval_request(sender, instance: GradeApprovalRequest, created, **kwargs):
    status_map = {
        GradeApprovalRequest.Status.APPROVED: AccessRequest.Status.APPROVED,
        GradeApprovalRequest.Status.REJECTED: AccessRequest.Status.DENIED,
        GradeApprovalRequest.Status.REVISION_REQUESTED: AccessRequest.Status.CLARIFICATION_REQUESTED,
        GradeApprovalRequest.Status.UNDER_REVIEW: AccessRequest.Status.PENDING,
        GradeApprovalRequest.Status.PENDING: AccessRequest.Status.PENDING,
    }
    status = status_map.get(instance.status, AccessRequest.Status.PENDING)
    requester = instance.requested_by or getattr(instance.teacher, "user", None)
    title = f"Grade approval: {instance.teacher}"
    summary = f"{instance.subject_assignment} ({instance.academic_year} - {instance.term})"
    details = {
        "teacher": str(instance.teacher),
        "subject_assignment": str(instance.subject_assignment),
        "academic_year": str(instance.academic_year),
        "term": str(instance.term),
        "status": instance.status,
    }
    sync_request_for_target(
        request_type=AccessRequest.RequestType.GRADE_APPROVAL,
        target=instance,
        requester=requester,
        title=title,
        summary=summary,
        details=details,
        status=status,
    )


@receiver(post_save, sender=TeacherLeaveRequest)
def sync_leave_request(sender, instance: TeacherLeaveRequest, created, **kwargs):
    status_map = {
        TeacherLeaveRequest.Status.APPROVED: AccessRequest.Status.APPROVED,
        TeacherLeaveRequest.Status.REJECTED: AccessRequest.Status.DENIED,
        TeacherLeaveRequest.Status.PENDING: AccessRequest.Status.PENDING,
    }
    status = status_map.get(instance.status, AccessRequest.Status.PENDING)
    requester = getattr(instance.teacher, "user", None)
    title = f"Leave request: {instance.teacher}"
    summary = f"{instance.start_date} to {instance.end_date}"
    details = {
        "teacher": str(instance.teacher),
        "start_date": str(instance.start_date),
        "end_date": str(instance.end_date),
        "status": instance.status,
    }
    sync_request_for_target(
        request_type=AccessRequest.RequestType.LEAVE_APPROVAL,
        target=instance,
        requester=requester,
        title=title,
        summary=summary,
        details=details,
        status=status,
    )


@receiver(post_save, sender=ReportRequest)
def sync_report_request(sender, instance: ReportRequest, created, **kwargs):
    status_map = {
        ReportRequest.RequestStatus.COMPLETED: AccessRequest.Status.APPROVED,
        ReportRequest.RequestStatus.IN_PROGRESS: AccessRequest.Status.PENDING,
        ReportRequest.RequestStatus.PENDING: AccessRequest.Status.PENDING,
    }
    status = status_map.get(instance.status, AccessRequest.Status.PENDING)
    requester = instance.requested_by
    title = f"Report request: {instance.report_type}"
    summary = instance.description or "Report request submitted."
    details = {
        "report_type": instance.report_type,
        "status": instance.status,
    }
    sync_request_for_target(
        request_type=AccessRequest.RequestType.REPORT_REQUEST,
        target=instance,
        requester=requester,
        title=title,
        summary=summary,
        details=details,
        status=status,
    )
