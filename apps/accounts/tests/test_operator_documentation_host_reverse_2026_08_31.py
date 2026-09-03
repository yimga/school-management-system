"""The operator Documentation body renders on THREE urlconfs, not just the manager one.

`accounts.views.user_documentation` renders through
`apps.accounts.operator_account_render.render_account_page`, which picks the
control-plane shell (and therefore
`accounts/partials/operator_documentation_body.html`) whenever
`apps.schools.control_plane.use_control_plane_shell(request)` is true --- and that
helper returns True for ``public_host_kind in ("manager", "local")``.

A "local" host (``localhost`` / ``127.0.0.1`` / ``testserver`` / a bare IP literal on a
non-sovereign box) is routed by ``UrlConfSwitcherMiddleware`` to ``config.urls``, which
does NOT mount ``manager_help_center`` --- that name exists only in
``config.manager_urls``. The body carried a BARE ``{% url 'manager_help_center' %}``,
so ``/authentication/documentation/`` raised ``NoReverseMatch`` and returned 500 on
every local/dev host while being perfectly fine on ``manager.runmycampus.com``.

Neither reference-integrity gate could see it:

* ``verify_url_name_integrity`` unions names across hosts, so the name "exists".
* ``audit_shell_url_namespace_contract`` walks six DECLARED shells through literal
  ``{% include %}`` edges; this body is reached through
  ``{% include operator_cp_body_template %}`` --- a VARIABLE include --- and its
  ``SHELL_HOSTS`` deliberately omits ``config.urls``.
* ``verify_cross_host_template_reverse`` only matched ``{% url 'ns:name' %}``; a
  namespace-less name was invisible to its regex (fixed in the same commit).

These tests assert on the RENDERED OUTPUT of the partial under each urlconf, not on
its source text: the pre-fix defect is "rendering raises", which only a render shows.
"""

from __future__ import annotations

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import NoReverseMatch, get_urlconf, reverse, set_urlconf

BODY = "accounts/partials/operator_documentation_body.html"

BASE_URLCONF = "config.urls"
TENANT_URLCONF = "config.tenant_urls"
MANAGER_URLCONF = "config.manager_urls"


class ManagerHelpCenterIsManagerOnlyTests(SimpleTestCase):
    """The precondition everything below depends on."""

    def test_reversible_on_the_manager_host(self):
        self.assertTrue(reverse("manager_help_center", urlconf=MANAGER_URLCONF))

    def test_absent_from_the_base_and_tenant_hosts(self):
        for urlconf in (BASE_URLCONF, TENANT_URLCONF):
            with self.subTest(urlconf=urlconf), self.assertRaises(NoReverseMatch):
                reverse("manager_help_center", urlconf=urlconf)


class ControlPlaneShellReachesLocalHostsTests(SimpleTestCase):
    """Which is what makes the unguarded reverse a real 500, not a theory."""

    def test_a_local_host_gets_the_control_plane_shell(self):
        from apps.schools.control_plane import use_control_plane_shell

        request = RequestFactory().get("/authentication/documentation/")
        request.public_host_kind = "local"
        request.is_tenant_host = False
        self.assertTrue(use_control_plane_shell(request))

    def test_documentation_is_routed_on_the_base_host(self):
        self.assertTrue(reverse("accounts:user_documentation", urlconf=BASE_URLCONF))


class OperatorDocumentationBodyRendersOnEveryHostTests(SimpleTestCase):
    """Render the partial for real under each urlconf and read the output."""

    def _render(self, urlconf: str) -> str:
        previous = get_urlconf()
        set_urlconf(urlconf)
        try:
            return render_to_string(BODY, {})
        finally:
            set_urlconf(previous)

    def test_manager_host_shows_the_help_center_link(self):
        html = self._render(MANAGER_URLCONF)
        self.assertIn(
            'href="%s"' % reverse("manager_help_center", urlconf=MANAGER_URLCONF),
            html,
            "the manager host must still get the Help center control",
        )

    def test_base_host_renders_and_omits_the_manager_only_link(self):
        # Before the fix this call raised NoReverseMatch (a 500 on localhost).
        html = self._render(BASE_URLCONF)
        self.assertIn(
            'href="%s"' % reverse("kb:kb_home", urlconf=BASE_URLCONF),
            html,
            "the rest of the body must still render",
        )
        self.assertNotIn("/help-center/", html)

    def test_tenant_host_renders_and_omits_the_manager_only_link(self):
        html = self._render(TENANT_URLCONF)
        self.assertIn(
            'href="%s"' % reverse("accounts:user_profile", urlconf=TENANT_URLCONF),
            html,
        )
        self.assertNotIn("/help-center/", html)

    def test_no_empty_href_is_emitted_when_the_name_is_absent(self):
        """`as`-form degradation must drop the control, not ship href=""."""
        self.assertNotIn('href=""', self._render(BASE_URLCONF))
