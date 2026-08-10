"""Deterministic, offline-safe onboarding *decision model*.

The sibling :mod:`apps.schools.onboarding_recommendations` turns a school's
declared profile into a module / blueprint / plan manifest. This module answers
the question one step earlier: **for each configuration decision, which option
should the tenant pick, and do we even need to ask?**

It exists to push tenant configuration toward *less human intervention*:

  1. Every decision carries a ``recommended`` option — the UI badges it and
     pre-selects it, so the default path is "review and accept".
  2. Decisions the earlier answers already settle (connectivity implied by
     country, an exam board that is unambiguous for the country, a governance
     posture fixed by the jurisdiction) are marked ``ask = False`` — the UI
     applies them automatically and shows a compact, editable "we set this for
     you" note instead of a question.
  3. Decisions that cannot change any blueprint / module / compliance profile /
     plan for the *current* context are dropped entirely.

Everything here is pure, deterministic and derivable without a network call or
an AI provider, so it produces the same result on the edge as in the cloud and
is trivially testable. Human-facing strings are lazily translated; machine
codes (the option ``value``) are never translated and are what downstream
provisioning and the recommendation manifest consume.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.utils.translation import gettext_lazy as _

DECISIONS_VERSION = 1


# --------------------------------------------------------------------------- #
# Country / region derivation tables.
#
# These are intentionally small, curated starting points, NOT an exhaustive
# world atlas: each entry only sets a *recommended default* the tenant reviews
# and can override. Extend a set to make a market's default sharper. Anything
# not listed falls back to the "ask, don't assume" branch.
# --------------------------------------------------------------------------- #

# Markets where intermittent power / connectivity is the safe planning default,
# so offline-first capture and sync should be pre-selected.
_LIMITED_CONNECTIVITY_COUNTRIES = frozenset({
    "CM", "NG", "GH", "KE", "UG", "TZ", "RW", "ET", "SN", "CI", "ML", "BF",
    "ZM", "ZW", "MW", "MZ", "CD", "CG", "TD", "NE", "BJ", "TG", "GN", "SL",
    "LR", "GM", "BI", "SS", "SO", "MG", "AO", "NP", "MM", "AF", "BD", "PG",
})
# Markets where always-on broadband is the safe default.
_RELIABLE_CONNECTIVITY_COUNTRIES = frozenset({
    "US", "CA", "GB", "IE", "DE", "FR", "NL", "BE", "LU", "SE", "NO", "DK",
    "FI", "CH", "AT", "ES", "PT", "IT", "AU", "NZ", "JP", "KR", "SG", "AE",
    "QA", "HK", "TW", "IL", "EE",
})
# Region keys (from the country pack) that imply limited connectivity when the
# specific country code is not in either set above.
_LIMITED_CONNECTIVITY_REGIONS = frozenset({
    "africa-anglophone", "africa-francophone", "africa-lusophone",
    "west-africa", "east-africa", "central-africa", "sub-saharan",
})

# National exam / curriculum board recommended per country. Value codes are
# stable slugs consumed by the grading-scale and report-template registries.
_COUNTRY_CURRICULUM_BOARD = {
    "CM": "gce-bac", "NG": "waec-neco", "GH": "waec", "SL": "waec",
    "GM": "waec", "LR": "waec", "KE": "knec", "UG": "uneb", "TZ": "necta",
    "RW": "reb", "ZA": "caps-nsc", "GB": "gcse-alevel", "IE": "leaving-cert",
    "US": "state-standards", "CA": "provincial", "FR": "brevet-bac",
    "IN": "cbse-state", "PK": "matric-fsc", "BD": "national-bd",
    "AU": "australian-curriculum", "NZ": "ncea", "SG": "singapore-gce",
    "AE": "moe-uae", "ET": "national-et", "SN": "bac-sn", "CI": "bac-ci",
}

# Jurisdictions whose data-protection / ministry-reporting regime warrants the
# *strict* governance profile as the recommended default.
_STRICT_GOVERNANCE_COUNTRIES = frozenset({
    # EU / EEA + UK (GDPR / UK-GDPR)
    "GB", "IE", "DE", "FR", "NL", "BE", "LU", "SE", "NO", "DK", "FI", "CH",
    "AT", "ES", "PT", "IT", "PL", "GR", "EE",
    # Africa & Asia data-protection statutes in force
    "NG", "KE", "ZA", "GH", "UG", "RW", "IN", "SG", "AE",
    # North America sectoral / student-privacy regimes
    "US", "CA",
})

# Markets where mobile-money is a mainstream fee-collection rail, so a
# multi-channel recommendation is apt once fees are actually collected.
_MOBILE_MONEY_COUNTRIES = frozenset({
    "CM", "NG", "GH", "KE", "UG", "TZ", "RW", "ET", "SN", "CI", "ZM", "ZW",
    "CD", "CG", "BJ", "TG", "ML", "BF", "GN", "MW", "MZ", "MG",
})


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _cc(value: Any) -> str:
    return str(value or "").strip().upper()[:2]


def _cycles_text(cycles: list[str] | None) -> str:
    return " ".join(_norm(c) for c in (cycles or []) if c)


def _has_school_age(cycles: list[str] | None) -> bool:
    """True when the school covers a level where a daily session pattern and an
    exam board are meaningful (i.e. not a higher-ed-only institution)."""
    text = _cycles_text(cycles)
    if not text:
        return True  # unknown → keep the question; don't silently drop it
    school_tokens = (
        "preschool", "nursery", "kg", "kindergarten", "primary", "elementary",
        "middle", "junior", "secondary", "high", "sss", "jss", "tvet", "k12",
    )
    higher_tokens = ("university", "tertiary", "higher", "college")
    has_school = any(tok in text for tok in school_tokens)
    only_higher = (not has_school) and any(tok in text for tok in higher_tokens)
    return not only_higher


def _option(
    value: str,
    label: Any,
    *,
    recommended: bool = False,
    reason: Any = "",
    sub: Any = "",
) -> dict[str, Any]:
    return {
        "value": value,
        "label": label,
        "sub": sub,
        "recommended": bool(recommended),
        "reason": reason,
    }


def _mark(options: list[dict[str, Any]], recommended_value: str) -> list[dict[str, Any]]:
    """Flag the recommended option and clear the rest — single source of truth
    for which choice the UI badges and pre-selects."""
    for opt in options:
        opt["recommended"] = opt["value"] == recommended_value
    return options


def _dimension(
    key: str,
    *,
    label: Any,
    question: Any,
    options: list[dict[str, Any]],
    recommended_value: str,
    impact: list[str],
    ask: bool,
    auto_reason: Any = "",
    help_text: Any = "",
) -> dict[str, Any]:
    _mark(options, recommended_value)
    return {
        "key": key,
        "label": label,
        "question": question,
        "help": help_text,
        "options": options,
        "recommended_value": recommended_value,
        "impact": impact,
        # ``ask`` = surface as an interactive question. When False the caller
        # applies ``recommended_value`` automatically and shows an editable
        # "we set this for you" note (review-before-provision still holds).
        "ask": bool(ask),
        "auto_reason": auto_reason,
    }


# --------------------------------------------------------------------------- #
# Per-dimension recommenders
# --------------------------------------------------------------------------- #

def _connectivity(country: str, region_key: str) -> tuple[str, bool, Any]:
    """(recommended_value, ask, auto_reason). Auto-applied when the country or
    region gives a confident signal; otherwise asked with 'mixed' pre-selected."""
    if country in _RELIABLE_CONNECTIVITY_COUNTRIES:
        return "reliable", False, _("Set from your country's typical connectivity — change if your campuses lose power or internet.")
    if country in _LIMITED_CONNECTIVITY_COUNTRIES or region_key in _LIMITED_CONNECTIVITY_REGIONS:
        return "limited", False, _("Set for offline-first from your region — we include capture, sync and continuity so work never stops.")
    return "mixed", True, ""


def _curriculum_board(country: str, funding: str) -> tuple[str, bool, Any, dict[str, Any]]:
    """(recommended_value, ask, auto_reason, extra_option). Auto-applied when the
    country has an unambiguous national board; international/private schools are
    still asked because they may run Cambridge/IB instead."""
    national = _COUNTRY_CURRICULUM_BOARD.get(country, "")
    international_leaning = funding in {"private", "charter"}
    if national and not international_leaning:
        return national, False, _("Matched to your country's national examination board — switch to an international board below if you run one."), {}
    if national and international_leaning:
        # Private/independent: national is a strong default but ask, since IB /
        # Cambridge are common in this segment.
        return national, True, "", {}
    return "national-default", True, "", {}


def _governance(country: str) -> tuple[str, bool, Any]:
    if country in _STRICT_GOVERNANCE_COUNTRIES:
        return "strict", False, _("Set to strict compliance for your jurisdiction's data-protection and ministry-reporting rules — you can relax it if it does not apply.")
    return "standard", True, ""


def _payment(country: str, funding: str) -> str:
    if funding in {"private", "mission", "charter", "nonprofit"}:
        return "multi-channel" if country in _MOBILE_MONEY_COUNTRIES else "online"
    if funding == "public":
        return "basic"
    return "basic"


def _organization_scope(campus_count: int, declared_scope: str) -> tuple[str, bool]:
    if declared_scope in {"district", "network"}:
        return declared_scope, True
    if campus_count and campus_count > 1:
        # More than one campus was declared — network is unambiguous.
        return "network", False
    return "single", True


# --------------------------------------------------------------------------- #
# Public builder
# --------------------------------------------------------------------------- #

def build_onboarding_decisions(
    *,
    country_code: str = "",
    region_key: str = "",
    education_cycles: list[str] | None = None,
    funding_type: str = "",
    institution_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the progressive decision model for the setup form.

    The result is JSON-serialisable and stable for a given input, so it can be
    server-rendered *and* returned from the live preview endpoint from the same
    code path — no rule duplication between Python and JavaScript.
    """
    country = _cc(country_code)
    region = _norm(region_key)
    cycles = [c for c in (education_cycles or []) if c]
    profile = dict(institution_profile or {})
    funding = _norm(funding_type or profile.get("funding_type"))

    def _int(name: str, maximum: int) -> int:
        try:
            return min(maximum, max(0, int(profile.get(name) or 0)))
        except (TypeError, ValueError, OverflowError):
            return 0

    campus_count = _int("campus_count", 10_000)
    school_age = _has_school_age(cycles)

    dimensions: list[dict[str, Any]] = []

    # 1. Organization scope -------------------------------------------------- #
    scope_value, scope_ask = _organization_scope(campus_count, _norm(profile.get("organization_scope")))
    dimensions.append(_dimension(
        "organization_scope",
        label=_("Organization"),
        question=_("How is your institution organized?"),
        options=[
            _option("single", _("One campus"), sub=_("A single school and administration team."), reason=_("Simplest setup for a standalone school.")),
            _option("district", _("District"), sub=_("A district office overseeing member schools.")),
            _option("network", _("School network"), sub=_("Multiple campuses with shared governance."), reason=_("Adds cross-campus governance and analytics.")),
        ],
        recommended_value=scope_value,
        impact=["blueprint", "module", "plan"],
        ask=scope_ask,
        auto_reason=_("Set from the campus count you entered — you can change it below.") if not scope_ask else "",
    ))

    # 2. Operating model ----------------------------------------------------- #
    dimensions.append(_dimension(
        "operating_model",
        label=_("Operating model"),
        question=_("How does the school day work?"),
        options=[
            _option("day", _("Day school"), sub=_("Core academics, people and finance."), reason=_("The lean default — nothing you won't use.")),
            _option("boarding", _("Boarding"), sub=_("Add hostel, welfare and duty operations.")),
            _option("mixed", _("Day and boarding"), sub=_("Both day learners and boarders.")),
        ],
        recommended_value="day",
        impact=["module"],
        ask=True,
    ))

    # 3. Connectivity -------------------------------------------------------- #
    conn_value, conn_ask, conn_reason = _connectivity(country, region)
    dimensions.append(_dimension(
        "connectivity_profile",
        label=_("Connectivity"),
        question=_("How reliable is internet at your campuses?"),
        options=[
            _option("reliable", _("Reliable internet"), sub=_("Cloud-first with normal offline protection.")),
            _option("mixed", _("Mixed"), sub=_("Usually online, occasionally not.")),
            _option("limited", _("Often limited or offline"), sub=_("Prioritize local-first and sync workflows.")),
        ],
        recommended_value=conn_value,
        impact=["module", "plan"],
        ask=conn_ask,
        auto_reason=conn_reason,
    ))

    # 4. Fee collection ------------------------------------------------------ #
    pay_value = _payment(country, funding)
    dimensions.append(_dimension(
        "payment_profile",
        label=_("Fee collection"),
        question=_("How will you collect fees?"),
        options=[
            _option("basic", _("Simple or not needed"), sub=_("Record-keeping only, no online collection.")),
            _option("online", _("Online payments"), sub=_("Cards and bank transfer.")),
            _option("multi-channel", _("Online, cash and mobile money"), sub=_("Every rail your families use."), reason=_("Matches mobile-money-first markets.")),
        ],
        recommended_value=pay_value,
        impact=["module", "plan"],
        # Fee collection is irrelevant for a fully public, no-fee school → don't
        # force the question when funding says there's nothing to collect.
        ask=funding != "public",
        auto_reason=_("Public schools start with record-keeping only — add collection later if you need it.") if funding == "public" else "",
    ))

    # 5. Session pattern (NEW nuance) --------------------------------------- #
    if school_age:
        dimensions.append(_dimension(
            "session_pattern",
            label=_("Session pattern"),
            question=_("How are teaching sessions scheduled?"),
            options=[
                _option("single", _("Single session"), sub=_("One cohort, one daily timetable."), reason=_("The standard pattern for most schools.")),
                _option("double", _("Double shift"), sub=_("Separate morning and afternoon cohorts.")),
                _option("continuous", _("Continuous / flexible"), sub=_("Rolling or block scheduling.")),
            ],
            recommended_value="single",
            impact=["blueprint", "module"],
            ask=True,
            help_text=_("Double-shift splits timetable, attendance and staffing into two cohorts."),
        ))

    # 6. Curriculum / exam board (NEW nuance) ------------------------------- #
    if school_age:
        board_value, board_ask, board_reason, _extra = _curriculum_board(country, funding)
        board_options = [
            _option("national-default", _("National curriculum"), sub=_("Your country's standard curriculum and grading.")),
            _option("cambridge", _("Cambridge International"), sub=_("IGCSE / A-Level.")),
            _option("ib", _("International Baccalaureate"), sub=_("PYP / MYP / DP.")),
        ]
        # Surface the specific national board as its own option when we know it.
        if board_value not in {"national-default", "cambridge", "ib"}:
            board_options.insert(0, _option(
                board_value,
                _("National examination board"),
                sub=_("Grading scale and report templates for your country."),
                reason=_("Matched to your country."),
            ))
        dimensions.append(_dimension(
            "curriculum_board",
            label=_("Curriculum / exam board"),
            question=_("Which curriculum or examination board do you follow?"),
            options=board_options,
            recommended_value=board_value,
            impact=["blueprint", "module", "compliance"],
            ask=board_ask,
            auto_reason=board_reason,
            help_text=_("Sets grading scales, report-card templates and examination modules."),
        ))

    # 7. Governance / data-residency (NEW nuance) --------------------------- #
    gov_value, gov_ask, gov_reason = _governance(country)
    dimensions.append(_dimension(
        "governance_profile",
        label=_("Governance"),
        question=_("How strict are your compliance requirements?"),
        options=[
            _option("standard", _("Standard"), sub=_("Sensible defaults for most schools.")),
            _option("strict", _("Strict"), sub=_("Data-residency, consent and ministry reporting."), reason=_("Matches regulated jurisdictions.")),
        ],
        recommended_value=gov_value,
        impact=["compliance"],
        ask=gov_ask,
        auto_reason=gov_reason,
    ))

    ask_keys = [d["key"] for d in dimensions if d["ask"]]
    auto_keys = [d["key"] for d in dimensions if not d["ask"]]
    recommended = {d["key"]: d["recommended_value"] for d in dimensions}
    auto_applied = {d["key"]: d["recommended_value"] for d in dimensions if not d["ask"]}

    fingerprint_payload = {
        "v": DECISIONS_VERSION,
        "country": country,
        "region": region,
        "cycles": sorted(_norm(c) for c in cycles),
        "funding": funding,
        "campus_count": campus_count,
        "recommended": recommended,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]

    return {
        "version": DECISIONS_VERSION,
        "fingerprint": fingerprint,
        "country_code": country,
        "region_key": region,
        "dimensions": dimensions,
        "recommended": recommended,
        "auto_applied": auto_applied,
        "ask_keys": ask_keys,
        "auto_keys": auto_keys,
        "offline_safe": True,
    }
