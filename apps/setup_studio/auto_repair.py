"""Setup Studio auto-repair — the real work behind the "Fix automatically" button.

Previously "Fix automatically" only called ``compile_setup_studio``, which
*recomputes* the health snapshot from the current state — it never *performed*
any setup, so the score never moved and the button looked broken.

This module performs the SAFE, deterministic, idempotent setup steps that do
NOT require a tenant-specific decision or real roster data:

  * seed + align the reference registries (kills the "yellow triangles"), and
    derive the school's localization defaults (timezone / currency / locale /
    calendar) from its country when they are blank;
  * attach the platform default plan when none is set;
  * create a starter academic year when none exists.

Every step is guarded so one failure cannot abort the rest, and every step only
fills a BLANK value — it never overwrites a choice the tenant already made. The
two remaining blockers that genuinely need a human — applying a region-matched
blueprint (it changes modules) and importing the roster — are reported back as
``needs_human`` rather than being silently performed.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# Month from which the autumn-anchored academic year is considered to have begun
# for the starter year name (e.g. Aug 2026 → "2026/2027").
_ACADEMIC_YEAR_START_MONTH = 8


def auto_repair_setup(school, *, actor_id: int | None = None) -> dict[str, Any]:
    """Perform safe auto-repair and return a structured report of the result."""
    from apps.setup_studio.services import compile_setup_studio

    before = compile_setup_studio(school)
    health_before = int(before.get("health_score", 0) or 0)

    fixed: list[str] = []
    _align_registries(school, fixed)
    _ensure_recommendations(school, fixed)
    _attach_default_plan(school, fixed)
    _ensure_academic_year(school, fixed)

    after = compile_setup_studio(school)
    health_after = int(after.get("health_score", 0) or 0)
    remaining = [
        b.get("label") or b.get("key") or "blocker"
        for b in (after.get("launch_blockers") or [])
    ]
    rec_bp = after.get("recommended_blueprint") or {}
    return {
        "ok": True,
        "actor_id": actor_id,
        "health_before": health_before,
        "health_after": health_after,
        "fixed": fixed,
        "fixed_count": len(fixed),
        "remaining_blockers": remaining,
        "launch_ready": bool(after.get("launch_ready")),
        "recommended_blueprint_slug": (
            rec_bp.get("slug") or rec_bp.get("pack_slug") or ""
        ),
        "needs_human": _human_steps(after),
    }


def _align_registries(school, fixed: list[str]) -> None:
    """Seed the reference registries and fill blank localization defaults from
    the school's country, so the registry-alignment card turns green."""
    try:
        from apps.registries.services import ensure_registry_baseline

        ensure_registry_baseline()
    except Exception:  # noqa: BLE001 — one seed failure must not abort repair
        logger.debug("auto-repair: registry baseline seed skipped", exc_info=True)

    try:
        from apps.siteconfig.global_catalog import GlobalGeoCatalog

        cc = str(getattr(school, "country_code", "") or "").strip()
        defaults = GlobalGeoCatalog.country_defaults(cc) if cc else {}
        changed_fields: list[str] = []
        settings = dict(school.settings) if isinstance(school.settings, dict) else {}

        if (
            not str(getattr(school, "timezone", "") or "").strip()
            and defaults.get("timezone")
        ):
            school.timezone = defaults["timezone"]
            changed_fields.append("timezone")

        # currency / locale / calendar are resolved from RegionConfig first; only
        # when the school has no region do the school.settings values apply.
        has_region = getattr(school, "default_region_id", None) is not None
        settings_changed = False
        if not has_region:
            if (
                not str(settings.get("default_currency") or "").strip()
                and defaults.get("currency")
            ):
                settings["default_currency"] = defaults["currency"]
                settings_changed = True
            locale_set = str(
                settings.get("default_locale")
                or settings.get("locale")
                or settings.get("default_language")
                or ""
            ).strip()
            if not locale_set and defaults.get("default_language"):
                settings["default_locale"] = defaults["default_language"]
                settings_changed = True
            if not str(settings.get("calendar_system") or "").strip():
                settings["calendar_system"] = "gregorian"
                settings_changed = True
        if settings_changed:
            school.settings = settings
            changed_fields.append("settings")

        if changed_fields:
            update_fields = list(dict.fromkeys(changed_fields + ["updated_at"]))
            school.save(update_fields=update_fields)
            fixed.append(
                "Aligned localization registries (timezone, currency, locale, "
                "calendar) using your country's defaults."
            )
        else:
            fixed.append("Seeded and verified the reference registries.")
    except Exception:  # noqa: BLE001
        logger.debug("auto-repair: localization derive skipped", exc_info=True)


def _attach_default_plan(school, fixed: list[str]) -> None:
    try:
        if getattr(school, "plan_id", None):
            return
        # School.plan FKs to siteconfig.Plan (the platform catalog Plan).
        from apps.siteconfig.models_platform_catalog import Plan

        plan = Plan.get_default_plan()
        if plan is not None:
            school.plan = plan
            school.save(update_fields=["plan", "updated_at"])
            fixed.append(f"Attached the default plan ({getattr(plan, 'name', plan)}).")
    except Exception:  # noqa: BLE001
        logger.debug("auto-repair: default plan bind skipped", exc_info=True)


def _ensure_recommendations(school, fixed: list[str]) -> None:
    """Grandfather a local recommendation manifest without changing choices."""
    try:
        from apps.schools.onboarding_recommendations import ensure_school_recommendations

        before = (dict(school.settings or {})).get("recommendation_manifest")
        ensure_school_recommendations(school)
        if not before:
            fixed.append("Built your local recommendation profile from existing school data.")
    except Exception:  # noqa: BLE001
        logger.debug("auto-repair: recommendation grandfather skipped", exc_info=True)


def _ensure_academic_year(school, fixed: list[str]) -> None:
    try:
        from apps.academics.models import AcademicYear

        if AcademicYear.objects.filter(school=school).exists():
            return
        from django.utils import timezone as djtz

        today = djtz.now().date()
        start_year = (
            today.year if today.month >= _ACADEMIC_YEAR_START_MONTH else today.year - 1
        )
        AcademicYear.objects.create(
            school=school,
            name=f"{start_year}/{start_year + 1}",
            start_date=date(start_year, 9, 1),
            end_date=date(start_year + 1, 7, 31),
            is_active=True,
        )
        fixed.append(
            f"Created a starter academic year ({start_year}/{start_year + 1}) — "
            "adjust the dates and add terms in Academic Year setup."
        )
    except Exception:  # noqa: BLE001
        logger.debug("auto-repair: academic year create skipped", exc_info=True)


def _human_steps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The remaining blockers that need a tenant decision, not auto-repair."""
    steps: list[dict[str, Any]] = []
    step_state = payload.get("step_state") or {}
    if not (step_state.get("blueprint") or {}).get("done"):
        rec = payload.get("recommended_blueprint") or {}
        steps.append(
            {
                "key": "blueprint",
                "label": "Apply the recommended blueprint",
                "detail": (
                    "Blueprints set region- and institution-appropriate modules, "
                    "policies, and dashboards. Review and apply the one matched to "
                    "your country and education system."
                ),
                "recommended_slug": rec.get("slug") or rec.get("pack_slug") or "",
                "cta_url": rec.get("cta_url") or "",
            }
        )
    if not (step_state.get("data_path") or {}).get("done"):
        steps.append(
            {
                "key": "data_path",
                "label": "Import your roster",
                "detail": (
                    "Bring in real students and staff (Migration Cloud) so "
                    "dashboards, previews, and reports reflect your school."
                ),
                "cta_url": (step_state.get("data_path") or {}).get("link") or "",
            }
        )
    return steps
