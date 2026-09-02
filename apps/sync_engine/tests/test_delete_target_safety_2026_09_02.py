"""A deletion must destroy the row that died, and never a share of a table.

MEASURED ON A PRODUCTION APPLIANCE, 2026-09-02. One pull carried 46 tombstones - 39
``teacher`` (pks 28..66), 6 ``specialty_subject`` (pks 1..6), 1 ``sync_schedule``. The 39
teacher deletions were recorded on the cloud inside 220ms at 12:00:01 - one sweep, not a
term's staff turnover - and NONE carried a ``client_offline_id``, so nothing could match
them except an integer minted on the far side. The run reported ``deleted 0 ... skipped 0``
and the sum was 46 short.

WHETHER ROWS WERE LOST HERE IS UNMEASURED. An earlier reading claimed 13 teacher records
had already been destroyed, by subtracting 26 survivors from 39 tombstones; the pk ranges
do not support it, because the box's live teacher pks are 2..27 and the tombstones cover
28..66 - DISJOINT. Not disproven, just unmeasured. The tests below therefore assert the
DEFECT, which is present whatever that measurement turns out to say, and not a body count.

TWO INDEPENDENT DEFECTS, and each one alone is enough to lose a school's staff:

  1. **The wrong row.** ``apply_deletes`` looked the target up by pk FIRST and fell back to
     the offline anchor only when the pk found nothing. That is backwards. The anchor is
     the only identity both sides mint once and agree on; the pk beside it belongs to
     whichever deployment wrote the row. Worse, a pk-only deletion was applied
     unconditionally - and a box mints pks independently of the cloud, so it lands on
     whatever local row happens to sit at that number.
  2. **No sense of proportion.** ``RMC_SYNC_MAX_DELETES_PER_BUNDLE`` counts ROWS and
     defaults to 500, so 39 deletions - every teacher a school has - were routine to it. A
     count cannot tell a big school's churn from a small school's extinction.

WHAT IS PROVEN HERE:

  * a pk-only deletion does not destroy a live local row this side cannot tie to the far
    side, and it is refused by a NAMED reason the skip tally counts, not silently dropped;
  * a pk-only deletion never destroys an ANCHORED local row - that refusal is provable
    from the two rows alone and no setting can switch it off;
  * a deletion that carries an anchor is matched by the anchor and NEVER falls back to the
    sender's pk, so it cannot take an unrelated row down with it;
  * a refused deletion records no tombstone, so refusing cannot itself bury a pk and make
    a live row permanently unupdatable;
  * a bundle that would delete too large a share of one entity is refused for that entity,
    loudly and reversibly - and does NOT fire on a small table, where deleting two of
    three rows is an ordinary Tuesday.

CONTROLS. Everything outside the two load-bearing classes asserts behaviour that existed
BEFORE this change and must still hold: the anchor match, the already-absent 200 and its
burial, the protected-entity refusal and re-assertion, the row-count flood guard, the
soft-delete path, the principal check, and a pk-only deletion applying where this side
HAS the evidence. They pass on BOTH trees; that is what makes them controls, and it was
checked rather than assumed - three tests first written as load-bearing passed on the
unfixed tree, so they were moved to ``TheProportionalGuardDoesNotOverRefuseTests``
instead of being counted as evidence they are not.
"""
from __future__ import annotations

import datetime as dt

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.academics.models import Department
from apps.accounts.models import User
from apps.api.sync_services import apply_deletes
from apps.schools.models import School
from apps.sync_engine import delete_safety
from apps.sync_engine.models import SyncTombstone, record_sync_apply
from apps.sync_engine.tombstones import DELETE_OP


def _delete_row(entity_type, pk, when, *, client_offline_id=""):
    """A deletion exactly as the delta builder emits it onto the wire."""
    return {
        "entity_type": entity_type,
        "id": str(pk) if pk is not None else None,
        "client_offline_id": client_offline_id,
        "op": DELETE_OP,
        "changes": {},
        "updated_at": when.isoformat(),
    }


class _Fixture(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Delete Target School",
            slug="delete-target-school",
            subdomain="delete-target-school",
        )
        self.admin = User.objects.create_user(
            username="delete-target-admin",
            password="x" * 12,
            role=User.Role.ADMIN,
            is_staff=True,
        )

    # -- fixture helpers ---------------------------------------------------- #
    def _dept(self, name, code, *, anchor=""):
        return Department.objects.create(
            school=self.school, name=name, code=code, client_offline_id=anchor
        )

    def _cloud_authored(self, entity_type, obj):
        """Leave behind exactly what a cloud-authored row leaves behind on a box.

        ``_create_from_cloud_pull`` creates the row AT THE OPERATOR'S PK and calls
        ``record_sync_apply``; ``apply_changes`` does the same for every row of the far
        side's this box has taken an update from. That ledger entry IS the evidence that
        the two sides address this row by the same number, so a test that wants a
        cloud-authored row has to produce it rather than assume it.
        """
        record_sync_apply(
            str(self.school.id),
            entity_type,
            obj.pk,
            getattr(obj, "updated_at", None),
            "cloud-pull",
        )
        return obj

    def _pull(self, rows):
        return apply_deletes(
            str(self.school.id), self.admin, rows, sync_origin="cloud-pull"
        )

    def _push(self, rows):
        return apply_deletes(
            str(self.school.id), self.admin, rows, sync_origin="edge-push"
        )


# --------------------------------------------------------------------------- #
# LOAD-BEARING: identity. Which row does this deletion actually name?
# --------------------------------------------------------------------------- #
class APkOnlyDeletionMustProveItNamesThisRowTests(_Fixture):
    def test_a_locally_minted_row_is_not_destroyed_by_a_foreign_pk(self):
        """The production defect, in one row.

        This department was created HERE. The far side has never addressed it, so nothing
        on this side ties the number to any row of theirs - and a box's pk sequence has
        never been related to the cloud's. Applying the deletion is a coin flip whose
        losing side is unrecoverable.
        """
        local = self._dept("Locally Minted", "LOC-1")

        out = self._pull([_delete_row("department", local.pk, timezone.now())])

        self.assertEqual(out["deleted"], 0)
        self.assertEqual(out["results"][0]["status"], 409)
        self.assertEqual(
            out["results"][0]["data"]["error"],
            delete_safety.REASON_PK_NOT_SHARED,
            "a refusal must carry a named reason or the skip tally cannot count it",
        )
        self.assertTrue(
            Department.objects.filter(pk=local.pk).exists(),
            "a row this side cannot identify was destroyed by a foreign integer",
        )

    def test_an_anchored_local_row_is_never_destroyed_by_a_pk_only_deletion(self):
        """Provable, not inferred - and the one refusal no setting may switch off.

        An anchored row is matched everywhere by ``(school, client_offline_id)``. If the
        far side had this row at all it would have it WITH the anchor, so its tombstone
        would carry the anchor too. A tombstone with none is about a different row.
        """
        anchored = self._dept("Created Offline", "OFF-1", anchor="anchor-offline-1")

        out = self._pull([_delete_row("department", anchored.pk, timezone.now())])

        self.assertEqual(out["results"][0]["status"], 409)
        self.assertEqual(
            out["results"][0]["data"]["error"], delete_safety.REASON_ANCHOR_MISMATCH
        )
        self.assertTrue(Department.objects.filter(pk=anchored.pk).exists())

    def test_the_anchor_refusal_holds_even_when_peer_pks_are_declared_trusted(self):
        """The declaration says "our pk spaces agree". It cannot say "this anchored row is
        that unanchored one", because the two rows themselves say otherwise."""
        anchored = self._dept("Created Offline", "OFF-2", anchor="anchor-offline-2")

        with override_settings(RMC_SYNC_DELETE_TRUSTS_PEER_PKS=True):
            out = self._pull([_delete_row("department", anchored.pk, timezone.now())])

        self.assertEqual(out["deleted"], 0)
        self.assertEqual(out["results"][0]["status"], 409)
        self.assertEqual(
            (out["results"][0]["data"] or {}).get("error"),
            delete_safety.REASON_ANCHOR_MISMATCH,
        )
        self.assertTrue(Department.objects.filter(pk=anchored.pk).exists())

    def test_an_anchored_deletion_never_falls_back_to_the_senders_pk(self):
        """Anchor-preferring means anchor-ONLY.

        The wire row names an anchor AND carries the sender's pk. Looking the pk up first -
        which is what this did - hands the deletion whichever local row is sitting at the
        sender's number, and here that is a completely different department.
        """
        bystander = self._dept("Bystander", "BYS-1")
        target = self._dept("Really Deleted", "TGT-1", anchor="anchor-target-1")
        self.assertNotEqual(bystander.pk, target.pk)

        out = self._pull(
            [
                _delete_row(
                    "department",
                    bystander.pk,  # the SENDER's pk - meaningless on this side
                    timezone.now(),
                    client_offline_id="anchor-target-1",
                )
            ]
        )

        self.assertEqual(out["results"][0]["status"], 200)
        self.assertTrue(
            Department.objects.filter(pk=bystander.pk).exists(),
            "the deletion took an unrelated row down with it",
        )
        self.assertFalse(Department.objects.filter(pk=target.pk).exists())

    def test_a_refused_deletion_records_no_tombstone(self):
        """Refusing must not itself be destructive.

        A tombstone at a pk this side cannot identify would make delete-dominance refuse
        every future update to whatever really lives there - one unsafe deletion turned
        into a permanently unreachable record.
        """
        local = self._dept("Locally Minted", "LOC-2")

        self._pull([_delete_row("department", local.pk, timezone.now())])

        self.assertFalse(
            SyncTombstone.objects.filter(
                school=self.school, entity_type="department", local_pk=str(local.pk)
            ).exists()
        )


# --------------------------------------------------------------------------- #
# LOAD-BEARING: proportion. How much of a table may one bundle take?
# --------------------------------------------------------------------------- #
class TheProportionalGuardTests(_Fixture):
    def _staff_room(self, n, *, deleted):
        """``n`` cloud-authored departments; the first ``deleted`` are buried by the cloud."""
        rows = [
            self._cloud_authored("department", self._dept(f"Dept {i}", f"D-{i}"))
            for i in range(n)
        ]
        return rows, [
            _delete_row("department", obj.pk, timezone.now()) for obj in rows[:deleted]
        ]

    def test_a_bundle_that_would_take_half_an_entity_is_refused(self):
        """39 deletions were 100% of a school's teaching staff and 8% of a 500-row cap.
        Only a fraction can tell those two numbers apart."""
        live, deletes = self._staff_room(12, deleted=6)

        out = self._pull(deletes)

        self.assertEqual(out["deleted"], 0)
        self.assertEqual(
            {r["status"] for r in out["results"]},
            {409},
            "a proportional wipe must be refused for the entity as a whole",
        )
        self.assertEqual(
            out["results"][0]["data"]["error"], delete_safety.REASON_PROPORTION_GUARD
        )
        self.assertEqual(Department.objects.filter(school=self.school).count(), len(live))

    def test_the_refusal_carries_the_numbers_an_operator_needs(self):
        """"Refused" is not actionable. "6 of 12, over a 0.25 ceiling" is."""
        _live, deletes = self._staff_room(12, deleted=6)

        result = self._pull(deletes)["results"][0]

        self.assertEqual(result["status"], 409)
        data = result["data"] or {}
        self.assertEqual(data.get("error"), delete_safety.REASON_PROPORTION_GUARD)
        self.assertEqual(data.get("entity_type"), "department")
        self.assertEqual(data.get("targets"), 6)
        self.assertEqual(data.get("live"), 12)
        self.assertEqual(data.get("fraction"), 0.5)
        self.assertEqual(data.get("max_fraction"), 0.25)

class TheProportionalGuardDoesNotOverRefuseTests(_Fixture):
    """CONTROLS, and deliberately filed as such.

    Every test here asserts that a deletion HAPPENS, which is what the rail did before
    this change when no proportional guard existed at all - so each one passes on the
    unfixed tree too and none of them is A/B evidence on its own. They were written as
    load-bearing and that was wrong; they are moved here rather than quietly counted.

    They still earn their place, next to
    ``TheProportionalGuardTests.test_a_bundle_that_would_take_half_an_entity_is_refused``
    which does fail on the unfixed tree. A guard that refuses is only worth having if it
    also lets go: paired, the two say the threshold is a threshold and not a ban.
    """

    _staff_room = TheProportionalGuardTests._staff_room

    def test_the_guard_is_reversible_by_raising_the_threshold(self):
        """Nothing is lost by refusing: the far side keeps its tombstones and re-offers
        them, so a threshold an operator has decided is wrong applies on the next cycle."""
        _live, deletes = self._staff_room(12, deleted=6)

        with override_settings(RMC_SYNC_MAX_DELETE_FRACTION_PER_BUNDLE=0.75):
            out = self._pull(deletes)

        self.assertEqual(out["deleted"], 6)
        self.assertEqual(Department.objects.filter(school=self.school).count(), 6)

    def test_a_tenant_may_set_its_own_threshold(self):
        """The tenant layer of the cascade: School.settings outranks the deployment's env
        var, because how much churn is normal is a property of the school."""
        _live, deletes = self._staff_room(12, deleted=6)
        self.school.settings = {delete_safety.SCHOOL_SETTING_MAX_FRACTION: 0.75}
        self.school.save(update_fields=["settings"])

        out = self._pull(deletes)

        self.assertEqual(out["deleted"], 6)

    def test_the_guard_counts_rows_it_would_delete_not_tombstones_received(self):
        """A tombstone is re-offered every cycle until the cursor passes it. Counting
        RECEIVED rows would refuse a box forever over deletions that already happened and
        would remove nothing now."""
        live, _deletes = self._staff_room(12, deleted=0)
        ghosts = [
            _delete_row("department", 900_000 + i, timezone.now()) for i in range(9)
        ]
        real = [_delete_row("department", live[0].pk, timezone.now())]

        out = self._pull(ghosts + real)

        self.assertEqual(
            out["deleted"], 1, "nine deletions of rows that are already gone are not a wipe"
        )
        self.assertEqual(Department.objects.filter(school=self.school).count(), 11)


class TheProportionalGuardArithmeticTests(SimpleTestCase):
    """The pure function, with no database in the way."""

    def test_a_table_at_or_below_the_floor_is_never_guarded(self):
        over = delete_safety.entities_over_delete_fraction(
            {"department": 2}, {"department": 3}, max_fraction=0.25, min_live_rows=10
        )
        self.assertEqual(over, {})

    def test_a_share_at_the_threshold_is_allowed_and_above_it_is_not(self):
        at = delete_safety.entities_over_delete_fraction(
            {"teacher": 5}, {"teacher": 20}, max_fraction=0.25, min_live_rows=10
        )
        above = delete_safety.entities_over_delete_fraction(
            {"teacher": 6}, {"teacher": 20}, max_fraction=0.25, min_live_rows=10
        )
        self.assertEqual(at, {})
        self.assertEqual(set(above), {"teacher"})

    def test_entities_are_judged_independently(self):
        """One entity's quiet cycle must not average away another's wipe."""
        over = delete_safety.entities_over_delete_fraction(
            {"teacher": 12, "student": 1},
            {"teacher": 12, "student": 400},
            max_fraction=0.25,
            min_live_rows=10,
        )
        self.assertEqual(set(over), {"teacher"})

    def test_an_entity_with_no_live_rows_is_not_a_wipe(self):
        over = delete_safety.entities_over_delete_fraction(
            {"teacher": 3}, {"teacher": 0}, max_fraction=0.25, min_live_rows=10
        )
        self.assertEqual(over, {})


class TheThresholdsRouteTheCascadeTests(SimpleTestCase):
    """Nothing here may be hardcoded, so the cascade is asserted by RUNNING it.

    Tenant (``School.settings``) -> deployment (env var, read into a Django setting) ->
    platform constant, highest layer first. The remaining layers of the 7-layer contract
    are deliberately absent rather than faked: how much of a school one bundle may erase
    is not a user preference, not a translated string, and not a DB fixture.

    CONTROLS - they exercise the helper, which is importable on both trees.
    """

    def test_a_tenant_override_outranks_the_deployment_setting(self):
        with override_settings(RMC_SYNC_MAX_DELETE_FRACTION_PER_BUNDLE=0.1):
            self.assertEqual(
                delete_safety.max_delete_fraction(
                    {delete_safety.SCHOOL_SETTING_MAX_FRACTION: 0.9}
                ),
                0.9,
            )
        with override_settings(RMC_SYNC_DELETE_FRACTION_MIN_ROWS=99):
            self.assertEqual(
                delete_safety.min_live_rows_for_fraction_guard(
                    {delete_safety.SCHOOL_SETTING_MIN_ROWS: 4}
                ),
                4,
            )

    def test_the_deployment_setting_is_used_when_the_tenant_says_nothing(self):
        with override_settings(
            RMC_SYNC_MAX_DELETE_FRACTION_PER_BUNDLE=0.4,
            RMC_SYNC_DELETE_FRACTION_MIN_ROWS=7,
        ):
            self.assertEqual(delete_safety.max_delete_fraction({}), 0.4)
            self.assertEqual(delete_safety.min_live_rows_for_fraction_guard({}), 7)

    def test_an_unusable_value_falls_back_to_the_platform_constant(self):
        """A typo in a tenant's JSON must not decide how much of it can be deleted."""
        for bad in ("nonsense", "", 0, -1):
            self.assertEqual(
                delete_safety.max_delete_fraction(
                    {delete_safety.SCHOOL_SETTING_MAX_FRACTION: bad}
                ),
                delete_safety._DEFAULT_MAX_DELETE_FRACTION,
                f"{bad!r} was accepted as a delete fraction",
            )
        self.assertEqual(
            delete_safety.min_live_rows_for_fraction_guard(
                {delete_safety.SCHOOL_SETTING_MIN_ROWS: "nonsense"}
            ),
            delete_safety._DEFAULT_MIN_LIVE_ROWS,
        )

    def test_the_shipped_defaults_are_the_ones_the_platform_declares(self):
        """The deployment layer must AGREE with the platform constant out of the box, or
        the constant is decoration and the real default is whatever settings.py typed."""
        self.assertEqual(
            delete_safety.max_delete_fraction({}),
            delete_safety._DEFAULT_MAX_DELETE_FRACTION,
        )
        self.assertEqual(
            delete_safety.min_live_rows_for_fraction_guard({}),
            delete_safety._DEFAULT_MIN_LIVE_ROWS,
        )

    def test_the_trust_declaration_ships_OFF(self):
        """Fail-closed is only fail-closed if it is the shipped default."""
        self.assertFalse(delete_safety.trusts_peer_pks())


class TheEvidenceIndexTests(_Fixture):
    """``peer_addressed_pks`` is the whole safety argument; it must not over-answer."""

    def test_a_ledger_row_for_another_entity_does_not_answer_for_this_one(self):
        """``entity_type__in`` x ``local_pk__in`` is a CROSS PRODUCT. Without the
        intersection a ledger row for ("student", "7") would vouch for ("teacher", "7")."""
        obj = self._dept("Cloud Authored", "CLD-1")
        record_sync_apply(
            str(self.school.id), "student", obj.pk, timezone.now(), "cloud-pull"
        )

        answered = delete_safety.peer_addressed_pks(
            str(self.school.id), {("department", str(obj.pk))}
        )

        self.assertEqual(answered, set())

    def test_a_ledger_row_for_this_entity_and_pk_does_answer(self):
        obj = self._cloud_authored("department", self._dept("Cloud Authored", "CLD-2"))

        answered = delete_safety.peer_addressed_pks(
            str(self.school.id), {("department", str(obj.pk))}
        )

        self.assertEqual(answered, {("department", str(obj.pk))})


# --------------------------------------------------------------------------- #
# CONTROLS - behaviour that existed BEFORE this change and must still hold.
# Every one of these passes on the unfixed tree too; that is what makes it a control.
# --------------------------------------------------------------------------- #
class ControlsTheDeleteRailStillWorksTests(_Fixture):
    def test_a_cloud_authored_row_is_still_deleted_by_its_pk(self):
        obj = self._cloud_authored("department", self._dept("Cloud Authored", "CTL-1"))

        out = self._pull([_delete_row("department", obj.pk, timezone.now())])

        self.assertEqual(out["deleted"], 1)
        self.assertEqual(out["results"][0]["data"], {"deleted": True})
        self.assertFalse(Department.objects.filter(pk=obj.pk).exists())

    def test_an_anchored_deletion_still_removes_the_anchored_row(self):
        obj = self._dept("Offline Created", "CTL-2", anchor="anchor-ctl-2")

        out = self._pull(
            [
                _delete_row(
                    "department", obj.pk, timezone.now(), client_offline_id="anchor-ctl-2"
                )
            ]
        )

        self.assertEqual(out["deleted"], 1)
        self.assertFalse(Department.objects.filter(pk=obj.pk).exists())

    def test_a_row_that_is_already_absent_is_still_recorded_as_buried(self):
        ghost = 987_654
        out = self._pull([_delete_row("department", ghost, timezone.now())])

        self.assertEqual(
            out["results"][0]["data"], {"deleted": False, "already_absent": True}
        )
        self.assertTrue(
            SyncTombstone.objects.filter(
                school=self.school, entity_type="department", local_pk=str(ghost)
            ).exists()
        )

    def test_a_burial_still_keeps_the_far_sides_original_timestamp(self):
        obj = self._cloud_authored("department", self._dept("Cloud Authored", "CTL-3"))
        when = timezone.now() - dt.timedelta(hours=3)

        self._pull([_delete_row("department", obj.pk, when)])

        tomb = SyncTombstone.objects.get(
            school=self.school, entity_type="department", local_pk=str(obj.pk)
        )
        self.assertEqual(tomb.deleted_at, when)
        self.assertEqual(tomb.origin, "cloud-pull")

    def test_an_unknown_entity_is_still_one_bad_row_not_a_dead_batch(self):
        obj = self._cloud_authored("department", self._dept("Cloud Authored", "CTL-4"))

        out = self._pull(
            [
                _delete_row("nonsense_entity", 1, timezone.now()),
                _delete_row("department", obj.pk, timezone.now()),
            ]
        )

        self.assertEqual(out["results"][0]["status"], 400)
        self.assertEqual(out["results"][1]["status"], 200)
        self.assertFalse(Department.objects.filter(pk=obj.pk).exists())

    def test_the_row_count_flood_guard_still_refuses_the_whole_batch(self):
        obj = self._cloud_authored("department", self._dept("Cloud Authored", "CTL-5"))
        rows = [
            _delete_row("department", obj.pk + 1_000 + i, timezone.now()) for i in range(4)
        ] + [_delete_row("department", obj.pk, timezone.now())]

        with override_settings(RMC_SYNC_MAX_DELETES_PER_BUNDLE=4):
            out = self._pull(rows)

        self.assertEqual(out["deleted"], 0)
        self.assertEqual(
            {r["data"]["error"] for r in out["results"]}, {"delete_flood_guard"}
        )
        self.assertTrue(Department.objects.filter(pk=obj.pk).exists())

    def test_deleting_two_of_three_rows_is_still_an_ordinary_tuesday(self):
        """The floor. A fraction on a three-row table is not evidence of anything."""
        rows = [
            self._cloud_authored("department", self._dept(f"Small {i}", f"SML-{i}"))
            for i in range(3)
        ]

        out = self._pull(
            [_delete_row("department", obj.pk, timezone.now()) for obj in rows[:2]]
        )

        self.assertEqual(out["deleted"], 2)
        self.assertEqual(Department.objects.filter(school=self.school).count(), 1)

    def test_two_deletions_naming_one_row_still_report_one_removal(self):
        """`deleted` is the one number an operator reads as \"records were destroyed\",
        so it must count rows that stopped existing, never deletion rows received."""
        obj = self._cloud_authored("department", self._dept("Cloud Authored", "CTL-9"))
        row = _delete_row("department", obj.pk, timezone.now())

        out = self._pull([row, dict(row)])

        self.assertEqual(out["deleted"], 1)
        self.assertEqual(
            out["results"][1]["data"], {"deleted": False, "already_absent": True}
        )
        self.assertFalse(Department.objects.filter(pk=obj.pk).exists())

    def test_the_kill_switch_still_refuses_everything(self):
        obj = self._cloud_authored("department", self._dept("Cloud Authored", "CTL-6"))

        with override_settings(RMC_SYNC_DELETE_PROPAGATION_ENABLED=False):
            out = self._pull([_delete_row("department", obj.pk, timezone.now())])

        self.assertEqual(
            out["results"][0]["data"]["error"], "delete_propagation_disabled"
        )
        self.assertTrue(Department.objects.filter(pk=obj.pk).exists())

    def test_a_non_admin_principal_still_may_not_delete_anything(self):
        obj = self._cloud_authored("department", self._dept("Cloud Authored", "CTL-7"))
        weak = User.objects.create_user(
            username="weak-delete-target", password="x" * 12, role=User.Role.STUDENT
        )

        out = apply_deletes(
            str(self.school.id),
            weak,
            [_delete_row("department", obj.pk, timezone.now())],
            sync_origin="cloud-pull",
        )

        self.assertEqual(out["results"][0]["status"], 403)
        self.assertTrue(Department.objects.filter(pk=obj.pk).exists())

    def test_a_schema_refusal_is_still_one_row_not_a_raised_batch(self):
        """``Specialty.department`` is PROTECT, so this deletion cannot be performed here."""
        from apps.academics.models import Specialty

        obj = self._cloud_authored("department", self._dept("Cloud Authored", "CTL-8"))
        Specialty.objects.create(
            school=self.school, department=obj, name="Held", code="HLD-DT"
        )

        out = self._pull([_delete_row("department", obj.pk, timezone.now())])

        self.assertEqual(out["results"][0]["status"], 422)
        self.assertEqual(out["results"][0]["data"]["error"], "delete_failed")
        self.assertTrue(Department.objects.filter(pk=obj.pk).exists())


class ControlsPolicyStillOutranksIdentityTests(_Fixture):
    """Policy is decided BEFORE identity, and must keep answering first."""

    def _an_invoice(self):
        from decimal import Decimal

        from apps.finance.models import ComplianceProfile, Invoice
        from apps.people.models import StudentProfile

        profile = ComplianceProfile.objects.create(name="CP dtgt", country_code="CM")
        student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="L", student_code="S-DTGT-1"
        )
        self.Invoice = Invoice
        return Invoice.objects.create(
            school=self.school,
            profile=profile,
            student=student,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
        )

    def test_a_box_still_may_not_delete_a_money_record_on_the_cloud(self):
        inv = self._an_invoice()

        out = self._push([_delete_row("invoice", inv.pk, timezone.now())])

        self.assertEqual(out["deleted"], 0)
        self.assertEqual(
            out["results"][0]["data"]["error"], "delete_refused_protected"
        )
        self.assertTrue(self.Invoice.objects.filter(pk=inv.pk).exists())

    def test_a_refused_upward_delete_still_re_asserts_the_row(self):
        inv = self._an_invoice()
        before = self.Invoice.objects.get(pk=inv.pk).updated_at

        out = self._push([_delete_row("invoice", inv.pk, timezone.now())])

        self.assertTrue(out["results"][0]["data"]["reasserted"])
        self.assertGreater(self.Invoice.objects.get(pk=inv.pk).updated_at, before)

    def test_the_cloud_deleting_a_money_record_still_honours_the_soft_delete(self):
        inv = self._an_invoice()
        self._cloud_authored("invoice", inv)

        out = self._pull([_delete_row("invoice", inv.pk, timezone.now())])

        self.assertEqual(
            out["results"][0]["data"], {"deleted": False, "soft_deleted": True}
        )
        inv.refresh_from_db()
        self.assertEqual(inv.status, self.Invoice.Status.VOID)
        self.assertFalse(
            SyncTombstone.objects.filter(
                entity_type="invoice", local_pk=str(inv.pk)
            ).exists(),
            "a soft-deleted row still exists, so burying it would refuse its future updates",
        )
