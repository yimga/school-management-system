"""Tests for the Platform Health connective tissue (2026-06-03).

DB-free by design: ``SimpleTestCase`` + mocks throughout, so they are robust to
the Windows in-memory-SQLite lock artifact noted in repo memory. Views are
exercised via ``RequestFactory`` with fabricated user objects (no DB user rows),
and the workflow tracker is patched so ``begin_run`` never touches the ORM.

See docs/PLATFORM_HEALTH_CONNECTIVE_TISSUE_2026_06_03.md.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.platform_runtime import platform_health as ph
from apps.platform_runtime import views_platform_health as vph
from apps.schools.feature_gap_register import FeatureRow


def _shipped(slug, **kw):
    return FeatureRow(feature_slug=slug, label=slug.upper(), capability_domain="ai", status="shipped", **kw)


class FeatureGapBrokenProofsTests(SimpleTestCase):
    def _patch_features(self, rows):
        return mock.patch(
            "apps.schools.feature_gap_register.iter_features",
            return_value=tuple(rows),
        )

    def test_unresolvable_route_is_broken(self):
        with self._patch_features([_shipped("x", proof_route_name="totally_missing_route_zzz")]):
            broken = ph.feature_gap_broken_proofs()
        self.assertEqual([b.feature_slug for b in broken], ["x"])
        self.assertEqual(broken[0].proof_kind, "route")

    def test_resolvable_route_not_broken(self):
        # This route is registered by this very wave, so it must reverse.
        with self._patch_features([_shipped("ok", proof_route_name="platform_runtime:platform_health_center")]):
            self.assertEqual(ph.feature_gap_broken_proofs(), [])

    def test_bad_model_broken_good_model_ok(self):
        rows = [
            _shipped("bad", proof_model="nope.DoesNotExist"),
            _shipped("good", proof_model="schools.School"),
        ]
        with self._patch_features(rows):
            broken = ph.feature_gap_broken_proofs()
        self.assertEqual([b.feature_slug for b in broken], ["bad"])
        self.assertEqual(broken[0].proof_kind, "model")

    def test_planned_rows_ignored(self):
        row = FeatureRow(
            feature_slug="p", label="P", capability_domain="ai",
            status="planned", proof_route_name="totally_missing_route_zzz",
        )
        with self._patch_features([row]):
            self.assertEqual(ph.feature_gap_broken_proofs(), [])

    def test_command_only_proof_not_flagged(self):
        # Rows whose only proof is a mgmt command / CI gate aren't route-resolvable
        # in-request and must NOT be reported as broken here.
        with self._patch_features([_shipped("cmd", proof_management_command="seed_x")]):
            self.assertEqual(ph.feature_gap_broken_proofs(), [])


class BacklogSlaBreachesTests(SimpleTestCase):
    def test_no_snapshot_returns_empty_unavailable(self):
        with mock.patch("django.core.cache.cache.get", return_value=None):
            breaches, available = ph.backlog_sla_breaches()
        self.assertEqual(breaches, [])
        self.assertFalse(available)

    def test_breached_items_parsed_from_json_string(self):
        snapshot = {
            "items": [
                {
                    "id": "a", "title": "A", "category": "verification_gates",
                    "sla_waiting_breached": True, "days_in_waiting": 30,
                    "sla_waiting_max_days": 21, "doc_href": "docs/x.md",
                    "action_hint": "python scripts/x.py",
                },
                {
                    "id": "b", "title": "B",
                    "sla_ready_attention_breached": True,
                    "days_in_ready_attention": 60, "sla_ready_attention_max_days": 45,
                },
                {"id": "c", "title": "C"},  # not breached
            ]
        }
        with mock.patch("django.core.cache.cache.get", return_value=json.dumps(snapshot)):
            breaches, available = ph.backlog_sla_breaches()
        self.assertTrue(available)
        self.assertEqual(sorted(b.item_id for b in breaches), ["a", "b"])
        by_id = {b.item_id: b for b in breaches}
        self.assertEqual(by_id["a"].column, "waiting")
        self.assertEqual(by_id["a"].days_in_column, 30)
        self.assertEqual(by_id["b"].column, "ready_attention")

    def test_dict_snapshot_also_supported(self):
        snapshot = {"items": [{"id": "z", "title": "Z", "sla_waiting_breached": True,
                               "days_in_waiting": 99, "sla_waiting_max_days": 21}]}
        with mock.patch("django.core.cache.cache.get", return_value=snapshot):
            breaches, available = ph.backlog_sla_breaches()
        self.assertTrue(available)
        self.assertEqual([b.item_id for b in breaches], ["z"])


class SummaryLevelTests(SimpleTestCase):
    def _patch(self, broken, breaches):
        return (
            mock.patch.object(ph, "feature_gap_broken_proofs", return_value=broken),
            mock.patch.object(ph, "backlog_sla_breaches", return_value=(breaches, True)),
        )

    def test_critical_when_proof_broken(self):
        p1, p2 = self._patch([ph.BrokenProof("x", "X", "ai", "route", "r", "e")], [])
        with p1, p2:
            s = ph.platform_health_summary()
        self.assertEqual(s["level"], ph.LEVEL_CRITICAL)
        self.assertEqual(s["count"], 1)

    def test_warning_when_only_sla_breach(self):
        p1, p2 = self._patch([], [ph.BacklogBreach("a", "A", "c", "waiting", 30, 21)])
        with p1, p2:
            s = ph.platform_health_summary()
        self.assertEqual(s["level"], ph.LEVEL_WARNING)

    def test_success_when_clean(self):
        p1, p2 = self._patch([], [])
        with p1, p2:
            s = ph.platform_health_summary()
        self.assertEqual(s["level"], ph.LEVEL_SUCCESS)
        self.assertEqual(s["count"], 0)


class BadgeViewTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _req(self, staff):
        r = self.rf.get("/platform-runtime/platform-health/badge/")
        r.user = SimpleNamespace(is_authenticated=True, is_staff=staff, id=1)
        return r

    def test_non_staff_gets_empty_success(self):
        resp = vph.platform_health_badge(self._req(False))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content), {"count": 0, "level": "success", "dot": False})

    def test_staff_reflects_summary(self):
        summary = {
            "count": 2, "level": "critical", "feature_gap_broken": 1,
            "backlog_breaches": 1, "backlog_snapshot_available": True,
        }
        with mock.patch.object(vph, "platform_health_summary", return_value=summary):
            resp = vph.platform_health_badge(self._req(True))
        data = json.loads(resp.content)
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["level"], "critical")
        self.assertTrue(data["dot"])


class SummaryCacheTests(SimpleTestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        ph.bust_summary_cache()

    def test_use_cache_serves_stale_within_ttl(self):
        # First call (use_cache) computes from the patched values and caches.
        with mock.patch.object(ph, "feature_gap_broken_proofs", return_value=[
            ph.BrokenProof("x", "X", "ai", "route", "r", "e")
        ]), mock.patch.object(ph, "backlog_sla_breaches", return_value=([], True)):
            first = ph.platform_health_summary(use_cache=True)
        self.assertEqual(first["count"], 1)
        # Now the underlying data "changes" but the cache should still serve old.
        with mock.patch.object(ph, "feature_gap_broken_proofs", return_value=[]), \
                mock.patch.object(ph, "backlog_sla_breaches", return_value=([], True)):
            cached = ph.platform_health_summary(use_cache=True)
            fresh = ph.platform_health_summary(use_cache=False)
        self.assertEqual(cached["count"], 1)   # stale (cached)
        self.assertEqual(fresh["count"], 0)    # fresh path bypasses cache

    def test_bust_clears_cache(self):
        with mock.patch.object(ph, "feature_gap_broken_proofs", return_value=[
            ph.BrokenProof("x", "X", "ai", "route", "r", "e")
        ]), mock.patch.object(ph, "backlog_sla_breaches", return_value=([], True)):
            ph.platform_health_summary(use_cache=True)
        ph.bust_summary_cache()
        with mock.patch.object(ph, "feature_gap_broken_proofs", return_value=[]), \
                mock.patch.object(ph, "backlog_sla_breaches", return_value=([], True)):
            after = ph.platform_health_summary(use_cache=True)
        self.assertEqual(after["count"], 0)


class RecheckViewTests(SimpleTestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()  # isolate throttle + summary cache between tests
        self.rf = RequestFactory()

    def _post(self, slug, staff=True):
        r = self.rf.post("/platform-runtime/platform-health/recheck/", data={"feature_slug": slug})
        r.user = SimpleNamespace(is_authenticated=True, is_staff=staff, id=1)
        r.META["HTTP_X_REQUESTED_WITH"] = "XMLHttpRequest"  # force JSON branch
        return r

    def _patch_tracker(self):
        return (
            mock.patch("apps.platform_runtime.workflow_tracker.begin_run", return_value=None),
            mock.patch("apps.platform_runtime.workflow_tracker.finalize_run"),
            mock.patch("apps.platform_runtime.workflow_tracker.push_workflow_run"),
            mock.patch("apps.platform_runtime.workflow_tracker.pop_workflow_run"),
        )

    def test_non_staff_403(self):
        resp = vph.platform_health_recheck(self._post("x", staff=False))
        self.assertEqual(resp.status_code, 403)

    def test_missing_slug_400(self):
        resp = vph.platform_health_recheck(self._post(""))
        self.assertEqual(resp.status_code, 400)

    def test_unknown_feature_404(self):
        with mock.patch("apps.schools.feature_gap_register.get_feature", return_value=None):
            resp = vph.platform_health_recheck(self._post("nope"))
        self.assertEqual(resp.status_code, 404)

    def test_not_shipped_400(self):
        feat = FeatureRow(feature_slug="p", label="P", capability_domain="ai", status="planned")
        with mock.patch("apps.schools.feature_gap_register.get_feature", return_value=feat):
            resp = vph.platform_health_recheck(self._post("p"))
        self.assertEqual(resp.status_code, 400)

    def test_resolved_true_when_not_broken(self):
        feat = _shipped("ok", proof_route_name="platform_runtime:platform_health_center")
        b1, b2, b3, b4 = self._patch_tracker()
        with mock.patch("apps.schools.feature_gap_register.get_feature", return_value=feat), \
                mock.patch.object(vph, "feature_gap_broken_proofs", return_value=[]), \
                b1, b2, b3, b4:
            resp = vph.platform_health_recheck(self._post("ok"))
        data = json.loads(resp.content)
        self.assertTrue(data["ok"])
        self.assertTrue(data["resolved"])

    def test_resolved_false_when_broken(self):
        feat = _shipped("bad", proof_route_name="missing_zzz")
        broken = [ph.BrokenProof("bad", "BAD", "ai", "route", "missing_zzz", "no reverse")]
        b1, b2, b3, b4 = self._patch_tracker()
        with mock.patch("apps.schools.feature_gap_register.get_feature", return_value=feat), \
                mock.patch.object(vph, "feature_gap_broken_proofs", return_value=broken), \
                b1, b2, b3, b4:
            resp = vph.platform_health_recheck(self._post("bad"))
        data = json.loads(resp.content)
        self.assertTrue(data["ok"])
        self.assertFalse(data["resolved"])
        self.assertIn("no reverse", data["detail"])

    def test_second_recheck_is_throttled(self):
        feat = _shipped("ok", proof_route_name="platform_runtime:platform_health_center")
        b1, b2, b3, b4 = self._patch_tracker()
        with mock.patch("apps.schools.feature_gap_register.get_feature", return_value=feat), \
                mock.patch.object(vph, "feature_gap_broken_proofs", return_value=[]), \
                b1, b2, b3, b4:
            first = vph.platform_health_recheck(self._post("ok"))
            second = vph.platform_health_recheck(self._post("ok"))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(json.loads(second.content)["reason"], "throttled")


class DockWiringTests(SimpleTestCase):
    def test_slot_registered_as_external_on_manager(self):
        from apps.assist_dock.registry import SURFACE_MANAGER, get_slot

        slot = get_slot("platform-health")
        self.assertIsNotNone(slot)
        self.assertEqual(slot.source, "external")
        self.assertIn(SURFACE_MANAGER, slot.surfaces)
        self.assertTrue(slot.href)

    def test_badge_resolver_registered(self):
        from apps.assist_dock.badges import get_badge_resolver

        self.assertIsNotNone(get_badge_resolver("platform-health"))

    def test_chip_href_matches_manager_reverse(self):
        # The chip href is a literal path; assert it matches the real reverse on
        # the manager urlconf so a remount can't silently 404 the chip.
        from django.urls import reverse

        from apps.assist_dock.registry import get_slot

        slot = get_slot("platform-health")
        expected = reverse(
            "platform_runtime:platform_health_center", urlconf="config.manager_urls"
        )
        self.assertEqual(slot.href, expected)

    def test_badge_resolver_none_for_non_staff(self):
        from apps.assist_dock.default_badges import platform_health_badge_resolver
        from apps.assist_dock.registry import get_slot

        req = RequestFactory().get("/")
        req.user = SimpleNamespace(is_authenticated=True, is_staff=False, pk=1)
        result = platform_health_badge_resolver(req, slot=get_slot("platform-health"), page_path="/")
        self.assertIsNone(result)

    def test_badge_resolver_paints_pill_for_staff_with_problems(self):
        from apps.assist_dock.default_badges import platform_health_badge_resolver
        from apps.assist_dock.registry import get_slot

        req = RequestFactory().get("/")
        req.user = SimpleNamespace(is_authenticated=True, is_staff=True, pk=1)
        summary = {
            "count": 3, "level": ph.LEVEL_CRITICAL, "feature_gap_broken": 2,
            "backlog_breaches": 1, "backlog_snapshot_available": True,
        }
        with mock.patch(
            "apps.platform_runtime.platform_health.platform_health_summary",
            return_value=summary,
        ):
            snap = platform_health_badge_resolver(req, slot=get_slot("platform-health"), page_path="/")
        self.assertIsNotNone(snap)
        self.assertEqual(snap.count, 3)
        self.assertEqual(snap.level, "critical")

    def test_badge_resolver_silent_when_healthy(self):
        from apps.assist_dock.default_badges import platform_health_badge_resolver
        from apps.assist_dock.registry import get_slot

        req = RequestFactory().get("/")
        req.user = SimpleNamespace(is_authenticated=True, is_staff=True, pk=1)
        summary = {
            "count": 0, "level": ph.LEVEL_SUCCESS, "feature_gap_broken": 0,
            "backlog_breaches": 0, "backlog_snapshot_available": True,
        }
        with mock.patch(
            "apps.platform_runtime.platform_health.platform_health_summary",
            return_value=summary,
        ):
            snap = platform_health_badge_resolver(req, slot=get_slot("platform-health"), page_path="/")
        self.assertIsNone(snap)
