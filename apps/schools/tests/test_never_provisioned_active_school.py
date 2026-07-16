"""An ACTIVE school with no tenant workspace must be fixable. It wasn't.

Found by an A-Z provisioning audit (2026-07-16) against production data.

``School.is_active`` defaults to ``True``, so any row created outside the
provisioning pipeline lands "live" with no schema behind it. Production carries
exactly one (``gilead-school``, 2026-02-22: is_active=True, no provisioning
markers, no workflow runs, no events, NO SCHEMA) and it 500s on every request.

It was unreachable by EVERY tool at once, all off one predicate:

    resolve_portal_ready = phase_a_complete OR is_active   # <- the OR
    provisioning_needs_resume  requires phase_a_complete   # <- bails without it

so the school read as *settled*: the watchdog skipped it, the reconciler's SQL
filter never selected it, ``can_operator_requeue_provisioning`` HID the Requeue
button, and ``operator_requeue_provisioning`` actively raised "Portal is already
ready". Nothing in the repo could repair it.

THE TRAP these tests also pin
-----------------------------
The obvious fix — "require the schema to exist" — is a loaded gun.
``schema_provisioning_repository.schema_exists`` returns **False** on any
non-PostgreSQL connection, so a naive check would declare every school in RLS
mode / SQLite (the entire local + test topology) a husk and re-provision the
platform. Hence the tri-state probe: only a PROVABLE absence downgrades a
school; an unknowable answer must change nothing.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.schools.models import School


def _probe(value):
    """Patch the workspace probe to a fixed tri-state answer."""
    return patch(
        "apps.schools.tenant_workspace.tenant_workspace_exists",
        return_value=value,
    )


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class NeverProvisionedActiveSchoolTests(TestCase):
    """The husk: active, no markers, and the workspace is PROVABLY absent."""

    def setUp(self):
        self.school = School.objects.create(
            name="Gilead School",
            slug="gilead-school-husk",
            subdomain="gilead-school-husk",
            is_active=True,  # the default -- nobody chose this
        )

    def test_husk_is_not_portal_ready(self):
        from apps.schools.provisioning_progress import resolve_portal_ready

        with _probe(False):
            self.assertFalse(
                resolve_portal_ready(self.school),
                "an active school with no tenant workspace is NOT portal-ready -- "
                "it 500s on every request",
            )

    def test_husk_needs_resume(self):
        from apps.schools.provisioning_progress import provisioning_needs_resume

        with _probe(False):
            self.assertTrue(
                provisioning_needs_resume(self.school),
                "a never-provisioned active school must be resumable",
            )

    def test_husk_is_not_settled_so_healers_stop_skipping_it(self):
        from apps.schools.provision_watchdog import _school_is_settled

        with _probe(False):
            self.assertFalse(
                _school_is_settled(self.school),
                "settled=True is what made every healer skip this school",
            )

    def test_operator_requeue_button_is_offered(self):
        from apps.schools.operator_school_lens import can_operator_requeue_provisioning

        with _probe(False):
            self.assertTrue(
                can_operator_requeue_provisioning(self.school),
                "the operator had NO fix button for this school",
            )

    def test_operator_requeue_does_not_raise_portal_already_ready(self):
        from apps.schools.operator_school_lens import operator_requeue_provisioning

        with _probe(False), patch(
            "apps.schools.tasks.kick_complete_provisioning_background"
        ) as kick:
            result = operator_requeue_provisioning(self.school)
        self.assertTrue(result.get("ok"))
        kick.assert_called_once()

    def test_reconciler_discovers_the_husk(self):
        """The SQL filter requires phase_a_complete -- a husk has no marker.

        Asserts THIS school is among those requeued rather than an exact count:
        ``schools/0012_seed_default_gilead_school`` seeds its own never-provisioned
        ``gilead-school`` into every database (see ``tenant_workspace``), so a
        clean tree legitimately holds more than one husk.
        """
        from apps.schools.tasks import reconcile_half_provisioned_tenants

        with _probe(False), patch(
            "apps.schools.tasks.dispatch_provision_school"
        ) as dispatch:
            result = reconcile_half_provisioned_tenants(limit=25)

        self.assertGreaterEqual(
            result.get("husks_requeued"),
            1,
            "the reconciler must find an active school that was never provisioned",
        )
        requeued_ids = {call.args[0] for call in dispatch.call_args_list}
        self.assertIn(str(self.school.id), requeued_ids)

    def test_do_provision_actually_drives_the_husk(self):
        """_do_provision bails on is_active unless needs_resume says otherwise."""
        from apps.schools.tasks import provision_school_sync

        with _probe(False):
            provision_school_sync(str(self.school.id), contact_email="o@husk.test")

        self.school.refresh_from_db()
        prov = (self.school.settings or {}).get("provisioning") or {}
        self.assertTrue(
            prov.get("phase_a_complete"),
            "the drive must run the pipeline instead of skipping an 'active' husk",
        )


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class UnknowableWorkspaceChangesNothingTests(TestCase):
    """The guard-rail: None (RLS mode / SQLite) is NOT absence.

    If these regress, the whole local + test topology reads as unprovisioned and
    the platform re-provisions every school it has.
    """

    def setUp(self):
        self.school = School.objects.create(
            name="Legacy Academy",
            slug="legacy-academy",
            subdomain="legacy-academy",
            is_active=True,
        )

    def test_unknowable_probe_keeps_legacy_school_ready(self):
        from apps.schools.provisioning_progress import resolve_portal_ready

        with _probe(None):
            self.assertTrue(
                resolve_portal_ready(self.school),
                "an unanswerable probe must NOT downgrade a school",
            )

    def test_unknowable_probe_does_not_request_a_resume(self):
        from apps.schools.provisioning_progress import provisioning_needs_resume

        with _probe(None):
            self.assertFalse(
                provisioning_needs_resume(self.school),
                "None must never be read as 'never provisioned' -- that would "
                "re-provision every school in RLS mode",
            )

    def test_present_workspace_keeps_legacy_school_ready(self):
        from apps.schools.provisioning_progress import (
            provisioning_needs_resume,
            resolve_portal_ready,
        )

        with _probe(True):
            self.assertTrue(resolve_portal_ready(self.school))
            self.assertFalse(provisioning_needs_resume(self.school))

    def test_probe_is_none_on_this_sqlite_test_database(self):
        """Calibration: the REAL probe must answer None here, not False."""
        from apps.schools.tenant_workspace import tenant_workspace_exists

        self.assertIsNone(
            tenant_workspace_exists(self.school, use_cache=False),
            "on a non-schema-mode backend the probe must be unknowable -- if this "
            "returns False, schema_exists()'s non-postgres no-op is leaking through "
            "and every local school looks like a husk",
        )

    def test_marker_backed_school_never_pays_a_probe(self):
        """phase_a_complete short-circuits: no probe query on the hot poll path."""
        from apps.schools.provisioning_progress import resolve_portal_ready

        self.school.settings = {"provisioning": {"phase_a_complete": True}}
        self.school.save(update_fields=["settings"])
        with patch(
            "apps.schools.tenant_workspace.tenant_workspace_exists"
        ) as probe:
            self.assertTrue(resolve_portal_ready(self.school))
        probe.assert_not_called()


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class InactiveSchoolIsNotAHuskTests(TestCase):
    """An inactive school is the normal pre-provision state, not a husk."""

    def test_inactive_school_needs_no_resume(self):
        from apps.schools.provisioning_progress import provisioning_needs_resume

        school = School.objects.create(
            name="Fresh Signup",
            slug="fresh-signup",
            subdomain="fresh-signup",
            is_active=False,
        )
        with _probe(False):
            self.assertFalse(
                provisioning_needs_resume(school),
                "an inactive school is handled by the normal provisioning path",
            )
