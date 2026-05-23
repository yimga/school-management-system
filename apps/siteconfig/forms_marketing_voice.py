"""Wave 15 (v3.62.20 — 2026-05-23) — per-tenant marketing voice rich-edit form.

Ports the Wave 13 ``CountryRegistryAdminForm`` rich-edit pattern from the
*country-wide* override (`CountryRegistry.cockpit_override_payload.
marketing_voice`) to the *per-tenant* override (`SiteSettings.cockpit_payload
[marketing_voice]`).

Same 15-field surface (14 scalars + 1 chips textarea); same `__init__`
pre-fill + `_build_marketing_voice_from_form` + `clean()` round-trip; same
"empty = omit so seed value wins" semantics.

Adds one Wave 15-specific extension: `per_page` mapping editor (JSON textarea)
so operators can ship page-specific overrides (e.g. only `/pricing/` gets a
bespoke headline).
"""

from __future__ import annotations

import json
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import SiteSettings


class MarketingVoiceForm(forms.ModelForm):
    """Per-tenant marketing voice rich-edit form.

    Writes to ``SiteSettings.cockpit_payload["marketing_voice"]`` while
    preserving every other top-level key in the payload.
    """

    # --- 14 scalar fields (mirrors CountryRegistryAdminForm) -------------

    mv_country_name = forms.CharField(required=False, max_length=120,
                                       label=_("Country name (display)"))
    mv_greeting = forms.CharField(required=False, max_length=120,
                                   label=_("Native greeting"),
                                   help_text=_("e.g. 'Karibu' (Swahili), 'Bienvenue' (French)."))
    mv_headline_lead = forms.CharField(required=False, max_length=240,
                                        label=_("Headline lead-in"))
    mv_headline_lead_native = forms.CharField(required=False, max_length=240,
                                               label=_("Headline lead-in — native language"),
                                               help_text=_("Optional — wins over English headline when visitor's "
                                                           "Accept-Language matches the market's native language."))
    mv_hero_subline = forms.CharField(required=False,
                                       widget=forms.Textarea(attrs={"rows": 2}),
                                       label=_("Hero subline"))
    mv_trust_count = forms.CharField(required=False, max_length=240,
                                      label=_("Trust line"),
                                      help_text=_("e.g. 'Trusted by schools across all 36 states + FCT'."))
    mv_currency_sample = forms.CharField(required=False, max_length=80,
                                          label=_("Sample fee"),
                                          help_text=_("e.g. '₦145,000 / term'."))
    mv_calendar_sample = forms.CharField(required=False, max_length=160,
                                          label=_("Sample calendar"),
                                          help_text=_("e.g. '3 terms — September to July'."))
    mv_regulatory_line = forms.CharField(required=False,
                                          widget=forms.Textarea(attrs={"rows": 2}),
                                          label=_("Regulatory line"))
    mv_anchor_city = forms.CharField(required=False, max_length=120,
                                      label=_("Anchor city"))
    mv_regional_phrase = forms.CharField(required=False, max_length=160,
                                          label=_("Regional phrase"))
    mv_testimonial_quote = forms.CharField(required=False,
                                            widget=forms.Textarea(attrs={"rows": 2}),
                                            label=_("Testimonial — quote"),
                                            help_text=_("Under ~140 characters reads best on the marketing band."))
    mv_testimonial_author = forms.CharField(required=False, max_length=160,
                                             label=_("Testimonial — author"))
    mv_testimonial_credential = forms.CharField(required=False, max_length=160,
                                                 label=_("Testimonial — credential"))
    mv_case_study_chips = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        label=_("Case-study chips"),
        help_text=_("One chip per line (3–5 works best)."),
    )

    # --- Wave 15 addition: per_page mapping editor ----------------------

    mv_per_page_json = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 6,
                                     "placeholder": '{"/pricing/": {"headline_lead": "..."}}'}),
        label=_("Per-page overrides (JSON)"),
        help_text=_(
            "Optional. JSON object mapping a page key (request path, URL "
            "name, view name, or '*') to a marketing-voice subset that "
            "overrides this tenant's defaults ONLY on that page. Leave "
            "blank to apply this tenant's voice to every marketing page."
        ),
    )

    class Meta:
        model = SiteSettings
        fields: list[str] = ["cockpit_payload"]
        widgets = {"cockpit_payload": forms.HiddenInput()}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        payload = getattr(self.instance, "cockpit_payload", None) or {}
        if not isinstance(payload, dict):
            payload = {}
        mv = payload.get("marketing_voice") or {}
        if not isinstance(mv, dict):
            mv = {}
        testimonial = mv.get("testimonial") if isinstance(mv.get("testimonial"), dict) else {}
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
        per_page = mv.get("per_page")
        if isinstance(per_page, dict) and per_page:
            self.fields["mv_per_page_json"].initial = json.dumps(per_page, indent=2, ensure_ascii=False)

    def _build_marketing_voice_from_form(self) -> dict[str, Any]:
        data = self.cleaned_data
        mv: dict[str, Any] = {}
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
        q = (data.get("mv_testimonial_quote") or "").strip()
        a = (data.get("mv_testimonial_author") or "").strip()
        c = (data.get("mv_testimonial_credential") or "").strip()
        if q or a or c:
            t: dict[str, str] = {}
            if q:
                t["quote"] = q
            if a:
                t["author"] = a
            if c:
                t["credential"] = c
            mv["testimonial"] = t
        chips_raw = (data.get("mv_case_study_chips") or "").strip()
        if chips_raw:
            chips = [line.strip() for line in chips_raw.splitlines() if line.strip()]
            if chips:
                mv["case_study_chips"] = chips
        per_page_raw = (data.get("mv_per_page_json") or "").strip()
        if per_page_raw:
            try:
                per_page = json.loads(per_page_raw)
            except json.JSONDecodeError:
                per_page = None
            if isinstance(per_page, dict) and per_page:
                # Sanitize: only accept dict values (page-key → mv subset).
                clean_per_page = {
                    str(k): v for k, v in per_page.items()
                    if isinstance(v, dict)
                }
                if clean_per_page:
                    mv["per_page"] = clean_per_page
        return mv

    def clean_mv_per_page_json(self) -> str:
        raw = (self.cleaned_data.get("mv_per_page_json") or "").strip()
        if not raw:
            return ""
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(
                _("Invalid JSON: %(msg)s. Expected an object mapping page "
                  "keys to marketing-voice subsets.") % {"msg": exc.msg}
            )
        if not isinstance(parsed, dict):
            raise forms.ValidationError(
                _("Expected a JSON object (dict) mapping page keys to "
                  "marketing-voice subsets.")
            )
        bad = [k for k, v in parsed.items() if not isinstance(v, dict)]
        if bad:
            raise forms.ValidationError(
                _("Each value in per_page must be a JSON object. Offending "
                  "keys: %(keys)s.") % {"keys": ", ".join(bad)}
            )
        return raw

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        payload = getattr(self.instance, "cockpit_payload", None) or {}
        if not isinstance(payload, dict):
            payload = {}
        payload = dict(payload)  # don't mutate the original
        rich_mv = self._build_marketing_voice_from_form()
        if rich_mv:
            payload["marketing_voice"] = rich_mv
        else:
            # Operator cleared every field — drop the key entirely so seed wins.
            payload.pop("marketing_voice", None)
        cleaned["cockpit_payload"] = payload
        return cleaned

    def save(self, commit: bool = True) -> SiteSettings:
        instance = super().save(commit=False)
        instance.cockpit_payload = self.cleaned_data.get("cockpit_payload", {})
        if commit:
            instance.save()
        return instance
