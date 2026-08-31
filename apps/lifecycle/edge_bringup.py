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
    staff_path: str = ""       # .rmcstaff -> import_tenant_staff (BEFORE identities)
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

    # BEFORE identities, and the order is load-bearing. import_tenant_identities
    # matches Users by username and otherwise takes a FRESH pk (its field list has no
    # `id`), so running it first lands the teacher logins at box-local pks: the staff
    # bundle then refuses rather than overwrite them, and import_tenant_bundle still
    # dies on the dangling FK because the user_id it carries is the cloud's -- rolling
    # the WHOLE operational seed back, not just the teachers.
    if inputs.staff_path:
        actions.append({
            "key": "migrate_staff", "cmd": "import_tenant_staff",
            "args": ["--in", inputs.staff_path],
        })

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
    do_go_dark: bool = True,
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
        # Steps 16-17. Separate from offline_ready on purpose -- see the tail of this
        # function for why the older word is left meaning exactly what it meant.
        "go_dark": None,
        "converged": False,
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
        # NOT guarded by running_on_edge_box(), deliberately. That helper reads
        # Django settings, which load once at process start -- and the step that
        # makes a box look like a box (enable_configure_sync) is a PREP step of this
        # same command. Guarding here would refuse the gate on a fresh box, before
        # the step that clears the guard has run.
        #
        # The refusal lives on the self-heals instead, which is where the risk is: a
        # console button somebody clicks. This command is typed by a person standing
        # at the box.
        gate = run_sync_gate(school)
        report["sync_gate"] = gate
        gate_cleared = bool(gate.get("cleared"))

    # 5) offline_ready: all prep ran, verification passes, gate cleared. A skipped
    #    gate can NEVER be certified offline-ready — it is held back until the gate runs.
    prep_ok = all(e["ok"] for e in report["prep"]) if report["prep"] else True
    report["offline_ready"] = bool(prep_ok and report["steps_ok"] and gate_cleared is True)

    # 6) Steps 16-17: prove one live round-trip, then the go-dark composite.
    #
    # These cannot come from the loop in (3). That loop walks
    # run_verification_suite(include_gate=False), which keeps only cloud_preview
    # steps -- and all three verification steps are cloud_preview=False precisely
    # because their evidence is a real sync. So they are healed explicitly, here,
    # after the gate has cleared.
    #
    # Ordering is not incidental: a live cycle attempted before the dry gate clears
    # fails for the same reason the gate would have, and writes a failed LIVE run
    # into the record an operator reads to decide whether this box converges at all.
    # The heals refuse on their own too, but a caller that invites the refusal is a
    # caller that will one day be read as permission.
    if do_go_dark and gate_cleared:
        from apps.lifecycle.edge_onboarding import heal_step

        go_dark: dict = {"attempted": True, "live": None, "checklist": None, "ok": False}
        live = heal_step(school, "live_sync_proof")
        go_dark["live"] = live
        if live.get("healed"):
            report["healed"].append("live_sync_proof")
        checklist = heal_step(school, "go_dark_checklist")
        go_dark["checklist"] = checklist
        if checklist.get("healed"):
            report["healed"].append("go_dark_checklist")
        go_dark["ok"] = bool(checklist.get("healed"))
        report["go_dark"] = go_dark
    elif do_go_dark:
        # Saying WHY it did not run matters: "not attempted" and "attempted and
        # failed" send somebody to different places.
        report["go_dark"] = {
            "attempted": False,
            "live": None,
            "checklist": None,
            "ok": False,
            "detail": (
                "not attempted -- the dry sync gate did not clear"
                if do_sync_gate
                else "not attempted -- the sync gate was skipped"
            ),
        }

    # `converged` is the strong claim: cleared to go offline AND proven to come back.
    # `offline_ready` deliberately keeps its original, weaker meaning, because it is
    # already pinned by tests and by an operator's expectations, and redefining a
    # word in place is how a report starts disagreeing with the people reading it.
    report["converged"] = bool(
        report["offline_ready"] and (report.get("go_dark") or {}).get("ok")
    )
    return report
