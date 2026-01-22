"""Signal handlers for compliance audit logging."""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ComplianceCheck, LegalDocument, RegionalComplianceRequirement, ComplianceAuditLog

@receiver(post_save, sender=ComplianceCheck)
def log_compliance_check(sender, instance, created, **kwargs):
    if created:
        ComplianceAuditLog.objects.create(region=instance.region, action_type='check_performed', description=f"Check: {instance.get_status_display()}", user=instance.checked_by, severity='medium' if instance.status == 'fail' else 'low')

@receiver(post_save, sender=LegalDocument)
def log_document_action(sender, instance, created, **kwargs):
    if created:
        ComplianceAuditLog.objects.create(region=instance.region, action_type='document_created', document=instance, description=f"Document: {instance.get_document_type_display()}", user=instance.created_by, severity='high')
