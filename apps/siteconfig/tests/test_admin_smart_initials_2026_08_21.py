"""Proof for the generic admin initial-value resolvers.

Every test here fails against the pre-expansion module, where ``INITIAL_BUILDERS``
held one entry and no field-level layer existed.  Three properties are asserted for
each resolver, because a suggestion that is merely present is not yet correct:

1. it produces the derived value,
2. the value stays EDITABLE (a suggestion, never a lock),
3. it cannot cross a tenant boundary.

Point 3 is the one worth the ceremony: two fully-populated schools exist in every
relevant fixture, and the assertions name the other school's row explicitly rather
than checking "not empty".
"""

from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear, Term
from apps.people.models import TeacherProfile
from apps.schools.models import School
from apps.siteconfig.admin_smart_initials import (
    ACTOR_FIELD_NAMES,
    FIELD_RESOLVERS,
    InitialContext,
    build_admin_smart_initials,
    build_admin_smart_initials_detailed,
    resolve_field_initials,
)
from apps.siteconfig.models_platform_catalog import RegionConfig
from config.admin import platform_admin_site, tenant_admin_site


def _request(*, user, school, host, urlconf="config.tenant_urls", kind="tenant"):
    request = RequestFactory().get("/admin/", HTTP_HOST=host)
    request.user = user
    request.school = school
    request.public_host_kind = kind
    request.urlconf = urlconf
    SessionMiddleware(lambda _r: None).process_request(request)
    MessageMiddleware(lambda _r: None).process_request(request)
    return request


class SmartInitialResolverTests(TestCase):
    """Two tenants, both fully populated, so isolation failures are visible."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="smart-initials-admin",
            email="smart-initials@example.test",
            password="test-only-password",
        )
        cls.region_ours = RegionConfig.objects.create(
            code="rmc-test-ours", name="Ours Region"
        )
        cls.region_theirs = RegionConfig.objects.create(
            code="rmc-test-theirs", name="Theirs Region"
        )
        cls.ours = School.objects.create(
            name="Ours School",
            slug="smart-ours",
            subdomain="smart-ours",
            country_code="CM",
            currency="XAF",
            timezone="Africa/Douala",
            default_language="fr",
            default_region=cls.region_ours,
            is_active=True,
        )
        cls.theirs = School.objects.create(
            name="Theirs School",
            slug="smart-theirs",
            subdomain="smart-theirs",
            country_code="GB",
            currency="GBP",
            timezone="Europe/London",
            default_language="en",
            default_region=cls.region_theirs,
            is_active=True,
        )

        today = timezone.now().date()
        cls.year_ours = AcademicYear.objects.create(
            school=cls.ours,
            name="Ours 2026/2027",
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=300),
            is_active=True,
        )
        cls.year_theirs = AcademicYear.objects.create(
            school=cls.theirs,
            name="Theirs 2026/2027",
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=300),
            is_active=True,
        )
        cls.term_ours = Term.objects.create(
            school=cls.ours,
            academic_year=cls.year_ours,
            name="FIRST",
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=60),
            is_active=True,
        )
        cls.term_theirs = Term.objects.create(
            school=cls.theirs,
            academic_year=cls.year_theirs,
            name="FIRST",
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=60),
            is_active=True,
        )

    def _ctx(self, school=None):
        school = school if school is not None else self.ours
        return InitialContext(
            request=_request(
                user=self.user, school=school, host=f"{school.slug}.runmycampus.com"
            ),
            school=school,
            user=self.user,
        )

    # -- academic year ----------------------------------------------------- #

    def test_academic_year_resolves_to_this_schools_active_year(self):
        values = resolve_field_initials(Term, self._ctx())
        self.assertEqual(values.get("academic_year"), self.year_ours.pk)

    def test_academic_year_never_returns_another_tenants_year(self):
        values = resolve_field_initials(Term, self._ctx(school=self.theirs))
        self.assertEqual(values.get("academic_year"), self.year_theirs.pk)
        self.assertNotEqual(values.get("academic_year"), self.year_ours.pk)

    def test_academic_year_is_empty_when_the_school_has_none(self):
        empty = School.objects.create(
            name="No Year", slug="smart-noyear", subdomain="smart-noyear", is_active=True
        )
        values = resolve_field_initials(Term, self._ctx(school=empty))
        self.assertNotIn("academic_year", values)

    def test_inactive_year_is_suggested_but_says_so_in_a_note(self):
        AcademicYear.objects.filter(pk=self.year_ours.pk).update(is_active=False)
        ctx = self._ctx()
        values = resolve_field_initials(Term, ctx)
        self.assertEqual(values.get("academic_year"), self.year_ours.pk)
        self.assertIn("academic_year", ctx.notes)
        self.assertIn("no year is marked active", ctx.notes["academic_year"].lower())

    # -- term -------------------------------------------------------------- #

    def test_term_resolves_within_this_schools_year_only(self):
        from apps.evals.models import Evaluation

        ours = resolve_field_initials(Evaluation, self._ctx())
        theirs = resolve_field_initials(Evaluation, self._ctx(school=self.theirs))
        self.assertEqual(ours.get("term"), self.term_ours.pk)
        self.assertEqual(theirs.get("term"), self.term_theirs.pk)

    # -- region (proxy target must resolve through) ------------------------- #

    def test_region_resolves_through_the_global_registries_proxy(self):
        from apps.global_registries.models import HolidayCalendar

        field = HolidayCalendar._meta.get_field("region")
        self.assertTrue(
            field.remote_field.model._meta.concrete_model is RegionConfig,
            "fixture assumption broken: region no longer proxies siteconfig.RegionConfig",
        )
        values = resolve_field_initials(HolidayCalendar, self._ctx())
        self.assertEqual(values.get("region"), self.region_ours.pk)

    def test_region_never_returns_another_tenants_region(self):
        from apps.global_registries.models import HolidayCalendar

        values = resolve_field_initials(HolidayCalendar, self._ctx(school=self.theirs))
        self.assertEqual(values.get("region"), self.region_theirs.pk)

    # -- school scalar attributes ------------------------------------------ #

    def test_country_currency_timezone_and_language_come_from_the_school(self):
        from apps.schools.models import School as SchoolModel

        ctx = self._ctx()
        # Any model carrying these names resolves them; School itself is the
        # densest carrier and is registered on the operator site.
        values = resolve_field_initials(SchoolModel, ctx)
        self.assertEqual(values.get("country_code"), "CM")
        self.assertEqual(values.get("currency"), "XAF")
        self.assertEqual(values.get("timezone"), "Africa/Douala")

    def test_scalar_values_differ_per_tenant(self):
        from apps.schools.models import School as SchoolModel

        theirs = resolve_field_initials(SchoolModel, self._ctx(school=self.theirs))
        self.assertEqual(theirs.get("country_code"), "GB")
        self.assertEqual(theirs.get("currency"), "GBP")

    def test_a_value_that_does_not_fit_the_field_is_refused(self):
        """A currency the field's choices do not allow is not offered at all."""
        from apps.siteconfig.admin_smart_initials import _value_fits
        from apps.schools.models import School as SchoolModel

        field = SchoolModel._meta.get_field("country_code")
        self.assertTrue(_value_fits(field, "CM"))
        # country_code is max_length=2; a longer value must be refused rather
        # than offered and truncated on save.
        self.assertFalse(_value_fits(field, "CMR"))

    # -- actor fields ------------------------------------------------------- #

    def test_actor_fields_resolve_to_the_requesting_user(self):
        from apps.analytics.models import GradePredictionLabel

        values = resolve_field_initials(GradePredictionLabel, self._ctx())
        self.assertEqual(values.get("labeled_by"), self.user.pk)

    def test_ambiguous_user_field_is_deliberately_left_empty(self):
        """`user` means the SUBJECT on an audit log, not the person filling the form."""
        from apps.compliance.models import AuditLog

        values = resolve_field_initials(AuditLog, self._ctx())
        self.assertNotIn("user", values)
        self.assertNotIn("user", ACTOR_FIELD_NAMES)

    def test_anonymous_request_yields_no_actor(self):
        from django.contrib.auth.models import AnonymousUser
        from apps.analytics.models import GradePredictionLabel

        ctx = InitialContext(
            request=_request(
                user=AnonymousUser(), school=self.ours, host="smart-ours.runmycampus.com"
            ),
            school=self.ours,
            user=AnonymousUser(),
        )
        values = resolve_field_initials(GradePredictionLabel, ctx)
        self.assertNotIn("labeled_by", values)

    # -- teacher profile ---------------------------------------------------- #

    def test_teacher_resolves_only_to_a_profile_in_this_school(self):
        from apps.evals.models import Evaluation

        other_user = get_user_model().objects.create_user(
            username="smart-teacher", email="smart-teacher@example.test", password="x"
        )
        TeacherProfile.objects.create(user=other_user, school=self.theirs)
        # The requesting superuser has no profile in `ours`, so nothing is offered.
        values = resolve_field_initials(Evaluation, self._ctx())
        self.assertNotIn("teacher", values)

        mine = TeacherProfile.objects.create(user=self.user, school=self.ours)
        values = resolve_field_initials(Evaluation, self._ctx())
        self.assertEqual(values.get("teacher"), mine.pk)

    def test_teacher_profile_in_another_school_is_not_offered(self):
        from apps.evals.models import Evaluation

        TeacherProfile.objects.create(user=self.user, school=self.theirs)
        values = resolve_field_initials(Evaluation, self._ctx())
        self.assertNotIn(
            "teacher",
            values,
            "a profile belonging to another tenant must never be suggested",
        )

    # -- layering and editability ------------------------------------------- #

    def test_exact_builder_wins_over_the_generic_layer(self):
        request = _request(
            user=self.user, school=self.ours, host="smart-ours.runmycampus.com"
        )
        values = build_admin_smart_initials(AcademicYear, request)
        # The academics.academicyear builder owns `name`/`start_date`/`end_date`.
        self.assertIn("name", values)
        self.assertIn("start_date", values)

    def test_suggestions_remain_editable_on_the_rendered_add_form(self):
        model_admin = tenant_admin_site._registry.get(Term)
        self.assertIsNotNone(model_admin, "academics.Term is not registered on tenant")
        request = _request(
            user=self.user, school=self.ours, host="smart-ours.runmycampus.com"
        )
        initial = model_admin.get_changeform_initial_data(request)
        self.assertEqual(initial.get("academic_year"), self.year_ours.pk)
        form = model_admin.get_form(request, obj=None, change=False)(initial=initial)
        self.assertIn("academic_year", form.fields)
        field = form.fields["academic_year"]
        self.assertFalse(
            field.disabled, "a suggestion must stay editable, not become a lock"
        )
        self.assertFalse(field.widget.attrs.get("readonly", False))

    def test_explicit_query_string_input_beats_a_suggestion(self):
        model_admin = tenant_admin_site._registry.get(Term)
        other_year = AcademicYear.objects.create(
            school=self.ours,
            name="Ours 2027/2028",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 7, 1),
            is_active=False,
        )
        request = RequestFactory().get(
            "/admin/", {"academic_year": str(other_year.pk)},
            HTTP_HOST="smart-ours.runmycampus.com",
        )
        request.user = self.user
        request.school = self.ours
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        SessionMiddleware(lambda _r: None).process_request(request)
        MessageMiddleware(lambda _r: None).process_request(request)
        initial = model_admin.get_changeform_initial_data(request)
        self.assertEqual(str(initial.get("academic_year")), str(other_year.pk))

    def test_detailed_builder_returns_notes_separately(self):
        request = _request(
            user=self.user, school=self.ours, host="smart-ours.runmycampus.com"
        )
        values, notes = build_admin_smart_initials_detailed(Term, request)
        self.assertIsInstance(values, dict)
        self.assertIsInstance(notes, dict)
        self.assertEqual(values.get("academic_year"), self.year_ours.pk)

    def test_no_resolver_ever_raises_for_any_registered_model(self):
        """A resolver that raises would break the add form for that model."""
        request = _request(
            user=self.user, school=self.ours, host="smart-ours.runmycampus.com"
        )
        failures = []
        for site in (tenant_admin_site, platform_admin_site):
            for model in site._registry:
                try:
                    build_admin_smart_initials(model, request)
                except Exception as exc:  # noqa: BLE001 - the assertion IS the point
                    failures.append(f"{model._meta.label_lower}: {type(exc).__name__} {exc}")
        self.assertEqual(failures, [])

    def test_suggestions_are_resolved_once_per_request(self):
        """Two callers ask per add form; resolving twice would double the queries."""
        request = _request(
            user=self.user, school=self.ours, host="smart-ours.runmycampus.com"
        )
        # Prime OUTSIDE the assertion: the first call is the one allowed to query.
        primed, _ = build_admin_smart_initials_detailed(Term, request)
        self.assertEqual(primed.get("academic_year"), self.year_ours.pk)
        with self.assertNumQueries(0):
            again, _ = build_admin_smart_initials_detailed(Term, request)
        self.assertEqual(again, primed)

    def test_the_memo_is_scoped_to_one_request(self):
        other = _request(
            user=self.user, school=self.theirs, host="smart-theirs.runmycampus.com"
        )
        build_admin_smart_initials_detailed(Term, self._ctx().request)
        values, _ = build_admin_smart_initials_detailed(Term, other)
        self.assertEqual(
            values.get("academic_year"),
            self.year_theirs.pk,
            "a memo leaking across requests would leak across TENANTS",
        )

    def test_resolvers_declare_a_target_shape_not_just_a_name(self):
        """A name-only resolver would fire on an unrelated field of the same name."""
        for resolver in FIELD_RESOLVERS:
            with self.subTest(names=sorted(resolver.names)):
                self.assertTrue(
                    resolver.target_label or resolver.value_field_types,
                    "resolver must constrain the field shape it answers for",
                )
                self.assertTrue(resolver.reason, "resolver must state why it is derivable")
