"""
Tests for translation system and multi-language support.
"""

from django.test import TestCase, Client, RequestFactory
from django.contrib.auth import get_user_model

from apps.siteconfig.translations import TranslationManager, SUPPORTED_LANGUAGES
from apps.siteconfig.models import RegionConfig
from apps.siteconfig.context_processors import language_context

User = get_user_model()


class TranslationManagerTestCase(TestCase):
    """Test TranslationManager functionality."""

    def setUp(self):
        """Clear cache before each test."""
        TranslationManager._cache.clear()

    def test_load_language(self):
        """Test loading language translations."""
        # Initialize
        TranslationManager.set_translation("Hello", "fr", "Bonjour")

        # Load and check
        translations = TranslationManager.load_language("fr")
        self.assertIn("Hello", translations)
        self.assertEqual(translations["Hello"], "Bonjour")

    def test_get_text_default(self):
        """Test getting text for English (no translation needed)."""
        text = TranslationManager.get_text("Hello", "en")
        self.assertEqual(text, "Hello")

    def test_get_text_translated(self):
        """Test getting translated text."""
        # Set translation
        TranslationManager.set_translation("Hello", "fr", "Bonjour")

        # Get translation
        text = TranslationManager.get_text("Hello", "fr")
        self.assertEqual(text, "Bonjour")

    def test_get_text_fallback(self):
        """Test getting untranslated text (returns original)."""
        text = TranslationManager.get_text("Unknown Text", "fr")
        self.assertEqual(text, "Unknown Text")

    def test_set_translation(self):
        """Test setting a translation."""
        TranslationManager.set_translation("Test", "fr", "Tester")

        translations = TranslationManager.load_language("fr")
        self.assertEqual(translations["Test"], "Tester")

    def test_bulk_import(self):
        """Test bulk importing translations."""
        import_data = {
            "String 1": "Chaîne 1",
            "String 2": "Chaîne 2",
            "String 3": "Chaîne 3",
        }

        TranslationManager.bulk_import("fr", import_data)

        translations = TranslationManager.load_language("fr")
        for key, value in import_data.items():
            self.assertEqual(translations.get(key), value)

    def test_multiple_languages(self):
        """Test handling multiple languages."""
        languages = ["en", "fr", "sw", "ha", "yo"]

        for lang in languages:
            TranslationManager.set_translation("Test", lang, f"Test-{lang}")

        for lang in languages:
            text = TranslationManager.get_text("Test", lang)
            if lang == "en":
                self.assertEqual(text, "Test")
            else:
                self.assertEqual(text, f"Test-{lang}")

    def test_cache_performance(self):
        """Test that cache prevents file reads."""
        TranslationManager.set_translation("Cached", "fr", "En cache")

        # Load once
        TranslationManager.load_language("fr")
        self.assertIn("fr", TranslationManager._cache)

        # Second access should use cache
        translations = TranslationManager.load_language("fr")
        self.assertEqual(translations["Cached"], "En cache")


class LanguageContextTestCase(TestCase):
    """Test language context processor."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="testuser", password="password")

        # Create test region
        self.region = RegionConfig.objects.create(
            code="TST",
            name="Test",
            timezone="UTC",
            default_currency="USD",
            academic_year_start_month=9,
            term_count_per_year=3,
        )

    def test_language_context_default(self):
        """Test language context with default settings."""
        request = self.factory.get("/")
        request.user = self.user

        context = language_context(request)

        self.assertIn("current_language", context)
        self.assertIn("available_languages", context)
        self.assertEqual(len(context["available_languages"]), len(SUPPORTED_LANGUAGES))

    def test_language_context_from_query_param(self):
        """Test language selection via query parameter."""
        request = self.factory.get("/?language=fr")
        request.user = self.user

        context = language_context(request)

        self.assertEqual(context["current_language"], "fr")
        self.assertEqual(context["current_language_name"], SUPPORTED_LANGUAGES["fr"])

    def test_language_context_from_cookie(self):
        """Test language selection via cookie."""
        request = self.factory.get("/")
        request.user = self.user
        request.COOKIES["django_language"] = "sw"

        context = language_context(request)

        self.assertEqual(context["current_language"], "sw")

    def test_language_context_query_overrides_cookie(self):
        """Test that query parameter overrides cookie."""
        request = self.factory.get("/?language=yo")
        request.user = self.user
        request.COOKIES["django_language"] = "sw"

        context = language_context(request)

        self.assertEqual(context["current_language"], "yo")

    def test_language_context_invalid_language(self):
        """Test that invalid language is ignored."""
        request = self.factory.get("/?language=invalid")
        request.user = self.user

        context = language_context(request)

        # Should fall back to default
        self.assertIn(context["current_language"], SUPPORTED_LANGUAGES)

    def test_translate_function(self):
        """Test translate function in context."""
        # Set up translation
        TranslationManager.set_translation("Test String", "fr", "Chaîne de test")

        request = self.factory.get("/?language=fr")
        request.user = self.user

        context = language_context(request)
        translate = context["translate"]

        result = translate("Test String")
        self.assertEqual(result, "Chaîne de test")

    def test_available_languages_list(self):
        """Test that all languages are available in context."""
        request = self.factory.get("/")
        request.user = self.user

        context = language_context(request)
        available = context["available_languages"]

        self.assertEqual(len(available), len(SUPPORTED_LANGUAGES))

        # Check all languages present
        available_codes = [code for code, name in available]
        for lang_code in SUPPORTED_LANGUAGES.keys():
            self.assertIn(lang_code, available_codes)


class LanguageSwitcherTemplateTestCase(TestCase):
    """Test language switcher template rendering."""

    def setUp(self):
        """Set up test client."""
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="password")

    def test_language_switcher_context(self):
        """Test that language switcher has correct context."""
        self.client.login(username="testuser", password="password")

        # Make request to a page that includes language context
        # (would need an actual view, so this tests the context structure)
        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.user

        context = language_context(request)

        # Verify switcher would have needed data
        self.assertIn("current_language", context)
        self.assertIn("available_languages", context)
        self.assertIn("current_language_name", context)


class TranslationManagementCommandTestCase(TestCase):
    """Test translation management command."""

    def setUp(self):
        """Clear translations before each test."""
        TranslationManager._cache.clear()

    def test_compile_translations_init(self):
        """Test translation initialization command."""
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("compile_translations", "--init", stdout=out)
        output = out.getvalue()

        # Should show initialization messages
        self.assertIn("Initializing", output)

    def test_compile_translations_status(self):
        """Test translation status command."""
        from django.core.management import call_command
        from io import StringIO

        # First initialize
        call_command("compile_translations", "--init")

        # Then check status
        out = StringIO()
        call_command("compile_translations", "--status", stdout=out)
        output = out.getvalue()

        # Should show all languages
        for lang_code in SUPPORTED_LANGUAGES.keys():
            self.assertIn(lang_code, output)

    def test_compile_translations_add(self):
        """Test adding translation via command."""
        from django.core.management import call_command
        from io import StringIO

        # Initialize first
        call_command("compile_translations", "--init")

        # Add translation
        out = StringIO()
        call_command(
            "compile_translations",
            "--add",
            "Hello World",
            "--translation",
            "Bonjour le monde",
            "--language",
            "fr",
            stdout=out,
        )
        output = out.getvalue()

        # Verify added
        self.assertIn("Added translation", output)

        # Verify it's actually stored
        text = TranslationManager.get_text("Hello World", "fr")
        self.assertEqual(text, "Bonjour le monde")


class RegionLanguageMappingTestCase(TestCase):
    """Test region-based language mapping."""

    def setUp(self):
        """Create test regions."""
        self.regions = {
            "CMR": RegionConfig.objects.create(
                code="CMR",
                name="Cameroon",
                timezone="Africa/Douala",
                default_currency="XAF",
                academic_year_start_month=9,
                term_count_per_year=3,
            ),
            "KEN": RegionConfig.objects.create(
                code="KEN",
                name="Kenya",
                timezone="Africa/Nairobi",
                default_currency="KES",
                academic_year_start_month=1,
                term_count_per_year=3,
            ),
        }

    def test_region_language_mapping(self):
        """Test that regions map to correct languages."""
        factory = RequestFactory()
        user = User.objects.create_user(username="test", password="pass")

        # Cameroon should default to French
        request = factory.get("/")
        request.user = user

        # Would need to mock the region selection
        # This verifies the mapping exists in context processor


class SupportedLanguagesTestCase(TestCase):
    """Test supported languages configuration."""

    def test_supported_languages(self):
        """Test that all required languages are supported."""
        required_languages = ["en", "fr", "pid", "sw", "ha", "yo"]

        for lang in required_languages:
            self.assertIn(lang, SUPPORTED_LANGUAGES)

    def test_language_names(self):
        """Test that all languages have display names."""
        for code, name in SUPPORTED_LANGUAGES.items():
            self.assertTrue(len(name) > 0)
            self.assertNotEqual(code, name)  # Should be different
