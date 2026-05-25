"""Account security score + quarterly posture review flags for all shells."""

from __future__ import annotations

import logging

from django.urls import NoReverseMatch, reverse

from apps.accounts.platform_access_policy import user_meets_platform_security_minimum
from apps.accounts.profile_security_evaluation import (
    evaluate_user_profile_security,
    is_security_posture_review_due,
    strength_band,
)
from apps.accounts.security_posture_notifications import (
    corner_notifications_for_request,
    is_corner_snoozed,
    is_session_modal_acknowledged,
    security_posture_zone,
    should_show_session_modal,
)

logger = logging.getLogger(__name__)

_SOFT = (
    AttributeError,
    ImportError,
    NoReverseMatch,
    RuntimeError,
    TypeError,
    ValueError,
)


def account_security_context(request):
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False) or not getattr(user, "pk", None):
        return {}
    school = getattr(request, "school", None)
    try:
        cached = getattr(request, "rmc_security_evaluation", None)
        if cached:
            evaluation = cached
        else:
            _allowed, _reason, evaluation = user_meets_platform_security_minimum(
                user, school=school
            )
            if not evaluation:
                evaluation = evaluate_user_profile_security(user, school=school)
        score = int(evaluation.get("security_score") or 0)
        band = evaluation.get("strength_band") or strength_band(score)
        review_due = bool(
            evaluation.get("security_posture_review_due")
            if "security_posture_review_due" in evaluation
            else is_security_posture_review_due(user, school)
        )
        review_url = reverse("accounts:security_posture_review")
        meets_min = bool(evaluation.get("meets_platform_minimum", True))
        required = int(evaluation.get("security_minimum_required") or 0)
        gap = int(evaluation.get("security_minimum_gap") or 0)
        show_block_banner = not meets_min and required > 0
        zone = security_posture_zone(
            score=score,
            meets_platform_minimum=meets_min,
            security_posture_review_due=review_due,
            security_posture_blocked=show_block_banner,
        )
        return {
            "account_security_score": score,
            "account_security_band": band,
            "security_minimum_required": required,
            "security_minimum_gap": gap,
            "meets_platform_minimum": meets_min,
            "platform_baseline_minimum": int(
                evaluation.get("platform_baseline_minimum") or 40
            ),
            "security_posture_review_due": review_due,
            "security_posture_review_url": review_url,
            "security_posture_corner_snoozed": is_corner_snoozed(request),
            "security_posture_inline_banner": False,
            "security_posture_blocked": show_block_banner,
            "security_posture_zone": zone,
            "security_posture_session_modal_show": should_show_session_modal(
                request, zone=zone
            ),
            "security_posture_session_modal_ack": is_session_modal_acknowledged(
                request
            ),
            "rmc_corner_notifications": corner_notifications_for_request(request),
        }
    except _SOFT:
        logger.debug("account_security_context skipped", exc_info=True)
        return {}


def account_security_evaluation_context(request):
    """Full evaluation on profile-heavy pages only — avoid duplicate work when possible."""
    return account_security_context(request)
