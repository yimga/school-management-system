"""Graceful degradation when feedback tables are not migrated."""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.feedback.db_readiness import (
    clear_feedback_schema_ready_cache,
    feedback_schema_ready,
    open_feature_request_count,
)
from apps.feedback.services import generate_you_said_we_did_items, top_pain_points


class FeedbackDbReadinessTests(SimpleTestCase):
    def tearDown(self):
        clear_feedback_schema_ready_cache()

    def test_schema_ready_false_when_tables_missing(self):
        with patch(
            "apps.feedback.db_readiness.connection.introspection.table_names",
            return_value=["auth_user"],
        ):
            clear_feedback_schema_ready_cache()
            self.assertFalse(feedback_schema_ready())

    def test_top_pain_points_empty_when_tables_missing(self):
        with patch("apps.feedback.services.feedback_schema_ready", return_value=False):
            self.assertEqual(top_pain_points(), [])

    def test_open_feature_count_zero_when_tables_missing(self):
        with patch("apps.feedback.db_readiness.feedback_schema_ready", return_value=False):
            self.assertEqual(open_feature_request_count(), 0)

    def test_you_said_we_did_empty_when_tables_missing(self):
        with patch("apps.feedback.services.feedback_schema_ready", return_value=False):
            self.assertEqual(generate_you_said_we_did_items(None), [])

    def test_module_sentiment_summary_empty_when_tables_missing(self):
        with patch("apps.feedback.services.feedback_schema_ready", return_value=False):
            from apps.feedback.services import module_sentiment_summary

            self.assertEqual(module_sentiment_summary(), [])


