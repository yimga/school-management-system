"""The queue where a box's request to create a person gets answered.

This is the human half of the identity handshake. The rail refuses to create
anybody who needs a login; the refusal is recorded as a ProvisioningRequest; and
this is the screen where an authorised person says yes or no. Without it the
whole mechanism is a table nobody reads, which is the defect it was built to fix
wearing different clothes.

Gated on ``staff.provision`` rather than a staff-editing permission. Editing a
phone number and bringing a new account into existence are different decisions --
that distinction is the entire reason the sync rail refuses the insert in the
first place, so the surface that resolves it must not be reachable by the weaker
of the two.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import require_permission
from apps.people.models_provisioning import ProvisioningRequest
from apps.people.provisioning_service import (
    approve_provisioning_request,
    decline_provisioning_request,
)
from apps.schools.mixins import require_school

_PAGE_SIZE = 25  # magic-number-allow: provisioning-queue-page-size


def _scoped(request):
    """Requests for THIS school only.

    The tenant bound is the security boundary of the whole screen: a pk in a URL
    must not reach another school's queue, and approving one would mint an
    account in a tenant the operator has no business in.
    """
    return ProvisioningRequest.objects.filter(school=request.school).select_related(
        "decided_by", "created_user"
    )


@login_required
@require_school
@require_permission("staff.provision")
@require_http_methods(["GET"])
def provisioning_queue(request):
    status = (request.GET.get("status") or ProvisioningRequest.Status.PENDING).upper()
    qs = _scoped(request)
    if status in dict(ProvisioningRequest.Status.choices):
        qs = qs.filter(status=status)
    else:
        status = ""

    page_obj = Paginator(qs.order_by("-last_seen_at"), _PAGE_SIZE).get_page(
        request.GET.get("page")
    )

    from apps.accounts.models import User
    from apps.people.bulk_staff_actions import FORBIDDEN_ROLES

    return render(
        request,
        "people/provisioning_queue.html",
        {
            "title": _("Access requests"),
            "requests": page_obj.object_list,
            "page_obj": page_obj,
            "selected_status": status,
            "status_choices": ProvisioningRequest.Status.choices,
            "pending_count": _scoped(request)
            .filter(status=ProvisioningRequest.Status.PENDING)
            .count(),
            # The role a request is approved with is chosen here, not taken from
            # the box: what arrived is what the box CALLED the person.
            "assignable_roles": [
                (value, label)
                for value, label in User.Role.choices
                if value not in FORBIDDEN_ROLES
            ],
        },
    )


@login_required
@require_school
@require_permission("staff.provision")
@require_http_methods(["POST"])
def provisioning_approve(request, pk):
    row = get_object_or_404(_scoped(request), pk=pk)
    try:
        approve_provisioning_request(
            row,
            actor=request.user,
            role=request.POST.get("role") or "",
            student_id=(request.POST.get("student_id") or "").strip() or None,
        )
    except ValueError as exc:
        # The refusals are the useful part of this screen -- "choose which
        # student", "that role cannot be granted" -- so they are shown as written
        # rather than flattened into "could not approve".
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            _("%(name)s was created. They cannot sign in until you invite them.")
            % {"name": row.display_name},
        )
    return HttpResponseRedirect(reverse("accounts:provisioning_queue"))


@login_required
@require_school
@require_permission("staff.provision")
@require_http_methods(["POST"])
def provisioning_decline(request, pk):
    row = get_object_or_404(_scoped(request), pk=pk)
    try:
        decline_provisioning_request(
            row, actor=request.user, reason=request.POST.get("reason") or ""
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            _("%(name)s was declined. The box will stop asking.")
            % {"name": row.display_name},
        )
    return HttpResponseRedirect(reverse("accounts:provisioning_queue"))
