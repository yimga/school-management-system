"""A conflict now records WHICH fields it is about and WHICH side asserted it.

Item 4 turned out to be half-built, which is worth saying plainly rather than quietly
rebuilding: `conflict_actions.field_comparison` already aligns the two stored versions per
field for the review screen, `_client_updates_for` already strips down-only columns, and
`may_resolve` already gates authority. What none of that does is PERSIST the answer. The
diff is re-derived at render time from two JSON blobs, so it can paint one row and cannot
answer a question about the backlog -- learning that the Gilead box's 405 pending conflicts
were 361 about student_code, 32 about first_name, 32 about last_name and 16 about
subject.code meant loading and diffing all 405 in application code.

And nothing recorded provenance at all. `reported_by` is a User, which on a sync write is
the paired service account; the row could not say whether the box asserted the value or the
cloud did. "Make the cloud match the box" is not a query anybody could write against it.

The third piece is a correctness fix rather than an ergonomic one, and it is the reason
this is worth a migration: keeping the client version wrote EVERY field of the incoming
change set, and a conflict is typically one field of twenty.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.api.sync_services import apply_changes
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import SyncConflict


class RecordedConflictTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Fp {uid}", slug=f"fp-{uid}", subdomain=f"fp{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"fp_admin_{uid}", password="Test1234", email=f"f{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Nkemelu",
            date_of_birth="2012-01-01",
        )

    def _stale_push(self, changes, *, sync_origin="edge-push"):
        """One change set, stamped an hour old so LWW grades it a conflict."""
        return apply_changes(
            str(self.school.id), self.user,
            [{
                "entity_type": "student",
                "id": self.student.pk,
                "changes": changes,
                "updated_at": (timezone.now() - timedelta(hours=1)).isoformat(),
            }],
            persist_conflicts=True, sync_origin=sync_origin,
        )

    def _one_conflict(self, changes, **kw):
        out = self._stale_push(changes, **kw)
        self.assertEqual(len(out["conflicts"]), 1, out)
        return SyncConflict.objects.get(school=self.school, entity_type="student")

    # -- what the row now knows ----------------------------------------------------- #
    def test_a_conflict_names_the_field_it_is_actually_about(self):
        """last_name is sent UNCHANGED alongside a changed first_name.

        This is the ordinary shape of a real push -- a bundle carries the whole row, not a
        diff -- so the stored list must be the one field in dispute, not the two fields
        that happened to be in the payload.
        """
        conflict = self._one_conflict(
            {"first_name": "Adaeze", "last_name": "Nkemelu"}
        )
        self.assertEqual(conflict.conflict_fields, ["first_name"])
        # and the whole payload is still there, because resolution may need it
        self.assertEqual(conflict.client_data.get("last_name"), "Nkemelu")

    def test_a_conflict_names_the_side_that_asserted_it(self):
        conflict = self._one_conflict({"first_name": "Adaeze"})
        self.assertEqual(conflict.origin, "edge-push")

    def test_an_online_write_is_recorded_as_neither_node(self):
        """A browser edit has no node of origin, and must not borrow one."""
        conflict = self._one_conflict({"first_name": "Adaeze"}, sync_origin=None)
        self.assertEqual(conflict.origin, "")

    def test_the_wire_carries_the_diff_to_a_caller_that_cannot_query_for_it(self):
        """Added because a mutation proved this was untested.

        Blanking the two fields in the RESPONSE changed nothing any test could see -- every
        assertion here read the database row. That is precisely the reader who cannot: the
        node receiving this payload is on the other side of the link, and the conflict row
        lives in a database it will never query. If the response does not carry the shape
        of the disagreement, that node does not learn it.
        """
        out = self._stale_push({"first_name": "Adaeze", "last_name": "Nkemelu"})
        row = out["conflicts"][0]
        self.assertEqual(row["conflict_fields"], ["first_name"])
        self.assertEqual(row["origin"], "edge-push")

    def test_the_field_list_is_never_empty_on_a_new_conflict(self):
        """THE INVARIANT, and it is a bug detector rather than tidiness.

        Control only reaches conflict creation when at least one field differed -- the
        unchanged-check above it returns early otherwise, using the SAME comparator. So an
        empty list on a freshly written row means the engine filed a conflict about a row
        where nothing changed, which is exactly the fault that produced 68,273 conflicts
        on a freshly cloned box, each asking an operator to choose between a value and
        that same value. Empty here would make it visible the day it returns.
        """
        conflict = self._one_conflict(
            {"first_name": "Adaeze", "last_name": "Nkemelu"}
        )
        self.assertTrue(conflict.conflict_fields)

    def test_the_backlog_can_be_grouped_without_loading_the_payloads(self):
        """THE POINT OF STORING IT. The question 'what is this backlog about' is now a
        query, not a full read plus a diff in Python.

        `.values_list` here is deliberate: it proves the answer comes from the column and
        never touches client_data/server_data, which on a real backlog are the expensive
        part. Filtering uses the first element rather than a containment lookup because
        SQLite has none -- and single-field conflicts are what a real backlog is made of.
        """
        self._one_conflict({"first_name": "Adaeze"})
        other = StudentProfile.objects.create(
            school=self.school, first_name="Bo", last_name="Tabi",
            date_of_birth="2011-05-05",
        )
        apply_changes(
            str(self.school.id), self.user,
            [{
                "entity_type": "student", "id": other.pk,
                "changes": {"last_name": "Tabe"},
                "updated_at": (timezone.now() - timedelta(hours=1)).isoformat(),
            }],
            persist_conflicts=True, sync_origin="edge-push",
        )
        listed = sorted(
            SyncConflict.objects.filter(school=self.school)
            .values_list("conflict_fields", flat=True)
        )
        self.assertEqual(listed, [["first_name"], ["last_name"]])
        self.assertEqual(
            SyncConflict.objects.filter(
                school=self.school, conflict_fields__0="last_name"
            ).count(),
            1,
        )

    # -- what the row now DOES ------------------------------------------------------ #
    def test_keeping_the_client_writes_only_the_field_in_dispute(self):
        """THE CORRECTNESS FIX.

        A conflict is detected on first_name; last_name was identical at that moment and
        rode along in the payload. The server then legitimately changes last_name -- an
        office corrects a spelling while the conflict sits in the queue, which on a real
        backlog is days. Resolving in the client's favour must settle the DISPUTE, not
        replay a day-old copy of the whole row over the top of it.
        """
        from apps.sync_engine.conflict_actions import apply_resolution

        conflict = self._one_conflict(
            {"first_name": "Adaeze", "last_name": "Nkemelu"}
        )
        StudentProfile.objects.filter(pk=self.student.pk).update(last_name="Nkemelu-Obi")

        ok, _detail = apply_resolution(conflict, "client", self.user)
        self.assertTrue(ok)

        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Adaeze")  # the dispute is settled
        self.assertEqual(self.student.last_name, "Nkemelu-Obi")  # and nothing else moved

    def test_a_conflict_from_before_the_column_existed_still_applies_everything(self):
        """An empty list means UNKNOWN, not 'nothing differed'.

        Rows recorded before this migration have no diff to narrow to. Reading empty as an
        empty diff would resolve every one of them by writing nothing at all while still
        stamping it RESOLVED_CLIENT -- silent, and worse than the behaviour it replaced.
        """
        from apps.sync_engine.conflict_actions import apply_resolution

        conflict = self._one_conflict(
            {"first_name": "Adaeze", "last_name": "Nkemelu"}
        )
        SyncConflict.objects.filter(pk=conflict.pk).update(conflict_fields=[])
        conflict.refresh_from_db()
        StudentProfile.objects.filter(pk=self.student.pk).update(last_name="Nkemelu-Obi")

        ok, _detail = apply_resolution(conflict, "client", self.user)
        self.assertTrue(ok)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Adaeze")
        self.assertEqual(self.student.last_name, "Nkemelu")  # the old, wider behaviour

    def test_the_review_screen_believes_what_the_engine_recorded(self):
        """Two notions of 'differs' in one system is how a reviewer is shown a difference
        the engine does not believe in.

        `field_comparison` fell back to comparing str() of both sides, which cannot tell a
        datetime serialised two ways from a real change -- the same blind spot that had 8
        of 17 rail entities conflicting with themselves. When the row carries the engine's
        own answer, the screen uses it.
        """
        from apps.sync_engine.conflict_actions import field_comparison

        conflict = self._one_conflict({"first_name": "Adaeze"})
        # a field the text comparison alone would call different
        conflict.client_data = dict(conflict.client_data, admission_number="0042")
        conflict.server_data = dict(conflict.server_data, admission_number=42)
        conflict.save(update_fields=["client_data", "server_data"])

        rows = {r["name"]: r["differs"] for r in field_comparison(conflict)}
        self.assertTrue(rows["first_name"])
        self.assertFalse(rows["admission_number"])


class AdminResolutionUsesTheSameGateTests(TestCase):
    """The Django admin had a SECOND copy of the resolution logic, and it had drifted.

    `views_sync_center` moved to `conflict_actions`, which grew `may_resolve` (a
    cloud-authoritative conflict may only be settled in the client's favour by someone who
    could have made that write directly) and the down-only field strip. The admin copy got
    neither, while its own comment still claimed it mirrored the view -- so the admin
    action was a way around the authority model, reachable by any staff user holding
    change permission on SyncConflict alone.
    """

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Ag {uid}", slug=f"ag-{uid}", subdomain=f"ag{uid}", is_active=True
        )
        self.staff = User.objects.create_user(
            username=f"ag_staff_{uid}", password="Test1234", email=f"a{uid}@test.com",
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=self.staff, school=self.school, role="ADMIN", is_primary=True
        )

    def test_a_protected_conflict_is_refused_to_a_user_who_could_not_write_it(self):
        from apps.siteconfig.admin import _resolve_sync_conflict

        conflict = SyncConflict.objects.create(
            school=self.school,
            entity_type="fee_payment",  # money: cloud-authoritative
            entity_id=1,
            client_data={"amount": "999999.00"},
            server_data={"amount": "100.00"},
            conflict_fields=["amount"],
            origin="edge-push",
            status=SyncConflict.Status.PENDING,
        )
        ok, reason = _resolve_sync_conflict(
            conflict, SyncConflict.Status.RESOLVED_CLIENT, self.staff
        )
        self.assertFalse(ok, "the admin settled a money conflict for a user with no "
                             "permission to write money")
        self.assertIn("cloud-authoritative", str(reason))
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.PENDING)

    def test_keeping_the_server_version_stays_open_to_anyone(self):
        """Refusing the harmless direction would leave protected conflicts to rot, which
        is paralysis rather than safety.
        """
        from apps.siteconfig.admin import _resolve_sync_conflict

        conflict = SyncConflict.objects.create(
            school=self.school, entity_type="fee_payment", entity_id=2,
            client_data={"amount": "999999.00"}, server_data={"amount": "100.00"},
            conflict_fields=["amount"], origin="edge-push",
            status=SyncConflict.Status.PENDING,
        )
        ok, _reason = _resolve_sync_conflict(
            conflict, SyncConflict.Status.RESOLVED_SERVER, self.staff
        )
        self.assertTrue(ok)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.RESOLVED_SERVER)
