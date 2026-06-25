"""Tests for the term-results-published closed-loop notifier.

No DB: the student/guardian resolution and the dispatch router are mocked at their
seams, so these assert the *policy* (off ⇒ silent; published/entered ⇒ fan out the
routed grade.published event) and the failure-isolation contract directly.
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.portal.student_results_visibility import (
    STUDENT_RESULTS_VISIBILITY_ENTERED,
    STUDENT_RESULTS_VISIBILITY_OFF,
    STUDENT_RESULTS_VISIBILITY_PUBLISHED,
)
from apps.reports import notify_term_published as ntp


class _Term:
    label = "Term 2"


def _run_immediately(cb):
    cb()


class NotifyTermResultsPublishedTests(SimpleTestCase):
    @patch("apps.communication.dispatch.dispatch_event")
    def test_off_mode_skips_fanout(self, mock_dispatch):
        ntp.notify_term_results_published(
            school=object(),
            year=object(),
            term=_Term(),
            classroom_ids=None,
            visibility_mode=STUDENT_RESULTS_VISIBILITY_OFF,
        )
        mock_dispatch.assert_not_called()

    @patch("apps.reports.notify_term_published.transaction.on_commit", side_effect=_run_immediately)
    @patch("apps.reports.notify_term_published._recipient_users_for_student")
    @patch("apps.reports.notify_term_published._students_for_scope")
    @patch("apps.communication.dispatch.dispatch_event")
    def test_published_mode_fans_out_routed_event(
        self, mock_dispatch, mock_students, mock_recipients, _mock_oncommit
    ):
        user = MagicMock(pk=1)
        mock_students.return_value = [MagicMock()]
        mock_recipients.return_value = [user]

        ntp.notify_term_results_published(
            school=object(),
            year=object(),
            term=_Term(),
            classroom_ids=None,
            visibility_mode=STUDENT_RESULTS_VISIBILITY_PUBLISHED,
        )

        self.assertTrue(mock_dispatch.called)
        args, kwargs = mock_dispatch.call_args
        self.assertEqual(args[0], "grade.published")
        self.assertEqual(kwargs["recipient"], user)
        self.assertIn("Term 2", kwargs["context"]["message"])

    @patch("apps.reports.notify_term_published.transaction.on_commit", side_effect=_run_immediately)
    @patch("apps.reports.notify_term_published._recipient_users_for_student")
    @patch("apps.reports.notify_term_published._students_for_scope")
    @patch("apps.communication.dispatch.dispatch_event")
    def test_entered_mode_also_fans_out(
        self, mock_dispatch, mock_students, mock_recipients, _mock_oncommit
    ):
        mock_students.return_value = [MagicMock()]
        mock_recipients.return_value = [MagicMock(pk=2)]

        ntp.notify_term_results_published(
            school=object(),
            year=object(),
            term=_Term(),
            visibility_mode=STUDENT_RESULTS_VISIBILITY_ENTERED,
        )
        self.assertTrue(mock_dispatch.called)

    @patch("apps.reports.notify_term_published.transaction.on_commit", side_effect=_run_immediately)
    @patch("apps.reports.notify_term_published._students_for_scope", return_value=[])
    @patch("apps.communication.dispatch.dispatch_event")
    def test_no_students_skips(self, mock_dispatch, _mock_students, _mock_oncommit):
        ntp.notify_term_results_published(
            school=object(),
            year=object(),
            term=_Term(),
            visibility_mode=STUDENT_RESULTS_VISIBILITY_PUBLISHED,
        )
        mock_dispatch.assert_not_called()

    @patch("apps.reports.notify_term_published.transaction.on_commit", side_effect=_run_immediately)
    @patch("apps.reports.notify_term_published._recipient_users_for_student")
    @patch("apps.reports.notify_term_published._students_for_scope")
    @patch("apps.communication.dispatch.dispatch_event", side_effect=RuntimeError("boom"))
    def test_dispatch_failure_is_isolated(
        self, _mock_dispatch, mock_students, mock_recipients, _mock_oncommit
    ):
        mock_students.return_value = [MagicMock()]
        mock_recipients.return_value = [MagicMock(pk=3)]
        # Must not raise even though every dispatch raises.
        ntp.notify_term_results_published(
            school=object(),
            year=object(),
            term=_Term(),
            visibility_mode=STUDENT_RESULTS_VISIBILITY_PUBLISHED,
        )

    @patch("apps.communication.dispatch.dispatch_event")
    def test_none_mode_with_no_site_defaults_published(self, mock_dispatch):
        # visibility_mode=None and site=None ⇒ default 'published' (not off), so it
        # proceeds to student resolution. With a real (empty) resolution it simply
        # finds no one — assert it did not crash and did not dispatch.
        with patch(
            "apps.reports.notify_term_published._students_for_scope", return_value=[]
        ):
            ntp.notify_term_results_published(
                school=object(), year=object(), term=_Term()
            )
        mock_dispatch.assert_not_called()
