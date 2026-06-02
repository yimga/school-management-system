"""Matrix-promoted registry keys bind to HTTP progress tracking."""

from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase

from apps.platform_runtime.workflow_guidance import (
    normalize_path_for_workflow_registry,
    resolve_workflow_for_entry_path,
    resolve_workflow_for_route,
)
from apps.platform_runtime.workflow_request_middleware import _workflow_key_for_request


class WorkflowMatrixPathNormalizationTests(SimpleTestCase):
    def test_strips_tenant_prefix(self):
        self.assertEqual(
            normalize_path_for_workflow_registry("/t/demo-school/authentication/rollover/"),
            "/authentication/rollover/",
        )


class WorkflowMatrixRegistryBindingTests(SimpleTestCase):
    def test_accounts_rollover_resolves(self):
        req = RequestFactory().post("/authentication/rollover/")
        workflow = resolve_workflow_for_route(req)
        self.assertIsNotNone(workflow)
        self.assertEqual(workflow.key, "accounts-rollover")

    def test_accounts_rollover_tenant_prefixed(self):
        req = RequestFactory().post("/t/gilead-high/authentication/rollover/")
        workflow = resolve_workflow_for_route(req)
        self.assertIsNotNone(workflow)
        self.assertEqual(workflow.key, "accounts-rollover")

    def test_middleware_uses_registry_key_not_http_slug(self):
        req = RequestFactory().post("/authentication/rollover/")
        key = _workflow_key_for_request(req)
        self.assertEqual(key, "accounts-rollover")
        self.assertFalse(key.startswith("http."))

    def test_entry_path_resolver_longest_prefix(self):
        workflow = resolve_workflow_for_entry_path("/authentication/rollover/extra-step/")
        self.assertIsNotNone(workflow)
        self.assertEqual(workflow.key, "accounts-rollover")

    def test_customer_success_hub_distinct_from_tenant_guided_onboarding(self):
        tenant_path = "/siteconfig/guided-onboarding/"
        cs_path = "/super/customer-success/"
        tenant_w = resolve_workflow_for_entry_path(tenant_path)
        cs_w = resolve_workflow_for_entry_path(cs_path)
        self.assertEqual(tenant_w.key, "tenant-guided-configuration")
        self.assertEqual(cs_w.key, "customersuccess-guided-onboarding")
