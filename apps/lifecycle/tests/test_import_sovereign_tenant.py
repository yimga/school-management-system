"""import_sovereign_tenant — end-to-end edge migration must recreate the tenant.

Written to FAIL before the command exists (call_command raises "Unknown command").
After it lands, the command must, in one atomic RLS-safe pass: pin the School
parent to the bundle's UUID, load the tenant rows into the empty target, entitle,
create a loginable owner, activate, and self-verify.

The nonempty-guard test asserts the specific refusal MESSAGE (not just any
CommandError) so an absent command — whose "Unknown command" error is also a
CommandError — cannot make it pass falsely.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.academics.models import AcademicYear
from apps.lifecycle.tenant_portability import export_tenant_bundle
from apps.schools.models import School, SchoolMembership
from apps.schools.rls_context import rls_bypass

_OWNER = "owner@gilead.school.lan"
_PW = "Str0ngPass23xy"


class ImportSovereignTenantTests(TestCase):
    SLUG = "gilead-tech"

    def _fresh_source(self):
        """A source Gilead school (slug pinned) with one tenant row to carry over."""
        with rls_bypass():
            School.objects.filter(slug=self.SLUG).delete()
        sid = uuid.uuid4()
        school = School.objects.create(
            id=sid,
            name="Gilead Technical High School",
            slug=self.SLUG,
            subdomain=self.SLUG,
            is_active=True,
            is_approved=True,
            country_code="CM",
            settings={},
        )
        AcademicYear.objects.create(
            school=school, name="2025/2026", starts_on="2025-09-01", ends_on="2026-07-31"
        )
        return school, sid

    def _export_to_file(self, school, tmpdir):
        blob = export_tenant_bundle(school)
        # The envelope must carry the source school id — that's the pin UUID.
        self.assertEqual(str(json.loads(blob)["school_id"]), str(school.id))
        path = os.path.join(tmpdir, "gilead.rmcbundle")
        with open(path, "wb") as fh:
            fh.write(blob)
        return path

    def test_end_to_end_migration_recreates_school_owner_and_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, sid = self._fresh_source()
            bundle = self._export_to_file(source, tmp)

            # Simulate a fresh box: remove the source school + its tenant rows.
            with rls_bypass():
                AcademicYear.objects.filter(school_id=sid).delete()
                School.objects.filter(id=sid).delete()
            self.assertFalse(School.objects.filter(id=sid).exists())

            call_command(
                "import_sovereign_tenant",
                in_path=bundle,
                owner_email=_OWNER,
                slug=self.SLUG,
                country="CM",
                password=_PW,
                no_offline=True,
            )

            # (1) School parent recreated at the EXACT bundle UUID, active.
            school = School.objects.get(id=sid)
            self.assertTrue(school.is_active)
            self.assertEqual(school.slug, self.SLUG)

            # (2) Tenant data restored, pk-preserving.
            self.assertTrue(
                AcademicYear.objects.filter(school_id=sid, name="2025/2026").exists()
            )

            # (3) Owner + membership created on the box (both excluded from bundle).
            membership = SchoolMembership.objects.filter(
                school=school, is_school_owner=True, is_primary=True
            ).first()
            self.assertIsNotNone(membership)
            owner = membership.user
            self.assertTrue(
                authenticate(username=_OWNER, password=_PW) is not None
                or authenticate(username=owner.username, password=_PW) is not None
            )

            # (4) Entitled to the sovereign plan.
            school.refresh_from_db()
            self.assertEqual(getattr(school, "billing_type", ""), "COMPLIMENTARY")

    def test_refuses_nonempty_target_without_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, sid = self._fresh_source()  # target stays present + non-empty
            bundle = self._export_to_file(source, tmp)
            # Do NOT delete — the target (id=sid) already holds an AcademicYear, so a
            # pk-preserving import would risk collisions and must be refused.
            with self.assertRaisesMessage(CommandError, "allow-nonempty"):
                call_command(
                    "import_sovereign_tenant",
                    in_path=bundle,
                    owner_email=_OWNER,
                    slug=self.SLUG,
                    no_offline=True,
                )
