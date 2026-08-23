"""
SessionSchoolBindingMiddleware must sit BELOW SessionMiddleware in BOTH stacks.

The guard resolves the request's user itself (``_resolve_user``), which needs
``request.session`` — every branch of ``__call__`` is behind
``hasattr(request, "session")``. The base list already satisfies that. The
django-tenants list does NOT: the guard is mounted with the other tenant
middlewares, far above ``SessionMiddleware``, so on the schema-per-tenant cloud
the BOLA guard is still completely inert — the HMAC verification, the realign
branch and the 403 never execute. That is the exact bug that was closed for the
edge topology and left open for the production one.

``SHARED_APPS`` / ``TENANT_APPS`` / the tenants ``MIDDLEWARE`` are only ASSIGNED
inside ``if USE_DJANGO_TENANTS and postgresql``, so at test runtime they do not
exist on the settings object. Read the settings SOURCE instead.
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase

SETTINGS_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "settings.py"
)

BIND = "apps.schools.middleware_session_school_bind.SessionSchoolBindingMiddleware"
SESSION = "django.contrib.sessions.middleware.SessionMiddleware"


def _middleware_lists():
    """Every ``MIDDLEWARE = [...]`` literal in config/settings.py, by line number."""
    tree = ast.parse(SETTINGS_PATH.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "MIDDLEWARE" not in names:
            continue
        entries = [
            el.value
            for el in node.value.elts
            if isinstance(el, ast.Constant) and isinstance(el.value, str)
        ]
        found.append((node.lineno, entries))
    return found


class SessionSchoolBindMiddlewareOrderTests(SimpleTestCase):
    def test_both_middleware_lists_were_found(self):
        """Guard the guard: an AST walk that finds nothing would pass vacuously."""
        lists = _middleware_lists()
        self.assertGreaterEqual(
            len(lists), 2, "expected the base list and the django-tenants list"
        )
        for _lineno, entries in lists:
            self.assertIn(BIND, entries)
            self.assertIn(SESSION, entries)

    def test_binding_guard_is_below_session_middleware_everywhere(self):
        broken = []
        for lineno, entries in _middleware_lists():
            if entries.index(SESSION) > entries.index(BIND):
                broken.append(lineno)
        self.assertEqual(
            broken,
            [],
            "SessionSchoolBindingMiddleware runs above SessionMiddleware in the "
            f"MIDDLEWARE list(s) starting at config/settings.py line(s) {broken}; "
            "request.session does not exist yet, so the whole BOLA guard is a no-op",
        )

    def test_guard_is_inert_without_a_session(self):
        """
        Pins WHY the ordering above is load-bearing rather than stylistic: with no
        session on the request the guard cannot resolve a user and returns early.
        """
        from apps.schools.middleware_session_school_bind import (
            SessionSchoolBindingMiddleware,
        )

        class _Req:
            pass

        request = _Req()  # no .session, no .user — what the cloud stack hands it
        mw = SessionSchoolBindingMiddleware(lambda r: "passed-through")
        self.assertIsNone(mw._resolve_user(request))
        self.assertEqual(mw(request), "passed-through")
