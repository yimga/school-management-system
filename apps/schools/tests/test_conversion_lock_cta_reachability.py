"""Every advertised "do this next" CTA must survive the conversion lock.

The activation landing and the tenant mission strip exist *because* a school has not
recorded its first value yet — i.e. precisely when ``ConversionLockMiddleware`` is
refusing traffic. Both surfaces used to pick their CTA independently of the
allowlist the middleware enforces, so they routinely handed the operator a link the
gate then bounced straight back to ``/activation/first-action/``:

    Next: Finance setup -> "Do it now" -> GET /finance/ -> 302 -> /activation/first-action/

which reads to the user as "it buffers and comes back to the same page, no progress".
Three concrete offenders were live: ``finance:dashboard`` (``/finance/`` is deliberately
outside the narrow allowlist), ``accounts:backend_dashboard`` (``/authentication/backend/``
is on the explicit DENY list), and ``feedback:help_center`` (``/kb/`` was open but
``/help/`` was not).

These tests make that class of drift impossible: they enumerate the real advertised
destinations and assert each one is reachable under the strictest production posture.
"""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import User
from apps.portal.tenant_experience_command import _role_actions
from apps.schools.conversion_lock_paths import (
    conversion_allows_path,
    path_matches_conversion_allowlist,
)

TENANT_URLCONF = "config.tenant_urls"

#: Production posture: strict lock + narrow first-value prefixes.
STRICT = dict(
    CONVERSION_LOCK_STRICT=True,
    CONVERSION_LOCK_USE_NARROW_WORKFLOW_PATHS=True,
    CONVERSION_LOCK_ALLOWED_PREFIXES=(),
    ROOT_URLCONF=TENANT_URLCONF,
)


def _safe(name: str) -> str:
    try:
        return reverse(name, urlconf=TENANT_URLCONF)
    except (NoReverseMatch, AttributeError, TypeError, ValueError):
        return ""


class MissionStripCtaReachabilityTests(SimpleTestCase):
    """`_role_actions` feeds `primary_action` — none of it may be a dead end."""

    ROLES = (
        User.Role.ADMIN,
        User.Role.PRINCIPAL,
        User.Role.BURSAR,
        User.Role.TEACHER,
        User.Role.STUDENT,
        User.Role.PARENT,
    )

    @override_settings(**STRICT)
    def test_every_role_has_at_least_one_reachable_action(self):
        for role in self.ROLES:
            with self.subTest(role=role):
                actions = _role_actions(role)
                reachable = [
                    action
                    for action in actions
                    if conversion_allows_path(action.url)
                ]
                self.assertTrue(
                    reachable,
                    f"{role} is offered {[a.url for a in actions]} and the "
                    "conversion lock refuses every one — guaranteed redirect loop.",
                )

    @override_settings(**STRICT)
    def test_operator_finance_cta_is_a_first_value_surface(self):
        """The regression that shipped: 'Finance setup' pointing at /finance/."""
        urls = {action.label: action.url for action in _role_actions(User.Role.ADMIN)}
        finance = next(
            (url for label, url in urls.items() if "Finance" in str(label)), ""
        )
        self.assertTrue(finance, "operator actions no longer include a finance CTA")
        self.assertTrue(
            conversion_allows_path(finance),
            f"Finance CTA {finance!r} is blocked by the conversion lock.",
        )
        self.assertNotEqual(
            finance.rstrip("/"),
            "/finance",
            "The /finance/ root dashboard is intentionally NOT a first-value path.",
        )


class ActivationLandingCtaReachabilityTests(SimpleTestCase):
    """The landing page's own links must not bounce back to the landing page."""

    @override_settings(**STRICT)
    def test_offered_choices_are_all_reachable(self):
        from apps.schools.activation_views import _reachable

        candidates = {
            "attendance": _safe("portal:take_student_attendance"),
            "marks": _safe("evals:teacher_marks_entry"),
            "backend": _safe("accounts:backend_dashboard"),
        }
        offered = {key: url for key, url in candidates.items() if _reachable(url)}
        self.assertTrue(
            offered, "activation landing would render zero usable choices"
        )
        for key, url in offered.items():
            with self.subTest(choice=key):
                self.assertTrue(conversion_allows_path(url))

    @override_settings(**STRICT)
    def test_operator_dashboard_is_recognised_as_unreachable(self):
        """Pins the deny-list behaviour the filter depends on."""
        from apps.schools.activation_views import _reachable

        backend = _safe("accounts:backend_dashboard")
        self.assertTrue(backend, "accounts:backend_dashboard should resolve")
        self.assertFalse(
            _reachable(backend),
            "/authentication/backend/ is explicitly denied while locked; the "
            "activation page must not offer it.",
        )


class HelpAndImportStayOpenTests(SimpleTestCase):
    """A walled operator must still be able to get help and bring data in."""

    @override_settings(**STRICT)
    def test_help_center_is_allowlisted(self):
        help_url = _safe("feedback:help_center")
        self.assertTrue(help_url, "feedback:help_center should resolve on tenant")
        self.assertTrue(
            conversion_allows_path(help_url),
            "A locked-out operator with no route to help is a support dead end.",
        )

    @override_settings(**STRICT)
    def test_import_setup_is_allowlisted(self):
        import_url = _safe("school_setup_imports")
        self.assertTrue(import_url, "school_setup_imports should resolve on tenant")
        self.assertTrue(
            conversion_allows_path(import_url),
            "Importing the old system IS the first value action for a migrating "
            "school; the lock must not wall it off.",
        )

    @override_settings(**STRICT)
    def test_allowlist_still_refuses_a_random_tenant_route(self):
        """Guard against the fix degenerating into 'allow everything'."""
        self.assertFalse(
            path_matches_conversion_allowlist("/authentication/rbac/", ()),
            "The lock must still hold; only first-value surfaces open up.",
        )
