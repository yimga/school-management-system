"""A sovereign box reached by IP must be a TENANT host, not a developer loopback.

WHAT WAS BROKEN. ``deploy/selfhost/.env.edge.example`` promises, in writing:

    "With this on, ANY host that doesn't match a subdomain -- a bare LAN hostname,
     the machine's IP, or the base domain -- resolves to the sole active school,
     so you do NOT need per-school subdomain DNS."

``_resolve_school_from_request`` kept that promise (locked by
``test_single_tenant_bare_host.py``). ``UrlConfSwitcherMiddleware`` never learned it.
It asked ``public_host_kind()``, got "local" for an IP literal -- the same answer it
gives ``localhost`` -- and handed the box ``config.urls``, the DEVELOPER urlconf. So a
school's own mini-PC, reached at http://10.10.20.137:10000, got:

  * no admin site at all (``config.urls`` mounts neither), which made
    /authentication/backend/ a 500 inside ``AdminSite.each_context``;
  * 1,422 ``tenant_admin:*`` names it could not reverse, which is why sidebars
    came up empty and the platform wordmark showed instead of the school's;
  * 428 ``/super/`` control-plane routes it should never serve;
  * ``public_host_kind == "local"``, which ``tenant_api_guards`` reads as a
    developer host and rewards with a tenant-crossing bypass.

The school resolved correctly the whole time. Only the URL layer disagreed with it.
"""
from django.test import RequestFactory, TestCase, override_settings

from apps.schools.middleware import UrlConfSwitcherMiddleware

BOX_IP = "10.10.20.137:10000"
BASE = "school.lan"


@override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN=BASE)
class SovereignBoxUrlConfTests(TestCase):
    def setUp(self):
        self.mw = UrlConfSwitcherMiddleware(lambda r: None)

    def _route(self, host):
        request = RequestFactory().get("/", HTTP_HOST=host)
        self.mw.process_request(request)
        return request

    # ---------------------------------------------------------- the box ----
    @override_settings(SINGLE_TENANT=True, USE_DJANGO_TENANTS=False)
    def test_ip_literal_is_a_tenant_host_on_a_box(self):
        request = self._route(BOX_IP)
        self.assertEqual(request.urlconf, "config.tenant_urls")
        self.assertTrue(request.is_tenant_host)

    @override_settings(SINGLE_TENANT=True, USE_DJANGO_TENANTS=False)
    def test_box_host_kind_is_not_local(self):
        # `tenant_api_guards.staff_may_bypass_tenant_guard_on_request` grants a
        # tenant-crossing bypass on "local". A school's box is not a dev loopback.
        self.assertEqual(self._route(BOX_IP).public_host_kind, "tenant")

    @override_settings(SINGLE_TENANT=True, USE_DJANGO_TENANTS=False)
    def test_base_domain_on_a_box_is_the_tenant_not_the_marketing_site(self):
        # A sovereign box has no public marketing surface to serve.
        self.assertEqual(self._route(BASE).urlconf, "config.tenant_urls")

    @override_settings(SINGLE_TENANT=True, USE_DJANGO_TENANTS=False)
    def test_box_does_not_serve_the_control_plane(self):
        from django.urls import Resolver404, resolve

        request = self._route(BOX_IP)
        with self.assertRaises(Resolver404):
            resolve("/super/founder/", urlconf=request.urlconf)

    @override_settings(SINGLE_TENANT=True, USE_DJANGO_TENANTS=False)
    def test_box_can_reverse_the_tenant_admin(self):
        from django.urls import reverse

        request = self._route(BOX_IP)
        # This is the namespace whose absence 500'd /authentication/backend/.
        self.assertTrue(reverse("admin:index", urlconf=request.urlconf))

    # ------------------------------------------------- nothing else moves ----
    @override_settings(SINGLE_TENANT=False)
    def test_cloud_is_untouched(self):
        # Default deployment: an IP still gets the developer surface, exactly as before.
        request = self._route(BOX_IP)
        self.assertEqual(request.urlconf, "config.urls")
        self.assertEqual(request.public_host_kind, "local")
        self.assertFalse(request.is_tenant_host)

    @override_settings(SINGLE_TENANT=True, USE_DJANGO_TENANTS=False)
    def test_manager_host_is_never_captured(self):
        with override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com"):
            request = self._route("manager.runmycampus.com")
        self.assertEqual(request.urlconf, "config.manager_urls")
        self.assertFalse(request.is_tenant_host)

    @override_settings(SINGLE_TENANT=True, USE_DJANGO_TENANTS=True)
    def test_schema_mode_box_is_left_alone(self):
        # Under django-tenants the schema is resolved from the hostname upstream, so
        # the bare-host fallback is inert -- `check_edge_readiness` says so and FAILs
        # that combination. Claiming it works here would be worse than not claiming it.
        from apps.schools.middleware import is_sovereign_single_tenant_box

        self.assertFalse(is_sovereign_single_tenant_box())
        self.assertEqual(self._route(BOX_IP).urlconf, "config.urls")


@override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN=BASE)
class HostKindOwnershipTests(TestCase):
    """`ReservedPublicHostAccessMiddleware` used to overwrite the switcher's answer."""

    @override_settings(SINGLE_TENANT=True, USE_DJANGO_TENANTS=False)
    def test_reserved_host_middleware_does_not_clobber_the_switcher(self):
        from apps.schools.middleware import ReservedPublicHostAccessMiddleware

        request = RequestFactory().get("/", HTTP_HOST=BOX_IP)
        UrlConfSwitcherMiddleware(lambda r: None).process_request(request)
        self.assertEqual(request.public_host_kind, "tenant")
        ReservedPublicHostAccessMiddleware(lambda r: None).process_request(request)
        self.assertEqual(request.public_host_kind, "tenant")
