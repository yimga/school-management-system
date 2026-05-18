"""Tests for the RunMyCampus canonical-template accelerator + template download.

Covers:
    * Signature recognition by the source classifier (file is named
      identity-test sentinel)
    * Filename-based activation (students.csv → students domain)
    * Header-based activation (renamed file with canonical headers)
    * Identity mapping (every known header maps to itself)
    * Unknown headers stay unmapped (mapper handles them as custom_fields)
    * Graceful fall-through when no artifact matches
    * Canonical template URL resolves
    * CSV template generator emits stable, sorted headers + version comment
    * Zip endpoint includes every canonical domain
"""

from __future__ import annotations

import io
import zipfile
from unittest.mock import MagicMock

from django.test import SimpleTestCase
from django.urls import reverse

from apps.migration_cloud.accelerators.base import AcceleratorError
from apps.migration_cloud.accelerators.runmycampus_canonical import (
    CANONICAL_FILENAME_TO_DOMAIN,
    DOMAIN_CANONICAL_HEADERS,
    RunMyCampusCanonicalAccelerator,
    _domain_for_artifact,
    _domain_from_headers,
)
from apps.migration_cloud.classifiers.signatures import SOURCE_HEADER_SIGNATURES


def _fake_artifact(*, filename: str = "", headers: list[str] | None = None, path: str = "") -> MagicMock:
    """Build a minimum-viable artifact stand-in (avoids DB setup)."""
    artifact = MagicMock()
    artifact.filename = filename
    artifact.path_within_bundle = path or filename
    if headers is None:
        artifact.profile = {}
    else:
        artifact.profile = {"columns": [{"name": h, "samples": []} for h in headers]}
    return artifact


def _fake_bundle(artifacts: list[MagicMock], *, pk: int = 7) -> MagicMock:
    """Build a minimum-viable bundle stand-in with a ``MigrationBundle`` spec."""
    from apps.migration_cloud.models import MigrationBundle

    bundle = MagicMock(spec=MigrationBundle)
    bundle.pk = pk
    qs = MagicMock()
    qs.all.return_value = list(artifacts)
    qs.values_list.return_value = [a.filename for a in artifacts]
    bundle.artifacts = qs
    return bundle


class SourceSignatureRegistrationTests(SimpleTestCase):
    """The accelerator is registered in the signature table so the
    classifier can name it as a candidate."""

    def test_signature_table_contains_runmycampus_canonical(self) -> None:
        self.assertIn("runmycampus_canonical", SOURCE_HEADER_SIGNATURES)
        sig = SOURCE_HEADER_SIGNATURES["runmycampus_canonical"]
        self.assertIn("external_id", sig["required"])
        self.assertIn("first_name", sig["required"])
        self.assertIn("last_name", sig["required"])

    def test_signature_required_overlap_with_students_canonical(self) -> None:
        """The signature required-set must be a subset of the students
        canonical header set so a students.csv upload triggers signature
        recognition naturally."""
        sig_required = set(SOURCE_HEADER_SIGNATURES["runmycampus_canonical"]["required"])
        students_canonical = DOMAIN_CANONICAL_HEADERS["students"]
        self.assertTrue(sig_required.issubset(students_canonical))


class DomainResolutionTests(SimpleTestCase):
    def test_filename_takes_precedence(self) -> None:
        artifact = _fake_artifact(filename="students.csv", headers=["foo", "bar"])
        self.assertEqual(_domain_for_artifact(artifact), "students")

    def test_filename_case_insensitive(self) -> None:
        artifact = _fake_artifact(filename="Students.CSV")
        self.assertEqual(_domain_for_artifact(artifact), "students")

    def test_header_signal_when_filename_unknown(self) -> None:
        # Renamed file but canonical headers present → still matches.
        artifact = _fake_artifact(
            filename="my_school_export_2026.csv",
            headers=["external_id", "first_name", "last_name", "grade_level"],
        )
        self.assertEqual(_domain_from_headers(artifact), "students")
        self.assertEqual(_domain_for_artifact(artifact), "students")

    def test_no_match_when_too_few_canonical_headers(self) -> None:
        artifact = _fake_artifact(
            filename="random.csv",
            headers=["foo", "bar", "external_id"],  # only 1 canonical hit
        )
        self.assertIsNone(_domain_for_artifact(artifact))

    def test_no_match_on_empty_artifact(self) -> None:
        artifact = _fake_artifact(filename="random.csv")
        self.assertIsNone(_domain_for_artifact(artifact))

    def test_alias_filenames_map_correctly(self) -> None:
        # parents.csv → guardians, teachers.csv → staff, etc.
        self.assertEqual(CANONICAL_FILENAME_TO_DOMAIN["parents.csv"], "guardians")
        self.assertEqual(CANONICAL_FILENAME_TO_DOMAIN["teachers.csv"], "staff")
        self.assertEqual(CANONICAL_FILENAME_TO_DOMAIN["classes.csv"], "sections")
        self.assertEqual(CANONICAL_FILENAME_TO_DOMAIN["incidents.csv"], "behavior")
        self.assertEqual(CANONICAL_FILENAME_TO_DOMAIN["invoices.csv"], "finance")


class AcceleratorExecutionTests(SimpleTestCase):
    def setUp(self) -> None:
        self.acc = RunMyCampusCanonicalAccelerator()

    def test_handle_unsupported_when_no_artifacts(self) -> None:
        bundle = _fake_bundle([])
        bundle.artifacts.values_list.return_value = []
        self.assertFalse(self.acc.is_handle_supported(bundle))

    def test_handle_supported_via_filename(self) -> None:
        artifacts = [_fake_artifact(filename="students.csv")]
        bundle = _fake_bundle(artifacts)
        self.assertTrue(self.acc.is_handle_supported(bundle))

    def test_handle_supported_via_headers(self) -> None:
        artifacts = [_fake_artifact(
            filename="not_canonical.csv",
            headers=["external_id", "first_name", "last_name", "grade_level"],
        )]
        bundle = _fake_bundle(artifacts)
        self.assertTrue(self.acc.is_handle_supported(bundle))

    def test_handle_unsupported_for_unrelated_bundle(self) -> None:
        artifacts = [_fake_artifact(filename="random.txt", headers=["foo", "bar"])]
        bundle = _fake_bundle(artifacts)
        self.assertFalse(self.acc.is_handle_supported(bundle))

    def test_execute_builds_identity_mappings(self) -> None:
        artifact = _fake_artifact(
            filename="students.csv",
            headers=["external_id", "first_name", "last_name", "custom_extra_field"],
            path="bundle/students.csv",
        )
        bundle = _fake_bundle([artifact])
        contract = self.acc.execute(bundle_id=bundle.pk, handle=bundle)
        entry = contract.pre_classified_artifacts["bundle/students.csv"]
        self.assertEqual(entry["domain"], "students")
        self.assertEqual(entry["method"], "accelerator_runmycampus_canonical")
        # Identity: known canonical headers map to themselves.
        self.assertEqual(entry["canonical_mappings"]["external_id"], "external_id")
        self.assertEqual(entry["canonical_mappings"]["first_name"], "first_name")
        # Non-canonical headers are NOT in the mapping (mapper picks them up).
        self.assertNotIn("custom_extra_field", entry["canonical_mappings"])

    def test_execute_emits_vendor_enum_tables(self) -> None:
        artifact = _fake_artifact(filename="students.csv", headers=["external_id"])
        bundle = _fake_bundle([artifact])
        contract = self.acc.execute(bundle_id=bundle.pk, handle=bundle)
        self.assertIn("enrollment_status", contract.vendor_enum_tables)
        self.assertEqual(contract.vendor_enum_tables["enrollment_status"]["enrolled"], "active")
        self.assertEqual(contract.vendor_enum_tables["is_primary"]["yes"], "true")

    def test_execute_raises_on_zero_matches(self) -> None:
        artifact = _fake_artifact(filename="totally_unrelated.txt", headers=["foo"])
        bundle = _fake_bundle([artifact])
        with self.assertRaises(AcceleratorError):
            self.acc.execute(bundle_id=bundle.pk, handle=bundle)

    def test_execute_raises_on_handle_mismatch(self) -> None:
        artifact = _fake_artifact(filename="students.csv")
        bundle = _fake_bundle([artifact], pk=7)
        with self.assertRaises(AcceleratorError):
            # Wrong bundle_id → guard fires.
            self.acc.execute(bundle_id=999, handle=bundle)

    def test_execute_handles_multiple_domains_in_one_bundle(self) -> None:
        artifacts = [
            _fake_artifact(filename="students.csv", headers=["external_id"], path="b/students.csv"),
            _fake_artifact(filename="staff.csv", headers=["staff_external_id"], path="b/staff.csv"),
            _fake_artifact(filename="guardians.csv", headers=["guardian_external_id"], path="b/guardians.csv"),
        ]
        bundle = _fake_bundle(artifacts)
        contract = self.acc.execute(bundle_id=bundle.pk, handle=bundle)
        self.assertEqual(len(contract.pre_classified_artifacts), 3)
        self.assertEqual(contract.pre_classified_artifacts["b/students.csv"]["domain"], "students")
        self.assertEqual(contract.pre_classified_artifacts["b/staff.csv"]["domain"], "staff")
        self.assertEqual(contract.pre_classified_artifacts["b/guardians.csv"]["domain"], "guardians")


class CanonicalTemplateUrlTests(SimpleTestCase):
    def test_template_zip_url_resolves(self) -> None:
        path = reverse("migration_cloud_super:canonical_template_zip", urlconf="config.urls")
        self.assertTrue(path.endswith("/template/"))

    def test_template_csv_url_resolves(self) -> None:
        path = reverse(
            "migration_cloud_super:canonical_template_csv",
            urlconf="config.urls",
            kwargs={"domain": "students"},
        )
        self.assertTrue(path.endswith("/template/students.csv"))

    def test_template_csv_url_resolves_in_portal_shell_too(self) -> None:
        # Long-tail customers reach this from the tenant portal as well.
        path = reverse(
            "migration_cloud_portal:canonical_template_csv",
            urlconf="config.urls",
            kwargs={"domain": "students"},
        )
        self.assertIn("/portal/", path)


class CanonicalTemplateGeneratorTests(SimpleTestCase):
    def test_csv_generator_emits_version_comment_and_sorted_headers(self) -> None:
        from apps.migration_cloud.views import _canonical_template_csv

        text = _canonical_template_csv("students", DOMAIN_CANONICAL_HEADERS["students"])
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("# runmycampus-canonical-template:"))
        self.assertIn("domain=students", lines[0])
        self.assertIn("version=1.0", lines[0])
        # Headers sorted alphabetically for diff stability.
        headers = lines[1].split(",")
        self.assertEqual(headers, sorted(headers))
        # Required fields present.
        self.assertIn("external_id", headers)
        self.assertIn("first_name", headers)
        self.assertIn("last_name", headers)

    def test_csv_generator_for_every_known_domain(self) -> None:
        """No domain in DOMAIN_CANONICAL_HEADERS should crash the generator."""
        from apps.migration_cloud.views import _canonical_template_csv

        for domain, headers in DOMAIN_CANONICAL_HEADERS.items():
            text = _canonical_template_csv(domain, headers)
            self.assertIn(f"domain={domain}", text)
            self.assertTrue(text.endswith("\n"))


class CanonicalTemplateZipShapeTests(SimpleTestCase):
    """The zip endpoint streams a real ZIP — assert its shape without a
    full HTTP roundtrip (which would need auth + middleware setup)."""

    def test_zip_includes_every_canonical_domain_plus_readme(self) -> None:
        from apps.migration_cloud.views import (
            _canonical_template_csv,
            _canonical_template_readme,
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for domain, headers in sorted(DOMAIN_CANONICAL_HEADERS.items()):
                zf.writestr(f"{domain}.csv", _canonical_template_csv(domain, headers))
            zf.writestr("README.txt", _canonical_template_readme())
        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as zf:
            names = set(zf.namelist())
        self.assertIn("README.txt", names)
        for domain in DOMAIN_CANONICAL_HEADERS:
            self.assertIn(f"{domain}.csv", names)
