"""Operator action: resend the owner setup / "school is ready" email for a tenant.

A clickable equivalent of ``manage.py resend_owner_setup_email`` for operators on
the tenant-360 page: dispatch the owner-setup email to a school's active owners
(``send_welcome_email`` routes an owner who hasn't claimed a credential into the
onboarding wizard), report HONESTLY whether transactional mail is actually
configured, and audit the action.

Operator-gated at the URL layer via ``require_super_access_with_host`` — the same
gate every other tenant-360 action (approve / activate / freeze / requeue) uses —
and restricted to POST so it can't be triggered by a bare link/prefetch.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.schools.deploy_dispatch import dispatch_setup_email_for_school

from .control_plane import log_control_plane_action
from .models import School

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
def resend_owner_setup_email_view(request, school_id):
    school = School.objects.filter(pk=str(school_id)).first()
    if school is None:
        messages.error(request, _("School not found."))
        return redirect("super:dashboard")

    result = dispatch_setup_email_for_school(school)

    log_control_plane_action(
        request,
        action="UPDATE",
        model_name="School",
        object_id=school.pk,
        object_repr=f"resend owner setup email for {school.slug or school.pk}",
        reason="operator resent the owner setup email",
        sensitivity="MEDIUM",
        new_values={
            "recipients": result.get("recipients", 0),
            "sent": result.get("sent", 0),
            "configured": result.get("configured"),
        },
        changed_fields=["owner_setup_email"],
    )

    if result.get("configured") is False:
        # The send was attempted + audited, but nothing will land until the
        # Brevo secrets are set — say so plainly instead of a false "sent".
        messages.warning(
            request,
            _(
                "Owner setup email queued to %(n)s owner(s), but transactional "
                "email is NOT configured (Brevo EMAIL_HOST_USER / "
                "EMAIL_HOST_PASSWORD are empty), so it will not be delivered until "
                "those secrets are set."
            )
            % {"n": result.get("recipients", 0)},
        )
    elif result.get("recipients", 0) == 0:
        messages.warning(
            request,
            _(
                "No active owner with an email address for this school — nothing "
                "was sent. Add or unsuspend an owner, or use the "
                "resend_owner_setup_email --email … command."
            ),
        )
    else:
        messages.success(
            request,
            _("Owner setup email sent to %(n)s owner(s).")
            % {"n": result.get("sent", 0)},
        )

    return redirect("super:tenant_360", school_id=str(school.pk))
