"""
PATH §6.2 III.5 / SOT §11.4 batch 953 — runtime_resolution_complete carries runtime_trace_id.

GAP.5 trace id is set in build_tenant_runtime (and get_effective_site_settings); logs must
include it so DEBUG / log pipelines can correlate resolver work.
"""

from __future__ import annotations

from unittest.mock import Mock

from django.test import TestCase

from apps.platform_runtime.runtime_resolver import build_tenant_runtime
from apps.platform_runtime.tracing import get_runtime_trace_id
from apps.schools.models import School
from apps.tenancy.context import TenantContext


class Batch953RuntimeResolutionTraceLogTests(TestCase):
    def test_runtime_resolution_complete_includes_trace_id_with_request(self):
        school = School.objects.create(
            name="Batch953 Trace School",
            slug="batch953-trace-school",
            subdomain="batch953-trace-school",
            is_active=True,
        )
        request = Mock()
        request.school = school
        request.user = None
        self.assertIsNone(get_runtime_trace_id(request))

        tenant_ctx = TenantContext(
            tenant_id=str(school.id),
            schema_name="public",
            school_id=school.id,
            country="US",
            timezone="UTC",
            feature_flags={},
            policy_overrides={},
            host="batch953-trace-school.example.com",
        )

        with self.assertLogs(
            "apps.platform_runtime.runtime_resolver", level="DEBUG"
        ) as cm:
            build_tenant_runtime(tenant_ctx, request=request)

        complete = [
            r.getMessage()
            for r in cm.records
            if "runtime_resolution_complete" in r.getMessage()
        ]
        self.assertEqual(len(complete), 1, complete)
        self.assertIn("runtime_trace_id=", complete[0])
        tid = get_runtime_trace_id(request)
        self.assertIsNotNone(tid)
        self.assertEqual(len(tid), 16)
        self.assertIn(tid, complete[0])

    def test_runtime_resolution_complete_logs_placeholder_without_request(self):
        ctx = TenantContext.empty(host="example.com")
        with self.assertLogs(
            "apps.platform_runtime.runtime_resolver", level="DEBUG"
        ) as cm:
            build_tenant_runtime(ctx, request=None)

        complete = [
            r.getMessage()
            for r in cm.records
            if "runtime_resolution_complete" in r.getMessage()
        ]
        self.assertEqual(len(complete), 1, complete)
        self.assertIn("runtime_trace_id=-", complete[0])
