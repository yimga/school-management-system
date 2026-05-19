"""Domain event outbox → trigger_dispatcher bridge."""


from django.test import SimpleTestCase, TestCase, tag

from apps.automation.domain_event_bridge import (
    dispatch_domain_event_to_triggers,
    resolve_trigger_key,
    register_domain_event_trigger_subscriber,
)
from apps.automation.trigger_dispatcher import clear_registry_for_tests, register_handler
from apps.events.bus import clear_subscribers_for_tests, dispatch_internal_subscribers


class ResolveTriggerKeyTests(SimpleTestCase):
    def test_payment_aliases(self):
        self.assertEqual(resolve_trigger_key("payment_received"), "payment_success")
        self.assertEqual(resolve_trigger_key("attendance.saved"), "attendance_saved")

    def test_unknown_returns_none(self):
        self.assertIsNone(resolve_trigger_key("not.a.real.trigger"))


@tag("tenants_rls")
class DomainEventBridgeDispatchTests(TestCase):
    def setUp(self):
        clear_registry_for_tests()
        clear_subscribers_for_tests()
        register_domain_event_trigger_subscriber()

    def tearDown(self):
        clear_registry_for_tests()
        clear_subscribers_for_tests()

    def test_subscriber_fires_registered_handler(self):
        from apps.events.models import DomainEvent
        from apps.schools.models import School

        school = School.objects.create(
            name="Bridge School",
            slug="bridge-school",
            subdomain="bridge-school",
            is_active=True,
        )
        seen = []

        @register_handler("payment_success")
        def _capture(payload, school_obj, actor):
            seen.append((school_obj.pk, payload.get("amount")))
            return {"records_processed": 1}

        event = DomainEvent.objects.create(
            event_type="payment_success",
            payload={"amount": "100"},
            school_id=school.pk,
        )
        dispatch_internal_subscribers(event)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], school.pk)

    def test_dispatch_helper_without_subscriber(self):
        from apps.events.models import DomainEvent
        from apps.schools.models import School

        school = School.objects.create(
            name="Bridge School 2",
            slug="bridge-school-2",
            subdomain="bridge-school-2",
            is_active=True,
        )

        @register_handler("attendance_saved")
        def _noop(payload, school_obj, actor):
            return {}

        event = DomainEvent.objects.create(
            event_type="attendance_saved",
            payload={"saved_count": 3},
            school_id=school.pk,
        )
        results = dispatch_domain_event_to_triggers(event)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "success")
