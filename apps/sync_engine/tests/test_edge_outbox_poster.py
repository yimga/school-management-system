"""Edge outbox poster + credential mint/resolve (Tier 3 Slice 3).

Covers the box-side command's queue-and-forward contract WITHOUT a live network:
post_bundle is mocked. Cursor advances only on success; an offline run keeps the
cursor and queues the bundle; an operator rejection raises and keeps the cursor.
"""
from __future__ import annotations

import tempfile
import urllib.error
import uuid
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import User
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.edge_outbox import mint_edge_credential, resolve_edge_credential

_SIGN_KEY = "edge-poster-test-key"
_POST = "apps.sync_engine.edge_outbox.post_bundle"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class EdgeOutboxPosterTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Poster {uid}", slug=f"poster-{uid}", subdomain=f"poster{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"poster_svc_{uid}", password="Test1234", email=f"p{uid}@test.com"
        )
        SchoolMembership.objects.create(user=self.user, school=self.school, role="ADMIN", is_primary=True)
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Njoya", date_of_birth="2012-01-01"
        )
        self.tmp = Path(tempfile.mkdtemp())

    def _make_pending_change(self):
        self.student.first_name = "Edited"
        self.student.save(update_fields=["first_name", "updated_at"])

    def _cursor_file(self, value):
        p = self.tmp / "sync.cursor"
        p.write_text(value, encoding="utf-8")
        return p

    def test_mint_and_resolve_round_trip(self):
        raw, token = mint_edge_credential(self.school, self.user, device_id="box", days=10)
        resolved = resolve_edge_credential(raw)
        self.assertIsNotNone(resolved)
        user, school = resolved
        self.assertEqual(user.pk, self.user.pk)
        self.assertEqual(school.pk, self.school.pk)
        # unknown token -> None; revoked device -> None
        self.assertIsNone(resolve_edge_credential("nope"))
        token.device.revoked_at = timezone.now()
        token.device.save(update_fields=["revoked_at"])
        self.assertIsNone(resolve_edge_credential(raw))

    def test_success_advances_cursor(self):
        self._make_pending_change()
        old = (timezone.now() - timedelta(hours=1)).isoformat()
        cursor = self._cursor_file(old)
        with mock.patch(_POST, return_value=(200, {"ok": True, "applied": 1, "conflicts": 0})) as m:
            call_command(
                "post_edge_outbox", slug=self.school.slug,
                endpoint="http://operator.example/api/v1/sync/bundle/upload/",
                token="tok", cursor_file=str(cursor),
            )
        m.assert_called_once()
        new_cursor = cursor.read_text(encoding="utf-8").strip()
        self.assertNotEqual(new_cursor, old)
        self.assertGreater(parse_datetime(new_cursor), parse_datetime(old))

    def test_offline_keeps_cursor_and_queues_bundle(self):
        self._make_pending_change()
        old = (timezone.now() - timedelta(hours=1)).isoformat()
        cursor = self._cursor_file(old)
        outbox = self.tmp / "outbox"
        with mock.patch(_POST, side_effect=urllib.error.URLError("offline")):
            call_command(
                "post_edge_outbox", slug=self.school.slug,
                endpoint="http://operator.example/x", token="tok",
                cursor_file=str(cursor), outbox_dir=str(outbox),
            )
        # cursor unchanged; bundle queued for replay
        self.assertEqual(cursor.read_text(encoding="utf-8").strip(), old)
        self.assertTrue(list(outbox.glob("*.rmcdelta")))

    def test_operator_rejection_raises_and_keeps_cursor(self):
        self._make_pending_change()
        old = (timezone.now() - timedelta(hours=1)).isoformat()
        cursor = self._cursor_file(old)
        with mock.patch(_POST, return_value=(400, {"ok": False, "errors": ["signature_mismatch"]})):
            with self.assertRaises(CommandError):
                call_command(
                    "post_edge_outbox", slug=self.school.slug,
                    endpoint="http://operator.example/x", token="tok",
                    cursor_file=str(cursor), outbox_dir=str(self.tmp / "outbox"),
                )
        self.assertEqual(cursor.read_text(encoding="utf-8").strip(), old)

    def test_nothing_changed_does_not_post(self):
        # cursor in the future -> no rows -> command must not call post_bundle
        future = (timezone.now() + timedelta(days=1)).isoformat()
        cursor = self._cursor_file(future)
        with mock.patch(_POST) as m:
            call_command(
                "post_edge_outbox", slug=self.school.slug,
                endpoint="http://operator.example/x", token="tok", cursor_file=str(cursor),
            )
        m.assert_not_called()
        self.assertEqual(cursor.read_text(encoding="utf-8").strip(), future)
