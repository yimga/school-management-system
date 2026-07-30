"""Operator action: resend the account setup / claim email to a tenant's users.

A clickable equivalent of ``manage.py resend_owner_setup_email`` for operators on
the tenant-360 page — but the operator SELECTS who receives it rather than
blasting every owner: pick specific owners and non-owner staff from the picker,
or target any single member (a parent / student not in the picker) by email
address. Each recipient is routed to the right email — an owner gets the "your
school is ready" welcome, a non-owner gets the generic set-password / claim link
(see ``deploy_dispatch.dispatch_setup_email_for_users``). The action reports
HONESTLY whether transactional mail is actually configured, and is audited.

Operator-gated at the URL layer via ``require_super_access_with_host`` — the same
gate every other tenant-360 action (approve / activate / freeze / requeue) uses —
and restricted to POST so it can't be triggered by a bare link/prefetch.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.schools.deploy_dispatch import dispatch_setup_email_for_users

from .control_plane import log_control_plane_action
from .models import School

logger = logging.getLogger(__name__)

# The staff picker is bounded so a school with hundreds of teachers doesn't render
# an unusable <select>; anyone beyond it (and the whole student / parent body) is
# reachable via the free-text email box, which resolves against ALL memberships.
_MEMBER_PICKER_LIMIT = 60


def addressable_member_options(school):
    """Members to offer in the operator "resend setup email" picker.

    Owners + non-owner STAFF (everything except the bulk student / parent
    population — those are reached via the email box, not a giant dropdown), owners
    first, each as a light dict for the template. Returns ``(rows, truncated)``;
    ``truncated`` is ``True`` when more staff exist than ``_MEMBER_PICKER_LIMIT``
    so the template can say so instead of silently dropping them.
    """
    from apps.platform_runtime.role_registry import ROLE_PARENT, ROLE_STUDENT
    from apps.schools.models import SchoolMembership

    bulk_roles = {ROLE_PARENT, ROLE_STUDENT}
    qs = (
        SchoolMembership.objects.filter(school=school, suspended_at__isnull=True)
        .exclude(role__in=bulk_roles)
        .select_related("user")
        .order_by("-is_school_owner", "-is_primary", "user__pk")
    )
    rows: list = []
    seen: set = set()
    # Pull one past the limit so we can tell whether the list was truncated.
    for m in qs[: _MEMBER_PICKER_LIMIT + 1]:
        user = getattr(m, "user", None)
        pk = getattr(user, "pk", None)
        if user is None or pk is None or pk in seen:
            continue
        seen.add(pk)
        label = (getattr(user, "email", "") or "").strip() or user.get_username()
        rows.append(
            {
                "pk": pk,
                "label": label,
                "role": m.role,
                "is_owner": bool(m.is_school_owner),
                "pending": not user.has_usable_password(),
            }
        )
    truncated = len(rows) > _MEMBER_PICKER_LIMIT
    return rows[:_MEMBER_PICKER_LIMIT], truncated


def _resolve_member_id(school, identifier):
    """The user-id of a NON-SUSPENDED member of ``school`` matching ``identifier``.

    ``identifier`` is a free-text email OR username. Resolution is scoped to this
    school's memberships, so the operator can only ever address a member of the
    school they are looking at — never an arbitrary or cross-tenant account.
    Returns ``None`` when nothing matches.
    """
    from apps.schools.models import SchoolMembership

    ident = (identifier or "").strip()
    if not ident:
        return None
    row = (
        SchoolMembership.objects.filter(school=school, suspended_at__isnull=True)
        .filter(Q(user__email__iexact=ident) | Q(user__username__iexact=ident))
        .select_related("user")
        .order_by("-is_school_owner", "user__pk")
        .first()
    )
    return getattr(row, "user_id", None) if row else None


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

    # Collect the selected recipients. ``user_ids`` is the new any-member field;
    # ``owner_user_ids`` is kept for backward compatibility with the prior
    # owner-only form. Every id is re-validated against this school's memberships
    # inside the dispatch, so a stray/foreign id can never trigger mail.
    selected_ids: list[int] = []
    for field in ("user_ids", "owner_user_ids"):
        for raw in request.POST.getlist(field):
            try:
                selected_ids.append(int(raw))
            except (TypeError, ValueError):
                continue

    # The free-text box lets the operator target ANY member (e.g. a parent or
    # student not shown in the staff picker) by email or username.
    typed = (request.POST.get("recipient_identifier") or "").strip()
    identifier_unresolved = False
    if typed:
        member_id = _resolve_member_id(school, typed)
        if member_id is not None:
            selected_ids.append(member_id)
        else:
            identifier_unresolved = True

    user_ids = list(dict.fromkeys(selected_ids)) or None

    # A typed address that matched nobody, with nothing else selected, is a
    # dead end — tell the operator instead of silently blasting all owners.
    if identifier_unresolved and user_ids is None:
        messages.warning(
            request,
            _(
                "No member of this school matches “%(id)s”. Check the address, "
                "or pick someone from the list."
            )
            % {"id": typed},
        )
        return redirect("super:tenant_360", school_id=str(school.pk))

    result = dispatch_setup_email_for_users(
        school, user_ids=user_ids, request=request
    )

    log_control_plane_action(
        request,
        action="UPDATE",
        model_name="School",
        object_id=school.pk,
        object_repr=f"resend setup email for {school.slug or school.pk}",
        reason="operator resent the account setup email to selected members",
        sensitivity="MEDIUM",
        new_values={
            "recipients": result.get("recipients", 0),
            "sent": result.get("sent", 0),
            "configured": result.get("configured"),
        },
        changed_fields=["account_setup_email"],
    )

    if result.get("recipients", 0) == 0:
        # Zero recipients resolved (e.g. an id that is not a member of this
        # school, or a suspended member) — there is nothing to queue, so say
        # that rather than a misleading "queued to 0 recipients".
        messages.warning(
            request,
            _(
                "No matching recipient with an email address for this school — "
                "nothing was sent. Select a member above, type their email in the "
                "box, or use the resend_owner_setup_email --email … command."
            ),
        )
    elif result.get("configured") is False:
        # The send was attempted + audited, but nothing will land until the
        # Brevo secrets are set — say so plainly instead of a false "sent".
        messages.warning(
            request,
            _(
                "Setup email queued to %(n)s recipient(s), but transactional "
                "email is NOT configured (Brevo EMAIL_HOST_USER / "
                "EMAIL_HOST_PASSWORD are empty), so it will not be delivered until "
                "those secrets are set."
            )
            % {"n": result.get("recipients", 0)},
        )
    else:
        messages.success(
            request,
            _("Setup email sent to %(n)s recipient(s).")
            % {"n": result.get("sent", 0)},
        )

    # A recognised selection went out, but a stray typed address matched nobody.
    if identifier_unresolved and user_ids is not None:
        messages.warning(
            request,
            _("“%(id)s” didn’t match anyone at this school and was skipped.")
            % {"id": typed},
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
