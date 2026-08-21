"""The migration assistant's prompts carried student records, and were refused.

Two defects with one cause: nobody checked what the gateway actually reads.

**1. The declared sensitivity class was written under a key nothing reads.**
``ai_bridge`` sent ``metadata={"content_sensitivity": "standard"}``. The external
tier gate, ``services.ai_gateway._data_tier_allows_premium``, reads
``sensitivity_class`` and denies by default when the class is absent or
unrecognised. So every Migration Cloud prompt was refused ``data_tier_disallowed``
and the cloud model never answered. Seven other callers across the platform pass
``sensitivity_class`` correctly; this one did not, and no test compared them.

That is the second half of the bundle-84 failure. The classifier scored the
subjects artifact below its 0.70 confidence floor and asked the AI arbitrator to
settle it — and the arbitrator could not run, because ``litellm`` was refused
here and ``ollama`` does not exist on a cloud host. The fallback took the top
scorer, ``behavior``, and 434 rows were held for review.

**2. The prompts embedded raw sample rows.** ``sample_rows[:3]`` put real student
names, dates of birth and guardian emails into an outbound payload. Correcting
the key alone would not have helped: the gateway's own PII detector matches the
DOB and the email and refuses the payload anyway. So the *only* prompt shape that
both protects the child and reaches the model is one that describes personal
columns instead of showing them.

A format-preserving mask is not enough, and that was measured rather than
assumed: rendering ``2009-04-17`` as ``9999-99-99`` and an address as
``a.aaa@aaa.aa`` still matched the detector's date and email patterns, so premium
stayed denied. Describing the column — "an ISO-style date, 10 chars" — carries
the classification signal without reproducing the pattern.

DB-free.
"""

from django.test import SimpleTestCase

from apps.migration_cloud.ai_bridge import (
    _build_domain_prompt,
    _build_source_prompt,
    _column_digest,
    _column_is_personal,
    _describe_personal_column,
    _sensitivity_class_for,
)
from services.ai_gateway import _data_tier_allows_premium

HEADERS = [
    "full_name",
    "date_of_birth",
    "admission_number",
    "guardian_email",
    "gender",
    "specialty",
]
ROWS = [
    {
        "full_name": "Ngwa Divine Ache",
        "date_of_birth": "2009-04-17",
        "admission_number": "GTHS-2231",
        "guardian_email": "parent.ache@yahoo.fr",
        "gender": "F",
        "specialty": "Plumbing",
    },
    {
        "full_name": "Tabi Ruth",
        "date_of_birth": "2010-11-02",
        "admission_number": "GTHS-2244",
        "guardian_email": "r.tabi@gmail.com",
        "gender": "F",
        "specialty": "Masonry",
    },
]
# Every token a child could be recognised by in the rows above.
IDENTIFYING = (
    "Ngwa", "Divine", "Ache", "Tabi", "Ruth",
    "2009-04-17", "2010-11-02",
    "parent.ache", "yahoo.fr", "r.tabi", "gmail.com",
    "GTHS-2231", "GTHS-2244",
)


class TheDeclaredClassIsTheOneTheGateReadsTests(SimpleTestCase):
    def test_standard_content_declares_the_internal_class(self):
        # "internal" is the house convention every other caller uses.
        self.assertEqual(_sensitivity_class_for("standard"), "internal")

    def test_the_internal_class_is_actually_accepted_by_the_gate(self):
        # The point of the mapping: not that it is spelled right, but that the
        # gate says yes. Asserting the string alone would have passed before.
        self.assertTrue(
            _data_tier_allows_premium(
                {"sensitivity_class": _sensitivity_class_for("standard")},
                prompt="Headers: ['subject_name', 'credits']",
            )
        )

    def test_pii_content_is_declared_high_and_stays_local(self):
        # The quarantine explainer sends real held rows. It must never leave.
        self.assertEqual(_sensitivity_class_for("high_pii"), "high")
        self.assertFalse(
            _data_tier_allows_premium(
                {"sensitivity_class": _sensitivity_class_for("high_pii")},
                prompt="Row: {'full_name': 'Ngwa Divine Ache'}",
            )
        )

    def test_an_unknown_label_fails_closed_to_high(self):
        # A new content label added later must not silently become sendable.
        for label in ("", "  ", "whatever", None):
            with self.subTest(label=label):
                self.assertEqual(_sensitivity_class_for(label), "high")


class NoStudentIsIdentifiableInAnOutboundPromptTests(SimpleTestCase):
    def test_the_domain_prompt_carries_no_identifying_token(self):
        prompt = _build_domain_prompt(HEADERS, ROWS, ["students", "staff"])
        leaked = [token for token in IDENTIFYING if token in prompt]
        self.assertEqual(leaked, [], f"identifying data in outbound prompt: {leaked}")

    def test_the_source_prompt_carries_no_identifying_token(self):
        prompt = _build_source_prompt(HEADERS, ROWS, ["powerschool", "alma"])
        leaked = [token for token in IDENTIFYING if token in prompt]
        self.assertEqual(leaked, [], f"identifying data in outbound prompt: {leaked}")

    def test_the_domain_prompt_is_now_accepted_by_the_external_gate(self):
        # The outcome that matters: cloud arbitration can actually happen. This
        # is what was returning data_tier_disallowed on every bundle.
        prompt = _build_domain_prompt(HEADERS, ROWS, ["students", "staff"])
        self.assertTrue(
            _data_tier_allows_premium(
                {"sensitivity_class": _sensitivity_class_for("standard")}, prompt=prompt
            )
        )

    def test_the_source_prompt_is_accepted_too(self):
        prompt = _build_source_prompt(HEADERS, ROWS, ["powerschool", "alma"])
        self.assertTrue(
            _data_tier_allows_premium(
                {"sensitivity_class": _sensitivity_class_for("standard")}, prompt=prompt
            )
        )


class TheClassificationSignalSurvivesTests(SimpleTestCase):
    """Protecting the row must not blind the classifier — that trade is refused."""

    def test_column_names_are_still_sent_in_full(self):
        # The header IS the signal. It is schema, not personal data.
        prompt = _build_domain_prompt(HEADERS, ROWS, ["students", "staff"])
        for header in HEADERS:
            with self.subTest(header=header):
                self.assertIn(header, prompt)

    def test_non_personal_values_are_still_shown_verbatim(self):
        # "Plumbing" / "Masonry" is exactly the vocabulary that separates a
        # specialties file from a students file. Masking it would have cost the
        # classifier the evidence it exists to weigh.
        digest = _column_digest(HEADERS, ROWS)
        self.assertIn("Plumbing", digest)
        self.assertIn("Masonry", digest)

    def test_a_personal_column_still_reports_what_kind_of_thing_it_holds(self):
        digest = _column_digest(HEADERS, ROWS)
        self.assertIn("an ISO-style date", digest)
        self.assertIn("an email address", digest)

    def test_a_column_with_no_values_says_so_rather_than_vanishing(self):
        digest = _column_digest(["orphan_column"], [{}])
        self.assertIn("orphan_column", digest)


class WhatCountsAsPersonalTests(SimpleTestCase):
    def test_names_and_contacts_are_personal(self):
        for header in (
            "full_name", "Surname", "guardian_email", "mother_phone",
            "home_address", "date_of_birth", "photo_url",
        ):
            with self.subTest(header=header):
                self.assertTrue(_column_is_personal(header, ["x"]))

    def test_a_school_identifier_is_personal_too(self):
        # It reads like a reference, but it singles out one child exactly, and
        # it is the join key an outside party would need to re-identify a row.
        for header in ("admission_number", "matricule", "student_id", "roll_no"):
            with self.subTest(header=header):
                self.assertTrue(_column_is_personal(header, ["GTHS-2231"]))

    def test_ordinary_school_vocabulary_is_not_personal(self):
        for header in ("specialty", "credits", "subject_code", "room", "term"):
            with self.subTest(header=header):
                self.assertFalse(_column_is_personal(header, ["Plumbing"]))

    def test_a_neutral_header_hiding_contact_values_is_still_caught(self):
        # The header lies; the values do not.
        self.assertTrue(_column_is_personal("col_7", ["parent.ache@yahoo.fr"]))


class TheDescriptionMustNotRebuildThePatternTests(SimpleTestCase):
    """The measured regression: a faithful mask defeated the detector.

    An earlier attempt emitted a character-class silhouette. It leaked nothing
    readable, but ``9999-99-99`` and ``a.aaa@aaa.aa`` matched the gateway's own
    date and email patterns, so the payload was refused exactly as before — and
    a shape-perfect mask of a national id is a template for forging one.
    """

    def test_a_described_date_does_not_read_as_a_date(self):
        described = _describe_personal_column(["2009-04-17", "2010-11-02"])
        self.assertIn("ISO-style date", described)
        self.assertNotIn("9999", described)
        self.assertTrue(
            _data_tier_allows_premium({"sensitivity_class": "internal"}, prompt=described)
        )

    def test_a_described_email_does_not_read_as_an_email(self):
        described = _describe_personal_column(["parent.ache@yahoo.fr"])
        self.assertIn("email address", described)
        self.assertNotIn("@", described)
        self.assertTrue(
            _data_tier_allows_premium({"sensitivity_class": "internal"}, prompt=described)
        )

    def test_a_described_name_keeps_only_its_word_and_length_span(self):
        described = _describe_personal_column(["Ngwa Divine Ache", "Tabi Ruth"])
        self.assertNotIn("Ngwa", described)
        self.assertNotIn("Tabi", described)
        self.assertIn("word", described)
        self.assertIn("chars", described)

    def test_an_identifier_is_described_by_kind_not_by_value(self):
        described = _describe_personal_column(["GTHS-2231", "GTHS-2244"])
        self.assertNotIn("GTHS", described)
        self.assertNotIn("2231", described)
        self.assertIn("alphanumeric identifier", described)

    def test_an_empty_column_is_handled_without_raising(self):
        self.assertIn("no sample values", _describe_personal_column([]))
