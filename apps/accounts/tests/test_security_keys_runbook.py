"""Tests for the v3.32.0 ``docs/SECURITY_KEYS.md`` rotation runbook.

The runbook is an operator-facing document, not code — but it is
load-bearing for incident response. We test it as a contract:

  * The file exists at the documented path.
  * Every required section (one per key/secret type) is present.
  * Every Python code block parses (no broken examples).
  * No example contains a literal-looking key — every example uses
    obvious placeholders so we never leak a real secret by pasting it
    into a runbook diff.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


def _runbook_path() -> Path:
    """Return the absolute path to the runbook under the repo root."""
    return Path(settings.BASE_DIR) / "docs" / "SECURITY_KEYS.md"


class SecurityKeysRunbookExistenceTests(SimpleTestCase):
    def test_runbook_file_exists(self) -> None:
        path = _runbook_path()
        self.assertTrue(
            path.is_file(), f"docs/SECURITY_KEYS.md missing at {path}"
        )

    def test_runbook_is_not_empty(self) -> None:
        path = _runbook_path()
        body = path.read_text(encoding="utf-8")
        self.assertGreater(len(body), 2000, "runbook is implausibly short")


class SecurityKeysRunbookSectionsTests(SimpleTestCase):
    """Every required section heading must be present."""

    REQUIRED_HEADINGS = [
        # The headings appear as markdown level-2 (##) entries.
        r"^##\s+0\.\s+Inventory",
        r"^##\s+1\.\s+`SECRET_KEY`",
        r"^##\s+2\.\s+`DJANGO_CRYPTOGRAPHY_KEY`",
        r"^##\s+3\.\s+`CompanionKeypair`",
        r"^##\s+4\.\s+Webhook subscription secrets",
        r"^##\s+5\.\s+`MigrationCloudAPIToken`",
        r"^##\s+6\.\s+Incident response",
    ]

    def test_all_required_headings_present(self) -> None:
        body = _runbook_path().read_text(encoding="utf-8")
        for pattern in self.REQUIRED_HEADINGS:
            self.assertRegex(
                body, re.compile(pattern, re.MULTILINE),
                msg=f"missing required runbook heading: {pattern!r}",
            )


class SecurityKeysRunbookCodeBlocksTests(SimpleTestCase):
    """Every ```python code block in the runbook must AST-parse."""

    _PY_BLOCK_RE = re.compile(
        r"```python\n(.*?)```", re.DOTALL,
    )

    def test_python_blocks_ast_parse(self) -> None:
        body = _runbook_path().read_text(encoding="utf-8")
        blocks = self._PY_BLOCK_RE.findall(body)
        self.assertGreater(
            len(blocks), 0,
            "expected at least one Python code block in the runbook",
        )
        for idx, src in enumerate(blocks):
            with self.subTest(block_index=idx):
                try:
                    ast.parse(src)
                except SyntaxError as exc:
                    self.fail(
                        f"runbook Python block #{idx} did not parse: {exc!r}\n"
                        f"--- block ---\n{src}\n--- end block ---"
                    )


class SecurityKeysRunbookNoLiteralSecretsTests(SimpleTestCase):
    """No code fence may contain a literal-looking key.

    Heuristic: a 24+-char base64-ish run inside a code fence that's NOT
    obviously a placeholder (`xxxx-xxxx`, `<INSERT...>`, etc.) trips
    the check. The intent is to catch a real Fernet key (44 chars
    URL-safe base64) accidentally pasted in.
    """

    # Anything inside ``` ... ``` fences.
    _CODE_FENCE_RE = re.compile(r"```[a-z]*\n(.*?)```", re.DOTALL)
    # 24+ run of [A-Za-z0-9_\-=] (URL-safe base64 alphabet).
    _SECRET_RE = re.compile(r"[A-Za-z0-9_\-=]{24,}")
    # Phrases that mark a placeholder + an explicit allowlist of
    # tokens that legitimately match the secret regex (env-var names,
    # function names, command tokens).
    _PLACEHOLDER_MARKERS = (
        "xxxx", "INSERT",
        "DJANGO_CRYPTOGRAPHY_KEY", "DJANGO_CRYPTOGRAPHY_KEYS",
        "encrypt_existing_legacy_hashes", "rewrap_all",
        "MigrationCloudWebhookSubscription",
        "companion_receiver", "rotate_companion_keypair",
        "CompanionUploadReceipt",
        "PASSWORD_RESET_TIMEOUT", "SECRET_KEY_FALLBACKS",
        "token_urlsafe", "generate_key",
        "X-Migration-Cloud-Signature", "Authorization",
        "api_token_revoked", "key_version_old", "key_version_new",
        "revoked-due-to-key-rotation", "secret_ciphertext",
        "MultiFernet", "EncryptedBinaryField",
        "rmctok", "whsec",
    )

    def test_no_literal_keys_in_code_blocks(self) -> None:
        body = _runbook_path().read_text(encoding="utf-8")
        for block in self._CODE_FENCE_RE.findall(body):
            for match in self._SECRET_RE.findall(block):
                if any(marker in match for marker in self._PLACEHOLDER_MARKERS):
                    continue
                self.fail(
                    f"runbook code block contains a literal-looking key: "
                    f"{match!r}\nIf this is intentional, add it to the "
                    f"_PLACEHOLDER_MARKERS allowlist with justification."
                )


class SecurityKeysRunbookReferencesIntakeTests(SimpleTestCase):
    """Runbook §7 names the three companion test files (forward link)."""

    def test_section_7_mentions_test_modules(self) -> None:
        body = _runbook_path().read_text(encoding="utf-8")
        for needle in (
            "test_security_keys_runbook",
            "test_legacy_hash_intake",
            "test_webhook_secret_encryption",
        ):
            self.assertIn(needle, body, f"runbook should reference {needle}")
