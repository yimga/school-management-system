import json

from django.test import SimpleTestCase

from services.ai.support_sse import format_sse_frame
from services.ai.support_stream import iter_support_assistant_sse


class SupportSseFormatTests(SimpleTestCase):
    def test_format_sse_frame_emits_event_and_data(self):
        raw = format_sse_frame(
            event="delta",
            payload={"text": "hello"},
            event_id="1",
        ).decode("utf-8")
        self.assertIn("event: delta", raw)
        self.assertIn("id: 1", raw)
        data_line = [line for line in raw.split("\n") if line.startswith("data:")][0]
        payload = json.loads(data_line.replace("data: ", "", 1))
        self.assertEqual(payload["text"], "hello")

    def test_stream_empty_query_emits_error_frame(self):
        frames = list(
            iter_support_assistant_sse(
                user_profile=None,
                active_url="/kb/",
                user_query="",
            )
        )
        self.assertTrue(frames)
        raw = frames[0].decode("utf-8")
        self.assertIn("event: error", raw)
        payload = json.loads(
            [line for line in raw.split("\n") if line.startswith("data:")][0].replace("data: ", "", 1)
        )
        self.assertEqual(payload.get("error"), "query required")
