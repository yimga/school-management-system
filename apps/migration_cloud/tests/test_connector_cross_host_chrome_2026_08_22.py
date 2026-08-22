"""Shell chrome must not 500 the operator host with a tenant-only {% url %}.

``apps/migration_cloud/urls.py`` is mounted in BOTH ``config/tenant_urls.py`` and
``config/manager_urls.py``. The connector wizard's templates extend
``portal_base.html``, which -- 900 lines below the content block -- includes
``partials/rmc_support_quick_create.html`` and its bare
``{% url 'portal:support_quick_create' %}``. ``portal:`` exists only on the tenant
host, so every one of these routes raised
``NoReverseMatch: 'portal' is not a registered namespace`` on
``manager.runmycampus.com`` -- AFTER the view had run, the query had run and the body
had rendered.

These tests hit the real routes on the real operator urlconf. A unit test that renders
the template with its own context and its own host cannot see this, which is precisely
why it survived: the failure is a property of the HOST, not of the template or the view.

Related: ``scripts/audit_shell_url_namespace_contract.py`` is the static seal;
``apps/schools/tests/test_edge_box_urlconf_2026_08_22.py`` covers the other half of
the same lesson (a box misrouted onto ``config.urls`` sees no host split at all).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import get_resolver

MANAGER_HOST = "manager.runmycampus.com"

#: Every no-arg GET route the connector wizard mounts on the operator host. Derived
#: from the urlconf rather than hardcoded, so a route added later is covered without
#: anyone remembering to add it here.
def _connector_routes() -> list[str]:
    found: list[str] = []

    def walk(node, prefix: str = "") -> None:
        for pattern in node.url_patterns:
            path = prefix + str(getattr(pattern, "pattern", ""))
            if hasattr(pattern, "url_patterns"):
                walk(pattern, path)
            elif "<" not in path:
                found.append("/" + path)

    walk(get_resolver("config.manager_urls"))
    return sorted({r for r in found if r.startswith("/super/migration/connectors")})


@override_settings(ROOT_URLCONF="config.manager_urls", ALLOWED_HOSTS=["*"])
class ConnectorRoutesRenderOnOperatorHostTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="conn-chrome-probe",
            email="conn-chrome-probe@example.test",
            password="probe-pw-not-a-real-secret",
        )
        # RequireMFA is a TWO stage gate and force_login satisfies neither. Without a
        # confirmed device the box 302s to /authentication/mfa/setup/, no template is
        # ever rendered, and a "no route 5xxs" assertion passes while proving nothing.
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.get_or_create(
            user=cls.user, name="default", defaults={"confirmed": True}
        )
        # The wizard resolves its school from request.school, request.tenant, or a
        # SchoolMembership. On the operator host none of the middleware sets the first
        # two, so without a membership every view raises Http404 -- and a "no 5xx"
        # assertion over eight 404s would be perfectly green and perfectly useless.
        from apps.schools.models import School, SchoolMembership

        cls.school = School.objects.create(
            name="Chrome Probe School", slug="chrome-probe-school", is_active=True
        )
        SchoolMembership.objects.create(
            user=cls.user, school=cls.school, role="ADMIN", is_primary=True
        )

    def _client(self) -> Client:
        client = Client(HTTP_HOST=MANAGER_HOST)
        client.force_login(self.user)
        # force_login satisfies authentication but NOT the MFA gate; without this the
        # request 302s to /mfa/setup/ and never reaches the template at all, so the
        # test would pass while proving nothing.
        session = client.session
        session["mfa_verified"] = True
        session.save()
        return client

    def test_the_wizard_actually_mounts_here(self):
        # If this ever returns an empty list the assertions below become vacuous.
        self.assertGreaterEqual(len(_connector_routes()), 5)

    def test_no_connector_route_5xxs_on_the_operator_host(self):
        client = self._client()
        broken = []
        rendered = 0
        for route in _connector_routes():
            response = client.get(route)
            if response.status_code >= 500:
                broken.append((route, response.status_code))
            elif response.status_code == 200:
                rendered += 1
        self.assertEqual(broken, [], f"5xx on the operator host: {broken}")
        # A 302 renders no template, so an all-redirect run would satisfy the
        # assertion above without exercising a single line of chrome. Require that
        # most of these routes actually produced a page.
        self.assertGreaterEqual(
            rendered,
            len(_connector_routes()) // 2,
            "too few routes rendered -- the 5xx check would be vacuous",
        )

    def test_the_support_chip_is_absent_rather_than_fatal(self):
        # The chip is a tenant feature. On the operator host the right outcome is that
        # it does not render -- not that it takes the page down with it.
        response = self._client().get("/super/migration/connectors/")
        self.assertEqual(
            response.status_code,
            200,
            f"expected a rendered page, got {response.status_code} -> "
            f"{response.headers.get('Location', '')}",
        )
        self.assertNotContains(response, "rmc-support-quick-create-config")


class SupportChipPartialTests(TestCase):
    """The partial itself, independent of any route."""

    def test_partial_uses_the_as_form_for_every_portal_url(self):
        # A bare {% url 'portal:...' %} here is the exact regression: it renders in
        # the closing chrome of 354 templates, on two different hosts.
        from pathlib import Path

        import django.conf as conf

        base = Path(conf.settings.BASE_DIR)
        source = (base / "templates" / "partials" / "rmc_support_quick_create.html").read_text(
            encoding="utf-8"
        )
        for name in ("portal:support_quick_create", "portal:kb_search_inline"):
            self.assertIn(f"{{% url '{name}' as ", source, name)
            self.assertNotIn(f"{{% url '{name}' %}}", source, name)
