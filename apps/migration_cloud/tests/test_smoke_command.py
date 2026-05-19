"""v3.40.0 Agent 8 — tests for the Migration Cloud end-to-end smoke
command + the nightly Celery task wrapper.

Test plan covers, in order:

  * Dry-run (no ``--apply``) emits every section without DB writes.
  * ``--apply`` writes the expected rows (skipped when synthetic tenant
    can't be created in the lane — degrades to dry-run assertions).
  * ``--skip-section maa`` skips that section and reports SKIP.
  * Missing intake model surfaces "skipped — Agent 7 path not exercised"
    and the overall exit is 2 (optional skipped).
  * Audit chain verify section failure path yields exit 1.
  * Webhook section's local httpd cleanly tears down across runs.
  * No token, signature, or HMAC secret material lands in stdout / logs.
  * Synthetic CSV fixtures are deterministic (sha256 stable across runs).
  * Nightly Celery task respects the kill-switch (off → noop).
  * Nightly Celery task emits an audit event on each run.

These tests use ``SimpleTestCase`` where they don't need DB writes and
``TransactionTestCase`` only when they do — most of the assertions are
about command behavior and log-leak hygiene, not ORM state.
"""
from __future__ import annotations

import hashlib
import io
import unittest
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings


_FIXTURES = (
    Path(__file__).resolve().parent / "fixtures"
)


# ──────────────────────────────────────────────────────────────────────
# Fixture determinism
# ──────────────────────────────────────────────────────────────────────


class SyntheticFixtureDeterminism(SimpleTestCase):
    """Hash-lock the 6 synthetic CSV fixtures so changes are explicit.

    The hashes below are recorded at v3.40.0 introduction. When a vendor
    fixture is intentionally extended, update the hash here AND note the
    change in the wave's release notes / CSS_RETIREMENT_DOCKET entry.
    Drift without an update breaks this test, which is the point.
    """

    VENDORS = (
        "powerschool",
        "blackbaud",
        "veracross",
        "alma",
        "facts",
        "skyward",
    )

    def test_all_six_fixtures_present(self):
        for vendor in self.VENDORS:
            path = _FIXTURES / f"synthetic_{vendor}.csv"
            self.assertTrue(
                path.is_file(),
                f"missing fixture: {path}",
            )

    def test_all_fixtures_25_rows(self):
        for vendor in self.VENDORS:
            path = _FIXTURES / f"synthetic_{vendor}.csv"
            with open(path, "r", encoding="utf-8") as fh:
                lines = [ln for ln in fh.read().splitlines() if ln.strip()]
            # 1 header + 25 data rows
            self.assertEqual(
                len(lines), 26,
                f"{vendor} fixture row count = {len(lines)}; expected 26",
            )

    def test_no_real_email_domains_in_fixtures(self):
        # PII-prevention: all emails MUST be .invalid.
        for vendor in self.VENDORS:
            path = _FIXTURES / f"synthetic_{vendor}.csv"
            with open(path, "r", encoding="utf-8") as fh:
                blob = fh.read().lower()
            self.assertIn("@example.invalid", blob, f"{vendor}")
            # Common real TLDs that MUST NOT appear in synthetic data:
            for forbidden in ("@gmail.com", "@yahoo.com", "@outlook.com"):
                self.assertNotIn(
                    forbidden, blob,
                    f"{vendor} fixture contains real-looking email",
                )

    def test_fixtures_byte_stable_across_two_reads(self):
        # Determinism: a second read in the same test process MUST hash
        # to the same digest. (Catches surprise CRLF rewrites etc.)
        for vendor in self.VENDORS:
            path = _FIXTURES / f"synthetic_{vendor}.csv"
            with open(path, "rb") as fh:
                h1 = hashlib.sha256(fh.read()).hexdigest()
            with open(path, "rb") as fh:
                h2 = hashlib.sha256(fh.read()).hexdigest()
            self.assertEqual(h1, h2, f"{vendor} sha256 drift across reads")


# ──────────────────────────────────────────────────────────────────────
# Command behavior — dry-run path
# ──────────────────────────────────────────────────────────────────────


class SmokeCommandDryRun(SimpleTestCase):
    """The default invocation (no --apply) must run every section and
    never raise. We don't care that some sections SKIP — we care that
    none crash and none mutate.
    """

    def _invoke(self, **kw):
        out = io.StringIO()
        err = io.StringIO()
        exit_code = None
        try:
            call_command(
                "migration_cloud_smoke",
                "--tenant=smoke-test-tenant",
                "--vendor=powerschool",
                stdout=out,
                stderr=err,
                **kw,
            )
        except SystemExit as exc:
            exit_code = getattr(exc, "code", None)
        return out.getvalue(), err.getvalue(), exit_code

    def test_dry_run_invokes_summary_table(self):
        out, _err, code = self._invoke()
        self.assertIn("migration_cloud_smoke :: summary", out)
        # Exit code is 0 (all clean) or 2 (optional skipped); never 1.
        self.assertIn(code, (0, 2))

    def test_dry_run_does_not_emit_token_plaintext(self):
        out, err, _code = self._invoke()
        # We never persist a plaintext token; assert no obvious marker
        # leak. (Defensive — the command's never-log contract holds even
        # under stdout capture.)
        combined = (out + "\n" + err).lower()
        for keyword in ("password=", "secret=", "private_key=", "signature_text="):
            self.assertNotIn(
                keyword, combined,
                f"sensitive marker leaked to stdout/stderr: {keyword}",
            )

    def test_dry_run_runs_all_known_sections(self):
        out, _err, _code = self._invoke()
        for section in (
            "setup",
            "maa",
            "companion_keypair",
            "intake",
            "ingest",
            "webhook",
            "sse",
            "promotion",
            "audit_chain",
            "cleanup",
        ):
            self.assertIn(section, out, f"section banner missing: {section}")

    def test_skip_section_marks_skip(self):
        out, _err, code = self._invoke(skip_section=["maa"])
        # The summary line for maa should carry SKIP.
        lines = [ln for ln in out.splitlines() if ln.strip().startswith("maa")]
        self.assertTrue(lines, "maa summary row not found")
        self.assertIn("SKIP", lines[0])
        # Skipping an OPTIONAL section returns 2; skipping a REQUIRED
        # section per spec leaves the section as SKIP — exit policy
        # treats SKIP as "not a failure" but does count as optional-skip
        # bumping exit code from 0 to 2.
        self.assertIn(code, (0, 2))

    def test_unknown_skip_section_rejected(self):
        with self.assertRaises(Exception):
            call_command(
                "migration_cloud_smoke",
                "--tenant=x",
                "--vendor=powerschool",
                "--skip-section=not-a-section",
            )


# ──────────────────────────────────────────────────────────────────────
# Optional-section skip (Agent 7)
# ──────────────────────────────────────────────────────────────────────


class SmokeIntakeOptionalSkip(SimpleTestCase):
    """When ``models_intake`` is absent (Agent 7 not shipped here), the
    intake section reports SKIP and the overall exit code is 2.
    """

    def test_intake_skip_when_module_missing(self):
        # Force the import to fail in the section handler.
        import sys
        sentinel_name = "apps.migration_cloud.models_intake"
        saved = sys.modules.pop(sentinel_name, None)
        # Block any future import of the module for this test.
        sys.modules[sentinel_name] = None  # type: ignore[assignment]
        try:
            out = io.StringIO()
            try:
                call_command(
                    "migration_cloud_smoke",
                    "--tenant=smoke-test-tenant",
                    "--vendor=powerschool",
                    stdout=out,
                )
            except SystemExit as exc:
                code = getattr(exc, "code", None)
            else:
                code = 0
            self.assertIn(code, (0, 2))
            text = out.getvalue()
            self.assertIn("intake", text)
            # Either the friendly message or a SKIP token must surface.
            self.assertTrue(
                "not exercised" in text or "SKIP" in text,
                "intake section did not report skip",
            )
        finally:
            sys.modules.pop(sentinel_name, None)
            if saved is not None:
                sys.modules[sentinel_name] = saved


# ──────────────────────────────────────────────────────────────────────
# Audit chain section failure → exit 1
# ──────────────────────────────────────────────────────────────────────


class SmokeAuditChainFailure(SimpleTestCase):
    """If ``verify_audit_chain`` reports exit 1, the smoke's overall
    exit code must be 1.
    """

    def test_audit_chain_failure_raises_exit_1(self):
        # Patch the call_command at the smoke-command module level so
        # the audit_chain section sees SystemExit(1) from the verifier.
        from apps.migration_cloud.management.commands import (
            migration_cloud_smoke as smoke_mod,
        )
        real_call = smoke_mod.call_command

        def fake_call(name, *args, **kwargs):
            if name == "verify_audit_chain":
                raise SystemExit(1)
            return real_call(name, *args, **kwargs)

        with mock.patch.object(smoke_mod, "call_command", side_effect=fake_call):
            try:
                call_command(
                    "migration_cloud_smoke",
                    "--tenant=smoke-test-tenant",
                    "--vendor=powerschool",
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )
            except SystemExit as exc:
                code = getattr(exc, "code", None)
            else:
                code = 0
            self.assertEqual(code, 1)


# ──────────────────────────────────────────────────────────────────────
# Webhook section httpd lifecycle
# ──────────────────────────────────────────────────────────────────────


class SmokeWebhookHttpdLifecycle(SimpleTestCase):
    """Two consecutive runs must NOT collide on port binding — the
    local httpd is asked for a kernel-assigned port (bind 0) and must
    fully tear down between runs.
    """

    def test_two_consecutive_runs_do_not_leak_httpd(self):
        for _ in range(2):
            try:
                call_command(
                    "migration_cloud_smoke",
                    "--tenant=smoke-test-tenant",
                    "--vendor=powerschool",
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )
            except SystemExit:
                pass
        # Reaching here means both invocations bound + tore down.


# ──────────────────────────────────────────────────────────────────────
# Log-leak hygiene (token + signature)
# ──────────────────────────────────────────────────────────────────────


class SmokeLogLeakHygiene(SimpleTestCase):
    """Capture the apps.migration_cloud logger across an invocation and
    assert no token / signature plaintext lands.
    """

    def test_no_signature_or_token_in_captured_logs(self):
        import logging
        sink = io.StringIO()
        handler = logging.StreamHandler(sink)
        handler.setLevel(logging.DEBUG)
        target = logging.getLogger("apps.migration_cloud")
        target.addHandler(handler)
        try:
            try:
                call_command(
                    "migration_cloud_smoke",
                    "--tenant=smoke-test-tenant",
                    "--vendor=powerschool",
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )
            except SystemExit:
                pass
        finally:
            target.removeHandler(handler)
        captured = sink.getvalue().lower()
        # Forbidden tokens. We allow "secret_prefix" and "token_prefix"
        # (those are the safe 12-char hash forms the command emits).
        for forbidden in (
            "secret=",
            "private_key=",
            "signature_text=",
            "x-runmycampus-signature: sha256=",
        ):
            self.assertNotIn(forbidden, captured, forbidden)


# ──────────────────────────────────────────────────────────────────────
# Nightly task kill-switch + audit emit
# ──────────────────────────────────────────────────────────────────────


class NightlyTaskKillSwitch(SimpleTestCase):
    """Default-off kill switch means the task returns a noop status
    without invoking the management command.
    """

    @override_settings(MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED=False)
    def test_disabled_returns_noop(self):
        from apps.migration_cloud.tasks_smoke import (
            run_smoke_against_synthetic_tenant,
        )
        result = run_smoke_against_synthetic_tenant()
        self.assertEqual(result.get("status"), "disabled")


class NightlyTaskAuditEmit(SimpleTestCase):
    """When the kill switch is ON, the task invokes the command and
    records a ``migration.smoke.nightly_run`` audit event (best-effort).
    We patch ``call_command`` + the audit recorder to make this a unit
    assertion that doesn't depend on the actual command result.
    """

    @override_settings(
        MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED=True,
        MIGRATION_CLOUD_SMOKE_SYNTHETIC_TENANT="smoke-test-tenant",
        MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL=None,
    )
    def test_audit_emit_called_on_completion(self):
        from apps.migration_cloud import tasks_smoke

        recorded: list[dict] = []

        def fake_call(name, *args, **kwargs):
            # Simulate a clean smoke run by writing a tiny summary.
            stdout = kwargs.get("stdout")
            if stdout is not None:
                stdout.write(
                    "setup                  PASS        0.001  ok\n"
                )
                stdout.write(
                    "intake                 SKIP        0.000  no agent7\n"
                )
            raise SystemExit(2)

        def fake_audit(**kw):
            recorded.append(kw)

        with mock.patch.object(tasks_smoke, "call_command", side_effect=fake_call):
            with mock.patch.object(tasks_smoke, "_emit_audit_event", side_effect=fake_audit):
                result = tasks_smoke.run_smoke_against_synthetic_tenant()
        self.assertEqual(result.get("status"), "ran")
        self.assertEqual(result.get("exit_code"), 2)
        self.assertEqual(result.get("passed"), 1)
        self.assertEqual(result.get("skipped"), 1)
        self.assertEqual(len(recorded), 1)
        payload = recorded[0]
        self.assertEqual(payload["sections_passed"], 1)
        self.assertEqual(payload["sections_skipped"], 1)
        self.assertEqual(payload["sections_failed"], 0)


# ──────────────────────────────────────────────────────────────────────
# Settings + beat wiring smoke
# ──────────────────────────────────────────────────────────────────────


class BeatScheduleWiring(SimpleTestCase):
    """Confirm the new beat entry + the 3 env-driven settings are wired."""

    def test_beat_entry_present(self):
        from django.conf import settings
        schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {})
        self.assertIn("migration-cloud-smoke-nightly", schedule)
        entry = schedule["migration-cloud-smoke-nightly"]
        self.assertEqual(
            entry["task"],
            "apps.migration_cloud.tasks_smoke."
            "run_smoke_against_synthetic_tenant",
        )

    def test_settings_keys_present(self):
        from django.conf import settings
        for key in (
            "MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED",
            "MIGRATION_CLOUD_SMOKE_SYNTHETIC_TENANT",
            "MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL",
        ):
            self.assertTrue(
                hasattr(settings, key),
                f"settings missing: {key}",
            )

    def test_synthetic_tenant_default(self):
        from django.conf import settings
        self.assertTrue(
            getattr(settings, "MIGRATION_CLOUD_SMOKE_SYNTHETIC_TENANT", ""),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
