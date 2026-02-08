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
        PARENT = "PARENT", "Parent"
        STUDENT = "STUDENT", "Student"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PARENT)
    roles = models.ManyToManyField(AccessRole, blank=True, related_name="users")
    feature_permissions = models.ManyToManyField(Permission, blank=True, related_name="users")
    profile_photo = models.ImageField(upload_to="profiles/", blank=True, null=True)

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
