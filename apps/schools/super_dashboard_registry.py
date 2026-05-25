"""
Server-side school registry for the control-plane dashboard.

Scales to large fleets: paginated queryset, DB-backed fleet metrics, and per-page
enrichment only (no loading 10k+ schools into one HTML response).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.http import HttpRequest

from apps.billing.models import TenantSubscription
from apps.brand_experience.models import BrandProfile
from apps.registries.models import CountryRegistry

from .models import School, SchoolProvisioningEvent
from .super_views_dashboard_helpers import (
    brand_profile_for_school,
    education_level_label,
    education_system_type_label,
    selected_system_names,
    status_tone,
)
from .super_views_helpers import safe_school_timeline_url


REGISTRY_PAGE_SIZE_DEFAULT = 25
REGISTRY_PAGE_SIZE_OPTIONS = (25, 50, 100)
REGISTRY_STATE_CHOICES = ("all", "attention", "pending", "inactive", "healthy")


@dataclass(frozen=True)
class FleetRegistryMetrics:
    school_count: int
    active_school_count: int
    identity_complete_count: int
    brand_profile_count: int
    custom_domain_count: int
    verified_domain_count: int
    impersonation_ready_count: int
    attention_school_count: int
    countries_live_count: int


def _latest_event_subquery():
    return SchoolProvisioningEvent.objects.filter(school_id=OuterRef("pk")).order_by(
        "-created_at", "-id"
    )


def _latest_subscription_subquery():
    return TenantSubscription.objects.filter(school_id=OuterRef("pk")).order_by(
        "-updated_at", "-created_at"
    )


def build_registry_queryset():
    """Annotated queryset shared by paginated registry and fleet metrics."""
    latest_event = _latest_event_subquery()
    latest_sub = _latest_subscription_subquery()
    level_through = School.education_levels.through
    system_through = School.education_system_types.through

    return (
        School.objects.all()
        .select_related("subdivision", "default_region")
        .prefetch_related(
            "tenant_systems__system", "education_levels", "education_system_types"
        )
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
        .annotate(teacher_count=Count("teacher_profiles", distinct=True))
        .annotate(latest_event_type=Subquery(latest_event.values("event_type")[:1]))
        .annotate(latest_event_status=Subquery(latest_event.values("status")[:1]))
        .annotate(
            latest_event_created_at=Subquery(latest_event.values("created_at")[:1])
        )
        .annotate(
            latest_subscription_status=Subquery(latest_sub.values("status")[:1])
        )
        .annotate(
            latest_subscription_amount=Subquery(latest_sub.values("billed_amount")[:1])
        )
        .annotate(
            latest_subscription_period_end=Subquery(
                latest_sub.values("current_period_end")[:1]
            )
        )
        .annotate(
            _has_education_levels=Exists(
                level_through.objects.filter(school_id=OuterRef("pk"))
            ),
            _has_education_system_types=Exists(
                system_through.objects.filter(school_id=OuterRef("pk"))
            ),
        )
    )


def compute_fleet_registry_metrics(
    *,
    incident_school_ids: set[Any],
    churn_risk_school_ids: set[Any],
) -> FleetRegistryMetrics:
    """Aggregate fleet posture without materializing every school row."""
    base = School.objects.all()
    school_count = base.count()
    active_school_count = base.filter(is_active=True).count()

    has_country = Q(country_code__gt="") | Q(default_region_id__isnull=False)
    identity_complete_count = (
        build_registry_queryset()
        .filter(has_country)
        .filter(_has_education_levels=True, _has_education_system_types=True)
        .count()
    )

    brand_profile_count = BrandProfile.objects.values("school_id").distinct().count()
    custom_domain_count = base.exclude(custom_domain="").count()
    verified_domain_count = base.filter(custom_domain_verified=True).count()
    impersonation_ready_count = base.filter(
        impersonation_consent_granted_at__isnull=False
    ).count()

    has_country = Q(country_code__gt="") | Q(default_region_id__isnull=False)
    identity_incomplete = (
        ~has_country
        | ~Q(_has_education_levels=True)
        | ~Q(_has_education_system_types=True)
    )
    attention_q = (
        Q(is_approved=False)
        | Q(latest_subscription_status__in=[
            TenantSubscription.Status.PAST_DUE,
            TenantSubscription.Status.SUSPENDED,
        ])
        | Q(latest_event_status=SchoolProvisioningEvent.Status.ERROR)
        | identity_incomplete
    )
    if incident_school_ids or churn_risk_school_ids:
        attention_q |= Q(pk__in=incident_school_ids | churn_risk_school_ids)

    attention_school_count = (
        build_registry_queryset().filter(attention_q).distinct().count()
    )

    countries_live_count = (
        base.exclude(country_code="")
        .values("country_code")
        .distinct()
        .count()
    )

    return FleetRegistryMetrics(
        school_count=school_count,
        active_school_count=active_school_count,
        identity_complete_count=identity_complete_count,
        brand_profile_count=brand_profile_count,
        custom_domain_count=custom_domain_count,
        verified_domain_count=verified_domain_count,
        impersonation_ready_count=impersonation_ready_count,
        attention_school_count=attention_school_count,
        countries_live_count=countries_live_count,
    )


def parse_registry_page_size(request: HttpRequest) -> int:
    raw = str(
        request.GET.get("page_size", REGISTRY_PAGE_SIZE_DEFAULT)
    ).strip()
    try:
        size = int(raw)
    except ValueError:
        size = REGISTRY_PAGE_SIZE_DEFAULT
    if size not in REGISTRY_PAGE_SIZE_OPTIONS:
        return REGISTRY_PAGE_SIZE_DEFAULT
    return size


def registry_pagination_extra_query(request: HttpRequest) -> str:
    """Preserve registry filters and month selector when paging."""
    q = request.GET.copy()
    for key in ("registry_page", "page"):
        q.pop(key, None)
    return q.urlencode()


def apply_registry_filters(
    queryset,
    *,
    search: str,
    state: str,
    incident_school_ids: set[Any],
    churn_risk_school_ids: set[Any],
):
    search = (search or "").strip()
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(slug__icontains=search)
            | Q(subdomain__icontains=search)
            | Q(country_code__icontains=search)
        )

    state = (state or "all").lower()
    if state not in REGISTRY_STATE_CHOICES:
        state = "all"

    if state == "inactive":
        return queryset.filter(is_active=False)
    if state == "pending":
        return queryset.filter(is_approved=False)
    if state == "healthy":
        return queryset.filter(
            is_active=True,
            is_approved=True,
        ).exclude(
            Q(latest_subscription_status__in=[
                TenantSubscription.Status.PAST_DUE,
                TenantSubscription.Status.SUSPENDED,
            ])
            | Q(latest_event_status=SchoolProvisioningEvent.Status.ERROR)
            | Q(pk__in=incident_school_ids | churn_risk_school_ids)
        ).filter(
            Q(country_code__gt="") | Q(default_region_id__isnull=False),
            _has_education_levels=True,
            _has_education_system_types=True,
        )
    if state == "attention":
        has_country = Q(country_code__gt="") | Q(default_region_id__isnull=False)
        identity_incomplete = (
            ~has_country
            | ~Q(_has_education_levels=True)
            | ~Q(_has_education_system_types=True)
        )
        attention_q = (
            Q(is_approved=False)
            | Q(latest_subscription_status__in=[
                TenantSubscription.Status.PAST_DUE,
                TenantSubscription.Status.SUSPENDED,
            ])
            | Q(latest_event_status=SchoolProvisioningEvent.Status.ERROR)
            | identity_incomplete
        )
        if incident_school_ids or churn_risk_school_ids:
            attention_q |= Q(pk__in=incident_school_ids | churn_risk_school_ids)
        return queryset.filter(attention_q).distinct()

    return queryset


def enrich_school_for_registry(
    school,
    *,
    country_names: dict[str, str],
    brand_profile_ids: set[Any],
    incident_school_ids: set[Any],
    churn_risk_lookup: dict[str, dict],
) -> None:
    """Attach display fields used by super_dashboard.html (mutates school in place)."""
    from django.urls import reverse

    from apps.billing.models import TenantSubscription

    school.timeline_url = safe_school_timeline_url(school.pk)
    school.sync_repair_url = reverse("super:sync_repair", args=[school.pk])
    school.selected_systems = selected_system_names(school)
    school.country_display = country_names.get(
        school.canonical_country_code, school.canonical_country_code or "Unassigned"
    )
    school.subdivision_display = (
        school.subdivision.name if school.subdivision_id else "-"
    )
    school.education_level_labels = [
        education_level_label(level, school.canonical_country_code)
        for level in school.education_levels.all()
    ]
    school.education_system_type_labels = [
        education_system_type_label(system_type, school.canonical_country_code)
        for system_type in school.education_system_types.all()
    ]
    school.has_brand_profile = (
        school.id in brand_profile_ids
        or brand_profile_for_school(school) is not None
    )
    school.brand_status = (
        "BrandProfile" if school.has_brand_profile else "Legacy fallback"
    )
    school.subscription_status = (
        school.latest_subscription_status or "UNSEEDED"
    ).upper()
    school.subscription_tone = status_tone(school.subscription_status)
    school.identity_status = "missing"
    if (
        school.canonical_country_code
        or school.education_level_labels
        or school.education_system_type_labels
    ):
        school.identity_status = "partial"
    if (
        school.canonical_country_code
        and school.education_level_labels
        and school.education_system_type_labels
    ):
        school.identity_status = "complete"
    school.identity_tone = status_tone(
        "success" if school.identity_status == "complete" else "warning"
    )
    school.attention_reasons = []
    if not school.is_approved:
        school.attention_reasons.append("Pending approval")
    if (
        getattr(school, "latest_event_status", "")
        == SchoolProvisioningEvent.Status.ERROR
    ):
        school.attention_reasons.append("Provisioning error")
    if school.subscription_status in {
        TenantSubscription.Status.PAST_DUE,
        TenantSubscription.Status.SUSPENDED,
    }:
        school.attention_reasons.append(
            f"Billing {school.subscription_status.lower().replace('_', ' ')}"
        )
    risk_row = churn_risk_lookup.get(str(school.pk))
    if risk_row and risk_row.get("reasons"):
        school.attention_reasons.append(risk_row["reasons"][0])
    if school.pk in incident_school_ids:
        school.attention_reasons.append("Open platform incident")
    if school.identity_status != "complete":
        school.attention_reasons.append("Canonical identity incomplete")
    school.attention_reasons = school.attention_reasons[:4]
    school.roster_state = "healthy"
    if not school.is_active:
        school.roster_state = "inactive"
    elif not school.is_approved:
        school.roster_state = "pending"
    elif school.attention_reasons:
        school.roster_state = "attention"
    school.roster_search = " ".join(
        filter(
            None,
            [
                school.name,
                school.slug,
                school.subdomain,
                school.country_display,
                school.subdivision_display,
                " ".join(school.education_level_labels),
                " ".join(school.education_system_type_labels),
                " ".join(school.selected_systems),
                " ".join(school.attention_reasons),
                school.subscription_status,
            ],
        )
    ).lower()


def paginate_registry(
    request: HttpRequest,
    *,
    incident_school_ids: set[Any],
    churn_risk_school_ids: set[Any],
    churn_risk_lookup: dict[str, dict],
    country_names: dict[str, str],
    brand_profile_ids: set[Any],
):
    """Return (page, search, state, page_size, extra_query)."""
    page_size = parse_registry_page_size(request)
    search = str(request.GET.get("registry_q", "")).strip()
    state = str(request.GET.get("registry_state", "all")).strip().lower()

    qs = build_registry_queryset()
    qs = apply_registry_filters(
        qs,
        search=search,
        state=state,
        incident_school_ids=incident_school_ids,
        churn_risk_school_ids=churn_risk_school_ids,
    )
    qs = qs.order_by("-is_active", "-is_approved", "name")

    paginator = Paginator(qs, page_size)
    page_number = request.GET.get("page", 1)
    page = paginator.get_page(page_number)

    for school in page.object_list:
        enrich_school_for_registry(
            school,
            country_names=country_names,
            brand_profile_ids=brand_profile_ids,
            incident_school_ids=incident_school_ids,
            churn_risk_lookup=churn_risk_lookup,
        )

    return (
        page,
        search,
        state,
        page_size,
        registry_pagination_extra_query(request),
    )


def load_country_names() -> dict[str, str]:
    return {
        code: name
        for code, name in CountryRegistry.objects.filter(is_active=True).values_list(
            "code", "name"
        )
    }


def load_brand_profile_ids() -> set[Any]:
    return set(BrandProfile.objects.values_list("school_id", flat=True))


def apply_operator_school_search(qs, search: str):
    """Name/slug/subdomain icontains filter for operator school lists."""
    search = (search or "").strip()
    if not search:
        return qs
    return qs.filter(
        Q(name__icontains=search)
        | Q(slug__icontains=search)
        | Q(subdomain__icontains=search)
    )


def paginate_operator_schools(
    request: HttpRequest,
    queryset,
    *,
    default_page_size: int = 50,
):
    """Paginate any operator school queryset; preserves q/page/page_size in URLs."""
    page_size = parse_registry_page_size(request)
    if page_size == REGISTRY_PAGE_SIZE_DEFAULT and default_page_size != REGISTRY_PAGE_SIZE_DEFAULT:
        raw = str(request.GET.get("page_size", default_page_size)).strip()
        try:
            size = int(raw)
        except ValueError:
            size = default_page_size
        if size in REGISTRY_PAGE_SIZE_OPTIONS:
            page_size = size
        else:
            page_size = default_page_size

    search = str(request.GET.get("q", "")).strip()
    queryset = apply_operator_school_search(queryset, search)
    paginator = Paginator(queryset, page_size)
    page = paginator.get_page(request.GET.get("page", 1))
    extra = request.GET.copy()
    extra.pop("page", None)
    return page, search, page_size, extra.urlencode()
