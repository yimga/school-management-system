"""i18n catalog builder: extraction + merge without GNU gettext."""

import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.siteconfig.i18n_catalog_builder import (
    collect_translatable_strings,
    merge_locale_catalogs,
    verify_en_catalog_against_codebase,
)


class I18nCatalogBuilderTests(SimpleTestCase):
    def test_collect_finds_known_ui_strings(self):
        strings = collect_translatable_strings(Path(settings.BASE_DIR))
        self.assertIn("No school context", strings)
        self.assertIn("Trust center", strings)
        self.assertGreater(len(strings), 500)

    def test_merge_writes_new_locale_tree(self):
        """Isolated project root: no dependency on repo-sized django.po."""
        token = f"sync-i18n-test-{uuid.uuid4().hex}"
        root = Path(tempfile.mkdtemp())
        added, pruned = merge_locale_catalogs(
            base_dir=root,
            languages=[("en", "English"), ("fr", "Français")],
            discovered={token},
            dry_run=False,
            compile_mo=False,
        )
        self.assertEqual(added["en"], 1)
        self.assertEqual(added["fr"], 1)
        self.assertEqual(pruned["en"], 0)
        en_po = root / "locale" / "en" / "LC_MESSAGES" / "django.po"
        self.assertTrue(en_po.is_file())
        self.assertIn(token, en_po.read_text(encoding="utf-8"))
        fr_po = root / "locale" / "fr" / "LC_MESSAGES" / "django.po"
        self.assertTrue(fr_po.is_file())
        self.assertIn(f'msgid "{token}"', fr_po.read_text(encoding="utf-8"))
        self.assertIn('msgstr ""', fr_po.read_text(encoding="utf-8"))

    def test_en_catalog_covers_codebase(self):
        """Gate: locale/en django.po must include every string the scanner finds."""
        missing, _stale = verify_en_catalog_against_codebase(Path(settings.BASE_DIR))
        self.assertEqual(
            missing,
            set(),
            msg=f"Run: python manage.py sync_i18n_catalog --compile — missing {len(missing)} msgids (sample: {list(sorted(missing))[:5]})",
        )
