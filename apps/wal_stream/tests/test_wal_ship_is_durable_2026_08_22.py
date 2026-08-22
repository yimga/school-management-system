"""A WAL envelope must not be acked unless it reached a durable sink.

``_ship_to_redis_stream`` acquired its connection with
``getattr(layer, "pools", None)`` and shipped only ``if conn_pool``.
``channels_redis.core.RedisChannelLayer`` has no ``pools`` attribute -- it keeps
``self._layers`` -- so the getattr always returned None, the branch never ran, and
nothing was EVER written to ``rmc.wal.<tenant_hash>``. The consumer then sent
``{"ok": True}`` unconditionally, so the device marked its offline outbox row
synced and deleted it: silent data loss on the path whose own comment promises
at-least-once.

These pin both halves -- the private attribute the old code depended on really is
absent (so the bug was real and cannot be reintroduced by "restoring" it), and a
failed ship no longer returns success.
"""

from __future__ import annotations

import asyncio

from django.test import SimpleTestCase, override_settings

from apps.wal_stream import consumers


class RedisChannelLayerHasNoPoolsAttributeTests(SimpleTestCase):
    def test_the_attribute_the_old_code_relied_on_does_not_exist(self) -> None:
        from channels_redis.core import RedisChannelLayer

        layer = RedisChannelLayer(hosts=["redis://localhost:6379"])
        self.assertFalse(
            hasattr(layer, "pools"),
            "if channels_redis ever grows a .pools attribute this test should be "
            "revisited -- but the shipping path must not depend on it either way",
        )
        self.assertTrue(
            hasattr(layer, "_layers"),
            "channels_redis keeps its pools in the private _layers mapping",
        )


class ShipReportsFailureHonestlyTests(SimpleTestCase):
    @override_settings(REDIS_URL="", CELERY_BROKER_URL="")
    def test_no_redis_configured_returns_false_not_none(self) -> None:
        envelope = {"tenant_hash": "abc123", "txn_id": "t" * 12}
        result = asyncio.run(consumers._ship_to_redis_stream(envelope))
        self.assertIs(
            result,
            False,
            "with no sink configured the ship must report failure, so the caller "
            "withholds the ack and the device keeps its outbox row",
        )

    @override_settings(REDIS_URL="redis://127.0.0.1:1/0")
    def test_unreachable_redis_returns_false_and_does_not_raise(self) -> None:
        # Port 1 is not listening: a Redis hiccup must not close the WS, but it
        # must not be reported as a durable write either.
        envelope = {"tenant_hash": "abc123", "txn_id": "t" * 12}
        result = asyncio.run(consumers._ship_to_redis_stream(envelope))
        self.assertIs(result, False)
