from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import User
from apps.communication.api_views import (
    BroadcastAPI,
    CommunicationAnalyticsAPI,
    MessageViewSet,
)
from apps.communication.models import Announcement, Message
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import RegionConfig


class CommunicationApiTenantIsolationTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            slug="comm-api-school",
            subdomain="comm-api-school",
            name="Communication API School",
            default_region=self.region,
            timezone=self.region.timezone,
        )
        self.other_school = School.objects.create(
            slug="comm-api-other",
            subdomain="comm-api-other",
            name="Communication API Other",
            default_region=self.region,
            timezone=self.region.timezone,
        )

        self.admin = User.objects.create_user(
            username="comm_admin",
            password="pass12345",
            role=User.Role.ADMIN,
        )
        self.parent = User.objects.create_user(
            username="comm_parent",
            password="pass12345",
            role=User.Role.PARENT,
        )
        self.other_admin = User.objects.create_user(
            username="comm_other_admin",
            password="pass12345",
            role=User.Role.ADMIN,
        )
        self.other_parent = User.objects.create_user(
            username="comm_other_parent",
            password="pass12345",
            role=User.Role.PARENT,
        )

        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        SchoolMembership.objects.create(
            user=self.parent, school=self.school, role=User.Role.PARENT, is_primary=True
        )
        SchoolMembership.objects.create(
            user=self.other_admin,
            school=self.other_school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        SchoolMembership.objects.create(
            user=self.other_parent,
            school=self.other_school,
            role=User.Role.PARENT,
            is_primary=True,
        )

    def test_message_create_rejects_cross_tenant_recipient(self):
        view = MessageViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/api/communication/messages/",
            {
                "recipient": self.other_parent.pk,
                "subject": "Hello",
                "body": "Cross-tenant attempt",
            },
            format="json",
        )
        request.school = self.school
        force_authenticate(request, user=self.admin)

        response = view(request)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            Message.objects.filter(
                sender=self.admin,
                recipient=self.other_parent,
                subject="Hello",
            ).exists()
        )

    def test_broadcast_only_targets_current_school(self):
        view = BroadcastAPI.as_view()
        request = self.factory.post(
            "/api/communication/broadcast/",
            {
                "recipient_group": "all_parents",
                "subject": "Tenant Notice",
                "body": "Scoped broadcast",
            },
            format="json",
        )
        request.school = self.school
        force_authenticate(request, user=self.admin)

        response = view(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Message.objects.filter(school=self.school, recipient=self.parent).count(), 1
        )
        self.assertEqual(Message.objects.filter(recipient=self.other_parent).count(), 0)

    def test_analytics_only_counts_current_school_records(self):
        now = timezone.now()
        Message.objects.create(
            sender=self.admin,
            recipient=self.parent,
            school=self.school,
            subject="Scoped",
            body="Tenant-local",
            created_at=now - timedelta(days=1),
        )
        Message.objects.create(
            sender=self.other_admin,
            recipient=self.other_parent,
            school=self.other_school,
            subject="Other",
            body="Other tenant",
            created_at=now - timedelta(days=1),
        )
        Announcement.objects.create(
            school=self.school,
            title="School A",
            content="Tenant A",
            audience="all",
            created_by=self.admin,
            status=Announcement.Status.PUBLISHED,
            expiry_date=now + timedelta(days=5),
        )
        Announcement.objects.create(
            school=self.other_school,
            title="School B",
            content="Tenant B",
            audience="all",
            created_by=self.other_admin,
            status=Announcement.Status.PUBLISHED,
            expiry_date=now + timedelta(days=5),
        )

        view = CommunicationAnalyticsAPI.as_view()
        request = self.factory.get("/api/communication/analytics/")
        request.school = self.school
        force_authenticate(request, user=self.admin)

        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_messages"], 1)
        self.assertEqual(response.data["active_announcements"], 1)
