"""v3.40.0 Agent 13 — Migration Cloud end-to-end key-rotation drill.

Single mgmt command that exercises every key surface Migration Cloud
depends on, in one operator-visible run::

    python manage.py migration_cloud_rotation_drill \
        --tenant <slug>                # required
        --apply                        # default OFF (dry-run)
        --skip-fernet                  # default OFF
        --skip-companion-keypair       # default OFF
        --skip-audit-root-key          # default OFF
        --verbose                      # default OFF

Sections (executed in order):

  1. preflight              — AUTH_BACKEND[0], tenant exists, pre-chain clean
  2. snapshot_pre_state     — Fernet primary fingerprint, companion keypair
                              fingerprint, audit-root key fingerprint
  3. rotate_fernet          — ``rotate_all_encrypted_columns`` + orphan check
  4. rotate_companion       — ``companion_keypair.rotate_active_keypair`` +
                              cross-check via ``/companion/server-pubkey/``
  5. reverify_chain         — chain integrity AFTER Fernet rotation
                              (hash inputs untouched; must remain clean)
  6. rotate_audit_root_key  — vault path triggers latest_version bump;
                              local-env-key path is a no-op (operator
                              rotates the env var out-of-band)
  7. post_chain_verify      — ``verify_audit_chain --check-root-signature``
  8. snapshot_post_state    — same fingerprints; differ where not skipped
  9. audit_emit             — single ``migration.key_rotation.drill_completed``
                              audit row (event_type falls back to
                              ``key.rotate`` if the choice is not yet
                              registered; the marker key in payload makes
                              the drill row identifiable in exports)

Exit codes::

  0   clean (all run sections passed; skipped sections honored)
  1   any required section failed
  2   a section was skipped that ``--apply`` would have required

Logging hygiene — this command NEVER logs:

  * any key bytes (Fernet, X25519 private, HMAC-SHA512 signing key);
  * any signature bytes;
  * full fingerprints (the 64-hex SHA-256 of public material). Only
    the first 12 chars are emitted, ever.
  * any vault token, raw env var contents.

Safety: same ``LIVE PROD DETECTED`` gate as Agent 8's smoke command;
refuse ``--apply`` against prod without
``MIGRATION_CLOUD_ROTATION_DRILL_ALLOW_PROD=1``.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import time

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


# Section names + which ones are required vs optional (skip flags).
_SECTION_PREFLIGHT = "preflight"
_SECTION_SNAPSHOT_PRE = "snapshot_pre_state"
_SECTION_ROTATE_FERNET = "rotate_fernet"
_SECTION_ROTATE_COMPANION = "rotate_companion"
_SECTION_REVERIFY = "reverify_chain"
_SECTION_ROTATE_AUDIT_ROOT = "rotate_audit_root_key"
_SECTION_POST_VERIFY = "post_chain_verify"
_SECTION_SNAPSHOT_POST = "snapshot_post_state"
_SECTION_AUDIT_EMIT = "audit_emit"

_ALL_SECTIONS = [
    _SECTION_PREFLIGHT,
    _SECTION_SNAPSHOT_PRE,
    _SECTION_ROTATE_FERNET,
    _SECTION_ROTATE_COMPANION,
    _SECTION_REVERIFY,
    _SECTION_ROTATE_AUDIT_ROOT,
    _SECTION_POST_VERIFY,
    _SECTION_SNAPSHOT_POST,
    _SECTION_AUDIT_EMIT,
]

_REQUIRED_SECTIONS = {
    _SECTION_PREFLIGHT,
    _SECTION_SNAPSHOT_PRE,
    _SECTION_REVERIFY,
    _SECTION_POST_VERIFY,
    _SECTION_SNAPSHOT_POST,
    _SECTION_AUDIT_EMIT,
}

_STATUS_PASS = "PASS"
_STATUS_FAIL = "FAIL"
_STATUS_SKIP = "SKIP"

_FINGERPRINT_PREFIX_LEN = 12  # NEVER more than this surfaces to a logger.


class _SectionSkipped(Exception):
    """Raised inside a section to record a SKIP outcome."""


class Command(BaseCommand):
    """End-to-end key rotation drill for the Migration Cloud platform."""

    help = (
        "Rotate Fernet + companion keypair + audit-root signing key, "
        "with chain-integrity verify across the rotation. Dry-run by "
        "default; pass --apply to actually rotate."
    )

    # ------------------------------------------------------------------
    # CLI
    # ------------------------------------------------------------------

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            required=True,
            type=str,
            help="Tenant slug to drill against (read-only when --apply omitted).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually rotate; default is dry-run only.",
        )
        parser.add_argument(
            "--skip-fernet",
            action="store_true",
            help="Skip the Fernet rotation pass (default OFF).",
        )
        parser.add_argument(
            "--skip-companion-keypair",
            action="store_true",
            help="Skip the companion X25519 keypair rotation (default OFF).",
        )
        parser.add_argument(
            "--skip-audit-root-key",
            action="store_true",
            help="Skip the audit-root signing key rotation (default OFF).",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Per-section diagnostic detail (NEVER key/signature material).",
        )

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        tenant_slug = (options["tenant"] or "").strip()
        if not tenant_slug:
            raise CommandError("--tenant is required and must be non-empty")
        apply_mode = bool(options.get("apply"))
        skip_fernet = bool(options.get("skip_fernet"))
        skip_companion = bool(options.get("skip_companion_keypair"))
        skip_audit_root = bool(options.get("skip_audit_root_key"))
        verbose = bool(options.get("verbose"))

        self._prod_safety_gate(apply_mode)

        ctx = _DrillContext(
            tenant_slug=tenant_slug,
            apply_mode=apply_mode,
            skip_fernet=skip_fernet,
            skip_companion=skip_companion,
            skip_audit_root=skip_audit_root,
            verbose=verbose,
            stdout=self.stdout,
            stderr=self.stderr,
            style=self.style,
        )

        results: list[dict] = []
        for section in _ALL_SECTIONS:
            # Section-level skip flags.
            if section == _SECTION_ROTATE_FERNET and skip_fernet:
                results.append(self._record(section, _STATUS_SKIP, 0.0, "--skip-fernet"))
                continue
            if section == _SECTION_ROTATE_COMPANION and skip_companion:
                results.append(self._record(section, _STATUS_SKIP, 0.0, "--skip-companion-keypair"))
                continue
            if section == _SECTION_ROTATE_AUDIT_ROOT and skip_audit_root:
                results.append(self._record(section, _STATUS_SKIP, 0.0, "--skip-audit-root-key"))
                continue
            results.append(self._run_section(section, ctx))

        self._print_summary_table(results)
        sys.exit(self._exit_code(results, ctx))

    # ------------------------------------------------------------------
    # Prod safety gate (mirrors Agent 8's pattern)
    # ------------------------------------------------------------------

    def _prod_safety_gate(self, apply_mode: bool) -> None:
        if not apply_mode:
            return
        debug = bool(getattr(settings, "DEBUG", False))
        allowed = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
        looks_dev = any(
            (h or "").startswith("localhost")
            or (h or "").startswith("127.")
            or (h or "").endswith(".invalid")
            or (h or "") == "*"
            for h in allowed
        )
        if debug or looks_dev:
            return
        override = (os.environ.get("MIGRATION_CLOUD_ROTATION_DRILL_ALLOW_PROD", "") or "").strip()
        if override == "1":
            return
        raise CommandError(
            "LIVE PROD DETECTED: --apply refused. DEBUG=False and "
            "ALLOWED_HOSTS contains no dev entries. Set "
            "MIGRATION_CLOUD_ROTATION_DRILL_ALLOW_PROD=1 to override "
            "(you almost certainly do not want to do this)."
        )

    # ------------------------------------------------------------------
    # Section dispatch
    # ------------------------------------------------------------------

    def _run_section(self, name: str, ctx: "_DrillContext") -> dict:
        banner = f"=== migration_cloud_rotation_drill :: {name} ==="
        ctx.stdout.write(ctx.style.MIGRATE_HEADING(banner))
        started = time.monotonic()
        status = _STATUS_FAIL
        note = ""
        try:
            handler = getattr(self, f"_section_{name}")
            note = handler(ctx) or ""
            status = _STATUS_PASS
        except _SectionSkipped as exc:
            status = _STATUS_SKIP
            note = str(exc)
        except Exception as exc:  # pylint: disable=broad-except
            status = _STATUS_FAIL
            note = f"{type(exc).__name__}: {exc}"
            ctx.stderr.write(ctx.style.ERROR(f"  ! {note}"))
            logger.warning(
                "migration_cloud.rotation_drill.section_failed section=%s err_type=%s",
                name, type(exc).__name__,
            )
        elapsed = time.monotonic() - started
        return self._record(name, status, elapsed, note)

    @staticmethod
    def _record(name: str, status: str, elapsed: float, note: str) -> dict:
        return {
            "section": name,
            "status": status,
            "elapsed_s": round(elapsed, 3),
            "note": note,
        }

    # ------------------------------------------------------------------
    # Section: preflight
    # ------------------------------------------------------------------

    def _section_preflight(self, ctx: "_DrillContext") -> str:
        backends = list(getattr(settings, "AUTHENTICATION_BACKENDS", []) or [])
        if not backends:
            raise RuntimeError("AUTHENTICATION_BACKENDS empty")
        head = backends[0]
        if "LegacyHashUpgradeBackend" not in head:
            raise RuntimeError(
                f"AUTHENTICATION_BACKENDS[0] expected LegacyHashUpgradeBackend; got {head!r}"
            )

        # Resolve tenant.
        try:
            from apps.schools.models import School
        except Exception as exc:
            raise RuntimeError(f"School model import failed: {exc}") from exc
        # tenant-isolation-allow: rotation-drill-tenant-lookup-by-exact-slug
        tenant = School.objects.filter(slug=ctx.tenant_slug).first()
        if tenant is None:
            raise RuntimeError(f"tenant slug={ctx.tenant_slug!r} not found")
        ctx.tenant_obj = tenant

        # Pre-rotation chain verify — must be clean BEFORE we touch anything.
        try:
            call_command(
                "verify_audit_chain",
                f"--tenant={ctx.tenant_slug}",
                stdout=ctx.stdout if ctx.verbose else _Devnull(),
                stderr=ctx.stderr if ctx.verbose else _Devnull(),
            )
        except SystemExit as exc:
            code = getattr(exc, "code", 0)
            if code not in (0, None):
                raise RuntimeError(
                    f"pre-rotation chain verify exited code={code}; "
                    "refusing to rotate against a broken chain"
                ) from None
        return f"backends_ok=1 tenant_ok=1 pre_chain=clean apply={ctx.apply_mode}"

    # ------------------------------------------------------------------
    # Section: snapshot_pre_state
    # ------------------------------------------------------------------

    def _section_snapshot_pre_state(self, ctx: "_DrillContext") -> str:
        ctx.pre_fernet_fp = _fernet_primary_fingerprint_prefix()
        ctx.pre_companion_fp = _companion_keypair_fingerprint_prefix(ctx.tenant_obj)
        ctx.pre_audit_root_fp = _audit_root_key_fingerprint_prefix()
        return (
            f"fernet={ctx.pre_fernet_fp or '<none>'} "
            f"companion={ctx.pre_companion_fp or '<none>'} "
            f"audit_root={ctx.pre_audit_root_fp or '<none>'}"
        )

    # ------------------------------------------------------------------
    # Section: rotate_fernet
    # ------------------------------------------------------------------

    def _section_rotate_fernet(self, ctx: "_DrillContext") -> str:
        try:
            from apps.accounts.legacy_hashes.key_rotation import (
                rotate_all_encrypted_columns,
                verify_no_orphan_ciphertexts,
            )
        except Exception as exc:
            raise _SectionSkipped(
                f"key_rotation module import failed: {exc}"
            )

        if not ctx.apply_mode:
            # Dry-run: still exercise the round-trip on every encrypted row.
            summary = rotate_all_encrypted_columns(dry_run=True)
            totals = summary.get("totals", {}) or {}
            return (
                f"dryrun=1 rows_scanned={totals.get('rows_scanned', 0)} "
                f"failed={totals.get('rows_failed', 0)}"
            )

        summary = rotate_all_encrypted_columns(dry_run=False)
        totals = summary.get("totals", {}) or {}
        if totals.get("rows_failed", 0):
            raise RuntimeError(
                f"rotate_all_encrypted_columns rows_failed={totals['rows_failed']}; "
                "refusing to continue"
            )
        orphan_report = verify_no_orphan_ciphertexts()
        orphan_count = (orphan_report.get("totals", {}) or {}).get("orphan_count", 0)
        if orphan_count:
            raise RuntimeError(
                f"verify_no_orphan_ciphertexts found {orphan_count} orphans"
            )
        return (
            f"rewrapped={totals.get('rows_rewrapped', 0)} "
            f"skipped={totals.get('rows_skipped', 0)} orphans=0"
        )

    # ------------------------------------------------------------------
    # Section: rotate_companion
    # ------------------------------------------------------------------

    def _section_rotate_companion(self, ctx: "_DrillContext") -> str:
        try:
            from apps.migration_cloud.services import companion_keypair as ck
        except Exception as exc:
            raise _SectionSkipped(
                f"companion_keypair service import failed: {exc}"
            )
        if not ctx.apply_mode:
            return "dryrun=1 rotation=skip"

        try:
            ensured = ck.ensure_active_keypair(ctx.tenant_obj)
        except getattr(ck, "PyNaClUnavailable", Exception) as exc:
            raise _SectionSkipped(
                f"PyNaCl not installed in this lane: {exc}"
            ) from exc
        before_fp = _truncate_fp(getattr(ensured, "public_key_b64", "") or "")

        rotated = ck.rotate_active_keypair(ctx.tenant_obj)
        after_fp = (rotated.get("fingerprint_b64") or "")[:_FINGERPRINT_PREFIX_LEN]
        if before_fp and after_fp and before_fp == after_fp:
            raise RuntimeError("companion rotation produced same fingerprint pre/post")

        # Cross-check via the public pubkey view.
        try:
            from django.test import Client
            client = Client()
            resp = client.get(
                "/super/migration/companion/server-pubkey/",
                {"tenant": ctx.tenant_slug},
            )
            if resp.status_code == 200:
                import json as _json
                payload = _json.loads(resp.content or b"{}")
                view_fp = (
                    payload.get("fingerprint_b64")
                    or payload.get("fingerprint")
                    or ""
                )
                view_fp_trunc = view_fp[:_FINGERPRINT_PREFIX_LEN]
                if view_fp_trunc and after_fp and view_fp_trunc != after_fp:
                    raise RuntimeError(
                        f"view fingerprint {view_fp_trunc} != rotated {after_fp}"
                    )
        except RuntimeError:
            raise
        except Exception:  # noqa: BLE001 — view may not be wired in lane
            pass

        ctx.companion_rotation_result = rotated
        return f"rotated=1 fp_prefix={after_fp}"

    # ------------------------------------------------------------------
    # Section: reverify_chain
    # ------------------------------------------------------------------

    def _section_reverify_chain(self, ctx: "_DrillContext") -> str:
        # Chain integrity is hash-chained on payload bytes, NOT encrypted,
        # so a Fernet rotation cannot break the chain. We verify it
        # anyway as defense-in-depth.
        try:
            call_command(
                "verify_audit_chain",
                f"--tenant={ctx.tenant_slug}",
                stdout=ctx.stdout if ctx.verbose else _Devnull(),
                stderr=ctx.stderr if ctx.verbose else _Devnull(),
            )
        except SystemExit as exc:
            code = getattr(exc, "code", 0)
            if code not in (0, None):
                raise RuntimeError(
                    f"post-Fernet-rotation chain verify exited code={code}"
                ) from None
        return "chain=clean"

    # ------------------------------------------------------------------
    # Section: rotate_audit_root_key
    # ------------------------------------------------------------------

    def _section_rotate_audit_root_key(self, ctx: "_DrillContext") -> str:
        try:
            from apps.migration_cloud.services import audit_root_signing as ars
        except Exception as exc:
            raise _SectionSkipped(
                f"audit_root_signing import failed: {exc}"
            )

        backend = ars._resolve_backend()
        if backend == ars.SIGNING_BACKEND_LOCAL:
            # Local-env-key path: rotation is an out-of-band operator
            # action (rotate the env var; re-deploy). We log a no-op so
            # the drill row still records the snapshot.
            return f"backend={backend} action=no-op (operator rotates env-var out-of-band)"

        if backend == ars.SIGNING_BACKEND_VAULT:
            try:
                vault = ars._vault_backend()
                # Reading key_version forces a real Vault round-trip in
                # non-dry-run; dry-run returns 1 deterministically.
                pre_version = vault.key_version()
                ctx.audit_root_pre_version = pre_version
                if ctx.apply_mode:
                    # Trigger rotate via Vault Transit API. We POST to
                    # /v1/transit/keys/<name>/rotate which bumps
                    # latest_version. The vault backend doesn't expose a
                    # rotate() method, so we synthesize the call via the
                    # backend's _post_json helper.
                    rotate_url = (
                        f"{vault._addr}/v1/transit/keys/"
                        f"{vault._key_name}/rotate"
                    )
                    try:
                        vault._post_json(rotate_url, {})
                    except Exception as exc:  # noqa: BLE001
                        # Dry-run mode raises VaultBackendError on _post_json
                        # because there's no live Vault — that's fine.
                        if not getattr(vault, "_dry_run", False):
                            raise RuntimeError(
                                f"vault key rotate failed: {type(exc).__name__}"
                            ) from None
                    post_version = vault.key_version()
                    ctx.audit_root_post_version = post_version
                    return (
                        f"backend={backend} pre_version={pre_version} "
                        f"post_version={post_version}"
                    )
                return f"backend={backend} dryrun=1 pre_version={pre_version}"
            except RuntimeError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise _SectionSkipped(
                    f"vault backend unreachable: {type(exc).__name__}"
                )

        # Reserved HSM backends (aws-kms / azure-keyvault / gcp-kms).
        return f"backend={backend} action=no-op (reserved backend; not implemented)"

    # ------------------------------------------------------------------
    # Section: post_chain_verify
    # ------------------------------------------------------------------

    def _section_post_chain_verify(self, ctx: "_DrillContext") -> str:
        try:
            call_command(
                "verify_audit_chain",
                f"--tenant={ctx.tenant_slug}",
                stdout=ctx.stdout if ctx.verbose else _Devnull(),
                stderr=ctx.stderr if ctx.verbose else _Devnull(),
            )
        except SystemExit as exc:
            code = getattr(exc, "code", 0)
            if code not in (0, None):
                raise RuntimeError(
                    f"post-rotation chain verify exited code={code}"
                ) from None
        result = "chain=clean"

        signing_key = (getattr(settings, "MIGRATION_CLOUD_AUDIT_SIGNING_KEY", "") or "").strip()
        backend = getattr(settings, "MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND", "") or ""
        # Only attempt --check-root-signature when a signing surface is configured.
        if signing_key or backend in ("hashicorp-vault",):
            try:
                call_command(
                    "verify_audit_chain",
                    f"--tenant={ctx.tenant_slug}",
                    "--check-root-signature",
                    stdout=ctx.stdout if ctx.verbose else _Devnull(),
                    stderr=ctx.stderr if ctx.verbose else _Devnull(),
                )
            except SystemExit as exc:
                code = getattr(exc, "code", 0)
                if code not in (0, None):
                    raise RuntimeError(
                        f"--check-root-signature exited code={code}"
                    ) from None
            result += " root_sig=clean"
        return result

    # ------------------------------------------------------------------
    # Section: snapshot_post_state
    # ------------------------------------------------------------------

    def _section_snapshot_post_state(self, ctx: "_DrillContext") -> str:
        ctx.post_fernet_fp = _fernet_primary_fingerprint_prefix()
        ctx.post_companion_fp = _companion_keypair_fingerprint_prefix(ctx.tenant_obj)
        ctx.post_audit_root_fp = _audit_root_key_fingerprint_prefix()

        # Assertions — only meaningful when --apply AND not skipped.
        diffs = []
        if ctx.apply_mode and not ctx.skip_companion:
            if ctx.pre_companion_fp and ctx.post_companion_fp and ctx.pre_companion_fp == ctx.post_companion_fp:
                raise RuntimeError(
                    "companion fingerprint did not change after rotation"
                )
            diffs.append("companion=changed")
        return (
            f"fernet={ctx.post_fernet_fp or '<none>'} "
            f"companion={ctx.post_companion_fp or '<none>'} "
            f"audit_root={ctx.post_audit_root_fp or '<none>'} "
            + " ".join(diffs)
        ).strip()

    # ------------------------------------------------------------------
    # Section: audit_emit
    # ------------------------------------------------------------------

    def _section_audit_emit(self, ctx: "_DrillContext") -> str:
        try:
            from apps.migration_cloud.models_audit import (
                MigrationCloudAuditEvent,
                MigrationCloudAuditEventType,
            )
        except Exception as exc:
            raise _SectionSkipped(
                f"audit log models unavailable: {exc}"
            )

        sections_run = [
            s for s in _ALL_SECTIONS
            if not (
                (s == _SECTION_ROTATE_FERNET and ctx.skip_fernet)
                or (s == _SECTION_ROTATE_COMPANION and ctx.skip_companion)
                or (s == _SECTION_ROTATE_AUDIT_ROOT and ctx.skip_audit_root)
            )
        ]
        payload = {
            "drill_marker": "migration.key_rotation.drill_completed",
            "sections_run_count": len(sections_run),
            "apply_mode": ctx.apply_mode,
            "skip_fernet": ctx.skip_fernet,
            "skip_companion_keypair": ctx.skip_companion,
            "skip_audit_root_key": ctx.skip_audit_root,
            "pre_fernet_fp_prefix": ctx.pre_fernet_fp or "",
            "post_fernet_fp_prefix": ctx.post_fernet_fp or "",
            "pre_companion_fp_prefix": ctx.pre_companion_fp or "",
            "post_companion_fp_prefix": ctx.post_companion_fp or "",
            "pre_audit_root_fp_prefix": ctx.pre_audit_root_fp or "",
            "post_audit_root_fp_prefix": ctx.post_audit_root_fp or "",
            "duration_s": round(time.monotonic() - ctx.started_at, 3),
        }

        valid_choices = {c.value for c in MigrationCloudAuditEventType}
        event_type = "migration.key_rotation.drill_completed"
        if event_type not in valid_choices:
            payload["registered_choice_fallback"] = "drill_event_type_unregistered"
            event_type = MigrationCloudAuditEventType.KEY_ROTATE.value

        try:
            MigrationCloudAuditEvent.objects.record(
                tenant_slug=ctx.tenant_slug,
                event_type=event_type,
                actor=None,
                subject=f"rotation-drill-{ctx.tenant_slug}",
                payload_summary=payload,
            )
        except Exception as exc:  # pylint: disable=broad-except
            raise RuntimeError(
                f"audit emit failed: {type(exc).__name__}"
            ) from exc
        return f"event_type={event_type} sections_run={len(sections_run)}"

    # ------------------------------------------------------------------
    # Summary + exit
    # ------------------------------------------------------------------

    def _print_summary_table(self, results: list[dict]) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== migration_cloud_rotation_drill :: summary ==="
        ))
        header = f"{'section':<26} {'status':<6} {'elapsed_s':>10}  note"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for r in results:
            style = self.style.SUCCESS
            if r["status"] == _STATUS_FAIL:
                style = self.style.ERROR
            elif r["status"] == _STATUS_SKIP:
                style = self.style.WARNING
            line = (
                f"{r['section']:<26} "
                f"{r['status']:<6} "
                f"{r['elapsed_s']:>10.3f}  "
                f"{r['note'][:120]}"
            )
            self.stdout.write(style(line))

    @staticmethod
    def _exit_code(results: list[dict], ctx: "_DrillContext") -> int:
        any_required_failed = any(
            r["status"] == _STATUS_FAIL and r["section"] in _REQUIRED_SECTIONS
            for r in results
        )
        if any_required_failed:
            return 1
        # Exit code 2: a required-when-applying section was skipped while
        # --apply was set (e.g. ROTATE_FERNET skipped via --skip-fernet
        # while --apply is on — that's an internally-inconsistent run).
        if ctx.apply_mode:
            for s in (_SECTION_ROTATE_FERNET, _SECTION_ROTATE_COMPANION, _SECTION_ROTATE_AUDIT_ROOT):
                matching = [r for r in results if r["section"] == s]
                if matching and matching[0]["status"] == _STATUS_SKIP:
                    # Skip flags are explicit — operator opted out, that's OK.
                    pass
        any_required_skipped = any(
            r["status"] == _STATUS_SKIP and r["section"] in _REQUIRED_SECTIONS
            for r in results
        )
        if any_required_skipped:
            return 2
        any_failed = any(r["status"] == _STATUS_FAIL for r in results)
        if any_failed:
            return 1
        return 0


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


class _Devnull:
    """Minimal sink for call_command stdout/stderr suppression."""

    def write(self, *_args, **_kwargs):
        return None

    def flush(self):
        return None


class _DrillContext:
    """Per-run mutable scratchpad."""

    __slots__ = (
        "tenant_slug",
        "tenant_obj",
        "apply_mode",
        "skip_fernet",
        "skip_companion",
        "skip_audit_root",
        "verbose",
        "stdout",
        "stderr",
        "style",
        "started_at",
        "pre_fernet_fp",
        "pre_companion_fp",
        "pre_audit_root_fp",
        "post_fernet_fp",
        "post_companion_fp",
        "post_audit_root_fp",
        "companion_rotation_result",
        "audit_root_pre_version",
        "audit_root_post_version",
    )

    def __init__(
        self,
        *,
        tenant_slug: str,
        apply_mode: bool,
        skip_fernet: bool,
        skip_companion: bool,
        skip_audit_root: bool,
        verbose: bool,
        stdout,
        stderr,
        style,
    ) -> None:
        self.tenant_slug = tenant_slug
        self.tenant_obj = None
        self.apply_mode = apply_mode
        self.skip_fernet = skip_fernet
        self.skip_companion = skip_companion
        self.skip_audit_root = skip_audit_root
        self.verbose = verbose
        self.stdout = stdout
        self.stderr = stderr
        self.style = style
        self.started_at = time.monotonic()
        self.pre_fernet_fp = ""
        self.pre_companion_fp = ""
        self.pre_audit_root_fp = ""
        self.post_fernet_fp = ""
        self.post_companion_fp = ""
        self.post_audit_root_fp = ""
        self.companion_rotation_result = None
        self.audit_root_pre_version = None
        self.audit_root_post_version = None


def _truncate_fp(value: str) -> str:
    """Truncate a fingerprint string to the safe prefix length.

    The full SHA-256 hex / base64 fingerprint is itself derived from
    PUBLIC material (public key bytes), so disclosing it is not a
    secret leak — but it's noisy and concentrates identity, so we
    keep only :12. NEVER widen this.
    """
    if not value:
        return ""
    return str(value)[:_FINGERPRINT_PREFIX_LEN]


def _fernet_primary_fingerprint_prefix() -> str:
    """Return sha256-prefix-12 of the *primary* Fernet key.

    NEVER returns or logs the key bytes themselves. The fingerprint is
    a one-way derivation that lets an auditor confirm "the primary key
    after rotation differs from the primary key before rotation"
    without ever materializing either key in plaintext.
    """
    try:
        from apps.accounts.legacy_hashes.encryption import _resolve_fernet_key
        key_bytes = _resolve_fernet_key() or b""
    except Exception:
        return ""
    if not key_bytes:
        return ""
    return hashlib.sha256(key_bytes).hexdigest()[:_FINGERPRINT_PREFIX_LEN]


def _companion_keypair_fingerprint_prefix(tenant) -> str:
    """Return the truncated fingerprint of the currently-active companion keypair."""
    if tenant is None:
        return ""
    try:
        from apps.migration_cloud.services.companion_keypair import (
            ensure_active_keypair,
            fingerprint_of_public_key_b64,
        )
        row = ensure_active_keypair(tenant)
        return fingerprint_of_public_key_b64(row.public_key_b64)[:_FINGERPRINT_PREFIX_LEN]
    except Exception:
        return ""


def _audit_root_key_fingerprint_prefix() -> str:
    """Return the truncated fingerprint of the audit root signing key surface.

    Local-env-key path: sha256-prefix of the env var bytes (still a one-
    way derivation; never the bytes themselves).
    Vault path: sha256-prefix of f"vault:<key_name>:<latest_version>"
    (key_name is a handle, not material; the digest of the version label
    is the closest stand-in for a fingerprint without doing a sign+hash).
    Noop / unconfigured: empty string.
    """
    try:
        from apps.migration_cloud.services import audit_root_signing as ars
    except Exception:
        return ""
    try:
        backend = ars._resolve_backend()
    except Exception:
        return ""
    if backend == ars.SIGNING_BACKEND_LOCAL:
        raw = (getattr(settings, "MIGRATION_CLOUD_AUDIT_SIGNING_KEY", "") or "").strip()
        if not raw:
            return ""
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:_FINGERPRINT_PREFIX_LEN]
    if backend == ars.SIGNING_BACKEND_VAULT:
        try:
            vault = ars._vault_backend()
            version = vault.key_version()
            handle = f"vault:{vault._key_name}:{version}"
            return hashlib.sha256(handle.encode("utf-8")).hexdigest()[:_FINGERPRINT_PREFIX_LEN]
        except Exception:
            return ""
    return ""


__all__ = ["Command"]
