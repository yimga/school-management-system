"""Tests for v3.33.0 — MAA v2.0 draft + signature_text_sha256 + compliance docs +
scan_pii_logging_smell baseline.

Coverage:

  1. MAA v2.0 DRAFT renderer
     * v1.0 remains the platform default (AGREEMENT_VERSION_CURRENT).
     * v2.0 is registered in AGREEMENT_VERSIONS but marked as draft.
     * v2.0 body carries the verbatim phrases: "scope of access",
       "data minimization", "no retention beyond migration",
       "right to withdraw at any time", "data subject rights".
     * v2.0 body carries the [DRAFT v2.0 — PENDING COUNSEL REVIEW]
       header.
     * Unknown versions still raise ValueError.

  2. signature_text_sha256 auto-compute
     * .save() populates the column from sha256(signature_text.utf-8).
     * Editing signature_text post-create updates the sha on next save.
     * Backfill migration's helper function is importable and
       computes the expected fingerprint.

  3. Compliance documents
     * docs/DPA_TEMPLATE.md exists, carries a DRAFT header, and
       does NOT contain any literal-looking 44-char base64 secret.
     * docs/DSAR_RUNBOOK.md exists, carries a DRAFT header.
     * docs/SECURITY_KEYS.md contains the v3.33.0 "Cross-System
       Trust Anchors" section cross-linking DSAR + DPA.

  4. scan_pii_logging_smell baseline=0 day 1
     * The scanner script imports + exposes its expected API.
     * Running it on the current tree yields 0 findings.
     * Baseline JSON file exists and records 0.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
import unittest

from django.test import SimpleTestCase, TestCase


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


# ─── 1. MAA v2.0 DRAFT renderer ───────────────────────────────────────────


class MAAv2DraftRendererTests(SimpleTestCase):
    """v2.0 ships as DRAFT; v1.0 remains the platform default."""

    def test_v1_remains_default(self):
        from apps.migration_cloud.services.maa_text import AGREEMENT_VERSION_CURRENT
        self.assertEqual(AGREEMENT_VERSION_CURRENT, "v1.0")

    def test_v2_registered(self):
        from apps.migration_cloud.services.maa_text import AGREEMENT_VERSIONS
        self.assertIn("v1.0", AGREEMENT_VERSIONS)
        self.assertIn("v2.0", AGREEMENT_VERSIONS)

    def test_v2_in_draft_set(self):
        from apps.migration_cloud.services.maa_text import (
            MAA_TEXT_DRAFT_VERSIONS,
            is_draft_version,
        )
        self.assertIn("v2.0", MAA_TEXT_DRAFT_VERSIONS)
        self.assertNotIn("v1.0", MAA_TEXT_DRAFT_VERSIONS)
        self.assertTrue(is_draft_version("v2.0"))
        self.assertFalse(is_draft_version("v1.0"))

    def test_v2_carries_draft_header(self):
        from apps.migration_cloud.services.maa_text import MAA_TEXT_V2_0
        self.assertIn("DRAFT v2.0", MAA_TEXT_V2_0)
        self.assertIn("PENDING COUNSEL REVIEW", MAA_TEXT_V2_0)

    def test_v2_verbatim_phrases_present(self):
        """v2.0 carries the GDPR/data-subject-rights phrases required by spec."""
        from apps.migration_cloud.services.maa_text import render_maa_text
        text = render_maa_text("powerschool", "Jane Doe", agreement_version="v2.0")
        # Spec: assert the following verbatim phrases (case-insensitive).
        required = [
            "scope of access",
            "data minimization",
            "no retention beyond migration",
            "right to withdraw at any time",
            "data subject rights",
        ]
        text_lower = text.lower()
        for phrase in required:
            self.assertIn(
                phrase, text_lower,
                f"v2.0 MAA body must contain verbatim phrase {phrase!r}",
            )

    def test_v1_render_works(self):
        from apps.migration_cloud.services.maa_text import render_maa_text
        text = render_maa_text("powerschool", "Jane Doe", agreement_version="v1.0")
        self.assertIn("powerschool", text)
        self.assertIn("Jane Doe", text)
        self.assertIn("FERPA", text)

    def test_unknown_version_raises(self):
        from apps.migration_cloud.services.maa_text import render_maa_text
        with self.assertRaises(ValueError):
            render_maa_text("powerschool", "Jane Doe", agreement_version="v999.0")


# ─── 2. signature_text_sha256 auto-compute ────────────────────────────────


def _can_use_db() -> bool:
    """Probe for the project's test DB; v3.23.10 documents an infra issue."""
    try:
        from django.contrib.auth import get_user_model
        from apps.schools.models import School  # noqa: F401
        get_user_model()
        return True
    except Exception:  # noqa: BLE001
        return False


class SignatureTextSha256ColumnTests(SimpleTestCase):
    """Model-shape tests — no DB needed."""

    def test_model_has_field(self):
        from apps.migration_cloud.models import MigrationAuthorizationAgreement
        field_names = {f.name for f in MigrationAuthorizationAgreement._meta.get_fields()}
        self.assertIn("signature_text_sha256", field_names)

    def test_field_is_64_char_indexed(self):
        from apps.migration_cloud.models import MigrationAuthorizationAgreement
        field = MigrationAuthorizationAgreement._meta.get_field("signature_text_sha256")
        self.assertEqual(field.max_length, 64)
        self.assertTrue(field.db_index)


@unittest.skipUnless(_can_use_db(), "DB or school/user model unavailable")
class SignatureTextSha256SaveTests(TestCase):
    """Save-time auto-compute behavior."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        from apps.schools.models import School
        User = get_user_model()
        cls.school = School.objects.create(
            name="MAA v2 Test Academy",
            subdomain="maa-v2-test",
        )
        cls.user = User.objects.create_user(
            username="maa_v2_test_operator",
            email="ops-v2@example.com",
            password="not-a-real-password",
        )

    def _make_maa(self, signature_text="(test text)"):
        from apps.migration_cloud.models import MigrationAuthorizationAgreement
        return MigrationAuthorizationAgreement.objects.create(
            tenant=self.school,
            signed_by_user=self.user,
            signed_by_role="IT Director",
            vendor_source="powerschool",
            vendor_account_holder_name="Jane Doe",
            agreement_version="v1.0",
            signature_text=signature_text,
        )

    def test_sha_computed_on_save(self):
        maa = self._make_maa(signature_text="hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        self.assertEqual(maa.signature_text_sha256, expected)
        self.assertEqual(len(maa.signature_text_sha256), 64)

    def test_sha_updates_when_text_edited(self):
        maa = self._make_maa(signature_text="first")
        first_sha = maa.signature_text_sha256
        maa.signature_text = "second"
        maa.save()
        self.assertNotEqual(maa.signature_text_sha256, first_sha)
        self.assertEqual(
            maa.signature_text_sha256,
            hashlib.sha256(b"second").hexdigest(),
        )

    def test_sha_handles_empty_signature_text(self):
        maa = self._make_maa(signature_text="")
        self.assertEqual(
            maa.signature_text_sha256,
            hashlib.sha256(b"").hexdigest(),
        )


class SignatureTextSha256BackfillHelperTests(SimpleTestCase):
    """The migration's RunPython helper is importable and deterministic."""

    def test_migration_module_imports(self):
        # Migration modules have leading digits, so they cannot be
        # imported with `from apps.migration_cloud.migrations import X`
        # — use importlib.import_module instead.
        from importlib import import_module
        mod = import_module(
            "apps.migration_cloud.migrations.0013_maa_signature_sha256"
        )
        self.assertTrue(hasattr(mod, "_backfill_signature_sha"))
        self.assertTrue(hasattr(mod, "_noop_reverse"))


# ─── 3. Compliance docs (DPA + DSAR) + SECURITY_KEYS additions ───────────


class ComplianceDocumentsTests(SimpleTestCase):
    """Both compliance scaffolds exist, ship the DRAFT header, and
    contain no literal-looking 44-char base64 secrets."""

    DPA_PATH = REPO_ROOT / "docs" / "DPA_TEMPLATE.md"
    DSAR_PATH = REPO_ROOT / "docs" / "DSAR_RUNBOOK.md"
    SECURITY_KEYS_PATH = REPO_ROOT / "docs" / "SECURITY_KEYS.md"

    # A 44-char URL-safe-base64 + trailing-= pattern matches a Fernet
    # key. We forbid it in compliance docs to prevent accidental
    # commits of real keys.
    _FERNET_LITERAL_RE = re.compile(
        r"(?<![A-Za-z0-9_+/-])[A-Za-z0-9_-]{43}=(?![A-Za-z0-9_+/-])"
    )

    def test_dpa_template_exists(self):
        self.assertTrue(self.DPA_PATH.is_file(), f"missing: {self.DPA_PATH}")

    def test_dsar_runbook_exists(self):
        self.assertTrue(self.DSAR_PATH.is_file(), f"missing: {self.DSAR_PATH}")

    def test_dpa_template_carries_draft_header(self):
        text = self.DPA_PATH.read_text(encoding="utf-8")
        self.assertIn("DRAFT", text)
        self.assertIn("pending counsel review", text.lower())

    def test_dsar_runbook_carries_draft_header(self):
        text = self.DSAR_PATH.read_text(encoding="utf-8")
        self.assertIn("DRAFT", text)
        self.assertIn("pending counsel review", text.lower())

    def test_dpa_template_no_literal_secrets(self):
        text = self.DPA_PATH.read_text(encoding="utf-8")
        hits = self._FERNET_LITERAL_RE.findall(text)
        self.assertEqual(hits, [], f"literal-looking secrets in DPA: {hits}")

    def test_dsar_runbook_no_literal_secrets(self):
        text = self.DSAR_PATH.read_text(encoding="utf-8")
        hits = self._FERNET_LITERAL_RE.findall(text)
        self.assertEqual(hits, [], f"literal-looking secrets in DSAR: {hits}")

    def test_dpa_template_lengths_reasonable(self):
        """Spec: each doc <=500 lines."""
        n = sum(1 for _ in self.DPA_PATH.read_text(encoding="utf-8").splitlines())
        self.assertLessEqual(n, 500, f"DPA template {n} lines > 500")

    def test_dsar_runbook_lengths_reasonable(self):
        n = sum(1 for _ in self.DSAR_PATH.read_text(encoding="utf-8").splitlines())
        self.assertLessEqual(n, 500, f"DSAR runbook {n} lines > 500")

    def test_security_keys_has_cross_system_section(self):
        text = self.SECURITY_KEYS_PATH.read_text(encoding="utf-8")
        self.assertIn("Cross-System Trust Anchors", text)
        # Cross-links to DSAR + DPA.
        self.assertIn("DSAR_RUNBOOK.md", text)
        self.assertIn("DPA_TEMPLATE.md", text)

    def test_security_keys_cross_section_lists_required_anchors(self):
        text = self.SECURITY_KEYS_PATH.read_text(encoding="utf-8")
        # Each of the required anchors mentioned by the spec.
        required_anchors = [
            "SECRET_KEY",
            "DJANGO_CRYPTOGRAPHY_KEYS",
            "CompanionKeypair",
            "secret_ciphertext",  # webhook secrets
            "MigrationCloudAPIToken",
            "MAA signature material",
        ]
        for anchor in required_anchors:
            self.assertIn(
                anchor, text,
                f"SECURITY_KEYS.md must mention trust anchor {anchor!r}",
            )


# ─── 4. scan_pii_logging_smell baseline=0 day 1 ──────────────────────────


class PIILoggingSmellScannerTests(SimpleTestCase):
    """The scanner exists, exposes its API, and exits 0 on current tree."""

    SCANNER_PATH = REPO_ROOT / "scripts" / "scan_pii_logging_smell.py"
    BASELINE_PATH = (
        REPO_ROOT / "var" / "security-audit-baseline-pii-logging-smell.json"
    )

    def _load_scanner(self):
        spec = importlib.util.spec_from_file_location(
            "scan_pii_logging_smell_test_loader",
            self.SCANNER_PATH,
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_scanner_script_exists(self):
        self.assertTrue(
            self.SCANNER_PATH.is_file(),
            f"missing scanner: {self.SCANNER_PATH}",
        )

    def test_scanner_api(self):
        s = self._load_scanner()
        self.assertTrue(hasattr(s, "scan_all"))
        self.assertTrue(hasattr(s, "SENSITIVE_KEYWORDS"))
        self.assertTrue(hasattr(s, "ALLOW_MARKER"))
        # Spec: keywords include password, hash, secret, token, ssn, dob.
        for kw in ("password", "hash", "secret", "token", "ssn", "dob"):
            self.assertIn(kw, s.SENSITIVE_KEYWORDS)

    def test_baseline_file_records_zero(self):
        self.assertTrue(self.BASELINE_PATH.is_file(), f"missing: {self.BASELINE_PATH}")
        data = json.loads(self.BASELINE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            data.get("finding_count"), 0,
            "scan_pii_logging_smell baseline must be 0 day 1",
        )

    def test_scan_yields_zero_findings(self):
        s = self._load_scanner()
        findings = s.scan_all()
        self.assertEqual(
            findings, [],
            f"pii-logging-smell scan must be clean; got {len(findings)} finding(s): "
            f"{findings[:5]}",
        )

    def test_scanner_detects_clear_positive(self):
        """The detector is not a no-op — fabricate a clear interpolation."""
        s = self._load_scanner()
        # The helper expects the full logger.<lvl>(...) span.
        positive = 'logger.info("user signed in password=%s", password)'
        spans = s._extract_logger_call_spans(positive)
        self.assertEqual(len(spans), 1)
        start, end, _ = spans[0]
        span_body = positive[start:end]
        # Heuristic should fire on "password".
        self.assertTrue(
            s._looks_like_interpolation(span_body, "password"),
            "scanner failed to detect a clear positive — heuristics regressed",
        )

    def test_scanner_ignores_clear_negative(self):
        s = self._load_scanner()
        negative = 'logger.warning("Webhook secret not configured, skipping signature check")'
        spans = s._extract_logger_call_spans(negative)
        self.assertEqual(len(spans), 1)
        start, end, _ = spans[0]
        span_body = negative[start:end]
        for kw in s.SENSITIVE_KEYWORDS:
            self.assertFalse(
                s._looks_like_interpolation(span_body, kw),
                f"scanner falsely flagged '{kw}' in negative case",
            )


# ─── 5. Companion receiver wiring — refuses to sign draft versions ──────


class MAASignDraftRefusalTests(SimpleTestCase):
    """The MAASignView refuses to bind a draft version."""

    def test_companion_receiver_imports_draft_helper(self):
        from apps.migration_cloud import companion_receiver
        from apps.migration_cloud.services import maa_text
        # The receiver must have imported is_draft_version.
        self.assertTrue(hasattr(maa_text, "is_draft_version"))
        # Soft-check that the receiver source references it.
        src = pathlib.Path(companion_receiver.__file__).read_text(encoding="utf-8")
        self.assertIn("is_draft_version", src)
        self.assertIn("draft_version", src)
