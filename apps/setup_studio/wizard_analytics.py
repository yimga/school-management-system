"""Wizard completion analytics + discovery surface (v4.00.8 #2–10).

Pure-Python helpers that read SetupProgress.step_state across tenants
and emit:

* Per-wizard completion rates (started / completed / completion_rate)
* Time-to-complete percentiles
* Step drop-off points (where users abandon)
* Wizard discovery / search index

Used by the operator wizard activation dashboard. Each helper takes
the queryset directly so callers can scope it to a tenant or to a
date range.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WizardActivationStat:
    wizard_key: str
    started: int = 0
    completed: int = 0
    abandoned: int = 0
    step_dropoff: dict[str, int] = field(default_factory=dict)
    median_completion_seconds: int | None = None
    p95_completion_seconds: int | None = None

    @property
    def completion_rate(self) -> float:
        if self.started == 0:
            return 0.0
        return round(self.completed / self.started, 3)

    @property
    def biggest_dropoff_step(self) -> str | None:
        if not self.step_dropoff:
            return None
        return max(self.step_dropoff.items(), key=lambda kv: kv[1])[0]


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def aggregate_wizard_stats(progress_rows: Iterable[Any]) -> dict[str, WizardActivationStat]:
    """Walk SetupProgress rows; build WizardActivationStat per wizard_key.

    Each progress row is expected to be a SetupProgress instance with a
    ``step_state`` JSONField containing the ``wizards.<key>`` namespace.

    Pure aggregation — no DB writes. Callers are responsible for scoping
    the queryset (e.g. only completed-or-touched-in-last-30-days).
    """
    accumulators: dict[str, dict[str, Any]] = {}

    def _acc(wizard_key: str) -> dict[str, Any]:
        if wizard_key not in accumulators:
            accumulators[wizard_key] = {
                "started": 0,
                "completed": 0,
                "abandoned": 0,
                "step_dropoff": {},
                "completion_durations": [],
            }
        return accumulators[wizard_key]

    for row in progress_rows:
        step_state = getattr(row, "step_state", None) or {}
        wizards = step_state.get("wizards") or {}
        if not isinstance(wizards, dict):
            continue
        for wizard_key, w_state in wizards.items():
            if not isinstance(w_state, dict):
                continue
            acc = _acc(wizard_key)
            acc["started"] += 1
            if w_state.get("completed_at"):
                acc["completed"] += 1
                started = _parse_iso(w_state.get("started_at"))
                completed = _parse_iso(w_state.get("completed_at"))
                if started and completed and completed > started:
                    acc["completion_durations"].append(int((completed - started).total_seconds()))
            else:
                acc["abandoned"] += 1
                current_step = w_state.get("current_step_key")
                if isinstance(current_step, str) and current_step:
                    acc["step_dropoff"][current_step] = acc["step_dropoff"].get(current_step, 0) + 1

    out: dict[str, WizardActivationStat] = {}
    for wizard_key, acc in accumulators.items():
        durations = sorted(acc["completion_durations"])
        median = _percentile(durations, 0.5)
        p95 = _percentile(durations, 0.95)
        out[wizard_key] = WizardActivationStat(
            wizard_key=wizard_key,
            started=acc["started"],
            completed=acc["completed"],
            abandoned=acc["abandoned"],
            step_dropoff=dict(acc["step_dropoff"]),
            median_completion_seconds=median,
            p95_completion_seconds=p95,
        )
    return out


def _percentile(sorted_values: list[int], q: float) -> int | None:
    if not sorted_values:
        return None
    idx = max(0, min(len(sorted_values) - 1, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[idx]


# ============================================================================
# Wizard discovery / search index
# ============================================================================


def build_wizard_search_index(wizards: Iterable[Any]) -> list[dict[str, Any]]:
    """Build a stable search index from the wizard registry.

    Each entry: ``{wizard_key, audience, icon_class, estimated_minutes,
    search_terms}``. ``search_terms`` is a lowercase string of joined
    tokens from wizard_key + label_token + description_token + step keys
    that the search endpoint can do substring matching against.
    """
    # Local import — avoids a hard dependency at module load and keeps the
    # humanizer (a thin pure function) close to its single use here.
    from apps.setup_studio.wizard_labels import humanize_wizard_token

    out = []
    for w in wizards:
        terms: list[str] = []
        terms.append(getattr(w, "wizard_key", "") or "")
        terms.append(getattr(w, "label_token", "") or "")
        terms.append(getattr(w, "description_token", "") or "")
        for s in getattr(w, "steps", ()) or ():
            terms.append(getattr(s, "key", "") or "")
            terms.append(getattr(s, "label_token", "") or "")
        label_token = getattr(w, "label_token", "") or ""
        out.append({
            "wizard_key": w.wizard_key,
            "audience": list(w.audience),
            "icon_class": w.icon_class,
            "estimated_minutes": w.estimated_minutes,
            "label_token": label_token,
            # Humanized, render-ready title so the client never paints a raw
            # `wizards.*` slug in the search dropdown (the mfa_setup-style leak).
            "label": humanize_wizard_token(label_token) or w.wizard_key,
            "description_token": getattr(w, "description_token", "") or "",
            "search_terms": " ".join(t.lower().replace("_", " ").replace(".", " ") for t in terms if t),
            "step_count": len(w.steps),
        })
    return sorted(out, key=lambda e: e["wizard_key"])


def search_wizards(index: list[dict[str, Any]], *, query: str, audience: str | None = None) -> list[dict[str, Any]]:
    """Substring search over the index. Lowercase. AND-tokens, OR not supported.

    Defensive caps: query trimmed to 100 chars, results to 50.
    """
    q = (query or "").strip().lower()[:100]
    if not q:
        return []
    tokens = [t for t in q.split() if t]
    results = []
    for entry in index:
        if audience is not None and audience not in entry["audience"]:
            continue
        haystack = entry["search_terms"]
        if all(tok in haystack for tok in tokens):
            results.append(entry)
        if len(results) >= 50:
            break
    return results


# ============================================================================
# Cockpit widget heatmap — derives "most used" from saved layouts
# ============================================================================


def aggregate_widget_heatmap(layout_rows: Iterable[Any]) -> dict[str, dict[str, int]]:
    """Build a heatmap of {widget_id: {placed_count, hidden_count, promoted_count}}.

    ``layout_rows`` is an iterable of DashboardLayout rows. Each row's
    ``layout`` JSONField is walked for items + __settings__.hidden_widget_ids
    + __settings__.promoted_cockpit_ids.
    """
    heatmap: dict[str, dict[str, int]] = {}

    def _bump(widget_id: str, key: str) -> None:
        if widget_id not in heatmap:
            heatmap[widget_id] = {"placed_count": 0, "hidden_count": 0, "promoted_count": 0}
        heatmap[widget_id][key] = heatmap[widget_id].get(key, 0) + 1

    for row in layout_rows:
        layout = getattr(row, "layout", None) or {}
        if not isinstance(layout, dict):
            continue
        for item in layout.get("items") or []:
            if isinstance(item, dict) and item.get("id"):
                _bump(str(item["id"]), "placed_count")
        settings = layout.get("__settings__") or {}
        if isinstance(settings, dict):
            for wid in settings.get("hidden_widget_ids") or []:
                if wid:
                    _bump(str(wid), "hidden_count")
            for wid in settings.get("promoted_cockpit_ids") or []:
                if wid:
                    _bump(str(wid), "promoted_count")
    return heatmap
