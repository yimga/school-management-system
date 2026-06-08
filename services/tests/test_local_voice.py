import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from services.local_voice import LocalVoiceError, synthesize, transcribe


class _Response:
    def __init__(self, body, content_type):
        self.body = body
        self.headers = MagicMock()
        self.headers.get_content_type.return_value = content_type

    def read(self, _limit=None):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


@override_settings(
    LOCAL_VOICE_ENABLED=True,
    LOCAL_VOICE_STT_ENDPOINT="http://voice.lan/stt",
    LOCAL_VOICE_TTS_ENDPOINT="http://voice.lan/tts",
    LOCAL_VOICE_ALLOWED_HOSTS=["voice.lan"],
    LOCAL_VOICE_LANGUAGES=["en"],
    LOCAL_VOICE_MAX_AUDIO_BYTES=100,
    LOCAL_VOICE_MAX_TRANSCRIPT_CHARS=100,
    LOCAL_VOICE_MAX_TTS_CHARS=100,
    LOCAL_VOICE_MAX_TTS_BYTES=100,
)
class LocalVoiceServiceTests(SimpleTestCase):
    @patch("services.local_voice._open")
    def test_transcribe_uses_configured_endpoint(self, open_mock):
        open_mock.return_value = _Response(
            json.dumps({"text": "hello"}).encode(), "application/json"
        )
        self.assertEqual(
            transcribe(b"audio", content_type="audio/webm", language="en"),
            "hello",
        )
        request = open_mock.call_args.args[0]
        self.assertEqual(request.full_url, "http://voice.lan/stt")

    @patch("services.local_voice._open")
    def test_synthesize_accepts_only_audio(self, open_mock):
        open_mock.return_value = _Response(b"wave", "audio/wav")
        result = synthesize("hello", language="en")
        self.assertEqual(result.body, b"wave")

    @override_settings(LOCAL_VOICE_ALLOWED_HOSTS=["different.lan"])
    def test_endpoint_host_must_be_allowlisted(self):
        with self.assertRaises(LocalVoiceError):
            transcribe(b"audio", content_type="audio/webm", language="en")

    def test_payload_caps_fail_before_network(self):
        with self.assertRaises(LocalVoiceError):
            transcribe(b"x" * 101, content_type="audio/webm", language="en")
