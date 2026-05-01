"""North Star SLICE 5 — compliance export engine (downloads only)."""

from datetime import date
import uuid

from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission as FeaturePermission, User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty, Term
from apps.reports import compliance_exports as cx
from apps.reports.models import ReportCard
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership

_HOST = "ns5cex.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=[
        "testserver",
        "127.0.0.1",
        "localhost",
        _HOST,
    ]
)
class ComplianceExportsSlice5Tests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        cls.school = School.objects.create(
            name="Compliance Export School",
            slug="ns5cex",
            subdomain="ns5cex",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025-2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        cls.term = Term.objects.create(
            school=cls.school,
            academic_year=cls.year,
            name="T1",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            position=1,
            is_active=True,
        )
        dept = Department.objects.create(
            school=cls.school,
            name="Core",
            code=f"CXNS-{uuid.uuid4().hex[:8]}",
        )
        sp = Specialty.objects.create(department=dept, name="General", code="GN")
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=dept,
            name="Form 5",
            code="F5",
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school,
            first_name="Ada",
            last_name="Student",
            student_code="CX-ADA-1",
            academic_year=cls.year,
            classroom=cls.classroom,
            specialty=sp,
            date_of_birth=date(2012, 1, 15),
            is_active=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_HOST)

    def _perm_user(self, *, is_superuser=False, username=None):
        u = User.objects.create_user(
            username=username or f"co_{uuid.uuid4().hex[:10]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=is_superuser,
        )
        u.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.get_or_create(
            user=u,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        return u

    def test_all_three_export_keys_in_registry(self):
        keys = list(cx.ALL_EXPORT_KEYS)
        self.assertEqual(len(keys), 3)
        for k in (
            cx.EXPORT_WAEC,
            cx.EXPORT_OFSTED,
            cx.EXPORT_MINISTRY,
        ):
            self.assertIn(k, keys)

    def test_requirements_structure(self):
        req = cx.get_compliance_export_requirements(cx.EXPORT_WAEC, self.school)
        self.assertEqual(req["export_key"], cx.EXPORT_WAEC)
        self.assertIn("student_count_active", req)
        self.assertIn("academic_year_label", req)

    def test_operator_page_renders_authorized_markers_and_links(self):
        u = self._perm_user()
        self.client.force_login(u)
        url = reverse("siteconfig:compliance_exports", urlconf="config.tenant_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:800])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-cp-evidence-surface="compliance-exports"', body)
        self.assertIn('data-rmc-compliance-exports="1"', body)
        self.assertIn("/siteconfig/reports/report-templates-catalog/", body)
        self.assertIn("/siteconfig/reports/output-history-evidence/", body)

    @patch(
        "apps.siteconfig.views_compliance_exports.cx.list_compliance_export_families",
        return_value=[],
    )
    def test_empty_export_families_guided_recovery_single_block(self, _mock):
        u = self._perm_user()
        self.client.force_login(u)
        url = reverse("siteconfig:compliance_exports", urlconf="config.tenant_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertEqual(body.count('data-rmc-guided-recovery="1"'), 1)
        self.assertIn("No export bundles available", body)
        self.assertIn("Try again", body)

    def test_no_membership_forbidden_even_with_manage_permission(self):
        u = User.objects.create_user(
            username=f"nm_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        self.client.force_login(u)
        url = reverse("siteconfig:compliance_exports", urlconf="config.tenant_urls")
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_teacher_without_feature_forbidden(self):
        u = User.objects.create_user(
            username=f"t_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=u,
            school=self.school,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        self.client.force_login(u)
        url = reverse("siteconfig:compliance_exports", urlconf="config.tenant_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_missing_report_cards_blocks_waec_and_ministry(self):
        # student exists but no ReportCard rows
        m = cx.get_compliance_export_missing_data(
            cx.EXPORT_WAEC, self.school, {}
        )
        self.assertTrue(m)
        m2 = cx.get_compliance_export_missing_data(
            cx.EXPORT_MINISTRY, self.school, {}
        )
        self.assertTrue(m2)

    def test_download_waec_blocked_redirects_with_message(self):
        u = self._perm_user()
        self.client.force_login(u)
        path = reverse(
            "siteconfig:compliance_export_download",
            urlconf="config.tenant_urls",
            kwargs={"export_key": cx.EXPORT_WAEC},
        )
        resp = self.client.get(path, follow=False)
        self.assertEqual(resp.status_code, 302)

    def test_download_ofsted_succeeds_without_report_cards(self):
        u = self._perm_user()
        self.client.force_login(u)
        path = reverse(
            "siteconfig:compliance_export_download",
            urlconf="config.tenant_urls",
            kwargs={"export_key": cx.EXPORT_OFSTED},
        )
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0].strip(), "text/csv")
        self.assertIn("attachment", resp["Content-Disposition"])
        body = b"".join(resp.streaming_content) if hasattr(resp, "streaming_content") else resp.content
        self.assertIn(b"pupil_count_active", body)

    def test_download_waec_with_report_card_csv_details(self):
        ReportCard.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            student=self.student,
            type=ReportCard.Type.TERM,
        )
        u = self._perm_user()
        self.client.force_login(u)
        path = reverse(
            "siteconfig:compliance_export_download",
            urlconf="config.tenant_urls",
            kwargs={"export_key": cx.EXPORT_WAEC},
        )
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0].strip(), "text/csv")
        blob = resp.content
        self.assertIn(b"CX-ADA-1", blob)

    def test_no_external_submission_only_file_response(self):
        """Exports return CSV attachment only — no outbound ministry URLs."""
        u = self._perm_user()
        self.client.force_login(u)
        path = reverse(
            "siteconfig:compliance_export_download",
            urlconf="config.tenant_urls",
            kwargs={"export_key": cx.EXPORT_OFSTED},
        )
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Location", resp)

    def test_superuser_sees_admin_fallback_super_only(self):
        su = self._perm_user(is_superuser=True, username=f"su_{uuid.uuid4().hex[:6]}")
        self.client.force_login(su)
        url = reverse("siteconfig:compliance_exports", urlconf="config.tenant_urls")
        body = self.client.get(url).content.decode("utf-8", errors="replace")
        self.assertIn("data-rmc-compliance-admin-fallback", body)
        u2 = self._perm_user()
        self.client.force_login(u2)
        body2 = self.client.get(url).content.decode("utf-8", errors="replace")
        self.assertNotIn("data-rmc-compliance-admin-fallback", body2)

    def test_audit_log_row_on_successful_export(self):
        from apps.compliance.models_audit import AuditLog

        before = AuditLog.objects.count()
        u = self._perm_user()
        self.client.force_login(u)
        path = reverse(
            "siteconfig:compliance_export_download",
            urlconf="config.tenant_urls",
            kwargs={"export_key": cx.EXPORT_OFSTED},
        )
        self.client.get(path)
        self.assertGreater(AuditLog.objects.count(), before)

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_magic_ux_strict_wraps_secondary_links_in_more_actions(self):
        u = self._perm_user()
        self.client.force_login(u)
        url = reverse("siteconfig:compliance_exports", urlconf="config.tenant_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:600])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("rmc-conversion-more-actions", body)
        self.assertIn('data-task="compliance_export_hub"', body)
