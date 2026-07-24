from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import DatabaseError, connection, models, transaction
from django.db.models import Q
from django.db.transaction import TransactionManagementError
from django.utils import timezone

# v3.29 migration-cloud "password preservation moat": Fernet-encrypted
# field descriptors for the three legacy_* User columns. The helper
# selects between the upstream django-cryptography wrapper and an
# internal Fernet shim — both expose the same constructor surface and
# both transparently decrypt at read time. Imported here (not as a
# late lazy import) so makemigrations resolves the deconstructed field
# correctly during schema generation.
from apps.accounts.legacy_hashes.encryption import (
    encrypt_charfield as _legacy_encrypt_charfield,
    encrypt_jsonfield as _legacy_encrypt_jsonfield,
)


# User UI/UX preferences (background logo, opacity, etc.)
# Note: theme preference (light/dark/system) lives on DashboardUserPreference —
# that's the canonical source the context processor reads. Don't add it here.
class UserPreference(models.Model):
    high_contrast_mode = models.BooleanField(
        default=False, help_text="Enable high contrast mode for accessibility."
    )
    reduced_motion = models.BooleanField(
        default=False, help_text="Reduce background/video motion for accessibility."
    )
    user = models.OneToOneField(
        "User", on_delete=models.CASCADE, related_name="preference"
    )
    show_background_logo = models.BooleanField(
        default=True, help_text="Show the background logo image."
    )
    background_logo_opacity = models.FloatField(
        default=0.3,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Custom opacity for background logo (0.0–1.0). Leave blank to use site default.",
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
    """
    RBAC role catalog. ``school=NULL`` rows are platform-wide templates (legacy default).
    ``school`` set scopes the role to one tenant catalog.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="access_roles",
        help_text="Null = global template role; set = school-specific catalog entry.",
    )
    code = models.CharField(max_length=120)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")

    class Meta:
        ordering = ["school_id", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(school__isnull=True),
                name="uniq_accessrole_global_code",
            ),
            models.UniqueConstraint(
                fields=["school", "code"],
                condition=models.Q(school__isnull=False),
                name="uniq_accessrole_school_code",
            ),
        ]

    def __str__(self) -> str:
        if self.school_id:
            return f"{self.code} ({self.school_id})"
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
    role = models.ForeignKey(
        AccessRole, on_delete=models.CASCADE, related_name="temporary_grants"
    )
    valid_from = models.DateTimeField(
        null=True, blank=True, help_text="Optional: grant active from this time."
    )
    expires_at = models.DateTimeField(
        help_text="Grant stops being active after this time."
    )
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


class RoleGroup(models.Model):
    """A named, reusable bundle of access roles an owner can apply to people at once.

    Authoring convenience only: applying a group adds its member roles to each
    selected user's ``roles`` M2M (additive). It never removes roles and never
    changes permission resolution — ``User.has_feature_permission`` still resolves
    through ``user.roles``. School-scoped; a code is unique within a school.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="role_groups",
    )
    code = models.CharField(max_length=120)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    roles = models.ManyToManyField(AccessRole, blank=True, related_name="role_groups")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "code"], name="uniq_role_group_code_per_school"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.school_id})"


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
        DPO = "DPO", "Data Protection Officer"
        BOARDING_MANAGER = "BOARDING_MANAGER", "Boarding Manager"
        ACCOUNTANT = "ACCOUNTANT", "Accountant"
        PROPRIETOR = "PROPRIETOR", "Proprietor"
        DISCIPLINE_MASTER = "DISCIPLINE_MASTER", "Discipline Master"
        PARENT = "PARENT", "Parent"
        STUDENT = "STUDENT", "Student"
        EMPLOYER = "EMPLOYER", "Employer (apprentice portal)"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PARENT)
    roles = models.ManyToManyField(AccessRole, blank=True, related_name="users")
    feature_permissions = models.ManyToManyField(
        Permission, blank=True, related_name="users"
    )
    profile_photo = models.ImageField(upload_to="profiles/", blank=True, null=True)
    # Security Powerhouse: lockdown forces password reset; cooldown uses last_lockdown_at
    requires_password_change = models.BooleanField(
        default=False,
        help_text="Set by Emergency Lockdown; user must set new password on next login.",
    )
    last_lockdown_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time user triggered Emergency Lockdown (for 24h cooldown).",
    )
    password_strength_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="zxcvbn score 0–4 when password was last set.",
    )
    password_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of last successful password change.",
    )
    last_security_posture_review_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last quarterly security posture review completed by the user.",
    )
    preferred_language = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text=(
            "Per-user language preference. When set, overrides Accept-Language "
            "and the tenant default at login. Values mirror settings.LANGUAGES codes "
            "(e.g. 'en', 'es', 'pt-br', 'zh-hans'). Empty string = inherit."
        ),
    )
    # Migration-cloud "password preservation moat": foreign-vendor hash
    # carried over so the user can sign in with their existing password
    # after a migration from PowerSchool / Blackbaud / Veracross / FACTS /
    # Skyward / Alma. Verified lazily on first login by
    # apps.accounts.auth_backends_legacy.LegacyHashUpgradeBackend, which
    # re-hashes to native Argon2 and clears all three fields atomically.
    #
    # v3.29: the three legacy_* columns are now encrypted at rest via
    # apps.accounts.legacy_hashes.encryption. The helper picks between
    # the upstream django-cryptography encrypt() decorator and an
    # internal Fernet shim depending on Django-version compatibility.
    # Reads transparently decrypt; writes transparently encrypt — no
    # caller change required.
    legacy_password_hash = _legacy_encrypt_charfield(
        max_length=512,
        blank=True,
        default="",
        help_text=(
            "Foreign-vendor password hash carried over by the migration "
            "cloud, ENCRYPTED AT REST via Fernet. Verified on first "
            "login, then cleared and re-hashed via PASSWORD_HASHERS. "
            "Never log, display, or expose the decrypted value."
        ),
    )
    legacy_hash_algorithm = _legacy_encrypt_charfield(
        max_length=64,
        blank=True,
        default="",
        help_text=(
            "Slug registered in apps.accounts.legacy_hashes (e.g. "
            "'pbkdf2_sha512', 'bcrypt', 'veracross_bcrypt', 'alma_bcrypt', "
            "'facts_auto', 'skyward_auto'). Encrypted at rest. Empty = "
            "standard Django auth path."
        ),
    )
    legacy_hash_params = _legacy_encrypt_jsonfield(
        default=dict,
        blank=True,
        help_text=(
            "Algorithm-specific parameters (salt, iterations, etc.) "
            "needed to verify legacy_password_hash. Encrypted at rest. "
            "Cleared on first successful login alongside the hash."
        ),
    )
    # v3.29 productionization: anchor + sunset-email timestamp for the
    # 12-month sunset job in apps.accounts.legacy_hashes.sunset_task.
    # Both fields default to NULL; the sunset job falls back to
    # date_joined when legacy_hash_created_at is NULL.
    legacy_hash_created_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Timestamp when the foreign-vendor legacy hash was imported. "
            "Anchor for the 12-month sunset task. NULL = imported before "
            "v3.29; sunset job falls back to User.date_joined."
        ),
    )
    legacy_hash_sunset_email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Set by sunset_stale_legacy_hashes when a one-time setup "
            "link is mailed. Drives the 30-day grace clock before the "
            "legacy fields are nulled and the user is forced through "
            "password reset."
        ),
    )

    def has_feature_permission(self, code: str, *, school=None) -> bool:
        if self.is_superuser:
            return True
        try:
            if connection.needs_rollback:
                try:
                    if connection.in_atomic_block:
                        transaction.set_rollback(False)
                    else:
                        connection.rollback()
                except (DatabaseError, TransactionManagementError):
                    pass
                return False
            if self.feature_permissions.filter(code=code).exists():
                return True
            roles_qs = self.roles.filter(permissions__code=code)
            if school is not None:
                roles_qs = roles_qs.filter(
                    Q(school__isnull=True) | Q(school_id=school.pk)
                )
            if roles_qs.exists():
                return True
            now = timezone.now()
            grant_qs = TemporaryRoleGrant.objects.filter(
                user=self, expires_at__gt=now
            ).filter(Q(valid_from__isnull=True) | Q(valid_from__lte=now))
            if school is not None:
                grant_qs = grant_qs.filter(
                    Q(role__school__isnull=True) | Q(role__school_id=school.pk)
                )
            if grant_qs.filter(role__permissions__code=code).exists():
                return True
            return False
        except (DatabaseError, TransactionManagementError):
            try:
                if connection.in_atomic_block:
                    transaction.set_rollback(False)
                else:
                    connection.rollback()
            except (DatabaseError, TransactionManagementError):
                pass
            return False


class Delegation(models.Model):
    """
    Out of Office / Acting: delegator assigns a delegate to act on their behalf for a date range.
    When end_date (or extended_end_date) is reached, proxy access is revoked (via task or on-request check).
    All behaviour is configurable from effective tenant site settings (max days, auto-revoke, role mapping).
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
    end_date = models.DateTimeField(
        help_text="When the delegation is scheduled to end."
    )
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
    reason = models.CharField(
        max_length=255, blank=True, help_text="Optional: e.g. Annual leave, Training."
    )
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
    action_taken = models.CharField(
        max_length=100, help_text="e.g. syllabus_approved, grade_approved."
    )
    object_repr = models.CharField(
        max_length=255,
        blank=True,
        help_text="Short description of the object (e.g. Physics Form 3).",
    )
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
        LOGOUT = "LOGOUT", "Logout"
        LOGIN_FAILED = "LOGIN_FAILED", "Login failed"
        MFA_CHANGE = "MFA_CHANGE", "MFA changed"
        PWD_RESET = "PWD_RESET", "Password reset"
        DATA_EXPORT = "DATA_EXPORT", "Data export"
        LOCKDOWN_TRIGGERED = "LOCKDOWN_TRIGGERED", "Emergency lockdown"
        SESSION_REVOKED = "SESSION_REVOKED", "Sessions revoked"
        OWNERSHIP_CHANGED = "OWNERSHIP_CHANGED", "School ownership changed"
        IMPOSSIBLE_TRAVEL = (
            "IMPOSSIBLE_TRAVEL",
            "Impossible travel (login from distant location)",
        )

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
    location_data = models.JSONField(
        default=dict, blank=True, help_text="e.g. {city, country, country_code}"
    )
    is_suspicious = models.BooleanField(default=False)
    last_seen = models.DateTimeField(
        auto_now=True, help_text="Updated on dedupe (same IP/device within 1h)."
    )
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


import uuid


class TenantStaffInvite(models.Model):
    """School-scoped staff invite (tenant identity hub lifecycle)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="staff_invites",
    )
    email = models.EmailField()
    role = models.CharField(max_length=32, default="TEACHER")
    is_school_owner = models.BooleanField(
        default=False,
        help_text=(
            "Invite this person as a school-scoped owner (tenant superadmin). "
            "This never grants platform SUPERADMIN/is_superuser authority."
        ),
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenant_staff_invites_sent",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["school", "email"],
                name="accounts_te_school__a1b2c3_idx",
            ),
            models.Index(fields=["token"], name="accounts_te_token_4d5e6f_idx"),
        ]
        verbose_name = "Tenant staff invite"
        verbose_name_plural = "Tenant staff invites"

    @property
    def is_pending(self) -> bool:
        if self.accepted_at:
            return False
        return self.expires_at >= timezone.now()

    def __str__(self) -> str:
        return f"{self.email} @ {self.school_id}"


class FederationSsoHealth(models.Model):
    """
    Per ServiceIntegration (SAML/OIDC IdP): last successful login vs failures.
    Wedge 45 — operator visibility before cert expiry breaks logins.
    """

    service_integration = models.OneToOneField(
        "siteconfig.ServiceIntegration",
        on_delete=models.CASCADE,
        related_name="federation_sso_health",
    )
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_error_summary = models.CharField(max_length=400, blank=True, default="")
    success_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Federation SSO health"
        verbose_name_plural = "Federation SSO health"

    def __str__(self) -> str:
        return f"SSO health #{self.service_integration_id}"


from apps.academics.models import RolloverProposal, RolloverProposalItem  # noqa: E402,F401
from apps.accounts.models_offline_device import (  # noqa: E402,F401
    DeviceRegistration,
    OfflineCapabilityToken,
)
from apps.accounts.models_rebac import (  # noqa: E402,F401
    OfflineAccessIntent,
    RelationshipTuple,
)

# v4.00.50 — SSO-provisioned user → tenant binding.
from apps.accounts.models_sso import UserTenantBinding  # noqa: E402,F401

# Suspicious-login alerting fingerprint (audit residual closeout).
from apps.accounts.models_login_context import KnownLoginContext  # noqa: E402,F401
