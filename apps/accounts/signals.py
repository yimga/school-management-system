import logging

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import AccessRole, User

# Django 4.0 removed LANGUAGE_SESSION_KEY; the session key is now `_language`.
LANGUAGE_SESSION_KEY = "_language"

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def ensure_identity_on_login(sender, user, request, **kwargs):
    """Every login gets portal preferences (and staff TeacherProfile when applicable)."""
    try:
        from apps.siteconfig.user_identity import ensure_user_identity

        ensure_user_identity(user, request=request)
    except Exception:
        logger.exception("ensure_identity_on_login failed for user_id=%s", getattr(user, "pk", None))


@receiver(user_logged_in)
def apply_preferred_language_on_login(sender, user, request, **kwargs):
    """When a user logs in, push their saved language preference into the
    session so LocaleMiddleware picks it up on the next request. Empty string
    or unknown code means "inherit" — we leave the session alone and let
    Accept-Language / tenant default win.
    """
    if request is None or not hasattr(request, "session"):
        return
    code = (getattr(user, "preferred_language", "") or "").strip().lower()
    if not code:
        return
    valid_codes = {c.lower() for c, _name in settings.LANGUAGES}
    if code not in valid_codes:
        return
    request.session[LANGUAGE_SESSION_KEY] = code


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
def _ensure_preferences_on_user_create(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from apps.siteconfig.user_identity import ensure_user_portal_preferences

        ensure_user_portal_preferences(instance)
    except Exception:
        logger.exception(
            "ensure preferences on user create failed for user_id=%s",
            getattr(instance, "pk", None),
        )


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
