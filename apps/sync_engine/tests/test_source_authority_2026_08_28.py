"""The join has to survive the disagreement it exists to adjudicate.

An external roster is the only evidence that can settle a conflict the rail cannot: two
nodes holding two values for one column, with nothing about either row to say which is
right. But to ask the roster about a row you must first find that row's line in it, and the
obvious keys are the disputed values themselves.

That is what these tests are mostly about. ``name_tokens`` + ``subset`` exists because a
StudentProfile has ``first_name`` and ``last_name`` and NO ``middle_name``: given a
three-token name, ``first_last`` keeps tokens 0 and -1 while ``last_first`` keeps tokens 1
and 0, so each variant DISCARDS a token the other kept. The two nodes do not hold the same
tokens as each other, and neither holds all of the roster's. What remains true either way
is containment -- and a join that returns a different line depending on which node you ask
would settle conflicts by rewriting rows to another student's data, which is worse than
leaving them pending. So it is asserted directly, under both variants, on the same roster.

The other theme is refusing to answer. A blank cell, a key that reaches two lines, and a
row that cannot be keyed at all are three different things, and each must be distinguished
from "the roster says X" -- because every one of them, mistaken for an answer, writes a
value nobody chose.
"""

from __future__ import annotations

import pathlib
import tempfile

from django.test import SimpleTestCase

from apps.sync_engine import source_authority as sa


class Row:
    """A row as a node holds it after a splitter ran: no middle name to put a token in."""

    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)


def _split(name: str, variant: str) -> tuple[str, str]:
    """Exactly what the two registered transformers keep when there is nowhere to put
    the middle token. Mirrors apps.migration_cloud.transformers.name_split."""
    parts = name.split()
    if len(parts) < 2:
        return (parts[0] if parts else ""), ""
    if variant == "first_last":
        return parts[0], parts[-1]
    return parts[1], parts[0]


class TheMatchersTests(SimpleTestCase):
    def test_exact_is_case_and_whitespace_insensitive(self):
        self.assertEqual(sa._m_exact("  Ada   Lovelace "), sa._m_exact("ada lovelace"))

    def test_alnum_ignores_punctuation(self):
        self.assertEqual(sa._m_alnum("24GIL0202MWIP1"), sa._m_alnum("24-gil-0202-mwip-1"))

    def test_digits_keeps_only_digits(self):
        self.assertEqual(sa._m_digits("+237 677 87 77 78"), "237677877778")

    def test_date_accepts_the_shapes_a_roster_writes(self):
        for raw in ("2012-11-16 00:00:00", "2012-11-16", "2012-11-16T09:30:00"):
            self.assertEqual(sa._m_date(raw), "2012-11-16", raw)

    def test_date_refuses_what_it_cannot_parse(self):
        self.assertIsNone(sa._m_date("sometime in November"))

    def test_a_blank_cell_is_never_a_key(self):
        # "nan" is what a pandas export writes for a missing cell. Treating it as a value
        # would let this module overwrite a real name with the word "nan".
        for raw in ("", "  ", "nan", "NaN", "None", "N/A", "-", "?"):
            self.assertIsNone(sa._m_exact(raw), raw)
            self.assertTrue(sa.is_blank(raw), raw)

    def test_name_tokens_is_order_independent(self):
        self.assertEqual(sa._m_name_tokens("ADA DECLAN LOVELACE"),
                         sa._m_name_tokens("LOVELACE ADA DECLAN"))

    def test_name_tokens_keeps_repeats(self):
        # A set would collapse these two to one key and merge two students.
        self.assertNotEqual(sa._m_name_tokens("ADA ADA LOVELACE"),
                            sa._m_name_tokens("ADA LOVELACE"))

    def test_an_unknown_matcher_is_refused_not_defaulted(self):
        with self.assertRaises(ValueError):
            sa.matcher("fuzzy")


class TheHeaderNormaliserTests(SimpleTestCase):
    def test_humans_retype_headers(self):
        for raw in ("Admission Number", "admission number", "ADMISSION_NUMBER", " Admission-Number "):
            self.assertEqual(sa.normalise_header(raw), "admission_number", raw)


class TheKeySpecTests(SimpleTestCase):
    def test_a_clause_can_read_several_model_fields(self):
        # The roster's one Name column corresponds to two columns on the row.
        spec = sa.KeySpec("Name", "first_name+last_name", "name_tokens", "subset")
        self.assertEqual(spec.fields, ("first_name", "last_name"))
        self.assertEqual(
            spec.of_instance(Row(first_name="ADA", last_name="LOVELACE")),
            ("ada", "lovelace"),
        )

    def test_subset_mode_demands_a_token_matcher(self):
        # Containment over a single opaque string is not containment of anything.
        with self.assertRaises(ValueError):
            sa.KeySpec("Name", "first_name", "exact", "subset")

    def test_an_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            sa.KeySpec("Name", "first_name", "name_tokens", "fuzzy")

    def test_a_clause_naming_no_field_is_refused(self):
        with self.assertRaises(ValueError):
            sa.KeySpec("Name", "  ", "exact")


class TheKeyIsAllOrNothingTests(SimpleTestCase):
    """A partial key would match on the clauses that happened to be present.

    Asserted on the helpers directly. A roster line missing one clause still produces a
    SHORTER tuple if the guard goes, and a shorter tuple simply never matches a full one
    -- so the line silently drops out of the index and the run reports "the roster does
    not mention this student" about a student it does mention. Nothing observable at the
    lookup boundary distinguishes that from an honest miss, which is exactly why the
    contract is pinned here instead.
    """

    SPECS = [
        sa.KeySpec("name", "first_name", "exact"),
        sa.KeySpec("dob", "date_of_birth", "date"),
    ]

    def test_a_complete_row_yields_every_clause(self):
        key = sa.source_key({"name": "ADA", "dob": "2012-01-01"}, self.SPECS)
        self.assertEqual(key, ("ada", "2012-01-01"))

    def test_a_row_missing_one_clause_yields_no_key_at_all(self):
        self.assertIsNone(sa.source_key({"name": "ADA", "dob": ""}, self.SPECS))
        self.assertIsNone(sa.source_key({"name": "", "dob": "2012-01-01"}, self.SPECS))

    def test_an_instance_missing_one_clause_yields_no_key_at_all(self):
        self.assertIsNone(
            sa.instance_key(Row(first_name="ADA", date_of_birth=""), self.SPECS)
        )

    def test_an_unkeyable_row_is_left_out_rather_than_indexed_short(self):
        index = sa.build_index(
            [{"name": "ADA", "dob": ""}, {"name": "GRACE", "dob": "2013-02-02"}],
            self.SPECS,
        )
        self.assertEqual(list(index), [("grace", "2013-02-02")])


class TheJoinMustSurviveTheSplitDisagreementTests(SimpleTestCase):
    """The load-bearing property. Both nodes must reach the SAME roster line."""

    ROSTER = [
        {"name": "ADA DECLAN LOVELACE", "admission_number": "24GIL0001"},
        {"name": "GRACE BRewSTER HOPPER", "admission_number": "24GIL0002"},
        {"name": "ALAN MATHISON TURING", "admission_number": "24GIL0003"},
    ]
    SPECS = [sa.KeySpec("Name", "first_name+last_name", "name_tokens", "subset")]

    def test_both_variants_reach_the_same_line(self):
        index = sa.SourceIndex(self.ROSTER, self.SPECS)
        for row in self.ROSTER:
            found = {}
            for variant in ("first_last", "last_first"):
                first, last = _split(row["name"], variant)
                hits = index.lookup(Row(first_name=first, last_name=last))
                self.assertEqual(len(hits or []), 1, (row["name"], variant, hits))
                found[variant] = hits[0]["admission_number"]
            self.assertEqual(
                found["first_last"], found["last_first"],
                "the two nodes joined to different students: %s" % found,
            )

    def test_the_two_variants_really_do_hold_different_tokens(self):
        # Guards the test above from passing vacuously. If the variants agreed there
        # would be nothing for containment to solve.
        a = _split("ADA DECLAN LOVELACE", "first_last")
        b = _split("ADA DECLAN LOVELACE", "last_first")
        self.assertNotEqual(set(a), set(b))
        self.assertEqual(a[0], b[1], "token 0 is the pivot: first on one side, last on the other")

    def test_a_row_holding_a_token_no_line_carries_matches_nothing(self):
        index = sa.SourceIndex(self.ROSTER, self.SPECS)
        self.assertEqual(index.lookup(Row(first_name="ADA", last_name="BABBAGE")), [])

    def test_tokens_split_across_two_lines_match_NEITHER(self):
        """Containment means ALL the tokens, on ONE line -- not any of them, anywhere.

        Deliberately built from two tokens that BOTH exist in the roster, on DIFFERENT
        lines. The test above cannot prove this: its second token appears nowhere, so the
        postings loop short-circuits on the empty set and reaches the right answer even if
        the tokens were being unioned rather than intersected -- and whether it
        short-circuits at all depends on set iteration order, which varies per process.
        Here neither token is missing, so nothing short-circuits and only real containment
        gives the empty answer. Union would hand back two students and call it a match.
        """
        index = sa.SourceIndex(self.ROSTER, self.SPECS)
        self.assertEqual(index.lookup(Row(first_name="ADA", last_name="TURING")), [])

    def test_a_row_with_no_name_at_all_returns_None_not_empty(self):
        # None means "never asked"; [] means "asked, and the roster does not mention it".
        # Reporting the first as the second invites a conclusion the run never reached.
        index = sa.SourceIndex(self.ROSTER, self.SPECS)
        self.assertIsNone(index.lookup(Row(first_name="", last_name="")))

    def test_two_lines_that_both_contain_the_tokens_are_both_returned(self):
        roster = self.ROSTER + [{"name": "ADA LOVELACE", "admission_number": "24GIL0009"}]
        index = sa.SourceIndex(roster, self.SPECS)
        hits = index.lookup(Row(first_name="ADA", last_name="LOVELACE"))
        self.assertEqual(len(hits), 2, "a winner picked here would be picked by file order")

    def test_file_order_does_not_change_the_answer(self):
        # Both nodes must reach the same values from the same file without exchanging
        # anything, so nothing may depend on the order rows happen to sit in.
        forward = sa.SourceIndex(self.ROSTER, self.SPECS)
        backward = sa.SourceIndex(list(reversed(self.ROSTER)), self.SPECS)
        probe = Row(first_name="ALAN", last_name="TURING")
        self.assertEqual(forward.lookup(probe), backward.lookup(probe))

    def test_an_equal_clause_narrows_a_subset_clause(self):
        roster = [
            {"name": "ADA LOVELACE", "dob": "2012-01-01", "admission_number": "A"},
            {"name": "ADA LOVELACE", "dob": "2013-02-02", "admission_number": "B"},
        ]
        specs = self.SPECS + [sa.KeySpec("dob", "date_of_birth", "date", "equal")]
        index = sa.SourceIndex(roster, specs)
        hits = index.lookup(
            Row(first_name="ADA", last_name="LOVELACE", date_of_birth="2013-02-02")
        )
        self.assertEqual([h["admission_number"] for h in hits], ["B"])

    def test_a_missing_equal_clause_value_is_no_key_not_a_wildcard(self):
        # A partial key would match on the clauses that happened to be present and ignore
        # the one that would have told two students apart.
        specs = self.SPECS + [sa.KeySpec("dob", "date_of_birth", "date", "equal")]
        index = sa.SourceIndex(self.ROSTER, specs)
        self.assertIsNone(
            index.lookup(Row(first_name="ADA", last_name="LOVELACE", date_of_birth=""))
        )

    def test_a_match_with_no_clauses_is_refused(self):
        with self.assertRaises(ValueError):
            sa.SourceIndex(self.ROSTER, [])


class TheFileReaderTests(SimpleTestCase):
    def _tmp(self, name: str, data: bytes) -> pathlib.Path:
        d = pathlib.Path(tempfile.mkdtemp())
        p = d / name
        p.write_bytes(data)
        self.addCleanup(lambda: (p.unlink(missing_ok=True), d.rmdir()))
        return p

    def test_a_bom_does_not_weld_itself_to_the_first_header(self):
        # Every export sampled from this pipeline carries one, and a BOM'd header is a
        # column no mapping can name.
        p = self._tmp("r.csv", "﻿NAME,CODE\nADA,EPS\n".encode("utf-8"))
        rows = sa.load_source_rows(p)
        self.assertEqual(rows, [{"name": "ADA", "code": "EPS"}])

    def test_blank_lines_are_skipped(self):
        p = self._tmp("r.csv", b"NAME,CODE\nADA,EPS\n,\n\nGRACE,PL\n")
        self.assertEqual(len(sa.load_source_rows(p)), 2)

    def test_a_short_row_does_not_raise(self):
        p = self._tmp("r.csv", b"NAME,CODE,DEPT\nADA,EPS\n")
        self.assertEqual(sa.load_source_rows(p), [{"name": "ADA", "code": "EPS"}])

    def test_an_unsupported_format_is_refused_by_name(self):
        p = self._tmp("r.pdf", b"%PDF-1.4")
        with self.assertRaises(ValueError):
            sa.load_source_rows(p)

    def test_a_missing_file_is_refused(self):
        with self.assertRaises(ValueError):
            sa.load_source_rows(pathlib.Path(tempfile.gettempdir()) / "nope-xyz.csv")

    def test_the_fingerprint_follows_the_content(self):
        # It is written into the resolution note: a row must be able to name its evidence.
        a = self._tmp("a.csv", b"NAME\nADA\n")
        b = self._tmp("b.csv", b"NAME\nGRACE\n")
        self.assertEqual(sa.source_fingerprint(a), sa.source_fingerprint(a))
        self.assertNotEqual(sa.source_fingerprint(a), sa.source_fingerprint(b))
        self.assertEqual(len(sa.source_fingerprint(a)), 12)
