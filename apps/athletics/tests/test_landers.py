"""Migration-Cloud athletics landers — real-fields-only, quarantine, happy path.

The three landers (teams / memberships / fixtures) persist canonical rows into
the athletics models with graceful degradation: a phantom column is never read
(no crash), an unresolved required FK QUARANTINES the row (never a silent drop),
and a valid row lands the object with correct FKs. Also asserts the accelerator
classifies the canonical filenames + headers to the right domains.
"""

from __future__ import annotations

from apps.athletics.models import (
    Fixture,
    FixtureResult,
    Season,
    Sport,
    Team,
    TeamMembership,
)
from apps.athletics.tests.base import BaseAthleticsTestCase
from apps.migration_cloud.landers.athletics_fixtures_lander import AthleticsFixturesLander
from apps.migration_cloud.landers.athletics_memberships_lander import (
    AthleticsMembershipsLander,
)
from apps.migration_cloud.landers.athletics_teams_lander import AthleticsTeamsLander
from apps.migration_cloud.landers.base import LanderContext


class _LanderMixin:
    def ctx(self, dry_run=False):
        return LanderContext(
            school=self.fx.school,
            schema_name="",
            bundle_id=None,
            artifact_id=None,
            dry_run=dry_run,
        )


class TeamsLanderTests(_LanderMixin, BaseAthleticsTestCase):
    def test_valid_row_lands_team_with_provisioned_scaffold(self):
        row = {
            "sport": "Basketball",
            "season": "Winter League",
            "team_name": "Junior Varsity",
            "gender": "boys",
            "roster_cap": "18",
            "status": "active",
            "phantom_column": "should be ignored, not written",
        }
        result = AthleticsTeamsLander().land(
            canonical_rows=iter([row]), ctx=self.ctx()
        )
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(result.created, 1)
        team = Team.objects.get(school=self.fx.school, name="Junior Varsity")
        self.assertEqual(team.gender, "boys")
        self.assertEqual(team.roster_cap, 18)
        # Scaffold provisioned school-scoped.
        self.assertTrue(
            Sport.objects.filter(school=self.fx.school, code="basketball").exists()
        )
        self.assertTrue(
            Season.objects.filter(
                school=self.fx.school, name="Winter League"
            ).exists()
        )

    def test_missing_required_field_quarantines(self):
        row = {"sport": "Basketball", "season": "Winter"}  # no team_name
        result = AthleticsTeamsLander().land(
            canonical_rows=iter([row]), ctx=self.ctx()
        )
        self.assertEqual(result.created, 0)
        self.assertEqual(result.quarantined, 1)
        self.assertIn("missing sport / season / team_name", result.errors[0])

    def test_rerun_updates_not_duplicates(self):
        row = {"sport": "Basketball", "season": "Winter", "team_name": "JV"}
        lander = AthleticsTeamsLander()
        lander.land(canonical_rows=iter([row]), ctx=self.ctx())
        result = lander.land(canonical_rows=iter([dict(row, status="disbanded")]), ctx=self.ctx())
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(
            Team.objects.filter(school=self.fx.school, name="JV").count(), 1
        )

    def test_dry_run_counts_without_writing(self):
        row = {"sport": "Rugby", "season": "Autumn", "team_name": "Colts"}
        result = AthleticsTeamsLander().land(
            canonical_rows=iter([row]), ctx=self.ctx(dry_run=True)
        )
        self.assertEqual(result.created, 1)
        self.assertFalse(
            Team.objects.filter(school=self.fx.school, name="Colts").exists()
        )
        self.assertFalse(
            Sport.objects.filter(school=self.fx.school, code="rugby").exists()
        )


class MembershipsLanderTests(_LanderMixin, BaseAthleticsTestCase):
    def test_valid_row_lands_membership_with_fks(self):
        row = {
            "student_external_id": self.fx.student.admission_number,
            "team_name": self.fx.team.name,
            "jersey_number": "11",
            "position": "Striker",
            "status": "active",
            "phantom_column": "ignored",
        }
        result = AthleticsMembershipsLander().land(
            canonical_rows=iter([row]), ctx=self.ctx()
        )
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(result.created, 1)
        membership = TeamMembership.objects.get(
            school=self.fx.school, team=self.fx.team, student=self.fx.student
        )
        self.assertEqual(membership.jersey_number, 11)
        self.assertEqual(membership.position, "Striker")

    def test_unknown_student_quarantines(self):
        row = {
            "student_external_id": "NOPE-DOES-NOT-EXIST",
            "team_name": self.fx.team.name,
        }
        result = AthleticsMembershipsLander().land(
            canonical_rows=iter([row]), ctx=self.ctx()
        )
        self.assertEqual(result.created, 0)
        self.assertEqual(result.quarantined, 1)
        self.assertFalse(
            TeamMembership.objects.filter(team=self.fx.team).exists()
        )

    def test_unknown_team_quarantines(self):
        row = {
            "student_external_id": self.fx.student.admission_number,
            "team_name": "Team That Never Landed",
        }
        result = AthleticsMembershipsLander().land(
            canonical_rows=iter([row]), ctx=self.ctx()
        )
        self.assertEqual(result.created, 0)
        self.assertEqual(result.quarantined, 1)


class FixturesLanderTests(_LanderMixin, BaseAthleticsTestCase):
    def test_valid_row_lands_fixture_and_result(self):
        row = {
            "team_name": self.fx.team.name,
            "opponent_name": "St Mary's College",
            "fixture_type": "home",
            "scheduled_start": "2026-04-10T15:00:00",
            "scheduled_end": "2026-04-10T17:00:00",
            "home_score": "3",
            "away_score": "1",
            "status": "completed",
            "phantom_column": "ignored",
        }
        result = AthleticsFixturesLander().land(
            canonical_rows=iter([row]), ctx=self.ctx()
        )
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(result.created, 1)
        fixture = Fixture.objects.get(
            school=self.fx.school, team=self.fx.team, opponent_name="St Mary's College"
        )
        self.assertEqual(fixture.season_id, self.fx.team.season_id)
        fresult = FixtureResult.objects.get(fixture=fixture)
        self.assertEqual(fresult.home_score, 3)
        self.assertEqual(fresult.outcome, "win")

    def test_away_fixture_result_outcome_is_perspective_aware(self):
        # Our team is AWAY and won 3-1 (home_score=1, away_score=3). The outcome
        # must be WIN from our perspective; deriving straight from home>away
        # (pre-fix) would store "loss" — silent corruption of every away match.
        row = {
            "team_name": self.fx.team.name,
            "opponent_name": "Away Hosts",
            "fixture_type": "away",
            "scheduled_start": "2026-05-01T15:00:00",
            "home_score": "1",
            "away_score": "3",
            "status": "completed",
        }
        result = AthleticsFixturesLander().land(
            canonical_rows=iter([row]), ctx=self.ctx()
        )
        self.assertEqual(result.quarantined, 0)
        fixture = Fixture.objects.get(
            school=self.fx.school, opponent_name="Away Hosts"
        )
        self.assertEqual(fixture.fixture_type, "away")
        fresult = FixtureResult.objects.get(fixture=fixture)
        self.assertEqual(fresult.outcome, "win")

    def test_home_fixture_result_outcome_unaffected(self):
        row = {
            "team_name": self.fx.team.name,
            "opponent_name": "Home Guests",
            "fixture_type": "home",
            "scheduled_start": "2026-05-02T15:00:00",
            "home_score": "3",
            "away_score": "1",
            "status": "completed",
        }
        AthleticsFixturesLander().land(canonical_rows=iter([row]), ctx=self.ctx())
        fixture = Fixture.objects.get(
            school=self.fx.school, opponent_name="Home Guests"
        )
        fresult = FixtureResult.objects.get(fixture=fixture)
        self.assertEqual(fresult.outcome, "win")

    def test_unknown_team_quarantines(self):
        row = {
            "team_name": "Ghost Team",
            "opponent_name": "Rivals",
            "scheduled_start": "2026-04-10T15:00:00",
        }
        result = AthleticsFixturesLander().land(
            canonical_rows=iter([row]), ctx=self.ctx()
        )
        self.assertEqual(result.created, 0)
        self.assertEqual(result.quarantined, 1)

    def test_missing_scheduled_start_quarantines(self):
        row = {"team_name": self.fx.team.name, "opponent_name": "Rivals"}
        result = AthleticsFixturesLander().land(
            canonical_rows=iter([row]), ctx=self.ctx()
        )
        self.assertEqual(result.quarantined, 1)


class AcceleratorClassificationTests(BaseAthleticsTestCase):
    def test_canonical_filenames_classify_to_athletics_domains(self):
        from apps.migration_cloud.accelerators.runmycampus_canonical import (
            CANONICAL_FILENAME_TO_DOMAIN,
        )

        self.assertEqual(
            CANONICAL_FILENAME_TO_DOMAIN["athletics_teams.csv"], "athletics_teams"
        )
        self.assertEqual(
            CANONICAL_FILENAME_TO_DOMAIN["athletics_memberships.csv"],
            "athletics_memberships",
        )
        self.assertEqual(
            CANONICAL_FILENAME_TO_DOMAIN["athletics_fixtures.csv"], "athletics_fixtures"
        )

    def test_canonical_headers_match_row_shape(self):
        from apps.migration_cloud.accelerators.runmycampus_canonical import (
            DOMAIN_CANONICAL_HEADERS,
        )

        self.assertIn("team_name", DOMAIN_CANONICAL_HEADERS["athletics_teams"])
        self.assertIn("sport", DOMAIN_CANONICAL_HEADERS["athletics_teams"])
        self.assertEqual(
            DOMAIN_CANONICAL_HEADERS["athletics_memberships"],
            {"student_external_id", "team_name", "jersey_number", "position",
             "status", "joined_date"},
        )
        self.assertIn("opponent_name", DOMAIN_CANONICAL_HEADERS["athletics_fixtures"])
        self.assertIn("scheduled_start", DOMAIN_CANONICAL_HEADERS["athletics_fixtures"])
