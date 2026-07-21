"""Program item 4.1 — a third-party credential must authenticate.

Every test here is a MUST-FIRE: each one goes RED when
``apps.api.third_party_auth`` is detached from the v1 CRUD viewsets.

Before this seam existed, a presented ``sk_live_…`` key on
``/api/v1/people/students/`` was rejected by ``JWTAuthentication`` with
``token_not_valid`` — it never reached a resolver. The suite proves the key now
authenticates, reads *only* what its scopes allow, and cannot cross a tenant
boundary.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.apicenter.models import (
    APIKey,
    DeveloperApplication,
    OAuthTokenPair,
    _hash_secret,
)
from apps.marketplace.lifecycle import install_app
from apps.marketplace.models import AppScope, MarketplaceApp, PublisherOrganization
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership

STUDENTS_URL = "/api/v1/people/students/"
TEACHERS_URL = "/api/v1/people/teachers/"
INVOICES_URL = "/api/v1/finance/invoices/"


def _host(school: School) -> str:
    return f"{school.subdomain}.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class ThirdPartyCredentialAuthTests(TestCase):
    """Tenant A holds a students:read-only integration. Tenant B is the victim."""

    @classmethod
    def setUpTestData(cls):
        cls.publisher, _ = PublisherOrganization.objects.get_or_create(
            slug="pub-4-1",
            defaults={
                "name": "Item 4.1 Publisher",
                "verification_status": (
                    PublisherOrganization.VerificationStatus.VERIFIED
                ),
            },
        )
        cls.app = MarketplaceApp.objects.create(
            publisher=cls.publisher,
            slug="roster-sync-4-1",
            name="Roster Sync",
            version="1.0.0",
            kind=MarketplaceApp.AppKind.FIRST_PARTY,
            is_intentionally_free=True,
        )
        AppScope.objects.create(
            app=cls.app, scope_code="students:read", description="Read students"
        )

        cls.school_a = cls._make_school("tp-tenant-a", "Tenant A")
        cls.school_b = cls._make_school("tp-tenant-b", "Tenant B")

        cls.admin_a = cls._make_admin("admin-a@example.com", cls.school_a)
        cls.admin_b = cls._make_admin("admin-b@example.com", cls.school_b)

        # Both tenants install the app; only tenant A issues a key we hold.
        cls.install_a = install_app(
            school=cls.school_a, app=cls.app, grant_scope_codes=["students:read"]
        )
        cls.install_b = install_app(
            school=cls.school_b, app=cls.app, grant_scope_codes=["students:read"]
        )

        cls.raw_key_a, cls.key_a = cls._make_key(
            cls.school_a, cls.admin_a, cls.install_a, name="tenant-a-key"
        )

        cls.student_a = StudentProfile.objects.create(
            school=cls.school_a, first_name="Ada", last_name="Lovelace"
        )
        cls.student_b = StudentProfile.objects.create(
            school=cls.school_b, first_name="Grace", last_name="Hopper"
        )

    # ─── fixtures ──────────────────────────────────────────────────────────

    @classmethod
    def _make_school(cls, slug: str, name: str) -> School:
        return School.objects.create(
            name=name, slug=slug, subdomain=slug, is_active=True
        )

    @classmethod
    def _make_admin(cls, email: str, school: School) -> User:
        user = User.objects.create_user(
            username=email, email=email, password="x-Passw0rd-x", role="ADMIN"
        )
        SchoolMembership.objects.create(user=user, school=school, role="ADMIN")
        return user

    @classmethod
    def _make_key(cls, school, creator, installation, *, name, scopes=None):
        prefix, raw = APIKey.generate_key_pair()
        key = APIKey.objects.create(
            school=school,
            name=name,
            key_prefix=prefix,
            secret_hash=_hash_secret(raw),
            scopes=scopes or [],
            marketplace_installation=installation,
            created_by=creator,
        )
        return raw, key

    def _get(self, url: str, *, school: School, raw: str | None = None):
        headers = {"HTTP_HOST": _host(school)}
        if raw is not None:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {raw}"
        return Client().get(url, **headers)

    # ─── 1. reads exactly what its scopes allow ────────────────────────────

    def test_scoped_key_reads_what_its_scope_allows(self):
        """students:read granted => 200, and the body is tenant A's roster."""
        r = self._get(STUDENTS_URL, school=self.school_a, raw=self.raw_key_a)
        self.assertEqual(r.status_code, 200, msg=r.content[:400])
        body = r.json()
        rows = body["results"] if isinstance(body, dict) else body
        names = {row.get("first_name") for row in rows}
        self.assertIn("Ada", names)
        self.assertNotIn("Grace", names)

    def test_scoped_key_denied_everything_else(self):
        """Only students:read is granted; every other resource is refused.

        The granted read is asserted in the SAME test as the refusals so the
        test cannot pass by the credential simply failing to authenticate:
        removing the auth class reddens the 200, removing the scope gate
        reddens the 403s.
        """
        granted = self._get(STUDENTS_URL, school=self.school_a, raw=self.raw_key_a)
        self.assertEqual(granted.status_code, 200, msg=granted.content[:300])

        for url in (TEACHERS_URL, INVOICES_URL):
            with self.subTest(url=url):
                r = self._get(url, school=self.school_a, raw=self.raw_key_a)
                self.assertEqual(r.status_code, 403, msg=f"{url} -> {r.content[:200]}")

    def test_scoped_key_denied_write_with_only_read_scope(self):
        """students:read must not imply students:write."""
        granted = self._get(STUDENTS_URL, school=self.school_a, raw=self.raw_key_a)
        self.assertEqual(granted.status_code, 200, msg=granted.content[:300])

        r = Client().post(
            STUDENTS_URL,
            data={"first_name": "Mallory", "last_name": "Intruder"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_a}",
            HTTP_HOST=_host(self.school_a),
        )
        self.assertEqual(r.status_code, 403, msg=r.content[:300])
        self.assertFalse(
            StudentProfile.objects.filter(first_name="Mallory").exists(),
            msg="write was refused but the row landed anyway",
        )

    def test_key_with_no_granted_scopes_is_denied(self):
        """Deny-by-default: revoking the grant revokes the read.

        Same credential, two phases — 200 while the grant exists, 403 once it
        is gone. Neither half can pass without both the auth class and the
        scope gate being live.
        """
        from apps.marketplace.models import ScopeGrant

        raw, _key = self._make_key(
            self.school_a, self.admin_a, self.install_a, name="grant-revocable"
        )
        before = self._get(STUDENTS_URL, school=self.school_a, raw=raw)
        self.assertEqual(before.status_code, 200, msg=before.content[:300])

        # Transactional test — the grant removal rolls back after this method.
        ScopeGrant.objects.filter(installation=self.install_a).delete()
        after = self._get(STUDENTS_URL, school=self.school_a, raw=raw)
        self.assertEqual(after.status_code, 403, msg=after.content[:300])

    # ─── 2. cross-tenant denial (the load-bearing test) ────────────────────

    def test_tenant_a_key_cannot_read_tenant_b(self):
        """THE test for item 4.1: A's credential replayed at B's host is 401.

        It must never be 200, and it must never return a single row of B's
        data. Both halves are asserted.
        """
        r = self._get(STUDENTS_URL, school=self.school_b, raw=self.raw_key_a)
        self.assertEqual(
            r.status_code,
            401,
            msg=f"tenant A key reached tenant B: {r.status_code} {r.content[:400]}",
        )
        self.assertNotIn(b"Grace", r.content)
        self.assertNotIn(b"Hopper", r.content)

    def test_tenant_b_data_is_never_visible_to_tenant_a_credential(self):
        """Same credential, both hosts: A's roster only, never B's."""
        ok = self._get(STUDENTS_URL, school=self.school_a, raw=self.raw_key_a)
        self.assertEqual(ok.status_code, 200, msg=ok.content[:300])
        self.assertIn(b"Ada", ok.content)
        self.assertNotIn(b"Hopper", ok.content)

    def test_key_without_tenant_binding_is_refused(self):
        """A NULL-school key must not float onto whichever host presents it."""
        prefix, raw = APIKey.generate_key_pair()
        APIKey.objects.create(
            school=None,
            name="unbound",
            key_prefix=prefix,
            secret_hash=_hash_secret(raw),
            scopes=["students:read"],
            marketplace_installation=self.install_a,
            created_by=self.admin_a,
        )
        for school in (self.school_a, self.school_b):
            with self.subTest(school=school.slug):
                r = self._get(STUDENTS_URL, school=school, raw=raw)
                self.assertEqual(r.status_code, 401, msg=r.content[:300])

    def test_issuer_without_membership_in_bound_school_is_refused(self):
        """The acting principal must actually belong to the bound tenant."""
        raw, _key = self._make_key(
            self.school_a, self.admin_b, self.install_a, name="wrong-issuer"
        )
        r = self._get(STUDENTS_URL, school=self.school_a, raw=raw)
        self.assertEqual(r.status_code, 401, msg=r.content[:300])

    def test_suspended_issuer_membership_revokes_the_credential(self):
        """Offboarding a person offboards the integrations they authorized."""
        user = self._make_admin("leaver@example.com", self.school_a)
        raw, _key = self._make_key(
            self.school_a, user, self.install_a, name="leaver-key"
        )
        self.assertEqual(
            self._get(STUDENTS_URL, school=self.school_a, raw=raw).status_code, 200
        )
        SchoolMembership.objects.filter(user=user, school=self.school_a).update(
            suspended_at=timezone.now()
        )
        self.assertEqual(
            self._get(STUDENTS_URL, school=self.school_a, raw=raw).status_code, 401
        )

    # ─── 3. revoked / expired / unknown fail closed ────────────────────────

    def test_revoked_key_is_rejected(self):
        raw, key = self._make_key(
            self.school_a, self.admin_a, self.install_a, name="to-revoke"
        )
        self.assertEqual(
            self._get(STUDENTS_URL, school=self.school_a, raw=raw).status_code, 200
        )
        key.revoked_at = timezone.now()
        key.save(update_fields=["revoked_at"])
        r = self._get(STUDENTS_URL, school=self.school_a, raw=raw)
        self.assertEqual(r.status_code, 401, msg=r.content[:300])

    def test_unknown_key_is_rejected(self):
        r = self._get(
            STUDENTS_URL, school=self.school_a, raw=APIKey.PREFIX + "not-a-real-secret"
        )
        self.assertEqual(r.status_code, 401, msg=r.content[:300])

    def test_expired_oauth_access_token_is_rejected(self):
        app_key, client_id, raw_secret = DeveloperApplication.generate_credentials()
        application = DeveloperApplication.objects.create(
            name="Roster Sync OAuth",
            app_key=app_key,
            client_id=client_id,
            client_secret_hash=_hash_secret(raw_secret),
            scopes=["students:read"],
            school=self.school_a,
            marketplace_app=self.app,
            created_by=self.admin_a,
        )
        raw_access = "rmc_at_expired-token-value"
        OAuthTokenPair.objects.create(
            application=application,
            user=self.admin_a,
            access_token_hash=_hash_secret(raw_access),
            refresh_token_hash=_hash_secret("rmc_rt_expired"),
            access_expires_at=timezone.now() - timedelta(hours=1),
            scope="students:read",
        )
        r = self._get(STUDENTS_URL, school=self.school_a, raw=raw_access)
        self.assertEqual(r.status_code, 401, msg=r.content[:300])

    def test_live_oauth_access_token_authenticates_and_is_tenant_bound(self):
        app_key, client_id, raw_secret = DeveloperApplication.generate_credentials()
        application = DeveloperApplication.objects.create(
            name="Roster Sync OAuth Live",
            app_key=app_key,
            client_id=client_id,
            client_secret_hash=_hash_secret(raw_secret),
            scopes=["students:read"],
            school=self.school_a,
            marketplace_app=self.app,
            created_by=self.admin_a,
        )
        raw_access = "rmc_at_live-token-value"
        OAuthTokenPair.objects.create(
            application=application,
            user=self.admin_a,
            access_token_hash=_hash_secret(raw_access),
            refresh_token_hash=_hash_secret("rmc_rt_live"),
            access_expires_at=timezone.now() + timedelta(hours=1),
            scope="students:read",
        )
        ok = self._get(STUDENTS_URL, school=self.school_a, raw=raw_access)
        self.assertEqual(ok.status_code, 200, msg=ok.content[:400])
        self.assertIn(b"Ada", ok.content)

        # The same token at tenant B: the issuer holds no membership there and
        # the OAuth path additionally requires an install bound to that host.
        cross = self._get(STUDENTS_URL, school=self.school_b, raw=raw_access)
        self.assertEqual(cross.status_code, 401, msg=cross.content[:400])
        self.assertNotIn(b"Hopper", cross.content)

    # ─── 4. no accidental blanket-open ─────────────────────────────────────

    def test_unauthenticated_request_is_still_rejected(self):
        for url in (STUDENTS_URL, TEACHERS_URL, INVOICES_URL):
            with self.subTest(url=url):
                r = self._get(url, school=self.school_a)
                self.assertIn(r.status_code, (401, 403), msg=f"{url} -> {r.status_code}")
                self.assertNotIn(b"Lovelace", r.content)

    def test_garbage_bearer_value_is_rejected(self):
        r = self._get(STUDENTS_URL, school=self.school_a, raw="totally-bogus")
        self.assertIn(r.status_code, (401, 403), msg=r.content[:300])

    def test_session_authentication_still_works(self):
        """Do not weaken any existing authentication path."""
        client = Client()
        client.force_login(self.admin_a)
        r = client.get(STUDENTS_URL, HTTP_HOST=_host(self.school_a))
        self.assertEqual(r.status_code, 200, msg=r.content[:400])
        self.assertIn(b"Ada", r.content)
