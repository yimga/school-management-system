"""
Compile and manage translations.
Usage: python manage.py compile_translations [--init] [--rebuild] [--status]
"""

from django.core.management.base import BaseCommand
from apps.siteconfig.translations import (
    TranslationManager,
    SUPPORTED_LANGUAGES,
    init_translations,
)
import json


class Command(BaseCommand):
    help = "Compile and manage translations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--init",
            action="store_true",
            help="Initialize translations for all languages",
        )
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Rebuild all translation files from scratch",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Show translation status",
        )
        parser.add_argument(
            "--language",
            type=str,
            help="Work with specific language (e.g., fr, sw)",
        )
        parser.add_argument(
            "--add",
            type=str,
            help="Add new string to translations (with --language)",
        )
        parser.add_argument(
            "--translation",
            type=str,
            help="Translation for the string (with --add)",
        )
        parser.add_argument(
            "--export",
            type=str,
            help="Export translations to file",
        )
        parser.add_argument(
            "--import",
            dest="import_file",
            type=str,
            help="Import translations from file",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("\n[*] Translation Manager\n"))
        self.stdout.write("=" * 60)

        if options["init"]:
            self.init_translations()
        elif options["rebuild"]:
            self.rebuild_translations()
        elif options["status"]:
            self.show_status(options.get("language"))
        elif options["add"] and options["translation"]:
            self.add_translation(options)
        elif options["export"]:
            self.export_translations(options["export"], options.get("language"))
        elif options["import_file"]:
            self.import_translations(options["import_file"], options.get("language"))
        else:
            self.show_status()

    def init_translations(self):
        """Initialize translations for all languages."""
        self.stdout.write("Initializing translations...\n")
        init_translations()
        self.stdout.write(self.style.SUCCESS("[+] Translations initialized for:"))

        trans_dir = TranslationManager.get_translation_dir()
        for lang_code in SUPPORTED_LANGUAGES.keys():
            file_path = trans_dir / f"{lang_code}.json"
            if file_path.exists():
                with open(file_path, "r") as f:
                    count = len(json.load(f))
                self.stdout.write(f"  [+] {lang_code}: {count} strings")

    def rebuild_translations(self):
        """Rebuild all translation files from scratch."""
        self.stdout.write(self.style.WARNING("[*] Rebuilding all translations...\n"))

        trans_dir = TranslationManager.get_translation_dir()

        # Clear all translation files
        for lang_code in SUPPORTED_LANGUAGES.keys():
            file_path = trans_dir / f"{lang_code}.json"
            if file_path.exists():
                file_path.unlink()
                self.stdout.write(f"  Cleared {lang_code}")

        # Reinitialize
        TranslationManager._cache.clear()
        self.init_translations()
        self.stdout.write(self.style.SUCCESS("\n[+] Translations rebuilt"))

    def show_status(self, language=None):
        """Show translation status."""
        self.stdout.write(self.style.SUCCESS("\n[*] Translation Status\n"))

        trans_dir = TranslationManager.get_translation_dir()

        if language:
            languages = [language] if language in SUPPORTED_LANGUAGES else []
        else:
            languages = list(SUPPORTED_LANGUAGES.keys())

        if not languages:
            self.stdout.write(self.style.ERROR(f'Language "{language}" not supported'))
            return

        for lang_code in languages:
            file_path = trans_dir / f"{lang_code}.json"

            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    translations = json.load(f)
                count = len(translations)
                size = file_path.stat().st_size

                lang_name = SUPPORTED_LANGUAGES.get(lang_code, lang_code)
                self.stdout.write(
                    f"[+] {lang_code:6} ({lang_name:15}): {count:4} strings, {size:8} bytes"
                )
            else:
                lang_name = SUPPORTED_LANGUAGES.get(lang_code, lang_code)
                self.stdout.write(
                    self.style.WARNING(
                        f"[!] {lang_code:6} ({lang_name:15}): Not initialized"
                    )
                )

    def add_translation(self, options):
        """Add a translation."""
        language = options.get("language")
        text = options.get("add")
        translation_text = options.get("translation")

        if not language or language not in SUPPORTED_LANGUAGES:
            self.stdout.write(self.style.ERROR(f"Invalid language: {language}"))
            return

        TranslationManager.set_translation(text, language, translation_text)
        self.stdout.write(
            self.style.SUCCESS(f'\n[+] Added translation for "{text}" in {language}')
        )

    def export_translations(self, export_file, language=None):
        """Export translations to file."""
        from datetime import datetime

        trans_dir = TranslationManager.get_translation_dir()

        if language:
            languages = [language] if language in SUPPORTED_LANGUAGES else []
        else:
            languages = list(SUPPORTED_LANGUAGES.keys())

        export_data = {"timestamp": datetime.now().isoformat(), "languages": {}}

        for lang_code in languages:
            file_path = trans_dir / f"{lang_code}.json"
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    export_data["languages"][lang_code] = json.load(f)

        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        self.stdout.write(
            self.style.SUCCESS(
                f"\n[+] Exported {len(export_data['languages'])} language(s) to {export_file}"
            )
        )

    def import_translations(self, import_file, language=None):
        """Import translations from file."""
        try:
            with open(import_file, "r", encoding="utf-8") as f:
                import_data = json.load(f)

            count = 0
            for lang_code, translations in import_data.get("languages", {}).items():
                if language and lang_code != language:
                    continue

                if lang_code not in SUPPORTED_LANGUAGES:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping unsupported language: {lang_code}"
                        )
                    )
                    continue

                TranslationManager.bulk_import(lang_code, translations)
                count += 1
                self.stdout.write(
                    f"  [+] Imported {len(translations)} strings for {lang_code}"
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"\n[+] Imported from {import_file} ({count} language(s))"
                )
            )

        except (OSError, ValueError, KeyError, TypeError) as e:
            self.stdout.write(self.style.ERROR(f"\n[!] Error importing: {e}"))
