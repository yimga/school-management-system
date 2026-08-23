"""Saving a lead must not silently drop its deal owner.

``lead_detail`` renders the owner picker from the first 200 ``is_staff`` users by
username::

    staff_owners = list(User.objects.filter(is_staff=True).order_by("username", "pk")[:200])

and the template marks an option ``selected`` only when it matches
``lead.deal_owner_id``. An owner who sorts outside that window therefore has NO
option in the list, so nothing is selected, the browser posts the blank first
option, and the POST handler does::

    deal_owner_id = (request.POST.get("deal_owner_id") or "").strip()
    if deal_owner_id.isdigit():
        lead.deal_owner = User.objects.filter(pk=int(deal_owner_id), is_staff=True).first()
    else:
        lead.deal_owner = None

-- clearing the owner. Editing an unrelated field (a note, a decision maker) is
enough to lose the assignment, with no error and nothing in the log.

The truncation is invisible until a platform passes 200 staff accounts, which is
exactly when a CRM starts to matter. Note the picker is NOT school-scoped either;
that is a separate question and is deliberately not changed here.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.sales import views as sales_views
from apps.sales.models import Lead, PipelineStage

_MANAGER_HOST = "manager.runmycampus.com"


# apps.sales is mounted ONLY on the manager host (config/manager_urls.py), so the
# default ROOT_URLCONF cannot resolve `sales:` at all -- and pinning ROOT_URLCONF
# is not enough either, because UrlConfSwitcherMiddleware picks the urlconf from
# the HOST. The client has to speak to the manager host, like the operator does.
@override_settings(ROOT_URLCONF="config.manager_urls", ALLOWED_HOSTS=["*"])
class DealOwnerSurvivesSaveTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(
            username="crm-actor", password="x", is_staff=True
        )
        # Sorts LAST by username, so a truncated picker drops this one.
        self.owner = User.objects.create_user(
            username="zzz-owner", password="x", is_staff=True
        )
        User.objects.create_user(username="aaa-other", password="x", is_staff=True)
        self.stage = PipelineStage.objects.create(key="discovery", label="Discovery", sort_order=1)
        self.lead = Lead.objects.create(
            school_name="Acme High", stage=self.stage, deal_owner=self.owner
        )
        # is_staff is NOT control-plane access -- the platform mints is_staff=True
        # TENANT admins, so the manager host refuses them. Operators are identified
        # by an active PlatformOperatorProfile.
        from apps.platform_runtime.models_operator_identity import (
            PlatformOperatorProfile,
        )

        PlatformOperatorProfile.objects.create(
            user=self.actor, status=PlatformOperatorProfile.Status.ACTIVE
        )
        self.client = self.client_class(HTTP_HOST=_MANAGER_HOST)
        self.client.force_login(self.actor)

    def _url(self):
        return reverse("sales:lead_detail", kwargs={"pk": self.lead.pk})

    def test_the_page_renders_and_the_fixture_owner_is_set(self):
        # Calibration: everything below is meaningless if the page 403s or the
        # fixture never had an owner.
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.deal_owner_id, self.owner.pk)

    def test_the_current_owner_is_always_offered_even_when_the_list_truncates(self):
        with mock.patch.object(sales_views, "_OWNER_PICKER_LIMIT", 1):
            response = self.client.get(self._url())
        offered = {u.pk for u in response.context["staff_owners"]}
        self.assertIn(
            self.owner.pk,
            offered,
            "the assigned owner must appear in the picker, or the browser posts a "
            "blank and the next save clears them",
        )

    def test_a_save_that_omits_the_field_keeps_the_owner(self):
        """A form that does not carry the select must not mean 'unassign'."""
        response = self.client.post(
            self._url(), {"save_lead": "1", "decision_maker": "Head of ICT"}
        )
        self.assertEqual(response.status_code, 302)
        self.lead.refresh_from_db()
        self.assertEqual(
            self.lead.deal_owner_id,
            self.owner.pk,
            "editing an unrelated field silently unassigned the lead",
        )
        self.assertEqual(self.lead.decision_maker, "Head of ICT")

    def test_an_explicit_blank_still_clears_the_owner(self):
        """Unassigning deliberately must keep working."""
        response = self.client.post(
            self._url(), {"save_lead": "1", "deal_owner_id": ""}
        )
        self.assertEqual(response.status_code, 302)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.deal_owner_id)

    def test_an_explicit_owner_is_still_assignable(self):
        other = User.objects.get(username="aaa-other")
        self.client.post(
            self._url(), {"save_lead": "1", "deal_owner_id": str(other.pk)}
        )
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.deal_owner_id, other.pk)
