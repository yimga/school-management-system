"""Operator checklists embedded on super templates (wedges 7+ surfaces)."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.test_utils.http_clients import login_manager_client


@override_settings(ALLOWED_HOSTS=["*"])
class OperatorWedgeChecklistTemplateTests(TestCase):
    """GET super wedge pages and assert checklist markup is present."""

    host = "manager.runmycampus.com"

    def setUp(self):
        self.user = User.objects.create_user(
            username="op_checklist_tpl",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        # Manager host reads MANAGER_SESSION_COOKIE_NAME and operators carry
        # baseline strict MFA; a bare force_login 302s to mfa/setup. Arm the
        # manager client (confirmed device + manager session + mfa_verified).
        self.client = login_manager_client(
            self.user, password="testpass123", host=self.host
        )
        cache.clear()

    def _get(self, url_name, **query):
        url = reverse(url_name)
        if query:
            url = url + "?" + "&".join(f"{k}={v}" for k, v in query.items())
        return self.client.get(url, HTTP_HOST=self.host)

    def test_geography_checklist_wedge_query(self):
        r = self._get("super:geography", wedge=9)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-operator-checklist-wedge="9"')
        self.assertContains(r, "W9 Europe")

    def test_education_systems_includes_checklist(self):
        r = self._get("super:education_systems", wedge=17)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Operator checklist")

    def test_learning_delivery_includes_checklist(self):
        r = self._get("super:learning_delivery_packs", wedge=28)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Operator checklist")

    def test_ministry_stubs_includes_checklist(self):
        r = self._get("super:ministry_report_stubs", wedge=35)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Operator checklist")

    def test_group_campuses_wedge_22_checklist(self):
        r = self._get("super:group_campuses")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-operator-checklist-wedge="22"')

    def test_trust_center_wedge_45_checklist(self):
        r = self._get("super:trust_center")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-operator-checklist-wedge="45"')

    def test_one_sis_shows_wedge_2_and_44(self):
        r = self._get("super:one_sis_any_lms")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-operator-checklist-wedge="2"')
        self.assertContains(r, 'data-operator-checklist-wedge="44"')

    def test_curriculum_packs_wedge_1_and_3_switcher(self):
        r1 = self._get("super:curriculum_packs")
        self.assertEqual(r1.status_code, 200)
        self.assertContains(r1, 'data-operator-checklist-wedge="1"')
        r3 = self._get("super:curriculum_packs", wedge=3)
        self.assertEqual(r3.status_code, 200)
        self.assertContains(r3, 'data-operator-checklist-wedge="3"')
        self.assertContains(r3, "W3 UK / British")
