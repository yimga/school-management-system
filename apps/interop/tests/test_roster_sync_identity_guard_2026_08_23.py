"""A district roster must not rewrite an existing platform user's identity.

``upsert_roster_person`` resolved the shared public-schema ``User`` by bare
``username`` and then overwrote ``first_name`` / ``last_name`` / ``email``
whenever the roster row differed. The module docstring only ever promised that
the *role* is create-only, and ``AbstractUser.email`` is not unique, so the
write always succeeded.

The roster body is tenant-controlled: ``native_classlink_base_url`` comes from
the school's own ``ServiceIntegration`` config, so school A's admin can point
the pull at a server they run and return
``{"username": "principal_b", "email": "attacker@evil.example"}``. School B's
principal then has their platform email replaced and password-reset mail
redirected.

Now: identity fields are create-only, an existing row is only ever FILLED where
it is empty and only for a user who already belongs to the target school, and
the ClassLink base URL is checked (https, no private/loopback/link-local host)
before it is used as a fetch target.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.interop.roster_sync import (
    RosterSyncError,
    classlink_fetch_pages,
    upsert_roster_person,
)
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class RosterIdentityRewriteTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(
            name="Roster A", slug="roster-a", subdomain="roster-a"
        )
        self.school_b = School.objects.create(
            name="Roster B", slug="roster-b", subdomain="roster-b"
        )
        self.principal_b = User.objects.create_user(
            username="principal_b",
            email="principal@schoolb.example",
            password="pass123",
            first_name="Real",
            last_name="Principal",
        )
        SchoolMembership.objects.create(
            user=self.principal_b, school=self.school_b, role="ADMIN", is_primary=True
        )

    def _person(self, **over):
        person = {
            "source_id": "1",
            "username": "principal_b",
            "email": "attacker@evil.example",
            "first_name": "Att",
            "last_name": "Acker",
            "role": "parent",
        }
        person.update(over)
        return person

    def test_foreign_user_identity_is_not_rewritten_by_a_roster_row(self):
        result = upsert_roster_person(self.school_a, self._person())

        # Vacuity guard: the upsert really did resolve THIS user and take the
        # existing-row branch — so the assertions below sit on the code path
        # that used to do the overwrite, not on an early return.
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["created"])
        self.assertEqual(result["user_id"], self.principal_b.pk)

        self.principal_b.refresh_from_db()
        self.assertEqual(self.principal_b.email, "principal@schoolb.example")
        self.assertEqual(self.principal_b.first_name, "Real")
        self.assertEqual(self.principal_b.last_name, "Principal")

    def test_new_username_still_creates_with_the_roster_values(self):
        # Control: the create path is untouched, so a green run above is not a
        # green run on a resolver that stopped working.
        result = upsert_roster_person(
            self.school_a, self._person(username="new_teacher", role="teacher")
        )
        self.assertTrue(result["created"], result)
        created = User.objects.get(username="new_teacher")
        self.assertEqual(created.email, "attacker@evil.example")
        self.assertTrue(
            SchoolMembership.objects.filter(
                user=created, school=self.school_a
            ).exists()
        )

    def test_empty_field_on_an_existing_member_is_still_filled(self):
        member = User.objects.create_user(
            username="member_a", email="", password="pass123"
        )
        SchoolMembership.objects.create(
            user=member, school=self.school_a, role="TEACHER", is_primary=True
        )
        upsert_roster_person(
            self.school_a,
            self._person(username="member_a", email="member@schoola.example"),
        )
        member.refresh_from_db()
        self.assertEqual(member.email, "member@schoola.example")
        self.assertEqual(member.first_name, "Att")


class ClasslinkBaseUrlTests(TestCase):
    def _pull(self, base_url):
        return list(classlink_fetch_pages("bearer-token-1234", base_url)())

    def test_private_and_non_https_bases_are_refused(self):
        for base in (
            "http://169.254.169.254/latest/meta-data",
            "http://127.0.0.1:8000/ims/oneroster/v1p1",
            "https://10.10.20.137/ims/oneroster/v1p1",
            "https://localhost/ims/oneroster/v1p1",
            "ftp://roster.example/v1p1",
        ):
            with self.subTest(base=base):
                # The client is stubbed to SUCCEED, so the only thing that can
                # raise is the URL guard. Without this the test passes on the
                # unguarded code purely because the socket connect times out —
                # measuring the network, not the fix.
                with mock.patch(
                    "apps.interop.clever_classlink_client.classlink_list_users",
                    return_value={"users": []},
                ) as listed:
                    with self.assertRaises(RosterSyncError) as ctx:
                        self._pull(base)
                self.assertFalse(
                    listed.called, "the refused base was still fetched"
                )
                self.assertIn("base_url", str(ctx.exception))

    def test_a_public_https_base_is_still_fetched(self):
        with mock.patch(
            "apps.interop.clever_classlink_client.classlink_list_users",
            return_value={"users": [{"sourcedId": "1"}]},
        ) as listed:
            pages = self._pull("https://district.classlink.example/ims/oneroster/v1p1")
        self.assertTrue(listed.called)
        self.assertEqual(pages, [[{"sourcedId": "1"}]])

    def test_an_empty_base_falls_back_to_the_built_in_host(self):
        # Empty means "use the vendor default" (clever_classlink_client applies
        # CLASSLINK_API) — the guard must not turn that into a hard failure.
        with mock.patch(
            "apps.interop.clever_classlink_client.classlink_list_users",
            return_value={"users": []},
        ) as listed:
            self._pull("")
        self.assertTrue(listed.called)
