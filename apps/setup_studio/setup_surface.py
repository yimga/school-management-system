"""Wizard lifecycle stages for the tenant onboarding "command surface".

``templates/partials/tenant/setup_command_surface.html`` (the v3-canvas landing
shown while a school is still onboarding) renders these as the same numbered
"stage -> wizard cards" journey the bespoke ``/school/studio/wizards/`` index
uses, so the landing and the full index stay in lockstep.

Single read; fully failure-isolated — any error returns empty stages so the
surface silently falls back to its onboarding-milestone cards. All content is
real registry data (label / estimated_minutes / step count) + the tenant's own
SetupProgress status; nothing is fabricated.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# The audience the tenant admin's Setup-Studio index is built from (SOT for which
# wizards a school admin may run — mirrors list_wizards_for_audience usage).
TENANT_AUDIENCE = "tenant_admin"

_EMPTY = {"stages": [], "overall": {"done": 0, "total": 0, "pct": 0}}


def build_setup_wizard_stages(school: Any) -> dict[str, Any]:
    """Return ``{"stages": [...], "overall": {...}}`` for the setup surface.

    Each stage: ``{key, label, description, step, done, total, cards}`` where a
    card is ``{key, title, status, minutes, steps}``. ``status`` is one of
    ``done`` / ``in_progress`` / ``not_started``. Returns empty stages on any
    failure (never raises into the dashboard render).
    """
    try:
        from apps.setup_studio import wizard_engine
        from apps.setup_studio.wizard_categories import group_wizards_by_category
        from apps.setup_studio.wizard_labels import humanize_wizard_token

        wizards = wizard_engine.list_wizards_for_audience(TENANT_AUDIENCE)
        if not wizards:
            return dict(_EMPTY)

        status_map = _status_map_for(school)
        groups = group_wizards_by_category(wizards)

        stages: list[dict[str, Any]] = []
        done_all = 0
        total_all = 0
        for group in groups:
            cards: list[dict[str, Any]] = []
            done = 0
            for wiz in group.get("wizards") or []:
                key = getattr(wiz, "wizard_key", "")
                if not key:
                    continue
                status = status_map.get(key, "not_started")
                if status == "done":
                    done += 1
                title = humanize_wizard_token(getattr(wiz, "label_token", "")) or key
                cards.append({
                    "key": key,
                    "title": title,
                    "status": status,
                    "minutes": int(getattr(wiz, "estimated_minutes", 0) or 0),
                    "steps": len(getattr(wiz, "steps", ()) or ()),
                })
            total = len(cards)
            if not total:
                continue
            done_all += done
            total_all += total
            stages.append({
                "key": group.get("key"),
                "label": group.get("label"),
                "description": group.get("description"),
                "step": group.get("step"),
                "done": done,
                "total": total,
                "cards": cards,
            })

        overall = {
            "done": done_all,
            "total": total_all,
            "pct": int(round(done_all * 100 / total_all)) if total_all else 0,
        }
        return {"stages": stages, "overall": overall}
    except Exception as exc:  # noqa: BLE001 — decorative; never break the dashboard
        logger.debug("build_setup_wizard_stages failed: %s", exc)
        return dict(_EMPTY)


def _status_map_for(school: Any) -> dict[str, str]:
    """``{wizard_key: "done"|"in_progress"}`` from the school's SetupProgress."""
    if school is None or getattr(school, "pk", None) is None:
        return {}
    try:
        from apps.setup_studio.models import SetupProgress
        from apps.setup_studio.wizard_extras import wizard_status_map

        progress = SetupProgress.objects.filter(school=school).first()
        if progress is None:
            return {}
        step_state = progress.step_state or {}
        namespace = step_state.get("wizards") if isinstance(step_state, dict) else None
        return wizard_status_map(namespace) or {}
    except Exception as exc:  # noqa: BLE001 — status is decorative
        logger.debug("setup surface status map failed: %s", exc)
        return {}
