"""
Policy Registry v2: versioned, auditable policy storage (optional).

Resolver (get_effective_policy) currently reads School.settings and School.features.
When POLICY_USE_BUNDLES is True and a PolicyBundle exists for the school, resolver
can merge from that snapshot instead (future). These models provide the storage.
"""

from django.db import models
from django.conf import settings


class CountryProfile(models.Model):
    """
    Region/country-level defaults (currency, timezone, grading_scale, etc.).
    Optional source for get_effective_policy when school.default_region is not used.
    """
    country_code = models.CharField(max_length=10, db_index=True, unique=True)
    name = models.CharField(max_length=255, blank=True)
    currency_code = models.CharField(max_length=6, blank=True)
    timezone = models.CharField(max_length=63, default="UTC")
    default_language = models.CharField(max_length=10, default="en")
    grading_scale = models.CharField(max_length=64, default="default")
    is_rtl = models.BooleanField(default=False)
    extra = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["country_code"]
        verbose_name = "Country profile (policy defaults)"
        verbose_name_plural = "Country profiles"

    def __str__(self):
        return f"{self.country_code}: {self.name or self.country_code}"


class PolicyBundle(models.Model):
    """
    Snapshot of merged policy (settings + features) for a school at a point in time.
    Used for versioning and audit; resolver can optionally use latest bundle when POLICY_USE_BUNDLES.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="policy_bundles",
        null=True,
        blank=True,
        help_text="Null = platform/country-level bundle.",
    )
    name = models.CharField(max_length=255, blank=True)
    policy_snapshot = models.JSONField(default=dict, help_text="Merged policy dict (terminology, grading, features, etc.).")
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Policy bundle"
        verbose_name_plural = "Policy bundles"
        indexes = [
            models.Index(fields=["school", "is_active", "-created_at"]),
        ]

    def __str__(self):
        return f"PolicyBundle #{self.id} school={self.school_id} v{self.version}"


class TenantBlueprint(models.Model):
    """
    Points a school to the active PolicyBundle (optional v2 path).
    When set, get_effective_policy can merge from active_bundle.policy_snapshot.
    """
    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="tenant_blueprint",
    )
    active_bundle = models.ForeignKey(
        PolicyBundle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="When set and POLICY_USE_BUNDLES=True, resolver uses this bundle.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant blueprint"
        verbose_name_plural = "Tenant blueprints"

    def __str__(self):
        return f"Blueprint for school {self.school_id} bundle={self.active_bundle_id}"
