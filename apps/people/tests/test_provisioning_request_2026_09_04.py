"""A person created on a box reaches the cloud -- as a question, not as a login.

The identity hold is not relaxed by any of this and these tests say so directly:
the rail still refuses the insert, still returns 409, and still mints nothing. What
is new is that the refusal is recorded, so a human can answer it, and that
answering it carries the box's anchor so the two sides converge afterwards
instead of ending up with the same person twice.

The measured case this is written against: a rebuilt Gilead box submitted the
same 39 teachers on all 687 sync cycles of one day. Every refusal was correct.
The staff never existed on the cloud. Both halves of that are tested here -- the
refusal still happens, and 687 refusals now produce ONE queue entry that says 687.
"""

from django.test import TestCase

from apps.accounts.models import User
from apps.api.sync_services import apply_edge_inserts
from apps.people.models import TeacherProfile
from apps.people.models_provisioning import ProvisioningRequest
from apps.people.provisioning_service import (
    approve_provisioning_request,
    decline_provisioning_request,
    record_refused_insert,
    sanitize_payload,
)
from apps.schools.models import School
from apps.test_utils.rbac_seed import seed_support_staff_catalog


class SanitizePayloadTests(TestCase):
    """The boundary between data and credential, tested at the boundary."""

    def test_credential_shaped_keys_are_dropped(self):
        out = sanitize_payload(
            {
                "first_name": "Ada",
                "password": "hunter2",
                "password_hash": "pbkdf2$...",
                "is_superuser": True,
                "is_staff": True,
                "user_id": 7,
                "last_login": "2026-01-01",
                "staff_id": "EMP-1",
            }
        )
        self.assertEqual(out, {"first_name": "Ada", "staff_id": "EMP-1"})

    def test_non_dict_is_empty(self):
        self.assertEqual(sanitize_payload(None), {})
        self.assertEqual(sanitize_payload("first_name=Ada"), {})


class RefusedInsertBecomesAQuestionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_support_staff_catalog()
        cls.school = School.objects.create(
            name="Provisioning School",
            slug="provisioning-school",
            subdomain="provisioning-school",
            is_active=True,
            country_code="CM",
        )
        cls.admin = User.objects.create_user(
            username="prov.admin", password="x", role=User.Role.ADMIN, is_staff=True
        )

    def _submit(self, coid="box-teacher-1", role="TEACHER"):
        # apply_edge_inserts returns {"created", "updated", "results"}; the
        # per-row outcomes are under "results", in the caller's original order.
        # sync_origin is what a real box push sets, and it is load-bearing here:
        # without it _get_entity_config excludes every DERIVED entity, so
        # "teacher" is not on the rail at all and the row 400s long before the
        # identity hold is reached. A test that omitted it would be asserting
        # about a different code path than the one production uses.
        return apply_edge_inserts(
            str(self.school.pk),
            self.admin,
            [
                {
                    "entity_type": "teacher",
                    "client_offline_id": coid,
                    "id": 4242,
                    "changes": {
                        "first_name": "Ada",
                        "last_name": "Nkeng",
                        "staff_id": "EMP-77",
                        "phone": "677000111",
                        "role": role,
                    },
                }
            ],
            sync_origin="edge-push",
        )

    # ------------------------------------------------- the hold still holds
    def test_the_insert_is_still_refused(self):
        results = self._submit()["results"]
        self.assertEqual(results[0]["status"], 409)
        self.assertEqual(results[0]["data"]["error"], "insert_held_for_entity")

    def test_no_account_and_no_profile_are_created(self):
        before = User.objects.count()
        self._submit()
        self.assertEqual(User.objects.count(), before, "the rail must mint nobody")
        self.assertFalse(TeacherProfile.objects.filter(school=self.school).exists())

    # ------------------------------------------------- the refusal goes somewhere
    def test_the_refusal_is_recorded_as_a_pending_request(self):
        self._submit()
        row = ProvisioningRequest.objects.get(
            school=self.school, client_offline_id="box-teacher-1"
        )
        self.assertEqual(row.status, ProvisioningRequest.Status.PENDING)
        self.assertEqual(row.entity_type, "teacher")
        self.assertEqual(row.payload["last_name"], "Nkeng")
        self.assertEqual(row.requested_role, "TEACHER")

    def test_the_box_is_told_where_the_question_went(self):
        results = self._submit()["results"]
        queued = results[0]["data"]["provisioning_request"]
        self.assertIsNotNone(queued, "a refusal with no next step is the old defect")
        self.assertEqual(queued["status"], ProvisioningRequest.Status.PENDING)

    def test_resubmission_counts_instead_of_piling_up(self):
        """687 cycles must produce ONE row that says 687, not 687 rows."""
        for _ in range(5):
            self._submit()
        rows = ProvisioningRequest.objects.filter(school=self.school)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().times_seen, 5)

    def test_a_declined_request_is_not_reopened_by_the_next_cycle(self):
        self._submit()
        row = ProvisioningRequest.objects.get(school=self.school)
        decline_provisioning_request(row, actor=self.admin, reason="Left in July.")
        self._submit()
        row.refresh_from_db()
        self.assertEqual(row.status, ProvisioningRequest.Status.DECLINED)
        self.assertEqual(row.times_seen, 2, "still counted, just not reopened")

    def test_a_queue_write_failure_never_breaks_the_cycle(self):
        """The refusal is the contract; the queue is an improvement on it."""
        out = record_refused_insert(
            school_id=None,
            entity_type="teacher",
            client_offline_id="x",
            values={},
        )
        self.assertIsNone(out)


class ApprovalMintsTheAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_support_staff_catalog()
        cls.school = School.objects.create(
            name="Approval School",
            slug="approval-school",
            subdomain="approval-school",
            is_active=True,
            country_code="CM",
        )
        cls.actor = User.objects.create_user(
            username="approver", password="x", role=User.Role.ADMIN
        )

    def _pending(self, entity_type="teacher", role="DRIVER", coid="box-anchor-9"):
        return ProvisioningRequest.objects.create(
            school=self.school,
            entity_type=entity_type,
            client_offline_id=coid,
            payload={
                "first_name": "Babila",
                "last_name": "Leonard",
                "staff_id": "EMP-48",
                "phone": "677222333",
            },
            requested_role=role,
        )

    def test_approval_creates_the_profile_carrying_the_boxs_anchor(self):
        row = self._pending()
        profile = approve_provisioning_request(row, actor=self.actor)
        self.assertEqual(profile.client_offline_id, "box-anchor-9")
        self.assertEqual(profile.school, self.school)
        self.assertEqual(profile.staff_id, "EMP-48")

    def test_the_account_exists_and_cannot_be_signed_into(self):
        row = self._pending()
        profile = approve_provisioning_request(row, actor=self.actor)
        self.assertFalse(
            profile.user.has_usable_password(),
            "approving a person is not the same act as handing them a credential",
        )
        self.assertFalse(profile.user.is_superuser)
        self.assertFalse(profile.user.is_staff)

    def test_the_requested_role_is_applied(self):
        row = self._pending(role="DRIVER")
        profile = approve_provisioning_request(row, actor=self.actor)
        self.assertEqual(profile.user.role, User.Role.DRIVER)

    def test_the_decision_is_recorded_on_the_request(self):
        row = self._pending()
        profile = approve_provisioning_request(row, actor=self.actor)
        row.refresh_from_db()
        self.assertEqual(row.status, ProvisioningRequest.Status.APPROVED)
        self.assertEqual(row.decided_by, self.actor)
        self.assertEqual(row.created_user, profile.user)
        self.assertIsNotNone(row.decided_at)

    def test_a_forbidden_role_is_refused(self):
        for role in ("SUPERADMIN", "PARENT", "STUDENT", "EMPLOYER"):
            with self.subTest(role=role):
                row = self._pending(role=role, coid="box-%s" % role)
                with self.assertRaises(ValueError):
                    approve_provisioning_request(row, actor=self.actor)
                self.assertFalse(
                    User.objects.filter(role=role, username__startswith="babila").exists()
                )

    def test_an_unknown_role_falls_back_to_the_inert_one(self):
        row = self._pending(role="WIZARD")
        profile = approve_provisioning_request(row, actor=self.actor)
        self.assertEqual(profile.user.role, User.Role.SUPPORT_STAFF)

    def test_a_guardian_request_is_recorded_but_not_approvable(self):
        row = self._pending(entity_type="student_guardian", coid="box-guardian-1")
        with self.assertRaises(ValueError) as ctx:
            approve_provisioning_request(row, actor=self.actor)
        self.assertIn("student", str(ctx.exception).lower())
        row.refresh_from_db()
        self.assertEqual(row.status, ProvisioningRequest.Status.PENDING)

    def test_a_decided_request_cannot_be_decided_twice(self):
        row = self._pending()
        approve_provisioning_request(row, actor=self.actor)
        with self.assertRaises(ValueError):
            approve_provisioning_request(row, actor=self.actor)

    def test_two_people_with_the_same_name_get_different_usernames(self):
        a = approve_provisioning_request(self._pending(coid="anchor-a"), actor=self.actor)
        b = approve_provisioning_request(self._pending(coid="anchor-b"), actor=self.actor)
        self.assertNotEqual(a.user.username, b.user.username)

    def test_a_non_latin_name_still_gets_a_username(self):
        row = ProvisioningRequest.objects.create(
            school=self.school,
            entity_type="teacher",
            client_offline_id="anchor-nonlatin",
            payload={"first_name": "林", "last_name": "张"},
        )
        profile = approve_provisioning_request(row, actor=self.actor)
        self.assertTrue(profile.user.username)
