"""One-shot edge bring-up — turn the 7-step Edge Onboarding runbook into a single
orchestrated command so an operator/engineer runs ONE thing instead of hand-copying
seven, cutting a box bring-up from ~24h to ~1h.

It composes the pieces already shipped:
  * the input-driven PREP commands (import_sovereign_tenant / import_tenant_identities
    / backfill_country_baseline / import_school_branding / mint_edge_credential);
  * :func:`edge_onboarding.run_verification_suite` — a REAL validate() per step;
  * :func:`edge_onboarding.heal_step` — self-healing for steps that support it;
  * :func:`edge_onboarding.run_sync_gate` — the MANDATORY no-write dry sync probe
    (connectivity + credential) that MUST clear before a box may go offline.

``offline_ready`` is True only when every executed prep step ran, every verification
step passes, AND the sync gate cleared. Skipping the gate (a box with no connectivity
yet) can never be "offline ready" — it is explicitly held back until the gate runs.

Nothing here raises for an expected failure: each step's outcome is captured in the
returned report so the caller can print an honest GO / NO-GO. The prep commands run
through an injectable ``runner`` (default ``call_command``) so the orchestration is
testable without a real box.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BringupInputs:
    """Everything a box bring-up might be handed. Absent file inputs skip their step."""

    slug: str
    country: str = ""
    owner_email: str = ""
    bundle_path: str = ""      # .rmcbundle -> import_sovereign_tenant --fresh
    data_bundle_path: str = ""  # .rmcbundle -> import_tenant_bundle (NOT --fresh)
    identity_path: str = ""    # .rmcidentity -> import_tenant_identities
    brand_path: str = ""       # .rmcbrand -> import_school_branding
    mint_credential: bool = False
    credential_user: str = ""
    credential_days: int = 365


def plan_prep_actions(inputs: BringupInputs) -> list[dict]:
    """The ordered, input-driven prep commands a bring-up will run (no side effects).

    Each action is ``{"key", "cmd", "args"}`` where args are CLI-style tokens passed
    verbatim to ``call_command`` (so argparse dest names never matter). A file input
    that is absent simply omits its step — the baseline seed always runs.
    """
    slug = inputs.slug
    actions: list[dict] = []

    if inputs.bundle_path:
        args = ["--in", inputs.bundle_path, "--slug", slug, "--fresh"]
        if inputs.owner_email:
            args += ["--owner-email", inputs.owner_email]
        if inputs.country:
            args += ["--country", inputs.country]
        actions.append({"key": "provision_shell", "cmd": "import_sovereign_tenant", "args": args})

    if inputs.identity_path:
        actions.append({
            "key": "migrate_identities", "cmd": "import_tenant_identities",
            "args": ["--in", inputs.identity_path, "--slug", slug],
        })

    actions.append({
        "key": "seed_baseline", "cmd": "backfill_country_baseline",
        "args": ["--school", slug],
    })

    if inputs.brand_path:
        actions.append({
            "key": "media_branding", "cmd": "import_school_branding",
            "args": ["--in", inputs.brand_path, "--slug", slug],
        })

    if inputs.data_bundle_path:
        actions.append({
            "key": "seed_operational_data", "cmd": "import_tenant_bundle",
            "args": ["--in", inputs.data_bundle_path],
        })

    if inputs.mint_credential and inputs.credential_user:
        actions.append({
            "key": "enable_configure_sync", "cmd": "mint_edge_credential",
            "args": ["--slug", slug, "--user", inputs.credential_user,
                     "--days", str(inputs.credential_days)],
        })

    return actions


def _resolve_school(slug: str):
    from apps.schools.models import School

    try:
        return School.objects.filter(slug=slug).first()
    except Exception:  # noqa: BLE001 — resolution failure is reported, never crashes
        logger.warning("edge_bringup: could not resolve school %s", slug, exc_info=True)
        return None


def run_edge_bringup(
    *,
    inputs: BringupInputs,
    do_prep: bool = True,
    do_sync_gate: bool = True,
    self_heal: bool = True,
    runner=None,
) -> dict:
    """Execute a bring-up and return a structured GO/NO-GO report. Never raises for an
    expected step failure — everything lands in the report."""
    from django.core.management import call_command

    runner = runner or call_command
    report: dict = {
        "slug": inputs.slug,
        "prep": [],
        "verification": None,
        "sync_gate": None,
        "gate_skipped": not do_sync_gate,
        "steps_ok": False,
        "healed": [],
        "offline_ready": False,
        "error": "",
    }

    # 1) Input-driven prep commands.
    if do_prep:
        for action in plan_prep_actions(inputs):
            entry = {"key": action["key"], "cmd": action["cmd"], "ok": False, "detail": ""}
            try:
                runner(action["cmd"], *action["args"])
                entry["ok"] = True
                entry["detail"] = "ran"
            except Exception as exc:  # noqa: BLE001 — a prep failure is a NO-GO, not a crash
                entry["detail"] = f"{type(exc).__name__}: {exc}"
                logger.warning("edge_bringup: prep %s failed: %s", action["cmd"], exc)
            report["prep"].append(entry)

    # 2) Resolve the (now provisioned) school.
    school = _resolve_school(inputs.slug)
    if school is None:
        report["error"] = f"school '{inputs.slug}' not found after prep — cannot verify."
        return report

    from apps.lifecycle.edge_onboarding import (
        heal_step,
        run_sync_gate,
        run_verification_suite,
    )

    # 3) Verification suite (steps 1-6), with a self-heal pass for failing steps.
    verification = run_verification_suite(school, include_gate=False)
    if self_heal and not verification.get("ok"):
        for step in verification.get("steps", []):
            if step.get("ok"):
                continue
            healed = heal_step(school, step["key"])
            if healed.get("healed"):
                report["healed"].append(step["key"])
        if report["healed"]:
            verification = run_verification_suite(school, include_gate=False)  # re-check
    report["verification"] = verification
    report["steps_ok"] = bool(verification.get("ok"))

    # 4) MANDATORY pre-offline sync gate (unless explicitly skipped).
    gate_cleared = None
    if do_sync_gate:
        gate = run_sync_gate(school)
        report["sync_gate"] = gate
        gate_cleared = bool(gate.get("cleared"))

    # 5) offline_ready: all prep ran, verification passes, gate cleared. A skipped
    #    gate can NEVER be certified offline-ready — it is held back until the gate runs.
    prep_ok = all(e["ok"] for e in report["prep"]) if report["prep"] else True
    report["offline_ready"] = bool(prep_ok and report["steps_ok"] and gate_cleared is True)
    return report
