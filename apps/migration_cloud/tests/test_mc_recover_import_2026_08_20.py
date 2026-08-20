"""The wedged-import recovery command routes through the repair guardrails.

Recovering a stalled import used to mean hand-editing status in a production
shell, which bypasses every check ``repair_readiness`` enforces — including the
financial control-total lock. These tests pin that the command is read-only
until explicitly told otherwise, that it re-runs a genuinely wedged import, and
that it REFUSES rather than forcing one the guardrails reject.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.migration_cloud.models import (
    BundleStatus,
    MigrationBundle,
    MigrationProgressEvent,
)
from apps.schools.models import School

_ENQUEUE = "apps.migration_cloud.celery_tasks.enqueue_apply"


class McRecoverImportCommandTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Recover {uid}", slug=f"recover-{uid}", subdomain=f"rec{uid}", is_active=True
        )

    def _bundle(self, *, status):
        return MigrationBundle.objects.create(
            school=self.school,
            status=status,
            idempotency_key=f"mc-recover-{uuid.uuid4().hex[:16]}",
        )

    def _wedge(self, bundle, *, minutes=120):
        """A claimed apply whose worker stopped writing progress."""
        ev = MigrationProgressEvent.objects.create(
            bundle=bundle, kind="artifact_progress", stage="APPLYING"
        )
        MigrationProgressEvent.objects.filter(pk=ev.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes)
        )
        return bundle

    def _run(self, *args):
        out = StringIO()
        call_command("mc_recover_import", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_listing_is_read_only_and_finds_the_wedged_import(self):
        wedged = self._wedge(self._bundle(status=BundleStatus.APPLYING))
        with mock.patch(_ENQUEUE) as enqueue:
            body = self._run("--school", self.school.slug)
        self.assertIn(f"#{wedged.pk}", body)
        self.assertIn("WEDGED", body)
        enqueue.assert_not_called()
        wedged.refresh_from_db()
        self.assertEqual(wedged.status, BundleStatus.APPLYING, "listing must not mutate")

    def test_repair_requires_an_explicit_bundle_id(self):
        self._wedge(self._bundle(status=BundleStatus.APPLYING))
        with self.assertRaises(CommandError):
            self._run("--repair")

    def test_repair_reclaims_and_queues_the_wedged_import(self):
        wedged = self._wedge(self._bundle(status=BundleStatus.APPLYING))
        queued = SimpleNamespace(outbox_id="recover-1")
        with mock.patch(_ENQUEUE, return_value=queued) as enqueue:
            body = self._run("--bundle-id", str(wedged.pk), "--repair")
        enqueue.assert_called_once()
        self.assertEqual(enqueue.call_args.kwargs.get("dry_run"), False)
        self.assertIn("Queued", body)
        wedged.refresh_from_db()
        self.assertEqual(
            wedged.status, BundleStatus.MAPPED, "a reclaimed apply is reset to MAPPED"
        )

    def test_live_import_is_not_reclaimed(self):
        """A healthy in-flight apply must never be yanked out from under itself."""
        live = self._wedge(self._bundle(status=BundleStatus.APPLYING), minutes=0)
        with mock.patch(_ENQUEUE) as enqueue:
            body = self._run("--bundle-id", str(live.pk), "--repair")
        enqueue.assert_not_called()
        self.assertIn("Refused", body)
        live.refresh_from_db()
        self.assertEqual(live.status, BundleStatus.APPLYING)

    def test_guardrail_refusal_is_reported_not_forced(self):
        done = self._bundle(status=BundleStatus.RECONCILED)
        with mock.patch(_ENQUEUE) as enqueue:
            body = self._run("--bundle-id", str(done.pk), "--repair")
        enqueue.assert_not_called()
        self.assertIn("Refused", body)
        done.refresh_from_db()
        self.assertEqual(done.status, BundleStatus.RECONCILED)
