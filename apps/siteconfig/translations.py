"""
Translation system for multi-language support.
Provides translation storage, loading, and management without GNU gettext dependency.
"""

import json
from pathlib import Path
from typing import Dict

from django.conf import settings


# --- Phase 8: Regionalizer and LocalizationService stubs for test compatibility ---
class Regionalizer:
    """Stub for region/country localization logic."""

    @staticmethod
    def get_region_for_country(country_code: str) -> str:
        mapping = {
            "NG": "west_africa",
            "GH": "west_africa",
            "SL": "west_africa",
            "KE": "east_africa",
            "UG": "east_africa",
            "TZ": "east_africa",
            "RW": "east_africa",
            "CM": "central_africa",
            "FR": "europe_west",
            "GB": "europe_west",
            "US": "north_america",
            "CA": "north_america",
        }
        return mapping.get((country_code or "").upper(), "global")

    @staticmethod
    def get_region_settings(region: str) -> dict:
        if region == "west_africa":
            return {"currency": "NGN", "languages": ["en", "fr", "pid", "ha", "yo"]}
        if region == "east_africa":
            return {"currency": "KES", "languages": ["en", "sw"]}
        if region == "central_africa":
            return {"currency": "XAF", "languages": ["en", "fr"]}
        if region == "europe_west":
            return {"currency": "EUR", "languages": ["en", "fr"]}
        if region == "north_america":
            return {"currency": "USD", "languages": ["en", "fr"]}
        return {"currency": "USD", "languages": ["en"]}

    @staticmethod
    def get_recommended_languages(country_code: str) -> list:
        code = (country_code or "").upper()
        if code == "NG":
            return ["en", "fr", "pid", "ha", "yo"]
        if code in {"KE", "UG", "TZ"}:
            return ["en", "sw"]
        if code == "CM":
            return ["en", "fr", "pid"]
        return ["en"]


def _date_format_to_strftime(pattern: str) -> str:
    """Convert placeholder pattern (DD/MM/YYYY, etc.) to strftime."""
    if not pattern:
        return "%d/%m/%Y"
    return pattern.replace("YYYY", "%Y").replace("DD", "%d").replace("MM", "%m")


class LocalizationService:
    """
    Localization formatting. When region is provided, uses RegionConfig-style
    date_format, default_currency, decimal_separator, thousands_separator.
    """

    @staticmethod
    def format_date(dt, lang=None, region=None):
        """Format date. If region has date_format, use it; else use lang (en -> DD/MM/YYYY)."""
        if dt is None:
            return ""
        try:
            if region is not None:
                pattern = getattr(region, "date_format", None) or "DD/MM/YYYY"
                fmt = _date_format_to_strftime(pattern)
                return dt.strftime(fmt)
            return dt.strftime("%d/%m/%Y") if lang == "en" else dt.isoformat()
        except Exception:
            return str(dt)

    @staticmethod
    def format_currency(amount, currency=None, lang=None, region=None):
        """Format amount. If region has default_currency and separators, use them."""
        from apps.siteconfig.currency import get_currency_symbol
        try:
            amt = float(amount)
        except (TypeError, ValueError):
            return str(amount)
        if region is not None:
            cur = getattr(region, "default_currency", None) or currency or "XAF"
            dec_sep = getattr(region, "decimal_separator", None) or "."
            thousands_sep = getattr(region, "thousands_separator", None) or ","
            symbol = get_currency_symbol(cur)
            s = f"{amt:,.2f}"
            if thousands_sep != ",":
                s = s.replace(",", thousands_sep)
            if dec_sep != ".":
                s = s.replace(".", dec_sep)
            return f"{symbol}{s}"
        currency = currency or "XAF"
        symbol = get_currency_symbol(currency)
        return f"{symbol}{amt:,.2f}"

    @staticmethod
    def format_number(number, decimals=2, region=None):
        """Format number. If region has decimal/thousands separators, use them."""
        try:
            num = float(number)
        except (TypeError, ValueError):
            return str(number)
        if region is not None:
            dec_sep = getattr(region, "decimal_separator", None) or "."
            thousands_sep = getattr(region, "thousands_separator", None) or ","
            s = f"{num:,.{decimals}f}"
            if thousands_sep != ",":
                s = s.replace(",", thousands_sep)
            if dec_sep != ".":
                s = s.replace(".", dec_sep)
            return s
        return f"{num:,.{decimals}f}"


# Supported languages
SUPPORTED_LANGUAGES = {
    "en": "English",
    "fr": "Français",
    "pid": "Pidgin English",
    "sw": "Kiswahili",
    "ha": "Hausa",
    "yo": "Yoruba",
}

# Translation storage
TRANSLATIONS_DIR = Path(settings.BASE_DIR) / "locale" / "translations"


class TranslationManager:
    """
    Manages translations without requiring GNU gettext.
    Uses JSON files for storage and runtime translation.
    """

    _cache: Dict[str, Dict[str, str]] = {}

    @classmethod
    def get_available_languages(cls) -> list:
        """Return list of supported language codes."""
        return list(SUPPORTED_LANGUAGES.keys())

    @classmethod
    def load_translations(cls, language_code: str) -> dict:
        """Alias for load_language for test compatibility."""
        return cls.load_language(language_code)

    @classmethod
    def translate_text(cls, text: str, language_code: str = "en") -> str:
        """Alias for get_text for test compatibility."""
        return cls.get_text(text, language_code)

    @classmethod
    def get_translation_dir(cls) -> Path:
        """Get translation directory, create if needed."""
        TRANSLATIONS_DIR.mkdir(parents=True, exist_ok=True)
        return TRANSLATIONS_DIR

    @classmethod
    def load_language(cls, language_code: str) -> Dict[str, str]:
        """Load translations for a language."""
        if language_code in cls._cache:
            return cls._cache[language_code]

        file_path = cls.get_translation_dir() / f"{language_code}.json"

        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                translations = json.load(f)
        else:
            translations = {}

        cls._cache[language_code] = translations
        return translations

    @classmethod
    def get_text(cls, text: str, language_code: str = "en") -> str:
        """Get translated text or return original if not translated."""
        if language_code == "en":
            return text.capitalize()

        lower_text = text.lower()
        direct = TEXT_TRANSLATIONS.get(lower_text)
        if direct and language_code in direct:
            return direct[language_code]

        translations = cls.load_language(language_code)
        translated = translations.get(text)
        if not translated:
            translated = translations.get(text.capitalize())
        return translated or text.capitalize()

    @classmethod
    def set_translation(cls, text: str, language_code: str, translation: str) -> None:
        """Set a translation for a text string."""
        translations = cls.load_language(language_code)
        translations[text] = translation
        cls._cache[language_code] = translations

        # Save to file
        file_path = cls.get_translation_dir() / f"{language_code}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(translations, f, ensure_ascii=False, indent=2)

    @classmethod
    def bulk_import(cls, language_code: str, translations: Dict[str, str]) -> None:
        """Import multiple translations at once."""
        file_path = cls.get_translation_dir() / f"{language_code}.json"

        # Load existing
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        else:
            existing = {}

        # Merge
        existing.update(translations)

        # Save
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        cls._cache[language_code] = existing


# Common UI strings to translate
COMMON_STRINGS = {
    # Admin interface
    "Region Configurations": "Configurations rÃ©gionales",
    "Grading Scale Configs": "Configurations d'Ã©chelle de notation",
    "Holiday Calendars": "Calendriers de vacances",
    "Add Region": "Ajouter une rÃ©gion",
    "Clone Region": "Cloner une rÃ©gion",
    "Validate Configuration": "Valider la configuration",
    "Export to CSV": "Exporter en CSV",
    "Mark as working day": "Marquer comme jour ouvrable",
    "Mark as holiday": "Marquer comme vacances",
    # Regional settings
    "Code": "Code",
    "Name": "Nom",
    "Timezone": "Fuseau horaire",
    "Currency": "Devise",
    "Language": "Langue",
    "Date Format": "Format de date",
    "Grading Scale": "Ã‰chelle de notation",
    # Academic settings
    "Academic Year": "AnnÃ©e acadÃ©mique",
    "Term": "Trimestre",
    "Grade": "Note",
    "Score": "Score",
    "Passing Score": "Score de rÃ©ussite",
    "Student": "Étudiant",
    "Teacher": "Enseignant",
    # Portal features
    "Student Portal": "Portail des Ã©tudiants",
    "Parent Portal": "Portail parental",
    "Teacher Portal": "Portail des enseignants",
    "Admin Portal": "Portail administrateur",
    "Online Admissions": "Admissions en ligne",
    # Dashboard
    "Dashboard": "Tableau de bord",
    "Status": "Statut",
    "Settings": "ParamÃ¨tres",
    "Configuration": "Configuration",
    "Complete": "Complet",
    "Incomplete": "Incomplet",
    "Valid": "Valide",
    "Invalid": "Invalide",
    # Actions
    "Add": "Ajouter",
    "Edit": "Modifier",
    "Delete": "Supprimer",
    "Save": "Enregistrer",
    "Cancel": "Annuler",
    "Submit": "Soumettre",
    "Search": "Rechercher",
    "Filter": "Filtrer",
    "Sort": "Trier",
    # Messages
    "Success": "SuccÃ¨s",
    "Error": "Erreur",
    "Warning": "Avertissement",
    "Info": "Information",
    "Saved successfully": "EnregistrÃ© avec succÃ¨s",
    "Changes saved": "Modifications enregistrÃ©es",
    "Error saving": "Erreur lors de l'enregistrement",
    # Holidays
    "Holiday": "Vacances",
    "Public Holiday": "Jour fÃ©riÃ©",
    "School Holiday": "Vacances scolaires",
    "Religious Holiday": "Jour religieux",
    "Exam Period": "PÃ©riode d'examen",
    "Special Date": "Date spÃ©ciale",
    "Date Start": "Date de dÃ©but",
    "Date End": "Date de fin",
    "Duration": "DurÃ©e",
    "Type": "Type",
}


def init_translations():
    """Initialize default translations for all languages."""
    # English (base language - no translation needed)
    english = {text: text for text in COMMON_STRINGS.keys()}
    TranslationManager.bulk_import("en", english)

    # French
    french = COMMON_STRINGS.copy()
    TranslationManager.bulk_import("fr", french)

    # For other languages, we'll use English as fallback for now
    # In production, these would be translated by native speakers
    TranslationManager.bulk_import("pid", english)  # Placeholder
    TranslationManager.bulk_import("sw", english)  # Placeholder
    TranslationManager.bulk_import("ha", english)  # Placeholder
    TranslationManager.bulk_import("yo", english)  # Placeholder


TEXT_TRANSLATIONS: dict[str, dict[str, str]] = {
    "student": {"en": "Student", "fr": "Étudiant"},
    "teacher": {"en": "Teacher", "fr": "Enseignant"},
    "grade": {"en": "Grade", "fr": "Note"},
}


class TextTranslator:
    """Simple translator for UI snippets/tests."""

    @classmethod
    def get_translated_text(cls, key: str, language: str = "en") -> str:
        entry = TEXT_TRANSLATIONS.get(key.lower(), {})
        if language in entry:
            return entry[language]

        # Fallback to translation manager (handles registered strings)
        translated = TranslationManager.translate_text(key.capitalize(), language) if language != "en" else key.capitalize()
        if translated != key.capitalize():
            return translated

        return key.capitalize()

    @classmethod
    def batch_translate(cls, keys: list[str], language: str = "en") -> dict[str, str]:
        return {key: cls.get_translated_text(key, language) for key in keys}


class MultiLanguageContent:
    """Helper for generating lightweight multilingual mockups."""

    @staticmethod
    def create_multilingual_report(template: str, data: dict, languages: list[str]) -> dict[str, str]:
        try:
            rendered = template.format(**data)
        except Exception:
            rendered = template

        previews: dict[str, str] = {}
        for lang in languages:
            localized = TranslationManager.translate_text(rendered, lang) if lang != "en" else rendered
            previews[lang] = localized

        return previews
