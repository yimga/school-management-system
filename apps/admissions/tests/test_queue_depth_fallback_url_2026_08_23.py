"""The cockpit drill-down fallback must be a path a real tenant can reach.

``_applicant_list_base_url`` reverses ``accounts:backend_applicant_list`` and
falls back to a literal path when ``reverse`` raises (off-request /
``AppRegistryNotReady``). The literal was ``/backend/applicants/`` -- but
``apps.accounts.urls`` is mounted under ``authentication/`` in BOTH host
urlconfs, so the real path is ``/authentication/backend/applicants/``. Whenever
the fallback fired, every ``drill_url`` and ``stale_drill_url`` on the
admissions queue tile pointed at a 404: precisely the regression the helper's
own docstring says it was written to end.

Resolving the literal against ``config.tenant_urls`` -- a REAL school's
urlconf, not the dev-only ``config.urls`` that ``ROOT_URLCONF`` points at under
test -- is what makes this test able to fail.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import Resolver404, resolve

from apps.admissions.queue_depth import (
    _APPLICANT_LIST_FALLBACK_PATH,
    _applicant_list_base_url,
)


class ApplicantListFallbackPathTests(SimpleTestCase):
    def _resolves_under(self, urlconf: str):
        try:
            return resolve(_APPLICANT_LIST_FALLBACK_PATH, urlconf=urlconf)
        except Resolver404:
            return None

    def test_fallback_resolves_on_a_real_tenant_host(self):
        match = self._resolves_under("config.tenant_urls")
        self.assertIsNotNone(
            match,
            f"{_APPLICANT_LIST_FALLBACK_PATH} 404s for every real school -- the "
            "admissions queue tile links land nowhere whenever reverse() fails",
        )
        self.assertEqual(match.view_name, "accounts:backend_applicant_list")

    def test_fallback_resolves_on_the_dev_host_too(self):
        match = self._resolves_under("config.urls")
        self.assertIsNotNone(match)
        self.assertEqual(match.view_name, "accounts:backend_applicant_list")

    def test_the_helper_returns_that_literal_when_reverse_fails(self):
        import django.urls as django_urls

        original = django_urls.reverse
        try:
            def _boom(*args, **kwargs):
                raise RuntimeError("no urlconf here")

            django_urls.reverse = _boom
            self.assertEqual(
                _applicant_list_base_url(), _APPLICANT_LIST_FALLBACK_PATH
            )
        finally:
            django_urls.reverse = original

    def test_the_live_reverse_and_the_fallback_agree(self):
        """If they ever diverge, one of the two is lying about where the list is."""
        self.assertEqual(_applicant_list_base_url(), _APPLICANT_LIST_FALLBACK_PATH)
