"""No apply failure may escape the drainer's bounded-retry handler.

``drain_tenant_stream`` caught ``(ValueError, TypeError, RuntimeError, DatabaseError)``
around ``_apply_envelope``, and ONLY inside that handler is the attempt counter
incremented and the envelope eventually dead-lettered.  Anything else -- a
``ValidationError`` out of ``DateField.get_prep_value``, an ``ObjectDoesNotExist``
from a writer -- propagated out of the task, so the entry was never ``xdel``'d,
its counter never advanced, and ``xrange`` re-read it from the stream head on
every drain thereafter.  Every later envelope for that tenant sat behind it:
the head-of-line poison pill ``_MAX_APPLY_ATTEMPTS`` exists to prevent.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.test import SimpleTestCase, override_settings


class _FakeRedis:
    """Just enough of the redis client for one drain cycle, in memory."""

    def __init__(self):
        self.streams: dict[str, list] = {}
        self.sets: dict[str, set] = {}
        self.hashes: dict[str, dict] = {}
        self.keys: dict[str, str] = {}
        self._seq = 0

    # --- stream ---------------------------------------------------------
    def xadd(self, stream, fields, maxlen=None, approximate=True):
        self._seq += 1
        entry_id = "{0}-0".format(self._seq).encode()
        self.streams.setdefault(stream, []).append((entry_id, fields))
        return entry_id

    def xrange(self, stream, count=None):
        return list(self.streams.get(stream, []))[: count or None]

    def xdel(self, stream, entry_id):
        rows = self.streams.get(stream, [])
        self.streams[stream] = [r for r in rows if r[0] != entry_id]

    # --- set / hash / plain key -----------------------------------------
    def sismember(self, key, member):
        return member in self.sets.get(key, set())

    def sadd(self, key, member):
        self.sets.setdefault(key, set()).add(member)

    def hincrby(self, key, field, amount):
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = bucket.get(field, 0) + amount
        return bucket[field]

    def hdel(self, key, field):
        self.hashes.get(key, {}).pop(field, None)

    def expire(self, key, seconds):
        return True

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return False
        self.keys[key] = value
        return True

    def delete(self, key):
        self.keys.pop(key, None)


_TENANT = "abc123abc123"
_STREAM = "rmc.wal.{0}".format(_TENANT)
_DEADLETTER = "rmc.wal.deadletter.{0}".format(_TENANT)
_ATTEMPTS = "rmc.wal.attempts.{0}".format(_TENANT)


@override_settings(REDIS_URL="redis://fake/0")
class DrainBoundedRetryCoversEveryFailureTests(SimpleTestCase):
    def _drain_with(self, exc):
        from apps.wal_stream.tasks import drain_tenant_stream

        fake = _FakeRedis()
        fake.xadd(
            _STREAM,
            {
                b"envelope": json.dumps(
                    {
                        "txn_id": "t" * 12,
                        "domain": "attendance",
                        "tenant_hash": _TENANT,
                        "actions": [{"student_id": 1}],
                    }
                ).encode()
            },
        )
        with patch("redis.Redis.from_url", return_value=fake), patch(
            "apps.wal_stream.tasks._apply_envelope", side_effect=exc
        ):
            result = drain_tenant_stream(_TENANT)
        return fake, result

    def test_validation_error_is_bounded_retried_not_raised(self):
        """A malformed date is a bad row, not a reason to stop the tenant's rail."""
        fake, result = self._drain_with(
            ValidationError("'2026-13-45' value has the correct format")
        )
        # The envelope stayed for retry, and — the load-bearing part — its attempt
        # counter advanced, which only happens inside the bounded-retry handler.
        self.assertEqual(fake.hashes.get(_ATTEMPTS, {}).get("t" * 12), 1)
        self.assertEqual(result.get("applied"), 0)

    def test_object_does_not_exist_is_bounded_retried_not_raised(self):
        fake, _result = self._drain_with(ObjectDoesNotExist("gone"))
        self.assertEqual(fake.hashes.get(_ATTEMPTS, {}).get("t" * 12), 1)

    def test_a_permanently_failing_envelope_is_dead_lettered_not_replayed_forever(self):
        """Five drains, then the head of the stream is cleared for everyone behind it."""
        from apps.wal_stream.tasks import _MAX_APPLY_ATTEMPTS, drain_tenant_stream

        fake = _FakeRedis()
        fake.xadd(
            _STREAM,
            {
                b"envelope": json.dumps(
                    {
                        "txn_id": "t" * 12,
                        "domain": "attendance",
                        "tenant_hash": _TENANT,
                        "actions": [{"student_id": 1}],
                    }
                ).encode()
            },
        )
        with patch("redis.Redis.from_url", return_value=fake), patch(
            "apps.wal_stream.tasks._apply_envelope",
            side_effect=ValidationError("bad date"),
        ):
            for _ in range(_MAX_APPLY_ATTEMPTS):
                drain_tenant_stream(_TENANT)
                # The lock is a plain key with a TTL the fake does not expire;
                # a real next drain starts with it gone.
                fake.delete("rmc.wal.lock.{0}".format(_TENANT))

        self.assertEqual(fake.streams.get(_STREAM), [])
        self.assertEqual(len(fake.streams.get(_DEADLETTER, [])), 1)

    def test_a_healthy_envelope_still_applies(self):
        """Guard against the above passing because nothing ran at all."""
        from apps.wal_stream.tasks import drain_tenant_stream

        fake = _FakeRedis()
        fake.xadd(
            _STREAM,
            {
                b"envelope": json.dumps(
                    {
                        "txn_id": "t" * 12,
                        "domain": "attendance",
                        "tenant_hash": _TENANT,
                        "actions": [{"student_id": 1}],
                    }
                ).encode()
            },
        )
        with patch("redis.Redis.from_url", return_value=fake), patch(
            "apps.wal_stream.tasks._apply_envelope"
        ) as apply:
            result = drain_tenant_stream(_TENANT)

        self.assertTrue(apply.called)
        self.assertEqual(result.get("applied"), 1)
        self.assertEqual(fake.streams.get(_STREAM), [])
