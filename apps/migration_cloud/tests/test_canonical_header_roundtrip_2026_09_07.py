"""A canonical header must map, and a shape detector must know its own template.

WHAT THIS COSTS WHEN IT IS MISSING, measured on a live school rather than argued.
On 2026-09-07 a staff directory for Gilead Technical High School was exported in
the platform's OWN canonical shape and imported to the cloud. It produced 48 new
teachers where 20 should have matched people already on file, leaving the school
with 75 records for 55 humans. Two independent defects had to line up, and this
file holds the line on both.

FIRST: a canonical field's own name was not a synonym of itself. ``all_synonyms``
returns a field's ALIASES, so ``_domain_synonym_index('staff')`` carried
``staff_id``, ``staff_code``, ``staff_number``, ``staff_ref`` and
``staffuniqueid`` -> ``staff_external_id`` and not ``staff_external_id``. The
header the platform publishes was the one header it could not read. The identity
column fell through to ``custom_fields.staff_external_id``, the staff lander found
no id on the row, minted ``auto-staff-<hash>``, and every upsert missed.

Swept the same day: 150 published canonical headers across 28 of 30 domains could
not be looked up, overwhelmingly the ``*_external_id`` identity columns -- student,
guardian, teacher, section, subject, recipient, item. Every one of those domains
had the same duplicate bug waiting in it. ``test_every_canonical_field_name_maps_
to_itself`` is the invariant that closes the class, not the instance.

SECOND: ``is_staff_directory_shape`` required a header literally named ``name``,
while the canonical staff template emits ``first_name`` + ``last_name``. So the
routing guard written expressly to stop a staff file being retagged to
``academics`` (catalog_preflight: ``if staff_dir and recommended in (academics,
specialties): continue``) could not fire on a canonically-exported staff file, and
``advance_bundle``'s auto-retag moved it to ``academics``.

WHY THE "ONLY STAFF" HALF MATTERS AS MUCH AS THE "STAFF" HALF. Widening a detector
is how you trade one misroute for another: students, guardians and alumni all
carry first_name + last_name + phone. ``test_no_other_canonical_template_reads_as_
staff`` asserts the detector accepts exactly one template, so a future widening
that swallows the student roster fails here instead of in a school's records.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud import mapper as M
from apps.migration_cloud.accelerators.runmycampus_canonical import (
    DOMAIN_CANONICAL_HEADERS,
)
from apps.migration_cloud.ingestion_lexicon import is_staff_directory_shape
from apps.migration_cloud.ontology import iter_canonical_fields


def _domains_with_ontology():
    for domain in sorted(DOMAIN_CANONICAL_HEADERS):
        try:
            fields = [f["canonical_field"] for f in iter_canonical_fields(domain)]
        except Exception:  # noqa: BLE001 - a domain whose ontology raises is skipped
            continue
        if fields:
            yield domain, fields


class CanonicalNameMapsToItselfTests(SimpleTestCase):
    """The invariant. Not a baseline, not a ratchet -- there is no honest exception."""

    def test_every_canonical_field_name_maps_to_itself(self):
        """If the platform names a field X, a column headed X must resolve to X."""
        broken = []
        checked = 0
        for domain, fields in _domains_with_ontology():
            index = M._domain_synonym_index(domain)
            for field in fields:
                checked += 1
                resolved = M._lookup_synonym_field(field, index)
                if resolved != field:
                    broken.append(f"{domain}.{field} -> {resolved!r}")
        self.assertGreater(checked, 100, "the sweep inspected almost nothing")
        self.assertEqual(broken, [], "canonical names that do not resolve to themselves")

    def test_the_identity_column_of_every_domain_is_mappable(self):
        """The specific failure: an id that will not map creates duplicates.

        Narrower than the test above and kept separately because it is the one
        whose breakage silently doubles a school's people rather than dropping a
        column somebody would notice.
        """
        broken = []
        for domain, fields in _domains_with_ontology():
            index = M._domain_synonym_index(domain)
            for field in fields:
                if not field.endswith("external_id"):
                    continue
                if M._lookup_synonym_field(field, index) != field:
                    broken.append(f"{domain}.{field}")
        self.assertEqual(broken, [], "identity columns that cannot be mapped")

    def test_the_gilead_case_specifically(self):
        """The exact header that cost 28 duplicate people."""
        index = M._domain_synonym_index("staff")
        self.assertEqual(
            M._lookup_synonym_field("staff_external_id", index), "staff_external_id"
        )

    def test_the_aliases_still_work(self):
        """Guard against a fix that registers names by discarding synonyms."""
        index = M._domain_synonym_index("staff")
        for alias in ("staff_id", "staff_ref", "staff_number", "staff_code"):
            self.assertEqual(
                M._lookup_synonym_field(alias, index),
                "staff_external_id",
                f"{alias} stopped resolving",
            )


class StaffDirectoryShapeTests(SimpleTestCase):
    """A detector must recognise its own template -- and only its own."""

    def test_the_canonical_staff_template_reads_as_a_staff_directory(self):
        headers = list(DOMAIN_CANONICAL_HEADERS["staff"])
        self.assertTrue(
            is_staff_directory_shape(headers, None),
            f"the platform's own staff template is unrecognisable to its own "
            f"detector: {sorted(headers)}",
        )

    def test_no_other_canonical_template_reads_as_staff(self):
        """Widening the detector must not swallow the neighbouring rosters.

        students, guardians and alumni all carry first_name + last_name + phone.
        Only the role-or-department requirement separates them from staff.
        """
        accepted = [
            domain
            for domain, headers in sorted(DOMAIN_CANONICAL_HEADERS.items())
            if headers and is_staff_directory_shape(list(headers), None)
        ]
        self.assertEqual(accepted, ["staff"])

    def test_the_raw_telephone_directory_is_still_recognised(self):
        """The shape the detector was originally written for, kept alive.

        Without this, a detector that returns False for everything would pass
        ``test_no_other_canonical_template_reads_as_staff`` perfectly.
        """
        self.assertTrue(
            is_staff_directory_shape(
                ["name", "post", "specialty", "telephone number"], None
            )
        )

    def test_a_subject_master_is_not_a_staff_directory(self):
        """The discrimination the routing guard depends on."""
        self.assertFalse(
            is_staff_directory_shape(
                ["subject_name", "code", "category", "coefficient"], None
            )
        )
