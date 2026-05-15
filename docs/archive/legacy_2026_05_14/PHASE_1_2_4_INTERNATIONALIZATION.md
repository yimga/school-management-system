# Phase 1.2.4: Internationalization & Multi-Region Support

## Objective
Transform the school management system from Cameroon-specific to globally flexible, supporting:
- Multiple languages (English, French, Cameroon Pidgin, and extensible for others)
- Multiple calendar systems (Gregorian, Islamic, Buddhist, etc.)
- Multiple grading scales (0-20 Cameroon, 0-100 US, 0-10 European, A-F, etc.)
- Multiple currencies (XAF, USD, EUR, GBP, etc.)
- Regional compliance (legal requirements, holidays, exam schedules)
- Time zones and localization
- Cultural/religious calendar considerations

## Architecture

### 1. Database Schema Changes
**New Models in `apps/siteconfig/models.py`:**

```python
class RegionConfig(models.Model):
    """Store region-specific settings."""
    CALENDAR_CHOICES = [
        ('gregorian', 'Gregorian'),
        ('islamic', 'Islamic'),
        ('buddhist', 'Buddhist'),
        ('hebrew', 'Hebrew'),
    ]
    GRADING_SCALE_CHOICES = [
        ('0-20', 'Cameroon (0-20)'),
        ('0-100', 'US/UK (0-100)'),
        ('0-10', 'European (0-10)'),
        ('a-f', 'Letter Grade (A-F)'),
        ('gpa', 'GPA (0-4.0)'),
    ]
    
    code = CharField(max_length=10, unique=True, primary_key=True)  # 'CMR', 'USA', 'KEN', etc.
    name = CharField(max_length=100)  # 'Cameroon', 'United States', 'Kenya'
    
    # Localization
    default_language = CharField(max_length=10, default='en')  # en, fr, pidgin, etc.
    timezone = CharField(max_length=50, default='UTC')
    decimal_separator = CharField(max_length=1, default='.')
    thousands_separator = CharField(max_length=1, default=',')
    date_format = CharField(max_length=20, default='DD/MM/YYYY')
    
    # Education system
    calendar_system = CharField(max_length=20, choices=CALENDAR_CHOICES, default='gregorian')
    grading_scale = CharField(max_length=20, choices=GRADING_SCALE_CHOICES, default='0-20')
    default_currency = CharField(max_length=3, default='XAF')
    
    # Academic structure
    academic_year_start_month = IntegerField(default=9)  # 1-12
    term_count_per_year = IntegerField(default=3)  # 2, 3, or 4 terms
    
    # Legal/compliance
    school_registration_number_format = CharField(max_length=100, blank=True)
    student_id_format = CharField(max_length=100, blank=True)
    certificate_template_name = CharField(max_length=100, default='standard')
    
    # Features
    enable_online_admissions = BooleanField(default=True)
    enable_parent_portal = BooleanField(default=True)
    enable_student_portal = BooleanField(default=True)
    
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Region Configurations"
    
    def __str__(self):
        return f"{self.name} ({self.code})"


class GradingScaleConfig(models.Model):
    """Define grading scales per region/school."""
    region = ForeignKey(RegionConfig, CASCADE, related_name='grading_scales')
    scale_type = CharField(max_length=20)  # '0-20', 'A-F', etc.
    min_score = DecimalField(max_digits=5, decimal_places=2)
    max_score = DecimalField(max_digits=5, decimal_places=2)
    
    # Conversion mapping for reports
    display_format = CharField(max_length=50)  # "{score:.0f}/20", "F", etc.
    
    # Grade ranges
    grade_a_min = DecimalField(max_digits=5, decimal_places=2)  # 18/20, 90/100, etc.
    grade_b_min = DecimalField(max_digits=5, decimal_places=2)
    grade_c_min = DecimalField(max_digits=5, decimal_places=2)
    grade_d_min = DecimalField(max_digits=5, decimal_places=2)
    grade_f_min = DecimalField(max_digits=5, decimal_places=2)
    
    created_at = DateTimeField(auto_now_add=True)


class HolidayCalendar(models.Model):
    """Store holidays and important dates per region."""
    region = ForeignKey(RegionConfig, CASCADE, related_name='holidays')
    academic_year = ForeignKey(AcademicYear, CASCADE, related_name='holidays_by_region')
    
    name = CharField(max_length=200)  # 'Christmas Break', 'Eid al-Fitr', etc.
    date_start = DateField()
    date_end = DateField()
    holiday_type = CharField(max_length=50, choices=[
        ('school_holiday', 'School Holiday'),
        ('public_holiday', 'Public Holiday'),
        ('exam_period', 'Exam Period'),
        ('religious', 'Religious Holiday'),
    ])
    
    is_working_day = BooleanField(default=False)  # Some regions work during certain holidays
    
    created_at = DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('region', 'academic_year', 'name')
```

### 2. Settings Configuration Changes

**Update `config/settings.py`:**

```python
# --- Internationalization ---
USE_I18N = True
USE_L10N = True
USE_TZ = True

LANGUAGE_CODE = os.getenv('LANGUAGE_CODE', 'en')
LANGUAGES = [
    ('en', 'English'),
    ('fr', 'Français'),
    ('pid', 'Pidgin'),
    ('sw', 'Swahili'),
    ('ha', 'Hausa'),
]

TIME_ZONE = os.getenv('TIME_ZONE', 'Africa/Douala')  # Default to Cameroon

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# --- Region Configuration ---
REGION_CODE = os.getenv('REGION_CODE', 'CMR')  # Default to Cameroon
DEFAULT_GRADING_SCALE = os.getenv('DEFAULT_GRADING_SCALE', '0-20')
DEFAULT_CURRENCY = os.getenv('DEFAULT_CURRENCY', 'XAF')

# Supported grading scales globally
GRADING_SCALES = {
    '0-20': {
        'min': 0, 'max': 20,
        'grades': {'A': 18, 'B': 15, 'C': 12, 'D': 9, 'F': 0},
        'display': lambda score: f"{score:.0f}/20"
    },
    '0-100': {
        'min': 0, 'max': 100,
        'grades': {'A': 90, 'B': 80, 'C': 70, 'D': 60, 'F': 0},
        'display': lambda score: f"{score:.0f}%"
    },
    '0-10': {
        'min': 0, 'max': 10,
        'grades': {'A': 9, 'B': 7.5, 'C': 6, 'D': 4.5, 'F': 0},
        'display': lambda score: f"{score:.1f}/10"
    },
    'a-f': {
        'min': 0, 'max': 4,
        'grades': {'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0},
        'display': lambda score: 'ABCDF'[int(score)]
    },
    'gpa': {
        'min': 0, 'max': 4.0,
        'grades': {'A': 4.0, 'B': 3.0, 'C': 2.0, 'D': 1.0, 'F': 0},
        'display': lambda score: f"{score:.2f}"
    }
}

# Currency symbols per region
CURRENCY_SYMBOLS = {
    'XAF': 'FCFA',  # Cameroon/Central Africa
    'USD': '$',     # USA
    'EUR': '€',     # Europe
    'GBP': '£',     # UK
    'KES': 'Ksh',   # Kenya
    'NGN': '₦',     # Nigeria
}
```

### 3. Template & View Localization

**New template context processor in `apps/siteconfig/context_processors.py`:**

```python
from apps.siteconfig.models import RegionConfig

def region_settings(request):
    """Add region-specific settings to template context."""
    try:
        region = RegionConfig.objects.get(code=request.session.get('region_code', 'CMR'))
    except RegionConfig.DoesNotExist:
        region = RegionConfig.objects.get(code='CMR')  # Fallback
    
    return {
        'region': region,
        'currency_symbol': CURRENCY_SYMBOLS.get(region.default_currency, '$'),
        'date_format': region.date_format,
        'grading_scale': DEFAULT_GRADING_SCALE,
    }
```

### 4. Scoring & Grade Conversion Utilities

**New file `apps/evals/grading.py`:**

```python
from decimal import Decimal
from django.core.cache import cache

def convert_score(score, from_scale, to_scale):
    """Convert score between different grading scales."""
    cache_key = f"score_convert:{score}:{from_scale}:{to_scale}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    if from_scale == to_scale:
        return score
    
    # Normalize to 0-1 range
    from_config = GRADING_SCALES.get(from_scale, {})
    to_config = GRADING_SCALES.get(to_scale, {})
    
    from_min, from_max = from_config.get('min', 0), from_config.get('max', 100)
    to_min, to_max = to_config.get('min', 0), to_config.get('max', 100)
    
    normalized = (Decimal(score) - Decimal(from_min)) / (Decimal(from_max) - Decimal(from_min))
    converted = normalized * (Decimal(to_max) - Decimal(to_min)) + Decimal(to_min)
    
    result = round(converted, 2)
    cache.set(cache_key, result, 3600)
    return result

def get_grade_letter(score, scale):
    """Get letter grade (A-F) from numerical score."""
    config = GRADING_SCALES.get(scale, GRADING_SCALES['0-20'])
    grades = config.get('grades', {})
    
    for letter in 'ABCDF':
        if score >= grades.get(letter, 0):
            return letter
    return 'F'

def format_score(score, scale):
    """Format score according to scale's display format."""
    config = GRADING_SCALES.get(scale, GRADING_SCALES['0-20'])
    display_fn = config.get('display', lambda x: x)
    return display_fn(score)
```

### 5. Django Template Filters

**New file `apps/siteconfig/templatetags/i18n_filters.py`:**

```python
from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def format_currency(amount, currency_code='XAF'):
    """Format amount with currency symbol."""
    symbol = CURRENCY_SYMBOLS.get(currency_code, '$')
    return f"{symbol} {amount:,.2f}"

@register.filter
def format_score(score, scale='0-20'):
    """Format score according to grading scale."""
    return format_score(score, scale)

@register.filter
def get_grade_letter(score, scale='0-20'):
    """Convert numerical score to letter grade."""
    return get_grade_letter(score, scale)

@register.filter
def localize_date(date_obj, date_format):
    """Format date according to region's date format."""
    # date_format: 'DD/MM/YYYY', 'MM/DD/YYYY', etc.
    return date_obj.strftime(date_format.replace('DD', '%d').replace('MM', '%m').replace('YYYY', '%Y'))
```

## Implementation Phases

### Phase 1.2.4a - Database & Models (Week 1)
- [ ] Create `RegionConfig`, `GradingScaleConfig`, `HolidayCalendar` models
- [ ] Create migration for new tables
- [ ] Add admin interface for region management
- [ ] Seed Cameroon, USA, UK, Kenya, Nigeria region configs
- [ ] Create fixture data for grading scales

### Phase 1.2.4b - Settings & Context (Week 1)
- [ ] Add i18n settings to `config/settings.py`
- [ ] Create region context processor
- [ ] Update base template to support language switcher
- [ ] Add locale path for translation files

### Phase 1.2.4c - Scoring Utilities (Week 2)
- [ ] Create `apps/evals/grading.py` with conversion functions
- [ ] Add caching for score conversions
- [ ] Create template filters for score/currency formatting
- [ ] Update ranking system to use regional grading scales

### Phase 1.2.4d - View Updates (Week 2)
- [ ] Update all student report views to use regional grading
- [ ] Update parent portal reports with score conversions
- [ ] Update admin dashboard with region selector
- [ ] Update export/PDF reports to respect region settings

### Phase 1.2.4e - Translations (Week 3)
- [ ] Extract all translatable strings (makemessages)
- [ ] Create French translations
- [ ] Create Cameroon Pidgin translations
- [ ] Set up translation management workflow

### Phase 1.2.4f - Testing & Documentation (Week 3)
- [ ] Write tests for grading conversions
- [ ] Write tests for date/time localization
- [ ] Write tests for multi-region views
- [ ] Document region setup for new schools

## Expected Changes by Feature

### Academic Module
- Rankings calculated per regional grading scale
- Reports show both original and converted scores
- Grade letters determined by region

### Finance Module
- Amounts displayed in regional currency with symbol
- Invoices generated with region-specific formatting
- Payment integrations support multiple currencies

### Portal Views
- Language dynamically selected per user/region
- Date formats respect regional standards
- Time displays adjusted for timezone
- Holiday calendar populated from HolidayCalendar model

### Admin Interface
- Region selector dropdown on dashboard
- Preview grading scales by region
- Holiday calendar management per region
- Settings adjusted for selected region

## Backward Compatibility

- Existing Cameroon-specific data migrated with `CMR` as default region
- All current queries filtered by `region_code` if multi-region enabled
- Feature flag: `MULTI_REGION_ENABLED` controls whether region picker appears
- Default behavior unchanged if only one region configured

## Security Considerations

- Region selection validated per request (no cross-region data leakage)
- Holiday calendars validated before import
- Currency conversions logged for audit trail
- Regional compliance settings immutable per school

## Success Metrics

✅ System works identically in Cameroon, USA, UK, Kenya, Nigeria
✅ New school can be set up in any region with 1 click
✅ Score conversions accurate to 2 decimal places
✅ All dates/currencies display correctly per region
✅ Holiday calendars show correct holidays per region
✅ Reports show both native and converted scores
