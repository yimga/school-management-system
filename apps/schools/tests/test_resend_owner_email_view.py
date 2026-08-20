"""Operator "resend setup email" button: select who, route each correctly.

The operator picks specific tenant users (owners AND non-owner staff, or any
member by email) instead of blasting every owner. These exercise the view
function directly (the operator gate is applied at the URL layer, like every
other tenant-360 action). Message branches are pinned with the dispatch patched;
the routing + school-scoping invariants run the REAL dispatch with only the mail
send mocked.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.schools.super_views_owner_email import (
    addressable_member_options,
    resend_owner_setup_email_view,
)

_DISPATCH = "apps.schools.super_views_owner_email.dispatch_setup_email_for_users"
_WELCOME = "apps.schools.welcome_email.send_welcome_email"
_CLAIM = "apps.accounts.login_recovery.send_set_password_link"


class ResendSetupEmailViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        slug = f"gil-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name="Gilead", slug=slug, subdomain=slug, is_active=True
        )
        self.operator = User.objects.create_user(
            username="op", email="op@x.com", password="pass12345678",
            is_staff=True, is_superuser=True,
        )

    def _member(self, *, owner=False, role=User.Role.ADMIN, email=None, username=None):
        username = username or f"u-{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(
            username=username,
            email=email if email is not None else f"{uuid.uuid4().hex[:8]}@x.com",
            password="pass12345678",
            role=role,
        )
        SchoolMembership.objects.create(
            user=user, school=self.school, role=role,
            is_school_owner=owner, suspended_at=None,
        )
        return user

    def _post(self, school_id, data=None):
        req = self.factory.post(
            f"/super/schools/{school_id}/resend-owner-setup-email/", data or {}
        )
        req.user = self.operator
        req.session = {}
        req._messages = FallbackStorage(req)
        return req

    def _messages(self, req):
        return [(m.level_tag, str(m)) for m in get_messages(req)]

    # --- gate + not-found -------------------------------------------------

    def test_get_is_not_allowed(self):
        req = self.factory.get(f"/super/schools/{self.school.pk}/resend-owner-setup-email/")
        req.user = self.operator
        resp = resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        self.assertEqual(resp.status_code, 405)

    def test_unknown_school_errors_to_dashboard(self):
        req = self._post(uuid.uuid4())
        resp = resend_owner_setup_email_view(req, school_id=str(uuid.uuid4()))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("super:dashboard"))
        self.assertTrue(any("error" in tag for tag, _m in self._messages(req)))

    # --- message branches (dispatch patched) ------------------------------

    def test_success_message_and_redirect(self):
        req = self._post(self.school.pk)
        with mock.patch(
            _DISPATCH,
            return_value={"found": True, "recipients": 2, "sent": 2, "configured": True},
        ) as disp:
            resp = resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        disp.assert_called_once()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url, reverse("super:tenant_360", args=[str(self.school.pk)])
        )
        msgs = self._messages(req)
        self.assertTrue(any("success" in tag for tag, _m in msgs))
        self.assertTrue(any("2 recipient" in m for _t, m in msgs))

    def test_not_configured_warns_honestly(self):
        req = self._post(self.school.pk)
        with mock.patch(
            _DISPATCH,
            return_value={"found": True, "recipients": 1, "sent": 0, "configured": False},
        ):
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        msgs = self._messages(req)
        self.assertTrue(any("warning" in tag for tag, _m in msgs))
        self.assertTrue(any("EMAIL_HOST_USER" in m for _t, m in msgs))

    def test_no_recipients_warns(self):
        req = self._post(self.school.pk)
        with mock.patch(
            _DISPATCH,
            return_value={"found": True, "recipients": 0, "sent": 0, "configured": True},
        ):
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        msgs = self._messages(req)
        self.assertTrue(any("warning" in tag for tag, _m in msgs))
        self.assertTrue(any("No matching recipient" in m for _t, m in msgs))

    def test_selection_passes_user_ids_and_request(self):
        owner_a = self._member(owner=True)
        self._member(owner=True)
        req = self._post(self.school.pk, {"user_ids": [str(owner_a.pk)]})
        with mock.patch(
            _DISPATCH,
            return_value={"found": True, "recipients": 1, "sent": 1, "configured": True},
        ) as disp:
            resp = resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        disp.assert_called_once_with(self.school, user_ids=[owner_a.pk], request=req)
        self.assertEqual(resp.status_code, 302)

    def test_legacy_owner_user_ids_field_still_honored(self):
        owner_a = self._member(owner=True)
        req = self._post(self.school.pk, {"owner_user_ids": [str(owner_a.pk)]})
        with mock.patch(
            _DISPATCH,
            return_value={"found": True, "recipients": 1, "sent": 1, "configured": True},
        ) as disp:
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        disp.assert_called_once_with(self.school, user_ids=[owner_a.pk], request=req)

    # --- real dispatch: routing owner vs non-owner ------------------------

    def test_owner_selected_gets_welcome_email(self):
        owner = self._member(owner=True, email="owner@x.com")
        req = self._post(self.school.pk, {"user_ids": [str(owner.pk)]})
        with mock.patch(_WELCOME, return_value=True) as welcome, mock.patch(
            _CLAIM, return_value=True
        ) as claim:
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        welcome.assert_called_once_with(str(self.school.pk), "owner@x.com")
        claim.assert_not_called()

    def test_non_owner_selected_gets_claim_link(self):
        teacher = self._member(owner=False, role=User.Role.TEACHER, email="t@x.com")
        req = self._post(self.school.pk, {"user_ids": [str(teacher.pk)]})
        with mock.patch(_WELCOME, return_value=True) as welcome, mock.patch(
            _CLAIM, return_value=True
        ) as claim:
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        # Teacher gets the generic set-password/claim link, NOT the owner welcome.
        claim.assert_called_once()
        self.assertEqual(claim.call_args.args[1], teacher)
        welcome.assert_not_called()

    def test_owner_and_non_owner_route_differently_in_one_send(self):
        owner = self._member(owner=True, email="owner@x.com")
        teacher = self._member(owner=False, role=User.Role.TEACHER, email="t@x.com")
        req = self._post(
            self.school.pk, {"user_ids": [str(owner.pk), str(teacher.pk)]}
        )
        with mock.patch(_WELCOME, return_value=True) as welcome, mock.patch(
            _CLAIM, return_value=True
        ) as claim:
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        welcome.assert_called_once_with(str(self.school.pk), "owner@x.com")
        claim.assert_called_once()
        self.assertEqual(claim.call_args.args[1], teacher)

    def test_default_no_selection_sends_to_owners_only(self):
        # Must exist to be mailed; the assertion inspects the mock, not this row.
        self._member(owner=True, email="owner@x.com")
        self._member(owner=False, role=User.Role.TEACHER)  # must NOT be mailed
        req = self._post(self.school.pk)  # nothing selected, no typed address
        with mock.patch(_WELCOME, return_value=True) as welcome, mock.patch(
            _CLAIM, return_value=True
        ) as claim:
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        welcome.assert_called_once_with(str(self.school.pk), "owner@x.com")
        claim.assert_not_called()

    # --- the email box (target anyone) ------------------------------------

    def test_email_box_targets_a_specific_parent(self):
        parent = self._member(owner=False, role=User.Role.PARENT, email="mum@x.com")
        req = self._post(self.school.pk, {"recipient_identifier": "MUM@x.com"})
        with mock.patch(_WELCOME, return_value=True) as welcome, mock.patch(
            _CLAIM, return_value=True
        ) as claim:
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        claim.assert_called_once()
        self.assertEqual(claim.call_args.args[1], parent)
        welcome.assert_not_called()

    def test_email_box_matches_by_username(self):
        member = self._member(owner=False, role=User.Role.TEACHER, username="jdoe")
        req = self._post(self.school.pk, {"recipient_identifier": "jdoe"})
        with mock.patch(_WELCOME, return_value=True), mock.patch(
            _CLAIM, return_value=True
        ) as claim:
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        claim.assert_called_once()
        self.assertEqual(claim.call_args.args[1], member)

    def test_unmatched_email_box_warns_and_sends_nothing(self):
        req = self._post(self.school.pk, {"recipient_identifier": "stranger@nowhere.io"})
        with mock.patch(_DISPATCH) as disp:
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        disp.assert_not_called()  # returns early — nothing dispatched
        msgs = self._messages(req)
        self.assertTrue(any("warning" in tag for tag, _m in msgs))
        self.assertTrue(any("No member of this school matches" in m for _t, m in msgs))

    # --- security: school-scoping -----------------------------------------

    def test_foreign_user_id_cannot_be_addressed(self):
        # A user who belongs to ANOTHER school must not receive mail just because
        # their id is POSTed to THIS school's resend action.
        other = School.objects.create(
            name="Other", slug=f"oth-{uuid.uuid4().hex[:6]}",
            subdomain=f"oth-{uuid.uuid4().hex[:6]}", is_active=True,
        )
        outsider = User.objects.create_user(
            username="outsider", email="out@x.com", password="pass12345678",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=outsider, school=other, role=User.Role.ADMIN, is_school_owner=True,
        )
        req = self._post(self.school.pk, {"user_ids": [str(outsider.pk)]})
        with mock.patch(_WELCOME, return_value=True) as welcome, mock.patch(
            _CLAIM, return_value=True
        ) as claim:
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        welcome.assert_not_called()
        claim.assert_not_called()
        self.assertTrue(
            any("No matching recipient" in m for _t, m in self._messages(req))
        )

    def test_email_box_cannot_reach_a_non_member(self):
        # An address that belongs to a real user who is NOT a member here resolves
        # to nobody — the operator can only address members of this school.
        User.objects.create_user(
            username="ghost", email="ghost@x.com", password="pass12345678",
        )
        req = self._post(self.school.pk, {"recipient_identifier": "ghost@x.com"})
        with mock.patch(_DISPATCH) as disp:
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        disp.assert_not_called()


class AddressableMemberOptionsTests(TestCase):
    def setUp(self):
        slug = f"gil-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name="Gilead", slug=slug, subdomain=slug, is_active=True
        )

    def _member(self, role, *, owner=False, suspended=False):
        user = User.objects.create_user(
            username=f"u-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@x.com",
            password="pass12345678", role=role,
        )
        from django.utils import timezone

        SchoolMembership.objects.create(
            user=user, school=self.school, role=role, is_school_owner=owner,
            suspended_at=timezone.now() if suspended else None,
        )
        return user

    def test_picker_lists_staff_and_owners_but_not_students_or_parents(self):
        owner = self._member(User.Role.ADMIN, owner=True)
        teacher = self._member(User.Role.TEACHER)
        self._member(User.Role.STUDENT)
        self._member(User.Role.PARENT)
        rows, truncated = addressable_member_options(self.school)
        pks = {r["pk"] for r in rows}
        self.assertIn(owner.pk, pks)
        self.assertIn(teacher.pk, pks)
        self.assertEqual(len(rows), 2)  # student + parent excluded
        self.assertFalse(truncated)
        # Owner sorts first and is flagged.
        self.assertEqual(rows[0]["pk"], owner.pk)
        self.assertTrue(rows[0]["is_owner"])

    def test_picker_excludes_suspended_members(self):
        self._member(User.Role.ADMIN, owner=True, suspended=True)
        rows, _truncated = addressable_member_options(self.school)
        self.assertEqual(rows, [])
