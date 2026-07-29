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
from django.template.response import TemplateResponse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.schools.deploy_dispatch import dispatch_setup_email_for_school

from .control_plane import log_control_plane_action
from .models import School

logger = logging.getLogger(__name__)


def _active_owner_users(school):
    """Active (non-suspended) owner user objects for a school, primary first.

    The user-object sibling of ``deploy_dispatch._active_owner_emails`` (which
    returns addresses for the mail path). The onboarding claim link is built per
    USER, so the reveal path needs the accounts, not just the emails.
    """
    from apps.schools.models import SchoolMembership

    users = []
    seen: set = set()
    rows = (
        SchoolMembership.objects.filter(
            school=school, is_school_owner=True, suspended_at__isnull=True
        )
        .select_related("user")
        .order_by("-is_primary", "user__pk")
    )
    for membership in rows:
        user = getattr(membership, "user", None)
        if user is not None and getattr(user, "pk", None) is not None and user.pk not in seen:
            seen.add(user.pk)
            users.append(user)
    return users


@require_http_methods(["POST"])
def resend_owner_setup_email_view(request, school_id):
    school = School.objects.filter(pk=str(school_id)).first()
    if school is None:
        messages.error(request, _("School not found."))
        return redirect("super:dashboard")

    owner_user_ids = None
    raw_ids = request.POST.getlist("owner_user_ids")
    if raw_ids:
        parsed = []
        for raw in raw_ids:
            try:
                parsed.append(int(raw))
            except (TypeError, ValueError):
                continue
        if parsed:
            owner_user_ids = parsed

    result = dispatch_setup_email_for_school(school, owner_user_ids=owner_user_ids)

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


@require_http_methods(["POST"])
def reveal_owner_setup_link_view(request, school_id):
    """Surface the owner's one-time setup/claim link so an operator can deliver it
    OUT OF BAND when transactional email is not landing.

    The owner account is created with ``set_unusable_password()``; its ONLY claim
    path is the signed onboarding token, which normally ships in the welcome
    email. If mail is misconfigured (Brevo secrets empty) or bounces, the owner
    can never log in and nothing in the product recovers them — a hard dependency
    on one delivery channel. This reveals the SAME signed link the email would
    carry: the token IS the auth, so it works over any channel the operator
    trusts (support chat, phone, a verified alternate address).

    HIGH-sensitivity + audited: whoever holds the link can set the owner's
    password. POST-only so it can't be triggered by a bare link or prefetch, and
    operator-gated at the URL layer via ``require_super_access_with_host``.
    """
    school = School.objects.filter(pk=str(school_id)).first()
    if school is None:
        messages.error(request, _("School not found."))
        return redirect("super:dashboard")

    from apps.schools.provision_email_urls import build_owner_onboarding_url

    links = []
    for user in _active_owner_users(school):
        url = build_owner_onboarding_url(school, user)
        if url:
            links.append(
                {"email": (getattr(user, "email", "") or "").strip(), "url": url}
            )

    log_control_plane_action(
        request,
        action="READ",
        model_name="School",
        object_id=school.pk,
        object_repr=f"reveal owner setup link for {school.slug or school.pk}",
        reason="operator revealed the owner onboarding claim link for out-of-band delivery",
        sensitivity="HIGH",
        new_values={"owners": len(links)},
        changed_fields=["owner_setup_link_revealed"],
    )

    if not links:
        messages.warning(
            request,
            _(
                "No active owner with a resolvable account for this school — there "
                "is no claim link to reveal. Add or unsuspend an owner first."
            ),
        )
        return redirect("super:tenant_360", school_id=str(school.pk))

    return TemplateResponse(
        request,
        "schools/super_owner_setup_link.html",
        {"school": school, "links": links},
    )
