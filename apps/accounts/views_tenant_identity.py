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
    if membership and str(membership.role or "").strip().upper() in _IDENTITY_HUB_MANAGE_ROLES:
        return True
    try:
        from apps.accounts.rebac import feature_permission_allowed

        return feature_permission_allowed(user, "settings.manage", school=school)
    except Exception:
        return False


@tenant_identity_hub_pdp
@login_required
@require_school
@require_GET
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
            "roster_url": reverse("accounts:tenant_identity_roster"),
            "can_manage": _can_manage_tenant_identity(request.user, school),
            "offboard_url": reverse(
                "accounts:tenant_identity_offboard", args=[user.pk]
            ),
            "revoke_sessions_url": reverse(
                "accounts:tenant_identity_revoke_sessions", args=[user.pk]
            ),
            "rbac_url": reverse("accounts:rbac"),
            "regulator_url": reverse("accounts:tenant_identity_regulator_grant"),
            "gov_body_label": localized_government_body_label(
                school, default=_("Regulatory authority")
            ),
        },
    )


@tenant_regulator_grant_pdp
@login_required
@require_school
@require_http_methods(["GET", "POST"])
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
        return redirect("accounts:tenant_identity_roster")
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
        return redirect("accounts:tenant_identity_roster")
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
    return redirect("accounts:tenant_identity_detail", user_id=user_id)


@login_required
@require_school
@require_POST
def tenant_identity_offboard(request, user_id: int):
    school = request.school
    if not _can_manage_tenant_identity(request.user, school):
        return HttpResponseForbidden("Not permitted.")
    if request.user.pk == user_id:
        messages.error(request, _("You cannot offboard yourself."))
        return redirect("accounts:tenant_identity_detail", user_id=user_id)
    membership = get_object_or_404(SchoolMembership, school=school, user_id=user_id)
    membership.delete()
    messages.success(request, _("Staff member removed from this school."))
    return redirect("accounts:tenant_identity_roster")


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
