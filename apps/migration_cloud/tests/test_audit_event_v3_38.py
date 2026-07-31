"""v3.38.0 Agent 5 — Migration Cloud tamper-evident audit event tests.

Coverage matrix (~20 tests):

  Model
  -----
  * create succeeds + hash + chain genesis
  * second save raises ReadOnly
  * delete raises ReadOnly
  * integrity_hash deterministic for same inputs
  * chain links correctly (event_2.prev_event_hash == event_1.integrity_hash)
  * _sanitize_payload rejects sensitive keys
    (password / signature_text / private_key / email / slug)
  * _sanitize_payload allows byte_count int
  * payload_summary None is coerced to {}

  Manager
  -------
  * record() writes the row with computed hash
  * second record() for same tenant chains to first
  * record() validates event_type
  * threaded concurrent record() preserves chain integrity

  View
  ----
  * audit dashboard 200 for staff
  * audit dashboard 403 for anonymous + 403 for non-staff
  * audit dashboard hides raw email / slug (no payload key 'email' or 'slug')

  Export
  ------
  * 200 for staff with valid params
  * Content-Type is application/x-ndjson
  * each line parseable JSON
  * ?verify_chain=1 adds _chain_verified key

  Management command
  ------------------
  * verify_audit_chain on clean chain returns 0
  * verify_audit_chain on tampered row (via raw SQL UPDATE) returns 1

  assertLogs
  ----------
  * no PII / secret material in any log line
"""
from __future__ import annotations

import io
import json
import logging
import threading
import time

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import OperationalError, connection
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.migration_cloud.models_audit import (
    GENESIS_SENTINEL,
    MigrationCloudAuditEvent,
    MigrationCloudAuditEventReadOnlyError,
    MigrationCloudAuditEventType,
    _compute_integrity_hash,
    _hash_email_or_id,
    _hash_tenant_slug,
    _sanitize_payload,
)


User = get_user_model()


def _make_staff() -> User:
    return User.objects.create_superuser(
        username="audit-staff-v338",
        email="staff-v338@example.invalid",
        password="x",
    )


def _make_nonstaff() -> User:
    return User.objects.create_user(
        username="audit-nonstaff-v338",
        email="nonstaff-v338@example.invalid",
        password="x",
        is_staff=False,
    )


# ─── Model layer ─────────────────────────────────────────────────────────


class AuditEventModelTests(TestCase):

    def test_create_succeeds_with_genesis_chain(self):
        ev = MigrationCloudAuditEvent.objects.record(
            "tenant-alpha",
            MigrationCloudAuditEventType.COMPANION_UPLOAD,
            payload_summary={"byte_count": 1024, "scheme": "x25519"},
        )
        self.assertIsNotNone(ev.pk)
        self.assertEqual(ev.prev_event_hash, GENESIS_SENTINEL)
        self.assertEqual(len(ev.integrity_hash), 64)
        self.assertEqual(ev.tenant_id_hash, _hash_tenant_slug("tenant-alpha"))
        self.assertTrue(ev.created_at_iso)

    def test_second_save_raises_readonly(self):
        ev = MigrationCloudAuditEvent.objects.record(
            "tenant-beta",
            MigrationCloudAuditEventType.MAA_SIGN,
            payload_summary={"vendor_source": "powerschool"},
        )
        ev.event_type = MigrationCloudAuditEventType.TOKEN_MINT
        with self.assertRaises(MigrationCloudAuditEventReadOnlyError):
            ev.save()

    def test_delete_raises_readonly(self):
        ev = MigrationCloudAuditEvent.objects.record(
            "tenant-gamma",
            MigrationCloudAuditEventType.TOKEN_MINT,
            payload_summary={"scopes_count": 3},
        )
        with self.assertRaises(MigrationCloudAuditEventReadOnlyError):
            ev.delete()

    def test_integrity_hash_deterministic(self):
        # Same inputs to _compute_integrity_hash must produce the same
        # output byte-for-byte (the chain property depends on this).
        pk = "00000000-0000-0000-0000-000000000001"
        h1 = _compute_integrity_hash(
            pk=pk,
            tenant_id_hash="abcdef012345",
            event_type="token.mint",
            actor_id="aa" * 32,
            event_subject_hash="bb" * 32,
            payload_summary={"a": 1, "b": [2, 3]},
            created_at_iso="2026-05-19T00:00:00+00:00",
            prev_event_hash=GENESIS_SENTINEL,
        )
        h2 = _compute_integrity_hash(
            pk=pk,
            tenant_id_hash="abcdef012345",
            event_type="token.mint",
            actor_id="aa" * 32,
            event_subject_hash="bb" * 32,
            payload_summary={"a": 1, "b": [2, 3]},
            created_at_iso="2026-05-19T00:00:00+00:00",
            prev_event_hash=GENESIS_SENTINEL,
        )
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_chain_links_per_tenant(self):
        a = MigrationCloudAuditEvent.objects.record(
            "tenant-chain",
            MigrationCloudAuditEventType.COMPANION_UPLOAD,
            payload_summary={"byte_count": 100},
        )
        b = MigrationCloudAuditEvent.objects.record(
            "tenant-chain",
            MigrationCloudAuditEventType.MAA_SIGN,
            payload_summary={"vendor_source": "blackbaud"},
        )
        self.assertEqual(b.prev_event_hash, a.integrity_hash)
        self.assertNotEqual(a.integrity_hash, b.integrity_hash)

    def test_chains_independent_across_tenants(self):
        a = MigrationCloudAuditEvent.objects.record(
            "tenant-iso-a",
            MigrationCloudAuditEventType.TOKEN_MINT,
            payload_summary={},
        )
        b = MigrationCloudAuditEvent.objects.record(
            "tenant-iso-b",
            MigrationCloudAuditEventType.TOKEN_MINT,
            payload_summary={},
        )
        self.assertEqual(a.prev_event_hash, GENESIS_SENTINEL)
        self.assertEqual(b.prev_event_hash, GENESIS_SENTINEL)

    def test_sanitize_payload_rejects_sensitive_keys(self):
        for k in ("password", "signature_text", "private_key", "email", "slug"):
            with self.assertRaises(ValueError):
                _sanitize_payload({k: "anything"})

    def test_sanitize_payload_rejects_nested_sensitive_keys(self):
        with self.assertRaises(ValueError):
            _sanitize_payload({"outer": {"inner": {"password": "x"}}})

    def test_sanitize_payload_allows_byte_count_int(self):
        out = _sanitize_payload({"byte_count": 1024, "scheme": "x25519"})
        self.assertEqual(out["byte_count"], 1024)

    def test_sanitize_payload_none_coerces_to_dict(self):
        self.assertEqual(_sanitize_payload(None), {})


# ─── Manager layer ───────────────────────────────────────────────────────


class AuditEventManagerTests(TestCase):

    def test_record_persists_with_chain(self):
        ev = MigrationCloudAuditEvent.objects.record(
            "tenant-mgr-1",
            "key.rotate",
            payload_summary={"old_version": "v1", "new_version": "v2"},
        )
        self.assertIsNotNone(ev.pk)
        self.assertEqual(ev.event_type, "key.rotate")
        self.assertEqual(ev.prev_event_hash, GENESIS_SENTINEL)

    def test_record_invalid_event_type_raises(self):
        with self.assertRaises(ValueError):
            MigrationCloudAuditEvent.objects.record(
                "tenant-mgr-2",
                "not.a.real.event",
                payload_summary={},
            )

    def test_record_actor_email_is_hashed(self):
        user = _make_staff()
        ev = MigrationCloudAuditEvent.objects.record(
            "tenant-mgr-3",
            "maa.sign",
            actor=user,
            subject="maa-pk-42",
            payload_summary={"vendor_source": "veracross"},
        )
        # actor_id is a hex prefix of sha256(email), NOT the email.
        self.assertIsNotNone(ev.actor_id)
        self.assertNotIn("@", ev.actor_id)
        self.assertEqual(
            ev.actor_id,
            _hash_email_or_id(user.email),
        )

    def test_concurrent_records_chain_eventually(self):
        """Threaded record() preserves chain self-consistency.

        SQLite under TestCase doesn't expose real concurrency, but the
        smoke test verifies the manager's transaction.atomic() block
        doesn't raise and the resulting rows all chain validly when
        replayed in created_at order.
        """
        results = []
        errors = []

        def _worker(i):
            for attempt in range(5):
                try:
                    ev = MigrationCloudAuditEvent.objects.record(
                        "tenant-concurrent",
                        "token.mint",
                        payload_summary={"i": i},
                    )
                    results.append(ev.pk)
                    return
                except OperationalError as exc:
                    if (
                        connection.vendor == "sqlite"
                        and "database is locked" in str(exc).lower()
                        and attempt < 4
                    ):
                        time.sleep(0.05 * (attempt + 1))
                        continue
                    errors.append(exc)
                    return
                except Exception as exc:  # broad-by-design test capture
                    errors.append(exc)
                    return

        threads = [
            threading.Thread(target=_worker, args=(i,)) for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 5)
        # Re-walk and assert chain consistency: each event's
        # prev_event_hash matches the prior event's integrity_hash.
        chain = list(
            MigrationCloudAuditEvent.objects
            .filter(tenant_id_hash=_hash_tenant_slug("tenant-concurrent"))
            .order_by("created_at")
        )
        prev = GENESIS_SENTINEL
        for ev in chain:
            self.assertEqual(ev.prev_event_hash, prev)
            self.assertEqual(ev.recompute_integrity_hash(), ev.integrity_hash)
            prev = ev.integrity_hash


# ─── View layer ──────────────────────────────────────────────────────────


class AuditViewAccessTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.staff = _make_staff()
        cls.nonstaff = _make_nonstaff()
        # Seed a few rows.
        for i in range(3):
            MigrationCloudAuditEvent.objects.record(
                "tenant-view-1",
                "token.mint",
                payload_summary={"i": i},
            )

    def _audit_url(self) -> str:
        return reverse("migration_cloud_super:audit_dashboard")

    def test_anonymous_redirects_or_403(self):
        client = Client()
        resp = client.get(self._audit_url())
        # staff_member_required redirects anonymous to admin login.
        self.assertIn(resp.status_code, (302, 403))

    def test_nonstaff_redirects_or_403(self):
        client = Client()
        client.force_login(self.nonstaff)
        resp = client.get(self._audit_url())
        self.assertIn(resp.status_code, (302, 403))

    def test_staff_200(self):
        from apps.migration_cloud.views_audit_admin import MigrationCloudAuditView

        request = RequestFactory().get(self._audit_url(), secure=True)
        request.user = self.staff
        resp = MigrationCloudAuditView.as_view()(request)
        self.assertEqual(resp.status_code, 200)

    def test_response_hides_raw_email_and_slug_keys(self):
        import re

        from apps.migration_cloud.views_audit_admin import MigrationCloudAuditView

        request = RequestFactory().get(self._audit_url(), secure=True)
        request.user = self.staff
        resp = MigrationCloudAuditView.as_view()(request)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        # Scope the leak check to the audit PAYLOAD cells. The payload column
        # re-sanitizes and any payload carrying a literal 'email'/'slug'/
        # 'tenant_slug' key is rejected at write time, so a sensitive key can
        # never render here. A whole-body substring check false-positives on
        # the surrounding operator shell, which legitimately carries an
        # "email" newsletter field (_newsletter_band.html) — chrome, not a
        # data leak.
        payload_cells = re.findall(
            r'<pre class="rmc-pre rmc-pre--audit-payload">(.*?)</pre>',
            body, re.DOTALL,
        )
        self.assertTrue(payload_cells, "expected rendered audit payload cells")
        joined = "\n".join(payload_cells)
        self.assertNotIn('"email"', joined)
        self.assertNotIn('"slug"', joined)
        self.assertNotIn('"tenant_slug"', joined)


# ─── Export layer ────────────────────────────────────────────────────────


class AuditExportTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.staff = _make_staff()
        for i in range(4):
            MigrationCloudAuditEvent.objects.record(
                "tenant-export",
                "companion.upload",
                payload_summary={"byte_count": 100 + i},
            )

    def _export_url(self) -> str:
        return reverse("migration_cloud_super:audit_export")

    def test_staff_200_content_type(self):
        from apps.migration_cloud.views_audit_admin import MigrationCloudAuditExportView

        request = RequestFactory().get(self._export_url(), secure=True)
        request.user = self.staff
        resp = MigrationCloudAuditExportView.as_view()(request)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/x-ndjson")

    def test_each_line_is_valid_json(self):
        from apps.migration_cloud.views_audit_admin import MigrationCloudAuditExportView

        request = RequestFactory().get(
            self._export_url(),
            data={"tenant": _hash_tenant_slug("tenant-export")[:8]},
            secure=True,
        )
        request.user = self.staff
        resp = MigrationCloudAuditExportView.as_view()(request)
        body = b"".join(resp.streaming_content).decode("utf-8")
        lines = [line for line in body.splitlines() if line.strip()]
        self.assertEqual(len(lines), 4)
        for line in lines:
            obj = json.loads(line)
            self.assertIn("integrity_hash", obj)
            self.assertIn("tenant_id_hash", obj)

    def test_verify_chain_flag_adds_field(self):
        from apps.migration_cloud.views_audit_admin import MigrationCloudAuditExportView

        request = RequestFactory().get(
            self._export_url(),
            data={
                "tenant": _hash_tenant_slug("tenant-export")[:8],
                "verify_chain": "1",
            },
            secure=True,
        )
        request.user = self.staff
        resp = MigrationCloudAuditExportView.as_view()(request)
        body = b"".join(resp.streaming_content).decode("utf-8")
        lines = [line for line in body.splitlines() if line.strip()]
        for line in lines:
            obj = json.loads(line)
            self.assertIn("_chain_verified", obj)
            self.assertIs(obj["_chain_verified"], True)


# ─── Management command ─────────────────────────────────────────────────


class VerifyAuditChainCommandTests(TestCase):

    def test_clean_chain_exit_0(self):
        for i in range(3):
            MigrationCloudAuditEvent.objects.record(
                "tenant-verify-clean",
                "token.mint",
                payload_summary={"i": i},
            )
        out = io.StringIO()
        # call_command swallows SystemExit when no broken rows.
        call_command(
            "verify_audit_chain",
            tenant="tenant-verify-clean",
            stdout=out,
        )
        self.assertIn("clean", out.getvalue())

    def test_tampered_chain_exit_1(self):
        a = MigrationCloudAuditEvent.objects.record(
            "tenant-verify-tampered",
            "token.mint",
            payload_summary={"i": 1},
        )
        MigrationCloudAuditEvent.objects.record(
            "tenant-verify-tampered",
            "token.mint",
            payload_summary={"i": 2},
        )
        # Tamper via raw SQL — bypasses save() guard.
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE migration_cloud_migrationcloudauditevent "
                "SET payload_summary='{\"i\":999}' WHERE id=%s",
                [a.id.hex],
            )

        err = io.StringIO()
        out = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            call_command(
                "verify_audit_chain",
                tenant="tenant-verify-tampered",
                stdout=out,
                stderr=err,
            )
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("BROKEN", err.getvalue())


# ─── Logging hygiene ────────────────────────────────────────────────────


class AuditLoggingHygieneTests(TestCase):

    def test_no_secret_material_in_logs(self):
        secret_marker = "SUPER_SECRET_PASSWORD_DONT_LOG"
        with self.assertLogs("apps.migration_cloud", level="DEBUG") as cap:
            # Try to write a payload with a sensitive key — this MUST
            # raise BEFORE any DB write or log emission of the value.
            with self.assertRaises(ValueError):
                MigrationCloudAuditEvent.objects.record(
                    "tenant-log-hygiene",
                    "maa.sign",
                    payload_summary={"password": secret_marker},
                )
            # And a clean record() that should emit no secrets.
            MigrationCloudAuditEvent.objects.record(
                "tenant-log-hygiene",
                "token.mint",
                payload_summary={"scopes_count": 1},
            )
            # Force at least one log to flush.
            logging.getLogger("apps.migration_cloud").info(
                "audit_test_marker"
            )
        for line in cap.output:
            self.assertNotIn(secret_marker, line)
            self.assertNotIn("private_key", line.lower())
            self.assertNotIn("signature_text", line.lower())
