"""A URL namespace with no module policy default-denies everyone on a tenant host.

ModuleAccessMiddleware turns a request into a module name by taking the TOP-level
URL namespace, and can_access_module() denies any module that is not a key of
MODULE_ACCESS_DEFAULTS. So a namespace nobody remembered to register is not
"unconfigured" -- it is a wall, for every authenticated user who is neither a
Django is_superuser nor a control-plane role, with a logger.warning nobody reads.

apps/accounts/permissions.py already carries three separate post-mortems for
exactly this (setup_studio, migration_cloud_connector, and the nested-namespace
lockout at /compliance/reports/). Three times is a class of defect, not three
accidents, so this is the gate rather than a fourth comment.

WHY ONLY THE NON-MANAGER HOSTS

The middleware returns early when request.public_host_kind == "manager", so an
unregistered namespace under /super/ costs nothing -- and every operator
namespace is unregistered on purpose. Asserting over config.urls (the dev
superset, which serves every host's routes) would therefore demand that the
whole operator console be granted to tenant roles. The hosts that matter are
config.tenant_urls and config.public_urls, and test_manager_host_short_circuits
asserts that exemption is real rather than assuming it.
"""

from __future__ import annotations

import importlib

from django.test import RequestFactory, SimpleTestCase
from django.urls import URLResolver

from apps.accounts.middleware import ModuleAccessMiddleware
from apps.accounts.permissions import MODULE_ACCESS_DEFAULTS

GATED_URLCONFS = ("config.tenant_urls", "config.public_urls")

# Unregistered TODAY on a host where the middleware actually runs. Every one of
# these is a wall for a non-superuser, non-control-plane authenticated user. The
# name says what they are, not that they are fine: this is a backlog with a
# ratchet on it, and the set may only SHRINK. Registering one is a permission
# WIDENING and needs a human to decide who the module is for -- which is why
# this gate stops new ones rather than silently granting the old ones.
DENIED_AND_NOT_TRIAGED = frozenset(
    {
        "api_v2",
        "billing_embedded_checkout",
        "integrations_marketplace",
        "marketplace_dev",
        "migration_guardian_consent",
        "oauth",
        "orchestration_api",
        "sync_engine",
        "tenant_admin",
    }
)


def _top_namespaces(urlconf: str) -> set[str]:
    """The module names ModuleAccessMiddleware would derive from this urlconf."""
    module = importlib.import_module(urlconf)
    names: set[str] = set()
    for pattern in getattr(module, "urlpatterns", []):
        if isinstance(pattern, URLResolver) and pattern.namespace:
            # Same collapse the middleware does: nested namespaces inherit the
            # top-level module, and api_v1 is aliased onto "api".
            top = pattern.namespace.lower().split(":", 1)[0]
            names.add("api" if top in {"api_v1", "api-v1"} else top)
    return names


def _unregistered() -> set[str]:
    found: set[str] = set()
    for urlconf in GATED_URLCONFS:
        found |= _top_namespaces(urlconf)
    return {name for name in found if name not in MODULE_ACCESS_DEFAULTS}


class ModuleNamespaceRegistrationTests(SimpleTestCase):
    def test_no_new_unregistered_namespace_on_a_gated_host(self):
        new = sorted(_unregistered() - DENIED_AND_NOT_TRIAGED)
        self.assertEqual(
            new,
            [],
            "URL namespace(s) mounted on a tenant or public host with no entry in "
            "MODULE_ACCESS_DEFAULTS: " + ", ".join(new) + ". can_access_module() "
            "default-denies an unknown module, so every authenticated user who is "
            "not is_superuser and not a control-plane role gets an 'Access required' "
            "page there, and the only trace is a logger.warning. Either add the "
            "module to MODULE_ACCESS_DEFAULTS with the roles it is for, or -- if the "
            "deny is intended -- add it to DENIED_AND_NOT_TRIAGED with a reason.",
        )

    def test_the_backlog_has_no_stale_entry(self):
        """A name that is registered, or gone, must leave the list.

        Without this the set outlives its subjects and keeps excusing names that
        no longer exist -- the same shape as a gate that stops checking when its
        subject moves, which is what put three of these in the codebase.
        """
        stale = sorted(DENIED_AND_NOT_TRIAGED - _unregistered())
        self.assertEqual(
            stale,
            [],
            "DENIED_AND_NOT_TRIAGED names that are now registered or no longer "
            "mounted on a gated host: " + ", ".join(stale) + ". Remove them; the "
            "list ratchets down.",
        )

    def test_manager_host_short_circuits_the_module_gate(self):
        """The premise of this whole file, asserted rather than assumed.

        If the manager exemption ever goes away, every unregistered operator
        namespace becomes a live lockout and GATED_URLCONFS is the wrong scope.
        """
        seen = []

        def get_response(request):
            seen.append(request)
            return "passed through"

        middleware = ModuleAccessMiddleware(get_response)
        request = RequestFactory().get("/super/migration-cloud/")
        request.public_host_kind = "manager"
        request.user = None  # never consulted: the host check comes first

        self.assertEqual(middleware(request), "passed through")
        self.assertEqual(len(seen), 1)

    def test_an_unregistered_module_really_is_denied(self):
        """And so is the other premise: unknown module -> deny, not allow."""
        from django.contrib.auth.models import AnonymousUser

        class _Staff:
            is_authenticated = True
            is_superuser = False
            is_staff = True
            role = "TEACHER"
            pk = 1

        from apps.accounts.permissions import can_access_module

        self.assertFalse(can_access_module(_Staff(), "a_module_that_does_not_exist"))
        self.assertFalse(can_access_module(AnonymousUser(), "portal"))
