from __future__ import annotations

from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Avg
from django.utils import timezone

from .models import (
    FeatureRequest,
    FeedbackSubmission,
    FeedbackTriageEvent,
    FeedbackVote,
    ReleaseNote,
    RoadmapItem,
    SurveyResponse,
)


ADMIN_ROLES = {
    "ADMIN",
    "IT_ADMIN",
    "LEADERSHIP",
    "PRINCIPAL",
    "VICE_PRINCIPAL",
    "BURSAR",
    "PROPRIETOR",
    "SUPERADMIN",
}


def get_user_role(user) -> str:
    return str(getattr(user, "role", "") or "").upper()


def get_request_school(request):
    school = getattr(request, "school", None)
    if school is not None:
        return school
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return None
    membership = (
        user.school_memberships.select_related("school")
        .order_by("-is_primary", "school__name")
        .first()
    )
    return membership.school if membership else None


def is_operator(user) -> bool:
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or get_user_role(user) == "SUPERADMIN"
    )


def visible_feedback_for_user(user, school=None):
    qs = FeedbackSubmission.objects.select_related("school", "user", "assigned_to")
    if is_operator(user):
        return qs
    if school is None:
        return qs.none()
    role = get_user_role(user)
    if role in {"PARENT", "STUDENT"}:
        return qs.filter(school=school, user=user)
    return qs.filter(school=school, visible_to_school=True)


def visible_roadmap_for_user(user, school=None):
    qs = RoadmapItem.objects.prefetch_related("feature_requests")
    if is_operator(user):
        return qs
    qs = qs.filter(tenant_visibility=True)
    if school is not None:
        qs = qs.filter(public_visibility=True) | qs.filter(
            feature_requests__school=school
        )
    else:
        qs = qs.filter(public_visibility=True)
    return qs.distinct()


def _student_privacy_defaults(role, privacy_level):
    if role == "STUDENT":
        return FeedbackSubmission.PrivacyLevel.SCHOOL_PRIVATE, True, True
    return privacy_level, False, True


def submit_feedback(
    *,
    school,
    user,
    title,
    description,
    category=FeedbackSubmission.Category.GENERAL,
    module="",
    route="",
    severity=FeedbackSubmission.Severity.MEDIUM,
    privacy_level=FeedbackSubmission.PrivacyLevel.SCHOOL_PRIVATE,
    contact_preference="",
    browser_context=None,
    device_context=None,
    current_action_context=None,
):
    role = get_user_role(user)
    privacy_level, moderation_required, visible_to_school = _student_privacy_defaults(
        role, privacy_level
    )
    feedback = FeedbackSubmission(
        school=school,
        user=user if getattr(user, "is_authenticated", False) else None,
        role=role,
        title=title,
        description=description,
        category=category,
        module=module,
        route=route,
        severity=severity,
        privacy_level=privacy_level,
        contact_preference=contact_preference,
        browser_context=browser_context or {},
        device_context=device_context or {},
        current_action_context=current_action_context or {},
        moderation_required=moderation_required,
        visible_to_school=visible_to_school,
    )
    feedback.full_clean()
    feedback.save()
    FeedbackTriageEvent.objects.create(
        feedback=feedback,
        actor=user if getattr(user, "is_authenticated", False) else None,
        action="submitted",
        to_status=feedback.status,
    )
    return feedback


def submit_feature_request(
    *,
    school,
    user,
    title,
    problem_statement,
    proposed_solution="",
    current_workaround="",
    affected_roles=None,
    module="",
    impact=FeatureRequest.Impact.MEDIUM,
    urgency=FeatureRequest.Urgency.SOON,
    school_type="",
    region="",
    pilot_interest=False,
    source_feedback=None,
):
    request = FeatureRequest(
        school=school,
        submitted_by=user if getattr(user, "is_authenticated", False) else None,
        source_feedback=source_feedback,
        title=title,
        problem_statement=problem_statement,
        proposed_solution=proposed_solution,
        current_workaround=current_workaround,
        affected_roles=affected_roles or [],
        module=module,
        impact=impact,
        urgency=urgency,
        school_type=school_type,
        region=region,
        pilot_interest=pilot_interest,
    )
    request.full_clean()
    request.save()
    request.weighted_score = calculate_priority_score(request)
    request.save(update_fields=["weighted_score", "updated_at"])
    FeedbackTriageEvent.objects.create(
        feature_request=request,
        actor=user if getattr(user, "is_authenticated", False) else None,
        action="submitted",
        to_status=request.status,
    )
    return request


def _vote_weight_for_role(role: str, *, strategic_customer=False, operator=False) -> int:
    if operator:
        return FeedbackVote.RoleWeight.PLATFORM_OPERATOR
    if strategic_customer:
        return FeedbackVote.RoleWeight.STRATEGIC_CUSTOMER
    if role in ADMIN_ROLES:
        return FeedbackVote.RoleWeight.TENANT_ADMIN
    if role == "TEACHER":
        return FeedbackVote.RoleWeight.TEACHER
    if role == "PARENT":
        return FeedbackVote.RoleWeight.PARENT
    return FeedbackVote.RoleWeight.STUDENT


@transaction.atomic
def vote_feature_request(
    feature_request,
    user,
    *,
    school=None,
    reason="",
    strategic_customer=False,
):
    role = get_user_role(user)
    weight = _vote_weight_for_role(
        role, strategic_customer=strategic_customer, operator=is_operator(user)
    )
    vote, _created = FeedbackVote.objects.update_or_create(
        feature_request=feature_request,
        user=user,
        defaults={
            "school": school or feature_request.school,
            "role": role,
            "weight": int(weight),
            "reason": reason,
        },
    )
    feature_request.vote_count = feature_request.votes.count()
    feature_request.weighted_score = calculate_priority_score(feature_request)
    feature_request.save(update_fields=["vote_count", "weighted_score", "updated_at"])
    return vote


def calculate_priority_score(feature_request) -> Decimal:
    severity = {"low": 5, "medium": 12, "high": 22, "blocking": 32}
    urgency = {"someday": 2, "soon": 6, "this_term": 12, "immediate": 18}
    role_spread = len(feature_request.affected_roles or []) * 3
    vote_weight = sum(v.weight for v in feature_request.votes.all())
    strategic_fit = 8 if feature_request.module in {"finance", "reports", "imports", "offline_sync", "accessibility"} else 4
    churn_signal = 12 if feature_request.impact == FeatureRequest.Impact.BLOCKING else 0
    implementation_cost_discount = 6 if feature_request.external_blocker else 0
    score = (
        severity.get(feature_request.impact, 12)
        + urgency.get(feature_request.urgency, 6)
        + role_spread
        + strategic_fit
        + churn_signal
        + min(vote_weight, 30)
        - implementation_cost_discount
    )
    return Decimal(max(score, 0))


def triage_feedback(feedback, *, actor, status, assigned_to=None, note="", decision_reason=""):
    old_status = feedback.status
    feedback.status = status
    if assigned_to is not None:
        feedback.assigned_to = assigned_to
    if decision_reason:
        feedback.decision_reason = decision_reason
    feedback.full_clean()
    feedback.save()
    FeedbackTriageEvent.objects.create(
        feedback=feedback,
        actor=actor,
        action="triaged",
        from_status=old_status,
        to_status=status,
        note=note,
    )
    return feedback


def merge_duplicate_requests(primary_request, duplicate_request, *, actor, note=""):
    duplicate_request.status = FeatureRequest.Status.DUPLICATE
    duplicate_request.duplicate_of = primary_request
    duplicate_request.decision_reason = note or f"Duplicate of #{primary_request.pk}."
    duplicate_request.full_clean()
    duplicate_request.save()
    FeedbackTriageEvent.objects.create(
        feature_request=duplicate_request,
        actor=actor,
        action="duplicate",
        to_status=duplicate_request.status,
        note=duplicate_request.decision_reason,
    )
    return duplicate_request


def convert_feedback_to_feature_request(feedback, *, actor, title=None):
    feature = submit_feature_request(
        school=feedback.school,
        user=actor,
        title=title or feedback.title,
        problem_statement=feedback.description,
        affected_roles=[feedback.role] if feedback.role else [],
        module=feedback.module,
        impact=FeatureRequest.Impact.BLOCKING
        if feedback.severity == FeedbackSubmission.Severity.CRITICAL
        else FeatureRequest.Impact.MEDIUM,
        urgency=FeatureRequest.Urgency.IMMEDIATE
        if feedback.severity == FeedbackSubmission.Severity.CRITICAL
        else FeatureRequest.Urgency.SOON,
        source_feedback=feedback,
    )
    triage_feedback(
        feedback,
        actor=actor,
        status=FeedbackSubmission.Status.ACCEPTED,
        note="Converted to feature request.",
    )
    return feature


def create_roadmap_item_from_request(feature_request, *, actor, public_visibility=False):
    item = RoadmapItem.objects.create(
        title=feature_request.title,
        problem=feature_request.problem_statement,
        status=RoadmapItem.Status.UNDER_REVIEW,
        target_module=feature_request.module,
        affected_roles=feature_request.affected_roles,
        source_feedback_count=1 + feature_request.votes.count(),
        priority_score=feature_request.weighted_score,
        public_visibility=public_visibility,
        tenant_visibility=True,
    )
    item.feature_requests.add(feature_request)
    feature_request.roadmap_status = item.status
    feature_request.status = FeatureRequest.Status.UNDER_REVIEW
    feature_request.save(update_fields=["roadmap_status", "status", "updated_at"])
    FeedbackTriageEvent.objects.create(
        feature_request=feature_request,
        actor=actor,
        action="roadmap_added",
        to_status=feature_request.status,
        payload={"roadmap_item_id": item.pk},
    )
    return item


def link_release_note_to_requests(release_note, feature_requests):
    release_note.feature_requests.add(*feature_requests)
    for request in feature_requests:
        request.status = FeatureRequest.Status.RELEASED
        request.save(update_fields=["status", "updated_at"])
    return release_note


def notify_submitters_of_release(release_note):
    release_note.notify_submitters = True
    release_note.save(update_fields=["notify_submitters"])
    for feature_request in release_note.feature_requests.all():
        FeedbackTriageEvent.objects.create(
            feature_request=feature_request,
            action="notified_submitter",
            to_status=feature_request.status,
            payload={"release_note_id": release_note.pk},
        )
    return True


def summarize_feedback_by_school():
    return (
        FeedbackSubmission.objects.values("school__name")
        .annotate(total=Count("id"))
        .order_by("-total")
    )


def summarize_feedback_by_role():
    return FeedbackSubmission.objects.values("role").annotate(total=Count("id")).order_by("-total")


def detect_churn_risk_signals():
    risky = FeedbackSubmission.objects.filter(
        severity__in=[FeedbackSubmission.Severity.HIGH, FeedbackSubmission.Severity.CRITICAL],
        status__in=[FeedbackSubmission.Status.NEW, FeedbackSubmission.Status.TRIAGED],
    )
    grouped = risky.values("school", "school__name").annotate(total=Count("id")).filter(total__gte=2)
    return list(grouped)


def generate_you_said_we_did_items(school=None):
    notes = ReleaseNote.objects.filter(published_at__isnull=False).prefetch_related(
        "feature_requests"
    )
    if school is not None:
        notes = notes.filter(feature_requests__school=school).distinct()
    items = []
    for note in notes[:20]:
        requests = list(note.feature_requests.all())
        problem = requests[0].problem_statement if requests else note.summary
        items.append({"you_said": problem, "we_did": note.summary, "release_note": note})
    return items


def module_sentiment_summary():
    rows = SurveyResponse.objects.values("workflow").annotate(
        total=Count("id"), average_score=Avg("score")
    )
    return list(rows)


def top_pain_points(limit=10):
    texts = FeedbackSubmission.objects.exclude(module="").values_list("module", flat=True)
    counts = Counter(texts)
    return counts.most_common(limit)


def publish_release_note(title, summary, *, roadmap_item=None, feature_requests=None, is_public=False):
    note = ReleaseNote.objects.create(
        title=title,
        summary=summary,
        roadmap_item=roadmap_item,
        published_at=timezone.now(),
        is_public=is_public,
    )
    if feature_requests:
        link_release_note_to_requests(note, feature_requests)
    return note
