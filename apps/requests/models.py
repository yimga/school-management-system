import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


def _generate_request_reference() -> str:
    return f"REQ-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"


class AccessRequest(models.Model):
    class RequestType(models.TextChoices):
        FINANCE_ACCESS = "FINANCE_ACCESS", "Finance access"
        PORTAL_FEATURE_ACCESS = "PORTAL_FEATURE_ACCESS", "Portal feature access"
        MODULE_ACCESS = "MODULE_ACCESS", "Module access"
        GRADE_APPROVAL = "GRADE_APPROVAL", "Grade approval"
        LEAVE_APPROVAL = "LEAVE_APPROVAL", "Leave approval"
        DOCUMENT_REQUEST = "DOCUMENT_REQUEST", "Document request"
        REPORT_REQUEST = "REPORT_REQUEST", "Report request"
        REFUND_REQUEST = "REFUND_REQUEST", "Refund request"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        DENIED = "DENIED", "Denied"
        CLARIFICATION_REQUESTED = "CLARIFICATION_REQUESTED", "Clarification requested"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(
        max_length=32, unique=True, default=_generate_request_reference, editable=False
    )
    request_type = models.CharField(max_length=40, choices=RequestType.choices)
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.PENDING
    )
    title = models.CharField(max_length=200, blank=True)
    summary = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="access_requests",
    )
    schema_name = models.CharField(max_length=63, blank=True, db_index=True)

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_requests",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_requests_assigned",
    )

    target_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    target_object_id = models.CharField(max_length=64, blank=True, null=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    requested_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self) -> str:
        return f"{self.reference} ({self.get_request_type_display()})"

    def add_audit(self, action: str, actor=None, message: str = "", details=None):
        return RequestAudit.objects.create(
            request=self,
            actor=actor,
            action=action,
            message=message or "",
            details=details or {},
        )


class RequestDecision(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "APPROVED", "Approved"
        DENIED = "DENIED", "Denied"
        CLARIFY = "CLARIFY", "Clarification requested"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        AccessRequest, on_delete=models.CASCADE, related_name="decisions"
    )
    decision = models.CharField(max_length=20, choices=Decision.choices)
    reason = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_request_decisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.request.reference} -> {self.get_decision_display()}"


class RequestAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        AccessRequest, on_delete=models.CASCADE, related_name="audits"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_request_audits",
    )
    action = models.CharField(max_length=64)
    message = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.request.reference} - {self.action}"
