"""Tier 0 A-Z upgrade wave (2026-08-08): convert built-but-not-wired backends
into reachable value.

  * Rollback surfacing — `_rollback_runs_for_bundle` associates the school-scoped
    MigrationRuns to a bundle via the stamped `execution_summary["bundle_id"]`,
    filtered to those that can still be rolled back, so the bundle detail page can
    render a per-run "Roll back" button wired to the existing IDOR-safe endpoint.
  * One-click Fix-All — the conflicts POST gained an `action:"fix_all"` batch that
    resolves every pending conflict for the (tenant-scoped) bundle at once.
  * SFTP SSRF parity — `_fetch_sftp` now runs the same `_assert_public_host` guard
    as `_fetch_http`.

Each test fails against the pre-Tier-0 code.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.automation.models import MigrationRun
from apps.migration_cloud.intake.base import IntakeError
from apps.migration_cloud.intake.url_intake import _fetch_sftp
from apps.migration_cloud.models import (
    BundleStatus,
    ConflictResolution,
    IntakeMethod,
    MigrationBundle,
    MigrationConflict,
)
from apps.migration_cloud.views import (
    MigrationCloudConflictsView,
    _rollback_runs_for_bundle,
)
from apps.schools.models import School


def _school(slug: str) -> School:
    return School.objects.create(name=slug, slug=slug, subdomain=slug, is_active=True)


def _bundle(school: School, key: str, status: str = BundleStatus.APPLIED) -> MigrationBundle:
    return MigrationBundle.objects.create(
        label=key,
        intake_method=IntakeMethod.FILE_UPLOAD,
        idempotency_key=key,
        status=status,
        school=school,
    )


def _run(school: School, bundle_pk: int, **over) -> MigrationRun:
    defaults = dict(
        school=school,
        migration_type="students:roster.csv",
        dry_run=False,
        status=MigrationRun.Status.SUCCESS,
        execution_summary={"bundle_id": bundle_pk},
        rollback_snapshot={"created_ids": [1, 2, 3]},
    )
    defaults.update(over)
    return MigrationRun.objects.create(**defaults)


class RollbackRunSurfacingTests(TestCase):
    def setUp(self):
        self.school = _school("rb-a")
        self.bundle = _bundle(self.school, "rb-bundle")

    def test_applied_bundle_surfaces_rollbackable_run(self):
        run = _run(self.school, self.bundle.pk)
        runs = _rollback_runs_for_bundle(self.bundle)
        self.assertEqual([r.pk for r in runs], [run.pk])

    def test_other_bundle_run_not_surfaced(self):
        other = _bundle(self.school, "rb-other")
        _run(self.school, other.pk)  # stamped with a DIFFERENT bundle_id
        self.assertEqual(_rollback_runs_for_bundle(self.bundle), [])

    def test_already_rolled_back_run_excluded(self):
        anchor = _run(self.school, self.bundle.pk)
        _run(
            self.school,
            self.bundle.pk,
            rolled_back_by_run=anchor,
            rollback_snapshot={"created_ids": [9]},
        )
        runs = _rollback_runs_for_bundle(self.bundle)
        self.assertEqual([r.pk for r in runs], [anchor.pk])

    def test_non_applied_bundle_has_no_rollback_surface(self):
        mapped = _bundle(self.school, "rb-mapped", status=BundleStatus.MAPPED)
        _run(self.school, mapped.pk)
        self.assertEqual(_rollback_runs_for_bundle(mapped), [])


class FixAllConflictTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school_a = _school("fa-a")
        self.school_b = _school("fa-b")
        self.user = User.objects.create_user(username="fa_user", password="x")
        self.bundle_a = _bundle(self.school_a, "fa-bundle-a")
        self.bundle_b = _bundle(self.school_b, "fa-bundle-b")
        for i in range(3):
            MigrationConflict.objects.create(
                bundle=self.bundle_a,
                domain="students",
                canonical_model="apps.people.StudentProfile",
                canonical_pk=str(i),
            )
        MigrationConflict.objects.create(
            bundle=self.bundle_b,
            domain="students",
            canonical_model="apps.people.StudentProfile",
            canonical_pk="99",
        )

    def _post(self, bundle_id, body, shell="portal", school=None):
        request = self.rf.post(
            f"/migration/{bundle_id}/conflicts/",
            data=json.dumps(body),
            content_type="application/json",
        )
        request.user = self.user
        if school is not None:
            request.school = school
        return MigrationCloudConflictsView.as_view()(
            request, bundle_id=bundle_id, shell=shell
        )

    def test_fix_all_resolves_every_pending_conflict(self):
        resp = self._post(
            self.bundle_a.pk,
            {"action": "fix_all", "resolution": "OVERWRITE"},
            school=self.school_a,
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertEqual(data["resolved_count"], 3)
        self.assertFalse(
            self.bundle_a.conflicts.filter(resolution=ConflictResolution.PENDING).exists()
        )

    def test_fix_all_does_not_touch_other_tenant(self):
        self._post(
            self.bundle_a.pk,
            {"action": "fix_all", "resolution": "OVERWRITE"},
            school=self.school_a,
        )
        self.assertTrue(
            self.bundle_b.conflicts.filter(resolution=ConflictResolution.PENDING).exists()
        )

    def test_fix_all_on_foreign_bundle_is_404(self):
        resp = self._post(
            self.bundle_b.pk,
            {"action": "fix_all", "resolution": "OVERWRITE"},
            school=self.school_a,
        )
        self.assertEqual(resp.status_code, 404)

    def test_fix_all_rejects_invalid_resolution(self):
        resp = self._post(
            self.bundle_a.pk,
            {"action": "fix_all", "resolution": "NOPE"},
            school=self.school_a,
        )
        self.assertEqual(resp.status_code, 400)

    def test_single_resolve_still_works(self):
        conflict = self.bundle_a.conflicts.first()
        resp = self._post(
            self.bundle_a.pk,
            {"conflict_id": conflict.pk, "resolution": "PRESERVE"},
            school=self.school_a,
        )
        self.assertEqual(resp.status_code, 200)
        conflict.refresh_from_db()
        self.assertEqual(conflict.resolution, ConflictResolution.PRESERVE)


class ConflictPIIMaskingTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school = _school("pii-a")
        self.bundle = _bundle(self.school, "pii-bundle")
        MigrationConflict.objects.create(
            bundle=self.bundle,
            domain="students",
            canonical_model="apps.people.StudentProfile",
            canonical_pk="1",
            existing_values={"ssn": "123-45-6789", "first_name": "Ada", "email": "ada@example.org"},
            incoming_values={"ssn": "987-65-4321", "first_name": "Ada"},
        )

    def _get_json(self, user, shell="portal"):
        request = self.rf.get(f"/migration/{self.bundle.pk}/conflicts/?format=json")
        request.user = user
        request.school = self.school
        return MigrationCloudConflictsView.as_view()(
            request, bundle_id=self.bundle.pk, shell=shell
        )

    def test_non_superuser_sees_masked_pii(self):
        viewer = User.objects.create_user(username="pii_viewer", password="x")
        resp = self._get_json(viewer)
        body = resp.content.decode()
        self.assertNotIn("123-45-6789", body)
        self.assertNotIn("ada@example.org", body)
        ev = json.loads(body)["pending"][0]["existing_values"]
        self.assertNotEqual(ev.get("ssn"), "123-45-6789")
        self.assertEqual(ev.get("first_name"), "Ada")  # non-PII preserved

    def test_superuser_sees_raw_pii(self):
        su = User.objects.create_user(
            username="pii_super", password="x", is_superuser=True, is_staff=True
        )
        resp = self._get_json(su, shell="super")
        ev = json.loads(resp.content.decode())["pending"][0]["existing_values"]
        self.assertEqual(ev.get("ssn"), "123-45-6789")


class SftpSSRFParityTests(TestCase):
    @mock.patch("apps.migration_cloud.intake.net_guard.socket.getaddrinfo")
    def test_sftp_blocks_private_host(self, gai):
        gai.return_value = [(2, 1, 6, "", ("10.0.0.5", 0))]
        with self.assertRaises(IntakeError):
            _fetch_sftp("sftp://intranet.local/export.csv", Path("/tmp/x"), 1000)
