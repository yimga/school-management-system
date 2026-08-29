"""What happens when one node ships a rail field the other node has never heard of.

WRITTEN BECAUSE THE CLAIM WAS MADE FROM READING. Deployment advice was given -- "the box
can go first, the cloud will drop the field silently" -- on the strength of two lines read
in `sync_services` (`{k: v for k, v in changes.items() if k in allowed}`) and never once
executed. A rail contract between two independently-deployed nodes is exactly the thing
that must be run rather than inferred: it is invisible in a single-version test suite,
because a suite only ever has one version of `allowed`.

An older receiver is simulated by NARROWING its own entity config, which is precisely what
being behind a deploy means -- the field exists on the sender and is absent from the
receiver's allow-list.

Two questions, and they have different answers:

  * does the unknown field break the write?  No -- it is dropped, the rest applies.
  * do the two nodes still agree they are in sync?  No -- the parity digest folds the
    rail field set, so the wider node hashes one more field per row and the entity
    mismatches even when every row is identical.

The second is the one worth having in a file. A mismatching digest during a staged
rollout looks exactly like data divergence, and an operator who does not know it is
expected will go looking for a corruption that is not there.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership


def _narrowed_without(config, entity_type, field):
    """The same registry, minus one field -- i.e. a node that predates that field."""
    model, allowed = config[entity_type]
    out = dict(config)
    out[entity_type] = (model, type(allowed)(f for f in allowed if f != field))
    return out


class VersionSkewOnTheRailTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Vs {uid}", slug=f"vs-{uid}", subdomain=f"vs{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"vs_admin_{uid}", password="Test1234", email=f"v{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Nkemelu",
            date_of_birth="2012-01-01", admission_number="26AAAB0001",
        )

    def test_the_older_receiver_drops_the_unknown_field_and_still_applies_the_rest(self):
        """THE CLAIM THE DEPLOYMENT ORDER RESTS ON. No 4xx, no lost row, no propagation."""
        from apps.api import sync_services

        real = sync_services._get_entity_config(include_derived=True)
        older = _narrowed_without(real, "student", "admission_number")
        self.assertNotIn("admission_number", older["student"][1], "the fixture is not older")

        with patch.object(sync_services, "_get_entity_config", return_value=older):
            out = sync_services.apply_changes(
                str(self.school.id), self.user,
                [{
                    "entity_type": "student",
                    "id": self.student.pk,
                    "changes": {
                        "first_name": "Adaeze",
                        "admission_number": "26ZZZC9999",  # the field it has never heard of
                    },
                    "updated_at": (timezone.now() + timedelta(hours=1)).isoformat(),
                }],
                persist_conflicts=True, sync_origin="edge-push",
            )

        self.assertEqual(out["success_count"], 1, out)
        self.assertEqual(out.get("conflicts"), [], out)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Adaeze")  # the known field landed
        self.assertEqual(self.student.admission_number, "26AAAB0001")  # the unknown one did not

    def test_CONTROL_the_same_payload_DOES_write_the_field_on_a_current_receiver(self):
        """Without this, the test above proves nothing.

        If `admission_number` were unwritable over the rail for any other reason -- absent
        from the registry, stripped as down-only, refused by policy -- the narrowed-config
        test would pass while measuring something else entirely, and would keep passing if
        the drop-unknown-fields filter were deleted tomorrow. This is the control that
        makes the narrowing the ONLY difference between the two runs.
        """
        from apps.api import sync_services

        out = sync_services.apply_changes(
            str(self.school.id), self.user,
            [{
                "entity_type": "student", "id": self.student.pk,
                "changes": {"first_name": "Adaeze", "admission_number": "26ZZZC9999"},
                "updated_at": (timezone.now() + timedelta(hours=1)).isoformat(),
            }],
            persist_conflicts=True, sync_origin="edge-push",
        )
        self.assertEqual(out["success_count"], 1, out)
        self.student.refresh_from_db()
        self.assertEqual(self.student.admission_number, "26ZZZC9999")

    def test_the_drop_is_silent_which_is_the_uncomfortable_half(self):
        """Nothing reports it. Recorded because it is the cost of the compatible behaviour.

        A refused row would at least be visible. This is the shape of the original defect
        the admission-number work was fixing -- a field that is not on the receiver's rail
        is never compared, so the two nodes disagree permanently and quietly. Tolerating
        skew during a rollout and hiding divergence forever are the same mechanism.
        """
        from apps.api import sync_services

        real = sync_services._get_entity_config(include_derived=True)
        older = _narrowed_without(real, "student", "admission_number")
        with patch.object(sync_services, "_get_entity_config", return_value=older):
            out = sync_services.apply_changes(
                str(self.school.id), self.user,
                [{
                    "entity_type": "student", "id": self.student.pk,
                    "changes": {"first_name": "Adaeze", "admission_number": "26ZZZC9999"},
                    "updated_at": (timezone.now() + timedelta(hours=1)).isoformat(),
                }],
                persist_conflicts=True, sync_origin="edge-push",
            )
        blob = repr(out)
        self.assertNotIn("admission_number", blob,
                         "if the drop is ever reported, say so in the rollout notes")

    def test_the_parity_digest_mismatches_across_the_skew_even_when_rows_are_identical(self):
        """THE SECOND CLAIM, and the one an operator will trip over.

        `entity_digest` folds the rail field set, so the node that knows one more field
        hashes one more value per row. Same rows, same count, different hash -- which
        during a staged rollout is indistinguishable from real divergence unless somebody
        wrote down that it is expected.
        """
        from apps.api import sync_services
        from apps.sync_engine import parity

        real = sync_services._get_entity_config(include_derived=True)
        model, wide = real["student"]
        narrow = type(wide)(f for f in wide if f != "admission_number")

        wide_digest = parity.entity_digest(self.school, "student", model, wide)
        narrow_digest = parity.entity_digest(self.school, "student", model, narrow)

        self.assertEqual(wide_digest["n"], narrow_digest["n"], "row COUNTS stay comparable")
        self.assertNotEqual(wide_digest["h"], narrow_digest["h"])

    def test_and_the_digests_agree_again_once_both_sides_know_the_field(self):
        """The mismatch is the SKEW, not the data -- so it has to clear on its own once
        both nodes deploy. Without this the test above would equally describe a rail that
        is simply broken.
        """
        from apps.api import sync_services
        from apps.sync_engine import parity

        real = sync_services._get_entity_config(include_derived=True)
        model, wide = real["student"]
        a = parity.entity_digest(self.school, "student", model, wide)
        b = parity.entity_digest(self.school, "student", model, wide)
        self.assertEqual(a["h"], b["h"])
