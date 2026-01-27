from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import DatabaseError, connection, models

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
        if connection.in_atomic_block and connection.needs_rollback:
            return False
        try:
            if self.feature_permissions.filter(code=code).exists():
                return True
            return self.roles.filter(permissions__code=code).exists()
        except DatabaseError:
            return False
