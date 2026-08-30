"""The bring-up sequence must land staff — driven, not asserted from reading.

Measured on 2026-08-30, and the reason this file exists: the generated runbook had no
staff step at all, and its order actively destroyed teachers.

  * `migrate_identities` mints Users at FRESH box pks (its field list has no `id`).
  * `seed_operational_data` then loads `people.teacherprofile` carrying the CLOUD's
    `user_id`, because `people` is a tenant app while `accounts` is shared.
  * `import_tenant_bundle` is ONE `transaction.atomic()`, so the dangling FK does not
    skip the teachers — it rolls the WHOLE operational seed back. Not a partial
    import: students, classrooms, everything.

`test_the_generated_order_lands_every_teacher` drives the REAL step order out of
`EDGE_ONBOARDING_STEPS` rather than a sequence copied into the test, so it fails the
moment someone reorders or deletes the staff step.
"""
from __future__ import annotations

import uuid

from django.test import SimpleTestCase, TestCase

from apps.accounts.models import User
from apps.lifecycle.edge_onboarding import EDGE_ONBOARDING_STEPS, generate_runbook
from apps.lifecycle.staff_portability import export_staff_bundle, import_staff_bundle
from apps.lifecycle.tenant_identity_portability import (
    export_tenant_identities,
    import_tenant_identities,
)
from apps.lifecycle.tenant_portability import export_tenant_bundle, import_tenant_bundle
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership

# Simulates a mature cloud: pks far above anything a freshly provisioned box would
# allocate. Without this the box would re-use the deleted rowids and accidentally
# "preserve" pks, hiding the very defect under test.
_CLOUD_PK_BASE = 900_001


def _keys() -> list:
    return [s.key for s in EDGE_ONBOARDING_STEPS]


class RunbookSequenceTests(SimpleTestCase):
    """Structure only — no database, so these stay fast and always run."""

    def test_a_staff_step_exists(self):
        self.assertIn(
            "migrate_staff",
            _keys(),
            "the runbook must carry a staff step; without one a school with teachers "
            "cannot be brought up at all",
        )

    def test_staff_is_imported_before_identities_and_before_the_data_seed(self):
        keys = _keys()
        staff = keys.index("migrate_staff")
        self.assertLess(
            staff,
            keys.index("migrate_identities"),
            "import_tenant_staff is the only pk-preserving staff path; run it after "
            "import_tenant_identities and the username/pk guard refuses the import",
        )
        self.assertLess(
            staff,
            keys.index("seed_operational_data"),
            "the operational bundle carries teacherprofile.user_id at CLOUD pks, so "
            "the logins must already exist at those pks",
        )

    def test_the_cloud_export_produces_the_artifact_the_staff_step_consumes(self):
        by_key = {s.key: s for s in EDGE_ONBOARDING_STEPS}
        exported = by_key["export_cloud_artifacts"].command_template
        self.assertIn("export_tenant_staff", exported)
        self.assertIn(".rmcstaff", exported)
        self.assertIn(".rmcstaff", by_key["migrate_staff"].command_template)


class BringupPlanOrderTests(SimpleTestCase):
    """`edge_bringup` keeps its OWN ordered command list — and it actually runs them.

    The runbook in `edge_onboarding` is what an operator reads; this is what a one-shot
    bring-up EXECUTES. They drifted apart silently: both had the same missing staff
    step, and fixing only the one people read would have left the automated path broken.
    """

    def _plan(self, **kw):
        from apps.lifecycle.edge_bringup import BringupInputs, plan_prep_actions

        return [a["key"] for a in plan_prep_actions(BringupInputs(slug="s", **kw))]

    def test_a_staff_bundle_is_planned_before_the_identity_bundle(self):
        keys = self._plan(staff_path="/srv/rmc/s.rmcstaff", identity_path="/srv/rmc/s.rmcidentity")
        self.assertIn("migrate_staff", keys)
        self.assertLess(
            keys.index("migrate_staff"),
            keys.index("migrate_identities"),
            "identities first mints box-local pks and strands the data bundle",
        )

    def test_a_staff_bundle_is_planned_before_the_operational_data_bundle(self):
        keys = self._plan(
            staff_path="/srv/rmc/s.rmcstaff", data_bundle_path="/srv/rmc/s.rmcbundle"
        )
        self.assertLess(keys.index("migrate_staff"), keys.index("seed_operational_data"))

    def test_no_staff_bundle_means_no_staff_step(self):
        """A school with no teachers must not gain a step that would always fail."""
        self.assertNotIn("migrate_staff", self._plan(identity_path="/srv/rmc/s.rmcidentity"))

    def test_the_planned_command_is_the_real_one(self):
        from apps.lifecycle.edge_bringup import BringupInputs, plan_prep_actions

        action = next(
            a
            for a in plan_prep_actions(BringupInputs(slug="s", staff_path="/srv/rmc/s.rmcstaff"))
            if a["key"] == "migrate_staff"
        )
        self.assertEqual(action["cmd"], "import_tenant_staff")
        self.assertEqual(action["args"], ["--in", "/srv/rmc/s.rmcstaff"])


class BoxCommandRenderingTests(TestCase):
    """A box step an operator cannot run is not a step."""

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"box {uid}", slug=f"box-{uid}", subdomain=f"box{uid}", is_active=True
        )

    def _commands(self) -> dict:
        book = generate_runbook(self.school)
        return {row["key"]: row["command"] for row in book["steps"]}

    def test_no_box_step_tells_the_operator_to_run_a_bare_python(self):
        """`python: command not found` — there is no host interpreter on a box."""
        book = generate_runbook(self.school)
        offenders = [
            row["key"]
            for row in book["steps"]
            if row["runs_on"] == "box"
            and any(
                line.strip().startswith("python manage.py")
                for line in str(row["command"]).splitlines()
            )
        ]
        self.assertEqual(
            offenders,
            [],
            "the selfhost stack runs a BAKED image; these steps cannot run as written",
        )

    def test_a_box_import_copies_the_artifact_into_the_container_first(self):
        """/srv/rmc is not mounted into the container, so --in cannot see it."""
        cmd = self._commands()["migrate_staff"]
        lines = [ln.strip() for ln in cmd.splitlines() if ln.strip()]
        self.assertTrue(
            any(ln.startswith("docker compose") and " cp " in ln for ln in lines),
            f"expected a `docker compose cp` of the bundle, got: {lines}",
        )
        self.assertIn("--in /app/", cmd)
        self.assertNotIn("--in /srv/rmc/", cmd)

    def test_cloud_steps_are_left_alone(self):
        """Only the box runs in a container; the cloud export is a plain shell."""
        cmd = self._commands()["export_cloud_artifacts"]
        self.assertIn("python manage.py export_tenant_staff", cmd)
        self.assertNotIn("docker compose", cmd)

    def test_a_native_box_gets_the_original_commands_back(self):
        with self.settings(RMC_BOX_MANAGE_PREFIX="python manage.py"):
            cmd = self._commands()["migrate_staff"]
        self.assertTrue(cmd.strip().startswith("python manage.py import_tenant_staff"))
        self.assertIn("--in /srv/rmc/", cmd)


class OnboardingSequenceEndToEndTests(TestCase):
    """Drive the documented order for real and count the teachers at the end."""

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.uid = uid
        self.school = School.objects.create(
            name=f"seq {uid}", slug=f"seq-{uid}", subdomain=f"seq{uid}", is_active=True
        )
        self.owner = User.objects.create_user(
            username=f"owner_{uid}", password="Test1234", email=f"o{uid}@t.com"
        )
        SchoolMembership.objects.create(
            user=self.owner,
            school=self.school,
            role="ADMIN",
            is_primary=True,
            is_school_owner=True,
        )
        self.teacher_pks = []
        for i in range(3):
            u = User.objects.create(
                pk=_CLOUD_PK_BASE + i,
                username=f"t{i}_{uid}",
                email=f"t{i}{uid}@t.com",
            )
            u.set_password("Test1234")
            u.save()
            SchoolMembership.objects.create(user=u, school=self.school, role="TEACHER")
            TeacherProfile.objects.create(
                school=self.school, user=u, staff_id=f"S-{i}-{uid}"
            )
            self.teacher_pks.append(u.pk)

        # The three artifacts the cloud export step produces.
        self.staff_bundle = export_staff_bundle(self.school)
        self.identity_bundle = export_tenant_identities(self.school)
        self.tenant_bundle = export_tenant_bundle(self.school)

        # ...and now the box, as provision_shell leaves it: the School parent pinned
        # at the same UUID, and none of the staff.
        User.objects.filter(pk__in=self.teacher_pks).delete()
        self.assertEqual(TeacherProfile.objects.filter(school=self.school).count(), 0)

    def _actions(self) -> dict:
        sid = self.school.id
        return {
            "migrate_staff": lambda: import_staff_bundle(
                self.staff_bundle, expected_school_id=sid
            ),
            "migrate_identities": lambda: import_tenant_identities(
                self.identity_bundle, expected_school_id=sid, skip_mfa=True
            ),
            "seed_operational_data": lambda: import_tenant_bundle(
                self.tenant_bundle, expected_school_id=sid
            ),
        }

    def test_the_generated_order_lands_every_teacher(self):
        """The whole point. Order comes from the runbook, not from this test."""
        actions = self._actions()
        ran = []
        for step in EDGE_ONBOARDING_STEPS:
            action = actions.get(step.key)
            if action is None:
                continue
            ran.append(step.key)
            action()

        self.assertIn("migrate_staff", ran, "the runbook never imported the staff")
        landed = TeacherProfile.objects.filter(school=self.school)
        self.assertEqual(
            landed.count(), 3, "every teacher must survive the documented sequence"
        )
        self.assertEqual(
            sorted(landed.values_list("user_id", flat=True)),
            sorted(self.teacher_pks),
            "pks must match the cloud or delta sync cannot converge by UPDATE-by-pk",
        )
        for profile in landed:
            self.assertTrue(User.objects.filter(pk=profile.user_id).exists())

    def test_identities_before_staff_is_refused_rather_than_corrupting(self):
        """The trap the ordering exists to avoid, pinned so nobody 'fixes' the order."""
        import_tenant_identities(
            self.identity_bundle, expected_school_id=self.school.id, skip_mfa=True
        )
        # Identities minted the logins at fresh box pks, not the cloud's.
        self.assertFalse(
            User.objects.filter(pk__in=self.teacher_pks).exists(),
            "import_tenant_identities does not preserve pks — that is the whole trap",
        )
        with self.assertRaises(ValueError) as ctx:
            import_staff_bundle(self.staff_bundle, expected_school_id=self.school.id)
        self.assertIn("staff_bundle_pk_collision", str(ctx.exception))

    def test_the_old_order_destroyed_the_entire_operational_seed(self):
        """Characterisation of the bug: not 'teachers skipped' — nothing lands."""
        import_tenant_identities(
            self.identity_bundle, expected_school_id=self.school.id, skip_mfa=True
        )
        with self.assertRaises(Exception) as ctx:
            import_tenant_bundle(self.tenant_bundle, expected_school_id=self.school.id)
        self.assertIn("User", str(ctx.exception))
        self.assertEqual(
            TeacherProfile.objects.filter(school=self.school).count(),
            0,
            "the rollback leaves nothing behind — which is why it reads as 'no sync'",
        )
