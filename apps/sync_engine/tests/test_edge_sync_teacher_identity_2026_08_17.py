"""Wave 5 — people.TeacherProfile rides, with MIXED per-field direction.

TeacherProfile was the deferred entity: CLASS-A master data that also carries pay,
authorization switches and a required link to the SHARED ``accounts.User``. Three
guarantees are locked here.

1. **The roster converges two-way.** A phone number or position corrected offline merges
   by last-writer-wins like any other master data. That is the whole point of registering
   it; making the entity protected would turn every offline correction into a manual
   conflict for no safety gain.

2. **Pay, authorization and governance ride DOWN ONLY.** Compensation is cloud-authoritative
   for the same reason money is. The ``allow_*`` flags are not preferences — ``allow_finance_panel``
   gates the teacher payroll block (payslips, net pay) and ``allow_leave_approvals`` confers
   approval authority — so a box that could push them upward could grant payroll visibility
   or approval rights on the cloud. ``is_active`` and ``merged_into`` are offboarding and
   duplicate-merge, i.e. governance. The box still RECEIVES all of them so it works
   correctly offline.

3. **Identity is never invented.** ``user`` is a non-nullable OneToOneField to the shared
   ``accounts.User``, whose pk differs box↔cloud, so ``user_id`` is not a synced field at
   all. An UPDATE is therefore safe (each side keeps its own link). An offline-CREATED
   teacher is REFUSED with its reason rather than attempted, because landing one would
   require the rail to mint a login — an authentication decision, not a data merge.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.api.sync_services import (
    _DOWN_ONLY_FIELDS_PER_ENTITY,
    _INSERT_HELD_ENTITIES,
    _derive_sync_fields,
    _get_entity_config,
    _sync_conflict_policy,
    apply_changes,
    apply_edge_inserts,
)
from apps.people.models import TeacherProfile
from apps.schools.models import School


class TeacherRegistrationShapeTests(TestCase):
    def test_teacher_is_registered_for_edge_sync_only(self):
        edge = _get_entity_config(include_derived=True)
        online = _get_entity_config(include_derived=False)
        self.assertIn("teacher", edge)
        self.assertIs(edge["teacher"][0], TeacherProfile)
        self.assertNotIn(
            "teacher",
            online,
            "an ordinary online DeltaSyncAPI request must still see only the three "
            "original entities",
        )

    def test_the_identity_fk_is_not_a_synced_field(self):
        """The core portability rule: accounts.User is SHARED, so its pk is not portable."""
        fields = _derive_sync_fields(TeacherProfile)
        self.assertNotIn("user_id", fields)
        self.assertNotIn("user", fields)

    def test_the_profile_photo_filefield_is_not_synced(self):
        """A bundle carries no bytes, so a synced path would dangle."""
        self.assertNotIn("profile_photo", _derive_sync_fields(TeacherProfile))

    def test_every_down_only_field_is_actually_a_synced_field(self):
        """Direction rule, not exclusion — a typo here would silently do nothing."""
        allowed = _get_entity_config(include_derived=True)["teacher"][1]
        stray = _DOWN_ONLY_FIELDS_PER_ENTITY["teacher"] - allowed
        self.assertEqual(stray, set(), f"down-only fields absent from the synced set: {stray}")

    def test_a_box_can_never_move_compensation_authorization_or_governance(self):
        """The guarantee, not one implementation of it.

        Down-only is how MOST of these are protected: the box receives the cloud's value
        and an upward write is refused. Being off the rail ENTIRELY is a stronger
        guarantee of the same thing -- a column that does not travel cannot be written
        upward by anyone -- so the assertion is the property, and each field is required
        to satisfy it one way or the other.
        """
        down = _DOWN_ONLY_FIELDS_PER_ENTITY["teacher"]
        allowed = _get_entity_config(include_derived=True)["teacher"][1]
        for field in (
            "salary_amount",
            "salary_cap",
            "pay_grade",
            "pay_scale_id",
            "next_pay_date",
            "paystub_notes",
            "payment_method",
            "allow_finance_panel",
            "allow_paystub_access",
            "allow_leave_approvals",
            "is_active",
            "merged_into_id",
        ):
            with self.subTest(field=field):
                self.assertTrue(
                    field in down or field not in allowed,
                    f"{field} rides two-way: a stale box could overwrite the cloud",
                )

    def test_the_pay_scale_link_is_off_the_rail_rather_than_down_only(self):
        """Which of the two protections applies to pay_scale_id, and why.

        payroll.PayScale has no ``school`` column, so the per-school provisioning clone
        never carries it and a scale minted on the cloud can never be resolved on a box.
        The reference was therefore unportable, not merely sensitive: an absent parent
        cost the WHOLE teacher row, and the runner read that refusal as a reason to
        re-download the entire corpus, which no replay could ever satisfy.

        The column is nullable, so dropping it is free -- the teacher lands, without a
        link the box could not have rendered anyway. Listing it as down-only as well
        would claim a direction for data that does not travel at all.
        """
        from apps.api.sync_services import _is_tenant_scoped_model
        from apps.payroll.models import PayScale

        allowed = _get_entity_config(include_derived=True)["teacher"][1]
        self.assertNotIn("pay_scale_id", allowed)
        self.assertNotIn("pay_scale_id", _DOWN_ONLY_FIELDS_PER_ENTITY["teacher"])
        self.assertFalse(_is_tenant_scoped_model(PayScale))
        self.assertTrue(TeacherProfile._meta.get_field("pay_scale").null)

    def test_benign_roster_fields_are_left_two_way(self):
        down = _DOWN_ONLY_FIELDS_PER_ENTITY["teacher"]
        for field in ("phone", "staff_id", "position_title", "department_id"):
            with self.subTest(field=field):
                self.assertNotIn(field, down)

    def test_entity_policy_is_declared_lww_not_left_to_the_fallback(self):
        self.assertEqual(_sync_conflict_policy("teacher"), ("causal_lww", False))


class _TeacherFixture(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Wave5 School", slug="wave5-school", subdomain="wave5-school"
        )
        self.admin = User.objects.create_user(
            username="wave5-admin", password="x" * 10, role=User.Role.ADMIN, is_staff=True
        )
        self.teacher_user = User.objects.create_user(
            username="wave5-teacher", password="x" * 10, role=User.Role.TEACHER
        )
        self.profile = TeacherProfile.objects.create(
            school=self.school,
            user=self.teacher_user,
            staff_id="T-100",
            phone="+237600000000",
            position_title="Teacher",
            salary_amount=Decimal("250000.00"),
            pay_grade="G3",
            next_pay_date=dt.date(2026, 9, 28),
            allow_finance_panel=False,
            allow_leave_approvals=False,
            is_active=True,
        )

    def _push(self, changes):
        """One box->cloud UPDATE for this profile."""
        return apply_changes(
            str(self.school.id),
            self.admin,
            [
                {
                    "entity_type": "teacher",
                    "id": self.profile.pk,
                    "changes": changes,
                    "updated_at": (timezone.now() + dt.timedelta(minutes=5)).isoformat(),
                }
            ],
            persist_conflicts=True,
            sync_origin="edge-push",
        )

    def _pull(self, changes):
        """One cloud->box apply for this profile."""
        return apply_changes(
            str(self.school.id),
            self.admin,
            [
                {
                    "entity_type": "teacher",
                    "id": self.profile.pk,
                    "changes": changes,
                    "updated_at": (timezone.now() + dt.timedelta(minutes=5)).isoformat(),
                }
            ],
            persist_conflicts=True,
            sync_origin="cloud-pull",
        )


class RosterConvergesTwoWayTests(_TeacherFixture):
    def test_an_offline_phone_correction_is_accepted_upward(self):
        self._push({"phone": "+237699999999"})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.phone, "+237699999999")

    def test_position_and_staff_id_are_accepted_upward(self):
        self._push({"position_title": "Head of Science", "staff_id": "T-101"})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.position_title, "Head of Science")
        self.assertEqual(self.profile.staff_id, "T-101")


class CompensationIsDownOnlyTests(_TeacherFixture):
    def test_a_box_cannot_raise_a_salary(self):
        self._push({"salary_amount": "999999.00"})
        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.salary_amount,
            Decimal("250000.00"),
            "a box push moved pay — payroll is cloud-authoritative",
        )

    def test_the_cloud_can_set_a_salary(self):
        self._pull({"salary_amount": "300000.00"})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.salary_amount, Decimal("300000.00"))

    def test_a_box_cannot_redirect_where_pay_is_sent(self):
        before = self.profile.payment_method
        self._push({"payment_method": "CASH"})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.payment_method, before)

    def test_a_refused_pay_field_does_not_cost_the_rest_of_the_row(self):
        self._push({"salary_amount": "999999.00", "phone": "+237611111111"})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.salary_amount, Decimal("250000.00"))
        self.assertEqual(self.profile.phone, "+237611111111")

    def test_a_pay_only_push_is_reported_as_a_refusal(self):
        out = self._push({"salary_amount": "999999.00", "pay_grade": "G9"})
        statuses = [r["status"] for r in out["results"]]
        self.assertIn(409, statuses)
        payload = str(out["results"][0]["data"])
        self.assertIn("down_only_fields_rejected", payload)
        self.assertIn("salary_amount", payload)


class AuthorizationFlagsAreDownOnlyTests(_TeacherFixture):
    def test_a_box_cannot_grant_itself_the_payroll_panel(self):
        self._push({"allow_finance_panel": True})
        self.profile.refresh_from_db()
        self.assertFalse(
            self.profile.allow_finance_panel,
            "a box push granted payroll visibility on the cloud — this flag gates "
            "PayrollEmployee / payslips / net pay",
        )

    def test_a_box_cannot_grant_itself_leave_approval_authority(self):
        self._push({"allow_leave_approvals": True})
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.allow_leave_approvals)

    def test_the_cloud_can_grant_both(self):
        self._pull({"allow_finance_panel": True, "allow_leave_approvals": True})
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.allow_finance_panel)
        self.assertTrue(self.profile.allow_leave_approvals)


class GovernanceFieldsAreDownOnlyTests(_TeacherFixture):
    def test_a_stale_box_cannot_reinstate_a_deactivated_teacher(self):
        TeacherProfile.objects.filter(pk=self.profile.pk).update(is_active=False)
        self._push({"is_active": True})
        self.profile.refresh_from_db()
        self.assertFalse(
            self.profile.is_active, "a box push reversed an offboarding done on the cloud"
        )

    def test_the_cloud_can_deactivate(self):
        self._pull({"is_active": False})
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_active)


class IdentityIsNeverInventedTests(_TeacherFixture):
    def test_an_offline_created_teacher_is_refused_with_its_reason(self):
        out = apply_edge_inserts(
            str(self.school.id),
            self.admin,
            [
                {
                    "entity_type": "teacher",
                    "id": 555,
                    "client_offline_id": "offline-teacher-1",
                    "changes": {"staff_id": "T-OFFLINE", "phone": "+237655555555"},
                    "updated_at": None,
                }
            ],
            sync_origin="edge-push",
        )
        self.assertEqual(out["created"], 0)
        result = out["results"][0]
        self.assertEqual(result["status"], 409)
        self.assertEqual(result["data"]["error"], "insert_held_for_entity")
        self.assertIn("authentication", result["data"]["reason"])
        self.assertFalse(
            TeacherProfile.objects.filter(
                school=self.school, client_offline_id="offline-teacher-1"
            ).exists()
        )

    def test_the_hold_is_declared_for_teacher(self):
        self.assertIn("teacher", _INSERT_HELD_ENTITIES)
        self.assertTrue(_INSERT_HELD_ENTITIES["teacher"].strip())

    def test_an_update_never_touches_the_user_link(self):
        original_user_id = self.profile.user_id
        self._push({"phone": "+237600000001", "staff_id": "T-XYZ"})
        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.user_id,
            original_user_id,
            "the identity link moved during a data merge",
        )

    def test_a_pushed_user_id_is_ignored_even_if_a_box_sends_one(self):
        """Defence in depth: the field is not in the allowed set, so it cannot be applied."""
        other = User.objects.create_user(
            username="wave5-other", password="x" * 10, role=User.Role.TEACHER
        )
        original_user_id = self.profile.user_id
        self._push({"user_id": other.pk, "phone": "+237600000002"})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.user_id, original_user_id)
        self.assertEqual(self.profile.phone, "+237600000002")
