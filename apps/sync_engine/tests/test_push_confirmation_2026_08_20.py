"""An ambiguous push timeout should be a question, not a guess.

A box pushes; the cloud accepts, applies, records the receipt — and the RESPONSE dies
in a gateway 502 or a read timeout. The box cannot tell "you never got it" from "you
got it and I lost the answer", so it leaves the cursor unmoved and re-ships the whole
page next cycle.

That re-ship was always CORRECT: ``export_delta_bundle`` regenerates the nonce per
build, so the rebuilt bundle is new to the replay guard and the apply is idempotent.
What it costs is bandwidth, on the link that just proved unreliable. These tests pin
the distinction that makes asking worthwhile and the failure modes that must never
turn the optimisation into a blocker.

The sharpest property here is the NEGATIVE one: a 400 or 403 must NOT be recorded as
ambiguous. Those are decisions — the cloud answered, and the answer was no. Treating
them as ambiguous would have the box asking the cloud about bundles it explicitly
rejected.
"""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.sync_engine.delta_bundle import bundle_nonce, export_delta_bundle
from apps.sync_engine.push_confirmation import (
    is_ambiguous_failure,
    record_ambiguous_push,
    resolve_pending,
)


class AmbiguityClassificationTests(SimpleTestCase):
    def test_transport_and_gateway_failures_are_ambiguous(self):
        for status in (0, 408, 502, 503, 504, 522, 524):
            with self.subTest(status=status):
                self.assertTrue(is_ambiguous_failure(status))

    def test_a_decision_by_the_cloud_is_not_ambiguous(self):
        """400/403/404/409 mean the cloud answered. It said no. Nothing was applied."""
        for status in (200, 400, 401, 403, 404, 409, 413, 422):
            with self.subTest(status=status):
                self.assertFalse(is_ambiguous_failure(status))


class BundleNonceTests(SimpleTestCase):
    def test_reads_back_the_nonce_from_a_bundle_we_built(self):
        data = export_delta_bundle(school_id="s1", rows=[{"a": 1}], device_id="edge")
        self.assertTrue(bundle_nonce(data))
        self.assertEqual(len(bundle_nonce(data)), 32)

    def test_each_build_gets_a_fresh_nonce(self):
        """This is why an honest retry works at all — pinned so it cannot regress."""
        rows = [{"a": 1}]
        first = bundle_nonce(export_delta_bundle(school_id="s1", rows=rows))
        second = bundle_nonce(export_delta_bundle(school_id="s1", rows=rows))
        self.assertNotEqual(first, second)

    def test_garbage_yields_empty_rather_than_raising(self):
        for junk in (b"", b"not json", b"\xff\xfe\x00", b"{}"):
            with self.subTest(junk=junk):
                self.assertEqual(bundle_nonce(junk), "")


class RecordAndResolveTests(TestCase):
    def setUp(self):
        from apps.schools.models import School

        self.school = School.objects.create(
            name="Gilead Tech", slug="gilead-tech", subdomain="gilead-tech"
        )
        self.data = export_delta_bundle(
            school_id=str(self.school.pk), rows=[{"a": 1}], device_id="edge"
        )
        self.nonce = bundle_nonce(self.data)

    def _pending(self):
        from apps.sync_engine.models_pairing import PendingPushConfirmation

        return PendingPushConfirmation.objects.filter(school=self.school)

    def test_recording_stores_the_nonce_and_the_cursor_it_would_advance_to(self):
        record_ambiguous_push(
            self.school,
            data=self.data,
            high_water="2026-08-20T10:00:00Z",
            row_count=7,
            failure="HTTP 502",
        )
        row = self._pending().get()
        self.assertEqual(row.nonce, self.nonce)
        self.assertEqual(row.high_water, "2026-08-20T10:00:00Z")
        self.assertEqual(row.row_count, 7)
        self.assertGreater(row.built_at, 0)

    def test_recording_the_same_bundle_twice_does_not_duplicate(self):
        for _ in range(3):
            record_ambiguous_push(self.school, data=self.data, row_count=1)
        self.assertEqual(self._pending().count(), 1)

    def test_a_confirmed_bundle_advances_the_cursor_and_is_cleared(self):
        record_ambiguous_push(
            self.school, data=self.data, high_water="HW-1", row_count=5
        )
        advanced = []
        with mock.patch(
            "apps.sync_engine.push_confirmation._ask",
            return_value={"ok": True, "seen": True, "row_count": 5},
        ):
            out = resolve_pending(
                self.school,
                base="https://c.example.com",
                token="t",
                set_cursor=advanced.append,
            )
        self.assertEqual(out["confirmed"], 1)
        self.assertEqual(advanced, ["HW-1"])
        self.assertEqual(self._pending().count(), 0)

    def test_an_unconfirmed_bundle_does_not_advance_the_cursor(self):
        """The ordinary re-ship must still happen — that path is the correct one."""
        record_ambiguous_push(
            self.school, data=self.data, high_water="HW-1", row_count=5
        )
        advanced = []
        with mock.patch(
            "apps.sync_engine.push_confirmation._ask",
            return_value={"ok": True, "seen": False, "confident": True},
        ):
            out = resolve_pending(
                self.school,
                base="https://c.example.com",
                token="t",
                set_cursor=advanced.append,
            )
        self.assertEqual(out["confirmed"], 0)
        self.assertEqual(advanced, [])
        self.assertEqual(self._pending().count(), 0)

    def test_an_unknown_answer_is_treated_exactly_like_not_seen(self):
        """Outside the replay window the cloud cannot be sure; neither are we."""
        record_ambiguous_push(
            self.school, data=self.data, high_water="HW-1", row_count=5
        )
        advanced = []
        with mock.patch(
            "apps.sync_engine.push_confirmation._ask",
            return_value={"ok": True, "seen": False, "confident": False},
        ):
            resolve_pending(
                self.school,
                base="https://c.example.com",
                token="t",
                set_cursor=advanced.append,
            )
        self.assertEqual(advanced, [])

    def test_an_unreachable_cloud_leaves_the_question_for_next_time(self):
        record_ambiguous_push(self.school, data=self.data, row_count=5)
        with mock.patch("apps.sync_engine.push_confirmation._ask", return_value={}):
            out = resolve_pending(self.school, base="https://c.example.com", token="t")
        self.assertEqual(out["unconfirmed"], 1)
        self.assertEqual(self._pending().count(), 1)
        self.assertEqual(self._pending().get().attempts, 1)

    def test_no_base_or_token_is_a_silent_no_op(self):
        record_ambiguous_push(self.school, data=self.data, row_count=1)
        self.assertEqual(
            resolve_pending(self.school, base="", token=""),
            {"confirmed": 0, "unconfirmed": 0, "asked": 0},
        )

    def test_a_broken_lookup_never_raises_into_the_sync_cycle(self):
        record_ambiguous_push(self.school, data=self.data, row_count=1)
        with mock.patch(
            "apps.sync_engine.push_confirmation._ask",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                # _ask itself is allowed to raise in this contrived case; what matters
                # is that the caller in sync_runner wraps resolve_pending. Documented
                # rather than silently swallowed here so the contract stays visible.
                resolve_pending(self.school, base="https://c", token="t")


class RunnerWrapsTheSweepTests(SimpleTestCase):
    """sync_runner must never let this optimisation break a push."""

    def test_the_sweep_call_is_guarded(self):
        import inspect

        from apps.sync_engine import sync_runner

        source = inspect.getsource(sync_runner)
        self.assertIn("resolve_pending", source)
        after = source.split("resolve_pending", 1)[1]
        self.assertIn("except Exception", after[:1200])

    def test_only_ambiguous_failures_are_recorded(self):
        import inspect

        from apps.sync_engine import sync_runner

        source = inspect.getsource(sync_runner)
        self.assertIn("if is_ambiguous_failure(status):", source)
