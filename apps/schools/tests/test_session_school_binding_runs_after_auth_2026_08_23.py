"""
SessionSchoolBindingMiddleware must actually RUN under the real MIDDLEWARE list.

The guard is mounted ABOVE ``AuthenticationMiddleware`` in both lists in
config/settings.py, so ``request.user`` did not exist yet and the entire body was
skipped on every request -- the HMAC verification, the realign branch and the
403 never executed anywhere. On top of that, ``TenantMiddleware`` overwrites
``request.session["school_id"]`` with the HOST school before this guard sees it,
so even a correctly ordered guard would compare a value against itself.

These tests run the project's real middleware stack (no override_settings) and
assert on effects only this middleware can produce -- its own 403 body, the
logout it performs, and the HMAC signature it writes -- so a 302 emitted by a
later middleware cannot make them pass while the guard is inert. (Repo logging
is globally disabled at CRITICAL, so log-based proofs are not available here.)
"""

import uuid

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import Client, TestCase

from apps.schools.models import School, SchoolMembership
from apps.schools.session_school_bind import SESSION_SCHOOL_SIG_KEY


def _make_pair(tag):
    uid = uuid.uuid4().hex[:8]
    school_a = School.objects.create(
        name=f"{tag} A {uid}",
        slug=f"{tag}a-{uid}",
        subdomain=f"{tag}a{uid}",
        is_active=True,
    )
    school_b = School.objects.create(
        name=f"{tag} B {uid}",
        slug=f"{tag}b-{uid}",
        subdomain=f"{tag}b{uid}",
        is_active=True,
    )
    User = get_user_model()
    user = User.objects.create_user(
        username=f"{tag}_{uid}", password="Test1234", role="ADMIN"
    )
    return school_a, school_b, user


class SessionSchoolBindingRunsTests(TestCase):
    def test_guard_rejects_foreign_session_school(self):
        """Member of A only, session pinned to A, request lands on B's host -> 403."""
        school_a, school_b, user = _make_pair("bindord")
        SchoolMembership.objects.create(
            user=user, school=school_a, role="ADMIN", is_primary=True
        )
        client = Client(HTTP_HOST=f"{school_b.subdomain}.runmycampus.com")
        client.force_login(user)
        session = client.session
        session["school_id"] = str(school_a.pk)
        session.save()

        resp = client.get("/authentication/backend/")

        self.assertEqual(resp.status_code, 403)
        # Body text is unique to this middleware: proves the reject branch ran
        # rather than some other 403 further down the stack.
        self.assertIn(
            "Session school does not match this campus",
            resp.content.decode("utf-8", "replace"),
        )
        # ...and it logged the session out, which nothing else in this flow does.
        self.assertNotIn("_auth_user_id", client.session)

    def test_guard_realigns_and_signs_when_user_may_switch(self):
        """Member of BOTH campuses: guard realigns + HMAC-signs instead of 403-ing."""
        school_a, school_b, user = _make_pair("bindrea")
        SchoolMembership.objects.create(
            user=user, school=school_a, role="ADMIN", is_primary=True
        )
        SchoolMembership.objects.create(user=user, school=school_b, role="ADMIN")
        client = Client(HTTP_HOST=f"{school_b.subdomain}.runmycampus.com")
        client.force_login(user)
        session = client.session
        session["school_id"] = str(school_a.pk)
        session.save()

        resp = client.get("/authentication/backend/")

        self.assertNotEqual(resp.status_code, 403)
        # Only sign_session_school_bind writes this key, and in this flow only the
        # binding middleware calls it -- an inert guard leaves the session unsigned.
        sig = client.session.get(SESSION_SCHOOL_SIG_KEY)
        self.assertTrue(sig, "session was never bound: the guard did not run")
        payload = signing.loads(sig, salt="rmc.session.school-bind.v1")
        self.assertEqual(payload["sid"], str(school_b.pk))
        self.assertEqual(payload["uid"], str(user.pk))
        self.assertEqual(client.session.get("school_id"), str(school_b.pk))

    def test_incoming_session_school_survives_host_overwrite(self):
        """
        TenantMiddleware rewrites session["school_id"] to the host school before the
        guard runs; the browser-sent value must still be visible to it.
        """
        school_a, school_b, user = _make_pair("bindinc")
        SchoolMembership.objects.create(
            user=user, school=school_a, role="ADMIN", is_primary=True
        )
        SchoolMembership.objects.create(user=user, school=school_b, role="ADMIN")
        client = Client(HTTP_HOST=f"{school_b.subdomain}.runmycampus.com")
        client.force_login(user)
        session = client.session
        session["school_id"] = str(school_a.pk)
        session.save()

        seen = {}
        import apps.schools.middleware_session_school_bind as bind_mod

        original = bind_mod.SessionSchoolBindingMiddleware.__call__

        def spy(self, request):
            seen.setdefault("school", getattr(request, "school", None))
            seen.setdefault(
                "incoming", getattr(request, "incoming_session_school_id", None)
            )
            return original(self, request)

        bind_mod.SessionSchoolBindingMiddleware.__call__ = spy
        try:
            client.get("/authentication/backend/")
        finally:
            bind_mod.SessionSchoolBindingMiddleware.__call__ = original

        self.assertIsNotNone(seen.get("school"), "request.school was never resolved")
        self.assertEqual(seen.get("school").pk, school_b.pk)
        self.assertEqual(seen.get("incoming"), str(school_a.pk))
