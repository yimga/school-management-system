"""Curated per-country academic-term calendars — real term windows.

Local-first minimum defaults so a migrated / freshly onboarded school's terms
land on REAL calendar windows instead of a naive even ``12 // term_count`` month
split (which gives Cameroon a term ending Aug 31 when its third trimester really
ends in July). Each country lists its terms as ``(start_month, start_day,
end_month, end_day)`` offsets *within* the academic year; the actual calendar
year for each date is derived from the school's academic-year start month, so the
same window works whether the year runs Sep→Aug (Cameroon), Aug→Jul (US), or
Jan→Dec (Kenya).

Resolution cascade (most specific wins), all admin-editable:

    tenant  School.settings['term_windows']            (per-school override)
      ⊕ profile  EducationSystemProfile.config['term_windows']  (per-education-system)
      ⊕ curated  _TERM_CALENDARS[country(-subsystem)]   (this module)
      ⊕ none  → caller falls back to the even split

A country DEFAULT, never a lock: a school with an exotic calendar just edits the
term rows (or its ``term_windows`` setting) afterward. Windows are representative
public-calendar approximations, not ministry-exact — the point is "real enough to
run a school on day one", and the exact dates are the first thing an admin tweaks.

Each list's LENGTH must match the country's ``term_count``; a mismatch makes the
resolver return ``None`` (fall back to the even split) rather than seed a wrong
number of terms.
"""

from __future__ import annotations

import datetime as _dt
import logging

logger = logging.getLogger(__name__)

# (start_month, start_day, end_month, end_day) per term, in teaching order.
# Keyed by ISO alpha-2 country, with optional "<CC>-<SUBSYS>" specialization.
_TERM_CALENDARS: dict[str, list[tuple[int, int, int, int]]] = {
    # --- Cameroon: 3 trimesters, year starts September, ends ~July -------------
    "CM": [(9, 1, 12, 15), (1, 5, 4, 5), (4, 15, 7, 10)],
    "CM-FR": [(9, 1, 12, 15), (1, 5, 4, 5), (4, 15, 7, 10)],
    "CM-EN": [(9, 1, 12, 15), (1, 5, 4, 5), (4, 15, 7, 10)],
    # --- West/Central Africa (3 terms, Sep start) ------------------------------
    "NG": [(9, 1, 12, 15), (1, 8, 4, 10), (4, 25, 7, 25)],
    "GH": [(9, 1, 12, 15), (1, 8, 4, 10), (4, 25, 7, 25)],
    # --- Kenya / East Africa: 3 terms, year starts January --------------------
    "KE": [(1, 5, 4, 5), (5, 2, 8, 5), (8, 28, 11, 25)],
    "UG": [(2, 5, 5, 5), (5, 28, 8, 25), (9, 15, 12, 5)],
    "TZ": [(1, 8, 4, 5), (4, 20, 6, 25), (7, 10, 12, 5)],
    # --- United Kingdom: 3 terms (Michaelmas / Lent / Trinity) ----------------
    "GB": [(9, 1, 12, 20), (1, 5, 3, 31), (4, 15, 7, 20)],
    # --- France: 3 trimesters, year starts September --------------------------
    "FR": [(9, 1, 12, 20), (1, 6, 3, 31), (4, 1, 7, 5)],
    # --- United States: 2 semesters, year starts August ----------------------
    "US": [(8, 15, 12, 20), (1, 8, 5, 30)],
    "CA": [(9, 1, 1, 31), (2, 1, 6, 25)],
    # --- Germany: 2 semesters, year starts August/September -------------------
    "DE": [(9, 1, 1, 31), (2, 1, 7, 20)],
    # --- India: 2 terms, year starts April ------------------------------------
    "IN": [(4, 1, 9, 30), (10, 1, 3, 25)],
    # --- Southern hemisphere: 4 terms, year starts late Jan -------------------
    "AU": [(1, 28, 4, 10), (4, 26, 7, 2), (7, 19, 9, 24), (10, 11, 12, 17)],
    "NZ": [(2, 1, 4, 15), (5, 1, 7, 5), (7, 22, 9, 27), (10, 14, 12, 18)],
    "ZA": [(1, 15, 3, 28), (4, 9, 6, 21), (7, 16, 9, 27), (10, 8, 12, 11)],
}


def _safe_date(year: int, month: int, day: int) -> _dt.date | None:
    """Build a date, backing the day off to the month's last valid day if needed
    (e.g. a curated (2, 30) for February). Returns ``None`` on a hopeless value."""
    for d in (day, 28, 1):
        try:
            return _dt.date(year, month, d)
        except ValueError:
            continue
    return None


def _lookup_windows(school, term_count: int):
    """Return the raw ``(sm, sd, em, ed)`` window list for a school, or ``None``.

    Cascade: per-school ``settings['term_windows']`` → per-education-system
    ``EducationSystemProfile.config['term_windows']`` → curated ``_TERM_CALENDARS``
    (country, then country-subsystem). Only returns a list whose length matches
    ``term_count`` — a shape mismatch falls through to the next layer, then to
    ``None`` (even split)."""
    def _valid(seq):
        if not isinstance(seq, (list, tuple)) or len(seq) != term_count:
            return None
        out: list[tuple[int, int, int, int]] = []
        for item in seq:
            if not isinstance(item, (list, tuple)) or len(item) != 4:
                return None
            try:
                out.append(tuple(int(x) for x in item))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
        return out

    # 1. per-school override
    settings_map = getattr(school, "settings", None) or {}
    override = _valid(settings_map.get("term_windows"))
    if override:
        return override

    iso = (getattr(school, "country_code", None) or "").strip().upper()[:2]
    sub = (getattr(school, "sub_system", None) or "").strip().upper()

    # 2. per-education-system profile config (admin-editable at profile level)
    try:
        from apps.policies.policy_registry import get_effective_policy
        from apps.siteconfig.education_profile_engine import resolve_profile_for_school

        policy = get_effective_policy(school) or {}
        profile = resolve_profile_for_school(
            school,
            requested_profile_code=str(policy.get("education_profile_code") or "").strip(),
            auto_create=False,
        )
        cfg = getattr(profile, "config", None) or {}
        prof_windows = _valid(cfg.get("term_windows") if isinstance(cfg, dict) else None)
        if prof_windows:
            return prof_windows
    except Exception:  # noqa: BLE001 — profile layer is best-effort
        logger.debug("_lookup_windows: profile resolve failed", exc_info=True)

    # 3. curated code module (country-subsystem, then bare country)
    if iso and sub:
        curated = _valid(_TERM_CALENDARS.get(f"{iso}-{sub}"))
        if curated:
            return curated
    if iso:
        return _valid(_TERM_CALENDARS.get(iso))
    return None


def resolve_term_windows(
    school,
    term_count: int,
    *,
    year_start: _dt.date,
    year_end: _dt.date,
    start_month: int,
) -> list[tuple[_dt.date, _dt.date]] | None:
    """Return real ``[(term_start, term_end), …]`` dates for a school's terms, or
    ``None`` when no usable calendar applies (caller then uses the even split).

    Two correctness rules, learned the hard way:

    1. **Alignment guard.** A curated calendar is authored around its country's
       real first-term month (Cameroon September, Kenya January). It is only
       applied when that first-term month equals the school's academic-year
       ``start_month`` — otherwise the year (say Sep→Aug) and the calendar (say
       Kenya's Jan→Dec) disagree, and the early terms would fall before
       ``year_start`` and clamp to a single day. When they disagree we return
       ``None`` and let the even split, which always fits the year, take over.

    2. **Sequential walk-anchor.** Windows are listed in teaching order, so each
       window's calendar year is assigned by WALKING the sequence and bumping the
       year whenever a term's start month wraps past the previous one (Dec→Jan) —
       and a window whose END month precedes its START month ends in the next
       year. Anchoring every month independently on ``start_month`` (the old bug)
       mis-dated any term sitting on the far side of it, producing ``start > end``
       windows that clamped to a zero-length term.

    Every date is still clamped inside ``[year_start, year_end]`` as a backstop."""
    raw = _lookup_windows(school, term_count)
    if not raw:
        return None

    # Alignment guard: the calendar's own first term must start in the same month
    # the academic year does, or it does not belong to this year window.
    if int(raw[0][0]) != int(start_month):
        return None

    windows: list[tuple[_dt.date, _dt.date]] = []
    cur_year = year_start.year
    prev_start_month: int | None = None
    for (sm, sd, em, ed) in raw:
        if prev_start_month is not None and sm < prev_start_month:
            cur_year += 1  # start month wrapped past December → next calendar year
        t_start = _safe_date(cur_year, sm, sd)
        end_year = cur_year + 1 if em < sm else cur_year
        t_end = _safe_date(end_year, em, ed)
        if t_start is None or t_end is None:
            return None  # a bad curated row → fall back to the even split wholesale
        # Clamp inside the academic year and keep start <= end (backstop).
        t_start = min(max(t_start, year_start), year_end)
        t_end = min(max(t_end, t_start), year_end)
        windows.append((t_start, t_end))
        prev_start_month = sm
    return windows
