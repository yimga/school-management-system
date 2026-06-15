"""Gap-closure validation (2026-06-14) — email ticker reads the real model.

Plain ``unittest`` (no DB).

`_source_email_delivery_events` imported a non-existent
`apps.communications.models.EmailDeliveryEvent` (plural app, wrong module),
swallowed the ImportError, and so the "N platform emails delivered today"
ticker row NEVER appeared. The real model is
`apps.schoolops.models_email_delivery.EmailDeliveryEvent` (platform-level, no
school FK — the cross-tenant aggregate is by-design). Fixed both import sites.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent


class EmailTickerSourceModuleTests(unittest.TestCase):

    def test_phantom_communications_import_gone(self) -> None:
        src = (
            REPO / "apps" / "siteconfig" / "cockpit_activity_ticker_realdata.py"
        ).read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("apps.communications.models", src)
        self.assertIn(
            "from apps.schoolops.models_email_delivery import EmailDeliveryEvent",
            src,
        )

    def test_real_model_has_created_at(self) -> None:
        from apps.schoolops.models_email_delivery import EmailDeliveryEvent

        names = {f.name for f in EmailDeliveryEvent._meta.get_fields()}
        self.assertIn("created_at", names)

    def test_source_runs_without_import_error(self) -> None:
        from apps.siteconfig.cockpit_activity_ticker_realdata import (
            _source_email_delivery_events,
        )

        # Must return a list (0 rows is fine) — never raise ImportError now.
        result = _source_email_delivery_events()
        self.assertIsInstance(result, list)
        # Sanity: the source body references the real module, not the phantom.
        body = inspect.getsource(_source_email_delivery_events)
        self.assertNotIn("communications", body)


if __name__ == "__main__":
    unittest.main()
