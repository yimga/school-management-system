"""View-layer authorization for the athletics surfaces.

The coach console gates on ``@login_required`` + ``@require_school`` +
``@require_permission("athletics.view", "athletics.manage")``: anonymous ->
login bounce (302), authed-without-grant -> branded PermissionDenied (403),
granted -> 200. The public participation-consent pages are anonymous-by-design
and must render a uniform 200 for valid, bogus, and missing tokens (no leak,
no 500). ``athletics_team_manage_access`` scopes a coach to their assigned teams.
"""

from __future__ import annotations

from importlib import import_module

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from apps.accounts import effective_access
from apps.accounts.decorators import require_permission
from apps.accounts.models import AccessRole, Permission
from apps.athletics.models import (
    CoachAssignment,
    ParticipationConsent,
    TeamMembership,
)
from apps.athletics.tests.base import BaseAthleticsTestCase
from apps.athletics.views.coach import coach_dashboard
from apps.athletics.views.consent_public import (
    participation_consent_decide,
    participation_consent_public,
)
from apps.schools.mixins import require_school

User = get_user_model()


def _grant(user, *codes):
    role, _ = AccessRole.objects.get_or_create(
        code="ATHLETICS_COACH", defaults={"name": "Coach", "description": "x"}
    )
    for code in codes:
        perm, _ = Permission.objects.get_or_create(
            code=code, defaults={"name": code, "description": code}
        )
        role.permissions.add(perm)
    user.roles.add(role)


class _RequestMixin:
    def setUp(self):
        super().setUp()
        self.rf = RequestFactory()

    def _plain_user(self, username):
        user = User.objects.create_user(username=username, password="pass123")
        if hasattr(user, "role"):
            user.role = User.Role.TEACHER
            user.save(update_fields=["role"])
        return user

    def _prep(self, request):
        engine = import_module(settings.SESSION_ENGINE)
        request.session = engine.SessionStore()
        request._messages = FallbackStorage(request)
        # The athletics namespace is registered on the tenant urlconf (host-split);
        # middleware normally sets this. RequestFactory doesn't run middleware, so
        # pin it here or template {% url 'athletics:...' %} raises NoReverseMatch.
        request.urlconf = "config.tenant_urls"
        return request

    def _coach_get(self, user):
        request = self.rf.get("/athletics/")
        request.user = user
        request.school = self.fx.school
        return self._prep(request)


class CoachRouteGatingTests(_RequestMixin, BaseAthleticsTestCase):
    def test_anonymous_redirects_to_login(self):
        resp = coach_dashboard(self._coach_get(AnonymousUser()))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"].lower())

    def test_authed_without_permission_raises_permission_denied(self):
        user = self._plain_user("no_perm_coach")
        with self.assertRaises(PermissionDenied):
            coach_dashboard(self._coach_get(user))

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_granted_user_reaches_dashboard_200(self):
        # The dashboard template reverses athletics: URLs; render against the
        # tenant urlconf (where the namespace is registered) so {% url %} resolves.
        user = self._plain_user("granted_coach")
        _grant(user, "athletics.manage")
        resp = coach_dashboard(self._coach_get(user))
        self.assertEqual(resp.status_code, 200)

    def test_decorator_stack_opens_for_grant_holder(self):
        # Rock-solid backstop: the EXACT decorator stack the coach views use,
        # over a trivial body, opens for a grant holder and closes otherwise.
        @require_permission("athletics.view", "athletics.manage")
        def _probe(request):
            return HttpResponse("ok")

        gated = require_school(_probe)

        granted = self._plain_user("probe_grant")
        _grant(granted, "athletics.view")
        self.assertEqual(gated(self._coach_get(granted)).status_code, 200)

        denied = self._plain_user("probe_deny")
        with self.assertRaises(PermissionDenied):
            gated(self._coach_get(denied))


class ConsentPublicPageTests(_RequestMixin, BaseAthleticsTestCase):
    def _mint(self):
        membership = self.add_member(self.fx, status=TeamMembership.Status.PENDING)
        raw, consent = ParticipationConsent.mint(
            membership=membership,
            guardian_name="Parent",
            guardian_email="parent@example.com",
            consent_text="I consent.",
        )
        return raw, consent

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_valid_token_renders_200(self):
        raw, _ = self._mint()
        request = self._prep(self.rf.get("/athletics/consent/", {"token": raw}))
        request.user = AnonymousUser()
        resp = participation_consent_public(request)
        self.assertEqual(resp.status_code, 200)
        # _secure() sets no-store; @never_cache appends further directives.
        self.assertIn("no-store", resp["Cache-Control"])

    def test_bogus_token_uniform_200_no_leak(self):
        request = self._prep(
            self.rf.get("/athletics/consent/", {"token": "bogus-token-value-1234567890"})
        )
        request.user = AnonymousUser()
        resp = participation_consent_public(request)
        # Uniform anti-enumeration response — not a 500, no data leaked.
        self.assertEqual(resp.status_code, 200)

    def test_missing_token_uniform_200(self):
        request = self._prep(self.rf.get("/athletics/consent/"))
        request.user = AnonymousUser()
        resp = participation_consent_public(request)
        self.assertEqual(resp.status_code, 200)

    def test_decide_consent_records_decision(self):
        raw, consent = self._mint()
        request = self._prep(
            self.rf.post(
                "/athletics/consent/decide/", {"token": raw, "choice": "consent"}
            )
        )
        request.user = AnonymousUser()
        resp = participation_consent_decide(request)
        self.assertEqual(resp.status_code, 200)
        consent.refresh_from_db()
        self.assertEqual(consent.decision, "consented")

    def test_decide_bogus_token_uniform_200(self):
        request = self._prep(
            self.rf.post(
                "/athletics/consent/decide/",
                {"token": "bogus-token-1234567890", "choice": "consent"},
            )
        )
        request.user = AnonymousUser()
        resp = participation_consent_decide(request)
        self.assertEqual(resp.status_code, 200)


class TeamManageAccessTests(BaseAthleticsTestCase):
    def _plain_user(self, username):
        user = User.objects.create_user(username=username, password="pass123")
        if hasattr(user, "role"):
            user.role = User.Role.TEACHER
            user.save(update_fields=["role"])
        return user

    def test_manager_tier_manages_any_team(self):
        # settings.manage grant makes the user the tenant-admin tier -> sees every team.
        admin = self._plain_user("ath_admin")
        _grant(admin, "athletics.manage", "settings.manage")
        self.assertTrue(
            effective_access.athletics_team_manage_access(
                admin, self.fx.school, self.fx.team.id
            )
        )

    def test_manager_cannot_manage_a_team_from_another_school(self):
        # A manager-tier admin of school A must NOT manage a team id that belongs
        # to school B. Pre-fix the admin branch returned True without confirming
        # the team is in `school`, so a cross-school team id was manageable.
        other = self.build_tenant("mgr-b")
        admin = self._plain_user("ath_admin_cross")
        _grant(admin, "athletics.manage", "settings.manage")
        self.assertTrue(
            effective_access.athletics_team_manage_access(
                admin, self.fx.school, self.fx.team.id
            )
        )
        self.assertFalse(
            effective_access.athletics_team_manage_access(
                admin, self.fx.school, other.team.id
            )
        )

    def test_coach_with_active_assignment_manages_own_team(self):
        coach = self._plain_user("assigned_coach")
        _grant(coach, "athletics.manage")
        CoachAssignment.objects.create(
            school=self.fx.school, team=self.fx.team, coach=coach, is_active=True
        )
        self.assertTrue(
            effective_access.athletics_team_manage_access(
                coach, self.fx.school, self.fx.team.id
            )
        )

    def test_coach_without_assignment_cannot_manage_team(self):
        # Holds athletics.manage but is NOT admin tier and has NO CoachAssignment
        # for this team -> object-level scoping denies.
        coach = self._plain_user("unassigned_coach")
        _grant(coach, "athletics.manage")
        self.assertFalse(
            effective_access.athletics_team_manage_access(
                coach, self.fx.school, self.fx.team.id
            )
        )

    def test_inactive_assignment_does_not_manage(self):
        coach = self._plain_user("inactive_coach")
        _grant(coach, "athletics.manage")
        CoachAssignment.objects.create(
            school=self.fx.school, team=self.fx.team, coach=coach, is_active=False
        )
        self.assertFalse(
            effective_access.athletics_team_manage_access(
                coach, self.fx.school, self.fx.team.id
            )
        )

    def test_no_permission_cannot_manage(self):
        nobody = self._plain_user("nobody")
        self.assertFalse(
            effective_access.athletics_team_manage_access(
                nobody, self.fx.school, self.fx.team.id
            )
        )
