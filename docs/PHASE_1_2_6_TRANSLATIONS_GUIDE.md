# Phase 1.2.6: Multi-Language Translations Guide

**Status**: ✅ COMPLETE  
**Version**: 1.0  
**Last Updated**: January 2025

## Overview

Phase 1.2.6 implements a comprehensive multi-language translation system for the school management platform. The system supports 6 languages with region-based auto-detection and persistent user preferences.

**Supported Languages**:
- English (en) - Default
- French (fr) - Français
- Pidgin English (pid) - Nigerian Pidgin
- Swahili (sw) - Kiswahili
- Hausa (ha) - Hausa
- Yoruba (yo) - Yoruba

## Architecture

### Design Philosophy

The translation system was designed with the following principles:

1. **No External Dependencies**: Pure Python implementation, no GNU gettext required
2. **Windows Compatible**: Works seamlessly on Windows, macOS, and Linux
3. **Human Editable**: JSON-based storage for easy manual updates
4. **Portable**: Simple backup/restore via JSON export/import
5. **Performant**: In-memory caching prevents repeated file reads
6. **Extensible**: Easy to add new languages or strings

### System Components

#### 1. TranslationManager (`apps/siteconfig/translations.py`)

Core class managing all translation operations.

```python
TranslationManager.load_language(code)      # Load translations with caching
TranslationManager.get_text(text, lang)     # Get translated text or original
TranslationManager.set_translation(...)     # Set single translation + save
TranslationManager.bulk_import(lang, dict)  # Import multiple translations
```

**Storage Location**: `locale/translations/{language_code}.json`

**Example**:
```json
{
  "Hello": "Bonjour",
  "Good Morning": "Bon matin",
  "Students": "Étudiants"
}
```

#### 2. Language Context Processor (`apps/siteconfig/context_processors.py`)

Makes translation system available to all Django templates.

**Function**: `language_context(request)`

**Returns**:
- `current_language`: Active language code (e.g., 'fr')
- `current_language_name`: Display name (e.g., 'Français')
- `available_languages`: List of (code, name) tuples
- `supported_languages`: Full SUPPORTED_LANGUAGES dict
- `translate`: Function for in-template translation

**Language Detection Priority**:
1. URL parameter: `?language=CODE`
2. Browser cookie: `django_language`
3. User region setting (auto-detect)
4. Fallback: English

#### 3. Language Switcher (`templates/partials/language_switcher.html`)

Bootstrap dropdown UI for language selection.

**Features**:
- Displays available languages with native names
- Shows current language as active
- Persists preference in localStorage and cookie
- Auto-restores on page reload
- Graceful reload on language change

**Usage in Template**:
```django
<nav>
  {% include 'partials/language_switcher.html' %}
</nav>
```

#### 4. Management Command (`compile_translations.py`)

CLI tool for translation operations and maintenance.

```bash
python manage.py compile_translations --init          # Initialize all languages
python manage.py compile_translations --status        # Show statistics
python manage.py compile_translations --add "Text" --translation "Traduction" --language fr
python manage.py compile_translations --export backup.json
python manage.py compile_translations --import backup.json
```

## Region-Based Language Mapping

Automatic language detection based on user's school region:

| Region | Code | Default Language |
|--------|------|-------------------|
| Cameroon | CMR | French (fr) |
| France | FRA | French (fr) |
| USA | USA | English (en) |
| United Kingdom | GBR | English (en) |
| Germany | DEU | English (en) |
| Kenya | KEN | Swahili (sw) |
| Nigeria | NGA | Yoruba (yo) |

## Common UI Strings

The system includes 60+ pre-translated common UI strings. Currently translated:

- **English**: All 60+ strings (base language)
- **French**: All 60+ strings
- **Pidgin, Swahili, Hausa, Yoruba**: 60 strings each (English fallback for untranslated)

**Common Strings** (`COMMON_STRINGS` dict):
```
- Region Configurations
- Grading Scales
- Holiday Calendars
- Students
- Teachers
- Academics
- Dashboard
- Settings
- [and 50+ more...]
```

## Usage Examples

### In Django Templates

**Simple Translation**:
```django
<h1>{{ translate "Welcome" }}</h1>
```

**Conditional Translation**:
```django
{% if current_language == 'fr' %}
  <p>Bienvenue</p>
{% else %}
  <p>Welcome</p>
{% endif %}
```

**Language Display**:
```django
<span>Current: {{ current_language_name }}</span>
```

**Language Switcher**:
```django
{% include 'partials/language_switcher.html' %}
```

### In Python Views

**Get Current Language**:
```python
from django.utils import translation
current_lang = translation.get_language()
```

**Translate Text**:
```python
from apps.siteconfig.translations import TranslationManager

text = TranslationManager.get_text("Hello", "fr")  # Returns "Bonjour"
```

**Add Translation Programmatically**:
```python
TranslationManager.set_translation("New String", "fr", "Nouvelle Chaîne")
```

### In Management Commands

**Initialize All Languages**:
```bash
python manage.py compile_translations --init
```

**Show Translation Status**:
```bash
python manage.py compile_translations --status
```

**Backup Translations**:
```bash
python manage.py compile_translations --export translations_backup.json
```

**Restore Translations**:
```bash
python manage.py compile_translations --import translations_backup.json
```

## Adding New Translations

### Method 1: Via Management Command

```bash
python manage.py compile_translations \
  --add "Welcome to School" \
  --translation "Bienvenue à l'École" \
  --language fr
```

### Method 2: Direct File Editing

Edit `locale/translations/{language_code}.json`:

```json
{
  "Hello": "Bonjour",
  "Welcome": "Bienvenue",
  "Dashboard": "Tableau de bord"
}
```

### Method 3: Bulk Import

Create `new_strings.json`:
```json
{
  "timestamp": "2025-01-18T12:00:00",
  "languages": {
    "fr": {
      "New String 1": "Nouvelle Chaîne 1",
      "New String 2": "Nouvelle Chaîne 2"
    },
    "sw": {
      "New String 1": "Kamba Mpya 1"
    }
  }
}
```

Then import:
```bash
python manage.py compile_translations --import new_strings.json
```

## Adding New Languages

### Step 1: Update SUPPORTED_LANGUAGES

Edit `apps/siteconfig/translations.py`:

```python
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'fr': 'Français',
    'pid': 'Pidgin English',
    'sw': 'Kiswahili',
    'ha': 'Hausa',
    'yo': 'Yoruba',
    'es': 'Español',  # New language
}
```

### Step 2: Update Region Mapping

Edit `apps/siteconfig/context_processors.py`:

```python
region_to_language = {
    'CMR': 'fr',
    'KEN': 'sw',
    'NGA': 'yo',
    'MEX': 'es',  # New region
}
```

### Step 3: Initialize Translations

```bash
python manage.py compile_translations --init
```

### Step 4: Translate Strings

Add translations to `locale/translations/es.json` or use management command:

```bash
python manage.py compile_translations --add "Hello" --translation "Hola" --language es
```

## Integration Checklist

### Dashboard & Admin

- [ ] Include language switcher in admin navbar
- [ ] Add to Django admin template
- [ ] Test language switching in admin

### User Portals

- [ ] Add language switcher to student portal
- [ ] Add language switcher to parent portal
- [ ] Add language switcher to teacher portal
- [ ] Add language switcher to admin portal

### Testing

- [ ] Test language persistence across page navigation
- [ ] Test cookie synchronization with localStorage
- [ ] Test auto-language detection by region
- [ ] Test translation fallback for missing strings
- [ ] Test management commands
- [ ] Test performance (caching works)

## Performance Considerations

### Caching Strategy

Translations are loaded once per language and cached in memory. Subsequent accesses use the cache:

```python
# First access: Reads from file
text = TranslationManager.get_text("Hello", "fr")  # File read

# Second access: Uses cache
text = TranslationManager.get_text("Hello", "fr")  # No file read
```

### Cache Management

Clear cache when needed:
```python
TranslationManager._cache.clear()  # Forces reload from files
```

Or via management command:
```bash
python manage.py compile_translations --rebuild
```

## Testing

### Running Tests

```bash
python manage.py test apps.siteconfig.tests.test_translations
```

### Test Coverage

- ✅ Translation loading and caching
- ✅ Text retrieval with fallback
- ✅ Setting translations
- ✅ Bulk import operations
- ✅ Language context processor
- ✅ Language detection priority
- ✅ Query parameter overrides
- ✅ Cookie persistence
- ✅ Supported languages configuration
- ✅ Management command operations

**Total Tests**: 22 passing

## File Locations

```
apps/
  siteconfig/
    translations.py                    # Core TranslationManager class
    context_processors.py              # Language context processor
    management/
      commands/
        compile_translations.py        # CLI management tool
    tests/
      test_translations.py             # 22 test cases
      
templates/
  partials/
    language_switcher.html             # UI component

locale/
  translations/
    en.json                            # English strings
    fr.json                            # French strings
    pid.json                           # Pidgin strings
    sw.json                            # Swahili strings
    ha.json                            # Hausa strings
    yo.json                            # Yoruba strings
```

## Troubleshooting

### Issue: Translations Not Appearing

**Solution**: 
1. Verify language file exists: `ls locale/translations/`
2. Check translation exists: `python manage.py compile_translations --status`
3. Clear cache: `python manage.py compile_translations --rebuild`
4. Restart Django server

### Issue: Language Not Switching

**Solution**:
1. Check browser localStorage: DevTools > Application > LocalStorage
2. Verify cookie: DevTools > Application > Cookies
3. Check context processor registered: Look in `config/settings.py`
4. Test: `?language=fr` in URL

### Issue: Performance Slow

**Solution**:
1. Verify caching working: Check `TranslationManager._cache`
2. Monitor file size: `ls -lh locale/translations/`
3. Reduce translation strings if excessive
4. Check Django DEBUG mode (disable in production)

## Best Practices

1. **Use English as Base**: Always define English string first
2. **Organize by Module**: Group related translations
3. **Keep Strings Short**: For UI consistency
4. **Test Translations**: Verify rendering in templates
5. **Backup Regularly**: Export translations before major changes
6. **Version Control**: Commit translation files to git
7. **Document Strings**: Use clear, descriptive keys
8. **Lazy Translation**: Use lazy evaluation in views where needed

## Future Enhancements

Planned improvements for future phases:

1. **Automated Translation**: Integrate translation API (Google, Azure)
2. **Translation Versioning**: Track translation history
3. **Admin UI**: Web interface for managing translations
4. **RTL Support**: Right-to-left language support
5. **Pluralization**: Handle singular/plural forms
6. **Context Variables**: Support dynamic values in translations
7. **Translation Workflow**: Approve/review translations
8. **Analytics**: Track which strings are translated

## References

### Related Documentation

- [Phase 1.2.4: Internationalization](PHASE_1_2_4_INTERNATIONALIZATION.md)
- [Phase 1.2.5: Admin Guide](PHASE_1_2_5_ADMIN_GUIDE.md)

### Django Documentation

- [Django Internationalization](https://docs.djangoproject.com/en/stable/topics/i18n/)
- [Context Processors](https://docs.djangoproject.com/en/stable/ref/templates/api/#django.template.context_processors)
- [Management Commands](https://docs.djangoproject.com/en/stable/howto/custom-management-commands/)

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review test cases for usage examples
3. Check Django logs: `tail -f logs/django.log`
4. Review management command help: `python manage.py compile_translations --help`

## Change Log

### Version 1.0 (January 2025)
- ✅ Initial release
- ✅ TranslationManager class
- ✅ Language context processor
- ✅ Language switcher UI
- ✅ Management command
- ✅ 22 test cases
- ✅ 60+ common UI strings
- ✅ Full documentation
