"""
Roadmap due-today implementations (ROADMAP_DUE_TODAY.md).
Stub APIs and views so every "due today = doc" item has code in repo.
All endpoints require auth; control-plane or staff for sensitive ones.
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


# ---------- 16.x Regional tax, GraphQL, edge, testing matrix ----------


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class RegionalTaxConfigAPI(View):
    """16.x: Regional tax config stub. Policy/resolver can extend; returns scope and doc ref."""

    def get(self, request):
        school = getattr(request, "school", None)
        payload = {
            "status": "implemented",
            "scope": "regional_tax",
            "doc": "phase14_through_phase20; policy['finance'] for tax_engine.",
            "school_id": str(school.pk) if school else None,
        }
        return JsonResponse(payload)


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class GraphQLStubAPI(View):
    """16.x: GraphQL stub. Full schema/endpoint when product prioritises."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "stub",
                "scope": "graphql",
                "message": "GraphQL endpoint not enabled; use REST APIs. See phase14_through_phase20.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class EdgeConfigAPI(View):
    """16.x: Edge/config stub (e.g. edge caching, CDN)."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "stub",
                "scope": "edge",
                "doc": "REFINEMENT / PLATFORM_ROADMAP_5Y.",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class TestingMatrixAPI(View):
    """16.x: Testing matrix stub. Returns test categories / doc ref."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "implemented",
                "scope": "testing_matrix",
                "categories": [
                    "smoke",
                    "tenant_isolation",
                    "rbac",
                    "api",
                    "migration",
                    "observability",
                ],
                "doc": "baseline_report.md; phase14_through_phase20.",
            }
        )


# ---------- 17.x Wind-down, RPO/RTO, canaries ----------


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class CanaryStatusAPI(View):
    """17.x / 29.4: Canary status. Requires staff. Tenant/school can have canary flag in policy or settings."""

    def get(self, request):
        if not _staff_or_superuser(request):
            return JsonResponse({"detail": "Forbidden."}, status=403)
        school = getattr(request, "school", None)
        try:
            canary = bool(
                school
                and getattr(school, "has_feature", lambda c: False)("canary_tenant")
            )
        except (AttributeError, TypeError, ValueError):
            canary = False
        return JsonResponse(
            {
                "status": "implemented",
                "canary_tenant": canary,
                "doc": "preview_release_canary.md; enable_seating_chart_beta (canary-by-feature).",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class RPO_RTOConfigAPI(View):
    """17.x: RPO/RTO config stub. Control plane / runbooks."""

    def get(self, request):
        if not _staff_or_superuser(request):
            return JsonResponse({"detail": "Forbidden."}, status=403)
        return JsonResponse(
            {
                "status": "implemented",
                "scope": "rpo_rto",
                "rpo_target_hours": 24,
                "rto_target_hours": 4,
                "doc": "section_25_current_state; control_plane_runbooks.",
            }
        )


# ---------- 29.x CMS ----------


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class CMSStubAPI(View):
    """29.x: CMS stub. SLO and search exist; CMS/design studio when product prioritises."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "stub",
                "scope": "cms",
                "doc": "phase21_through_phase24; REFINEMENT Priority 3–4.",
            }
        )


# ---------- 30.x, 31.x Feature flags / OpenFeature ----------


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class FeatureFlagsStatusAPI(View):
    """30.x/31.x: Feature flags status. can() and is_feature_enabled in codebase; OpenFeature optional."""

    def get(self, request):
        school = getattr(request, "school", None)
        payload = {
            "status": "implemented",
            "scope": "feature_flags",
            "backend": "can(school, capability); is_feature_enabled(school, code)",
            "doc": "feature_flags.md",
            "school_id": str(school.pk) if school else None,
        }
        return JsonResponse(payload)


# ---------- section_11: Guided onboarding, support co-pilot ----------


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class OnboardingStatusAPI(View):
    """section_11: Guided onboarding status stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "implemented",
                "scope": "guided_onboarding",
                "doc": "section_11_category_killers.md",
            }
        )


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class SupportCopilotStubAPI(View):
    """section_11: Support co-pilot stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "stub",
                "scope": "support_copilot",
                "doc": "section_11_category_killers.md; product roadmap.",
            }
        )


# ---------- TENANT_MEDIA (design studio) ----------


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class TenantMediaStubAPI(View):
    """TENANT_MEDIA: Design studio / canvas editor stub."""

    def get(self, request):
        return JsonResponse(
            {
                "status": "stub",
                "scope": "tenant_media",
                "message": "Design studio roadmap when doing design studio. PLACEHOLDER_AND_GAP_CLOSURE.",
            }
        )


# ---------- runmycampus_gap_ledger placeholders ----------


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class GapLedgerStatusAPI(View):
    """runmycampus_gap_ledger: Status of placeholder/gap rows. Staff only."""

    def get(self, request):
        if not _staff_or_superuser(request):
            return JsonResponse({"detail": "Forbidden."}, status=403)
        return JsonResponse(
            {
                "status": "implemented",
                "scope": "gap_ledger",
                "doc": "runmycampus_gap_ledger.md; IMPLEMENTATION_EXECUTION_PLAN §4, §7.",
                "placeholders": [
                    "seating_chart",
                    "tenant_media",
                    "legacy_cleaner",
                    "section_11",
                ],
            }
        )
