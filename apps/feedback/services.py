from __future__ import annotations

from collections import Counter
from decimal import Decimal

from django.db import models, transaction
from django.db.models import Count, Avg
from django.urls import reverse
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

SUPPORT_ESCALATION_CATEGORIES = {
    FeedbackSubmission.Category.TRAINING.value,
    FeedbackSubmission.Category.BILLING.value,
    FeedbackSubmission.Category.DATA_IMPORT.value,
    FeedbackSubmission.Category.LOGIN.value,
    FeedbackSubmission.Category.ACCESSIBILITY.value,
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


def _normalize_text(value) -> str:
    return str(value or "").strip()


def _help_query(title="", description="", module="", category="") -> str:
    parts = [_normalize_text(title), _normalize_text(module), _normalize_text(category)]
    desc = _normalize_text(description)
    if desc:
        parts.append(" ".join(desc.split()[:18]))
    return " ".join(p for p in parts if p)[:220]


def _visible_kb_and_faq(request):
    try:
        from apps.portal.views_kb import _approved_faq_for_request, _published_kb_for_request

        return _published_kb_for_request(request), _approved_faq_for_request(request)
    except Exception:
        return None, None


def suggest_help_resources(
    request,
    *,
    title="",
    description="",
    module="",
    category="",
    limit=4,
):
    """Return role/region-aware KB and FAQ resources before users file feedback.

    This keeps the feedback center connected to the help center: users can self-serve
    first, while submitted feedback still records which help surface they came from.
    """
    query = _help_query(title=title, description=description, module=module, category=category)
    articles_qs, faqs_qs = _visible_kb_and_faq(request)
    if not query or articles_qs is None or faqs_qs is None:
        return {"query": query, "articles": [], "faqs": []}
    try:
        from apps.portal.kb_search import search_kb_articles

        ranked_articles = [article for article, _score in search_kb_articles(articles_qs, query, limit=limit)]
    except Exception:
        ranked_articles = list(
            articles_qs.filter(title__icontains=query).order_by("-is_featured", "-view_count")[:limit]
        )
    faqs = list(
        faqs_qs.filter(
            models.Q(question__icontains=query)
            | models.Q(answer__icontains=query)
            | models.Q(tags__icontains=query)
        )[:limit]
    )
    if not faqs:
        tokens = [token for token in query.split() if len(token) > 3][:4]
        faq_filter = models.Q()
        for token in tokens:
            faq_filter |= models.Q(question__icontains=token) | models.Q(tags__icontains=token)
        if faq_filter:
            faqs = list(faqs_qs.filter(faq_filter)[:limit])
    return {"query": query, "articles": ranked_articles[:limit], "faqs": faqs[:limit]}


def should_escalate_to_support(category, severity=None, explicit=False) -> bool:
    return bool(
        explicit
        or category in SUPPORT_ESCALATION_CATEGORIES
        or severity == FeedbackSubmission.Severity.CRITICAL
    )


def support_entry_points(request):
    """Centralized URLs for every help/contact/product voice surface."""
    links = {}
    route_names = {
        "help_center": "feedback:help_center",
        "kb_home": "kb:kb_home",
        "faq_list": "kb:faq_list",
        "support_request": "portal:support_request",
        "portal_help": "portal:support_help_hub",
        "school_feedback": "feedback:school_feedback",
        "school_roadmap": "feedback:school_roadmap",
        "release_notes": "feedback:release_notes_public",
    }
    for key, name in route_names.items():
        try:
            links[key] = reverse(name)
        except Exception:
            links[key] = ""
    try:
        links["contact_us"] = reverse("marketing_contact")
    except Exception:
        links["contact_us"] = links.get("support_request", "")
    return links


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
    source_channel=FeedbackSubmission.SourceChannel.IN_APP,
    source_url="",
    related_kb_article_id=None,
    related_faq_id=None,
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
        source_channel=source_channel or FeedbackSubmission.SourceChannel.IN_APP,
        source_url=source_url or route,
        related_kb_article_id=related_kb_article_id or None,
        related_faq_id=related_faq_id or None,
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


def create_support_ticket_from_feedback(feedback, *, request=None, actor=None):
    """Mirror operational feedback into the existing support queue.

    Product feedback remains in apps.feedback. Training, billing, login, data/import,
    accessibility, and critical issues also become GlobalSupportTicket rows so the
    school/support operation can work them without waiting for product triage.
    """
    if feedback.school_id is None:
        return None
    try:
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket
    except Exception:
        return None
    priority = GlobalSupportTicket.Priority.NORMAL
    if feedback.severity == FeedbackSubmission.Severity.CRITICAL:
        priority = GlobalSupportTicket.Priority.URGENT
    elif feedback.severity == FeedbackSubmission.Severity.HIGH:
        priority = GlobalSupportTicket.Priority.HIGH
    elif feedback.severity == FeedbackSubmission.Severity.LOW:
        priority = GlobalSupportTicket.Priority.LOW
    user = actor or feedback.user
    body = (
        f"Feedback #{feedback.pk}\n"
        f"Category: {feedback.get_category_display()}\n"
        f"Role: {feedback.role or 'unknown'}\n"
        f"Module: {feedback.module or 'general'}\n"
        f"Route: {feedback.route or feedback.source_url or 'N/A'}\n"
        f"Source: {feedback.source_channel}\n\n"
        f"{feedback.description}"
    )
    ticket = GlobalSupportTicket.objects.create(
        school=feedback.school,
        user=user if getattr(user, "is_authenticated", False) else feedback.user,
        subject=f"[Feedback] {feedback.title}"[:255],
        body=body,
        priority=priority,
        status=GlobalSupportTicket.Status.OPEN,
        tags=["feedback", feedback.category, feedback.module or "general"],
        metadata={
            "feedback_id": feedback.pk,
            "source_channel": feedback.source_channel,
            "source_url": feedback.source_url,
            "route": feedback.route,
            "privacy_level": feedback.privacy_level,
        },
    )
    feedback.related_support_ticket_id = str(ticket.pk)
    feedback.support_escalated = True
    feedback.tags = sorted(set((feedback.tags or []) + ["support_escalated"]))
    feedback.save(
        update_fields=[
            "related_support_ticket_id",
            "support_escalated",
            "tags",
            "updated_at",
        ]
    )
    FeedbackTriageEvent.objects.create(
        feedback=feedback,
        actor=user if getattr(user, "is_authenticated", False) else None,
        action="support_ticket_created",
        to_status=feedback.status,
        payload={"support_ticket_id": str(ticket.pk)},
    )
    return ticket


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
    # tenant-isolation-allow: platform-level churn-risk analytics aggregated across all tenants for super-admin dashboards (results grouped by school below)
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
