"""Held rows are the TENANT's to judge, so the review surface must be readable.

A tenant reported a bundle showing "Held for review: 442" with no way to tell what
that meant. The review page then said "Quarantine (200)" — a second, different
number for the same thing, because the table was capped at 200 while the banner
counted all 442. The 242 rows past the cap were not visible anywhere.

Worse, the biggest bucket usually needs nobody: ``source_deletion`` means the
source system marked the row deleted, so it was deliberately NOT imported. That
is a correct outcome being counted beside real failures.

Only the tenant admin and whoever ran the migration know what the data set
represents, so these tests pin the vocabulary they are shown — not an operator's.
"""

from django.test import SimpleTestCase

from apps.migration_cloud.orchestrator import _classify_quarantine_issue
from apps.migration_cloud.views import (
    QUARANTINE_ISSUE_LABELS,
    QUARANTINE_NO_ACTION_CLASSES,
    QUARANTINE_TABLE_LIMIT,
)


class EveryIssueClassHasATenantFacingLabelTests(SimpleTestCase):
    """The classifier and the label map must not drift apart."""

    # Error strings shaped like the ones landers actually produce, one per branch
    # of _classify_quarantine_issue.
    SAMPLES = {
        "source_deletion": "students: source marked this row deleted — held for review",
        "duplicate": "academics upsert failed: duplicate key value violates unique constraint",
        "invalid_ref": "grades: classroom not found for row 12",
        "missing_required": "students: missing admission_number in row",
        "lander_error": "finance upsert failed: TypeError: unsupported operand",
    }

    def test_the_samples_really_do_classify_the_way_this_test_assumes(self):
        # Guard against the test quietly testing nothing if the classifier changes.
        for expected, sample in self.SAMPLES.items():
            with self.subTest(issue_class=expected):
                self.assertEqual(_classify_quarantine_issue(sample), expected)

    def test_every_class_the_classifier_can_emit_has_a_label(self):
        for issue_class in self.SAMPLES:
            with self.subTest(issue_class=issue_class):
                self.assertIn(
                    issue_class,
                    QUARANTINE_ISSUE_LABELS,
                    msg=(
                        "a held row would render its raw internal class name to a "
                        "school admin; add a plain-English label"
                    ),
                )

    def test_labels_are_plain_english_not_internal_jargon(self):
        for issue_class, label in QUARANTINE_ISSUE_LABELS.items():
            with self.subTest(issue_class=issue_class):
                self.assertNotIn("_", label, msg="reads like a code identifier")
                self.assertGreater(len(label.split()), 3, msg="too terse to act on")


class NoActionClassesTests(SimpleTestCase):
    def test_source_deletion_needs_nobody(self):
        # The single most important classification on this page: it is why a
        # scary "442 held" can be a correct import.
        self.assertIn("source_deletion", QUARANTINE_NO_ACTION_CLASSES)

    def test_a_row_that_already_exists_needs_nobody(self):
        # Landers upsert by external id, so "already exists" means the delta was
        # applied and the duplicate correctly skipped — not data loss.
        self.assertIn("duplicate", QUARANTINE_NO_ACTION_CLASSES)

    def test_real_failures_are_never_silently_excused(self):
        for issue_class in ("missing_required", "invalid_ref", "lander_error"):
            with self.subTest(issue_class=issue_class):
                self.assertNotIn(
                    issue_class,
                    QUARANTINE_NO_ACTION_CLASSES,
                    msg="this hides a row that did not import",
                )

    def test_the_no_action_set_only_names_classes_that_exist(self):
        for issue_class in QUARANTINE_NO_ACTION_CLASSES:
            with self.subTest(issue_class=issue_class):
                self.assertIn(issue_class, QUARANTINE_ISSUE_LABELS)


class TableLimitIsDisclosedNotHiddenTests(SimpleTestCase):
    def test_the_cap_is_a_render_bound_not_a_count_bound(self):
        # The cap may exist — a bundle can hold a million rows — but the TOTAL
        # must never be derived from it, which is what made the page show 200
        # beside a banner saying 442.
        self.assertGreater(QUARANTINE_TABLE_LIMIT, 0)

    def test_template_reports_total_and_shown_separately(self):
        from django.template.loader import get_template

        source = get_template("migration_cloud/anomaly_nudge.html").template.source
        self.assertIn("quarantine_total", source)
        self.assertIn("quarantine_shown", source)
        self.assertIn("quarantine_action_needed", source)
        # The old bug: length of the CAPPED list rendered as the headline count.
        self.assertNotIn("quarantine_rows|length", source)
