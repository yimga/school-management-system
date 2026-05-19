"""v3.40.0 Agent 14 — tests for ``migration_cloud_smoke_multi``.

Covers CLI guard rails, parallel execution, fail-fast behavior, and the
aggregate audit event emission. The smoke command itself is monkey-
patched at ``call_command`` so the tests are fast + deterministic and
don't depend on the synthetic-tenant fixture machinery (which is
exercised by ``test_smoke_command.py``).
"""
from __future__ import annotations

import io
import threading
import time
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings


def _fake_call_command_pass(*args, **kwargs):
    """Stand-in that prints a fake-PASS summary then exits 0."""
    out = kwargs.get("stdout")
    if out is not None:
        out.write(
            "section1                PASS         0.001  ok\n"
            "section2                PASS         0.002  ok\n"
        )
    # Simulate the smoke command's sys.exit(0).
    raise SystemExit(0)


def _fake_call_command_fail(*args, **kwargs):
    out = kwargs.get("stdout")
    if out is not None:
        out.write(
            "section1                FAIL         0.001  bad\n"
            "section2                PASS         0.002  ok\n"
        )
    raise SystemExit(1)


def _fake_call_command_skip(*args, **kwargs):
    out = kwargs.get("stdout")
    if out is not None:
        out.write(
            "section1                SKIP         0.001  optional\n"
            "section2                PASS         0.002  ok\n"
        )
    raise SystemExit(2)


def _fake_call_command_per_tenant(stdout_map):
    """Factory: return a stub whose behavior depends on the --tenant flag."""
    def stub(*args, **kwargs):
        tenant = ""
        for arg in args:
            if isinstance(arg, str) and arg.startswith("--tenant="):
                tenant = arg.split("=", 1)[1]
        action = stdout_map.get(tenant, "pass")
        out = kwargs.get("stdout")
        if action == "fail":
            if out is not None:
                out.write("s1 FAIL 0.001 boom\n")
            raise SystemExit(1)
        elif action == "skip":
            if out is not None:
                out.write("s1 SKIP 0.001 opt\n")
            raise SystemExit(2)
        else:
            if out is not None:
                out.write("s1 PASS 0.001 ok\n")
            raise SystemExit(0)
    return stub


@override_settings(DEBUG=True)
class MultiTenantSmokeCommandTests(TestCase):

    def test_concurrency_cap_above_16_is_refused(self):
        with self.assertRaises(CommandError) as cm:
            call_command(
                "migration_cloud_smoke_multi",
                "--tenants=a,b",
                "--vendor=powerschool",
                "--concurrency=17",
            )
        self.assertIn("hard cap", str(cm.exception))

    def test_concurrency_cap_at_16_is_allowed(self):
        # Stub the inner call_command so the test stays fast.
        with mock.patch(
            "apps.migration_cloud.management.commands."
            "migration_cloud_smoke_multi.call_command",
            side_effect=_fake_call_command_pass,
        ):
            with self.assertRaises(SystemExit) as cm:
                call_command(
                    "migration_cloud_smoke_multi",
                    "--tenants=a,b",
                    "--vendor=powerschool",
                    "--concurrency=16",
                    stdout=io.StringIO(),
                )
            self.assertEqual(cm.exception.code, 0)

    def test_concurrency_zero_is_refused(self):
        with self.assertRaises(CommandError):
            call_command(
                "migration_cloud_smoke_multi",
                "--tenants=a,b",
                "--vendor=powerschool",
                "--concurrency=0",
            )

    def test_two_tenant_parallel_run_table_has_two_rows(self):
        out = io.StringIO()
        with mock.patch(
            "apps.migration_cloud.management.commands."
            "migration_cloud_smoke_multi.call_command",
            side_effect=_fake_call_command_pass,
        ):
            with self.assertRaises(SystemExit) as cm:
                call_command(
                    "migration_cloud_smoke_multi",
                    "--tenants=alpha,beta",
                    "--vendor=powerschool",
                    "--concurrency=2",
                    stdout=out,
                )
        self.assertEqual(cm.exception.code, 0)
        rendered = out.getvalue()
        # Two distinct tenant-hash lines should appear.
        self.assertEqual(rendered.count("PASS"), 2)

    def test_concurrency_one_is_sequential(self):
        # No assertion on order — just that it doesn't break with N=1.
        out = io.StringIO()
        with mock.patch(
            "apps.migration_cloud.management.commands."
            "migration_cloud_smoke_multi.call_command",
            side_effect=_fake_call_command_pass,
        ):
            with self.assertRaises(SystemExit) as cm:
                call_command(
                    "migration_cloud_smoke_multi",
                    "--tenants=alpha,beta,gamma",
                    "--vendor=powerschool",
                    "--concurrency=1",
                    stdout=out,
                )
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(out.getvalue().count("PASS"), 3)

    def test_exit_code_1_when_any_failed(self):
        with mock.patch(
            "apps.migration_cloud.management.commands."
            "migration_cloud_smoke_multi.call_command",
            side_effect=_fake_call_command_per_tenant({
                "alpha": "pass",
                "beta": "fail",
            }),
        ):
            with self.assertRaises(SystemExit) as cm:
                call_command(
                    "migration_cloud_smoke_multi",
                    "--tenants=alpha,beta",
                    "--vendor=powerschool",
                    "--concurrency=2",
                    stdout=io.StringIO(),
                )
        self.assertEqual(cm.exception.code, 1)

    def test_exit_code_2_when_only_skipped(self):
        with mock.patch(
            "apps.migration_cloud.management.commands."
            "migration_cloud_smoke_multi.call_command",
            side_effect=_fake_call_command_per_tenant({
                "alpha": "pass",
                "beta": "skip",
            }),
        ):
            with self.assertRaises(SystemExit) as cm:
                call_command(
                    "migration_cloud_smoke_multi",
                    "--tenants=alpha,beta",
                    "--vendor=powerschool",
                    "--concurrency=2",
                    stdout=io.StringIO(),
                )
        self.assertEqual(cm.exception.code, 2)

    def test_fail_fast_cancels_in_flight(self):
        # Use a slow stub for second tenant, fast fail for first.
        started_event = threading.Event()
        def stub(*args, **kwargs):
            tenant = ""
            for arg in args:
                if isinstance(arg, str) and arg.startswith("--tenant="):
                    tenant = arg.split("=", 1)[1]
            out = kwargs.get("stdout")
            if tenant == "fail-first":
                if out is not None:
                    out.write("s1 FAIL 0.001 boom\n")
                started_event.set()
                raise SystemExit(1)
            # Slow-running tenant.
            started_event.wait(timeout=2.0)
            time.sleep(0.5)
            if out is not None:
                out.write("s1 PASS 0.001 ok\n")
            raise SystemExit(0)
        with mock.patch(
            "apps.migration_cloud.management.commands."
            "migration_cloud_smoke_multi.call_command",
            side_effect=stub,
        ):
            with self.assertRaises(SystemExit) as cm:
                call_command(
                    "migration_cloud_smoke_multi",
                    "--tenants=fail-first,slow1,slow2,slow3",
                    "--vendor=powerschool",
                    "--concurrency=4",
                    "--fail-fast",
                    stdout=io.StringIO(),
                )
        self.assertEqual(cm.exception.code, 1)

    def test_aggregate_audit_event_emitted(self):
        # Capture audit-record calls.
        captured: list[dict] = []
        from apps.migration_cloud.models_audit import AuditEventManager


        def fake_record(self, tenant_slug, event_type, **kwargs):
            captured.append({
                "tenant_slug": tenant_slug,
                "event_type": event_type,
                "payload": kwargs.get("payload_summary") or {},
            })
            class _Stub:
                pk = 1
            return _Stub()

        with mock.patch.object(AuditEventManager, "record", fake_record):
            with mock.patch(
                "apps.migration_cloud.management.commands."
                "migration_cloud_smoke_multi.call_command",
                side_effect=_fake_call_command_pass,
            ):
                with self.assertRaises(SystemExit):
                    call_command(
                        "migration_cloud_smoke_multi",
                        "--tenants=a,b",
                        "--vendor=powerschool",
                        "--concurrency=2",
                        stdout=io.StringIO(),
                    )

        aggregate = [
            c for c in captured
            if c["event_type"] in (
                "migration.smoke.multi_run_completed", "key.rotate",
            )
            and c["payload"].get("tenants_passed") is not None
        ]
        self.assertEqual(len(aggregate), 1)
        agg_payload = aggregate[0]["payload"]
        self.assertEqual(agg_payload["tenants_passed"], 2)
        self.assertEqual(agg_payload["tenants_failed"], 0)
        self.assertEqual(agg_payload["tenants_skipped"], 0)

    def test_per_tenant_audit_events_emitted(self):
        captured: list[dict] = []
        from apps.migration_cloud.models_audit import AuditEventManager

        def fake_record(self, tenant_slug, event_type, **kwargs):
            captured.append({
                "tenant_slug": tenant_slug,
                "event_type": event_type,
            })
            class _Stub:
                pk = 1
            return _Stub()

        with mock.patch.object(AuditEventManager, "record", fake_record):
            with mock.patch(
                "apps.migration_cloud.management.commands."
                "migration_cloud_smoke_multi.call_command",
                side_effect=_fake_call_command_pass,
            ):
                with self.assertRaises(SystemExit):
                    call_command(
                        "migration_cloud_smoke_multi",
                        "--tenants=a,b,c",
                        "--vendor=powerschool",
                        "--concurrency=3",
                        stdout=io.StringIO(),
                    )

        per_tenant_events = [
            c for c in captured if c["tenant_slug"] in ("a", "b", "c")
        ]
        self.assertEqual(len(per_tenant_events), 3)


@override_settings(DEBUG=False, ALLOWED_HOSTS=["runmycampus.com"])
class ProdGateTests(TestCase):

    def test_prod_gate_refuses_apply(self):
        # Pretend ALLOW_PROD is unset.
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("MIGRATION_CLOUD_SMOKE_ALLOW_PROD", None)
            with self.assertRaises(CommandError) as cm:
                call_command(
                    "migration_cloud_smoke_multi",
                    "--tenants=a",
                    "--vendor=powerschool",
                    "--apply",
                )
        self.assertIn("LIVE PROD", str(cm.exception))

    def test_prod_gate_skips_when_apply_not_set(self):
        # No --apply → gate is bypassed.
        with mock.patch(
            "apps.migration_cloud.management.commands."
            "migration_cloud_smoke_multi.call_command",
            side_effect=_fake_call_command_pass,
        ):
            with self.assertRaises(SystemExit) as cm:
                call_command(
                    "migration_cloud_smoke_multi",
                    "--tenants=a",
                    "--vendor=powerschool",
                    stdout=io.StringIO(),
                )
            self.assertEqual(cm.exception.code, 0)
