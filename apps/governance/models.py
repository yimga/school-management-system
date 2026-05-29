"""Organization overlay models (public schema). School remains the tenant boundary."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from apps.governance.org_role_registry import ROLE_GROUP_ADMIN


class Organization(models.Model):
    """Legal owner above optional group membership. Schools may omit this entirely."""

    class LegalOwnerType(models.TextChoices):
        PROPRIETOR = "proprietor", "Proprietor / sole owner"
        CORPORATION = "corporation", "Corporation / company"
        DIOCESE = "diocese", "Diocese / faith network"
        MINISTRY = "ministry", "Ministry / government body"
        NGO = "ngo", "NGO / nonprofit cluster"
        FRANCHISE = "franchise", "Franchise / licensed network"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=120, unique=True)
    legal_owner_type = models.CharField(
        max_length=32,
        choices=LegalOwnerType.choices,
        default=LegalOwnerType.PROPRIETOR,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"

    def __str__(self) -> str:
        return self.name


class GovernanceNode(models.Model):
    """Optional tree node under an Organization (diocese office, LGA, MAT central, etc.)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="governance_nodes",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("organization__name", "name")
        unique_together = [("organization", "slug")]
        verbose_name = "Governance node"
        verbose_name_plural = "Governance nodes"

    def __str__(self) -> str:
        return f"{self.organization.name} / {self.name}"


class OrgMembership(models.Model):
    """User membership at organization scope (distinct from SchoolMembership)."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        GROUP_ADMIN = "group_admin", "Group administrator"
        INSPECTOR = "inspector", "Inspector / auditor"
        SUPERINTENDENT = "superintendent", "Superintendent"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="org_memberships",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=ROLE_GROUP_ADMIN,  # role-string-allow: model default via OrgMembership.Role registry
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Preferred org context when the user belongs to multiple organizations.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "organization")]
        ordering = ("-is_primary", "organization__name")
        verbose_name = "Organization membership"
        verbose_name_plural = "Organization memberships"

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.organization.name} ({self.role})"


def _get_school_membership_role_choices():
    from apps.accounts.models import User

    return User.Role.choices


class SchoolContextProfile(models.Model):
    """
    Multi-role context for one user at one school (Phase 3C).

    Lets the same login switch between teacher / student / parent personas
    without separate accounts. Distinct from ``SchoolMembership`` (one row per
    user+school); profiles add ``context_key`` granularity.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="school_context_profiles",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="context_profiles",
    )
    role = models.CharField(
        max_length=20,
        choices=_get_school_membership_role_choices,
        default="ADMIN",  # role-string-allow: model default via User.Role registry
    )
    context_key = models.SlugField(
        max_length=64,
        help_text="Stable slug for this persona (e.g. teacher, student, parent).",
    )
    label = models.CharField(
        max_length=120,
        help_text="Human label shown in the context switcher.",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Preferred profile when the user lands on this school.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "school", "context_key")]
        ordering = ("-is_default", "school__name", "label")
        verbose_name = "School context profile"
        verbose_name_plural = "School context profiles"

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.school_id} [{self.context_key}] ({self.role})"


class Employment(models.Model):
    """Org-level employer record (Phase 4B — teacher transfer foundation)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="employments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="org_employments",
    )
    title = models.CharField(max_length=120, blank=True)
    started_on = models.DateField()
    ended_on = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-started_on", "organization__name")
        verbose_name = "Employment"
        verbose_name_plural = "Employments"

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.organization.name}"


class SchoolAssignment(models.Model):
    """Deploy an ``Employment`` to a member school (fractional allocation supported)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employment = models.ForeignKey(
        Employment,
        on_delete=models.CASCADE,
        related_name="school_assignments",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="org_school_assignments",
    )
    role = models.CharField(
        max_length=32,
        choices=_get_school_membership_role_choices,
        default="TEACHER",  # role-string-allow: model default via User.Role registry
    )
    allocation_fraction = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1,
        help_text="1.00 = full-time at this school; 0.50 = half-day cross-campus.",
    )
    started_on = models.DateField()
    ended_on = models.DateField(null=True, blank=True)
    is_primary = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-started_on", "school__name")
        verbose_name = "School assignment"
        verbose_name_plural = "School assignments"

    def __str__(self) -> str:
        return f"{self.employment_id} → {self.school_id} ({self.allocation_fraction})"
