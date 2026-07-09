"""Tenant Identity & Access hub — school-scoped staff roster and lifecycle."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.iam_pdp_guards import (
    tenant_identity_hub_pdp,
    tenant_regulator_grant_pdp,
)
from apps.accounts.models import TenantStaffInvite, User
from apps.accounts.iam_localization import localized_government_body_label

logger = logging.getLogger(__name__)
from apps.accounts.tenant_identity import (
    localized_role_for_user,
    mfa_enrolled_for_user,
    school_mfa_compliance_rows,
    user_has_school_membership,
)
from apps.schools.mixins import require_school
from apps.schools.models import SchoolMembership
from services.post_delete_navigation import (
    mutation_return_url,
    redirect_after_delete,
    redirect_after_detail_mutation,
    redirect_after_save,
)


_IDENTITY_HUB_MANAGE_ROLES = frozenset(
    {"ADMIN", "LEADERSHIP", "IT_ADMIN", "PRINCIPAL", "VICE_PRINCIPAL"}
)


def _can_manage_tenant_identity(user, school) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not user_has_school_membership(user, school):
        return False
    if getattr(user, "is_superuser", False):
        return True
    membership = SchoolMembership.objects.filter(
        user_id=user.pk, school_id=school.pk
    ).first()
    if membership is not None and membership.suspended_at is not None:
        # Suspended members retain their row but hold no management authority.
        return False
    if membership and str(membership.role or "").strip().upper() in _IDENTITY_HUB_MANAGE_ROLES:
        return True
    try:
        from apps.accounts.rebac import feature_permission_allowed

        return feature_permission_allowed(user, "settings.manage", school=school)
    except Exception:
        return False


def _is_school_owner(user, school) -> bool:
    """Ownership gate for transfer/grant/release.

    Deliberately STRICTER than ``_can_manage_tenant_identity``: changing who owns
    the tenant is an authority-bearing act, so it must require *actual ownership*
    (the per-school ``is_school_owner`` flag), never the broad identity-hub manage
    role set (which admits IT_ADMIN / VICE_PRINCIPAL / LEADERSHIP and would be a
    privilege-escalation path into ownership). Platform superusers are allowed for
    support/recovery.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return SchoolMembership.objects.filter(
        school_id=school.pk, user_id=user.pk, is_school_owner=True,
        suspended_at__isnull=True,
    ).exists()


def _audit_ownership(request, school, action: str, target_user_id) -> None:
    """Record an ownership change in the security trail (no PII in logs)."""
    try:
        from apps.accounts.models import SecurityAuditLog
        from apps.accounts.security_audit import log_security_event

        log_security_event(
            request.user,
            SecurityAuditLog.EventType.OWNERSHIP_CHANGED,
            request=request,
            school=school,
        )
    except Exception:
        logger.warning(
            "tenant_ownership.audit_failed action=%s", action, exc_info=True
        )
    # PK-only structured line — no usernames/emails (passes pii-logging-smell gate).
    logger.info(
        "tenant_ownership.%s actor=%s target=%s school=%s",
        action,
        getattr(request.user, "pk", None),
        target_user_id,
        getattr(school, "pk", None),
    )


def _revoke_user_sessions(user_id) -> int:
    """Delete all live sessions belonging to a user. Returns the count revoked.

    Used to kick a member out immediately when they're suspended, so a suspension
    takes effect on their current browser tabs, not just future requests.
    """
    now = timezone.now()
    revoked = 0
    user_pk_str = str(user_id)
    for session in Session.objects.filter(expire_date__gte=now):
        try:
            data = session.get_decoded()
            if str(data.get("_auth_user_id")) == user_pk_str:
                session.delete()
                revoked += 1
        except Exception:  # noqa: BLE001 — a corrupt session must not block the sweep
            continue
    return revoked


@login_required
@require_school
@require_GET
@tenant_identity_hub_pdp
def tenant_identity_roster(request):
    school = request.school
    if not _can_manage_tenant_identity(request.user, school):
        return HttpResponseForbidden("Not permitted.")
    qs = (
        SchoolMembership.objects.filter(school=school)
        .select_related("user")
        .order_by("-is_primary", "user__username")
    )
    page_obj = Paginator(qs, 25).get_page(request.GET.get("page"))
    mfa_rows = {r["user"].pk: r["mfa_ok"] for r in school_mfa_compliance_rows(school)}
    rows = []
    for membership in page_obj.object_list:
        user = membership.user
        rows.append(
            {
                "membership": membership,
                "user": user,
                "effective_role": localized_role_for_user(user, school),
                "role_code": membership.role or "",
                "is_owner": membership.is_school_owner,
                "mfa_ok": mfa_rows.get(user.pk, mfa_enrolled_for_user(user)),
                "detail_url": reverse(
                    "accounts:tenant_identity_detail", args=[user.pk]
                ),
            }
        )
    compliance = school_mfa_compliance_rows(school)
    enrolled = sum(1 for r in compliance if r["mfa_ok"])
    return render(
        request,
        "accounts/tenant_identity_roster.html",
        {
            "school": school,
            "page_obj": page_obj,
            "rows": rows,
            "mfa_enrolled_count": enrolled,
            "mfa_total_count": len(compliance),
            "invite_url": reverse("accounts:tenant_identity_invite"),
            "regulator_url": reverse("accounts:tenant_identity_regulator_grant"),
            "gov_body_label": localized_government_body_label(
                school, default=_("Regulatory authority")
            ),
            "trust_hub_url": reverse("accounts:security_trust_hub"),
            "rbac_url": reverse("accounts:rbac"),
        },
    )


@login_required
@require_school
@require_GET
def tenant_identity_detail(request, user_id: int):
    school = request.school
    if not _can_manage_tenant_identity(request.user, school):
        return HttpResponseForbidden("Not permitted.")
    user = get_object_or_404(User, pk=user_id)
    membership = get_object_or_404(SchoolMembership, school=school, user=user)
    sessions = []
    now = timezone.now()
    for session in Session.objects.filter(expire_date__gte=now).order_by("-expire_date")[
        :100
    ]:
        try:
            data = session.get_decoded()
            if str(data.get("_auth_user_id")) == str(user.pk):
                sessions.append(
                    {
                        "key_prefix": (session.session_key or "")[:8] + "…",
                        "expire_date": session.expire_date,
                    }
                )
        except Exception:
            continue
    roster_url = reverse("accounts:tenant_identity_roster")
    detail_url = reverse("accounts:tenant_identity_detail", args=[user.pk])
    return_url = mutation_return_url(request, roster_url, list_url=roster_url)
    detail_return_url = mutation_return_url(request, detail_url, list_url=detail_url)
    caller_is_owner = _is_school_owner(request.user, school)
    owner_count = SchoolMembership.objects.filter(
        school=school, is_school_owner=True
    ).count()
    return render(
        request,
        "accounts/tenant_identity_detail.html",
        {
            "school": school,
            "staff_user": user,
            "membership": membership,
            "effective_role": localized_role_for_user(user, school),
            "role_code": membership.role,
            "mfa_ok": mfa_enrolled_for_user(user),
            "sessions": sessions,
            "roster_url": roster_url,
            "return_url": return_url,
            "detail_return_url": detail_return_url,
            "can_manage": _can_manage_tenant_identity(request.user, school),
            # Ownership controls — only an actual owner may transfer/grant/release.
            "caller_is_owner": caller_is_owner,
            "target_is_owner": membership.is_school_owner,
            "target_is_self": request.user.pk == user.pk,
            "owner_count": owner_count,
            "grant_ownership_url": reverse(
                "accounts:tenant_identity_grant_ownership", args=[user.pk]
            ),
            "revoke_ownership_url": reverse(
                "accounts:tenant_identity_revoke_ownership", args=[user.pk]
            ),
            "transfer_ownership_url": reverse(
                "accounts:tenant_identity_transfer_ownership", args=[user.pk]
            ),
            "offboard_url": reverse(
                "accounts:tenant_identity_offboard", args=[user.pk]
            ),
            "revoke_sessions_url": reverse(
                "accounts:tenant_identity_revoke_sessions", args=[user.pk]
            ),
            "suspend_url": reverse(
                "accounts:tenant_identity_suspend", args=[user.pk]
            ),
            "reactivate_url": reverse(
                "accounts:tenant_identity_reactivate", args=[user.pk]
            ),
            "target_is_suspended": membership.suspended_at is not None,
            "rbac_url": reverse("accounts:rbac"),
            "regulator_url": reverse("accounts:tenant_identity_regulator_grant"),
            "gov_body_label": localized_government_body_label(
                school, default=_("Regulatory authority")
            ),
        },
    )


@login_required
@require_school
@require_http_methods(["GET", "POST"])
@tenant_regulator_grant_pdp
def tenant_identity_regulator_grant(request):
    """Time-boxed read-only access for external regulators (TemporaryRoleGrant)."""
    from datetime import datetime, time

    from apps.accounts.models import AccessRole, TemporaryRoleGrant

    school = request.school
    if not _can_manage_tenant_identity(request.user, school):
        return HttpResponseForbidden("Not permitted.")
    auditor_role, _created = AccessRole.objects.get_or_create(
        school=school,
        code="regulatory_auditor",
        defaults={
            "name": "Regulatory auditor (read-only)",
            "description": "Time-boxed external inspection access.",
        },
    )
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        days_raw = (request.POST.get("days") or "1").strip()
        try:
            days = max(1, min(30, int(days_raw)))
        except ValueError:
            days = 1
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            messages.error(
                request,
                _("No user with that email. Invite them as staff first, then grant access."),
            )
            return redirect("accounts:tenant_identity_regulator_grant")
        if not user_has_school_membership(user, school):
            messages.error(
                request,
                _("User must be a school member before regulator access can be granted."),
            )
            return redirect("accounts:tenant_identity_regulator_grant")
        expires_date = timezone.localdate() + timedelta(days=days)
        expires_at = timezone.make_aware(
            datetime.combine(expires_date, time(23, 59, 59)),
            timezone.get_current_timezone(),
        )
        TemporaryRoleGrant.objects.create(
            user=user,
            role=auditor_role,
            expires_at=expires_at,
            created_by=request.user,
            notes=f"Regulator access {days}d",
        )
        messages.success(
            request,
            _("Regulator read-only access granted to %(email)s until %(date)s.")
            % {"email": email, "date": expires_date.isoformat()},
        )
        roster_url = reverse("accounts:tenant_identity_roster")
        return redirect_after_save(request, roster_url, list_url=roster_url)
    return render(
        request,
        "accounts/tenant_identity_regulator_grant.html",
        {
            "school": school,
            "roster_url": reverse("accounts:tenant_identity_roster"),
            "gov_body_label": localized_government_body_label(
                school, default=_("Regulatory authority")
            ),
        },
    )


@login_required
@require_school
@require_http_methods(["GET", "POST"])
def tenant_identity_invite(request):
    school = request.school
    if not _can_manage_tenant_identity(request.user, school):
        return HttpResponseForbidden("Not permitted.")
    role_choices = [
        (c[0], c[1])
        for c in User.Role.choices
        if c[0] in ("ADMIN", "TEACHER", "LEADERSHIP", "IT_ADMIN", "SECRETARY")
    ]
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        role = (request.POST.get("role") or "TEACHER").strip().upper()
        if not email or "@" not in email:
            messages.error(request, _("Valid email required."))
            return redirect("accounts:tenant_identity_invite")
        valid_roles = {c[0] for c in role_choices}
        if role not in valid_roles:
            role = "TEACHER"
        invite = TenantStaffInvite.objects.create(
            school=school,
            email=email,
            role=role,
            invited_by=request.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        accept_url = request.build_absolute_uri(
            reverse("accounts:tenant_staff_invite_accept", kwargs={"token": invite.token})
        )
        # Audit C5 — actually email the invite link (previously only flashed).
        school_name = getattr(school, "name", "") or "your school"
        emailed = False
        try:
            from apps.schoolops.email_delivery import send_transactional

            res = send_transactional(
                subject=_("You're invited to join %(school)s on RunMyCampus")
                % {"school": school_name},
                body=_(
                    "You have been invited to join %(school)s as %(role)s.\n\n"
                    "Accept your invitation (valid 7 days):\n%(url)s\n"
                ) % {"school": school_name, "role": role, "url": accept_url},
                to=[email],
                priority="transactional",
                school=school,
                allow_suppressed=True,
                idempotency_key=f"staff_invite:{invite.token}",
            )
            emailed = bool(res.get("ok") or res.get("queued"))
        except Exception:  # noqa: BLE001 — invite still usable via the link
            logger.warning("accounts.staff_invite_email_failed")
        if emailed:
            messages.success(
                request,
                _("Staff invite emailed to %(email)s. Link: %(url)s")
                % {"email": email, "url": accept_url},
            )
        else:
            messages.success(
                request,
                _("Staff invite created. Share this link: %(url)s") % {"url": accept_url},
            )
        roster_url = reverse("accounts:tenant_identity_roster")
        return redirect_after_save(request, roster_url, list_url=roster_url)
    return render(
        request,
        "accounts/tenant_identity_invite.html",
        {
            "school": school,
            "role_choices": role_choices,
            "roster_url": reverse("accounts:tenant_identity_roster"),
        },
    )


@login_required
@require_school
@require_POST
def tenant_identity_revoke_sessions(request, user_id: int):
    """Revoke all active sessions for a school staff member (admin action)."""
    school = request.school
    if not _can_manage_tenant_identity(request.user, school):
        return HttpResponseForbidden("Not permitted.")
    user = get_object_or_404(User, pk=user_id)
    if not user_has_school_membership(user, school):
        return HttpResponseForbidden("User is not a member of this school.")
    now = timezone.now()
    revoked = 0
    user_pk_str = str(user.pk)
    for session in Session.objects.filter(expire_date__gte=now):
        try:
            data = session.get_decoded()
            if str(data.get("_auth_user_id")) == user_pk_str:
                session.delete()
                revoked += 1
        except Exception:
            continue
    try:
        from apps.accounts.security_audit import log_security_event
        from apps.accounts.models import SecurityAuditLog

        log_security_event(
            request.user,
            SecurityAuditLog.EventType.SESSION_REVOKED,
            request=request,
            school=school,
        )
    except Exception:
        pass
    messages.success(
        request,
        _("Revoked %(count)s active session(s) for %(user)s.")
        % {"count": revoked, "user": user.get_username()},
    )
    detail_url = reverse("accounts:tenant_identity_detail", args=[user_id])
    return redirect_after_detail_mutation(request, detail_url)


@login_required
@require_school
@require_POST
def tenant_identity_offboard(request, user_id: int):
    school = request.school
    if not _can_manage_tenant_identity(request.user, school):
        return HttpResponseForbidden("Not permitted.")
    if request.user.pk == user_id:
        messages.error(request, _("You cannot offboard yourself."))
        detail_url = reverse("accounts:tenant_identity_detail", args=[user_id])
        return redirect_after_detail_mutation(request, detail_url)
    membership = get_object_or_404(SchoolMembership, school=school, user_id=user_id)
    membership.delete()
    messages.success(request, _("Staff member removed from this school."))
    roster_url = reverse("accounts:tenant_identity_roster")
    return redirect_after_delete(request, roster_url, list_url=roster_url)


def _owner_detail_redirect(request, user_id):
    return redirect_after_detail_mutation(
        request, reverse("accounts:tenant_identity_detail", args=[user_id])
    )


@login_required
@require_school
@require_POST
def tenant_identity_grant_ownership(request, user_id: int):
    """Make another active member a co-owner (multi-owner is allowed).

    Owner-gated. Granting ownership also ensures the target carries the ADMIN role
    (owners are admin-like). Caller keeps their own ownership.
    """
    school = request.school
    if not _is_school_owner(request.user, school):
        return HttpResponseForbidden("Only a school owner can grant ownership.")
    with transaction.atomic():
        target = get_object_or_404(
            SchoolMembership.objects.select_for_update(),
            school=school,
            user_id=user_id,
        )
        if target.is_school_owner:
            messages.info(request, _("That member is already an owner."))
        else:
            target.is_school_owner = True
            update_fields = ["is_school_owner", "updated_at"]
            if str(target.role or "").strip().upper() != User.Role.ADMIN:
                target.role = User.Role.ADMIN
                update_fields.append("role")
            target.save(update_fields=update_fields)
            _audit_ownership(request, school, "grant", target.user_id)
            messages.success(
                request, _("Ownership granted — this member is now a co-owner.")
            )
    return _owner_detail_redirect(request, user_id)


@login_required
@require_school
@require_POST
def tenant_identity_revoke_ownership(request, user_id: int):
    """Remove a member's ownership (or step yourself down).

    Owner-gated, with a hard last-owner guard: a school can never be left with
    zero owners. The target's other roles/membership are untouched — only the
    owner flag is cleared.
    """
    school = request.school
    if not _is_school_owner(request.user, school):
        return HttpResponseForbidden("Only a school owner can change ownership.")
    with transaction.atomic():
        target = get_object_or_404(
            SchoolMembership.objects.select_for_update(),
            school=school,
            user_id=user_id,
        )
        if not target.is_school_owner:
            messages.info(request, _("That member is not an owner."))
            return _owner_detail_redirect(request, user_id)
        # Last-owner guard — lock the owner rows so two concurrent revokes can't
        # both read "2 owners" and race the school down to zero.
        owner_count = (
            SchoolMembership.objects.select_for_update()
            .filter(school=school, is_school_owner=True)
            .count()
        )
        if owner_count <= 1:
            messages.error(
                request,
                _(
                    "You can't remove the last owner. Grant ownership to another "
                    "member first, then remove this one."
                ),
            )
            return _owner_detail_redirect(request, user_id)
        target.is_school_owner = False
        target.save(update_fields=["is_school_owner", "updated_at"])
        _audit_ownership(request, school, "revoke", target.user_id)
        if target.user_id == request.user.pk:
            messages.success(request, _("You have stepped down as owner."))
        else:
            messages.success(request, _("Ownership removed from this member."))
    return _owner_detail_redirect(request, user_id)


@login_required
@require_school
@require_POST
def tenant_identity_transfer_ownership(request, user_id: int):
    """Transfer ownership to a chosen member and step down — atomically.

    The headline "release the role to a chosen person" action. The target becomes
    an owner (and ADMIN) and the caller relinquishes their own ownership in the
    same transaction. Because the target is promoted before the caller steps down,
    the school always retains at least one owner.
    """
    school = request.school
    if not _is_school_owner(request.user, school):
        return HttpResponseForbidden("Only a school owner can transfer ownership.")
    if request.user.pk == user_id:
        messages.error(request, _("Choose a different member to transfer ownership to."))
        return _owner_detail_redirect(request, user_id)
    with transaction.atomic():
        # Transfer means "hand off MY ownership", so the caller must actually hold
        # an owner membership here. A platform superuser doing support/recovery has
        # no membership to step down from — point them at "Make co-owner" instead,
        # which assigns ownership without implying the actor relinquishes any.
        caller = (
            SchoolMembership.objects.select_for_update()
            .filter(school=school, user_id=request.user.pk, is_school_owner=True)
            .first()
        )
        if caller is None:
            messages.error(
                request,
                _(
                    "Use “Make co-owner” to assign an owner — transfer "
                    "steps you down, and you don't currently hold ownership of this "
                    "school."
                ),
            )
            return _owner_detail_redirect(request, user_id)
        target = get_object_or_404(
            SchoolMembership.objects.select_for_update(),
            school=school,
            user_id=user_id,
        )
        # Promote the chosen member to owner (+ ADMIN) FIRST, so the school always
        # retains at least one owner across the handoff.
        target_fields = ["is_school_owner", "updated_at"]
        if not target.is_school_owner:
            target.is_school_owner = True
        if str(target.role or "").strip().upper() != User.Role.ADMIN:
            target.role = User.Role.ADMIN
            target_fields.append("role")
        target.save(update_fields=target_fields)
        # Step the caller down.
        caller.is_school_owner = False
        caller.save(update_fields=["is_school_owner", "updated_at"])
        _audit_ownership(request, school, "transfer", target.user_id)
        messages.success(
            request,
            _(
                "Ownership transferred. You remain an admin; the new owner now "
                "controls the school."
            ),
        )
    return _owner_detail_redirect(request, user_id)


@login_required
@require_school
@require_POST
def tenant_identity_suspend(request, user_id: int):
    """Suspend a member: revoke their management/ownership authority AND kill their
    active sessions, without deleting the membership (reversible via reactivate).

    Owner-gated — a suspend can strip an admin/owner of power, so it requires real
    ownership. Guards mirror revoke-ownership: you can't suspend yourself, and you
    can't suspend the last ACTIVE owner (grant/transfer ownership first).
    """
    school = request.school
    if not _is_school_owner(request.user, school):
        return HttpResponseForbidden("Only a school owner can suspend a member.")
    if request.user.pk == user_id:
        messages.error(request, _("You cannot suspend yourself."))
        return _owner_detail_redirect(request, user_id)
    with transaction.atomic():
        target = get_object_or_404(
            SchoolMembership.objects.select_for_update(),
            school=school,
            user_id=user_id,
        )
        if target.suspended_at is not None:
            messages.info(request, _("That member is already suspended."))
            return _owner_detail_redirect(request, user_id)
        if target.is_school_owner:
            active_owner_count = (
                SchoolMembership.objects.select_for_update()
                .filter(
                    school=school, is_school_owner=True, suspended_at__isnull=True
                )
                .count()
            )
            if active_owner_count <= 1:
                messages.error(
                    request,
                    _(
                        "You can't suspend the last active owner. Grant ownership to "
                        "another member first, then suspend this one."
                    ),
                )
                return _owner_detail_redirect(request, user_id)
        target.suspended_at = timezone.now()
        target.save(update_fields=["suspended_at", "updated_at"])
        _audit_ownership(request, school, "suspend", target.user_id)
    # Kick the member out of any live sessions so the suspension is immediate.
    _revoke_user_sessions(user_id)
    messages.success(
        request,
        _("Member suspended — their access is revoked until you reactivate them."),
    )
    return _owner_detail_redirect(request, user_id)


@login_required
@require_school
@require_POST
def tenant_identity_reactivate(request, user_id: int):
    """Reactivate a suspended member — restore their authority (owner-gated)."""
    school = request.school
    if not _is_school_owner(request.user, school):
        return HttpResponseForbidden("Only a school owner can reactivate a member.")
    with transaction.atomic():
        target = get_object_or_404(
            SchoolMembership.objects.select_for_update(),
            school=school,
            user_id=user_id,
        )
        if target.suspended_at is None:
            messages.info(request, _("That member is not suspended."))
            return _owner_detail_redirect(request, user_id)
        target.suspended_at = None
        target.save(update_fields=["suspended_at", "updated_at"])
        _audit_ownership(request, school, "reactivate", target.user_id)
    messages.success(request, _("Member reactivated — their access is restored."))
    return _owner_detail_redirect(request, user_id)


@require_http_methods(["GET", "POST"])
def tenant_staff_invite_accept(request, token):
    """Accept tenant staff invite (pre-auth allowed)."""
    invite = get_object_or_404(TenantStaffInvite, token=token)
    if not invite.is_pending:
        messages.error(request, _("Invite expired or already used."))
        return redirect("accounts:login")
    school = invite.school
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        password2 = request.POST.get("password2") or ""
        if not username or len(password) < 8:
            messages.error(request, _("Username and password (8+ chars) required."))
            return render(
                request,
                "accounts/tenant_staff_invite_accept.html",
                {"invite": invite, "school": school},
            )
        if password != password2:
            messages.error(request, _("Passwords do not match."))
            return render(
                request,
                "accounts/tenant_staff_invite_accept.html",
                {"invite": invite, "school": school},
            )
        UserModel = get_user_model()
        with transaction.atomic():
            user, created = UserModel.objects.get_or_create(
                username=username,
                defaults={"email": invite.email, "is_active": True},
            )
            if not created and user.email.lower() != invite.email.lower():
                messages.error(
                    request,
                    _("Username exists with a different email. Contact your school admin."),
                )
                return render(
                    request,
                    "accounts/tenant_staff_invite_accept.html",
                    {"invite": invite, "school": school},
                )
            user.set_password(password)
            user.email = invite.email
            user.is_active = True
            if hasattr(user, "role"):
                user.role = invite.role
            user.save()
            SchoolMembership.objects.update_or_create(
                user=user,
                school=school,
                defaults={"role": invite.role, "is_primary": True},
            )
            invite.accepted_at = timezone.now()
            invite.save(update_fields=["accepted_at"])
        messages.success(
            request,
            _("Account ready. Sign in to access %(school)s.")
            % {"school": school.name},
        )
        return redirect("accounts:login")
    return render(
        request,
        "accounts/tenant_staff_invite_accept.html",
        {"invite": invite, "school": school},
    )
