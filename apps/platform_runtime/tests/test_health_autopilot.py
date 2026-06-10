"""Tests for the health self-healing engine (Phase 1).

DB-free: SimpleTestCase + mocks. The engine's gateway/policy/apply touchpoints are all
imported lazily inside functions, so patching the source module paths is sufficient.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.platform_runtime import health_autopilot as ha


class CatalogInvariantTests(SimpleTestCase):
    def test_every_kind_is_reversible_and_scoped(self):
        self.assertTrue(ha.HEALTH_REMEDIATION_KINDS)
        for kind, meta in ha.HEALTH_REMEDIATION_KINDS.items():
            self.assertTrue(meta.get("reversible"), f"{kind} must be reversible")
            self.assertIn(meta.get("scope"), ("school", "platform"), kind)

    def test_signal_rules_only_target_catalog_kinds(self):
        for sig, kind in ha._SIGNAL_RULES.items():
            self.assertIn(kind, ha.HEALTH_REMEDIATION_KINDS, sig)

    def test_ai_confidence_floor_is_sane(self):
        self.assertGreaterEqual(ha.AI_MIN_CONFIDENCE, 0.5)
        self.assertLessEqual(ha.AI_MIN_CONFIDENCE, 1.0)


class ProposeRemediationTests(SimpleTestCase):
    def test_rule_match(self):
        prop = ha.propose_remediation("tenant_offline_unconfigured")
        self.assertEqual(prop["verdict"], "match")
        self.assertEqual(prop["kind"], ha.KIND_REBUILD_OFFLINE_MANIFEST)
        self.assertEqual(prop["source"], "rule")
        self.assertEqual(prop["confidence"], 1.0)
        self.assertTrue(prop["auto_fix_available"])

    def test_empty_signal_no_match(self):
        prop = ha.propose_remediation("")
        self.assertEqual(prop["verdict"], "no_match")
        self.assertFalse(prop["auto_fix_available"])

    def test_unknown_signal_ai_disabled_no_match(self):
        with mock.patch.object(ha, "_classify_signal_with_ai", return_value=None):
            prop = ha.propose_remediation("some_unknown_signal")
        self.assertEqual(prop["verdict"], "no_match")
        self.assertFalse(prop["auto_fix_available"])

    def test_unknown_signal_ai_promotes_to_catalog_kind(self):
        with mock.patch.object(
            ha,
            "_classify_signal_with_ai",
            return_value=(ha.KIND_RECOMPUTE_HEALTH_SNAPSHOT, 0.91),
        ):
            prop = ha.propose_remediation("weird_degradation")
        self.assertEqual(prop["verdict"], "match")
        self.assertEqual(prop["kind"], ha.KIND_RECOMPUTE_HEALTH_SNAPSHOT)
        self.assertEqual(prop["source"], "ai")
        self.assertEqual(prop["confidence"], 0.91)


class AIClassifierTests(SimpleTestCase):
    def _patch(self, *, enabled, text):
        return (
            mock.patch(
                "apps.platform_runtime.ai_providers.get_ai_runtime_config",
                return_value={"enabled": enabled},
            ),
            mock.patch(
                "apps.platform_runtime.ai_providers.run_ai_prompt",
                return_value=(text, {}),
            ),
        )

    def test_ai_disabled_makes_no_model_call(self):
        run = mock.MagicMock()
        with mock.patch(
            "apps.platform_runtime.ai_providers.get_ai_runtime_config",
            return_value={"enabled": False},
        ), mock.patch("apps.platform_runtime.ai_providers.run_ai_prompt", run):
            out = ha._classify_signal_with_ai("x")
        self.assertIsNone(out)
        run.assert_not_called()

    def test_ai_valid_kind_high_confidence(self):
        text = '{"kind": "recompute_health_snapshot", "confidence": 0.88}'
        cfg, run = self._patch(enabled=True, text=text)
        with cfg, run:
            out = ha._classify_signal_with_ai("x")
        self.assertEqual(out, (ha.KIND_RECOMPUTE_HEALTH_SNAPSHOT, 0.88))

    def test_ai_invented_kind_is_rejected(self):
        text = '{"kind": "delete_all_tenants", "confidence": 0.99}'
        cfg, run = self._patch(enabled=True, text=text)
        with cfg, run:
            out = ha._classify_signal_with_ai("x")
        self.assertIsNone(out)

    def test_ai_low_confidence_is_rejected(self):
        text = '{"kind": "recompute_health_snapshot", "confidence": 0.3}'
        cfg, run = self._patch(enabled=True, text=text)
        with cfg, run:
            out = ha._classify_signal_with_ai("x")
        self.assertIsNone(out)

    def test_ai_malformed_output_is_rejected(self):
        cfg, run = self._patch(enabled=True, text="not json at all")
        with cfg, run:
            out = ha._classify_signal_with_ai("x")
        self.assertIsNone(out)

    def test_ai_kind_embedded_in_prose_is_parsed(self):
        text = 'Sure: {"kind": "recompute_health_snapshot", "confidence": 0.8} hope that helps'
        cfg, run = self._patch(enabled=True, text=text)
        with cfg, run:
            out = ha._classify_signal_with_ai("x")
        self.assertEqual(out, (ha.KIND_RECOMPUTE_HEALTH_SNAPSHOT, 0.8))


class ApplyKindTests(SimpleTestCase):
    def test_unsupported_kind(self):
        self.assertFalse(ha._apply_kind("nope")["ok"])

    def test_rebuild_offline_manifest_needs_school(self):
        out = ha._apply_kind(ha.KIND_REBUILD_OFFLINE_MANIFEST)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "missing_school")

    def test_recompute_snapshot_busts_and_recomputes(self):
        with mock.patch(
            "apps.platform_runtime.platform_health.bust_summary_cache"
        ) as bust, mock.patch(
            "apps.platform_runtime.platform_health.platform_health_summary",
            return_value={"level": "success", "count": 0},
        ):
            out = ha._apply_kind(ha.KIND_RECOMPUTE_HEALTH_SNAPSHOT)
        self.assertTrue(out["ok"])
        bust.assert_called_once()


class PreviewTests(SimpleTestCase):
    def test_preview_known_kind(self):
        p = ha.preview_remediation(ha.KIND_REBUILD_OFFLINE_MANIFEST)
        self.assertTrue(p["ok"])
        self.assertTrue(p["dry_run"])
        self.assertTrue(p["needs_school"])

    def test_preview_unknown_kind(self):
        self.assertFalse(ha.preview_remediation("nope")["ok"])


class TryAutoApplyTests(SimpleTestCase):
    def test_shadow_when_no_auto_fix(self):
        with mock.patch.object(ha, "_classify_signal_with_ai", return_value=None):
            out = ha.try_auto_apply(signal="totally_unknown")
        self.assertEqual(out["mode"], "shadow")
        self.assertFalse(out["applied"])

    def test_shadow_when_policy_disabled(self):
        with mock.patch(
            "apps.platform_runtime.workflow_autopilot.policy_allows_auto_fix",
            return_value=False,
        ):
            out = ha.try_auto_apply(signal="platform_health_degraded")
        self.assertEqual(out["mode"], "shadow")
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "policy_disabled")
        self.assertIn("preview", out)

    def test_apply_when_policy_enabled(self):
        with mock.patch(
            "apps.platform_runtime.workflow_autopilot.policy_allows_auto_fix",
            return_value=True,
        ), mock.patch.object(
            ha,
            "_apply_kind",
            return_value={"ok": True, "applied": ha.KIND_RECOMPUTE_HEALTH_SNAPSHOT},
        ), mock.patch.object(ha, "record_health_log"), mock.patch(
            "apps.platform_runtime.workflow_autopilot.record_apply_log"
        ) as log:
            out = ha.try_auto_apply(signal="platform_health_degraded")
        self.assertEqual(out["mode"], "apply")
        self.assertTrue(out["applied"])
        log.assert_called_once()

    def test_apply_failure_is_logged_as_failed(self):
        with mock.patch(
            "apps.platform_runtime.workflow_autopilot.policy_allows_auto_fix",
            return_value=True,
        ), mock.patch.object(
            ha, "_apply_kind", return_value={"ok": False, "reason": "boom"}
        ), mock.patch.object(ha, "record_health_log"), mock.patch(
            "apps.platform_runtime.workflow_autopilot.record_apply_log"
        ) as log:
            out = ha.try_auto_apply(signal="platform_health_degraded")
        self.assertFalse(out["applied"])
        log.assert_called_once()
        self.assertEqual(log.call_args.kwargs["outcome"], "failed")


class HealthRemediationLogTests(TestCase):
    def _count(self, **kw):
        from apps.platform_runtime.models import HealthRemediationLog

        return HealthRemediationLog.objects.filter(**kw).count()

    def test_record_creates_school_attributed_row(self):
        from apps.platform_runtime.models import HealthRemediationLog

        ha.record_health_log(
            signal="platform_health_degraded",
            kind=ha.KIND_RECOMPUTE_HEALTH_SNAPSHOT,
            source="rule",
            mode="apply",
            outcome="applied",
        )
        row = HealthRemediationLog.objects.get(signal="platform_health_degraded")
        self.assertEqual(row.kind, ha.KIND_RECOMPUTE_HEALTH_SNAPSHOT)
        self.assertEqual(row.mode, "apply")
        self.assertEqual(row.outcome, "applied")
        self.assertEqual(row.school_slug, "")

    def test_apply_path_writes_log(self):
        with mock.patch(
            "apps.platform_runtime.workflow_autopilot.policy_allows_auto_fix",
            return_value=True,
        ), mock.patch.object(
            ha,
            "_apply_kind",
            return_value={"ok": True, "applied": ha.KIND_RECOMPUTE_HEALTH_SNAPSHOT},
        ), mock.patch(
            "apps.platform_runtime.workflow_autopilot.record_apply_log"
        ):
            ha.try_auto_apply(signal="platform_health_degraded")
        self.assertEqual(self._count(mode="apply", outcome="applied"), 1)

    def test_shadow_records_only_when_requested(self):
        with mock.patch(
            "apps.platform_runtime.workflow_autopilot.policy_allows_auto_fix",
            return_value=False,
        ):
            ha.try_auto_apply(signal="platform_health_degraded")  # default: no record
            self.assertEqual(self._count(mode="shadow"), 0)
            ha.try_auto_apply(signal="platform_health_degraded", record_shadow=True)
            self.assertEqual(self._count(mode="shadow", outcome="proposed"), 1)


class ConsoleViewTests(TestCase):
    def test_console_builds_consolidated_context(self):
        from apps.platform_runtime.views_health_autopilot import health_autopilot_console

        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="op_health", email="op_health@example.com", password="x"
        )
        user.is_staff = True
        user.save(update_fields=["is_staff"])

        req = RequestFactory().get("/self-healing/")
        req.user = user
        with mock.patch(
            "apps.platform_runtime.views_health_autopilot.render",
            return_value=HttpResponse("ok"),
        ) as rndr:
            resp = health_autopilot_console(req)

        self.assertEqual(resp.status_code, 200)
        ctx = rndr.call_args.args[2]
        for key in (
            "proposals",
            "policies",
            "recent_log",
            "catalog",
            "ai_surfaces",
            "ai_min_confidence",
        ):
            self.assertIn(key, ctx)
        # Catalog surfaced and every kind reversible.
        self.assertTrue(ctx["catalog"])
        self.assertTrue(all(c["reversible"] for c in ctx["catalog"]))
