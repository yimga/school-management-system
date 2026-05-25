from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from .form_widgets import apply_bootstrap_form_styles
from .forms import FeatureRequestForm, FeedbackSubmissionForm, RoleFeedbackForm, SurveyResponseForm
from .models import FeatureRequest, FeedbackSubmission, ReleaseNote, RoadmapItem, SurveyResponse
from .services import (
    convert_feedback_to_feature_request,
    create_support_ticket_from_feedback,
    create_roadmap_item_from_request,
    detect_churn_risk_signals,
    generate_you_said_we_did_items,
    get_request_school,
    get_user_role,
    is_operator,
    module_sentiment_summary,
    should_escalate_to_support,
    suggest_help_resources,
    submit_feature_request,
    submit_feedback,
    summarize_feedback_by_role,
    summarize_feedback_by_school,
    support_entry_points,
    top_pain_points,
    triage_feedback,
    visible_feedback_for_user,
    visible_roadmap_for_user,
    vote_feature_request,
)


PARENT_CATEGORIES = [
    ("general", "Portal usability"),
    ("billing", "Payment/receipt issue"),
    ("communication", "Communication issue"),
    ("workflow", "Student progress visibility"),
    ("mobile", "Mobile issue"),
    ("accessibility", "Accessibility issue"),
    ("training", "School support request"),
]

STUDENT_CATEGORIES = [
    ("workflow", "Assignment issue"),
    ("general", "Schedule issue"),
    ("data_import", "Result/report issue"),
    ("login", "Login issue"),
    ("mobile", "Mobile issue"),
    ("accessibility", "Accessibility issue"),
    ("suggestion", "Suggestion"),
]

TEACHER_CATEGORIES = [
    ("workflow", "Attendance"),
    ("data_import", "Gradebook"),
    ("general", "Lesson planning"),
    ("bug", "Report cards"),
    ("communication", "Messaging"),
    ("mobile", "Mobile issue"),
    ("accessibility", "Accessibility issue"),
]


def _feedback_context(request, audience="school"):
    school = get_request_school(request)
    user = request.user
    return {
        "school": school,
        "audience": audience,
        "feedback_items": visible_feedback_for_user(user, school)[:50],
        "feature_requests": FeatureRequest.objects.filter(school=school).order_by("-weighted_score", "-created_at")[:50],
        "roadmap_items": visible_roadmap_for_user(user, school)[:30],
        "release_notes": ReleaseNote.objects.filter(feature_requests__school=school).distinct()[:20],
        "you_said_we_did": generate_you_said_we_did_items(school),
        "support_links": support_entry_points(request),
    }


@login_required
def school_feedback_center(request):
    context = _feedback_context(request, "school")
    if request.method == "POST":
        if request.POST.get("form_kind") == "feature":
            form = FeatureRequestForm(request.POST)
            feedback_form = FeedbackSubmissionForm()
            if form.is_valid():
                submit_feature_request(
                    school=context["school"],
                    user=request.user,
                    affected_roles=[r.strip().upper() for r in form.cleaned_data["affected_roles"].split(",") if r.strip()],
                    **{k: v for k, v in form.cleaned_data.items() if k != "affected_roles"},
                )
                messages.success(request, "Feature request submitted for product triage.")
                return redirect("feedback:school_feedback")
        else:
            feedback_form = FeedbackSubmissionForm(request.POST)
            form = FeatureRequestForm()
            if feedback_form.is_valid():
                cleaned = dict(feedback_form.cleaned_data)
                escalate = cleaned.pop("escalate_to_support", False)
                feedback = submit_feedback(school=context["school"], user=request.user, **cleaned)
                if should_escalate_to_support(
                    feedback.category,
                    feedback.severity,
                    explicit=escalate,
                ):
                    ticket = create_support_ticket_from_feedback(
                        feedback, request=request, actor=request.user
                    )
                    if ticket is not None:
                        messages.success(
                            request,
                            "Feedback submitted and routed to the support queue.",
                        )
                    else:
                        messages.success(request, "Feedback submitted.")
                else:
                    messages.success(request, "Feedback submitted.")
                return redirect("feedback:school_feedback")
    else:
        form = FeatureRequestForm()
        initial = {
            "route": request.GET.get("route", ""),
            "module": request.GET.get("module", ""),
            "source_channel": request.GET.get("source", FeedbackSubmission.SourceChannel.IN_APP),
            "source_url": request.GET.get("source_url", request.META.get("HTTP_REFERER", "")),
            "related_kb_article_id": request.GET.get("kb_article", ""),
            "related_faq_id": request.GET.get("faq", ""),
        }
        feedback_form = FeedbackSubmissionForm(initial=initial)
    help_resources = suggest_help_resources(
        request,
        title=request.POST.get("title", request.GET.get("q", "")),
        description=request.POST.get("description", ""),
        module=request.POST.get("module", request.GET.get("module", "")),
        category=request.POST.get("category", request.GET.get("category", "")),
    )
    context.update(
        {
            "feedback_form": feedback_form,
            "feature_form": form,
            "help_resources": help_resources,
        }
    )
    return render(request, "feedback/school_center.html", context)


@login_required
def role_feedback_center(request, role):
    category_map = {
        "teacher": TEACHER_CATEGORIES,
        "parent": PARENT_CATEGORIES,
        "student": STUDENT_CATEGORIES,
    }
    school = get_request_school(request)
    categories = category_map.get(role, FeedbackSubmission.Category.choices)
    if request.method == "POST":
        form = RoleFeedbackForm(request.POST, role_categories=categories)
        if form.is_valid():
            cleaned = dict(form.cleaned_data)
            escalate = cleaned.pop("escalate_to_support", False)
            feedback = submit_feedback(school=school, user=request.user, **cleaned)
            if should_escalate_to_support(feedback.category, feedback.severity, explicit=escalate):
                create_support_ticket_from_feedback(feedback, request=request, actor=request.user)
            messages.success(request, "Feedback submitted.")
            return redirect(f"feedback:{role}_feedback")
    else:
        privacy = FeedbackSubmission.PrivacyLevel.SCHOOL_PRIVATE
        form = RoleFeedbackForm(
            initial={
                "route": request.GET.get("route", ""),
                "privacy_level": privacy,
                "source_channel": FeedbackSubmission.SourceChannel.HELP_CENTER
                if request.GET.get("from") == "help"
                else FeedbackSubmission.SourceChannel.IN_APP,
                "source_url": request.META.get("HTTP_REFERER", ""),
            },
            role_categories=categories,
        )
    items = visible_feedback_for_user(request.user, school)[:20]
    help_resources = suggest_help_resources(
        request,
        title=request.GET.get("q", ""),
        module=request.GET.get("module", ""),
        category=request.GET.get("category", ""),
    )
    return render(
        request,
        "feedback/role_center.html",
        {
            "form": form,
            "role_surface": role,
            "school": school,
            "feedback_items": items,
            "help_resources": help_resources,
            "support_links": support_entry_points(request),
        },
    )


@login_required
def school_roadmap(request):
    school = get_request_school(request)
    return render(
        request,
        "feedback/school_roadmap.html",
        {
            "roadmap_items": visible_roadmap_for_user(request.user, school),
            "you_said_we_did": generate_you_said_we_did_items(school),
        },
    )


@login_required
def feature_center(request):
    """Tenant-facing product discovery surface."""
    from apps.portal.help_governance import should_redirect_feature_center_for_request

    if should_redirect_feature_center_for_request(request):
        messages.info(
            request,
            "Use Help Center for guided support — feature voting is for staff.",
        )
        return redirect("feedback:help_center")
    school = get_request_school(request)
    role = get_user_role(request.user)
    if role == "STUDENT":
        messages.info(request, "Use student feedback for safe school-first help.")
        return redirect("feedback:student_feedback")
    if role == "PARENT":
        messages.info(request, "Use parent feedback or Contact Us for parent portal help.")
        return redirect("feedback:parent_feedback")
    operator_view = is_operator(request.user) and school is None
    if request.method == "POST":
        form = FeatureRequestForm(request.POST)
        apply_bootstrap_form_styles(form)
        if form.is_valid():
            submit_feature_request(
                school=school,
                user=request.user,
                affected_roles=[
                    r.strip().upper()
                    for r in form.cleaned_data["affected_roles"].split(",")
                    if r.strip()
                ],
                **{k: v for k, v in form.cleaned_data.items() if k != "affected_roles"},
            )
            messages.success(request, "Feature request submitted for product discovery.")
            return redirect("feedback:feature_center")
    else:
        form = FeatureRequestForm(
            initial={
                "module": request.GET.get("module", ""),
                "title": request.GET.get("title", ""),
            }
        )
    qs = (
        FeatureRequest.objects.all()  # tenant-isolation-allow: operator-feature-center-cross-tenant-read
        if operator_view
        else FeatureRequest.objects.filter(school=school)
    ).order_by("-weighted_score", "-created_at")
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    apply_bootstrap_form_styles(form)
    return render(
        request,
        "feedback/feature_center.html",
        {
            "school": school,
            "is_operator_view": operator_view,
            "feature_form": form,
            "feature_requests": page.object_list,
            "feature_requests_page": page,
            "roadmap_items": visible_roadmap_for_user(request.user, school)[:30],
            "you_said_we_did": generate_you_said_we_did_items(school)[:10],
            "support_links": support_entry_points(request),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def contact_us(request):
    """Authenticated contact router for tenant users and platform operators."""
    school = get_request_school(request)
    role = (get_user_role(request.user) or "").lower()
    links = support_entry_points(request)
    if request.method == "POST" and request.POST.get("form_kind") == "platform_message":
        title = (request.POST.get("title") or "").strip() or "Contact us message"
        description = (request.POST.get("description") or "").strip()
        if description:
            submit_feedback(
                school=school,
                user=request.user,
                title=title[:180],
                description=description,
                category=request.POST.get("category")
                or FeedbackSubmission.Category.GENERAL,
                module=request.POST.get("module", ""),
                route=request.POST.get("route", request.path),
                severity=request.POST.get("severity")
                or FeedbackSubmission.Severity.MEDIUM,
                source_channel=FeedbackSubmission.SourceChannel.CONTACT_US,
                source_url=request.build_absolute_uri(),
            )
            messages.success(
                request,
                "Message sent — our team will route it to the right lane.",
            )
            return redirect(links.get("contact_center") or "feedback:contact_us")
        messages.error(request, "Please describe how we can help.")
    open_support_count = 0
    open_contact_count = 0
    if school is not None:
        try:
            from apps.siteconfig.models_feature_controls import GlobalSupportTicket

            open_support_count = GlobalSupportTicket.objects.filter(
                school=school,
                user=request.user,
                status__in=[
                    GlobalSupportTicket.Status.OPEN,
                    GlobalSupportTicket.Status.IN_PROGRESS,
                    GlobalSupportTicket.Status.WAITING,
                ],
            ).count()
        except Exception:
            open_support_count = 0
        try:
            from apps.communication.models import ContactRequest

            open_contact_count = ContactRequest.objects.filter(
                school=school,
                parent=request.user,
                status__in=[
                    ContactRequest.Status.OPEN,
                    ContactRequest.Status.TRIAGED,
                    ContactRequest.Status.ASSIGNED,
                    ContactRequest.Status.IN_PROGRESS,
                ],
            ).count()
        except Exception:
            open_contact_count = 0
    return render(
        request,
        "feedback/contact_us.html",
        {
            "school": school,
            "role": role,
            "is_operator": is_operator(request.user),
            "support_links": links,
            "open_support_count": open_support_count,
            "open_contact_count": open_contact_count,
        },
    )


@login_required
@require_POST
def vote_feature(request, pk):
    feature = get_object_or_404(FeatureRequest, pk=pk)
    school = get_request_school(request)
    if not is_operator(request.user) and feature.school_id != getattr(school, "id", None):
        return JsonResponse({"error": "Not found"}, status=404)
    vote_feature_request(feature, request.user, school=school, reason=request.POST.get("reason", ""))
    messages.success(request, "Priority signal recorded.")
    return redirect(request.POST.get("next") or "feedback:school_feedback")


@login_required
@require_POST
def contextual_feedback(request):
    school = get_request_school(request)
    title = request.POST.get("title") or request.POST.get("action") or "Contextual feedback"
    category = request.POST.get("category") or FeedbackSubmission.Category.GENERAL
    feedback = submit_feedback(
        school=school,
        user=request.user,
        title=title,
        description=request.POST.get("description") or title,
        category=category,
        module=request.POST.get("module", ""),
        route=request.POST.get("route", request.META.get("HTTP_REFERER", "")),
        severity=request.POST.get("severity", FeedbackSubmission.Severity.MEDIUM),
        privacy_level=request.POST.get("privacy_level", FeedbackSubmission.PrivacyLevel.SCHOOL_PRIVATE),
        browser_context={"user_agent": request.META.get("HTTP_USER_AGENT", "")},
        device_context={"accept": request.META.get("HTTP_ACCEPT", "")},
        current_action_context={"page_title": request.POST.get("page_title", "")},
        source_channel=FeedbackSubmission.SourceChannel.CONTEXTUAL,
        source_url=request.META.get("HTTP_REFERER", ""),
    )
    if should_escalate_to_support(feedback.category, feedback.severity):
        create_support_ticket_from_feedback(feedback, request=request, actor=request.user)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "id": feedback.pk})
    messages.success(request, "Feedback captured.")
    return redirect(request.POST.get("next") or request.META.get("HTTP_REFERER", "/"))


@login_required
@require_POST
def pulse_survey(request):
    form = SurveyResponseForm(request.POST)
    if form.is_valid():
        SurveyResponse.objects.create(
            school=get_request_school(request),
            user=request.user,
            role=get_user_role(request.user),
            browser_context={"user_agent": request.META.get("HTTP_USER_AGENT", "")},
            **form.cleaned_data,
        )
        messages.success(request, "Pulse response recorded.")
    return redirect(request.POST.get("next") or request.META.get("HTTP_REFERER", "/"))


@login_required
def voice_of_customer(request):
    if not is_operator(request.user):
        return redirect("accounts:redirect")
    from .db_readiness import (
        feature_request_queryset,
        feedback_schema_ready,
        feedback_submission_queryset,
    )

    schema_ready = feedback_schema_ready()
    qs = feedback_submission_queryset().select_related("school", "user", "assigned_to")
    base_qs = qs
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    if request.GET.get("role"):
        qs = qs.filter(role=request.GET["role"])
    if request.GET.get("module"):
        qs = qs.filter(module=request.GET["module"])
    if request.GET.get("severity"):
        qs = qs.filter(severity=request.GET["severity"])
    return render(
        request,
        "feedback/voice_of_customer.html",
        {
            "feedback_items": list(qs[:100]),
            "feature_requests": list(
                feature_request_queryset()
                .select_related("school")
                .all()[:100]  # tenant-isolation-allow: voice-of-customer-operator-cross-tenant
            ),
            "feedback_schema_pending": not schema_ready,
            "roadmap_candidates": list(
                RoadmapItem.objects.filter(status=RoadmapItem.Status.UNDER_REVIEW)[:50]
            )
            if schema_ready
            else [],
            "by_school": summarize_feedback_by_school(),
            "by_role": summarize_feedback_by_role(),
            "pain_points": top_pain_points(),
            "sentiment": module_sentiment_summary(),
            "churn_risk": detect_churn_risk_signals(),
            "help_sourced_count": base_qs.filter(
                source_channel__in=[
                    FeedbackSubmission.SourceChannel.HELP_CENTER,
                    FeedbackSubmission.SourceChannel.KB_ARTICLE,
                    FeedbackSubmission.SourceChannel.FAQ,
                ]
            ).count(),
            "support_escalated_count": base_qs.filter(support_escalated=True).count(),
            "accessibility_count": base_qs.filter(
                category=FeedbackSubmission.Category.ACCESSIBILITY
            ).count(),
            "mobile_offline_count": base_qs.filter(
                category__in=[
                    FeedbackSubmission.Category.MOBILE,
                    FeedbackSubmission.Category.OFFLINE_SYNC,
                ]
            ).count(),
        },
    )


@login_required
@require_POST
def operator_feedback_action(request, pk):
    if not is_operator(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    feedback = get_object_or_404(FeedbackSubmission, pk=pk)
    action = request.POST.get("action")
    if action == "convert":
        convert_feedback_to_feature_request(feedback, actor=request.user)
        messages.success(request, "Converted to feature request.")
    else:
        triage_feedback(
            feedback,
            actor=request.user,
            status=request.POST.get("status", FeedbackSubmission.Status.TRIAGED),
            note=request.POST.get("note", ""),
            decision_reason=request.POST.get("decision_reason", ""),
        )
        messages.success(request, "Feedback updated.")
    return redirect("feedback:voice_of_customer")


@login_required
def product_roadmap(request):
    if not is_operator(request.user):
        return redirect("accounts:redirect")
    return render(
        request,
        "feedback/product_roadmap.html",
        {
            "roadmap_items": RoadmapItem.objects.prefetch_related("feature_requests", "release_notes"),
            "release_notes": ReleaseNote.objects.prefetch_related("feature_requests")[:50],
        },
    )


@login_required
@require_POST
def add_to_roadmap(request, pk):
    if not is_operator(request.user):
        return JsonResponse({"error": "Forbidden"}, status=403)
    feature = get_object_or_404(FeatureRequest, pk=pk)
    create_roadmap_item_from_request(
        feature,
        actor=request.user,
        public_visibility=request.POST.get("public_visibility") == "on",
    )
    messages.success(request, "Roadmap item created.")
    return redirect("feedback:product_roadmap")


@login_required
@require_http_methods(["GET", "POST"])
def help_center(request):
    """Role-aware Help Center landing — bridges KB / feedback / contact / release notes / pulse.

    Single entry point for in-app users. Marketing contact lives at /contact/; this surface is
    inside the authenticated shell so role-aware shortcuts and tenant-scoped data show first.
    """
    role = (get_user_role(request.user) or "").lower()
    school = get_request_school(request)
    is_op = is_operator(request.user)
    can_request_features = role not in ("parent", "student")
    from apps.portal.help_page_inbound import (
        feature_form_initial_from_request,
        parse_help_landing_inbound,
    )

    page_help_inbound = parse_help_landing_inbound(request)
    search_title = page_help_inbound.get("help_search_initial_q") or request.GET.get("q", "")
    recent_release_notes = list(
        ReleaseNote.objects.filter(
            is_public=True, published_at__isnull=False
        ).order_by("-published_at")[:5]
    )
    help_resources = suggest_help_resources(
        request,
        title=search_title,
        module=page_help_inbound.get("page_help_module") or request.GET.get("module", ""),
        category=request.GET.get("category", ""),
        limit=6,
    )
    open_support_count = 0
    if school is not None:
        try:
            from apps.siteconfig.models_feature_controls import GlobalSupportTicket

            open_support_count = GlobalSupportTicket.objects.filter(
                school=school,
                user=request.user,
                status__in=[
                    GlobalSupportTicket.Status.OPEN,
                    GlobalSupportTicket.Status.IN_PROGRESS,
                    GlobalSupportTicket.Status.WAITING,
                ],
            ).count()
        except Exception:
            open_support_count = 0
    pinned_feedback_route = "feedback:school_feedback"
    if role == "teacher":
        pinned_feedback_route = "feedback:teacher_feedback"
    elif role == "parent":
        pinned_feedback_route = "feedback:parent_feedback"
    elif role == "student":
        pinned_feedback_route = "feedback:student_feedback"

    feature_quick_form = FeatureRequestForm(
        initial=feature_form_initial_from_request(
            request,
            {
                "module": request.GET.get("module", ""),
                "title": request.GET.get("title", ""),
                "affected_roles": "ADMIN,TEACHER",
            },
        )
    )
    apply_bootstrap_form_styles(feature_quick_form)
    if (
        request.method == "POST"
        and request.POST.get("form_kind") == "feature_quick"
        and can_request_features
    ):
        feature_quick_form = FeatureRequestForm(request.POST)
        apply_bootstrap_form_styles(feature_quick_form)
        if feature_quick_form.is_valid():
            submit_feature_request(
                school=school,
                user=request.user,
                affected_roles=[
                    r.strip().upper()
                    for r in feature_quick_form.cleaned_data["affected_roles"].split(",")
                    if r.strip()
                ],
                **{
                    k: v
                    for k, v in feature_quick_form.cleaned_data.items()
                    if k != "affected_roles"
                },
            )
            messages.success(
                request,
                "Feature request received — track it in Feature center.",
            )
            return redirect("feedback:help_center")

    recent_features = []
    if can_request_features:
        fr_qs = FeatureRequest.objects.filter(  # tenant-isolation-allow: help-center-user-scoped-recent-features
            submitted_by=request.user,
        )
        if school is not None:
            fr_qs = fr_qs.filter(school=school)
        recent_features = list(fr_qs.order_by("-created_at")[:5])

    links = support_entry_points(request)
    deflection_urls = {}
    try:
        from django.urls import reverse

        deflection_urls = {
            "support_deflection_url": reverse("api:support-deflection"),
            "support_deflection_ack_url": reverse("api:support-deflection-ack"),
            "kb_search_url": reverse("kb:kb_search"),
            "kb_typeahead_url": reverse("api:kb-typeahead"),
        }
    except Exception:
        pass
    from apps.portal.help_unified_hub import tenant_community_lane
    from apps.portal.tenant_support_hub import build_tenant_support_hub_context

    community_lane = tenant_community_lane(request)
    support_hub = build_tenant_support_hub_context(request)
    help_section = (request.GET.get("section") or "").strip()
    return render(
        request,
        "feedback/help_center.html",
        {
            "role": role,
            "school": school,
            "community_lane": community_lane,
            "support_hub": support_hub,
            "help_section": help_section,
            "is_operator": is_op,
            "can_request_features": can_request_features,
            "release_notes": recent_release_notes,
            "pinned_feedback_route": pinned_feedback_route,
            "you_said_we_did": generate_you_said_we_did_items(school)[:5] if school else [],
            "help_resources": help_resources,
            "support_links": links,
            "open_support_count": open_support_count,
            "feature_quick_form": feature_quick_form,
            "recent_features": recent_features,
            "feature_center_url": links.get("feature_center") or "",
            "contact_center_url": links.get("contact_center") or "",
            **page_help_inbound,
            **deflection_urls,
        },
    )


def release_notes_public(request):
    """Public release-notes feed (no login required) — only `is_public=True` items.

    Tenant viewers see the same global feed (release notes are platform-level, not per-tenant).
    Operators see a richer view inside `feedback:product_roadmap`.
    """
    notes = list(
        ReleaseNote.objects.filter(
            is_public=True, published_at__isnull=False
        ).prefetch_related("feature_requests").order_by("-published_at")[:100]
    )
    return render(
        request,
        "feedback/release_notes_public.html",
        {"release_notes": notes},
    )
