"""Operator Identity hub — /super/team/ (control plane user management)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import transaction
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from services.post_delete_navigation import (
    mutation_return_url,
    redirect_after_delete,
    redirect_after_detail_mutation,
)
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.platform_runtime.models_operator_identity import (
    PlatformOperatorInvite,
    PlatformOperatorProfile,
    PlatformOperatorPromotionRequest,
)
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_TEAM_MANAGE,
    PLATFORM_SCOPE_TEAM_PROMOTE,
    PLATFORM_SCOPE_TEAM_READ,
    TIER_CHOICES,
    audit_operator_action,
    is_canonical_platform_admin,
    list_active_operators_for_peer_picker,
    operator_mfa_enrolled,
    queryset_platform_operators,
    require_platform_scope,
    tier_display,
    user_effective_platform_scopes,
    user_has_platform_scope,
    user_may_offboard_operator,
)
from apps.schools.control_plane import require_super_access_with_host
from apps.schools.control_plane_pagination import paginate_for_request


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _profile_for_user(user):
    profile, _created = PlatformOperatorProfile.objects.get_or_create(
        user=user,
        defaults={
            "status": PlatformOperatorProfile.Status.ACTIVE,
            "tier": "break_glass"
            if is_canonical_platform_admin(user) or user.is_superuser
            else "support",
            "activated_at": timezone.now(),
        },
    )
    if is_canonical_platform_admin(user) and profile.tier != "break_glass":
        profile.tier = "break_glass"
        profile.status = PlatformOperatorProfile.Status.ACTIVE
        profile.save(update_fields=["tier", "status", "updated_at"])
    return profile


@require_GET
@require_platform_scope(PLATFORM_SCOPE_TEAM_READ)
def api_operator_lens_snapshot(request, user_id):
    """Lightweight identity + MFA chips for operator team roster Lens."""
    from apps.schools.operator_school_lens import build_operator_team_lens_snapshot

    User = get_user_model()
    user = get_object_or_404(User, pk=user_id)
    if not queryset_platform_operators().filter(pk=user.pk).exists():
        return JsonResponse({"ok": False, "error": "not_operator"}, status=404)
    return JsonResponse(build_operator_team_lens_snapshot(user))


@require_GET
@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_TEAM_READ)
def super_operator_team_roster(request):
    dashboard_url = reverse("super:dashboard")
    qs = queryset_platform_operators().select_related("platform_operator_profile")
    page_obj = paginate_for_request(request, qs, per_page=25)
    rows = []
    for user in page_obj.object_list:
        profile = getattr(user, "platform_operator_profile", None)
        rows.append(
            {
                "user": user,
                "profile": profile,
                "tier": getattr(profile, "tier", "—"),
                "tier_label": tier_display(getattr(profile, "tier", "")),
                "status": getattr(profile, "status", "legacy"),
                "is_canonical_admin": is_canonical_platform_admin(user),
                "mfa_ok": operator_mfa_enrolled(user),
                "detail_url": reverse("super:operator_team_detail", args=[user.pk]),
            }
        )
    return render(
        request,
        "schools/super_operator_team_roster.html",
        {
            "dashboard_url": dashboard_url,
            "page_obj": page_obj,
            "rows": rows,
            "can_manage": user_has_platform_scope(
                request.user, PLATFORM_SCOPE_TEAM_MANAGE
            ),
            "can_promote": user_has_platform_scope(
                request.user, PLATFORM_SCOPE_TEAM_PROMOTE
            ),
            "invite_url": reverse("super:operator_team_invite"),
            "promote_url": reverse("super:operator_team_promote"),
        },
    )


@require_GET
@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_TEAM_READ)
def super_operator_team_detail(request, user_id: int):
    User = get_user_model()
    user = get_object_or_404(User, pk=user_id)
    if user not in queryset_platform_operators():
        return HttpResponseForbidden("Not a platform operator.")
    profile = _profile_for_user(user)
    scopes = sorted(user_effective_platform_scopes(user))
    sessions = []
    now = timezone.now()
    for session in Session.objects.filter(expire_date__gte=now).order_by("-expire_date")[
        :200
    ]:
        try:
            data = session.get_decoded()
            if str(data.get("_auth_user_id")) == str(user.pk):
                sessions.append(
                    {
                        "key_prefix": (session.session_key or "")[:8] + "…",
                        "expire_date": session.expire_date,
                        "session_key": session.session_key,
                    }
                )
        except Exception:
            continue
    impersonation_rows = []
    try:
        from apps.siteconfig.models import ImpersonationLog

        # tenant-isolation-allow: platform-operator-impersonation-audit-cross-tenant-by-design
        impersonation_rows = list(
            ImpersonationLog.objects.filter(actor_id=user.pk)
            .select_related("peer_actor", "school")
            .order_by("-created_at")[:20]
        )
    except Exception:
        pass
    promotion_rows = list(
        PlatformOperatorPromotionRequest.objects.filter(target_user_id=user.pk).order_by(
            "-created_at"
        )[:10]
    )
    roster_url = reverse("super:operator_team_roster")
    detail_url = reverse("super:operator_team_detail", args=[user.pk])
    return_url = mutation_return_url(request, roster_url, list_url=roster_url)
    detail_return_url = mutation_return_url(request, detail_url, list_url=detail_url)
    return render(
        request,
        "schools/super_operator_team_detail.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "roster_url": roster_url,
            "return_url": return_url,
            "detail_return_url": detail_return_url,
            "operator_user": user,
            "profile": profile,
            "scopes": scopes,
            "sessions": sessions,
            "impersonation_rows": impersonation_rows,
            "promotion_rows": promotion_rows,
            "mfa_ok": operator_mfa_enrolled(user),
            "tier_label": tier_display(profile.tier),
            "is_canonical_admin": is_canonical_platform_admin(user),
            "can_offboard": user_may_offboard_operator(request.user, user),
            "can_manage": user_has_platform_scope(
                request.user, PLATFORM_SCOPE_TEAM_MANAGE
            ),
            "suspend_url": reverse("super:operator_team_suspend", args=[user.pk]),
            "reactivate_url": reverse("super:operator_team_reactivate", args=[user.pk]),
        },
    )


@require_http_methods(["GET", "POST"])
@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_TEAM_MANAGE)
def super_operator_team_invite(request):
    dashboard_url = reverse("super:dashboard")
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        tier = (request.POST.get("tier") or "support").strip().lower()
        if tier not in dict(TIER_CHOICES):
            tier = "support"
        if not email or "@" not in email:
            messages.error(request, _("Valid email required."))
            return redirect("super:operator_team_invite")
        expires_at = timezone.now() + timedelta(days=7)
        invite = PlatformOperatorInvite.objects.create(
            email=email,
            tier=tier,
            invited_by=request.user,
            expires_at=expires_at,
        )
        audit_operator_action(
            request,
            action="CREATE",
            model_name="PlatformOperatorInvite",
            object_id=str(invite.pk),
            object_repr=email,
            new_values={"tier": tier, "expires_at": expires_at.isoformat()},
        )
        accept_url = request.build_absolute_uri(
            reverse("accounts:operator_invite_accept", kwargs={"token": invite.token})
        )
        messages.success(
            request,
            _("Invite created. Share this link with the operator: %(url)s")
            % {"url": accept_url},
        )
        return redirect("super:operator_team_roster")
    return render(
        request,
        "schools/super_operator_team_invite.html",
        {
            "dashboard_url": dashboard_url,
            "roster_url": reverse("super:operator_team_roster"),
            "tier_choices": TIER_CHOICES,
        },
    )


@require_POST
@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_TEAM_MANAGE)
def super_operator_team_offboard(request, user_id: int):
    User = get_user_model()
    user = get_object_or_404(User, pk=user_id)
    if not user_may_offboard_operator(request.user, user):
        if is_canonical_platform_admin(user):
            messages.error(
                request,
                _("The canonical platform admin account cannot be offboarded."),
            )
        elif user.pk == request.user.pk:
            messages.error(request, _("You cannot offboard yourself."))
        else:
            return HttpResponseForbidden("Not permitted.")
        return redirect("super:operator_team_detail", user_id=user_id)
    profile = _profile_for_user(user)
    profile.mark_offboarded()
    profile.save(update_fields=["status", "offboarded_at", "updated_at"])
    user.is_active = False
    user.is_superuser = False
    user.is_staff = False
    user.save(update_fields=["is_active", "is_superuser", "is_staff"])
    Session.objects.filter(session_key__in=_session_keys_for_user(user)).delete()
    audit_operator_action(
        request,
        action="UPDATE",
        model_name="PlatformOperatorProfile",
        object_id=str(profile.pk),
        object_repr=user.get_username(),
        new_values={"status": "offboarded"},
    )
    messages.success(request, _("Operator offboarded and sessions revoked."))
    roster_url = reverse("super:operator_team_roster")
    return redirect_after_delete(request, roster_url, list_url=roster_url)


def _session_keys_for_user(user):
    keys = []
    now = timezone.now()
    for session in Session.objects.filter(expire_date__gte=now):
        try:
            if str(session.get_decoded().get("_auth_user_id")) == str(user.pk):
                keys.append(session.session_key)
        except Exception:
            continue
    return keys


@require_POST
@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_TEAM_MANAGE)
def super_operator_team_revoke_sessions(request, user_id: int):
    User = get_user_model()
    user = get_object_or_404(User, pk=user_id)
    deleted, _deleted_count = Session.objects.filter(
        session_key__in=_session_keys_for_user(user)
    ).delete()
    from apps.accounts.mfa_device_trust import revoke_device_trust

    revoke_device_trust(user)
    audit_operator_action(
        request,
        action="UPDATE",
        model_name="UserSession",
        object_id=str(user.pk),
        object_repr=user.get_username(),
        new_values={"sessions_revoked": deleted},
    )
    messages.success(request, _("Revoked %(n)s session(s).") % {"n": deleted})
    detail_url = reverse("super:operator_team_detail", args=[user_id])
    return redirect_after_detail_mutation(request, detail_url)


@require_POST
@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_TEAM_MANAGE)
def super_operator_team_suspend(request, user_id: int):
    User = get_user_model()
    user = get_object_or_404(User, pk=user_id)
    if is_canonical_platform_admin(user):
        messages.error(request, _("The canonical platform admin cannot be suspended."))
        return redirect("super:operator_team_detail", user_id=user_id)
    profile = _profile_for_user(user)
    profile.status = PlatformOperatorProfile.Status.SUSPENDED
    profile.save(update_fields=["status", "updated_at"])
    Session.objects.filter(session_key__in=_session_keys_for_user(user)).delete()
    from apps.accounts.mfa_device_trust import revoke_device_trust

    revoke_device_trust(user)
    audit_operator_action(
        request,
        action="UPDATE",
        model_name="PlatformOperatorProfile",
        object_id=str(profile.pk),
        object_repr=user.get_username(),
        new_values={"status": "suspended"},
    )
    messages.success(request, _("Operator suspended and sessions revoked."))
    detail_url = reverse("super:operator_team_detail", args=[user_id])
    return redirect_after_detail_mutation(request, detail_url)


@require_POST
@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_TEAM_MANAGE)
def super_operator_team_reactivate(request, user_id: int):
    User = get_user_model()
    user = get_object_or_404(User, pk=user_id)
    profile = _profile_for_user(user)
    profile.mark_active()
    profile.save(update_fields=["status", "activated_at", "offboarded_at", "updated_at"])
    user.is_active = True
    user.is_staff = True
    user.save(update_fields=["is_active", "is_staff"])
    audit_operator_action(
        request,
        action="UPDATE",
        model_name="PlatformOperatorProfile",
        object_id=str(profile.pk),
        object_repr=user.get_username(),
        new_values={"status": "active"},
    )
    messages.success(request, _("Operator reactivated."))
    detail_url = reverse("super:operator_team_detail", args=[user_id])
    return redirect_after_detail_mutation(request, detail_url)


@require_http_methods(["GET", "POST"])
@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_TEAM_PROMOTE)
def super_operator_team_promote(request):
    dashboard_url = reverse("super:dashboard")
    peer_operators = list(
        list_active_operators_for_peer_picker(exclude_user_id=request.user.pk)[:100]
    )
    if request.method == "POST":
        target_id = request.POST.get("target_user_id")
        tier = (request.POST.get("tier") or "").strip().lower()
        peer_id = request.POST.get("peer_approver_id")
        reason = (request.POST.get("reason") or "").strip()[:255]
        if tier not in dict(TIER_CHOICES):
            messages.error(request, _("Invalid tier."))
            return redirect("super:operator_team_promote")
        User = get_user_model()
        target = get_object_or_404(User, pk=target_id)
        if is_canonical_platform_admin(target) and tier != "break_glass":
            messages.error(
                request,
                _("The canonical platform admin must remain on the break_glass tier."),
            )
            return redirect("super:operator_team_promote")
        peer = get_object_or_404(User, pk=peer_id)
        if peer.pk == request.user.pk:
            messages.error(request, _("Peer approver must be a different operator."))
            return redirect("super:operator_team_promote")
        if not user_has_platform_scope(peer, PLATFORM_SCOPE_TEAM_PROMOTE):
            messages.error(request, _("Peer must have platform.team.promote scope."))
            return redirect("super:operator_team_promote")
        promo = PlatformOperatorPromotionRequest.objects.create(
            target_user=target,
            requested_tier=tier,
            requester=request.user,
            peer_approver=peer,
            reason=reason,
        )
        audit_operator_action(
            request,
            action="CREATE",
            model_name="PlatformOperatorPromotionRequest",
            object_id=str(promo.pk),
            object_repr=f"{target.username}->{tier}",
            new_values={"peer_id": peer.pk, "reason": reason},
        )
        messages.success(
            request,
            _("Promotion request recorded. Peer %(peer)s must approve.")
            % {"peer": peer.get_username()},
        )
        return redirect("super:operator_team_roster")
    operators = queryset_platform_operators().filter(is_active=True)[:200]
    pending_rows = []
    for promo in PlatformOperatorPromotionRequest.objects.filter(
        status=PlatformOperatorPromotionRequest.Status.PENDING
    ).select_related("target_user", "requester", "peer_approver")[:25]:
        pending_rows.append(
            {
                "promo": promo,
                "can_decide": promo.peer_approver_id == request.user.pk,
            }
        )
    return render(
        request,
        "schools/super_operator_team_promote.html",
        {
            "dashboard_url": dashboard_url,
            "roster_url": reverse("super:operator_team_roster"),
            "operators": operators,
            "peer_operators": peer_operators,
            "tier_choices": TIER_CHOICES,
            "pending_rows": pending_rows,
        },
    )


@require_POST
@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_TEAM_PROMOTE)
def super_operator_team_promotion_decide(request, promo_id: int):
    promo = get_object_or_404(PlatformOperatorPromotionRequest, pk=promo_id)
    decision = (request.POST.get("decision") or "").strip().lower()
    if promo.status != PlatformOperatorPromotionRequest.Status.PENDING:
        messages.error(request, _("Promotion request is already decided."))
        return redirect("super:operator_team_promote")
    if promo.peer_approver_id != request.user.pk:
        return HttpResponseForbidden("Only the assigned peer approver may decide.")
    if decision == "approve":
        profile = _profile_for_user(promo.target_user)
        if is_canonical_platform_admin(promo.target_user):
            promo.requested_tier = "break_glass"
        profile.tier = promo.requested_tier
        profile.status = PlatformOperatorProfile.Status.ACTIVE
        profile.activated_at = profile.activated_at or timezone.now()
        profile.save(
            update_fields=["tier", "status", "activated_at", "updated_at"]
        )
        promo.status = PlatformOperatorPromotionRequest.Status.APPROVED
        promo.decided_at = timezone.now()
        promo.save(update_fields=["status", "decided_at"])
        audit_operator_action(
            request,
            action="APPROVE",
            model_name="PlatformOperatorPromotionRequest",
            object_id=str(promo.pk),
            object_repr=promo.target_user.get_username(),
            new_values={"tier": promo.requested_tier},
        )
        messages.success(request, _("Promotion approved and tier applied."))
    elif decision == "reject":
        promo.status = PlatformOperatorPromotionRequest.Status.REJECTED
        promo.decided_at = timezone.now()
        promo.save(update_fields=["status", "decided_at"])
        messages.info(request, _("Promotion rejected."))
    else:
        messages.error(request, _("Invalid decision."))
    return redirect("super:operator_team_promote")


@require_http_methods(["GET", "POST"])
def operator_invite_accept(request, token):
    """Public invite acceptance on manager or tenant host (pre-auth allowed)."""
    invite = get_object_or_404(PlatformOperatorInvite, token=token)
    if not invite.is_pending:
        messages.error(request, _("Invite expired or already used."))
        return redirect("accounts:login")
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        password2 = request.POST.get("password2") or ""
        if not username or len(password) < 8:
            messages.error(request, _("Username and password (8+ chars) required."))
            return render(
                request,
                "accounts/operator_invite_accept.html",
                {"invite": invite},
            )
        if password != password2:
            messages.error(request, _("Passwords do not match."))
            return render(
                request,
                "accounts/operator_invite_accept.html",
                {"invite": invite},
            )
        User = get_user_model()
        with transaction.atomic():
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": invite.email, "is_active": True, "is_staff": True},
            )
            if not created and user.email.lower() != invite.email.lower():
                messages.error(
                    request,
                    _("Username exists with a different email. Contact platform admin."),
                )
                return render(
                    request,
                    "accounts/operator_invite_accept.html",
                    {"invite": invite},
                )
            user.set_password(password)
            user.email = invite.email
            user.is_active = True
            user.is_staff = True
            user.is_superuser = False
            user.save()
            profile, _profile_created = PlatformOperatorProfile.objects.update_or_create(
                user=user,
                defaults={
                    "status": PlatformOperatorProfile.Status.INVITED,
                    "tier": invite.tier,
                    "invited_by": invite.invited_by,
                    "invited_at": invite.created_at,
                    "mfa_required": True,
                },
            )
            profile.status = PlatformOperatorProfile.Status.ACTIVE
            profile.activated_at = timezone.now()
            profile.save(update_fields=["status", "activated_at", "updated_at"])
            invite.accepted_at = timezone.now()
            invite.save(update_fields=["accepted_at"])
        audit_operator_action(
            request,
            action="CREATE",
            model_name="PlatformOperatorProfile",
            object_id=str(profile.pk),
            object_repr=user.get_username(),
            new_values={"tier": invite.tier, "email": invite.email},
        )
        messages.success(
            request,
            _("Account ready. Sign in on the manager host and enroll MFA."),
        )
        return redirect("accounts:login")
    return render(request, "accounts/operator_invite_accept.html", {"invite": invite})


def operator_peer_picker_context(exclude_user_id: int | None = None) -> list[dict]:
    """For impersonation dual-control dropdown."""
    return [
        {
            "id": u.pk,
            "email": u.email or u.username,
            "label": u.get_full_name() or u.username,
        }
        for u in list_active_operators_for_peer_picker(exclude_user_id=exclude_user_id)[
            :50
        ]
    ]
