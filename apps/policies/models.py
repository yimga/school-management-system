"""
Policy Registry v2: versioned, auditable policy storage (optional).

Resolver (get_effective_policy) currently reads School.settings and School.features.
When POLICY_USE_BUNDLES is True and a PolicyBundle exists for the school, resolver
can merge from that snapshot instead (future). These models provide the storage.

Phase 6: BlueprintPack = catalog of installable policy packs (e.g. Cameroon Francophone,
UAE MoE+IB, UK GCSE/A-Level). Applying a pack creates a PolicyBundle for the school
and sets TenantBlueprint.active_bundle.
"""

from decimal import Decimal

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
    policy_snapshot should contain typed module sections: admissions_policy, gradebook_policy,
    finance_policy, attendance_policy, communication_policy, compliance_policy, portal_policy, payroll_policy.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="policy_bundles",
        null=True,
        blank=True,
        help_text="Null = platform/country-level bundle.",
    )
    code = models.CharField(max_length=80, blank=True, db_index=True)
    name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    policy_snapshot = models.JSONField(
        default=dict, help_text="Merged policy dict with typed module sections."
    )
    version = models.PositiveIntegerField(default=1)
    applied_pack_version = models.CharField(
        max_length=32,
        blank=True,
        help_text="When created from a BlueprintPack, store pack.version for update detection.",
    )
    country_scope = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Country code or '*' for global.",
    )
    blueprint_compatibility = models.JSONField(
        default=list,
        blank=True,
        help_text="List of blueprint pack slugs this bundle is compatible with.",
    )
    precedence_weight = models.PositiveIntegerField(
        default=0, help_text="Higher = overrides lower when multiple apply."
    )
    migration_notes = models.TextField(blank=True)
    deprecated_replacement_reference = models.CharField(max_length=80, blank=True)
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
    Catalog entry for a blueprint pack. Defines institution archetype and policy_snapshot template.
    Applying creates a PolicyBundle and sets TenantBlueprint.active_bundle.
    """

    slug = models.SlugField(max_length=80, unique=True)
    code = models.CharField(
        max_length=80, blank=True, db_index=True, help_text="Alias for slug/code."
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    family = models.CharField(max_length=64, blank=True, db_index=True)
    category = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="e.g. Cameroon Francophone, UAE MoE+IB, UK GCSE/A-Level, US charter",
    )
    institution_type = models.ForeignKey(
        "registries.InstitutionTypeRegistry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    supported_country_scope = models.JSONField(
        default=list, blank=True, help_text="List of country codes or [] for all."
    )
    supported_education_system_types = models.JSONField(
        default=list, blank=True, help_text="List of education system type codes."
    )
    recommended_education_levels = models.JSONField(
        default=list, blank=True, help_text="List of education level codes."
    )
    default_terminology_pack = models.CharField(max_length=48, blank=True)
    default_calendar_family = models.CharField(max_length=48, blank=True)
    default_grade_scale_family_hints = models.JSONField(default=list, blank=True)
    default_dashboard_pack_id = models.PositiveIntegerField(null=True, blank=True)
    default_workflow_pack_id = models.PositiveIntegerField(null=True, blank=True)
    branding_family_hint = models.CharField(max_length=48, blank=True)
    policy_snapshot = models.JSONField(
        default=dict,
        help_text="Merged policy dict (terminology, grading, features, admissions, etc.).",
    )
    version = models.CharField(max_length=32, default="1.0")
    deprecated_replacement_reference = models.CharField(max_length=80, blank=True)
    list_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Commercial list price for premium blueprint packs (billing integration).",
    )
    is_premium_commercial = models.BooleanField(
        default=False,
        db_index=True,
        help_text="When True, apply/upgrade may require commercial entitlement.",
    )
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

        return (
            School.objects.filter(
                tenant_blueprint__applied_pack=self,
            )
            .exclude(
                tenant_blueprint__active_bundle__applied_pack_version=self.version,
            )
            .distinct()
        )


class BlueprintCompatibilityRule(models.Model):
    """Rule linking blueprint packs to compatible policy bundles or constraints."""

    blueprint_pack = models.ForeignKey(
        BlueprintPack,
        on_delete=models.CASCADE,
        related_name="compatibility_rules",
    )
    compatible_policy_slugs = models.JSONField(default=list, blank=True)
    compatible_country_codes = models.JSONField(default=list, blank=True)
    min_version = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Blueprint compatibility rule"
        verbose_name_plural = "Blueprint compatibility rules"


class PolicyCompatibilityRule(models.Model):
    """Rule for which blueprints/countries a policy bundle applies to."""

    policy_bundle = models.ForeignKey(
        PolicyBundle,
        on_delete=models.CASCADE,
        related_name="compatibility_rules",
        null=True,
        blank=True,
    )
    blueprint_slug = models.CharField(max_length=80, blank=True, db_index=True)
    country_code = models.CharField(max_length=10, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Policy compatibility rule"
        verbose_name_plural = "Policy compatibility rules"


class TenantPolicyOverride(models.Model):
    """Tenant-level override for a specific policy key (stored per school)."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="policy_overrides",
    )
    policy_key = models.CharField(
        max_length=120, db_index=True, help_text="e.g. admissions.numbering_strategy"
    )
    value = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant policy override"
        verbose_name_plural = "Tenant policy overrides"
        unique_together = [("school", "policy_key")]


class ScheduledPolicyOverride(models.Model):
    """Temporary policy override active between start_at and end_at."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="scheduled_policy_overrides",
    )
    policy_key = models.CharField(max_length=120, db_index=True)
    value = models.JSONField(default=dict)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Scheduled policy override"
        verbose_name_plural = "Scheduled policy overrides"


class PolicyRule(models.Model):
    """Move 3 (ABAC): typed policy rule.

    Each rule has an effect (allow|deny), subject/action/resource selectors,
    and optional structured conditions. The PolicyDecisionPoint (see
    ``apps.policies.pdp``) evaluates rules in priority order and emits a
    decision + explanation written to ``PolicyDecisionLog``.

    A rule is "scoped" to either the platform (school=None) or a specific tenant.
    """

    class Effect(models.TextChoices):
        ALLOW = "allow", "Allow"
        DENY = "deny", "Deny"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="policy_rules",
        help_text="Null => platform-wide rule applied to every tenant.",
    )
    code = models.SlugField(max_length=120, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    effect = models.CharField(
        max_length=8, choices=Effect.choices, default=Effect.ALLOW, db_index=True
    )
    # Selectors. The string DSL is documented in apps/policies/pdp.py.
    subject_match = models.JSONField(
        default=dict,
        blank=True,
        help_text='e.g. {"role_any": ["TEACHER","ADMIN"]} or {"user_id": 42}.',
    )
    action_match = models.JSONField(
        default=dict,
        blank=True,
        help_text='e.g. {"actions": ["read","export"]} or {"actions": ["*"]}.',
    )
    resource_match = models.JSONField(
        default=dict,
        blank=True,
        help_text='e.g. {"entity": "student", "field": "ssn"} or {"entity_any": ["student","parent"]}.',
    )
    conditions = models.JSONField(
        default=list,
        blank=True,
        help_text='List of {attr,op,value} predicates ANDed together.',
    )
    priority = models.IntegerField(
        default=100,
        db_index=True,
        help_text="Lower number = higher priority. First-matching rule wins.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Policy rule"
        verbose_name_plural = "Policy rules"
        ordering = ["priority", "code"]
        unique_together = [["school", "code"]]
        indexes = [
            models.Index(fields=["is_active", "priority"], name="pol_rule_act_pri_idx"),
        ]

    def __str__(self) -> str:
        scope = self.school.slug if self.school_id else "platform"
        return f"[{scope}] {self.effect}:{self.code}"


class PolicyDecisionLog(models.Model):
    """Append-only log of every PDP decision.

    The decision_reason field carries a human-readable explanation (e.g.,
    "denied because rule abac.ssn_secret matched on field-level sensitivity").
    """

    class Effect(models.TextChoices):
        ALLOW = "allow", "Allow"
        DENY = "deny", "Deny"
        IMPLICIT_DENY = "implicit_deny", "Implicit deny (no rule matched)"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="policy_decision_logs",
    )
    subject_id = models.CharField(max_length=120, blank=True, db_index=True)
    subject_role = models.CharField(max_length=64, blank=True, db_index=True)
    action = models.CharField(max_length=64, db_index=True)
    resource_type = models.CharField(max_length=120, db_index=True)
    resource_id = models.CharField(max_length=190, blank=True, db_index=True)
    effect = models.CharField(max_length=20, choices=Effect.choices, db_index=True)
    matched_rule = models.ForeignKey(
        PolicyRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decisions",
    )
    decision_reason = models.TextField(blank=True)
    context_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Policy decision log"
        verbose_name_plural = "Policy decision logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "subject_role", "-created_at"], name="pol_dec_sch_role_idx"),
            models.Index(fields=["action", "resource_type"], name="pol_dec_act_res_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.effect}:{self.action}:{self.resource_type}"
