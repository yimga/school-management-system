from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.analytics.ml_inference import run_risk_inference_batch


class RiskInferenceBatchContractTests(SimpleTestCase):
    @patch("apps.analytics.ml.at_risk_model.predict_at_risk")
    @patch("apps.people.models.StudentProfile.objects")
    def test_scores_active_tenant_students_with_canonical_predictor(
        self,
        student_objects,
        predict_at_risk,
    ):
        student = SimpleNamespace(pk=7)
        queryset = MagicMock()
        queryset.select_related.return_value = queryset
        queryset.iterator.return_value = iter([student])
        student_objects.filter.return_value = queryset
        predict_at_risk.return_value = (72.5, "Model drivers", "risk-v3")

        rows = run_risk_inference_batch("school-1", threshold=50)

        student_objects.filter.assert_called_once_with(
            school_id="school-1",
            is_active=True,
        )
        predict_at_risk.assert_called_once_with(student)
        self.assertEqual(
            rows,
            [(student, Decimal("72.5"), "Model drivers", "risk-v3")],
        )

    @patch("apps.analytics.ml.at_risk_model.predict_at_risk")
    @patch("apps.people.models.StudentProfile.objects")
    def test_keeps_green_scores_for_complete_school_reporting(
        self,
        student_objects,
        predict_at_risk,
    ):
        student = SimpleNamespace(pk=8)
        queryset = MagicMock()
        queryset.select_related.return_value = queryset
        queryset.iterator.return_value = iter([student])
        student_objects.filter.return_value = queryset
        predict_at_risk.return_value = (12.0, "No notable risk signals.", None)

        rows = run_risk_inference_batch("school-2", threshold=50)

        self.assertEqual(rows[0][1], Decimal("12.0"))
        self.assertIsNone(rows[0][3])
