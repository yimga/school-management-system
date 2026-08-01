"""Applying a blueprint must visibly land, and must not double-install.

Reported as "clicking apply spins endlessly / nothing happens". It is not a
spinner: the service worker passes every non-GET straight through and the
offline queue only binds forms marked ``data-rmc-offline-form``, so the POST
always reaches Django. What made it *look* like nothing happened is that the
page rendered after the apply was built BEFORE it: the preview, the readiness
meter, and the Apply button were all computed at the top of the view, so a
successful apply re-rendered a page identical to the one the user just
submitted — same enabled "Apply tenant blueprint" button, no trace of the
install. The natural response is to click again.

Clicking again was not harmless. The idempotency key hashed the whole preview,
and the preview embeds a live installation COUNT, so the second click hashed
differently, missed the duplicate guard, and wrote a second installation row.

These tests pin both halves: the apply is visible, and repeating it is inert.
"""
from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.platform_runtime.models import BlueprintInstallation
from apps.schools.models import School, SchoolMembership

BLUEPRINT = "private-primary-school"


@override_settings(
    ALLOWED_HOSTS=["*", "apply-feedback.runmycampus.com"],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class TenantBlueprintApplyFeedbackTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Apply Feedback",
            slug="apply-feedback",
            subdomain="apply-feedback",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username="apply_feedback_admin",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        TOTPDevice.objects.create(user=self.admin, name="test-device", confirmed=True)

    def _client(self):
        client = Client(
            HTTP_HOST="apply-feedback.runmycampus.com", raise_request_exception=False
        )
        client.login(username="apply_feedback_admin", password="x" * 8)
        session = client.session
        session["mfa_verified"] = True
        session.save()
        return client

    def _apply(self, client):
        return client.post(
            "/school/setup/blueprints/",
            {"blueprint": BLUEPRINT, "confirm": "yes"},
        )

    def test_apply_lands_and_the_page_says_so(self):
        client = self._client()

        response = self._apply(client)

        self.assertEqual(response.status_code, 200, msg=response.content[:400])
        self.assertTrue(
            BlueprintInstallation.objects.filter(
                school=self.school,
                blueprint_key=BLUEPRINT,
                status=BlueprintInstallation.Status.APPLIED,
            ).exists(),
            msg="The POST must actually install, not just render a banner.",
        )
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Blueprint applied", body)

    def test_page_after_apply_reflects_the_install(self):
        # The reported symptom. A page that still offers a fresh "Apply" and
        # shows no installed state is indistinguishable from one where nothing
        # happened — which is exactly how it was described.
        client = self._client()

        response = self._apply(client)
        body = response.content.decode("utf-8", errors="replace")

        self.assertIn(
            "Applied",
            body,
            msg="The post-apply page must show that this blueprint is installed.",
        )
        self.assertNotIn(
            "Apply tenant blueprint",
            body,
            msg="An already-applied blueprint must not re-offer a plain Apply button.",
        )

    def test_applying_twice_does_not_create_a_second_installation(self):
        client = self._client()

        self._apply(client)
        self._apply(client)

        self.assertEqual(
            BlueprintInstallation.objects.filter(
                school=self.school, blueprint_key=BLUEPRINT
            ).count(),
            1,
            msg="A repeated apply must be idempotent, not a second install row.",
        )

    def test_preview_reports_the_active_installation_count(self):
        # active_same_blueprint was hardcoded 0, so nothing downstream could
        # tell whether this very blueprint was already applied.
        from apps.platform_runtime.blueprint_preview import preview_blueprint

        client = self._client()
        self._apply(client)

        counts = preview_blueprint(BLUEPRINT, school=self.school)["audit_summary"][
            "tenant_counts"
        ]

        self.assertEqual(counts["blueprint_installations"], 1)
        self.assertEqual(counts["active_same_blueprint"], 1)
