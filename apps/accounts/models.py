from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import DatabaseError, connection, models, transaction
from django.db.models import Q
from django.db.transaction import TransactionManagementError
from django.utils import timezone

# User UI/UX preferences (background logo, opacity, etc.)
class UserPreference(models.Model):
    high_contrast_mode = models.BooleanField(default=False, help_text="Enable high contrast mode for accessibility.")
    reduced_motion = models.BooleanField(default=False, help_text="Reduce background/video motion for accessibility.")
    user = models.OneToOneField('User', on_delete=models.CASCADE, related_name='preference')
    show_background_logo = models.BooleanField(default=True, help_text="Show the background logo image.")
    background_logo_opacity = models.FloatField(
        default=0.3,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Custom opacity for background logo (0.0–1.0). Leave blank to use site default."
    )
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return f"Preferences for {self.user.username}"

from django.contrib.auth.models import AbstractUser


class Permission(models.Model):
    code = models.CharField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class AccessRole(models.Model):
    code = models.CharField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class TemporaryRoleGrant(models.Model):
    """
    Time-limited role grant (e.g. auditor for one month). Permissions from this
    role are effective only while expires_at > now (and valid_from <= now if set).
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="temporary_role_grants",
    )
    role = models.ForeignKey(AccessRole, on_delete=models.CASCADE, related_name="temporary_grants")
    valid_from = models.DateTimeField(null=True, blank=True, help_text="Optional: grant active from this time.")
    expires_at = models.DateTimeField(help_text="Grant stops being active after this time.")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_temporary_grants",
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-expires_at"]

    def __str__(self):
        return f"{self.user.username} <- {self.role.code} until {self.expires_at}"

    @property
    def is_active(self):
        now = timezone.now()
        if self.expires_at <= now:
            return False
        if self.valid_from is not None and self.valid_from > now:
            return False
        return True


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPERADMIN = "SUPERADMIN", "Super Administrator"
        ADMIN = "ADMIN", "Administrator"
        LEADERSHIP = "LEADERSHIP", "Leadership"
        PRINCIPAL = "PRINCIPAL", "Principal"
        VICE_PRINCIPAL = "VICE_PRINCIPAL", "Vice Principal"
        DEAN = "DEAN", "Dean"
        CENSOR = "CENSOR", "Censor"
        BURSAR = "BURSAR", "Bursar"
        HOD = "HOD", "Head of Department"
        DEPT_LEAD = "DEPT_LEAD", "Department Lead"
        FINANCE_STAFF = "FINANCE_STAFF", "Finance Staff"
        ACADEMICS_STAFF = "ACADEMICS_STAFF", "Academics Staff"
        COMMS_STAFF = "COMMS_STAFF", "Communications Staff"
        SECRETARY = "SECRETARY", "Secretary"
        EXECUTIVE_ASSISTANT = "EXECUTIVE_ASSISTANT", "Executive Assistant"
        VIRTUAL_ASSISTANT = "VIRTUAL_ASSISTANT", "Virtual Assistant"
        TEACHER = "TEACHER", "Teacher"
        IT_ADMIN = "IT_ADMIN", "IT Administrator"
        BOARDING_MANAGER = "BOARDING_MANAGER", "Boarding Manager"
        ACCOUNTANT = "ACCOUNTANT", "Accountant"
        PROPRIETOR = "PROPRIETOR", "Proprietor"
        DISCIPLINE_MASTER = "DISCIPLINE_MASTER", "Discipline Master"
        PARENT = "PARENT", "Parent"
        STUDENT = "STUDENT", "Student"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PARENT)
    roles = models.ManyToManyField(AccessRole, blank=True, related_name="users")
    feature_permissions = models.ManyToManyField(Permission, blank=True, related_name="users")
    profile_photo = models.ImageField(upload_to="profiles/", blank=True, null=True)
    # Security Powerhouse: lockdown forces password reset; cooldown uses last_lockdown_at
    requires_password_change = models.BooleanField(default=False, help_text="Set by Emergency Lockdown; user must set new password on next login.")
    last_lockdown_at = models.DateTimeField(null=True, blank=True, help_text="Last time user triggered Emergency Lockdown (for 24h cooldown).")

    def has_feature_permission(self, code: str) -> bool:
        if self.is_superuser:
            return True
        try:
            if connection.needs_rollback:
                try:
                    if connection.in_atomic_block:
                        transaction.set_rollback(False)
                    else:
                        connection.rollback()
                except Exception:
                    pass
                return False
            if self.feature_permissions.filter(code=code).exists():
                return True
            if self.roles.filter(permissions__code=code).exists():
                return True
            now = timezone.now()
            if TemporaryRoleGrant.objects.filter(
                user=self, expires_at__gt=now
            ).filter(
                Q(valid_from__isnull=True) | Q(valid_from__lte=now)
            ).filter(role__permissions__code=code).exists():
                return True
            return False
        except (DatabaseError, TransactionManagementError):
            try:
                if connection.in_atomic_block:
                    transaction.set_rollback(False)
                else:
                    connection.rollback()
            except Exception:
                pass
            return False


class Delegation(models.Model):
    """
    Out of Office / Acting: delegator assigns a delegate to act on their behalf for a date range.
    When end_date (or extended_end_date) is reached, proxy access is revoked (via task or on-request check).
    All behaviour is configurable from SiteSettings (max days, auto-revoke, role mapping).
    """
    delegator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="delegations_made",
        help_text="User who is away (Principal, Dean, Teacher, etc.).",
    )
    delegate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="delegations_received",
        help_text="User who will act on their behalf (e.g. Vice-Principal).",
    )
    start_date = models.DateTimeField(help_text="When the delegation becomes active.")
    end_date = models.DateTimeField(help_text="When the delegation is scheduled to end.")
    extended_end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="If set, effective end is this date instead of end_date.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="When False, delegation is no longer in effect (e.g. revoked or returned early).",
    )
    scope = models.JSONField(
        default=dict,
        blank=True,
        help_text='Which workflows this applies to: list of keys e.g. ["syllabus_approval", "grade_approval"] or empty for "all".',
    )
    reason = models.CharField(max_length=255, blank=True, help_text="Optional: e.g. Annual leave, Training.")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_delegations",
        help_text="User who created this (delegator or admin for emergency override).",
    )

    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["delegator", "is_active"]),
            models.Index(fields=["delegate", "is_active"]),
            models.Index(fields=["end_date", "extended_end_date"]),
        ]

    def __str__(self):
        return f"{self.delegator.username} → {self.delegate.username} until {self.effective_end_date}"

    @property
    def effective_end_date(self):
        if self.extended_end_date:
            return self.extended_end_date
        return self.end_date

    @property
    def is_current(self):
        """True if delegation is active and today is within [start_date, effective_end_date]."""
        if not self.is_active:
            return False
        now = timezone.now()
        if now < self.start_date:
            return False
        if now > self.effective_end_date:
            return False
        return True


class DelegationActionLog(models.Model):
    """
    Log of an action performed by a delegate (proxy) on behalf of the delegator.
    Used for "While You Were Away" catch-up and audit.
    """
    delegation = models.ForeignKey(
        Delegation,
        on_delete=models.CASCADE,
        related_name="action_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="delegation_actions_performed",
        help_text="The delegate who performed the action.",
    )
    acting_for = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="delegation_actions_received",
        help_text="The delegator on whose behalf the action was taken.",
    )
    action_taken = models.CharField(max_length=100, help_text="e.g. syllabus_approved, grade_approved.")
    object_repr = models.CharField(max_length=255, blank=True, help_text="Short description of the object (e.g. Physics Form 3).")
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_type = models.ForeignKey(
        "contenttypes.ContentType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Optional: link to the affected object.",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["acting_for", "created_at"]),
            models.Index(fields=["delegation", "created_at"]),
        ]

    def __str__(self):
        return f"{self.actor.username} (for {self.acting_for.username}): {self.action_taken} @ {self.created_at}"


# =============================================================================
# Security & Identity Powerhouse (plan 3.13–3.23): Audit log, passkeys
# =============================================================================

class SecurityAuditLog(models.Model):
    """
    Tenant-scoped security event log: LOGIN, MFA_CHANGE, PWD_RESET, DATA_EXPORT, LOCKDOWN_TRIGGERED.
    django-ipware for IP; GeoIP for city/country; is_suspicious when country != school.
    Dedupe: same device/IP within 1h → update last_seen (handled in service layer).
    """
    class EventType(models.TextChoices):
        LOGIN = "LOGIN", "Login"
        LOGIN_FAILED = "LOGIN_FAILED", "Login failed"
        MFA_CHANGE = "MFA_CHANGE", "MFA changed"
        PWD_RESET = "PWD_RESET", "Password reset"
        DATA_EXPORT = "DATA_EXPORT", "Data export"
        LOCKDOWN_TRIGGERED = "LOCKDOWN_TRIGGERED", "Emergency lockdown"
        SESSION_REVOKED = "SESSION_REVOKED", "Sessions revoked"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="security_audit_logs",
        help_text="Tenant (school); null for platform-level events.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="security_audit_logs",
    )
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    location_data = models.JSONField(default=dict, blank=True, help_text="e.g. {city, country, country_code}")
    is_suspicious = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True, help_text="Updated on dedupe (same IP/device within 1h).")
    created_at = models.DateTimeField(auto_now_add=True)
    initiator = models.CharField(
        max_length=20,
        blank=True,
        help_text="self = user triggered; admin = admin triggered lockdown.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["school", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]
        verbose_name = "Security audit log"
        verbose_name_plural = "Security audit logs"

    def __str__(self):
        return f"{self.user_id} {self.event_type} @ {self.created_at}"


class UserPasskey(models.Model):
    """
    WebAuthn/Passkeys: store public key for biometric login (SimpleWebAuthn registration).
    Tenant-scoped via user → school membership.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="passkeys",
    )
    name = models.CharField(max_length=120, blank=True, help_text="e.g. iPhone Face ID")
    credential_id = models.CharField(max_length=255, unique=True)
    public_key = models.TextField()
    sign_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "User passkey"
        verbose_name_plural = "User passkeys"

    def __str__(self):
        return f"{self.user_id} {self.name or self.credential_id[:16]}"
