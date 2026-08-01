"""`provision_sovereign_school --create` must stand up a USABLE sovereign box.

The fresh-edge-box gap (2026-08-01 self-host audit): an empty database has no
School and no login. `provision_sovereign_school` used to REQUIRE the school to
already exist ("Create the tenant first") and `ensure_gilead_sovereignty_entitlements`
fails closed when it is absent — so a first-time self-host operator following the
docs got an empty, un-loginable box. The `--create` path closes that: it invokes
the real, self-verifying `create_school` engine under the canonical `gilead-tech`
slug, then runs the existing entitle + offline chain, in one command.

These are must-FIRE, effect-probing tests: they assert the school is genuinely
usable (active, resolvable, the owner AUTHENTICATES), sovereign-entitled, and
offline-enabled — not merely that the command returned. They also lock the
guards (create needs --email; the slug must be Gilead-resolvable) and prove the
non-create behaviour is unchanged.
"""
from __future__ import annotations

from io import StringIO

from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.billing.management.commands.ensure_gilead_sovereignty_entitlements import (
    GILEAD_SLUGS,
)
from apps.schools.models import School

User = get_user_model()

_OWNER_EMAIL = "owner@gilead.school.lan"
_OWNER_PW = "Str0ngGileadPass"


@override_settings(MULTI_TENANT_BASE_DOMAIN="gilead.school.lan")
class ProvisionSovereignSchoolCreateTests(TestCase):
    def _run_create(self, **overrides):
        opts = dict(
            create=True,
            email=_OWNER_EMAIL,
            password=_OWNER_PW,
            name="Gilead Tech High",
            country="CM",
        )
        opts.update(overrides)
        out, err = StringIO(), StringIO()
        call_command("provision_sovereign_school", stdout=out, stderr=err, **opts)
        return out.getvalue(), err.getvalue()

    def _gilead(self):
        for slug in GILEAD_SLUGS:
            school = School.objects.filter(slug=slug).first()
            if school is not None:
                return school
        return None

    # --- the headline must-fire: empty DB -> usable, entitled, loginable ---- #

    def test_create_on_empty_db_yields_usable_entitled_loginable_school(self):
        self.assertIsNone(self._gilead(), "precondition: no Gilead school yet")

        self._run_create()

        school = self._gilead()
        self.assertIsNotNone(school, "--create did not produce a Gilead school")
        self.assertEqual(school.slug, "gilead-tech")

        # (a) usable: active + resolves the way tenant middleware resolves it
        self.assertTrue(school.is_active, "school must be active after provisioning")
        self.assertTrue(
            School.objects.filter(
                subdomain__iexact=school.subdomain, is_active=True
            ).exists()
            or School.objects.filter(slug__iexact=school.slug, is_active=True).exists(),
            "school would not resolve in tenant middleware",
        )

        # (b) loginable owner: authenticate() actually succeeds (effect, not X=Y)
        authed = authenticate(username=_OWNER_EMAIL, password=_OWNER_PW)
        if authed is None:
            owner = User.objects.filter(email=_OWNER_EMAIL).first()
            self.assertIsNotNone(owner, "owner account was not created")
            authed = authenticate(username=owner.username, password=_OWNER_PW)
        self.assertIsNotNone(
            authed, "owner could NOT authenticate with the provided password"
        )

        # (c) sovereign-entitled: plan bound + complimentary + real entitlements
        school.refresh_from_db()
        self.assertEqual(
            getattr(school.plan, "slug", None),
            "sovereign-self-hosted",
            "school not bound to the sovereign plan",
        )
        self.assertEqual(school.billing_type, "COMPLIMENTARY")
        from apps.billing.models import Entitlement

        self.assertGreater(
            Entitlement.objects.filter(school=school, is_enabled=True).count(),
            0,
            "no feature entitlements were materialized",
        )
        enabled_features = sum(
            1 for v in (getattr(school, "features", None) or {}).values() if v
        )
        self.assertGreater(enabled_features, 0, "no features enabled on the school")

        # (d) offline mode on
        self.assertTrue(
            (getattr(school, "features", None) or {}).get("enable_offline_mode"),
            "offline mode was not enabled",
        )

    def test_create_is_idempotent(self):
        self._run_create()
        first = self._gilead()
        self.assertIsNotNone(first)

        # Re-run: must not duplicate, must stay usable, must not raise.
        self._run_create()
        matches = School.objects.filter(slug__in=GILEAD_SLUGS)
        self.assertEqual(matches.count(), 1, "re-run created a duplicate school")
        again = self._gilead()
        self.assertEqual(again.pk, first.pk)
        self.assertTrue(again.is_active)
        # Owner still authenticates after the second pass.
        self.assertIsNotNone(
            authenticate(username=_OWNER_EMAIL, password=_OWNER_PW)
            or authenticate(
                username=(User.objects.filter(email=_OWNER_EMAIL).first() or User()).username,
                password=_OWNER_PW,
            )
        )

    def test_no_offline_flag_skips_offline_but_still_entitles(self):
        self._run_create(no_offline=True)
        school = self._gilead()
        self.assertIsNotNone(school)
        self.assertEqual(getattr(school.plan, "slug", None), "sovereign-self-hosted")
        self.assertFalse(
            (getattr(school, "features", None) or {}).get("enable_offline_mode"),
            "--no-offline must not enable offline mode",
        )

    # --- guards ---------------------------------------------------------- #

    def test_create_requires_email(self):
        _out, err = self._run_create(email="")
        self.assertIn("requires --email", err)
        self.assertIsNone(self._gilead(), "no school should be created without --email")

    def test_create_refuses_non_gilead_slug(self):
        _out, err = self._run_create(slug="totally-not-gilead")
        self.assertIn("not a Gilead slug", err)
        self.assertEqual(
            School.objects.count(), 0, "a non-resolvable school must not be created"
        )

    def test_dry_run_create_writes_nothing(self):
        out, _err = self._run_create(dry_run=True)
        self.assertIn("DRY RUN", out)
        self.assertIsNone(self._gilead(), "dry-run must not create a school")

    # --- backward compatibility ----------------------------------------- #

    def test_without_create_and_no_school_errors_unchanged(self):
        # The historical behaviour: no --create, no school -> error, no creation.
        out, err = StringIO(), StringIO()
        call_command("provision_sovereign_school", stdout=out, stderr=err)
        self.assertIn("Sovereign school not found", err.getvalue())
        self.assertEqual(School.objects.count(), 0)
