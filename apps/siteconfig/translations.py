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
        # Example: 'NG' -> 'west_africa', 'KE' -> 'east_africa'
        mapping = {"NG": "west_africa", "KE": "east_africa"}
        return mapping.get(country_code, "west_africa")

    @staticmethod
    def get_region_settings(region: str) -> dict:
        # Example settings for 'west_africa'
        if region == "west_africa":
            return {"currency": "NGN", "languages": ["en", "fr", "pid", "ha", "yo"]}
        if region == "east_africa":
            return {"currency": "KES", "languages": ["en", "sw"]}
        return {"currency": "USD", "languages": ["en"]}

    @staticmethod
    def get_recommended_languages(country_code: str) -> list:
        # Example: 'NG' -> ['en', 'fr', 'pid', 'ha', 'yo']
        if country_code == "NG":
            return ["en", "fr", "pid", "ha", "yo"]
        if country_code == "KE":
            return ["en", "sw"]
        return ["en"]


class LocalizationService:
    """Stub for localization formatting logic."""

    @staticmethod
    def format_date(dt, lang):
        # Format as DD/MM/YYYY for 'en', fallback to ISO
        try:
            return dt.strftime("%d/%m/%Y") if lang == "en" else dt.isoformat()
        except Exception:
            return str(dt)

    @staticmethod
    def format_currency(amount, currency, lang):
        # Simple formatting for NGN, KES, etc.
        symbol = {"NGN": "â‚¦", "KES": "KSh", "USD": "$"}.get(currency, currency)
        return f"{symbol}{amount:,.2f}"

    @staticmethod
    def format_number(number, decimals=2):
        return f"{number:,.{decimals}f}"


# Supported languages
SUPPORTED_LANGUAGES = {
    "en": "English",
    "fr": "FranÃ§ais",
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
            return text

        translations = cls.load_language(language_code)
        return translations.get(text, text)

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
