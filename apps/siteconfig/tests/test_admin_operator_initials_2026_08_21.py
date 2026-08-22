"""Operator-side auto-fill: the two derivable signals that site actually has.

The operator admin has no `request.school`, so every tenant-state resolver returned
nothing there. Two of those signals are real and were simply not being read:

1. Django preserves the changelist's filters across the Add link
   (`?_changelist_filters=school__id__exact%3D5`). An operator who filtered to one
   school and clicked Add has already stated the school.
2. An event being recorded by hand happened now -- a convention, not derived state,
   so it must announce itself in the field's help text.

The isolation tests matter more here than on the tenant site: on the operator site
`school` is an ordinary editable field, so a resolver that reads it from the request
is reading attacker-influenceable input.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.schools.models import School
from apps.siteconfig.admin_smart_initials import (
    EVENT_TIMESTAMP_FIELD_NAMES,
    NOTE_EVENT_NOW,
    _request_school,
    _school_id_from_changelist_filters,
    build_admin_smart_initials_detailed,
)
from apps.siteconfig.models_platform_catalog import RegionConfig


def _operator_request(query: dict | None = None, *, user):
    request = RequestFactory().get(
        "/admin/", query or {}, HTTP_HOST="manager.runmycampus.com"
    )
    request.user = user
    request.school = None
    request.public_host_kind = "manager"
    request.urlconf = "config.manager_urls"
    SessionMiddleware(lambda _r: None).process_request(request)
    MessageMiddleware(lambda _r: None).process_request(request)
    return request


class OperatorChangelistFilterSchoolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="operator-initials",
            email="operator-initials@example.test",
            password="test-only-password",
        )
        cls.region = RegionConfig.objects.create(code="op-region", name="Op Region")
        cls.school = School.objects.create(
            name="Operator Filtered School",
            slug="op-filtered",
            subdomain="op-filtered",
            country_code="CM",
            default_region=cls.region,
            is_active=True,
        )
        today = timezone.now().date()
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="Op 2026/2027",
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=300),
            is_active=True,
        )

    # -- parsing ------------------------------------------------------------ #

    def test_reads_the_school_django_preserved_from_the_changelist(self):
        request = _operator_request(
            {"_changelist_filters": f"school__id__exact={self.school.pk}"},
            user=self.user,
        )
        self.assertEqual(
            _school_id_from_changelist_filters(request), str(self.school.pk)
        )
        self.assertEqual(_request_school(request).pk, self.school.pk)

    def test_accepts_the_other_key_shapes_a_filter_can_arrive_under(self):
        for key in ("school", "school__id", "school_id"):
            with self.subTest(key=key):
                request = _operator_request(
                    {"_changelist_filters": f"{key}={self.school.pk}"}, user=self.user
                )
                self.assertEqual(_request_school(request).pk, self.school.pk)

    def test_a_filter_on_something_else_yields_no_school(self):
        request = _operator_request(
            {"_changelist_filters": "status__exact=active&is_paid__exact=1"},
            user=self.user,
        )
        self.assertEqual(_school_id_from_changelist_filters(request), "")
        self.assertIsNone(_request_school(request))

    def test_a_malformed_filter_string_is_not_an_error(self):
        for raw in ("", "%%%", "school__id__exact=", "=5", "&&&"):
            with self.subTest(raw=raw):
                request = _operator_request(
                    {"_changelist_filters": raw}, user=self.user
                )
                self.assertIsNone(_request_school(request))

    def test_an_unknown_school_id_yields_nothing_rather_than_an_error(self):
        request = _operator_request(
            {"_changelist_filters": "school__id__exact=99999999"}, user=self.user
        )
        self.assertIsNone(_request_school(request))

    def test_a_non_numeric_school_id_does_not_raise(self):
        request = _operator_request(
            {"_changelist_filters": "school__id__exact=not-a-pk"}, user=self.user
        )
        self.assertIsNone(_request_school(request))

    def test_an_explicit_school_param_still_wins_over_the_filter(self):
        other = School.objects.create(
            name="Explicit", slug="op-explicit", subdomain="op-explicit", is_active=True
        )
        request = _operator_request(
            {
                "school": str(other.pk),
                "_changelist_filters": f"school__id__exact={self.school.pk}",
            },
            user=self.user,
        )
        self.assertEqual(_request_school(request).pk, other.pk)

    # -- effect on a real operator add form ---------------------------------- #

    def test_tenant_state_resolvers_now_work_on_the_operator_site(self):
        from apps.academics.models import Term

        without = _operator_request(user=self.user)
        with_filter = _operator_request(
            {"_changelist_filters": f"school__id__exact={self.school.pk}"},
            user=self.user,
        )
        blank, _ = build_admin_smart_initials_detailed(Term, without)
        filled, _ = build_admin_smart_initials_detailed(Term, with_filter)
        self.assertNotIn("academic_year", blank)
        self.assertEqual(filled.get("academic_year"), self.year.pk)


class EventTimestampTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="event-ts-admin",
            email="event-ts@example.test",
            password="test-only-password",
        )

    def test_an_event_being_recorded_now_defaults_to_now(self):
        from apps.billing.models import PlatformLedgerEntry

        request = _operator_request(user=self.user)
        values, notes = build_admin_smart_initials_detailed(
            PlatformLedgerEntry, request
        )
        self.assertIn("happened_at", values)
        delta = abs((timezone.now() - values["happened_at"]).total_seconds())
        self.assertLess(delta, 60)

    def test_the_default_announces_itself(self):
        """Rule 1.2: a convention-derived value must say so where a person reads it."""
        from apps.billing.models import PlatformLedgerEntry

        request = _operator_request(user=self.user)
        _values, notes = build_admin_smart_initials_detailed(
            PlatformLedgerEntry, request
        )
        self.assertEqual(notes.get("happened_at"), NOTE_EVENT_NOW)
        self.assertIn("change it if", NOTE_EVENT_NOW.lower())

    def test_future_facing_timestamps_are_deliberately_excluded(self):
        """Defaulting an expiry or a start to NOW is wrong, not merely unhelpful."""
        for name in ("expires_at", "starts_at", "start_at", "due_at", "scheduled_at",
                     "valid_until", "ends_at", "published_at"):
            with self.subTest(name=name):
                self.assertNotIn(name, EVENT_TIMESTAMP_FIELD_NAMES)

    def test_the_note_reaches_the_rendered_add_form_help_text(self):
        from apps.billing.models import PlatformLedgerEntry
        from config.admin import platform_admin_site

        model_admin = platform_admin_site._registry.get(PlatformLedgerEntry)
        if model_admin is None:
            self.skipTest("billing.PlatformLedgerEntry is not registered on operator")
        request = _operator_request(user=self.user)
        context = {}
        form_class = model_admin.get_form(request, obj=None, change=False)
        form = form_class(initial=model_admin.get_changeform_initial_data(request))

        class _Adminform:
            pass

        adminform = _Adminform()
        adminform.form = form
        context["adminform"] = adminform
        try:
            model_admin.render_change_form(
                request, context, add=True, change=False, obj=None
            )
        except Exception:  # noqa: BLE001 - rendering needs a full template context
            # The help-text annotation happens before super() renders, so the
            # annotation is observable even when the template render cannot run
            # under a bare RequestFactory.
            pass
        self.assertIn(
            NOTE_EVENT_NOW,
            form.fields["happened_at"].help_text,
            "the fallback note must reach the field a person actually reads",
        )
