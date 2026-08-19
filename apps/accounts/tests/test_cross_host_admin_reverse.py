"""A view reachable on the base host must not reverse an `admin:` route unguarded.

`config.urls` (the base / public host) does NOT mount `django.contrib.admin`, while
`config.tenant_urls` and `config.manager_urls` do. A bare `reverse("admin:...")` in a
view that the base host routes is therefore an uncaught `NoReverseMatch` — a 500 the
first time that page is opened on that host.

Neither existing reference-integrity gate catches this:

  * `verify_url_name_integrity` UNIONS registered names across every host urlconf, so
    `admin:index` resolves because *some* host mounts it, and
  * `verify_cross_host_template_reverse` only inspects `{% url %}` inside templates —
    not `reverse()` inside a view.

Two live instances were found by sweeping the Workflow Center's destinations:
`accounts.views.backend_dashboard` (its "Frontend admin" hero action — and
`/authentication/backend/` IS routed on the base host) and
`accounts.views_certification.certification_home` (both its GCE-disabled redirect
target and its two context URLs).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

BASE_URLCONF = "config.urls"
TENANT_URLCONF = "config.tenant_urls"


class AdminNamespaceIsHostSplitTests(SimpleTestCase):
    """The precondition every other test here depends on."""

    def test_admin_is_absent_from_the_base_host(self):
        with self.assertRaises(NoReverseMatch):
            reverse("admin:index", urlconf=BASE_URLCONF)

    def test_admin_is_present_on_the_tenant_host(self):
        self.assertEqual(reverse("admin:index", urlconf=TENANT_URLCONF), "/admin/")

    def test_backend_dashboard_is_routed_on_the_base_host(self):
        """Which is what makes the unguarded reverse a real 500, not a theory."""
        self.assertTrue(reverse("accounts:backend_dashboard", urlconf=BASE_URLCONF))


def _unguarded_admin_reverses(module) -> list[tuple[int, str]]:
    """Literal `reverse("admin:…")` calls in ``module`` not inside a guarding try."""
    source = Path(inspect.getfile(module)).read_text(encoding="utf8")
    tree = ast.parse(source)

    guarded_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        catches = False
        for handler in node.handlers:
            exc = handler.type
            names: list[str] = []
            if isinstance(exc, ast.Name):
                names = [exc.id]
            elif isinstance(exc, ast.Tuple):
                names = [e.id for e in exc.elts if isinstance(e, ast.Name)]
            elif exc is None:
                catches = True
            # Named guard tuples (e.g. ACCOUNTS_SOFT_FAILURES) are the repo's
            # convention and do include NoReverseMatch.
            if any(
                n == "NoReverseMatch"
                or n.endswith(("_FAILURES", "_ERRORS", "_EXCEPTIONS"))
                or n in {"Exception", "BaseException"}
                for n in names
            ):
                catches = True
        if catches:
            for child in ast.walk(node):
                if hasattr(child, "lineno"):
                    guarded_lines.add(child.lineno)

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        fname = getattr(fn, "id", None) or getattr(fn, "attr", None)
        if fname not in {"reverse", "reverse_lazy"} or not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        if not first.value.startswith("admin:"):
            continue
        if node.lineno in guarded_lines:
            continue
        found.append((node.lineno, first.value))
    return found


class BaseHostViewsGuardAdminReverseTests(SimpleTestCase):
    """The two modules whose views the base host actually routes."""

    def test_backend_dashboard_module_has_no_unguarded_admin_reverse(self):
        from apps.accounts import views

        offenders = _unguarded_admin_reverses(views)
        self.assertEqual(
            offenders,
            [],
            "apps/accounts/views.py reverses an admin: route without a "
            f"NoReverseMatch guard: {offenders}. The base host does not mount "
            "the Django admin, so this 500s there.",
        )

    def test_certification_module_has_no_unguarded_admin_reverse(self):
        from apps.accounts import views_certification

        offenders = _unguarded_admin_reverses(views_certification)
        self.assertEqual(
            offenders,
            [],
            "apps/accounts/views_certification.py reverses an admin: route "
            f"without a guard: {offenders}.",
        )


class CertificationSafeAdminUrlTests(SimpleTestCase):
    """The helper must degrade to "" rather than raising."""

    def test_safe_admin_url_returns_empty_when_admin_is_absent(self):
        from apps.accounts.views_certification import _safe_admin_url

        with self.settings(ROOT_URLCONF=BASE_URLCONF):
            self.assertEqual(_safe_admin_url("admin:academics_academicyear_changelist"), "")

    def test_safe_admin_url_resolves_when_admin_is_present(self):
        from apps.accounts.views_certification import _safe_admin_url

        with self.settings(ROOT_URLCONF=TENANT_URLCONF):
            self.assertEqual(
                _safe_admin_url("admin:academics_academicyear_changelist"),
                "/admin/academics/academicyear/",
            )

    def test_setup_redirect_never_returns_empty(self):
        """A redirect target of "" would be a broken response, not a fallback."""
        from apps.accounts.views_certification import (
            _certification_setup_redirect_target,
        )

        for urlconf in (BASE_URLCONF, TENANT_URLCONF):
            with self.subTest(urlconf=urlconf), self.settings(ROOT_URLCONF=urlconf):
                self.assertTrue(_certification_setup_redirect_target())


class CertificationTemplateGuardsEmptyUrlsTests(SimpleTestCase):
    """An empty href is a dead control — the buttons must be conditional."""

    def test_admin_buttons_are_wrapped_in_existence_checks(self):
        from django.conf import settings

        markup = (
            Path(settings.BASE_DIR)
            / "templates"
            / "accounts"
            / "certification_home.html"
        ).read_text(encoding="utf8")
        self.assertIn("{% if admin_year_url %}", markup)
        self.assertIn("{% if admin_session_url %}", markup)
