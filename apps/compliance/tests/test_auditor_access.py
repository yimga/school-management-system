"""Wave E — auditor magic-link: time-bounded, PII-masked, access-logged grant."""

from __future__ import annotations

import uuid

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department
from apps.compliance import auditor_access
from apps.compliance.models import AuditorAccessGrant, AuditorAccessLog
from apps.compliance.pii_masking import mask_student_for_auditor
from apps.people.models import StudentProfile
from apps.schools.models import School


class AuditorAccessTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"AUD {uid}", slug=f"aud-{uid}", subdomain=f"aud{uid}", is_active=True
        )
        year = AcademicYear.objects.create(
            name="Y1", start_date="2025-01-01", end_date="2025-12-31", school=self.school
        )
        dept = Department.objects.create(name="D", code=f"D{uid}", school=self.school)
        classroom = Classroom.objects.create(
            academic_year=year, department=dept, name="Grade 5", code=f"C{uid}", school=self.school
        )
        self.student = StudentProfile.objects.create(
            first_name="Amara",
            last_name="Okoro",
            date_of_birth="2014-03-09",
            student_code=f"ST{uid}",
            parent_phone="+250788000111",
            school=self.school,
            classroom=classroom,
        )

    def test_masking_hides_pii(self):
        masked = mask_student_for_auditor(self.student)
        self.assertEqual(masked["initials"], "A.O.")
        self.assertEqual(masked["birth_year"], 2014)  # year only, no day/month
        self.assertEqual(masked["class"], "Grade 5")
        self.assertEqual(masked["guardian_contact"], "withheld")
        # full name + phone must not leak anywhere in the projection
        blob = str(masked)
        self.assertNotIn("Amara", blob)
        self.assertNotIn("Okoro", blob)
        self.assertNotIn("788000111", blob)

    def test_create_resolve_and_log(self):
        grant, token = auditor_access.create_grant(
            school_id=self.school.id, inspector_label="Ofsted Lead", ttl_hours=48
        )
        self.assertTrue(grant.is_valid())
        resolved = auditor_access.resolve_grant(token)
        self.assertEqual(resolved.id, grant.id)
        auditor_access.log_access(resolved, resource="auditor:roster", ip_address="10.0.0.5")
        self.assertEqual(AuditorAccessLog.objects.filter(grant=grant).count(), 1)
        roster = auditor_access.masked_roster_for_grant(grant)
        self.assertEqual(len(roster), 1)
        self.assertEqual(roster[0]["initials"], "A.O.")

    def test_bad_token_rejected(self):
        self.assertIsNone(auditor_access.resolve_grant("not-a-real-token"))
        self.assertIsNone(auditor_access.resolve_grant(""))

    def test_revoke_invalidates_token(self):
        grant, token = auditor_access.create_grant(school_id=self.school.id)
        self.assertIsNotNone(auditor_access.resolve_grant(token))
        self.assertTrue(auditor_access.revoke_grant(grant.id))
        self.assertIsNone(auditor_access.resolve_grant(token))  # revoked -> no access
        self.assertFalse(auditor_access.revoke_grant(grant.id))  # already revoked

    def test_expired_grant_rejected(self):
        grant, token = auditor_access.create_grant(school_id=self.school.id, ttl_hours=1)
        # force expiry
        grant.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        grant.save(update_fields=["expires_at"])
        self.assertFalse(grant.is_valid())
        self.assertIsNone(auditor_access.resolve_grant(token))


class AuditorInspectViewTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"AUDV {uid}", slug=f"audv-{uid}", subdomain=f"audv{uid}", is_active=True
        )

    def test_public_inspect_endpoint(self):
        from apps.compliance.views_auditor import auditor_inspect
        from django.test import RequestFactory

        grant, token = auditor_access.create_grant(
            school_id=self.school.id, inspector_label="State Inspector"
        )
        rf = RequestFactory()
        resp = auditor_inspect(rf.get(f"/compliance/auditor/inspect/?token={token}"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AuditorAccessLog.objects.filter(grant=grant).count(), 1)
        bad = auditor_inspect(rf.get("/compliance/auditor/inspect/?token=bogus"))
        self.assertEqual(bad.status_code, 403)


class AuditorGeoFenceTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"AUDG {uid}", slug=f"audg-{uid}", subdomain=f"audg{uid}", is_active=True
        )

    def test_normalize_allowlist_accepts_ip_and_cidr_drops_garbage(self):
        out = auditor_access.normalize_ip_allowlist(
            ["203.0.113.5", "198.51.100.0/24", "not-an-ip", "  ", "203.0.113.5"]
        )
        # bare host -> /32, CIDR preserved, garbage dropped, dedup
        self.assertEqual(out, ["203.0.113.5/32", "198.51.100.0/24"])

    def test_normalize_allowlist_parses_comma_or_newline_string(self):
        out = auditor_access.normalize_ip_allowlist("203.0.113.5, 10.0.0.0/8\n2001:db8::1")
        self.assertIn("203.0.113.5/32", out)
        self.assertIn("10.0.0.0/8", out)
        self.assertIn("2001:db8::1/128", out)

    def test_empty_allowlist_allows_any_ip(self):
        grant, _ = auditor_access.create_grant(school_id=self.school.id)
        self.assertTrue(auditor_access.ip_is_allowed(grant, "8.8.8.8"))
        self.assertTrue(auditor_access.ip_is_allowed(grant, None))

    def test_allowlist_matches_inside_cidr_and_rejects_outside(self):
        grant, _ = auditor_access.create_grant(
            school_id=self.school.id, ip_allowlist=["198.51.100.0/24"]
        )
        self.assertTrue(auditor_access.ip_is_allowed(grant, "198.51.100.77"))
        self.assertFalse(auditor_access.ip_is_allowed(grant, "203.0.113.9"))

    def test_geofenced_grant_fails_closed_on_missing_ip(self):
        grant, _ = auditor_access.create_grant(
            school_id=self.school.id, ip_allowlist=["198.51.100.7"]
        )
        # geo-fenced grant + unplaceable client -> deny
        self.assertFalse(auditor_access.ip_is_allowed(grant, None))
        self.assertFalse(auditor_access.ip_is_allowed(grant, "garbage"))

    def test_view_denies_offnet_ip_and_logs_denial(self):
        from apps.compliance.views_auditor import auditor_inspect
        from django.test import RequestFactory

        grant, token = auditor_access.create_grant(
            school_id=self.school.id, ip_allowlist=["198.51.100.0/24"]
        )
        rf = RequestFactory()
        # off-net -> 403, denial logged, roster NOT served
        denied = auditor_inspect(
            rf.get(f"/c/auditor/?token={token}", REMOTE_ADDR="203.0.113.9")
        )
        self.assertEqual(denied.status_code, 403)
        log = AuditorAccessLog.objects.get(grant=grant)
        self.assertFalse(log.allowed)
        self.assertEqual(log.denied_reason, "ip-not-in-allowlist")

        # on-net (via X-Forwarded-For) -> 200, allowed access logged
        ok = auditor_inspect(
            rf.get(f"/c/auditor/?token={token}", HTTP_X_FORWARDED_FOR="198.51.100.42")
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(AuditorAccessLog.objects.filter(grant=grant, allowed=True).count(), 1)
