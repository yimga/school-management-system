"""Two concurrent audit events for one tenant must not fork the hash chain.

``MigrationCloudAuditEvent.save()`` read the chain tail with a plain
``.filter(tenant_id_hash=...).order_by("-created_at").first()`` — no lock, and
the ``transaction.atomic()`` in ``AuditEventManager.record`` does not serialise
that read. Under READ COMMITTED two writers for one tenant both observe tail N
and both persist ``prev_event_hash = integrity_hash(N)``.

``verify_audit_chain`` walks ``order_by("created_at", "id")`` carrying a single
``prev_hash`` and requires ``hmac.compare_digest(prev_hash, ev.prev_event_hash)``,
so the second of the forked pair fails ``link_ok`` — and so does every event
after it, because the chain never re-converges. That drives ``_send_break_email``
and the weekly beat alarm forever. A permanent false tamper alarm is worse than
none: once operators learn to ignore it, a real tamper looks identical.

The interleaving is forced deterministically rather than raced: writer A is
parked between its tail read and its insert (the patched hash function is called
after the tail read), and writer B runs while A is parked. On the unfixed code B
reads the same tail and the two rows come out sharing a ``prev_event_hash``.

Scope of this proof: it runs on SQLite against the direct ``.save()`` path,
where the fallback process-local lock applies. Production is PostgreSQL, where
the append takes a transaction-scoped advisory lock — that path is not exercised
by a SQLite suite and is asserted only by construction.
"""

from __future__ import annotations

import threading

from django.db import connection
from django.test import TransactionTestCase
from unittest import mock

from apps.migration_cloud import models_audit
from apps.migration_cloud.models_audit import (
    GENESIS_SENTINEL,
    MigrationCloudAuditEvent,
)

TENANT = "chainfork0001"
PARK_TIMEOUT = 3.0  # seconds A waits for B before giving up and committing


class AuditChainConcurrentAppendTests(TransactionTestCase):
    def _run_two_writers(self):
        a_parked = threading.Event()
        b_reached_hash = threading.Event()
        calls: list[str] = []
        real_hash = models_audit._compute_integrity_hash
        first = threading.Lock()
        seen_first = []

        def _hooked(**kwargs):
            calls.append(kwargs.get("event_type", ""))
            with first:
                is_first = not seen_first
                if is_first:
                    seen_first.append(True)
            if is_first:
                # A has already read the tail; park it here so B runs in the
                # window between A's read and A's insert.
                a_parked.set()
                b_reached_hash.wait(PARK_TIMEOUT)
            else:
                b_reached_hash.set()
            return real_hash(**kwargs)

        errors: list[BaseException] = []

        def _write(event_type):
            try:
                MigrationCloudAuditEvent(
                    tenant_id_hash=TENANT, event_type=event_type,
                    payload_summary={"n": event_type},
                ).save()
            except BaseException as exc:  # noqa: BLE001 — reported to the test
                errors.append(exc)
            finally:
                connection.close()

        with mock.patch.object(
            models_audit, "_compute_integrity_hash", side_effect=_hooked
        ):
            t_a = threading.Thread(target=_write, args=("A",))
            t_a.start()
            # Only start B once A is genuinely parked past its tail read —
            # otherwise the two writers may not overlap at all and the test
            # would pass on the broken code by accident.
            self.assertTrue(
                a_parked.wait(PARK_TIMEOUT + 5), "writer A never reached the hash step"
            )
            t_b = threading.Thread(target=_write, args=("B",))
            t_b.start()
            t_a.join(PARK_TIMEOUT + 15)
            t_b.join(PARK_TIMEOUT + 15)

        self.assertEqual(errors, [], f"a writer raised: {errors}")
        self.assertFalse(t_a.is_alive() or t_b.is_alive(), "a writer never finished")
        # Vacuity guards: both writes really went through save()'s chain step,
        # and both rows really landed — so the chain assertions below are
        # reading two concurrently appended events and not one lucky one.
        self.assertEqual(len(calls), 2, calls)
        return list(
            MigrationCloudAuditEvent.objects.filter(  # tenant-isolation-allow: test reads the tenant's own chain
                tenant_id_hash=TENANT
            ).order_by("created_at", "id")
        )

    def test_concurrent_appends_do_not_share_a_prev_event_hash(self):
        events = self._run_two_writers()
        self.assertEqual(len(events), 2, [e.event_type for e in events])

        prevs = [e.prev_event_hash for e in events]
        self.assertEqual(
            len(set(prevs)), 2,
            f"both events chained off the same tail — chain forked: {prevs}",
        )
        # And the surviving order is a real chain: genesis, then A's hash.
        self.assertEqual(events[0].prev_event_hash, GENESIS_SENTINEL)
        self.assertEqual(events[1].prev_event_hash, events[0].integrity_hash)

    def test_the_verifier_sees_an_unbroken_chain(self):
        # The consequence the finding is actually about: the weekly verifier's
        # link check. Walked exactly as verify_audit_chain does.
        events = self._run_two_writers()
        prev = GENESIS_SENTINEL
        for ev in events:
            self.assertEqual(
                ev.prev_event_hash, prev,
                f"verifier would report {ev.event_type} BROKEN",
            )
            prev = ev.integrity_hash
