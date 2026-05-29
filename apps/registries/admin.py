from django import forms
from django.contrib import admin

from config.admin import platform_admin_site

from .models import (
    AcademicTerminologyRegistry,
    CalendarSystemRegistry,
    CountryRegistry,
    CurrencyRegistry,
    DocumentTypeRegistry,
    EducationLevelRegistry,
    EducationSystemTypeRegistry,
    FeeCategoryRegistry,
    GradeScaleRegistry,
    InstitutionTypeRegistry,
    LocaleRegistry,
    SubdivisionRegistry,
    TenantGradeScaleOverride,
    TimeZoneRegistry,
)


class CountryRegistryAdminForm(forms.ModelForm):
    """Wave 8/10/12/13 — operator-friendly cockpit override.

    Validates that ``cockpit_override_payload`` is a dict and the top-level
    keys belong to the country-pack contract. Surfaces a JSON-shape error
    INSIDE the form (so operators see "calendar_systems must be a list"
    instead of staring at a HTTP 500). Empty / null / "{}" all accepted.

    Wave 13 (v3.62.17 — 2026-05-23): rich-edit form for ``marketing_voice``.
    Instead of forcing the operator to hand-edit the raw JSON, the form
    exposes 14 discrete scalar fields plus a line-separated textarea for
    ``case_study_chips`` and round-trips them into the nested JSON shape
    on save. The raw ``cockpit_override_payload`` textarea remains available
    in the collapsible "Operator overrides" fieldset for power users.
    """

    _ALLOWED_KEYS = {
        "calendar_systems",
        "school_types",
        "education_levels",
        "terminology",
        "languages",
        "writing_direction",
        "system_name",
        # Wave 12 (v3.62.16 — 2026-05-23): operator marketing-voice override.
        # Shape (any subset of these keys; operator-modifiable scalars + the
        # nested `testimonial` dict + `case_study_chips` list):
        #   "marketing_voice": {
        #       "country_name": "...", "greeting": "...", "headline_lead": "...",
        #       "headline_lead_native": "...", "hero_subline": "...",
        #       "trust_count": "...", "currency_sample": "...",
        #       "calendar_sample": "...", "regulatory_line": "...",
        #       "anchor_city": "...", "regional_phrase": "...",
        #       "testimonial": {"quote": "...", "author": "...", "credential": "..."},
        #       "case_study_chips": ["...", "...", "..."]
        #   }
        "marketing_voice",
    }

    # Wave 13 rich-edit scalar fields. Field name → marketing_voice key.
    _MV_SCALAR_FIELDS = (
        ("mv_country_name", "country_name", "Country name (display, e.g. 'Nigeria')"),
        ("mv_greeting", "greeting", "Native greeting (e.g. 'Karibu')"),
        ("mv_headline_lead", "headline_lead", "Headline lead-in (e.g. 'Built for Nigerian schools')"),
        ("mv_headline_lead_native", "headline_lead_native", "Headline lead-in — native language (optional)"),
        ("mv_hero_subline", "hero_subline", "Hero subline (supporting line)"),
        ("mv_trust_count", "trust_count", "Trust line (e.g. 'Trusted by schools across all 36 states')"),
        ("mv_currency_sample", "currency_sample", "Sample fee (e.g. '₦145,000 / term')"),
        ("mv_calendar_sample", "calendar_sample", "Sample calendar (e.g. '3 terms — September to July')"),
        ("mv_regulatory_line", "regulatory_line", "Regulatory line (curriculum alignment)"),
        ("mv_anchor_city", "anchor_city", "Anchor city (e.g. 'Lagos')"),
        ("mv_regional_phrase", "regional_phrase", "Regional phrase (e.g. 'Nigerian schools')"),
        ("mv_testimonial_quote", "_t_quote", "Testimonial — quote (under ~140 chars works best)"),
        ("mv_testimonial_author", "_t_author", "Testimonial — author (e.g. 'Proprietor, K-12 school in Lagos')"),
        ("mv_testimonial_credential", "_t_credential", "Testimonial — credential (e.g. '1,800 students · 3 campuses')"),
    )

    mv_country_name = forms.CharField(required=False, max_length=120)
    mv_greeting = forms.CharField(required=False, max_length=120)
    mv_headline_lead = forms.CharField(required=False, max_length=240)
    mv_headline_lead_native = forms.CharField(required=False, max_length=240)
    mv_hero_subline = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    mv_trust_count = forms.CharField(required=False, max_length=240)
    mv_currency_sample = forms.CharField(required=False, max_length=80)
    mv_calendar_sample = forms.CharField(required=False, max_length=160)
    mv_regulatory_line = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    mv_anchor_city = forms.CharField(required=False, max_length=120)
    mv_regional_phrase = forms.CharField(required=False, max_length=160)
    mv_testimonial_quote = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Under 140 characters reads best on the marketing band.",
    )
    mv_testimonial_author = forms.CharField(required=False, max_length=160)
    mv_testimonial_credential = forms.CharField(required=False, max_length=160)
    mv_case_study_chips = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One chip per line (3–5 works best). Example:\nWAEC + NECO result import\nJSS / SSS promotion engine",
    )

    class Meta:
        model = CountryRegistry
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill the rich-edit scalars from existing payload.marketing_voice
        # so the operator sees the current override and can edit incrementally.
        instance = kwargs.get("instance") or getattr(self, "instance", None)
        if instance and getattr(instance, "cockpit_override_payload", None):
            mv = (instance.cockpit_override_payload or {}).get("marketing_voice") or {}
            if isinstance(mv, dict):
                testimonial = mv.get("testimonial") or {}
                if not isinstance(testimonial, dict):
                    testimonial = {}
                self.fields["mv_country_name"].initial = mv.get("country_name", "")
                self.fields["mv_greeting"].initial = mv.get("greeting", "")
                self.fields["mv_headline_lead"].initial = mv.get("headline_lead", "")
                self.fields["mv_headline_lead_native"].initial = mv.get("headline_lead_native", "")
                self.fields["mv_hero_subline"].initial = mv.get("hero_subline", "")
                self.fields["mv_trust_count"].initial = mv.get("trust_count", "")
                self.fields["mv_currency_sample"].initial = mv.get("currency_sample", "")
                self.fields["mv_calendar_sample"].initial = mv.get("calendar_sample", "")
                self.fields["mv_regulatory_line"].initial = mv.get("regulatory_line", "")
                self.fields["mv_anchor_city"].initial = mv.get("anchor_city", "")
                self.fields["mv_regional_phrase"].initial = mv.get("regional_phrase", "")
                self.fields["mv_testimonial_quote"].initial = testimonial.get("quote", "")
                self.fields["mv_testimonial_author"].initial = testimonial.get("author", "")
                self.fields["mv_testimonial_credential"].initial = testimonial.get("credential", "")
                chips = mv.get("case_study_chips") or []
                if isinstance(chips, list):
                    self.fields["mv_case_study_chips"].initial = "\n".join(
                        str(c) for c in chips if c
                    )

    def _build_marketing_voice_from_form(self) -> dict:
        """Round-trip the 14 scalars + chips textarea into a nested dict.

        Empty-string fields are omitted (so they don't shadow the seed
        pack with empty strings). Returns ``{}`` if every field is empty.
        """
        data = self.cleaned_data
        mv: dict = {}
        # Scalars.
        for fname, key in (
            ("mv_country_name", "country_name"),
            ("mv_greeting", "greeting"),
            ("mv_headline_lead", "headline_lead"),
            ("mv_headline_lead_native", "headline_lead_native"),
            ("mv_hero_subline", "hero_subline"),
            ("mv_trust_count", "trust_count"),
            ("mv_currency_sample", "currency_sample"),
            ("mv_calendar_sample", "calendar_sample"),
            ("mv_regulatory_line", "regulatory_line"),
            ("mv_anchor_city", "anchor_city"),
            ("mv_regional_phrase", "regional_phrase"),
        ):
            val = (data.get(fname) or "").strip()
            if val:
                mv[key] = val
        # Testimonial nested dict.
        q = (data.get("mv_testimonial_quote") or "").strip()
        a = (data.get("mv_testimonial_author") or "").strip()
        c = (data.get("mv_testimonial_credential") or "").strip()
        if q or a or c:
            t: dict = {}
            if q:
                t["quote"] = q
            if a:
                t["author"] = a
            if c:
                t["credential"] = c
            mv["testimonial"] = t
        # Case-study chips list.
        chips_raw = (data.get("mv_case_study_chips") or "").strip()
        if chips_raw:
            chips = [line.strip() for line in chips_raw.splitlines() if line.strip()]
            if chips:
                mv["case_study_chips"] = chips
        return mv

    def clean_cockpit_override_payload(self):
        value = self.cleaned_data.get("cockpit_override_payload")
        if value in (None, "", {}):
            return {}
        if not isinstance(value, dict):
            raise forms.ValidationError(
                "Override must be a JSON object (dict), e.g. "
                '{"terminology": {"teacher": "Tuteur"}}.'
            )
        unknown = set(value.keys()) - self._ALLOWED_KEYS
        if unknown:
            raise forms.ValidationError(
                "Unknown override keys: "
                f"{', '.join(sorted(unknown))}. "
                f"Allowed: {', '.join(sorted(self._ALLOWED_KEYS))}."
            )
        # Shape checks per known key.
        for k in ("calendar_systems", "school_types", "education_levels", "languages"):
            if k in value and not isinstance(value[k], list):
                raise forms.ValidationError(
                    f"`{k}` override must be a list (each entry a dict)."
                )
        if "terminology" in value and not isinstance(value["terminology"], dict):
            raise forms.ValidationError(
                "`terminology` override must be a dict (e.g. "
                '{"teacher": "Tuteur"}).'
            )
        # Wave 12 — validate marketing_voice shape.
        if "marketing_voice" in value:
            mv = value["marketing_voice"]
            if not isinstance(mv, dict):
                raise forms.ValidationError(
                    "`marketing_voice` override must be a dict."
                )
            if "testimonial" in mv and not isinstance(mv["testimonial"], dict):
                raise forms.ValidationError(
                    "`marketing_voice.testimonial` must be a dict with "
                    "keys: quote, author, credential."
                )
            if "case_study_chips" in mv and not isinstance(mv["case_study_chips"], list):
                raise forms.ValidationError(
                    "`marketing_voice.case_study_chips` must be a list of strings."
                )
        return value

    def clean(self):
        """Wave 13: merge the rich-edit ``mv_*`` fields into
        ``cockpit_override_payload['marketing_voice']`` so the operator
        can edit either surface (rich form or raw JSON textarea) and the
        result is consistent.

        Rich-edit fields win over the raw JSON's marketing_voice subkey
        (since the operator typically uses the rich form). Other top-level
        keys in the raw payload (calendar_systems, terminology, etc.) are
        preserved untouched.
        """
        cleaned = super().clean()
        # Pull the validated payload — guard against missing key when the
        # raw textarea failed validation independently.
        payload = cleaned.get("cockpit_override_payload")
        if payload in (None, ""):
            payload = {}
        if not isinstance(payload, dict):
            return cleaned  # let clean_cockpit_override_payload's error stand
        rich_mv = self._build_marketing_voice_from_form()
        if rich_mv:
            payload = dict(payload)
            payload["marketing_voice"] = rich_mv
        elif "marketing_voice" in payload and not payload["marketing_voice"]:
            # Operator cleared every rich field AND payload's mv is empty —
            # drop the key so the merge contract stays minimal.
            payload = {k: v for k, v in payload.items() if k != "marketing_voice"}
        cleaned["cockpit_override_payload"] = payload
        return cleaned

    def save(self, commit=True):
        """After save, evict the country_localization service cache so the
        edit takes effect immediately without a process restart."""
        instance = super().save(commit=commit)
        try:
            from apps.siteconfig.country_localization_service import clear_cache
            clear_cache()
        except Exception:  # noqa: BLE001 — admin save must never break on cache evict
            pass
        return instance


@admin.register(CountryRegistry, site=platform_admin_site)
class CountryRegistryAdmin(admin.ModelAdmin):
    form = CountryRegistryAdminForm
    list_display = (
        "code",
        "alpha3_code",
        "name",
        "default_language",
        "default_currency",
        "writing_direction",
        "has_override",
        "is_active",
    )
    list_filter = ("is_active", "default_language", "default_currency", "writing_direction")
    search_fields = ("code", "alpha3_code", "name")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": ("code", "alpha3_code", "name", "is_active"),
        }),
        ("Display defaults", {
            "fields": (
                "default_language", "default_currency", "default_timezone",
                "writing_direction", "default_calendar_family",
                "default_terminology_pack",
            ),
        }),
        ("Marketing voice override (Wave 13)", {
            "description": (
                "Override the marketing band voice for this country WITHOUT "
                "editing the JSON payload. Each field below maps directly "
                "into <code>cockpit_override_payload.marketing_voice.*</code>. "
                "Leave a field blank to fall back to the seed value (the "
                "hand-voiced text in <code>marketing_local_context.py</code>). "
                "Changes take effect immediately — no process restart needed."
            ),
            "classes": ("collapse",),
            "fields": (
                "mv_country_name", "mv_greeting",
                "mv_headline_lead", "mv_headline_lead_native",
                "mv_hero_subline",
                "mv_trust_count",
                "mv_currency_sample", "mv_calendar_sample",
                "mv_regulatory_line",
                "mv_anchor_city", "mv_regional_phrase",
                "mv_testimonial_quote", "mv_testimonial_author", "mv_testimonial_credential",
                "mv_case_study_chips",
            ),
        }),
        ("Operator overrides — raw JSON (Wave 8/10/12)", {
            "description": (
                "Raw JSON overlay for advanced operators. Marketing voice "
                "lives in the dedicated fieldset above and round-trips into "
                "this payload on save. Other allowed top-level keys: "
                "calendar_systems (list), school_types (list), education_levels "
                "(list), languages (list), terminology (dict), writing_direction "
                "(str), system_name (str). "
                "Lists override wholesale; dicts merge one level deep. "
                "Empty / blank = no override."
            ),
            "classes": ("collapse",),
            "fields": ("cockpit_override_payload",),
        }),
        ("Registry metadata", {
            "classes": ("collapse",),
            "fields": ("labels", "metadata", "created_at", "updated_at"),
        }),
    )

    def has_override(self, obj) -> bool:
        return bool(getattr(obj, "cockpit_override_payload", None) or {})
    has_override.boolean = True
    has_override.short_description = "Override"


@admin.register(SubdivisionRegistry, site=platform_admin_site)
class SubdivisionRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country", "subdivision_type", "is_active")
    list_filter = ("country", "subdivision_type", "is_active")
    search_fields = ("code", "name", "country__name", "country__code")


@admin.register(EducationLevelRegistry, site=platform_admin_site)
class EducationLevelRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "global_name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "global_name")


@admin.register(EducationSystemTypeRegistry, site=platform_admin_site)
class EducationSystemTypeRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "sort_order", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("code", "name", "category")


@admin.register(TimeZoneRegistry, site=platform_admin_site)
class TimeZoneRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "utc_offset", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(CurrencyRegistry, site=platform_admin_site)
class CurrencyRegistryAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "symbol",
        "decimal_places",
        "sort_order",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "name", "symbol")


@admin.register(LocaleRegistry, site=platform_admin_site)
class LocaleRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_rtl", "sort_order", "is_active")
    list_filter = ("is_active", "is_rtl")
    search_fields = ("code", "name")


@admin.register(CalendarSystemRegistry, site=platform_admin_site)
class CalendarSystemRegistryAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "country_code",
        "term_count_per_year",
        "sort_order",
        "is_active",
    )
    list_filter = ("is_active", "country_code")
    search_fields = ("code", "name")


@admin.register(InstitutionTypeRegistry, site=platform_admin_site)
class InstitutionTypeRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(AcademicTerminologyRegistry, site=platform_admin_site)
class AcademicTerminologyRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country_code", "sort_order", "is_active")
    list_filter = ("is_active", "country_code")
    search_fields = ("code", "name")


@admin.register(DocumentTypeRegistry, site=platform_admin_site)
class DocumentTypeRegistryAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "category",
        "country_code",
        "sort_order",
        "is_active",
    )
    list_filter = ("is_active", "category")
    search_fields = ("code", "name")


@admin.register(FeeCategoryRegistry, site=platform_admin_site)
class FeeCategoryRegistryAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "category",
        "country_code",
        "sort_order",
        "is_active",
    )
    list_filter = ("is_active", "category")
    search_fields = ("code", "name")


@admin.register(GradeScaleRegistry, site=platform_admin_site)
class GradeScaleRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "family", "country_code", "sort_order", "is_active")
    list_filter = ("is_active", "family")
    search_fields = ("code", "name")


@admin.register(TenantGradeScaleOverride, site=platform_admin_site)
class TenantGradeScaleOverrideAdmin(admin.ModelAdmin):
    """v4.00.36 — per-tenant grade-scale override.

    Resolution order used by ``apps.registries.grade_scale_resolver``:

    1. ``(school, context_key)`` exact-match row (e.g. context_key="primary").
    2. ``(school, context_key="")`` is the tenant's default override.
    3. ``RuntimeDefaults.default_grading_scale`` (platform default).
    4. ``GradeScaleRegistry`` first row matching ``school.country_code``.
    5. ``None`` (caller falls back to its model default).

    Leave ``context_key`` blank to override the tenant's default scale.
    Fill it (e.g. "primary", "secondary", "university") to scope the
    override to a single academic division.
    """

    list_display = (
        "school",
        "grade_scale",
        "context_key",
        "is_default",
        "effective_from",
        "effective_until",
        "updated_at",
    )
    list_filter = ("is_default", "context_key")
    search_fields = ("school__name", "grade_scale__code", "grade_scale__name")
    readonly_fields = ("created_at", "updated_at")
