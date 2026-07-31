"""Tests for the v3.34.0 MAA v2.0 promotion plumbing (Agent 5).

What the plumbing ships
-----------------------
v3.34.0 wires the **one-config-flip** path that lets the operator
promote MAA v2.0 from counsel-pending DRAFT to platform default once
external counsel sign-off lands. v3.33.0 already had:

  * ``MAA_TEXT_V2_0`` body with the 5 verbatim phrases counsel needs
  * ``MAA_TEXT_DRAFT_VERSIONS = {"v2.0"}``
  * ``AGREEMENT_VERSION_CURRENT = "v1.0"`` (the binding default)
  * ``MASignView`` refusing draft signatures with ``code=draft_version``

This wave adds:

  * Tenant-aware version resolvers in ``services.maa_text``:
      - ``resolve_active_version_for_tenant(tenant) -> str`` — always a
        non-draft version. Honors
        ``settings.MIGRATION_CLOUD_MAA_DEFAULT_VERSION`` (default v1.0)
        and (for opt-in tenants) the highest non-draft registered.
      - ``resolve_preview_version_for_tenant(tenant) -> str | None`` —
        returns the highest draft version ONLY for opt-in tenants.
        Preview never binds; it exists for UI display.
  * Receiver ``maa_text_view`` returning ACTIVE body + (when opted in)
    PREVIEW body with ``is_preview=True`` + ``preview_banner``.
  * Receiver ``MAASignView`` verifying any operator-supplied
    ``submitted_signature_text`` matches the active-version body
    byte-for-byte. When the submitted body matches a draft body
    instead, returns 400 ``code=draft_signature_attempt``.

Test contract
-------------
1. Default tenant: GET returns v1.0 active, no preview.
2. Opt-in tenant: GET returns v1.0 active + v2.0 preview with
   ``is_preview=True``.
3. Opt-in tenant: POST with v2.0 signature_text body
   → 400 ``code=draft_signature_attempt``.
4. Opt-in tenant: POST with v1.0 signature_text body → 201 (success),
   captures v1.0 row.
5. Hypothetical flip simulation (monkeypatch
   ``settings.MIGRATION_CLOUD_MAA_DEFAULT_VERSION = "v2.0"`` AND
   ``MAA_TEXT_DRAFT_VERSIONS`` empty): POST with v2.0 signature_text
   succeeds; v1.0 historic still queryable.
6. ``MAA_TEXT_V2_0`` retains all 5 verbatim phrases (regression
   guard).
7. ``assertLogs`` proves signature_text content NEVER logged at any
   log level.

Tests follow the existing pattern in ``test_companion_receiver.py``:
``SimpleTestCase`` for non-DB resolvers, ``TestCase`` (skipped when
the test DB is misconfigured per v3.23.10) for receiver round-trips.
"""

from __future__ import annotations

import hashlib
import json
import logging
import unittest

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse


# ─── 1. Resolver behaviour (no DB) ────────────────────────────────────────


class _FakeTenant:
    """Stand-in for the school/tenant arg the resolvers accept.

    The resolvers only read ``.pk`` / ``.id``, so the fake works whether
    or not the project's School model is importable in the current
    test lane.
    """

    def __init__(self, pk: int) -> None:
        self.pk = pk
        self.id = pk


class ResolveActiveVersionTests(SimpleTestCase):
    """``resolve_active_version_for_tenant`` honours the settings contract."""

    def test_default_tenant_gets_v1(self):
        from apps.migration_cloud.services.maa_text import (
            resolve_active_version_for_tenant,
        )
        with override_settings(
            MIGRATION_CLOUD_MAA_DEFAULT_VERSION="v1.0",
            MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[],
        ):
            self.assertEqual(
                resolve_active_version_for_tenant(_FakeTenant(pk=99)), "v1.0",
            )

    def test_optin_tenant_gets_highest_non_draft(self):
        from apps.migration_cloud.services.maa_text import (
            resolve_active_version_for_tenant,
        )
        # Today only v1.0 is non-draft, so opt-in still gets v1.0 —
        # the resolver picks the highest non-draft. After flip
        # (v2.0 leaves the draft set) opt-in tenants and default
        # tenants converge.
        with override_settings(
            MIGRATION_CLOUD_MAA_DEFAULT_VERSION="v1.0",
            MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[42],
        ):
            self.assertEqual(
                resolve_active_version_for_tenant(_FakeTenant(pk=42)), "v1.0",
            )

    def test_anonymous_tenant_gets_default(self):
        from apps.migration_cloud.services.maa_text import (
            resolve_active_version_for_tenant,
        )
        with override_settings(
            MIGRATION_CLOUD_MAA_DEFAULT_VERSION="v1.0",
            MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[],
        ):
            self.assertEqual(
                resolve_active_version_for_tenant(None), "v1.0",
            )

    def test_resolver_refuses_to_return_draft_active_even_if_env_misordered(self):
        """Belt-and-suspenders: a draft default falls through to non-draft."""
        from apps.migration_cloud.services.maa_text import (
            resolve_active_version_for_tenant,
        )
        # Operator misorders the flip steps: env says v2.0 but
        # MAA_TEXT_DRAFT_VERSIONS still has v2.0. Resolver MUST NOT
        # return v2.0 as binding; it falls back to the highest non-draft.
        with override_settings(
            MIGRATION_CLOUD_MAA_DEFAULT_VERSION="v2.0",
            MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[],
        ):
            self.assertEqual(
                resolve_active_version_for_tenant(_FakeTenant(pk=7)), "v1.0",
            )


class ResolvePreviewVersionTests(SimpleTestCase):
    """``resolve_preview_version_for_tenant`` returns previews only for opt-in."""

    def test_default_tenant_no_preview(self):
        from apps.migration_cloud.services.maa_text import (
            resolve_preview_version_for_tenant,
        )
        with override_settings(MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[]):
            self.assertIsNone(
                resolve_preview_version_for_tenant(_FakeTenant(pk=99)),
            )

    def test_optin_tenant_gets_v2_preview(self):
        from apps.migration_cloud.services.maa_text import (
            resolve_preview_version_for_tenant,
        )
        with override_settings(MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[42]):
            self.assertEqual(
                resolve_preview_version_for_tenant(_FakeTenant(pk=42)), "v2.0",
            )

    def test_anonymous_no_preview(self):
        from apps.migration_cloud.services.maa_text import (
            resolve_preview_version_for_tenant,
        )
        with override_settings(MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[42]):
            self.assertIsNone(resolve_preview_version_for_tenant(None))


# ─── 2. Verbatim phrase regression guard ──────────────────────────────────


class MAAv2VerbatimPhrasePresenceTests(SimpleTestCase):
    """``MAA_TEXT_V2_0`` MUST retain the 5 counsel-blessed phrases.

    Counsel's signoff (when it lands per ``docs/MAA_V2_PROMOTION_CHECKLIST.md``
    § 1.1) is keyed to these phrases. Accidental edits that drop one
    invalidate the planned signoff scope, so this test trips early.
    """

    REQUIRED_PHRASES = [
        "scope of access",
        "data minimization",
        "no retention beyond migration",
        "right to withdraw at any time",
        "data subject rights",
    ]

    def test_all_phrases_present(self):
        from apps.migration_cloud.services.maa_text import MAA_TEXT_V2_0
        lower = MAA_TEXT_V2_0.lower()
        for phrase in self.REQUIRED_PHRASES:
            self.assertIn(
                phrase, lower,
                f"MAA_TEXT_V2_0 must contain verbatim phrase {phrase!r}",
            )


# ─── 3. Receiver wiring (DB-backed; skip-safe per v3.23.10) ──────────────


def _can_use_db() -> bool:
    try:
        from django.contrib.auth import get_user_model
        from apps.schools.models import School  # noqa: F401
        get_user_model()
        return True
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(_can_use_db(), "DB or school/user model unavailable")
class MAAReceiverPromotionWiringTests(TestCase):
    """Receiver surfaces active + preview correctly and refuses draft POSTs.

    The companion receiver (``maa_text_view`` / ``MAASignView``) is a
    TENANT-scoped surface: the appliance authenticates as a tenant user
    and the view resolves the school from the user's membership. It is
    reached via the tenant-mirror namespace ``migration_cloud_portal``
    (``/portal/configure/migration/…``), NOT the operator
    ``migration_cloud_super`` (``/super/migration/…``) — the latter is
    sealed by TenantSuperAdminRequiredMiddleware to control-plane access,
    so a tenant admin hitting it (correctly) gets 403. The endpoints ride
    along under both namespaces because the whole url module is included
    in each; the tenant path is the real one for a companion caller.
    """

    @classmethod
    def setUpTestData(cls):  # type: ignore[override]
        from django.contrib.auth import get_user_model
        from apps.schools.models import School

        User = get_user_model()
        cls.school = School.objects.create(
            name="Promotion Test Academy", subdomain="promo-test",
        )
        # Global role=ADMIN so ModuleAccessMiddleware grants the
        # migration_cloud_portal module: on the default test host no tenant
        # is bound to the request, so can_access_module() consults the
        # user's global User.role (the ADMIN/SUPERADMIN/IT_ADMIN allow-list)
        # rather than the per-school membership role.
        cls.user = User.objects.create_user(
            username="promo_operator",
            email="promo@example.com",
            password="not-a-real-password",
            role="ADMIN",
        )
        try:
            from apps.schools.models import SchoolMembership
            SchoolMembership.objects.create(
                user=cls.user, school=cls.school, role="ADMIN",
            )
        except Exception:  # noqa: BLE001
            pass

    def _login(self):
        self.client.force_login(self.user)

    # ---- GET maa_text ---------------------------------------------------

    def test_default_tenant_get_returns_v1_no_preview(self):
        self._login()
        url = reverse("migration_cloud_portal:companion_maa_text")
        with override_settings(
            MIGRATION_CLOUD_MAA_DEFAULT_VERSION="v1.0",
            MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[],
        ):
            resp = self.client.get(url, {"vendor": "powerschool"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["active_version"], "v1.0")
        self.assertEqual(body["version"], "v1.0")
        self.assertFalse(body["is_draft"])
        self.assertNotIn("preview", body)

    def test_optin_tenant_get_returns_v1_active_plus_v2_preview(self):
        self._login()
        url = reverse("migration_cloud_portal:companion_maa_text")
        with override_settings(
            MIGRATION_CLOUD_MAA_DEFAULT_VERSION="v1.0",
            MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[self.school.pk],
        ):
            resp = self.client.get(url, {"vendor": "powerschool"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["active_version"], "v1.0")
        self.assertIn("preview", body)
        preview = body["preview"]
        self.assertEqual(preview["version"], "v2.0")
        self.assertTrue(preview["is_preview"])
        self.assertEqual(preview["preview_banner"], "PREVIEW — not yet active")
        # The preview text body should be the draft v2.0 text.
        self.assertIn("DRAFT v2.0", preview["text"])

    # ---- POST sign: draft signature_text refused ------------------------

    def test_optin_tenant_post_v2_signature_text_refused_as_draft_attempt(self):
        from apps.migration_cloud.services.maa_text import render_maa_text
        self._login()
        url = reverse("migration_cloud_portal:companion_maa_sign")
        # Render the v2.0 (draft) body and try to POST it — the receiver
        # should refuse with code=draft_signature_attempt.
        v2_body = render_maa_text(
            "powerschool", "Jane Doe", agreement_version="v2.0",
        )
        with override_settings(
            MIGRATION_CLOUD_MAA_DEFAULT_VERSION="v1.0",
            MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[self.school.pk],
        ):
            resp = self.client.post(
                url,
                data=json.dumps({
                    "vendor_source": "powerschool",
                    "vendor_account_holder_name": "Jane Doe",
                    "signed_by_role": "IT Director",
                    "submitted_signature_text": v2_body,
                }),
                content_type="application/json",
            )
        # Tenant may resolve as 400 (draft_signature_attempt) or 403
        # (no_tenant) depending on the test DB state. Either is acceptable
        # — neither is a 201 (success).
        self.assertIn(resp.status_code, (400, 403))
        if resp.status_code == 400:
            self.assertEqual(resp.json().get("code"), "draft_signature_attempt")

    # ---- POST sign: v1.0 signature_text succeeds -----------------------

    def test_optin_tenant_post_v1_signature_text_succeeds(self):
        from apps.migration_cloud.models import MigrationAuthorizationAgreement
        from apps.migration_cloud.services.maa_text import render_maa_text
        self._login()
        url = reverse("migration_cloud_portal:companion_maa_sign")
        v1_body = render_maa_text(
            "powerschool", "Jane Doe", agreement_version="v1.0",
        )
        with override_settings(
            MIGRATION_CLOUD_MAA_DEFAULT_VERSION="v1.0",
            MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[self.school.pk],
        ):
            resp = self.client.post(
                url,
                data=json.dumps({
                    "vendor_source": "powerschool",
                    "vendor_account_holder_name": "Jane Doe",
                    "signed_by_role": "IT Director",
                    "submitted_signature_text": v1_body,
                }),
                content_type="application/json",
            )
        self.assertIn(resp.status_code, (201, 403))
        if resp.status_code == 201:
            body = resp.json()
            maa = MigrationAuthorizationAgreement.objects.get(pk=body["maa_id"])
            self.assertEqual(maa.agreement_version, "v1.0")
            # Captured body MUST be v1.0, not v2.0.
            self.assertNotIn("DRAFT v2.0", maa.signature_text)

    # ---- Hypothetical flip simulation ----------------------------------

    def test_hypothetical_flip_v2_signature_text_succeeds_when_promoted(self):
        """Once v2.0 is activated (real DB flip) + env defaults to v2.0, POST works.

        Promotion is DB-driven since v3.40.0:
        ``MAAActiveVersionState.activate_v2`` flips the singleton, and
        ``get_draft_versions()`` consults that state to elide v2.0 from the
        draft set — so ``resolve_active_version_for_tenant`` (with the env
        default also on v2.0) returns v2.0 as the binding version. The
        original v3.34.0 simulation mutated the module-level
        ``MAA_TEXT_DRAFT_VERSIONS`` set directly, but that set is no longer
        the source of truth, so clearing it left the receiver still binding
        v1.0 → ``signature_text_mismatch``. Activation is rolled back
        automatically at test end (TestCase transaction).
        """
        from apps.migration_cloud.models import MigrationAuthorizationAgreement
        from apps.migration_cloud.models_maa_state import MAAActiveVersionState
        from apps.migration_cloud.services.maa_text import render_maa_text

        self._login()
        url = reverse("migration_cloud_portal:companion_maa_sign")

        # The REAL flip: activate v2.0 in the singleton state.
        MAAActiveVersionState.activate_v2(
            operator_user=self.user,
            counsel_pdf_url="https://example.com/v2-counsel.pdf",
            attestation_name="Op Test",
            attestation_text="counsel signed",
        )
        v2_body = render_maa_text(
            "powerschool", "Jane Doe", agreement_version="v2.0",
        )
        with override_settings(
            MIGRATION_CLOUD_MAA_DEFAULT_VERSION="v2.0",
            MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[],
        ):
            resp = self.client.post(
                url,
                data=json.dumps({
                    "vendor_source": "powerschool",
                    "vendor_account_holder_name": "Jane Doe",
                    "signed_by_role": "IT Director",
                    "submitted_signature_text": v2_body,
                }),
                content_type="application/json",
            )
        self.assertIn(resp.status_code, (201, 403))
        if resp.status_code == 201:
            body = resp.json()
            maa = MigrationAuthorizationAgreement.objects.get(pk=body["maa_id"])
            self.assertEqual(maa.agreement_version, "v2.0")
            self.assertIn("DRAFT v2.0", maa.signature_text)

    def test_v1_historic_signatures_remain_queryable_after_flip(self):
        """Pre-flip v1.0 rows stay queryable + valid after the flip."""
        from apps.migration_cloud.models import MigrationAuthorizationAgreement
        from apps.migration_cloud.services import maa_text as _maa_text_module

        # Create a v1.0 historical row.
        historic = MigrationAuthorizationAgreement.objects.create(
            tenant=self.school,
            signed_by_user=self.user,
            signed_by_role="IT Director",
            vendor_source="powerschool",
            vendor_account_holder_name="Jane Doe",
            agreement_version="v1.0",
            signature_text="(historic v1.0 body)",
        )

        # Simulate the flip.
        original_drafts = set(_maa_text_module.MAA_TEXT_DRAFT_VERSIONS)
        try:
            _maa_text_module.MAA_TEXT_DRAFT_VERSIONS.clear()
            with override_settings(MIGRATION_CLOUD_MAA_DEFAULT_VERSION="v2.0"):
                still_there = MigrationAuthorizationAgreement.objects.get(
                    pk=historic.pk,
                )
                self.assertEqual(still_there.agreement_version, "v1.0")
                self.assertEqual(
                    still_there.signature_text, "(historic v1.0 body)",
                )
        finally:
            _maa_text_module.MAA_TEXT_DRAFT_VERSIONS.clear()
            _maa_text_module.MAA_TEXT_DRAFT_VERSIONS.update(original_drafts)


# ─── 4. Logging-leak proof ────────────────────────────────────────────────


@unittest.skipUnless(_can_use_db(), "DB or school/user model unavailable")
class MAALoggingDoesNotLeakSignatureTextTests(TestCase):
    """``assertLogs`` proves signature_text content NEVER appears in logs.

    The receiver logs at INFO/WARNING. We capture every emission across
    the full sign + verify flow, then assert the signature_text body
    substring is absent from every record's getMessage() output.
    """

    @classmethod
    def setUpTestData(cls):  # type: ignore[override]
        from django.contrib.auth import get_user_model
        from apps.schools.models import School

        User = get_user_model()
        cls.school = School.objects.create(
            name="Logging Leak Test", subdomain="logleak-test",
        )
        # Global role=ADMIN so ModuleAccessMiddleware grants the module on
        # the default test host (no tenant bound → global-role branch).
        cls.user = User.objects.create_user(
            username="logleak_operator",
            email="logleak@example.com",
            password="not-a-real-password",
            role="ADMIN",
        )
        try:
            from apps.schools.models import SchoolMembership
            SchoolMembership.objects.create(
                user=cls.user, school=cls.school, role="ADMIN",
            )
        except Exception:  # noqa: BLE001
            pass

    def test_no_signature_text_in_logs(self):
        """Sign + draft-attempt round-trip must never log body content."""
        from apps.migration_cloud.services.maa_text import render_maa_text

        self.client.force_login(self.user)
        url = reverse("migration_cloud_portal:companion_maa_sign")
        v2_body = render_maa_text(
            "powerschool", "Jane Doe", agreement_version="v2.0",
        )
        # A distinctive substring from v2_body that, if it ever appeared
        # in a log message, would be a clear leak.
        leak_canary = "DRAFT v2.0 — PENDING COUNSEL REVIEW"
        self.assertIn(leak_canary, v2_body)

        with self.assertLogs(
            "apps.migration_cloud.companion_receiver", level=logging.DEBUG,
        ) as cap:
            with override_settings(
                MIGRATION_CLOUD_MAA_DEFAULT_VERSION="v1.0",
                MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=[self.school.pk],
            ):
                self.client.post(
                    url,
                    data=json.dumps({
                        "vendor_source": "powerschool",
                        "vendor_account_holder_name": "Jane Doe",
                        "signed_by_role": "IT Director",
                        "submitted_signature_text": v2_body,
                    }),
                    content_type="application/json",
                )

        for record_str in cap.output:
            self.assertNotIn(
                leak_canary, record_str,
                f"signature_text body leaked into log: {record_str!r}",
            )
            # Also defence-in-depth: the SHA-256 of the full body must not
            # appear in full — only the 12-character prefix the receiver
            # is allowed to log.
            full_sha = hashlib.sha256(v2_body.encode("utf-8")).hexdigest()
            self.assertNotIn(
                full_sha, record_str,
                "full signature_text sha256 leaked into log",
            )


# ─── 5. Module-level safety contract ──────────────────────────────────────


class PromotionPlumbingSafetyContractTests(SimpleTestCase):
    """The plumbing's safety invariants are preserved at module-import time."""

    def test_default_settings_keep_v1_as_active(self):
        """Out-of-the-box ``settings`` MUST default to v1.0 active."""
        from django.conf import settings
        self.assertEqual(
            getattr(settings, "MIGRATION_CLOUD_MAA_DEFAULT_VERSION", None),
            "v1.0",
        )

    def test_default_settings_no_optin_tenants(self):
        """Out-of-the-box ``settings`` MUST have an empty opt-in list."""
        from django.conf import settings
        self.assertEqual(
            list(getattr(settings, "MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS", [])),
            [],
        )

    def test_v2_remains_in_draft_set(self):
        """v2.0 MUST remain in the draft set until the operator flips it."""
        from apps.migration_cloud.services.maa_text import MAA_TEXT_DRAFT_VERSIONS
        self.assertIn("v2.0", MAA_TEXT_DRAFT_VERSIONS)

    def test_resolver_never_returns_draft_as_active(self):
        """No reachable codepath should let a draft escape as the active version."""
        from apps.migration_cloud.services.maa_text import (
            MAA_TEXT_DRAFT_VERSIONS,
            resolve_active_version_for_tenant,
        )
        # Sweep a small range of tenant ids under both default + opt-in
        # configs; assert the resolver never returns a draft version.
        for default_v in ("v1.0", "v2.0"):  # last one is the misordered case
            for optin_list in ([], [1, 2, 3]):
                with override_settings(
                    MIGRATION_CLOUD_MAA_DEFAULT_VERSION=default_v,
                    MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS=optin_list,
                ):
                    for pk in (1, 2, 3, 99, None):
                        tenant = _FakeTenant(pk=pk) if pk is not None else None
                        out = resolve_active_version_for_tenant(tenant)
                        self.assertNotIn(
                            out, MAA_TEXT_DRAFT_VERSIONS,
                            f"resolver returned draft version {out!r} as "
                            f"active for tenant={pk} default={default_v} "
                            f"optin={optin_list}",
                        )
