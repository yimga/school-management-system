"""Tests for the Pressing Issues single-pane-of-glass widget builders."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase


def _mock_request(*, user=None, school=None, public_host_kind="tenant"):
    req = SimpleNamespace(
        user=user
        or SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            is_staff=False,
            role="ADMIN",
            pk=1,
        ),
        school=school,
        public_host_kind=public_host_kind,
    )
    return req


def _mock_school(pk=42, name="Demo School"):
    return SimpleNamespace(pk=pk, id=pk, name=name, slug="demo-school")


def _empty_qs():
    qs = mock.MagicMock()
    qs.filter.return_value = qs
    qs.select_related.return_value = qs
    qs.order_by.return_value = qs
    qs.count.return_value = 0
    qs.__iter__ = lambda self: iter([])
    qs.__getitem__ = lambda self, item: []
    return qs


_CC_EMPTY = {
    "support_open_count": 0,
    "support_backlog_48h_count": 0,
    "trial_ending_soon_count": 0,
    "tenant_churn_risk_count": 0,
    "provisioning_sla_breaches": 0,
    "support_stale_rows": [],
}


class OperatorPressingIssuesTests(SimpleTestCase):
    """Operator builder returns scope=operator and URLs point to /super/."""

    def _run(self, cc=None):
        from apps.dashboard.pressing_issues import build_operator_pressing_issues

        with mock.patch(
            "apps.schools.super_views_command_center_data.build_command_center_data",
            return_value=cc or _CC_EMPTY,
        ), mock.patch(
            "apps.siteconfig.models_feature_controls.GlobalSupportTicket.objects"
        ) as ticket_objects:
            ticket_objects.filter.return_value = _empty_qs()
            request = _mock_request(public_host_kind="manager")
            return build_operator_pressing_issues(request)

    def test_returns_operator_scope(self):
        result = self._run()
        self.assertEqual(result["scope"], "operator")
        self.assertIn("title", result)
        self.assertIn("subtitle", result)
        self.assertIn("metrics", result)
        self.assertIn("items", result)
        self.assertIn("empty_message", result)
        self.assertIn("primary_cta", result)
        self.assertIn("show_empty", result)

    def test_metric_urls_use_super_namespace(self):
        result = self._run()
        for metric in result["metrics"]:
            url = metric.get("url", "")
            if url:
                self.assertIn(
                    "/super/",
                    url,
                    f"Operator metric '{metric['key']}' URL should contain /super/: {url}",
                )

    def test_empty_items_safe(self):
        result = self._run()
        self.assertIsInstance(result["items"], list)
        self.assertTrue(len(result["items"]) <= 8)
        self.assertTrue(result["show_empty"])

    def test_command_center_data_flows_through(self):
        fake_cc = {
            "support_open_count": 7,
            "support_backlog_48h_count": 2,
            "trial_ending_soon_count": 1,
            "tenant_churn_risk_count": 3,
            "provisioning_sla_breaches": 0,
            "support_stale_rows": [],
        }
        result = self._run(cc=fake_cc)
        counts = {m["key"]: m["count"] for m in result["metrics"]}
        self.assertEqual(counts.get("support_open"), 7)
        self.assertEqual(counts.get("support_backlog_48h"), 2)
        self.assertEqual(counts.get("trial_ending"), 1)
        self.assertEqual(counts.get("churn_risk"), 3)
        self.assertFalse(result["show_empty"])


class TenantPressingIssuesTests(SimpleTestCase):
    """Tenant builder returns scope=tenant and NO /super/ URLs."""

    def _run(self, school=None):
        from apps.dashboard.pressing_issues import build_tenant_pressing_issues

        with mock.patch(
            "apps.siteconfig.models_feature_controls.GlobalSupportTicket.objects"
        ) as ticket_objects, mock.patch(
            "apps.requests.models.AccessRequest.objects", create=True
        ) as access_objects, mock.patch(
            "apps.finance.models.Invoice.objects", create=True
        ) as invoice_objects:
            ticket_objects.filter.return_value = _empty_qs()
            access_objects.filter.return_value = _empty_qs()
            invoice_objects.filter.return_value = _empty_qs()
            request = _mock_request(school=school)
            return build_tenant_pressing_issues(request)

    def test_returns_tenant_scope(self):
        result = self._run(school=_mock_school())
        self.assertEqual(result["scope"], "tenant")

    def test_no_super_urls(self):
        result = self._run(school=_mock_school())
        for metric in result["metrics"]:
            url = metric.get("url", "")
            self.assertNotIn(
                "/super/",
                url,
                f"Tenant metric '{metric['key']}' must NOT use /super/ URLs: {url}",
            )
        for item in result["items"]:
            url = item.get("url", "")
            self.assertNotIn(
                "/super/",
                url,
                f"Tenant item '{item['title']}' must NOT use /super/ URLs: {url}",
            )

    def test_without_school_returns_safe_structure(self):
        from apps.dashboard.pressing_issues import build_tenant_pressing_issues

        request = _mock_request(school=None)
        result = build_tenant_pressing_issues(request)
        self.assertEqual(result["scope"], "tenant")
        self.assertIsInstance(result["metrics"], list)
        self.assertIsInstance(result["items"], list)
        self.assertIn("empty_message", result)
        self.assertTrue(result["show_empty"])

    def test_items_capped_at_8(self):
        result = self._run(school=_mock_school())
        self.assertTrue(len(result["items"]) <= 8)

    def test_dict_shape(self):
        result = self._run(school=_mock_school())
        required_keys = {
            "title",
            "subtitle",
            "scope",
            "metrics",
            "items",
            "empty_message",
            "primary_cta",
            "show_empty",
        }
        self.assertTrue(required_keys.issubset(set(result.keys())))
        self.assertIn("label", result["primary_cta"])
        self.assertIn("url", result["primary_cta"])
        self.assertIsInstance(result["show_empty"], bool)

    def test_metric_shape(self):
        result = self._run(school=_mock_school())
        for metric in result["metrics"]:
            self.assertIn("key", metric)
            self.assertIn("label", metric)
            self.assertIn("count", metric)
            self.assertIn("url", metric)
            self.assertIn("tone", metric)
