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

from types import SimpleNamespace

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

    #: Roles the lock still applies to. These CAN record a first value, so
    #: funnelling them toward it is the whole point — most of their actions
    #: being refused is correct, not a bug.
    FUNNELLED_ROLES = (
        User.Role.ADMIN,
        User.Role.PRINCIPAL,
        User.Role.BURSAR,
        User.Role.TEACHER,
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
    def test_funnelled_roles_keep_a_first_value_surface_not_just_help(self):
        """"At least one reachable" is too low a bar on its own.

        STUDENT used to satisfy the test above with ``/help/`` alone while every
        other advertised action was refused — a portal that is technically not a
        redirect loop and still completely unusable. For the roles the lock DOES
        apply to, the surviving action has to be a real first-value surface, not
        the support escape hatch.
        """
        help_url = _safe("feedback:help_center")
        for role in self.FUNNELLED_ROLES:
            with self.subTest(role=role):
                reachable = [
                    action.url
                    for action in _role_actions(role)
                    if conversion_allows_path(action.url)
                ]
                substantive = [url for url in reachable if url != help_url]
                self.assertTrue(
                    substantive,
                    f"{role} can reach only {reachable} while locked — help is "
                    "an escape hatch, not a way to record first value.",
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


class LearnerLockExemptionTests(SimpleTestCase):
    """A learner cannot clear the lock, so the lock must not apply to them.

    Measured before the exemption, under the production posture: a STUDENT could
    reach 1 of 7 advertised destinations (``/help/``). Their own home, workflow,
    homework, syllabus, messages and profile were all bounced to
    ``/activation/first-action/`` — a page whose every choice is a staff action
    they have no permission to perform. CONVERSION_LOCK_STRICT defaults ON in
    production and OFF under RUNNING_TESTS, which is why no suite caught it.
    """

    #: CONVERSION_LOCK_ALL_SCHOOLS short-circuits the activation-gate lookup, so
    #: these stay DB-free.
    STRICT_ALL = dict(STRICT, CONVERSION_LOCK_ALL_SCHOOLS=True)

    @staticmethod
    def _user(role, **kw):
        return SimpleNamespace(
            is_authenticated=True, is_staff=False, is_superuser=False, role=role, **kw
        )

    @override_settings(**STRICT_ALL)
    def test_student_is_exempt_and_the_funnelled_roles_are_not(self):
        from apps.schools.conversion_lock_state import school_conversion_is_locked

        school = SimpleNamespace(pk=1, settings={})
        expected = {
            User.Role.STUDENT: False,
            User.Role.TEACHER: True,
            User.Role.ADMIN: True,
            User.Role.PARENT: True,
        }
        for role, locked in expected.items():
            with self.subTest(role=role):
                self.assertEqual(
                    school_conversion_is_locked(school, user=self._user(role)),
                    locked,
                )

    @override_settings(**STRICT_ALL)
    def test_an_elevated_account_is_never_exempted_by_its_role_column(self):
        """Defence in depth: the exemption keys off role, so staff must be excluded."""
        from apps.schools.conversion_lock_state import school_conversion_is_locked

        school = SimpleNamespace(pk=1, settings={})
        for flag in ("is_staff", "is_superuser"):
            with self.subTest(flag=flag):
                user = self._user(User.Role.STUDENT)
                setattr(user, flag, True)
                self.assertTrue(
                    school_conversion_is_locked(school, user=user),
                    f"{flag} account slipped through the learner exemption",
                )

    @override_settings(**STRICT_ALL)
    def test_completed_first_action_still_wins_for_everyone(self):
        from apps.schools.conversion_lock_state import school_conversion_is_locked

        done = SimpleNamespace(
            pk=1, settings={"rmc_conversion": {"first_action_completed": True}}
        )
        for role in (User.Role.STUDENT, User.Role.ADMIN):
            with self.subTest(role=role):
                self.assertFalse(
                    school_conversion_is_locked(done, user=self._user(role))
                )

    @override_settings(**STRICT_ALL)
    def test_the_lock_is_off_entirely_when_not_strict(self):
        from apps.schools.conversion_lock_state import school_conversion_is_locked

        school = SimpleNamespace(pk=1, settings={})
        with override_settings(CONVERSION_LOCK_STRICT=False):
            self.assertFalse(
                school_conversion_is_locked(school, user=self._user(User.Role.ADMIN))
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
