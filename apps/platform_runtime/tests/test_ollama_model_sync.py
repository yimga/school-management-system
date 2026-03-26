from __future__ import annotations

import os
from unittest import mock

from django.test import SimpleTestCase

from apps.platform_runtime.ollama_model_sync import (
    collect_ollama_models_for_sync,
    filtered_models,
    is_allowed_ollama_model_id,
)


class OllamaModelSyncAllowlistTests(SimpleTestCase):
    def test_allows_common_tags(self):
        self.assertTrue(is_allowed_ollama_model_id("llama3"))
        self.assertTrue(is_allowed_ollama_model_id("qwen2.5:7b"))
        self.assertTrue(is_allowed_ollama_model_id("nomic-embed-text"))

    def test_rejects_injection_like_tokens(self):
        self.assertFalse(is_allowed_ollama_model_id("; rm -rf /"))
        self.assertFalse(is_allowed_ollama_model_id("$(whoami)"))
        self.assertFalse(is_allowed_ollama_model_id(""))
        self.assertFalse(is_allowed_ollama_model_id("x" * 300))

    def test_filtered_models_dedupes(self):
        self.assertEqual(
            filtered_models(["llama3", "llama3", "bad;cmd"]),
            ["llama3"],
        )


class OllamaModelCollectTests(SimpleTestCase):
    def test_collect_from_env_without_registry(self):
        with mock.patch.dict(
            os.environ,
            {
                "OLLAMA_MODEL": "llama3.2",
                "AI_EMBEDDING_BACKEND": "ollama",
                "AI_EMBEDDING_OLLAMA_MODEL": "nomic-embed-text",
                "OLLAMA_SYNC_EXTRA_MODELS": "phi3:mini",
            },
            clear=False,
        ):
            got = collect_ollama_models_for_sync(include_registry=False)
        self.assertEqual(
            got,
            ["llama3.2", "nomic-embed-text", "phi3:mini"],
        )
