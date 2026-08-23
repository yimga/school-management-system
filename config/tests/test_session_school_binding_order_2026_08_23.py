"""The session-school binding guard needs a session to exist.

``SessionSchoolBindingMiddleware`` stops a user holding a session bound to school A
from browsing school B. It deliberately does NOT wait for
``AuthenticationMiddleware``: its ``_resolve_user`` pulls the user out of the
session itself, so the guard can run before the view rather than after everything
that trusts it. That design has one hard requirement -- ``request.session`` must
already exist -- and every branch is behind ``hasattr(request, "session")``, so if
it does not, the whole middleware silently does nothing.

In the BASE list that requirement is met: SessionMiddleware sits at index 9 and the
guard at 16. In the DJANGO-TENANTS list -- the one the cloud actually runs -- the
guard sat at index 8 and SessionMiddleware at 20. So on every schema-per-tenant
request the guard resolved no session, resolved no user, and returned immediately:
the HMAC check, the realign branch and the 403 had never run in production.

This is the same shape as the idempotency-middleware ordering fixed alongside it,
with the lists reversed -- there the BASE list was wrong. Hence one assertion over
BOTH topologies rather than a fix to whichever one is currently broken.
"""

from __future__ import annotations

import importlib.util
import pathlib

from django.test import SimpleTestCase

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCANNER = _REPO_ROOT / "scripts" / "verify_middleware_topology_parity.py"
_SETTINGS = _REPO_ROOT / "config" / "settings.py"

_BINDING = "apps.schools.middleware_session_school_bind.SessionSchoolBindingMiddleware"
_SESSION = "django.contrib.sessions.middleware.SessionMiddleware"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("_mw_parity_bind", _SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SessionSchoolBindingOrderingTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base, cls.tenants = _load_scanner().collect(_SETTINGS)

    def test_both_lists_were_parsed(self):
        # Calibration: empty lists would make the ordering assertions vacuous.
        self.assertGreater(len(self.base), 30)
        self.assertGreater(len(self.tenants), 30)
        for chain in (self.base, self.tenants):
            self.assertIn(_BINDING, chain)
            self.assertIn(_SESSION, chain)

    def test_the_session_exists_before_the_binding_guard_in_both_topologies(self):
        for label, chain in (("base", self.base), ("tenants", self.tenants)):
            with self.subTest(topology=label):
                self.assertLess(
                    chain.index(_SESSION),
                    chain.index(_BINDING),
                    f"In the {label} MIDDLEWARE, SessionMiddleware must run BEFORE "
                    "SessionSchoolBindingMiddleware. Above it there is no "
                    "request.session, so _resolve_user returns None and every "
                    "branch of the guard is skipped -- it protects nothing.",
                )
