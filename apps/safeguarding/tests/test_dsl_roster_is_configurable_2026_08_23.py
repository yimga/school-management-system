"""A school must be able to NAME its Designated Safeguarding Lead.

``user_is_dsl`` has a deliberate, documented fallback: with no roster configured,
tenant ADMIN/PRINCIPAL/OWNER may triage, so a child-protection concern is never
dispatched into the void. That fallback is right. What was wrong is that it could
never end -- **no product surface could write the roster it waits for**:

* ``safeguarding["dsl_user_ids"]`` is read at services.py:57 and written nowhere
  in the product; the only writer in the tree is a test helper.
* ``safeguarding["stakeholder_pipeline"]`` is written only by
  ``apply_stakeholder_pipeline``, fed by the wizard step
  ``encrypted_stakeholder_pipeline`` -- a ``ranked_list`` that carried NO
  ``options_resolver``, so it collected free-text labels. ``int(raw_uid)`` at
  services.py:76 then dropped every row.

So ``load_dsl_assignments`` returned ``[]`` for every real tenant, permanently, with
two consequences: every tenant administrator could read and transition every open
child-protection concern, and a genuinely designated lead who is a TEACHER or
COUNSELLOR was refused her own inbox -- she is not a superuser, her role is not in
the admin set, and the empty roster made ``is_dsl`` False.

The sibling ``ranked_list`` step ``gateway_prioritization`` already carries a
resolver, so this is the odd one out rather than an unsupported shape.
"""

from __future__ import annotations

import json
import pathlib
import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.safeguarding.services import load_dsl_assignments, user_is_dsl
from apps.schools.models import School, SchoolMembership

_WIZARD = (
    pathlib.Path(__file__).resolve().parents[3]
    / "apps"
    / "setup_studio"
    / "wizards"
    / "dynamic_safeguarding_incident_medical.json"
)
_STEP_KEY = "encrypted_stakeholder_pipeline"


def _step():
    doc = json.loads(_WIZARD.read_text(encoding="utf-8"))
    for step in doc.get("steps", []) or []:
        if step.get("key") == _STEP_KEY:
            return step
    raise AssertionError(f"{_STEP_KEY} is no longer in {_WIZARD.name}")


class StakeholderStepHasAnOptionSourceTests(TestCase):
    def test_the_step_still_exists_and_is_a_ranked_list(self):
        # Calibration: the assertions below are meaningless if the step was renamed.
        self.assertEqual(_step().get("input_type"), "ranked_list")

    def test_the_step_can_offer_real_people_to_rank(self):
        resolver = _step().get("options_resolver")
        self.assertTrue(
            resolver,
            "encrypted_stakeholder_pipeline is the step that names the school's DSL. "
            "Without an options_resolver it collects free text, load_dsl_assignments "
            "drops every row, and the roster can never be configured.",
        )
        self.assertIn("::", resolver, resolver)


class DslRosterEndToEndTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        slug = f"dsl-{uuid.uuid4().hex[:8]}"
        cls.school = School.objects.create(name="DSL School", slug=slug, subdomain=slug)
        cls.admin = User.objects.create_user(username=f"adm_{slug}", password="x")
        cls.admin.role = "ADMIN"
        cls.admin.save(update_fields=["role"])
        cls.teacher = User.objects.create_user(username=f"tch_{slug}", password="x")
        cls.teacher.role = "TEACHER"
        cls.teacher.save(update_fields=["role"])
        for user, role in ((cls.admin, "ADMIN"), (cls.teacher, "TEACHER")):
            SchoolMembership.objects.create(user=user, school=cls.school, role=role)

    def test_before_configuration_the_documented_fallback_is_in_force(self):
        """Not a bug -- the state the fallback exists for. Pinned so the fix is visible."""
        self.assertEqual(load_dsl_assignments(self.school), [])
        self.assertTrue(user_is_dsl(self.admin, self.school))
        self.assertFalse(
            user_is_dsl(self.teacher, self.school),
            "a teacher is not a DSL until somebody names her one",
        )

    def _configure_from_the_resolver(self):
        """Drive the REAL wizard path: resolver -> its values -> the step's writer.

        Going through the resolver is the point. Handing the writer ids I made up
        myself would prove the writer works while leaving the actual defect --
        that nothing can produce those ids -- untested.
        """
        from apps.setup_studio import wizard_resolvers

        module_path, _, func_name = _step()["options_resolver"].partition("::")
        self.assertEqual(module_path, "apps.setup_studio.wizard_resolvers", module_path)
        resolver = getattr(wizard_resolvers, func_name)
        options = resolver(request=None, school=self.school)

        offered = {str(o["value"]) for o in options}
        self.assertIn(
            str(self.teacher.pk),
            offered,
            "the school's own staff must be offerable as the DSL",
        )
        wizard_resolvers.write_safeguarding_stakeholders(
            school=self.school,
            wizard_key="dynamic_safeguarding_incident_medical",
            step_key=_STEP_KEY,
            payload={"value": [str(self.teacher.pk)]},
            actor_user_id=self.admin.pk,
        )
        self.school.refresh_from_db()

    def test_the_named_lead_can_reach_her_own_inbox(self):
        self._configure_from_the_resolver()
        assignments = load_dsl_assignments(self.school)
        self.assertEqual([a.user_id for a in assignments], [self.teacher.pk])
        self.assertTrue(
            user_is_dsl(self.teacher, self.school),
            "the named DSL was locked out of the module she is responsible for",
        )

    def test_naming_a_lead_closes_the_blanket_admin_fallback(self):
        """The fallback is scoped to 'nobody named yet', not to 'admins forever'."""
        self._configure_from_the_resolver()
        self.assertFalse(
            user_is_dsl(self.admin, self.school),
            "once a school has named its DSL, an unrelated tenant admin must no "
            "longer be able to read every child-protection concern",
        )

    def test_urgent_alerts_go_to_the_named_lead_not_every_admin(self):
        from apps.safeguarding.services import resolve_dsl_recipients

        before = {u.pk for u in resolve_dsl_recipients(self.school)}
        self.assertIn(self.admin.pk, before, "fallback pool should be the admins")
        self._configure_from_the_resolver()
        after = {u.pk for u in resolve_dsl_recipients(self.school)}
        self.assertEqual(after, {self.teacher.pk})
