import os
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.schools.models import SchoolMembership
from apps.school_events.models import (
    EventRegistration,
    EventTicketTier,
    EventVenue,
    SchoolEvent,
)
from apps.school_events.services import (
    RegistrationStateError,
    confirm_registration_payment,
    register_for_tier,
    release_reservation,
    upcoming_public_events_for_school,
)
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
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.PARENT,
            is_primary=True,
        )
        self.tenant_host = f"{self.school.subdomain}.runmycampus.com"
        self.client = Client(HTTP_HOST=self.tenant_host)

    def tearDown(self):
        self.env.stop()

    def _login_verified(self, user=None):
        """Auth must be bound on the tenant host — force_login on testserver does not survive HTTP_HOST."""
        user = user or self.user
        self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        session = self.client.session
        session["mfa_verified"] = True
        session["school_id"] = str(self.school.id)
        session.save()

    def test_upcoming_public_events_service_scopes_to_school(self):
        rows = upcoming_public_events_for_school(self.school)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["slug"], self.event.slug)
        self.assertEqual(rows[0]["title"], self.event.title)

    def test_event_hub_and_detail_render_on_tenant_host(self):
        self._login_verified()

        hub = self.client.get(
            reverse("school_events:event_hub", urlconf="config.tenant_urls"),
        )
        detail = self.client.get(
            reverse(
                "school_events:event_detail",
                kwargs={"slug": self.event.slug},
                urlconf="config.tenant_urls",
            ),
        )

        self.assertEqual(hub.status_code, 200)
        self.assertContains(hub, self.event.title)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "General Admission")

    def test_event_registration_increments_ticket_sales(self):
        self._login_verified()

        response = self.client.post(
            reverse(
                "school_events:register_for_event",
                kwargs={"slug": self.event.slug},
                urlconf="config.tenant_urls",
            ),
            {"ticket_tier_id": self.tier.pk, "quantity": 2},
        )

        self.assertEqual(response.status_code, 302)
        self.tier.refresh_from_db()
        registration = EventRegistration.objects.get(
            event=self.event, purchaser=self.user
        )
        self.assertEqual(self.tier.sold_quantity, 2)
        self.assertEqual(registration.quantity, 2)
        self.assertEqual(registration.amount_due, Decimal("50.00"))

    def test_registration_refuses_oversell(self):
        self._login_verified()
        self.tier.capacity = 2
        self.tier.sold_quantity = 2
        self.tier.save(update_fields=["capacity", "sold_quantity"])
        response = self.client.post(
            reverse(
                "school_events:register_for_event",
                kwargs={"slug": self.event.slug},
                urlconf="config.tenant_urls",
            ),
            {"ticket_tier_id": self.tier.pk, "quantity": 1},
        )
        self.assertEqual(response.status_code, 302)
        self.tier.refresh_from_db()
        self.assertEqual(self.tier.sold_quantity, 2)
        self.assertFalse(
            EventRegistration.objects.filter(
                event=self.event, purchaser=self.user
            ).exists()
        )

    def test_registration_exact_capacity_then_sold_out(self):
        from apps.school_events.services import TicketCapacityError

        self.tier.capacity = 1
        self.tier.sold_quantity = 0
        self.tier.save(update_fields=["capacity", "sold_quantity"])
        register_for_tier(
            event=self.event, tier=self.tier, purchaser=self.user, quantity=1
        )
        self.tier.refresh_from_db()
        self.assertEqual(self.tier.sold_quantity, 1)
        self.assertEqual(self.tier.remaining_capacity, 0)
        with self.assertRaises(TicketCapacityError):
            register_for_tier(
                event=self.event, tier=self.tier, purchaser=self.user, quantity=1
            )

    def test_confirm_registration_payment_settles_reserved_hold(self):
        registration = register_for_tier(
            event=self.event, tier=self.tier, purchaser=self.user, quantity=2
        )
        self.assertEqual(registration.status, EventRegistration.Status.RESERVED)
        settled = confirm_registration_payment(
            registration=registration, method="cash"
        )
        settled.refresh_from_db()
        self.assertEqual(settled.status, EventRegistration.Status.CONFIRMED)
        self.assertEqual(settled.amount_paid, Decimal("50.00"))
        self.assertEqual(settled.metadata.get("payment_method"), "cash")
        # Idempotent when already confirmed.
        again = confirm_registration_payment(registration=settled)
        self.assertEqual(again.pk, settled.pk)
        self.assertEqual(again.status, EventRegistration.Status.CONFIRMED)

    def test_release_reservation_restores_tier_capacity(self):
        registration = register_for_tier(
            event=self.event, tier=self.tier, purchaser=self.user, quantity=3
        )
        self.tier.refresh_from_db()
        self.assertEqual(self.tier.sold_quantity, 3)
        self.assertEqual(registration.status, EventRegistration.Status.RESERVED)

        released = release_reservation(registration=registration)
        released.refresh_from_db()
        self.tier.refresh_from_db()
        self.assertEqual(released.status, EventRegistration.Status.CANCELED)
        self.assertEqual(self.tier.sold_quantity, 0)
        self.assertIn("released_at", released.metadata or {})

        # Cannot release a confirmed booking.
        paid = register_for_tier(
            event=self.event, tier=self.tier, purchaser=self.user, quantity=1
        )
        confirm_registration_payment(registration=paid)
        with self.assertRaises(RegistrationStateError):
            release_reservation(registration=paid)

    def test_expire_stale_reservations_releases_old_holds(self):
        from datetime import timedelta

        from apps.school_events.services import expire_stale_reservations

        fresh = register_for_tier(
            event=self.event, tier=self.tier, purchaser=self.user, quantity=1
        )
        stale = register_for_tier(
            event=self.event, tier=self.tier, purchaser=self.user, quantity=2
        )
        EventRegistration.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(minutes=90)
        )
        self.tier.refresh_from_db()
        self.assertEqual(self.tier.sold_quantity, 3)

        released = expire_stale_reservations(older_than_minutes=45)
        self.assertEqual(released, 1)
        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.tier.refresh_from_db()
        self.assertEqual(stale.status, EventRegistration.Status.CANCELED)
        self.assertEqual(fresh.status, EventRegistration.Status.RESERVED)
        self.assertEqual(self.tier.sold_quantity, 1)

    def test_confirm_registration_from_psp_stores_reference(self):
        from apps.school_events.services import confirm_registration_from_psp

        registration = register_for_tier(
            event=self.event, tier=self.tier, purchaser=self.user, quantity=1
        )
        confirmed = confirm_registration_from_psp(
            registration_id=registration.pk,
            amount=Decimal("25.00"),
            method="mpesa_daraja",
            reference="ws_CO_TEST_1",
        )
        self.assertEqual(confirmed.status, EventRegistration.Status.CONFIRMED)
        self.assertEqual(confirmed.metadata.get("psp_reference"), "ws_CO_TEST_1")
        self.assertEqual(confirmed.metadata.get("payment_method"), "mpesa_daraja")

    def test_ticket_invoice_webhook_settles_registration(self):
        """RESERVED → ticket invoice → mocked Paystack webhook → CONFIRMED."""
        import hashlib
        import hmac
        import json

        from apps.academics.models import AcademicYear
        from apps.finance.models import ComplianceProfile, Invoice
        from apps.school_events.services import create_ticket_invoice_for_registration
        from apps.integrations_marketplace.models import Integration

        profile = ComplianceProfile.objects.create(
            name="Ticket PSP",
            country_code="CM",
            currency_code="XAF",
            currency_symbol="XAF",
            timezone="Africa/Douala",
            chart_template=ComplianceProfile.ChartTemplate.OHADA,
            min_wage=Decimal("60000"),
            default_hours_per_week=Decimal("40"),
            overtime_multiplier=Decimal("1.5"),
            annual_leave_days=21,
            maternity_leave_days=84,
            is_active=True,
        )
        year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
            school=self.school,
        )
        registration = register_for_tier(
            event=self.event, tier=self.tier, purchaser=self.user, quantity=1
        )
        invoice = create_ticket_invoice_for_registration(
            registration=registration,
            profile=profile,
            academic_year=year,
        )
        registration.refresh_from_db()
        self.assertEqual(registration.metadata.get("invoice_id"), invoice.pk)
        self.assertEqual(Invoice.objects.filter(pk=invoice.pk).count(), 1)

        secret = "ticket-psk-secret"
        Integration.objects.create(
            name="Paystack Ticket",
            slug="paystack-ticket",
            provider="payments",
            enabled=True,
            config={"provider_slug": "paystack", "webhook_secret": secret},
        )
        payload = {
            "event": "charge.success",
            "invoiceId": invoice.pk,
            "amount": "25.00",
            "transaction_id": "psk-ticket-1",
            "status": "successful",
            "event_registration_id": registration.pk,
            "data": {
                "reference": "psk-ticket-1",
                "status": "success",
                "amount": 2500,
                "currency": "XAF",
                "metadata": {
                    "invoice_id": invoice.pk,
                    "event_registration_id": registration.pk,
                },
            },
        }
        body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        # Finance webhook lives on the platform urlconf, not the tenant host Client.
        webhook_client = Client()
        response = webhook_client.post(
            reverse(
                "finance:payment_webhook",
                kwargs={"provider_slug": "paystack"},
            ),
            data=body,
            content_type="application/json",
            HTTP_X_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json().get("status"), "ok")
        registration.refresh_from_db()
        self.assertEqual(registration.status, EventRegistration.Status.CONFIRMED)
        self.assertEqual(registration.amount_paid, Decimal("25.00"))
        self.assertEqual(registration.metadata.get("psp_reference"), "psk-ticket-1")
