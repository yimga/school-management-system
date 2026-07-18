"""Athletics HTTP-layer forms.

Every ModelChoiceField queryset is school-scoped in ``__init__`` (the view passes
``school=request.school``) so a coach/admin can never pick another tenant's venue,
sport, academic year, or student. Plain ``Form`` classes are used where the write is
owned by a service (schedule-fixture / record-result / request-consent) so the form
only validates + normalizes input and the service performs the mutation.
"""

from __future__ import annotations

from django import forms

from apps.athletics.models import Fixture, Season


_TEXT = {"class": "form-control"}
_SELECT = {"class": "form-select"}
_DATETIME = {"class": "form-control", "type": "datetime-local"}
_DATE = {"class": "form-control", "type": "date"}


class ScheduleFixtureForm(forms.Form):
    """Validate a coach's request to schedule a fixture (the service creates it)."""

    opponent_name = forms.CharField(
        max_length=200, widget=forms.TextInput(attrs=_TEXT)
    )
    fixture_type = forms.ChoiceField(
        choices=Fixture.FixtureType.choices, widget=forms.Select(attrs=_SELECT)
    )
    venue = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs=_SELECT),
        help_text="Home venue to book (leave blank for away/neutral fixtures).",
    )
    scheduled_start = forms.DateTimeField(widget=forms.DateTimeInput(attrs=_DATETIME))
    scheduled_end = forms.DateTimeField(widget=forms.DateTimeInput(attrs=_DATETIME))
    book_venue = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Reserve the venue (fails if it double-books an overlapping slot).",
    )

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.school_events.models import EventVenue

        if school is not None:
            self.fields["venue"].queryset = EventVenue.objects.filter(
                school=school, is_active=True
            ).order_by("name")
        else:
            self.fields["venue"].queryset = EventVenue.objects.none()

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("scheduled_start")
        end = cleaned.get("scheduled_end")
        if start and end and end <= start:
            self.add_error("scheduled_end", "End time must be after the start time.")
        return cleaned


class RecordResultForm(forms.Form):
    """Validate a fixture score (the service creates the FixtureResult)."""

    home_score = forms.IntegerField(
        min_value=0, widget=forms.NumberInput(attrs=_TEXT)
    )
    away_score = forms.IntegerField(
        min_value=0, widget=forms.NumberInput(attrs=_TEXT)
    )
    notes = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2})
    )


class RequestConsentForm(forms.Form):
    """Capture the guardian address a participation-consent token is minted for."""

    guardian_name = forms.CharField(
        max_length=256, widget=forms.TextInput(attrs=_TEXT)
    )
    guardian_email = forms.EmailField(widget=forms.EmailInput(attrs=_TEXT))


class RecordClearanceForm(forms.Form):
    """Record a fitness-to-play medical clearance (the service sets CLEARED).

    Every field is optional: the one-click roster surface submits an empty form
    and the service applies sensible defaults (today .. today+validity, the
    team's sport). A richer surface may pass an explicit window, sport, or notes.
    The service performs the write and stamps ``cleared_by`` — the form only
    validates + scopes ``sport`` to the school.
    """

    sport = forms.ModelChoiceField(
        queryset=None, required=False, widget=forms.Select(attrs=_SELECT)
    )
    valid_from = forms.DateField(
        required=False, widget=forms.DateInput(attrs=_DATE)
    )
    valid_until = forms.DateField(
        required=False, widget=forms.DateInput(attrs=_DATE)
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.athletics.models import Sport

        if school is not None:
            self.fields["sport"].queryset = Sport.objects.filter(
                school=school, is_active=True
            ).order_by("name")
        else:
            self.fields["sport"].queryset = Sport.objects.none()

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("valid_from")
        end = cleaned.get("valid_until")
        if start and end and end < start:
            self.add_error(
                "valid_until", "Valid-until cannot be before valid-from."
            )
        return cleaned


class AddMemberForm(forms.Form):
    """Add a student to a team roster (view creates the pending TeamMembership)."""

    student = forms.ModelChoiceField(
        queryset=None, widget=forms.Select(attrs=_SELECT)
    )
    jersey_number = forms.IntegerField(
        required=False, min_value=0, widget=forms.NumberInput(attrs=_TEXT)
    )
    position = forms.CharField(
        max_length=48, required=False, widget=forms.TextInput(attrs=_TEXT)
    )

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.people.models import StudentProfile

        if school is not None:
            self.fields["student"].queryset = StudentProfile.objects.filter(
                school=school, is_active=True
            ).order_by("last_name", "first_name")
        else:
            self.fields["student"].queryset = StudentProfile.objects.none()


class SeasonForm(forms.ModelForm):
    """Academic-leadership season admin. FK querysets scoped to the school."""

    class Meta:
        model = Season
        fields = [
            "sport",
            "academic_year",
            "name",
            "start_date",
            "end_date",
            "status",
        ]
        widgets = {
            "sport": forms.Select(attrs=_SELECT),
            "academic_year": forms.Select(attrs=_SELECT),
            "name": forms.TextInput(attrs=_TEXT),
            "start_date": forms.DateInput(attrs=_DATE),
            "end_date": forms.DateInput(attrs=_DATE),
            "status": forms.Select(attrs=_SELECT),
        }

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.academics.models import AcademicYear
        from apps.athletics.models import Sport

        if school is not None:
            self.fields["sport"].queryset = Sport.objects.filter(
                school=school, is_active=True
            ).order_by("name")
            self.fields["academic_year"].queryset = AcademicYear.objects.filter(
                school=school
            ).order_by("-start_date")
        else:
            self.fields["sport"].queryset = Sport.objects.none()
            self.fields["academic_year"].queryset = AcademicYear.objects.none()
        self.fields["academic_year"].required = False

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date cannot be before the start date.")
        # ``school`` is not a form field, so ModelForm.validate_unique skips the
        # (school, sport, academic_year, name) constraint. Enforce it here (the
        # view binds ``instance.school`` before is_valid) so a duplicate surfaces
        # as a form error rather than a DB IntegrityError 500 — and so a NULL
        # academic_year duplicate is not silently created either.
        from apps.athletics.models import Season

        school_id = getattr(self.instance, "school_id", None)
        sport = cleaned.get("sport")
        name = cleaned.get("name")
        if school_id and sport and name:
            dupes = Season.objects.filter(
                school_id=school_id,
                sport=sport,
                academic_year=cleaned.get("academic_year"),
                name=name,
            )
            if self.instance.pk:
                dupes = dupes.exclude(pk=self.instance.pk)
            if dupes.exists():
                self.add_error(
                    "name",
                    "A season with this sport, academic year, and name already exists.",
                )
        return cleaned
