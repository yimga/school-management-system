"""Account security score + quarterly posture review flags for all shells."""

from __future__ import annotations

import logging

from django.urls import NoReverseMatch, reverse

from apps.accounts.profile_security_evaluation import (
    evaluate_user_profile_security,
    is_security_posture_review_due,
    strength_band,
)
from apps.accounts.security_health import calculate_profile_strength

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
        score = int(calculate_profile_strength(user, school=school, use_cache=True))
        band = strength_band(score)
        review_due = is_security_posture_review_due(user, school)
        review_url = reverse("accounts:security_posture_review")
        return {
            "account_security_score": score,
            "account_security_band": band,
            "security_posture_review_due": review_due,
            "security_posture_review_url": review_url,
        }
    except _SOFT:
        logger.debug("account_security_context skipped", exc_info=True)
        return {}


def account_security_evaluation_context(request):
    """Full evaluation on profile-heavy pages only — avoid duplicate work when possible."""
    return account_security_context(request)
