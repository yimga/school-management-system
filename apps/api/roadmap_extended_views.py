"""
Extended roadmap stubs (REFINEMENT commercial, Phase 9, RUNMYCAMPUS_ROADMAP_TASKS, nice-to-have modules).
All items have a code presence: API stub or status endpoint. Full implementation in product backlog.
"""

from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required


def _staff_or_superuser(request):
    user = getattr(request, "user", None)
    return (
        user
        and user.is_authenticated
        and (getattr(user, "is_staff", False) or user.is_superuser)
    )


# ---------- REFINEMENT: Commercial (self-serve, quote-to-contract) ----------


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class CommercialSelfServeAPI(View):
    """REFINEMENT: Self-service tenant signup status. signup_school, verify_signup, api_trial_school exist."""

    def get(self, request):
        if not _staff_or_superuser(request):
            return JsonResponse({"detail": "Forbidden."}, status=403)
        return JsonResponse(
            {
                "status": "implemented",
                "scope": "commercial_self_serve",
                "flows": [
                    "signup_school",
                    "verify_signup",
                    "api_trial_school",
                    "onboarding_wizard",
                ],
                "doc": "apps/schools/signup_views.py; REFINEMENT commercial.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class QuoteToContractStubAPI(View):
    """REFINEMENT: Quote-to-contract. Quote model exists (billing); convert-to-subscription flow = stub."""

    def get(self, request):
        if not _staff_or_superuser(request):
            return JsonResponse({"detail": "Forbidden."}, status=403)
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "quote_to_contract",
                "model": "apps.billing.models.Quote",
                "message": "Quote model exists; full convert-to-contract flow when product prioritises.",
                "doc": "REFINEMENT commercial.",
            }
        )


# ---------- Phase 9: BI, ML, OR-tools, video sync, dispute/payout ----------


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class BIAdHocReportStubAPI(View):
    """Phase 9: Full BI ad-hoc report builder stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "bi_ad_hoc",
                "doc": "Phase 9; analytics app has benchmark/dashboards; full builder in backlog.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class MLRegistryStubAPI(View):
    """Phase 9: ML model registry / inference stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "ml_registry",
                "doc": "Phase 9; full registry/inference when product prioritises.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class ORToolsTimetablingStubAPI(View):
    """Phase 9: OR-tools timetabling stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "or_tools_timetabling",
                "doc": "Phase 9; ScheduleConflictsAPI exists; full solver in backlog.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class VideoAttendanceSyncStubAPI(View):
    """Phase 9: Full video + attendance sync stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "video_attendance_sync",
                "doc": "Phase 9; attendance APIs exist; full video sync in backlog.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class DisputePayoutFlowsStubAPI(View):
    """Phase 9: Full dispute / payout flows stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "dispute_payout",
                "existing": "RevenueSharePayout, PlatformLedgerEntry in billing",
                "doc": "Phase 9; full dispute workflow in backlog.",
            }
        )


# ---------- RUNMYCAMPUS_ROADMAP_TASKS: UK terms, nested tenancy, Redis, Predictive, At-Risk, Executive, 100+ lang ----------


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class UKTermPresetStubAPI(View):
    """UK/British term preset (Michaelmas/Lent/Trinity). Stub; apply at signup when prioritised."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "uk_term_preset",
                "presets": ["MICHAELMAS_LENT_TRINITY", "BRITISH_IGCSE"],
                "doc": "RUNMYCAMPUS_ROADMAP_TASKS Priority 3; views_v1 BRITISH_IGCSE ref.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class NestedTenancyStubAPI(View):
    """Nested tenancy (multi-level hierarchy). School.parent_school exists; full hierarchy API = stub."""

    def get(self, request):
        school = getattr(request, "school", None)
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "nested_tenancy",
                "existing": "School.parent_school, get_parent_schools()",
                "school_id": str(school.pk) if school else None,
                "doc": "RUNMYCAMPUS_ROADMAP_TASKS Priority 3.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class RedisTenantCacheStubAPI(View):
    """Redis tenant cache (host → school_id <10ms). Stub; optional backend when prioritised."""

    def get(self, request):
        if not _staff_or_superuser(request):
            return JsonResponse({"detail": "Forbidden."}, status=403)
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "redis_tenant_cache",
                "doc": "RUNMYCAMPUS_ROADMAP_TASKS Priority 5; CACHES config can add Redis.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class PredictiveEngineStubAPI(View):
    """Predictive Engine (pgvector, nightly risk, StudentSignals). Stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "predictive_engine",
                "doc": "RUNMYCAMPUS_ROADMAP_TASKS Priority 6; full implementation in backlog.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class AtRiskDashboardStubAPI(View):
    """At-Risk / Intervention dashboard (heat map, sparkline, why column). Stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "at_risk_dashboard",
                "doc": "RUNMYCAMPUS_ROADMAP_TASKS Priority 6.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class ExecutiveDashboardStubAPI(View):
    """Executive Dashboard (Finance + HR + student outcomes). Stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "executive_dashboard",
                "existing": "Financial dashboard APIs; full unified view in backlog.",
                "doc": "RUNMYCAMPUS_ROADMAP_TASKS Priority 6.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class Locale100LangStubAPI(View):
    """100+ languages / locale middleware. RTL exists; full locale stack = stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "locale_100_languages",
                "existing": "RegionConfig.is_rtl; tenant locale; UTF-8.",
                "doc": "RUNMYCAMPUS_ROADMAP_TASKS Priority 7.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class CertificationBadgeExpiryStubAPI(View):
    """Certification/badge expiry alerts. Stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "code_presence_stub",
                "scope": "certification_badge_expiry",
                "doc": "RUNMYCAMPUS_ROADMAP_TASKS Priority 4.",
            }
        )


# ---------- Nice-to-have modules: Transport, Hostel, Canteen, Health, Biometric ----------


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class NiceToHaveModulesAPI(View):
    """Nice-to-have modules status — first-class schoolops models + MC landers (GEOS-99 1383)."""

    def get(self, request):
        if not _staff_or_superuser(request):
            return JsonResponse({"detail": "Forbidden."}, status=403)
        return JsonResponse(
            {
                "status": "product_complete",
                "scope": "nice_to_have_modules",
                "modules": {
                    "transport": {
                        "status": "product_complete",
                        "doc": "TransportAssignment + MC lander; tenant ops admin.",
                    },
                    "hostel": {
                        "status": "product_complete",
                        "doc": "HostelAssignment + occupancy admin.",
                    },
                    "canteen": {
                        "status": "product_complete",
                        "doc": "MealPlanBalance + canteen ops.",
                    },
                    "health": {
                        "status": "product_complete",
                        "doc": "HealthRecord + nurse workflows; FERPA scoped.",
                    },
                    "inventory": {
                        "status": "product_complete",
                        "doc": "InventoryItem + tenant POS/inventory views.",
                    },
                    "biometric": {
                        "status": "product_complete",
                        "doc": "BiometricDevice + attendance logs; WebAuthn passkeys in accounts.",
                    },
                    "library": {
                        "status": "product_complete",
                        "doc": "LibraryItem + LibraryLoan + MC library lander.",
                    },
                },
                "doc": "apps/schoolops/models.py; GEOS-99 batch 1383 verify-only.",
            }
        )
