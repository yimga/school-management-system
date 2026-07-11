"""WAL tenant_hash handshake: the offline client must assert the SAME tenant_hash
the server derives — or omit it — never a host-derived guess.

static/js/rmc-wal-stream.js used to hash window.location.host, but the server
(apps/wal_stream/consumers.py) validates the asserted tenant_hash against
sha256(str(school.id))[:12] and rejects any mismatch — so every real-browser WAL
envelope was rejected tenant_mismatch and the entire offline rail was
dead-on-arrival. The client now reads the server-provided value from the offline
config island (wal_tenant_hash_for_request), which equals the server's derivation;
the server also tolerates an absent value (it stamps its own authoritative one).
"""

from __future__ import annotations

import hashlib
import uuid
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from apps.siteconfig.platform_surface_config import wal_tenant_hash_for_request
from apps.wal_stream.consumers import _validate


def _envelope(**overrides):
    env = {
        "txn_id": "abcd1234ef56",
        "vector_clock": 1,
        "domain": "attendance",
        "actions": [{"student_id": "s1", "status": "present"}],
    }
    env.update(overrides)
    return env


class WalTenantHashValidateTests(SimpleTestCase):
    def test_absent_tenant_hash_is_accepted(self):
        # The fixed client omits tenant_hash when the config island has none; the
        # server must skip the cross-check (it stamps its own), not reject.
        ok, reason = _validate(_envelope(), expected_tenant_hash="deadbeefcafe")
        self.assertTrue(ok, reason)

    def test_empty_tenant_hash_is_accepted(self):
        ok, reason = _validate(
            _envelope(tenant_hash=""), expected_tenant_hash="deadbeefcafe"
        )
        self.assertTrue(ok, reason)

    def test_matching_tenant_hash_is_accepted(self):
        ok, reason = _validate(
            _envelope(tenant_hash="deadbeefcafe"), expected_tenant_hash="deadbeefcafe"
        )
        self.assertTrue(ok, reason)

    def test_wrong_tenant_hash_still_rejected(self):
        # A wrong value (the old host-derived bug) is correctly rejected — that is
        # WHY the old client broke. The fix is to assert the RIGHT value, not to
        # weaken this cross-check.
        ok, reason = _validate(
            _envelope(tenant_hash="ffffffffffff"), expected_tenant_hash="deadbeefcafe"
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "tenant_mismatch")

    def test_config_helper_empty_without_school(self):
        self.assertEqual(wal_tenant_hash_for_request(SimpleNamespace(school=None)), "")
        self.assertEqual(wal_tenant_hash_for_request(SimpleNamespace()), "")


class WalTenantHashDerivationTests(TestCase):
    def test_config_value_matches_server_scope_derivation(self):
        from apps.schools.models import School

        uid = uuid.uuid4().hex[:8]
        school = School.objects.create(
            name=f"WAL {uid}",
            slug=f"wal-{uid}",
            subdomain=f"wal-{uid}",
            is_active=True,
        )
        # What the server consumer derives from the authenticated socket scope:
        expected = hashlib.sha256(str(school.id).encode("utf-8")).hexdigest()[:12]
        # The stored column the offline config exposes to the client equals it:
        self.assertEqual(school.tenant_hash, expected)
        cfg_value = wal_tenant_hash_for_request(SimpleNamespace(school=school))
        self.assertEqual(cfg_value, expected)
        # So the value the fixed client asserts passes validation instead of
        # being rejected tenant_mismatch — the whole point of the fix.
        ok, reason = _validate(
            _envelope(tenant_hash=cfg_value), expected_tenant_hash=expected
        )
        self.assertTrue(ok, reason)
