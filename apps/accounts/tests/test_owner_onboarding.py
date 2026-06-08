"""Guided owner-onboarding wizard + account-recovery hardening (2026-06-08).

Drives the REAL flow end-to-end through the test client so the wiring (token →
create-account → school → done) is validated, not just the units.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.schools.models import School, SchoolMembership

STRONG_PW = "Zaq12wsx!RmC9"


def _make_owner(username="jane", email="jane@cedar.test", activated=False):
    User = get_user_model()
    user = User.objects.create_user(username=username, email=email, role="ADMIN")
    if activated:
        user.set_password(STRONG_PW)
    else:
        user.set_unusable_password()
    user.save()
    school = School.objects.create(
        name="Cedar School", slug=f"cedar-{username}", subdomain=f"cedar-{username}",
        is_active=False, country_code="US", settings={},
    )
    SchoolMembership.objects.create(
        user=user, school=school, role="ADMIN", is_primary=True
    )
    return user, school


@override_settings(RATELIMIT_ENABLE=False)
class OwnerOnboardingFlowTests(TestCase):
    def setUp(self):
        self.user, self.school = _make_owner()

    def _account_url(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        return reverse(
            "accounts:owner_onboarding_account", kwargs={"uidb64": uid, "token": token}
        )

    def _login_past_mfa(self):
        """Log the owner in AND satisfy the platform's mandatory-MFA gate, so a
        test exercises the wizard's own logic rather than the MFA-setup redirect
        an ADMIN-role user without a device would otherwise hit (see
        ``test_step_two_gates_on_mfa_and_preserves_resume_target`` for that)."""
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.create(user=self.user, name="test-totp", confirmed=True)
        self.client.force_login(
            self.user, backend="django.contrib.auth.backends.ModelBackend"
        )
        session = self.client.session
        session["mfa_verified"] = True
        session.save()

    def test_account_step_sets_password_name_and_advances(self):
        # PasswordResetConfirmView swaps the token into the session then redirects
        # to a "set-password" sentinel URL — follow that dance.
        url = self._account_url()
        r = self.client.get(url)
        self.assertEqual(r.status_code, 302)
        sentinel = r.url
        self.client.get(sentinel)  # renders the form, seeds the session token
        r2 = self.client.post(
            sentinel,
            {
                "first_name": "Jane",
                "last_name": "Doe",
                "new_password1": STRONG_PW,
                "new_password2": STRONG_PW,
            },
        )
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(r2.url, reverse("accounts:owner_onboarding_school"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")
        self.assertEqual(self.user.last_name, "Doe")
        self.assertTrue(self.user.has_usable_password())
        self.school.refresh_from_db()
        self.assertEqual(self.school.settings["owner_onboarding"]["step"], "school")

    def test_wizard_is_reachable_without_mfa_interruption(self):
        # A brand-new owner has NO MFA device and NO password-set flow behind
        # them yet. Forcing /authentication/mfa/setup/ in front of the wizard is
        # the dead-end that walled owners out (prod: verify → school-not-found →
        # activation → mfa → manager login). /authentication/onboarding/ is now
        # in RequireMFAMiddleware.BYPASS_PREFIXES + the strict conversion-lock
        # allowlist, so step 2 renders directly. MFA is offered AFTER the wizard.
        self.client.force_login(
            self.user, backend="django.contrib.auth.backends.ModelBackend"
        )
        r = self.client.get(reverse("accounts:owner_onboarding_school"))
        self.assertEqual(r.status_code, 200)  # renders, does NOT bounce to MFA
        self.assertNotIn("/mfa/", getattr(r, "url", "") or "")

    def test_school_step_saves_and_advances(self):
        self._login_past_mfa()
        r = self.client.post(
            reverse("accounts:owner_onboarding_school"),
            {"school_name": "Cedar Academy", "primary_color": "#112233"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("accounts:owner_onboarding_done"))
        self.school.refresh_from_db()
        self.assertEqual(self.school.name, "Cedar Academy")
        self.assertEqual(self.school.primary_color, "#112233")
        self.assertEqual(self.school.settings["owner_onboarding"]["step"], "done")

    def test_school_step_skip_changes_nothing(self):
        self._login_past_mfa()
        r = self.client.post(
            reverse("accounts:owner_onboarding_school"),
            {"school_name": "Should Not Apply", "skip": "1"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("accounts:owner_onboarding_done"))
        self.school.refresh_from_db()
        self.assertEqual(self.school.name, "Cedar School")

    def test_done_marks_completed(self):
        self._login_past_mfa()
        r = self.client.get(reverse("accounts:owner_onboarding_done"))
        self.assertEqual(r.status_code, 200)
        self.school.refresh_from_db()
        self.assertTrue(self.school.settings["owner_onboarding"]["completed"])

    def test_completed_owner_is_bounced_out_of_wizard(self):
        self.school.settings = {"owner_onboarding": {"completed": True}}
        self.school.save(update_fields=["settings"])
        self._login_past_mfa()
        r = self.client.get(reverse("accounts:owner_onboarding_school"))
        self.assertEqual(r.status_code, 302)  # redirected to dashboard, not the wizard
        self.assertNotIn("/mfa/", r.url)  # the bounce is to the dashboard, not MFA
        self.assertNotIn(
            reverse("accounts:owner_onboarding_done"), r.url
        )  # completed → dashboard, not deeper into the wizard


@override_settings(ROOT_URLCONF="config.public_urls")
class OwnerOnboardingPublicHostRenderTests(TestCase):
    """The wizard now runs on the PUBLIC host (the verify link's host), not the
    tenant host it was first designed for. Every prior flow test resolves
    ``{% url %}`` against the monolithic test urlconf (``config.urls``), which
    has EVERY route — so it cannot catch a reverse that is missing only on the
    public host. That blind spot is exactly what 500'd the login page (a bare
    ``{% url 'resend_signup_verification' %}`` that reverses in dev's combined
    urlconf but NoReverseMatch'd per-host in prod).

    These tests render the two later wizard templates (which extend ``base.html``
    and carry the cross-host launchpad links) with ``ROOT_URLCONF`` pinned to
    ``config.public_urls``, so any reverse that does not resolve on the public
    host raises NoReverseMatch here instead of in front of a new owner."""

    def setUp(self):
        # A real request (not render_to_string) so base.html's context
        # processors run AND request.urlconf resolves to the public host.
        self.user, self.school = _make_owner(
            username="render", email="render@cedar.test"
        )
        self.client.force_login(
            self.user, backend="django.contrib.auth.backends.ModelBackend"
        )

    def test_school_step_renders_on_public_host(self):
        # 200 here means every {% url %} in school.html + base.html resolves on
        # the public urlconf — a per-host NoReverseMatch would surface as a 500.
        r = self.client.get(reverse("accounts:owner_onboarding_school"))
        self.assertEqual(r.status_code, 200)

    def test_done_launchpad_renders_on_public_host(self):
        # done.html reverses accounts:tenant_identity_invite / school_studio /
        # accounts:redirect — the guarded ``{% url as %}`` pattern must keep this
        # from 500-ing even when a target is tenant-only and absent on public.
        r = self.client.get(reverse("accounts:owner_onboarding_done"))
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"dashboard", r.content.lower())

    def test_account_step_bare_reverses_resolve_on_public_host(self):
        # account.html's only non-guarded reverse is the accounts:login fallback;
        # accounts is mounted at /authentication/ on the public host, so it must
        # resolve there. (Full CBV render needs reset-token form context; this
        # pins the reverse that would 500 the page if accounts were unmounted.)
        from django.urls import reverse

        self.assertTrue(reverse("accounts:login").startswith("/authentication/"))
        self.assertTrue(
            reverse(
                "accounts:owner_onboarding_account",
                kwargs={"uidb64": "abc", "token": "x-y"},
            ).startswith("/authentication/onboarding/account/")
        )

    def test_account_set_password_step_renders_on_public_host(self):
        """Full PasswordResetConfirmView dance on the public urlconf — catches
        NoReverseMatch in base.html (command_bar_actions was the 2026-06-08 prod
        500 that walled owners out of the wizard → login/MFA dead-end)."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        url = reverse(
            "accounts:owner_onboarding_account", kwargs={"uidb64": uid, "token": token}
        )
        r = self.client.get(url)
        self.assertEqual(r.status_code, 302)
        sentinel = r.url
        self.assertIn("/set-password/", sentinel)
        r2 = self.client.get(sentinel)
        self.assertEqual(
            r2.status_code,
            200,
            msg="set-password step must render on public host, not 500",
        )
        self.assertIn(b"Create a password", r2.content)


class EmailOrUsernameLoginTests(TestCase):
    def setUp(self):
        self.user, _ = _make_owner(
            username="jane", email="jane@cedar.test", activated=True
        )

    def test_login_with_username(self):
        self.assertEqual(authenticate(username="jane", password=STRONG_PW), self.user)

    def test_login_with_email(self):
        self.assertEqual(
            authenticate(username="jane@cedar.test", password=STRONG_PW), self.user
        )

    def test_login_with_email_case_insensitive(self):
        self.assertEqual(
            authenticate(username="JANE@CEDAR.TEST", password=STRONG_PW), self.user
        )

    def test_wrong_password_rejected(self):
        self.assertIsNone(authenticate(username="jane@cedar.test", password="nope"))


class ForgotPasswordRecoveryTests(TestCase):
    def test_never_activated_owner_can_recover(self):
        from apps.accounts.password_reset import PortalPasswordResetForm

        user, _ = _make_owner(
            username="stuck", email="stuck@cedar.test", activated=False
        )
        self.assertFalse(user.has_usable_password())
        form = PortalPasswordResetForm()
        users = list(form.get_users("stuck@cedar.test"))
        # Django's default would have filtered this never-activated owner out.
        self.assertIn(user, users)

    def test_lookup_by_username_too(self):
        from apps.accounts.password_reset import PortalPasswordResetForm

        user, _ = _make_owner(
            username="stuck2", email="stuck2@cedar.test", activated=False
        )
        users = list(PortalPasswordResetForm().get_users("stuck2"))
        self.assertIn(user, users)

    def test_reset_form_validates_a_bare_username(self):
        # Regression for the EmailField trap: a bare username must pass FORM
        # validation (not just get_users), else the "username or email" promise
        # and username recovery are dead at the web boundary.
        from apps.accounts.password_reset import PortalPasswordResetForm

        user, _ = _make_owner(
            username="stuck3", email="stuck3@cedar.test", activated=False
        )
        form = PortalPasswordResetForm(data={"email": "stuck3"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn(user, list(form.get_users(form.cleaned_data["email"])))


class MagicLinkLoginBackendTests(TestCase):
    """B1 regression: verify_signup logs the new owner in with a plain ORM user
    (no ``.backend`` attr) while several AUTHENTICATION_BACKENDS are configured.
    ``login()`` raises ValueError unless the backend is named — which was being
    swallowed, skipping the onboarding redirect and dumping owners on the login
    wall. Assert the named backend authenticates such a user without error."""

    def test_fresh_orm_user_logs_in_with_named_backend(self):
        from django.contrib.auth import BACKEND_SESSION_KEY, SESSION_KEY

        user, _ = _make_owner(username="ml", email="ml@cedar.test", activated=True)
        request = RequestFactory().get("/verify-signup/")
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        backend = "django.contrib.auth.backends.ModelBackend"
        self.assertIn(backend, settings.AUTHENTICATION_BACKENDS)
        auth_login(request, user, backend=backend)  # must NOT raise ValueError
        # login() only sets request.user when the request already carries one
        # (AuthenticationMiddleware adds it in real requests); assert the session
        # instead, which is what actually persists the logged-in owner.
        self.assertEqual(request.session[SESSION_KEY], str(user.pk))
        self.assertEqual(request.session[BACKEND_SESSION_KEY], backend)
