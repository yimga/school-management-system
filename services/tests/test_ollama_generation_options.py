"""The Ollama payload must be able to bound latency and keep the model resident.

Measured on a CPU-only box (2026-08-19) with the payload as it used to be --
`{model, prompt, stream}` and nothing else:

  * no ``keep_alive``  -> Ollama unloads after its 5-minute default, so the next
    call pays a 17s cold load before generating and the provider timeout fires.
  * no ``num_predict`` -> unbounded output: 93.5s for 392 tokens (~4.2 tok/s),
    well past the 60s ceiling _request_timeout_seconds() allows.

The visible symptom was that offline failover looked broken: the gateway reported
``ollama: unavailable`` and served the rules fallback, even though Ollama was up
and answering. These tests pin the two knobs that fix it.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from services.inference import _ollama_generation_options

#: The helper reads settings THEN os.environ, so a developer .env carrying real
#: values would otherwise leak into these assertions. Clear both knobs per test.
_NO_ENV = patch.dict(os.environ, {"AI_OLLAMA_NUM_PREDICT": "", "AI_OLLAMA_KEEP_ALIVE": ""})


class _EnvIsolated(SimpleTestCase):
    def setUp(self):
        _NO_ENV.start()
        self.addCleanup(_NO_ENV.stop)


class KeepAliveTests(_EnvIsolated):
    """Residency is a pure win, so it is on by default."""

    def test_keep_alive_defaults_on(self):
        self.assertEqual(_ollama_generation_options().get("keep_alive"), "30m")

    @override_settings(AI_OLLAMA_KEEP_ALIVE="2h")
    def test_keep_alive_is_configurable(self):
        self.assertEqual(_ollama_generation_options().get("keep_alive"), "2h")

    @override_settings(AI_OLLAMA_KEEP_ALIVE="off")
    def test_keep_alive_can_be_disabled(self):
        self.assertNotIn("keep_alive", _ollama_generation_options())


class NumPredictTests(_EnvIsolated):
    """Capping output trades completeness for bounded latency, so it is OPT-IN:
    right for a slow CPU box, wrong for a GPU deployment."""

    def test_num_predict_absent_by_default(self):
        self.assertNotIn("options", _ollama_generation_options())

    @override_settings(AI_OLLAMA_NUM_PREDICT=200)
    def test_num_predict_sets_options(self):
        self.assertEqual(
            _ollama_generation_options().get("options"), {"num_predict": 200}
        )

    @override_settings(AI_OLLAMA_NUM_PREDICT="not-a-number")
    def test_garbage_num_predict_is_ignored(self):
        self.assertNotIn("options", _ollama_generation_options())

    def test_zero_num_predict_is_ignored(self):
        with patch.dict(os.environ, {"AI_OLLAMA_NUM_PREDICT": "0"}):
            self.assertNotIn("options", _ollama_generation_options())


class PayloadShapeTests(_EnvIsolated):
    """Merged into the payload, the keys must not collide with model/prompt/stream."""

    @override_settings(AI_OLLAMA_NUM_PREDICT=128, AI_OLLAMA_KEEP_ALIVE="10m")
    def test_options_do_not_shadow_core_payload_keys(self):
        opts = _ollama_generation_options()
        for reserved in ("model", "prompt", "stream"):
            self.assertNotIn(reserved, opts)
