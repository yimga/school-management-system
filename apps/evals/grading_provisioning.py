"""Local-first grading provisioning — the missing link in studio academic seeding.

At school provision the country pack already drives the academic year, terms, subjects,
and class structure, but the per-school ``GradingScale`` row was NEVER created — a new
school landed with the country's grading scale computed into ``school.settings`` yet no
GradingScale model row, so the dashboard read "no grading scale configured" until an
admin manually ran the grading wizard and blind-picked from a generic list.

``ensure_local_grading_scale`` closes that gap: it resolves the school's COUNTRY grading
scale (Education-DNA preset → scale type), creates a per-school default ``GradingScale``
with country-appropriate bands (from ``GRADING_SCALE_BANDS``) + a passing threshold, and
seeds a matching school-wide default ``AssessmentWeights`` so letter/GPA computation uses
the right scale from day one. Idempotent, tenant-scoped, and it NEVER overrides a scale an
admin already chose (a wizard-default or any existing default scale wins).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Sentinel for "the caller did not supply a fallback" — distinct from an explicit
# ``default=None``, which is itself a meaningful choice for display callers.
_UNSET: Any = object()


# The bound to apply when the school — and therefore the scale — is unknown.
# For an UPPER bound, failing closed means choosing the NARROWEST plausible axis,
# never the widest: an over-tight bound rejects a legitimate mark loudly, while a
# 100-point assumption admits an illegitimate one silently. 20 is this platform's
# historical narrow default and is already what ``_validate_ocr_entries`` and
# ``_normalized_scale_max`` fall back to, so the three bound-enforcing callers agree.
UNRESOLVED_SCALE_FALLBACK_MAX = Decimal("20")


class UnresolvedScoreScale(RuntimeError):
    """No score-scale max could be determined for the given school.

    Raised by :func:`resolve_school_score_scale` when it is handed no school (or a
    school whose scale cannot be derived) and the caller supplied no ``default``.

    This used to be a silent ``Decimal("100")``. Returning the platform's WIDEST
    scale as the "unknown" answer inverts the safety of every bound built on it:
    a /20 school whose school link came back empty accepted a mark of 25, which
    is exactly what a real Cameroon end-to-end run recorded. Callers that need a
    bound must now handle the unknown; callers that only need a display
    denominator opt in explicitly with ``default=100``.
    """


# Education-DNA preset key (apps.governance.academic_pack_bridge.resolve_grading_preset_key)
# → GradingScale.ScaleType. Keeps the country→scale decision in one auditable place.
_PRESET_TO_SCALE_TYPE: dict[str, str] = {
    "francophone_bac": "french_0_20",       # France / Francophone Africa — 0–20
    "west_african_waec": "waec_letter",       # WAEC raw scores are percentages
    "east_asia_competitive": "percentage",   # CN/KR/JP — 0–100
    "american": "us_letter",                   # US — letter bands on 0–100
    "british_igcse": "uk_gcse_9_1",           # UK GCSE 9–1
    "ib_programme": "ib_1_7",
    "german_standard": "german_1_6",
    "indian_cbse": "cbse_10",
    "generic": "percentage",
}

_LOCAL_DEFAULT_CODE = "local-default"
_VALID_SCALE_TYPES = {
    "numeric_0_20", "letter_a_e", "gpa_4_0", "percentage", "numeric_1_5",
    "waec_letter", "pass_fail", "qualitative_pd", "standard_score_t",
    "uk_gcse_9_1", "ib_1_7", "german_1_6", "cbse_10", "french_0_20", "us_letter",
}


def _normalize_scale_type(raw: Any) -> str:
    """Coerce a raw ``default_grading_scale`` value (a ScaleType or a wizard option
    key like ``gpa_4`` / ``letter``) to a known ScaleType, else ""."""
    val = str(raw or "").strip().lower().replace("-", "_")
    if val in _VALID_SCALE_TYPES:
        return val
    try:
        from apps.evals.grading_wizard_kernel import _SCALE_TYPE_MAP

        return _SCALE_TYPE_MAP.get(val, "")
    except Exception:  # noqa: BLE001 — wizard map is best-effort
        return ""


def _school_explicit_scale_type(school) -> str:
    """A grading scale EXPLICITLY chosen for THIS school, read straight from
    ``school.settings`` — NOT the platform-wide default.

    Local-first hinges on this distinction: ``get_effective_site_settings`` merges
    the platform singleton's ``default_grading_scale`` UNDER every school, so a
    global default is indistinguishable from a per-tenant choice once resolved.
    Reading the per-tenant layer directly lets a real admin choice win while a
    platform default stays a below-country hint (see ``resolve_local_scale_type``).
    Honors the nested wizard bucket (``settings['runtime_defaults']``) first — that
    is where ``set_runtime_default`` persists and it wins in the effective merge —
    then a top-level key.
    """
    settings = getattr(school, "settings", None)
    if not isinstance(settings, dict):
        return ""
    rd = settings.get("runtime_defaults")
    if isinstance(rd, dict):
        nested = _normalize_scale_type(rd.get("default_grading_scale"))
        if nested in _VALID_SCALE_TYPES:
            return nested
    return _normalize_scale_type(settings.get("default_grading_scale"))


def _scale_type_from_cascade(school) -> str:
    """The EFFECTIVE ``default_grading_scale`` for ``school`` (per-tenant layer
    merged over the platform singleton). When the per-tenant layer is blank this
    is the platform-wide default — used by ``resolve_local_scale_type`` only as a
    seed-time hint BELOW country derivation, never as a hard override. Else ""."""
    try:
        from apps.platform_runtime.config_resolver import get_effective_config

        raw = get_effective_config(key="default_grading_scale", school=school, default="")
    except Exception:  # noqa: BLE001 — cascade is best-effort
        return ""
    return _normalize_scale_type(raw)


def country_default_scale_type(country_code: Any) -> str:
    """The DATA-driven country → scale mapping: ``siteconfig.CountryGradingProfile``.

    Globalization program 2.1. Adding or correcting a country is a row in a SHARED
    platform-catalog table (seeded by ``siteconfig.country_grading_seed``, editable
    by an operator), never a code branch — the same idiom as ``CountryMultiplier``
    and ``SubdivisionTaxRate``.

    Returns "" when the country has no active row, so the caller falls through to
    the older Education-DNA preset engine rather than losing a mapping.
    """
    iso = str(country_code or "").strip().upper()
    if not iso:
        return ""
    try:
        from django.apps import apps as django_apps

        model = django_apps.get_model("siteconfig", "CountryGradingProfile")
        raw = (
            model.objects.filter(country_code__iexact=iso, is_active=True)
            .values_list("scale_type", flat=True)
            .first()
        )
    except Exception as exc:  # noqa: BLE001 — catalog read is best-effort; preset engine still answers
        logger.debug("country_default_scale_type lookup failed cc=%s err=%s", iso, exc)
        return ""
    normalized = _normalize_scale_type(raw)
    return normalized if normalized in _VALID_SCALE_TYPES else ""


def resolve_local_scale_type(school) -> str:
    """The grading scale a school SHOULD use, local-first. Always a valid ScaleType.

    Precedence:
      1. An explicit per-school choice (``school.settings``) — a real admin pick wins.
      2. The school's COUNTRY row in ``siteconfig.CountryGradingProfile`` — the
         data-driven national default (Globalization program 2.1).
      3. The school's COUNTRY Education-DNA preset — the legacy code cascade, kept
         as a fallback for countries with no catalog row yet. A platform-wide
         ``default_grading_scale`` must NOT override either country leg, or every
         tenant silently inherits one country's scale.
      4. The platform-wide default, as a seed-time hint, only when there is no
         country signal to derive from.
      5. "percentage" — the most internationally neutral fallback.
    """
    explicit = _school_explicit_scale_type(school)
    if explicit in _VALID_SCALE_TYPES:
        return explicit
    country_code = (getattr(school, "country_code", "") or "").strip()
    if country_code:
        from_catalog = country_default_scale_type(country_code)
        if from_catalog in _VALID_SCALE_TYPES:
            return from_catalog
        try:
            from apps.governance.academic_pack_bridge import resolve_grading_preset_key

            preset = resolve_grading_preset_key(country_code)
            mapped = _PRESET_TO_SCALE_TYPE.get(preset)
            if mapped in _VALID_SCALE_TYPES:
                return mapped
        except Exception as exc:  # noqa: BLE001 — fall through to platform hint / neutral default
            logger.debug("resolve_local_scale_type preset failed cc=%s err=%s", country_code, exc)
    platform_hint = _scale_type_from_cascade(school)
    if platform_hint in _VALID_SCALE_TYPES:
        return platform_hint
    return "percentage"


def _scale_config(scale_type: str) -> dict[str, Any]:
    """Country-appropriate band config + passing threshold for a scale type."""
    from apps.evals.models import default_bands_for_scale

    bands = default_bands_for_scale(scale_type)
    config: dict[str, Any] = {
        "score_scale": int(bands.get("score_scale", 20)),
        "pass_threshold": float(bands.get("d", 0)),  # lowest passing band (D)
        "grade_thresholds": {
            "A": float(bands.get("a", 0)),
            "B": float(bands.get("b", 0)),
            "C": float(bands.get("c", 0)),
            "D": float(bands.get("d", 0)),
            "E": float(bands.get("e", 0)),
        },
    }
    try:
        from apps.evals.grading_formula_engine import PRESET_GRADING_FORMULAS

        formula = PRESET_GRADING_FORMULAS.get(scale_type)
        if formula:
            config["formula_text"] = formula
    except Exception:  # noqa: BLE001 — formula is optional decoration
        pass
    return config


def resolve_school_score_scale(school, *, default: Any = _UNSET) -> Decimal:
    """The numeric score-scale MAX a school computes grades on (operational SoT).

    Reads the school's default ``AssessmentWeights.score_scale`` — the exact scale
    grade computation and ``GradeConverter`` use — so any scale-bounded check (OCR
    score validation, the early-warning drop yardstick) stays consistent with how
    grades are actually scored: 20 for a francophone /20 school, 100 percentage,
    4 GPA. Falls back to the country-derived scale's band ``score_scale``.

    **Fails closed.** With no school (or a school whose scale cannot be derived at
    all) there is nothing to bound a mark against, so this raises
    :class:`UnresolvedScoreScale` unless the caller passes an explicit ``default``.
    It used to return ``Decimal("100")`` — the platform's WIDEST scale — which
    turned every broken school link into a silent widening of the accepted range
    and let a mark of 25 through on a /20 school.

    Pass ``default=100`` (or any value) from callers that only need a display
    denominator or a ratio and must never break a page render; do NOT pass one
    from a caller that is enforcing an upper bound.

    Deliberately NOT ``apps.evals.grading.max_score_for_school`` (locale-derived):
    that lags the per-school seeded scale — it reports 100 for a /20 francophone
    school whose AssessmentWeights.score_scale is 20 — so using it for an upper-bound
    check would be too lenient and inconsistent with grade computation.
    """
    if school is not None:
        if getattr(school, "pk", None) is not None:
            try:
                from apps.evals.models import AssessmentWeights

                weights = (
                    AssessmentWeights.objects.filter(
                        school=school, term=None, classroom=None
                    )
                    .order_by("-academic_year")
                    .first()
                    or AssessmentWeights.objects.filter(school=school)
                    .order_by("-academic_year")
                    .first()
                )
                if weights is not None and getattr(weights, "score_scale", None):
                    return Decimal(str(weights.score_scale))
            except Exception:  # noqa: BLE001 — operational read is best-effort
                pass
        try:
            score_scale = _scale_config(resolve_local_scale_type(school)).get("score_scale")
            if score_scale:
                return Decimal(str(score_scale))
        except Exception as exc:  # noqa: BLE001 — fall through to the fail-closed branch
            logger.debug(
                "resolve_school_score_scale band lookup failed school_id=%s err=%s",
                getattr(school, "pk", None),
                exc,
            )
    if default is _UNSET:
        raise UnresolvedScoreScale(
            "No grading scale could be resolved for school="
            f"{getattr(school, 'pk', None)!r}; refusing to assume a 100-point scale."
        )
    return Decimal(str(default))


def ensure_local_grading_scale(school, *, academic_year=None) -> dict[str, Any]:
    """Idempotently seed a per-school default ``GradingScale`` (+ matching default
    ``AssessmentWeights``) from the school's country, unless a default scale already exists.

    Returns a summary dict; never raises (logs + returns {"ok": False, ...} on failure).
    """
    if school is None or getattr(school, "pk", None) is None:
        return {"ok": False, "error": "missing_school"}

    try:
        from apps.evals.models import AssessmentWeights, GradingScale

        # Respect an existing choice (wizard-default or any admin-set default scale).
        if GradingScale.objects.filter(school=school, is_default=True).exists():
            return {"ok": True, "skipped": "default_scale_exists"}

        scale_type = resolve_local_scale_type(school)
        config = _scale_config(scale_type)
        country_code = (getattr(school, "country_code", "") or "").strip().upper()
        name = f"{country_code or 'Local'} grading scale".strip()

        scale, created = GradingScale.objects.get_or_create(
            school=school,
            code=_LOCAL_DEFAULT_CODE,
            defaults={
                "name": name,
                "scale_type": scale_type,
                "config": config,
                "is_default": True,
                "is_active": True,
            },
        )
        if not created:
            # Backfill an existing local-default row that predates this seeder.
            scale.scale_type = scale_type
            scale.config = config
            scale.is_default = True
            scale.is_active = True
            scale.save(update_fields=["scale_type", "config", "is_default", "is_active"])
        # Single default per school.
        GradingScale.objects.filter(school=school, is_default=True).exclude(pk=scale.pk).update(
            is_default=False
        )

        # Seed a school-wide default AssessmentWeights so grade math uses this scale
        # (the Wave-4 pre_save aligns the letter thresholds to the scale on create).
        weights_created = False
        if academic_year is not None:
            _, weights_created = AssessmentWeights.objects.get_or_create(
                school=school,
                academic_year=academic_year,
                term=None,
                classroom=None,
                defaults={"grading_scale": scale_type},
            )

        # Converge the locale/display grading scale (the `grading_scale` settings key
        # get_tenant_locale reads) with the operational scale, so reports + grade
        # display match how grades are COMPUTED. Provisioning writes the resolved
        # profile's grading_scale into settings, but that profile is not always
        # country-accurate (only a few countries have a curated 0-20 profile; the
        # rest of the francophone world falls to a generic 0-100), leaving display
        # on /100 while computation is on /20. We only reach here when NO admin
        # default scale existed, so this corrects the provision default without
        # overriding a deliberate choice.
        locale_scale_aligned = False
        try:
            from apps.evals.grading import ASSESSMENT_WEIGHTS_SCALE_MAP

            locale_scale_id = ASSESSMENT_WEIGHTS_SCALE_MAP.get(scale_type)
            if locale_scale_id:
                school_settings = getattr(school, "settings", None)
                if not isinstance(school_settings, dict):
                    school_settings = {}
                if school_settings.get("grading_scale") != locale_scale_id:
                    school_settings["grading_scale"] = locale_scale_id
                    school.settings = school_settings
                    school.save(update_fields=["settings", "updated_at"])
                    locale_scale_aligned = True
        except Exception as exc:  # noqa: BLE001 — display alignment is best-effort
            logger.debug(
                "locale grading_scale align failed school_id=%s err=%s",
                getattr(school, "pk", None),
                exc,
            )
        return {
            "ok": True,
            "grading_scale_id": scale.pk,
            "scale_type": scale_type,
            "created": created,
            "assessment_weights_created": weights_created,
            "locale_scale_aligned": locale_scale_aligned,
        }
    except Exception as exc:  # noqa: BLE001 — provisioning step must never break the flow
        logger.warning(
            "ensure_local_grading_scale failed school_id=%s err=%s",
            getattr(school, "pk", None),
            exc,
        )
        return {"ok": False, "error": str(exc)}
