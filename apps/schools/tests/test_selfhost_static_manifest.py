"""Self-host static must be COLLECTED under the same storage it is SERVED under.

The box runs with ``DEBUG=0`` -> ``ForgivingCompressedManifestStaticFilesStorage``,
which rewrites ``{% static %}`` to content-hashed names (``foo.<hash>.css``) and
needs a ``staticfiles.json`` manifest + the hashed files on disk. But off-Render
``DEBUG`` defaults to ``1`` (``config/settings.py``: ``_debug_default = "1"``),
under which settings selects the PLAIN storage (no hashing, no manifest).

If the image's build-time ``collectstatic`` runs under the default ``DEBUG=1`` while
the container serves under ``DEBUG=0``, every hashed URL the templates emit 404s and
the entire UI renders unstyled (observed live on the SER8 box: ``staticfiles.json``
absent, ``/static/css/*.<hash>.css`` -> 404). The fix pins ``DEBUG=0`` on the
Dockerfile's collectstatic step so the two storages agree.

DB-free ``SimpleTestCase`` string assertions on the Dockerfile recipe; they fail
before the ``DEBUG=0`` pin is added.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

_DOCKERFILE = Path(settings.BASE_DIR) / "deploy" / "selfhost" / "Dockerfile"


class SelfHostStaticManifestBuildTests(SimpleTestCase):
    def test_dockerfile_exists(self):
        self.assertTrue(
            _DOCKERFILE.is_file(), f"self-host Dockerfile not found at {_DOCKERFILE}"
        )

    def test_collectstatic_pins_debug_off_so_manifest_storage_is_used(self):
        text = _DOCKERFILE.read_text(encoding="utf-8")
        # Only the real invocation ("manage.py collectstatic"), never comment prose
        # that merely mentions the word "collectstatic".
        collect_lines = [ln for ln in text.splitlines() if "manage.py collectstatic" in ln]
        self.assertTrue(collect_lines, "Dockerfile has no `manage.py collectstatic` step")
        for ln in collect_lines:
            self.assertIn(
                "DEBUG=0",
                ln,
                "Build-time collectstatic must run with DEBUG=0 so it uses the "
                "hashed/manifest storage the DEBUG=0 runtime serves; otherwise "
                "hashed static URLs 404 and the UI is unstyled. Offending line: "
                f"{ln.strip()!r}",
            )
