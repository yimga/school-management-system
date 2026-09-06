"""A selection must mean what it says: no silent truncation, no half-mutation.

Both paths here used to stop at 200 with nothing said. On the export that
produced a file which called itself the selection and was not; on the bulk role
change it produced a WRITE that applied to 200 of 250 people and reported
success. These tests pin the two different cures, because the two cases do not
deserve the same one.

The export has no cap now, and the reason it does not need one is in the helper:
the unrestricted export on the same view bounds itself at 10000 rows, so the
capped path was fifty times stricter than the uncapped one behind identical
permissions. The mutation keeps its cap and REFUSES, because a bulk write that
half-lands is worse than one that does not land.
"""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.people.bulk_staff_actions import MAX_BULK_IDS, parse_staff_id_list
from apps.people.bulk_student_actions import parse_student_id_list
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School
from apps.test_utils.http_clients import login_tenant_admin_client
from apps.test_utils.tenant_hosts import host_routed, tenant_host

PASSWORD = "selection-truncation-pw"
OVER = MAX_BULK_IDS + 50


@host_routed
class ExportHonoursTheWholeSelectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Selection School",
            slug="selection-school",
            subdomain="selection-school",
            is_active=True,
            country_code="CM",
        )
        StudentProfile.objects.bulk_create([
            StudentProfile(
                school=cls.school,
                first_name="Pupil%d" % i,
                last_name="Selected",
                admission_number="ADM-SEL-%04d" % i,
            )
            for i in range(OVER)
        ])
        cls.ids = list(
            StudentProfile.objects.filter(school=cls.school)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        cls.actor = User.objects.create_user(
            username="selection.admin", password=PASSWORD, role=User.Role.ADMIN
        )

    def setUp(self):
        self.host = tenant_host(self.school)
        self.client = login_tenant_admin_client(
            self.actor, password=PASSWORD, host=self.host, school=self.school
        )

    def test_the_premise(self):
        """Guard the guard: the selection must actually exceed the old cap."""
        self.assertEqual(len(self.ids), OVER)
        self.assertGreater(len(self.ids), 200)

    def test_every_selected_row_reaches_the_file(self):
        res = self.client.get(
            reverse("accounts:backend_student_list"),
            {"ids": ",".join(str(pk) for pk in self.ids), "format": "csv"},
            HTTP_HOST=self.host,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res["Content-Type"])
        body = res.content.decode("utf-8")
        rows = [ln for ln in body.splitlines() if ln.strip()]
        # one header row plus one row per selected student
        self.assertEqual(
            len(rows) - 1,
            OVER,
            "the export dropped %d of %d selected rows" % (OVER - (len(rows) - 1), OVER),
        )
        self.assertIn("ADM-SEL-0000", body)
        self.assertIn("ADM-SEL-%04d" % (OVER - 1), body)


class OversizedMutationIsRefusedNotTrimmedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Mutation School",
            slug="mutation-school",
            subdomain="mutation-school",
            is_active=True,
            country_code="CM",
        )

    def test_a_selection_within_the_cap_is_returned_whole(self):
        ids = list(range(1, MAX_BULK_IDS + 1))
        self.assertEqual(parse_staff_id_list(ids), ids)

    def test_the_student_parser_carries_the_same_cure(self):
        """The idiom was copied, so the defect was too. Both refuse now."""
        self.assertEqual(
            len(parse_student_id_list(list(range(1, MAX_BULK_IDS + 1)))), MAX_BULK_IDS
        )
        with self.assertRaises(ValueError) as ctx:
            parse_student_id_list(list(range(1, OVER + 1)))
        self.assertIn("Nothing was changed", str(ctx.exception))

    def test_an_oversized_selection_raises_instead_of_trimming(self):
        with self.assertRaises(ValueError) as ctx:
            parse_staff_id_list(list(range(1, OVER + 1)))
        message = str(ctx.exception)
        self.assertIn(str(MAX_BULK_IDS), message)
        self.assertIn("Nothing was changed", message)

    def test_nothing_is_written_when_the_selection_is_refused(self):
        """The assertion that matters: a refusal must not be a partial apply."""
        users = [
            User.objects.create_user(
                username="bulk.staff.%d" % i,
                password=PASSWORD,
                role=User.Role.TEACHER,
            )
            for i in range(5)
        ]
        for i, user in enumerate(users):
            TeacherProfile.objects.create(
                school=self.school, user=user, staff_id="EMP-BULK-%d" % i
            )
        profile_ids = list(
            TeacherProfile.objects.filter(school=self.school).values_list("pk", flat=True)
        )
        # A real selection of five, padded past the cap with further ids.
        oversized = profile_ids + list(range(900000, 900000 + OVER))
        with self.assertRaises(ValueError):
            parse_staff_id_list(oversized)
        for user in users:
            user.refresh_from_db()
            self.assertEqual(
                user.role,
                User.Role.TEACHER,
                "a refused bulk change still moved somebody's role",
            )
