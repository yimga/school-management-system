from django.test import SimpleTestCase

from apps.observability.logging_context import (
    RequestContextFilter,
    clear_request_logging_context,
    set_request_logging_context,
)


class LoggingContextHelperTests(SimpleTestCase):
    def test_clear_request_logging_context_resets_values(self):
        set_request_logging_context("req-1", "tenant-1", "user-1")
        clear_request_logging_context()

        record = type("Record", (), {})()
        RequestContextFilter().filter(record)

        self.assertEqual(record.request_id, "-")
        self.assertEqual(record.tenant_id, "-")
        self.assertEqual(record.user_id, "-")
