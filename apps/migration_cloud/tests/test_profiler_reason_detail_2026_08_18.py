"""A file the profiler cannot read must say WHY, not just that it failed.

Bundle 82 on a live tenant quarantined ``archive.zip`` with the reason
``profiler_error`` -- a category name and nothing else. The traceback went to
the server log, which the school cannot see, so the review page told them their
upload had failed while withholding the single fact that would let them fix it.
A renamed .zip, a password-protected workbook and a truncated download all
produced that identical, useless string.

The reason now carries the real exception plus, for recognisable causes, a plain
next step -- while keeping the stable ``profiler_error`` prefix so anything
matching on it keeps working.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.profiler import _PROFILER_REASON_MAX, _profiler_failure_reason


class ProfilerFailureReasonTests(SimpleTestCase):
    def test_keeps_machine_readable_prefix(self):
        self.assertTrue(_profiler_failure_reason(ValueError("boom")).startswith("profiler_error"))

    def test_carries_the_real_cause(self):
        reason = _profiler_failure_reason(ValueError("Bad magic number for file header"))
        self.assertIn("ValueError", reason)
        self.assertIn("Bad magic number", reason)

    def test_renamed_zip_gets_an_actionable_hint(self):
        reason = _profiler_failure_reason(Exception("File is not a zip file"))
        self.assertIn("not a valid archive", reason)
        self.assertIn("upload the CSV/Excel files directly", reason)

    def test_password_protected_gets_an_actionable_hint(self):
        self.assertIn(
            "password-protected", _profiler_failure_reason(Exception("workbook is encrypted"))
        )

    def test_unrecognised_cause_still_reports_it(self):
        reason = _profiler_failure_reason(RuntimeError("something exotic"))
        self.assertIn("RuntimeError", reason)
        self.assertIn("something exotic", reason)

    def test_pathological_message_is_bounded(self):
        reason = _profiler_failure_reason(ValueError("x" * 5000))
        self.assertLessEqual(len(reason), _PROFILER_REASON_MAX + 120)

    def test_message_is_single_line(self):
        """Reasons render inline on the review page; newlines would break it."""
        self.assertNotIn("\n", _profiler_failure_reason(ValueError("line one\nline two")))
