"""Operator "reveal owner setup link": mail-independent owner claim path (G8).

The owner is created with set_unusable_password(); its only claim path is the
signed onboarding token, which normally ships in the welcome email. When mail is
misconfigured or bounces, the owner can never log in. This view surfaces the SAME
signed link for the operator to deliver out of band. Exercised as a view function
(the operator gate is applied at the URL layer, like every other tenant-360
action); a TemplateResponse lets us assert context without rendering the full
operator shell.
"""
from __future__ import annotations

import uuid

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.schools.super_views_owner_email import reveal_owner_setup_link_view


class RevealOwnerSetupLinkViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        slug = f"gil-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name="Gilead", slug=slug, subdomain=slug, is_active=True
        )
        self.operator = User.objects.create_user(
            username="op",
            email="op@x.com",
            password="pass12345678",
            is_staff=True,
            is_superuser=True,
        )

    def _post(self, school_id):
        req = self.factory.post(
            f"/super/schools/{school_id}/reveal-owner-setup-link/"
        )
        req.user = self.operator
        req.session = {}
        req._messages = FallbackStorage(req)
        return req

    def _add_owner(self, email="founder@x.com", *, suspended=False):
        owner = User.objects.create_user(
            username=f"own-{uuid.uuid4().hex[:6]}",
            email=email,
            password="pass12345678",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=owner,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
            is_school_owner=True,
            suspended_at=timezone.now() if suspended else None,
        )
        return owner

    def test_get_is_not_allowed(self):
        req = self.factory.get(
            f"/super/schools/{self.school.pk}/reveal-owner-setup-link/"
        )
        req.user = self.operator
        resp = reveal_owner_setup_link_view(req, school_id=str(self.school.pk))
        self.assertEqual(resp.status_code, 405)

    def test_unknown_school_redirects_to_dashboard(self):
        req = self._post(uuid.uuid4())
        resp = reveal_owner_setup_link_view(req, school_id=str(uuid.uuid4()))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("super:dashboard"))

    def test_active_owner_claim_link_is_revealed(self):
        owner = self._add_owner()
        req = self._post(self.school.pk)
        resp = reveal_owner_setup_link_view(req, school_id=str(self.school.pk))
        self.assertEqual(resp.status_code, 200)
        links = resp.context_data["links"]
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["email"], "founder@x.com")

        # The claim link is the signed onboarding link. Its token is time-based
        # (regenerating gives a fresh valid token), so assert the stable shape:
        # an absolute https URL whose path carries THIS owner's uid segment.
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(owner.pk))
        self.assertTrue(links[0]["url"].startswith("https://"))
        self.assertIn(f"/onboarding/account/{uid}/", links[0]["url"])

    def test_suspended_owner_link_is_not_revealed(self):
        self._add_owner(email="active@x.com")
        self._add_owner(email="suspended@x.com", suspended=True)
        req = self._post(self.school.pk)
        resp = reveal_owner_setup_link_view(req, school_id=str(self.school.pk))
        revealed = {link["email"] for link in resp.context_data["links"]}
        self.assertIn("active@x.com", revealed)
        self.assertNotIn("suspended@x.com", revealed)

    def test_no_active_owner_warns_and_redirects(self):
        req = self._post(self.school.pk)
        resp = reveal_owner_setup_link_view(req, school_id=str(self.school.pk))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url, reverse("super:tenant_360", args=[str(self.school.pk)])
        )

    def test_reveal_is_audited_high_sensitivity(self):
        self._add_owner()
        from apps.compliance.models_audit import AuditLog

        before = AuditLog.objects.count()
        req = self._post(self.school.pk)
        reveal_owner_setup_link_view(req, school_id=str(self.school.pk))
        self.assertEqual(AuditLog.objects.count(), before + 1)
        entry = AuditLog.objects.latest("id")
        self.assertEqual(entry.sensitivity, "HIGH")
        self.assertEqual(entry.action, "READ")
