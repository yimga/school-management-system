"""Staff portability: the explicit path that lands teachers on a sovereign box.

The first two tests are the MEASUREMENTS that made this module necessary, kept as tests so
nobody has to rediscover them:

  * the tenant bundle carries `people.teacherprofile` but NOT `accounts.user`, and its
    import therefore rolls back entirely rather than skipping the teachers;
  * the delta rail refuses a teacher CREATE in the cloud->box direction.

If either of those ever stops being true, these tests fail and this whole module becomes
deletable — which is the outcome to want.
"""
from __future__ import annotations

import base64
import gzip
import json
import uuid

from django.test import TestCase

from apps.academics.models import Department
from apps.accounts.models import User
from apps.lifecycle.staff_portability import (
    BUNDLE_FORMAT,
    export_staff_bundle,
    import_staff_bundle,
    inspect_staff_bundle,
)
from apps.lifecycle.tenant_dr_snapshot import decrypt_blob
from apps.lifecycle.tenant_portability import export_tenant_bundle, import_tenant_bundle
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership


def _school(prefix="staff"):
    uid = uuid.uuid4().hex[:8]
    school = School.objects.create(
        name=f"{prefix} {uid}",
        slug=f"{prefix}-{uid}",
        subdomain=f"{prefix}{uid}",
        is_active=True,
    )
    owner = User.objects.create_user(
        username=f"owner_{uid}", password="Test1234", email=f"o{uid}@t.com"
    )
    SchoolMembership.objects.create(
        user=owner, school=school, role="ADMIN", is_primary=True
    )
    return school, owner, uid


def _teachers(school, uid, n=3, department=None):
    users, profiles = [], []
    for i in range(n):
        u = User.objects.create_user(
            username=f"t{i}_{uid}", password="Test1234", email=f"t{i}{uid}@t.com"
        )
        p = TeacherProfile.objects.create(
            school=school, user=u, staff_id=f"S-{i}-{uid}", department=department
        )
        users.append(u)
        profiles.append(p)
    return users, profiles


class WhyThisModuleExistsTests(TestCase):
    """The two blocked paths, pinned."""

    def test_tenant_bundle_omits_the_logins_it_depends_on(self):
        school, _owner, uid = _school("omit")
        _teachers(school, uid, n=1)
        payload = json.loads(
            gzip.decompress(
                decrypt_blob(
                    base64.b64decode(json.loads(export_tenant_bundle(school))["blob_b64"]),
                    school_id=str(school.id),
                )
            )
        )
        self.assertIn(
            "people.teacherprofile",
            payload["tables"],
            "the tenant bundle is expected to carry teacher PROFILES",
        )
        self.assertNotIn(
            "accounts.user",
            payload["tables"],
            "accounts is not a tenant app, so the logins are expected to be ABSENT -- "
            "this asymmetry is the whole reason staff_portability exists",
        )

    def test_tenant_bundle_import_fails_whole_when_the_login_is_absent(self):
        """Not 'skips the teacher' — rolls back everything. Measured 2026-08-29."""
        school, _owner, uid = _school("roll")
        users, _profiles = _teachers(school, uid, n=1)
        bundle = export_tenant_bundle(school)
        users[0].delete()  # cascades the profile; the box's starting state

        with self.assertRaises(Exception) as ctx:
            import_tenant_bundle(bundle, expected_school_id=school.id)
        self.assertIn("User", str(ctx.exception))
        self.assertEqual(
            TeacherProfile.objects.filter(school=school).count(),
            0,
            "the failed import must leave nothing behind",
        )

    def test_the_delta_rail_refuses_a_teacher_create_downward(self):
        from apps.api.sync_services import _INSERT_HELD_ENTITIES

        self.assertIn(
            "teacher",
            _INSERT_HELD_ENTITIES,
            "if the rail ever learns to create teachers, this module is redundant",
        )


class StaffBundleRoundTripTests(TestCase):
    def test_round_trip_lands_logins_and_profiles_pk_preserving(self):
        school, _owner, uid = _school("rt")
        dept = Department.objects.create(
            name=f"Sci {uid}", code=f"SCI{uid[:4]}", school=school
        )
        users, profiles = _teachers(school, uid, n=3, department=dept)
        user_pks = [u.pk for u in users]
        teacher_pks = [p.pk for p in profiles]

        data = export_staff_bundle(school)
        User.objects.filter(pk__in=user_pks).delete()
        self.assertEqual(TeacherProfile.objects.filter(school=school).count(), 0)

        result = import_staff_bundle(data, expected_school_id=school.id)

        self.assertEqual(result["users"], 3)
        self.assertEqual(result["teachers"], 3)
        self.assertEqual(
            sorted(TeacherProfile.objects.filter(school=school).values_list("pk", flat=True)),
            sorted(teacher_pks),
            "pks must be preserved or later delta sync cannot match by pk",
        )
        for t in TeacherProfile.objects.filter(school=school):
            self.assertTrue(User.objects.filter(pk=t.user_id).exists())
            self.assertEqual(t.department_id, dept.pk)

    def test_carried_password_still_authenticates(self):
        """The offline point of the box: a teacher can sign in with no cloud."""
        school, _owner, uid = _school("pw")
        users, _p = _teachers(school, uid, n=1)
        username = users[0].username
        data = export_staff_bundle(school)
        users[0].delete()

        import_staff_bundle(data, expected_school_id=school.id)
        landed = User.objects.get(username=username)
        self.assertTrue(landed.check_password("Test1234"))

    def test_reset_passwords_lands_an_unusable_login(self):
        school, _owner, uid = _school("reset")
        users, _p = _teachers(school, uid, n=1)
        username = users[0].username
        data = export_staff_bundle(school)
        users[0].delete()

        result = import_staff_bundle(
            data, expected_school_id=school.id, reset_passwords=True
        )
        self.assertEqual(result["passwords"], "reset")
        landed = User.objects.get(username=username)
        self.assertFalse(landed.has_usable_password())
        self.assertFalse(landed.check_password("Test1234"))
        self.assertTrue(landed.requires_password_change)

    def test_is_superuser_is_never_carried(self):
        """A data import must not be able to mint an administrator on the box."""
        school, _owner, uid = _school("su")
        users, _p = _teachers(school, uid, n=1)
        User.objects.filter(pk=users[0].pk).update(is_superuser=True)
        username = users[0].username
        data = export_staff_bundle(school)
        users[0].delete()

        import_staff_bundle(data, expected_school_id=school.id)
        self.assertFalse(
            User.objects.get(username=username).is_superuser,
            "the bundle must never confer superuser on the target",
        )

    def test_import_is_idempotent(self):
        school, _owner, uid = _school("idem")
        _users, _p = _teachers(school, uid, n=2)
        data = export_staff_bundle(school)

        first = import_staff_bundle(data, expected_school_id=school.id)
        second = import_staff_bundle(data, expected_school_id=school.id)
        self.assertEqual(first["teachers"], second["teachers"])
        self.assertEqual(TeacherProfile.objects.filter(school=school).count(), 2)


class StaffBundleSafetyTests(TestCase):
    def test_a_pk_owned_by_a_different_account_aborts_the_import(self):
        """`loaddata` semantics would silently overwrite the box's own owner login."""
        school, _owner, uid = _school("clash")
        users, _p = _teachers(school, uid, n=1)
        pk = users[0].pk
        data = export_staff_bundle(school)
        users[0].delete()
        # Something else on the box now holds that pk.
        User.objects.create_user(
            username=f"local_{uid}", password="Test1234", email=f"l{uid}@t.com", pk=pk
        )

        with self.assertRaises(ValueError) as ctx:
            import_staff_bundle(data, expected_school_id=school.id)
        self.assertIn("staff_bundle_pk_collision", str(ctx.exception))
        self.assertEqual(
            User.objects.get(pk=pk).username,
            f"local_{uid}",
            "the local account must survive a refused import untouched",
        )

    def test_a_username_already_taken_by_another_pk_aborts(self):
        """Unique on `username`, so this would otherwise die on the constraint mid-import."""
        school, _owner, uid = _school("uname")
        users, _p = _teachers(school, uid, n=1)
        name = users[0].username
        data = export_staff_bundle(school)
        users[0].delete()
        # Some other account on the box has since taken that username.
        User.objects.create_user(username=name, password="Test1234", email=f"x{uid}@t.com")

        with self.assertRaises(ValueError) as ctx:
            import_staff_bundle(data, expected_school_id=school.id)
        self.assertIn("staff_bundle_pk_collision", str(ctx.exception))
        self.assertIn("username", str(ctx.exception))

    def test_a_bundle_for_another_school_is_refused(self):
        school_a, _o, uid_a = _school("a")
        _teachers(school_a, uid_a, n=1)
        school_b, _o2, _uid_b = _school("b")
        data = export_staff_bundle(school_a)

        with self.assertRaises(ValueError) as ctx:
            import_staff_bundle(data, expected_school_id=school_b.id)
        self.assertIn("staff_bundle_school_mismatch", str(ctx.exception))

    def test_a_tampered_bundle_is_refused_before_decrypt(self):
        school, _owner, uid = _school("tamper")
        _teachers(school, uid, n=1)
        container = json.loads(export_staff_bundle(school))
        container["sig"] = "0" * len(container["sig"])

        with self.assertRaises(ValueError) as ctx:
            import_staff_bundle(json.dumps(container).encode("utf-8"))
        self.assertIn("staff_bundle_signature_mismatch", str(ctx.exception))

    def test_an_absent_optional_fk_is_nulled_and_REPORTED(self):
        """A missing pay scale must not roll the import back, and must not be silent."""
        from decimal import Decimal

        from apps.payroll.models import PayScale

        school, _owner, uid = _school("fk")
        users, profiles = _teachers(school, uid, n=1)
        # PayScale is not school-scoped and `code` is unique; it does not ride the
        # delta rail either, which is exactly why a box usually lacks it.
        scale = PayScale.objects.create(
            name=f"Grade A {uid}",
            code=f"GA{uid[:6]}",
            min_salary=Decimal("100000.00"),
            max_salary=Decimal("200000.00"),
        )
        TeacherProfile.objects.filter(pk=profiles[0].pk).update(pay_scale=scale)

        data = export_staff_bundle(school)
        users[0].delete()
        scale.delete()  # the box never received it: PayScale does not ride the rail

        result = import_staff_bundle(data, expected_school_id=school.id)
        self.assertEqual(result["teachers"], 1)
        self.assertEqual(result["dropped_references"].get("pay_scale_id"), 1)
        self.assertIsNone(
            TeacherProfile.objects.get(pk=profiles[0].pk).pay_scale_id,
            "the reference had to be dropped for the row to land at all",
        )

    def test_format_is_pinned(self):
        self.assertEqual(BUNDLE_FORMAT, "rmc-staff-bundle/1")


class ManagementCommandTests(TestCase):
    """The two commands an operator actually types, driven end to end."""

    def test_export_then_dry_run_then_import(self):
        import io
        import pathlib
        import tempfile

        from django.core.management import call_command

        school, _owner, uid = _school("cmd")
        users, profiles = _teachers(school, uid, n=2)
        out = pathlib.Path(tempfile.mkdtemp()) / "staff.rmcstaff"

        buf = io.StringIO()
        call_command("export_tenant_staff", slug=school.slug, out=str(out), stdout=buf)
        self.assertTrue(out.exists())
        self.assertIn("Exported 2 teacher(s)", buf.getvalue())
        self.assertIn("password hashes", buf.getvalue())

        User.objects.filter(pk__in=[u.pk for u in users]).delete()

        dry = io.StringIO()
        call_command("import_tenant_staff", in_path=str(out), dry_run=True, stdout=dry)
        self.assertIn("Would import 2 login(s)", dry.getvalue())
        self.assertIn("No pk collisions", dry.getvalue())
        self.assertEqual(
            TeacherProfile.objects.filter(school=school).count(), 0,
            "--dry-run must write nothing",
        )

        real = io.StringIO()
        call_command(
            "import_tenant_staff",
            in_path=str(out),
            expect_school_id=str(school.id),
            stdout=real,
        )
        self.assertIn("Imported 2 login(s)", real.getvalue())
        self.assertEqual(TeacherProfile.objects.filter(school=school).count(), 2)

    def test_import_command_refuses_a_bundle_for_another_school(self):
        import io
        import pathlib
        import tempfile

        from django.core.management import call_command
        from django.core.management.base import CommandError

        school_a, _o, uid_a = _school("cmda")
        _teachers(school_a, uid_a, n=1)
        school_b, _o2, _u = _school("cmdb")
        out = pathlib.Path(tempfile.mkdtemp()) / "a.rmcstaff"
        call_command("export_tenant_staff", slug=school_a.slug, out=str(out), stdout=io.StringIO())

        with self.assertRaises(CommandError) as ctx:
            call_command(
                "import_tenant_staff",
                in_path=str(out),
                expect_school_id=str(school_b.id),
                stdout=io.StringIO(),
            )
        self.assertIn("school_mismatch", str(ctx.exception))


class ProfileNumberedDifferentlyTests(TestCase):
    """The live-box shape, measured on the Gilead appliance 2026-08-31.

    39 real staff on both sides, the SAME people, USER pks agreeing -- and teacher
    PROFILE pks disagreeing, because each side created its own profile row locally
    (cloud 2+, box 28+). The user-only guard is silent on that, so the import used to
    reach `update_or_create(pk=<cloud pk>)` and violate the `TeacherProfile.user`
    OneToOne index: an opaque IntegrityError rolling the whole import back, which is
    exactly the failure the guard exists to replace with a reason.
    """

    def _diverge(self, prefix):
        """Cloud bundle in hand; box holds the same person's profile at another pk."""
        school, _owner, uid = _school(prefix)
        users, profiles = _teachers(school, uid, n=1)
        data = export_staff_bundle(school)
        cloud_pk = profiles[0].pk
        TeacherProfile.objects.filter(pk=cloud_pk).delete()
        # Explicit pk: deleting the max rowid and re-inserting would REUSE it on
        # SQLite, and the test would then prove nothing.
        local = TeacherProfile.objects.create(
            pk=cloud_pk + 5000, school=school, user=users[0], staff_id=f"LOCAL-{uid}"
        )
        self.assertNotEqual(local.pk, cloud_pk)
        return school, uid, data, local

    def test_it_is_refused_with_a_reason_not_an_integrity_error(self):
        school, uid, data, local = self._diverge("prof")

        with self.assertRaises(ValueError) as ctx:
            import_staff_bundle(data, expected_school_id=school.id)
        message = str(ctx.exception)
        self.assertIn("staff_bundle_pk_collision", message)
        self.assertIn("already holds teacher profile", message)
        self.assertEqual(
            TeacherProfile.objects.get(pk=local.pk).staff_id,
            f"LOCAL-{uid}",
            "a refused import must leave the box's own row exactly as it was",
        )

    def test_the_dry_run_says_the_same_thing(self):
        """A dry run that passes where the import refuses is worse than no dry run."""
        school, _uid, data, _local = self._diverge("dry")

        report = inspect_staff_bundle(data, expected_school_id=school.id)
        self.assertTrue(report["collisions"])
        self.assertIn("already holds teacher profile", report["collisions"][0])

    def test_an_ordinary_re_import_is_still_idempotent(self):
        """The guard must fire on DIVERGENCE only -- never on the same row twice."""
        school, _owner, uid = _school("idem2")
        _users, _profiles = _teachers(school, uid, n=2)
        data = export_staff_bundle(school)

        first = import_staff_bundle(data, expected_school_id=school.id)
        second = import_staff_bundle(data, expected_school_id=school.id)
        self.assertEqual(first["teachers"], 2)
        self.assertEqual(second["teachers"], 2)
        self.assertEqual(TeacherProfile.objects.filter(school=school).count(), 2)

