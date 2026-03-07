"""
Tests for report localization system.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.reports.localization import (
    CertificateLocalizer,
    TranscriptLocalizer,
    get_certificate_localizer,
    get_transcript_localizer,
)
from apps.siteconfig.models import RegionConfig, GradingScaleConfig
from apps.siteconfig.translations import SUPPORTED_LANGUAGES
from decimal import Decimal

User = get_user_model()


class CertificateLocalizerTestCase(TestCase):
    """Test certificate localization functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.region_cmr, _ = RegionConfig.objects.update_or_create(
            code='CMR',
            defaults={
                'name': 'Cameroon',
                'timezone': 'Africa/Douala',
                'default_currency': 'XAF',
                'academic_year_start_month': 9,
                'term_count_per_year': 3,
            },
        )
        self.region_ken, _ = RegionConfig.objects.update_or_create(
            code='KEN',
            defaults={
                'name': 'Kenya',
                'timezone': 'Africa/Nairobi',
                'default_currency': 'KES',
                'academic_year_start_month': 1,
                'term_count_per_year': 3,
            },
        )

    def test_certificate_localizer_english(self):
        """Test certificate localizer with English."""
        localizer = CertificateLocalizer(language='en')
        self.assertEqual(localizer.language, 'en')
        self.assertEqual(localizer.translate('certificate_of_achievement'), 'Certificate of Achievement')

    def test_certificate_localizer_french(self):
        """Test certificate localizer with French."""
        localizer = CertificateLocalizer(language='fr', region=self.region_cmr)
        self.assertEqual(localizer.language, 'fr')
        self.assertEqual(localizer.translate('certificate_of_achievement'), 'Certificat de Réussite')

    def test_certificate_localizer_swahili(self):
        """Test certificate localizer with Swahili."""
        localizer = CertificateLocalizer(language='sw', region=self.region_ken)
        self.assertEqual(localizer.language, 'sw')
        self.assertEqual(localizer.translate('certificate_of_achievement'), 'Cheti cha Mafanikio')

    def test_translate_all_keys(self):
        """Test that all language packs have same keys."""
        localizer_en = CertificateLocalizer(language='en')
        localizer_fr = CertificateLocalizer(language='fr')
        
        en_keys = set(localizer_en.strings.keys())
        fr_keys = set(localizer_fr.strings.keys())
        
        self.assertEqual(en_keys, fr_keys)

    def test_get_grade_letter_a(self):
        """Test grade letter for score >= 80."""
        localizer = CertificateLocalizer(language='en')
        self.assertEqual(localizer.get_grade_letter(85), 'A')

    def test_get_grade_letter_b(self):
        """Test grade letter for score 70-79."""
        localizer = CertificateLocalizer(language='en')
        self.assertEqual(localizer.get_grade_letter(75), 'B')

    def test_get_grade_letter_c(self):
        """Test grade letter for score 60-69."""
        localizer = CertificateLocalizer(language='en')
        self.assertEqual(localizer.get_grade_letter(65), 'C')

    def test_get_grade_letter_d(self):
        """Test grade letter for score 50-59."""
        localizer = CertificateLocalizer(language='en')
        self.assertEqual(localizer.get_grade_letter(55), 'D')

    def test_get_grade_letter_f(self):
        """Test grade letter for score < 50."""
        localizer = CertificateLocalizer(language='en')
        self.assertEqual(localizer.get_grade_letter(40), 'F')

    def test_performance_comment_excellent(self):
        """Test performance comment for high score."""
        localizer = CertificateLocalizer(language='en')
        self.assertEqual(localizer.get_performance_comment(85), 'Excellent')

    def test_performance_comment_french(self):
        """Test performance comment in French."""
        localizer = CertificateLocalizer(language='fr')
        self.assertEqual(localizer.get_performance_comment(85), 'Excellent')

    def test_performance_comment_poor(self):
        """Test performance comment for low score."""
        localizer = CertificateLocalizer(language='en')
        self.assertEqual(localizer.get_performance_comment(30), 'Needs Improvement')

    def test_get_certificate_context(self):
        """Test certificate context building."""
        student_data = {
            'student': 'John Doe',
            'academic_year': '2024-2025',
            'average': 75.5,
            'rank': 5,
            'promotion_status': 'PROMOTED',
            'date_issued': '2025-01-18',
        }
        
        localizer = CertificateLocalizer(language='en')
        context = localizer.get_certificate_context(student_data)
        
        self.assertEqual(context['language'], 'en')
        self.assertEqual(context['grade_letter'], 'B')
        self.assertEqual(context['student'], 'John Doe')

    def test_invalid_language_fallback(self):
        """Test that invalid language falls back to English."""
        localizer = CertificateLocalizer(language='invalid')
        self.assertEqual(localizer.language, 'en')

    def test_all_supported_languages(self):
        """Test that all supported languages work."""
        for language in SUPPORTED_LANGUAGES.keys():
            localizer = CertificateLocalizer(language=language)
            self.assertEqual(localizer.language, language)
            self.assertTrue(len(localizer.strings) > 0)


class TranscriptLocalizerTestCase(TestCase):
    """Test transcript localization functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.region_cmr, _ = RegionConfig.objects.update_or_create(
            code='CMR',
            defaults={
                'name': 'Cameroon',
                'timezone': 'Africa/Douala',
                'default_currency': 'XAF',
                'academic_year_start_month': 9,
                'term_count_per_year': 3,
            },
        )

    def test_transcript_localizer_init(self):
        """Test transcript localizer initialization."""
        localizer = TranscriptLocalizer(language='en', region=self.region_cmr)
        self.assertEqual(localizer.language, 'en')
        self.assertEqual(localizer.region, self.region_cmr)

    def test_convert_scores_for_transcript(self):
        """Test score conversion for transcript."""
        localizer = TranscriptLocalizer(language='en', region=self.region_cmr)
        
        scores = {
            'Mathematics': 75.0,
            'English': 85.0,
            'Science': 70.0,
        }
        
        converted = localizer.convert_scores_for_transcript(scores)
        
        self.assertEqual(len(converted), 3)
        self.assertIn('Mathematics', converted)
        self.assertTrue('grade_letter' in converted['Mathematics'])
        self.assertTrue('comment' in converted['Mathematics'])

    def test_convert_scores_with_conversion_scale(self):
        """Test score conversion with scale conversion."""
        localizer = TranscriptLocalizer(language='en', region=self.region_cmr)
        
        scores = {
            'Math': 75.0,
            'English': 85.0,
        }
        
        converted = localizer.convert_scores_for_transcript(
            scores,
            from_scale='0-100',
            to_scale='0-20'
        )
        
        self.assertEqual(len(converted), 2)
        self.assertTrue('converted' in converted['Math'])

    def test_format_transcript(self):
        """Test transcript formatting."""
        student_data = {
            'student_name': 'Jane Doe',
            'student_id': 'STU001',
            'academic_year': '2024-2025',
            'class': 'Form 3A',
            'scores': {
                'Math': 75.0,
                'English': 85.0,
                'Science': 80.0,
            },
            'average': 80.0,
            'date_issued': '2025-01-18',
        }
        
        localizer = TranscriptLocalizer(language='en', region=self.region_cmr)
        formatted = localizer.format_transcript(student_data)
        
        self.assertEqual(formatted['language'], 'en')
        self.assertEqual(formatted['student_name'], 'Jane Doe')
        self.assertEqual(formatted['student_id'], 'STU001')
        self.assertTrue('scores' in formatted)


class FactoryFunctionsTestCase(TestCase):
    """Test factory functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.region_cmr, _ = RegionConfig.objects.update_or_create(
            code='CMR',
            defaults={
                'name': 'Cameroon',
                'timezone': 'Africa/Douala',
                'default_currency': 'XAF',
                'academic_year_start_month': 9,
                'term_count_per_year': 3,
            },
        )

    def test_get_certificate_localizer(self):
        """Test certificate localizer factory."""
        localizer = get_certificate_localizer(language='fr', region_code='CMR')
        self.assertEqual(localizer.language, 'fr')
        self.assertEqual(localizer.region.code, 'CMR')

    def test_get_transcript_localizer(self):
        """Test transcript localizer factory."""
        localizer = get_transcript_localizer(language='sw', region_code='CMR')
        self.assertEqual(localizer.language, 'sw')
        self.assertEqual(localizer.region.code, 'CMR')

    def test_get_localizer_invalid_region(self):
        """Test localizer with invalid region."""
        localizer = get_certificate_localizer(language='en', region_code='INVALID')
        self.assertEqual(localizer.language, 'en')
        self.assertIsNone(localizer.region)


class LanguageConsistencyTestCase(TestCase):
    """Test language consistency across localizers."""

    def test_certificate_strings_consistency(self):
        """Test that all certificate strings are consistent."""
        strings_dict = CertificateLocalizer.CERTIFICATE_STRINGS
        
        # Get keys from English
        en_keys = set(strings_dict['en'].keys())
        
        # Check all languages have same keys
        for lang in strings_dict.keys():
            lang_keys = set(strings_dict[lang].keys())
            self.assertEqual(en_keys, lang_keys, f"Key mismatch in {lang}")

    def test_supported_languages_coverage(self):
        """Test that all supported languages have certificates."""
        supported = SUPPORTED_LANGUAGES.keys()
        certificate_langs = CertificateLocalizer.CERTIFICATE_STRINGS.keys()
        
        for lang in supported:
            self.assertIn(lang, certificate_langs, f"Missing certificate strings for {lang}")
