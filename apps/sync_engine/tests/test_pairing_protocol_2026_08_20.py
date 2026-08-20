"""Box<->cloud pairing: the security properties, pinned.

These are not "does the happy path work" tests. Each one holds down a property the
design depends on, and would pass just as well if the feature were merely convenient
rather than safe:

  * the short code is not sufficient to collect a credential (the poll secret is),
  * an admin of school A cannot adopt a box that asked for school B,
  * a credential is issued exactly once, even under concurrent polls,
  * a wrong secret is indistinguishable from an unknown request, so the endpoint
    cannot be used to enumerate ids,
  * expiry is applied on READ, so a request cannot be revived by a sweeper never
    having run.

The pairing binding tests additionally pin the precedence rule that makes a rebuilt
container keep its pairing: the durable binding beats the environment.
"""
from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.sync_engine.models_pairing import (
    CODE_ALPHABET,
    EdgePairingRequest,
    generate_user_code,
    hash_poll_secret,
    normalize_user_code,
)


class UserCodeTests(SimpleTestCase):
    def test_code_shape_is_two_groups_of_four(self):
        code = generate_user_code()
        head, _, tail = code.partition("-")
        self.assertEqual(len(head), 4)
        self.assertEqual(len(tail), 4)

    def test_code_avoids_every_confusable_character(self):
        for _ in range(200):
            for ch in generate_user_code().replace("-", ""):
                self.assertIn(ch, CODE_ALPHABET)
                self.assertNotIn(ch, "ILO01")

    def test_normalize_accepts_what_a_human_actually_types(self):
        canonical = "FRTY-8K2M"
        for typed in ("frty8k2m", "FRTY 8K2M", " frty-8k2m ", "FRTY--8K2M"):
            with self.subTest(typed=typed):
                self.assertEqual(normalize_user_code(typed), canonical)

    def test_normalize_does_not_rewrite_valid_characters(self):
        """Folding O->Q would corrupt a correctly typed code; both are excluded."""
        self.assertEqual(normalize_user_code("QQQQ-JJJJ"), "QQQQ-JJJJ")

    def test_poll_secret_is_hashed_not_stored(self):
        self.assertNotEqual(hash_poll_secret("secret"), "secret")
        self.assertEqual(len(hash_poll_secret("secret")), 64)


class PairingProtocolTests(TestCase):
    """End to end across the real models."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        from apps.schools.models import School, SchoolMembership

        self.school = School.objects.create(name="Gilead Tech", slug="gilead-tech")
        self.other = School.objects.create(name="Other School", slug="other-school")
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="gilead_admin", password="x", email="a@example.com"
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role="ADMIN"
        )
        self.outsider = User.objects.create_user(
            username="other_admin", password="x", email="b@example.com"
        )
        SchoolMembership.objects.create(
            user=self.outsider, school=self.other, role="ADMIN"
        )

    # ------------------------------------------------------------------ start --
    def _start(self, slug="gilead-tech"):
        from apps.sync_engine.pairing_service import start_pairing

        with mock.patch(
            "apps.sync_engine.pairing_service.notify_admins_of_pending_pairing"
        ):
            return start_pairing(claimed_slug=slug, device_id="edge-gilead-tech")

    def test_start_returns_a_code_and_a_secret_and_stores_only_the_hash(self):
        result = self._start()
        self.assertTrue(result["ok"])
        row = EdgePairingRequest.objects.get(pk=result["request_id"])
        self.assertEqual(row.status, EdgePairingRequest.Status.PENDING)
        self.assertEqual(row.poll_secret_hash, hash_poll_secret(result["poll_secret"]))
        self.assertNotIn(result["poll_secret"], row.poll_secret_hash)

    def test_an_unknown_slug_still_opens_a_visible_request(self):
        """A mistyped slug must be diagnosable, not a silent 404 the box misreports."""
        result = self._start(slug="does-not-exist")
        self.assertTrue(result["ok"])
        self.assertFalse(result["school_resolved"])
        row = EdgePairingRequest.objects.get(pk=result["request_id"])
        self.assertIsNone(row.school)
        self.assertEqual(row.claimed_slug, "does-not-exist")

    # ------------------------------------------------------------------- poll --
    def test_pending_poll_yields_no_credential(self):
        from apps.sync_engine.pairing_service import collect_pairing

        started = self._start()
        out = collect_pairing(
            request_id=started["request_id"], poll_secret=started["poll_secret"]
        )
        self.assertEqual(out["status"], "pending")
        self.assertNotIn("credential", out)

    def test_the_code_alone_cannot_collect_a_credential(self):
        """The central claim of the whole design."""
        from apps.sync_engine.pairing_service import approve_pairing, collect_pairing

        started = self._start()
        approve_pairing(code=started["user_code"], approver=self.admin, school=self.school)
        out = collect_pairing(
            request_id=started["request_id"], poll_secret="not-the-secret"
        )
        self.assertEqual(out["status"], "unknown")
        self.assertNotIn("credential", out)

    def test_a_wrong_secret_is_indistinguishable_from_an_unknown_request(self):
        from apps.sync_engine.pairing_service import collect_pairing

        started = self._start()
        wrong_secret = collect_pairing(
            request_id=started["request_id"], poll_secret="nope"
        )
        unknown_id = collect_pairing(
            request_id="00000000-0000-0000-0000-000000000000", poll_secret="nope"
        )
        self.assertEqual(wrong_secret, unknown_id)

    # --------------------------------------------------------------- approval --
    def test_approval_by_the_schools_admin_issues_a_credential_once(self):
        from apps.sync_engine.pairing_service import approve_pairing, collect_pairing

        started = self._start()
        approved = approve_pairing(
            code=started["user_code"], approver=self.admin, school=self.school
        )
        self.assertTrue(approved["ok"])

        first = collect_pairing(
            request_id=started["request_id"], poll_secret=started["poll_secret"]
        )
        self.assertEqual(first["status"], "approved")
        self.assertTrue(first["credential"])
        self.assertEqual(first["school_slug"], "gilead-tech")

        second = collect_pairing(
            request_id=started["request_id"], poll_secret=started["poll_secret"]
        )
        self.assertEqual(second["status"], "redeemed")
        self.assertNotIn("credential", second)

    def test_the_issued_credential_actually_resolves_to_the_school(self):
        """A credential that does not authenticate would be a very quiet failure."""
        from apps.sync_engine.edge_outbox import resolve_edge_credential
        from apps.sync_engine.pairing_service import approve_pairing, collect_pairing

        started = self._start()
        approve_pairing(code=started["user_code"], approver=self.admin, school=self.school)
        out = collect_pairing(
            request_id=started["request_id"], poll_secret=started["poll_secret"]
        )
        resolved = resolve_edge_credential(out["credential"])
        self.assertIsNotNone(resolved)
        user, school = resolved
        self.assertEqual(school.pk, self.school.pk)
        self.assertEqual(user.pk, self.admin.pk)

    def test_an_admin_of_another_school_cannot_adopt_this_box(self):
        from apps.sync_engine.pairing_service import approve_pairing

        started = self._start()
        result = approve_pairing(
            code=started["user_code"], approver=self.outsider, school=self.other
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "wrong_tenant")
        row = EdgePairingRequest.objects.get(pk=started["request_id"])
        self.assertEqual(row.status, EdgePairingRequest.Status.PENDING)

    def test_a_non_admin_of_the_right_school_cannot_approve(self):
        from django.contrib.auth import get_user_model

        from apps.sync_engine.pairing_service import approve_pairing

        nobody = get_user_model().objects.create_user(username="nobody", password="x")
        started = self._start()
        result = approve_pairing(
            code=started["user_code"], approver=nobody, school=self.school
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "forbidden")

    def test_a_denied_request_never_yields_a_credential(self):
        from apps.sync_engine.pairing_service import collect_pairing, deny_pairing

        started = self._start()
        denied = deny_pairing(
            code=started["user_code"],
            approver=self.admin,
            school=self.school,
            reason="not ours",
        )
        self.assertTrue(denied["ok"])
        out = collect_pairing(
            request_id=started["request_id"], poll_secret=started["poll_secret"]
        )
        self.assertEqual(out["status"], "denied")
        self.assertNotIn("credential", out)

    # ----------------------------------------------------------------- expiry --
    def test_expiry_is_applied_on_read_not_by_a_sweeper(self):
        from apps.sync_engine.pairing_service import collect_pairing

        started = self._start()
        row = EdgePairingRequest.objects.get(pk=started["request_id"])
        row.expires_at = timezone.now() - timedelta(seconds=1)
        row.save(update_fields=["expires_at"])

        out = collect_pairing(
            request_id=started["request_id"], poll_secret=started["poll_secret"]
        )
        self.assertEqual(out["status"], "expired")
        row.refresh_from_db()
        self.assertEqual(row.status, EdgePairingRequest.Status.EXPIRED)

    def test_an_expired_request_cannot_be_approved(self):
        from apps.sync_engine.pairing_service import approve_pairing

        started = self._start()
        EdgePairingRequest.objects.filter(pk=started["request_id"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        result = approve_pairing(
            code=started["user_code"], approver=self.admin, school=self.school
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "expired")

    @override_settings(RMC_EDGE_PAIRING_TTL_HOURS=72)
    def test_the_default_window_is_days_so_deferred_approval_is_possible(self):
        started = self._start()
        row = EdgePairingRequest.objects.get(pk=started["request_id"])
        self.assertGreater(row.expires_at - timezone.now(), timedelta(hours=71))

    # ------------------------------------------------------------- queue view --
    def test_pending_queue_is_scoped_to_one_school(self):
        from apps.sync_engine.pairing_service import pending_requests_for_school

        self._start(slug="gilead-tech")
        self._start(slug="other-school")
        mine = list(pending_requests_for_school(self.school))
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0].school_id, self.school.pk)


class EdgeBindingPrecedenceTests(TestCase):
    """A rebuilt container must not silently unpair itself."""

    def test_binding_beats_the_environment(self):
        from apps.sync_engine import edge_binding
        from apps.sync_engine.models_pairing import EdgeCloudBinding

        EdgeCloudBinding.objects.create(
            operator_base="https://paired.example.com",
            school_slug="gilead-tech",
            credential="from-pairing",
            sealed=True,
        )
        with override_settings(RMC_EDGE_OPERATOR_BASE="https://stale-env.example.com"):
            with mock.patch.dict("os.environ", {"RMC_EDGE_CREDENTIAL": "from-env"}):
                self.assertEqual(
                    edge_binding.operator_base(), "https://paired.example.com"
                )
                self.assertEqual(edge_binding.edge_credential(), "from-pairing")

    def test_environment_still_works_when_no_binding_exists(self):
        """Every existing deployment keeps working with no migration step."""
        from apps.sync_engine import edge_binding

        with override_settings(RMC_EDGE_OPERATOR_BASE="https://env.example.com"):
            with mock.patch.dict("os.environ", {"RMC_EDGE_CREDENTIAL": "env-token"}):
                self.assertEqual(edge_binding.operator_base(), "https://env.example.com")
                self.assertEqual(edge_binding.edge_credential(), "env-token")

    def test_credential_is_encrypted_at_rest(self):
        from django.db import connection

        from apps.sync_engine.models_pairing import EdgeCloudBinding

        row = EdgeCloudBinding.objects.create(
            operator_base="https://c.example.com", credential="super-secret-token"
        )
        with connection.cursor() as cur:
            cur.execute(
                "SELECT credential FROM sync_engine_edgecloudbinding WHERE id = %s",
                [str(row.pk)],
            )
            stored = cur.fetchone()[0]
        self.assertNotIn("super-secret-token", stored or "")
        self.assertEqual(
            EdgeCloudBinding.objects.get(pk=row.pk).credential, "super-secret-token"
        )

    def test_unpairing_clears_the_binding(self):
        from apps.sync_engine import edge_binding
        from apps.sync_engine.models_pairing import EdgeCloudBinding

        EdgeCloudBinding.objects.create(
            operator_base="https://c.example.com", credential="t", sealed=True
        )
        self.assertTrue(edge_binding.is_sealed())
        self.assertTrue(edge_binding.clear_binding())
        self.assertEqual(EdgeCloudBinding.objects.count(), 0)


class DerivedOperatorBaseTests(SimpleTestCase):
    """The only value shaped per-school is the slug; derive the rest."""

    @override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
    def test_derives_the_tenant_host_from_the_slug(self):
        from apps.sync_engine.edge_binding import derive_operator_base

        with mock.patch.dict("os.environ", {}, clear=False):
            self.assertEqual(
                derive_operator_base("gilead-tech"),
                "https://gilead-tech.runmycampus.com",
            )

    @override_settings(MULTI_TENANT_BASE_DOMAIN="school.lan")
    def test_refuses_to_derive_a_lan_address_which_would_point_at_the_box(self):
        from apps.sync_engine.edge_binding import derive_operator_base

        with mock.patch.dict("os.environ", {"MULTI_TENANT_BASE_DOMAIN": "school.lan"}):
            self.assertEqual(derive_operator_base("gilead-tech"), "")

    def test_no_slug_derives_nothing(self):
        from apps.sync_engine.edge_binding import derive_operator_base

        self.assertEqual(derive_operator_base(""), "")


class PlatformStaffBackstopTests(TestCase):
    """The answer to 'nobody at the school is available to approve'."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        from apps.schools.models import School

        self.school = School.objects.create(name="Gilead Tech", slug="gilead-tech")
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="platform_ops", password="x", is_staff=True
        )
        self.nobody = User.objects.create_user(username="random", password="x")

    def _start(self):
        from apps.sync_engine.pairing_service import start_pairing

        with mock.patch(
            "apps.sync_engine.pairing_service.notify_admins_of_pending_pairing"
        ):
            return start_pairing(claimed_slug="gilead-tech")

    def test_platform_staff_can_approve_on_the_schools_behalf(self):
        from apps.sync_engine.pairing_service import approve_pairing

        started = self._start()
        result = approve_pairing(code=started["user_code"], approver=self.staff)
        self.assertTrue(result["ok"], result)

    def test_the_credential_is_bound_to_the_staff_member_who_approved(self):
        """An operator-approved box stays visibly operator-approved."""
        from apps.sync_engine.edge_outbox import resolve_edge_credential
        from apps.sync_engine.pairing_service import approve_pairing, collect_pairing

        started = self._start()
        approve_pairing(code=started["user_code"], approver=self.staff)
        out = collect_pairing(
            request_id=started["request_id"], poll_secret=started["poll_secret"]
        )
        user, _school = resolve_edge_credential(out["credential"])
        self.assertEqual(user.pk, self.staff.pk)
        row = EdgePairingRequest.objects.get(pk=started["request_id"])
        self.assertEqual(row.approved_by_id, self.staff.pk)

    def test_an_ordinary_user_is_still_refused(self):
        from apps.sync_engine.pairing_service import approve_pairing

        started = self._start()
        result = approve_pairing(code=started["user_code"], approver=self.nobody)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "forbidden")
