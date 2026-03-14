from datetime import date
from unittest.mock import patch

from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.people.models import StudentProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.siteconfig.models import ReportCardStyle, ReportCardStyleAssignment


class ReportCardBuilderViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="builder_admin",
            email="builder@example.com",
            password="testpass123",
        )
        self.client.force_login(self.user)
        self.url = reverse("siteconfig:reportcard_builder")

        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )
        self.department = Department.objects.create(name="Science", code="SCI")
        self.specialty = Specialty.objects.create(department=self.department, name="General", code="GEN")
        self.classroom_a = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 1A",
            code="F1A",
        )
        self.classroom_b = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 1B",
            code="F1B",
        )
        self.style = ReportCardStyle.objects.create(
            slug="compact-cameroon",
            name="Compact Cameroon",
            description="Compact preset",
            term_template="reports/term_report_cameroon_modern.html",
            annual_template="reports/annual_report_cameroon_modern.html",
            primary_color="#123456",
            accent_color="#abcdef",
            is_active=True,
        )
        ReportCardStyleAssignment.objects.create(classroom=self.classroom_a, style=self.style)
        StudentProfile.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            student_code="STU-BUILD-1",
            academic_year=self.year,
            classroom=self.classroom_a,
            specialty=self.specialty,
            is_active=True,
        )
        site = get_platform_site_settings_record(create=True)
        site.default_term_report_style = self.style
        site.default_annual_report_style = self.style
        site.save(update_fields=["default_term_report_style", "default_annual_report_style"])

    def test_builder_page_places_workflow_with_catalog_and_assignments(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "builder-status-strip")
        self.assertContains(response, "report-builder-workflow")
        self.assertContains(response, "builder-live-style-badge")
        self.assertContains(response, "builder-draft-state")
        self.assertContains(response, "builderStyleFilter")
        self.assertContains(response, "builderStyleFilterEmpty")
        self.assertContains(response, "Assigned")
        self.assertContains(response, "builderStylesList")
        self.assertContains(response, "live-report-preview")
        self.assertContains(response, "reportPreviewFallback")
        self.assertContains(response, "reportPreviewRetryButton")
        self.assertEqual(response.context["total_classroom_count"], 2)
        self.assertEqual(response.context["assigned_classroom_count"], 1)
        self.assertEqual(response.context["unassigned_classroom_count"], 1)

    def test_live_preview_script_tracks_html_and_pdf_urls_separately(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "latestPreviewUrl")
        self.assertContains(response, "latestPdfUrl")
        self.assertContains(response, "latestPreviewToken")
        self.assertContains(response, "preview_token=")
        self.assertContains(response, 'window.addEventListener("message"')
        self.assertContains(response, "reportcard-preview-ready")
        self.assertContains(response, "/siteconfig/reports/embed-preview/")
        self.assertContains(response, "frame.src = latestPreviewUrl")
        self.assertContains(response, "fallbackOpenTab.href = latestPdfUrl")

    def test_builder_can_create_style_from_workflow_form(self):
        response = self.client.post(
            self.url,
            data={
                "form_type": "style",
                "style-name": "Academic Authority",
                "style-slug": "academic-authority-custom",
                "style-description": "Professional admin style",
                "style-term_template": "reports/term_report_cameroon.html",
                "style-annual_template": "reports/annual_report_cameroon.html",
                "style-primary_color": "#0d173b",
                "style-accent_color": "#007bff",
                "style-watermark_text": "GTHS",
                "style-watermark_mode": "SITE_LOGO",
                "style-watermark_opacity": "0.12",
                "style-watermark_scale": "68",
                "style-watermark_position": "TOP_RIGHT",
                "style-header_tagline": "Knowledge Technology Excellence",
                "style-css_snippet": "",
                "style-labels": "{}",
                "style-layout_config": "{}",
                "style-is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.url)
        created = ReportCardStyle.objects.get(slug="academic-authority-custom")
        self.assertEqual(created.watermark_mode, "SITE_LOGO")
        self.assertEqual(created.watermark_position, "TOP_RIGHT")

    def test_builder_keeps_assignment_workflow_open_on_assignment_form_error(self):
        response = self.client.post(
            self.url,
            data={
                "form_type": "assignment",
                "assign-style": str(self.style.id),
                # No classrooms selected -> invalid assignment form.
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="workflow-assignment" class="accordion-collapse collapse show"')
        self.assertContains(response, 'id="workflow-style" class="accordion-collapse collapse"')

    def test_builder_keeps_default_mapping_workflow_open_on_selection_form_error(self):
        response = self.client.post(
            self.url,
            data={
                "form_type": "selection",
                "selection-default_term_report_style": "999999",
                "selection-default_annual_report_style": str(self.style.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="workflow-defaults" class="accordion-collapse collapse show"')
        self.assertContains(response, 'id="workflow-style" class="accordion-collapse collapse"')

    def test_live_preview_html_endpoint_allows_same_origin_iframe(self):
        response = self.client.get(
            reverse("siteconfig:reportcard_style_preview", args=[self.style.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertContains(response, "Text watermark")

    def test_live_preview_iframe_endpoint_allows_same_origin(self):
        response = self.client.get(
            reverse("siteconfig:reportcard_style_live_preview", args=[self.style.slug, "term"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertContains(response, "cameroon-letterhead")

    def test_embed_preview_endpoint_uses_csp_self_without_xfo_header(self):
        response = self.client.get(
            reverse("siteconfig:reportcard_style_embed_preview", args=[self.style.slug, "term"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("X-Frame-Options"))
        self.assertIn("frame-ancestors 'self'", response.headers.get("Content-Security-Policy", ""))
        self.assertContains(response, "cameroon-letterhead")

    def test_embed_preview_endpoint_injects_ready_signal_with_preview_token(self):
        response = self.client.get(
            reverse("siteconfig:reportcard_style_embed_preview", args=[self.style.slug, "term"]),
            {"preview_token": "abc123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "reportcard-preview-ready")
        self.assertContains(response, "abc123")

    def test_live_preview_pdf_endpoint_allows_same_origin_iframe(self):
        with patch("apps.siteconfig.views.render_pdf") as mocked_render_pdf:
            mocked_render_pdf.return_value = HttpResponse(
                b"%PDF-1.4 mock",
                content_type="application/pdf",
            )
            response = self.client.get(
                reverse("siteconfig:reportcard_style_pdf", args=[self.style.slug, "term"])
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")
