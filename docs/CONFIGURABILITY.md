# Configurability contract

Every value in this codebase belongs in **one** of seven configuration layers.
Hardcoding a value into source code is an anti-pattern unless it's a true
platform constant (e.g. a math operation, a Bootstrap selector name).

This document is the decision tree. If you're writing new code or polishing
existing code, check here first. **No new code should add hardcoded
tenant-facing values, hardcoded URLs, hardcoded brand strings, hardcoded
business thresholds, or untranslated user-facing English.**

---

## The decision tree

Ask these questions, in order, for every value you'd otherwise hardcode:

```
1. Does this value differ between TENANTS (schools)?
   YES → Tenant-level config (see Layer A)
   NO  → continue

2. Does this value differ between ENVIRONMENTS (dev / staging / prod)?
   YES → Environment variable (see Layer B)
   NO  → continue

3. Does this value differ between USERS (theme, density, locale)?
   YES → User preference (see Layer C)
   NO  → continue

4. Is this value a TRANSLATABLE STRING visible to users?
   YES → Django i18n (see Layer D)
   NO  → continue

5. Is this value a FEATURE TOGGLE that ops want to flip without a deploy?
   YES → Feature flag (see Layer E)
   NO  → continue

6. Is this value REGIONAL / CURRICULAR data (countries, grade scales,
   currencies, term lengths)?
   YES → Database fixture (see Layer F)
   NO  → continue

7. None of the above? It's a platform constant — Layer G applies.
```

---

## Layer A — Tenant-level config

**Where:** `apps/siteconfig/models.py` (`SiteSettings`), `apps/schools/models.py` (`School`), `apps/brand_experience/models.py` (`BrandProfile`).

**For:**
- Brand: `site_name`, `primary_color`, `accent_color`, `logo`, `favicon`, `custom_css`
- Contact: `company_name`, `company_email`, `company_phone`, `company_address`
- Regional: `country_code`, `currency`, `term_preset`, `academic_year`
- Identity: `slug`, `subdomain`, `ministry_registration_code`
- Compliance: `report_preview_footer_note`, `report_preview_contact_email`
- Theme: `theme_brightness`, `brand_font`, `secondary_font`, `LAYOUT_STYLE`

**Read pattern in views:**
```python
site = request.site_settings  # from middleware
context['school_name'] = site.site_name
```

**Read pattern in templates:**
```django
{{ SITE.site_name|default:"School" }}
{{ SITE.company_email|default:"info@school.local" }}
```

The `|default:` fallback should be a NEUTRAL placeholder, never a specific
tenant's name. `"School"` is fine; `"Gilead Tech High"` is not.

---

## Layer B — Environment variables

**Where:** Read in `config/settings.py` via `django-environ` (`env()`).

**For:**
- Secrets: `DJANGO_SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, API keys, signing keys
- Hosts: `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `MULTI_TENANT_BASE_DOMAIN`
- Service integrations: `TWILIO_*`, `AFRICASTALKING_*`, `EMAIL_HOST_*`, `STRIPE_*`
- Behaviour flags that toggle by deploy: `DEBUG`, `USE_DJANGO_TENANTS`
- Limits per environment: `WEBHOOK_RATE_LIMIT`, `CELERY_WORKER_CONCURRENCY`

**Pattern:**
```python
# settings.py
import environ
env = environ.Env()
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost'])
THREAT_WINDOW_MINUTES = env.int('THREAT_WINDOW_MINUTES', default=60)
```

**Anti-pattern:** never reference `os.environ.get(...)` directly outside
settings.py. Use Django settings throughout the app code.

---

## Layer C — Per-user preferences

**Where:** `apps/siteconfig/models.py` (`UserPreferences`).

**For:**
- Display: `theme` (light/dark/system), `dashboard_visual_preset`, `density`
- Locale: `preferred_language`, `time_zone`
- Notifications: `email_digest_frequency`, `quiet_hours_start/end`
- A11y: `high_contrast`, `reduced_motion`, `font_scale`
- Workflow: `default_landing_page`, `pinned_actions`

**Pattern:** middleware reads `UserPreferences` and sets context vars
(`USER_THEME_PREFERENCE`, `HIGH_CONTRAST_MODE`) used in `base.html`.

---

## Layer D — i18n (translatable strings)

**Where:** Django translation files at `locale/<lang>/LC_MESSAGES/django.po`.

**For:** Every user-facing string in templates, views, models (verbose_name),
form labels, error messages.

**Template pattern:**
```django
{% load i18n %}
<h1>{% trans "Welcome back" %}</h1>
<p>{% blocktrans with name=request.user.first_name %}Hello, {{ name }}.{% endblocktrans %}</p>
```

**Python pattern:**
```python
from django.utils.translation import gettext_lazy as _
class Meta:
    verbose_name = _("Student profile")
ROLE_CHOICES = [('TEACHER', _('Teacher')), ('PARENT', _('Parent'))]
```

**Anti-pattern:**
```django
<button>Save</button>             {# missing {% trans %} #}
<input placeholder="Email">       {# placeholder is user-facing #}
```

---

## Layer E — Feature flags

**Where:** `SiteSettings` boolean fields (`features_enabled` JSON or `feature_*` columns), or `django-waffle` switches/flags.

**For:**
- Module toggles: `enable_finance`, `enable_marketplace`, `enable_ai_copilot`
- Beta gates: `beta_threat_detection`, `beta_offline_sync`
- Ops kill-switches: `disable_outbound_email`, `maintenance_mode`

**Pattern in views:**
```python
if site.features.get('finance_module'):
    return render('finance/dashboard.html', ...)
```

**Pattern in templates:**
```django
{% if SITE.features.parent_app %}
  <a href="{% url 'parent_dashboard' %}">Parents</a>
{% endif %}
```

---

## Layer F — Database fixtures (regional + curricular data)

**Where:** `apps/siteconfig/fixtures/*.json`, `apps/schools/fixtures/*.json`,
plus seed migrations.

**For:**
- Countries (`CountryRegistry`)
- Subdivisions (Kenyan counties, US states, etc.)
- Education systems (CBC, IGCSE, IB, A-Level, US-K12)
- Default grade scales per education system
- Default term structures (UK Michaelmas/Lent/Trinity vs East-African 3-term)
- Currency codes per country
- Subjects per curriculum

**Anti-pattern:**
```python
# views.py — DO NOT DO THIS
if country == 'KE':
    terms = ['Term 1', 'Term 2', 'Term 3']
elif country == 'UK':
    terms = ['Michaelmas', 'Lent', 'Trinity']
```

**Correct:**
```python
profile = EducationSystemProfile.objects.get(country=country)
terms = profile.term_names  # from fixture
```

---

## Layer G — Platform constants (the only "hardcoding" allowed)

**Where:** A clearly-named `constants.py` in the relevant app, OR inline
when the value is truly never going to vary.

**For:**
- Mathematical constants (`PI`, `DEGREES_PER_CIRCLE`)
- Bootstrap class names (`'btn-primary'`)
- HTTP status codes (`200`, `404`)
- Django framework values (`'GET'`, `'POST'`)
- Internal enum values that map to Layer D translated labels via `gettext_lazy`

**Pattern:**
```python
# apps/people/constants.py
ROLE_TEACHER = 'TEACHER'
ROLE_PARENT = 'PARENT'
ROLE_STAFF = 'STAFF'
ROLE_ADMIN = 'ADMIN'

# Used elsewhere:
from apps.people.constants import ROLE_TEACHER
if user.role == ROLE_TEACHER:
    ...
```

**Not OK:**
```python
if user.role == 'TEACHER':       # magic string
    return PAGE_SIZE = 25         # magic number that should be SiteSettings
```

---

## Anti-patterns checklist

When reviewing code (yours or others'), flag any of these:

| Anti-pattern | Fix |
|---|---|
| `<title>RunMyCampus</title>` in tenant-facing template | `{{ SITE.site_name }}` |
| `href="https://runmycampus.com"` | `{{ PUBLIC_BRAND_DOMAIN }}` or `{% url '...' %}` |
| `email = "admin@school.edu"` in views/templates | `SITE.company_email` |
| `style="background: #4f46e5"` in templates | `style="background: var(--school-primary)"` |
| `<p>Welcome back</p>` in template | `<p>{% trans "Welcome back" %}</p>` |
| `if role == 'TEACHER':` in Python | `if role == ROLE_TEACHER:` (imported constant) |
| `MAX_FILE_SIZE = 5 * 1024 * 1024` in views | settings.py + `SiteSettings.max_upload_mb` if tenant-overridable |
| `country == 'KE': terms = [...]` | Query `EducationSystemProfile` fixture |
| `paginate_by = 25` | `paginate_by = settings.DEFAULT_PAGE_SIZE` |
| `placeholder="Search students"` | `placeholder="{% trans 'Search students' %}"` |
| `if grade >= 50:` for "pass" in views | `if grade >= site.passing_grade_threshold:` |
| `"Term 1"` literal in code | Look up from `AcademicTerm` model |
| Hardcoded role-permission strings | Use Django `permissions` + `Group` |
| Inline `<style>` with brand colors | Move to a CSS file using tokens |
| `{ 'role': 'admin' }` JSON literal in templates | Pull from `settings.ROLE_*` exposed via context processor |

---

## When you find an existing hardcoded value

Don't fix everything at once. The cleanup is incremental. Process:

1. **Identify the layer it belongs in** (use the decision tree above).
2. **If a new SiteSettings field is needed**, write a migration: add the field with a sensible default. Migrate. Then update the code to read from `SiteSettings`.
3. **If it's just untranslated text**, wrap with `{% trans %}` and regenerate `.po` files (`python manage.py makemessages -l en` — actually do this when a translator is ready, otherwise the string stays as-is in English which is fine).
4. **If it's a brand color in a CSS file**, convert to `var(--school-primary)` etc. (already done for `#0d6efd` / `#198754` / `#d4af37` — see `feedback_aesthetic_polish` memory).
5. **If it's a magic number**, add to `settings.py` + write a setting on `SiteSettings` only if it's tenant-overridable.

---

## Verifying the contract

Run these greps periodically to catch new hardcoding:

```bash
# Hardcoded URLs in templates (excluding well-known CDNs):
grep -rn 'https\?://' templates/ | grep -v 'cdn\.\|cdnjs\|jsdelivr\|googleapis\|gstatic\|placehold'

# Untranslated text in user-facing templates:
grep -rn '<button[^>]*>[A-Z][a-z]' templates/    # buttons with literal English
grep -rn 'placeholder="[A-Z][a-z]' templates/    # untranslated placeholders

# Hardcoded role strings outside constants files:
grep -rn "== 'TEACHER'\|== 'PARENT'\|== 'STAFF'\|== 'ADMIN'" apps/ --include="*.py" | grep -v constants.py | grep -v migrations

# Hardcoded hex colors in templates (most should be tokens):
grep -rn 'style="[^"]*#[0-9a-fA-F]\{3,6\}' templates/

# Hardcoded brand names in tenant-facing templates:
grep -rn "RunMyCampus\b" templates/ | grep -v 'auth/manager\|auth/admin_login\|control_plane\|marketing\|errors/.*_control_plane'

# Magic numbers in views:
grep -rn 'paginate_by\s*=\s*[0-9]' apps/ --include="*.py" | grep -v settings
```

---

## Owners

- Brand/tenant config (Layer A): siteconfig app maintainer
- Env vars (Layer B): platform/devops
- User prefs (Layer C): accounts app
- i18n (Layer D): every contributor (when adding a string, wrap it)
- Feature flags (Layer E): platform team
- Fixtures (Layer F): curriculum/regional team
- Constants (Layer G): app-level (e.g. `apps/people/constants.py`)

---

*This contract is the source of truth for "where does this value go?".
If you can't find the right layer for something, that's a sign the
architecture needs a new abstraction — discuss before hardcoding.*
