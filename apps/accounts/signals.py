import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import AccessRole, User

logger = logging.getLogger(__name__)

ROLE_TEMPLATES: dict[str, list[str]] = {
    User.Role.SUPERADMIN: ["ADMIN"],
    User.Role.ADMIN: ["ADMIN"],
    User.Role.LEADERSHIP: ["LEADERSHIP"],
    User.Role.PRINCIPAL: ["PRINCIPAL"],
    User.Role.VICE_PRINCIPAL: ["VICE_PRINCIPAL"],
    User.Role.DEAN: ["DEAN"],
    User.Role.CENSOR: ["CENSOR"],
    User.Role.BURSAR: ["BURSAR"],
    User.Role.HOD: ["HOD"],
    User.Role.DEPT_LEAD: ["HOD"],
    User.Role.FINANCE_STAFF: ["BURSAR"],
    User.Role.ACADEMICS_STAFF: ["DEAN"],
    User.Role.COMMS_STAFF: ["BOARDING_MANAGER"],
    User.Role.TEACHER: ["TEACHER"],
    User.Role.IT_ADMIN: ["IT_ADMIN"],
    User.Role.BOARDING_MANAGER: ["BOARDING_MANAGER"],
    User.Role.ACCOUNTANT: ["ACCOUNTANT"],
    User.Role.PROPRIETOR: ["PROPRIETOR"],
    User.Role.DISCIPLINE_MASTER: ["DISCIPLINE_MASTER"],
    User.Role.SECRETARY: ["SECRETARY"],
    User.Role.EXECUTIVE_ASSISTANT: ["EXECUTIVE_ASSISTANT"],
    User.Role.VIRTUAL_ASSISTANT: ["VIRTUAL_ASSISTANT"],
    User.Role.PARENT: ["PARENT"],
    User.Role.STUDENT: ["STUDENT"],
}


@receiver(pre_save, sender=User)
def _cache_previous_role(sender, instance, **kwargs):
    if instance.pk:
        try:
            previous = sender.objects.get(pk=instance.pk).role
        except sender.DoesNotExist:
            previous = None
    else:
        previous = None
    instance._previous_role = previous


@receiver(post_save, sender=User)
def _apply_role_template(sender, instance, created, **kwargs):
    previous = getattr(instance, "_previous_role", None)
    if not created and previous == instance.role:
        return
    codes = ROLE_TEMPLATES.get(instance.role)
    if not codes:
        return
    roles = AccessRole.objects.filter(code__in=codes)
    if not roles.exists():
        # Role templates may be evaluated before access roles are seeded in isolated setup flows.
        return
    instance.roles.set(roles)
