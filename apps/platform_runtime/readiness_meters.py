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
    checks.extend(_external_checks(preview, school, weight=15))
    return checks


def _external_checks(
    preview: dict[str, Any], school, *, weight: float
) -> list[ReadinessCheck]:
    """Weigh outstanding external requirements, by kind.

    A HARD blocker (``external_dependencies`` — only the platform can clear it)
    is always weighed and always unmet while present. A GO-LIVE gate
    (``external_required_items``) is resolved against the tenant's real
    fee-collection posture. Previews written before the split expose only
    ``external_required``; those are treated as go-live gates, which is what
    every one of them is today.
    """
    hard = list(preview.get("external_hard_blockers") or [])
    if "external_go_live" in preview:
        go_live = list(preview.get("external_go_live") or [])
    else:
        go_live = [item for item in (preview.get("external_required") or []) if item not in hard]

    checks: list[ReadinessCheck] = []
    if hard:
        checks.append(ReadinessCheck(weight, False, "External dependencies"))
        return checks
    if not go_live:
        return checks
    if _declares_manual_payment_model(preview):
        # Out of scope for this BLUEPRINT: dropped from the weighting, not
        # credited — same treatment as a tenant-recorded manual posture.
        return checks

    collection = _live_collection_state(school)
    if collection.get("not_applicable"):
        # Out of scope for this tenant: dropped from the weighting, not credited.
        return checks
    # NOTE: a conditional gate ("PSP proof IF live payment collection is
    # enabled", on the two policy bundles) is deliberately NOT dropped here.
    # ``pending`` means the tenant has not DECIDED, not that it will never
    # collect online, so treating the condition as false would infer a decision
    # from silence — the same "never set up payments" -> "done" false credit
    # apps.finance.fee_collection_posture exists to forbid. Those packs read 80
    # until the tenant records a posture, which is one click on the pack setup
    # page. Sealed by test_the_ceiling_is_not_reachable_by_doing_nothing.
    checks.append(
        ReadinessCheck(
            weight,
            bool(collection.get("live")),
            str(collection.get("label") or "Live payment onboarding"),
        )
    )
    return checks


#: Constraint tokens by which a contract declares "we reconcile fees by hand".
_MANUAL_PAYMENT_CONSTRAINTS = frozenset(
    {"manual_payment_fallback", "manual_receipt_reconciliation"}
)


def _declares_manual_payment_model(preview: dict[str, Any]) -> bool:
    """True when the BLUEPRINT's own contract prescribes manual reconciliation.

    Two blueprints declare a live-collection go-live gate while their own
    contracts declare the opposite operating model:

    * ``low-connectivity-school`` — ``manual_receipt_reconciliation``, plus a
      "Manual payment reconciliation" workflow pack, a "Payments fallback"
      module and the ``payments.reconcile`` permission;
    * ``cameroon-gce-school`` — ``manual_payment_fallback``, and "Set manual
      payment fallback" as an implementation step.

    The gate is weighed at 15, so both read 85 for every tenant — the
    offline-first archetype being told it could not finish until it onboarded an
    online PSP, the very thing a low-connectivity school exists to operate
    without. A school running exactly the model its blueprint prescribes has no
    remaining work, so the check does not apply and leaves the denominator.

    This reads a BLUEPRINT CONTRACT fact, never tenant state.
    ``apps.finance.fee_collection_posture`` documents that a manual posture is
    never inferred from the absence of a rail, because that would turn "this
    school never set up payments" into "this school is done". Nothing here
    infers anything about a tenant: a blueprint that stays silent on its payment
    model is unaffected and still resolves against the tenant's real posture.

    The gate itself remains DECLARED on the contract and keeps being surfaced by
    the preview as a capability requirement (never an apply blocker), so a
    school that does want a live rail is still guided to one.
    """
    key = preview.get("blueprint_key")
    if not key:
        # Packs share this helper and carry no blueprint key — unaffected.
        return False
    try:
        from apps.platform_runtime.blueprint_contract import get_blueprint

        blueprint = get_blueprint(str(key))
    except (ImportError, AttributeError, TypeError, ValueError):
        return False
    if blueprint is None:
        return False
    constraints = {
        str(c).strip().lower()
        for c in (getattr(blueprint, "local_constraints", None) or ())
    }
    return bool(constraints & _MANUAL_PAYMENT_CONSTRAINTS)


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


def pack_readiness_checks(
    preview: dict[str, Any], *, school=None
) -> list[ReadinessCheck]:
    """Real readiness facts for a pack preview (same contract shape).

    Packs carry the same two kinds of external requirement as blueprints and are
    resolved the same way — two policy bundles declared a *conditional* go-live
    PSP proof as an apply-time dependency, which pinned them at 80 for every
    tenant including ones that never collect online.
    """
    checks = [
        ReadinessCheck(50, bool(preview.get("can_apply")), "Applyable preview"),
        ReadinessCheck(30, not preview.get("conflicts"), "Conflict-free"),
    ]
    checks.extend(_external_checks(preview, school, weight=20))
    return checks


def pack_readiness(preview: dict[str, Any], *, school=None) -> dict[str, Any]:
    return readiness_detail(pack_readiness_checks(preview, school=school))


def platform_billing_readiness() -> dict[str, Any]:
    """Operator-facing billing-rail readiness, from the corridor register.

    Replaces a hardcoded ``value="64"`` on the billing configuration module — a
    number that measured nothing and could never move. The facts here are the
    platform's own rails: how many pilot corridors have an adapter wired, and
    how many have live settlement evidence filed. A platform that has filed no
    live evidence honestly reads low; it reaches 100 when every corridor is
    adapter-wired AND verified live.
    """
    try:
        from apps.finance.payment_lane2_status import build_lane2_corridor_rows

        rows = build_lane2_corridor_rows(school=None)
    except Exception:  # noqa: BLE001 — an operator meter must never 500 the page
        rows = []

    if not rows:
        return {
            "value": 0,
            "status": "external-blocked",
            "status_label": "No corridors registered",
            "body": "No payment corridor is registered yet, so no billing rail can be claimed.",
            "unmet": ["Corridor registry"],
        }

    adapter_ready = sum(1 for row in rows if row.get("adapter_status") == "ready")
    live_proof = sum(1 for row in rows if row.get("live_proof"))
    checks = [
        ReadinessCheck(40, adapter_ready / len(rows), "Corridor adapters wired"),
        ReadinessCheck(60, live_proof / len(rows), "Live settlement evidence filed"),
    ]
    detail = readiness_detail(checks)
    detail["status"] = "ready" if live_proof == len(rows) else "external-blocked"
    detail["status_label"] = (
        "Live settlement verified" if live_proof else "Manual fallback"
    )
    detail["body"] = (
        f"{adapter_ready}/{len(rows)} corridors adapter-wired, "
        f"{live_proof}/{len(rows)} with live settlement evidence filed. "
        "Package changes show entitlement and billing impact without claiming "
        "live payment readiness."
    )
    return detail
