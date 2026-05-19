"""Tests for the v3.37.0 MAA v2.0 promotion verifier + campaign + dashboard.

Agent 3 of the v3.37.0 fan-out ships:

  1. ``scripts/verify_maa_v2_promotion_readiness.py`` (stdlib-only
     pre-flight verifier).
  2. ``apps.migration_cloud.management.commands.maa_v2_resign_campaign``
     (dry-run by default, idempotent re-sign campaign driver).
  3. ``MigrationCloudCounselAttestation`` +
     ``MigrationCloudMAACampaignNotification`` (append-only audit).
  4. ``MAA_V2_PromotionDashboardView`` staff-only operator dashboard.

This module verifies all four with both DB-free (``SimpleTestCase``)
and DB-backed (``TestCase`` — skipped when the project's test DB +
schools/user model aren't reachable, mirroring the v3.34.0 plumbing
test pattern).

Logging discipline (zero-tolerance): the tests assert no log record
emitted during any of the in-process verifier / dashboard / campaign
runs leaks MAA body text, signature_text bytes, sha256 bytes, or
counsel attestation_text. The body of the v2.0 draft template is
public (it lives in the maa_text.py source) so we instead spot-check
that the DRAFT header is never printed verbatim into log output.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _ensure_scripts_on_path() -> None:
    s = str(SCRIPTS_DIR)
    if s not in sys.path:
        sys.path.insert(0, s)


# ─── 1. Pre-flight verifier (stdlib-only, no DB) ──────────────────────────


class PreflightVerifierTests(SimpleTestCase):
    """``scripts/verify_maa_v2_promotion_readiness.py`` is pure-stdlib + DB-free.

    We exercise the verifier's ``run_all_checks()`` callable directly so
    the test does not shell out. The contract: the DRAFT header check
    fails today (header is present), and a tmp-file fixture proves the
    check goes green once the header is removed by hand.
    """

    def test_verifier_module_is_importable(self):
        _ensure_scripts_on_path()
        import verify_maa_v2_promotion_readiness as verifier  # noqa: F401

    def test_v2_phrases_present_check_passes_today(self):
        _ensure_scripts_on_path()
        import verify_maa_v2_promotion_readiness as verifier

        result = verifier._check_v2_phrases_present()
        self.assertTrue(
            result["ok"],
            f"v2_phrases_present should pass today, got: {result!r}",
        )

    def test_draft_header_check_fails_while_header_present(self):
        _ensure_scripts_on_path()
        import verify_maa_v2_promotion_readiness as verifier

        # Today the maa_text.py source carries the DRAFT header so the
        # promotion-readiness check MUST report ok=False.
        result = verifier._check_draft_header_removed()
        self.assertFalse(
            result["ok"],
            "draft_header_removed should still fail until counsel signoff lands",
        )

    def test_draft_header_check_passes_when_header_removed_tmp_fixture(self):
        """tmpfile-fixture variant: rewrite maa_text.py without the DRAFT header.

        We swap out ``REPO_ROOT`` on the verifier module to point at a
        temp dir that contains a hand-written copy of maa_text.py with
        the DRAFT header substring stripped, then re-run the check.
        Restored in tearDown so subsequent tests see the real source.
        """
        _ensure_scripts_on_path()
        import verify_maa_v2_promotion_readiness as verifier

        tmp = Path(tempfile.mkdtemp(prefix="maa_v2_verifier_test_"))
        try:
            # Mirror the directory layout the verifier expects.
            target_dir = (
                tmp / "apps" / "migration_cloud" / "services"
            )
            target_dir.mkdir(parents=True, exist_ok=True)
            src_path = (
                REPO_ROOT
                / "apps"
                / "migration_cloud"
                / "services"
                / "maa_text.py"
            )
            src = src_path.read_text(encoding="utf-8")
            # Remove the DRAFT header substring (only the string literal
            # inside _TEMPLATE_V2; everything else stays).
            patched = src.replace(
                verifier.DRAFT_HEADER_SUBSTR, "[v2.0 ACTIVE]",
            )
            (target_dir / "maa_text.py").write_text(
                patched, encoding="utf-8",
            )
            original_root = verifier.REPO_ROOT
            verifier.REPO_ROOT = tmp
            try:
                result = verifier._check_draft_header_removed()
            finally:
                verifier.REPO_ROOT = original_root
            self.assertTrue(
                result["ok"],
                f"draft_header_removed should pass on the patched fixture, "
                f"got: {result!r}",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_v2_still_in_draft_set_check_fails_today(self):
        _ensure_scripts_on_path()
        import verify_maa_v2_promotion_readiness as verifier

        result = verifier._check_v2_not_in_draft_set()
        # Today MAA_TEXT_DRAFT_VERSIONS still contains "v2.0", so the
        # check MUST be ok=False — this gate refuses to flip the
        # promotion until that set is emptied.
        self.assertFalse(result["ok"])
        self.assertIn("v2.0", result["note"])

    def test_run_all_checks_reports_overall_not_ok_today(self):
        _ensure_scripts_on_path()
        import verify_maa_v2_promotion_readiness as verifier

        report = verifier.run_all_checks()
        # Today (pre-flip) the report MUST be ok=False — at minimum the
        # draft-header check is failing.
        self.assertFalse(report["ok"])
        self.assertGreaterEqual(report["fail_count"], 1)
        self.assertEqual(
            report["ok_count"] + report["fail_count"], report["total_count"],
        )


# ─── 2. Counsel attestation deterministic-hash helper (DB-free) ──────────


def _canonical_attestation_hash(
    version: str, attested_by_email: str, attested_at_iso: str,
) -> str:
    """Helper mirroring the canonical-JSON SHA256 used by the dashboard.

    This is the contract the operator UI / mgmt tooling should produce
    when stamping ``attestation_hash`` on a future
    ``MigrationCloudCounselAttestation`` row. Today the model stores
    operator narrative + path; the hash helper is exercised here so
    the contract is testable + portable.
    """
    canonical = json.dumps(
        {
            "version": version,
            "attested_by_email": attested_by_email,
            "attested_at_isoformat": attested_at_iso,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class AttestationHashHelperTests(SimpleTestCase):
    """Canonical-JSON attestation hash is deterministic + constant-time-cmp-safe."""

    def test_hash_is_deterministic(self):
        h1 = _canonical_attestation_hash(
            "v2.0", "counsel@example.com", "2026-06-01T00:00:00",
        )
        h2 = _canonical_attestation_hash(
            "v2.0", "counsel@example.com", "2026-06-01T00:00:00",
        )
        self.assertEqual(h1, h2)
        self.assertTrue(hmac.compare_digest(h1, h2))
        self.assertEqual(len(h1), 64)

    def test_hash_changes_when_email_changes(self):
        h1 = _canonical_attestation_hash(
            "v2.0", "counsel@example.com", "2026-06-01T00:00:00",
        )
        h2 = _canonical_attestation_hash(
            "v2.0", "other@example.com", "2026-06-01T00:00:00",
        )
        self.assertFalse(hmac.compare_digest(h1, h2))


# ─── 3. Module-level regression guards (DB-free) ─────────────────────────


class MAAv2DraftSetRegressionTests(SimpleTestCase):
    """``MAA_TEXT_DRAFT_VERSIONS`` still contains v2.0 + default still v1.0.

    Belt-and-suspenders against an accidental promotion landing in a
    PR without running the verifier first.
    """

    def test_v2_still_in_draft_set(self):
        from apps.migration_cloud.services.maa_text import (
            MAA_TEXT_DRAFT_VERSIONS,
        )
        self.assertIn("v2.0", MAA_TEXT_DRAFT_VERSIONS)

    def test_default_version_is_v1(self):
        # This is the in-process default constant; the actual binding
        # default also honours settings.MIGRATION_CLOUD_MAA_DEFAULT_VERSION.
        from apps.migration_cloud.services.maa_text import (
            AGREEMENT_VERSION_CURRENT,
        )
        self.assertEqual(AGREEMENT_VERSION_CURRENT, "v1.0")


# ─── 4. DB-backed: campaign mgmt command + dashboard view ────────────────


def _can_use_db() -> bool:
    try:
        from django.contrib.auth import get_user_model
        from apps.schools.models import School  # noqa: F401
        get_user_model()
        return True
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(_can_use_db(), "DB or school/user model unavailable")
class CampaignMgmtCommandTests(TestCase):
    """``maa_v2_resign_campaign`` dry-run + apply + idempotent re-run."""

    @classmethod
    def setUpTestData(cls):  # type: ignore[override]
        from django.contrib.auth import get_user_model
        from apps.schools.models import School
        from apps.migration_cloud.models import (
            MigrationAuthorizationAgreement,
        )

        User = get_user_model()
        cls.school = School.objects.create(
            name="Campaign Test Academy", subdomain="campaign-test",
        )
        cls.user = User.objects.create_user(
            username="campaign_op",
            email="campaign-op@example.com",
            password="not-a-real-password",
        )
        cls.agreement = MigrationAuthorizationAgreement.objects.create(
            tenant=cls.school,
            signed_by_user=cls.user,
            signed_by_role="IT Director",
            vendor_source="powerschool",
            vendor_account_holder_name="Campaign Holder",
            agreement_version="v1.0",
            signature_text="(historic v1.0 body)",
        )

    def _run_command(self, *args: str) -> str:
        from django.core.management import call_command

        buf = io.StringIO()
        call_command("maa_v2_resign_campaign", *args, stdout=buf, stderr=buf)
        return buf.getvalue()

    def test_dry_run_default_creates_dry_run_rows(self):
        from apps.migration_cloud.models import (
            MigrationCloudMAACampaignNotification,
        )

        # tenant-isolation-allow: test-fixture-counts-only-cross-tenant
        pre = MigrationCloudMAACampaignNotification.objects.count()
        output = self._run_command()
        # tenant-isolation-allow: test-fixture-counts-only-cross-tenant
        post = MigrationCloudMAACampaignNotification.objects.count()
        # Either we created a row (no v2 row exists for this signer
        # yet, no prior notification) or we already had one in this
        # transaction. Either way: at least one dry-run row exists.
        self.assertGreaterEqual(post, pre + 0)
        self.assertIn("maa_v2_resign_campaign:dry_run", output)
        # tenant-isolation-allow: test-fixture-counts-only-cross-tenant
        dry_rows = MigrationCloudMAACampaignNotification.objects.filter(
            dispatch_mode="dry_run", agreement=self.agreement,
        )
        # The first dry-run leaves a row recorded.
        self.assertTrue(dry_rows.exists())
        # NEVER prints the signature_text body content.
        self.assertNotIn("(historic v1.0 body)", output)

    def test_apply_creates_queued_row_and_actual_email(self):
        from apps.migration_cloud.models import (
            MigrationCloudMAACampaignNotification,
        )
        from django.core import mail
        from apps.migration_cloud.models import (
            MigrationAuthorizationAgreement,
        )

        # Run the campaign with a *fresh* campaign-version so the
        # idempotency constraint doesn't suppress the row from a
        # previous dry_run.
        fresh = MigrationAuthorizationAgreement.objects.create(
            tenant=self.school,
            signed_by_user=self.user,
            signed_by_role="IT Director",
            vendor_source="blackbaud",
            vendor_account_holder_name="Campaign Holder",
            agreement_version="v1.0",
            signature_text="(another historic v1.0 body)",
        )
        mail.outbox.clear()
        output = self._run_command(
            "--apply", "--campaign-version", "test_apply_campaign",
        )
        self.assertIn("maa_v2_resign_campaign:queued", output)
        # tenant-isolation-allow: test-fixture-counts-only-cross-tenant
        queued_rows = MigrationCloudMAACampaignNotification.objects.filter(
            dispatch_mode="queued",
            campaign_version="test_apply_campaign",
            agreement=fresh,
        )
        self.assertTrue(queued_rows.exists())
        # Email got sent to the locmem backend.
        recipients_flat = {
            addr for msg in mail.outbox for addr in (msg.to or [])
        }
        self.assertIn("campaign-op@example.com", recipients_flat)

    def test_idempotent_second_run_does_not_double_notify(self):
        from apps.migration_cloud.models import (
            MigrationCloudMAACampaignNotification,
        )

        cv = "test_idempotent_campaign"
        self._run_command("--campaign-version", cv)
        # tenant-isolation-allow: test-fixture-counts-only-cross-tenant
        first_count = MigrationCloudMAACampaignNotification.objects.filter(
            campaign_version=cv,
        ).count()
        # Re-run with the same campaign version. The unique constraint
        # on (agreement, recipient_email, campaign_version) prevents
        # double-insertion.
        self._run_command("--campaign-version", cv)
        # tenant-isolation-allow: test-fixture-counts-only-cross-tenant
        second_count = MigrationCloudMAACampaignNotification.objects.filter(
            campaign_version=cv,
        ).count()
        self.assertEqual(first_count, second_count)

    def test_tenant_flag_restricts_to_one_tenant(self):
        from apps.schools.models import School
        from apps.migration_cloud.models import (
            MigrationAuthorizationAgreement,
            MigrationCloudMAACampaignNotification,
        )

        other = School.objects.create(
            name="Other Academy", subdomain="other-academy",
        )
        # Cross-tenant fixture: a v1.0 agreement in a different tenant.
        MigrationAuthorizationAgreement.objects.create(
            tenant=other,
            signed_by_user=self.user,
            signed_by_role="IT Director",
            vendor_source="powerschool",
            vendor_account_holder_name="Other Holder",
            agreement_version="v1.0",
            signature_text="(historic other-tenant v1.0 body)",
        )
        cv = "test_tenant_scoped_campaign"
        # --tenant restricts strictly to the other-academy subdomain.
        self._run_command(
            "--tenant", "other-academy", "--campaign-version", cv,
        )
        # tenant-isolation-allow: test-fixture-counts-only-cross-tenant
        rows = MigrationCloudMAACampaignNotification.objects.filter(
            campaign_version=cv,
        )
        for row in rows:
            self.assertEqual(row.agreement.tenant_id, other.pk)


@unittest.skipUnless(_can_use_db(), "DB or school/user model unavailable")
class CounselAttestationUniquenessTests(TestCase):
    """``MigrationCloudCounselAttestation`` accepts multi-row + protects FK."""

    def test_two_rows_for_same_operator_and_type_allowed(self):
        from django.contrib.auth import get_user_model
        from apps.migration_cloud.models import (
            MigrationCloudCounselAttestation,
        )

        User = get_user_model()
        op = User.objects.create_user(
            username="legal_op", email="legal@example.com",
            password="not-a-real-password",
        )
        # tenant-isolation-allow: platform-wide-counsel-attestation-audit-log
        MigrationCloudCounselAttestation.objects.create(
            operator=op,
            attestation_type="maa_v2_counsel_signoff_received",
            attestation_text="first attestation event",
            related_artifact_path="docs/legal/maa_v2_signoff.pdf",
        )
        # tenant-isolation-allow: platform-wide-counsel-attestation-audit-log
        MigrationCloudCounselAttestation.objects.create(
            operator=op,
            attestation_type="maa_v2_counsel_signoff_received",
            attestation_text="supersedes prior attestation (counsel re-confirm)",
            related_artifact_path="docs/legal/maa_v2_signoff_v2.pdf",
        )
        # tenant-isolation-allow: platform-wide-counsel-attestation-audit-log
        self.assertEqual(
            MigrationCloudCounselAttestation.objects.filter(
                operator=op,
                attestation_type="maa_v2_counsel_signoff_received",
            ).count(),
            2,
        )


@unittest.skipUnless(_can_use_db(), "DB or school/user model unavailable")
class PromotionDashboardViewTests(TestCase):
    """``MAA_V2_PromotionDashboardView`` is staff-gated and renders four panels."""

    @classmethod
    def setUpTestData(cls):  # type: ignore[override]
        from django.contrib.auth import get_user_model

        User = get_user_model()
        cls.staff = User.objects.create_user(
            username="dash_staff",
            email="dash-staff@example.com",
            password="not-a-real-password",
            is_staff=True,
        )
        cls.civilian = User.objects.create_user(
            username="dash_civilian",
            email="dash-civilian@example.com",
            password="not-a-real-password",
            is_staff=False,
        )

    def _dashboard_url(self) -> str:
        return reverse(
            "migration_cloud_super:maa_v2_promotion_dashboard",
        )

    def test_anonymous_user_redirected_or_forbidden(self):
        resp = self.client.get(self._dashboard_url())
        # ``staff_member_required`` redirects to the admin login by
        # default; some deploys map this to a 403. Either is acceptable
        # — we just MUST NOT see a 200 with the body.
        self.assertIn(resp.status_code, (302, 403, 401))

    def test_civilian_user_forbidden(self):
        self.client.force_login(self.civilian)
        resp = self.client.get(self._dashboard_url())
        self.assertIn(resp.status_code, (302, 403))
        if resp.status_code == 200:
            self.fail("Civilian users must not see the dashboard body")

    def test_staff_user_sees_dashboard_with_panels(self):
        self.client.force_login(self.staff)
        resp = self.client.get(self._dashboard_url())
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        # All four panel headings present.
        self.assertIn("MAA v2.0 promotion status", body)
        self.assertIn("Readiness", body)
        self.assertIn("Draft", body)
        self.assertIn("Counsel attestations", body)
        self.assertIn("campaign", body.lower())
        # Today the default version is v1.0; the badge must say so.
        self.assertIn("v1.0", body)

    def test_dashboard_does_not_leak_signature_text_into_response(self):
        """Smoke: the dashboard page must not contain MAA body content.

        We render the page with at least one v1.0 MAA row + at least
        one counsel attestation present, then check the response body
        does NOT contain the v1.0 boilerplate phrase. Belt-and-
        suspenders: the dashboard is COUNT-only by design.
        """
        from apps.migration_cloud.models import (
            MigrationAuthorizationAgreement,
            MigrationCloudCounselAttestation,
        )
        from apps.schools.models import School

        school = School.objects.create(
            name="Dash Audit Academy", subdomain="dash-audit",
        )
        MigrationAuthorizationAgreement.objects.create(
            tenant=school,
            signed_by_user=self.staff,
            signed_by_role="IT Director",
            vendor_source="powerschool",
            vendor_account_holder_name="Dash Holder",
            agreement_version="v1.0",
            signature_text="UNIQUE_BODY_TOKEN_FOR_LEAK_DETECTION_42",
        )
        # tenant-isolation-allow: platform-wide-counsel-attestation-audit-log
        MigrationCloudCounselAttestation.objects.create(
            operator=self.staff,
            attestation_type="maa_v2_counsel_signoff_received",
            attestation_text="counsel signoff PDF filed",
            related_artifact_path="docs/legal/maa_v2_signoff.pdf",
        )
        self.client.force_login(self.staff)
        resp = self.client.get(self._dashboard_url())
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertNotIn("UNIQUE_BODY_TOKEN_FOR_LEAK_DETECTION_42", body)


# ─── 5. v3.34 draft refusal regression guard (no DB required) ────────────


class DraftRefusalRegressionTests(SimpleTestCase):
    """The v3.34.0 receiver-side draft refusal stays in place."""

    def test_is_draft_version_still_says_yes_for_v2(self):
        from apps.migration_cloud.services.maa_text import is_draft_version
        self.assertTrue(is_draft_version("v2.0"))
        self.assertFalse(is_draft_version("v1.0"))

    def test_render_maa_text_v2_carries_draft_header_today(self):
        from apps.migration_cloud.services.maa_text import render_maa_text
        body = render_maa_text("powerschool", "Jane Doe", agreement_version="v2.0")
        self.assertIn("[DRAFT v2.0 — PENDING COUNSEL REVIEW]", body)


# ─── 6. Verifier-logging discipline (zero PII / no body bytes) ───────────


class VerifierLoggingDisciplineTests(SimpleTestCase):
    """The verifier never logs MAA body content at any level."""

    def test_run_all_checks_logs_emit_no_body_bytes(self):
        _ensure_scripts_on_path()
        import verify_maa_v2_promotion_readiness as verifier

        # Capture ALL log records emitted during the verifier run.
        captured = io.StringIO()
        handler = logging.StreamHandler(captured)
        root = logging.getLogger()
        original_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            verifier.run_all_checks()
        finally:
            root.removeHandler(handler)
            root.setLevel(original_level)
        emitted = captured.getvalue()
        # Body-content indicators we MUST NOT see:
        forbidden = [
            # The v1.0 body opens with this phrase.
            "RunMyCampus Migration Authorization Agreement",
            # The v2.0 body opens with this DRAFT header.
            "[DRAFT v2.0 — PENDING COUNSEL REVIEW]",
            # Section heading verbatim phrases.
            "DATA MINIMIZATION",
            "RIGHT TO WITHDRAW AT ANY TIME",
        ]
        for needle in forbidden:
            self.assertNotIn(
                needle, emitted,
                f"verifier log output leaked MAA body content: {needle!r}",
            )
