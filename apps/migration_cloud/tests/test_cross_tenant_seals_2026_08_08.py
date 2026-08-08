"""Regression seals for four Migration Cloud isolation / SSRF defects
found in the 2026-08-08 world-leader audit.

Each seal has a test that FAILS against the pre-fix code and PASSES against
the fix:

  1. ``MigrationCloudMergeBundlesView`` — the portal shell merged bundles by
     raw pk with NO school filter, so a tenant could fold another school's
     bundle into a joint parent for a cross-tenant apply (IDOR).
  2. ``MigrationCloudShadowView`` — ``start``/``refresh``/``close`` mutate
     cutover state but passed the raw ``bundle_id`` straight into ``shadow.*``
     with no tenant check, so a portal caller could arm/seal another tenant's
     shadow window (IDOR).
  3. ``MigrationCloudIdMappingLookupView`` — the portal shell only filtered by
     school *when it resolved*; a ``None`` school returned every tenant's
     legacy→canonical id map (fail-open leak).
  4. ``url_intake._fetch_http`` — fetched arbitrary URLs with no SSRF guard, so
     an intake handle resolving to loopback / RFC-1918 / link-local
     (``169.254.169.254`` cloud metadata) would be fetched by the server.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest import mock

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.migration_cloud.intake.base import IntakeError
from apps.migration_cloud.intake.url_intake import (
    _SSRFGuardedRedirectHandler,
    _assert_public_host,
)
from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationBundle,
    MigrationIdMapping,
)
from apps.migration_cloud.views import (
    MigrationCloudIdMappingLookupView,
    MigrationCloudMergeBundlesView,
    MigrationCloudShadowView,
)
from apps.schools.models import School


def _school(slug: str) -> School:
    return School.objects.create(name=slug, slug=slug, subdomain=slug, is_active=True)


def _bundle(school: School, key: str, status: str = BundleStatus.MAPPED) -> MigrationBundle:
    return MigrationBundle.objects.create(
        label=f"bundle-{key}",
        intake_method=IntakeMethod.FILE_UPLOAD,
        idempotency_key=key,
        status=status,
        school=school,
    )


class MergeBundlesTenantScopeTests(TestCase):
    """Seal #1 — portal merge may only touch the caller's own bundles."""

    def setUp(self):
        self.rf = RequestFactory()
        self.school_a = _school("merge-seal-a")
        self.school_b = _school("merge-seal-b")
        self.user = User.objects.create_user(username="merge_seal_user", password="x")
        self.a1 = _bundle(self.school_a, "merge-a1")
        self.a2 = _bundle(self.school_a, "merge-a2")
        self.b1 = _bundle(self.school_b, "merge-b1")

    def _post(self, bundle_ids, shell, school=None):
        request = self.rf.post(
            "/migration/merge/",
            data=json.dumps({"bundle_ids": bundle_ids}),
            content_type="application/json",
        )
        request.user = self.user
        if school is not None:
            request.school = school
        return MigrationCloudMergeBundlesView.as_view()(request, shell=shell)

    def test_portal_cannot_merge_foreign_bundle(self):
        before = MigrationBundle.objects.count()
        resp = self._post([self.a1.pk, self.b1.pk], shell="portal", school=self.school_a)
        self.assertEqual(resp.status_code, 404)
        # No parent bundle was created folding B's data under A.
        self.assertEqual(MigrationBundle.objects.count(), before)

    def test_portal_can_merge_own_bundles(self):
        resp = self._post([self.a1.pk, self.a2.pk], shell="portal", school=self.school_a)
        self.assertEqual(resp.status_code, 200)
        merged_id = json.loads(resp.content.decode())["merged_bundle_id"]
        self.assertTrue(
            MigrationBundle.objects.filter(pk=merged_id, school=self.school_a).exists()
        )

    def test_portal_unresolved_school_cannot_merge(self):
        resp = self._post([self.a1.pk, self.a2.pk], shell="portal", school=None)
        self.assertEqual(resp.status_code, 404)

    def test_super_shell_merge_still_works(self):
        resp = self._post([self.a1.pk, self.a2.pk], shell="super")
        self.assertEqual(resp.status_code, 200)


class ShadowActionTenantScopeTests(TestCase):
    """Seal #2 — every shadow action is tenant-scoped in the portal shell."""

    def setUp(self):
        self.rf = RequestFactory()
        self.school_a = _school("shadow-seal-a")
        self.school_b = _school("shadow-seal-b")
        self.user = User.objects.create_user(username="shadow_seal_user", password="x")
        self.a = _bundle(self.school_a, "shadow-a", status=BundleStatus.APPLIED)
        self.b = _bundle(self.school_b, "shadow-b", status=BundleStatus.APPLIED)

    def _post(self, bundle_id, action, shell, school=None):
        request = self.rf.post(
            f"/migration/{bundle_id}/shadow/?action={action}",
            data=json.dumps({}),
            content_type="application/json",
        )
        request.user = self.user
        if school is not None:
            request.school = school
        return MigrationCloudShadowView.as_view()(
            request, bundle_id=bundle_id, shell=shell
        )

    @mock.patch("apps.migration_cloud.shadow.start_shadow_window")
    def test_portal_cannot_start_shadow_on_foreign_bundle(self, start_mock):
        resp = self._post(self.b.pk, "start", shell="portal", school=self.school_a)
        self.assertEqual(resp.status_code, 404)
        start_mock.assert_not_called()

    @mock.patch("apps.migration_cloud.shadow.close_shadow")
    def test_portal_cannot_close_shadow_on_foreign_bundle(self, close_mock):
        resp = self._post(self.b.pk, "close", shell="portal", school=self.school_a)
        self.assertEqual(resp.status_code, 404)
        close_mock.assert_not_called()

    @mock.patch("apps.migration_cloud.shadow.start_shadow_window")
    def test_portal_own_bundle_shadow_start_reaches_service(self, start_mock):
        @dataclass
        class _FakeState:
            bundle_id: int
            opened: bool = True

        start_mock.return_value = _FakeState(bundle_id=self.a.pk)
        resp = self._post(self.a.pk, "start", shell="portal", school=self.school_a)
        self.assertEqual(resp.status_code, 200)
        start_mock.assert_called_once()
        self.assertEqual(start_mock.call_args.kwargs["bundle_id"], self.a.pk)

    @mock.patch("apps.migration_cloud.shadow.start_shadow_window")
    def test_super_shell_shadow_start_not_blocked(self, start_mock):
        @dataclass
        class _FakeState:
            bundle_id: int

        start_mock.return_value = _FakeState(bundle_id=self.b.pk)
        resp = self._post(self.b.pk, "start", shell="super")
        self.assertEqual(resp.status_code, 200)
        start_mock.assert_called_once()


class IdMappingLookupTenantScopeTests(TestCase):
    """Seal #3 — id-map lookup fails closed for an unresolved portal tenant."""

    def setUp(self):
        self.rf = RequestFactory()
        self.school_a = _school("idmap-seal-a")
        self.school_b = _school("idmap-seal-b")
        self.user = User.objects.create_user(username="idmap_seal_user", password="x")
        self.bundle_a = _bundle(self.school_a, "idmap-a")
        self.bundle_b = _bundle(self.school_b, "idmap-b")
        MigrationIdMapping.objects.create(
            bundle=self.bundle_a,
            school=self.school_a,
            legacy_namespace="powerschool",
            legacy_id="PS-1",
            canonical_model="apps.people.StudentProfile",
            canonical_pk="11",
            domain="students",
        )
        MigrationIdMapping.objects.create(
            bundle=self.bundle_b,
            school=self.school_b,
            legacy_namespace="powerschool",
            legacy_id="PS-1",
            canonical_model="apps.people.StudentProfile",
            canonical_pk="22",
            domain="students",
        )

    def _get(self, shell, school=None, legacy_id="PS-1"):
        request = self.rf.get(f"/migration/id-map/lookup/?legacy_id={legacy_id}")
        request.user = self.user
        if school is not None:
            request.school = school
        return MigrationCloudIdMappingLookupView.as_view()(request, shell=shell)

    def test_portal_unresolved_school_fails_closed(self):
        resp = self._get(shell="portal", school=None)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content.decode())["matches"], [])

    def test_portal_sees_only_own_mappings(self):
        resp = self._get(shell="portal", school=self.school_a)
        matches = json.loads(resp.content.decode())["matches"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["canonical_pk"], "11")
        self.assertTrue(all(str(m["school_id"]) == str(self.school_a.pk) for m in matches))

    def test_super_shell_sees_all(self):
        resp = self._get(shell="super")
        matches = json.loads(resp.content.decode())["matches"]
        self.assertEqual(len(matches), 2)


class UrlIntakeSSRFGuardTests(TestCase):
    """Seal #4 — URL intake refuses non-public hosts (SSRF)."""

    @staticmethod
    def _addrinfo(ip):
        # (family, type, proto, canonname, sockaddr) — sockaddr[0] is the IP.
        return [(2, 1, 6, "", (ip, 0))]

    @mock.patch("apps.migration_cloud.intake.url_intake.socket.getaddrinfo")
    def test_blocks_cloud_metadata_ip(self, gai):
        gai.return_value = self._addrinfo("169.254.169.254")
        with self.assertRaises(IntakeError):
            _assert_public_host("http://metadata.internal/latest/meta-data/")

    @mock.patch("apps.migration_cloud.intake.url_intake.socket.getaddrinfo")
    def test_blocks_loopback(self, gai):
        gai.return_value = self._addrinfo("127.0.0.1")
        with self.assertRaises(IntakeError):
            _assert_public_host("http://localhost/secret")

    @mock.patch("apps.migration_cloud.intake.url_intake.socket.getaddrinfo")
    def test_blocks_private_rfc1918(self, gai):
        gai.return_value = self._addrinfo("10.1.2.3")
        with self.assertRaises(IntakeError):
            _assert_public_host("http://intranet.example/export.csv")

    @mock.patch("apps.migration_cloud.intake.url_intake.socket.getaddrinfo")
    def test_allows_public_ip(self, gai):
        gai.return_value = self._addrinfo("93.184.216.34")
        # Should not raise.
        _assert_public_host("https://exports.example.edu/roster.csv")

    @mock.patch("apps.migration_cloud.intake.url_intake.mc_defaults.get", return_value=False)
    @mock.patch("apps.migration_cloud.intake.url_intake.socket.getaddrinfo")
    def test_opt_out_flag_allows_private(self, gai, _flag):
        gai.return_value = self._addrinfo("10.1.2.3")
        # Self-host opt-out: with block_private_network_fetch off, the guard
        # steps aside even for a private address.
        _assert_public_host("http://intranet.example/export.csv")

    @mock.patch("apps.migration_cloud.intake.url_intake.socket.getaddrinfo")
    def test_redirect_handler_revalidates_target(self, gai):
        gai.return_value = self._addrinfo("169.254.169.254")
        handler = _SSRFGuardedRedirectHandler()
        with self.assertRaises(IntakeError):
            handler.redirect_request(
                None, None, 302, "Found", {}, "http://169.254.169.254/latest/meta-data/"
            )
