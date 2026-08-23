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
        # self.user is a PARENT. The hub is now staff-only -- it lists every
        # draft event and the operations snapshot -- so the console half of this
        # test needs a staff account. The DETAIL half stays on the parent, which
        # is the point: ticket purchase must keep working for them.
        staff = User.objects.create_user(
            username="events-staff",
            email="events-staff@example.com",
            password="pass1234",
        )
        staff.role = User.Role.ADMIN
        staff.save(update_fields=["role"])
        SchoolMembership.objects.create(
            user=staff, school=self.school, role=User.Role.ADMIN
        )
        self._login_verified(staff)

        hub = self.client.get(
            reverse("school_events:event_hub", urlconf="config.tenant_urls"),
        )
        self.assertEqual(hub.status_code, 200)

        self._login_verified()
        detail = self.client.get(
            reverse(
                "school_events:event_detail",
                kwargs={"slug": self.event.slug},
                urlconf="config.tenant_urls",
            ),
        )

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
            school=self.school,
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


class EventRegistrationTenantScopeTests(TestCase):
    """A PSP webhook must not be able to settle another school's ticket.

    ``_maybe_confirm_event_registration`` (apps/finance/views_payments.py) reads
    ``event_registration_id`` straight off the webhook PAYLOAD -- body, nested
    ``metadata``, ``data``, or the invoice's own metadata -- and handed it to
    ``EventRegistration.objects.get(pk=...)`` with no check that the registration
    belongs to the school whose invoice is being settled.

    So a payment posted against school A's invoice, carrying school B's
    registration id, confirmed school B's ticket: a free ticket at a school the
    payer has no relationship with, and a cross-tenant write out of a webhook.

    The same file already guards the other direction -- ``create_ticket_invoice_
    for_registration`` scopes its invoice-reuse lookup to ``locked.event.school``
    with a comment saying a stray invoice_id must never resolve cross-tenant. The
    confirm path was simply missed.
    """

    def setUp(self):
        self.buyer = User.objects.create_user(
            username="xt-buyer", email="xt-buyer@example.com", password="pass1234"
        )
        self.school_a, self.tier_a = self._school_with_tier("alpha")
        self.school_b, self.tier_b = self._school_with_tier("bravo")

    def _school_with_tier(self, tag):
        school = School.objects.create(
            name=f"School {tag}", slug=f"sch-{tag}", subdomain=f"sch-{tag}", is_active=True
        )
        event = SchoolEvent.objects.create(
            school=school,
            title=f"{tag} Gala",
            slug=f"{tag}-gala",
            status=SchoolEvent.Status.PUBLISHED,
            organizer_name="Office",
            start_at=timezone.now() + timedelta(days=5),
            is_public=True,
            ticketing_enabled=True,
        )
        tier = EventTicketTier.objects.create(
            event=event,
            name="General",
            code=f"gen-{tag}",
            price=Decimal("25.00"),
            capacity=100,
            sold_quantity=0,
        )
        return school, tier

    def test_the_fixture_really_is_two_schools(self):
        # Calibration: if both tiers hung off one school, "refused" would prove
        # nothing about tenant scoping.
        self.assertNotEqual(self.school_a.pk, self.school_b.pk)
        self.assertNotEqual(self.tier_a.event.school_id, self.tier_b.event.school_id)

    def test_a_webhook_for_one_school_cannot_confirm_another_schools_ticket(self):
        from apps.school_events.services import confirm_registration_from_psp

        victim = register_for_tier(
            event=self.tier_b.event, tier=self.tier_b, purchaser=self.buyer, quantity=1
        )
        self.assertEqual(victim.status, EventRegistration.Status.RESERVED)

        with self.assertRaises(EventRegistration.DoesNotExist):
            confirm_registration_from_psp(
                registration_id=victim.pk,
                amount=Decimal("25.00"),
                method="psp",
                reference="evil-1",
                school=self.school_a,  # the invoice being settled is school A's
            )

        victim.refresh_from_db()
        self.assertEqual(
            victim.status,
            EventRegistration.Status.RESERVED,
            "school B's ticket must still be unpaid",
        )

    def test_the_owning_school_can_still_confirm_its_own_ticket(self):
        """The guard must not break the path it is protecting."""
        from apps.school_events.services import confirm_registration_from_psp

        registration = register_for_tier(
            event=self.tier_a.event, tier=self.tier_a, purchaser=self.buyer, quantity=1
        )
        confirmed = confirm_registration_from_psp(
            registration_id=registration.pk,
            amount=Decimal("25.00"),
            method="psp",
            reference="ok-1",
            school=self.school_a,
        )
        self.assertEqual(confirmed.status, EventRegistration.Status.CONFIRMED)
        self.assertEqual(confirmed.metadata.get("psp_reference"), "ok-1")

    def test_the_webhook_helper_passes_the_invoice_school_through(self):
        """The service-level guard is only real if the caller supplies the school."""
        import inspect

        from apps.finance import views_payments

        source = inspect.getsource(views_payments._maybe_confirm_event_registration)
        self.assertIn(
            "school=",
            source,
            "_maybe_confirm_event_registration must pass the invoice's school to "
            "confirm_registration_from_psp, or the guard is unreachable",
        )


class EventRlsCoverageTests(TestCase):
    """Every tenant-reaching school_events table must be named in an RLS migration.

    0002/0003 enumerate only the three models carrying a literal ``school`` FK.
    EventTicketTier, EventSponsorCommitment and EventRegistration reach their
    school through ``event``, so they had no ENABLE, no policy and no FORCE --
    under USE_DJANGO_TENANTS=0 (one schema, RLS is the boundary) any tenant
    connection could read every school's ticket pricing, sponsor pledges and
    attendee registrations. 0004 closes it.

    ``scripts/scan_rls_table_coverage.py`` could not see this: it decides a model
    is tenant-scoped by looking for a FK literally NAMED ``school``, so a
    relation-scoped child is invisible to it and the gate reports 0 while telling
    the truth about the question it asks. This test asks the other question, for
    this app, by FOLLOWING relations -- so a new child model added later fails
    here instead of shipping unprotected.

    NOTE ON WHAT THIS PROVES. The suite runs on SQLite, where RLS does not exist,
    so this asserts the DECLARATION, not the enforcement. The policy SQL itself
    only ever executes on PostgreSQL with USE_DJANGO_TENANTS=0 and is not
    exercised here.
    """

    maxDiff = None

    def _tenant_reaching_tables(self):
        from django.apps import apps as django_apps

        app = django_apps.get_app_config("school_events")
        out = {}
        for model in app.get_models():
            seen, frontier, hops = set(), [model], 0
            while frontier and hops < 4:
                nxt = []
                for current in frontier:
                    if current in seen:
                        continue
                    seen.add(current)
                    for field in current._meta.get_fields():
                        if not getattr(field, "many_to_one", False):
                            continue
                        target = field.related_model
                        if target is None:
                            continue
                        if target._meta.label == "schools.School":
                            out[model._meta.db_table] = model.__name__
                            nxt = []
                            break
                        nxt.append(target)
                    else:
                        continue
                    break
                frontier, hops = nxt, hops + 1
        return out

    def _tables_named_in_rls_migrations(self):
        import pathlib

        directory = pathlib.Path(__file__).resolve().parent / "migrations"
        named = set()
        for path in directory.glob("*.py"):
            if "rls" not in path.name:
                continue
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                for token in line.split('"'):
                    if token.startswith("school_events_"):
                        named.add(token)
        return named

    def test_the_probe_finds_the_models_it_is_supposed_to(self):
        # Calibration: an empty or tiny map would make the assertion below vacuous.
        reaching = self._tenant_reaching_tables()
        self.assertGreaterEqual(len(reaching), 6, reaching)
        self.assertIn("school_events_eventregistration", reaching)
        self.assertIn("school_events_schoolevent", reaching)

    def test_every_tenant_reaching_table_has_an_rls_declaration(self):
        reaching = self._tenant_reaching_tables()
        named = self._tables_named_in_rls_migrations()
        missing = sorted(set(reaching) - named)
        self.assertEqual(
            missing,
            [],
            "these school_events tables hold tenant data but appear in no RLS "
            f"migration, so they have no policy under USE_DJANGO_TENANTS=0: {missing}",
        )


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class EventConsoleIsStaffOnlyTests(TestCase):
    """The events console showed drafts and sponsor money to anyone signed in.

    ``event_hub`` carried ``@login_required`` and nothing else, so a STUDENT or a
    PARENT of the school could open it and read every DRAFT event plus
    ``event_operations_snapshot``. ``event_detail`` was the same: no status
    filter, so an unpublished event was readable by slug, and its template lists
    every sponsor's name, tier and PLEDGED AMOUNT.

    Ticket purchase must keep working for exactly the people now excluded from
    the console, so ``event_detail`` stays reachable -- what it stops doing is
    serving unpublished events and sponsor money to them.
    """

    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
             "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.school = School.objects.create(
            name="Console School", slug="console-school",
            subdomain="console-school", is_active=True,
        )
        self.host = "console-school.runmycampus.com"
        self.parent = User.objects.create_user(
            username="ev-parent", email="ev-parent@example.com", password="pass1234"
        )
        self.parent.role = "PARENT"
        self.parent.save(update_fields=["role"])
        SchoolMembership.objects.create(
            user=self.parent, school=self.school, role="PARENT"
        )
        self.draft = SchoolEvent.objects.create(
            school=self.school, title="Unannounced Gala", slug="unannounced-gala",
            status=SchoolEvent.Status.DRAFT, organizer_name="Advancement",
            start_at=timezone.now() + timedelta(days=9), is_public=False,
        )
        self.published = SchoolEvent.objects.create(
            school=self.school, title="Open Day", slug="open-day",
            status=SchoolEvent.Status.PUBLISHED, organizer_name="Advancement",
            start_at=timezone.now() + timedelta(days=3), is_public=True,
            ticketing_enabled=True,
        )

    def _client(self):
        client = Client(HTTP_HOST=self.host)
        client.force_login(self.parent)
        return client

    def test_the_request_actually_reaches_the_view(self):
        """Calibration for the vacuous-403 trap.

        Without HTTP_HOST the tenant middleware leaves request.school None, the
        view returns 'Tenant context required', and a 403 assertion would pass
        against a completely ungated page.
        """
        response = self._client().get(
            reverse("school_events:event_detail",
                    kwargs={"slug": self.published.slug},
                    urlconf="config.tenant_urls")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open Day")

    def test_a_parent_cannot_open_the_events_console(self):
        response = self._client().get(
            reverse("school_events:event_hub", urlconf="config.tenant_urls")
        )
        self.assertEqual(
            response.status_code, 403,
            "the hub lists every draft event and the operations snapshot",
        )

    def test_a_parent_cannot_read_an_unpublished_event(self):
        response = self._client().get(
            reverse("school_events:event_detail",
                    kwargs={"slug": self.draft.slug},
                    urlconf="config.tenant_urls")
        )
        self.assertEqual(response.status_code, 404)

    def test_a_parent_does_not_see_sponsor_pledge_amounts(self):
        from apps.school_events.models import EventSponsor, EventSponsorCommitment

        sponsor = EventSponsor.objects.create(
            school=self.school, name="Wealthy Donor Ltd"
        )
        EventSponsorCommitment.objects.create(
            event=self.published, sponsor=sponsor, pledged_amount=Decimal("50000.00")
        )
        response = self._client().get(
            reverse("school_events:event_detail",
                    kwargs={"slug": self.published.slug},
                    urlconf="config.tenant_urls")
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Wealthy Donor Ltd")
        self.assertNotContains(response, "50,000")
