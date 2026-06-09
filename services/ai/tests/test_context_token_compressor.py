"""ContextTokenCompressor unit tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from services.ai.context_token_compressor import ContextTokenCompressor


class ContextTokenCompressorTests(SimpleTestCase):
    def test_prioritizes_permission_keys_when_trimming(self):
        compressor = ContextTokenCompressor(max_chars=200)
        payload = {
            "narrative": "x" * 500,
            "required_permissions": ["settings.manage"],
            "url_path": "/super/configuration/",
            "tenant_id": "abc",
        }
        out = compressor.compress_mapping(payload)
        self.assertIn("required_permissions", out)
        self.assertIn("url_path", out)
        self.assertLessEqual(len(json_dump(out)), 200)

    def test_compress_text_blocks_preserves_head_and_tail(self):
        compressor = ContextTokenCompressor(max_chars=80)
        text = compressor.compress_text_blocks(["HEAD" * 20, "MID" * 20, "TAIL" * 20])
        self.assertIn("HEAD", text)
        self.assertIn("...", text)


def json_dump(obj):
    import json

    return json.dumps(obj, ensure_ascii=True)
