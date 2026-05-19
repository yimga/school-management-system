"""Wave 2 tests — shadow scoring + agreement metric + promotion classification.

The shadow command is exercised through `call_command` with stubbed
prediction calls. We monkey-patch `predict_with_artifact` at the
command-module level so tests don't need joblib bundles on disk.
"""

from __future__ import annotations

import tempfile
import unittest.mock as mock
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.analytics.models import (
    AtRiskModelArtifact,
    AtRiskShadowComparison,
    AtRiskShadowRun,
)
from apps.analytics.management.commands import score_shadow_at_risk as cmd_mod
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class ShadowMathTests(SimpleTestCase):
    def test_band_thresholds(self):
        self.assertEqual(cmd_mod._band(85), "red")
        self.assertEqual(cmd_mod._band(80), "red")
        self.assertEqual(cmd_mod._band(60), "amber")
        self.assertEqual(cmd_mod._band(50), "amber")
        self.assertEqual(cmd_mod._band(49.99), "green")
        self.assertEqual(cmd_mod._band(0), "green")

    def test_band_rank_order(self):
        self.assertLess(cmd_mod._band_rank("green"), cmd_mod._band_rank("amber"))
        self.assertLess(cmd_mod._band_rank("amber"), cmd_mod._band_rank("red"))

    def test_distribution_sums_to_one(self):
        dist = cmd_mod._distribution([5, 15, 25, 35, 45, 55, 65, 75, 85, 95])
        self.assertAlmostEqual(sum(dist), 1.0, places=6)
        self.assertEqual(len(dist), 10)

    def test_identical_distributions_score_zero(self):
        dist = cmd_mod._distribution([10, 50, 90, 10, 50, 90])
        self.assertAlmostEqual(cmd_mod._psi(dist, dist), 0.0, places=6)


class _ShadowFixtureMixin:
    @classmethod
    def _seed(cls, uid: int):
        region, _ = RegionConfig.objects.get_or_create(
            code=f"SH{uid % 9999}",
            defaults={
                "name": "Shadow Region",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        school = School.objects.create(
            name=f"Sh {uid}",
            slug=f"shadow-{uid}",
            subdomain=f"shadow-{uid}",
            is_active=True,
            default_region=region,
        )
        operator = User.objects.create_user(
            username=f"shop_{uid}", email=f"op_{uid}@example.com", password="p",
        )
        # 5 active students.
        students = []
        for i in range(5):
            u = User.objects.create_user(
                username=f"sh_st_{uid}_{i}",
                email=f"sh_st_{uid}_{i}@example.com",
                password="p",
            )
            students.append(StudentProfile.objects.create(
                school=school, user=u,
                first_name=f"S{i}", last_name="Shdw",
                student_code=f"SH-{uid % 9999}-{i}",
                is_active=True,
            ))
        return school, operator, students

    @classmethod
    def _make_artifact(cls, operator, *, version, status, path=None):
        if path is None:
            tmp = tempfile.NamedTemporaryFile(suffix=".joblib", delete=False)
            tmp.write(b"placeholder")
            tmp.close()
            path = tmp.name
        promoted_at = (
            timezone.now() if status == AtRiskModelArtifact.Status.PRODUCTION else None
        )
        return AtRiskModelArtifact.objects.create(
            model_version=version,
            artifact_path=path,
            trained_at=timezone.now(),
            status=status,
            registered_by=operator,
            promoted_at=promoted_at,
            promoted_by=operator if promoted_at else None,
        )


class ScoreShadowAtRiskTests(_ShadowFixtureMixin, TestCase):
    """Run the command with stubbed model scoring."""

    def test_skips_when_no_candidate(self):
        school, op, _ = self._seed(uid=id(self))
        self._make_artifact(
            op, version="prod1", status=AtRiskModelArtifact.Status.PRODUCTION,
        )
        # No candidate registered → SKIPPED.
        call_command(
            "score_shadow_at_risk",
            "--school", school.slug,
            stdout=StringIO(),
        )
        run = AtRiskShadowRun.objects.get(school=school)
        self.assertEqual(run.outcome, AtRiskShadowRun.Outcome.SKIPPED)

    def test_shadow_run_computes_agreement_and_psi(self):
        school, op, students = self._seed(uid=id(self))
        prod = self._make_artifact(
            op, version="prod_v1",
            status=AtRiskModelArtifact.Status.PRODUCTION,
        )
        self._make_artifact(
            op, version="cand_v1",
            status=AtRiskModelArtifact.Status.CANDIDATE,
        )
        # Production scores 5 students all green (20); candidate flips
        # 2 to red (85), 1 to amber (55), keeps 2 green (20).
        prod_seq = iter([20.0] * 5)
        cand_seq = iter([85.0, 85.0, 55.0, 20.0, 20.0])

        def _fake(student, path):
            return (
                next(prod_seq) if path == prod.artifact_path
                else next(cand_seq)
            )

        with mock.patch.object(cmd_mod, "predict_with_artifact", side_effect=_fake):
            call_command(
                "score_shadow_at_risk",
                "--school", school.slug,
                stdout=StringIO(),
            )

        run = AtRiskShadowRun.objects.get(school=school)
        self.assertEqual(run.outcome, AtRiskShadowRun.Outcome.OK)
        self.assertEqual(run.students_scored, 5)
        # 3 students changed band (green→red x2, green→amber x1)
        self.assertEqual(run.band_changes, 3)
        # All 3 were promotions (higher risk band).
        self.assertEqual(run.promotions, 3)
        self.assertEqual(run.demotions, 0)
        self.assertAlmostEqual(run.agreement_pct, 2 / 5, places=6)
        # PSI > 0 because distributions differ.
        self.assertGreater(run.psi_score_distribution, 0.0)
        # 5 per-student rows recorded.
        self.assertEqual(
            AtRiskShadowComparison.objects.filter(run=run).count(), 5,
        )

    def test_explicit_candidate_version(self):
        school, op, students = self._seed(uid=id(self))
        self._make_artifact(
            op, version="prod_x",
            status=AtRiskModelArtifact.Status.PRODUCTION,
        )
        # Two CANDIDATES — the most recent should be picked by default,
        # but --candidate-version targets the older one explicitly.
        older = self._make_artifact(
            op, version="cand_old",
            status=AtRiskModelArtifact.Status.CANDIDATE,
        )
        self._make_artifact(
            op, version="cand_new",
            status=AtRiskModelArtifact.Status.CANDIDATE,
        )
        with mock.patch.object(
            cmd_mod, "predict_with_artifact", side_effect=lambda s, p: 40.0,
        ):
            call_command(
                "score_shadow_at_risk",
                "--school", school.slug,
                "--candidate-version", older.model_version,
                stdout=StringIO(),
            )
        run = AtRiskShadowRun.objects.get(school=school)
        self.assertEqual(run.candidate_artifact_id, older.pk)

    def test_zero_score_delta_yields_perfect_agreement(self):
        school, op, students = self._seed(uid=id(self))
        self._make_artifact(
            op, version="p_ident",
            status=AtRiskModelArtifact.Status.PRODUCTION,
        )
        self._make_artifact(
            op, version="c_ident",
            status=AtRiskModelArtifact.Status.CANDIDATE,
        )
        with mock.patch.object(
            cmd_mod, "predict_with_artifact", side_effect=lambda s, p: 30.0,
        ):
            call_command(
                "score_shadow_at_risk",
                "--school", school.slug,
                stdout=StringIO(),
            )
        run = AtRiskShadowRun.objects.get(school=school)
        self.assertEqual(run.band_changes, 0)
        self.assertEqual(run.promotions, 0)
        self.assertEqual(run.demotions, 0)
        self.assertAlmostEqual(run.agreement_pct, 1.0, places=6)
        self.assertAlmostEqual(run.mean_abs_delta, 0.0, places=6)

    def test_demotion_classified_correctly(self):
        school, op, students = self._seed(uid=id(self))
        self._make_artifact(
            op, version="p_dem",
            status=AtRiskModelArtifact.Status.PRODUCTION,
        )
        self._make_artifact(
            op, version="c_dem",
            status=AtRiskModelArtifact.Status.CANDIDATE,
        )
        # Prod red, candidate green for every student → 5 demotions.
        with mock.patch.object(
            cmd_mod, "predict_with_artifact",
            side_effect=lambda s, p: (
                90.0 if "p_dem" in p or "placeholder" in p else 20.0
            ),
        ):
            # The lambda needs to identify prod vs candidate; rely on
            # the actual path comparison so use the real artifact paths.
            prod_obj = AtRiskModelArtifact.objects.get(model_version="p_dem")
            cand_obj = AtRiskModelArtifact.objects.get(model_version="c_dem")

            def _fake(student, path):
                if path == prod_obj.artifact_path:
                    return 90.0
                if path == cand_obj.artifact_path:
                    return 20.0
                return 0.0

            with mock.patch.object(cmd_mod, "predict_with_artifact", side_effect=_fake):
                call_command(
                    "score_shadow_at_risk",
                    "--school", school.slug,
                    stdout=StringIO(),
                )
        run = AtRiskShadowRun.objects.filter(school=school).order_by("-started_at").first()
        self.assertEqual(run.demotions, 5)
        self.assertEqual(run.promotions, 0)
