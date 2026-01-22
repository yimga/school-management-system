"""
Signal handlers for compliance audit logging.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import (
    ComplianceCheck, LegalDocument, RegionalComplianceRequirement,
    ComplianceAuditLog, ComplianceRule
)


@receiver(post_save, sender=ComplianceCheck)
def log_compliance_check(sender, instance, created, **kwargs):
    """Log when a compliance check is performed."""
    if created:
        ComplianceAuditLog.objects.create(
            region=instance.region,
            action_type='check_performed',
            requirement=instance.requirement,
            description=f"Compliance check performed: {instance.get_check_type_display()}",
            user=instance.checked_by,
            severity='medium' if instance.status == 'fail' else 'low'
        )


@receiver(post_save, sender=LegalDocument)
def log_document_action(sender, instance, created, **kwargs):
    """Log when legal documents are created or updated."""
    action_type = 'document_created' if created else 'document_updated'
    ComplianceAuditLog.objects.create(
        region=instance.region,
        action_type=action_type,
        document=instance,
        description=f"{action_type}: {instance.get_document_type_display()}",
        user=instance.created_by,
        severity='high'
    )


@receiver(post_save, sender=RegionalComplianceRequirement)
def log_requirement_action(sender, instance, created, **kwargs):
    """Log when compliance requirements are created or updated."""
    action_type = 'requirement_created' if created else 'requirement_updated'
    ComplianceAuditLog.objects.create(
        region=instance.region,
        action_type=action_type,
        requirement=instance,
        description=f"{action_type}: {instance.rule.name}",
        user=instance.created_by,
        severity='medium'
    )
