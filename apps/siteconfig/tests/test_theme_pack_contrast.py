"""Wave 3-tail: ThemePack contrast seal.

``ThemePack.clean()`` rejects invalid-hex or invisible-brand packs so a school can
never save an unreadable theme. Foreground text itself stays readable through the
adaptive ``--text-on-brand`` cascade, so a bright brand is allowed. The AAA
brand-cycle remediation engine (``scripts/verify_theme_aaa_brand_cycle``) is
exercised here so that gate actually runs on every PR (ci.yml::django-tests).
"""

from __future__ import annotations

import importlib.util
import pathlib

from django.core.exceptions import ValidationError
from django.test import TestCase


def _load_brand_cycle():
    root = pathlib.Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "verify_theme_aaa_brand_cycle", root / "scripts" / "verify_theme_aaa_brand_cycle.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ThemePackContrastTests(TestCase):
    def _pack(self, **kw):
        from apps.siteconfig.models_tooling import ThemePack

        defaults = dict(
            name="Ocean", slug="ocean", primary_color="#0d6efd",
            accent_color="#198754", background_color="#ffffff",
        )
        defaults.update(kw)
        return ThemePack(**defaults)

    def test_clean_accepts_readable_pack(self):
        self._pack().full_clean()  # must not raise

    def test_clean_rejects_invalid_hex(self):
        with self.assertRaises(ValidationError):
            self._pack(primary_color="not-a-color").full_clean()

    def test_clean_rejects_invisible_primary(self):
        # primary indistinguishable from a white canvas -> the brand vanishes
        with self.assertRaises(ValidationError):
            self._pack(primary_color="#fffffe", background_color="#ffffff").full_clean()

    def test_clean_allows_bright_brand(self):
        # a vivid brand on a dark canvas is fine — text adapts via --text-on-brand
        self._pack(primary_color="#facc15", background_color="#0f172a").full_clean()

    def test_aaa_brand_cycle_gate_passes(self):
        self.assertEqual(_load_brand_cycle().main(), 0)
