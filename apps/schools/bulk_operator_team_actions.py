"""Bulk platform-operator team mutations for the control-plane roster."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from apps.platform_runtime.models_operator_identity import PlatformOperatorProfile
from apps.platform_runtime.operator_identity import (
    TIER_CHOICES,
    is_canonical_platform_admin,
    queryset_platform_operators,
    user_is_platform_operator,
    user_may_offboard_operator,
)

MAX_BULK_IDS = 200

ALLOWED_TEAM_ACTIONS = frozenset(
    {
        "suspend",
        "reactivate",
        "revoke_sessions",
        "offboard",
        "set_tier",
    }
)

ACTION_CONFIRM_PHRASES = {
    "offboard": "OFFBOARD OPERATORS",
    "set_tier": "SET OPERATOR TIER",
}


def parse_operator_user_id_list(raw_ids: Any) -> list[int]:
    if not raw_ids:
        return []
    if not isinstance(raw_ids, (list, tuple)):
        return []
    out: list[int] = []
    for item in raw_ids:
        if isinstance(item, int) and item > 0:
            out.append(item)
        else:
            text = str(item or "").strip()
            if text.isdigit():
                out.append(int(text))
        if len(out) >= MAX_BULK_IDS:
            break
    return out


def _session_keys_for_user(user) -> list[str]:
    keys: list[str] = []
    now = timezone.now()
    for session in Session.objects.filter(expire_date__gte=now):
        try:
            if str(session.get_decoded().get("_auth_user_id")) == str(user.pk):
                keys.append(session.session_key)
        except Exception:
            continue
    return keys


def _profile_for_user(user) -> PlatformOperatorProfile:
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
    return profile


def _apply_one_operator_action(
    user,
    *,
    action: str,
    actor,
    tier: str = "",
) -> dict[str, Any]:
    if not user_is_platform_operator(user):
        raise ValueError("Not a platform operator.")

    profile = _profile_for_user(user)

    if action == "suspend":
        if is_canonical_platform_admin(user):
            raise ValueError("The canonical platform admin cannot be suspended.")
        profile.status = PlatformOperatorProfile.Status.SUSPENDED
        profile.save(update_fields=["status", "updated_at"])
        revoked = Session.objects.filter(
            session_key__in=_session_keys_for_user(user)
        ).delete()[0]
        from apps.accounts.mfa_device_trust import revoke_device_trust

        revoke_device_trust(user)
        return {"message": "Suspended.", "sessions_revoked": revoked}

    if action == "reactivate":
        profile.mark_active()
        profile.save(update_fields=["status", "activated_at", "offboarded_at", "updated_at"])
        user.is_active = True
        user.is_staff = True
        user.save(update_fields=["is_active", "is_staff"])
        return {"message": "Reactivated."}

    if action == "revoke_sessions":
        revoked = Session.objects.filter(
            session_key__in=_session_keys_for_user(user)
        ).delete()[0]
        from apps.accounts.mfa_device_trust import revoke_device_trust

        revoke_device_trust(user)
        return {"message": "Sessions revoked.", "sessions_revoked": revoked}

    if action == "offboard":
        if not user_may_offboard_operator(actor, user):
            if is_canonical_platform_admin(user):
                raise ValueError("The canonical platform admin cannot be offboarded.")
            if getattr(actor, "pk", None) == getattr(user, "pk", None):
                raise ValueError("You cannot offboard yourself.")
            raise ValueError("Not permitted to offboard this operator.")
        profile.mark_offboarded()
        profile.save(update_fields=["status", "offboarded_at", "updated_at"])
        user.is_active = False
        user.is_superuser = False
        user.is_staff = False
        user.save(update_fields=["is_active", "is_superuser", "is_staff"])
        revoked = Session.objects.filter(
            session_key__in=_session_keys_for_user(user)
        ).delete()[0]
        return {"message": "Offboarded.", "sessions_revoked": revoked}

    if action == "set_tier":
        target_tier = str(tier or "").strip().lower()
        if target_tier not in dict(TIER_CHOICES):
            raise ValueError(f"Unsupported tier: {target_tier}")
        if is_canonical_platform_admin(user) and target_tier != "break_glass":
            raise ValueError(
                "The canonical platform admin must remain on the break_glass tier."
            )
        profile.tier = target_tier
        profile.save(update_fields=["tier", "updated_at"])
        return {"message": f"Tier set to {target_tier}.", "tier": target_tier}

    raise ValueError(f"Unsupported team action: {action}")


def bulk_apply_operator_team_actions(
    *,
    user_ids: list[int],
    action: str,
    actor=None,
    confirm_phrase: str = "",
    tier: str = "",
) -> dict[str, Any]:
    action = str(action or "").strip().lower().replace("-", "_")
    if action not in ALLOWED_TEAM_ACTIONS:
        raise ValueError(f"Unsupported bulk action: {action}")
    required_phrase = ACTION_CONFIRM_PHRASES.get(action)
    if required_phrase and str(confirm_phrase or "").strip() != required_phrase:
        raise ValueError(f'Type "{required_phrase}" to confirm.')
    if action == "set_tier" and not str(tier or "").strip():
        raise ValueError("tier is required for set_tier.")
    if not user_ids:
        raise ValueError("Select at least one operator.")

    User = get_user_model()
    users = list(
        User.objects.filter(pk__in=user_ids)
        .filter(pk__in=queryset_platform_operators().values("pk"))
        .order_by("username")
    )
    found_ids = {user.pk for user in users}
    missing = [str(uid) for uid in user_ids if uid not in found_ids]

    results: list[dict[str, Any]] = []
    for user in users:
        try:
            with transaction.atomic():
                payload = _apply_one_operator_action(
                    user,
                    action=action,
                    actor=actor,
                    tier=tier,
                )
            results.append(
                {
                    "id": user.pk,
                    "username": user.get_username(),
                    "ok": True,
                    "message": payload.get("message", ""),
                    **{
                        k: v
                        for k, v in payload.items()
                        if k not in ("message",)
                    },
                }
            )
        except Exception as exc:
            results.append(
                {
                    "id": user.pk,
                    "username": getattr(user, "username", ""),
                    "ok": False,
                    "error": str(exc),
                }
            )

    for mid in missing:
        results.append({"id": mid, "ok": False, "error": "Operator not found."})

    succeeded = sum(1 for row in results if row.get("ok"))
    return {
        "ok": succeeded > 0,
        "action": action,
        "processed": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }
