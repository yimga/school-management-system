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

# Reusable regional window shapes (start_month, start_day, end_month, end_day per
# term, in teaching order). A country that follows a regional norm references the
# shared template; a country with a distinct calendar lists its own windows. The
# TEMPLATE's first-term month and length are what ``country_calendar_shape`` reads
# to drive a fresh ``RegionConfig``'s academic-year start month + term count — so
# the region shape and these windows can never disagree (which is exactly what the
# alignment guard in ``resolve_term_windows`` would otherwise reject).
_TRI_SEP_EN = [(9, 1, 12, 15), (1, 8, 4, 10), (4, 25, 7, 25)]        # Anglophone, 3 terms, Sep start
_TRI_SEP_FR = [(9, 15, 12, 20), (1, 7, 4, 5), (4, 20, 7, 10)]        # Francophone, 3 trimesters, Sep start
_TRI_OCT_FR = [(10, 1, 12, 22), (1, 8, 4, 5), (4, 20, 7, 10)]        # Sahel francophone, 3 trimesters, Oct start
_TRI_JAN = [(1, 8, 4, 10), (5, 2, 8, 8), (9, 2, 11, 28)]            # East/Southern Africa, 3 terms, Jan start
_TRI_FEB = [(2, 5, 5, 5), (5, 28, 8, 25), (9, 15, 12, 5)]           # 3 terms, Feb start (Uganda-style)
_TRI_FEB_SH = [(2, 1, 4, 30), (5, 15, 8, 15), (9, 1, 12, 5)]        # Southern-lusophone, 3 trimesters, Feb start
_SEM_SEP = [(9, 1, 1, 20), (2, 1, 6, 25)]                          # 2 semesters, Sep start (Europe / East Asia)
_SEM_AUG = [(8, 15, 12, 20), (1, 8, 5, 30)]                        # 2 semesters, Aug start (US-style)

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

    # ======================================================================
    # WEST AFRICA — Anglophone (WAEC, Sep start, 3 terms) & Francophone (bac)
    # ======================================================================
    "LR": _TRI_SEP_EN, "SL": _TRI_SEP_EN, "GM": _TRI_SEP_EN,
    "CI": _TRI_SEP_FR, "TG": _TRI_SEP_FR, "BJ": _TRI_SEP_FR, "CV": _TRI_SEP_FR,
    "SN": _TRI_OCT_FR, "ML": _TRI_OCT_FR, "BF": _TRI_OCT_FR, "NE": _TRI_OCT_FR,
    "GN": _TRI_OCT_FR, "MR": _TRI_OCT_FR, "GW": _TRI_OCT_FR,

    # ======================================================================
    # CENTRAL AFRICA — Francophone (Sep/Oct, 3 trimesters); Angola/Congo basin
    # ======================================================================
    "GA": _TRI_SEP_FR, "CG": _TRI_SEP_FR, "CD": _TRI_SEP_FR, "CF": _TRI_SEP_FR,
    "GQ": _TRI_SEP_FR, "BI": _TRI_SEP_FR, "ST": _TRI_SEP_FR,
    "TD": _TRI_OCT_FR,
    "AO": _TRI_FEB_SH,  # southern-hemisphere lusophone, year starts February

    # ======================================================================
    # EAST AFRICA & Indian Ocean — Jan/Feb 3 terms; Ethiopia 2 semesters (Sep)
    # ======================================================================
    "RW": _TRI_SEP_EN,          # REB, 3 terms, Sep start
    "SS": _TRI_FEB,             # South Sudan, Feb start
    "ET": _SEM_SEP, "SO": _SEM_SEP, "ER": _SEM_SEP, "SD": _SEM_SEP,
    "DJ": _TRI_SEP_FR, "KM": _TRI_SEP_FR,
    "MG": _TRI_OCT_FR,          # Madagascar, francophone
    "MU": _TRI_JAN, "SC": _TRI_JAN,  # Mauritius / Seychelles, Jan 3-term

    # ======================================================================
    # SOUTHERN AFRICA — Jan 3-term (ZA is 4-term, above); Malawi moved to Sep
    # ======================================================================
    "ZW": _TRI_JAN, "ZM": _TRI_JAN, "BW": _TRI_JAN, "NA": _TRI_JAN,
    "LS": _TRI_JAN, "SZ": _TRI_JAN,
    "MW": _TRI_SEP_EN,
    "MZ": _TRI_FEB_SH,          # Mozambique, southern lusophone

    # ======================================================================
    # NORTH AFRICA — Sep start; Egypt/Morocco/Libya 2 semesters, Maghreb 3 tri
    # ======================================================================
    "EG": [(9, 15, 1, 25), (2, 10, 6, 10)],
    "MA": [(9, 7, 1, 20), (1, 21, 6, 30)],
    "LY": _SEM_SEP,
    "DZ": [(9, 10, 12, 20), (1, 3, 3, 20), (4, 3, 7, 5)],
    "TN": [(9, 15, 12, 20), (1, 2, 3, 20), (4, 1, 6, 30)],

    # ======================================================================
    # EUROPE — Sep start; trimesters (ES/PT/IE/BE) or 2 semesters; RU 4 quarters
    # ======================================================================
    "ES": [(9, 10, 12, 20), (1, 8, 3, 28), (4, 8, 6, 22)],
    "PT": [(9, 15, 12, 17), (1, 4, 3, 25), (4, 5, 6, 14)],
    "IE": [(9, 1, 12, 20), (1, 6, 3, 28), (4, 10, 6, 28)],
    "BE": _TRI_SEP_FR,
    "IT": _SEM_SEP, "PL": _SEM_SEP, "AT": _SEM_SEP, "GR": _SEM_SEP,
    "RO": _SEM_SEP, "UA": _SEM_SEP,
    "NL": [(8, 25, 1, 31), (2, 1, 7, 15)],
    "SE": [(8, 20, 12, 20), (1, 10, 6, 10)],
    "NO": [(8, 18, 12, 20), (1, 2, 6, 20)],
    "DK": [(8, 10, 12, 20), (1, 2, 6, 25)],
    "FI": [(8, 10, 12, 20), (1, 8, 6, 3)],
    "CH": [(8, 20, 1, 31), (2, 1, 7, 5)],
    "RU": [(9, 1, 10, 27), (11, 6, 12, 28), (1, 9, 3, 22), (4, 1, 5, 27)],

    # ======================================================================
    # AMERICAS — US/CA above; Latin America (Feb/Mar 2-sem, southern); Caribbean
    # ======================================================================
    "MX": [(8, 26, 12, 20), (1, 8, 7, 15)],
    "BR": [(2, 1, 6, 30), (8, 1, 12, 15)],
    "AR": [(3, 1, 7, 15), (8, 1, 12, 10)],
    "CL": [(3, 1, 7, 10), (7, 28, 12, 15)],
    "PE": [(3, 1, 7, 20), (8, 10, 12, 20)],
    "CO": [(1, 20, 6, 10), (7, 8, 11, 30)],
    "JM": _TRI_SEP_EN, "TT": _TRI_SEP_EN, "BB": _TRI_SEP_EN,

    # ======================================================================
    # ASIA — varied start months; term count by national system
    # ======================================================================
    "JP": [(4, 8, 7, 20), (9, 1, 12, 25), (1, 8, 3, 25)],
    "KR": [(3, 2, 7, 20), (9, 1, 2, 10)],
    "CN": [(9, 1, 1, 15), (2, 20, 7, 5)],
    "HK": [(9, 1, 1, 20), (2, 1, 7, 10)],
    "ID": [(7, 15, 12, 20), (1, 8, 6, 20)],
    "MY": [(1, 2, 5, 31), (6, 16, 11, 20)],
    "PH": [(8, 22, 12, 20), (1, 8, 6, 15)],
    "TH": [(5, 16, 9, 30), (11, 1, 3, 15)],
    "VN": [(8, 20, 12, 31), (1, 8, 5, 25)],
    "SG": [(1, 2, 3, 15), (3, 25, 5, 31), (7, 1, 9, 1), (9, 9, 11, 20)],
    "PK": [(8, 1, 12, 20), (1, 2, 5, 31)],
    "BD": [(1, 1, 4, 30), (5, 1, 8, 31), (9, 1, 12, 15)],
    "LK": [(1, 2, 4, 5), (5, 2, 8, 10), (9, 2, 12, 10)],
    "NP": [(4, 15, 10, 5), (11, 1, 4, 5)],

    # ======================================================================
    # MENA / GULF — Sep/Aug start; Gulf reformed to 3 terms; Levant 2 semesters
    # ======================================================================
    "SA": [(8, 20, 11, 20), (11, 27, 3, 7), (3, 17, 6, 25)],
    "AE": [(9, 1, 12, 8), (1, 2, 3, 29), (4, 8, 7, 5)],
    "QA": [(8, 20, 12, 8), (1, 2, 3, 29), (4, 8, 6, 25)],
    "TR": [(9, 9, 1, 17), (2, 10, 6, 20)],
    "KW": _SEM_SEP, "BH": _SEM_SEP, "OM": _SEM_SEP, "JO": _SEM_SEP,
    "IL": _SEM_SEP, "IR": _SEM_SEP, "IQ": _SEM_SEP, "SY": _SEM_SEP, "YE": _SEM_SEP,
    "LB": _TRI_SEP_FR,

    # ======================================================================
    # OCEANIA — AU/NZ above (4-term); Pacific islands Jan start
    # ======================================================================
    "FJ": _TRI_JAN,
    "PG": [(1, 29, 6, 20), (7, 15, 12, 10)],

    # ======================================================================
    # EUROPE (remainder) — Sep start, mostly 2 semesters; Nordic/Alpine Aug
    # ======================================================================
    "AL": _SEM_SEP, "AM": _SEM_SEP, "AZ": _SEM_SEP, "BA": _SEM_SEP, "BG": _SEM_SEP,
    "BY": _SEM_SEP, "CY": _SEM_SEP, "CZ": _SEM_SEP, "EE": _SEM_SEP, "GE": _SEM_SEP,
    "HR": _SEM_SEP, "HU": _SEM_SEP, "LT": _SEM_SEP, "LV": _SEM_SEP, "MD": _SEM_SEP,
    "ME": _SEM_SEP, "MK": _SEM_SEP, "PL": _SEM_SEP, "RS": _SEM_SEP, "SI": _SEM_SEP,
    "SK": _SEM_SEP, "SM": _SEM_SEP, "VA": _SEM_SEP,
    "IS": [(8, 22, 12, 20), (1, 4, 5, 31)],
    "LI": [(8, 20, 1, 31), (2, 1, 7, 5)],
    "AD": _TRI_SEP_FR, "MC": _TRI_SEP_FR, "LU": _TRI_SEP_FR,
    "MT": _TRI_SEP_EN,

    # ======================================================================
    # CAUCASUS / CENTRAL ASIA / rest of MENA — Sep start, 2 semesters
    # ======================================================================
    "KZ": _SEM_SEP, "KG": _SEM_SEP, "TJ": _SEM_SEP, "TM": _SEM_SEP, "UZ": _SEM_SEP,
    "PS": _SEM_SEP, "EH": _SEM_SEP,
    "AF": [(3, 21, 8, 10), (8, 25, 12, 30)],  # Solar-year spring start

    # ======================================================================
    # ASIA (remainder) — national start months vary widely
    # ======================================================================
    "BN": [(1, 2, 5, 31), (6, 16, 11, 20)],   # Brunei, Jan (Malaysia-style)
    "BT": [(2, 1, 6, 15), (7, 10, 12, 10)],   # Bhutan, Feb
    "KH": [(11, 1, 3, 15), (3, 25, 8, 10)],   # Cambodia, Nov
    "KP": [(4, 1, 8, 20), (9, 1, 3, 25)],     # DPR Korea, April
    "MM": [(6, 1, 10, 20), (11, 1, 3, 10)],   # Myanmar, June
    "LA": _SEM_SEP, "MN": _SEM_SEP, "MO": _SEM_SEP,
    "MV": _TRI_JAN,                            # Maldives, Jan 3-term
    "TL": [(1, 2, 5, 31), (7, 15, 12, 10)],   # Timor-Leste, Jan (southern)
    "TW": [(9, 1, 1, 20), (2, 15, 6, 30)],    # Taiwan, Sep 2-sem

    # ======================================================================
    # LATIN AMERICA (remainder) — southern (Feb/Mar) & northern (Jan/Aug/Sep)
    # ======================================================================
    "VE": [(9, 16, 12, 20), (1, 8, 3, 28), (4, 8, 7, 10)],  # 3 lapsos, Sep
    "EC": [(9, 2, 1, 31), (2, 10, 7, 5)],     # Ecuador (Sierra regime), Sep
    "CU": _SEM_SEP,
    "DO": [(8, 19, 12, 20), (1, 8, 6, 15)],   # Dominican Rep, Aug
    "BO": [(2, 1, 6, 30), (7, 15, 11, 30)],   # Bolivia, Feb (southern)
    "PY": [(2, 15, 6, 30), (7, 20, 11, 30)],  # Paraguay, Feb (southern)
    "UY": [(3, 1, 7, 10), (7, 25, 12, 10)],   # Uruguay, Mar (southern)
    "CR": [(2, 8, 7, 5), (7, 17, 12, 15)],    # Costa Rica, Feb
    "NI": [(2, 1, 6, 15), (7, 8, 11, 30)],    # Nicaragua, Feb
    "HN": [(2, 1, 6, 20), (7, 20, 11, 30)],   # Honduras, Feb
    "GT": [(1, 15, 5, 30), (7, 1, 10, 20)],   # Guatemala, Jan
    "SV": [(1, 15, 5, 30), (7, 1, 11, 10)],   # El Salvador, Jan
    "PA": [(3, 1, 7, 10), (7, 22, 12, 20)],   # Panama, Mar
    "SR": [(10, 1, 2, 10), (2, 20, 7, 10)],   # Suriname, Oct (Dutch)
    "HT": _TRI_SEP_FR,                         # Haiti, francophone

    # ======================================================================
    # CARIBBEAN (English-speaking / Commonwealth) — Sep, 3 terms
    # ======================================================================
    "GY": _TRI_SEP_EN, "BZ": _TRI_SEP_EN, "AG": _TRI_SEP_EN, "BS": _TRI_SEP_EN,
    "DM": _TRI_SEP_EN, "GD": _TRI_SEP_EN, "KN": _TRI_SEP_EN, "LC": _TRI_SEP_EN,
    "VC": _TRI_SEP_EN,

    # ======================================================================
    # PACIFIC — US-affiliated (Aug); Melanesia/Polynesia/Micronesia (Jan/Feb)
    # ======================================================================
    "FM": _SEM_AUG, "MH": _SEM_AUG, "PW": _SEM_AUG,
    "KI": _TRI_JAN, "NR": _TRI_JAN, "SB": _TRI_JAN, "TO": _TRI_JAN, "TV": _TRI_JAN,
    "WS": _TRI_JAN,
    "VU": _TRI_FEB,
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


def _to_alpha2(code: str) -> str:
    """Best-effort ISO alpha-3 → alpha-2 (``_TERM_CALENDARS`` is alpha-2 keyed).

    An alpha-2 code passes through; an alpha-3 code is converted via ``pycountry``
    when available (it is a project dependency). If conversion is impossible the
    caller simply gets no curated shape and falls back to today's hemisphere
    default — never an exception."""
    raw = (code or "").strip().upper()
    if len(raw) == 2:
        return raw
    if len(raw) == 3:
        try:
            import pycountry  # project dependency (see apps/siteconfig/global_catalog.py)

            match = pycountry.countries.get(alpha_3=raw)
            if match and getattr(match, "alpha_2", None):
                return str(match.alpha_2).upper()
        except Exception:  # noqa: BLE001 — missing lib / unknown code → no shape
            pass
    # No reliable conversion: return "" so the caller gets no shape and keeps the
    # hemisphere default. A naive ``raw[:2]`` truncation would mis-map (CHN→"CH"
    # collides with Switzerland, MDG→"MD" is not Madagascar's "MG") — a wrong
    # calendar is worse than none.
    return ""


def country_calendar_shape(code: str) -> tuple[int, int] | None:
    """Return ``(academic_year_start_month, term_count)`` for a country, or ``None``.

    Derived from the SAME curated windows the term seeder uses, so a fresh
    ``RegionConfig`` created for this country carries a start month and term count
    that AGREE with the term-date calendar — otherwise ``resolve_term_windows``'s
    alignment guard would reject the calendar (a January-start country whose region
    still said September, or a 4-term country whose region still said 3, would
    silently drop to the even split). ``RegionConfig.code`` is ISO alpha-3, so an
    alpha-3 is accepted and normalized. Accepts the bare country only (subsystem
    specializations share the country's shape). Returns ``None`` for an unknown
    country — the caller then keeps the hemisphere-default behaviour."""
    raw = (code or "").strip().upper()
    if not raw:
        return None
    windows = _TERM_CALENDARS.get(raw) if len(raw) == 2 else None
    if windows is None:
        windows = _TERM_CALENDARS.get(_to_alpha2(raw))
    if not windows:
        return None
    return int(windows[0][0]), len(windows)
