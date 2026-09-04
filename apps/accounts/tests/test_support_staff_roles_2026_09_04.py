"""Non-teaching staff can exist, and cost nobody a privilege they did not earn.

Written against a real 49-row staff directory (Gilead Technical High School,
2026-09-04) whose COORDINATOR, DRIVER, SECURITY and ADMINISTRATIVE ASSISTANT / IT
rows could not be imported at all: ``User.Role`` had no token for any of them, so
``staff_role_map`` held the rows rather than collapse them onto TEACHER -- which
would have been a real grant, since the TEACHER access role carries
``attendance.manage`` and ``grades.enter``.

The three things that must all hold at once, and each has a test here:

1. the roles EXIST, and every one is materialised (the DPO/EMPLOYER defect: a
   ``User.Role`` with no ``ROLE_TEMPLATES`` entry gets an empty ``roles`` M2M and
   resolves every granular check to False, silently and forever);
2. an unreadable or blank title lands on a role that grants NOTHING; and
3. adding the vocabulary did not make any previously-working cell worse.

(3) is the one that is easy to get wrong. ``TEACHER /DRIVER`` resolved to TEACHER
only because DRIVER was an unknown word; under the old "all segments must agree"
rule, teaching the map DRIVER would have turned that cell from resolved into
held. An import must not regress because the system learned a word.
"""

from django.test import TestCase

from apps.accounts.models import AccessRole, Permission, User
from apps.accounts.permissions import (
    OPS_MODULE_EXTRA_ROLE_CODES,
    user_can_access_ops_module,
)
from apps.accounts.signals import ROLE_TEMPLATES
from apps.test_utils.rbac_seed import grant, seed_support_staff_catalog
from apps.migration_cloud.staff_role_map import (
    ROLE_SUPPORT_STAFF,
    resolve_staff_role,
    staff_role_segments,
    unresolvable_staff_role,
)

# The non-teaching roles added on 2026-09-04. Listed literally rather than
# derived from User.Role: a test that recomputes the thing it checks passes when
# the source list is empty, and this list existing is the point.
NEW_STAFF_ROLES = [
    "SUPPORT_STAFF",
    "COORDINATOR",
    "LIBRARIAN",
    "NURSE",
    "LAB_TECHNICIAN",
    "STOREKEEPER",
    "DRIVER",
    "SECURITY",
    "MAINTENANCE",
    "CATERING_STAFF",
    "RECEPTIONIST",
    "COUNSELOR",
]


class NewStaffRolesAreFullyMaterialisedTests(TestCase):
    """A declared role with no template or no AccessRole row is a silent deny-all."""

    @classmethod
    def setUpTestData(cls):
        # Runs the MIGRATION's own data step, so this still tests what 0065 does
        # while not depending on a shared --keepdb database still holding its
        # rows. See apps/test_utils/rbac_seed.py for what empties them.
        seed_support_staff_catalog()

    def test_every_new_role_is_a_user_role_choice(self):
        declared = {value for value, _label in User.Role.choices}
        missing = [code for code in NEW_STAFF_ROLES if code not in declared]
        self.assertEqual(missing, [], "not declared on User.Role: %s" % missing)

    def test_every_new_role_has_a_role_template(self):
        missing = [code for code in NEW_STAFF_ROLES if not ROLE_TEMPLATES.get(code)]
        self.assertEqual(
            missing,
            [],
            "no ROLE_TEMPLATES entry, so these accounts get an EMPTY roles M2M "
            "and resolve every granular permission check to False: %s" % missing,
        )

    def test_every_new_role_has_a_seeded_global_access_role(self):
        present = set(
            AccessRole.objects.filter(
                code__in=NEW_STAFF_ROLES, school__isnull=True
            ).values_list("code", flat=True)
        )
        missing = sorted(set(NEW_STAFF_ROLES) - present)
        self.assertEqual(missing, [], "AccessRole row never seeded: %s" % missing)

    def test_the_roles_carry_the_permissions_the_job_needs(self):
        """Not just "a role exists" -- the librarian must actually reach the library."""
        for role_code, permission_code in [
            ("LIBRARIAN", "library.manage"),
            ("NURSE", "health.manage"),
            ("DRIVER", "transport.view"),
            ("SECURITY", "visitors.manage"),
            ("STOREKEEPER", "stock.manage"),
            ("MAINTENANCE", "maintenance.manage"),
            ("CATERING_STAFF", "canteen.manage"),
            ("COORDINATOR", "attendance.view"),
        ]:
            with self.subTest(role=role_code):
                user = User.objects.create_user(
                    username="perm.%s" % role_code.lower(), password="x", role=role_code
                )
                self.assertTrue(
                    user.has_feature_permission(permission_code),
                    "%s cannot reach %s" % (role_code, permission_code),
                )

    def test_a_role_does_not_get_a_neighbours_permission(self):
        """The negative half, with the positive half above as its control."""
        driver = User.objects.create_user(
            username="perm.driver.neg", password="x", role=User.Role.DRIVER
        )
        self.assertTrue(driver.has_feature_permission("transport.view"))
        for code in ("library.manage", "health.manage", "visitors.manage"):
            with self.subTest(code=code):
                self.assertFalse(driver.has_feature_permission(code))

    def test_every_permission_a_new_role_names_actually_exists(self):
        """An unseeded code denies everyone forever; it does not raise."""
        seeded = set(Permission.objects.values_list("code", flat=True))
        dangling = {}
        for role in AccessRole.objects.filter(
            code__in=NEW_STAFF_ROLES, school__isnull=True
        ):
            codes = set(role.permissions.values_list("code", flat=True))
            if codes - seeded:
                dangling[role.code] = sorted(codes - seeded)
        self.assertEqual(dangling, {})

    def test_role_template_materialises_on_save(self):
        user = User.objects.create_user(
            username="gate.driver", password="x", role=User.Role.DRIVER
        )
        self.assertIn(
            "DRIVER", set(user.roles.values_list("code", flat=True))
        )


class SupportStaffGrantsNothingTests(TestCase):
    """The base identity has to be genuinely inert or none of this is safe."""

    @classmethod
    def setUpTestData(cls):
        seed_support_staff_catalog()
        # The positive control. Without it, "SUPPORT_STAFF cannot reach
        # attendance.manage" passes on a database where NOTHING can reach
        # anything -- which is the state a flushed catalog leaves behind, and a
        # green test that cannot fail is worse than no test.
        grant("TEACHER", "attendance.manage", "grades.enter")

    def test_the_control_holds_what_support_staff_must_not(self):
        teacher = User.objects.create_user(
            username="gate.teacher", password="x", role=User.Role.TEACHER
        )
        self.assertTrue(teacher.has_feature_permission("attendance.manage"))
        self.assertTrue(teacher.has_feature_permission("grades.enter"))

    def test_support_staff_access_role_holds_no_permissions(self):
        role = AccessRole.objects.get(code="SUPPORT_STAFF", school__isnull=True)
        self.assertEqual(list(role.permissions.all()), [])

    def test_support_staff_holds_neither_teacher_capability(self):
        user = User.objects.create_user(
            username="gate.support", password="x", role=User.Role.SUPPORT_STAFF
        )
        # The two codes the TEACHER access role carries, which is exactly what a
        # blank or unreadable title used to be granted.
        self.assertFalse(user.has_feature_permission("attendance.manage"))
        self.assertFalse(user.has_feature_permission("grades.enter"))

    def test_a_blank_title_does_not_become_a_teacher(self):
        """Blank claims no privilege, so the import must grant none."""
        self.assertEqual(
            resolve_staff_role("", default=ROLE_SUPPORT_STAFF), ROLE_SUPPORT_STAFF
        )
        self.assertNotEqual(
            resolve_staff_role("", default=ROLE_SUPPORT_STAFF), User.Role.TEACHER
        )


class DirectoryLabelsResolveTests(TestCase):
    """The four labels a real directory could not import, and why each one lands."""

    def test_previously_unmappable_titles_now_resolve(self):
        for label, expected in [
            ("COORDINATOR", "COORDINATOR"),
            ("DRIVER", "DRIVER"),
            ("SECURITY", "SECURITY"),
            ("BABILA LEONARD's post is DRIVER", None),  # free text stays unreadable
        ]:
            with self.subTest(label=label):
                if expected is None:
                    self.assertIsNotNone(unresolvable_staff_role(label))
                else:
                    self.assertIsNone(unresolvable_staff_role(label))
                    self.assertEqual(resolve_staff_role(label), expected)

    def test_support_titles_map_in_english_and_french(self):
        for label, expected in [
            ("Security Guard", "SECURITY"),
            ("Gardien", "SECURITY"),
            ("School Bus Driver", "DRIVER"),
            ("Chauffeur", "DRIVER"),
            ("Librarian", "LIBRARIAN"),
            ("Bibliothecaire", "LIBRARIAN"),
            ("School Nurse", "NURSE"),
            ("Laboratory Technician", "LAB_TECHNICIAN"),
            ("Storekeeper", "STOREKEEPER"),
            ("Caretaker", "MAINTENANCE"),
            ("Cook", "CATERING_STAFF"),
            ("Receptionist", "RECEPTIONIST"),
            ("Guidance Counsellor", "COUNSELOR"),
        ]:
            with self.subTest(label=label):
                self.assertEqual(resolve_staff_role(label), expected)

    def test_matron_is_boarding_not_clinic(self):
        """Mapped by what the job IS, not by which word it sounds like."""
        self.assertEqual(resolve_staff_role("Matron"), "BOARDING_MANAGER")


class CompoundCellsDidNotRegressTests(TestCase):
    """Teaching the map a new word must not un-resolve a cell that already worked."""

    def test_teacher_slash_driver_is_still_a_teacher(self):
        # Under the old "every segment must name the SAME role" rule this cell
        # resolved to TEACHER only because DRIVER was unknown. Now that DRIVER is
        # a real role, first-segment-wins is what keeps the answer right.
        self.assertEqual(resolve_staff_role("TEACHER /DRIVER"), User.Role.TEACHER)
        self.assertIsNone(unresolvable_staff_role("TEACHER /DRIVER"))

    def test_every_compound_cell_from_the_real_directory(self):
        for label, expected in [
            ("BURSAR/ PARTNER", "BURSAR"),
            ("SCHOOL SYSTEM ADMINISTRATOR/IT", "IT_ADMIN"),
            ("ADMINISTRATIVE ASSISTANT / IT", "SECRETARY"),
            ("TEACHER /DRIVER", "TEACHER"),
        ]:
            with self.subTest(label=label):
                self.assertEqual(resolve_staff_role(label), expected)

    def test_the_losing_segment_is_reported_not_thrown_away(self):
        segments = staff_role_segments("ADMINISTRATIVE ASSISTANT / IT")
        self.assertEqual(segments[0], "SECRETARY")
        self.assertIn("IT_ADMIN", segments)

    def test_a_forbidden_segment_still_forbids_the_whole_cell(self):
        """A staff sheet may never mint a superadmin, compound or not."""
        self.assertIsNotNone(unresolvable_staff_role("TEACHER / SUPERADMIN"))
        self.assertIsNotNone(unresolvable_staff_role("SUPERADMIN"))
        self.assertNotEqual(resolve_staff_role("TEACHER / SUPERADMIN"), "SUPERADMIN")


class OpsModuleAccessIsPerModuleTests(TestCase):
    """Each support role reaches its OWN module and no other."""

    def _user(self, role):
        return User.objects.create_user(
            username="ops.%s" % role.lower(), password="x", role=role
        )

    def test_librarian_reaches_the_library(self):
        self.assertTrue(user_can_access_ops_module("library")(self._user("LIBRARIAN")))

    def test_librarian_does_not_reach_transport(self):
        self.assertFalse(
            user_can_access_ops_module("transport")(self._user("LIBRARIAN"))
        )

    def test_driver_reaches_transport_and_nothing_else(self):
        driver = self._user("DRIVER")
        self.assertTrue(user_can_access_ops_module("transport")(driver))
        for module in ("library", "inventory", "clinic", "visitor_log", "canteen"):
            with self.subTest(module=module):
                self.assertFalse(user_can_access_ops_module(module)(driver))

    def test_nurse_reaches_the_clinic_which_keeps_its_narrower_base(self):
        nurse = self._user("NURSE")
        self.assertTrue(user_can_access_ops_module("clinic")(nurse))
        # HOD is in the BROAD ops set but not the clinic's narrower one; adding
        # the nurse must not have widened the clinic to general ops.
        self.assertFalse(user_can_access_ops_module("clinic")(self._user("HOD")))

    def test_broad_ops_roles_keep_every_module_they_had(self):
        admin = self._user("ADMIN")
        for module in OPS_MODULE_EXTRA_ROLE_CODES:
            with self.subTest(module=module):
                self.assertTrue(user_can_access_ops_module(module)(admin))

    def test_support_staff_reaches_no_ops_module_at_all(self):
        base = self._user("SUPPORT_STAFF")
        for module in OPS_MODULE_EXTRA_ROLE_CODES:
            with self.subTest(module=module):
                self.assertFalse(user_can_access_ops_module(module)(base))
