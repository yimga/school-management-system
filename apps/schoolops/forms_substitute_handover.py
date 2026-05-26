"""
Form for the substitute-handover micro-friction workflow (batch 1509).

Provides input validation for `apps.schoolops.substitute_handover.build_packet`.
Field-level constraints intentionally mirror the service's invariants:
- absence_end > absence_start
- tenant_id / teacher_id / substitute_id non-empty
- expose_medical_iep defaults False (gated by default)
"""

from __future__ import annotations

import json
from datetime import datetime

from django import forms
from django.utils import timezone


class SubstituteHandoverForm(forms.Form):
    teacher_id = forms.CharField(
        max_length=128,
        help_text="Internal teacher identifier. Hashed before any audit event.",
    )
    substitute_id = forms.CharField(
        max_length=128,
        help_text="Internal substitute identifier. Hashed before any audit event.",
    )
    absence_start = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    absence_end = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    reason_code = forms.CharField(
        required=False,
        max_length=64,
        initial="unspecified",
        help_text="Short reason code (e.g. sick, training). No free-text comments.",
    )
    grace_minutes = forms.IntegerField(
        min_value=0,
        max_value=240,
        initial=30,
        help_text="Window (minutes) before/after the absence during which the packet is valid.",
    )
    seating_chart_ref = forms.CharField(
        required=False,
        max_length=128,
        help_text="Reference key to a seating chart asset (no inline student names).",
    )
    expose_medical_iep = forms.BooleanField(
        required=False,
        initial=False,
        help_text="DEFAULT FALSE. Tick only when authorised by school admin.",
    )
    lesson_outline_json = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text='JSON array of {"period","topic","materials"} objects. Body content not echoed in audit.',
    )

    def clean_lesson_outline_json(self) -> list[dict]:
        raw = (self.cleaned_data.get("lesson_outline_json") or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"lesson_outline_json must be valid JSON: {exc}")
        if not isinstance(parsed, list):
            raise forms.ValidationError("lesson_outline_json must be a JSON array")
        for entry in parsed:
            if not isinstance(entry, dict):
                raise forms.ValidationError("each lesson_outline entry must be an object")
        return parsed

    def clean(self) -> dict:
        cleaned = super().clean()
        start: datetime | None = cleaned.get("absence_start")
        end: datetime | None = cleaned.get("absence_end")
        if start and end and end <= start:
            raise forms.ValidationError("absence_end must be strictly after absence_start")
        if start and end:
            # Normalize to aware UTC datetimes - the service requires both.
            if timezone.is_naive(start):
                cleaned["absence_start"] = timezone.make_aware(start, timezone.utc)
            if timezone.is_naive(end):
                cleaned["absence_end"] = timezone.make_aware(end, timezone.utc)
        return cleaned
