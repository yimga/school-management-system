"""PASS 2 must be CRYPTOGRAPHIC, and it must be able to FAIL (2026-08-31).

The requirement is a two-pass validation loop: pass 1 confirms the local transaction
committed, pass 2 is an out-of-band SHA-256 comparison of SOURCE versus DESTINATION
records that fails the migration on any divergence, so integrity is PROVEN rather than
inferred. What existed was pass 1 twice.

``verification.verify_landed_counts`` re-queries the tenant and returns
``{domain: int}``. That is a real check and reconciliation already blocks the seal on
it — but it is a COUNT. It agrees with itself when a surname is truncated by the
column width, when a value lands in the wrong column, when a date is coerced, and when
100 rows land as 50 duplicates of one row. The only place the pipeline put a source
record beside a destination record was ``reconciliation._stratified_sample``, and BOTH
of its sides are built from ``artifact.profile["columns"][*]["samples"]`` — the same
in-memory source object, one copy re-keyed through the mapping. It never queries the
tenant at all, so it cannot disagree with itself no matter what landed.

``test_inferred_totals_do_not_verify_2026_08_28`` established the principle these tests
extend: a number the import derived from itself is not a verification. An inferred
control total compares a number to itself; a "side-by-side" built from one dict does
the same thing with more steps. These tests pin the property that closes it — two
INDEPENDENT reads (source bytes re-parsed from the encrypted artifact; landed values
read back out of the tenant database) hashed separately and compared.

The last class here is the one that matters most. A verifier that cannot fail is worse
than no verifier, because it manufactures confidence. So the divergence tests do not
assert on a mock: they PLANT a real defect in the landed row — a truncation, a swapped
column, a deleted row — and require the digest to catch it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.migration_cloud import verification
from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationArtifactBlob,
    MigrationBundle,
)
from apps.migration_cloud.verification import (
    normalise_for_digest,
    record_digest,
    verify_bundle_checksums,
)
from apps.people.models import StudentProfile
from apps.schools.models import School

# One roster, three students. Written as bytes because that is what actually gets
# stored: the verifier re-reads the ENCRYPTED ARTIFACT, not a Python dict we kept.
ROSTER_CSV = (
    b"StudentID,First,Last,DOB,Gender,Stream\r\n"
    b"PS-1001,Ayuk,Nkeng,2010-05-03,M,Form 4A\r\n"
    b"PS-1002,Manka,Fotso,2011-11-17,F,Form 3B\r\n"
    b"PS-1003,Bih,Tanyi,2009-02-28,F,Form 5C\r\n"
)

MAPPINGS = [
    {"source_column": "StudentID", "canonical_field": "external_id"},
    {"source_column": "First", "canonical_field": "first_name"},
    {"source_column": "Last", "canonical_field": "last_name"},
    {"source_column": "DOB", "canonical_field": "date_of_birth"},
    {"source_column": "Gender", "canonical_field": "gender"},
    {"source_column": "Stream", "canonical_field": "section"},
]

# What the CSV above SHOULD produce in the tenant, written independently of the CSV so
# a shared typo cannot make both sides agree by accident.
EXPECTED_LANDED = [
    ("PS-1001", "Ayuk", "Nkeng", dt.date(2010, 5, 3), "M", "Form 4A"),
    ("PS-1002", "Manka", "Fotso", dt.date(2011, 11, 17), "F", "Form 3B"),
    ("PS-1003", "Bih", "Tanyi", dt.date(2009, 2, 28), "F", "Form 5C"),
]


def tenant_schema_name(school) -> str:
    """The schema name a REAL bundle for ``school`` carries.

    Fixtures must stamp this, because a bundle with a BLANK ``schema_name`` is not
    a realistic bundle and Pass 2 deliberately refuses to verify one: on a
    schema-per-tenant connection the landed-row read would fall through to the
    PUBLIC schema, which holds stale copies of the tenant tables, and a false clean
    there is the outcome that purges the encrypted source.

    That refusal is runner-visible. ``manage.py test`` installs the reliable
    runner's single-schema shim (config/reliable_test_runner.py), which adds a
    NO-OP ``set_schema`` to the sqlite wrapper so ``schema_context`` is harmless
    here -- but that also makes ``hasattr(connection, "set_schema")`` true, so the
    connection LOOKS schema-per-tenant and the refusal fires. pytest installs no
    such shim, so it does not. A blank schema_name therefore turned every
    verification below into a silent no-verify under the runner CI actually uses,
    while staying green under pytest. Resolving the school's real schema fixes the
    fixture on both, and keeps these tests asserting VERIFICATION rather than the
    verifier declining to run.
    """
    from apps.migration_cloud.schema_binding import resolve_school_schema_name

    return resolve_school_schema_name(school) or "public"


class DigestPrimitiveTests(SimpleTestCase):
    """The digest itself: field-ordered, collision-resistant, representation-stable."""

    def test_digest_is_a_real_sha256_of_a_field_ordered_pre_image(self):
        """Not a hand-rolled hash and not a dict repr — SHA-256 over a defined string."""
        digest = record_digest({"a": "1", "b": "2"}, ["a", "b"])
        expected_pre_image = "a\x1f1\x1eb\x1f2"
        self.assertEqual(
            digest, hashlib.sha256(expected_pre_image.encode("utf-8")).hexdigest()
        )
        self.assertEqual(len(digest), 64)

    def test_field_order_is_the_argument_not_the_dict(self):
        """Two sides built by different code must not hash differently for that reason.

        The source dict is assembled by the CSV reader and the landed dict by the ORM,
        so their key order differs by construction. If the digest keyed off dict order
        every healthy record would read as a divergence.
        """
        source_shaped = {"last_name": "Nkeng", "first_name": "Ayuk"}
        landed_shaped = {"first_name": "Ayuk", "last_name": "Nkeng"}
        fields = ["first_name", "last_name"]
        self.assertEqual(
            record_digest(source_shaped, fields), record_digest(landed_shaped, fields)
        )

    def test_swapping_two_values_between_columns_changes_the_digest(self):
        """The mis-mapped-column case a row count is structurally blind to."""
        fields = ["first_name", "last_name"]
        right = record_digest({"first_name": "Ayuk", "last_name": "Nkeng"}, fields)
        swapped = record_digest({"first_name": "Nkeng", "last_name": "Ayuk"}, fields)
        self.assertNotEqual(right, swapped)

    def test_a_delimiter_in_a_value_cannot_forge_another_records_pre_image(self):
        """"a|bc" vs "ab|c" — the reason the separators are control characters."""
        fields = ["x", "y"]
        self.assertNotEqual(
            record_digest({"x": "a", "y": "bc"}, fields),
            record_digest({"x": "ab", "y": "c"}, fields),
        )

    def test_truncation_survives_normalisation(self):
        """A column width clipping a surname MUST reach the digest."""
        self.assertNotEqual(
            normalise_for_digest("Nkeng-Ayuk-Ntonifor"),
            normalise_for_digest("Nkeng-Ayuk-Ntonif"),
        )

    def test_case_change_survives_normalisation(self):
        self.assertNotEqual(normalise_for_digest("Ayuk"), normalise_for_digest("ayuk"))

    def test_representation_differences_do_not_manufacture_divergence(self):
        """A date object and its ISO text are the same VALUE, so the same digest."""
        self.assertEqual(
            normalise_for_digest(dt.date(2010, 5, 3)), normalise_for_digest("2010-05-03")
        )
        self.assertEqual(
            normalise_for_digest(Decimal("1.50")), normalise_for_digest(Decimal("1.5"))
        )
        self.assertEqual(normalise_for_digest(" Ayuk "), normalise_for_digest("Ayuk"))

    def test_absent_is_not_the_same_as_empty(self):
        """A NULL column and an empty string are different states; keep them apart."""
        self.assertNotEqual(normalise_for_digest(None), normalise_for_digest(""))

    def test_the_pass_2_entry_points_exist_and_are_sha256(self):
        self.assertEqual(verification.CHECKSUM_ALGORITHM, "sha256")
        self.assertIn("students", verification.domains_with_checksum_verification())

    def test_every_checksummable_domain_names_what_it_does_not_compare(self):
        """A spec that silently drops fields would overclaim what "verified" covers."""
        for domain, excluded in verification.checksum_spec_exclusions().items():
            self.assertTrue(
                excluded, f"{domain} declares no exclusions — say so explicitly"
            )
            for field_name, reason in excluded.items():
                self.assertGreater(
                    len(reason), 20, f"{domain}.{field_name} needs a real reason"
                )


class _RosterFixture(TestCase):
    """A bundle whose SOURCE bytes are real and whose LANDED rows are separately made."""

    def setUp(self):
        self.school = School.objects.create(
            name="Checksum Test College",
            slug="checksum-test-college-20260831",
            subdomain="checksum-test-college-20260831",
            is_active=True,
            is_approved=True,
        )
        self.bundle = MigrationBundle.objects.create(
            label="two-pass-checksum",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="two-pass-checksum-20260831",
            status=BundleStatus.APPLIED,
            school=self.school,
            schema_name=tenant_schema_name(self.school),
            discovery_summary={
                "per_artifact_domain": {"roster.csv": {"domain": "students"}}
            },
            mapping_summary={"per_artifact": {"roster.csv": MAPPINGS}},
        )
        self.artifact = MigrationArtifact.objects.create(
            bundle=self.bundle,
            path_within_bundle="roster.csv",
            filename="roster.csv",
            mime_type="text/csv",
            detected_format="csv",
            encoding="utf-8",
            byte_size=len(ROSTER_CSV),
            sha256=hashlib.sha256(ROSTER_CSV).hexdigest(),
            row_count=3,
        )
        MigrationArtifactBlob.objects.create(
            artifact=self.artifact,
            payload=ROSTER_CSV,
            byte_size=len(ROSTER_CSV),
            sha256=hashlib.sha256(ROSTER_CSV).hexdigest(),
            expires_at=timezone.now() + dt.timedelta(days=7),
        )

    def land_roster(self, rows=None):
        """Create the destination rows the way a correct apply would have."""
        for admission, first, last, dob, gender, section in rows or EXPECTED_LANDED:
            StudentProfile.objects.create(
                school=self.school,
                admission_number=admission,
                first_name=first,
                last_name=last,
                date_of_birth=dob,
                gender=gender,
                section=section,
            )

    def students_result(self, report):
        for d in report.per_domain:
            if d.domain == "students":
                return d
        self.fail("Pass 2 produced no result for the students domain")

    def assert_tally_closes(self, report):
        """Every source record under exactly one NAMED bucket, and they sum."""
        for d in report.per_domain:
            self.assertEqual(
                d.bucketed,
                d.source_records,
                f"{d.domain}: buckets sum to {d.bucketed} but there are "
                f"{d.source_records} source records — a record fell out of the tally",
            )
            self.assertTrue(d.tally_closes)


class ChecksumComparesTwoIndependentReadsTests(_RosterFixture):
    """A faithful import verifies, and the two sides really are read separately."""

    def test_a_faithful_import_verifies(self):
        self.land_roster()
        report = verify_bundle_checksums(self.bundle)
        d = self.students_result(report)
        self.assertEqual(d.source_records, 3)
        self.assertEqual(d.matched, 3)
        self.assertEqual(d.divergent, 0)
        self.assertEqual(d.missing_in_destination, 0)
        self.assert_tally_closes(report)
        self.assertTrue(report.ok)

    def test_the_source_side_is_re_read_from_the_artifact_not_from_the_apply(self):
        """Delete the stored bytes and the pass must go blind — proving it read them.

        If the source side were reconstructed from anything the apply left behind
        (profiler samples, MigrationRun stats, mapping_summary) this would still
        report three records, and that is exactly the failure mode being excluded.
        """
        self.land_roster()
        MigrationArtifactBlob.objects.filter(artifact=self.artifact).delete()
        report = verify_bundle_checksums(self.bundle)
        d = self.students_result(report)
        self.assertEqual(
            d.source_records,
            0,
            "the source side survived deletion of the source — it is not reading it",
        )
        self.assertTrue(d.source_error, "an unreadable source must be REPORTED")
        self.assertFalse(report.complete)

    def test_the_landed_side_is_read_from_the_database(self):
        """With the source intact and nothing landed, every record must be missing."""
        report = verify_bundle_checksums(self.bundle)
        d = self.students_result(report)
        self.assertEqual(d.source_records, 3)
        self.assertEqual(d.matched, 0)
        self.assertEqual(d.missing_in_destination, 3)
        self.assert_tally_closes(report)
        self.assertFalse(report.ok)

    def test_the_landed_read_is_scoped_to_the_bundles_school(self):
        """Another school's identical roster must not satisfy this bundle's lookup.

        Under RLS every tenant shares one schema, so an unscoped read would let a
        neighbouring school's rows verify this migration clean.
        """
        other = School.objects.create(
            name="Neighbour Academy",
            slug="neighbour-academy-20260831",
            subdomain="neighbour-academy-20260831",
            is_active=True,
            is_approved=True,
        )
        for admission, first, last, dob, gender, section in EXPECTED_LANDED:
            StudentProfile.objects.create(
                school=other,
                admission_number=admission,
                first_name=first,
                last_name=last,
                date_of_birth=dob,
                gender=gender,
                section=section,
            )
        report = verify_bundle_checksums(self.bundle)
        d = self.students_result(report)
        self.assertEqual(
            d.missing_in_destination,
            3,
            "another school's rows verified this school's migration",
        )
        self.assertFalse(report.ok)


class PlantedDivergenceTests(_RosterFixture):
    """The detector must actually bite. Each test plants a REAL defect in the database.

    A zero from a verifier nobody has seen fail is not evidence.
    """

    def test_a_truncated_field_is_caught_and_named(self):
        """The case a row count is structurally incapable of seeing."""
        self.land_roster()
        clean = verify_bundle_checksums(self.bundle)
        self.assertEqual(self.students_result(clean).divergent, 0)

        # PLANT: the column clipped the surname.
        row = StudentProfile.objects.get(school=self.school, admission_number="PS-1001")
        row.last_name = "Nken"
        row.save(update_fields=["last_name"])

        report = verify_bundle_checksums(self.bundle)
        d = self.students_result(report)
        self.assertEqual(d.divergent, 1)
        self.assertEqual(d.matched, 2)
        self.assert_tally_closes(report)
        self.assertFalse(report.ok)

        # Enumerated, not merely counted: the record and the field must be named.
        div = d.divergences[0]
        self.assertEqual(div.identity, "PS-1001")
        self.assertEqual(div.kind, "digest_mismatch")
        self.assertIn("last_name", div.field_diffs)
        self.assertEqual(div.field_diffs["last_name"], ["Nkeng", "Nken"])
        self.assertNotEqual(div.source_digest, div.landed_digest)
        self.assertEqual(len(div.source_digest), 64)

        # REMOVE THE PLANT — and confirm the verifier goes green again, so the failure
        # above is attributable to the defect and not to a broken verifier.
        row.last_name = "Nkeng"
        row.save(update_fields=["last_name"])
        restored = verify_bundle_checksums(self.bundle)
        self.assertEqual(self.students_result(restored).divergent, 0)
        self.assertEqual(self.students_result(restored).matched, 3)
        self.assertTrue(restored.ok)

    def test_a_mis_mapped_column_is_caught(self):
        """Values swapped between two columns: same row count, same field count."""
        self.land_roster()
        row = StudentProfile.objects.get(school=self.school, admission_number="PS-1002")
        row.first_name, row.last_name = row.last_name, row.first_name
        row.save(update_fields=["first_name", "last_name"])

        d = self.students_result(verify_bundle_checksums(self.bundle))
        self.assertEqual(d.divergent, 1)
        diffs = d.divergences[0].field_diffs
        self.assertEqual(diffs["first_name"], ["Manka", "Fotso"])
        self.assertEqual(diffs["last_name"], ["Fotso", "Manka"])

    def test_a_coerced_date_is_caught(self):
        """DD/MM read as MM/DD. Both are valid dates, so nothing else complains."""
        self.land_roster()
        row = StudentProfile.objects.get(school=self.school, admission_number="PS-1001")
        row.date_of_birth = dt.date(2010, 3, 5)  # was 2010-05-03
        row.save(update_fields=["date_of_birth"])

        d = self.students_result(verify_bundle_checksums(self.bundle))
        self.assertEqual(d.divergent, 1)
        self.assertIn("date_of_birth", d.divergences[0].field_diffs)

    def test_a_dropped_row_is_caught_and_named(self):
        self.land_roster()
        StudentProfile.objects.filter(
            school=self.school, admission_number="PS-1003"
        ).delete()

        d = self.students_result(verify_bundle_checksums(self.bundle))
        self.assertEqual(d.matched, 2)
        self.assertEqual(d.missing_in_destination, 1)
        self.assert_tally_closes(verify_bundle_checksums(self.bundle))
        self.assertEqual(d.divergences[0].identity, "PS-1003")
        self.assertEqual(d.divergences[0].kind, "missing_in_destination")

    def test_duplicate_rows_cannot_pass_as_a_matching_count(self):
        """Three rows landed, three rows expected — but they are the wrong rows.

        This is precisely what a count comparison reports as 100% parity.
        """
        self.land_roster(
            rows=[
                ("PS-1001", "Ayuk", "Nkeng", dt.date(2010, 5, 3), "M", "Form 4A"),
                ("PS-9998", "Ayuk", "Nkeng", dt.date(2010, 5, 3), "M", "Form 4A"),
                ("PS-9999", "Ayuk", "Nkeng", dt.date(2010, 5, 3), "M", "Form 4A"),
            ]
        )
        self.assertEqual(
            StudentProfile.objects.filter(school=self.school).count(),
            3,
            "the count matches the source — which is the whole problem",
        )
        report = verify_bundle_checksums(self.bundle)
        d = self.students_result(report)
        self.assertEqual(d.matched, 1)
        self.assertEqual(d.missing_in_destination, 2)
        self.assertFalse(report.ok)


class CleanQueueIsNotAnImportTests(_RosterFixture):
    """Zero divergences over zero comparisons is not a verification."""

    def test_a_domain_that_matched_nothing_is_not_ok(self):
        """An artifact whose every row was dismissed leaves exactly this shape.

        The bundle is APPLIED, the quarantine queue is empty, and nothing landed. A
        naive verdict of "no divergences found" would clear it.
        """
        report = verify_bundle_checksums(self.bundle)
        d = self.students_result(report)
        self.assertEqual(d.divergent, 0, "there is nothing to diverge FROM")
        self.assertGreater(d.source_records, 0)
        self.assertEqual(d.matched, 0)
        self.assertFalse(
            report.ok, "a bundle that landed nothing was reported as verified"
        )

    def test_unverifiable_domains_are_named_rather_than_passed(self):
        """A bundle carrying a domain Pass 2 cannot compare must not read as cleared."""
        self.bundle.discovery_summary = {
            "per_artifact_domain": {
                "roster.csv": {"domain": "students"},
                "payslips.csv": {"domain": "payroll"},
            }
        }
        self.bundle.save(update_fields=["discovery_summary"])
        self.land_roster()
        report = verify_bundle_checksums(self.bundle)
        self.assertIn("payroll", report.unverifiable_domains)
        self.assertFalse(
            report.complete, "a bundle with an unverifiable domain is not fully proven"
        )


class ReconcileRefusesToSealOnDivergenceTests(_RosterFixture):
    """A divergence must FAIL the migration, not record a status nobody reads."""

    def test_divergence_blocks_the_seal_and_retains_the_source(self):
        from apps.migration_cloud.reconciliation import reconcile_bundle

        self.land_roster()
        row = StudentProfile.objects.get(school=self.school, admission_number="PS-1001")
        row.section = "Form 9Z"  # PLANT: not what the source says
        row.save(update_fields=["section"])

        report = reconcile_bundle(bundle_id=self.bundle.pk)
        self.bundle.refresh_from_db()

        self.assertEqual(
            self.bundle.status,
            BundleStatus.APPLIED,
            "a bundle whose landed data does not match its source was sealed RECONCILED",
        )
        self.assertTrue(
            MigrationArtifactBlob.objects.filter(artifact=self.artifact).exists(),
            "the encrypted source was purged while the migration was still unproven",
        )

        blocking = [n for n in report.notes if "SHA-256" in n]
        self.assertTrue(blocking, f"no blocking note was recorded; notes={report.notes}")
        # The note carries the identity AND the closing tally, so an operator can act
        # on it without opening a shell.
        self.assertIn("PS-1001", blocking[0])
        self.assertIn("matched", blocking[0])
        self.assertIn("unidentified", blocking[0])

        summary = self.bundle.reconciliation_summary or {}
        checksum = summary.get("checksum_verification") or {}
        self.assertTrue(checksum.get("ran"))
        self.assertFalse(checksum.get("ok"))
        self.assertEqual(checksum.get("algorithm"), "sha256")
        self.assertEqual(checksum.get("total_divergent"), 1)

    def test_the_verdict_is_recorded_even_when_it_passes(self):
        """A clean pass must leave evidence, not just an absence of complaints."""
        from apps.migration_cloud.reconciliation import reconcile_bundle

        self.land_roster()
        reconcile_bundle(bundle_id=self.bundle.pk)
        self.bundle.refresh_from_db()
        checksum = (self.bundle.reconciliation_summary or {}).get(
            "checksum_verification"
        ) or {}
        self.assertTrue(checksum.get("ran"))
        self.assertTrue(checksum.get("ok"))
        self.assertEqual(checksum.get("total_matched"), 3)
        per_domain = {d["domain"]: d for d in checksum.get("per_domain") or []}
        self.assertTrue(per_domain["students"]["tally_closes"])


class CommandExitCodeTests(_RosterFixture):
    """The operator entry point must exit NON-ZERO on divergence.

    A verifier whose failure path returns 0 is decoration: no deploy script, CI job or
    cron wrapper can act on it. The three-valued split matters too — "I proved this is
    broken" (1) and "I could not check" (2) are different answers, and collapsing them
    is how "no divergences found" starts meaning "the source was unreadable".
    """

    def _run(self, **kwargs):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        try:
            call_command(
                "verify_migration_checksums", bundle=self.bundle.pk, stdout=out, **kwargs
            )
        except SystemExit as exc:  # non-zero verdict
            return int(exc.code), out.getvalue()
        return 0, out.getvalue()

    def test_a_faithful_import_exits_zero_and_shows_a_closing_tally(self):
        self.land_roster()
        code, output = self._run()
        self.assertEqual(code, 0, output)
        self.assertIn("VERIFIED", output)
        # Every bucket named, and the sum printed — never a partial breakdown.
        self.assertIn("3 source = 3 matched + 0 divergent + 0 missing", output)
        self.assertIn("unidentified", output)
        self.assertIn("(sum=3)", output)

    def test_a_planted_divergence_exits_one_and_names_the_record(self):
        self.land_roster()
        row = StudentProfile.objects.get(school=self.school, admission_number="PS-1001")
        row.last_name = "Nken"  # PLANT
        row.save(update_fields=["last_name"])

        code, output = self._run()
        self.assertEqual(code, 1, output)
        self.assertIn("DIVERGENCE", output)
        self.assertIn("PS-1001", output)
        self.assertIn("last_name", output)

        row.last_name = "Nkeng"  # PLANT REMOVED
        row.save(update_fields=["last_name"])
        code_after, output_after = self._run()
        self.assertEqual(
            code_after,
            0,
            f"the verifier stayed red after the defect was removed: {output_after}",
        )

    def test_an_unreadable_source_exits_two_not_zero(self):
        """Could-not-check must never be reported as checked-and-clean."""
        self.land_roster()
        MigrationArtifactBlob.objects.filter(artifact=self.artifact).delete()
        code, output = self._run()
        self.assertEqual(code, 2, output)
        self.assertIn("NOT VERIFIED", output)

    def test_a_bundle_that_landed_nothing_exits_one(self):
        code, output = self._run()
        self.assertEqual(code, 1, output)


# ---------------------------------------------------------------------------
# PER-DOMAIN PLANT PROOFS
# ---------------------------------------------------------------------------
# One spec per domain, and one PLANTED DEFECT per domain. Not one plant standing in
# for all of them: a spec naming a column that does not exist, or an identity that
# never matches, verifies precisely nothing while reporting a serene zero — and a
# shared plant on the students domain would not notice. Each case below runs the real
# management command three times: clean (exit 0), planted (exit 1, and the offending
# record and field are named in the output), restored (exit 0 again, so the red is
# attributable to the defect and not to a verifier that is simply broken).
#
# For a VALUE domain the plant is a wrong value in a landed column.
# For a PRESENCE domain (no payload column the lander copies verbatim beside its key)
# the only defect the digest can see is the record failing to arrive, so the plant is
# a deleted row. That is stated in the assertion messages, not glossed.


class _PlantCycleMixin(TestCase):
    """Machinery for a per-domain clean -> planted -> restored proof."""

    def _make_bundle(self, *, domain, csv_bytes, mappings, label):
        bundle = MigrationBundle.objects.create(
            label=label,
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"pass2-{label}",
            status=BundleStatus.APPLIED,
            school=self.school,
            schema_name=tenant_schema_name(self.school),
            discovery_summary={
                "per_artifact_domain": {f"{domain}.csv": {"domain": domain}}
            },
            mapping_summary={"per_artifact": {f"{domain}.csv": mappings}},
        )
        artifact = MigrationArtifact.objects.create(
            bundle=bundle,
            path_within_bundle=f"{domain}.csv",
            filename=f"{domain}.csv",
            mime_type="text/csv",
            detected_format="csv",
            encoding="utf-8",
            byte_size=len(csv_bytes),
            sha256=hashlib.sha256(csv_bytes).hexdigest(),
            row_count=csv_bytes.count(b"\n") - 1,
        )
        MigrationArtifactBlob.objects.create(
            artifact=artifact,
            payload=csv_bytes,
            byte_size=len(csv_bytes),
            sha256=hashlib.sha256(csv_bytes).hexdigest(),
            expires_at=timezone.now() + dt.timedelta(days=7),
        )
        return bundle

    def _cmd(self, bundle):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        try:
            call_command(
                "verify_migration_checksums", bundle=bundle.pk, stdout=out
            )
        except SystemExit as exc:
            return int(exc.code), out.getvalue()
        return 0, out.getvalue()

    def assert_plant_bites(
        self, *, domain, csv_bytes, mappings, land, plant, expect_tokens, depth
    ):
        bundle = self._make_bundle(
            domain=domain, csv_bytes=csv_bytes, mappings=mappings, label=domain
        )
        # Exposed so a fixture can attach bundle-scoped audit rows (the grades
        # case has to write the MigrationIdMapping the lander would have written).
        self.bundle_under_test = bundle
        land()

        code, out = self._cmd(bundle)
        self.assertEqual(code, 0, f"[{domain}] a faithful import did not verify:\n{out}")
        self.assertIn(f"{domain} [{depth}]", out, f"[{domain}] wrong depth label:\n{out}")
        self.assertIn("0 divergent", out)
        # The spec must actually be comparing something, or the green above is empty.
        self.assertNotIn("(none)", out, f"[{domain}] no comparable field resolved:\n{out}")

        undo = plant()
        code, out = self._cmd(bundle)
        self.assertEqual(
            code,
            1,
            f"[{domain}] a PLANTED defect was not caught — this spec verifies "
            f"nothing:\n{out}",
        )
        for token in expect_tokens:
            self.assertIn(
                token, out, f"[{domain}] output did not name {token!r}:\n{out}"
            )

        undo()
        code, out = self._cmd(bundle)
        self.assertEqual(
            code,
            0,
            f"[{domain}] stayed red after the plant was removed — the failure above "
            f"was the verifier, not the defect:\n{out}",
        )


class _TenantFixture(_PlantCycleMixin):
    """School + the shared parents the heavier destination models require."""

    def setUp(self):
        self.school = School.objects.create(
            name="Pass2 Domain College",
            slug="pass2-domain-college-20260831",
            subdomain="pass2-domain-college-20260831",
            is_active=True,
            is_approved=True,
        )

    # --- lazily-built shared parents ---------------------------------------

    def student(self, admission="PS-2001", first="Ayuk", last="Nkeng"):
        from apps.people.models import StudentProfile

        obj, _ = StudentProfile.objects.get_or_create(
            school=self.school,
            admission_number=admission,
            defaults={"first_name": first, "last_name": last},
        )
        return obj

    def user(self, username):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        obj, _ = User.objects.get_or_create(
            username=username, defaults={"email": f"{username}@example.test"}
        )
        return obj

    def academic_year(self):
        from apps.academics.models import AcademicYear

        obj, _ = AcademicYear.objects.get_or_create(
            school=self.school,
            name="2025-2026",
            defaults={
                "start_date": dt.date(2025, 9, 1),
                "end_date": dt.date(2026, 7, 31),
            },
        )
        return obj

    def department(self):
        from apps.academics.models import Department

        obj, _ = Department.objects.get_or_create(
            school=self.school, name="General", defaults={"code": "DPT-GEN"}
        )
        return obj

    def classroom(self, name="Form 4A"):
        from apps.academics.models import Classroom

        obj, _ = Classroom.objects.get_or_create(
            school=self.school,
            name=name,
            defaults={
                "code": f"CLS-{name.replace(' ', '')}",
                "academic_year": self.academic_year(),
                "department": self.department(),
            },
        )
        return obj


class ValueDomainPlantTests(_TenantFixture):
    """Domains where a real payload column is compared: plant a WRONG VALUE."""

    def test_finance_catches_a_wrong_invoice_amount(self):
        from apps.finance.models import Invoice
        from apps.finance.provisioning_seed import ensure_tenant_compliance_profile

        csv = (
            b"Ref,Amount,Due,Issued,Desc\r\n"
            b"INV-9001,450000,2026-01-31,2026-01-05,Term 1 tuition\r\n"
            b"INV-9002,125000,2026-02-28,2026-02-01,Bus levy\r\n"
        )
        mappings = [
            {"source_column": "Ref", "canonical_field": "reference"},
            {"source_column": "Amount", "canonical_field": "amount"},
            {"source_column": "Due", "canonical_field": "due_date"},
            {"source_column": "Issued", "canonical_field": "issue_date"},
            {"source_column": "Desc", "canonical_field": "description"},
        ]

        def land():
            profile = ensure_tenant_compliance_profile(self.school)
            for ref, amt, due, iss, desc in (
                ("INV-9001", "450000", dt.date(2026, 1, 31), dt.date(2026, 1, 5), "Term 1 tuition"),
                ("INV-9002", "125000", dt.date(2026, 2, 28), dt.date(2026, 2, 1), "Bus levy"),
            ):
                Invoice.objects.create(
                    school=self.school, profile=profile, student=self.student(),
                    reference=ref, total_amount=Decimal(amt),
                    due_date=due, issued_date=iss, notes=desc,
                )

        def plant():
            inv = Invoice.objects.get(school=self.school, reference="INV-9001")
            original = inv.total_amount
            inv.total_amount = Decimal("45000")  # a lost zero: 450,000 -> 45,000
            inv.save(update_fields=["total_amount"])

            def undo():
                inv.total_amount = original
                inv.save(update_fields=["total_amount"])

            return undo

        self.assert_plant_bites(
            domain="finance", csv_bytes=csv, mappings=mappings, land=land,
            plant=plant, depth="value",
            expect_tokens=["INV-9001", "total_amount", "450000", "45000"],
        )

    def test_attendance_catches_a_rewritten_remark(self):
        from apps.academics.models import Attendance

        csv = (
            b"StudentID,Date,Note\r\n"
            b"PS-2001,2026-01-12,Arrived after assembly\r\n"
            b"PS-2001,2026-01-13,Medical appointment\r\n"
        )
        mappings = [
            {"source_column": "StudentID", "canonical_field": "student_external_id"},
            {"source_column": "Date", "canonical_field": "date"},
            {"source_column": "Note", "canonical_field": "notes"},
        ]

        def land():
            for day, note in (
                (dt.date(2026, 1, 12), "Arrived after assembly"),
                (dt.date(2026, 1, 13), "Medical appointment"),
            ):
                Attendance.objects.create(
                    school=self.school, student=self.student(),
                    classroom=self.classroom(), date=day, remarks=note,
                )

        def plant():
            row = Attendance.objects.get(student=self.student(), date=dt.date(2026, 1, 12))
            original = row.remarks
            row.remarks = "Arrived after assembl"  # a one-character clip
            row.save(update_fields=["remarks"])

            def undo():
                row.remarks = original
                row.save(update_fields=["remarks"])

            return undo

        self.assert_plant_bites(
            domain="attendance", csv_bytes=csv, mappings=mappings, land=land,
            plant=plant, depth="value",
            expect_tokens=["PS-2001", "remarks", "Arrived after assembly"],
        )

    def test_guardians_catches_a_wrong_address(self):
        from apps.people.models import StudentGuardian

        csv = (
            b"StudentID,Email,Phone,WhatsApp,Address\r\n"
            b"PS-2001,ma.fotso@example.test,+237670000001,+237670000001,12 Rue Bastos Yaounde\r\n"
        )
        mappings = [
            {"source_column": "StudentID", "canonical_field": "student_external_id"},
            {"source_column": "Email", "canonical_field": "email"},
            {"source_column": "Phone", "canonical_field": "phone"},
            {"source_column": "WhatsApp", "canonical_field": "whatsapp_number"},
            {"source_column": "Address", "canonical_field": "address"},
        ]

        def land():
            StudentGuardian.objects.create(
                student=self.student(),
                guardian_user=self.user("ma.fotso"),
                email="ma.fotso@example.test",
                phone="+237670000001",
                whatsapp_number="+237670000001",
                address="12 Rue Bastos Yaounde",
            )

        def plant():
            g = StudentGuardian.objects.get(student=self.student())
            original = g.address
            g.address = "12 Rue Bastos Douala"  # wrong city
            g.save(update_fields=["address"])

            def undo():
                g.address = original
                g.save(update_fields=["address"])

            return undo

        self.assert_plant_bites(
            domain="guardians", csv_bytes=csv, mappings=mappings, land=land,
            plant=plant, depth="value",
            expect_tokens=["address", "Yaounde", "Douala"],
        )

    def test_events_catches_a_rewritten_description(self):
        from apps.school_events.models import SchoolEvent

        csv = (
            b"Title,Start,Description\r\n"
            b"Founders Day,2026-03-15,Whole-school assembly and prize giving\r\n"
        )
        mappings = [
            {"source_column": "Title", "canonical_field": "title"},
            {"source_column": "Start", "canonical_field": "starts_at"},
            {"source_column": "Description", "canonical_field": "description"},
        ]

        def land():
            SchoolEvent.objects.create(
                school=self.school,
                title="Founders Day",
                slug="founders-day-2026-03-15",
                description="Whole-school assembly and prize giving",
                start_at=dt.datetime.combine(dt.date(2026, 3, 15), dt.time.min),
            )

        def plant():
            ev = SchoolEvent.objects.get(school=self.school, slug="founders-day-2026-03-15")
            original = ev.description
            ev.description = "Whole-school assembly"
            ev.save(update_fields=["description"])

            def undo():
                ev.description = original
                ev.save(update_fields=["description"])

            return undo

        self.assert_plant_bites(
            domain="events", csv_bytes=csv, mappings=mappings, land=land,
            plant=plant, depth="value",
            expect_tokens=["founders-day-2026-03-15", "description", "prize giving"],
        )

    def test_library_catches_a_wrong_author(self):
        from apps.schoolops.models import LibraryItem

        csv = (
            b"ISBN,Title,Author\r\n"
            b"9780143105985,Things Fall Apart,Chinua Achebe\r\n"
        )
        mappings = [
            {"source_column": "ISBN", "canonical_field": "isbn"},
            {"source_column": "Title", "canonical_field": "title"},
            {"source_column": "Author", "canonical_field": "author"},
        ]

        def land():
            LibraryItem.objects.create(
                school=self.school, isbn="9780143105985",
                title="Things Fall Apart", author="Chinua Achebe",
            )

        def plant():
            item = LibraryItem.objects.get(school=self.school, isbn="9780143105985")
            original = item.author
            item.author = "Chinua Achebi"
            item.save(update_fields=["author"])

            def undo():
                item.author = original
                item.save(update_fields=["author"])

            return undo

        self.assert_plant_bites(
            domain="library", csv_bytes=csv, mappings=mappings, land=land,
            plant=plant, depth="value",
            expect_tokens=["9780143105985", "author", "Achebe"],
        )

    def test_cafeteria_catches_a_wrong_price(self):
        from apps.schoolops.models import CanteenMeal

        csv = b"Meal,Price\r\nHot Lunch,1500\r\nBreakfast,750\r\n"
        mappings = [
            {"source_column": "Meal", "canonical_field": "meal_name"},
            {"source_column": "Price", "canonical_field": "price"},
        ]

        def land():
            for name, price in (("Hot Lunch", "1500"), ("Breakfast", "750")):
                CanteenMeal.objects.create(
                    school=self.school, name=name, price=Decimal(price)
                )

        def plant():
            meal = CanteenMeal.objects.get(school=self.school, name="Hot Lunch")
            original = meal.price
            meal.price = Decimal("15000")
            meal.save(update_fields=["price"])

            def undo():
                meal.price = original
                meal.save(update_fields=["price"])

            return undo

        self.assert_plant_bites(
            domain="cafeteria", csv_bytes=csv, mappings=mappings, land=land,
            plant=plant, depth="value",
            expect_tokens=["Hot Lunch", "price", "1500"],
        )

    def test_transcripts_catches_a_rewritten_artifact_ref(self):
        from apps.migration_cloud.verification import (
            _transcripts_artifact_type,
            _transcripts_verification_hash,
        )
        from apps.people.models import StudentPassport, TranscriptVaultItem

        csv = (
            b"StudentID,Year,Term,Subject,Grade,Type,Ref,Issued\r\n"
            b"PS-2001,2025-2026,Term 1,MATH,A,transcript,vault://ps2001/math/t1,2026-02-01\r\n"
        )
        mappings = [
            {"source_column": "StudentID", "canonical_field": "student_external_id"},
            {"source_column": "Year", "canonical_field": "academic_year"},
            {"source_column": "Term", "canonical_field": "term"},
            {"source_column": "Subject", "canonical_field": "subject_code"},
            {"source_column": "Grade", "canonical_field": "final_grade"},
            {"source_column": "Type", "canonical_field": "artifact_type"},
            {"source_column": "Ref", "canonical_field": "artifact_ref"},
            {"source_column": "Issued", "canonical_field": "issued_at"},
        ]
        source_row = {
            "student_external_id": "PS-2001",
            "academic_year": "2025-2026",
            "term": "Term 1",
            "subject_code": "MATH",
            "final_grade": "A",
            "artifact_type": "transcript",
        }

        def land():
            student = self.student()
            passport = StudentPassport.objects.create()
            TranscriptVaultItem.objects.create(
                passport=passport,
                issuing_school=self.school,
                student_profile=student,
                artifact_type=_transcripts_artifact_type(source_row),
                verification_hash=_transcripts_verification_hash(source_row),
                artifact_ref="vault://ps2001/math/t1",
                issued_at=dt.date(2026, 2, 1),
            )

        def plant():
            item = TranscriptVaultItem.objects.get(student_profile=self.student())
            original = item.artifact_ref
            item.artifact_ref = "vault://ps2001/math/t2"  # points at the wrong document
            item.save(update_fields=["artifact_ref"])

            def undo():
                item.artifact_ref = original
                item.save(update_fields=["artifact_ref"])

            return undo

        self.assert_plant_bites(
            domain="transcripts", csv_bytes=csv, mappings=mappings, land=land,
            plant=plant, depth="value",
            expect_tokens=["artifact_ref", "math/t1", "math/t2"],
        )

    def test_grades_catches_a_wrong_score_through_the_landers_id_map(self):
        from apps.academics.models import Specialty, Subject, SubjectAssignment, Term
        from apps.evals.models import Evaluation
        from apps.migration_cloud.models import MigrationIdMapping
        from apps.people.models import TeacherProfile

        csv = (
            b"StudentID,Term,Subject,Seq1,Exam,Letter\r\n"
            b"PS-2001,Term 1,MATH,14.5,16,B\r\n"
        )
        mappings = [
            {"source_column": "StudentID", "canonical_field": "student_external_id"},
            {"source_column": "Term", "canonical_field": "term"},
            {"source_column": "Subject", "canonical_field": "subject_code"},
            {"source_column": "Seq1", "canonical_field": "seq1_score"},
            {"source_column": "Exam", "canonical_field": "exam_score"},
            {"source_column": "Letter", "canonical_field": "grade_letter"},
        ]
        self._evaluation = None

        def land():
            year = self.academic_year()
            term, _ = Term.objects.get_or_create(
                academic_year=year,
                name="Term 1",
                defaults={
                    "start_date": dt.date(2025, 9, 1),
                    "end_date": dt.date(2025, 12, 20),
                },
            )
            subject, _ = Subject.objects.get_or_create(school=self.school, name="MATH")
            specialty, _ = Specialty.objects.get_or_create(
                school=self.school,
                name="General",
                defaults={"code": "SPC-GEN", "department": self.department()},
            )
            assignment, _ = SubjectAssignment.objects.get_or_create(
                school=self.school, academic_year=year, term=term,
                classroom=self.classroom(), specialty=specialty, subject=subject,
            )
            teacher, _ = TeacherProfile.objects.get_or_create(
                user=self.user("teacher.math"), school=self.school
            )
            # Evaluation.clean() requires the student to sit in the assignment's
            # year, classroom and specialty.
            student = self.student()
            student.academic_year = year
            student.classroom = self.classroom()
            student.specialty = specialty
            student.save(
                update_fields=["academic_year", "classroom", "specialty"]
            )
            ev = Evaluation.objects.create(
                school=self.school, academic_year=year, term=term,
                subject_assignment=assignment, student=student, teacher=teacher,
                seq1_score=Decimal("14.5"), exam_score=Decimal("16"), letter_grade="B",
            )
            self._evaluation = ev
            # The pointer the grades lander records for this row, verbatim.
            MigrationIdMapping.objects.create(
                bundle=self.bundle_under_test,
                legacy_namespace="unknown_custom",
                legacy_id="PS-2001:Term 1:MATH",
                canonical_model="apps.evals.models.Evaluation",
                school_id=self.school.pk,
                domain="grades",
                canonical_pk=str(ev.pk),
            )

        def plant():
            ev = self._evaluation
            original = ev.seq1_score
            ev.seq1_score = Decimal("4.5")  # 14.5 -> 4.5: a dropped leading digit
            ev.save(update_fields=["seq1_score"])

            def undo():
                ev.seq1_score = original
                ev.save(update_fields=["seq1_score"])

            return undo

        self.assert_plant_bites(
            domain="grades", csv_bytes=csv, mappings=mappings, land=land,
            plant=plant, depth="value",
            expect_tokens=["PS-2001:Term 1:MATH", "seq1_score", "14.5"],
        )


class PresenceDomainPlantTests(_TenantFixture):
    """Domains with no verbatim payload column: plant a MISSING RECORD.

    The digest here covers the identity alone, so the only defect it can see is the
    record failing to arrive. That is still strictly more than a row count can do —
    a count of 3 is satisfied by three copies of the wrong row — but it is not value
    verification, and every one of these asserts the ``presence`` label is printed so
    an operator is never told more than was proved.
    """

    def test_academics_catches_a_subject_that_never_landed(self):
        from apps.academics.models import Subject

        csv = b"Subject\r\nMathematics\r\nBiology\r\nHistory\r\n"
        mappings = [{"source_column": "Subject", "canonical_field": "subject_name"}]

        def land():
            for name in ("Mathematics", "Biology", "History"):
                Subject.objects.create(school=self.school, name=name)

        def plant():
            obj = Subject.objects.get(school=self.school, name="Biology")
            pk = obj.pk
            obj.delete()

            def undo():
                Subject.objects.create(pk=pk, school=self.school, name="Biology")

            return undo

        self.assert_plant_bites(
            domain="academics", csv_bytes=csv, mappings=mappings, land=land,
            plant=plant, depth="presence",
            expect_tokens=["MISSING", "Biology"],
        )

    def test_staff_catches_a_teacher_that_never_landed(self):
        from apps.people.models import TeacherProfile

        csv = b"StaffID\r\nSTF-100\r\nSTF-101\r\n"
        mappings = [
            {"source_column": "StaffID", "canonical_field": "staff_external_id"}
        ]

        def land():
            for i, staff_id in enumerate(("STF-100", "STF-101")):
                TeacherProfile.objects.create(
                    user=self.user(f"staff{i}"), school=self.school, staff_id=staff_id
                )

        def plant():
            obj = TeacherProfile.objects.get(school=self.school, staff_id="STF-101")
            obj.staff_id = "STF-999"  # landed under the wrong identity
            obj.save(update_fields=["staff_id"])

            def undo():
                obj.staff_id = "STF-101"
                obj.save(update_fields=["staff_id"])

            return undo

        self.assert_plant_bites(
            domain="staff", csv_bytes=csv, mappings=mappings, land=land,
            plant=plant, depth="presence",
            expect_tokens=["MISSING", "STF-101"],
        )

    def test_sections_catches_a_classroom_that_never_landed(self):
        from apps.academics.models import Classroom

        csv = b"Name\r\nForm 4A\r\nForm 5B\r\n"
        mappings = [{"source_column": "Name", "canonical_field": "name"}]

        def land():
            self.classroom("Form 4A")
            self.classroom("Form 5B")

        def plant():
            obj = Classroom.objects.get(school=self.school, name="Form 5B")
            obj.name = "Form 5B (old)"
            obj.save(update_fields=["name"])

            def undo():
                obj.name = "Form 5B"
                obj.save(update_fields=["name"])

            return undo

        self.assert_plant_bites(
            domain="sections", csv_bytes=csv, mappings=mappings, land=land,
            plant=plant, depth="presence",
            expect_tokens=["MISSING", "Form 5B"],
        )

    def test_transport_catches_a_route_that_never_landed(self):
        from apps.schoolops.models import Route

        csv = b"Route\r\nBastos Loop\r\nMvan Express\r\n"
        mappings = [{"source_column": "Route", "canonical_field": "route_name"}]

        def land():
            for name in ("Bastos Loop", "Mvan Express"):
                Route.objects.create(school=self.school, name=name)

        def plant():
            obj = Route.objects.get(school=self.school, name="Mvan Express")
            pk = obj.pk
            obj.delete()

            def undo():
                Route.objects.create(pk=pk, school=self.school, name="Mvan Express")

            return undo

        self.assert_plant_bites(
            domain="transport", csv_bytes=csv, mappings=mappings, land=land,
            plant=plant, depth="presence",
            expect_tokens=["MISSING", "Mvan Express"],
        )


class CoverageIsQueryableTests(SimpleTestCase):
    """The verified/unverified split is a fact in the code, not a claim in a report."""

    def test_every_uncovered_domain_carries_a_written_reason(self):
        """A domain missing from BOTH lists would read as verified to anyone auditing."""
        cov = verification.checksum_coverage()
        reasons = cov["unverifiable_reasons"]
        for domain in cov["checksum_unverified_domains"]:
            self.assertIn(
                domain,
                reasons,
                f"{domain} is counted but not checksummed, and says nothing about why",
            )
            self.assertGreater(
                len(reasons[domain]),
                60,
                f"{domain}'s reason is too thin to audit",
            )

    def test_the_split_adds_up(self):
        cov = verification.checksum_coverage()
        self.assertEqual(
            cov["value_verified"] + cov["presence_verified"] + cov["checksum_unverified"],
            cov["count_verified"],
            "the coverage split does not account for every countable domain",
        )

    def test_presence_domains_are_not_advertised_as_value_verified(self):
        """A digest over the identity alone is circular; it must never claim more."""
        for domain in verification.checksum_coverage()["presence_verified_domains"]:
            spec = verification._CHECKSUM_SPECS[domain]
            self.assertEqual(verification.spec_verification_depth(spec), "presence")

    def test_value_domains_compare_a_column_outside_their_identity(self):
        """Otherwise the digest is found-by-then-compared-to the same value."""
        import importlib as _il

        for domain in verification.checksum_coverage()["value_verified_domains"]:
            spec = verification._CHECKSUM_SPECS[domain]
            if spec.id_map_domain:
                self.assertTrue(spec.fields, f"{domain} compares nothing")
                continue
            model = getattr(_il.import_module(spec.module_path), spec.model_attr)
            identity = set(spec.identity_columns(model))
            self.assertTrue(
                set(spec.fields) - identity,
                f"{domain} claims value verification but only hashes its own identity",
            )


class BlankSchemaNameIsRefusedNotVerifiedTests(_RosterFixture):
    """The public-schema guard, pinned independently of which runner is in play.

    This is the defect that made the suite green under pytest and red under
    ``manage.py test``: whether the guard fires depends on
    ``hasattr(connection, "set_schema")``, and that attribute is absent on the raw
    sqlite wrapper but PRESENT under ``manage.py test``, where the reliable runner
    installs a no-op shim (config/reliable_test_runner.py). So the test patches the
    attribute in explicitly and pins the GUARD rather than the lane it happens to
    run on.

    Both halves matter. Asserting only the refusal would be the same class of defect
    as the count-based Pass 2 this work replaced: a suite that proves the verifier
    declines to verify is green while testing nothing. The second half therefore
    requires the SAME bundle, with a real schema stamped, to actually verify.
    """

    def _schema_per_tenant_connection(self):
        """Make the connection look schema-per-tenant on EITHER runner.

        Patches the same FOUR attributes on the same class that
        config/reliable_test_runner.py's shim patches -- ``type(connections[alias])``,
        the real DatabaseWrapper. Two traps live here:

        * ``set_schema`` alone is not enough. It is what the guard tests for, but
          entering ``schema_context`` afterwards also touches ``tenant`` /
          ``set_tenant``, so a partial patch kills the positive half of this pair
          inside the context manager instead of verifying.
        * ``django.db.connection`` is a ConnectionProxy, so ``type(connection)`` is
          the PROXY class. Patching that satisfies ``hasattr`` (the proxy forwards)
          while ``schema_context`` -- which resolves ``connections[alias]`` directly
          -- still sees a wrapper with no ``set_schema``.
        """
        import contextlib
        from unittest import mock

        from django.db import DEFAULT_DB_ALIAS, connections

        cls = type(connections[DEFAULT_DB_ALIAS])

        def _noop(self, *args, **kwargs):
            return None

        stack = contextlib.ExitStack()
        for attr, value in (
            ("set_schema", _noop),
            ("set_schema_to_public", _noop),
            ("set_tenant", _noop),
            ("tenant", None),
        ):
            stack.enter_context(
                mock.patch.object(cls, attr, create=True, new=value)
            )
        return stack

    def test_a_blank_schema_name_refuses_rather_than_reading_public(self):
        self.land_roster()
        self.bundle.schema_name = ""
        self.bundle.save(update_fields=["schema_name"])

        with self._schema_per_tenant_connection():
            report = verify_bundle_checksums(self.bundle)

        self.assertEqual(
            report.per_domain,
            [],
            "Pass 2 compared rows it had no business reading — on a schema-per-tenant "
            "connection a blank schema_name resolves to PUBLIC, which holds stale "
            "copies of the tenant tables",
        )
        self.assertIn("*", report.unverifiable_domains)
        self.assertFalse(report.complete)
        self.assertTrue(
            any("PUBLIC schema" in note for note in report.notes),
            f"the refusal was not explained to the operator: {report.notes}",
        )

    def test_the_same_bundle_verifies_once_it_carries_its_real_schema(self):
        """The guard must DISCRIMINATE, not refuse everything.

        Without this half the test above would still pass if Pass 2 had been broken
        into refusing unconditionally.
        """
        self.land_roster()
        self.assertTrue(
            self.bundle.schema_name,
            "the fixture must stamp the schema a real bundle carries",
        )

        with self._schema_per_tenant_connection():
            report = verify_bundle_checksums(self.bundle)

        d = self.students_result(report)
        self.assertEqual(d.matched, 3)
        self.assertEqual(d.divergent, 0)
        self.assertTrue(report.ok)

    def test_the_command_reports_a_refusal_as_could_not_verify_not_as_clean(self):
        """Exit 2, never 0. "I could not check" must not read as "I checked"."""
        self.land_roster()
        self.bundle.schema_name = ""
        self.bundle.save(update_fields=["schema_name"])

        with self._schema_per_tenant_connection():
            code, output = self._cmd_for(self.bundle)

        self.assertEqual(code, 2, output)
        self.assertIn("NOT VERIFIED", output)

    def _cmd_for(self, bundle):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        try:
            call_command("verify_migration_checksums", bundle=bundle.pk, stdout=out)
        except SystemExit as exc:
            return int(exc.code), out.getvalue()
        return 0, out.getvalue()
