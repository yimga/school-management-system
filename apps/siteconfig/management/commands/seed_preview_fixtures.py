from __future__ import annotations


from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.compliance.models import LegalDocument
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.portal.models import PortalFeatureItem
from apps.portal.portal_models import PortalAuditLog, PortalSession
from apps.siteconfig.models import RegionConfig
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Seed preview fixtures for documents, widgets, sessions, and site settings."

    def handle(self, *args, **options):
        admin_user = self._get_admin_user()
        region = RegionConfig.get_default()

        site = get_platform_site_settings_record(create=True)
        if site is None:
            raise RuntimeError("Site settings baseline could not be initialized")
        site.portal_recent_grades = [
            {"label": "Physics", "grade": "A (95%)", "tone": "success", "roles": ["PARENT"], "enabled": True},
            {"label": "Mathematics", "grade": "A- (89%)", "tone": "primary", "roles": ["PARENT"], "enabled": True},
            {"label": "Literature", "grade": "B+ (86%)", "tone": "warning", "roles": ["PARENT"], "enabled": True},
        ]
        site.portal_upcoming_assessments = [
            {"title": "Chemistry Test", "when": "Tomorrow 8AM", "detail": "Organic unit 3", "tone": "info", "roles": ["PARENT"], "enabled": True},
            {"title": "History Essay", "when": "Fri 2PM", "detail": "African Independence", "tone": "secondary", "roles": ["PARENT"], "enabled": True},
        ]
        site.portal_announcements = [
            {"title": "Midterm Grades Published", "meta": "Moments ago", "roles": ["PARENT"], "enabled": True},
            {"title": "New WhatsApp Support Line", "meta": "2 days ago", "roles": ["PARENT"], "enabled": True},
        ]
        site.portal_quick_actions = [
            {"label": "Message Teacher", "url": "#contact-teacher", "icon": "bi-chat-dots", "roles": ["PARENT"], "enabled": True},
            {"label": "Access Report Card", "url": "#report-card", "icon": "bi-file-earmark-text", "roles": ["PARENT"], "enabled": True},
            {"label": "Book Counseling", "url": "#counseling", "icon": "bi-calendar-event", "roles": ["PARENT"], "enabled": True},
        ]
        site.footer_badges = [
            {"label": "Live Chat Ready", "tone": "secure"},
            {"label": "2026 Compliance", "tone": "compliant"},
        ]
        site.save()

        feature_items = [
            {
                "feature": PortalFeatureItem.Feature.DOCUMENTS,
                "title": "Student Handbook",
                "description": "View and download policy documents before sharing with parents.",
                "link": "https://example.com/handbook",
            },
            {
                "feature": PortalFeatureItem.Feature.SYLLABUS,
                "title": "Weekly Syllabus Update",
                "description": "Synthetic lessons preview with compliance notes.",
                "link": "https://example.com/syllabus",
            },
            {
                "feature": PortalFeatureItem.Feature.MESSAGING,
                "title": "Message Teacher",
                "description": "Draft a preview notice for parents before sending.",
                "link": "https://example.com/messaging",
            },
        ]

        for entry in feature_items:
            PortalFeatureItem.objects.update_or_create(
                feature=entry["feature"],
                title=entry["title"],
                defaults={
                    "description": entry["description"],
                    "link": entry["link"],
                    "is_active": True,
                    "created_by": admin_user,
                },
            )

        LegalDocument.objects.update_or_create(
            region=region,
            document_type="privacy_policy",
            language="en",
            version=1,
            defaults={
                "title": "Privacy Policy (Preview)",
                "content": "<p>Sample privacy policy used in the AI preview.</p>",
                "effective_date": timezone.now().date(),
                "created_by": admin_user,
            },
        )

        PortalSession.objects.update_or_create(
            session_token="preview-session-token",
            defaults={
                "parent_id": 1,
                "ip_address": "127.0.0.1",
                "user_agent": "Preview Agent",
                "device_type": "desktop",
            },
        )

        PortalAuditLog.objects.update_or_create(
            parent_id=1,
            action=PortalAuditLog.ACTION_TYPES[0][0],
            defaults={
                "description": "Preview AI session",
                "ip_address": "127.0.0.1",
                "user_agent": "Preview Agent",
                "details": {"preview": True},
            },
        )

        self.stdout.write(self.style.SUCCESS("Preview fixtures seeded."))

    def _get_admin_user(self):
        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).first()
        if admin:
            return admin
        return User.objects.create_superuser("preview-admin", "preview@example.com", "Preview123!")
