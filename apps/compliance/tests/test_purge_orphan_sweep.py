"""SimpleTestCase coverage for the tenant-purge orphan sweep (no DB).

The full delete path is DB-backed (TestCase) and runs in CI; here we validate
the introspection + value-matching + Redis-key logic that drives it.
"""
from __future__ import annotations

import hashlib
import uuid
from unittest import mock

from django.test import SimpleTestCase, override_settings


class ScalarOrphanIntrospectionTests(SimpleTestCase):
    def test_iter_finds_bare_school_id_columns(self):
        from apps.compliance.tenant_offboarding_inventory import (
            iter_school_scalar_id_targets,
        )

        targets = list(iter_school_scalar_id_targets())
        labels = {m._meta.label_lower for m, _f in targets}
        # Every target's swept field is named school_id (never a FK attname).
        self.assertTrue(all(f == "school_id" for _m, f in targets))
        # The known orphan-bearing model (bare school_id UUID) must be covered.
        self.assertIn("events.domainevent", labels)

    def test_match_value_uses_uuid_or_str_by_field_type(self):
        from apps.compliance.tenant_offboarding_inventory import (
            _scalar_school_match_value,
            iter_school_scalar_id_targets,
        )

        pk = uuid.uuid4()
        seen_uuid = seen_char = False
        for model, field_name in iter_school_scalar_id_targets():
            val = _scalar_school_match_value(model, field_name, pk)
            internal = model._meta.get_field(field_name).get_internal_type()
            if internal == "UUIDField":
                self.assertEqual(val, pk)
                seen_uuid = True
            else:
                self.assertEqual(val, str(pk))
                seen_char = True
        # The codebase has both UUID and Char scalar school_id columns.
        self.assertTrue(seen_uuid)
        self.assertTrue(seen_char)


class WalStreamPurgeKeyTests(SimpleTestCase):
    @override_settings(REDIS_URL="redis://localhost:6379/0")
    def test_purge_streams_deletes_all_tenant_wal_keys(self):
        import redis as redis_mod

        from apps.wal_stream.tasks import purge_streams_for_school

        pk = uuid.uuid4()
        expected = hashlib.sha256(str(pk).encode("utf-8")).hexdigest()[:12]
        client = mock.MagicMock()
        client.delete.return_value = 4
        with mock.patch.object(redis_mod.Redis, "from_url", return_value=client):
            out = purge_streams_for_school(pk)
        self.assertEqual(out.get("tenant_hash"), expected)
        called_keys = set(client.delete.call_args[0])
        # All SIX tenant WAL keys. conflict/ and lock/ were added to the purge
        # after this test was written and are genuinely written by
        # apps/wal_stream/tasks.py -- leaving them behind would leave tenant
        # residue in Redis after an erasure, so the purge growing is correct and
        # the assertion is what had gone stale. Enumerated rather than derived
        # from the implementation, so a key being DROPPED still fails here.
        self.assertEqual(
            called_keys,
            {
                f"rmc.wal.{expected}",
                f"rmc.wal.dedupe.{expected}",
                f"rmc.wal.attempts.{expected}",
                f"rmc.wal.deadletter.{expected}",
                f"rmc.wal.conflict.{expected}",
                f"rmc.wal.lock.{expected}",
            },
        )
        # The invariant that actually matters: a purge for one school must never
        # name a key that is not scoped to that school's tenant hash.
        for key in called_keys:
            self.assertTrue(key.endswith(expected), key)

    @override_settings(REDIS_URL="")
    def test_purge_streams_no_redis_url_is_safe_noop(self):
        from apps.wal_stream.tasks import purge_streams_for_school

        out = purge_streams_for_school(uuid.uuid4())
        self.assertEqual(out.get("deleted"), 0)


class SubscriptionOffboardCancelTests(SimpleTestCase):
    def test_marks_canceled_and_captures_external_ref_for_reconciliation(self):
        from apps.billing.models import TenantSubscription
        from apps.billing.offboarding import cancel_subscriptions_for_offboarding

        fake_sub = mock.MagicMock()
        fake_sub.external_subscription_ref = "sub_ext_123"
        fake_sub.status = TenantSubscription.Status.ACTIVE
        school = mock.MagicMock(pk=uuid.uuid4())
        qs = mock.MagicMock()
        qs.exclude.return_value = [fake_sub]
        with mock.patch.object(TenantSubscription.objects, "filter", return_value=qs):
            out = cancel_subscriptions_for_offboarding(school)

        self.assertEqual(out["canceled"], 1)
        self.assertIn("sub_ext_123", out["external_refs"])
        # No live provider client wired -> recorded as pending for reconciliation.
        self.assertIn("sub_ext_123", out["remote_pending"])
        self.assertEqual(fake_sub.status, TenantSubscription.Status.CANCELED)
        self.assertIsNotNone(fake_sub.canceled_at)
        fake_sub.save.assert_called_once()
