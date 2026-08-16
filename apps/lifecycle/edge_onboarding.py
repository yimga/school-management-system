"""Edge Onboarding Runbook — the backend engine (feature ③ of the RMC Edge initiative).

We stand up an offline / sovereign edge box via a standardized, proven sequence
(validated end-to-end on the Gilead tenant): pin the School parent at the bundle's
UUID and provision a clean, entitled, loginable shell; recreate the user identities;
seed the country academic baseline; set branding; sanity-check the box environment;
enable + configure edge<->cloud sync; and — the MANDATORY final gate — prove the box
is done with a verification suite AND a no-write pre-offline sync probe before the box
may go dark.

This module is ONLY the engine: an ordered, frozen model of the seven steps plus the
functions an operator wizard (built later) will drive. There is no UI, no view, no URL
here. Nothing changes the sync protocol or money policy — the sync gate merely calls
the existing :func:`apps.sync_engine.sync_runner.run_sync_cycle` in ``dry`` mode.

Everything is self-healing: NO function here raises to its caller. A per-school runbook
generates deterministically, a validate() that blows up is recorded as a failure (never
aborting the suite), and the sync gate returns a result dict whatever the network does.

Any validation that reads TENANT-SCOPED tables (academics / people / billing) wraps the
read in :func:`apps.schools.rls_context.rls_bypass` so it works on a PostgreSQL edge box
where those tables are FORCE RLS + default-deny (the ``School`` parent itself is a public
/ shared row and needs no bypass).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from django.conf import settings

from apps.schools.rls_context import rls_bypass

# A validate()/self_heal() callable takes the school and returns (ok/healed, detail).
StepCheck = Callable[[Any], "tuple[bool, str]"]


@dataclass(frozen=True)
class EdgeOnboardingStep:
    """One immutable, ordered step of the edge bring-up runbook.

    ``command_template`` is a copy-pasteable shell / ``manage.py`` string with
    ``{slug}`` / ``{school_id}`` / ``{country}`` placeholders that
    :func:`generate_runbook` fills for a specific school. ``validate`` does a REAL
    check (returns ``(ok, detail)``, never raises past its own guard); ``workaround``
    is the human fallback when a step can't complete; ``self_heal`` (optional) is an
    automated remediation the engine can attempt.
    """

    key: str
    title: str
    purpose: str
    category: str
    command_template: str
    validate: StepCheck
    workaround: str
    self_heal: Optional[StepCheck] = field(default=None)


# --------------------------------------------------------------------------- #
# Small helpers (all defensive)
# --------------------------------------------------------------------------- #
def _school_id(school) -> str:
    return str(getattr(school, "id", None) or getattr(school, "pk", "") or "")


def _slug(school) -> str:
    return str(getattr(school, "slug", "") or "")


def _country(school) -> str:
    return str(getattr(school, "country_code", "") or "").upper()


def _fill_command(template: str, school) -> str:
    """Fill a command template for ``school``. Plain string substitution (not
    ``str.format``) so a template that happens to contain shell/Python braces is
    never mis-parsed."""
    return (
        str(template)
        .replace("{slug}", _slug(school))
        .replace("{school_id}", _school_id(school))
        .replace("{country}", _country(school))
    )


def _operator_base() -> str:
    """Operator (cloud) base URL — the same knobs the sync runner reads."""
    base = (getattr(settings, "RMC_EDGE_OPERATOR_BASE", "") or "").strip()
    if not base:
        base = (getattr(settings, "RMC_HUB_BASE_URL", "") or "").strip()
    return base.rstrip("/")


def _edge_token() -> str:
    return (os.getenv("RMC_EDGE_CREDENTIAL") or "").strip()


def _school_has_entitlements(school) -> bool:
    """True when the box's tenant is entitled to run features — via a sovereignty
    billing type, a plan/add-on/features grant, or a materialized Entitlement row.
    The Entitlement read is tenant-scoped, so it is RLS-bypassed."""
    billing_type = getattr(school, "billing_type", None)
    if billing_type in ("COMPLIMENTARY", "MANUAL_OVERRIDE"):
        return True
    plan = getattr(school, "plan", None)
    if plan is not None and getattr(plan, "included_features", None):
        return True
    feats = getattr(school, "features", None) or {}
    if isinstance(feats, dict) and any(bool(v) for v in feats.values()):
        return True
    try:
        from apps.billing.models import Entitlement

        with rls_bypass():
            return Entitlement.objects.filter(school=school, is_enabled=True).exists()
    except Exception:  # noqa: BLE001 — billing app / DB not ready is "not entitled", never a crash
        return False


# --------------------------------------------------------------------------- #
# Step validations — REAL checks, each defensive (never raise past its guard).
# --------------------------------------------------------------------------- #
def _validate_provision_shell(school) -> "tuple[bool, str]":
    try:
        if not bool(getattr(school, "is_active", False)):
            return False, "School is not active — the shell has not been activated yet."
        if not _school_has_entitlements(school):
            return (
                False,
                "School is active but carries no entitlements — run "
                "ensure_gilead_sovereignty_entitlements.",
            )
        return True, "School parent is active and entitled."
    except Exception as exc:  # noqa: BLE001
        return False, f"provision check failed: {exc}"


def _validate_migrate_identities(school) -> "tuple[bool, str]":
    try:
        from apps.schools.models import SchoolMembership

        with rls_bypass():
            has_owner = SchoolMembership.has_active_owner(school)
        if has_owner:
            return True, "School has at least one active owner (a loginable admin)."
        return (
            False,
            "No active owner — import the identity bundle (import_tenant_identities) "
            "or create an owner.",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"identity check failed: {exc}"


def _validate_seed_baseline(school) -> "tuple[bool, str]":
    try:
        from apps.academics.models import AcademicYear, Subject, Term

        with rls_bypass():
            has_year = AcademicYear.objects.filter(school=school).exists()
            has_term = Term.objects.filter(school=school).exists()
            has_subject = Subject.objects.filter(school=school).exists()
        present = [
            name
            for name, ok in (("year", has_year), ("term", has_term), ("subject", has_subject))
            if ok
        ]
        if present:
            return True, "Academic baseline present (" + ", ".join(present) + ")."
        return (
            False,
            "No academic year / term / subject — run backfill_country_baseline "
            "--school <slug> (underlying SoT: the provision_country_baseline() function).",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"baseline check failed: {exc}"


def _validate_media_branding(school) -> "tuple[bool, str]":
    """Pass only when the logo will actually RESOLVE on the box.

    The old check accepted any non-empty ``logo_url`` — including the
    ``https://{slug}.school.lan/…`` URL the old runbook set, which does not resolve
    on a box with no LAN DNS. A logo is genuinely offline-safe when either the
    DB-resident data URI is present (renders with no media server at all) or the
    referenced media file exists on disk. An absolute off-box URL alone is NOT
    enough on an offline box.
    """
    try:
        metadata = getattr(school, "branding_metadata", None) or {}
        data_uri = str(metadata.get("logo_data_uri") or "")
        if data_uri.startswith("data:"):
            return True, "Logo is offline-safe (DB-resident data URI — renders with no media server)."

        from apps.lifecycle.branding_portability import _media_relpath, _read_storage

        logo = (getattr(school, "logo_url", "") or "").strip()
        rel = _media_relpath(logo) or _media_relpath(str(metadata.get("logo_storage_path") or ""))
        if rel and _read_storage(rel) is not None:
            return True, f"Logo file present on the box ({rel})."

        if logo.startswith("http://") or logo.startswith("https://"):
            return False, (
                f"logo_url is an off-box URL ({logo}) with no on-disk file or data URI — "
                "it will not resolve offline. Import the branding bundle "
                "(import_school_branding) so the logo travels as a data URI + local file."
            )
        return False, "No offline logo — import the branding bundle or upload a logo on the box."
    except Exception as exc:  # noqa: BLE001
        return False, f"branding check failed: {exc}"


def _validate_configure_box_env(school) -> "tuple[bool, str]":
    """Best-effort mirror of the hard requirements in ``check_edge_readiness``:
    a real SECRET_KEY and, at DEBUG=0, a non-empty ALLOWED_HOSTS (an empty one 400s
    every request). This does not read tenant tables — pure settings presence."""
    try:
        secret = getattr(settings, "SECRET_KEY", "") or ""
        if not secret or secret.strip().lower() == "change-me-to-a-long-random-string" or len(secret) < 32:
            return False, "SECRET_KEY is unset, a placeholder, or too short (<32 chars)."
        debug = bool(getattr(settings, "DEBUG", False))
        hosts = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
        if not debug and not hosts:
            return False, "ALLOWED_HOSTS is empty at DEBUG=0 — every request will 400."
        return True, "Box environment sane: SECRET_KEY set, ALLOWED_HOSTS present."
    except Exception as exc:  # noqa: BLE001
        return False, f"box-env check failed: {exc}"


def _validate_enable_configure_sync(school) -> "tuple[bool, str]":
    try:
        if not bool(getattr(settings, "RMC_EDGE_SYNC_ENABLED", False)):
            return False, "RMC_EDGE_SYNC_ENABLED is off — the box cannot sync to the operator."
        base = _operator_base()
        token = _edge_token()
        if not base and not token:
            return (
                False,
                "Sync is enabled but neither an operator base URL "
                "(RMC_EDGE_OPERATOR_BASE / RMC_HUB_BASE_URL) nor an edge credential "
                "(RMC_EDGE_CREDENTIAL) is configured.",
            )
        missing = [
            label
            for label, present in (("operator base URL", base), ("edge credential", token))
            if not present
        ]
        if missing:
            return False, "Sync enabled but still missing: " + ", ".join(missing) + "."
        return True, "Sync enabled with an operator base URL and edge credential present."
    except Exception as exc:  # noqa: BLE001
        return False, f"sync-config check failed: {exc}"


def _validate_verify_and_sync_gate(school) -> "tuple[bool, str]":
    """The mandatory pre-offline gate: delegate to the no-write dry sync probe."""
    gate = run_sync_gate(school)
    return bool(gate.get("cleared")), str(gate.get("detail") or "")


# --------------------------------------------------------------------------- #
# Self-heal callables (optional) — also never raise past their guard.
# --------------------------------------------------------------------------- #
def _heal_seed_baseline(school) -> "tuple[bool, str]":
    """Re-run the idempotent country baseline seeding (terms / grading / subjects /
    codes / trades / grids). Safe to repeat: uploaded catalogs, issued admission
    numbers, and admin edits are all left untouched."""
    try:
        from apps.academics.structure_provisioning import provision_country_baseline

        with rls_bypass():
            summary = provision_country_baseline(school) or {}
        highlights = {
            k: summary.get(k)
            for k in ("terms", "subjects", "subject_codes", "trades")
            if k in summary
        }
        return True, "Re-ran country baseline seeding: " + (str(highlights) or "idempotent no-op") + "."
    except Exception as exc:  # noqa: BLE001
        return False, f"baseline self-heal failed: {exc}"


# --------------------------------------------------------------------------- #
# The ORDERED runbook — seven steps, provisioning through the pre-offline gate.
# --------------------------------------------------------------------------- #
EDGE_ONBOARDING_STEPS: "tuple[EdgeOnboardingStep, ...]" = (
    EdgeOnboardingStep(
        key="provision_shell",
        title="Provision the sovereign tenant shell",
        purpose=(
            "Pin the School parent at the cloud bundle's exact UUID and provision a "
            "clean, RLS-safe, entitled, loginable shell (no bundle data load)."
        ),
        category="provision",
        command_template=(
            "python manage.py import_sovereign_tenant --in /srv/rmc/{slug}.rmcbundle "
            "--slug {slug} --owner-email owner@{slug}.school.lan --country {country} --fresh"
        ),
        validate=_validate_provision_shell,
        workaround=(
            "If no cloud bundle exists, provision from scratch with "
            "provision_sovereign_school --create, then entitle via "
            "ensure_gilead_sovereignty_entitlements. If the slug already resolves to a "
            "DIFFERENT UUID, rename/remove that school first — the importer refuses to guess."
        ),
    ),
    EdgeOnboardingStep(
        key="migrate_identities",
        title="Recreate user identities + MFA",
        purpose=(
            "Recreate the school's Users (password hashes copied verbatim), their "
            "SchoolMembership (role / owner flag), and MFA devices so people sign in "
            "on the box with their existing credentials."
        ),
        category="identity",
        command_template=(
            "python manage.py import_tenant_identities --in /srv/rmc/{slug}.rmcidentity "
            "--slug {slug} --expect-school-id {school_id}"
        ),
        validate=_validate_migrate_identities,
        workaround=(
            "No identity bundle? Create the owner directly with "
            "ensure_default_tenant_admin --slug <slug> (or the shell import already made "
            "one) and have members reset passwords + re-enroll MFA on the box."
        ),
    ),
    EdgeOnboardingStep(
        key="seed_baseline",
        title="Seed the country academic baseline",
        purpose=(
            "Seed the country minimum defaults — academic year + terms (real dates), "
            "grading scale, subjects + national codes, TVET trades, admission template, "
            "curriculum, and grids. Idempotent."
        ),
        category="academics",
        command_template="python manage.py backfill_country_baseline --school {slug}",
        validate=_validate_seed_baseline,
        workaround=(
            "If the country catalog is missing, set the school's country_code (which "
            "seeds region defaults) then re-run; or configure the term window + grading "
            "scale manually in Academics settings."
        ),
        self_heal=_heal_seed_baseline,
    ),
    EdgeOnboardingStep(
        key="media_branding",
        title="Set media + branding",
        purpose=(
            "Set the school logo (and login wallpaper / colors) so report cards, the "
            "portal, and login carry the tenant's identity."
        ),
        category="branding",
        command_template=(
            # On the CLOUD: package the logo (as a DB-resident data URI + raw bytes),
            # colours, and brand profile. On the BOX: apply it — the logo renders with
            # no internet and logo_url is set to a box-resolvable /media/… path.
            "# On the cloud, export the branding:\n"
            "python manage.py export_school_branding --slug {slug} --out {slug}.rmcbrand\n"
            "# Copy {slug}.rmcbrand to the box, then on the box:\n"
            "python manage.py import_school_branding --in {slug}.rmcbrand --slug {slug}"
        ),
        validate=_validate_media_branding,
        workaround=(
            "If there is no logo to carry, upload one through the tenant admin branding "
            "screen on the box — the platform falls back to a neutral mark until then "
            "(never a crash). Do NOT hand-set logo_url to an off-box https URL: it will "
            "not resolve on an offline box."
        ),
    ),
    EdgeOnboardingStep(
        key="configure_box_env",
        title="Configure + verify the box environment",
        purpose=(
            "Validate the offline box's settings — SECRET_KEY, ALLOWED_HOSTS, the "
            "plain-HTTP-over-LAN secure-cookie trap, offline email/SMS queues, OCR, and "
            "at-rest keys — before go-live."
        ),
        category="environment",
        command_template="python manage.py check_edge_readiness --strict   # edge box: {slug} ({country})",
        validate=_validate_configure_box_env,
        workaround=(
            "Address each FAIL/WARN check_edge_readiness prints. For a plain-HTTP LAN "
            "box set SECURE_SSL_REDIRECT / SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE / "
            "HSTS all to 0, and schedule run_periodic_jobs on cron when there is no broker."
        ),
    ),
    EdgeOnboardingStep(
        key="enable_configure_sync",
        title="Enable + configure edge sync",
        purpose=(
            "Turn on RMC_EDGE_SYNC_ENABLED and configure the operator base URL + a minted "
            "per-box edge credential so the box can push local changes up and pull cloud "
            "changes down (money stays cloud-authoritative)."
        ),
        category="sync",
        command_template=(
            "export RMC_EDGE_SYNC_ENABLED=1 RMC_EDGE_OPERATOR_BASE=https://hub.runmycampus.app && "
            "python manage.py mint_edge_credential --slug {slug} --user <owner-username> --days 365"
        ),
        validate=_validate_enable_configure_sync,
        workaround=(
            "Mint the credential (mint_edge_credential) on the OPERATOR (cloud) side and "
            "copy the one-time token onto the box as RMC_EDGE_CREDENTIAL; if the box has no "
            "outbound reach yet, leave sync off and re-run this step once connectivity exists."
        ),
    ),
    EdgeOnboardingStep(
        key="verify_and_sync_gate",
        title="Run the verification suite + pre-offline sync gate",
        purpose=(
            "Prove the box is done: run the full verification suite AND the MANDATORY "
            "no-write dry sync probe (connectivity + credential accepted) that must clear "
            "before the box may go offline."
        ),
        category="verification",
        command_template=(
            "python manage.py shell -c \"from apps.lifecycle import edge_onboarding as e; "
            "from apps.schools.models import School; import json; "
            "s=School.objects.get(slug='{slug}'); "
            "print(json.dumps(e.run_verification_suite(s), default=str)); "
            "print(json.dumps(e.run_sync_gate(s), default=str))\""
        ),
        validate=_validate_verify_and_sync_gate,
        workaround=(
            "If the dry sync gate does not clear, the box is NOT cleared to go offline: "
            "fix connectivity to the operator base URL and re-mint/re-set the edge "
            "credential, then re-run. Never take a box dark on a red gate."
        ),
    ),
)

# Convenience: the ordered step keys.
EDGE_ONBOARDING_STEP_KEYS: "tuple[str, ...]" = tuple(s.key for s in EDGE_ONBOARDING_STEPS)


def _step_by_key(step_key: str) -> Optional[EdgeOnboardingStep]:
    for step in EDGE_ONBOARDING_STEPS:
        if step.key == step_key:
            return step
    return None


# --------------------------------------------------------------------------- #
# Engine functions — ALL self-healing (never raise to the caller).
# --------------------------------------------------------------------------- #
def generate_runbook(school) -> dict:
    """A deterministic, ordered, per-school runbook.

    Returns ``{school_id, slug, country, total, steps}`` where each step is
    ``{key, title, purpose, category, command, workaround}`` with the command's
    ``{slug}`` / ``{school_id}`` / ``{country}`` placeholders filled from the school.
    """
    steps: list[dict] = []
    for step in EDGE_ONBOARDING_STEPS:
        try:
            command = _fill_command(step.command_template, school)
        except Exception:  # noqa: BLE001 — a template fill must never crash the runbook
            command = step.command_template
        steps.append(
            {
                "key": step.key,
                "title": step.title,
                "purpose": step.purpose,
                "category": step.category,
                "command": command,
                "workaround": step.workaround,
            }
        )
    return {
        "school_id": _school_id(school),
        "slug": _slug(school),
        "country": _country(school),
        "total": len(steps),
        "steps": steps,
    }


def run_verification_suite(school, *, include_gate: bool = True) -> dict:
    """Run every step's ``validate(school)`` — the final test suite that proves the box
    is done.

    Returns ``{steps: [{key, ok, detail}], ok, passed, total}``. A single validate()
    that RAISES is caught and recorded as ``ok=False`` — the suite is never aborted.

    ``include_gate=False`` runs steps 1-6 ONLY (skips ``verify_and_sync_gate``): a
    READ-ONLY readiness preview that touches no network and records NO ``EdgeSyncRun``.
    The pre-offline sync gate is a BOX-SIDE check (it must run on the box, where the
    sync flag + credential live), so a cloud-side preview must never fake-run it. Run
    the gate on the box via :func:`run_sync_gate` (the runbook's final step).
    """
    steps = (
        EDGE_ONBOARDING_STEPS
        if include_gate
        else tuple(s for s in EDGE_ONBOARDING_STEPS if s.key != "verify_and_sync_gate")
    )
    results: list[dict] = []
    passed = 0
    for step in steps:
        try:
            outcome = step.validate(school)
            ok, detail = bool(outcome[0]), str(outcome[1])
        except Exception as exc:  # noqa: BLE001 — a raising check never aborts the suite
            ok, detail = False, f"validation raised {type(exc).__name__}: {exc}"
        if ok:
            passed += 1
        results.append({"key": step.key, "ok": ok, "detail": detail})
    total = len(results)
    return {"steps": results, "ok": passed == total and total > 0, "passed": passed, "total": total}


def run_sync_gate(school) -> dict:
    """The MANDATORY pre-offline sync gate.

    Runs the existing no-write connectivity probe
    (``sync_runner.run_sync_cycle(school, mode='dry')``) and returns
    ``{cleared, detail, run}``. ``cleared`` is True only when the dry sync reports
    BOTH enabled AND ok (operator reachable + credential accepted). Never raises.
    """
    run: Optional[dict] = None
    try:
        from apps.sync_engine import sync_runner

        run = sync_runner.run_sync_cycle(school, mode="dry")
    except Exception as exc:  # noqa: BLE001 — the gate must always return a verdict
        return {
            "cleared": False,
            "detail": f"sync gate errored before probing: {type(exc).__name__}: {exc}",
            "run": None,
        }

    run = run or {}
    enabled = bool(run.get("enabled"))
    ok = bool(run.get("ok"))
    cleared = enabled and ok
    if not enabled:
        detail = run.get("message") or "Edge sync is not enabled on this deployment."
    elif ok:
        detail = run.get("message") or "Dry sync cleared: operator reachable, credential accepted."
    else:
        detail = run.get("error") or run.get("message") or "Dry sync did not clear."
    return {"cleared": cleared, "detail": str(detail), "run": run}


def heal_step(school, step_key: str) -> dict:
    """Attempt a step's ``self_heal(school)`` if it has one.

    Returns ``{healed, detail}``; a step with no self-heal (or an unknown key) returns
    ``healed=False``. Never raises — a self-heal that blows up is recorded, not raised.
    """
    step = _step_by_key(step_key)
    if step is None:
        return {"healed": False, "detail": f"unknown step: {step_key!r}"}
    if step.self_heal is None:
        return {"healed": False, "detail": "no self-heal for step"}
    try:
        outcome = step.self_heal(school)
        return {"healed": bool(outcome[0]), "detail": str(outcome[1])}
    except Exception as exc:  # noqa: BLE001 — a failing self-heal never crashes the caller
        return {"healed": False, "detail": f"self-heal raised {type(exc).__name__}: {exc}"}


__all__ = [
    "EdgeOnboardingStep",
    "EDGE_ONBOARDING_STEPS",
    "EDGE_ONBOARDING_STEP_KEYS",
    "generate_runbook",
    "run_verification_suite",
    "run_sync_gate",
    "heal_step",
]
