"""v4.00.36 — unit tests for apps.billing.tasks_ai_token_flush."""

from __future__ import annotations

from datetime import date as _date
from unittest import mock

from django.test import SimpleTestCase

from apps.billing import tasks_ai_token_flush as mod


class ParseKeyTests(SimpleTestCase):
    def test_well_formed_key_parses(self):
        result = mod._parse_key(
            "ai:metrics:2026-05-29:42:transcription:premium:premium_cost"
        )
        self.assertEqual(
            result, ("2026-05-29", "42", "transcription", "premium", "premium_cost")
        )

    def test_missing_prefix_returns_none(self):
        self.assertIsNone(mod._parse_key("metrics:2026-05-29:42:a:b:c"))

    def test_wrong_part_count_returns_none(self):
        self.assertIsNone(mod._parse_key("ai:metrics:2026-05-29:42:a:b"))
        self.assertIsNone(mod._parse_key("ai:metrics:2026-05-29:42:a:b:c:d"))

    def test_empty_returns_none(self):
        self.assertIsNone(mod._parse_key(""))
        self.assertIsNone(mod._parse_key(None))


class DateFromStrTests(SimpleTestCase):
    def test_valid(self):
        self.assertEqual(mod._date_from_str("2026-05-29"), _date(2026, 5, 29))

    def test_invalid_returns_none(self):
        self.assertIsNone(mod._date_from_str(""))
        self.assertIsNone(mod._date_from_str("2026-05"))
        self.assertIsNone(mod._date_from_str("not-a-date"))


class FlushAIMetricsBucketsTests(SimpleTestCase):
    def test_empty_keyspace_returns_zero_counts(self):
        with mock.patch.object(mod, "_iter_keys", return_value=[]):
            out = mod.flush_ai_metrics_buckets()
        self.assertEqual(out, {"keys_seen": 0, "flushed": 0, "skipped": 0})

    def test_malformed_key_skipped(self):
        with mock.patch.object(
            mod, "_iter_keys", return_value=["ai:metrics:bad"]
        ):
            out = mod.flush_ai_metrics_buckets()
        self.assertEqual(out["keys_seen"], 1)
        self.assertEqual(out["flushed"], 0)
        self.assertEqual(out["skipped"], 1)

    def test_unrouteable_global_key_dropped_silently(self):
        with mock.patch.object(
            mod, "_iter_keys",
            return_value=["ai:metrics:2026-05-29:global:nuance:standard:no_cost"],
        ), mock.patch("apps.billing.tasks_ai_token_flush.cache") as cache_mock:
            cache_mock.get.return_value = {"count": 5, "latency_sum": 100.0}
            out = mod.flush_ai_metrics_buckets()
        self.assertEqual(out["flushed"], 0)
        self.assertEqual(out["skipped"], 1)
        cache_mock.delete.assert_called_once()

    def test_routable_key_calls_record_and_deletes(self):
        with mock.patch.object(
            mod, "_iter_keys",
            return_value=["ai:metrics:2026-05-29:42:nuance:standard:no_cost"],
        ), mock.patch.object(
            mod, "_resolve_school", return_value=mock.Mock(pk=42)
        ), mock.patch("apps.billing.tasks_ai_token_flush.cache") as cache_mock, mock.patch(
            "apps.billing.models_metering.record"
        ) as record_mock:
            cache_mock.get.return_value = {"count": 7, "latency_sum": 250.0}
            out = mod.flush_ai_metrics_buckets()
        self.assertEqual(out["flushed"], 1)
        record_mock.assert_called_once()
        kwargs = record_mock.call_args.kwargs
        self.assertEqual(kwargs["delta"], 7)
        self.assertEqual(kwargs["day"], _date(2026, 5, 29))
        self.assertEqual(record_mock.call_args.args[1], "ai_invocations")
        cache_mock.delete.assert_called_once()

    def test_zero_count_bucket_skipped(self):
        with mock.patch.object(
            mod, "_iter_keys",
            return_value=["ai:metrics:2026-05-29:42:nuance:standard:no_cost"],
        ), mock.patch("apps.billing.tasks_ai_token_flush.cache") as cache_mock:
            cache_mock.get.return_value = {"count": 0}
            out = mod.flush_ai_metrics_buckets()
        self.assertEqual(out["flushed"], 0)
        self.assertEqual(out["skipped"], 1)
