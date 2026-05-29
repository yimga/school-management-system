"""v4.00.45 — Generate recurring on-call shifts (alternating roster).

Given a list of user ids and a weekly pattern, emit ``SupportOnCallShift`` rows
that cover the next N weeks. Users are rotated round-robin across calendar
weeks so two operators alternate week-on / week-off, three operators rotate
every third week, etc.

Pattern shape::

    {
        "days": ["mon", "tue", "wed", "thu", "fri"],
        "start_hour": 9,
        "end_hour": 17,
        "tz_name": "UTC",
        "role_tag": "platform",
    }

The generator never overwrites existing shifts — every row is a fresh row.
Operators can delete unwanted rows from the on-call dashboard.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Iterable

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[assignment]

from django.utils import timezone


_DAY_INDEX = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


def _coerce_tz(tz_name: str):
    if not tz_name:
        return timezone.get_current_timezone()
    if ZoneInfo is None:
        return timezone.get_current_timezone()
    try:
        return ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 — bad tz name falls back gracefully
        return timezone.get_current_timezone()


def _normalize_days(days: Iterable[str]) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for token in days or ():
        idx = _DAY_INDEX.get((token or "").strip().lower()[:3])
        if idx is not None and idx not in seen:
            seen.add(idx)
            out.append(idx)
    return sorted(out)


def _normalize_skip_weeks(raw, weeks: int) -> set[int]:
    """Parse a comma- or space-separated list of 1-indexed week numbers to skip.

    Accepts strings ("1,3,5"), lists ([1, 3]), or numeric scalars. Out-of-range
    entries are silently dropped — operator typos shouldn't crash the generator.
    Returned indices are 0-indexed (week 1 → 0) to match the loop counter.
    """
    if raw is None or raw == "":
        return set()
    tokens: list[str] = []
    if isinstance(raw, (list, tuple, set)):
        tokens = [str(t) for t in raw]
    else:
        tokens = str(raw).replace(",", " ").split()
    out: set[int] = set()
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        try:
            n = int(tok)
        except ValueError:
            continue
        if 1 <= n <= weeks:
            out.add(n - 1)
    return out


def _resolve_skip_pattern(pattern_name: str, weeks: int) -> set[int]:
    """Interpret a named skip pattern (e.g. ``alternating``, ``first-week-only``).

    Named patterns let the UI offer common shapes (every-other-week, every-third,
    skip first week so the existing schedule plays out) without forcing the
    operator to type week numbers by hand.
    """
    name = (pattern_name or "").strip().lower()
    if not name:
        return set()
    if name in ("alternating", "every-other"):
        # Skip week 2, 4, 6 ... (operator owns weeks 1, 3, 5 ...).
        return {i for i in range(weeks) if i % 2 == 1}
    if name in ("every-third",):
        return {i for i in range(weeks) if i % 3 != 0}
    if name in ("first-week-only",):
        return set(range(1, weeks))
    if name in ("skip-first-week",):
        return {0}
    if name in ("none", "all-weeks"):
        return set()
    return set()


def generate_recurring_shifts(
    user_ids: list[int],
    pattern: dict,
    weeks: int,
    *,
    start_date=None,
) -> int:
    """Create the requested shifts; return how many rows were inserted.

    v4.00.49 supports two new keys on ``pattern``:
      * ``skip_weeks`` — explicit 1-indexed week numbers to skip
        (``"2, 4, 6"`` or ``[2, 4, 6]``).
      * ``skip_pattern`` — named shape: ``"alternating"`` / ``"every-third"``
        / ``"first-week-only"`` / ``"skip-first-week"`` / ``"none"``.

    If both keys are present, their results are unioned. Skipped weeks emit
    zero rows (no primary, no backup) — operators can still add ad-hoc shifts
    for those weeks via the "Add shift" form.
    """
    from apps.siteconfig.models_feature_controls import SupportOnCallShift

    if not user_ids:
        return 0
    weeks = max(1, min(int(weeks or 1), 26))

    days = _normalize_days(pattern.get("days") or [])
    if not days:
        days = [0, 1, 2, 3, 4]  # Mon-Fri default
    start_hour = max(0, min(int(pattern.get("start_hour") or 9), 23))
    end_hour_raw = int(pattern.get("end_hour") or 17)
    end_hour = max(start_hour + 1, min(end_hour_raw, 24))
    role_tag = (pattern.get("role_tag") or "")[:40]
    tz = _coerce_tz((pattern.get("tz_name") or "UTC").strip())

    skip_weeks = _normalize_skip_weeks(pattern.get("skip_weeks"), weeks) | _resolve_skip_pattern(
        pattern.get("skip_pattern") or "", weeks
    )

    base = start_date or timezone.now().astimezone(tz).date()
    # Move base back to Monday so weekly rotation aligns cleanly.
    monday = base - timedelta(days=base.weekday())

    # Round-robin assignment ignores skipped weeks so two operators still
    # alternate fairly across the live weeks (skipping week 2 doesn't mean
    # operator A picks up week 3 — the cursor advances).
    live_week_cursor = 0

    created = 0
    bulk: list[SupportOnCallShift] = []
    for week_offset in range(weeks):
        if week_offset in skip_weeks:
            continue
        primary_user_id = user_ids[live_week_cursor % len(user_ids)]
        backup_user_id = (
            user_ids[(live_week_cursor + 1) % len(user_ids)]
            if len(user_ids) > 1
            else None
        )
        live_week_cursor += 1
        for day_idx in days:
            day = monday + timedelta(days=week_offset * 7 + day_idx)
            start_naive = datetime.combine(day, time(start_hour, 0))
            if end_hour == 24:
                end_naive = datetime.combine(day + timedelta(days=1), time(0, 0))
            else:
                end_naive = datetime.combine(day, time(end_hour, 0))
            start_at = start_naive.replace(tzinfo=tz)
            end_at = end_naive.replace(tzinfo=tz)
            bulk.append(
                SupportOnCallShift(
                    user_id=primary_user_id,
                    role_tag=role_tag,
                    is_primary=True,
                    starts_at=start_at,
                    ends_at=end_at,
                    notes=f"auto-generated week {week_offset + 1}",
                )
            )
            if backup_user_id is not None:
                bulk.append(
                    SupportOnCallShift(
                        user_id=backup_user_id,
                        role_tag=role_tag,
                        is_primary=False,
                        starts_at=start_at,
                        ends_at=end_at,
                        notes=f"auto-generated week {week_offset + 1} backup",
                    )
                )
    if bulk:
        SupportOnCallShift.objects.bulk_create(bulk)
        created = len(bulk)
    return created
