"""
Multi-tenant School and SchoolMembership models (Option B+C).
School is the tenant; SchoolMembership links users to schools with a role.
Phase D: Plan + addons; is_feature_enabled(tenant, code) for feature gate.
"""

import hashlib
import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.utils import DatabaseError, OperationalError


logger = logging.getLogger(__name__)

# Avoid shadowing by School.settings JSONField when referencing AUTH_USER_MODEL in FKs.
_AUTH_USER_MODEL = getattr(settings, "AUTH_USER_MODEL", "accounts.User")


def _default_timezone():
    """Platform default timezone (no hardcoded Africa/Douala). See config.PLATFORM_DEFAULT_TIMEZONE."""
    return getattr(settings, "PLATFORM_DEFAULT_TIMEZONE", "UTC")


def _default_currency():
    """Platform default currency (last-resort fallback only). See config.PLATFORM_DEFAULT_CURRENCY.

    Tenant-facing money should resolve through ``School.resolve_currency`` (local-first:
    explicit override → region → country pack → this platform default), never a hardcoded
    literal. This callable exists so model field defaults route through the platform
    setting instead of an inline "USD" literal.
    """
    return getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD")


def _resolve_owner_school(instance):
    """Best-effort owning ``School`` for a school-scoped row (direct FK, else via donor)."""
    school = getattr(instance, "school", None)
    if school is not None:
        return school
    donor = getattr(instance, "donor", None)
    if donor is not None:
        return getattr(donor, "school", None)
    return None


def _apply_local_currency_default(instance):
    """On create, fill a blank currency with the owning school's resolved (local-first) currency.

    Keeps the field tenant-local instead of a global literal: a school in Nigeria gets NGN,
    Cameroon gets XAF, etc. Falls back to the platform default when no school resolves so a
    row is never persisted with a blank currency.
    """
    state = getattr(instance, "_state", None)
    if state is None or not getattr(state, "adding", False):
        return
    if (getattr(instance, "currency", "") or "").strip():
        return
    school = _resolve_owner_school(instance)
    resolved = ""
    if school is not None:
        try:
            resolved = school.resolve_currency()
        except (AttributeError, DatabaseError, OperationalError, ValueError, TypeError):
            resolved = ""
    instance.currency = resolved or _default_currency()


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
    # Plan ceiling — behind RMC_PLAN_GATING_ENFORCED (default OFF => this block is
    # a no-op and resolution stays the historical pure union below). When ON, a
    # genuinely plan-gated code (in a paid plan but NOT the free/default plan) is
    # granted ONLY by an explicit plan/addon/feature/entitlement grant, so the
    # module-manifest + policy union further down can no longer silently open a
    # premium feature. Universal codes are not in the plan-gated set and fall
    # through to the union unchanged. See apps/schools/plan_gating.py.
    from apps.schools.plan_gating import (
        in_active_trial,
        is_plan_gated_code,
        plan_ceiling_grants,
        plan_gating_enforced,
    )

    if plan_gating_enforced():
        # Reverse trial: full access during the active trial window. When it
        # lapses (trial_end_date passed) this falls through and the ceiling
        # binds -> automatic downgrade to the plan's features (data untouched;
        # re-upgrading restores everything). This makes expiry gating work even
        # if the billing beat never flips FREE_TRIAL -> REGULAR.
        if in_active_trial(school):
            return True
        if is_plan_gated_code(normalized):
            return plan_ceiling_grants(school, normalized)
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


def _get_governance_operating_mode_choices():
    from apps.governance.operating_modes import GovernanceOperatingMode

    return GovernanceOperatingMode.choices


class SchoolQuerySet(models.QuerySet):
    """School querysets delete without chasing relations into tenant schemas.

    ``School.objects.filter(...).delete()`` used to raise
    ``ProgrammingError: relation "portal_portalfeatureitem" does not exist``
    whenever it ran in ``public`` under schema-per-tenant: the cascade collector
    walks every reverse relation, and ~200 of them are tenant tables that do not
    exist there. See ``apps/schools/deletion.py`` for the full explanation.
    """

    def delete(self):
        from apps.schools.deletion import assert_deletable, delete_school_rows

        schools = list(self)
        for school in schools:
            assert_deletable(school)
        deleted_count, by_label, _skipped = delete_school_rows(schools, using=self.db)
        self._result_cache = None
        return deleted_count, by_label

    delete.alters_data = True


class LiveSchoolManager(models.Manager.from_queryset(SchoolQuerySet)):
    """Opt-in manager that hides soft-deleted schools (deleted_at IS NOT NULL).

    Wave L6 (v3.61.6 — 2026-05-22). The default ``School.objects`` is
    intentionally LEFT ALONE so that ~50 existing callers don't
    silently change behavior. New code (and code that explicitly wants
    only live schools) should use ``School.live_objects``.
    """

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


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
    # Stored, indexed sha256(str(id))[:12] used by the WAL drain to resolve a
    # tenant from its hash in O(1). Kept in sync in save(); the drain falls back
    # to a full scan for any row whose hash predates the backfill migration.
    tenant_hash = models.CharField(
        max_length=12,
        blank=True,
        db_index=True,
        editable=False,
        help_text="Derived sha256(id)[:12] for fast WAL tenant resolution.",
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
    currency = models.CharField(
        max_length=3,
        blank=True,
        default="",
        help_text=(
            "Tenant default currency (ISO 4217, e.g. NGN / XAF / GBP / USD). Empty = "
            "derive local-first via resolve_currency(): country pack -> default_region -> "
            "platform default. Set explicitly to override (e.g. an international school "
            "billing in a currency other than its country's default)."
        ),
    )
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "School-level overrides: grading_logic, term_count, custom fields config, etc. "
            "Optional governance_inherit map (domain → inherit|local|hybrid) for group-member schools."
        ),
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
    # Wave L4 (v3.61.3 — 2026-05-22): reversible offboarding. Soft-delete
    # marker — when set, the school is in the grace period before purge.
    # Queries that should hide soft-deleted schools must filter
    # explicitly on `deleted_at__isnull=True` OR use the opt-in
    # ``School.live_objects`` manager added in v3.61.6 Wave L6. NEVER
    # touched by the hard purge path (drop_tenant_schema_for_school);
    # only by apps.lifecycle.services_offboarding.mark_deleted/restore.
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Soft-delete timestamp. NULL when school is live; set when offboarding requested.",
    )
    # Phase 4: super-tenant (parent school for consolidated dashboard)
    parent_school = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_schools",
        help_text="Parent tenant e.g. Catholic Education Secretariat",
    )
    # Global governance Phase 2A: optional legal owner (nullable — standalone schools unaffected)
    organization = models.ForeignKey(
        "governance.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schools",
        help_text="Optional Organization overlay; null = standalone individual management.",
    )
    governance_operating_mode = models.CharField(
        max_length=32,
        choices=_get_governance_operating_mode_choices,
        default="standalone",  # role-string-allow: default matches GovernanceOperatingMode.STANDALONE registry
        db_index=True,
        help_text="standalone | group_member | group_member_sovereign (default standalone).",
    )
    # Multi-level hierarchy: materialized path (e.g. "" or "uuid1" or "uuid1/uuid2") for recursive queries
    hierarchy_path = models.CharField(
        max_length=1024,  # magic-number-allow: charfield-max-length
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
    # Wave 6/10 (v3.62.10 — 2026-05-22): per-school primary language of
    # instruction. Drives the per-language education-system overlay (CM
    # Anglo/Franco, CA EN/Quebec-FR, BE NL/FR/DE, CH 4 lang, IN 11 lang, ZA
    # 5 lang) and the lexicon cascade. BCP-47 primary subtag form (en, fr,
    # zh-hans, etc.). Empty string = use country pack's default language.
    primary_language = models.CharField(
        max_length=16,
        blank=True,
        db_index=True,
        help_text=(
            "Primary language of instruction (BCP-47 primary subtag form: "
            "en/fr/zh-hans/ar/hi/ur/...). For multilingual countries this "
            "drives the per-language education-system overlay shown across "
            "the platform. Empty = use the country's default language."
        ),
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

    # v4.00.39 — Tier-C wedge per-tenant institution-type assignment.
    # Each tenant can flag which charter authorizer / IB+Cambridge
    # programmes / faith tradition applies. Drives Wedge 16/17/18 detail
    # pages + per-school reporting.
    charter_authorizer_code = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text=(
            "Wedge 16 (Charter): the authorizer code from "
            "apps.siteconfig._institution_types.CHARTER_AUTHORIZERS "
            "(e.g. 'us-soe', 'uk-academy-trust')."
        ),
    )
    ib_programmes = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Wedge 17 (International): list of IB / Cambridge programme "
            "codes this school is authorized for (e.g. ['pyp', 'myp', "
            "'dp', 'cam-igcse'])."
        ),
    )
    faith_tradition_code = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text=(
            "Wedge 18 (Faith-based): the tradition code from "
            "apps.siteconfig._institution_types.FAITH_TRADITIONS "
            "(e.g. 'catholic', 'islamic-sunni', 'interfaith')."
        ),
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "School"
        verbose_name_plural = "Schools"
        indexes = [
            # A3: the soft-delete + active filter is the hot path —
            # LiveSchoolManager scopes on deleted_at IS NULL and the many
            # is_active=True queries (group hierarchy, dashboards, listings).
            # A composite btree on (deleted_at, is_active) serves both.
            models.Index(
                fields=["deleted_at", "is_active"],
                name="schools_softdel_active_idx",
            ),
        ]

    # Wave L6 (v3.61.6 — 2026-05-22): opt-in soft-delete-aware manager.
    # Django only auto-creates ``objects`` when the model declares NO
    # custom managers; declaring ``live_objects`` alone made it the sole
    # default and broke ``School.objects`` site-wide. Keep explicit
    # ``objects`` first so legacy callers stay unchanged; new code that
    # should hide soft-deleted rows uses ``School.live_objects``.
    objects = SchoolQuerySet.as_manager()
    live_objects = LiveSchoolManager()

    def __str__(self):
        return self.name

    def delete(self, using=None, keep_parents=False):
        """Hard-delete, cascading over SHARED relations only.

        The stock implementation cannot run in ``public`` under
        schema-per-tenant: the collector walks 328 tenant tables that are not
        there and dies on the first one. Tenant rows are not orphaned by
        skipping them — they live in the tenant schema and go with it.

        A school that still owns a live tenant schema cannot be deleted at all
        (its rows hold real cross-schema foreign keys to this row); that raises
        ``TenantSchemaStillPresent`` naming the schema. Delete both together with
        ``apps.schools.deletion.delete_school(school, drop_schema=True)``.
        """
        from apps.schools.deletion import assert_deletable, delete_school_rows

        assert_deletable(self)

        deleted_count, by_label, _skipped = delete_school_rows([self], using=using)
        return deleted_count, by_label

    delete.alters_data = True

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError

        from apps.siteconfig.billing_sku_registry import REPORT_PLATFORM_SKU_BUNDLES

        # Reject a parent_school assignment that would create a cycle in the
        # group hierarchy. The detector existed in hierarchy_helpers but was
        # never wired into validation, so a cycle (A→B, B→A) could be saved
        # and then hang every ancestor-chain / hierarchy_path walk.
        if getattr(self, "parent_school_id", None):
            from apps.schools.hierarchy_helpers import hierarchy_link_would_cycle

            if hierarchy_link_would_cycle(self, self.parent_school_id):
                raise ValidationError(
                    {
                        "parent_school": (
                            "This parent assignment would create a cycle in the "
                            "school group hierarchy."
                        )
                    }
                )

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

    def resolve_currency(self) -> str:
        """Tenant currency, local-first: explicit override -> country pack -> region -> platform default.

        This is the canonical read path for "what currency does this school use" so no caller
        hardcodes a literal. Returns an upper-cased ISO 4217 code; never blank.
        """
        explicit = (getattr(self, "currency", "") or "").strip()
        if explicit:
            return explicit.upper()
        country_code = (getattr(self, "country_code", "") or "").strip()
        if country_code:
            try:
                from apps.siteconfig.global_catalog import GlobalGeoCatalog

                pack_currency = (
                    GlobalGeoCatalog.country_defaults(country_code).get("currency") or ""
                ).strip()
                if pack_currency:
                    return pack_currency.upper()
            except (ImportError, AttributeError, TypeError, ValueError, KeyError) as e:
                logger.debug("schools.School.resolve_currency country pack failed: %s", e)
        region = getattr(self, "default_region", None)
        if region is not None:
            region_currency = (getattr(region, "default_currency", "") or "").strip()
            if region_currency:
                return region_currency.upper()
        return _default_currency().upper()

    def save(self, *args, **kwargs):
        rp = (getattr(self, "report_platform_bundle_slug", None) or "").strip()
        self.report_platform_bundle_slug = rp.lower() if rp else ""
        # Keep the WAL tenant_hash in sync. id is a UUID set at instantiation
        # (default=uuid4), so it is available on first save before super().save().
        if self.id:
            self.tenant_hash = hashlib.sha256(
                str(self.id).encode("utf-8")
            ).hexdigest()[:12]
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
        # Capture prior country before persist for EAV reseed (Metric #5).
        _prev_country_code = ""
        if self.pk:
            _prev_country_code = (
                School.objects.filter(pk=self.pk)
                .values_list("country_code", flat=True)
                .first()
                or ""
            )
            _prev_country_code = str(_prev_country_code).strip().upper()
        # Local-first: a school created with a country but no region (admin / import
        # / API paths that skip the signup + provisioning flow) would otherwise fall
        # back to a generic pack. Link the matching RegionConfig when one already
        # exists — read-only (region creation stays in signup/provisioning), never
        # raises, only when default_region is unset (an explicit choice always wins),
        # and only when the field will actually persist (respects update_fields).
        if self.default_region_id is None and (self.country_code or "").strip():
            _update_fields = kwargs.get("update_fields")
            if _update_fields is None or "default_region" in _update_fields:
                try:
                    from apps.siteconfig.education_profile_engine import (
                        find_region_for_country,
                    )

                    _region = find_region_for_country(self.country_code)
                    if _region is not None:
                        self.default_region = _region
                except Exception:  # noqa: BLE001 — region linking must never break a save
                    logger.debug(
                        "schools.School.save default_region auto-link skipped",
                        exc_info=True,
                    )
        super().save(*args, **kwargs)
        # Metric #5: country change reseeds the identity EAV catalog (idempotent).
        _update_fields = kwargs.get("update_fields")
        if _update_fields is not None and "country_code" not in _update_fields:
            return
        new_cc = (self.country_code or "").strip().upper()
        if not new_cc or new_cc == _prev_country_code:
            return
        try:
            from apps.metadata.country_eav_catalog import seed_country_eav_definitions

            seed_country_eav_definitions(school=self, country_code=new_cc)
        except Exception:  # noqa: BLE001 — catalog reseed must never break a save
            logger.debug(
                "schools.School.save country EAV reseed skipped",
                exc_info=True,
            )

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
        ACADEMIC_STRUCTURE_READY = (
            "ACADEMIC_STRUCTURE_READY",
            "Academic Structure Ready",
        )
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
    is_school_owner = models.BooleanField(
        default=False,
        help_text=(
            "Per-school OWNER (the tenant's 'super admin'). The user who created "
            "the school is the owner by default; ownership is transferable and a "
            "school may have multiple owners. Distinct from is_primary (a per-user "
            "default-school pointer with no authority) and from User.role=SUPERADMIN "
            "(a control-plane/operator role that is redirected off tenant hosts). "
            "Owners are admin-like; granting ownership ensures the ADMIN role."
        ),
    )
    suspended_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "When set, this membership is suspended: the member keeps their row "
            "(so ownership/history is preserved and they can be reactivated) but "
            "loses management + ownership authority on this school and their active "
            "sessions are revoked. Reversible — clear it to reactivate."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_suspended(self) -> bool:
        """True when this membership is currently suspended (authority revoked)."""
        return self.suspended_at is not None

    class Meta:
        unique_together = [("user", "school")]
        ordering = ["-is_primary", "school__name"]
        verbose_name = "School membership"
        verbose_name_plural = "School memberships"
        indexes = [
            # Hot path for the ownership gate + last-owner guard: "owners of this school".
            models.Index(
                fields=["school", "is_school_owner"],
                name="schoolmember_owner_idx",
            ),
        ]

    def __str__(self):
        return f"{self.user.username} @ {self.school.name} ({self.role})"

    @staticmethod
    def owner_memberships(school):
        """Active owner memberships for a school (queryset)."""
        return SchoolMembership.objects.filter(school=school, is_school_owner=True)

    @staticmethod
    def is_owner(user, school) -> bool:
        """True if ``user`` is an owner of ``school`` (membership flag only)."""
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return SchoolMembership.objects.filter(
            school=school, user_id=getattr(user, "pk", None), is_school_owner=True
        ).exists()

    @staticmethod
    def is_active_owner(user, school) -> bool:
        """True if ``user`` is a NON-SUSPENDED owner of ``school``.

        Gate ownership-bearing actions on this, not ``is_owner``: a member
        suspended to revoke their authority must lose it everywhere (the Owner
        Console, the Identity hub, and the first-login card all agree). ``is_owner``
        remains the raw membership-flag check.
        """
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return SchoolMembership.objects.filter(
            school=school,
            user_id=getattr(user, "pk", None),
            is_school_owner=True,
            suspended_at__isnull=True,
        ).exists()


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


class TenantInvite(models.Model):
    """Operator-issued invitation for a NEW school to join the platform.

    Distinct from ``accounts.TenantStaffInvite`` (which invites STAFF to an
    EXISTING tenant). This invites a whole school: an operator sends it by
    email with optional prefill (school name / country); the recipient opens
    the accept link and is routed into the standard onboarding/signup workflow.
    The ``school`` FK is null until the invite is accepted and the tenant is
    created, at which point it's bound for audit.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    # Optional operator-supplied prefill carried into the onboarding form.
    school_name = models.CharField(max_length=255, blank=True, default="")
    country_code = models.CharField(max_length=2, blank=True, default="")
    note = models.CharField(max_length=500, blank=True, default="")
    invited_by = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenant_invites_sent",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    school = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenant_invites",
        help_text="Bound to the created school once the invite is accepted.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Tenant invite"
        verbose_name_plural = "Tenant invites"
        indexes = [
            models.Index(fields=["email", "accepted_at"]),
        ]

    def __str__(self):
        return f"invite:{self.email}"

    @property
    def status(self) -> str:
        from django.utils import timezone

        if self.accepted_at is not None:
            return "accepted"
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at and self.expires_at < timezone.now():
            return "expired"
        return "pending"

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"


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


class FundraisingCampaign(models.Model):
    """
    Wedge 5: a tenant-scoped fundraising campaign / appeal. Gifts and in-kind
    donations may FK to it; progress is aggregated from those (no stored running
    total). `is_public` controls visibility on the donor magic-link portal.
    """

    class Status(models.TextChoices):
        PLANNING = "planning", "Planning"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="fundraising_campaigns",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    goal_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    currency = models.CharField(max_length=3, blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PLANNING
    )
    is_public = models.BooleanField(
        default=False, help_text="Show this campaign on the donor portal."
    )
    award_source = models.ForeignKey(
        "finance.AwardSource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="fundraising_campaigns",
        help_text="Optional fund that gifts to this campaign credit by default.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Fundraising campaign"
        verbose_name_plural = "Fundraising campaigns"
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["school", "is_public"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"


class DonationPledge(models.Model):
    """
    Wedge 5: a promise to give later (distinct from AdvancementGift, which is a gift
    already received). Tracks due date, fulfillment (via linked gifts), reminder
    counters and aging. Tenant-scoped via school.
    """

    class Status(models.TextChoices):
        PLEDGED = "pledged", "Pledged"
        PARTIAL = "partial", "Partially fulfilled"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="donation_pledges",
    )
    donor = models.ForeignKey(
        "schools.AdvancementDonor",
        on_delete=models.CASCADE,
        related_name="pledges",
    )
    campaign = models.ForeignKey(
        "schools.FundraisingCampaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pledges",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, blank=True, default="")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PLEDGED
    )
    fulfilled_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    reminders_sent = models.PositiveIntegerField(default=0)
    last_reminder_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "-created_at"]
        verbose_name = "Donation pledge"
        verbose_name_plural = "Donation pledges"
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["school", "due_date"]),
        ]

    def __str__(self) -> str:
        return f"Pledge {self.amount} {self.currency} ({self.get_status_display()})"

    @property
    def outstanding_amount(self) -> Decimal:
        return max(Decimal("0.00"), self.amount - (self.fulfilled_amount or Decimal("0.00")))

    @property
    def is_open(self) -> bool:
        return self.status in (self.Status.PLEDGED, self.Status.PARTIAL)


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
    currency = models.CharField(max_length=3, blank=True, default="")
    received_at = models.DateField()
    receipt_sent = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    campaign_name = models.CharField(
        max_length=120,
        blank=True,
        help_text="Campaign or appeal label (e.g. Annual Fund 2026).",
    )
    campaign = models.ForeignKey(
        "schools.FundraisingCampaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gifts",
        help_text="Optional structured campaign this gift counts toward.",
    )
    award_source = models.ForeignKey(
        "finance.AwardSource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="advancement_gifts",
        help_text="Optional restricted/scholarship fund this gift credits.",
    )
    credited_to_fund_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set once this gift has been applied to its award_source fund (idempotency guard).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    client_offline_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text=(
            "Client-generated offline idempotency key; dedupes replayed offline "
            "donation captures so one captured gift can never credit a fund twice."
        ),
    )

    class Meta:
        ordering = ["-received_at", "-pk"]
        verbose_name = "Advancement gift"
        verbose_name_plural = "Advancement gifts"
        constraints = [
            models.UniqueConstraint(
                fields=["donor", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_advancementgift_donor_client_offline_id",
            ),
        ]


class InKindDonation(models.Model):
    """
    Wedge 5: a donated good/service recorded against a school. On acceptance it feeds
    the existing schoolops InventoryItem register rather than forking a new inventory
    engine. Tenant-scoped by school; donor optional (blank = anonymous).
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"

    class Category(models.TextChoices):
        BOOKS = "books", "Books / learning materials"
        EQUIPMENT = "equipment", "Equipment"
        FOOD = "food", "Food / supplies"
        UNIFORMS = "uniforms", "Uniforms"
        FURNITURE = "furniture", "Furniture"
        VEHICLE = "vehicle", "Vehicle"
        SERVICE = "service", "Service / volunteer time"
        OTHER = "other", "Other"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="in_kind_donations",
    )
    donor = models.ForeignKey(
        AdvancementDonor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="in_kind_donations",
        help_text="Optional; blank for anonymous in-kind gifts.",
    )
    campaign = models.ForeignKey(
        "schools.FundraisingCampaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="in_kind_donations",
        help_text="Optional structured campaign this donation counts toward.",
    )
    description = models.CharField(max_length=255)
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.OTHER
    )
    quantity = models.PositiveIntegerField(default=1)
    unit = models.CharField(
        max_length=40, blank=True, help_text="e.g. boxes, units, hours"
    )
    estimated_value = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=3, blank=True, default="")
    condition = models.CharField(
        max_length=40, blank=True, help_text="e.g. new, good, fair, poor"
    )
    received_at = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    acknowledgment_sent = models.BooleanField(default=False)
    inventory_item = models.ForeignKey(
        "schoolops.InventoryItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="in_kind_donations",
        help_text="Inventory line created/incremented when this donation is accepted.",
    )
    notes = models.TextField(blank=True)
    client_offline_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text=(
            "Client-generated offline idempotency key; dedupes replayed offline "
            "in-kind captures so one capture can never create two donation records."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_at", "-pk"]
        verbose_name = "In-kind donation"
        verbose_name_plural = "In-kind donations"
        indexes = [
            models.Index(fields=["school", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_inkinddonation_school_client_offline_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.description} x{self.quantity} ({self.get_status_display()})"


class DonorGiftAccessLink(models.Model):
    """
    Signed magic-link grant for a donor to view their own gifts/receipts/public
    campaigns WITHOUT a login account. Verified by random UUID token + expiry
    (mirrors SignupVerification). Tenant-scoped via the donor's school.
    """

    donor = models.ForeignKey(
        AdvancementDonor,
        on_delete=models.CASCADE,
        related_name="access_links",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    expires_at = models.DateTimeField()
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    access_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Donor gift access link"
        verbose_name_plural = "Donor gift access links"

    def __str__(self) -> str:
        return f"link for {self.donor_id} (exp {self.expires_at:%Y-%m-%d})"

    @property
    def is_valid(self) -> bool:
        from django.utils import timezone as _tz

        return self.expires_at > _tz.now()


class GrantApplication(models.Model):
    """
    Wedge 5: an outbound grant the school applies for, tracked through its full
    lifecycle — draft → submitted → under_review → awarded/declined → closed (with
    renewal via ``renewed_from``). On award it credits a finance ``AwardSource`` (the
    fund bucket) via ``aid_services.credit_award_source`` rather than forking a funding
    ledger. The narrative may be AI-drafted (``services.advancement_ai``). Tenant-scoped.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        AWARDED = "awarded", "Awarded"
        DECLINED = "declined", "Declined"
        CLOSED = "closed", "Closed"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="grant_applications"
    )
    funder_name = models.CharField(max_length=200)
    program = models.CharField(
        max_length=200, blank=True, help_text="Programme or purpose the grant funds."
    )
    requested_amount = models.DecimalField(max_digits=14, decimal_places=2)
    awarded_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=3, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    narrative = models.TextField(
        blank=True, help_text="Application narrative (may be AI-drafted, then edited)."
    )
    award_source = models.ForeignKey(
        "finance.AwardSource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="grant_applications",
        help_text="Fund credited when the grant is awarded.",
    )
    credited_to_fund_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Idempotency stamp: set once the award has credited its fund.",
    )
    renewed_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="renewals",
        help_text="Prior grant this application renews.",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(
        null=True, blank=True, help_text="Submission deadline."
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Grant application"
        verbose_name_plural = "Grant applications"
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["school", "due_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.funder_name} ({self.get_status_display()})"

    @property
    def is_open(self) -> bool:
        return self.status in (
            self.Status.DRAFT,
            self.Status.SUBMITTED,
            self.Status.UNDER_REVIEW,
        )


class GrantMilestone(models.Model):
    """A deliverable/checkpoint on an awarded grant (e.g. interim report due, build phase)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        WAIVED = "waived", "Waived"

    grant = models.ForeignKey(
        GrantApplication, on_delete=models.CASCADE, related_name="milestones"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "due_date", "id"]
        verbose_name = "Grant milestone"
        verbose_name_plural = "Grant milestones"

    def __str__(self) -> str:
        return f"{self.title} ({self.get_status_display()})"


class GrantReport(models.Model):
    """A narrative or financial report filed against an awarded grant."""

    class ReportType(models.TextChoices):
        NARRATIVE = "narrative", "Narrative"
        FINANCIAL = "financial", "Financial"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        ACCEPTED = "accepted", "Accepted"

    grant = models.ForeignKey(
        GrantApplication, on_delete=models.CASCADE, related_name="reports"
    )
    report_type = models.CharField(
        max_length=12, choices=ReportType.choices, default=ReportType.NARRATIVE
    )
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    content = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_end", "-created_at"]
        verbose_name = "Grant report"
        verbose_name_plural = "Grant reports"

    def __str__(self) -> str:
        return f"{self.get_report_type_display()} report ({self.get_status_display()})"


class RecurringDonationSchedule(models.Model):
    """
    Wedge 5: a donor's recurring giving commitment. The platform has NO card-on-file
    auto-charge, so this is a SCHEDULE that MINTS a ``DonationPledge`` on each due date
    (an expected gift the donor fulfils as usual) — never an automatic charge. A daily
    periodic job advances due schedules. Tenant-scoped.
    """

    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        ANNUAL = "annual", "Annual"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="recurring_donation_schedules",
    )
    donor = models.ForeignKey(
        "schools.AdvancementDonor",
        on_delete=models.CASCADE,
        related_name="recurring_schedules",
    )
    campaign = models.ForeignKey(
        "schools.FundraisingCampaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recurring_schedules",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, blank=True, default="")
    frequency = models.CharField(
        max_length=12, choices=Frequency.choices, default=Frequency.MONTHLY
    )
    start_date = models.DateField()
    end_date = models.DateField(
        null=True, blank=True, help_text="Optional; blank = ongoing."
    )
    next_run_date = models.DateField(help_text="Next date a pledge is minted.")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    pledges_created = models.PositiveIntegerField(default=0)
    last_run_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["next_run_date", "-created_at"]
        verbose_name = "Recurring donation schedule"
        verbose_name_plural = "Recurring donation schedules"
        indexes = [models.Index(fields=["school", "status", "next_run_date"])]

    def __str__(self) -> str:
        return (
            f"{self.amount} {self.currency} {self.get_frequency_display()} "
            f"({self.get_status_display()})"
        )


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


# ---------------------------------------------------------------------------
# Local-first currency default for school-scoped money rows
# ---------------------------------------------------------------------------
# These advancement/fundraising models used to hardcode ``default="USD"``. They
# now default blank and a single pre_save receiver fills the currency from the
# owning school's resolved (local-first) currency on create, so a school in
# Nigeria gets NGN, Cameroon XAF, etc. — never a hardcoded literal. Migration-
# invisible (signals are not part of model state). Guards on ``_state.adding``
# so it only acts on inserts and never overrides an explicitly-set currency.
def _fill_local_currency_pre_save(sender, instance, **kwargs):  # noqa: ARG001
    _apply_local_currency_default(instance)


for _local_currency_model in (
    FundraisingCampaign,
    DonationPledge,
    AdvancementGift,
    InKindDonation,
    GrantApplication,
    RecurringDonationSchedule,
):
    models.signals.pre_save.connect(
        _fill_local_currency_pre_save,
        sender=_local_currency_model,
        dispatch_uid=f"fill_local_currency_{_local_currency_model.__name__}",
    )
