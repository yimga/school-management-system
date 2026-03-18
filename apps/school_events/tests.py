import os
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.school_events.models import (
    EventRegistration,
    EventTicketTier,
    EventVenue,
    SchoolEvent,
)
from apps.school_events.services import upcoming_public_events_for_school
from apps.schools.models import School


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class SchoolEventsTests(TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        self.user = User.objects.create_user(
            username="events-user",
            email="events-user@example.com",
            password="pass1234",
        )
        self.school = School.objects.create(
            name="Riverfront Academy",
            slug="riverfront-academy",
            subdomain="riverfront-academy",
            is_active=True,
        )
        self.other_school = School.objects.create(
            name="Other Academy",
            slug="other-academy",
            subdomain="other-academy",
            is_active=True,
        )
        self.venue = EventVenue.objects.create(
            school=self.school,
            name="Main Hall",
            code="main-hall",
            location="Campus West",
            capacity=500,
        )
        self.event = SchoolEvent.objects.create(
            school=self.school,
            title="Founders Gala",
            slug="founders-gala",
            status=SchoolEvent.Status.PUBLISHED,
            summary="Annual fundraising and awards night.",
            description="Gala dinner with student showcases.",
            venue=self.venue,
            organizer_name="Advancement Office",
            start_at=timezone.now() + timedelta(days=5),
            end_at=timezone.now() + timedelta(days=5, hours=3),
            is_public=True,
            ticketing_enabled=True,
            sponsorship_enabled=True,
        )
        self.tier = EventTicketTier.objects.create(
            event=self.event,
            name="General Admission",
            code="general",
            price=Decimal("25.00"),
            capacity=200,
            sold_quantity=0,
        )
        SchoolEvent.objects.create(
            school=self.other_school,
            title="Other School Showcase",
            slug="other-school-showcase",
            status=SchoolEvent.Status.PUBLISHED,
            organizer_name="Other School",
            start_at=timezone.now() + timedelta(days=7),
            is_public=True,
        )

    def tearDown(self):
        self.env.stop()

    def test_upcoming_public_events_service_scopes_to_school(self):
        rows = upcoming_public_events_for_school(self.school)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["slug"], self.event.slug)
        self.assertEqual(rows[0]["title"], self.event.title)

    def test_event_hub_and_detail_render_on_tenant_host(self):
        self.client.force_login(self.user)

        hub = self.client.get(
            reverse("school_events:event_hub", urlconf="config.tenant_urls"),
            HTTP_HOST="riverfront-academy.runmycampus.com",
        )
        detail = self.client.get(
            reverse(
                "school_events:event_detail",
                kwargs={"slug": self.event.slug},
                urlconf="config.tenant_urls",
            ),
            HTTP_HOST="riverfront-academy.runmycampus.com",
        )

        self.assertEqual(hub.status_code, 200)
        self.assertContains(hub, self.event.title)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "General Admission")

    def test_event_registration_increments_ticket_sales(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "school_events:register_for_event",
                kwargs={"slug": self.event.slug},
                urlconf="config.tenant_urls",
            ),
            {"ticket_tier_id": self.tier.pk, "quantity": 2},
            HTTP_HOST="riverfront-academy.runmycampus.com",
        )

        self.assertEqual(response.status_code, 302)
        self.tier.refresh_from_db()
        registration = EventRegistration.objects.get(
            event=self.event, purchaser=self.user
        )
        self.assertEqual(self.tier.sold_quantity, 2)
        self.assertEqual(registration.quantity, 2)
        self.assertEqual(registration.amount_due, Decimal("50.00"))
