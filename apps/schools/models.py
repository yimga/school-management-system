"""
Multi-tenant School and SchoolMembership models (Option B+C).
School is the tenant; SchoolMembership links users to schools with a role.
Phase D: Plan + addons; is_feature_enabled(tenant, code) for feature gate.
"""

import logging
import uuid

from django.conf import settings
from django.db import models
from django.db.utils import DatabaseError, OperationalError


logger = logging.getLogger(__name__)

# Avoid shadowing by School.settings JSONField when referencing AUTH_USER_MODEL in FKs.
_AUTH_USER_MODEL = getattr(settings, "AUTH_USER_MODEL", "accounts.User")


def _default_timezone():
    """Platform default timezone (no hardcoded Africa/Douala). See config.PLATFORM_DEFAULT_TIMEZONE."""
    return getattr(settings, "PLATFORM_DEFAULT_TIMEZONE", "UTC")


def can(school, capability: str) -> bool:
    """
    Section 25.1: Entitlement check — return True if tenant has the capability/module enabled.
    Alias for is_feature_enabled(school, capability). Use for can(tenant, "MODULE_X") semantics.
    """
    return is_feature_enabled(school, capability)


def limits(school) -> dict:
    """
    Section 25.1: Return effective quota limits for the tenant (from TenantQuotaLimit).
    Returns dict mapping limit_type (e.g. api_calls_per_month) to limit_value.
    Plan-level limits can be merged by callers if needed.
    """
    if school is None:
        return {}
    try:
        from apps.schools.models import TenantQuotaLimit

        qs = TenantQuotaLimit.objects.filter(school=school, is_active=True)
        return {q.limit_type: q.limit_value for q in qs}
    except (
        ImportError,
        DatabaseError,
        OperationalError,
        AttributeError,
        TypeError,
        KeyError,
    ):
        return {}


def is_feature_enabled(school, code: str) -> bool:
    """
    Return True if the tenant (school) has the feature/module enabled.
    Phase D: (1) plan.included_features, (2) school.addons, (3) School.features + FeatureToggleState.
    Phase E: When billing_type is COMPLIMENTARY or MANUAL_OVERRIDE, grant full access (return True).
    """
    if school is None:
        return False
    # Phase E: Billing waiver — skip plan/feature checks and grant full access
    billing_type = getattr(school, "billing_type", None)
    if billing_type in ("COMPLIMENTARY", "MANUAL_OVERRIDE"):
        return True
    normalized = (code or "").strip().lower()
    if not normalized:
        return False
    plan = getattr(school, "plan", None)
    if plan and getattr(plan, "included_features", None):
        included = [str(x).strip().lower() for x in plan.included_features if x]
        if normalized in included:
            return True
    addons = getattr(school, "addons", None) or []
    if isinstance(addons, list):
        addon_set = [str(x).strip().lower() for x in addons if x]
        if normalized in addon_set:
            return True
    # Wedges 23–43: School.features JSON (learning institution packs + one-click installs)
    raw_feats = getattr(school, "features", None) or {}
    if isinstance(raw_feats, dict):
        for fk, fv in raw_feats.items():
            if fv and str(fk).strip().lower() == normalized:
                return True
    # Phase A: getTenantModules — union of feature keys from TenantSystem + SystemFeature
    try:
        from apps.siteconfig.tenant_config import get_tenant_modules

        if normalized in (get_tenant_modules(school) or []):
            return True
    except (ImportError, AttributeError, TypeError) as e:
        logger.debug(
            "schools.is_feature_enabled get_tenant_modules for school=%s code=%s: %s",
            school,
            code,
            e,
        )
    return _has_feature_fallback(school, code)


def _plan_entitlements_direct_grant(school, normalized: str) -> bool:
    """Plan.included_features, addons, or School.features JSON — no operator floor."""
    plan = getattr(school, "plan", None)
    if plan and getattr(plan, "included_features", None):
        included = [str(x).strip().lower() for x in plan.included_features if x]
        if normalized in included:
            return True
    addons = getattr(school, "addons", None) or []
    if isinstance(addons, list):
        addon_set = [str(x).strip().lower() for x in addons if x]
        if normalized in addon_set:
            return True
    raw_feats = getattr(school, "features", None) or {}
    if isinstance(raw_feats, dict):
        for fk, fv in raw_feats.items():
            if fv and str(fk).strip().lower() == normalized:
                return True
    return False


def _materialized_feature_entitlement_state(school, normalized: str):
    """Return True/False from billing Entitlement when present; None when absent."""
    try:
        from apps.billing.models import Entitlement

        row = (
            Entitlement.objects.filter(
                school=school,
                code=normalized,
                kind=Entitlement.Kind.FEATURE,
            )
            .order_by("-is_enabled", "-updated_at")
            .first()
        )
        if row is not None:
            return bool(row.is_enabled)
    except (ImportError, DatabaseError, OperationalError, AttributeError, TypeError):
        return None
    return None


def is_plan_entitlement_feature_enabled(school, code: str) -> bool:
    """
    True when the capability is granted via plan, addons, or School.features JSON,
    or via the platform operator default report-platform bundle (manifest
    ``operator_default_report_platform_bundle``) or per-school
    ``School.report_platform_bundle_slug`` as a **floor** for granular codes
    when the tenant has coarse ``reports`` on plan/addons/features.

    Does not include module-manifest required_apps, TenantSystem, or policy toggles.

    Use for HTTP feature gates tied to billing SKUs (e.g. ministry report URLs) where
    ``is_feature_enabled`` would be true for base ``reports`` from BASE_SCHOOL manifest.
    Same billing waiver as ``is_feature_enabled`` (COMPLIMENTARY / MANUAL_OVERRIDE).
    """
    if school is None:
        return False
    billing_type = getattr(school, "billing_type", None)
    if billing_type in ("COMPLIMENTARY", "MANUAL_OVERRIDE"):
        return True
    normalized = (code or "").strip().lower()
    if not normalized:
        return False
    materialized = _materialized_feature_entitlement_state(school, normalized)
    if materialized is not None:
        return materialized
    if _plan_entitlements_direct_grant(school, normalized):
        return True
    from apps.siteconfig.billing_sku_registry import (
        ALL_REPORT_PLATFORM_FEATURE_CODES,
        get_effective_report_platform_floor_codes_for_school,
    )

    if (
        normalized != "reports"
        and normalized in ALL_REPORT_PLATFORM_FEATURE_CODES
        and _plan_entitlements_direct_grant(school, "reports")
    ):
        if normalized in get_effective_report_platform_floor_codes_for_school(school):
            return True
    return False


def _has_feature_fallback(school, code: str) -> bool:
    """Legacy: policy features + resolve_module_enabled (constitution: read from get_effective_policy)."""
    normalized = (code or "").strip().lower()
    if not normalized:
        return False
    from apps.policies.policy_registry import get_effective_policy

    policy = get_effective_policy(school)
    fallback = bool(policy.get("features", {}).get(normalized))
    try:
        from apps.siteconfig.feature_toggles import resolve_module_enabled

        return resolve_module_enabled(normalized, school=school, fallback=fallback)
    except (
        ImportError,
        AttributeError,
        TypeError,
        ValueError,
        KeyError,
        DatabaseError,
    ) as e:
        logger.debug(
            "schools._has_feature_fallback for school=%s code=%s: %s",
            getattr(school, "id", None),
            code,
            e,
        )
        return fallback


def _get_role_choices():
    from apps.accounts.models import User

    return User.Role.choices


class School(models.Model):
    """
    Tenant: one row per school. Subdomain/slug identifies the school in the URL.
    Canonical mapping: School = Tenant (one-to-one). Campus = future multi-branch entity.
    See docs/SCHOOL_TENANT_CAMPUS_CANONICAL.md.

    Field responsibilities: identity, branding, plan, and region stay here; behavior comes from
    request.tenant_runtime. settings/features are storage only — written by tenant_config,
    read only by policies.resolver for compilation. See docs/SCHOOL_FIELD_RESPONSIBILITY_MAP.md.
    """

    class SubSystem(models.TextChoices):
        FR = "FR", "French sub-system"
        EN = "EN", "English sub-system"
        INT = "INT", "International"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(
        max_length=120, unique=True, help_text="URL slug e.g. ghs-limbe"
    )
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
        help_text="Sub-system: FR/EN or International (region-configurable)",
    )
    default_region = models.ForeignKey(
        "siteconfig.RegionConfig",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="schools",
        help_text="Region for currency, grading, timezone",
    )
    country_code = models.CharField(
        max_length=2,
        blank=True,
        db_index=True,
        help_text="Canonical ISO 3166-1 alpha-2 country code for onboarding and analytics.",
    )
    # Wave E — G4: data residency region. Distinct from `regional_cluster`
    # (which the existing TenantDatabaseRouter uses to pick a DB alias):
    # `data_region` is the *regulatory* answer ("EU data must live in EU"),
    # while `regional_cluster` is the *operational* answer ("which alias to
    # route this request to"). The verify_data_residency command refuses to
    # complete if the two disagree.
    data_region = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        help_text=(
            "Regulatory data residency region (e.g. 'eu_central', 'us_east', "
            "'apac_southeast'). Defaults from country_code via "
            "apps.schools.data_residency.derive_default_region; explicit override "
            "wins."
        ),
    )
    subdivision = models.ForeignKey(
        "registries.SubdivisionRegistry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schools",
        help_text="Canonical subdivision selection for this school.",
    )
    timezone = models.CharField(max_length=50, default=_default_timezone)
    default_language = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text=(
            "Tenant default language code (mirrors settings.LANGUAGES). When set, "
            "anonymous visitors to this tenant's marketing surface get this language "
            "before Accept-Language is consulted. Empty = platform default 'en'."
        ),
    )
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="School-level overrides: grading_logic, term_count, custom fields config, etc.",
    )
    features = models.JSONField(
        default=dict,
        blank=True,
        help_text='Enabled modules: {"library": true, "transport": false}',
    )
    logo_url = models.URLField(
        blank=True, help_text="URL to school logo (e.g. from tenants/{id}/logo.png)"
    )
    wallpaper_url = models.URLField(
        blank=True,
        help_text="URL to tenant login wallpaper (split-screen left panel image)",
    )
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
    # Multi-level hierarchy: materialized path (e.g. "" or "uuid1" or "uuid1/uuid2") for recursive queries
    hierarchy_path = models.CharField(
        max_length=1024,
        blank=True,
        db_index=True,
        help_text="Slash-separated UUIDs from root to parent; empty for root. Used for get_descendants/get_ancestors.",
    )
    # Phase 4: whitelabel custom domain
    custom_domain = models.CharField(
        max_length=255,
        blank=True,
        help_text="Custom domain e.g. portal.school.edu",
    )
    custom_domain_verified = models.BooleanField(default=False)
    # Phase B/H: Admin theme choice (Unfold [RECOMMENDED], Jazzmin, Sneat); optional "Change theme" in settings.
    theme_choice = models.CharField(
        max_length=20,
        choices=[
            ("UNFOLD", "Unfold (Modern)"),
            ("JAZZMIN", "Jazzmin (Classic)"),
            ("SNEAT", "Sneat (Enterprise)"),
        ],
        default="UNFOLD",
        blank=True,
        help_text="Admin/backend theme. Change theme in School edit or Site settings.",
    )
    # W3-5: Per-tenant theme pack (portal/login). When set, overrides the global tenant platform theme default for this school.
    theme_pack = models.ForeignKey(
        "siteconfig.ThemePack",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schools_using_theme",
        help_text="Portal/login theme pack for this school. Leave blank to use global default.",
    )
    plan = models.ForeignKey(
        "siteconfig.Plan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schools",
        help_text="Subscription plan; included_features + addons determine enabled modules.",
    )
    # 21.4 Operational identity: default workflow/dashboard/comms/fee pack (slugs or keys from registry)
    default_workflow_slug = models.CharField(
        max_length=80,
        blank=True,
        help_text="Default workflow preset slug for this school (e.g. from TenantWorkflow registry).",
    )
    default_dashboard_slug = models.CharField(
        max_length=80,
        blank=True,
        help_text="Default dashboard preset slug for this school (e.g. from dashboard registry).",
    )
    addons = models.JSONField(
        default=list,
        blank=True,
        help_text="Additional feature codes beyond plan (e.g. ['design_studio', 'inventory'])",
    )
    report_platform_bundle_slug = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=(
            "Optional reports-standard or reports-advanced: overrides platform operator "
            "default for granular report SKU floor when plan/addons/features include coarse "
            "reports. Empty = operator default only (see billing_sku_registry)."
        ),
    )
    school_type = models.CharField(
        max_length=32,
        default="BASE_SCHOOL",
        blank=True,
        db_index=True,
        help_text="School type from module manifest (BASE_SCHOOL, TECHNICAL_COLLEGE, STEM_ACADEMY). Determines required_apps and UI skin.",
    )

    class BillingType(models.TextChoices):
        REGULAR = "REGULAR", "Regular (paying)"
        FREE_TRIAL = "FREE_TRIAL", "Free trial"
        COMPLIMENTARY = "COMPLIMENTARY", "Complimentary (waived)"
        MANUAL_OVERRIDE = "MANUAL_OVERRIDE", "Manual override (full access)"

    billing_type = models.CharField(
        max_length=20,
        choices=BillingType.choices,
        default=BillingType.REGULAR,
        help_text="When COMPLIMENTARY or MANUAL_OVERRIDE, billing checks are skipped; waiver_note required.",
    )
    trial_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="When billing_type is FREE_TRIAL, trial ends on this date.",
    )
    waiver_note = models.TextField(
        blank=True,
        help_text="Required when billing_type is COMPLIMENTARY or MANUAL_OVERRIDE (e.g. partnership with NGO).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Phase H: Optional approval workflow; Super Admin can list/filter unapproved schools.
    is_approved = models.BooleanField(
        default=True,
        help_text="When False, school is pending approval. Default True for backward compatibility.",
    )
    last_activity = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Phase H optional: last request time for this tenant (throttled updates).",
    )
    # Section 8.7: Account freeze (storage/billing limit exceeded)
    is_frozen = models.BooleanField(
        default=False,
        help_text="When True, tenant is restricted (e.g. storage or billing); middleware redirects to frozen page except billing/logout.",
    )
    frozen_reason = models.CharField(
        max_length=30,
        blank=True,
        choices=[
            ("", "—"),
            ("STORAGE", "Storage limit exceeded"),
            ("BILLING", "Subscription overdue"),
        ],
        help_text="Reason for freeze; required when is_frozen is True.",
    )

    # Plan XXI: Compliance Region — GDPR (EU), FERPA (US), NDPR (Nigeria). Enables data masking, retention, consent flows.
    class ComplianceRegion(models.TextChoices):
        NONE = "", "None (default)"
        EU = "EU", "EU (GDPR)"
        US = "US", "US (FERPA)"
        NDPR = "NDPR", "Nigeria (NDPR)"

    compliance_region = models.CharField(
        max_length=10,
        choices=ComplianceRegion.choices,
        default=ComplianceRegion.NONE,
        blank=True,
        help_text="Compliance region for data privacy: EU (GDPR), US (FERPA), Nigeria (NDPR). Affects masking, retention, consent.",
    )
    # World Engine: optional JSON branding (primary, accent, font) → CSS vars --primary, --accent for tenant surfaces.
    branding_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Optional: {"primary": "#hex", "accent": "#hex", "font": "Family, sans-serif"}. Maps to --primary, --accent in tenant CSS.',
    )
    education_levels = models.ManyToManyField(
        "registries.EducationLevelRegistry",
        blank=True,
        related_name="schools",
        help_text="Canonical education levels served by this school.",
    )
    education_system_types = models.ManyToManyField(
        "registries.EducationSystemTypeRegistry",
        blank=True,
        related_name="schools",
        help_text="Canonical education system types served by this school.",
    )
    # SOT §0.2.1 wedge 14–22: primary sector (Public, Private, Charter, International, etc.) for RBAC/reporting.
    primary_sector = models.CharField(
        max_length=48,
        blank=True,
        db_index=True,
        help_text="Primary education system sector (wedge 14–22): PUBLIC, PRIVATE, CHARTER, INTERNATIONAL, FAITH_BASED, HOME_SCHOOL, GOVERNMENT_MINISTRY, NGO, MULTI_CAMPUS.",
    )
    # World Engine: data sovereignty / scaling — region cluster and optional dedicated DB.
    regional_cluster = models.CharField(
        max_length=63,
        blank=True,
        help_text="Optional: region cluster for DB routing (e.g. eu, apac). Used with multi-DB router.",
    )
    dedicated_db_alias = models.CharField(
        max_length=63,
        blank=True,
        help_text="Optional: dedicated DB alias for mega-schools (10k+ students). Super Admin can set.",
    )
    # JIT (Just-In-Time): principal/school admin consent required before super-admin can impersonate (195-country governance).
    impersonation_consent_granted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When set, principal/school admin has consented to RunMyCampus support impersonation (JIT).",
    )
    impersonation_consent_granted_by = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="User (e.g. principal) who granted impersonation consent.",
    )
    impersonation_dual_control = models.BooleanField(
        default=False,
        help_text=(
            "When True, platform operators must name a second approver (different SUPERADMIN/superuser) "
            "before impersonation is allowed (four-eyes)."
        ),
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "School"
        verbose_name_plural = "Schools"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError

        from apps.siteconfig.billing_sku_registry import REPORT_PLATFORM_SKU_BUNDLES

        raw = (getattr(self, "report_platform_bundle_slug", None) or "").strip()
        if raw:
            s = raw.lower()
            if s not in REPORT_PLATFORM_SKU_BUNDLES:
                raise ValidationError(
                    {
                        "report_platform_bundle_slug": (
                            "Must be empty, reports-standard, or reports-advanced "
                            "(see billing_sku_registry.REPORT_PLATFORM_SKU_BUNDLES)."
                        )
                    }
                )

    @property
    def canonical_country_code(self) -> str:
        if self.country_code:
            return str(self.country_code).upper()
        try:
            from apps.siteconfig.global_catalog import GlobalGeoCatalog

            return GlobalGeoCatalog.alpha2_for_country(
                getattr(self, "default_region_id", "") or ""
            )
        except (ImportError, AttributeError, TypeError, ValueError, KeyError) as e:
            logger.debug("schools.Region.canonical_country_code failed: %s", e)
            return ""

    @property
    def resolved_country_alpha3(self) -> str:
        try:
            from apps.siteconfig.global_catalog import GlobalGeoCatalog

            return GlobalGeoCatalog.normalize_country_code(
                self.country_code or getattr(self, "default_region_id", "") or ""
            )
        except (ImportError, AttributeError, TypeError, ValueError, KeyError) as e:
            logger.debug("schools.Region.resolved_country_alpha3 failed: %s", e)
            return ""

    def save(self, *args, **kwargs):
        rp = (getattr(self, "report_platform_bundle_slug", None) or "").strip()
        self.report_platform_bundle_slug = rp.lower() if rp else ""
        # Keep materialized path in sync for multi-level hierarchy
        if self.parent_school_id:
            parent = School.objects.filter(pk=self.parent_school_id).first()
            if parent:
                base = (getattr(parent, "hierarchy_path", "") or "").strip()
                self.hierarchy_path = (
                    (base + "/" + str(parent.pk)).strip("/") if base else str(parent.pk)
                )
            else:
                self.hierarchy_path = str(self.parent_school_id)
        else:
            self.hierarchy_path = ""
        super().save(*args, **kwargs)

    def has_feature(self, code: str) -> bool:
        """Return True if the school has the given feature/module enabled. Phase D: considers plan + addons."""
        return is_feature_enabled(self, code)

    def get_cname_target(self) -> str:
        """Return the hostname schools should CNAME their custom_domain to (whitelabel Phase 4)."""
        from apps.schools.host_routing import get_canonical_base_domain

        return get_canonical_base_domain() or "runmycampus.com"

    def get_ancestor_chain(self) -> list:
        """
        Return list of parent schools from this school up to root (for deeper nested tenancy).
        Order: [immediate_parent, grandparent, ...]. Empty if no parent.
        """
        chain = []
        current = self.parent_school
        seen = {self.pk}
        while current and current.pk not in seen:
            seen.add(current.pk)
            chain.append(current)
            current = getattr(current, "parent_school", None)
        return chain

    def get_root_school(self) -> "School | None":
        """Return the top-level parent in the tenant hierarchy, or self if no parent."""
        chain = self.get_ancestor_chain()
        return chain[-1] if chain else (None if self.parent_school_id else self)

    def get_child_schools(self):
        """
        Active direct children (nested tenancy / campus switcher).

        Consumed by :func:`apps.api.views_v1.MeSchoolsView` to populate ``child_schools`` when
        ``request.school`` is the parent campus.
        """
        return School.objects.filter(parent_school_id=self.pk, is_active=True).order_by("name")

    def get_descendants(self, include_self=False):
        """Return all schools in the subtree (children, grandchildren, ...). Uses hierarchy_path when set."""
        from django.db.models import Q

        # Path format: root has ""; child has "/root_id"; grandchild has "/root_id/parent_id"
        if self.hierarchy_path:
            prefix = (self.hierarchy_path + "/" + str(self.pk)).strip("/")
            qs = School.objects.filter(
                Q(hierarchy_path=prefix) | Q(hierarchy_path__startswith=prefix + "/"),
                is_active=True,
            )
        else:
            qs = School.objects.filter(parent_school_id=self.pk, is_active=True)
        if include_self:
            qs = School.objects.filter(
                Q(pk=self.pk) | Q(pk__in=qs.values_list("id", flat=True)),
                is_active=True,
            )
        return qs

    def get_ancestors(self):
        """Return all ancestor schools (parent, grandparent, ...) using hierarchy_path or parent_school walk."""
        if self.hierarchy_path:
            uuids = [u.strip() for u in self.hierarchy_path.split("/") if u.strip()]
            if not uuids:
                return School.objects.none()
            return School.objects.filter(pk__in=uuids, is_active=True)
        return type(self).objects.filter(
            pk__in=[p.pk for p in self.get_ancestor_chain()]
        )


class SchoolProvisioningEvent(models.Model):
    """Audit trail for school onboarding and domain-verification lifecycle."""

    class EventType(models.TextChoices):
        REQUEST_RECEIVED = "REQUEST_RECEIVED", "Request Received"
        QUEUED = "QUEUED", "Queued"
        STARTED = "STARTED", "Started"
        PROFILE_APPLIED = "PROFILE_APPLIED", "Profile Applied"
        ACADEMIC_YEAR_READY = "ACADEMIC_YEAR_READY", "Academic Year Ready"
        SUBJECTS_READY = "SUBJECTS_READY", "Subjects Ready"
        BLUEPRINT_TEMPLATE_RECORDED = (
            "BLUEPRINT_TEMPLATE_RECORDED",
            "Blueprint Template Recorded",
        )
        SAMPLE_DATA_READY = "SAMPLE_DATA_READY", "Sample Data Ready"
        DOMAIN_PENDING = "DOMAIN_PENDING", "Domain Pending"
        DOMAIN_VERIFIED = "DOMAIN_VERIFIED", "Domain Verified"
        DOMAIN_UNVERIFIED = "DOMAIN_UNVERIFIED", "Domain Unverified"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        OFFBOARDING_EXPORT = "OFFBOARDING_EXPORT", "Offboarding Export"
        OFFBOARDING_DEACTIVATED = (
            "OFFBOARDING_DEACTIVATED",
            "Offboarding Deactivated",
        )
        OFFBOARDING_PURGE_REQUESTED = (
            "OFFBOARDING_PURGE_REQUESTED",
            "Offboarding Purge Requested",
        )
        OFFBOARDING_PURGE_COMPLETED = (
            "OFFBOARDING_PURGE_COMPLETED",
            "Offboarding Purge Completed",
        )
        OFFBOARDING_SELF_SERVICE_REQUESTED = (
            "OFFBOARDING_SELF_SERVICE_REQUESTED",
            "Offboarding Self-Service Requested",
        )
        OFFBOARDING_SELF_SERVICE_CANCELLED = (
            "OFFBOARDING_SELF_SERVICE_CANCELLED",
            "Offboarding Self-Service Cancelled",
        )
        OFFBOARDING_AUTO_PURGE_SCHEDULED = (
            "OFFBOARDING_AUTO_PURGE_SCHEDULED",
            "Offboarding Auto Purge Scheduled",
        )
        OFFBOARDING_AUTO_PURGE_EXECUTED = (
            "OFFBOARDING_AUTO_PURGE_EXECUTED",
            "Offboarding Auto Purge Executed",
        )

    class Status(models.TextChoices):
        INFO = "INFO", "Info"
        SUCCESS = "SUCCESS", "Success"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="provisioning_events",
    )
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.INFO
    )
    message = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="school_provisioning_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["school", "-created_at"]),
            models.Index(fields=["event_type"]),
        ]
        verbose_name = "School provisioning event"
        verbose_name_plural = "School provisioning events"

    def __str__(self):
        return f"{self.school.name}: {self.event_type} ({self.status})"

    @classmethod
    def log_event(
        cls,
        *,
        school: School | None,
        event_type: str,
        status: str = Status.INFO,
        message: str = "",
        payload: dict | None = None,
        created_by=None,
    ):
        if school is None:
            return None
        return cls.objects.create(
            school=school,
            event_type=event_type,
            status=status,
            message=message or "",
            payload=payload or {},
            created_by=created_by if getattr(created_by, "pk", None) else None,
        )


class SchoolDomain(models.Model):
    """
    Multiple domains per tenant (shared schema). Used for subdomain and custom domains;
    Caddy ask endpoint and middleware resolve tenant from domain. DNS verification
    uses dns_token (TXT runmycampus-verify=<token>).
    """

    class Kind(models.TextChoices):
        SUBDOMAIN = "SUBDOMAIN", "Subdomain"
        CUSTOM = "CUSTOM", "Custom domain"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="domain_entries",
    )
    domain = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Hostname e.g. school.runmycampus.com or portal.school.edu",
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="True after TXT verification (custom) or when created from School.subdomain (subdomain).",
    )
    dns_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="TXT record runmycampus-verify=<token> for custom domain verification.",
    )
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        default=Kind.CUSTOM,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["school", "domain"]
        unique_together = [("school", "domain")]
        indexes = [
            models.Index(fields=["domain"]),
            models.Index(fields=["is_verified", "domain"]),
        ]
        verbose_name = "School domain"
        verbose_name_plural = "School domains"

    def __str__(self):
        return f"{self.domain} → {self.school.name}"


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
        default="ADMIN",  # role-string-allow: model field default, resolved via _get_role_choices registry
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


class SignupVerification(models.Model):
    """
    Token for self-service school signup email verification. School is created
    with is_active=False; when user clicks link with valid token, school is
    activated and provisioning runs.
    """

    school = models.OneToOneField(
        School,
        on_delete=models.CASCADE,
        related_name="signup_verification",
    )
    email = models.EmailField()
    token = models.UUIDField(
        default=uuid.uuid4, editable=False, unique=True, db_index=True
    )
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Signup verification"
        verbose_name_plural = "Signup verifications"

    def __str__(self):
        return f"{self.email} → {self.school.name}"


class TenantQuotaLimit(models.Model):
    """Per-tenant API/quota limits for SaaS billing and fairness (Plan I)."""

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="quota_limits",
    )
    limit_type = models.CharField(
        max_length=64,
        help_text="e.g. api_calls_per_month, api_calls_per_minute, storage_mb",
    )
    limit_value = models.PositiveIntegerField(help_text="Numeric limit")
    period_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Period length in days (e.g. 30 for monthly); null for per-minute.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school", "limit_type"]
        unique_together = [("school", "limit_type")]
        verbose_name = "Tenant quota limit"
        verbose_name_plural = "Tenant quota limits"

    def __str__(self):
        return f"{self.school.name}: {self.limit_type}={self.limit_value}"


class TenantApiUsage(models.Model):
    """Per-tenant API usage for billing and super-admin dashboard (Plan I)."""

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="api_usage_records",
    )
    period_date = models.DateField(
        help_text="Date (or first day of period) for aggregation"
    )
    request_count = models.PositiveIntegerField(default=0)
    limit_type = models.CharField(
        max_length=64,
        default="api_calls",
        help_text="Matches TenantQuotaLimit.limit_type",
    )

    class Meta:
        ordering = ["-period_date", "school"]
        unique_together = [("school", "period_date", "limit_type")]
        verbose_name = "Tenant API usage"
        verbose_name_plural = "Tenant API usage"

    def __str__(self):
        return f"{self.school.name} {self.period_date}: {self.request_count}"


class TenantInteropAccessLog(models.Model):
    """
    OneRoster / interop API access audit (which token, which endpoint, from where).
    Phase J+: procurement and security review trail.
    """

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="interop_access_logs",
    )
    service = models.CharField(max_length=32, db_index=True, default="oneroster")
    endpoint = models.CharField(max_length=64, db_index=True)
    integration_id = models.IntegerField(null=True, blank=True)
    client_ip = models.CharField(max_length=64, blank=True)
    token_prefix = models.CharField(max_length=16, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "created_at"]),
        ]
        verbose_name = "Tenant interop access log"
        verbose_name_plural = "Tenant interop access logs"


from apps.schoolops.models import (  # noqa: E402,F401
    Bus,
    BiometricAttendanceLog,
    BiometricDevice,
    CanteenMeal,
    Campus,
    HealthRecord,
    Hostel,
    HostelRoom,
    InventoryItem,
    LibraryItem,
    LibraryLoan,
    Route,
    Stop,
)


class AdvancementDonor(models.Model):
    """
    Wedge 5 Phase 2: per-school donor CRM (minimal v1 — gifts and receipts).
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="advancement_donors",
    )
    display_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    external_ref = models.CharField(
        max_length=120, blank=True, help_text="External CRM id"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Advancement donor"
        verbose_name_plural = "Advancement donors"

    def __str__(self) -> str:
        return f"{self.display_name} ({self.school.slug})"


class AdvancementGift(models.Model):
    """Gift / receipt line tied to a donor."""

    donor = models.ForeignKey(
        AdvancementDonor,
        on_delete=models.CASCADE,
        related_name="gifts",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    received_at = models.DateField()
    receipt_sent = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    campaign_name = models.CharField(
        max_length=120,
        blank=True,
        help_text="Campaign or appeal label (e.g. Annual Fund 2026).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at", "-pk"]
        verbose_name = "Advancement gift"
        verbose_name_plural = "Advancement gifts"


class MarketingFunnelEvent(models.Model):
    """
    Growth analytics: full conversion funnel (anonymous + school-scoped).
    Legacy: visit → discovery → signup → activation.
    Extended: demo_started → signup_completed → first_dashboard_view → first_action →
    first_result → subscription_started (billing closed-loop).
    utm_source / utm_medium support funnel breakdown by channel.
    """

    EVENT_TYPES = (
        ("visit", "Visit (landing)"),
        ("discovery", "Discovery (find school / discover)"),
        ("signup", "Signup (form submitted)"),
        ("signup_started", "Signup flow opened (landing on self-service form)"),
        ("activation", "Activation (school verified / live)"),
        ("onboarding_start", "Public onboarding wizard opened (step 1)"),
        ("onboarding_complete", "Public onboarding wizard finished (review / signup)"),
        ("demo_started", "Demo started (book-demo submitted)"),
        ("demo_attendance_completed", "Conversion demo: attendance step completed"),
        ("demo_marks_completed", "Conversion demo: marks step completed"),
        ("demo_report_completed", "Conversion demo: report step completed"),
        ("demo_cta_seen", "Conversion demo: create-school CTA viewed"),
        ("signup_completed", "Signup completed (email verified, school active)"),
        ("first_dashboard_view", "First authenticated dashboard view"),
        ("first_action", "First substantive POST / action"),
        ("first_result", "First operational outcome (e.g. payment recorded)"),
        ("subscription_started", "Platform subscription row created (billing)"),
        ("payment_success", "Payment processor reported successful charge/settlement"),
        ("payment_failed", "Payment processor reported failed or declined payment"),
        ("tenant_recovered", "Tenant marked recovered after churn/at-risk resolution"),
    )
    event_type = models.CharField(max_length=40, choices=EVENT_TYPES, db_index=True)
    session_key = models.CharField(max_length=128, blank=True, db_index=True)
    utm_source = models.CharField(max_length=128, blank=True, db_index=True)
    utm_medium = models.CharField(max_length=128, blank=True, db_index=True)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="marketing_funnel_events",
    )
    user = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_funnel_events",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Marketing funnel event"
        verbose_name_plural = "Marketing funnel events"
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["school", "event_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} at {self.created_at}"
