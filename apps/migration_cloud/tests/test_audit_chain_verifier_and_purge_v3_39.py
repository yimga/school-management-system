"""v3.39.0 Agent 1 — audit-chain verifier sweep + retention purge tests.

Coverage matrix (~14 tests):

  --all-tenants verifier sweep
  ----------------------------
  * 0 active tenants → exit 0, summary shows tenants_checked=0
  * 1 active tenant, clean chain → exit 0, summary tenants_clean=1
  * 2 active tenants, both clean → exit 0, summary
    tenants_checked=2, tenants_clean=2
  * 3 active tenants, 1 broken → exit 1, summary
    tenants_broken=1, broken UUID surfaced
  * --tenant + --all-tenants mutually exclusive → CommandError
  * --email-on-broken=<addr> sends summary email; body never contains
    hash bytes or payload bytes

  Celery beat task
  ----------------
  * verify_audit_chain_weekly_task callable, returns gracefully when
    MIGRATION_CLOUD_AUDIT_OPS_EMAIL empty
  * Returns ``{"status": "clean"}`` when no chains broken

  Purge command
  -------------
  * Refuses (exit 1) when MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN
    setting empty — prints counsel-pending message
  * Refuses (exit 1) on wrong token (constant-time compare path)
  * Dry-run (default) shows row count + first/last UUID prefixes
  * --apply deletes rows AND emits meta-audit-event
  * assertLogs proves no PII / secret leaks
"""
from __future__ import annotations

import io
import logging
import uuid
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.migration_cloud.models_audit import (
    GENESIS_SENTINEL,
    MigrationCloudAuditEvent,
    MigrationCloudAuditEventType,
    _hash_tenant_slug,
)
from apps.migration_cloud.tasks_audit import verify_audit_chain_weekly_task
from apps.schools.models import School


def _make_school(slug: str, *, is_active: bool = True) -> School:
    return School.objects.create(
        slug=slug,
        name=f"Test {slug}",
        subdomain=slug,
        is_active=is_active,
    )


def _seed_clean_chain(tenant_slug: str, n: int = 2) -> None:
    for i in range(n):
        MigrationCloudAuditEvent.objects.record(
            tenant_slug=tenant_slug,
            event_type=MigrationCloudAuditEventType.TOKEN_MINT.value,
            payload_summary={"index": i},
        )


def _tamper_first_event(tenant_slug: str) -> str:
    """Tamper with the first event's stored integrity_hash via raw SQL.

    Returns the UUID of the tampered row.
    """
    from django.db import connection

    tenant_hash = _hash_tenant_slug(tenant_slug)
    first = (
        MigrationCloudAuditEvent.objects
        .filter(tenant_id_hash=tenant_hash)  # tenant-isolation-allow: test-fixture-tampering-by-tenant-hash-prefix
        .order_by("created_at")
        .first()
    )
    assert first is not None
    bogus = "f" * 64
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE migration_cloud_migrationcloudauditevent "
            "SET integrity_hash=%s WHERE id=%s",
            [bogus, first.id.hex],
        )
    return str(first.id)


# ─── --all-tenants sweep ────────────────────────────────────────────────


class AllTenantsSweepTests(TestCase):

    def test_zero_active_tenants_exits_clean(self):
        out = io.StringIO()
        err = io.StringIO()
        # Inactive tenant should be ignored.
        _make_school("inactive-zero", is_active=False)
        try:
            call_command(
                "verify_audit_chain", "--all-tenants", stdout=out, stderr=err
            )
            exit_code = 0
        except SystemExit as exc:
            exit_code = exc.code or 0
        self.assertEqual(exit_code, 0)
        self.assertIn("tenants_checked=0", out.getvalue())

    def test_one_clean_tenant_exits_clean(self):
        _make_school("solo-clean")
        _seed_clean_chain("solo-clean", n=2)
        out = io.StringIO()
        err = io.StringIO()
        try:
            call_command(
                "verify_audit_chain", "--all-tenants", stdout=out, stderr=err
            )
            exit_code = 0
        except SystemExit as exc:
            exit_code = exc.code or 0
        self.assertEqual(exit_code, 0)
        self.assertIn("tenants_checked=1", out.getvalue())
        self.assertIn("tenants_clean=1", out.getvalue())
        self.assertIn("total_events_checked=2", out.getvalue())

    def test_two_clean_tenants_exit_clean(self):
        _make_school("alpha-clean")
        _make_school("beta-clean")
        _seed_clean_chain("alpha-clean", n=3)
        _seed_clean_chain("beta-clean", n=1)
        out = io.StringIO()
        try:
            call_command("verify_audit_chain", "--all-tenants", stdout=out)
            exit_code = 0
        except SystemExit as exc:
            exit_code = exc.code or 0
        self.assertEqual(exit_code, 0)
        self.assertIn("tenants_checked=2", out.getvalue())
        self.assertIn("tenants_clean=2", out.getvalue())
        self.assertIn("tenants_broken=0", out.getvalue())

    def test_one_broken_among_three_exits_nonzero(self):
        _make_school("g-clean-a")
        _make_school("g-broken")
        _make_school("g-clean-b")
        _seed_clean_chain("g-clean-a", n=2)
        _seed_clean_chain("g-broken", n=2)
        _seed_clean_chain("g-clean-b", n=2)
        broken_uuid = _tamper_first_event("g-broken")

        out = io.StringIO()
        err = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command(
                "verify_audit_chain", "--all-tenants", stdout=out, stderr=err
            )
        self.assertEqual(ctx.exception.code, 1)
        out_str = out.getvalue()
        self.assertIn("tenants_checked=3", out_str)
        self.assertIn("tenants_broken=1", out_str)
        err_str = err.getvalue()
        self.assertIn(broken_uuid, err_str)

    def test_all_tenants_and_tenant_flag_mutually_exclusive(self):
        with self.assertRaises(CommandError):
            call_command(
                "verify_audit_chain",
                "--all-tenants",
                "--tenant=should-not-work",
            )


# ─── --email-on-broken ──────────────────────────────────────────────────


class EmailOnBrokenTests(TestCase):

    def test_email_sent_with_safe_body_only(self):
        _make_school("email-broken")
        _seed_clean_chain("email-broken", n=2)
        # Pre-grab payload bytes before tampering so we can assert
        # they do NOT appear in the email body.
        tenant_hash = _hash_tenant_slug("email-broken")
        first = (
            MigrationCloudAuditEvent.objects
            .filter(tenant_id_hash=tenant_hash)  # tenant-isolation-allow: test-pre-tamper-readback-by-tenant-hash
            .order_by("created_at")
            .first()
        )
        original_integrity = first.integrity_hash
        original_payload = dict(first.payload_summary or {})
        _tamper_first_event("email-broken")

        with mock.patch("django.core.mail.send_mail") as send_mail_mock:
            with self.assertRaises(SystemExit):
                call_command(
                    "verify_audit_chain",
                    "--all-tenants",
                    "--email-on-broken=audit-ops@example.invalid",
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )

            self.assertEqual(send_mail_mock.call_count, 1)
            call_kwargs = send_mail_mock.call_args.kwargs
            recipients = call_kwargs.get("recipient_list") or []
            self.assertIn("audit-ops@example.invalid", recipients)
            body = call_kwargs.get("message") or ""

            # Body MUST surface the tenant hash + count
            self.assertIn(tenant_hash, body)
            self.assertIn("tenants_broken=1", body)
            # Body MUST NOT carry hash bytes (full 64-char digests)
            # nor raw payload values.
            self.assertNotIn(original_integrity, body)
            self.assertNotIn(str(original_payload), body)
            # And MUST NOT carry the raw tenant slug.
            self.assertNotIn("email-broken", body)


# ─── Celery beat task ───────────────────────────────────────────────────


class WeeklyTaskTests(TestCase):

    @override_settings(MIGRATION_CLOUD_AUDIT_OPS_EMAIL="")
    def test_weekly_task_warns_and_runs_when_email_empty(self):
        # 0 tenants → verifier runs cleanly + task returns "clean".
        with self.assertLogs(
            "apps.migration_cloud.tasks_audit", level="WARNING"
        ) as cm:
            result = verify_audit_chain_weekly_task()
        self.assertEqual(result.get("status"), "clean")
        joined = "\n".join(cm.output)
        self.assertIn("MIGRATION_CLOUD_AUDIT_OPS_EMAIL", joined)

    @override_settings(
        MIGRATION_CLOUD_AUDIT_OPS_EMAIL="ops@example.invalid"
    )
    def test_weekly_task_returns_clean_for_clean_tree(self):
        _make_school("weekly-clean")
        _seed_clean_chain("weekly-clean", n=1)
        with mock.patch(
            "apps.migration_cloud.management.commands.verify_audit_chain.send_mail"
        ):
            result = verify_audit_chain_weekly_task()
        self.assertEqual(result.get("status"), "clean")


# ─── Retention purge command ────────────────────────────────────────────


class PurgeCommandTests(TestCase):

    @override_settings(MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN="")
    def test_refuses_when_setting_empty(self):
        out = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command(
                "purge_audit_events_pre_approved",
                "--tenant=purge-tenant",
                "--before=2099-01-01",
                "--counsel-approval-token=anything",
                stdout=out,
            )
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("Counsel approval pending", out.getvalue())

    @override_settings(MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN="real-token-abc")
    def test_refuses_on_wrong_token(self):
        err = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command(
                "purge_audit_events_pre_approved",
                "--tenant=purge-tenant",
                "--before=2099-01-01",
                "--counsel-approval-token=wrong-token",
                stdout=io.StringIO(),
                stderr=err,
            )
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("mismatch", err.getvalue())

    @override_settings(MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN="real-token-abc")
    def test_dry_run_shows_count_and_warning(self):
        _make_school("purge-tenant")
        _seed_clean_chain("purge-tenant", n=3)
        out = io.StringIO()
        # No --apply → dry-run (exit 0)
        call_command(
            "purge_audit_events_pre_approved",
            "--tenant=purge-tenant",
            "--before=2099-01-01",
            "--counsel-approval-token=real-token-abc",
            stdout=out,
        )
        out_str = out.getvalue()
        self.assertIn("rows_eligible=3", out_str)
        self.assertIn("DRY-RUN", out_str)
        self.assertIn("irreversible", out_str)
        # Verify NO rows were deleted.
        tenant_hash = _hash_tenant_slug("purge-tenant")
        remaining = MigrationCloudAuditEvent.objects.filter(  # tenant-isolation-allow: test-readback-by-tenant-hash-post-dry-run
            tenant_id_hash=tenant_hash
        ).count()
        self.assertEqual(remaining, 3)

    @override_settings(MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN="real-token-xyz")
    def test_apply_deletes_rows_and_emits_meta_event(self):
        _make_school("purge-apply-tenant")
        _seed_clean_chain("purge-apply-tenant", n=4)
        out = io.StringIO()
        call_command(
            "purge_audit_events_pre_approved",
            "--tenant=purge-apply-tenant",
            "--before=2099-01-01",
            "--counsel-approval-token=real-token-xyz",
            "--apply",
            stdout=out,
        )
        out_str = out.getvalue()
        self.assertIn("APPLIED", out_str)

        tenant_hash = _hash_tenant_slug("purge-apply-tenant")
        remaining = list(
            MigrationCloudAuditEvent.objects.filter(  # tenant-isolation-allow: test-readback-by-tenant-hash-post-apply
                tenant_id_hash=tenant_hash
            ).order_by("created_at")
        )
        # 4 original rows DELETEd, 1 meta-event written.
        self.assertEqual(len(remaining), 1)
        meta = remaining[0]
        self.assertEqual(
            meta.event_type,
            MigrationCloudAuditEventType.AUDIT_RETENTION_PURGE_APPLIED.value,
        )
        self.assertEqual(meta.payload_summary.get("rows_purged"), 4)
        self.assertIn("approval_fingerprint", meta.payload_summary)
        # The meta-event's approval_fingerprint is a 12-char prefix —
        # NOT the raw token.
        fingerprint = meta.payload_summary["approval_fingerprint"]
        self.assertEqual(len(fingerprint), 12)
        self.assertNotIn("real-token-xyz", fingerprint)

    @override_settings(MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN="meta-chain-token")
    def test_meta_event_chains_into_audit_log(self):
        """The post-purge meta-event becomes a fresh chain head with a
        valid integrity_hash. The next verify_audit_chain run sees it
        and reports the chain as clean."""
        _make_school("meta-chain-tenant")
        _seed_clean_chain("meta-chain-tenant", n=2)
        # Cut everything before a future date so all 2 rows are purged.
        call_command(
            "purge_audit_events_pre_approved",
            "--tenant=meta-chain-tenant",
            "--before=2099-01-01",
            "--counsel-approval-token=meta-chain-token",
            "--apply",
            stdout=io.StringIO(),
        )

        tenant_hash = _hash_tenant_slug("meta-chain-tenant")
        rows = list(
            MigrationCloudAuditEvent.objects.filter(  # tenant-isolation-allow: test-meta-chain-readback-by-tenant-hash
                tenant_id_hash=tenant_hash
            ).order_by("created_at")
        )
        self.assertEqual(len(rows), 1)
        meta = rows[0]
        # The meta-event is a fresh chain head (prev_event_hash == genesis
        # since we DELETEd all prior rows before recording it).
        self.assertEqual(meta.prev_event_hash, GENESIS_SENTINEL)
        # Its integrity_hash must be self-consistent (re-derives identically).
        self.assertEqual(meta.recompute_integrity_hash(), meta.integrity_hash)

        # And the verifier confirms it.
        out = io.StringIO()
        try:
            call_command(
                "verify_audit_chain",
                "--tenant=meta-chain-tenant",
                stdout=out,
            )
            exit_code = 0
        except SystemExit as exc:
            exit_code = exc.code or 0
        self.assertEqual(exit_code, 0)
        self.assertIn("clean", out.getvalue())

    @override_settings(MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN="leak-test-token")
    def test_assertlogs_proves_no_pii_or_secret_leak(self):
        _make_school("leak-tenant")
        _seed_clean_chain("leak-tenant", n=2)

        # Capture all relevant loggers
        with self.assertLogs(level="DEBUG") as cm:
            call_command(
                "purge_audit_events_pre_approved",
                "--tenant=leak-tenant",
                "--before=2099-01-01",
                "--counsel-approval-token=leak-test-token",
                "--apply",
                stdout=io.StringIO(),
            )
        joined = "\n".join(cm.output)
        self.assertNotIn("leak-test-token", joined)
        # Raw tenant slug must not appear in any log line.
        self.assertNotIn("leak-tenant", joined)
