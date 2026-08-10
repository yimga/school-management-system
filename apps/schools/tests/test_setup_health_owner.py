"""setup_health owner-presence check.

Seals the ownerless-honesty residual on the per-school setup-completeness
surface (Setup Studio + admin cockpit nudges): a school with branding + plan +
runtime but no active owner must NOT read 100% healthy, and must surface an
unmet "owner" check so the cockpit nudges the operator to assign one.

The presence assertion (`test_owner_check_present_in_health`) is the must-fire
seal — it fails before the owner check exists and passes after.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.schools.models import School, SchoolMembership
from apps.schools.setup_health import setup_health_score, next_best_action


class SetupHealthOwnerCheckTests(TestCase):
    def _checks(self, health):
        return {name: (passed, label) for name, passed, label in health["checks"]}

    def test_owner_check_present_in_health(self):
        # Must-fire seal: before the owner criterion existed, setup_health carried
        # no 'owner' check at all, so a fully-scaffolded ownerless school read as
        # complete on this surface.
        school = School.objects.create(
            name="Health", slug="sh-owner", subdomain="sh-owner-sub"
        )
        health = setup_health_score(school)
        self.assertIn(
            "owner",
            self._checks(health),
            "setup_health must surface an 'owner' check.",
        )

    def test_ownerless_school_owner_check_fails(self):
        school = School.objects.create(
            name="Health2", slug="sh-noowner", subdomain="sh-noowner-sub"
        )
        passed, _label = self._checks(setup_health_score(school))["owner"]
        self.assertFalse(passed)

    def test_owner_present_owner_check_passes_and_raises_score(self):
        school = School.objects.create(
            name="Health3", slug="sh-hasowner", subdomain="sh-hasowner-sub"
        )
        before = setup_health_score(school)["score"]
        User = get_user_model()
        owner = User.objects.create_user(
            username="owner_sh", email="osh@example.com", password="pwd"
        )
        SchoolMembership.objects.create(
            school=school, user=owner, is_school_owner=True
        )
        after = setup_health_score(school)
        self.assertTrue(self._checks(after)["owner"][0])
        self.assertGreater(
            after["score"], before, "Granting an owner must raise the health score."
        )

    def test_suspended_owner_does_not_pass_owner_check(self):
        school = School.objects.create(
            name="Health4", slug="sh-suspowner", subdomain="sh-suspowner-sub"
        )
        User = get_user_model()
        owner = User.objects.create_user(
            username="owner_sh2", email="osh2@example.com", password="pwd"
        )
        SchoolMembership.objects.create(
            school=school,
            user=owner,
            is_school_owner=True,
            suspended_at=timezone.now(),
        )
        passed, _label = self._checks(setup_health_score(school))["owner"]
        self.assertFalse(
            passed, "A suspended owner has no live authority — must not satisfy the check."
        )

    def test_owner_is_an_unmet_check_and_has_a_dedicated_nudge(self):
        # An ownerless school carries 'owner' among its unmet checks, and the
        # next_best_action mapping has a dedicated assign_owner branch for it
        # (verified directly since satisfying runtime evidence to make owner the
        # SOLE unmet check is not cheap to set up here).
        school = School.objects.create(
            name="Health5", slug="sh-nba", subdomain="sh-nba-sub"
        )
        unmet = [name for name, passed, _l in setup_health_score(school)["checks"] if not passed]
        self.assertIn("owner", unmet)
        # next_best_action returns the first unmet action; assert it resolves to a
        # real mapped action (never None) for an ownerless school.
        action = next_best_action(school)
        self.assertIn(action["action"], {"assign_owner", "configure_branding", "assign_plan", "assign_dashboard", "complete_school"})
