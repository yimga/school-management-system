"""Operator queue signals for smart-link banners (Wave T / batch 1526)."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.smart_links_kernel import (
    STATE_ADMISSION_PENDING,
    STATE_DSL_CONCERN_OPEN,
)


def build_operator_queue_smart_link_context(request: Any) -> dict[str, Any]:
    """
    Resolve which smart-link state (if any) should surface on admin landings.

    Safeguarding unacknowledged inbox entries take precedence over admissions.
    """
    school = getattr(request, "school", None)
    if school is None:
        return {
            "operator_queue_smart_link_state": "",
            "operator_queue_pending_admissions": 0,
            "operator_queue_dsl_unacknowledged": 0,
        }

    dsl_unack = 0
    try:
        from apps.safeguarding.dsl_notify import list_unacknowledged

        bucket = (getattr(school, "settings", None) or {}).get("safeguarding") or {}
        dsl_unack = len(list_unacknowledged(bucket.get("dsl_inbox")))
    except Exception:  # noqa: BLE001
        dsl_unack = 0

    pending_admissions = 0
    try:
        from apps.people.models import Applicant

        pending_admissions = Applicant.objects.filter(
            school=school,
            stage__in=(
                Applicant.Stage.APPLIED,
                Applicant.Stage.UNDER_REVIEW,
            ),
        ).count()
    except Exception:  # noqa: BLE001
        pending_admissions = 0

    state = ""
    if dsl_unack > 0:
        state = STATE_DSL_CONCERN_OPEN
    elif pending_admissions > 0:
        state = STATE_ADMISSION_PENDING

    return {
        "operator_queue_smart_link_state": state,
        "operator_queue_pending_admissions": pending_admissions,
        "operator_queue_dsl_unacknowledged": dsl_unack,
    }
