"""
Audit trail for tenant membership / role changes (compliance ``AuditLog``).
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.schools.models import SchoolMembership


@receiver(pre_save, sender=SchoolMembership)
def _membership_capture_old_role(sender, instance, **kwargs):
    if not instance.pk:
        setattr(instance, "_audit_prev_role", None)
        return
    try:
        prev = SchoolMembership.objects.filter(pk=instance.pk).values_list(
            "role", flat=True
        ).first()
        setattr(instance, "_audit_prev_role", prev)
    except Exception:
        setattr(instance, "_audit_prev_role", None)


@receiver(post_save, sender=SchoolMembership)
def _membership_post_save_audit(sender, instance, created, **kwargs):
    from apps.compliance.enterprise_audit import log_school_membership_event

    old_role = getattr(instance, "_audit_prev_role", None)
    log_school_membership_event(
        instance=instance,
        created=created,
        old_role=old_role,
        deleted=False,
    )


@receiver(post_delete, sender=SchoolMembership)
def _membership_post_delete_audit(sender, instance, **kwargs):
    from apps.compliance.enterprise_audit import log_school_membership_event

    log_school_membership_event(
        instance=instance,
        created=False,
        old_role=getattr(instance, "role", None),
        deleted=True,
    )
