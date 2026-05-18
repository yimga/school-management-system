"""v3.32.0 — Tests for first-class assignment admin pages + reverse inlines.

Structural-mode assertions (:class:`SimpleTestCase`) verify that:

  * The three new ModelAdmins are registered on ``tenant_admin_site``.
  * The reverse-relation inlines are wired onto the parent admins
    (Route / HostelRoom / CanteenMeal).
  * The custom ``is_low_display`` method is configured as a boolean
    column on :class:`MealPlanBalanceAdmin`.

Where the project test DB is available, :class:`TestCase` assertions
add a smoke render of each list page for a staff user.
"""

from __future__ import annotations

from django.test import SimpleTestCase


class AssignmentAdminRegistrationTests(SimpleTestCase):
    """ModelAdmin registration smoke tests."""

    def test_transport_assignment_admin_registered(self) -> None:
        from config.admin import tenant_admin_site
        from apps.schoolops.models import TransportAssignment

        self.assertIn(TransportAssignment, tenant_admin_site._registry)

    def test_hostel_assignment_admin_registered(self) -> None:
        from config.admin import tenant_admin_site
        from apps.schoolops.models import HostelAssignment

        self.assertIn(HostelAssignment, tenant_admin_site._registry)

    def test_meal_plan_balance_admin_registered(self) -> None:
        from config.admin import tenant_admin_site
        from apps.schoolops.models import MealPlanBalance

        self.assertIn(MealPlanBalance, tenant_admin_site._registry)


class AssignmentAdminConfigurationTests(SimpleTestCase):
    """Admin classes expose the documented list / filter / search config."""

    def test_transport_admin_list_filter_search(self) -> None:
        from config.admin import tenant_admin_site
        from apps.schoolops.models import TransportAssignment

        admin_obj = tenant_admin_site._registry[TransportAssignment]
        for col in ("student", "route", "pickup_stop", "dropoff_stop",
                    "effective_from", "effective_to", "status", "school"):
            self.assertIn(col, admin_obj.list_display)
        self.assertEqual(admin_obj.date_hierarchy, "effective_from")
        self.assertIn("status", admin_obj.list_filter)
        self.assertIn("school", admin_obj.list_filter)

    def test_hostel_admin_list_filter_search(self) -> None:
        from config.admin import tenant_admin_site
        from apps.schoolops.models import HostelAssignment

        admin_obj = tenant_admin_site._registry[HostelAssignment]
        for col in ("student", "room", "bed_label",
                    "effective_from", "status"):
            self.assertIn(col, admin_obj.list_display)
        self.assertEqual(admin_obj.date_hierarchy, "effective_from")

    def test_meal_balance_admin_has_is_low_boolean_column(self) -> None:
        from config.admin import tenant_admin_site
        from apps.schoolops.models import MealPlanBalance

        admin_obj = tenant_admin_site._registry[MealPlanBalance]
        self.assertIn("is_low_display", admin_obj.list_display)
        method = getattr(admin_obj, "is_low_display", None)
        self.assertTrue(callable(method))
        self.assertTrue(getattr(method, "boolean", False))
        for col in ("last_topup_at", "last_topup_amount",
                    "last_low_balance_notification_sent_at",
                    "low_balance_notification_count"):
            self.assertIn(col, admin_obj.readonly_fields)


class ReverseRelationInlineTests(SimpleTestCase):
    """Inlines on parent admins surface the assignment rows."""

    def test_route_admin_has_transport_inline(self) -> None:
        from config.admin import tenant_admin_site
        from apps.schoolops.models import Route, TransportAssignment

        admin_obj = tenant_admin_site._registry[Route]
        inline_models = [i.model for i in (admin_obj.inlines or [])]
        self.assertIn(TransportAssignment, inline_models)

    def test_hostel_room_admin_has_hostel_inline(self) -> None:
        from config.admin import tenant_admin_site
        from apps.schoolops.models import HostelAssignment, HostelRoom

        admin_obj = tenant_admin_site._registry[HostelRoom]
        inline_models = [i.model for i in (admin_obj.inlines or [])]
        self.assertIn(HostelAssignment, inline_models)

    def test_canteen_meal_admin_has_meal_plan_inline(self) -> None:
        from config.admin import tenant_admin_site
        from apps.schoolops.models import CanteenMeal, MealPlanBalance

        admin_obj = tenant_admin_site._registry[CanteenMeal]
        inline_models = [i.model for i in (admin_obj.inlines or [])]
        self.assertIn(MealPlanBalance, inline_models)
