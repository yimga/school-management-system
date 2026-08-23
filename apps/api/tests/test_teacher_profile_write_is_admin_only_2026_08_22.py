"""A teacher must not be able to write their own salary or authority flags.

``TeacherProfileViewSet`` is a full ``ModelViewSet`` with
``permission_classes = [IsAuthenticated]`` and no override of
create/update/partial_update/destroy. It DEFINES ``_require_admin`` -- and never
calls it. Its own docstring says "admin-only writes" and its
``@extend_schema_view`` block advertises 403 on every write, so the schema, the
docstring and the helper all describe a gate that does not exist.

``get_queryset`` deliberately returns the caller's OWN row when their role is
TEACHER (correct, for self-read), so ``get_object()`` succeeds on it and the
write lands. ``TeacherProfileSerializer`` exposes ``salary_amount``,
``salary_cap``, ``pay_grade``, ``next_pay_date``, ``payment_method`` and the
three ``allow_*`` authority flags as writable:

  * ``allow_finance_panel``   gates the teacher payroll block
  * ``allow_leave_approvals`` confers approval authority
  * ``salary_amount``         is the gross-pay source in payroll

``apps/api/sync_services.py`` names those three flags as authority fields the
sync path must protect. The REST path did not protect them, on either route --
``/api/entities/teachers/<pk>/`` and ``/api/v1/people/teachers/<pk>/`` are the
same viewset.

``TeacherProfile.school`` is ``null=True``, and ``create`` was ungated too, so
any authenticated member could POST a school-less row.

Two independent layers are asserted here, because either alone leaves a hole:
the viewset gate (a non-admin cannot write at all) and the serializer's
read_only_fields (nothing can set an authority field through this serializer,
including the subclassed V1 viewset and any future caller).
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.people.models import TeacherProfile
from apps.schools.models import School

WRITE_ROUTES = ["/api/entities/teachers/", "/api/v1/people/teachers/"]


class TeacherProfileWriteIsAdminOnlyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Escalation High",
            slug=f"esc-{uuid.uuid4().hex[:8]}",
            subdomain=f"esc-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        self.teacher_user = User.objects.create_user(
            username=f"teach_{uuid.uuid4().hex[:10]}",
            password="pass",
            role=User.Role.TEACHER,
        )
        self.profile = TeacherProfile.objects.create(
            user=self.teacher_user,
            school=self.school,
            staff_id=f"T-{uuid.uuid4().hex[:6]}",
            salary_amount=Decimal("1000.00"),
            allow_finance_panel=False,
            allow_paystub_access=False,
            allow_leave_approvals=False,
        )
        # HTTP_HOST is load-bearing, not decoration: request.school is resolved
        # from the subdomain, and get_queryset returns .none() without it -- so a
        # test that forgets it 404s on every route and "passes" against
        # vulnerable code. test_teacher_can_still_read_their_own_profile is the
        # guard that proves these requests actually reach the view.
        self.client = APIClient(HTTP_HOST=f"{self.school.subdomain}.runmycampus.com")

    def _authenticate_teacher(self):
        self.client.force_authenticate(user=self.teacher_user)
        session = self.client.session
        session["school_id"] = str(self.school.pk)
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    ESCALATION = {
        "salary_amount": "500000.00",
        "allow_finance_panel": True,
        "allow_paystub_access": True,
        "allow_leave_approvals": True,
    }

    def test_teacher_cannot_patch_their_own_salary_and_authority_flags(self):
        self._authenticate_teacher()
        for route in WRITE_ROUTES:
            with self.subTest(route=route):
                resp = self.client.patch(
                    f"{route}{self.profile.pk}/", self.ESCALATION, format="json"
                )
                self.assertNotEqual(
                    resp.status_code,
                    200,
                    f"{route} accepted a teacher's self-escalation: {resp.content[:300]}",
                )

                self.profile.refresh_from_db()
                self.assertEqual(
                    self.profile.salary_amount,
                    Decimal("1000.00"),
                    "salary_amount is the gross-pay source; a teacher must not set it",
                )
                self.assertFalse(self.profile.allow_finance_panel)
                self.assertFalse(self.profile.allow_paystub_access)
                self.assertFalse(
                    self.profile.allow_leave_approvals,
                    "allow_leave_approvals confers approval authority",
                )

    def test_teacher_cannot_create_a_teacher_profile(self):
        self._authenticate_teacher()
        other = User.objects.create_user(
            username=f"other_{uuid.uuid4().hex[:10]}", password="pass"
        )
        before = TeacherProfile.objects.count()
        for route in WRITE_ROUTES:
            with self.subTest(route=route):
                resp = self.client.post(
                    route,
                    {"user": other.pk, "staff_id": f"X-{uuid.uuid4().hex[:6]}"},
                    format="json",
                )
                self.assertNotIn(resp.status_code, (200, 201), resp.content[:300])
        self.assertEqual(
            TeacherProfile.objects.count(),
            before,
            "TeacherProfile.school is null=True, so an ungated create mints a "
            "school-less row that belongs to no tenant",
        )

    def test_teacher_cannot_delete_their_own_profile(self):
        self._authenticate_teacher()
        resp = self.client.delete(f"/api/entities/teachers/{self.profile.pk}/")
        self.assertNotEqual(resp.status_code, 204, resp.content[:300])
        self.assertTrue(TeacherProfile.objects.filter(pk=self.profile.pk).exists())

    def test_teacher_can_still_read_their_own_profile(self):
        # The gate is on WRITES only; self-read is the documented behaviour and
        # a fix that broke it would be a regression of its own.
        self._authenticate_teacher()
        resp = self.client.get(f"/api/entities/teachers/{self.profile.pk}/")
        self.assertEqual(resp.status_code, 200, resp.content[:300])


class TeacherProfileSerializerAuthorityFieldsTests(TestCase):
    """Second layer: the serializer itself must refuse authority writes."""

    AUTHORITY_FIELDS = [
        "salary_amount",
        "salary_cap",
        "pay_grade",
        "next_pay_date",
        "payment_method",
        "allow_finance_panel",
        "allow_paystub_access",
        "allow_leave_approvals",
    ]

    def test_authority_fields_are_read_only(self):
        from apps.api.serializers import TeacherProfileSerializer

        fields = TeacherProfileSerializer().get_fields()
        for name in self.AUTHORITY_FIELDS:
            with self.subTest(field=name):
                self.assertIn(name, fields, "field must still be READABLE")
                self.assertTrue(
                    fields[name].read_only,
                    f"{name} is an authority/pay field; it must not be writable "
                    "through the generic entity serializer, which V1TeacherViewSet "
                    "also inherits",
                )

    def test_ordinary_fields_are_still_writable(self):
        from apps.api.serializers import TeacherProfileSerializer

        fields = TeacherProfileSerializer().get_fields()
        for name in ("staff_id", "phone", "position_title", "is_active"):
            with self.subTest(field=name):
                self.assertFalse(
                    fields[name].read_only,
                    f"{name} is ordinary profile data; locking it would break "
                    "legitimate admin edits",
                )
