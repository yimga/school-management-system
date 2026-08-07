"""S2 seal — the at-risk feature extractor references real Evaluation fields.

``_populate_evaluations`` used ``.only("seq1", "seq2", "exam", ...)`` but the
Evaluation fields are ``seq1_score``/``seq2_score``/``exam_score``. The bare names
raised FieldError, which the caller's broad ``except`` swallowed — so three of the
nine at-risk ML features were silently pinned to 0. This forces the queryset to
compile (which validates the field names) so a regression re-raises here instead
of hiding.
"""

from __future__ import annotations

from django.test import TestCase


class AtRiskFeatureFieldsTests(TestCase):
    def test_only_fields_compile_against_evaluation(self):
        from apps.evals.models import Evaluation

        # Evaluating the queryset compiles it; invalid field names raise FieldError.
        list(
            Evaluation.objects.all().only(
                "seq1_score", "seq2_score", "exam_score", "updated_at"
            )[:1]
        )

    def test_extractor_uses_score_suffixed_fields(self):
        # Belt-and-suspenders: the module must not reference the old bare names.
        import inspect

        from apps.analytics.ml import at_risk_features

        src = inspect.getsource(at_risk_features._populate_evaluations)
        self.assertIn("seq1_score", src)
        self.assertNotIn('"seq1"', src)
        self.assertNotIn("getattr(r, \"seq1\"", src)
