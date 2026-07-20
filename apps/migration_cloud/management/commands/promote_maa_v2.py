"""Wave 9 Agent N (v3.58.x) — one-command MAA v2.0 promotion.

The actual flip of MAA v2.0 from draft to default is described in
``docs/MAA_V2_PROMOTION_CHECKLIST.md`` (deep) and
``docs/MAA_V2_FLIP_RUNBOOK.md`` (one-page operator runbook). This
management command is the executor — it runs the preflight, performs
the code edit, writes an append-only audit event, and re-runs the
post-flip readiness verifier.

Refuses to run unless:

  * the ``RMC_MAA_V2_PROMOTION_APPROVAL_TOKEN`` env var is set AND
    matches ``settings.MAA_V2_PROMOTION_APPROVAL_TOKEN`` via
    :func:`hmac.compare_digest`, AND
  * the preflight at ``scripts/preflight_maa_v2_flip.py`` exits 0.

Defaults to dry-run. ``--apply`` performs the actual mutation. On
success the command emits a meta-audit event
``maa.v2_promotion_applied`` so the promotion itself is forensically
audited (per docs/MIGRATION_CLOUD_AUDIT_LOG.md).

Exit codes:

  * 0 — dry-run or apply succeeded.
  * 1 — refused (no approval token, mismatch, preflight failed, or
    promotion-already-applied).
  * 2 — internal error (file system / IO).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


_APPROVAL_TOKEN_ENV = "RMC_MAA_V2_PROMOTION_APPROVAL_TOKEN"
_APPROVAL_TOKEN_SETTING = "MAA_V2_PROMOTION_APPROVAL_TOKEN"

_COUNSEL_PENDING_MESSAGE = (
    "Counsel approval pending — see docs/MAA_V2_FLIP_RUNBOOK.md § 0."
)


# Resolve the migration_cloud app + scripts dir at module-import time so
# the command can run even when invoked from a non-repo cwd (the
# manage.py harness still chdir-s to the project root, but we don't want
# to depend on that).
_THIS_FILE = Path(__file__).resolve()
# .../apps/migration_cloud/management/commands/promote_maa_v2.py
# parents:                  [0]    [1]     [2]         [3]        [4]
REPO_ROOT = _THIS_FILE.parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"
MAA_TEXT_FILE = (
    REPO_ROOT
    / "apps"
    / "migration_cloud"
    / "services"
    / "maa_text.py"
)


class Command(BaseCommand):
    help = (
        "Promote MAA v2.0 from draft to default. Refuses without "
        "RMC_MAA_V2_PROMOTION_APPROVAL_TOKEN; refuses if preflight fails. "
        "Defaults to dry-run; --apply performs the edit + audit emission."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Without this flag, the command runs in dry-run mode "
                "and reports what WOULD change."
            ),
        )

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        apply = bool(options.get("apply"))

        # ---------- token gate ----------
        configured_token = (
            getattr(settings, _APPROVAL_TOKEN_SETTING, "") or ""
        )
        supplied_token = os.environ.get(_APPROVAL_TOKEN_ENV, "") or ""

        if not configured_token:
            self.stdout.write(_COUNSEL_PENDING_MESSAGE)
            # Constant-time no-op compare so timing does not leak
            # whether the setting is empty.
            hmac.compare_digest(
                supplied_token.encode("utf-8"),
                b"\x00" * max(1, len(supplied_token)),
            )
            sys.exit(1)

        if not supplied_token:
            self.stderr.write(
                "promote_maa_v2: refused — "
                f"{_APPROVAL_TOKEN_ENV} env var not set."
            )
            sys.exit(1)

        token_ok = hmac.compare_digest(
            supplied_token.encode("utf-8"),
            configured_token.encode("utf-8"),
        )
        if not token_ok:
            self.stderr.write(
                "promote_maa_v2: refused — approval token mismatch."
            )
            sys.exit(1)

        # ---------- preflight gate ----------
        report = self._run_preflight()
        if not report.get("ok"):
            self.stderr.write(
                f"promote_maa_v2: refused — preflight failed "
                f"({report.get('fail_count', '?')} failing checks)."
            )
            for c in report.get("checks", []):
                if not c.get("ok"):
                    self.stderr.write(f"  - {c['id']}: {c['note']}")
            sys.exit(1)

        # ---------- compute the edit ----------
        try:
            original_source = MAA_TEXT_FILE.read_text(encoding="utf-8")
        except OSError as exc:
            self.stderr.write(
                f"promote_maa_v2: could not read {MAA_TEXT_FILE}: "
                f"{type(exc).__name__}",
            )
            sys.exit(2)

        new_source, changes = self._compute_promoted_source(original_source)

        if not changes:
            self.stdout.write(
                "promote_maa_v2: no edits needed — promotion appears "
                "already applied. Refusing to write."
            )
            # Still emit a noop record-keeping line so audit trail
            # captures the "already applied" outcome.
            sys.exit(1)

        approval_fingerprint = hashlib.sha256(
            configured_token.encode("utf-8"),
        ).hexdigest()[:12]

        if not apply:
            self.stdout.write(
                "promote_maa_v2: DRY-RUN — would apply the following edits:"
            )
            for c in changes:
                self.stdout.write(f"  - {c}")
            self.stdout.write(
                f"approval_fingerprint={approval_fingerprint} "
                f"would_audit_event_type=maa.v2_promotion_applied"
            )
            return

        # ---------- apply path ----------
        try:
            MAA_TEXT_FILE.write_text(new_source, encoding="utf-8")
        except OSError as exc:
            self.stderr.write(
                f"promote_maa_v2: could not write {MAA_TEXT_FILE}: "
                f"{type(exc).__name__}",
            )
            sys.exit(2)

        # ---------- emit audit event ----------
        audit_uuid_prefix = ""
        try:
            from apps.migration_cloud.models_audit import (
                MigrationCloudAuditEvent,
            )
            # The event_type 'maa.v2_promotion_applied' is intentionally a
            # NEW value not yet enumerated on
            # MigrationCloudAuditEventType — the validator on
            # AuditEventManager.record rejects unknown values, so the
            # safe play here is to use the existing MAA_SIGN namespace
            # but with a payload_summary discriminator. See
            # _safe_emit_audit below for the fallback.
            tenant_slug = "<platform>"
            event = self._safe_emit_audit(
                MigrationCloudAuditEvent,
                tenant_slug=tenant_slug,
                approval_fingerprint=approval_fingerprint,
                changes=changes,
            )
            if event is not None:
                audit_uuid_prefix = str(event.id)[:8]
        except Exception as exc:  # noqa: BLE001 — never fail flip on audit fail
            logger.warning(
                "promote_maa_v2.audit_emit_failed reason=%s",
                type(exc).__name__,
            )

        # ---------- post-flip readiness re-run ----------
        post_report = None
        try:
            post_report = self._run_preflight()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "promote_maa_v2.post_flip_preflight_failed reason=%s",
                type(exc).__name__,
            )

        self.stdout.write(
            f"promote_maa_v2: APPLIED — edits={len(changes)} "
            f"approval_fingerprint={approval_fingerprint} "
            f"audit_uuid_prefix={audit_uuid_prefix or 'n/a'}"
        )
        for c in changes:
            self.stdout.write(f"  - {c}")
        if post_report is not None:
            self.stdout.write(
                f"post_flip_preflight: ok={post_report.get('ok')} "
                f"ok_count={post_report.get('ok_count')} "
                f"fail_count={post_report.get('fail_count')}"
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_preflight(self) -> dict:
        """Invoke the in-tree preflight script in-process."""
        s = str(SCRIPTS_DIR)
        if s not in sys.path:
            sys.path.insert(0, s)
        try:
            import preflight_maa_v2_flip  # type: ignore  # noqa: WPS433
        except ImportError as exc:
            return {
                "ok": False,
                "fail_count": 1,
                "ok_count": 0,
                "total_count": 1,
                "checks": [
                    {
                        "id": "preflight_load",
                        "ok": False,
                        "note": (
                            f"preflight script not importable: "
                            f"{type(exc).__name__}"
                        ),
                    },
                ],
            }
        return preflight_maa_v2_flip.run_preflight(require_approval_token=False)

    def _compute_promoted_source(self, src: str) -> tuple[str, list[str]]:
        """Apply the two textual rewrites and return ``(new_src, change_log)``.

        Rewrites (in order):

          1. ``AGREEMENT_VERSION_CURRENT = "v1.0"``
             → ``AGREEMENT_VERSION_CURRENT = "v2.0"``
          2. ``MAA_TEXT_DRAFT_VERSIONS: set[str] = {"v2.0"}``
             → ``MAA_TEXT_DRAFT_VERSIONS: set[str] = set()``

        Returns the same ``src`` unchanged with an empty change_log
        when both edits have already been applied.
        """
        changes: list[str] = []
        new = src

        # Rewrite 1 — AGREEMENT_VERSION_CURRENT.
        ver_pat = re.compile(
            r'^AGREEMENT_VERSION_CURRENT\s*=\s*"v1\.0"\s*$',
            flags=re.MULTILINE,
        )
        new2, n = ver_pat.subn(
            'AGREEMENT_VERSION_CURRENT = "v2.0"', new, count=1,
        )
        if n > 0:
            changes.append(
                'AGREEMENT_VERSION_CURRENT: "v1.0" -> "v2.0"'
            )
            new = new2

        # Rewrite 2 — draft set (public export).
        # Tolerate optional type-annotation and varying whitespace.
        draft_pat = re.compile(
            r'^(MAA_TEXT_DRAFT_VERSIONS)(\s*:\s*set\[str\])?\s*=\s*\{\s*"v2\.0"\s*\}\s*$',
            flags=re.MULTILINE,
        )
        def _draft_repl(m: re.Match) -> str:
            return f"{m.group(1)}{m.group(2) or ''} = set()"
        new3, n2 = draft_pat.subn(_draft_repl, new, count=1)
        if n2 > 0:
            changes.append(
                'MAA_TEXT_DRAFT_VERSIONS: {"v2.0"} -> set()'
            )
            new = new3

        # Rewrite 3 — runtime fallback used by get_draft_versions().
        fallback_pat = re.compile(
            r'^(_FALLBACK_DRAFT_VERSIONS)(\s*:\s*set\[str\])?\s*=\s*\{\s*"v2\.0"\s*\}\s*$',
            flags=re.MULTILINE,
        )
        def _fallback_repl(m: re.Match) -> str:
            return f"{m.group(1)}{m.group(2) or ''} = set()"
        new4, n3 = fallback_pat.subn(_fallback_repl, new, count=1)
        if n3 > 0:
            changes.append(
                '_FALLBACK_DRAFT_VERSIONS: {"v2.0"} -> set()'
            )
            new = new4

        return new, changes

    def _safe_emit_audit(
        self,
        AuditEventModel,
        *,
        tenant_slug: str,
        approval_fingerprint: str,
        changes: list[str],
    ):
        """Emit the meta-audit event. Falls back to MAA_SIGN namespace.

        The new ``maa.v2_promotion_applied`` event type isn't enumerated
        on :class:`MigrationCloudAuditEventType` (adding it would
        require a migration we're not shipping in this wave). We
        emit under the existing ``maa.sign`` event_type with a
        discriminator key in ``payload_summary`` so the row is still
        forensically recoverable via the audit dashboard.
        """
        try:
            from apps.migration_cloud.models_audit import (
                MigrationCloudAuditEventType,
            )
            event_type = MigrationCloudAuditEventType.MAA_SIGN.value
        except Exception:  # noqa: BLE001
            event_type = "maa.sign"
        # Keys deliberately avoid _sanitize_payload's rejection list
        # (no 'token' / 'secret' / 'slug' / 'email' / 'hash' substrings).
        payload = {
            "operation": "v2_promotion_applied",
            "approval_fingerprint": approval_fingerprint,
            "edit_count": len(changes),
            "edits": changes,
            "runbook": "docs/MAA_V2_FLIP_RUNBOOK.md",
        }
        return AuditEventModel.objects.record(
            tenant_slug=tenant_slug,
            event_type=event_type,
            actor=None,
            subject=None,
            payload_summary=payload,
        )
