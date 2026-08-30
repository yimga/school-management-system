"""A PDF-noise rule must require a PDF (2026-08-30).

Found while reading the production state for bundle 85, whose 88 held rows all
sit on ``school_stats_2026-01-18 22_47_25.679938.pdf``. The predicate that
dismisses them was:

    if "school_stats" in artifact_name and not row_has_domain_identity(...):
        return True
    if not artifact_name.endswith(".pdf"):
        return False

The filename shortcut sat ABOVE the extension gate, so a ``.csv`` or ``.xlsx``
whose NAME merely contained ``school_stats`` was auto-dismissed by a rule whose
name, docstring and entire justification are about PDF tabularisation noise.
Filenames are operator-supplied.

That is the exact case the operator said must reach a human: "real academics CSV
gaps (missing subject/course fields) still need mapping fixes -- that is genuine
human judgement". A CSV named school_stats* would never have got there.

Derived stats reports already have a stronger owner: ``is_derived_report()``
reads the HEADERS, not just the name, and skips them at classification time for
any extension (see test_derived_report_skip_2026_08_13). If a school_stats.csv
reaches quarantine as academics rows, that check already declined to call it
derived -- so overruling it on a substring is a weaker test beating a better one.

With the extension gate first, the shortcut is redundant: every ``.pdf`` already
falls through to the same identity check. So it is gone rather than reordered.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.landers._helpers import row_is_pdf_noise_hold

# Plausible academics content with no subject/course identity -- indistinguishable
# from page furniture by identity alone, which is why the ARTIFACT decides.
ROW = {"teacher": "Mr Ndip", "period": "3", "term": "Term 1"}

# The real artifact behind bundle 85's 88 held rows, from the production read.
BUNDLE_85_ARTIFACT = "school_stats_2026-01-18 22_47_25.679938.pdf"


class PdfNoiseRequiresAPdfTests(SimpleTestCase):
    def test_the_production_bundle_85_artifact_is_still_noise(self):
        # The fix must not change the answer for the bundle that prompted it:
        # it IS a PDF, so it still clears. Pinned so a later tightening cannot
        # silently strand 88 rows that the operator was told would close.
        self.assertTrue(row_is_pdf_noise_hold("academics", ROW, BUNDLE_85_ARTIFACT))

    def test_a_non_pdf_is_never_pdf_noise_however_it_is_named(self):
        for artifact in (
            "school_stats_export.csv",
            "school_stats.xlsx",
            "SCHOOL_STATS_2026.CSV",
            "exports/school_stats/term1.csv",
            "school_stats",
        ):
            with self.subTest(artifact=artifact):
                self.assertFalse(
                    row_is_pdf_noise_hold("academics", ROW, artifact),
                    "a filename substring dismissed a row that needs a person",
                )

    def test_an_ordinary_pdf_without_identity_is_still_noise(self):
        self.assertTrue(row_is_pdf_noise_hold("academics", ROW, "timetable.pdf"))

    def test_a_pdf_row_that_does_have_identity_is_kept(self):
        real = dict(ROW, subject_name="Mathematics", subject_code="MATH101")
        self.assertFalse(row_is_pdf_noise_hold("academics", real, BUNDLE_85_ARTIFACT))

    def test_an_ordinary_csv_is_unaffected(self):
        # Control: this was already False and must stay False.
        self.assertFalse(row_is_pdf_noise_hold("academics", ROW, "academics_export.csv"))
