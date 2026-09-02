"""``report_delete_evidence`` must answer with evidence, not subtraction.

The command exists because 39 tombstones minus 26 survivors was written down as "13
records destroyed" and the box's own data did not support it. These tests hold the two
properties that make the command trustworthy where the subtraction was not:

1.  EVERY pk lands in exactly one bucket and the buckets sum to the tombstones -- the
    tally closes, by assertion inside ``classify`` and again out here.
2.  "destroyed" is claimed ONLY on positive evidence (an apply-ledger row for a pk with
    no live row), and an unreadable instrument degrades to ``unknown``, never to a
    flattering bucket. A ledger hit while the live table is unreadable is NOT destroyed
    -- the row might be sitting there fine.
"""

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from apps.academics.models import Department
from apps.schools.models import School
from apps.sync_engine.management.commands.report_delete_evidence import classify
from apps.sync_engine.models import SyncApplyLedger, SyncTombstone
from django.utils import timezone


class ClassifyBucketsTests(SimpleTestCase):
    """The pure classifier: one bucket per pk, evidence outranks inference."""

    def test_live_pk_is_answered_by_liveness_alone(self):
        out = classify(["5"], live={"5"}, ledger={"5"}, high_water=100)
        self.assertEqual(out["live"], ["5"])
        self.assertEqual(out["destroyed"], [])

    def test_absent_pk_with_ledger_evidence_is_destroyed(self):
        out = classify(["7"], live=set(), ledger={"7"}, high_water=100)
        self.assertEqual(out["destroyed"], ["7"])

    def test_absent_pk_above_high_water_was_never_allocated(self):
        out = classify(["40"], live=set(), ledger=set(), high_water=27)
        self.assertEqual(out["pk_above_high_water"], ["40"])
        self.assertEqual(out["destroyed"], [])

    def test_absent_pk_below_high_water_with_no_ledger_is_unknown(self):
        # pk 5 was allocated at some point and has no ledger trace: the instruments
        # cannot say whether the tombstone found a row. Saying "unknown" is the point.
        out = classify(["5"], live=set(), ledger=set(), high_water=27)
        self.assertEqual(out["unknown"], ["5"])

    def test_unreadable_live_table_blocks_a_destroyed_verdict(self):
        # THE load-bearing ordering. A ledger hit proves a row existed here once; only
        # the live table proves it is gone NOW. With live unreadable the row may still
        # be present, so filing it as destroyed would manufacture a data-loss finding
        # out of a database error.
        out = classify(["7"], live=None, ledger={"7"}, high_water=100)
        self.assertEqual(out["unknown"], ["7"])
        self.assertEqual(out["destroyed"], [])

    def test_unreadable_ledger_degrades_absent_pks_to_unknown(self):
        out = classify(["40"], live=set(), ledger=None, high_water=27)
        self.assertEqual(out["unknown"], ["40"])
        self.assertEqual(out["pk_above_high_water"], [])

    def test_no_high_water_means_no_never_allocated_claim(self):
        # SQLite, a non-sequence pk, or a failed sequence read all hand back None,
        # and None must not classify anything -- 0 would file EVERY tombstone as
        # never-allocated, which is a clean bill of health from a broken instrument.
        out = classify(["40"], live=set(), ledger=set(), high_water=None)
        self.assertEqual(out["unknown"], ["40"])

    def test_non_numeric_pk_never_compares_against_high_water(self):
        out = classify(["abc-uuid"], live=set(), ledger=set(), high_water=27)
        self.assertEqual(out["unknown"], ["abc-uuid"])

    def test_every_pk_lands_in_exactly_one_bucket(self):
        pks = ["1", "2", "28", "40", "x"]
        out = classify(pks, live={"1"}, ledger={"2"}, high_water=27)
        placed = sorted(p for bucket in out.values() for p in bucket)
        self.assertEqual(placed, sorted(pks))
        self.assertEqual(out["live"], ["1"])
        self.assertEqual(out["destroyed"], ["2"])
        self.assertEqual(out["pk_above_high_water"], ["28", "40"])
        self.assertEqual(out["unknown"], ["x"])

    def test_duplicate_pks_are_counted_not_collapsed(self):
        # The command hands classify() a set, but the function must not depend on
        # that: if two tombstones name one pk, both are placed and the sum still
        # matches the input length -- the internal tally assertion stays satisfiable.
        out = classify(["9", "9"], live={"9"}, ledger=set(), high_water=None)
        self.assertEqual(out["live"], ["9", "9"])


class ReportDeleteEvidenceCommandTests(TestCase):
    """The command against a real (SQLite) database: no sequence, real ORM reads."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.first() or School.objects.create(
            name="Evidence High", slug="evidence-high", subdomain="evidencehigh"
        )
        cls.dept_live = Department.objects.create(
            school=cls.school, name="Sciences", code="SCI-DE"
        )
        cls.dept_gone = Department.objects.create(
            school=cls.school, name="Letters", code="LET-DE"
        )
        now = timezone.now()
        # Tombstone for a row that is still live: the delete never took effect here.
        SyncTombstone.objects.create(
            school=cls.school, entity_type="department",
            local_pk=str(cls.dept_live.pk), deleted_at=now, origin="cloud-pull",
        )
        # Tombstone for a row with ledger evidence, then really deleted: data loss.
        SyncTombstone.objects.create(
            school=cls.school, entity_type="department",
            local_pk=str(cls.dept_gone.pk), deleted_at=now, origin="cloud-pull",
        )
        SyncApplyLedger.objects.create(
            school=cls.school, entity_type="department",
            local_pk=str(cls.dept_gone.pk),
        )
        # Tombstone for a pk nothing here ever saw: no row, no ledger.
        SyncTombstone.objects.create(
            school=cls.school, entity_type="department",
            local_pk="999999", deleted_at=now, origin="cloud-pull",
        )
        cls.gone_pk = str(cls.dept_gone.pk)
        cls.dept_gone.delete()

    def _run(self, *args):
        out = StringIO()
        call_command("report_delete_evidence", *args, stdout=out)
        return out.getvalue()

    def test_buckets_close_over_the_real_orm(self):
        import json

        payload = json.loads(self._run("--json"))
        e = payload["entities"]["department"]
        self.assertEqual(e["tombstones"], 3)
        b = e["buckets"]
        self.assertEqual(b["live"], 1)
        self.assertEqual(b["destroyed"], 1)
        # SQLite has no sequence, so the never-seen pk is honestly unknown, never
        # "above high water".
        self.assertEqual(b["pk_above_high_water"], 0)
        self.assertEqual(b["unknown"], 1)
        self.assertEqual(sum(b.values()), e["tombstones"])
        self.assertTrue(e["live_table_readable"])
        self.assertTrue(e["ledger_readable"])
        self.assertIsNone(e["high_water"])
        self.assertEqual(e["destroyed_pks"], [self.gone_pk])

    def test_render_names_the_destroyed_pk_and_prints_the_restore_caveat(self):
        text = self._run()
        self.assertIn("department", text)
        self.assertIn("apply-ledger evidence and no live row: %s" % self.gone_pk, text)
        self.assertIn("That is data loss", text)
        self.assertIn("pg_dump re-seeds sequences", text)
        self.assertIn("could not be placed by either instrument", text)

    def test_fail_on_destroyed_actually_fails(self):
        # The detector must be able to report something -- a gate that cannot go red
        # is not a gate.
        with self.assertRaises(CommandError):
            self._run("--fail-on-destroyed")

    def test_entity_filter_restricts_the_report(self):
        import json

        payload = json.loads(self._run("--json", "--entity", "department"))
        self.assertEqual(list(payload["entities"]), ["department"])

    def test_off_rail_entity_is_unknown_with_a_note_not_a_crash(self):
        import json

        SyncTombstone.objects.create(
            school=self.school, entity_type="not_a_rail_entity",
            local_pk="1", deleted_at=timezone.now(), origin="cloud-pull",
        )
        payload = json.loads(self._run("--json", "--entity", "not_a_rail_entity"))
        e = payload["entities"]["not_a_rail_entity"]
        self.assertIsNone(e["model"])
        self.assertEqual(e["buckets"], {"unknown": 1})
        self.assertIn("not on the rail", e["note"])

    def test_clean_deployment_says_nothing_to_explain(self):
        SyncTombstone.objects.all().delete()
        text = self._run()
        self.assertIn("No tombstones on this deployment", text)
