"""Clearing an optional JSON box on an admin form returned a 500.

Reported from production: ``/admin/people/studentprofile/add/`` answered 500
"service interrupted" when a student was saved.  The page itself is healthy --
GET renders, and a Save that leaves the form alone succeeds -- which is why
every existing add-form check passed against a surface that was breaking for
real users.

The trigger is emptying the "Custom attributes" box.  ``StudentProfile.
custom_attributes`` is ``JSONField(default=dict, blank=True)``: ``blank=True``
makes the form field optional, ``forms.JSONField`` returns None for empty
input, the ModelForm writes that None over the model default, and the INSERT
sends NULL to a NOT NULL column.  Django 5.2 wraps the non-GET changeform in
``transaction.atomic``, so the ``IntegrityError`` surfaces as an uncaught 500
rather than a form error.

Measured on the add form before the fix:

    omitted        -> 302, row created
    ``{}``         -> 302, row created     (the value the box renders holding)
    empty          -> 500 IntegrityError   (the box was cleared)
    whitespace     -> 200, validation error

496 fields across 42 apps share ``JSONField(default=..., blank=True)`` with
``null=False``, so the coercion lives in the shared form-policy mixin that
``BaseRunMyCampusAdminSite.register`` injects into every registration rather
than on this one model.

These tests POST the real form through the real tenant urlconf.  A source
assertion would not do: the pre-fix view returns 200 for whitespace and 302 for
an untouched save, so only an actual cleared-box POST distinguishes fixed from
broken.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership

_URLCONF = "config.tenant_urls"

# The MFA ENROLMENT gate redirects a device-less principal before the changeform
# runs, so the POST would land on that redirect instead of the admin.
_MW = [
    m
    for m in settings.MIDDLEWARE
    if "RequireMFAMiddleware" not in m and "OperatorMfaRequiredMiddleware" not in m
]


def _url(name, *args):
    return reverse(name, args=list(args) or None, urlconf=_URLCONF)


@override_settings(ROOT_URLCONF=_URLCONF, MIDDLEWARE=_MW)
class ClearedJsonBoxSavesTheDefaultTests(TestCase):
    """An emptied optional JSON box stores the model default, not NULL."""

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"JSON Default {uid}",
            slug=f"json-default-{uid}",
            subdomain=f"jsondefault{uid}",
            is_active=True,
        )
        self.root = User.objects.create_superuser(
            username=f"root_{uid}",
            password="Test1234!x",
            email=f"r{uid}@test.com",
        )
        SchoolMembership.objects.create(
            user=self.root, school=self.school, role="ADMIN", is_primary=True
        )
        self.host = f"{self.school.subdomain}.runmycampus.com"
        self.add_url = _url("admin:people_studentprofile_add")

    def _login(self):
        self.client.force_login(self.root)
        session = self.client.session
        session["mfa_verified"] = True
        session["school_id"] = str(self.school.id)
        session.save()

    def _payload(self, **overrides):
        payload = {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "student_code": "",
            "admission_number": "",
            "academic_year": "",
            "classroom": "",
            "specialty": "",
            "status": "NEW",
            "section": "",
            "gender": "",
            "date_of_birth": "",
            "place_of_birth": "",
            "joined_term": "",
            "joined_date": "",
            "parent_phone": "",
            "referral_code": "",
            "is_active": "on",
            "guardian_links-TOTAL_FORMS": "0",
            "guardian_links-INITIAL_FORMS": "0",
            "guardian_links-MIN_NUM_FORMS": "0",
            "guardian_links-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }
        payload.update(overrides)
        return payload

    def test_clearing_the_json_box_saves_instead_of_500(self):
        """The reported failure: the box is emptied and Save is pressed."""
        self._login()
        before = StudentProfile.objects.count()
        resp = self.client.post(
            self.add_url,
            self._payload(custom_attributes=""),
            HTTP_HOST=self.host,
        )
        self.assertEqual(
            resp.status_code,
            302,
            "clearing an optional JSON box must save, not raise IntegrityError",
        )
        self.assertEqual(StudentProfile.objects.count(), before + 1)
        student = StudentProfile.objects.order_by("-id").first()
        self.assertEqual(
            student.custom_attributes,
            {},
            "the cleared box must store the model default, never NULL",
        )
        self.assertIsNotNone(student.custom_attributes)

    def test_a_real_json_value_is_still_stored(self):
        """The coercion must not flatten data someone actually typed."""
        self._login()
        resp = self.client.post(
            self.add_url,
            self._payload(
                last_name="Hopper", custom_attributes='{"house": "Blue", "bus": 3}'
            ),
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 302)
        student = StudentProfile.objects.order_by("-id").first()
        self.assertEqual(student.custom_attributes, {"house": "Blue", "bus": 3})

    def test_invalid_json_is_still_a_form_error_not_a_save(self):
        """Coercing empty must not also swallow genuinely bad input."""
        self._login()
        before = StudentProfile.objects.count()
        resp = self.client.post(
            self.add_url,
            self._payload(last_name="Babbage", custom_attributes="   "),
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, "invalid JSON must re-render the form")
        self.assertEqual(StudentProfile.objects.count(), before)

    def test_an_untouched_form_still_saves(self):
        """The path that always worked must keep working."""
        self._login()
        before = StudentProfile.objects.count()
        resp = self.client.post(
            self.add_url,
            self._payload(last_name="Turing", custom_attributes="{}"),
            HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(StudentProfile.objects.count(), before + 1)


class CoercionIsScopedToNotNullDefaultedFieldsTests(TestCase):
    """A ``null=True`` JSON field legitimately stores NULL and is left alone."""

    def test_nullable_json_field_is_not_coerced(self):
        from django.db import models as dj_models

        from apps.siteconfig.admin_form_intelligence import _json_empty_means_default

        class _FormField:
            def clean(self, value):
                return None

        nullable = dj_models.JSONField(null=True, default=dict)
        formfield = _FormField()
        _json_empty_means_default(nullable, formfield)
        # The helper coerces by setting an INSTANCE attribute over the bound
        # method.  Comparing ``formfield.clean`` to a saved reference cannot
        # detect that -- attribute access builds a fresh bound-method object
        # every time, so ``is`` is False even when nothing was touched.
        self.assertNotIn(
            "clean",
            vars(formfield),
            "a nullable JSON field must keep NULL as a legal value",
        )
        self.assertIsNone(formfield.clean(""))

    def test_not_null_defaulted_field_is_coerced(self):
        from django.db import models as dj_models

        from apps.siteconfig.admin_form_intelligence import _json_empty_means_default

        class _FormField:
            def clean(self, value):
                return None

        field = dj_models.JSONField(default=dict)
        formfield = _FormField()
        _json_empty_means_default(field, formfield)
        self.assertEqual(formfield.clean(""), {})
