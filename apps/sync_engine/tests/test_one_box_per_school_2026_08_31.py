"""G5: a school gets ONE box, and a second one is refused instead of half-working.

WHAT IS ACTUALLY WRONG. One box per school is STRUCTURAL in this engine, not
configured, and until now nothing said so out loud:

  * ``EdgeFleetState.school`` is a ``OneToOneField`` -- the cloud can hold the
    self-reported state of exactly one box per school;
  * ``EdgeSyncCursor`` is unique on ``(school, direction)``, with no device column;
  * ``SyncApplyLedger`` is unique on ``(school, entity_type, local_pk)``, and its
    ``origin`` field says of itself "Observability only; the suppression logic does
    not depend on it".

The last one is not a cosmetic limit. That ledger DRIVES echo-suppression inside
``build_edge_delta_rows``, and it is device-blind:

    box A pushes row R   ->  the cloud applies R and writes a ledger entry for it
    box B pulls          ->  build_edge_delta_rows sees R.updated_at still equal to
                             the recorded value and drops R as an "echo" -- of a
                             write box B has never seen

Box B is never told. Nothing raises, no conflict is recorded, no counter moves: the
row is simply ABSENT on box B, and stays absent until some unrelated LOCAL edit moves
R's ``updated_at`` off the recorded value. :class:`EchoStarvationTests` reproduces
exactly that, including the part that makes it unrecoverable by the normal repairs --
a FULL pull (``since=None``, which is what a full-resync directive and a parity repair
both fall back to) omits the row too, because echo-suppression runs BEFORE any of the
narrowing does.

WHAT THIS CHANGE DOES, AND DELIBERATELY DOES NOT DO. Supporting two boxes properly
means putting a device dimension on the apply ledger and on the pull cursor, which is
a migration on shared tables plus a rewrite of the suppression predicate and of every
call site that advances a cursor. That is NOT what this change is. This change makes
the unsupported topology fail LOUDLY: the pairing flow refuses to bind a second box to
a school and says why, so an operator meets a refusal at install time instead of a
half-syncing school six weeks later. The recorded decision, and what the full fix
would cost, is in ``docs/EDGE_ONE_BOX_PER_SCHOOL_2026_08_31.md``.

:class:`EchoStarvationTests` therefore pins the JUSTIFICATION and must keep passing
while the limitation stands. If someone later gives the ledger a device dimension,
those tests SHOULD start failing -- that is the signal that the refusal below has
become unnecessary, and it is the right way to find out.
"""
from __future__ import annotations

import datetime as dt
import uuid
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import Department
from apps.schools.models import School
from apps.sync_engine.edge_outbox import build_edge_delta_rows
from apps.sync_engine.models import SyncApplyLedger
from apps.sync_engine.models_pairing import EdgePairingRequest


def _school(prefix):
    """A school with a DISTINCT subdomain.

    ``School.subdomain`` is ``blank=True, unique=True``, which means optional exactly
    ONCE: the second row created without one collides on "" under the unique index.
    """
    uid = uuid.uuid4().hex[:8]
    return School.objects.create(
        name=f"{prefix} {uid}", slug=f"{prefix}-{uid}", subdomain=f"{prefix}{uid}"
    )


class EchoStarvationTests(TestCase):
    """The claim, reproduced: box B is silently starved of box A's changes.

    This is the whole reason a second box is refused, so it is proved here rather than
    asserted in a comment. Both boxes are represented by what the CLOUD actually does
    for them -- an apply with ``sync_origin="edge-push"`` (box A's push landing) and a
    ``build_edge_delta_rows`` call (the bundle served to box B's pull). No HTTP: the
    starvation is in the builder, not in the transport.
    """

    def setUp(self):
        from apps.accounts.models import User

        uid = uuid.uuid4().hex[:6]
        self.school = _school("starve")
        self.admin = User.objects.create_user(
            username=f"starve_{uid}", password="x" * 12, role=User.Role.ADMIN, is_staff=True
        )
        # A row that exists on the cloud and on both boxes before anything happens.
        self.dept = Department.objects.create(
            school=self.school, name="Ops", code=f"OPS-{uid}"
        )
        # Box B has synced everything up to here and holds this as its pull position.
        self.box_b_cursor = timezone.now()

    def _box_a_pushes(self, new_name):
        """What the cloud does when box A's bundle arrives: apply + write the ledger."""
        from apps.api.sync_services import apply_changes

        out = apply_changes(
            str(self.school.id),
            self.admin,
            [
                {
                    "entity_type": "department",
                    "id": self.dept.pk,
                    "client_offline_id": "",
                    "changes": {"name": new_name},
                    # Newer than the cloud's copy, so this is an ordinary accepted
                    # push and not an LWW refusal -- otherwise the test would be
                    # measuring the conflict path instead of the ledger.
                    "updated_at": (timezone.now() + dt.timedelta(minutes=5)).isoformat(),
                }
            ],
            persist_conflicts=False,
            sync_origin="edge-push",
        )
        self.assertEqual(out["results"][0]["status"], 200, out["results"])
        return out

    def _served_to_box_b(self, since):
        rows, _meta = build_edge_delta_rows(self.school, since=since)
        return [r["id"] for r in rows if r["entity_type"] == "department"]

    def test_the_apply_ledger_has_no_device_dimension(self):
        """The premise, stated as a schema fact rather than a belief about the code."""
        field_names = {f.name for f in SyncApplyLedger._meta.get_fields()}
        self.assertNotIn("device_id", field_names)
        self.assertNotIn("device", field_names)
        constraint = next(
            c for c in SyncApplyLedger._meta.constraints if c.name == "uq_syncapplyledger_row"
        )
        self.assertEqual(
            list(constraint.fields),
            ["school", "entity_type", "local_pk"],
            "the ledger key gained/lost a dimension; re-derive the starvation argument",
        )

    def test_box_b_is_starved_of_a_row_box_a_pushed(self):
        """The finding. Not a crash, not a conflict -- an absence."""
        self._box_a_pushes("Renamed by box A")

        self.assertEqual(
            SyncApplyLedger.objects.filter(
                school=self.school, entity_type="department", local_pk=str(self.dept.pk)
            ).count(),
            1,
            "premise check: the cloud recorded box A's push in the shared ledger",
        )
        self.assertNotIn(
            self.dept.pk,
            self._served_to_box_b(self.box_b_cursor),
            "box B was served box A's row after all -- re-derive the starvation claim",
        )

    def test_a_full_pull_does_not_rescue_box_b(self):
        """`since=None` is the biggest hammer the rail has, and it does not help.

        A full-resync directive and a parity-driven repair both fall back to a
        no-cursor pull. Echo-suppression runs BEFORE the cursor filter and before the
        parity bucket narrowing (`build_edge_delta_bundle` filters `keep_buckets`
        AFTER `build_edge_delta_rows` has already dropped the row), so neither repair
        can reach a row the ledger has marked. That is what makes this permanent
        rather than merely slow.
        """
        self._box_a_pushes("Renamed by box A")
        self.assertNotIn(self.dept.pk, self._served_to_box_b(None))

    def test_the_ledger_is_what_drops_it(self):
        """Control: with the provenance marker gone, the same pull ships the row.

        Without this the test above would prove only that the row was missing, not
        WHY -- and a wrong diagnosis is what the refusal would then be built on.
        """
        self._box_a_pushes("Renamed by box A")
        SyncApplyLedger.objects.filter(school=self.school).delete()
        self.assertIn(self.dept.pk, self._served_to_box_b(self.box_b_cursor))

    def test_a_later_local_edit_does_reach_box_b(self):
        """The bound, stated honestly: the starvation ends if anything touches the row.

        Echo-suppression compares provenance, not a clock, so a genuine later edit
        moves `updated_at` off the recorded value and the row ships again. That is why
        this is invisible in testing -- an actively edited record self-heals, and only
        the records nobody touches again stay missing.
        """
        self._box_a_pushes("Renamed by box A")
        local = Department.objects.get(pk=self.dept.pk)
        local.name = "Edited on the cloud by a human"
        local.save(update_fields=["name", "updated_at"])
        self.assertIn(self.dept.pk, self._served_to_box_b(self.box_b_cursor))


class SecondBoxIsRefusedTests(TestCase):
    """A second box for one school must be REFUSED, at every gate that can bind one.

    Four gates, because each closes a different way in:

      * ``start_pairing``  -- the technician standing at the box learns immediately,
        which is the whole point of the box->cloud direction;
      * ``approve_pairing`` -- a request opened while the school was unbound must not
        become approvable after another box binds;
      * ``collect_pairing`` -- a claim ticket AUTO-APPROVES inside ``start_pairing``
        and never passes through ``approve_pairing`` at all, so the mint itself has to
        be the fail-closed gate;
      * ``mint_claim_ticket`` -- pre-authorising an adoption of an already-bound school
        is pre-authorising the thing the other three refuse.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model

        from apps.schools.models import SchoolMembership

        uid = uuid.uuid4().hex[:6]
        self.school = _school("onebox")
        self.other = _school("onebox-other")
        User = get_user_model()
        self.admin = User.objects.create_user(
            username=f"onebox_admin_{uid}", password="x" * 12, email=f"a{uid}@example.com"
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role="ADMIN", is_school_owner=True
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.other, role="ADMIN", is_school_owner=True
        )

    # ------------------------------------------------------------------ helpers --
    def _start(self, device_id, school=None, claim_ticket=""):
        from apps.sync_engine.pairing_service import start_pairing

        school = school or self.school
        with mock.patch(
            "apps.sync_engine.pairing_service.notify_admins_of_pending_pairing"
        ):
            return start_pairing(
                claimed_slug=school.slug, device_id=device_id, claim_ticket=claim_ticket
            )

    def _pair(self, device_id, school=None, claim_ticket=""):
        """Drive a whole pairing. Returns the outcome tagged with the stage it ended at."""
        from apps.sync_engine.pairing_service import approve_pairing, collect_pairing

        school = school or self.school
        started = self._start(device_id, school=school, claim_ticket=claim_ticket)
        if not started.get("ok"):
            return {"stage": "start", **started}
        if not started.get("pre_approved"):
            approved = approve_pairing(
                code=started["user_code"], approver=self.admin, school=school
            )
            if not approved.get("ok"):
                return {"stage": "approve", **approved}
        collected = collect_pairing(
            request_id=started["request_id"], poll_secret=started["poll_secret"]
        )
        if not collected.get("ok"):
            return {"stage": "collect", **collected}
        return {"stage": "paired", **collected}

    # -------------------------------------------------------------------- gates --
    def test_the_first_box_pairs_normally(self):
        """Premise check. A guard that refuses everything is not a guard."""
        outcome = self._pair("edge-box-a")
        self.assertEqual(outcome["stage"], "paired", outcome)
        self.assertTrue(outcome.get("credential"))

    def test_a_second_box_cannot_even_open_a_request(self):
        self.assertEqual(self._pair("edge-box-a")["stage"], "paired")
        second = self._pair("edge-box-b")
        self.assertEqual(second["stage"], "start", second)
        self.assertEqual(second.get("error"), "school_already_paired", second)

    def test_the_refusal_leaves_no_request_row_behind(self):
        """Refused before anything is written: an anonymous caller gets no write."""
        self.assertEqual(self._pair("edge-box-a")["stage"], "paired")
        before = EdgePairingRequest.objects.filter(school=self.school).count()
        self._pair("edge-box-b")
        self.assertEqual(
            EdgePairingRequest.objects.filter(school=self.school).count(), before
        )

    def test_a_request_opened_before_the_first_box_bound_cannot_be_approved_after(self):
        """The race the start-gate alone cannot close.

        Box B's request is legitimately open (the school had no box when it asked).
        Box A then binds. Approving box B afterwards would create exactly the topology
        the start gate refuses, so the approval decision re-checks rather than trusting
        that the request was clean when it was made.
        """
        from apps.sync_engine.pairing_service import approve_pairing

        pending = self._start("edge-box-b")
        self.assertTrue(pending["ok"], pending)

        self.assertEqual(self._pair("edge-box-a")["stage"], "paired")

        approved = approve_pairing(
            code=pending["user_code"], approver=self.admin, school=self.school
        )
        self.assertFalse(approved.get("ok"), approved)
        self.assertEqual(approved.get("error"), "school_already_paired", approved)

    def test_a_claim_ticket_cannot_smuggle_a_second_box_past_the_mint(self):
        """A ticket auto-approves inside `start_pairing`, so `collect` is the last gate.

        The sequence is the one an operator can genuinely produce: a ticket is minted
        and redeemed by box B on a Friday (pre-approved, credential not yet collected),
        box A is paired over the weekend, and box B's Monday poll would otherwise walk
        away with the second credential.
        """
        from apps.sync_engine.pairing_service import collect_pairing, mint_claim_ticket

        minted = mint_claim_ticket(school=self.school, minted_by=self.admin)
        self.assertTrue(minted["ok"], minted)

        pre = self._start("edge-box-b", claim_ticket=minted["ticket"])
        self.assertTrue(pre["ok"], pre)
        self.assertTrue(pre["pre_approved"], pre)

        self.assertEqual(self._pair("edge-box-a")["stage"], "paired")

        collected = collect_pairing(
            request_id=pre["request_id"], poll_secret=pre["poll_secret"]
        )
        self.assertFalse(collected.get("ok"), collected)
        self.assertEqual(collected.get("error"), "school_already_paired", collected)
        self.assertNotIn("credential", collected)

    def test_a_claim_ticket_cannot_be_minted_for_a_school_that_already_has_a_box(self):
        from apps.sync_engine.pairing_service import mint_claim_ticket

        self.assertEqual(self._pair("edge-box-a")["stage"], "paired")
        minted = mint_claim_ticket(school=self.school, minted_by=self.admin)
        self.assertFalse(minted.get("ok"), minted)
        self.assertEqual(minted.get("error"), "school_already_paired", minted)

    # ------------------------------------------------------- what stays possible --
    def test_the_same_box_may_re_pair(self):
        """A box that lost its own database is the SAME box and must not be locked out.

        This is the case the whole durable-binding design exists for: a rebuilt box
        normally keeps its `EdgeCloudBinding`, and only a box that also lost its
        database comes back asking to pair. Refusing that would turn a recoverable
        incident into a support call, so identity -- not novelty -- is what is checked.
        """
        self.assertEqual(self._pair("edge-box-a")["stage"], "paired")
        again = self._pair("edge-box-a")
        self.assertEqual(again["stage"], "paired", again)

    def test_a_blank_device_id_is_never_treated_as_the_same_box(self):
        """Two anonymous boxes look identical, so "" can never prove sameness.

        `mint_edge_credential` derives `edge-<slug>` when a box sends no device id, so
        the FIRST anonymous box does get a real identity on the cloud -- and a second
        anonymous box would then match it if the check compared what was SENT. It
        compares what is BOUND, and "" matches nothing, so the second is refused.
        """
        self.assertEqual(self._pair("")["stage"], "paired")
        second = self._pair("")
        self.assertEqual(second["stage"], "start", second)
        self.assertEqual(second.get("error"), "school_already_paired", second)

    def test_another_school_is_unaffected(self):
        self.assertEqual(self._pair("edge-box-a")["stage"], "paired")
        self.assertEqual(
            self._pair("edge-box-a", school=self.other)["stage"], "paired"
        )

    def test_revoking_the_box_releases_the_school(self):
        """The documented way out, proved to actually work.

        Revocation is already the product's explicit, audited release action
        (`/portal/super/devices/`), and `mint_edge_credential` refuses to re-arm a
        revoked device -- so a released school accepts a NEW box and never silently
        re-arms the old one.
        """
        from apps.accounts.models_offline_device import DeviceRegistration

        self.assertEqual(self._pair("edge-box-a")["stage"], "paired")
        DeviceRegistration.objects.filter(school=self.school).update(
            revoked_at=timezone.now()
        )
        self.assertEqual(self._pair("edge-box-b")["stage"], "paired")

    def test_an_expired_credential_releases_the_school(self):
        """A binding is a LIVE credential, not a historical fact.

        A school whose box died a year ago holds an expired token and no working box.
        Refusing a replacement on the strength of a credential that can no longer
        authenticate would be a guard protecting nothing.
        """
        from apps.accounts.models_offline_device import OfflineCapabilityToken

        self.assertEqual(self._pair("edge-box-a")["stage"], "paired")
        OfflineCapabilityToken.objects.filter(school=self.school).update(
            expires_at=timezone.now() - dt.timedelta(days=1)
        )
        self.assertEqual(self._pair("edge-box-b")["stage"], "paired")

    # ------------------------------------------------------------- the message --
    def test_the_refusal_says_what_went_wrong_and_what_to_do(self):
        """A refusal a technician cannot act on is a connectivity error in disguise.

        The failure this whole pairing design exists to prevent is an operator reading
        "check RMC_EDGE_OPERATOR_BASE" four days after a wrong path. A bare
        `school_already_paired` code on a terminal is the same mistake, so the message
        has to name the limitation and the release action.
        """
        self.assertEqual(self._pair("edge-box-a")["stage"], "paired")
        refusal = self._start("edge-box-b")
        message = (refusal.get("message") or "").lower()
        self.assertTrue(message, refusal)
        self.assertIn("one box", message)
        self.assertIn("release", message)

    def test_the_anonymous_refusal_does_not_name_the_incumbent(self):
        """`start_pairing` answers UNAUTHENTICATED callers.

        Saying "this school already has a box" is unavoidable -- it is the diagnosis
        the technician came for. Naming the bound device id, hostname or last-seen time
        is not, and an anonymous caller has no standing to learn it.
        """
        self.assertEqual(self._pair("edge-box-a")["stage"], "paired")
        refusal = self._start("edge-box-b")
        blob = repr(refusal)
        self.assertNotIn("edge-box-a", blob)
        self.assertNotIn("bound_device_ids", blob)


class BoundEdgeDevicesTests(TestCase):
    """The predicate the refusal is built on, tested on its own.

    It must answer the same question ``resolve_edge_credential`` answers -- "could a
    box authenticate as this school RIGHT NOW" -- because a guard that consults a
    different source of truth than the authenticator is a guard that disagrees with
    reality in one direction or the other.
    """

    def setUp(self):
        from apps.accounts.models import User

        uid = uuid.uuid4().hex[:6]
        self.school = _school("bound")
        self.user = User.objects.create_user(
            username=f"bound_{uid}", password="x" * 12, role=User.Role.ADMIN, is_staff=True
        )

    def _mint(self, device_id):
        from apps.sync_engine.edge_outbox import mint_edge_credential

        return mint_edge_credential(self.school, self.user, device_id=device_id)

    def test_an_unpaired_school_is_bound_to_nothing(self):
        from apps.sync_engine.pairing_service import bound_edge_device_ids

        self.assertEqual(bound_edge_device_ids(self.school), set())

    def test_a_minted_credential_binds_its_device(self):
        from apps.sync_engine.pairing_service import bound_edge_device_ids

        self._mint("edge-box-a")
        self.assertEqual(bound_edge_device_ids(self.school), {"edge-box-a"})

    def test_a_hand_minted_box_counts_too(self):
        """The pre-pairing install path is still a binding.

        Boxes minted by `manage.py mint_edge_credential` have no `EdgePairingRequest`
        at all. Keying the guard on the pairing audit trail would have let every box
        installed before pairing existed acquire a silent second box -- which is the
        population most likely to get one.
        """
        from apps.sync_engine.models_pairing import EdgePairingRequest
        from apps.sync_engine.pairing_service import bound_edge_device_ids

        self._mint("edge-legacy")
        self.assertFalse(EdgePairingRequest.objects.filter(school=self.school).exists())
        self.assertEqual(bound_edge_device_ids(self.school), {"edge-legacy"})

    def test_a_revoked_device_is_not_bound(self):
        from apps.accounts.models_offline_device import DeviceRegistration
        from apps.sync_engine.pairing_service import bound_edge_device_ids

        self._mint("edge-box-a")
        DeviceRegistration.objects.filter(school=self.school).update(
            revoked_at=timezone.now()
        )
        self.assertEqual(bound_edge_device_ids(self.school), set())

    def test_a_revoked_token_is_not_bound(self):
        from apps.accounts.models_offline_device import OfflineCapabilityToken
        from apps.sync_engine.pairing_service import bound_edge_device_ids

        self._mint("edge-box-a")
        OfflineCapabilityToken.objects.filter(school=self.school).update(
            revoked_at=timezone.now()
        )
        self.assertEqual(bound_edge_device_ids(self.school), set())

    def test_a_non_edge_token_is_not_a_box(self):
        """An ordinary offline device (a teacher's tablet) is not an edge appliance.

        Both live in `DeviceRegistration`. Only the `EDGE_SYNC_SCOPE` marker separates
        them, and without that check a school where one teacher works offline could
        never be given a box at all.
        """
        from datetime import timedelta

        from apps.accounts.models_offline_device import (
            DeviceRegistration,
            OfflineCapabilityToken,
        )
        from apps.sync_engine.pairing_service import bound_edge_device_ids

        device = DeviceRegistration.objects.create(
            school=self.school,
            user=self.user,
            device_id="tablet-7",
            permission_bitmap=["offline-read"],
        )
        OfflineCapabilityToken.objects.create(
            device=device,
            school=self.school,
            user=self.user,
            token_fingerprint="f" * 64,
            permission_bitmap=["offline-read"],
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertEqual(bound_edge_device_ids(self.school), set())

    def test_no_school_is_never_a_conflict(self):
        """An unresolvable slug is already handled, and differently.

        `start_pairing` deliberately opens a visible request for a slug it cannot
        resolve so a typo is diagnosable. This guard must not turn that into a
        refusal, or the diagnosis disappears again.
        """
        from apps.sync_engine.pairing_service import adoption_conflict

        self.assertIsNone(adoption_conflict(None, "edge-box-a"))
