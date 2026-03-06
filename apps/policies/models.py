"""
Policy Registry v2: versioned, auditable policy storage (optional).

Resolver (get_effective_policy) currently reads School.settings and School.features.
When POLICY_USE_BUNDLES is True and a PolicyBundle exists for the school, resolver
can merge from that snapshot instead (future). These models provide the storage.

Phase 6: BlueprintPack = catalog of installable policy packs (e.g. Cameroon Francophone,
UAE MoE+IB, UK GCSE/A-Level). Applying a pack creates a PolicyBundle for the school
and sets TenantBlueprint.active_bundle.
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
    applied_pack_version = models.CharField(
        max_length=32,
        blank=True,
        help_text="When created from a BlueprintPack, store pack.version for update detection.",
    )
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
    applied_pack tracks which BlueprintPack was last applied for "Update bundle" when pack version increases.
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
    applied_pack = models.ForeignKey(
        "BlueprintPack",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenant_blueprints",
        help_text="Blueprint pack last applied; used to offer update when pack version increases.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant blueprint"
        verbose_name_plural = "Tenant blueprints"

    def __str__(self):
        return f"Blueprint for school {self.school_id} bundle={self.active_bundle_id}"


class BlueprintPack(models.Model):
    """
    Catalog entry for a blueprint pack (Phase 6 marketplace).
    Packs define policy_snapshot templates (terminology, grading, admissions, etc.)
    that can be applied to a school; applying creates a PolicyBundle and sets
    TenantBlueprint.active_bundle.
    """
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="e.g. Cameroon Francophone, UAE MoE+IB, UK GCSE/A-Level, US charter",
    )
    policy_snapshot = models.JSONField(
        default=dict,
        help_text="Merged policy dict (terminology, grading, features, admissions, etc.).",
    )
    version = models.CharField(max_length=32, default="1.0")
    is_active = models.BooleanField(default=True, db_index=True)
    country_code = models.CharField(max_length=10, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Blueprint pack"
        verbose_name_plural = "Blueprint packs"
        indexes = [models.Index(fields=["is_active", "category"])]

    def __str__(self):
        return f"{self.name} ({self.slug})"

    def get_schools_using_this_pack(self):
        """Schools that have this pack applied (for "Update bundle" when version increases)."""
        from apps.schools.models import School
        return School.objects.filter(tenant_blueprint__applied_pack=self).distinct()

    def get_schools_needing_update(self):
        """Schools using this pack whose active bundle version is older than this pack's version."""
        from apps.schools.models import School
        return School.objects.filter(
            tenant_blueprint__applied_pack=self,
        ).exclude(
            tenant_blueprint__active_bundle__applied_pack_version=self.version,
        ).distinct()
