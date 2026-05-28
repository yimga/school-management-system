"""Quick-resume + per-tenant override helpers (v4.00.8 #5 + #6).

Pure-Python — no Django queryset operations; callers supply already-fetched data.

* ``list_resumable_wizards`` — given a SetupProgress row's wizards namespace,
  return wizards that were started but not completed in the last N days.
* ``filter_disabled_for_tenant`` — given a list of WizardDefinitions and the
  tenant's School.settings, drop any wizard whose key appears in
  ``setup_studio.disabled_wizard_keys``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class ResumableWizard:
    wizard_key: str
    current_step_key: str | None
    last_modified_iso: str | None
    completed_step_count: int
    # v4.00.13: friendly label resolved from the wizard registry; falls back
    # to title-cased wizard_key when the registry is unreachable.
    resolved_label: str = ""


def list_resumable_wizards(
    *,
    wizards_namespace: dict[str, Any] | None,
    within_days: int = 7,
) -> list[ResumableWizard]:
    """Return wizards started but not completed within the last N days.

    ``wizards_namespace`` is the ``step_state["wizards"]`` dict from a
    SetupProgress row. Returns a stable list ordered by last_modified DESC.
    """
    if not isinstance(wizards_namespace, dict) or not wizards_namespace:
        return []
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=int(within_days))
    out: list[tuple[datetime, ResumableWizard]] = []
    for wizard_key, w_state in wizards_namespace.items():
        if not isinstance(w_state, dict):
            continue
        if w_state.get("completed_at"):
            continue  # already done
        last_iso = w_state.get("last_modified") or w_state.get("started_at")
        if not isinstance(last_iso, str):
            continue
        try:
            last_dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if last_dt < cutoff:
            continue
        completed = w_state.get("completed") or []
        out.append((last_dt, ResumableWizard(
            wizard_key=str(wizard_key),
            current_step_key=w_state.get("current_step_key"),
            last_modified_iso=last_iso,
            completed_step_count=len(completed) if isinstance(completed, list) else 0,
            resolved_label=resolve_wizard_label(str(wizard_key)),
        )))
    out.sort(key=lambda pair: pair[0], reverse=True)
    return [item[1] for item in out]


def filter_disabled_for_tenant(
    wizards: list[Any],
    *,
    school_settings: dict[str, Any] | None,
) -> list[Any]:
    """Drop wizards whose key is in ``school.settings.setup_studio.disabled_wizard_keys``.

    ``wizards`` is a list of WizardDefinition objects. Returns a filtered list
    preserving original order. When the override dict is missing or malformed,
    returns the input unchanged.
    """
    if not isinstance(school_settings, dict):
        return list(wizards)
    studio = school_settings.get("setup_studio") or {}
    if not isinstance(studio, dict):
        return list(wizards)
    disabled = studio.get("disabled_wizard_keys") or []
    if not isinstance(disabled, list) or not disabled:
        return list(wizards)
    disabled_set = {str(k) for k in disabled if k}
    return [w for w in wizards if getattr(w, "wizard_key", None) not in disabled_set]


def resolve_wizard_label(wizard_key: str) -> str:
    """v4.00.13 — return the friendly label for a wizard key, with safe fallback.

    Best-effort lookup via wizard_engine. Falls back to a title-cased version
    of the key (``parent_link_child`` -> ``"Parent Link Child"``) when the
    registry is unavailable or the key is unknown.
    """
    if not wizard_key:
        return ""
    try:
        from apps.setup_studio import wizard_engine

        wizard = wizard_engine.get_wizard(wizard_key)
        label = getattr(wizard, "label_token", "") or ""
        if label:
            return label
    except Exception:  # noqa: BLE001
        pass
    return wizard_key.replace("_", " ").title()


def prune_stale_resumable_entries(
    *,
    wizards_namespace: dict[str, Any] | None,
    older_than_days: int = 30,
    now_iso: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """v4.00.13 — drop wizard entries with last_modified older than ``older_than_days``.

    Returns ``(pruned_namespace, removed_keys)``. Idempotent. Defensive: does
    nothing when input shape is wrong or no entries match.
    """
    if not isinstance(wizards_namespace, dict):
        return ({}, [])
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max(1, int(older_than_days)))
    if now_iso:
        try:
            cutoff = datetime.fromisoformat(now_iso.replace("Z", "+00:00")) - timedelta(days=max(1, int(older_than_days)))
        except (ValueError, TypeError):
            pass
    pruned: dict[str, Any] = {}
    removed: list[str] = []
    for wizard_key, w_state in wizards_namespace.items():
        if not isinstance(w_state, dict):
            pruned[wizard_key] = w_state
            continue
        if w_state.get("completed_at"):
            pruned[wizard_key] = w_state
            continue
        last_iso = w_state.get("last_modified") or w_state.get("started_at")
        if not isinstance(last_iso, str) or not last_iso:
            pruned[wizard_key] = w_state
            continue
        try:
            last_dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pruned[wizard_key] = w_state
            continue
        if last_dt < cutoff:
            removed.append(str(wizard_key))
            continue
        pruned[wizard_key] = w_state
    return (pruned, removed)


def set_disabled_wizard_keys(school: Any, keys: list[str]) -> None:
    """Persist the disabled list into ``school.settings.setup_studio.disabled_wizard_keys``.

    Safe to call with school=None (no-op). Keys are de-duplicated + sorted.
    """
    if school is None or getattr(school, "pk", None) is None:
        return
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        settings = {}
    studio = settings.get("setup_studio") or {}
    if not isinstance(studio, dict):
        studio = {}
    studio["disabled_wizard_keys"] = sorted({str(k) for k in keys if k})
    settings["setup_studio"] = studio
    school.settings = settings
    school.save(update_fields=["settings"])
