"""
Form for the permission-to-pay micro-friction workflow (batch 1509).

Validates inputs for `apps.finance.permission_to_pay.open_request` and the
guardian-approval step.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import forms


_APPROVAL_METHODS = (
    ("portal", "Tenant portal"),
    ("sms", "SMS"),
    ("email", "Email"),
    ("in_person", "In person"),
)


class OpenPermissionToPayForm(forms.Form):
    student_id = forms.CharField(
        max_length=128,
        help_text="Internal student identifier. Hashed before any audit event.",
    )
    event_code = forms.CharField(
        max_length=64,
        help_text="Short event code (e.g. excursion_2026_q3, lab_kit_2026).",
    )
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    currency = forms.CharField(
        max_length=3,
        min_length=3,
        help_text="ISO 4217 currency code (USD, EUR, KES, ...).",
    )
    guardian_threshold = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        help_text="Amount at or above which guardian approval is required.",
    )

    def clean_currency(self) -> str:
        value = (self.cleaned_data.get("currency") or "").strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise forms.ValidationError("currency must be 3 alphabetic characters (ISO 4217)")
        return value


class RecordGuardianApprovalForm(forms.Form):
    guardian_id = forms.CharField(
        max_length=128,
        help_text="Internal guardian identifier. Hashed before recording.",
    )
    approved_at_iso = forms.CharField(
        max_length=64,
        help_text="ISO-8601 timestamp of the guardian approval.",
    )
    method = forms.ChoiceField(choices=_APPROVAL_METHODS)
