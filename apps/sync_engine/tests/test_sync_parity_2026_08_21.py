"""G8: the parity seal — does the far side actually HOLD what this side holds?

The property every test here is really defending is the one the obvious implementation
gets wrong. ``updated_at`` is ``auto_now``, so when the box applies a row the cloud sent,
the local save stamps a NEW timestamp: two perfectly converged sides hold different
``updated_at`` for the same row, permanently. A digest over it would report drift on
every row on the first cycle and never stop, and a monitor that is always red is a
monitor nobody reads. ``test_updated_at_skew_is_not_drift`` is therefore the first test
in the file and the one to read first.

The second property is identity. A row created on the CLOUD keeps its pk when it lands on
the box (``_create_from_cloud_pull`` is pk-preserving); a row created on the BOX is
upserted by ``(school, client_offline_id)`` and the cloud mints its OWN pk. So neither
"key on pk" nor "key on the anchor" is correct alone, and getting it wrong fails in the
quietest possible way — every offline-created row reported as drift forever, or every
cloud-authored row collapsed onto one empty key.

The endpoint tests then prove the handshake end to end on the cloud half: a box that
presents a STALE digest is told which entities disagree, a box that presents a current
one is told nothing, and a box that presents none pays nothing.
"""
from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import uuid

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIRequestFactory

from apps.academics.models import Department
from apps.accounts.models import User
from apps.api.sync_bundle_api import SyncBundleDownloadView
from apps.schools.models import School
from apps.sync_engine import parity
from apps.sync_engine.edge_outbox import (
    SYNC_PARITY_DRIFT_HEADER,
    SYNC_PARITY_HEADER,
    mint_edge_credential,
)


def _digest(school, entity_type="department"):
    """The digest for one entity, using the registry's own model + field set."""
    from apps.api.sync_services import _get_entity_config

    model, allowed = _get_entity_config(include_derived=True)[entity_type]
    return parity.entity_digest(school, entity_type, model, allowed)


class _ParityFixture(TestCase):
    """One school holding three departments — small, but every rail shape is present."""

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Parity {uid}",
            slug=f"parity-{uid}",
            subdomain=f"parity{uid}",
            is_active=True,
        )
        self.other = School.objects.create(
            name=f"Other {uid}",
            slug=f"other-{uid}",
            subdomain=f"other{uid}",
            is_active=True,
        )
        # Cloud-authored (empty anchor, identity is the pk) and box-authored (anchor set).
        self.cloud_row = Department.objects.create(
            school=self.school, name="Science", code=f"SCI{uid}"
        )
        self.box_row = Department.objects.create(
            school=self.school,
            name="Arts",
            code=f"ART{uid}",
            client_offline_id=f"anchor-{uid}",
        )
        self.uid = uid
        cache.clear()
        self.addCleanup(cache.clear)


class ParityDigestSemanticsTests(_ParityFixture):
    def test_updated_at_skew_is_not_drift(self):
        """THE central claim: a converged row digests the same on both sides.

        Simulated exactly as it happens in production — the far side applied the row, so
        its ``updated_at`` moved while every rail field stayed identical. If the digest
        covered ``updated_at`` this assertion fails, which is the whole reason it does not.
        """
        before = _digest(self.school)
        # `.update()` writes the column directly and does NOT fire auto_now, so this is a
        # deliberate, controlled skew rather than an incidental one.
        moved = Department.objects.filter(school=self.school).first().updated_at
        Department.objects.filter(school=self.school).update(  # tenant-isolation-allow: test-fixture-scoped-to-its-own-school
            updated_at=moved.replace(year=moved.year - 1) if moved else None
        )
        self.assertEqual(_digest(self.school), before)

    def test_changed_rail_field_is_drift_of_kind_row_values(self):
        before = _digest(self.school)
        self.cloud_row.name = "Sciences"
        self.cloud_row.save(update_fields=["name"])
        after = _digest(self.school)

        self.assertNotEqual(after["h"], before["h"])
        self.assertEqual(after["n"], before["n"])  # same rows, different contents
        comparison = parity.compare_digests({"department": before}, {"department": after})
        self.assertEqual(comparison["drifted"], ["department"])
        self.assertEqual(comparison["detail"]["department"]["kind"], "row_values")

    def test_missing_row_is_drift_of_kind_row_count(self):
        before = _digest(self.school)
        self.cloud_row.delete()
        after = _digest(self.school)

        self.assertEqual(after["n"], before["n"] - 1)
        comparison = parity.compare_digests({"department": after}, {"department": before})
        self.assertEqual(comparison["detail"]["department"]["kind"], "row_count")
        # Orientation matters: local is the side MISSING a row, so the delta is positive
        # ("the peer has one more than I do"). A sign flip here sends an operator hunting
        # for extra records when records are missing.
        self.assertEqual(comparison["detail"]["department"]["row_delta"], 1)

    def test_identity_is_the_anchor_when_present_so_pks_may_differ(self):
        """A box-created row keeps its identity across a pk the two sides disagree on."""
        before = _digest(self.school)
        anchor, name, code = (
            self.box_row.client_offline_id,
            self.box_row.name,
            self.box_row.code,
        )
        self.box_row.delete()
        # Same anchor, same rail fields, a pk that cannot repeat: exactly what the cloud
        # holds after `apply_edge_inserts` mints its own id for a box-authored row.
        replacement = Department.objects.create(
            school=self.school, name=name, code=code, client_offline_id=anchor
        )
        self.assertNotEqual(replacement.pk, self.box_row.pk)
        self.assertEqual(_digest(self.school), before)

    def test_digest_is_scoped_to_one_school(self):
        before = _digest(self.school)
        Department.objects.create(school=self.other, name="Ghost", code=f"GH{self.uid}")
        self.assertEqual(_digest(self.school), before)
        # ...and the other school's own digest is genuinely different, so the scoping is
        # doing real work rather than the two happening to be empty.
        self.assertNotEqual(_digest(self.other)["h"], before["h"])

    def test_digest_is_order_independent(self):
        """The XOR fold is what lets both sides stream rows in their planner's order."""
        a = parity.entity_digest(
            self.school, "department", Department, {"name", "code"}
        )
        Department.objects.filter(pk=self.cloud_row.pk).update(name="Science")  # tenant-isolation-allow: test-fixture-row-addressed-by-its-own-pk
        b = parity.entity_digest(
            self.school, "department", Department, {"code", "name"}
        )
        self.assertEqual(a, b)  # field-set order cannot change the answer either

    def test_live_digest_survives_the_wire_round_trip(self):
        """The pure round-trip is asserted above; this one starts from real rows, so a
        digest that only agrees with itself in memory cannot pass."""
        digests = parity.parity_digests(self.school, entities=["department"])
        decoded = parity.decode_digests(parity.encode_digests(digests))
        comparison = parity.compare_digests(digests, decoded)
        self.assertTrue(comparison["in_parity"])
        self.assertEqual(decoded["department"]["n"], 2)


class ParityCanonicalEncodingTests(SimpleTestCase):
    """Two Postgres deployments must reduce the same column value to the same bytes.

    No database: these are the pure conversions, and they are where a cross-deployment
    digest quietly goes wrong. Each case below is a shape where two correct deployments
    can legitimately hand Python different objects for the same stored value.
    """

    def test_decimal_scale_does_not_change_the_digest(self):
        """``1.50``, ``1.5`` and ``1.5E+0`` are one money value, not three."""
        forms = [_decimal.Decimal("1.50"), _decimal.Decimal("1.5"), _decimal.Decimal("1.5E+0")]
        rendered = {parity._canonical(d) for d in forms}
        self.assertEqual(len(rendered), 1, rendered)

    def test_decimal_is_never_rendered_in_scientific_notation(self):
        self.assertEqual(parity._canonical(_decimal.Decimal("1E+2")), "100")

    def test_datetimes_are_normalised_to_utc(self):
        """A box on a local TIME_ZONE and a cloud on UTC digest the same instant alike."""
        instant = _dt.datetime(2026, 8, 21, 12, 0, tzinfo=_dt.timezone.utc)
        shifted = instant.astimezone(_dt.timezone(_dt.timedelta(hours=3)))
        self.assertNotEqual(instant.isoformat(), shifted.isoformat())
        self.assertEqual(parity._canonical(instant), parity._canonical(shifted))

    def test_memoryview_digests_by_content_not_by_address(self):
        """psycopg hands back a memoryview for bytea; ``str()`` on one embeds its ADDRESS,
        which would differ on every single call and report drift on every cycle."""
        a = parity._canonical(memoryview(b"same-bytes"))
        b = parity._canonical(memoryview(b"same-bytes"))
        self.assertEqual(a, b)
        self.assertNotEqual(a, parity._canonical(memoryview(b"other-bytes")))

    def test_none_and_empty_string_are_distinguishable(self):
        """A nulled column and a blanked one are different edits, so they must digest
        differently — otherwise clearing a field reads as no change at all."""
        self.assertNotEqual(
            parity._row_digest("id", {"f": None}), parity._row_digest("id", {"f": ""})
        )

    def test_identity_cannot_be_confused_with_a_value(self):
        """The unit separator is why an identity ending in a value-like suffix cannot
        collide with a different identity carrying that suffix as data."""
        self.assertNotEqual(
            parity._row_digest("a", {"f": "b"}), parity._row_digest("a\x1fb", {})
        )

    def test_field_order_cannot_change_a_row_digest(self):
        self.assertEqual(
            parity._row_digest("id", {"a": 1, "b": 2}),
            parity._row_digest("id", {"b": 2, "a": 1}),
        )


class ParityWireFormatTests(SimpleTestCase):
    """The header round trip and the comparison — all pure, so no database."""

    def test_encode_decode_round_trip(self):
        digests = {
            "department": {"n": 2, "h": "9f3a1c7e5b2d4086aa11"},
            "classroom": {"n": 41, "h": "0011223344556677ffff"},
        }
        decoded = parity.decode_digests(parity.encode_digests(digests))
        self.assertEqual(decoded["department"]["n"], 2)
        self.assertEqual(decoded["classroom"]["n"], 41)
        comparison = parity.compare_digests(digests, decoded)
        self.assertTrue(comparison["in_parity"])
        self.assertEqual(comparison["drifted"], [])

    def test_truncation_is_symmetric_so_a_match_is_never_lost_to_it(self):
        """The header carries a truncated digest; the comparison must truncate BOTH sides
        or a full-width local digest would never equal the wire form it just produced."""
        full = {"department": {"n": 1, "h": "a" * 64}}
        comparison = parity.compare_digests(full, parity.decode_digests(parity.encode_digests(full)))
        self.assertEqual(comparison["drifted"], [])

    def test_malformed_segments_are_dropped_not_raised(self):
        """A peer may be a version this one has never met."""
        decoded = parity.decode_digests("department:2:abcd,garbage,too:many:colons:here,,x::")
        self.assertEqual(list(decoded), ["department"])

    def test_entity_known_to_only_one_side_is_not_drift(self):
        comparison = parity.compare_digests(
            {"department": {"n": 1, "h": "aa"}, "brand_new": {"n": 1, "h": "bb"}},
            {"department": {"n": 1, "h": "aa"}},
        )
        self.assertEqual(comparison["drifted"], [])
        self.assertEqual(comparison["only_local"], ["brand_new"])
        self.assertTrue(comparison["in_parity"])

    def test_rank_puts_missing_rows_before_stale_values(self):
        comparison = parity.compare_digests(
            {"a": {"n": 1, "h": "1"}, "b": {"n": 5, "h": "2"}, "c": {"n": 1, "h": "3"}},
            {"a": {"n": 1, "h": "9"}, "b": {"n": 9, "h": "8"}, "c": {"n": 2, "h": "7"}},
        )
        # b is short by 4 rows, c by 1, a is merely stale — worst hole first.
        self.assertEqual(parity.rank_for_flush(comparison), ["b", "c", "a"])


class ParityCadenceTests(_ParityFixture):
    def test_due_claims_the_window_so_a_sweep_cannot_run_every_cycle(self):
        self.assertTrue(parity.due(self.school))
        self.assertFalse(parity.due(self.school))  # claimed for the interval
        self.assertTrue(parity.due(self.school, force=True))  # an operator may override

    def test_reset_re_arms_the_sweep(self):
        self.assertTrue(parity.due(self.school))
        parity.reset(self.school)
        self.assertTrue(parity.due(self.school))

    @override_settings(RMC_SYNC_PARITY_ENABLED=False)
    def test_disabled_means_no_digest_and_no_sweep(self):
        self.assertFalse(parity.enabled())
        self.assertFalse(parity.due(self.school, force=True))
        self.assertEqual(parity.parity_digests(self.school), {})


class ParityResilienceTests(_ParityFixture):
    def test_a_failing_entity_is_omitted_never_faked(self):
        """An entity that cannot be digested must not report a digest at all.

        Reporting SOMETHING for it would read as agreement on the far side, which is the
        one answer a broken scan must never give.
        """
        from unittest.mock import patch

        real = parity.entity_digest

        def _boom(school, entity_type, model, allowed):
            if entity_type == "department":
                raise RuntimeError("column does not exist")
            return real(school, entity_type, model, allowed)

        with patch.object(parity, "entity_digest", side_effect=_boom):
            digests = parity.parity_digests(self.school)
        self.assertNotIn("department", digests)
        self.assertTrue(digests, "the other entities must still be reported")

    def test_registry_failure_answers_empty_rather_than_raising(self):
        from unittest.mock import patch

        with patch(
            "apps.api.sync_services._get_entity_config", side_effect=RuntimeError("nope")
        ):
            self.assertEqual(parity.parity_digests(self.school), {})


class ParityHandshakeEndpointTests(_ParityFixture):
    """The cloud half of the handshake, over the real download endpoint."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_superuser(
            username=f"parity{self.uid}",
            email=f"parity{self.uid}@example.com",
            password="x",
        )
        self.token, _obj = mint_edge_credential(
            self.school, self.user, device_id="parity-box", days=30
        )
        self.rf = APIRequestFactory()

    def _download(self, **extra):
        request = self.rf.get(
            "/api/v1/sync/bundle/download/",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            **extra,
        )
        return SyncBundleDownloadView.as_view()(request)

    def _header_kwarg(self, value):
        return {"HTTP_" + SYNC_PARITY_HEADER.upper().replace("-", "_"): value}

    def test_stale_digest_is_answered_with_the_drifted_entity(self):
        stale = parity.encode_digests(parity.parity_digests(self.school))
        # The box's copy is now out of date in exactly the way that matters: the cloud has
        # a row it does not.
        Department.objects.create(
            school=self.school, name="Later", code=f"LTR{self.uid}"
        )

        resp = self._download(**self._header_kwarg(stale))
        self.assertEqual(resp.status_code, 200)
        drift = resp.headers.get(SYNC_PARITY_DRIFT_HEADER, "")
        self.assertIn("department", drift.split(","))

    def test_current_digest_is_answered_with_no_drift(self):
        current = parity.encode_digests(parity.parity_digests(self.school))
        resp = self._download(**self._header_kwarg(current))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(SYNC_PARITY_DRIFT_HEADER, resp.headers)

    def test_a_box_that_sends_no_digest_is_charged_nothing(self):
        """The hot path must be untouched for the overwhelmingly common cycle."""
        from unittest.mock import patch

        with patch.object(parity, "parity_digests") as scan:
            resp = self._download()
        self.assertEqual(resp.status_code, 200)
        scan.assert_not_called()
        self.assertNotIn(SYNC_PARITY_DRIFT_HEADER, resp.headers)

    @override_settings(RMC_SYNC_PARITY_ENABLED=False)
    def test_disabled_cloud_answers_no_drift_even_to_a_stale_digest(self):
        resp = self._download(**self._header_kwarg("department:0:0000000000000000"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(SYNC_PARITY_DRIFT_HEADER, resp.headers)

    def test_parity_failure_never_costs_the_box_its_bundle(self):
        from unittest.mock import patch

        stale = parity.encode_digests(parity.parity_digests(self.school))
        with patch.object(parity, "compare_digests", side_effect=RuntimeError("boom")):
            resp = self._download(**self._header_kwarg(stale))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(SYNC_PARITY_DRIFT_HEADER, resp.headers)
