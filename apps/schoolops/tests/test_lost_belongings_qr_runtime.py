"""Runtime tests for apps.schoolops.lost_belongings_qr (batch 1493)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schoolops.lost_belongings_qr import (
    LostBelongingsError,
    mint_tag,
    record_finder_sighting,
    record_staff_recovery,
)


class LostBelongingsQRRuntimeTests(SimpleTestCase):
    def test_mint_tag_hashes_tenant_and_assigns_short_code(self) -> None:
        tag = mint_tag(tenant_id="tenant-x", asset_id="a-1", label_hint="blue lunch bag")
        self.assertNotEqual(tag.tenant_id_hash, "tenant-x")
        self.assertEqual(len(tag.tenant_id_hash), 12)
        self.assertTrue(len(tag.short_code) >= 8)

    def test_mint_tag_rejects_email_in_label(self) -> None:
        with self.assertRaises(LostBelongingsError):
            mint_tag(tenant_id="t", asset_id="a", label_hint="parent@school.com bag")

    def test_finder_sighting_redacts_sensitive_tokens(self) -> None:
        tag = mint_tag(tenant_id="t", asset_id="a", label_hint="grey hoodie")
        event = record_finder_sighting(
            tag=tag,
            notes="contact phone 555-1234",
        )
        self.assertEqual(event.notes_redacted, "[REDACTED]")
        self.assertEqual(event.actor_kind, "anonymous_finder")
        self.assertTrue(event.parent_notified)

    def test_staff_recovery_records_hashed_staff(self) -> None:
        tag = mint_tag(tenant_id="t", asset_id="a", label_hint="ruler")
        event = record_staff_recovery(tag=tag, staff_id="staff-1", notes="returned at recess")
        self.assertEqual(event.actor_kind, "staff")
        self.assertEqual(event.notes_redacted, "returned at recess")

    def test_staff_recovery_requires_staff_id(self) -> None:
        tag = mint_tag(tenant_id="t", asset_id="a", label_hint="ruler")
        with self.assertRaises(LostBelongingsError):
            record_staff_recovery(tag=tag, staff_id="")
