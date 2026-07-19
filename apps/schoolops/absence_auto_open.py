"""Open the substitute market automatically when a teacher is marked absent.

Metric 12 residual (absence auto-open): TeacherAttendance → ABSENT should open a
cover shift and notify ranked candidates, not wait for an ops admin to click
"Open market & notify". Fail-soft — attendance save must never break if the
market layer errors.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _auto_open_enabled(school: Any) -> bool:
    attrs = getattr(school, "custom_attributes", None) or {}
    if isinstance(attrs, dict) and "substitute_absence_auto_open" in attrs:
        return bool(attrs.get("substitute_absence_auto_open"))
    try:
        from apps.platform_runtime.config_resolver import get_effective_config

        raw = get_effective_config(
            school, "substitute_absence_auto_open", default=True
        )
        if isinstance(raw, str):
            return raw.strip().lower() not in {"0", "false", "no", "off"}
        return bool(raw)
    except Exception:  # noqa: BLE001
        return True


def maybe_open_market_for_teacher_absence(
    attendance: Any,
    *,
    notify: bool = True,
    publish_fn=None,
) -> Any | None:
    """Open a full-day market shift for an ABSENT TeacherAttendance row.

    Returns the OpenShift (or None when skipped / soft-failed). Idempotent for
    the same (school, teacher, date, full-day) lock used by ``open_shift``.
    """
    try:
        from apps.people.models import TeacherAttendance
        from apps.schoolops.substitute_market import ShiftAlreadyBooked, open_shift
    except Exception:  # noqa: BLE001
        logger.debug("substitute absence auto-open import skipped", exc_info=True)
        return None

    status = getattr(attendance, "status", "") or ""
    if status != TeacherAttendance.Status.ABSENT:
        return None

    teacher = getattr(attendance, "teacher", None)
    if teacher is None:
        return None
    school = getattr(teacher, "school", None)
    if school is None:
        return None
    if not _auto_open_enabled(school):
        return None

    user_id = getattr(teacher, "user_id", None)
    work_date = getattr(attendance, "date", None)
    if not user_id or work_date is None:
        return None

    try:
        return open_shift(
            school=school,
            absent_teacher_id=int(user_id),
            work_date=work_date,
            period_label="",
            notify=notify,
            publish_fn=publish_fn,
        )
    except ShiftAlreadyBooked:
        logger.info(
            "substitute_absence_auto_open.already_open school=%s teacher=%s date=%s",
            getattr(school, "pk", None),
            user_id,
            work_date,
        )
        return None
    except Exception:  # noqa: BLE001 — never break attendance save
        logger.warning(
            "substitute_absence_auto_open.failed school=%s teacher=%s date=%s",
            getattr(school, "pk", None),
            user_id,
            work_date,
            exc_info=True,
        )
        return None


__all__ = ["maybe_open_market_for_teacher_absence"]
