"""The critical-UI pack must be served by the COMPILED catalog, not merely typed.

``scripts/verify_critical_msgid_depth.py`` reads ``django.po``. A .po file is not
what a user gets: Django reads ``django.mo``, and ``polib``/``msgfmt`` do not
compile an entry whose msgstr is empty. So a locale can hold a perfectly good
translation in its .po and still render English -- and the .po-reading gate says
PASS the whole time.

These tests ask the runtime instead. For every locale that gate covers, they
activate it and read what ``gettext`` actually returns, which is the .mo or
nothing. They also interpolate the one msgid carrying format placeholders,
because a translation that drops ``%(tier)s`` is not a cosmetic defect: it raises
``KeyError`` on the line that renders it.

ha / pid / sw / yo are deliberately NOT here. ``scan_locale_coverage``'s
``_STUB_HUMANONLY_REASON`` forbids AI drafts for them in writing, so their pack
is English until a human translator delivers, and asserting otherwise would
either force that policy to be broken or make this file permanently red.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.utils import translation

REPO_ROOT = Path(settings.BASE_DIR)


def _load_gate():
    path = REPO_ROOT / "scripts" / "verify_critical_msgid_depth.py"
    spec = importlib.util.spec_from_file_location("_critical_msgid_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE = _load_gate()

#: locale dir name -> the LANGUAGES code Django activates. They differ for the
#: BCP47-ish codes: locale/zh_Hans is served to language "zh-hans".
LOCALE_TO_LANGUAGE = {
    "fr": "fr",
    "es": "es",
    "pt_BR": "pt-br",
    "de": "de",
    "it": "it",
    "ru": "ru",
    "ja": "ja",
    "zh_Hans": "zh-hans",
    "zh_Hant": "zh-hant",
    "hi": "hi",
    "tr": "tr",
    "ar": "ar",
    "fa": "fa",
    "he": "he",
    "ur": "ur",
}

PLACEHOLDER_MSGID = "MTSS tier updated to %(tier)s (%(count)s open incident(s))."


class CriticalPackIsCompiledAndServedTests(SimpleTestCase):
    def test_the_gate_and_this_test_cover_the_same_locales(self):
        """Otherwise one of them silently stops protecting a locale."""
        self.assertEqual(set(GATE.LOCALES), set(LOCALE_TO_LANGUAGE))

    def test_every_locale_serves_every_critical_msgid_from_its_mo(self):
        english = set(GATE.CRITICAL_MSGIDS)
        for locale, language in sorted(LOCALE_TO_LANGUAGE.items()):
            for msgid in english:
                with self.subTest(locale=locale, msgid=msgid):
                    with translation.override(language):
                        served = translation.gettext(msgid)
                    self.assertNotEqual(
                        served,
                        msgid,
                        f"{locale}: gettext returned the English source, so the "
                        "msgstr never reached django.mo (an empty msgstr is not "
                        "compiled -- run `manage.py sync_i18n_catalog --compile`).",
                    )

    def test_the_format_placeholders_survive_translation(self):
        for locale, language in sorted(LOCALE_TO_LANGUAGE.items()):
            with self.subTest(locale=locale):
                with translation.override(language):
                    served = translation.gettext(PLACEHOLDER_MSGID)
                self.assertIn("%(tier)s", served, locale)
                self.assertIn("%(count)s", served, locale)
                # A dropped or renamed placeholder is a KeyError at render time,
                # so interpolate it here rather than trusting the substring test.
                rendered = served % {"tier": "Tier 2", "count": 3}
                self.assertIn("Tier 2", rendered)
                self.assertIn("3", rendered)

    def test_human_only_locales_are_left_in_english_on_purpose(self):
        """The policy is a decision, so it gets a test rather than a comment."""
        for language in ("ha", "pid", "sw", "yo"):
            with self.subTest(language=language):
                with translation.override(language):
                    self.assertEqual(
                        translation.gettext("Booking confirmed."),
                        "Booking confirmed.",
                        "an AI draft has been added to a locale that "
                        "scan_locale_coverage reserves for a human translator",
                    )

    def test_the_pack_is_not_empty(self):
        """A green run over an empty msgid list would prove nothing."""
        self.assertGreaterEqual(len(GATE.CRITICAL_MSGIDS), 19)
        self.assertIn(PLACEHOLDER_MSGID, GATE.CRITICAL_MSGIDS)
