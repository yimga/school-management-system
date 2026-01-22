"""
Phase 8 Task 5: Internationalization and Localization
Multi-language support, regional customization, and translations
"""

import json
from pathlib import Path
from django.utils import timezone
from django.utils.translation import get_language, activate


class TranslationManager:
    """Manage translations and localization"""
    
    SUPPORTED_LANGUAGES = {
        'en': 'English',
        'fr': 'Français',
        'sw': 'Kiswahili',
        'ha': 'Hausa',
        'yo': 'Yorùbá',
        'pid': 'Pidgin English',
    }
    
    TRANSLATIONS_DIR = Path(__file__).parent.parent / 'locale' / 'translations'
    
    @classmethod
    def get_available_languages(cls):
        """Get list of available languages"""
        return cls.SUPPORTED_LANGUAGES
    
    @classmethod
    def load_translations(cls, language_code):
        """Load translation file for language"""
        trans_file = cls.TRANSLATIONS_DIR / f'{language_code}.json'
        
        if not trans_file.exists():
            return {}
        
        with open(trans_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def translate_text(cls, text, language_code='en'):
        """Translate text to specified language"""
        translations = cls.load_translations(language_code)
        return translations.get(text, text)
    
    @classmethod
    def get_current_language_name(cls):
        """Get name of current language"""
        current = get_language()
        return cls.SUPPORTED_LANGUAGES.get(current, 'English')


class Regionalizer:
    """Handle regional customization"""
    
    REGIONS = {
        'west_africa': {
            'countries': ['NG', 'GH', 'SN', 'CI', 'BJ', 'TG', 'LR', 'SL'],
            'languages': ['en', 'fr', 'ha', 'yo', 'pid'],
            'currency': 'NGN',
            'date_format': 'DD/MM/YYYY',
            'time_format': 'HH:MM',
        },
        'east_africa': {
            'countries': ['KE', 'TZ', 'UG', 'ET', 'DJ', 'SO'],
            'languages': ['en', 'sw'],
            'currency': 'KES',
            'date_format': 'DD/MM/YYYY',
            'time_format': 'HH:MM',
        },
        'central_africa': {
            'countries': ['CM', 'CG', 'CD', 'GA', 'CF', 'TD'],
            'languages': ['en', 'fr'],
            'currency': 'XAF',
            'date_format': 'DD/MM/YYYY',
            'time_format': 'HH:MM',
        },
        'southern_africa': {
            'countries': ['ZA', 'BW', 'ZW', 'NA', 'MZ'],
            'languages': ['en'],
            'currency': 'ZAR',
            'date_format': 'YYYY/MM/DD',
            'time_format': 'HH:MM',
        },
    }
    
    @classmethod
    def get_region_for_country(cls, country_code):
        """Get region for country code"""
        for region, data in cls.REGIONS.items():
            if country_code in data['countries']:
                return region
        return None
    
    @classmethod
    def get_region_settings(cls, region):
        """Get settings for region"""
        return cls.REGIONS.get(region, {})
    
    @classmethod
    def get_recommended_languages(cls, country_code):
        """Get recommended languages for country"""
        region = cls.get_region_for_country(country_code)
        if region:
            return cls.REGIONS[region]['languages']
        return ['en']


class LocalizationService:
    """Localization service for reports and documents"""
    
    DATE_FORMATS = {
        'en': '%d/%m/%Y',
        'fr': '%d/%m/%Y',
        'sw': '%d/%m/%Y',
        'ha': '%d/%m/%Y',
        'yo': '%d/%m/%Y',
        'pid': '%d/%m/%Y',
    }
    
    CURRENCY_SYMBOLS = {
        'NGN': '₦',
        'KES': 'Ksh',
        'XAF': 'Fr',
        'ZAR': 'R',
        'USD': '$',
        'EUR': '€',
    }
    
    CURRENCY_DECIMALS = {
        'NGN': 2,
        'KES': 2,
        'XAF': 0,
        'ZAR': 2,
    }
    
    @classmethod
    def format_date(cls, date, language_code='en'):
        """Format date according to locale"""
        date_format = cls.DATE_FORMATS.get(language_code, '%d/%m/%Y')
        return date.strftime(date_format)
    
    @classmethod
    def format_currency(cls, amount, currency_code, language_code='en'):
        """Format currency with locale settings"""
        symbol = cls.CURRENCY_SYMBOLS.get(currency_code, currency_code)
        decimals = cls.CURRENCY_DECIMALS.get(currency_code, 2)
        
        formatted = f"{symbol}{amount:,.{decimals}f}"
        return formatted
    
    @classmethod
    def format_number(cls, number, decimals=2):
        """Format number with thousand separators"""
        return f"{number:,.{decimals}f}"
    
    @classmethod
    def localize_report_dates(cls, report_data, language_code='en'):
        """Localize dates in report"""
        localized = report_data.copy()
        
        for key, value in localized.items():
            if isinstance(value, timezone.datetime):
                localized[key] = cls.format_date(value, language_code)
        
        return localized


class MultiLanguageContent:
    """Manage multi-language content"""
    
    @staticmethod
    def create_multilingual_report(report_template, data, language_codes=None):
        """Create report in multiple languages"""
        if language_codes is None:
            language_codes = ['en', 'fr']
        
        reports = {}
        
        for lang in language_codes:
            reports[lang] = {
                'language': lang,
                'template': report_template,
                'data': data,
                'created_at': timezone.now().isoformat(),
            }
        
        return reports
    
    @staticmethod
    def get_localized_email_template(template_name, language_code='en'):
        """Get email template in specified language"""
        from django.template.loader import render_to_string
        
        template_path = f'emails/{template_name}_{language_code}.html'
        
        try:
            return render_to_string(template_path)
        except:
            # Fallback to English
            return render_to_string(f'emails/{template_name}_en.html')


class TextTranslator:
    """Text translation utilities"""
    
    COMMON_TRANSLATIONS = {
        'en': {
            'student': 'Student',
            'teacher': 'Teacher',
            'grade': 'Grade',
            'score': 'Score',
            'class': 'Class',
            'subject': 'Subject',
            'pass': 'Pass',
            'fail': 'Fail',
        },
        'fr': {
            'student': 'Étudiant',
            'teacher': 'Enseignant',
            'grade': 'Note',
            'score': 'Score',
            'class': 'Classe',
            'subject': 'Matière',
            'pass': 'Réussi',
            'fail': 'Échoué',
        },
        'sw': {
            'student': 'Mwanafunzi',
            'teacher': 'Mwalimu',
            'grade': 'Daraja',
            'score': 'Alama',
            'class': 'Darasa',
            'subject': 'Somo',
            'pass': 'Kupita',
            'fail': 'Kushindwa',
        },
    }
    
    @classmethod
    def get_translated_text(cls, key, language_code='en'):
        """Get translated text"""
        lang_dict = cls.COMMON_TRANSLATIONS.get(language_code, {})
        return lang_dict.get(key, key)
    
    @classmethod
    def batch_translate(cls, text_keys, language_code='en'):
        """Batch translate multiple texts"""
        return {
            key: cls.get_translated_text(key, language_code)
            for key in text_keys
        }
