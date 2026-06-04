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


def _client_ip(request) -> str:
    """Best-effort client IP from X-Forwarded-For (first hop) or REMOTE_ADDR."""
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return xff or (request.META.get("REMOTE_ADDR") or "").strip()


@receiver(user_logged_in)
def alert_on_suspicious_login(sender, user, request, **kwargs):
    """Email the account owner the first time we see a login from a NEW
    device/network fingerprint (after their first-ever login).

    Privacy: we store only hashes of the IP + User-Agent (never the raw
    values). The alert email — sent to the owner about their own account —
    does surface the IP for recognisability, but nothing is logged. Best-
    effort: any failure is swallowed so it never blocks a login.
    """
    import hashlib

    if not getattr(settings, "RMC_SUSPICIOUS_LOGIN_ALERTS_ENABLED", True):
        return
    if request is None:
        return
    email = (getattr(user, "email", "") or "").strip()
    if not email:
        return
    try:
        ip = _client_ip(request)
        ua = (request.META.get("HTTP_USER_AGENT") or "").strip()
        ip_hash = hashlib.sha256((ip or "").encode("utf-8")).hexdigest()[:12] if ip else ""
        ua_hash = hashlib.sha256((ua or "").encode("utf-8")).hexdigest()[:12] if ua else ""
        context_hash = hashlib.sha256(
            f"{ip}|{ua}".encode("utf-8")
        ).hexdigest()[:16]

        from apps.accounts.models_login_context import KnownLoginContext

        _row, created = KnownLoginContext.objects.get_or_create(
            user=user,
            context_hash=context_hash,
            defaults={"ip_hash": ip_hash, "ua_hash": ua_hash},
        )
        if not created:
            return
        # First-ever login (only this one context exists) → record silently.
        known_count = KnownLoginContext.objects.filter(user=user).count()
        if known_count <= 1:
            return
        from apps.schoolops.email_delivery import send_transactional

        site_url = getattr(settings, "RMC_PUBLIC_SITE_URL", "") or "the platform"
        body = (
            "We noticed a new sign-in to your account.\n\n"
            f"Approximate IP: {ip or 'unknown'}\n"
            f"Device: {(ua or 'unknown')[:160]}\n\n"  # magic-number-allow: ua-display-truncation
            "If this was you, no action is needed. If you don't recognise this "
            "sign-in, change your password immediately and contact your "
            f"administrator. ({site_url})"
        )
        send_transactional(
            subject="New sign-in to your account",
            body=body,
            to=[email],
            priority="transactional",
            allow_suppressed=True,
            idempotency_key=f"login_alert:{getattr(user, 'pk', '')}:{context_hash}",
        )
    except Exception:  # noqa: BLE001 — alerting never blocks login
        logger.warning(
            "alert_on_suspicious_login failed for user_id=%s",
            getattr(user, "pk", None),
        )


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
    # tenant-isolation-allow: seed-lookup-of-platform-wide-template-roles-by-code-school-is-null
    roles = AccessRole.objects.filter(code__in=codes)
    if not roles.exists():
        # Role templates may be evaluated before access roles are seeded in isolated setup flows.
        return
    instance.roles.set(roles)
