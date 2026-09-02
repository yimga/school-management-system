"""An import onto an appliance must say what will never leave it -- BEFORE it writes.

WHAT WAS WRONG
--------------
The edge delta rail registers 17 entities; 370 models carry a ``school`` relation.
A model that is not registered does not fail to sync -- it produces no error, no
conflict and no refusal. The rows land, the bundle reports APPLIED, and the data
stays on the box forever with nothing anywhere saying so.

Measured on 2026-09-02, 31 of the 33 canonical domains a school can import write at
least one such model. Importing a library catalogue, a health register, a bus roster
or a payroll onto a box was a permanent decision about where that school's records
live, made silently, by whichever lander happened to run.

THE TESTS
---------
LOAD-BEARING (each fails when only the CALLER is reverted, helpers left importable):

  * ``GuardFiresBeforeTheWriteTests`` -- ordering, proven by running a real apply and
    recording which happened first. Revert the ``guard_before_apply`` call in
    ``orchestrator._apply_bundle_inner`` and it fails.
  * ``RefusePolicyTests`` -- under ``refuse`` an unacknowledged stranding stops the
    import with zero landers run, and acknowledging it lets the same import through.
  * ``ReviewPageTests`` -- the warning reaches the page the Apply button lives on.
    Revert the ``review_notice`` call in ``live_import_attention`` and it fails.
  * ``PreflightTests`` -- ``preflight.run_all`` carries the check.
  * ``DeclarationIsMeasuredTests`` -- ``write_targets.py`` still matches what the
    landers actually write, resolved by the audit script. This is the seal that stops
    the table rotting the first time a lander gains a model.

CONTROLS (assert only PRE-EXISTING behaviour; must pass on both trees):

  * ``ControlRailFactsTests`` -- the rail facts this work is built on, asserted
    against the live resolvers, not repeated from a summary.
  * ``ControlCloudUnaffectedTests`` -- a cloud deployment behaves exactly as before.
  * ``ControlApplyLifecycleTests`` -- the existing already-applied / wrong-status
    behaviour of ``apply_bundle`` is untouched.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from apps.migration_cloud import edge_reachability as er
from apps.migration_cloud import orchestrator
from apps.migration_cloud.landers.write_targets import (
    DOMAIN_WRITE_TARGETS,
    FALLBACK_DOMAIN,
    write_targets_for,
)
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)

REPO_ROOT = settings.BASE_DIR

# A domain whose only first-class model (``schoolops.LibraryItem``) is on no rail --
# resolved, not assumed: ControlRailFactsTests asserts it.
STRANDED_DOMAIN = "library"


class _Factory(TestCase):
    def _bundle(self, key, status=BundleStatus.MAPPED, **kwargs):
        return MigrationBundle.objects.create(
            label="edge-reach",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"edge-reach-{key}",
            status=status,
            school=None,
            **kwargs,
        )

    def _artifact(self, bundle, name, *, domain=STRANDED_DOMAIN, rows=42):
        return MigrationArtifact.objects.create(
            bundle=bundle,
            path_within_bundle=name,
            filename=name,
            detected_format=ArtifactFormat.CSV,
            sha256=f"sha-{name}",
            assigned_domain=domain,
            row_count=rows,
        )

    def _as_edge(self, policy=er.POLICY_WARN):
        """Make this process answer as an appliance with a chosen policy."""
        return (
            mock.patch.object(er, "deployment_is_edge", return_value=True),
            mock.patch.object(er, "stranded_write_policy", return_value=policy),
        )


class _Job:
    """The orchestrator's ``_ArtifactJob`` shape, for the DB-free assessments."""

    def __init__(self, domain, row_count=10):
        self.domain = domain
        self.artifact = type("A", (), {"row_count": row_count})()


# --- LOAD-BEARING -----------------------------------------------------------


class GuardFiresBeforeTheWriteTests(_Factory):
    """The whole point: the operator is told before the rows land, not after."""

    def test_warning_is_recorded_before_the_first_artifact_is_applied(self):
        bundle = self._bundle("order")
        self._artifact(bundle, "library.csv")
        order: list[str] = []

        def _record(bundle_, report):
            order.append("warned")

        def _apply_artifact(*args, **kwargs):
            order.append("wrote")
            raise AssertionError("stop the apply once ordering is proven")

        edge, policy = self._as_edge()
        with edge, policy, \
                mock.patch.object(er, "_record", side_effect=_record), \
                mock.patch.object(orchestrator, "_apply_artifact",
                                  side_effect=_apply_artifact):
            try:
                orchestrator.apply_bundle(bundle_id=bundle.pk)
            except Exception:  # noqa: BLE001 -- the sentinel above, deliberately
                pass

        self.assertIn("warned", order,
                      "the apply reached a lander without assessing what can leave")
        self.assertIn("wrote", order, "the apply never reached a lander at all")
        self.assertLess(order.index("warned"), order.index("wrote"),
                        "the warning arrived AFTER rows were written")

    def test_the_assessment_is_durable_on_the_bundle(self):
        bundle = self._bundle("durable")
        self._artifact(bundle, "library.csv", rows=1234)
        edge, policy = self._as_edge()
        with edge, policy, mock.patch.object(orchestrator, "_apply_artifact",
                                             side_effect=RuntimeError("halt")):
            try:
                orchestrator.apply_bundle(bundle_id=bundle.pk)
            except Exception:  # noqa: BLE001
                pass
        bundle.refresh_from_db()
        recorded = (bundle.mapping_summary or {}).get(er.SUMMARY_KEY) or {}
        self.assertTrue(recorded, "nothing was recorded for a later audit to read")
        self.assertTrue(recorded["has_finding"])
        self.assertEqual(recorded["rows_stranded"], 1234)
        self.assertIn(STRANDED_DOMAIN, [d["domain"] for d in recorded["domains"]])

    def test_a_warning_event_reaches_the_operator_stream(self):
        bundle = self._bundle("event")
        self._artifact(bundle, "library.csv")
        seen: list[dict] = []
        edge, policy = self._as_edge()
        with edge, policy, \
                mock.patch.object(orchestrator, "_emit_progress",
                                  side_effect=lambda **kw: seen.append(kw)), \
                mock.patch.object(orchestrator, "_apply_artifact",
                                  side_effect=RuntimeError("halt")):
            try:
                orchestrator.apply_bundle(bundle_id=bundle.pk)
            except Exception:  # noqa: BLE001
                pass
        warnings = [e for e in seen if e.get("kind") == "warning"
                    and "never reach the cloud" in str(e.get("message", ""))]
        self.assertTrue(warnings, "no operator-visible warning was emitted")


class RefusePolicyTests(_Factory):
    """Choosing 'the box owns this' is allowed. Choosing it by accident is not."""

    def test_refuse_stops_the_import_before_any_lander_runs(self):
        bundle = self._bundle("refuse")
        self._artifact(bundle, "library.csv")
        edge, policy = self._as_edge(er.POLICY_REFUSE)
        with edge, policy, mock.patch.object(orchestrator, "_apply_artifact") as landed:
            orchestrator.apply_bundle(bundle_id=bundle.pk)
        landed.assert_not_called()
        bundle.refresh_from_db()
        self.assertEqual(bundle.status, BundleStatus.FAILED)
        self.assertIn("edge_stranded_writes_refused", bundle.size_summary or {})

    def test_an_acknowledged_stranding_is_allowed_through(self):
        bundle = self._bundle("acked")
        self._artifact(bundle, "library.csv")
        er.acknowledge(bundle, [STRANDED_DOMAIN], actor="operator@example.test")
        bundle.refresh_from_db()
        edge, policy = self._as_edge(er.POLICY_REFUSE)
        with edge, policy, mock.patch.object(orchestrator, "_apply_artifact",
                                             side_effect=RuntimeError("halt")) as landed:
            try:
                orchestrator.apply_bundle(bundle_id=bundle.pk)
            except Exception:  # noqa: BLE001
                pass
        self.assertTrue(landed.called,
                        "an acknowledged stranding must not keep refusing the import")

    def test_acknowledging_one_domain_does_not_acknowledge_another(self):
        bundle = self._bundle("partial")
        self._artifact(bundle, "library.csv", domain="library")
        self._artifact(bundle, "health.csv", domain="health")
        er.acknowledge(bundle, ["library"])
        bundle.refresh_from_db()
        edge, policy = self._as_edge(er.POLICY_REFUSE)
        with edge, policy, mock.patch.object(orchestrator, "_apply_artifact") as landed:
            orchestrator.apply_bundle(bundle_id=bundle.pk)
        landed.assert_not_called()
        bundle.refresh_from_db()
        self.assertEqual(bundle.status, BundleStatus.FAILED)

    def test_a_dry_run_is_never_refused(self):
        """A preview exists to SHOW what an apply would do; failing it is a bug."""
        bundle = self._bundle("dryrun")
        self._artifact(bundle, "library.csv")
        edge, policy = self._as_edge(er.POLICY_REFUSE)
        with edge, policy, mock.patch.object(orchestrator, "_apply_artifact",
                                             side_effect=RuntimeError("halt")):
            try:
                orchestrator.apply_bundle(bundle_id=bundle.pk, dry_run=True)
            except Exception:  # noqa: BLE001
                pass
        bundle.refresh_from_db()
        self.assertEqual(bundle.status, BundleStatus.MAPPED,
                         "a dry run must never move the durable bundle status")
        self.assertNotIn("edge_stranded_writes_refused", bundle.size_summary or {})

    def test_policy_comes_from_the_configurability_cascade(self):
        """No literal: the env rung of ``migration_cloud.defaults`` decides."""
        env_key = "MIGRATION_CLOUD__MIGRATION_CLOUD__EDGE__STRANDED_WRITE_POLICY"
        previous = os.environ.get(env_key)
        try:
            os.environ[env_key] = er.POLICY_REFUSE
            self.assertEqual(er.stranded_write_policy(), er.POLICY_REFUSE)
            os.environ[env_key] = "nonsense-value"
            self.assertEqual(er.stranded_write_policy(), er.POLICY_WARN,
                             "an unreadable policy must fall back to warning, never to off")
        finally:
            if previous is None:
                os.environ.pop(env_key, None)
            else:
                os.environ[env_key] = previous


class ReviewPageTests(_Factory):
    """The warning has to be on the page the button is on."""

    def test_compose_live_import_carries_the_stranding_notice(self):
        from apps.migration_cloud.live_import_attention import compose_live_import

        bundle = self._bundle("page")
        self._artifact(bundle, "library.csv", rows=7)
        edge, policy = self._as_edge()
        with edge, policy:
            payload = compose_live_import(bundle)
        notice = payload.get("edge_stranding")
        self.assertIsNotNone(
            notice, "the Review & Import page shows nothing about box-only records")
        self.assertEqual(notice["kind"], "edge_stranding")
        self.assertEqual(notice["rows"], 7)
        self.assertEqual([d["domain"] for d in notice["domains"]], [STRANDED_DOMAIN])

    def test_a_rail_covered_domain_still_names_its_residual_dfv_writes(self):
        from apps.migration_cloud.live_import_attention import compose_live_import

        bundle = self._bundle("clean")
        # ``academic_sessions`` writes AcademicYear + Term, both on the rail; its only
        # stranded writes are the residual-capture DFV pair, which every domain has.
        self._artifact(bundle, "years.csv", domain="academic_sessions")
        edge, policy = self._as_edge()
        with edge, policy:
            payload = compose_live_import(bundle)
        # DFV is genuinely stranded, so this domain DOES have a finding. Assert the
        # honest thing rather than a convenient one: the notice names DFV and nothing
        # more, and does not claim a first-class model is stranded.
        notice = payload.get("edge_stranding")
        self.assertIsNotNone(notice)
        stranded = notice["domains"][0]["stranded"]
        self.assertEqual(sorted(stranded),
                         ["metadata.DynamicFieldDefinition", "metadata.DynamicFieldValue"])


class PreflightTests(_Factory):
    def test_run_all_includes_the_edge_reachability_check(self):
        from apps.migration_cloud import preflight

        bundle = self._bundle("preflight")
        self._artifact(bundle, "library.csv")
        edge, policy = self._as_edge()
        with edge, policy:
            report = preflight.run_all(bundle=bundle)
        names = [c.name for c in report.checks]
        self.assertIn("edge_reachability", names)
        check = next(c for c in report.checks if c.name == "edge_reachability")
        self.assertTrue(check.passed, "a warning must not read as a preflight failure")
        self.assertIn("never reach the cloud", check.message)

    def test_refuse_policy_makes_preflight_fail(self):
        from apps.migration_cloud import preflight

        bundle = self._bundle("preflight-refuse")
        self._artifact(bundle, "library.csv")
        edge, policy = self._as_edge(er.POLICY_REFUSE)
        with edge, policy:
            check = preflight.check_edge_reachability(bundle=bundle)
        self.assertFalse(check.passed)


class OperatorCommandTests(_Factory):
    """A box is operated from a shell; the choice has to be makeable there."""

    def _run(self, *args):
        from django.core.management import call_command

        out = io.StringIO()
        call_command("edge_import_reachability", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_it_reports_what_the_import_would_strand(self):
        bundle = self._bundle("cmd")
        self._artifact(bundle, "library.csv", rows=31)
        edge, policy = self._as_edge()
        with edge, policy:
            output = self._run("--bundle", str(bundle.pk))
        self.assertIn("library", output)
        self.assertIn("31", output)
        self.assertIn("schoolops.LibraryItem", output)

    def test_accepting_a_domain_this_bundle_does_not_strand_is_refused(self):
        """An acknowledgement about data that is not here reads later as a decision."""
        from django.core.management.base import CommandError

        bundle = self._bundle("cmd-bogus")
        self._artifact(bundle, "library.csv")
        edge, policy = self._as_edge()
        with edge, policy, self.assertRaises(CommandError):
            self._run("--bundle", str(bundle.pk), "--accept", "hostel")

    def test_accepting_records_the_domain_the_time_and_the_actor(self):
        bundle = self._bundle("cmd-accept")
        self._artifact(bundle, "library.csv")
        edge, policy = self._as_edge()
        with edge, policy:
            self._run("--bundle", str(bundle.pk), "--accept", "library",
                      "--actor", "head@example.test")
        bundle.refresh_from_db()
        ack = (bundle.mapping_summary or {}).get(er.ACK_KEY) or {}
        self.assertEqual(ack.get("domains"), ["library"])
        self.assertEqual(ack.get("acknowledged_by"), "head@example.test")
        self.assertTrue(ack.get("acknowledged_at"))


class AssessmentHonestyTests(SimpleTestCase):
    """Figures that could be wrong must say so rather than read as clean."""

    def test_an_uncountable_artifact_makes_the_total_a_floor(self):
        with mock.patch.object(er, "deployment_is_edge", return_value=True), \
                mock.patch.object(er, "stranded_write_policy", return_value=er.POLICY_WARN):
            report = er.assess(
                _StubBundle(),
                [_Job(STRANDED_DOMAIN, 10), _Job(STRANDED_DOMAIN, None)],
            )
        self.assertFalse(report.counts_are_complete)
        self.assertEqual(report.rows_stranded, 10)
        self.assertIn("at least 10 rows", report.operator_message())
        self.assertIn("1 file could not be row-counted", report.operator_message())

    def test_nothing_countable_says_so_instead_of_at_least_zero(self):
        """An "at least 0 rows" total is true, useless, and shaped like good news."""
        edge = mock.patch.object(er, "deployment_is_edge", return_value=True)
        policy = mock.patch.object(er, "stranded_write_policy",
                                   return_value=er.POLICY_WARN)
        with edge, policy:
            report = er.assess(_StubBundle(), [_Job(STRANDED_DOMAIN, None)])
        self.assertEqual(report.rows_stranded, 0)
        self.assertIn("an unknown number of rows", report.operator_message())
        self.assertNotIn("at least 0", report.operator_message())

    def test_an_unreadable_rail_reports_nothing_rather_than_zero(self):
        with mock.patch.object(er, "deployment_is_edge", return_value=True), \
                mock.patch.object(er, "_rail_labels", return_value=None):
            report = er.assess(_StubBundle(), [_Job(STRANDED_DOMAIN, 10)])
        self.assertTrue(report.rail_unavailable)
        self.assertFalse(report.has_finding)
        self.assertEqual(report.domains, [],
                         "a report that could not read the rail must carry no figures")

    def test_an_unregistered_domain_is_the_worst_case_not_the_empty_one(self):
        # A canonical domain with no lander falls through to the ``custom_fields``
        # catch-all, which writes the whole row to DynamicFieldValue. Reporting () for
        # it would say a brand-new domain costs nothing to import.
        self.assertEqual(write_targets_for("a-domain-nobody-wrote-a-lander-for"),
                         DOMAIN_WRITE_TARGETS[FALLBACK_DOMAIN])


class _StubBundle:
    mapping_summary: dict = {}
    pk = 0


class DeclarationIsMeasuredTests(SimpleTestCase):
    """``write_targets.py`` must keep matching what the landers actually write."""

    def test_declaration_matches_the_resolver(self):
        script = os.path.join(str(REPO_ROOT), "scripts",
                              "audit_lander_write_reachability.py")
        proc = subprocess.run(  # noqa: S603 -- fixed argv, no shell
            [sys.executable, script, "--check-declaration"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(
            proc.returncode, 0,
            "write_targets.py has drifted from what the landers write:\n"
            + proc.stdout + proc.stderr,
        )

    def test_the_resolver_can_report_a_non_zero_answer(self):
        """A scan never shown finding something is not evidence it found nothing."""
        script = os.path.join(str(REPO_ROOT), "scripts",
                              "audit_lander_write_reachability.py")
        proc = subprocess.run(  # noqa: S603 -- fixed argv, no shell
            [sys.executable, script, "--self-test"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(proc.returncode, 0,
                         "the resolver's self-test failed:\n" + proc.stdout + proc.stderr)
        self.assertIn("SELF-TEST PASSED", proc.stdout)


# --- CONTROLS ---------------------------------------------------------------


class ControlRailFactsTests(SimpleTestCase):
    """Facts about the rail that predate this work. True on both trees."""

    def test_teacher_is_registered_but_the_rail_refuses_to_create_it(self):
        from apps.api.sync_services import _get_entity_config, _INSERT_HELD_ENTITIES

        config = _get_entity_config(include_derived=True)
        self.assertIn("teacher", config)
        self.assertIn("teacher", _INSERT_HELD_ENTITIES)

    def test_library_and_health_models_are_on_no_rail(self):
        from apps.sync_engine.rail_coverage import rail_models

        on_rail = set(rail_models())
        self.assertNotIn("schoolops.libraryitem", on_rail)
        self.assertNotIn("schoolops.healthrecord", on_rail)

    def test_dynamic_field_value_is_on_no_rail(self):
        from apps.sync_engine.rail_coverage import rail_models

        self.assertNotIn("metadata.dynamicfieldvalue", set(rail_models()))

    def test_academic_year_is_on_the_rail(self):
        from apps.sync_engine.rail_coverage import rail_models

        self.assertIn("academics.academicyear", set(rail_models()))


class ControlCloudUnaffectedTests(_Factory):
    """A multi-tenant deployment must see and pay for none of this."""

    def test_no_notice_and_no_recording_when_not_an_edge_box(self):
        from apps.migration_cloud.live_import_attention import compose_live_import

        bundle = self._bundle("cloud")
        self._artifact(bundle, "library.csv")
        with mock.patch.object(er, "deployment_is_edge", return_value=False):
            self.assertIsNone(compose_live_import(bundle).get("edge_stranding"))
            with mock.patch.object(orchestrator, "_apply_artifact",
                                   side_effect=RuntimeError("halt")):
                try:
                    orchestrator.apply_bundle(bundle_id=bundle.pk)
                except Exception:  # noqa: BLE001
                    pass
        bundle.refresh_from_db()
        self.assertNotIn(er.SUMMARY_KEY, bundle.mapping_summary or {})

    def test_cloud_apply_still_reaches_the_landers(self):
        bundle = self._bundle("cloud-apply")
        self._artifact(bundle, "library.csv")
        with mock.patch.object(er, "deployment_is_edge", return_value=False), \
                mock.patch.object(orchestrator, "_apply_artifact",
                                  side_effect=RuntimeError("halt")) as landed:
            try:
                orchestrator.apply_bundle(bundle_id=bundle.pk)
            except Exception:  # noqa: BLE001
                pass
        self.assertTrue(landed.called)


class ControlApplyLifecycleTests(_Factory):
    """Pre-existing ``apply_bundle`` lifecycle behaviour, unchanged by this work."""

    def test_a_bundle_that_is_not_mapped_still_raises(self):
        bundle = self._bundle("notmapped", status=BundleStatus.PENDING)
        with self.assertRaises(ValueError):
            orchestrator.apply_bundle(bundle_id=bundle.pk)

    def test_an_already_applied_bundle_is_still_a_no_op(self):
        bundle = self._bundle("done", status=BundleStatus.APPLIED)
        with mock.patch.object(orchestrator, "_apply_artifact") as landed:
            result = orchestrator.apply_bundle(bundle_id=bundle.pk)
        landed.assert_not_called()
        self.assertEqual(result.status, BundleStatus.APPLIED)

    def test_a_bundle_whose_artifacts_are_all_quarantined_still_fails(self):
        bundle = self._bundle("allq")
        MigrationArtifact.objects.create(
            bundle=bundle, path_within_bundle="bad.csv", filename="bad.csv",
            detected_format=ArtifactFormat.CSV, sha256="sha-bad",
            quarantined=True, quarantine_reason="bad-file",
        )
        edge, policy = self._as_edge()
        with edge, policy:
            orchestrator.apply_bundle(bundle_id=bundle.pk)
        bundle.refresh_from_db()
        self.assertEqual(bundle.status, BundleStatus.FAILED)
        self.assertTrue((bundle.size_summary or {}).get("no_workable_artifacts"))
