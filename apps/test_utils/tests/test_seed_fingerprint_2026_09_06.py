"""Tests for the damaged-test-database guard.

The case that matters is the must-REFUSE one: a table that held seeded rows and
holds none now. The must-stay-SILENT cases matter almost as much, because a
guard that fires on ordinary test residue is a guard someone sets
RMC_ALLOW_DAMAGED_TEST_DB to permanently.

Every test redirects the sidecar to a temp file. Writing the real one would let
a test run rewrite the fingerprint of the developer's own database -- which is
the exact class of silent, persistent damage this module exists to catch.
"""

import json
import tempfile
from pathlib import Path
from unittest import mock

from django.db import connections
from django.test import TestCase

from apps.test_utils import seed_fingerprint


class SeedFingerprintTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sidecar = Path(self._tmp.name) / "fp.json"
        patcher = mock.patch.object(
            seed_fingerprint, "_sidecar_path", return_value=self.sidecar
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = connections["default"]

    # --- must stay silent -------------------------------------------------

    def test_freshly_recorded_database_reports_no_damage(self):
        path = seed_fingerprint.record(self.conn)
        self.assertEqual(path, self.sidecar)
        self.assertEqual(seed_fingerprint.damaged_tables(self.conn), [])

    def test_record_captures_a_non_trivial_number_of_seeded_tables(self):
        """A fingerprint over an empty corpus would make every later check vacuous."""
        seed_fingerprint.record(self.conn)
        seeded = json.loads(self.sidecar.read_text(encoding="utf-8"))["seeded_tables"]
        self.assertGreater(
            len(seeded), 5, "recorded almost nothing; introspection is broken"
        )
        self.assertTrue(all(v > 0 for v in seeded.values()))

    def test_missing_fingerprint_is_unknown_not_clean(self):
        """None and [] are different answers and must not be conflated."""
        self.assertFalse(self.sidecar.exists())
        self.assertIsNone(seed_fingerprint.damaged_tables(self.conn))

    def test_unreadable_fingerprint_is_unknown_not_clean(self):
        self.sidecar.write_text("{not json", encoding="utf-8")
        self.assertIsNone(seed_fingerprint.damaged_tables(self.conn))

    def test_djangos_own_bookkeeping_is_never_fingerprinted(self):
        seed_fingerprint.record(self.conn)
        seeded = json.loads(self.sidecar.read_text(encoding="utf-8"))["seeded_tables"]
        for ignored in seed_fingerprint.IGNORED:
            self.assertNotIn(ignored, seeded)

    # --- must fire --------------------------------------------------------

    def test_emptying_a_seeded_table_is_reported(self):
        """Uses its own table on purpose.

        Emptying a real seeded one (accounts_accessrole) orphans its M2M rows
        and dies on an FK check at transaction end -- which says nothing about
        this guard. The real-schema case is covered by the integration proof:
        a genuine unrestored flush produced 38 reported tables.
        """
        with self.conn.cursor() as cursor:
            cursor.execute("CREATE TABLE fp_probe_empty (id integer primary key)")
            cursor.execute("INSERT INTO fp_probe_empty VALUES (1)")
        seed_fingerprint.record(self.conn)
        self.assertEqual(seed_fingerprint.damaged_tables(self.conn), [])

        with self.conn.cursor() as cursor:
            cursor.execute("DELETE FROM fp_probe_empty")

        self.assertIn("fp_probe_empty", seed_fingerprint.damaged_tables(self.conn))

    def test_a_partial_delete_is_not_damage(self):
        """Ordinary residue must not fire it, or nobody will leave it switched on."""
        with self.conn.cursor() as cursor:
            cursor.execute("CREATE TABLE fp_probe_partial (id integer primary key)")
            cursor.execute("INSERT INTO fp_probe_partial VALUES (1), (2)")
        seed_fingerprint.record(self.conn)
        with self.conn.cursor() as cursor:
            cursor.execute("DELETE FROM fp_probe_partial WHERE id = 1")

        self.assertNotIn("fp_probe_partial", seed_fingerprint.damaged_tables(self.conn))

    def test_a_table_dropped_since_the_fingerprint_is_not_damage(self):
        """A migration may legitimately remove a table; that is not truncation."""
        self.sidecar.write_text(
            json.dumps({"version": 1, "seeded_tables": {"fp_gone_away": 3}}),
            encoding="utf-8",
        )
        self.assertEqual(seed_fingerprint.damaged_tables(self.conn), [])

    # --- the report -------------------------------------------------------

    def test_report_names_the_tables_the_database_and_the_way_out(self):
        text = seed_fingerprint.report(["accounts_permission"], "/tmp/x.sqlite3")
        self.assertIn("accounts_permission", text)
        self.assertIn("/tmp/x.sqlite3", text)
        self.assertIn(seed_fingerprint.ESCAPE_ENV, text)
        self.assertIn("-wal", text)

    def test_report_truncates_a_long_list_but_says_how_many_it_hid(self):
        text = seed_fingerprint.report(["t%02d" % i for i in range(38)], "db")
        self.assertIn("38 table(s)", text)
        self.assertIn("... and 23 more", text)

    def test_escape_hatch_reads_the_environment(self):
        with mock.patch.dict("os.environ", {seed_fingerprint.ESCAPE_ENV: "1"}):
            self.assertTrue(seed_fingerprint.escape_hatch_engaged())
        with mock.patch.dict("os.environ", {seed_fingerprint.ESCAPE_ENV: "0"}):
            self.assertFalse(seed_fingerprint.escape_hatch_engaged())
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(seed_fingerprint.escape_hatch_engaged())
