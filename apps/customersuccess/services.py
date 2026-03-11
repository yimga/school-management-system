"""
Section 11: Services for benchmark intelligence (11.3) and customer success (11.4).
"""
from decimal import Decimal
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.db.models import Count, Avg, Q
from django.utils import timezone

CUSTOMER_SUCCESS_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ObjectDoesNotExist,
    TypeError,
    ValueError,
)
OPTIONAL_ONBOARDING_STEP_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    ObjectDoesNotExist,
    TypeError,
    ValueError,
)


def get_peer_school_ids(school, cohort=None):
    """
    Return list of school IDs in the same benchmark cohort (same country/size band/type).
    Used for peer comparison. If cohort is None, infer from school attributes.
    """
    from apps.schools.models import School
    from .models import BenchmarkCohort

    if not school:
        return []
    country = getattr(school, "country_code", "") or ""
    # Infer size band from student count if available
    try:
        cnt = school.student_profiles.count() if hasattr(school, "student_profiles") else 0
    except CUSTOMER_SUCCESS_SOFT_FAILURES:
        cnt = 0
    if cnt < 100:
        size_band = "micro"
    elif cnt < 500:
        size_band = "small"
    elif cnt < 2000:
        size_band = "medium"
    else:
        size_band = "large"

    cohorts = BenchmarkCohort.objects.filter(is_active=True)
    if country:
        cohorts = cohorts.filter(Q(country_code=country) | Q(country_code=""))
    if size_band:
        cohorts = cohorts.filter(Q(size_band=size_band) | Q(size_band=""))
    cohort_obj = cohorts.first() if cohort is None else cohort
    if not cohort_obj:
        # Fallback: same country only
        return list(
            School.objects.filter(is_active=True, country_code=country)
            .exclude(pk=school.pk)
            .values_list("pk", flat=True)[:50]
        )
    # Match schools by cohort criteria
    qs = School.objects.filter(is_active=True).exclude(pk=school.pk)
    if cohort_obj.country_code:
        qs = qs.filter(country_code=cohort_obj.country_code)
    if cohort_obj.size_band:
        # Size band filter would need annotation by student count; keep simple
        pass
    return list(qs.values_list("pk", flat=True)[:50])


def compute_tenant_health_score(school):
    """
    Compute a 0–100 health score for a tenant from last_activity, recent workflow failures, and optional adoption.
    Returns (score, dimensions dict). Does not persist; caller can save TenantHealthScore.
    """
    from apps.schools.models import School
    from .models import WorkflowFailureEvent

    dimensions = {}
    # Activity: last_activity within 7d = 100, 30d = 70, 90d = 40, else 20
    last = getattr(school, "last_activity", None)
    if last:
        delta = (timezone.now() - last).total_seconds() / 86400
        if delta <= 7:
            dimensions["activity"] = 100
        elif delta <= 30:
            dimensions["activity"] = 70
        elif delta <= 90:
            dimensions["activity"] = 40
        else:
            dimensions["activity"] = 20
    else:
        dimensions["activity"] = 10

    # Workflow failures in last 14 days
    from datetime import timedelta
    since = timezone.now() - timedelta(days=14)
    fail_count = WorkflowFailureEvent.objects.filter(school=school, created_at__gte=since).count()
    if fail_count == 0:
        dimensions["workflows"] = 100
    elif fail_count <= 3:
        dimensions["workflows"] = 70
    elif fail_count <= 10:
        dimensions["workflows"] = 40
    else:
        dimensions["workflows"] = 20

    # Adoption placeholder: assume 70 if we have no module adoption metrics
    dimensions["adoption"] = 70

    score = sum(dimensions.values()) / len(dimensions) if dimensions else 50
    return round(Decimal(str(score)), 2), dimensions


def ensure_health_score_record(school):
    """Compute and save latest TenantHealthScore for school. Idempotent (one per day)."""
    from .models import TenantHealthScore

    today = timezone.now().date()
    if TenantHealthScore.objects.filter(school=school, computed_at__date=today).exists():
        return TenantHealthScore.objects.filter(school=school).order_by("-computed_at").first()
    score, dimensions = compute_tenant_health_score(school)
    return TenantHealthScore.objects.create(
        school=school,
        score=score,
        dimensions=dimensions,
    )


def get_peer_benchmark_metrics(school, metric_key="maturity"):
    """
    Return aggregate metric for peer cohort (e.g. average maturity or health) for comparison.
    """
    from .models import TenantMaturityScore, TenantHealthScore

    peer_ids = get_peer_school_ids(school)
    if not peer_ids:
        return None
    if metric_key == "maturity":
        agg = TenantMaturityScore.objects.filter(
            school_id__in=peer_ids,
            computed_at__gte=timezone.now() - timezone.timedelta(days=90),
        ).aggregate(avg=Avg("score"))
    else:
        agg = TenantHealthScore.objects.filter(
            school_id__in=peer_ids,
            computed_at__gte=timezone.now() - timezone.timedelta(days=30),
        ).aggregate(avg=Avg("score"))
    return float(agg["avg"]) if agg.get("avg") is not None else None


def record_workflow_failure(school, workflow_name, workflow_run_id="", error_summary="", payload=None):
    """Record a workflow failure event for health and optional auto-ticket."""
    from .models import WorkflowFailureEvent, AutoTicketRule

    event = WorkflowFailureEvent.objects.create(
        school=school,
        workflow_name=workflow_name,
        workflow_run_id=workflow_run_id,
        error_summary=error_summary[:500],
        payload=payload or {},
    )
    rule = AutoTicketRule.objects.filter(trigger=AutoTicketRule.Trigger.WORKFLOW_FAILURE, is_active=True).first()
    if rule:
        create_auto_ticket(school, rule, trigger_context={"workflow_failure_event_id": event.pk, "error_summary": error_summary})
    return event


def create_auto_ticket(school, rule, trigger_context=None):
    """
    Create a GlobalSupportTicket when an AutoTicketRule matches.
    trigger_context: dict with event details for title/description.
    """
    try:
        from apps.siteconfig.models import GlobalSupportTicket
    except ImportError:
        return None
    trigger_context = trigger_context or {}
    title = f"[Auto] {rule.name}: {trigger_context.get('error_summary', rule.get_trigger_display())}"[:255]
    ticket = GlobalSupportTicket.objects.create(
        school=school,
        user=None,
        subject=title,
        body=trigger_context.get("message", "Auto-created by customer success rule."),
        status=GlobalSupportTicket.Status.OPEN,
        priority=GlobalSupportTicket.Priority.NORMAL,
        metadata={"source": "auto_ticket_rule", "rule_id": rule.pk, "trigger": rule.trigger, **trigger_context},
    )
    return ticket


def get_support_copilot_suggestions(school):
    """
    Section 11.4: Support co-pilot — suggested actions from interventions, risk alerts, health.
    Returns list of {title, description, link, priority}.
    """
    suggestions = []
    from .models import TenantInterventionSuggestion, TenantRiskAlert, TenantHealthScore

    for s in TenantInterventionSuggestion.objects.filter(
        school=school, dismissed_at__isnull=True
    ).order_by("priority", "-created_at")[:10]:
        suggestions.append({
            "title": s.title,
            "description": s.description[:200] if s.description else "",
            "link": "",
            "priority": s.priority,
        })
    for a in TenantRiskAlert.objects.filter(school=school, acknowledged_at__isnull=True).order_by("-created_at")[:5]:
        suggestions.append({
            "title": f"Risk: {a.reason}",
            "description": (a.suggested_action or "")[:200],
            "link": "",
            "priority": 1 if a.severity == "red" else 2,
        })
    latest = TenantHealthScore.objects.filter(school=school).order_by("-computed_at").first()
    if latest and float(latest.score) < 50:
        suggestions.append({
            "title": "Health score below 50",
            "description": "Consider checking workflow failures and recent activity.",
            "link": "/siteconfig/",
            "priority": 2,
        })
    return sorted(suggestions, key=lambda x: x["priority"])[:15]


def get_guided_onboarding_steps(school):
    """
    Section 11.4: Guided onboarding — steps and completion from existing data.
    Returns list of {key, label, done, link}.
    """
    steps = []
    try:
        from apps.academics.models import AcademicYear
        has_year = AcademicYear.objects.filter(school=school).exists()
        steps.append({
            "key": "academic_year",
            "label": "Create academic year",
            "done": has_year,
            "link": "/admin/academics/academicyear/add/" if not has_year else "",
        })
    except OPTIONAL_ONBOARDING_STEP_FAILURES:
        pass
    try:
        from apps.people.models import StudentProfile
        has_students = StudentProfile.objects.filter(school=school, is_active=True).exists()
        steps.append({
            "key": "students",
            "label": "Add students",
            "done": has_students,
            "link": "/authentication/backend/students/" if not has_students else "",
        })
    except OPTIONAL_ONBOARDING_STEP_FAILURES:
        pass
    try:
        from apps.platform_runtime.helpers import get_effective_site_settings
        site = get_effective_site_settings(school=school)
        has_grading = bool(getattr(site, "grading_scale", None) or getattr(site, "default_grading_scale", None))
        steps.append({
            "key": "grading",
            "label": "Configure grading",
            "done": has_grading,
            "link": "/siteconfig/grading-settings/" if not has_grading else "",
        })
        has_branding = bool(
            (getattr(site, "site_name", None) or "").strip()
            or getattr(site, "logo", None)
            or (getattr(site, "school_name", None) or "").strip()
        )
        steps.append({
            "key": "branding",
            "label": "Set school branding",
            "done": has_branding,
            "link": "/siteconfig/customizer/" if not has_branding else "",
        })
    except OPTIONAL_ONBOARDING_STEP_FAILURES:
        pass
    steps.append({
        "key": "dashboard",
        "label": "Review dashboard",
        "done": True,
        "link": "/authentication/backend/",
    })
    return steps
