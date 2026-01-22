# Phase 1.2.4 Quick Start: Using Cameroon Tech for Worldwide Schools

## System Now Supports Any School Anywhere in the World! 🌍

Your system is no longer just for Cameroon schools—it can be deployed in **any country** with appropriate grading scales, currencies, timezones, and languages.

## What's New

### 7 Pre-Configured Regions Ready to Use

| Region | Code | Grading Scale | Currency | Timezone | Academic Year Start |
|--------|------|---------------|----------|----------|---------------------|
| 🇨🇲 Cameroon | CMR | 0-20 | XAF (FCFA) | Africa/Douala | September |
| 🇺🇸 United States | USA | 0-100 | USD ($) | America/New_York | August |
| 🇬🇧 United Kingdom | GBR | A-F Letters | GBP (£) | Europe/London | September |
| 🇰🇪 Kenya | KEN | 0-100 | KES (Ksh) | Africa/Nairobi | January |
| 🇳🇬 Nigeria | NGA | 0-100 | NGN (₦) | Africa/Lagos | September |
| 🇫🇷 France | FRA | 0-20 | EUR (€) | Europe/Paris | September |
| 🇩🇪 Germany | DEU | 0-10 | EUR (€) | Europe/Berlin | August |

### Core Features Added

#### 1. **Multiple Grading Scales**
Convert scores between any scale automatically:
```python
from apps.evals.grading import convert_score, get_grade_letter, format_score

# Cameroon: Convert 18/20 to US 0-100 scale
us_score = convert_score(18, '0-20', '0-100')  # Returns: 90.0

# Get letter grade
grade = get_grade_letter(18, '0-20')  # Returns: 'A'

# Format for display
display = format_score(18, '0-20')  # Returns: "18/20"
```

#### 2. **Regional Configuration**
Each school can be assigned a region with automatic settings:
```python
# Get a region
from apps.siteconfig.models import RegionConfig

cameroon = RegionConfig.objects.get(code='CMR')
print(cameroon.grading_scale)    # '0-20'
print(cameroon.default_currency)  # 'XAF'
print(cameroon.timezone)         # 'Africa/Douala'
print(cameroon.date_format)      # 'DD/MM/YYYY'
```

#### 3. **Grading Scale Definitions**
Each region has configured grade breakpoints:
```python
# Get Kenya's grading scale
kenya_scale = cameroon.grading_scales.get(scale_type='0-100')

# Get letter grade for a score
letter = kenya_scale.get_letter_grade(75)  # Returns: 'B'
```

#### 4. **Holiday Calendars**
Schools can manage holidays per region and academic year:
```python
from apps.siteconfig.models import HolidayCalendar
from apps.academics.models import AcademicYear

holidays = HolidayCalendar.objects.filter(
    region__code='KEN',
    academic_year__name='2024/2025'
)

# Check if date is a holiday
christmas = HolidayCalendar.objects.get(name='Christmas Break')
is_closed = christmas.overlaps_date(date(2024, 12, 25))  # True
```

#### 5. **Currency Formatting**
Automatically format amounts in regional currency:
```python
from apps.evals.grading import format_currency

# Cameroon
fmt = format_currency(15000, 'XAF')   # "FCFA 15,000.00"

# USA
fmt = format_currency(85.50, 'USD')   # "$ 85.50"

# UK
fmt = format_currency(150, 'GBP')     # "£ 150.00"
```

## How to Set Up a New School in Any Country

### Step 1: Choose Region in Admin
1. Login to Django admin: `/admin/`
2. Go to **Site Configuration > Region Configs**
3. Select pre-configured region (e.g., USA)

### Step 2: Create Academic Calendar with Region Holidays
```python
from apps.siteconfig.models import HolidayCalendar
from apps.academics.models import AcademicYear

year = AcademicYear.objects.create(
    name='2024/2025',
    start_date=date(2024, 8, 1),  # US starts August
    end_date=date(2025, 5, 31),
)

# Add holidays automatically
HolidayCalendar.objects.create(
    region_code='USA',
    academic_year=year,
    name='Thanksgiving',
    date_start=date(2024, 11, 28),
    date_end=date(2024, 11, 29),
    holiday_type='public_holiday'
)
```

### Step 3: Update Reports to Use Regional Scale
Reports will automatically show scores in the region's grading scale:
```python
# In templates: Scores display in regional format
{{ score|get_grade_letter:"0-100" }}  {# "A" #}
{{ score|format_score:"0-100" }}      {# "90%" #}
```

## Key Features for Each Region

### 🇺🇸 United States Setup
- ✅ 0-100 scoring (90=A, 80=B, etc.)
- ✅ Academic year: August-May (2 terms)
- ✅ Standard holidays: Thanksgiving, Christmas, Spring Break
- ✅ Currency: USD ($)
- ✅ Timezone: Eastern/Central/Mountain/Pacific (configure per school)
- ✅ Date format: MM/DD/YYYY

### 🇬🇧 United Kingdom Setup
- ✅ A-F letter grades (not numerical)
- ✅ Academic year: September-July (3 terms)
- ✅ Standard holidays: Half-terms, Summer, Christmas
- ✅ Currency: GBP (£)
- ✅ Timezone: Europe/London
- ✅ Date format: DD/MM/YYYY

### 🇰🇪 Kenya Setup
- ✅ 0-100 scoring (80=A, 65=B, 50=C, 40=D)
- ✅ Academic year: January-November (3 terms)
- ✅ Regional holidays: Holidays from school holidays
- ✅ Currency: KES (Ksh)
- ✅ Timezone: Africa/Nairobi
- ✅ Date format: DD/MM/YYYY

## Developers: Integration Guide

### Adding a New Region

```python
# 1. Create in admin or via management command
python manage.py seed_regions  # Re-run to add more

# 2. Or create programmatically
from apps.siteconfig.models import RegionConfig, GradingScaleConfig
from decimal import Decimal

region = RegionConfig.objects.create(
    code='AUS',
    name='Australia',
    default_language='en',
    timezone='Australia/Sydney',
    date_format='DD/MM/YYYY',
    grading_scale='0-100',
    default_currency='AUD',
    academic_year_start_month=1,  # January
    term_count_per_year=4,
)

# 2. Create grading scale
GradingScaleConfig.objects.create(
    region=region,
    scale_type='0-100',
    min_score=Decimal('0'),
    max_score=Decimal('100'),
    display_format='{score:.0f}%',
    grade_a_min=Decimal('85'),
    grade_b_min=Decimal('75'),
    grade_c_min=Decimal('65'),
    grade_d_min=Decimal('50'),
    grade_f_min=Decimal('0'),
)
```

### Using Grading Conversions in Views

```python
from apps.evals.grading import convert_score

class StudentReportView(View):
    def get(self, request, student_id):
        student = StudentProfile.objects.get(id=student_id)
        evaluations = student.evaluations.all()
        
        # Get region from school or request
        region = request.session.get('region', 'CMR')
        
        # Convert scores if viewing in different scale
        for eval in evaluations:
            eval.regional_score = convert_score(
                eval.total_score,
                from_scale='0-20',  # Original Cameroon scale
                to_scale=region.grading_scale
            )
        
        return render(request, 'report.html', {'evaluations': evaluations})
```

### Template Usage

```django
{% load i18n %}

<!-- Region selector -->
<select name="region">
    {% for region in available_regions %}
        <option value="{{ region.code }}">{{ region.name }}</option>
    {% endfor %}
</select>

<!-- Format currency -->
<span>{{ fee_amount|format_currency:region.default_currency }}</span>

<!-- Format date -->
<span>{{ exam_date|date:region.date_format }}</span>

<!-- Convert score -->
<span>{{ score|convert_score:"0-20,0-100" }}</span>
```

## Environment Configuration

Set these in `.env` to choose region:

```bash
# Default region code
REGION_CODE=CMR

# Default grading scale
DEFAULT_GRADING_SCALE=0-20

# Default currency
DEFAULT_CURRENCY=XAF

# Enable multi-region support
ENABLE_MULTI_REGION=True

# Language
LANGUAGE_CODE=en

# Timezone
TIME_ZONE=Africa/Douala
```

## Database Tables Added

```sql
-- Region configurations
siteconfig_regionconfig (code, name, timezone, default_currency, grading_scale, etc.)

-- Grading scale definitions per region
siteconfig_gradingscaleconfig (region_id, scale_type, grade_a_min, grade_b_min, etc.)

-- Holiday calendars per region & year
siteconfig_holidaycalendar (region_id, academic_year_id, name, date_start, date_end, etc.)
```

## Next Steps

### Phase 1.2.5: Regional Views & Admin
- [ ] Admin interface for region configuration
- [ ] Region selector in staff dashboard
- [ ] Holiday calendar management UI
- [ ] Grading scale preview/comparison tool

### Phase 1.2.6: Multi-Language Translations
- [ ] Extract Django strings (makemessages)
- [ ] Translate UI to French, Pidgin, Swahili, Hausa
- [ ] Language switcher in portal
- [ ] Region-based language auto-selection

### Phase 1.2.7: Report Localization
- [ ] Generate certificates in regional language
- [ ] Export transcripts with converted scores
- [ ] Email notifications in regional language
- [ ] SMS/WhatsApp messages in regional language

## FAQ

**Q: Can I use scores from different regions in the same school?**
A: Yes! Use `convert_score()` to normalize before comparisons.

**Q: What if my school has a custom grading scale?**
A: Create a custom `GradingScaleConfig` for your region, or contact support to add it.

**Q: How do I change a region's settings?**
A: Edit in Django admin under **Site Configuration > Region Configs**, or update programmatically.

**Q: Will existing Cameroon data be affected?**
A: No! Cameroon is the default region. All existing data remains unchanged.

**Q: Can teachers see scores in multiple scales?**
A: Yes! Use template filters: `{{ score|get_grade_letter:"0-100" }}`

---

**System is now globally deployable!** 🚀

For support, documentation updates, or feature requests, refer to `docs/PHASE_1_2_4_INTERNATIONALIZATION.md`.
