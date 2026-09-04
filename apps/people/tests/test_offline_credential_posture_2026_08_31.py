"""Credential posture for offline onboarding and admin-issued temporary passwords.

Three defects, all "a usable credential exists somewhere it should not":

1. ``offline_workflow_handlers._apply_teacher_create`` minted a teacher account
   from an admin-supplied temporary password WITHOUT the forced-reset markers its
   online twin (``people.views_backend.backend_teacher_create``) sets, so a
   teacher onboarded on the offline/LAN drain kept a durable, admin-known
   password that ``OnboardingEnforcementMiddleware`` never challenged.

2/3. ``tenant_identity_reset_password`` and ``super_operator_team_reset_password``
   put the freshly minted CLEARTEXT temporary password into a ``messages`` call
   and then REDIRECTED. ``MESSAGE_STORAGE`` is unset project-wide, so Django uses
   ``FallbackStorage`` = (CookieStorage, SessionStorage); a message the response
   never renders is persisted, so the cleartext was written into the
   signed-but-UNENCRYPTED ``messages`` cookie (recoverable with nothing but
   SECRET_KEY) and, once the queue outgrows ``CookieStorage.max_cookie_size``,
   into the ``django_session`` table. The docstrings' "never logged" is true and
   is not the same claim as "never persisted".

The guards below pin the fixed behaviour: the offline path sets both markers, and
a reset leaves NO copy of the cleartext in the response cookies or in
``django_session`` while still showing it to the admin exactly once.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.people.models import StudentProfile
from apps.people.offline_workflow_handlers import (
    _link_parent,
    apply_people_workflow,
)
from apps.schools.models import School, SchoolMembership
from apps.test_utils.http_clients import login_manager_client

_BASE_DOMAIN = "runmycampus.com"
_MANAGER_HOST = "manager.runmycampus.com"
# Deterministic via a patched generate_temp_password, and shaped so a substring
# scan cannot collide with anything else in a cookie or a session blob.
_TEMP = "TmpMark-7Q2zX9vK"


def _mk_school(tag: str) -> School:
    # A blank subdomain is UNIQUE, so every school in a test needs its own.
    return School.objects.create(
        name="School %s" % tag,
        slug="%s-%s" % (tag, uuid.uuid4().hex[:8]),
        subdomain="%s-%s" % (tag, uuid.uuid4().hex[:8]),
        is_active=True,
    )


def _mk_user(role, *, password="pass12345678", **kwargs) -> User:
    return User.objects.create_user(
        username="u-%s" % uuid.uuid4().hex[:8],
        email="%s@example.test" % uuid.uuid4().hex[:8],
        password=password,
        role=role,
        **kwargs,
    )


def _member(user, school, *, owner=False, role=None) -> SchoolMembership:
    return SchoolMembership.objects.create(
        user=user,
        school=school,
        role=role or user.role,
        is_primary=True,
        is_school_owner=owner,
    )


def _session_rows_carrying(secret: str) -> list[str]:
    """Every django_session row whose DECODED payload contains ``secret``.

    Decoded, not the stored column: SessionStorage writes the message text as
    JSON inside a base64 blob, so a raw-column scan misses it and reports a false
    clean.
    """
    hits = []
    for row in Session.objects.all():
        try:
            decoded = row.get_decoded()
        except Exception:  # noqa: BLE001 — an undecodable row cannot carry it
            continue
        if secret in repr(decoded):
            hits.append(row.session_key)
    return hits


def _cookies_carrying(response, secret: str) -> list[str]:
    """Cookie names on ``response`` whose value carries ``secret``.

    The ``messages`` cookie is SIGNED, not encrypted, so its raw value looks
    opaque but is trivially reversible — decode it the way Django itself does
    rather than substring-scanning the blob and declaring victory.
    """
    from django.contrib.messages.storage.cookie import CookieStorage
    from django.test import RequestFactory

    hits = []
    for name, morsel in response.cookies.items():
        value = morsel.value or ""
        if not value:
            continue
        if secret in value:
            hits.append(name)
            continue
        if name == "messages":
            decoded = CookieStorage(RequestFactory().get("/"))._decode(value) or []
            if any(secret in str(m.message) for m in decoded):
                hits.append(name)
    return hits


class OfflineTeacherCreateMarkerTests(TestCase):
    """DEFECT 1 — the offline drain must force the same first-login reset."""

    def setUp(self):
        self.school = _mk_school("offline")
        # An admin-like role picks up people.* through RolePermissionBackend. The
        # shared test DB has an essentially empty RBAC catalog, so assert the
        # permission instead of trusting it — otherwise the handler would refuse
        # and every assertion below would pass for the wrong reason.
        self.actor = _mk_user(User.Role.ADMIN)
        _member(self.actor, self.school)
        self.assertTrue(
            self.actor.has_perm("people.add_teacherprofile"),
            "actor lacks people.add_teacherprofile; the handler would refuse",
        )

    def _create_offline_teacher(self, *, password="TempFromAdmin-4471"):
        email = "%s@teachers.test" % uuid.uuid4().hex[:8]
        result = apply_people_workflow(
            self.school.pk,
            self.actor.pk,
            "people_teacher_create",
            {"email": email, "password": password},
            {"client_offline_id": uuid.uuid4().hex},
        )
        self.assertTrue(result and result.get("ok"), msg=repr(result))
        return User.objects.get(pk=result["user_id"]), password

    def test_offline_teacher_create_sets_both_forced_reset_markers(self):
        user, password = self._create_offline_teacher()
        # The admin-supplied password works, exactly as online...
        self.assertTrue(user.check_password(password))
        # ...and both markers its ONLINE twin sets are present, so
        # OnboardingEnforcementMiddleware challenges the very first request.
        self.assertTrue(
            user.requires_password_change,
            "offline teacher keeps a durable admin-known password",
        )
        self.assertFalse(
            user.profile_setup_completed,
            "offline teacher skips forced profile setup",
        )

    def test_offline_teacher_is_flagged_for_onboarding_enforcement(self):
        # needs_onboarding() is the exact predicate the middleware reads; assert
        # THAT, not only the two columns, so a rename of either cannot pass.
        user, _pw = self._create_offline_teacher()
        self.assertTrue(user.needs_onboarding())


class OfflineGuardianCarveOutTests(TestCase):
    """DEFECT 1, the deliberate exception — no password is minted for a guardian.

    ``_link_parent`` creates the guardian with an UNUSABLE password and sends a
    one-time set-password link; that link is the credential. The forced-reset
    markers are therefore not applicable, and ``guardian_invite`` clears
    ``requires_password_change`` when the guardian redeems the link anyway. This
    pins the carve-out so it is not "fixed" blindly.
    """

    def test_offline_guardian_gets_unusable_password_and_no_reset_marker(self):
        school = _mk_school("guardian")
        student = StudentProfile.objects.create(
            school=school, first_name="Ada", last_name="Nkeng"
        )
        email = "%s@guardians.test" % uuid.uuid4().hex[:8]
        with patch(
            "apps.accounts.guardian_invite.send_guardian_invite", return_value=None
        ):
            linked = _link_parent(student, email, "+237600000000")
        self.assertTrue(linked)
        parent = User.objects.get(email=email)
        self.assertFalse(parent.has_usable_password())
        self.assertFalse(
            parent.requires_password_change,
            "no password was minted, so the forced-reset marker is not applicable",
        )


@override_settings(
    ALLOWED_HOSTS=["*"],
    SECURE_SSL_REDIRECT=False,
    MULTI_TENANT_BASE_DOMAIN=_BASE_DOMAIN,
    SESSION_PINNING_ENABLED=False,
)
class TenantResetPasswordNotPersistedTests(TestCase):
    """DEFECT 2 — the tenant credential reset must not persist the cleartext."""

    def setUp(self):
        cache.clear()
        self.school = _mk_school("tenant")
        self.host = "%s.%s" % (self.school.subdomain, _BASE_DOMAIN)
        self.owner = _mk_user(User.Role.ADMIN, password="ownerpass12345")
        _member(self.owner, self.school, owner=True)
        self.target = _mk_user(User.Role.TEACHER, password="oldpass12345")
        _member(self.target, self.school)
        from apps.test_utils.http_clients import login_tenant_admin_client

        self.client = login_tenant_admin_client(
            self.owner,
            password="ownerpass12345",
            host=self.host,
            school=self.school,
        )
        self.reset_url = reverse(
            "accounts:tenant_identity_reset_password", args=[self.target.pk]
        )
        self.detail_url = reverse(
            "accounts:tenant_identity_detail", args=[self.target.pk]
        )

    @patch("apps.accounts.credential_reset.generate_temp_password", return_value=_TEMP)
    def test_reset_leaves_no_cleartext_in_cookie_or_session(self, _mock):
        resp = self.client.post(self.reset_url, HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 302, msg=resp.get("Location", ""))
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password(_TEMP))  # the reset really ran
        self.assertEqual(_cookies_carrying(resp, _TEMP), [])
        self.assertEqual(_session_rows_carrying(_TEMP), [])

    @patch("apps.accounts.credential_reset.generate_temp_password", return_value=_TEMP)
    def test_missed_handover_states_the_loss_and_shows_no_credential(self, _mock):
        # The handoff rides django.core.cache, which is a PER-PROCESS LocMemCache
        # unless CACHE_BACKEND / REDIS_URL is set, so on a multi-worker deploy the
        # POST and the GET can land on different workers and the pop misses.
        # Sessions do not mask it: without Redis SESSION_ENGINE is plain ``db``, so
        # login keeps working while this one handoff comes up empty. Clearing the
        # cache reproduces exactly that: slot gone, session breadcrumb intact.
        self.client.post(self.reset_url, HTTP_HOST=self.host)
        cache.clear()
        resp = self.client.get(self.detail_url, HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200, msg=resp.get("Location", ""))
        body = resp.content.decode()
        # The operator is TOLD, rather than shown a blank where a password was.
        self.assertIn("can no longer be displayed", body)
        self.assertIn("reset the password again", body)
        # ...and the notice does not carry the credential it reports the loss of.
        self.assertNotIn(_TEMP, body)
        self.assertEqual(_cookies_carrying(resp, _TEMP), [])
        self.assertEqual(_session_rows_carrying(_TEMP), [])

    @patch("apps.accounts.credential_reset.generate_temp_password", return_value=_TEMP)
    def test_admin_still_sees_the_credential_exactly_once(self, _mock):
        self.client.post(self.reset_url, HTTP_HOST=self.host)
        first = self.client.get(self.detail_url, HTTP_HOST=self.host)
        self.assertEqual(first.status_code, 200, msg=first.get("Location", ""))
        self.assertIn(_TEMP, first.content.decode())
        # Rendered by THIS response, so the framework stored nothing.
        self.assertEqual(_cookies_carrying(first, _TEMP), [])
        self.assertEqual(_session_rows_carrying(_TEMP), [])
        # ...and a refresh does not show it a second time.
        second = self.client.get(self.detail_url, HTTP_HOST=self.host)
        self.assertEqual(second.status_code, 200)
        self.assertNotIn(_TEMP, second.content.decode())


@override_settings(
    ALLOWED_HOSTS=["*"],
    SECURE_SSL_REDIRECT=False,
    MULTI_TENANT_BASE_DOMAIN=_BASE_DOMAIN,
    ROOT_URLCONF="config.manager_urls",
    SESSION_PINNING_ENABLED=False,
)
class OperatorResetPasswordNotPersistedTests(TestCase):
    """DEFECT 3 — the operator-team twin must not persist the cleartext either."""

    def setUp(self):
        cache.clear()
        self.password = "actorpass123"
        self.actor = User.objects.create_user(
            username="op_actor_%s" % uuid.uuid4().hex[:8],
            password=self.password,
            is_staff=True,
            is_superuser=True,
        )
        self.client = login_manager_client(self.actor, password=self.password)
        self.target = User.objects.create_user(
            username="op_target_%s" % uuid.uuid4().hex[:8],
            password="oldpass123",
            is_staff=True,
        )
        # The detail view refuses anyone outside queryset_platform_operators(),
        # so the colleague being reset needs a real operator profile.
        from apps.platform_runtime.models_operator_identity import (
            PlatformOperatorProfile,
        )

        PlatformOperatorProfile.objects.get_or_create(
            user=self.target,
            defaults={
                "status": PlatformOperatorProfile.Status.ACTIVE,
                "tier": "support",
            },
        )
        self.reset_url = reverse(
            "super:operator_team_reset_password", args=[self.target.pk]
        )
        self.detail_url = reverse("super:operator_team_detail", args=[self.target.pk])

    @patch("apps.accounts.credential_reset.generate_temp_password", return_value=_TEMP)
    def test_reset_leaves_no_cleartext_in_cookie_or_session(self, _mock):
        resp = self.client.post(self.reset_url, HTTP_HOST=_MANAGER_HOST)
        self.assertEqual(resp.status_code, 302, msg=resp.get("Location", ""))
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password(_TEMP))
        self.assertEqual(_cookies_carrying(resp, _TEMP), [])
        self.assertEqual(_session_rows_carrying(_TEMP), [])

    @patch("apps.accounts.credential_reset.generate_temp_password", return_value=_TEMP)
    def test_missed_handover_states_the_loss_and_shows_no_credential(self, _mock):
        # The handoff rides django.core.cache, which is a PER-PROCESS LocMemCache
        # unless CACHE_BACKEND / REDIS_URL is set, so on a multi-worker deploy the
        # POST and the GET can land on different workers and the pop misses.
        # Sessions do not mask it: without Redis SESSION_ENGINE is plain ``db``, so
        # login keeps working while this one handoff comes up empty. Clearing the
        # cache reproduces exactly that: slot gone, session breadcrumb intact.
        self.client.post(self.reset_url, HTTP_HOST=_MANAGER_HOST)
        cache.clear()
        resp = self.client.get(self.detail_url, HTTP_HOST=_MANAGER_HOST)
        self.assertEqual(resp.status_code, 200, msg=resp.get("Location", ""))
        body = resp.content.decode()
        # The operator is TOLD, rather than shown a blank where a password was.
        self.assertIn("can no longer be displayed", body)
        self.assertIn("reset the password again", body)
        # ...and the notice does not carry the credential it reports the loss of.
        self.assertNotIn(_TEMP, body)
        self.assertEqual(_cookies_carrying(resp, _TEMP), [])
        self.assertEqual(_session_rows_carrying(_TEMP), [])

    @patch("apps.accounts.credential_reset.generate_temp_password", return_value=_TEMP)
    def test_operator_still_sees_the_credential_exactly_once(self, _mock):
        self.client.post(self.reset_url, HTTP_HOST=_MANAGER_HOST)
        first = self.client.get(self.detail_url, HTTP_HOST=_MANAGER_HOST)
        self.assertEqual(first.status_code, 200, msg=first.get("Location", ""))
        self.assertIn(_TEMP, first.content.decode())
        self.assertEqual(_cookies_carrying(first, _TEMP), [])
        self.assertEqual(_session_rows_carrying(_TEMP), [])
        second = self.client.get(self.detail_url, HTTP_HOST=_MANAGER_HOST)
        self.assertEqual(second.status_code, 200)
        self.assertNotIn(_TEMP, second.content.decode())
