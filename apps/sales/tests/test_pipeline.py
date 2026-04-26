"""
Manager-host CRM: ``ReservedPublicHostAccessMiddleware`` only allows paths in
``MANAGER_HOST_ALLOWED_PREFIXES`` (``apps.schools.middleware``). ``/sales/`` must stay
listed or requests are redirected to ``/`` before views run — regression tests below.
"""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.sales.models import ActivityLog, Lead, PipelineStage
from apps.accounts.models import User

_MANAGER = "config.manager_urls"


# Match control-plane E2E pattern (e.g. siteconfig entity_catalog on manager):
# do NOT set ROOT_URLCONF globally — UrlConfSwitcher sets request.urlconf from HTTP_HOST;
# a forced ROOT_URLCONF can fight middleware and produce redirects (e.g. to /).
@override_settings(
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ALLOWED_HOSTS=[
        "testserver",
        "127.0.0.1",
        "localhost",
        "manager.runmycampus.com",
    ],
)
class SalesPipelineViewTests(TestCase):
    """Manager /sales/ with host manager.runmycampus.com and control-plane user."""

    _HOST = "manager.runmycampus.com"

    @classmethod
    def setUpTestData(cls):
        cls.mgr = User.objects.create_user(
            username="sales_mer",
            email="ops@e.test",
            password="p" * 8,
            is_staff=True,
            is_superuser=True,
        )
        # Idempotent with sales.0001_initial RunPython seed (covers --keepdb without re-run).
        for key, label, so in [
            ("lead", "Lead", 1),
            ("contacted", "Contacted", 2),
            ("demo", "Demo", 3),
            ("pilot", "Pilot", 4),
            ("onboarded", "Onboarded", 5),
        ]:
            PipelineStage.objects.get_or_create(
                key=key, defaults={"label": label, "sort_order": so}
            )

    def test_pipeline_stage_seed_is_idempotent(self):
        """Re-running the migration-style seed must not duplicate rows or explode."""
        before = PipelineStage.objects.count()
        self.assertGreaterEqual(before, 5)
        for key, label, so in [
            ("lead", "Lead", 1),
            ("contacted", "Contacted", 2),
            ("demo", "Demo", 3),
            ("pilot", "Pilot", 4),
            ("onboarded", "Onboarded", 5),
        ]:
            _, created = PipelineStage.objects.get_or_create(
                key=key, defaults={"label": label, "sort_order": so}
            )
            self.assertFalse(created)
        self.assertEqual(PipelineStage.objects.count(), before)
        self.assertTrue(PipelineStage.objects.filter(key="lead").exists())

    def setUp(self):
        self.client = Client(HTTP_HOST=self._HOST, raise_request_exception=True)
        self.assertTrue(
            self.client.login(username="sales_mer", password="p" * 8),
            "login failed for control-plane test user",
        )

    def test_pipeline_board_requires_control_plane(self):
        u = User.objects.create_user(
            username="pl_teacher", email="t@e.test", password="p" * 8
        )
        c = Client(HTTP_HOST=self._HOST)
        c.force_login(u)
        url = reverse("sales:pipeline_board", urlconf=_MANAGER)
        r = c.get(url)
        self.assertIn(r.status_code, (302, 403))

    def test_pipeline_board_200_for_superuser(self):
        url = reverse("sales:pipeline_board", urlconf=_MANAGER)
        r = self.client.get(url)
        if r.status_code != 200:
            loc = r.get("Location", "")
            self.fail(
                f"expected 200, got {r.status_code} loc={loc!r} body={r.content[:500]!r}"
            )

    def test_sales_lead_create_path_not_manager_home_redirect(self):
        """
        Second route under /sales/ (not only pipeline_board): must hit the view, not 302 to /.
        Catches allowlist gaps that would send all /sales/ traffic to manager root.
        """
        url = reverse("sales:lead_create", urlconf=_MANAGER)
        r = self.client.get(url)
        self.assertEqual(
            r.status_code,
            200,
            msg=(
                f"expected 200 for {url!r}; "
                f"if 302 to /, check MANAGER_HOST_ALLOWED_PREFIXES includes /sales/"
            ),
        )

    def test_lead_create_and_detail_flow(self):
        st = PipelineStage.objects.get(key="lead")
        lead = Lead.objects.create(
            school_name="Lincoln",
            contact_name="Pat",
            email="p@lincoln.school",
            stage=st,
        )
        du = reverse("sales:lead_detail", args=[lead.pk], urlconf=_MANAGER)
        r = self.client.get(du)
        self.assertEqual(r.status_code, 200)
        r2 = self.client.post(
            du,
            {
                "save_lead": "1",
                "stage_id": st.pk,
                "notes": "ok",
            },
        )
        self.assertEqual(r2.status_code, 302)
        r3 = self.client.post(
            du,
            {"add_activity": "1", "body": "Call notes"},
        )
        self.assertEqual(r3.status_code, 302)
        self.assertTrue(
            ActivityLog.objects.filter(lead_id=lead.pk, body="Call notes").exists()
        )
