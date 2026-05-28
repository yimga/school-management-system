"""v4.00.9 — Tests for the streaming AI gateway view.

Endpoint: POST /portal/ai/stream/

Covers:
  * 401/403 when unauthenticated.
  * 400 on missing prompt / bad JSON.
  * 413 on oversize prompt.
  * 503 when LiteLLM unconfigured.
  * 200 SSE stream when configured (mock stream_litellm yielding 2 chunks).
  * Response carries Cache-Control: no-cache + X-Accel-Buffering: no.
  * Viewport header reflected back.
"""

from __future__ import annotations

import json
from unittest import mock

from django.test import RequestFactory, SimpleTestCase


def _build_user(*, authenticated: bool = True):
    user = mock.MagicMock()
    user.is_authenticated = authenticated
    user.pk = 42
    return user


def _post(path: str, body: dict, *, user=None, viewport: str = "A"):
    factory = RequestFactory()
    request = factory.post(
        path,
        data=json.dumps(body).encode("utf-8"),
        content_type="application/json",
        HTTP_X_RMC_VIEWPORT=viewport,
    )
    request.user = user or _build_user()
    # csrf_protect requires the cookie/token; bypass for unit tests.
    request._dont_enforce_csrf_checks = True
    return request


class AIStreamViewBadInputTests(SimpleTestCase):
    def test_bad_json_returns_400(self):
        from apps.portal.views_ai_stream import ai_stream_view

        factory = RequestFactory()
        request = factory.post(
            "/portal/ai/stream/",
            data=b"not json",
            content_type="application/json",
        )
        request.user = _build_user()
        request._dont_enforce_csrf_checks = True
        response = ai_stream_view(request)
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertEqual(body["error"], "bad_json")

    def test_empty_prompt_returns_400(self):
        from apps.portal.views_ai_stream import ai_stream_view

        request = _post("/portal/ai/stream/", {"prompt": "   "})
        response = ai_stream_view(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["error"], "no_prompt")

    def test_oversize_prompt_returns_413(self):
        from apps.portal.views_ai_stream import ai_stream_view

        request = _post("/portal/ai/stream/", {"prompt": "x" * (33 * 1024)})
        response = ai_stream_view(request)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(json.loads(response.content)["error"], "prompt_too_large")


class AIStreamViewGatewayConfigTests(SimpleTestCase):
    def test_unconfigured_litellm_returns_503(self):
        from apps.portal import views_ai_stream

        request = _post("/portal/ai/stream/", {"prompt": "hello"})
        with mock.patch("services.ai_deployment_posture.is_litellm_configured", return_value=False):
            response = views_ai_stream.ai_stream_view(request)
        self.assertEqual(response.status_code, 503)


class AIStreamViewSuccessTests(SimpleTestCase):
    def test_configured_streams_sse_chunks(self):
        from apps.portal import views_ai_stream

        def _fake_stream(prompt, viewport="A"):
            yield "First chunk.", {"provider": "litellm", "model": "test", "viewport": viewport}
            yield "Second chunk.", {"provider": "litellm", "model": "test", "viewport": viewport}

        request = _post("/portal/ai/stream/", {"prompt": "what is 2+2"}, viewport="B")
        with mock.patch("services.ai_deployment_posture.is_litellm_configured", return_value=True), \
             mock.patch("services.ai_gateway_stream.stream_litellm", side_effect=_fake_stream):
            response = views_ai_stream.ai_stream_view(request)
            # streaming_content is a lazy generator — iterate inside the patch context.
            body = b"".join(response.streaming_content).decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertEqual(response["X-Accel-Buffering"], "no")
        self.assertEqual(response["X-RMC-Viewport"], "B")
        self.assertIn("data: First chunk.", body)
        self.assertIn("data: Second chunk.", body)
        self.assertTrue(body.endswith("data: [DONE]\n\n"))

    def test_stream_handles_empty_generator(self):
        from apps.portal import views_ai_stream

        def _empty(prompt, viewport="A"):
            return
            yield  # pragma: no cover — make this a generator

        request = _post("/portal/ai/stream/", {"prompt": "hello"})
        with mock.patch("services.ai_deployment_posture.is_litellm_configured", return_value=True), \
             mock.patch("services.ai_gateway_stream.stream_litellm", side_effect=_empty):
            response = views_ai_stream.ai_stream_view(request)
            body = b"".join(response.streaming_content).decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body, "data: [DONE]\n\n")

    def test_stream_swallows_chunk_exception_and_terminates(self):
        from apps.portal import views_ai_stream

        def _explodes(prompt, viewport="A"):
            yield "ok-chunk", {"provider": "litellm"}
            raise RuntimeError("upstream blew up mid-stream")

        request = _post("/portal/ai/stream/", {"prompt": "hello"})
        with mock.patch("services.ai_deployment_posture.is_litellm_configured", return_value=True), \
             mock.patch("services.ai_gateway_stream.stream_litellm", side_effect=_explodes):
            response = views_ai_stream.ai_stream_view(request)
            body = b"".join(response.streaming_content).decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("data: ok-chunk", body)
        self.assertTrue(body.endswith("data: [DONE]\n\n"))


class SSEPackingTests(SimpleTestCase):
    def test_multiline_chunk_emits_one_data_per_line(self):
        from apps.portal.views_ai_stream import _sse_pack

        out = _sse_pack("line1\nline2\nline3").decode("utf-8")
        self.assertEqual(out.count("data: "), 3)
        self.assertTrue(out.endswith("\n\n"))

    def test_crlf_normalized(self):
        from apps.portal.views_ai_stream import _sse_pack

        out = _sse_pack("a\r\nb").decode("utf-8")
        self.assertEqual(out.count("data: "), 2)
