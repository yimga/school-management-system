"""Regression seals (2026-06-17 gap analysis), offline-sync tier.

1. config_version_for must move when a GLOBAL config source changes, not only when the
   School row changes — else edge hubs run stale offline config indefinitely.
2. Offline grade conflict 'keep_mine' (force_local=True) must actually overwrite the
   server Evaluation — previously _apply_grading ignored force_local so the row was stuck
   in CONFLICT forever.
"""
from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase
from django.utils import timezone

from apps.platform_runtime import remote_support_reverse_channel as rc
from apps.platform_runtime import offline_queue as oq


def _rd_mock(dt):
    m = mock.MagicMock()
    m.objects.filter.return_value.values_list.return_value.first.return_value = dt
    return m


def _ss_mock(dt):
    m = mock.MagicMock()
    m.objects.values_list.return_value.first.return_value = dt
    return m


class ConfigVersionSealTests(SimpleTestCase):
    def test_token_is_hex_and_stable(self):
        school = mock.Mock(updated_at=timezone.now(), pk=1)
        token = rc.config_version_for(school)
        self.assertTrue(token)
        self.assertEqual(len(token), 24)
        int(token, 16)  # raises if not hex
        self.assertEqual(token, rc.config_version_for(school))

    def test_token_changes_with_school_updated_at(self):
        t1 = timezone.now()
        t2 = t1 + timezone.timedelta(minutes=5)
        a = rc.config_version_for(mock.Mock(updated_at=t1, pk=1))
        b = rc.config_version_for(mock.Mock(updated_at=t2, pk=1))
        self.assertNotEqual(a, b)

    def test_token_changes_when_global_runtime_defaults_change(self):
        school = mock.Mock(updated_at=timezone.now(), pk=1)
        ss = _ss_mock(timezone.now())
        dt_a = timezone.now()
        dt_b = dt_a + timezone.timedelta(hours=1)
        with mock.patch("apps.platform_runtime.models.RuntimeDefaults", _rd_mock(dt_a)), \
                mock.patch("apps.siteconfig.models.SiteSettings", ss):
            first = rc.config_version_for(school)
        with mock.patch("apps.platform_runtime.models.RuntimeDefaults", _rd_mock(dt_b)), \
                mock.patch("apps.siteconfig.models.SiteSettings", ss):
            second = rc.config_version_for(school)
        self.assertNotEqual(
            first, second, "global RuntimeDefaults change must move the config version"
        )


class GradeConflictForceLocalSealTests(SimpleTestCase):
    PAYLOAD = {
        "subject_assignment_id": 1,
        "student_id": 1,
        "academic_year_id": 1,
        "term_id": 1,
        "seq1_score": "15",
        "seq2_score": None,
        "exam_score": None,
        "mock_score": None,
        "practical_score": None,
        "remarks": "teacher offline value",
    }

    def _patches(self, server_eval):
        tp = mock.Mock(school_id=7)
        sa = mock.Mock(classroom=None)
        tp_model = mock.MagicMock()
        tp_model.objects.filter.return_value.first.return_value = tp
        sa_model = mock.MagicMock()
        sa_model.objects.filter.return_value.first.return_value = sa
        eval_model = mock.MagicMock()
        eval_model.objects.filter.return_value.first.return_value = server_eval
        return [
            mock.patch("apps.people.models.TeacherProfile", tp_model),
            mock.patch("apps.academics.models.SubjectAssignment", sa_model),
            mock.patch("apps.evals.models.Evaluation", eval_model),
        ]

    def _server_eval(self):
        return mock.Mock(
            pk=99,
            seq1_score=Decimal("10"),  # differs from payload "15" -> conflict
            seq2_score=None,
            exam_score=None,
            mock_score=None,
            practical_score=None,
            remarks="server value",
        )

    def test_force_local_overwrites_server_eval(self):
        server_eval = self._server_eval()
        patches = self._patches(server_eval)
        for p in patches:
            p.start()
        try:
            result = oq._apply_grading(7, 1, dict(self.PAYLOAD), force_local=True)
        finally:
            for p in patches:
                p.stop()
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("forced_local"))
        self.assertEqual(result.get("evaluation_id"), 99)
        self.assertEqual(server_eval.seq1_score, "15")
        self.assertEqual(server_eval.remarks, "teacher offline value")
        self.assertTrue(server_eval.save.called)

    def test_without_force_local_returns_conflict(self):
        server_eval = self._server_eval()
        patches = self._patches(server_eval)
        for p in patches:
            p.start()
        try:
            with mock.patch(
                "apps.sync_engine.conflict_resolver.resolve_one", return_value={}
            ):
                result = oq._apply_grading(7, 1, dict(self.PAYLOAD), force_local=False)
        finally:
            for p in patches:
                p.stop()
        self.assertFalse(result.get("ok"))
        self.assertTrue(result.get("conflict"))
        self.assertFalse(server_eval.save.called)
