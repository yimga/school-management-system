"""Fail-closed verification for the canonical platform + tenant seed contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedCheck:
    key: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class PlatformSeedAudit:
    checks: tuple[SeedCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def failures(self) -> tuple[SeedCheck, ...]:
        return tuple(check for check in self.checks if not check.ok)


def _manifest_check(key, queryset, field, expected) -> SeedCheck:
    expected_set = {str(value) for value in expected if str(value)}
    actual = {str(value) for value in queryset.values_list(field, flat=True)}
    missing = sorted(expected_set - actual)
    return SeedCheck(
        key,
        not missing,
        (
            f"{len(actual)} present; required manifest complete"
            if not missing
            else f"missing {len(missing)}: {missing[:12]}"
        ),
    )


def audit_platform_seed(*, only_tenant: str = "") -> PlatformSeedAudit:
    """Evaluate actual rows against seed manifests and active-tenant invariants."""
    from apps.academics.models import AcademicYear, Subject, Term
    from apps.accounts.models import AccessRole, Permission
    from apps.accounts.signals import ROLE_TEMPLATES
    from apps.billing.management.commands.seed_subscription_catalog import (
        ADDON_CATALOG,
        PLAN_CATALOG,
    )
    from apps.evals.models import AssessmentWeights
    from apps.marketplace.management.commands.seed_capability_registry import (
        DEFAULT_CAPABILITIES,
    )
    from apps.marketplace.management.commands.seed_marketplace_apps import (
        FIRST_PARTY_APPS,
    )
    from apps.marketplace.models import CapabilityRegistry, MarketplaceApp
    from apps.policies.management.commands.seed_blueprint_policy_packs import (
        BLUEPRINT_PACKS,
        EXTRA_BLUEPRINT_PACKS,
        REGIONAL_BLUEPRINT_PACKS,
    )
    from apps.policies.models import BlueprintPack
    from apps.registries.currency_seed import CURRENCIES_ISO4217
    from apps.registries.models import (
        CalendarSystemRegistry,
        CountryRegistry,
        CurrencyRegistry,
        DocumentTypeRegistry,
        EducationLevelRegistry,
        EducationSystemTypeRegistry,
        FeeCategoryRegistry,
        GradeScaleRegistry,
        InstitutionTypeRegistry,
        LocaleRegistry,
        TimeZoneRegistry,
    )
    from apps.registries.services import (
        CALENDAR_SYSTEM_SEED_DEFAULTS,
        DEFAULT_EDUCATION_LEVELS,
        DEFAULT_EDUCATION_SYSTEM_TYPES,
        GRADE_SCALE_SEED_DEFAULTS,
        INSTITUTION_TYPE_SEED_DEFAULTS,
        LOCALE_SEED_DEFAULTS,
    )
    from apps.schools.models import School
    from apps.siteconfig.dashboard_pack_catalog import DASHBOARD_PACKS
    from apps.siteconfig.management.commands.seed_admin_dashboard_palettes import (
        CURATED_CATALOG_SLUGS,
    )
    from apps.siteconfig.management.commands.seed_provider_registry import (
        PROVIDER_REGISTRY,
    )
    from apps.siteconfig.management.commands.seed_workflow_dashboard_packs import (
        WORKFLOW_PACKS,
    )
    from apps.siteconfig.models import Integration, ThemePack
    from apps.siteconfig.models_dashboard import DashboardPack
    from apps.siteconfig.models_platform_catalog import (
        EducationSystemProfile,
        Plan,
        PlanAddon,
        RegionConfig,
    )
    from apps.siteconfig.models_workflow import WorkflowPack

    checks: list[SeedCheck] = []
    active = {"is_active": True}
    checks.append(
        SeedCheck(
            "registry.countries",
            CountryRegistry.objects.filter(**active).count() >= 195,
            f"{CountryRegistry.objects.filter(**active).count()} active (minimum 195)",
        )
    )
    checks.extend(
        [
            _manifest_check(
                "registry.education_levels",
                EducationLevelRegistry.objects.filter(**active),
                "code",
                [row["code"] for row in DEFAULT_EDUCATION_LEVELS],
            ),
            _manifest_check(
                "registry.education_system_types",
                EducationSystemTypeRegistry.objects.filter(**active),
                "code",
                [row["code"] for row in DEFAULT_EDUCATION_SYSTEM_TYPES],
            ),
            _manifest_check(
                "registry.currencies",
                CurrencyRegistry.objects.filter(**active),
                "code",
                [row[0] for row in CURRENCIES_ISO4217],
            ),
            _manifest_check(
                "registry.locales",
                LocaleRegistry.objects.filter(**active),
                "code",
                [row["code"] for row in LOCALE_SEED_DEFAULTS],
            ),
            _manifest_check(
                "registry.institution_types",
                InstitutionTypeRegistry.objects.filter(**active),
                "code",
                [row["code"] for row in INSTITUTION_TYPE_SEED_DEFAULTS],
            ),
            _manifest_check(
                "registry.calendar_systems",
                CalendarSystemRegistry.objects.filter(**active),
                "code",
                [row["code"] for row in CALENDAR_SYSTEM_SEED_DEFAULTS],
            ),
            _manifest_check(
                "registry.grade_scales",
                GradeScaleRegistry.objects.filter(**active),
                "code",
                [row["code"] for row in GRADE_SCALE_SEED_DEFAULTS],
            ),
        ]
    )
    checks.extend(
        [
            SeedCheck(
                "registry.timezones",
                TimeZoneRegistry.objects.filter(**active).count() >= 400,
                f"{TimeZoneRegistry.objects.filter(**active).count()} active (minimum 400)",
            ),
            SeedCheck(
                "registry.documents",
                DocumentTypeRegistry.objects.filter(**active).count() >= 9,
                f"{DocumentTypeRegistry.objects.filter(**active).count()} active (minimum 9)",
            ),
            SeedCheck(
                "registry.fee_categories",
                FeeCategoryRegistry.objects.filter(**active).count() >= 8,
                f"{FeeCategoryRegistry.objects.filter(**active).count()} active (minimum 8)",
            ),
        ]
    )

    region_codes = set(
        RegionConfig.objects.exclude(code="GLOBAL").values_list("code", flat=True)
    )
    approved_region_codes = set(
        EducationSystemProfile.objects.filter(
            is_active=True,
            approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
        ).values_list("region_id", flat=True)
    )
    from apps.siteconfig.country_grading_seed import COUNTRY_GRADING_SEED_ROWS
    from apps.siteconfig.models import CountryGradingProfile

    expected_country_grading = {
        row["country_code"].strip().upper() for row in COUNTRY_GRADING_SEED_ROWS
    }
    actual_country_grading = set(
        CountryGradingProfile.objects.filter(is_active=True).values_list(
            "country_code", flat=True
        )
    )
    missing_profiles = sorted(region_codes - approved_region_codes)
    regions_without_default_grading = sorted(
        RegionConfig.objects.exclude(code="GLOBAL")
        .filter(grading_scale="")
        .values_list("code", flat=True)
    )
    missing_grading = sorted(expected_country_grading - actual_country_grading)
    checks.extend(
        [
            SeedCheck(
                "catalog.education_profiles",
                bool(region_codes) and not missing_profiles,
                (
                    f"approved profiles cover all {len(region_codes)} regions"
                    if region_codes and not missing_profiles
                    else f"regions without approved profiles: {missing_profiles[:12]}"
                ),
            ),
            SeedCheck(
                "catalog.regional_grading",
                bool(region_codes)
                and not regions_without_default_grading
                and not missing_grading,
                (
                    f"all {len(region_codes)} regions have defaults; "
                    f"{len(expected_country_grading)} curated country profiles present"
                    if region_codes
                    and not regions_without_default_grading
                    and not missing_grading
                    else (
                        "missing region defaults="
                        f"{regions_without_default_grading[:12]}; "
                        f"missing country profiles={missing_grading[:12]}"
                    )
                ),
            ),
        ]
    )

    checks.extend(
        [
            _manifest_check(
                "catalog.access_roles",
                AccessRole.objects.filter(school__isnull=True),
                "code",
                sorted(
                    {
                        code
                        for role_codes in ROLE_TEMPLATES.values()
                        for code in role_codes
                    }
                ),
            ),
            SeedCheck(
                "catalog.permissions",
                Permission.objects.count() >= 40,
                f"{Permission.objects.count()} permission codes (minimum 40)",
            ),
            SeedCheck(
                "catalog.superadmin_permissions",
                not (
                    set(Permission.objects.values_list("id", flat=True))
                    - set(
                        AccessRole.objects.filter(
                            school__isnull=True, code="SUPERADMIN"
                        ).values_list("permissions__id", flat=True)
                    )
                ),
                "global SUPERADMIN holds every seeded permission",
            ),
            _manifest_check(
                "catalog.plans",
                Plan.objects.filter(**active),
                "slug",
                [row["slug"] for row in PLAN_CATALOG],
            ),
            _manifest_check(
                "catalog.plan_addons",
                PlanAddon.objects.filter(**active),
                "code",
                [row[0] for row in ADDON_CATALOG],
            ),
            SeedCheck(
                "catalog.default_plan",
                Plan.objects.filter(is_active=True, is_default=True).count() == 1,
                f"{Plan.objects.filter(is_active=True, is_default=True).count()} active defaults (expected 1)",
            ),
            _manifest_check(
                "catalog.blueprints",
                BlueprintPack.objects.filter(**active),
                "slug",
                [
                    row["slug"]
                    for row in [
                        *BLUEPRINT_PACKS,
                        *REGIONAL_BLUEPRINT_PACKS,
                        *EXTRA_BLUEPRINT_PACKS,
                    ]
                ],
            ),
            _manifest_check(
                "catalog.workflow_packs",
                WorkflowPack.objects.filter(**active),
                "code",
                [row["code"] for row in WORKFLOW_PACKS],
            ),
            _manifest_check(
                "catalog.dashboard_packs",
                DashboardPack.objects.filter(**active),
                "code",
                [row["code"] for row in DASHBOARD_PACKS],
            ),
            _manifest_check(
                "catalog.capabilities",
                CapabilityRegistry.objects.filter(**active),
                "code",
                [row[1] for row in DEFAULT_CAPABILITIES],
            ),
            _manifest_check(
                "catalog.marketplace_apps",
                MarketplaceApp.objects.filter(**active),
                "slug",
                [row["slug"] for row in FIRST_PARTY_APPS],
            ),
            _manifest_check(
                "catalog.admin_palettes",
                ThemePack.objects.all(),
                "slug",
                CURATED_CATALOG_SLUGS,
            ),
            _manifest_check(
                "catalog.provider_registry",
                Integration.objects.filter(school__isnull=True),
                "slug",
                [row["slug"] for row in PROVIDER_REGISTRY],
            ),
        ]
    )

    schools = School.objects.filter(is_active=True).order_by("slug")
    if only_tenant:
        schools = schools.filter(slug=only_tenant)
    school_rows = list(schools)
    if only_tenant and not school_rows:
        checks.append(
            SeedCheck("tenant.selection", False, f"active school not found: {only_tenant}")
        )
    for school in school_rows:
        prefix = f"tenant.{school.slug}"
        profile_code = str((school.settings or {}).get("education_profile_code") or "")
        profile_ok = bool(
            profile_code
            and EducationSystemProfile.objects.filter(
                code=profile_code,
                is_active=True,
                approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
            ).exists()
        )
        year = (
            AcademicYear.objects.filter(school=school, is_active=True).first()
            or AcademicYear.objects.filter(school=school).order_by("-start_date").first()
        )
        tenant_contract = {
            "geo": bool(
                school.default_region_id
                and str(school.country_code or "").strip()
                and str(school.timezone or "").strip()
                and str(school.currency or "").strip()
                and str(school.default_language or "").strip()
            ),
            "education_system_types": school.education_system_types.filter(
                is_active=True
            ).exists(),
            "education_levels": school.education_levels.filter(is_active=True).exists(),
            "education_profile": profile_ok,
            "plan": bool(school.plan_id and getattr(school.plan, "is_active", False)),
            "academic_year": year is not None,
            "terms": bool(year and Term.objects.filter(school=school, academic_year=year).exists()),
            "subjects": Subject.objects.filter(school=school).exists(),
            "grading": bool(
                year
                and AssessmentWeights.objects.filter(school=school, academic_year=year).exists()
            ),
        }
        failed = sorted(key for key, value in tenant_contract.items() if not value)
        checks.append(
            SeedCheck(
                prefix,
                not failed,
                "complete" if not failed else f"missing: {failed}",
            )
        )

    return PlatformSeedAudit(tuple(checks))


__all__ = ["PlatformSeedAudit", "SeedCheck", "audit_platform_seed"]
