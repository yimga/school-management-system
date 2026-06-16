"""Onboarding checklist links must be tenant-admin reachable, never operator-gated.

Regression: the `ccc` (domains) step linked to siteconfig:console_domains_hub,
which is @staff_member_required (operator console). A tenant admin clicking the
"Domains / email routing" onboarding row got bounced to the operator login wall.
The fix points it (and the guided_configuration fallback) at the tenant-facing
siteconfig:custom_domain_wizard (@login_required).

These are no-DB checks: a source-level guard (no operator-gated route name may
reappear in the onboarding link builder) + a reverse() proof that the
replacement resolves on the tenant urlconf.
"""

from __future__ import annotations

import inspect

from django.test import SimpleTestCase
from django.urls import reverse

from apps.platform_runtime import onboarding


class OnboardingLinksTenantFacingTests(SimpleTestCase):
    def test_no_operator_gated_console_hub_in_onboarding_links(self):
        # console_domains_hub is @staff_member_required; it must never be the
        # target of a tenant onboarding step again. Match the reverse *call*
        # form (not bare mentions) so explanatory comments stay allowed.
        source = inspect.getsource(onboarding._compute_data_driven_onboarding_steps)
        self.assertNotIn(
            '_reverse_tenant("siteconfig:console_domains_hub")',
            source,
            "Onboarding step links to an operator-gated (@staff_member_required) "
            "route; tenant admins would be bounced.",
        )

    def test_domains_wizard_reverses_on_tenant_urlconf(self):
        # The replacement target must actually resolve on the tenant subdomain
        # urlconf the onboarding builder reverses against.
        url = reverse(
            "siteconfig:custom_domain_wizard", urlconf="config.tenant_urls"
        )
        self.assertTrue(url)

    def test_reverse_helper_returns_blank_for_unknown_name(self):
        # Guards the helper contract the fix relies on (no exception, "" on miss).
        self.assertEqual(
            onboarding._reverse_tenant("siteconfig:does_not_exist_xyz"), ""
        )
