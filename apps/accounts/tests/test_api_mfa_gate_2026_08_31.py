"""The MFA wall must hold on the JSON API, and must not fall on a machine.

FINDING (measured at HEAD before the fix, by this same test file's fixtures)
---------------------------------------------------------------------------
``RequireMFAMiddleware.BYPASS_PREFIXES`` carried ``"/api/"`` with no explaining
comment while every neighbour carried one. For a school-owner ADMIN whose role
requires MFA and who has enrolled no TOTP device:

    GET  /dashboard/             302 -> /authentication/mfa/setup/?legacy=1
    GET  /finance/               302 -> /authentication/mfa/setup/?legacy=1
    GET  /people/                302 -> /authentication/mfa/setup/?legacy=1
    GET  /api/auth/profile/      200  {"username": ..., "email": ..., "role": "ADMIN"}
    GET  /api/entities/students/ 200  {"results": [{"first_name": "Ada", ...}]}
    POST /api/auth/token/        200  {"access": "<JWT>"}
    GET  /api/auth/profile/      200  with that Bearer JWT

The wall was HTML-only, and a password could be exchanged for a bearer token
that walked around it. Both doors are closed below; the tests that assert 403
are the regression seal.

THE TRAP THIS FILE ALSO GUARDS
------------------------------
The sovereign edge box authenticates with an opaque machine credential that
resolves to a HUMAN row -- routinely a superuser with no TOTP app, because a box
owns no phone. A gate that asked "does this principal need MFA?" after DRF
authentication would have 403'd the entire edge sync rail.
``test_edge_machine_credential_still_reaches_the_sync_rail`` drives a really
minted credential through the full middleware stack, and
``test_the_edge_service_account_is_itself_mfa_required`` proves that test is not
vacuous: the very same user IS refused when it arrives as a browser session.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.api_mfa import MFA_ENROLLMENT_REQUIRED_CODE, api_gate_applies
from apps.accounts.middleware import RequireMFAMiddleware
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.edge_outbox import mint_edge_credential

User = get_user_model()

HOST = "mfagate-school.runmycampus.com"
# The box tests get their own tenant host: a host that does not match the
# school under test resolves to no tenant and the request never reaches the
# view, which reads as a failure of the gate rather than of the fixture.
BOX_HOST = "mfagate-box.runmycampus.com"
# /ws/wal/ is mounted in config.urls and config.manager_urls, NOT in
# config.tenant_urls -- on a tenant host it is a genuine 404. "testserver"
# gets config.urls, which is where the stub actually lives.
BASE_HOST = "testserver"
PASSWORD = "MfaGate123!xQ"


def _make_totp(user):
    from django_otp.plugins.otp_totp.models import TOTPDevice

    return TOTPDevice.objects.create(user=user, name="test-totp", confirmed=True)


@override_settings(
    ALLOWED_HOSTS=["*", HOST, "testserver"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class ApiMfaEnrollmentGateTests(TestCase):
    """A session or a JWT held by an un-enrolled, MFA-required principal."""

    def setUp(self):
        self.school = School.objects.create(
            name="MfaGate School",
            slug="mfagate-school",
            subdomain="mfagate-school",
            is_active=True,
        )
        # Role ADMIN + active school owner => principal_requires_strict_mfa pins
        # the posture to "strict", so the verdict does not depend on whatever
        # mfa_enforcement_mode this tenant happens to carry.
        self.admin = User.objects.create_user(
            username="mfagate-admin@example.com",
            email="mfagate-admin@example.com",
            password=PASSWORD,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
            is_school_owner=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Njoya",
            date_of_birth="2012-01-01",
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get(self, path, **extra):
        return self.client.get(path, HTTP_HOST=HOST, **extra)

    def _assert_mfa_refusal(self, response, where):
        self.assertEqual(
            response.status_code, 403, f"{where}: expected 403, got {response.status_code}"
        )
        self.assertIn("application/json", response["Content-Type"], where)
        # An API client cannot follow a redirect to an HTML enrolment page.
        self.assertNotIn("Location", response, f"{where}: must not redirect")
        body = json.loads(response.content.decode())
        self.assertEqual(body.get("code"), MFA_ENROLLMENT_REQUIRED_CODE, where)
        self.assertIn("mfa_setup_url", body, where)
        self.assertIn("/mfa/setup", body["mfa_setup_url"], where)
        self.assertTrue(body.get("detail"), where)
        return body

    def _obtain_jwt(self, username, password=PASSWORD):
        response = self.client.post(
            "/api/auth/token/",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
            HTTP_HOST=HOST,
        )
        return response

    # ── the wall the finding was measured against ────────────────────────────

    def test_html_wall_still_redirects_an_unenrolled_admin(self):
        """The precondition. If this stops walling, the API assertions are void."""
        self.client.force_login(self.admin)
        for path in ("/dashboard/", "/finance/", "/people/"):
            response = self._get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/mfa/setup", response.url, path)

    # ── door 1: the session cookie ───────────────────────────────────────────

    def test_session_api_call_is_refused_with_a_machine_readable_403(self):
        self.client.force_login(self.admin)
        response = self._get("/api/auth/profile/")
        body = self._assert_mfa_refusal(response, "/api/auth/profile/")
        self.assertEqual(body.get("path"), "/api/auth/profile/")

    def test_tenant_data_endpoint_no_longer_serves_rows(self):
        self.client.force_login(self.admin)
        response = self._get("/api/entities/students/")
        self._assert_mfa_refusal(response, "/api/entities/students/")
        self.assertNotIn(b"Njoya", response.content)

    def test_session_claims_endpoint_is_refused(self):
        self.client.force_login(self.admin)
        self._assert_mfa_refusal(self._get("/api/session/claims/"), "/api/session/claims/")

    # ── door 2: the JWT minted from the same password ────────────────────────

    def test_token_endpoint_stays_reachable(self):
        """Never wall the way in, or enrolment becomes unreachable for a client."""
        response = self._obtain_jwt(self.admin.username)
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertIn("access", response.json())

    def test_jwt_bearer_cannot_route_around_the_wall(self):
        access = self._obtain_jwt(self.admin.username).json()["access"]
        self.assertEqual(len(access.split(".")), 3, "sanity: a JWT has 3 segments")
        self.client.logout()
        response = self._get(
            "/api/auth/profile/", HTTP_AUTHORIZATION=f"Bearer {access}"
        )
        self._assert_mfa_refusal(response, "JWT /api/auth/profile/")

    # ── who must NOT be affected ─────────────────────────────────────────────

    def test_enrolled_admin_is_unaffected(self):
        _make_totp(self.admin)
        self.client.force_login(self.admin)
        response = self._get("/api/auth/profile/")
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertEqual(response.json().get("role"), "ADMIN")

    def test_role_that_does_not_require_mfa_is_unaffected(self):
        teacher = User.objects.create_user(
            username="mfagate-teacher@example.com",
            email="mfagate-teacher@example.com",
            password=PASSWORD,
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=teacher, school=self.school, role=User.Role.TEACHER, is_primary=True
        )
        self.client.force_login(teacher)
        response = self._get("/api/auth/profile/")
        self.assertEqual(response.status_code, 200, response.content[:200])

    def test_anonymous_api_call_is_not_touched_by_this_gate(self):
        response = self._get("/api/auth/profile/")
        self.assertIn(response.status_code, (401, 403))
        self.assertNotIn(MFA_ENROLLMENT_REQUIRED_CODE, response.content.decode())

    def test_public_probes_stay_open_for_a_walled_principal(self):
        self.client.force_login(self.admin)
        for path in ("/api/health/", "/api/schema/"):
            response = self._get(path)
            self.assertNotEqual(response.status_code, 403, path)
            self.assertNotIn(MFA_ENROLLMENT_REQUIRED_CODE, response.content.decode(errors="ignore"), path)

    def test_the_enrolment_page_itself_stays_reachable(self):
        """The way out of the wall. Walling it would be a permanent lockout."""
        self.client.force_login(self.admin)
        response = self._get("/authentication/mfa/setup/?legacy=1")
        self.assertEqual(response.status_code, 200, response.status_code)

    def test_no_mfa_enrolment_route_lives_under_slash_api(self):
        """Why the /api/ gate cannot trap anybody: enrolment is not on /api/.

        Enumerated over BOTH urlconfs -- the tenant host gets config.tenant_urls
        and only a dev/base host gets config.urls, so checking one proves nothing
        about the other.
        """
        import importlib

        from django.urls.resolvers import RegexPattern, URLPattern, URLResolver

        def walk(resolver, prefix=""):
            for entry in resolver.url_patterns:
                if isinstance(entry, URLResolver):
                    yield from walk(entry, prefix + str(entry.pattern))
                elif isinstance(entry, URLPattern):
                    yield prefix + str(entry.pattern)

        needles = ("mfa", "passkey", "webauthn", "totp", "otp/")
        for modname in ("config.urls", "config.tenant_urls"):
            resolver = URLResolver(RegexPattern(r"^/"), importlib.import_module(modname))
            routes = {"/" + route.lstrip("^") for route in walk(resolver)}
            api_routes = [r for r in routes if r.startswith("/api/")]
            self.assertGreater(len(api_routes), 100, f"{modname}: enumeration looks broken")
            offenders = [
                r for r in api_routes if any(n in r.lower() for n in needles)
            ]
            self.assertEqual(
                offenders,
                [],
                f"{modname}: an MFA-enrolment route now lives under /api/ and would "
                f"be walled by the gate; exempt it in api_mfa.API_MFA_EXEMPT_PREFIXES",
            )

    def test_exempt_prefix_table_is_honoured_exactly(self):
        self.assertTrue(api_gate_applies("/api/auth/profile/"))
        self.assertTrue(api_gate_applies("/api/entities/students/"))
        self.assertTrue(api_gate_applies("/api/sync/bundle/download/"))
        self.assertFalse(api_gate_applies("/api/auth/token/"))
        self.assertFalse(api_gate_applies("/api/auth/token/refresh/"))
        self.assertFalse(api_gate_applies("/api/health/"))
        self.assertFalse(api_gate_applies("/api/schema/ui/"))
        self.assertFalse(api_gate_applies("/api/sync/pair/start/"))
        # Not API surface at all.
        self.assertFalse(api_gate_applies("/dashboard/"))
        self.assertFalse(api_gate_applies("/ws/wal/"))
        # "/api/auth/token" must not swallow its sibling "/api/auth/profile".
        self.assertTrue(api_gate_applies("/api/auth/tokenish/"))

    def test_ws_wal_is_not_converted_to_an_html_redirect(self):
        """It answers 401/426 by design.

        Its BYPASS_PREFIXES entry is written "/ws/wal/", but ``path`` reaches the
        middleware de-slashed as "/ws/wal", which does not startswith("/ws/wal/").
        Measured at HEAD: GET /ws/wal/ -> 302 /authentication/mfa/setup/, i.e. the
        entry never fired. _is_bypass_prefix now matches the bare directory too.
        """
        self.client.force_login(self.admin)
        response = self.client.get("/ws/wal/", HTTP_HOST=BASE_HOST)
        self.assertNotEqual(response.status_code, 302, "must not HTML-redirect")
        self.assertIn(response.status_code, (401, 426), response.status_code)

    def test_bypass_prefix_table_no_longer_carries_a_blanket_api_entry(self):
        self.assertNotIn("/api/", RequireMFAMiddleware.BYPASS_PREFIXES)


@override_settings(
    ALLOWED_HOSTS=["*", BOX_HOST, "testserver"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class EdgeMachineCredentialSurvivesTheGateTests(TestCase):
    """Breaking edge sync to close an MFA hole would be a net loss."""

    def setUp(self):
        self.school = School.objects.create(
            name="MfaGate Box School",
            slug="mfagate-box",
            subdomain="mfagate-box",
            is_active=True,
        )
        # The shape apps/api/tests/test_edge_credential_auth.py mints against: a
        # superuser service account with an ADMIN membership and NO TOTP device.
        # principal_requires_strict_mfa() returns True for is_superuser, so this
        # principal is squarely inside the wall.
        self.box_user = User.objects.create_superuser(
            username="mfagate-box@example.com",
            email="mfagate-box@example.com",
            password=PASSWORD,
        )
        SchoolMembership.objects.create(
            user=self.box_user, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.raw_token, self.token_obj = mint_edge_credential(
            self.school, self.box_user, device_id="mfagate-box-1", days=30
        )

    def test_the_edge_service_account_is_itself_mfa_required(self):
        """Non-vacuity: the rail test below only means something if this passes."""
        self.client.force_login(self.box_user)
        response = self.client.get("/api/auth/profile/", HTTP_HOST=BOX_HOST)
        self.assertEqual(response.status_code, 403, response.content[:200])
        self.assertEqual(
            json.loads(response.content.decode()).get("code"),
            MFA_ENROLLMENT_REQUIRED_CODE,
        )

    def test_edge_credential_is_not_jwt_shaped(self):
        """The JWT pre-filter's whole safety rests on this."""
        self.assertEqual(len(self.raw_token.split(".")), 1, self.raw_token)

    def test_edge_machine_credential_still_reaches_the_sync_rail(self):
        """Full middleware stack, real minted credential, no session cookie."""
        response = self.client.get(
            "/api/sync/changes/?wait=0",
            HTTP_HOST=BOX_HOST,
            HTTP_AUTHORIZATION=f"Bearer {self.raw_token}",
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertNotIn(
            MFA_ENROLLMENT_REQUIRED_CODE, response.content.decode(errors="ignore")
        )
        self.assertTrue(response.json().get("ok"), response.content[:300])

    def test_edge_credential_reaches_the_bundle_rail_too(self):
        """SyncBundleDownloadView splats the DEFAULT authentication classes, so
        it is the rail most likely to be caught by a session-shaped gate."""
        response = self.client.get(
            "/api/sync/bundle/download/",
            HTTP_HOST=BOX_HOST,
            HTTP_AUTHORIZATION=f"Bearer {self.raw_token}",
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertNotIn(
            MFA_ENROLLMENT_REQUIRED_CODE, response.content.decode(errors="ignore")
        )
