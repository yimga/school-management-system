"""Canvas-first Experience builder — #rollout proof-before-publish gate (Phase 3).

No DB: the approval store is session-backed and the gate logic is pure given an
explicit values dict. Fingerprint invalidation (approval dies when the draft
changes) and enforce-vs-advisory behaviour are the load-bearing invariants.
"""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.studio_os.experience_regions import STUDIO_EXPERIENCE_REGIONS, resolve_selected_region
from apps.studio_os.experience_rollout import (
    approve_region,
    build_rollout_status,
    compute_region_fingerprint,
    get_region_approvals,
    reset_region_approval,
    rollout_enforcement_mode,
    rollout_publish_block,
    rollout_summary,
)


class _Session(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.modified = False


class _Req:
    def __init__(self, session=None, school="tenant"):
        self.session = session if session is not None else _Session()
        self.school = school


HEADER = resolve_selected_region("header")


def _approve_all(req, values):
    for region in STUDIO_EXPERIENCE_REGIONS:
        fp = compute_region_fingerprint(region, values)
        approve_region(req, region["key"], fp)


class FingerprintTests(SimpleTestCase):
    def test_fingerprint_is_stable(self):
        v = {"primary_color": "#2fbcff", "accent_color": "#3edb8f"}
        self.assertEqual(
            compute_region_fingerprint(HEADER, v),
            compute_region_fingerprint(HEADER, dict(v)),
        )

    def test_fingerprint_changes_with_value(self):
        a = compute_region_fingerprint(HEADER, {"primary_color": "#111111"})
        b = compute_region_fingerprint(HEADER, {"primary_color": "#222222"})
        self.assertNotEqual(a, b)

    def test_fingerprint_is_16_hex(self):
        fp = compute_region_fingerprint(HEADER, {})
        self.assertEqual(len(fp), 16)
        int(fp, 16)  # raises if not hex

    def test_none_and_missing_are_equivalent(self):
        self.assertEqual(
            compute_region_fingerprint(HEADER, {"primary_color": None}),
            compute_region_fingerprint(HEADER, {}),
        )


class ApprovalStoreTests(SimpleTestCase):
    def test_approve_and_read_back(self):
        req = _Req()
        approve_region(req, "header", "abc123", actor="ann", timestamp="2026-07-10 09:00")
        approvals = get_region_approvals(req)
        self.assertIn("header", approvals)
        self.assertEqual(approvals["header"]["fingerprint"], "abc123")
        self.assertTrue(req.session.modified)

    def test_reset_removes_approval(self):
        req = _Req()
        approve_region(req, "header", "abc123")
        reset_region_approval(req, "header")
        self.assertNotIn("header", get_region_approvals(req))

    def test_malformed_session_is_ignored(self):
        req = _Req(session=_Session({"studio_experience_region_approvals": "garbage"}))
        self.assertEqual(get_region_approvals(req), {})


class RolloutStatusTests(SimpleTestCase):
    def test_pending_when_no_approval(self):
        req = _Req()
        rows = build_rollout_status(req, {})
        header = next(r for r in rows if r["key"] == "header")
        self.assertFalse(header["approved"])
        self.assertFalse(header["stale"])

    def test_approved_when_fingerprint_matches(self):
        req = _Req()
        values = {"primary_color": "#2fbcff"}
        approve_region(req, "header", compute_region_fingerprint(HEADER, values))
        rows = build_rollout_status(req, values)
        header = next(r for r in rows if r["key"] == "header")
        self.assertTrue(header["approved"])
        self.assertFalse(header["stale"])

    def test_stale_when_values_drift_after_approval(self):
        req = _Req()
        approve_region(
            req, "header", compute_region_fingerprint(HEADER, {"primary_color": "#111111"})
        )
        # Draft changed underneath the approval -> stale, not approved.
        rows = build_rollout_status(req, {"primary_color": "#999999"})
        header = next(r for r in rows if r["key"] == "header")
        self.assertFalse(header["approved"])
        self.assertTrue(header["stale"])

    def test_summary_counts(self):
        req = _Req()
        _approve_all(req, {})
        summary = rollout_summary(req, {})
        self.assertEqual(summary["approved_count"], summary["total"])
        self.assertTrue(summary["all_approved"])
        self.assertEqual(summary["pending_count"], 0)


class EnforcementModeTests(SimpleTestCase):
    @override_settings(STUDIO_EXPERIENCE_ROLLOUT_ENFORCEMENT="enforce")
    def test_mode_enforce(self):
        self.assertEqual(rollout_enforcement_mode(), "enforce")

    @override_settings(STUDIO_EXPERIENCE_ROLLOUT_ENFORCEMENT="advisory")
    def test_mode_advisory(self):
        self.assertEqual(rollout_enforcement_mode(), "advisory")

    @override_settings(STUDIO_EXPERIENCE_ROLLOUT_ENFORCEMENT="banana")
    def test_unknown_mode_is_advisory(self):
        self.assertEqual(rollout_enforcement_mode(), "advisory")


class PublishBlockTests(SimpleTestCase):
    @override_settings(STUDIO_EXPERIENCE_ROLLOUT_ENFORCEMENT="advisory")
    def test_advisory_never_blocks(self):
        req = _Req()
        self.assertEqual(rollout_publish_block(req, {}), [])

    @override_settings(STUDIO_EXPERIENCE_ROLLOUT_ENFORCEMENT="enforce")
    def test_enforce_blocks_when_unapproved(self):
        req = _Req()
        errors = rollout_publish_block(req, {})
        self.assertTrue(errors)
        self.assertIn("approve every region", errors[0])

    @override_settings(STUDIO_EXPERIENCE_ROLLOUT_ENFORCEMENT="enforce")
    def test_enforce_passes_when_all_approved(self):
        req = _Req()
        values = {"primary_color": "#2fbcff"}
        _approve_all(req, values)
        self.assertEqual(rollout_publish_block(req, values), [])

    @override_settings(STUDIO_EXPERIENCE_ROLLOUT_ENFORCEMENT="enforce")
    def test_enforce_blocks_again_after_draft_change(self):
        req = _Req()
        values = {"primary_color": "#2fbcff"}
        _approve_all(req, values)
        # Change the draft -> every approval goes stale -> blocked again.
        errors = rollout_publish_block(req, {"primary_color": "#000000"})
        self.assertTrue(errors)
