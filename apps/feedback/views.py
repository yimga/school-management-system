from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import FeatureRequestForm, FeedbackSubmissionForm, RoleFeedbackForm, SurveyResponseForm
from .models import FeatureRequest, FeedbackSubmission, ReleaseNote, RoadmapItem, SurveyResponse
from .services import (
    convert_feedback_to_feature_request,
    create_roadmap_item_from_request,
    detect_churn_risk_signals,
    generate_you_said_we_did_items,
    get_request_school,
    get_user_role,
    is_operator,
    module_sentiment_summary,
    submit_feature_request,
    submit_feedback,
    summarize_feedback_by_role,
    summarize_feedback_by_school,
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
                submit_feedback(school=context["school"], user=request.user, **feedback_form.cleaned_data)
                messages.success(request, "Feedback submitted.")
                return redirect("feedback:school_feedback")
    else:
        form = FeatureRequestForm()
        feedback_form = FeedbackSubmissionForm(initial={"route": request.GET.get("route", ""), "module": request.GET.get("module", "")})
    context.update({"feedback_form": feedback_form, "feature_form": form})
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
            submit_feedback(school=school, user=request.user, **form.cleaned_data)
            messages.success(request, "Feedback submitted.")
            return redirect(f"feedback:{role}_feedback")
    else:
        privacy = FeedbackSubmission.PrivacyLevel.SCHOOL_PRIVATE
        form = RoleFeedbackForm(
            initial={"route": request.GET.get("route", ""), "privacy_level": privacy},
            role_categories=categories,
        )
    items = visible_feedback_for_user(request.user, school)[:20]
    return render(
        request,
        "feedback/role_center.html",
        {"form": form, "role_surface": role, "school": school, "feedback_items": items},
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
    )
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
    qs = FeedbackSubmission.objects.select_related("school", "user", "assigned_to")
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
            "feedback_items": qs[:100],
            "feature_requests": FeatureRequest.objects.select_related("school").all()[:100],
            "roadmap_candidates": RoadmapItem.objects.filter(status=RoadmapItem.Status.UNDER_REVIEW)[:50],
            "by_school": summarize_feedback_by_school(),
            "by_role": summarize_feedback_by_role(),
            "pain_points": top_pain_points(),
            "sentiment": module_sentiment_summary(),
            "churn_risk": detect_churn_risk_signals(),
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
