"""Seal: a counsel-approved retention purge must not permanently break the chain.

purge_audit_events_pre_approved DELETEs a PREFIX of a tenant's audit hash chain,
so the first surviving event's prev_event_hash pointed at a now-purged event ->
verify_audit_chain reported that tenant BROKEN forever, indistinguishable from a
real tamper (and --repair-genesis only fixes an EMPTY prev, not a stale one). The
purge now re-anchors the surviving events into a valid chain from a new genesis.

This test FAILS against the pre-fix purge (orphaned first survivor) and PASSES
against the re-anchoring fix.
"""

from __future__ import annotations

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.migration_cloud.models_audit import (
    GENESIS_SENTINEL,
    MigrationCloudAuditEvent,
    MigrationCloudAuditEventType,
    _compute_integrity_hash,
    _hash_tenant_slug,
)

_TOKEN = "counsel-approved-test-token"
_SLUG = "purge-seal-tenant"


def _chain_is_valid(tenant_hash: str) -> bool:
    events = list(
        MigrationCloudAuditEvent.objects.filter(
            tenant_id_hash=tenant_hash,
        ).order_by("created_at", "id")
    )
    prev = GENESIS_SENTINEL
    for ev in events:
        expected = _compute_integrity_hash(
            pk=str(ev.id), tenant_id_hash=ev.tenant_id_hash, event_type=ev.event_type,
            actor_id=ev.actor_id, event_subject_hash=ev.event_subject_hash,
            payload_summary=ev.payload_summary or {}, created_at_iso=ev.created_at_iso,
            prev_event_hash=prev,
        )
        if ev.prev_event_hash != prev or ev.integrity_hash != expected:
            return False
        prev = ev.integrity_hash
    return True


@override_settings(MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN=_TOKEN)
class PurgeReanchorTests(TestCase):
    def _record(self, i: int):
        return MigrationCloudAuditEvent.objects.record(
            tenant_slug=_SLUG,
            event_type=MigrationCloudAuditEventType.values[0],
            actor=None,
            subject=str(i),
            payload_summary={"n": i},
        )

    def test_purge_reanchors_surviving_chain(self):
        tenant_hash = _hash_tenant_slug(_SLUG)
        self._record(1)
        self._record(2)
        e3 = self._record(3)
        self._record(4)
        # The chain is valid before any purge.
        self.assertTrue(_chain_is_valid(tenant_hash))

        # Purge everything strictly before e3 -> deletes the first two events.
        call_command(
            "purge_audit_events_pre_approved",
            tenant=_SLUG,
            before=e3.created_at.isoformat(),
            counsel_approval_token=_TOKEN,
            apply=True,
        )

        remaining = MigrationCloudAuditEvent.objects.filter(tenant_id_hash=tenant_hash)
        # A prefix was purged (at least the earliest events) and the meta-event
        # was added; survivors were orphaned from the deleted head.
        self.assertGreaterEqual(remaining.count(), 2)
        self.assertLess(remaining.count(), 5)

        # The surviving chain re-verifies from a NEW genesis. Must-fire: without
        # re-anchoring the first survivor's prev_event_hash still pointed at the
        # deleted event, so this returns False.
        self.assertTrue(_chain_is_valid(tenant_hash))
        first = remaining.order_by("created_at", "id").first()
        self.assertEqual(first.prev_event_hash, GENESIS_SENTINEL)
