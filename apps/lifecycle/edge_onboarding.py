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


# Where the operator runs the step. Cloud GET must never pretend a box/LAN
# settings check or a network probe ran on manager.runmycampus.com.
RUNS_ON_CLOUD = "cloud"
RUNS_ON_BOX = "box"
RUNS_ON_LAN = "lan"

# What the validate() call actually inspects.
EVIDENCE_SOURCE_TENANT = "source_tenant"
EVIDENCE_BOX_SETTINGS = "box_settings"
EVIDENCE_OPERATOR_FILE = "operator_file"
EVIDENCE_NETWORK = "network"
EVIDENCE_COMPOSITE = "composite"

ONBOARDING_SETTINGS_KEY = "rmc_edge_onboarding"
MC_SKIP_REASON_MIN_LEN = 12


@dataclass(frozen=True)
class EdgeOnboardingStep:
    """One immutable, ordered step of the edge bring-up runbook.

    ``command_template`` is a copy-pasteable shell / ``manage.py`` string with
    ``{slug}`` / ``{school_id}`` / ``{country}`` placeholders that
    :func:`generate_runbook` fills for a specific school. ``validate`` does a REAL
    check (returns ``(ok, detail)``, never raises past its own guard); ``workaround``
    is the human fallback when a step can't complete; ``self_heal`` (optional) is an
    automated remediation the engine can attempt.

    ``runs_on`` is ``cloud`` | ``box`` | ``lan``. ``evidence`` says what the
    check inspects so a manager-host preview can skip box-settings/network
    without faking a PASS. ``cloud_preview`` False means the step is omitted
    from ``run_verification_suite(..., include_gate=False)`` (no network, no
    EdgeSyncRun write).
    """

    key: str
    title: str
    purpose: str
    category: str
    command_template: str
    validate: StepCheck
    workaround: str
    self_heal: Optional[StepCheck] = field(default=None)
    runs_on: str = RUNS_ON_BOX
    evidence: str = EVIDENCE_SOURCE_TENANT
    cloud_preview: bool = True
    named_url_name: str = ""
    help_doc: str = ""


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


def _onboarding_state(school) -> dict:
    """Tenant-scoped onboarding overlay in ``school.settings``. Never raises."""
    try:
        settings_blob = getattr(school, "settings", None) or {}
        if not isinstance(settings_blob, dict):
            return {}
        blob = settings_blob.get(ONBOARDING_SETTINGS_KEY) or {}
        return dict(blob) if isinstance(blob, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def migration_cloud_skip_reason(school) -> str:
    return str(_onboarding_state(school).get("migration_cloud_skip_reason") or "").strip()


def set_migration_cloud_skip_reason(school, reason: str) -> "tuple[bool, str]":
    """Persist an operator skip (≥12 chars) on the source tenant. Never auto-applies MC."""
    text = str(reason or "").strip()
    if len(text) < MC_SKIP_REASON_MIN_LEN:
        return False, (
            f"Skip reason must be at least {MC_SKIP_REASON_MIN_LEN} characters "
            "(explain why Migration Cloud does not apply)."
        )
    try:
        from apps.schools.models import School

        blob = dict(getattr(school, "settings", None) or {})
        overlay = dict(blob.get(ONBOARDING_SETTINGS_KEY) or {})
        overlay["migration_cloud_skip_reason"] = text[:500]
        blob[ONBOARDING_SETTINGS_KEY] = overlay
        School.objects.filter(pk=school.pk).update(settings=blob)
        school.settings = blob
        return True, "Migration Cloud skip recorded."
    except Exception as exc:  # noqa: BLE001
        return False, f"could not record skip: {exc}"


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


def _validate_lan_hostname(school) -> "tuple[bool, str]":
    """The BOX side of LAN-hostname reachability is ready.

    Client-side DNS (does ``{slug}.school.lan`` resolve to the box?) is the
    operator's network job and cannot be seen from here. What the box CAN prove is
    that it would ACCEPT that hostname instead of 400-ing on it: ALLOWED_HOSTS must
    cover the tenant's LAN host, which on this platform comes from setting
    ``MULTI_TENANT_BASE_DOMAIN`` (it injects a leading-dot ``.<base>`` wildcard into
    ALLOWED_HOSTS). Pure settings — no tenant tables. The box is served over plain
    HTTP on the LAN, so the working URL is ``http://<host>:<web-port>/`` (not https)."""
    try:
        hosts = [str(h).strip().lower() for h in (getattr(settings, "ALLOWED_HOSTS", []) or [])]
        if "*" in hosts:
            return True, "ALLOWED_HOSTS is '*' — any hostname is accepted (open dev config)."
        base = (getattr(settings, "MULTI_TENANT_BASE_DOMAIN", "") or "").strip().lower()
        if not base:
            return (
                False,
                "MULTI_TENANT_BASE_DOMAIN is unset, so a '.school.lan' hostname is not "
                "covered by ALLOWED_HOSTS (default covers .local, not .lan). Set "
                "MULTI_TENANT_BASE_DOMAIN=school.lan on the box.",
            )
        slug = _slug(school)
        lan_host = f"{slug}.{base}" if slug else base
        # Django treats a leading-dot ALLOWED_HOSTS entry as "this host + all subdomains".
        covered = any(
            h == lan_host or (h.startswith(".") and (lan_host == h[1:] or lan_host.endswith(h)))
            for h in hosts
        )
        if covered:
            return True, (
                f"ALLOWED_HOSTS accepts {lan_host}. Reach the box at "
                f"http://{lan_host}:<web-port>/ (plain HTTP — the box has no TLS; "
                "an https:// URL is the 'no lock' failure)."
            )
        return (
            False,
            f"ALLOWED_HOSTS does not cover {lan_host}. Add '.{base}' (wildcard) or "
            f"'{lan_host}', and set MULTI_TENANT_BASE_DOMAIN={base}.",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"LAN hostname check failed: {exc}"


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


def _validate_cloud_entitle_pin(school) -> "tuple[bool, str]":
    """Source tenant is active, entitled, and has a stable UUID to pin on the box."""
    try:
        if not _school_id(school):
            return False, "School has no UUID — cannot pin the box parent."
        ok, detail = _validate_provision_shell(school)
        if not ok:
            return False, detail
        return True, f"Source tenant is active, entitled, and pinable at UUID {_school_id(school)}."
    except Exception as exc:  # noqa: BLE001
        return False, f"entitle/pin check failed: {exc}"


def _validate_migration_cloud_apply(school) -> "tuple[bool, str]":
    """Pass when an MC bundle is applied/reconciled, or an operator skip reason (≥12 chars) exists."""
    try:
        skip = migration_cloud_skip_reason(school)
        if len(skip) >= MC_SKIP_REASON_MIN_LEN:
            return True, f"Migration Cloud skipped by operator ({len(skip)}-char reason)."
        from apps.migration_cloud.models import BundleStatus, MigrationBundle

        applied = {BundleStatus.APPLIED, BundleStatus.RECONCILED}
        with rls_bypass():
            row = (
                MigrationBundle.objects.filter(school=school, status__in=applied)
                .order_by("-id")
                .only("id", "status")
                .first()
            )
        if row is not None:
            return True, f"Migration Cloud bundle {row.id} is {row.status}."
        return (
            False,
            "No applied Migration Cloud bundle on this source tenant. Apply the "
            "connector import on the cloud (students/staff/finance), or record a "
            f"skip reason of at least {MC_SKIP_REASON_MIN_LEN} characters. "
            "Delta sync is not a bulk loader — do not Sync now to seed the box.",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"migration-cloud check failed: {exc}"


def _validate_sync_ownership(school) -> "tuple[bool, str]":
    """No row that provably belongs to this school may be left unowned.

    Edge sync ships ``filter(school=school)``, so a row with ``school_id`` NULL
    reaches NO box, ever, and nothing reports it — the tenant simply never sees
    that data on the box. Production hit exactly this: every academics row was
    unowned, so the whole curriculum was structurally unsyncable while the
    runbook looked green.

    Only ASSIGNABLE rows fail this step. Foreign / ambiguous rows are somebody
    else's problem to adjudicate and must never block or be auto-claimed here.
    """
    try:
        from apps.sync_engine.ownership_repair import ASSIGNABLE, plan_ownership_repair

        plan = plan_ownership_repair(school)
        counts = plan.get("counts") or {}
        claimable = int(counts.get(ASSIGNABLE) or 0)
        if claimable:
            return False, (
                f"{claimable} row(s) have no school but provably belong to this one — "
                "they can never sync until claimed. Run the self-heal, or "
                "repair_sync_ownership --apply."
            )
        leftovers = {k: v for k, v in counts.items() if v}
        if leftovers:
            detail = ", ".join(f"{k}={v}" for k, v in sorted(leftovers.items()))
            return True, f"No claimable rows. Unowned but not attributable: {detail}."
        return True, "Every syncable row has an owner."
    except Exception as exc:  # noqa: BLE001 — a check must never break the runbook
        return False, f"Ownership audit could not run: {str(exc)[:160]}"


def _heal_sync_ownership(school) -> "tuple[bool, str]":
    """Claim only the rows whose owner was INFERRED from referring data."""
    try:
        from apps.sync_engine.ownership_repair import apply_ownership_repair

        result = apply_ownership_repair(school)
        total = int(result.get("total") or 0)
        if not total:
            return False, "Nothing was claimable — no evidence-backed rows to assign."
        detail = ", ".join(f"{k}={v}" for k, v in sorted(result["updated"].items()))
        return True, f"Claimed {total} unowned row(s): {detail}. They ship on the next delta."
    except Exception as exc:  # noqa: BLE001 — self-heal never raises to the runbook
        return False, f"Ownership repair failed: {str(exc)[:160]}"


def _validate_export_cloud_artifacts(school) -> "tuple[bool, str]":
    """The three export commands are real; this host can export if the school is active."""
    try:
        if not bool(getattr(school, "is_active", False)):
            return False, "School is inactive — activate before exporting cloud artifacts."
        if not _school_id(school):
            return False, "School has no UUID — export would not pin."
        return True, (
            "Source tenant can be exported (identities + branding + sovereign data). "
            "Confirm the three files exist on disk before the box import — the engine "
            "cannot see /srv/rmc."
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"export-readiness check failed: {exc}"


def _validate_seed_operational_data(school) -> "tuple[bool, str]":
    """Students and/or classrooms exist — the pk-preserving data seed, not --fresh, not delta sync."""
    try:
        from apps.academics.models import Classroom
        from apps.people.models import StudentProfile

        with rls_bypass():
            student_n = StudentProfile.objects.filter(school=school).count()
            classroom_n = Classroom.objects.filter(school=school).count()
        if student_n or classroom_n:
            return True, (
                f"Operational roster present ({student_n} student(s), "
                f"{classroom_n} classroom(s))."
            )
        return (
            False,
            "No students or classrooms — import the pk-preserving data bundle "
            "(import_tenant_bundle / import_sovereign_tenant WITHOUT --fresh). "
            "Delta sync is not a bulk loader; Sync now will not carry the initial roster.",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"operational-data check failed: {exc}"


def _validate_conversion_first_action(school) -> "tuple[bool, str]":
    try:
        from apps.schools.conversion_lock_state import school_first_action_completed

        if school_first_action_completed(school):
            return True, "Conversion first-value recorded; workspace unlocked."
        return (
            False,
            "Conversion lock still on — save one attendance, mark, report, or payment "
            "(or the activation first-action CTA). Imports are not blocked; the UI is.",
        )
    except Exception as extra:  # noqa: BLE001
        return False, f"conversion-lock check failed: {extra}"


def _latest_sync_run(school, *, mode: str):
    from apps.sync_engine.models import EdgeSyncRun

    with rls_bypass():
        return (
            EdgeSyncRun.objects.filter(school=school, mode=mode)
            .order_by("-created_at")
            .first()
        )


def _validate_live_sync_proof(school) -> "tuple[bool, str]":
    """Read-only: last successful LIVE EdgeSyncRun. Never calls run_sync_cycle."""
    try:
        row = _latest_sync_run(school, mode="live")
        if row is None:
            return (
                False,
                "No live Class-A sync recorded yet. After the dry gate, run a live "
                "cycle ON THE BOX (edge_sync_resync / Sync Center). Never Sync now "
                "from the manager console to seed data.",
            )
        if not bool(getattr(row, "ok", False)):
            err = (getattr(row, "error", "") or getattr(row, "message", "") or "failed")[:180]
            return False, f"Last live sync did not succeed: {err}"
        conflicts = int(getattr(row, "conflicts", 0) or 0)
        return True, (
            f"Last live sync ok (pushed={getattr(row, 'pushed', 0)}, "
            f"pulled={getattr(row, 'pulled', 0)}, conflicts={conflicts})."
        )
    except Exception as extra:  # noqa: BLE001
        return False, f"live-sync proof failed: {extra}"


def _validate_go_dark_checklist(school) -> "tuple[bool, str]":
    """Composite pre-offline proof: dry gate row, live proof, zero conflicts, data, conversion."""
    try:
        parts: list[str] = []
        dry = _latest_sync_run(school, mode="dry")
        dry_ok = bool(dry and getattr(dry, "ok", False))
        parts.append("dry-gate=" + ("ok" if dry_ok else "missing"))

        live_ok, live_detail = _validate_live_sync_proof(school)
        parts.append("live=" + ("ok" if live_ok else "not-ok"))

        live_row = _latest_sync_run(school, mode="live")
        conflicts = int(getattr(live_row, "conflicts", 0) or 0) if live_row is not None else -1
        parts.append(f"conflicts={conflicts if conflicts >= 0 else 'n/a'}")

        data_ok, _ = _validate_seed_operational_data(school)
        conv_ok, _ = _validate_conversion_first_action(school)
        parts.append("roster=" + ("ok" if data_ok else "empty"))
        parts.append("conversion=" + ("unlocked" if conv_ok else "locked"))

        from apps.academics.models import AcademicYear

        with rls_bypass():
            locked_n = AcademicYear.objects.filter(school=school, is_locked=True).count()
            soft_n = AcademicYear.objects.filter(school=school, is_soft_closed=True).count()
        parts.append(
            f"year-governance: cloud owns hard-close ({locked_n} locked) and "
            f"soft-close ({soft_n} soft-closed); the box cannot reopen a cloud lock. "
            "Finance stays cloud-authoritative / down-only."
        )

        if dry_ok and live_ok and conflicts == 0 and data_ok and conv_ok:
            return True, "Go-dark checklist cleared. " + " ".join(parts)
        return False, "Go-dark checklist not cleared. " + " ".join(parts) + (
            "" if live_ok else f" Live: {live_detail}"
        )
    except Exception as extra:  # noqa: BLE001
        return False, f"go-dark checklist failed: {extra}"


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
# The ORDERED runbook — cloud data path through go-dark. Delta sync is never
# a bulk loader; --fresh never seeds roster/finance.
# --------------------------------------------------------------------------- #
EDGE_ONBOARDING_STEPS: "tuple[EdgeOnboardingStep, ...]" = (
    EdgeOnboardingStep(
        key="cloud_entitle_pin",
        title="Entitle and pin the source tenant (cloud)",
        purpose=(
            "Confirm the cloud school is active, entitled, and has a stable UUID. "
            "The box parent is pinned to this exact id so pk-preserving imports land."
        ),
        category="provision",
        command_template=(
            "python manage.py ensure_gilead_sovereignty_entitlements   "
            "# tenant {slug} pin UUID {school_id} ({country})"
        ),
        validate=_validate_cloud_entitle_pin,
        workaround=(
            "If entitlements are missing, run ensure_gilead_sovereignty_entitlements. "
            "If the school is inactive, activate it on the cloud before any box import."
        ),
        runs_on=RUNS_ON_CLOUD,
        evidence=EVIDENCE_SOURCE_TENANT,
        named_url_name="super:dashboard",
        help_doc="docs/EDGE_CLOUD_SYNC_OPERATOR_RUNBOOK.md",
    ),
    EdgeOnboardingStep(
        key="migration_cloud_apply",
        title="Apply Migration Cloud on the cloud (or skip with a reason)",
        purpose=(
            "Bulk-load the school's real files (students, staff, finance) on the CLOUD. "
            "Delta sync will not carry this initial import. Skip only with a written "
            "reason of at least 12 characters (empty shell, already loaded, etc.)."
        ),
        category="migration",
        command_template=(
            "# On the cloud operator console — never 'Sync now' to seed data:\n"
            "# Open Migration Cloud → upload → map → apply for {slug} (id {school_id})."
        ),
        validate=_validate_migration_cloud_apply,
        workaround=(
            "No SIS files? Record a skip reason (≥12 characters) on this runbook page. "
            "Do not use Sync now as a substitute for Migration Cloud apply."
        ),
        runs_on=RUNS_ON_CLOUD,
        evidence=EVIDENCE_SOURCE_TENANT,
        named_url_name="migration_cloud_super:bundle_new",
        help_doc="docs/EDGE_CLOUD_SYNC_OPERATOR_RUNBOOK.md",
    ),
    EdgeOnboardingStep(
        key="sync_ownership_repair",
        title="Give every syncable row an owner (cloud)",
        purpose=(
            "Edge sync ships rows with filter(school=school), so a row whose school_id "
            "is NULL can never reach any box — silently, forever. This claims the rows "
            "that provably belong to this tenant (inferred from the rows referencing "
            "them) and reports any that are ambiguous or belong to another school."
        ),
        category="migration",
        command_template=(
            "python manage.py repair_sync_ownership --school {slug}   "
            "# dry run; re-run with --apply once the verdicts look right"
        ),
        validate=_validate_sync_ownership,
        self_heal=_heal_sync_ownership,
        workaround=(
            "Rows listed AMBIGUOUS or FOREIGN are never auto-claimed — they are "
            "referenced by more than one school, or by a different one. Decide the "
            "owner by hand before importing more data on top of them."
        ),
        runs_on=RUNS_ON_CLOUD,
        evidence=EVIDENCE_SOURCE_TENANT,
        help_doc="docs/EDGE_CLOUD_SYNC_OPERATOR_RUNBOOK.md",
    ),
    EdgeOnboardingStep(
        key="export_cloud_artifacts",
        title="Export identity, branding, and sovereign data (cloud)",
        purpose=(
            "Package three artifacts on the cloud: identities, branding, and the "
            "pk-preserving operational data bundle. Copy them to the box before import."
        ),
        category="export",
        command_template=(
            "python manage.py export_tenant_identities --slug {slug} --out /srv/rmc/{slug}.rmcidentity\n"
            "python manage.py export_school_branding --slug {slug} --out /srv/rmc/{slug}.rmcbrand\n"
            "python manage.py export_tenant_bundle --slug {slug} --out /srv/rmc/{slug}.rmcbundle"
        ),
        validate=_validate_export_cloud_artifacts,
        workaround=(
            "If an export command is missing, you are on a build that cannot seed the box. "
            "Do not invent a CSV copy — use these three commands."
        ),
        runs_on=RUNS_ON_CLOUD,
        evidence=EVIDENCE_OPERATOR_FILE,
        help_doc="docs/EDGE_CLOUD_SYNC_OPERATOR_RUNBOOK.md",
    ),
    EdgeOnboardingStep(
        key="provision_shell",
        title="Provision the sovereign tenant shell",
        purpose=(
            "Pin the School parent at the cloud bundle's exact UUID and provision a "
            "clean, RLS-safe, entitled, loginable shell (no bundle data load). "
            "--fresh is the EMPTY-SHELL path only."
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
        runs_on=RUNS_ON_BOX,
        evidence=EVIDENCE_SOURCE_TENANT,
        help_doc="docs/EDGE_CLOUD_SYNC_OPERATOR_RUNBOOK.md",
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
        runs_on=RUNS_ON_BOX,
        evidence=EVIDENCE_SOURCE_TENANT,
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
            "python manage.py import_school_branding --in /srv/rmc/{slug}.rmcbrand --slug {slug}"
        ),
        validate=_validate_media_branding,
        workaround=(
            "If there is no logo to carry, upload one through the tenant admin branding "
            "screen on the box — the platform falls back to a neutral mark until then "
            "(never a crash). Do NOT hand-set logo_url to an off-box https URL: it will "
            "not resolve on an offline box."
        ),
        runs_on=RUNS_ON_BOX,
        evidence=EVIDENCE_SOURCE_TENANT,
    ),
    EdgeOnboardingStep(
        key="seed_operational_data",
        title="Import the pk-preserving operational data bundle (not --fresh, not Sync now)",
        purpose=(
            "Load students, classrooms, and other operational rows onto the box with "
            "the SAME primary keys as the cloud. This is the initial data seed. "
            "Never use --fresh here. Never use delta sync / Sync now as a bulk loader."
        ),
        category="data",
        command_template=(
            "python manage.py import_tenant_bundle --in /srv/rmc/{slug}.rmcbundle "
            "--expect-school-id {school_id}"
        ),
        validate=_validate_seed_operational_data,
        workaround=(
            "Equivalent: import_sovereign_tenant WITHOUT --fresh after the shell exists. "
            "If the target is not empty, the importer refuses — that is safety, not a bug. "
            "Do not click Sync now to invent a roster."
        ),
        runs_on=RUNS_ON_BOX,
        evidence=EVIDENCE_SOURCE_TENANT,
        help_doc="docs/EDGE_CLOUD_SYNC_OPERATOR_RUNBOOK.md",
    ),
    EdgeOnboardingStep(
        key="seed_baseline",
        title="Seed the country academic baseline",
        purpose=(
            "Seed the country minimum defaults — academic year + terms (real dates), "
            "grading scale, subjects + national codes, TVET trades, admission template, "
            "curriculum, and grids. Idempotent; does not replace imported roster rows."
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
        runs_on=RUNS_ON_BOX,
        evidence=EVIDENCE_SOURCE_TENANT,
    ),
    EdgeOnboardingStep(
        key="conversion_first_action",
        title="Clear the conversion / first-value lock",
        purpose=(
            "The box UI stays gated until one first value is recorded (attendance, mark, "
            "report, or payment). Imports are not blocked; operators still need the UI."
        ),
        category="activation",
        command_template=(
            "# On the box UI after login: complete Activation First Action for {slug}, "
            "or save one attendance / mark / report / payment."
        ),
        validate=_validate_conversion_first_action,
        workaround=(
            "The pink first-action CTA on the activation screen records completion. "
            "There is no manage.py skip — first value must be real."
        ),
        runs_on=RUNS_ON_BOX,
        evidence=EVIDENCE_SOURCE_TENANT,
        help_doc="docs/EDGE_CLOUD_SYNC_OPERATOR_RUNBOOK.md",
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
        runs_on=RUNS_ON_BOX,
        evidence=EVIDENCE_BOX_SETTINGS,
    ),
    EdgeOnboardingStep(
        key="configure_lan_hostname",
        title="Give the box a stable LAN hostname (DNS)",
        purpose=(
            "Map a stable name — {slug}.school.lan — to the box's FIXED LAN IP so "
            "clients reach it by name. The box serves plain HTTP, so the working URL "
            "is http://{slug}.school.lan:<web-port>/ — NOT https://."
        ),
        category="network",
        command_template=(
            "# 0) Fix the box IP first (DHCP reservation on the router), then map the\n"
            "#    name. Pick ONE reach method by how big your LAN is:\n"
            "#  a. Router DNS (OpenWrt / pfSense / prosumer) — every LAN client, cleanest.\n"
            "#  b. Pi-hole / dnsmasq on the box — whole-LAN + logging:\n"
            "#       echo 'address=/{slug}.school.lan/<BOX_LAN_IP>' | sudo tee /etc/dnsmasq.d/rmc-edge.conf\n"
            "#       sudo systemctl restart dnsmasq   # then point the router's DHCP DNS at the box\n"
            "#  c. Per-client hosts file (fast test; only edited devices):\n"
            "#       Linux/macOS: echo '<BOX_LAN_IP>  {slug}.school.lan' | sudo tee -a /etc/hosts\n"
            "#       Windows (admin): add '<BOX_LAN_IP>  {slug}.school.lan' to\n"
            "#         C:\\Windows\\System32\\drivers\\etc\\hosts\n"
            "# 1) On the box, make sure the host is accepted (settings):\n"
            "#     MULTI_TENANT_BASE_DOMAIN=school.lan   (injects the .school.lan wildcard)\n"
            "#     ALLOWED_HOSTS=...,school.lan,{slug}.school.lan,<BOX_LAN_IP>\n"
            "#     CSRF_TRUSTED_ORIGINS=http://{slug}.school.lan:<web-port>\n"
            "# 2) Verify it resolves to the box, then open the login page:\n"
            "getent hosts {slug}.school.lan   # must print <BOX_LAN_IP>\n"
            "#   Open:  http://{slug}.school.lan:<web-port>/authentication/login/"
        ),
        validate=_validate_lan_hostname,
        workaround=(
            "No LAN DNS yet? The box is reachable by IP RIGHT NOW — "
            "http://<BOX_LAN_IP>:<web-port>/ — because SINGLE_TENANT routes any host "
            "to the sole school. Never use https:// on the box (no TLS = the 'no "
            "lock'); use http:// with the explicit port (default 10000). For a real "
            "browser lock + a clean https://{slug}.school.lan (no port), front the box "
            "with a reverse proxy (Caddy / nginx + a local CA) and flip the "
            "secure-cookie flags back to 1. See docs/EDGE_LAN_HOSTNAME_DNS.md."
        ),
        runs_on=RUNS_ON_LAN,
        evidence=EVIDENCE_BOX_SETTINGS,
        help_doc="docs/EDGE_LAN_HOSTNAME_DNS.md",
    ),
    EdgeOnboardingStep(
        key="enable_configure_sync",
        title="Enable + configure edge sync",
        purpose=(
            "Turn on RMC_EDGE_SYNC_ENABLED and configure the operator base URL + a minted "
            "per-box edge credential so the box can push local changes up and pull cloud "
            "changes down (money stays cloud-authoritative). This keeps both sides "
            "converged AFTER the data seed — it does not load the initial roster."
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
        runs_on=RUNS_ON_BOX,
        evidence=EVIDENCE_BOX_SETTINGS,
        named_url_name="siteconfig:sync_center",
    ),
    EdgeOnboardingStep(
        key="verify_and_sync_gate",
        title="Run the verification suite + pre-offline sync gate",
        purpose=(
            "Prove the box is done: run the full verification suite AND the MANDATORY "
            "no-write dry sync probe (connectivity + credential accepted) that must clear "
            "before the box may go offline. Runs on the box only — never from a cloud GET."
        ),
        category="verification",
        command_template="python manage.py edge_onboarding_verify --slug {slug} --include-gate",
        validate=_validate_verify_and_sync_gate,
        workaround=(
            "If the dry sync gate does not clear, the box is NOT cleared to go offline: "
            "fix connectivity to the operator base URL and re-mint/re-set the edge "
            "credential, then re-run. Never take a box dark on a red gate."
        ),
        runs_on=RUNS_ON_BOX,
        evidence=EVIDENCE_NETWORK,
        cloud_preview=False,
    ),
    EdgeOnboardingStep(
        key="live_sync_proof",
        title="Prove one live Class-A round-trip (after the dry gate)",
        purpose=(
            "After the dry gate, run one LIVE sync on the box and confirm it succeeded. "
            "This is convergence proof, not a data loader."
        ),
        category="verification",
        command_template="python manage.py edge_sync_cycle --slug {slug}",
        validate=_validate_live_sync_proof,
        workaround=(
            "If live sync fails, read Sync Center conflicts. Money stays cloud-authoritative. "
            "Do not retry from the manager host — the credential lives on the box."
        ),
        runs_on=RUNS_ON_BOX,
        evidence=EVIDENCE_NETWORK,
        cloud_preview=False,
        named_url_name="siteconfig:sync_center",
    ),
    EdgeOnboardingStep(
        key="go_dark_checklist",
        title="Go-dark checklist (finance down-only, year lock owned by cloud)",
        purpose=(
            "Final composite: dry gate recorded ok, live sync ok with zero conflicts, "
            "roster present, conversion unlocked. Finance is cloud-authoritative / down-only. "
            "Academic year hard-close and soft-close are owned by the cloud; the box cannot reopen them."
        ),
        category="verification",
        command_template="python manage.py edge_onboarding_verify --slug {slug} --include-gate",
        validate=_validate_go_dark_checklist,
        workaround=(
            "Stay online until every go-dark line is green. A box with an empty roster "
            "or a red live sync is not offline-ready."
        ),
        runs_on=RUNS_ON_BOX,
        evidence=EVIDENCE_COMPOSITE,
        cloud_preview=False,
        named_url_name="super:dashboard",
        help_doc="docs/EDGE_CLOUD_SYNC_OPERATOR_RUNBOOK.md",
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
    ``{key, title, purpose, category, command, workaround, runs_on, evidence,
    named_url_name, help_doc, cloud_preview}`` with placeholders filled.
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
                "runs_on": step.runs_on,
                "evidence": step.evidence,
                "named_url_name": step.named_url_name,
                "help_doc": step.help_doc,
                "cloud_preview": bool(step.cloud_preview),
            }
        )
    return {
        "school_id": _school_id(school),
        "slug": _slug(school),
        "country": _country(school),
        "total": len(steps),
        "steps": steps,
    }


def run_verification_suite(school, *, include_gate: bool = True, host_kind: Optional[str] = None) -> dict:
    """Run every step's ``validate(school)`` — the final test suite that proves the box
    is done.

    Returns ``{steps: [{key, ok, detail}], ok, passed, total}``. A single validate()
    that RAISES is caught and recorded as ``ok=False`` — the suite is never aborted.

    ``include_gate=False`` keeps only ``cloud_preview=True`` steps (omits the dry
    gate, live Class-A proof, and go-dark checklist): a READ-ONLY readiness preview
    that touches no network and records NO ``EdgeSyncRun``. Those three checks are
    BOX-SIDE (credential + last cycle live on the box), so a cloud GET must never
    fake-run them. On the box: ``edge_onboarding_verify --slug <slug> --include-gate``.
    """
    steps = (
        EDGE_ONBOARDING_STEPS
        if include_gate
        else tuple(s for s in EDGE_ONBOARDING_STEPS if s.cloud_preview)
    )
    results: list[dict] = []
    passed = 0
    skipped_n = 0
    kind = (host_kind or "").strip().lower()
    for step in steps:
        if kind == "manager" and step.evidence == EVIDENCE_BOX_SETTINGS:
            skipped_n += 1
            results.append(
                {
                    "key": step.key,
                    "ok": False,
                    "skipped": True,
                    "detail": "Not evaluated on the manager host — run this check on the edge box.",
                }
            )
            continue
        try:
            outcome = step.validate(school)
            ok, detail = bool(outcome[0]), str(outcome[1])
        except Exception as extra:  # noqa: BLE001 — a raising check never aborts the suite
            ok, detail = False, f"validation raised {type(extra).__name__}: {extra}"
        if ok:
            passed += 1
        results.append({"key": step.key, "ok": ok, "detail": detail, "skipped": False})
    evaluated = [row for row in results if not row.get("skipped")]
    total = len(results)
    suite_ok = bool(evaluated) and all(row["ok"] for row in evaluated)
    return {
        "steps": results,
        "ok": suite_ok,
        "passed": passed,
        "total": total,
        "skipped": skipped_n,
        "evaluated": len(evaluated),
    }


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
    "RUNS_ON_CLOUD",
    "RUNS_ON_BOX",
    "RUNS_ON_LAN",
    "MC_SKIP_REASON_MIN_LEN",
    "generate_runbook",
    "run_verification_suite",
    "run_sync_gate",
    "heal_step",
    "migration_cloud_skip_reason",
    "set_migration_cloud_skip_reason",
]
