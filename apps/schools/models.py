"""
Multi-tenant School and SchoolMembership models (Option B+C).
School is the tenant; SchoolMembership links users to schools with a role.
"""
import uuid
from django.conf import settings
from django.db import models


def _get_role_choices():
    from apps.accounts.models import User
    return User.Role.choices


class School(models.Model):
    """Tenant: one row per school. Subdomain/slug identifies the school in the URL."""

    class SubSystem(models.TextChoices):
        FR = "FR", "French sub-system"
        EN = "EN", "English sub-system"
        INT = "INT", "International"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=120, unique=True, help_text="URL slug e.g. ghs-limbe")
    name = models.CharField(max_length=255)
    subdomain = models.CharField(
        max_length=120,
        unique=True,
        blank=True,
        help_text="Subdomain for this school (e.g. ghs-limbe for ghs-limbe.yoursystem.com)",
    )
    sub_system = models.CharField(
        max_length=10,
        choices=SubSystem.choices,
        default=SubSystem.EN,
        help_text="Cameroon FR/EN or International",
    )
    default_region = models.ForeignKey(
        "siteconfig.RegionConfig",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="schools",
        help_text="Region for currency, grading, timezone",
    )
    timezone = models.CharField(max_length=50, default="Africa/Douala")
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="School-level overrides: grading_logic, term_count, custom fields config, etc.",
    )
    features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Enabled modules: {\"library\": true, \"transport\": false}",
    )
    logo_url = models.URLField(blank=True, help_text="URL to school logo (e.g. from tenants/{id}/logo.png)")
    primary_color = models.CharField(max_length=20, default="#0d6efd")
    accent_color = models.CharField(max_length=20, default="#198754")
    is_active = models.BooleanField(default=True)
    # Phase 4: super-tenant (parent school for consolidated dashboard)
    parent_school = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_schools",
        help_text="Parent tenant e.g. Catholic Education Secretariat",
    )
    # Phase 4: whitelabel custom domain
    custom_domain = models.CharField(
        max_length=255,
        blank=True,
        help_text="Custom domain e.g. portal.school.edu",
    )
    custom_domain_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "School"
        verbose_name_plural = "Schools"

    def __str__(self):
        return self.name

    def has_feature(self, code: str) -> bool:
        """Return True if the school has the given feature/module enabled."""
        normalized = (code or "").strip().lower()
        if not normalized:
            return False
        fallback = bool(self.features.get(normalized)) if isinstance(self.features, dict) else False
        try:
            from apps.siteconfig.feature_toggles import resolve_module_enabled

            return resolve_module_enabled(normalized, school=self, fallback=fallback)
        except Exception:
            return fallback

    def get_cname_target(self) -> str:
        """Return the hostname schools should CNAME their custom_domain to (whitelabel Phase 4)."""
        import os
        base = os.getenv("MULTI_TENANT_BASE_DOMAIN", "").strip()
        return base or "your-platform.com"


class SchoolMembership(models.Model):
    """Links a user to a school with a role. User can belong to multiple schools."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="school_memberships",
    )
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=_get_role_choices,
        default="ADMIN",
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="When user has multiple schools, which one is primary",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "school")]
        ordering = ["-is_primary", "school__name"]
        verbose_name = "School membership"
        verbose_name_plural = "School memberships"

    def __str__(self):
        return f"{self.user.username} @ {self.school.name} ({self.role})"
