"""Per-aspect infrastructure waivers on the Edge Onboarding Runbook.

Not every campus has an uplink, LAN DNS, USB disk, SIS files, or a logo. A
checklist that can only FAIL those sites is a checklist nobody finishes. Each
waivable line takes a written reason of at least 12 characters. Owner login and
SECRET_KEY stay non-waivable. A blank skip is not a skip.
"""
from __future__ import annotations

from io import StringIO
import json
import os
import tempfile
import time
import uuid
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from apps.academics.models import AcademicYear
from apps.billing.models import Entitlement
from apps.lifecycle import edge_onboarding
from apps.lifecycle.onboarding_waivers import WAIVABLE_ASPECTS, WAIVE_BY_KEY
from apps.people.models import StudentProfile
from apps.schools.conversion_lock_state import record_conversion_first_action
from apps.schools.models import School, SchoolMembership
from apps.schools.rls_context import rls_bypass
from apps.sync_engine.models import EdgeSyncRun

REASON = "No uplink at this campus — sovereign-only box."


def _school(**overrides):
    with rls_bypass():
        School.objects.filter(slug="waiver-lab").delete()
    kwargs = dict(
        id=uuid.uuid4(),
        name="Waiver Lab School",
        slug="waiver-lab",
        subdomain="waiver-lab",
        is_active=True,
        is_approved=True,
        country_code="CM",
        settings={},
    )
    kwargs.update(overrides)
    return School.objects.create(**kwargs)


def _write_state(payload):
    handle, path = tempfile.mkstemp(suffix=".json")
    os.close(handle)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return path


class CatalogIsTheSingleListTests(SimpleTestCase):
    def test_every_infrastructure_key_is_catalogued(self):
        keys = {row.key for row in WAIVABLE_ASPECTS}
        self.assertEqual(
            keys,
            {
                "migration_cloud_apply",
                "media_branding",
                "seed_operational_data",
                "conversion_first_action",
                "configure_lan_hostname",
                "enable_configure_sync",
                "verify_and_sync_gate",
                "live_sync_proof",
                "box_backup_verified",
                "offbox_copy",
            },
        )

    def test_identity_and_secret_key_are_not_in_the_catalog(self):
        for banned in (
            "migrate_identities",
            "cloud_entitle_pin",
            "configure_box_env",
            "go_dark_checklist",
            "provision_shell",
        ):
            self.assertNotIn(banned, WAIVE_BY_KEY)

    def test_offbox_form_lives_on_the_backup_step(self):
        self.assertEqual(WAIVE_BY_KEY["offbox_copy"].form_step(), "box_backup_verified")

    def test_every_form_lands_on_a_real_runbook_step(self):
        keys = set(edge_onboarding.EDGE_ONBOARDING_STEP_KEYS)
        for row in WAIVABLE_ASPECTS:
            self.assertIn(row.form_step(), keys, row.key)

    def test_unknown_aspect_cannot_be_recorded(self):
        school = SimpleNamespace(settings={}, pk=1)
        ok, detail = edge_onboarding.set_aspect_skip_reason(
            school, "migrate_identities", REASON
        )
        self.assertFalse(ok)
        self.assertIn("Unknown waivable aspect", detail)


class AShortReasonIsNotASkipTests(TestCase):
    def test_eleven_characters_do_not_waive(self):
        school = _school()
        ok, _ = edge_onboarding.set_aspect_skip_reason(
            school, "live_sync_proof", "too short!!"
        )
        self.assertFalse(ok)
        self.assertFalse(edge_onboarding.aspect_is_waived(school, "live_sync_proof"))
        live_ok, live_detail = edge_onboarding._validate_live_sync_proof(school)
        self.assertFalse(live_ok)
        self.assertIn("No live", live_detail)


class TwelveCharactersClearsEachAspectTests(TestCase):
    def test_each_catalogued_aspect_passes_its_validate(self):
        school = _school()
        missing = os.path.join(tempfile.gettempdir(), "rmc-no-such-backup-state.json")
        for row in WAIVABLE_ASPECTS:
            if row.key == "offbox_copy":
                continue
            recorded, _ = edge_onboarding.set_aspect_skip_reason(school, row.key, REASON)
            self.assertTrue(recorded, row.key)
            validate = {
                "migration_cloud_apply": edge_onboarding._validate_migration_cloud_apply,
                "media_branding": edge_onboarding._validate_media_branding,
                "seed_operational_data": edge_onboarding._validate_seed_operational_data,
                "conversion_first_action": edge_onboarding._validate_conversion_first_action,
                "configure_lan_hostname": edge_onboarding._validate_lan_hostname,
                "enable_configure_sync": edge_onboarding._validate_enable_configure_sync,
                "verify_and_sync_gate": edge_onboarding._validate_verify_and_sync_gate,
                "live_sync_proof": edge_onboarding._validate_live_sync_proof,
                "box_backup_verified": edge_onboarding._validate_box_backup_verified,
            }[row.key]
            with override_settings(RMC_BOX_BACKUP_STATE_FILE=missing):
                ok, detail = validate(school)
            self.assertTrue(ok, "%s: %s" % (row.key, detail))
            blob = detail.lower()
            self.assertTrue(
                "waived by operator" in blob or "skipped by operator" in blob,
                "%s: %s" % (row.key, detail),
            )


class GoDarkHonoursWaiversTests(TestCase):
    def test_dry_and_live_waived_clears_without_an_edgesyncrun(self):
        school = _school()
        with rls_bypass():
            StudentProfile.objects.create(
                school=school, first_name="Ada", last_name="Okoro", student_code="S1"
            )
        record_conversion_first_action(school, source="waiver-test")
        school.refresh_from_db()
        self.assertTrue(
            edge_onboarding.set_aspect_skip_reason(school, "verify_and_sync_gate", REASON)[0]
        )
        self.assertTrue(
            edge_onboarding.set_aspect_skip_reason(school, "live_sync_proof", REASON)[0]
        )
        self.assertTrue(
            edge_onboarding.set_aspect_skip_reason(
                school, "box_backup_verified", "Lab box — dump already on USB stick."
            )[0]
        )
        self.assertEqual(EdgeSyncRun.objects.filter(school=school).count(), 0)
        missing = os.path.join(tempfile.gettempdir(), "rmc-no-such-backup-state.json")
        with override_settings(RMC_BOX_BACKUP_STATE_FILE=missing):
            ok, detail = edge_onboarding._validate_go_dark_checklist(school)
        self.assertTrue(ok, detail)
        self.assertIn("dry-gate=waived", detail)
        self.assertIn("live=waived", detail)
        self.assertIn("conflicts=n/a", detail)
        self.assertIn("backup=waived", detail)
        self.assertIn("Go-dark checklist cleared", detail)

    def test_empty_roster_still_blocks_when_not_waived(self):
        school = _school()
        record_conversion_first_action(school, source="waiver-test")
        school.refresh_from_db()
        for key in ("verify_and_sync_gate", "live_sync_proof", "box_backup_verified"):
            self.assertTrue(edge_onboarding.set_aspect_skip_reason(school, key, REASON)[0])
        missing = os.path.join(tempfile.gettempdir(), "rmc-no-such-backup-state.json")
        with override_settings(RMC_BOX_BACKUP_STATE_FILE=missing):
            ok, detail = edge_onboarding._validate_go_dark_checklist(school)
        self.assertFalse(ok)
        self.assertIn("roster=empty", detail)
        self.assertIn("at least 12 characters", detail)


class OffBoxWaiverOnlyRewritesAVerifiedDumpTests(TestCase):
    def test_verified_dump_without_usb_warns_until_waived(self):
        dump = "rmc-box-db-20260901T020000Z.dump.enc"
        payload = {
            "schema": 1,
            "last_file": dump,
            "last_success_epoch": int(time.time()),
            "verified_at": "2026-09-01T02:01:00Z",
            "verified_file": dump,
            "verified_full_read": "true",
            "verified_toc_entries": 40,
            "offbox_independent": "false",
        }
        path = _write_state(payload)
        school = _school()
        try:
            with override_settings(RMC_BOX_BACKUP_STATE_FILE=path):
                ok, detail = edge_onboarding._validate_box_backup_verified(school)
                self.assertTrue(ok, detail)
                self.assertIn("off-box copy is NOT", detail)
                self.assertTrue(
                    edge_onboarding.set_aspect_skip_reason(
                        school, "offbox_copy", "No USB disk or NAS at this site."
                    )[0]
                )
                ok, detail = edge_onboarding._validate_box_backup_verified(school)
            self.assertTrue(ok, detail)
            self.assertIn("off-box copy waived", detail)
            self.assertNotIn("off-box copy is NOT", detail)
        finally:
            os.unlink(path)

    def test_offbox_waiver_does_not_invent_a_dump(self):
        school = _school()
        self.assertTrue(
            edge_onboarding.set_aspect_skip_reason(
                school, "offbox_copy", "No USB disk or NAS at this site."
            )[0]
        )
        missing = os.path.join(tempfile.gettempdir(), "rmc-no-such-backup-state.json")
        with override_settings(RMC_BOX_BACKUP_STATE_FILE=missing):
            ok, detail = edge_onboarding._validate_box_backup_verified(school)
        self.assertFalse(ok)
        self.assertIn("never taken a backup", detail)


class EmptyStaffIsLegitimateTests(TestCase):
    def test_zero_teachers_passes_without_a_skip(self):
        school = _school()
        ok, detail = edge_onboarding._validate_migrate_staff(school)
        self.assertTrue(ok, detail)
        self.assertIn("No teacher profiles", detail)
        self.assertFalse(edge_onboarding.aspect_is_waived(school, "migrate_staff"))


class HostileSchoolNeverRaisesTests(SimpleTestCase):
    def test_every_validate_survives_a_hostile_school(self):
        broken = SimpleNamespace()
        for step in edge_onboarding.EDGE_ONBOARDING_STEPS:
            try:
                outcome = step.validate(broken)
            except Exception as exc:  # noqa: BLE001
                self.fail("%s raised %r" % (step.key, exc))
            self.assertIsInstance(outcome[0], bool, step.key)
            self.assertIsInstance(outcome[1], str, step.key)


class HealsDoNotProbeWhenWaivedTests(TestCase):
    def test_dry_gate_heal_returns_without_touching_the_network(self):
        school = _school()
        self.assertTrue(
            edge_onboarding.set_aspect_skip_reason(school, "verify_and_sync_gate", REASON)[0]
        )
        with mock.patch(
            "apps.lifecycle.edge_onboarding.running_on_edge_box",
            return_value=(True, ""),
        ), mock.patch(
            "apps.lifecycle.edge_onboarding.run_sync_gate",
            side_effect=RuntimeError("must not probe"),
        ):
            ok, detail = edge_onboarding._heal_verify_and_sync_gate(school)
        self.assertTrue(ok, detail)
        self.assertIn("waived by operator", detail)

    def test_live_heal_returns_without_running_a_cycle(self):
        school = _school()
        self.assertTrue(
            edge_onboarding.set_aspect_skip_reason(school, "live_sync_proof", REASON)[0]
        )
        with mock.patch(
            "apps.lifecycle.edge_onboarding.running_on_edge_box",
            return_value=(True, ""),
        ), mock.patch(
            "apps.sync_engine.sync_runner.run_sync_cycle",
            side_effect=RuntimeError("must not cycle"),
        ):
            ok, detail = edge_onboarding._heal_live_sync_proof(school)
        self.assertTrue(ok, detail)
        self.assertIn("waived by operator", detail)


class RunbookSurfacesTheSkipFormsTests(TestCase):
    def test_generate_runbook_attaches_waives_to_the_right_steps(self):
        school = _school()
        runbook = edge_onboarding.generate_runbook(school)
        by_key = {row["key"]: row for row in runbook["steps"]}
        live = by_key["live_sync_proof"]["waives"]
        self.assertEqual([row["key"] for row in live], ["live_sync_proof"])
        backup = by_key["box_backup_verified"]["waives"]
        self.assertEqual(
            [row["key"] for row in backup],
            ["box_backup_verified", "offbox_copy"],
        )
        self.assertEqual(by_key["migrate_identities"]["waives"], [])
        self.assertEqual(by_key["configure_box_env"]["waives"], [])
        self.assertEqual(by_key["go_dark_checklist"]["waives"], [])
        cli = live[0]["cli"]
        self.assertIn(school.slug, cli)
        self.assertIn("edge_onboarding_skip", cli)
        self.assertIn("--aspect live_sync_proof", cli)
        self.assertEqual(live[0]["recorded_chars"], 0)
        self.assertTrue(live[0]["must_record_on_box"])
        mc = by_key["migration_cloud_apply"]["waives"]
        self.assertEqual([row["key"] for row in mc], ["migration_cloud_apply"])
        self.assertFalse(mc[0]["must_record_on_box"])


class BoxSideSkipCommandTests(TestCase):
    def test_list_prints_every_catalog_key(self):
        out = StringIO()
        call_command("edge_onboarding_skip", "--list", stdout=out)
        body = out.getvalue()
        for row in WAIVABLE_ASPECTS:
            self.assertIn(row.key, body)

    def test_records_a_skip_on_this_host(self):
        school = _school()
        out = StringIO()
        call_command(
            "edge_onboarding_skip",
            slug=school.slug,
            aspect="live_sync_proof",
            reason=REASON,
            stdout=out,
        )
        school.refresh_from_db()
        self.assertTrue(edge_onboarding.aspect_is_waived(school, "live_sync_proof"))
        self.assertIn("skip recorded", out.getvalue().lower())
        from apps.lifecycle.models_edge_onboarding import EdgeOnboardingRun

        row = EdgeOnboardingRun.objects.filter(
            school=school, kind="skip_aspect"
        ).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.payload.get("via"), "cli")
        self.assertEqual(row.payload.get("aspect"), "live_sync_proof")

    def test_short_reason_is_a_command_error(self):
        school = _school()
        with self.assertRaises(CommandError):
            call_command(
                "edge_onboarding_skip",
                f"--slug={school.slug}",
                "--aspect=live_sync_proof",
                "--reason=nope",
            )

    def test_unknown_aspect_is_a_command_error(self):
        school = _school()
        with self.assertRaises(CommandError):
            call_command(
                "edge_onboarding_skip",
                f"--slug={school.slug}",
                "--aspect=migrate_identities",
                f"--reason={REASON}",
            )


class OverlayIsPerSchoolTests(TestCase):
    def test_a_skip_on_one_school_does_not_waive_another(self):
        a = _school()
        with rls_bypass():
            School.objects.filter(slug="waiver-lab-b").delete()
        b = School.objects.create(
            id=uuid.uuid4(),
            name="Waiver Lab B",
            slug="waiver-lab-b",
            subdomain="waiver-lab-b",
            is_active=True,
            is_approved=True,
            country_code="CM",
            settings={},
        )
        self.assertTrue(
            edge_onboarding.set_aspect_skip_reason(a, "live_sync_proof", REASON)[0]
        )
        self.assertTrue(edge_onboarding.aspect_is_waived(a, "live_sync_proof"))
        self.assertFalse(edge_onboarding.aspect_is_waived(b, "live_sync_proof"))


class PairingWaiverIsIndependentTests(TestCase):
    def test_pairing_skip_does_not_waive_dry_or_live(self):
        school = _school()
        self.assertTrue(
            edge_onboarding.set_aspect_skip_reason(
                school, "enable_configure_sync", REASON
            )[0]
        )
        self.assertFalse(
            edge_onboarding.aspect_is_waived(school, "verify_and_sync_gate")
        )
        self.assertFalse(edge_onboarding.aspect_is_waived(school, "live_sync_proof"))
        dry_ok, _ = edge_onboarding._validate_verify_and_sync_gate(school)
        live_ok, _ = edge_onboarding._validate_live_sync_proof(school)
        self.assertFalse(dry_ok)
        self.assertFalse(live_ok)


class SovereignOnlyCampusCanFinishTests(TestCase):
    """A box with no uplink, no SIS, no logo, no USB, and no roster can still
    finish the runbook once a login exists and each missing line is waived."""

    def test_waiving_infrastructure_clears_the_full_include_gate_suite(self):
        school = _school()
        User = get_user_model()
        with rls_bypass():
            owner = User.objects.create_user(
                username="waiver_owner",
                email="owner@waiver.school.lan",
                password="x",
            )
            SchoolMembership.objects.create(
                school=school,
                user=owner,
                role="ADMIN",
                is_school_owner=True,
                is_primary=True,
            )
            AcademicYear.objects.create(
                school=school,
                name="2025/2026",
                starts_on="2025-09-01",
                ends_on="2026-07-31",
            )
            Entitlement.objects.create(school=school, code="reports")
        for row in WAIVABLE_ASPECTS:
            self.assertTrue(
                edge_onboarding.set_aspect_skip_reason(school, row.key, REASON)[0],
                row.key,
            )
        missing = os.path.join(tempfile.gettempdir(), "rmc-no-such-backup-state.json")
        with override_settings(
            RMC_BOX_BACKUP_STATE_FILE=missing,
            SECRET_KEY="waiver-audit-secret-key-32chars-min",
        ):
            suite = edge_onboarding.run_verification_suite(school, include_gate=True)
        failed = [
            f"{row['key']}: {row['detail']}"
            for row in suite.get("steps") or []
            if not row.get("ok") and not row.get("skipped")
        ]
        self.assertEqual(failed, [], "sovereign-only suite still red: " + "; ".join(failed))
        self.assertTrue(suite.get("ok"), suite)
