"""Fixture smoke test — proves the tenant graph builds on the lane."""

from __future__ import annotations

from apps.athletics.tests.base import BaseAthleticsTestCase


class FixtureSmokeTests(BaseAthleticsTestCase):
    def test_graph_builds(self):
        self.assertIsNotNone(self.fx.school.pk)
        self.assertEqual(self.fx.team.season_id, self.fx.season.pk)
        self.assertEqual(self.fx.season.status, self.fx.season.Status.ACTIVE)

    def test_helpers_build(self):
        m = self.add_member(self.fx)
        self.assertEqual(m.status, m.Status.ACTIVE)
        self.make_attendance(self.fx, present=3, absent=1)
        ev = self.make_evaluation(self.fx, exam_score=80)
        self.assertEqual(float(ev.total_score), 80.0)
        self.make_clearance(self.fx)
