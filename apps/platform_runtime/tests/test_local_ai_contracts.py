import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.core.cache import cache

from apps.platform_runtime.browser_inference import (
    BrowserInferenceConfigurationError,
    browser_inference_public_config,
    validate_browser_model_pack,
)
from apps.platform_runtime.views_local_ai import (
    browser_inference_config_view,
    local_voice_synthesize_view,
    local_voice_transcribe_view,
)
from services.local_voice import LocalVoiceError, SpeechAudio, allowed_language


def _valid_pack():
    return {
        "schema_version": 1,
        "pack_id": "test-pack",
        "staged": True,
        "runtime": {
            "url": "/static/browser/runtime.js",
            "sha256": "b" * 64,
            "size_bytes": 50,
        },
        "model": {
            "model_id": "test/model",
            "task": "text-generation",
            "revision": "immutable-revision",
            "assets": [
                {
                    "url": "/static/browser/model.onnx",
                    "sha256": "a" * 64,
                    "size_bytes": 100,
                }
            ],
        },
        "limits": {"max_input_chars": 1000, "max_new_tokens": 128},
        "allowed_use": ["reversible_draft", "synthetic_data"],
    }


class BrowserInferenceContractTests(SimpleTestCase):
    def test_valid_pack_is_normalized(self):
        result = validate_browser_model_pack(_valid_pack())
        self.assertEqual(result["model"]["revision"], "immutable-revision")

    def test_remote_runtime_is_rejected(self):
        pack = _valid_pack()
        pack["runtime"]["url"] = "https://cdn.example/runtime.js"
        with self.assertRaises(BrowserInferenceConfigurationError):
            validate_browser_model_pack(pack)

    def test_unpinned_asset_is_rejected(self):
        pack = _valid_pack()
        pack["model"]["assets"][0]["sha256"] = ""
        with self.assertRaises(BrowserInferenceConfigurationError):
            validate_browser_model_pack(pack)

    @override_settings(BROWSER_AI_ENABLED=False)
    def test_disabled_config_fails_closed(self):
        self.assertEqual(
            browser_inference_public_config(),
            {"available": False, "reason": "disabled"},
        )


class LocalVoiceContractTests(SimpleTestCase):
    @override_settings(LOCAL_VOICE_LANGUAGES=["en", "fr"])
    def test_language_allowlist(self):
        self.assertEqual(allowed_language("FR"), "fr")
        with self.assertRaises(LocalVoiceError):
            allowed_language("de")


@override_settings(
    BROWSER_AI_ENABLED=False,
    LOCAL_VOICE_ENABLED=True,
    LOCAL_VOICE_LANGUAGES=["en"],
)
class LocalAIViewTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, pk=7)
        self.school = SimpleNamespace(pk=42)

    def _tenant_request(self, request):
        request.user = self.user
        request.school = self.school
        return request

    def test_browser_config_requires_tenant(self):
        request = self.factory.get(
            "/platform-runtime/local-ai/browser-config/",
            HTTP_ACCEPT="application/json",
        )
        request.user = self.user
        response = browser_inference_config_view(request)
        self.assertEqual(response.status_code, 403)

    def test_transcription_requires_explicit_consent(self):
        request = self._tenant_request(
            self.factory.post(
                "/platform-runtime/local-ai/voice/transcribe/",
                data=b"audio",
                content_type="audio/webm",
            )
        )
        response = local_voice_transcribe_view(request)
        self.assertEqual(response.status_code, 400)

    @patch("apps.platform_runtime.views_local_ai.AuditLog.objects.create")
    @patch(
        "apps.platform_runtime.views_local_ai.transcribe",
        return_value="editable transcript",
    )
    def test_transcription_returns_editable_text_without_retention(
        self, transcribe_mock, _audit
    ):
        request = self._tenant_request(
            self.factory.post(
                "/platform-runtime/local-ai/voice/transcribe/",
                data=b"audio",
                content_type="audio/webm",
                HTTP_X_RMC_VOICE_CONSENT="true",
                HTTP_X_RMC_VOICE_LANGUAGE="en",
            )
        )
        response = local_voice_transcribe_view(request)
        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["text"], "editable transcript")
        self.assertFalse(payload["retained"])
        self.assertEqual(response["Cache-Control"], "no-store")
        transcribe_mock.assert_called_once()

    @override_settings(LOCAL_VOICE_RATE_LIMIT_PER_MINUTE=1)
    @patch("apps.platform_runtime.views_local_ai.AuditLog.objects.create")
    @patch(
        "apps.platform_runtime.views_local_ai.transcribe",
        return_value="editable transcript",
    )
    def test_voice_rate_limit_is_tenant_and_user_scoped(self, _transcribe, _audit):
        def request():
            return self._tenant_request(
                self.factory.post(
                    "/platform-runtime/local-ai/voice/transcribe/",
                    data=b"audio",
                    content_type="audio/webm",
                    HTTP_X_RMC_VOICE_CONSENT="true",
                    HTTP_X_RMC_VOICE_LANGUAGE="en",
                )
            )

        self.assertEqual(local_voice_transcribe_view(request()).status_code, 200)
        response = local_voice_transcribe_view(request())
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "60")

    @patch("apps.platform_runtime.views_local_ai.AuditLog.objects.create")
    @patch(
        "apps.platform_runtime.views_local_ai.synthesize",
        return_value=SpeechAudio(b"wave", "audio/wav"),
    )
    def test_synthesis_is_no_store(self, _synthesize, _audit):
        request = self._tenant_request(
            self.factory.post(
                "/platform-runtime/local-ai/voice/synthesize/",
                data=json.dumps(
                    {"text": "Read this", "language": "en", "consent": True}
                ),
                content_type="application/json",
            )
        )
        response = local_voice_synthesize_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["X-Content-Retained"], "false")
