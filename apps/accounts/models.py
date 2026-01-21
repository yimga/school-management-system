from django.contrib.auth.models import AbstractUser
from django.db import models


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
        ADMIN = "ADMIN", "Administrator"
        LEADERSHIP = "LEADERSHIP", "Leadership"
        PRINCIPAL = "PRINCIPAL", "Principal"
        VICE_PRINCIPAL = "VICE_PRINCIPAL", "Vice Principal"
        DEAN = "DEAN", "Dean"
        CENSOR = "CENSOR", "Censor"
        BURSAR = "BURSAR", "Bursar"
        HOD = "HOD", "Head of Department"
        TEACHER = "TEACHER", "Teacher"
        IT_ADMIN = "IT_ADMIN", "IT Administrator"
        BOARDING_MANAGER = "BOARDING_MANAGER", "Boarding Manager"
        PARENT = "PARENT", "Parent"
        STUDENT = "STUDENT", "Student"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ADMIN)
    roles = models.ManyToManyField(AccessRole, blank=True, related_name="users")
    feature_permissions = models.ManyToManyField(Permission, blank=True, related_name="users")
    profile_photo = models.ImageField(upload_to="profiles/", blank=True, null=True)

    def has_feature_permission(self, code: str) -> bool:
        if self.is_superuser:
            return True
        if self.feature_permissions.filter(code=code).exists():
            return True
        return self.roles.filter(permissions__code=code).exists()
