"""
Forms for the lost-belongings QR micro-friction workflow (batch 1509).
"""

from __future__ import annotations

from django import forms


class MintTagForm(forms.Form):
    asset_id = forms.CharField(
        max_length=128,
        help_text="Internal asset identifier (e.g. inventory tag, bag SKU).",
    )
    label_hint = forms.CharField(
        max_length=80,
        help_text="Descriptive label visible on the QR sticker (e.g. 'blue lunch bag'). NEVER include a name or email.",
    )

    def clean_label_hint(self) -> str:
        value = (self.cleaned_data.get("label_hint") or "").strip()
        if "@" in value:
            raise forms.ValidationError("label_hint must not contain an email-like substring")
        return value[:80]


class FinderSightingForm(forms.Form):
    short_code = forms.CharField(
        max_length=32,
        help_text="The short code printed on the QR sticker.",
    )
    notes = forms.CharField(
        required=False,
        max_length=280,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Optional short note from the finder. Phone numbers, addresses, SSN/DOB are auto-redacted.",
    )
    notify_parent = forms.BooleanField(required=False, initial=True)


class StaffRecoveryForm(forms.Form):
    short_code = forms.CharField(max_length=32)
    staff_id = forms.CharField(
        max_length=128,
        help_text="Staff member confirming recovery. Hashed before logging.",
    )
    notes = forms.CharField(required=False, max_length=280, widget=forms.Textarea(attrs={"rows": 3}))
