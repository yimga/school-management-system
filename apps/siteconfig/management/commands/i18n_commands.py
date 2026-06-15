"""
Phase 8 Task 5: Internationalization Management Commands
compile_translations - Compile translation files
validate_translations - Verify translation completeness

Note: regional report generation lives in the registered, maintained command
``apps/reports/management/commands/generate_regional_reports.py``. The former
``GenerateRegionalReportsCommand`` here was an unregistered duplicate that
referenced a nonexistent ``ReportCompilationService`` and was retired.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Compile translation JSON files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--language",
            type=str,
            default=None,
            help="Compile specific language",
        )
        parser.add_argument(
            "--validate",
            action="store_true",
            help="Validate translations after compilation",
        )

    def handle(self, *args, **options):
        locale_path = (
            Path(__file__).parent.parent.parent.parent / "locale" / "translations"
        )

        if not locale_path.exists():
            self.stdout.write(
                self.style.ERROR(f"Translation directory not found: {locale_path}")
            )
            raise CommandError("Translation directory missing")

        language = options.get("language")
        validate = options.get("validate")

        if language:
            self.compile_language(language, locale_path)
        else:
            self.compile_all_languages(locale_path)

        if validate:
            self.validate_translations(locale_path)

        self.stdout.write(self.style.SUCCESS("✓ Translations compiled successfully"))


class ValidateTranslationsCommand(BaseCommand):
    """Management command to validate translation completeness"""

    help = "Validate translation files for completeness and consistency"

    def handle(self, *args, **options):
        locale_path = (
            Path(__file__).parent.parent.parent.parent / "locale" / "translations"
        )

        if not locale_path.exists():
            raise CommandError("Translation directory not found")

        # Get all translation files
        translation_files = list(locale_path.glob("*.json"))

        if not translation_files:
            raise CommandError("No translation files found")

        # Load base English translation
        en_file = locale_path / "en.json"
        if not en_file.exists():
            raise CommandError("English translation file not found")

        with open(en_file, "r", encoding="utf-8") as f:
            en_keys = set(json.load(f).keys())

        self.stdout.write(f"Base English keys: {len(en_keys)}")

        issues = {}

        # Check each language
        for trans_file in translation_files:
            if trans_file.name == "en.json":
                continue

            with open(trans_file, "r", encoding="utf-8") as f:
                trans_keys = set(json.load(f).keys())

            lang = trans_file.stem
            missing = en_keys - trans_keys
            extra = trans_keys - en_keys

            if missing or extra:
                issues[lang] = {
                    "missing_keys": list(missing),
                    "extra_keys": list(extra),
                    "key_count": len(trans_keys),
                }

        if issues:
            self.stdout.write(self.style.WARNING("⚠ Translation Issues Found:"))
            for lang, issue in issues.items():
                self.stdout.write(f"  {lang}:")
                if issue["missing_keys"]:
                    self.stdout.write(f"    Missing: {len(issue['missing_keys'])} keys")
                if issue["extra_keys"]:
                    self.stdout.write(f"    Extra: {len(issue['extra_keys'])} keys")
        else:
            self.stdout.write(self.style.SUCCESS("✓ All translations consistent"))


class CompileTranslationsCommand(Command):
    """Compile all translation files"""

    def compile_language(self, language, locale_path):
        """Compile specific language"""
        trans_file = locale_path / f"{language}.json"

        if not trans_file.exists():
            self.stdout.write(
                self.style.WARNING(f"Translation file not found for {language}")
            )
            return

        with open(trans_file, "r", encoding="utf-8") as f:
            translations = json.load(f)

        self.stdout.write(f"✓ Compiled {language}: {len(translations)} translations")

    def compile_all_languages(self, locale_path):
        """Compile all language files"""
        translation_files = list(locale_path.glob("*.json"))

        for trans_file in translation_files:
            lang = trans_file.stem
            with open(trans_file, "r", encoding="utf-8") as f:
                translations = json.load(f)

            self.stdout.write(f"✓ Compiled {lang}: {len(translations)} translations")

    def validate_translations(self, locale_path):
        """Validate translation files"""
        en_file = locale_path / "en.json"

        if not en_file.exists():
            return

        with open(en_file, "r", encoding="utf-8") as f:
            en_keys = set(json.load(f).keys())

        issues = 0

        for trans_file in locale_path.glob("*.json"):
            if trans_file.name == "en.json":
                continue

            with open(trans_file, "r", encoding="utf-8") as f:
                trans_keys = set(json.load(f).keys())

            missing = en_keys - trans_keys
            if missing:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ⚠ {trans_file.stem}: Missing {len(missing)} keys"
                    )
                )
                issues += 1

        if issues == 0:
            self.stdout.write(self.style.SUCCESS("✓ All translations valid"))
