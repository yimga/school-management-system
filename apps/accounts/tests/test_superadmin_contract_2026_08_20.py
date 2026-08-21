"""The superadmin contract, checked without touching the database.

``SimpleTestCase`` on purpose so this runs alongside a peer holding the shared
test database. The DB-backed half lives in
``test_superadmin_holds_everything_2026_08_20.py``.
"""

from __future__ import annotations

from pathlib import Path

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase

from apps.accounts.superadmin import (
    REASON_DJANGO_SUPERUSER,
    REASON_PRIMARY_ROLE,
    SUPERADMIN_ROLE_CODE,
    is_platform_superadmin,
    superadmin_reason,
)


class _Account:
    """Duck-typed user — no DB, no model instance."""

    def __init__(self, *, role="TEACHER", is_superuser=False, authenticated=True):
        self.role = role
        self.is_superuser = is_superuser
        self.is_authenticated = authenticated
        self.roles = None


class WhoOwnsTheKeysTests(SimpleTestCase):
    def test_a_django_superuser_owns_everything(self):
        self.assertTrue(is_platform_superadmin(_Account(is_superuser=True)))
        self.assertEqual(
            superadmin_reason(_Account(is_superuser=True)), REASON_DJANGO_SUPERUSER
        )

    def test_the_superadmin_role_owns_everything_without_the_django_flag(self):
        """The gap that produced the report: SUPERADMIN != is_superuser."""
        account = _Account(role="SUPERADMIN", is_superuser=False)
        self.assertTrue(is_platform_superadmin(account))
        self.assertEqual(superadmin_reason(account), REASON_PRIMARY_ROLE)

    def test_the_role_comparison_is_case_and_type_insensitive(self):
        for raw in ("superadmin", " SuperAdmin ", "SUPERADMIN"):
            with self.subTest(raw=raw):
                self.assertTrue(is_platform_superadmin(_Account(role=raw)))

    def test_an_ordinary_role_owns_nothing_extra(self):
        for role in ("TEACHER", "PARENT", "ADMIN", "PRINCIPAL", ""):
            with self.subTest(role=role):
                self.assertFalse(is_platform_superadmin(_Account(role=role)))

    def test_an_anonymous_visitor_is_never_a_superadmin(self):
        self.assertFalse(is_platform_superadmin(AnonymousUser()))
        self.assertFalse(is_platform_superadmin(None))
        self.assertFalse(
            is_platform_superadmin(_Account(is_superuser=True, authenticated=False)),
            "an unauthenticated request must not inherit god-mode from a flag",
        )

    def test_the_db_free_path_answers_without_touching_roles(self):
        """``allow_queries=False`` must not reach for the M2M at all.

        The profile and ``has_feature_permission`` both call it while the
        connection may be in a broken transaction; a query there would turn one
        failure into two.
        """
        account = _Account(role="SUPERADMIN")
        account.roles = None  # any attribute access would raise
        self.assertTrue(is_platform_superadmin(account, allow_queries=False))
        self.assertFalse(
            is_platform_superadmin(_Account(role="TEACHER"), allow_queries=False)
        )


class TheResolverIsWiredIntoTheGateTests(SimpleTestCase):
    """``has_feature_permission`` is THE gate; god-mode must be resolved inside it.

    A behaviour test proves the grant for codes that exist today. This one pins
    the mechanism, because the whole point is codes that do NOT exist yet: if a
    later edit replaces the resolver call with a seeded list, coverage silently
    goes back to drifting and every behaviour test still passes.
    """

    def setUp(self):
        self.src = Path("apps/accounts/models.py").read_text(encoding="utf-8")

    def test_the_gate_consults_the_superadmin_resolver(self):
        self.assertIn("is_platform_superadmin", self.src)

    def test_the_role_m2m_query_folds_in_the_superadmin_role(self):
        self.assertIn("Q(code=SUPERADMIN_ROLE_CODE, school__isnull=True)", self.src)

    def test_the_temporary_grant_query_folds_it_in_too(self):
        self.assertIn(
            "Q(role__code=SUPERADMIN_ROLE_CODE, role__school__isnull=True)", self.src
        )

    def test_only_the_global_role_confers_god_mode(self):
        """A tenant can mint its own row coded SUPERADMIN — it must not escalate."""
        self.assertNotIn(
            'roles.filter(code=SUPERADMIN_ROLE_CODE)"',
            self.src,
            "an unscoped SUPERADMIN lookup would let any tenant-created role escalate",
        )
        superadmin_src = Path("apps/accounts/superadmin.py").read_text(encoding="utf-8")
        self.assertIn("school__isnull=True", superadmin_src)


class RoleTemplatesTests(SimpleTestCase):
    def test_superadmin_materialises_as_superadmin_not_admin(self):
        """It mapped to ADMIN, which is short a dozen codes SUPERADMIN owns."""
        from apps.accounts.signals import ROLE_TEMPLATES

        self.assertEqual(ROLE_TEMPLATES["SUPERADMIN"], [SUPERADMIN_ROLE_CODE])

    def test_every_declared_role_choice_has_a_template(self):
        """DPO and EMPLOYER had none, so those accounts carried no roles at all."""
        from apps.accounts.models import User
        from apps.accounts.signals import ROLE_TEMPLATES

        # COMMS_STAFF intentionally borrows BOARDING_MANAGER; every other choice
        # must resolve to something rather than leaving the account empty.
        missing = [
            choice.value
            for choice in User.Role
            if choice.value not in ROLE_TEMPLATES
        ]
        self.assertEqual(
            missing,
            [],
            f"role choices with no access-role template: {missing}",
        )

    def test_the_template_application_is_not_destructive(self):
        """No EXECUTABLE ``.set()`` — the docstring quotes it on purpose."""
        src = Path("apps/accounts/signals.py").read_text(encoding="utf-8")
        executable = [
            line.strip()
            for line in src.splitlines()
            if line.strip() == "instance.roles.set(roles)"
        ]
        self.assertEqual(
            executable,
            [],
            "a role edit would again delete every additionally granted role",
        )
        self.assertIn("instance.roles.add(*roles)", src)

    def test_the_template_lookup_is_scoped_to_global_rows(self):
        """Unscoped, it attached every tenant's catalog row of that code."""
        src = Path("apps/accounts/signals.py").read_text(encoding="utf-8")
        self.assertIn(
            'AccessRole.objects.filter(code__in=codes, school__isnull=True)', src
        )


class BothProfilesRenderTheSameCardTests(SimpleTestCase):
    """Tenant and operator previously showed different (and wrong) things."""

    PARTIAL = "accounts/partials/_access_summary_card.html"

    def test_the_tenant_profile_includes_the_card(self):
        src = Path("templates/accounts/profile.html").read_text(encoding="utf-8")
        self.assertIn(self.PARTIAL, src)

    def test_the_operator_profile_includes_the_same_card(self):
        src = Path("templates/accounts/partials/operator_profile_body.html").read_text(
            encoding="utf-8"
        )
        self.assertIn(self.PARTIAL, src)

    def test_the_card_is_not_gated_on_being_an_admin(self):
        """It used to render only inside ``{% if admin_context %}``."""
        src = Path("templates/accounts/profile.html").read_text(encoding="utf-8")
        card_at = src.index(self.PARTIAL)
        admin_at = src.index("{% if admin_context %}")
        self.assertLess(
            card_at,
            admin_at,
            "the access card sits inside the admin-only block again",
        )

    def test_the_admin_facing_profile_shows_it_too(self):
        """An admin viewing a staff member saw one role and no permissions."""
        src = Path("templates/accounts/tenant_identity_detail.html").read_text(
            encoding="utf-8"
        )
        self.assertIn(self.PARTIAL, src)
        view = Path("apps/accounts/views_tenant_identity.py").read_text(encoding="utf-8")
        self.assertIn('"access_summary": effective_access_summary(user, school=school)', view)

    def test_the_card_wording_works_for_someone_elses_profile(self):
        """One partial serves self AND admin-viewing-another, so no second person."""
        src = Path(f"templates/{self.PARTIAL}").read_text(encoding="utf-8")
        self.assertNotIn("that apply to you", src)
        self.assertNotIn("when you hold every role", src)

    def test_the_truncated_admin_only_list_is_gone(self):
        src = Path("templates/accounts/profile.html").read_text(encoding="utf-8")
        self.assertNotIn("admin_context.permissions_summary", src)
        views = Path("apps/accounts/views.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "[:20]  # cap for display",
            views,
            "the silent 20-code truncation is back",
        )


class BypassesResolveBeforeDeniesTests(SimpleTestCase):
    """A superuser grant placed BELOW a deny never runs.

    Both of these read as correct on the page — the bypass is right there — and
    both were unreachable. No DB: each returns at the bypass, which is the point.
    """

    def test_group_messaging_admits_a_superuser_whose_role_is_parent(self):
        """``User.role`` DEFAULTS to PARENT, so createsuperuser lands here."""
        from apps.communication.views_groups import _can_access_group_messaging

        self.assertTrue(
            _can_access_group_messaging(_Account(role="PARENT", is_superuser=True))
        )
        self.assertTrue(
            _can_access_group_messaging(_Account(role="STUDENT", is_superuser=True))
        )

    def test_group_messaging_still_refuses_an_ordinary_parent(self):
        from apps.communication.views_groups import _can_access_group_messaging

        self.assertFalse(_can_access_group_messaging(_Account(role="PARENT")))
        self.assertFalse(_can_access_group_messaging(_Account(role="STUDENT")))

    def test_tenant_identity_admits_a_superuser_with_no_membership(self):
        """An operator inspecting a tenant has no SchoolMembership row there."""
        from apps.accounts.views_tenant_identity import _can_manage_tenant_identity

        self.assertTrue(
            _can_manage_tenant_identity(_Account(role="PARENT", is_superuser=True), None)
        )

    def test_tenant_identity_still_refuses_an_anonymous_visitor(self):
        from apps.accounts.views_tenant_identity import _can_manage_tenant_identity

        self.assertFalse(_can_manage_tenant_identity(AnonymousUser(), None))
        self.assertFalse(_can_manage_tenant_identity(None, None))
