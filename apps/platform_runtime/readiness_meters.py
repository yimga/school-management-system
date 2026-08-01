"""Honest readiness scoring for the tenant/operator setup meters.

Background
----------
The ``world_class_readiness_meter`` / ``apple_class_data_quality_meter``
components were dropped onto several setup surfaces with hardcoded integer
values (72, 70, 74, 64, 68 …). A hardcoded number on a bar labelled
"readiness" can never move and can never legitimately reach 100 — it measures
nothing. This module replaces those placeholders with a real computation: a
weighted set of *concrete, checkable facts* about the tenant/preview, so the
bar reaches 100 exactly when every fact is satisfied, and its shortfall is
explainable ("what is not done yet").

Design
------
``readiness_from_checks`` is the generic core: a list of ``ReadinessCheck``
rows, each a (weight, satisfied, label) triple. ``satisfied`` may be a bool or
a 0..1 fraction (for partial credit). The score is the weighted fraction
satisfied, clamped to 0..100. ``readiness_detail`` additionally returns the
list of unmet check labels so a caller can say *why* it is below 100.

Every surface builds its own checks from real signals it already has in hand
(a blueprint/pack preview, a configuration summary, a usage snapshot); nothing
here invents data. A go-live payment/settlement requirement is intentionally a
*check that is unmet until PSP onboarding completes* — so a payment-capable
blueprint honestly reads e.g. 85% ("live collection pending") rather than a
fake 72%, and a fully-provisioned non-payment surface can honestly reach 100%.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


# Offline proof is scored on offline evidence alone. The historical composite
# "READY_WITH_EXTERNAL_BLOCKERS" is deliberately absent: it was produced whenever
# a blueprint carried a *payment* blocker, and counting it as ready meant a
# payment-gated blueprint out-scored a clean one. blueprint_preview no longer
# emits it, and it must never be re-admitted here.
_OFFLINE_READY_STATUSES = {"READY"}


@dataclass(frozen=True)
class ReadinessCheck:
    weight: float
    satisfied: bool | float
    label: str


def _fraction(satisfied: bool | float) -> float:
    if satisfied is True:
        return 1.0
    if satisfied is False:
        return 0.0
    try:
        return max(0.0, min(1.0, float(satisfied)))
    except (TypeError, ValueError):
        return 0.0


def readiness_from_checks(checks: Iterable[ReadinessCheck]) -> int:
    checks = list(checks)
    total = sum(c.weight for c in checks)
    if total <= 0:
        return 0
    got = sum(c.weight * _fraction(c.satisfied) for c in checks)
    return max(0, min(100, round(100 * got / total)))


def readiness_detail(checks: Iterable[ReadinessCheck]) -> dict[str, Any]:
    """Score plus the labels of checks that are not fully satisfied.

    The unmet labels are what a caption/tooltip shows so the tenant sees the
    concrete remaining work instead of an unexplained sub-100 number.
    """
    checks = list(checks)
    value = readiness_from_checks(checks)
    unmet = [c.label for c in checks if _fraction(c.satisfied) < 1.0]
    return {"value": value, "unmet": unmet, "complete": value >= 100}


def _offline_ready(preview: dict[str, Any]) -> bool:
    status = (preview.get("offline_readiness") or {}).get("status")
    return status in _OFFLINE_READY_STATUSES


def blueprint_readiness_checks(
    preview: dict[str, Any], *, school=None
) -> list[ReadinessCheck]:
    """Real readiness facts for a blueprint preview, evaluated for one tenant.

    A blueprint that applies cleanly with no conflicts and a proven offline
    posture reaches 100 — unless it carries a go-live payment requirement this
    tenant has neither met nor ruled out.

    The live-payment check is resolved against real per-tenant state
    (``finance.fee_collection_posture``), not against the static contract tuple:

    * a tenant with a live rail SATISFIES it;
    * a tenant that has explicitly recorded a manual-reconciliation posture is
      NOT APPLICABLE — the check is dropped from the weighting entirely rather
      than credited, so the score is taken over the checks that apply to it;
    * anything else leaves it unmet and named in the caption.

    Passing no ``school`` (or resolving one is impossible) falls back to the
    static contract reading, which is the conservative direction: the check
    stays unmet rather than being handed a pass.
    """
    checks = [
        ReadinessCheck(40, bool(preview.get("can_apply")), "Applyable preview"),
        ReadinessCheck(25, not preview.get("conflicts"), "Conflict-free"),
        ReadinessCheck(20, _offline_ready(preview), "Offline proof"),
    ]
    if not preview.get("external_required"):
        # Blueprint declares no go-live payment gate: nothing to weigh.
        return checks

    collection = _live_collection_state(school)
    if collection.get("not_applicable"):
        return checks
    checks.append(
        ReadinessCheck(
            15,
            bool(collection.get("live")),
            str(collection.get("label") or "Live payment onboarding"),
        )
    )
    return checks


def _live_collection_state(school) -> dict[str, Any]:
    if school is None:
        return {"live": False, "not_applicable": False, "label": "Live payment onboarding"}
    try:
        from apps.finance.fee_collection_posture import resolve_live_collection_state

        return resolve_live_collection_state(school)
    except Exception:  # noqa: BLE001 — a resolver failure must not fake a pass
        return {"live": False, "not_applicable": False, "label": "Live payment onboarding"}


def blueprint_readiness(preview: dict[str, Any], *, school=None) -> dict[str, Any]:
    return readiness_detail(blueprint_readiness_checks(preview, school=school))


def pack_readiness_checks(preview: dict[str, Any]) -> list[ReadinessCheck]:
    """Real readiness facts for a pack preview (same contract shape)."""
    has_external = bool(preview.get("external_required"))
    return [
        ReadinessCheck(50, bool(preview.get("can_apply")), "Applyable preview"),
        ReadinessCheck(30, not preview.get("conflicts"), "Conflict-free"),
        ReadinessCheck(20, not has_external, "Dependencies resolved"),
    ]


def pack_readiness(preview: dict[str, Any]) -> dict[str, Any]:
    return readiness_detail(pack_readiness_checks(preview))
