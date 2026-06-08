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

    def test_inspect_html_default_renders_masked_roster(self):
        from apps.compliance.views_auditor import auditor_inspect
        from django.test import RequestFactory

        grant, token = auditor_access.create_grant(
            school_id=self.school.id, inspector_label="Ofsted Lead"
        )
        rf = RequestFactory()
        resp = auditor_inspect(rf.get(f"/c/auditor/?token={token}"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp["Content-Type"])
        body = resp.content.decode()
        self.assertIn("A.O.", body)  # masked initials render
        self.assertIn("2014", body)  # birth year only
        self.assertNotIn("Amara", body)  # full name never leaks
        self.assertNotIn("788000111", body)

    def test_inspect_json_when_format_param(self):
        import json as _json

        from apps.compliance.views_auditor import auditor_inspect
        from django.test import RequestFactory

        grant, token = auditor_access.create_grant(school_id=self.school.id)
        rf = RequestFactory()
        resp = auditor_inspect(rf.get(f"/c/auditor/?token={token}&format=json"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/json", resp["Content-Type"])
        data = _json.loads(resp.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["students"][0]["initials"], "A.O.")

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

    def test_bad_token_renders_html_denied_page(self):
        from apps.compliance.views_auditor import auditor_inspect
        from django.test import RequestFactory

        rf = RequestFactory()
        resp = auditor_inspect(rf.get("/c/auditor/?token=bogus"))
        self.assertEqual(resp.status_code, 403)
        self.assertIn("text/html", resp["Content-Type"])
        self.assertIn("Inspection unavailable", resp.content.decode())


class AuditorConsoleTests(TestCase):
    databases = {"default"}

    def setUp(self):
        from django.contrib.auth import get_user_model

        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"AUDC {uid}", slug=f"audc-{uid}", subdomain=f"audc{uid}", is_active=True
        )
        User = get_user_model()
        self.staff = User.objects.create_user(
            username=f"ops{uid}", email=f"ops{uid}@x.test", password="x", is_staff=True
        )

    def _staff_request(self, method, data=None):
        from django.contrib.sessions.backends.db import SessionStore
        from django.test import RequestFactory

        rf = RequestFactory()
        if method == "get":
            req = rf.get("/compliance/auditor/grants/", data or {})
        else:
            req = rf.post("/compliance/auditor/grants/", data or {})
        req.user = self.staff
        req.session = SessionStore()
        req.session.create()
        return req

    def test_console_create_via_form_redirects_and_stashes_link(self):
        from apps.compliance.models import AuditorAccessGrant
        from apps.compliance.views_auditor import AuditorGrantConsoleView

        req = self._staff_request(
            "post",
            {
                "action": "create",
                "school": str(self.school.id),
                "inspector_label": "State Inspector",
                "ttl_hours": "48",
                "ip_allowlist": "198.51.100.0/24, garbage",
            },
        )
        resp = AuditorGrantConsoleView.as_view()(req)
        self.assertEqual(resp.status_code, 302)  # PRG
        grant = AuditorAccessGrant.objects.get(school_id=self.school.id)
        self.assertEqual(grant.ip_allowlist, ["198.51.100.0/24"])  # garbage dropped
        stashed = req.session["auditor_fresh_grant"]
        self.assertEqual(stashed["grant_id"], str(grant.id))
        self.assertTrue(stashed["token"])

    def test_console_create_json_returns_token(self):
        import json as _json

        from apps.compliance.views_auditor import AuditorGrantConsoleView

        req = self._staff_request(
            "post",
            {"action": "create", "school": str(self.school.id), "format": "json"},
        )
        resp = AuditorGrantConsoleView.as_view()(req)
        self.assertEqual(resp.status_code, 200)
        data = _json.loads(resp.content)
        self.assertTrue(data["ok"])
        self.assertTrue(data["token"])

    def test_console_list_json_surfaces_allowlist_and_denied_counts(self):
        import json as _json

        from apps.compliance.views_auditor import AuditorGrantConsoleView

        grant, _ = auditor_access.create_grant(
            school_id=self.school.id, ip_allowlist=["198.51.100.7"]
        )
        auditor_access.log_access(
            grant, resource="auditor:roster", ip_address="203.0.113.1",
            allowed=False, denied_reason="ip-not-in-allowlist",
        )
        req = self._staff_request("get", {"format": "json"})
        resp = AuditorGrantConsoleView.as_view()(req)
        data = _json.loads(resp.content)
        row = next(r for r in data["grants"] if r["id"] == str(grant.id))
        self.assertEqual(row["ip_allowlist"], ["198.51.100.7/32"])  # canonical host net
        self.assertEqual(row["denied_views"], 1)

    def test_console_get_renders_html_with_geofence_field(self):
        from apps.compliance.views_auditor import AuditorGrantConsoleView

        req = self._staff_request("get")
        resp = AuditorGrantConsoleView.as_view()(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('name="ip_allowlist"', body)  # geo-fence field is wired in
        self.assertIn("Geo-fence", body)

    def test_console_revoke_via_form_redirects(self):
        from apps.compliance.views_auditor import AuditorGrantConsoleView

        grant, _ = auditor_access.create_grant(school_id=self.school.id)
        req = self._staff_request(
            "post", {"action": "revoke", "grant_id": str(grant.id)}
        )
        resp = AuditorGrantConsoleView.as_view()(req)
        self.assertEqual(resp.status_code, 302)
        grant.refresh_from_db()
        self.assertTrue(grant.is_revoked)


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
