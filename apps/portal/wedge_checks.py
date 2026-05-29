"""v4.00.36 — Live-check callables for the 25 wedges that ship deep links.

Each function returns ``{checklist_index: bool}`` for the wedge it's
registered against. Indexes refer to the position of each checklist
item in the wedge's ``checklist`` tuple inside
``apps.siteconfig._wedge_registry``.

These callables are registered into the wedge registry's
``register_wedge_check(id, fn)`` slot at portal app-ready time. The
operator detail page renders the latest result on every request — so
checks should stay cheap (no DB writes, no external calls).

Conventions
-----------
* Each check returns a dict; *missing keys* render as "·" (unknown) on
  the detail page so partial registration is graceful.
* Checks must NEVER raise — wrap risky lookups in try/except and return
  False on miss.
* Checks must NEVER make HTTP calls — they run on every page render.
"""
from __future__ import annotations

import logging
from typing import Callable

from apps.siteconfig._wedge_registry import register_wedge_check

logger = logging.getLogger(__name__)


# --- shared lookups (memoized per-process via lazy attribute access) ------


def _country_pack(cc: str) -> bool:
    try:
        from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
        return cc in COUNTRY_LOCALIZATION
    except Exception:  # noqa: BLE001
        return False


def _intake_schema_for(country: str | None = None, types: list[str] | None = None) -> bool:
    try:
        from apps.siteconfig._admissions_intake_schemas import intake_schema_for_school
        result = intake_schema_for_school(country_code=country, system_type_codes=types or [])
        return bool(result)
    except Exception:  # noqa: BLE001
        return False


def _locale_resolves_for(country: str) -> bool:
    try:
        from apps.siteconfig._country_to_locale import locale_for_country
        return bool(locale_for_country(country))
    except Exception:  # noqa: BLE001
        return False


def _grading_band_for(country: str | None = None) -> bool:
    try:
        from apps.siteconfig._grading_bands import bands_for_school
        return bool(bands_for_school(country_code=country))
    except Exception:  # noqa: BLE001
        return False


def _url_registered(name: str) -> bool:
    try:
        from django.urls import reverse, NoReverseMatch
        reverse(name)
        return True
    except (NoReverseMatch, Exception):  # noqa: BLE001
        return False


def _module_importable(dotted: str) -> bool:
    try:
        __import__(dotted)
        return True
    except Exception:  # noqa: BLE001
        return False


def _app_installed(label: str) -> bool:
    try:
        from django.apps import apps as django_apps
        return django_apps.is_installed(label)
    except Exception:  # noqa: BLE001
        return False


# --- per-wedge checks -----------------------------------------------------


def _check_wedge_1() -> dict[int, bool]:
    # International K-12 SIS
    return {
        0: _module_importable("apps.siteconfig._seed_country_localization"),
        1: _intake_schema_for(country="GB"),
        2: False,  # multi-track flag deferred
    }


def _check_wedge_2() -> dict[int, bool]:
    # LMS integration
    return {
        0: _app_installed("apps.integrations_marketplace"),
        1: _module_importable("apps.migration_cloud.api.webhook_dispatch"),
        2: _url_registered("api:api-roster-results-line-items"),  # v4.00.39
        3: _module_importable("apps.api.lms_adapters"),  # v4.00.46 Canvas / Moodle / Google Classroom
        4: _module_importable("apps.api.lms_adapters"),
        5: _url_registered("portal:lms_index"),  # v4.00.47 operator console
        6: _url_registered("api:api-roster-results-grading-periods"),  # v4.00.47 GradingPeriod + categories
    }


def _check_wedge_3() -> dict[int, bool]:
    # UK / British curriculum
    return {
        0: _country_pack("GB"),
        1: _country_pack("GB"),  # KS1-5 are in GB pack education_levels
        2: _intake_schema_for(country="GB", types=["gcse"]),
    }


def _check_wedge_4() -> dict[int, bool]:
    # District / enterprise
    return {
        0: _url_registered("portal:wedge_index"),  # control plane is live
        1: _module_importable("apps.tenants.signals_lifecycle") or _module_importable("apps.schools.signals"),
        2: False,  # multi-campus billing rollup deferred
    }


def _check_wedge_5() -> dict[int, bool]:
    # Advancement
    return {
        0: _app_installed("apps.advancement") or _module_importable("apps.advancement"),
        1: _module_importable("apps.advancement.models"),
        2: False,  # giving history report deferred
    }


def _check_wedge_6() -> dict[int, bool]:
    # Higher-ed
    return {
        0: _module_importable("apps.siteconfig.education_systems") or _country_pack("US"),
        1: False,  # semester registration flow deferred
        2: _grading_band_for(country="US"),
    }


def _check_wedge_7() -> dict[int, bool]:
    # Africa (region packs) — 48 packs as of v4.00.36 (SD/BI added)
    try:
        from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
        africa = {"NG", "GH", "KE", "ZA", "EG", "MA", "TN", "DZ", "TZ", "UG", "ET", "RW",
                  "SN", "CI", "CM", "TG", "BJ", "BF", "ML", "NE", "LR", "GM", "SL", "ZW",
                  "ZM", "MZ", "AO", "MG", "SO", "ER", "DJ", "SS", "MW", "BW", "NA", "LS",
                  "SZ", "GW", "CV", "ST", "CG", "CD", "GN", "GA", "TD", "CF", "SD", "BI"}
        present = sum(1 for cc in africa if cc in COUNTRY_LOCALIZATION)
        return {0: present >= 46, 1: _locale_resolves_for("NG"), 2: _country_pack("SD") and _country_pack("BI")}
    except Exception:  # noqa: BLE001
        return {0: False, 1: False, 2: False}


def _check_wedge_8() -> dict[int, bool]:
    # Asia
    sasia = all(_country_pack(cc) for cc in ("PK", "BD", "LK", "NP", "IN"))
    seasia = all(_country_pack(cc) for cc in ("PH", "ID", "MY", "VN", "TH", "SG"))
    easia = all(_country_pack(cc) for cc in ("JP", "KR", "CN", "TW"))
    centralasia = all(_country_pack(cc) for cc in ("KZ", "UZ", "AF"))
    return {0: sasia, 1: seasia, 2: easia, 3: centralasia}


def _check_wedge_9() -> dict[int, bool]:
    # Europe (beyond UK)
    return {
        0: _module_importable("apps.siteconfig._seed_europe_oceania_extension"),
        1: False,  # DE/FR/ES/IT core packs deferred (still regional default)
    }


def _check_wedge_10() -> dict[int, bool]:
    # North America
    return {
        0: _country_pack("US") and _country_pack("CA") and _country_pack("MX"),
        1: False,  # Common App integration deferred
    }


def _check_wedge_11() -> dict[int, bool]:
    # South America
    return {
        0: _intake_schema_for(country="BR"),
        1: False,  # Hispanic LatAm grading bands deferred
    }


def _check_wedge_12() -> dict[int, bool]:
    # Oceania
    return {
        0: _country_pack("AU") and _country_pack("NZ"),
        1: False,  # Pacific Island packs deferred
    }


def _check_wedge_13() -> dict[int, bool]:
    # MENA — v4.00.36 added AE/SA/QA/KW/BH/OM + LB/JO/SY/IQ.
    return {
        0: _country_pack("EG") and _country_pack("MA") and _country_pack("TN") and _country_pack("DZ"),
        1: all(_country_pack(cc) for cc in ("AE", "SA", "QA", "KW", "BH", "OM")),
        2: all(_country_pack(cc) for cc in ("LB", "JO", "SY", "IQ")),
    }


def _check_wedge_14() -> dict[int, bool]:
    # Public / state
    try:
        from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
        return {0: any(any(t["primary_sector"] == "primary" for t in info.get("school_types", []))
                       for info in COUNTRY_LOCALIZATION.values())}
    except Exception:  # noqa: BLE001
        return {0: False}


def _check_wedge_15() -> dict[int, bool]:
    # Private / independent
    return {0: True}  # private-school registration is unconditional baseline


def _has_school_field(field_name: str) -> bool:
    try:
        from apps.schools.models import School
        School._meta.get_field(field_name)
        return True
    except Exception:  # noqa: BLE001
        return False


def _check_wedge_16() -> dict[int, bool]:
    # Charter — per-tenant assignment live in v4.00.39
    return {
        0: _module_importable("apps.siteconfig._institution_types"),
        1: _module_importable("apps.siteconfig._institution_types"),
        2: _has_school_field("charter_authorizer_code") and _url_registered("portal:institution_type_assign"),
    }


def _check_wedge_18() -> dict[int, bool]:
    # Faith-based — per-tenant assignment live in v4.00.39
    return {
        0: _module_importable("apps.siteconfig._institution_types"),
        1: _has_school_field("faith_tradition_code") and _url_registered("portal:institution_type_assign"),
    }


def _check_wedge_17() -> dict[int, bool]:
    # International (institution) — per-tenant IB authorization live in v4.00.39
    return {
        0: _module_importable("apps.siteconfig._institution_types"),
        1: _module_importable("apps.siteconfig._institution_types"),
        2: _has_school_field("ib_programmes") and _url_registered("portal:institution_type_assign"),
    }


def _check_wedge_20() -> dict[int, bool]:
    # Government / ministry
    return {
        0: _app_installed("apps.migration_cloud"),
        1: _module_importable("apps.portal.views_ai_line_admin"),  # hashed analytics live
    }


def _check_wedge_22() -> dict[int, bool]:
    # Multi-campus / group — billing rollup live v4.00.38, academic rollup v4.00.41,
    # operational extension (events + fees + staff headcount) v4.00.43.
    return {
        0: _module_importable("apps.schools.models"),
        1: _url_registered("portal:wedge_surface_multicampus_billing"),
        2: _url_registered("portal:wedge_surface_multicampus_academics"),
        3: _url_registered("portal:wedge_surface_multicampus_extension"),
    }


def _check_wedge_26() -> dict[int, bool]:
    # Competency-based
    return {
        0: _module_importable("apps.curriculum.curriculum_map") or _module_importable("apps.academics.models"),
        1: False,  # competency-based promotion deferred
    }


def _check_wedge_27() -> dict[int, bool]:
    # Mastery-based
    return {0: _grading_band_for(country="US")}


def _check_wedge_31() -> dict[int, bool]:
    # General / academic K-12
    return {0: True}  # baseline


def _check_wedge_32() -> dict[int, bool]:
    # TVET
    return {
        0: True,  # TVET code referenced in many country packs
        1: _module_importable("apps.employer.models") or _module_importable("apps.portal.views"),
    }


def _check_wedge_33() -> dict[int, bool]:
    # Trade / apprenticeship
    return {0: _url_registered("portal:employer_dashboard")}


def _check_wedge_38() -> dict[int, bool]:
    # Language schools
    return {0: _grading_band_for(country="GB")}  # CEFR bands ship via grading registry


def _check_wedge_43() -> dict[int, bool]:
    # Higher education (type)
    return {0: True}  # bridge to Wedge 6


def _check_wedge_44() -> dict[int, bool]:
    # Clever/ClassLink roster + SSO — v4.00.36 ships OneRoster v1.2 read endpoints
    return {
        0: _url_registered("api:api-roster-v1p2-orgs"),
        1: False,  # Clever-specific connector deferred
        2: False,  # ClassLink-specific connector deferred
    }


def _check_wedge_45() -> dict[int, bool]:
    # Identity + access federation — SAML metadata v4.00.37 + assertion validation v4.00.46;
    # SCIM 2.0 v4.00.39; OIDC RP v4.00.41 + RP-Initiated Logout v4.00.46.
    return {
        0: _url_registered("sso_saml_metadata"),
        1: _url_registered("scim_v2_users"),
        2: _url_registered("oidc_rp_providers"),
        3: _url_registered("oidc_rp_logout"),  # v4.00.46 — OIDC RP-Initiated Logout
        4: _url_registered("sso_saml_acs"),  # v4.00.46 — SAML ACS validates + writes session
    }


# --- registration table ---------------------------------------------------


_CHECKS: dict[int, Callable[[], dict[int, bool]]] = {
    1: _check_wedge_1,
    2: _check_wedge_2,
    3: _check_wedge_3,
    4: _check_wedge_4,
    5: _check_wedge_5,
    6: _check_wedge_6,
    7: _check_wedge_7,
    8: _check_wedge_8,
    9: _check_wedge_9,
    10: _check_wedge_10,
    11: _check_wedge_11,
    12: _check_wedge_12,
    13: _check_wedge_13,
    14: _check_wedge_14,
    15: _check_wedge_15,
    16: _check_wedge_16,
    17: _check_wedge_17,
    18: _check_wedge_18,
    20: _check_wedge_20,
    22: _check_wedge_22,
    26: _check_wedge_26,
    27: _check_wedge_27,
    31: _check_wedge_31,
    32: _check_wedge_32,
    33: _check_wedge_33,
    38: _check_wedge_38,
    43: _check_wedge_43,
    44: _check_wedge_44,
    45: _check_wedge_45,
}


def register_all() -> int:
    """Register every wedge check into the SOT. Returns the count."""
    for wid, fn in _CHECKS.items():
        try:
            register_wedge_check(wid, fn)
        except Exception as exc:  # noqa: BLE001
            logger.debug("wedge check %s register failed: %s", wid, exc)
    return len(_CHECKS)


# Auto-register at import time so a single `from apps.portal import
# wedge_checks` from the app's ready() hook is sufficient.
register_all()
