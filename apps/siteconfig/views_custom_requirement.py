# Request-to-Feature: school submits a CustomFeatureTicket (plan 3.20, Powerhouse)
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required, login_required

from .models_platform_catalog import CustomFeatureTicket, get_feature_fragment_cap


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET", "POST"])
def request_custom_requirement(request):
    """
    School admin submits a custom feature/requirement request.
    Creates CustomFeatureTicket; Super Admin (or AI) can later create a FeatureFragment.
    Plan cap (Basic 0, Pro 2, Enterprise 5) is enforced when creating fragments, not when submitting requests.
    """
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "Select your school to submit a custom requirement.")
        return redirect("portal:home")

    cap = get_feature_fragment_cap(school)
    _can_request = (
        cap is None or cap > 0
    )  # Basic has cap 0; we still allow submitting the request
    upgrade_message = None
    if cap == 0:
        upgrade_message = (
            "Your current plan does not include custom feature fragments. "
            "Upgrade to Pro or Enterprise to have custom features built and deployed for your school."
        )

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        if not title:
            messages.error(request, "Please provide a title for your request.")
            return redirect("siteconfig:request_custom_requirement")
        _ticket = CustomFeatureTicket.objects.create(
            school=school,
            title=title,
            description=description,
            status=CustomFeatureTicket.Status.SUBMITTED,
            created_by=request.user,
        )
        messages.success(
            request,
            "Your custom requirement has been submitted. Our team will review it and get back to you.",
        )
        return redirect("siteconfig:request_custom_requirement")

    recent = CustomFeatureTicket.objects.filter(school=school).order_by("-created_at")[
        :10
    ]
    return render(
        request,
        "siteconfig/request_custom_requirement.html",
        {
            "school": school,
            "recent_tickets": recent,
            "upgrade_message": upgrade_message,
            "fragment_cap": cap,
        },
    )
