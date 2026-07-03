"""Owner Console — Context Profile wizard (Wave 7.2).

A short guided setup that captures a school's operating context — where it is
(region/currency) and how it grades — and writes each value into the config
cascade through the first-class resolver (``set_runtime_default`` →
``school.settings['runtime_defaults']``, read back by ``get_effective_config``).
No new model, no migration: it writes to keys the platform already owns.

Three steps on one URL (``?step=1..3``); each step persists immediately, so the
owner can leave and come back. It is owner-gated, tenant-skinned and fail-soft.
The calendar/terms piece lives in its own editor, so the review step deep-links
there rather than pretending to own it.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.accounts.views_owner_console import _owner_only, _safe
from apps.schools.mixins import require_school

logger = logging.getLogger(__name__)

_SOFT = Exception
_TOTAL_STEPS = 3
_MAX = 120  # magic-number-allow: context-profile-input-cap-chars


def _grade_scale_choices() -> list[dict]:
    """`[{code, name}]` from the seeded grade-scale registry (SOT), fail-soft."""
    try:
        from apps.registries.services import GRADE_SCALE_SEED_DEFAULTS

        return [
            {"code": row["code"], "name": row.get("name") or row["code"]}
            for row in GRADE_SCALE_SEED_DEFAULTS
        ]
    except _SOFT as exc:  # noqa: BLE001 — empty list simply hides the picker
        logger.debug("context profile grade-scale choices failed: %s", exc)
        return []


def _current(school, key: str, default: str = "") -> str:
    """The effective value of a config key for this school (fail-soft)."""
    try:
        from apps.platform_runtime.config_resolver import get_effective_config

        return str(get_effective_config(school, key, default=default) or default)
    except _SOFT as exc:  # noqa: BLE001
        logger.debug("context profile read %s failed: %s", key, exc)
        return default


def _write(school, key: str, value) -> None:
    """Persist a first-class config value through the sanctioned setter."""
    try:
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        set_runtime_default(school=school, field=key, value=value)
    except _SOFT as exc:  # noqa: BLE001 — never break the wizard on a write error
        logger.warning("context profile write %s failed: %s", key, exc)


def _profile_state(school) -> dict:
    return dict((getattr(school, "settings", None) or {}).get("context_profile", {}))


def _mark_profile(school, **updates) -> None:
    if not school:
        return
    blob = dict(getattr(school, "settings", None) or {})
    state = dict(blob.get("context_profile", {}))
    state.update(updates)
    blob["context_profile"] = state
    try:
        school.settings = blob
        school.save(update_fields=["settings"])
    except _SOFT as exc:  # noqa: BLE001 — completion flag is best-effort
        logger.warning("context profile state save failed: %s", exc)


def _resolved_currency(school) -> str:
    try:
        return str(school.resolve_currency() or "")
    except _SOFT:  # noqa: BLE001
        return ""


def _clamp_step(raw) -> int:
    try:
        step = int(raw)
    except (TypeError, ValueError):
        return 1
    return min(max(step, 1), _TOTAL_STEPS)


@login_required
@require_school
def owner_console_context_profile(request):
    """Context Profile — a guided capture of the school's operating context."""
    ctx, denied = _owner_only(request, "setup")
    if denied:
        return denied
    school = request.school

    if request.method == "POST":
        step = _clamp_step(request.POST.get("step"))
        if step == 1:
            country = (request.POST.get("country") or "").strip().upper()[:_MAX]
            region = (request.POST.get("region") or "").strip()[:_MAX]
            if country:
                _write(school, "country", country)
            if region:
                _write(school, "region", region)
            _mark_profile(school, region_done=True)
            return redirect(f"{request.path}?step=2")
        if step == 2:
            scale = (request.POST.get("grading_scale") or "").strip()[:_MAX]
            valid = {c["code"] for c in _grade_scale_choices()}
            if scale and scale in valid:
                _write(school, "default_grading_scale", scale)
                _mark_profile(school, grading_done=True)
            return redirect(f"{request.path}?step=3")
        # step 3 — finish
        _mark_profile(school, completed=True)
        messages.success(request, _("Your school's context profile is saved."))
        try:
            return redirect("accounts:owner_console")
        except _SOFT:  # noqa: BLE001
            return redirect(request.path)

    step = _clamp_step(request.GET.get("step"))
    state = _profile_state(school)
    ctx.update(
        {
            "step": step,
            "total_steps": _TOTAL_STEPS,
            "profile_state": state,
            "profile_complete": bool(state.get("completed")),
            # current effective values, so the owner edits rather than re-enters
            "current_country": _current(school, "country"),
            "current_region": _current(school, "region"),
            "current_grading_scale": _current(school, "default_grading_scale"),
            "resolved_currency": _resolved_currency(school),
            "grade_scale_choices": _grade_scale_choices(),
            # calendar/terms lives in its own editor — deep-link, don't fake it
            "calendar_url": _safe("siteconfig:academic_calendar")
            or _safe("academics:academic_years")
            or _safe("siteconfig:grading_settings"),
            "grading_settings_url": _safe("siteconfig:grading_settings"),
        }
    )
    return render(request, "accounts/owner_console/context_profile.html", ctx)
