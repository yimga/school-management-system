"""An empty Redis queue is depth 0, not a broken health probe.

Observed on a live self-host box (`deploy/selfhost/docker-compose.yml`, broker
``redis://valkey:6379/1``) whose worker was demonstrably healthy —
``celery_workers: {"status": "ok", "workers": ["celery@..."]}`` — yet::

    "celery_queue_depth": {
        "status": "unavailable",
        "error": "Channel.queue_declare: (404) NOT_FOUND - no queue 'celery' in vhost '1'"
    }

kombu's virtual transports back a queue with a plain Redis key, so a queue with
no messages does not exist as a key and a passive declare raises NOT_FOUND. A
working worker keeps the queue empty, so the "failure" was permanent on a
healthy deployment — and a health endpoint that always shows an error is one
operators stop reading.
"""

from django.test import SimpleTestCase

from apps.observability.views import _is_absent_queue_error

# Verbatim from the live box, including the Redis DB index rendered as a vhost.
LIVE_ERROR = (
    "Channel.queue_declare: (404) NOT_FOUND - no queue 'celery' in vhost '1'"
)


class ChannelError(Exception):
    """Stand-in for kombu's ChannelError, which carries a string ``code``."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class AbsentQueueDetectionTests(SimpleTestCase):
    def test_the_exact_live_error_is_recognised_as_an_empty_queue(self):
        self.assertTrue(
            _is_absent_queue_error(ChannelError(LIVE_ERROR, code="404"), "celery")
        )

    def test_recognised_without_a_code_attribute(self):
        # Not every transport sets `.code`; the message alone must be enough.
        self.assertTrue(_is_absent_queue_error(Exception(LIVE_ERROR), "celery"))

    def test_a_custom_default_queue_name_is_honoured(self):
        err = "Channel.queue_declare: (404) NOT_FOUND - no queue 'rmc_main' in vhost '1'"
        self.assertTrue(_is_absent_queue_error(Exception(err), "rmc_main"))

    def test_a_missing_OTHER_queue_is_not_treated_as_our_queue_being_empty(self):
        # Narrowness matters: reporting depth 0 because some unrelated queue is
        # missing would hide a real misconfiguration.
        self.assertFalse(_is_absent_queue_error(Exception(LIVE_ERROR), "rmc_main"))

    def test_genuine_broker_faults_still_surface(self):
        for message in (
            "Error 111 connecting to valkey:6379. Connection refused.",
            "[Errno 110] Connection timed out",
            "ACCESS_REFUSED - Login was refused using authentication mechanism PLAIN",
            "AUTH failed: invalid password",
        ):
            with self.subTest(message=message):
                self.assertFalse(_is_absent_queue_error(Exception(message), "celery"))

    def test_a_404_that_is_not_about_a_queue_is_not_swallowed(self):
        # A 404 mentioning something else must not be read as "queue is empty"
        # merely because the code matches.
        err = ChannelError("NOT_FOUND - no exchange 'amq.topic'", code="404")
        self.assertFalse(_is_absent_queue_error(err, "celery"))


class QueueDepthProbeReportsZeroTests(SimpleTestCase):
    """The probe itself, driven through a channel that behaves like Valkey."""

    def _probe_with(self, declare):
        from unittest import mock

        from apps.observability import views

        channel = mock.Mock()
        channel.queue_declare.side_effect = declare
        conn = mock.MagicMock()
        conn.default_channel = channel
        celery_app = mock.Mock()
        celery_app.conf.task_default_queue = "celery"
        celery_app.connection.return_value = conn

        with mock.patch.dict(
            "sys.modules", {"config.celery": mock.Mock(app=celery_app)}
        ), self.settings(CELERY_BROKER_URL="redis://valkey:6379/1"):
            return views._check_celery_queue_depth()

    def test_empty_valkey_queue_reports_ok_depth_zero(self):
        def declare(*args, **kwargs):
            raise ChannelError(LIVE_ERROR, code="404")

        result = self._probe_with(declare)
        self.assertEqual(result.get("status"), "ok", msg=result)
        self.assertEqual(result.get("depth"), 0, msg=result)
        self.assertNotIn("error", result)

    def test_a_real_broker_failure_still_reports_unavailable(self):
        def declare(*args, **kwargs):
            raise OSError("Error 111 connecting to valkey:6379. Connection refused.")

        result = self._probe_with(declare)
        self.assertEqual(result.get("status"), "unavailable", msg=result)
        self.assertIn("error", result)

    def test_a_queue_with_messages_still_reports_its_depth(self):
        from unittest import mock

        def declare(*args, **kwargs):
            return mock.Mock(message_count=7)

        result = self._probe_with(declare)
        self.assertEqual(result.get("depth"), 7, msg=result)
        self.assertEqual(result.get("status"), "ok", msg=result)
