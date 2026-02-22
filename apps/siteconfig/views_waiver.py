# Optional: school-submitted waiver request (Phase E)
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django.http import HttpResponseForbidden

from apps.accounts.decorators import permission_required, login_required


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET", "POST"])
def request_waiver(request):
    """School admin submits a waiver request (reason + optional proof). Super Admin approves/denies in Django admin."""
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "Select your school (use your school subdomain) to request a waiver.")
        return redirect("portal:home")
    from .models import WaiverRequest
    if request.method == "POST":
        reason = (request.POST.get("reason") or "").strip()
        if not reason:
            messages.error(request, "Please provide a reason for the waiver request.")
            return redirect("siteconfig:request_waiver")
        proof_file = request.FILES.get("proof_file")
        wr = WaiverRequest.objects.create(
            school=school,
            reason=reason,
            status=WaiverRequest.Status.PENDING,
        )
        if proof_file:
            wr.proof_file = proof_file
            wr.save(update_fields=["proof_file", "updated_at"])
        messages.success(request, "Waiver request submitted. A Super Admin will review it.")
        return redirect("siteconfig:request_waiver")
    pending = WaiverRequest.objects.filter(school=school).order_by("-created_at")[:10]
    return render(request, "siteconfig/request_waiver.html", {
        "school": school,
        "pending_requests": pending,
    })
