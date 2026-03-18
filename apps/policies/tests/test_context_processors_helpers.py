from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.policies.context_processors import tenant_policy_context


class PolicyContextProcessorHelperTests(SimpleTestCase):
    def test_tenant_policy_context_returns_empty_policy_slices_on_soft_failure(self):
        request = SimpleNamespace(
            tenant_ctx={"tenant_id": "abc"},
            school=object(),
            user=object(),
        )

        with patch(
            "apps.policies.policy_registry.get_effective_policy",
            side_effect=AttributeError,
        ):
            ctx = tenant_policy_context(request)

        self.assertEqual(ctx["tenant_ctx"], {"tenant_id": "abc"})
        self.assertEqual(ctx["global_env"], {})
        self.assertEqual(ctx["tenant_attendance_policy"], {})
        self.assertEqual(ctx["tenant_communication_policy"], {})
        self.assertEqual(ctx["tenant_compliance_policy"], {})
