"""JSON-Logic nuance toolset contract (registry, ranking parity)."""

from django.test import SimpleTestCase, TestCase

from apps.evals.ranking import _compute_student_average
from apps.policies.grading_nuance_templates import sync_grading_nuance_from_policy
from apps.schools.models import School
from apps.siteconfig.nuance_engine import (
    compute_report_card_average,
    default_test_contexts_for_hook,
    model_hook_point_choices,
)


class NuanceLogicToolsetContractTests(SimpleTestCase):
    def test_model_choices_cover_database_hooks(self):
        from apps.siteconfig.models import CustomNuance
        from apps.siteconfig.nuance_engine import database_hook_points

        model_values = {v for v, _ in model_hook_point_choices()}
        self.assertEqual(model_values, database_hook_points())
        self.assertEqual(
            {v for v, _ in CustomNuance.HOOK_CHOICES}, database_hook_points()
        )

    def test_report_card_test_contexts_use_allowed_keys(self):
        from apps.siteconfig.nuance_engine import HOOK_REGISTRY

        allowed = set(HOOK_REGISTRY["report_card_avg"])
        for ctx in default_test_contexts_for_hook("report_card_avg"):
            self.assertTrue(set(ctx) <= allowed)


class RankingNuanceParityTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Ranking Nuance School",
            slug="ranking-nuance-school",
            subdomain="ranking-nuance-school",
            country_code="CM",
            is_active=True,
        )

    def test_compute_report_card_average_matches_synced_template(self):
        sync_grading_nuance_from_policy(self.school)
        avg = compute_report_card_average(
            self.school,
            weighted_sum=30.0,
            coefficient_total=5.0,
            scale_max=20.0,
        )
        self.assertEqual(avg, 6.0)

    def test_compute_student_average_without_school_uses_raw_mean(self):
        class _Eval:
            def __init__(self, score, coef):
                self.total_score = score
                self.exam_score = None
                self.mock_score = None
                self.subject_assignment = type(
                    "SA", (), {"coefficient": coef}
                )()

        evaluations = [_Eval(10.0, 2.0), _Eval(20.0, 3.0)]
        # (10*2 + 20*3) / (2+3) = 80/5 = 16.0
        avg = _compute_student_average(evaluations, school=None)
        self.assertEqual(avg, 16.0)
