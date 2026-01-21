from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import AccessRole, User

ROLE_TEMPLATES: dict[str, list[str]] = {
    User.Role.ADMIN: ["ADMIN"],
    User.Role.LEADERSHIP: ["LEADERSHIP"],
    User.Role.TEACHER: ["TEACHER"],
    User.Role.PARENT: ["PARENT"],
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
    instance.roles.set(roles)
