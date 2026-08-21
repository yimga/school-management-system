"""The Sync Center's schedule editor.

WHO FILLS THIS IN. A school administrator, not an SRE. So: named interval choices rather
than a free integer box, day CHECKBOXES rather than a comma string, and never a cron
expression. Every refusal names the field and says what to do instead — a schedule that
saves cleanly and then silently never fires is the exact failure this feature exists to
remove, and it would be indistinguishable from a broken box.

WHY THE FORM FIELDS ARE NAMED AFTER THE MODEL'S. ``SyncSchedule.clean()`` is the single
validation implementation — it has to be, because the admin and any future API reach the
model without passing through this form. Django maps a model ``ValidationError`` dict onto
form fields BY NAME and raises ``ValueError`` for a key the form has no field for, so
friendlier names (``days``, ``interval_choice``) would turn "you picked no days" into a
500. The widgets are friendly; the names match the model.

They are declared but deliberately kept OUT of ``Meta.fields``: ``days_of_week`` arrives
from a checkbox group as a LIST and ``interval_minutes`` as a coerced int, neither of which
``construct_instance`` should write straight onto the model. ``clean()`` converts them to
the model's canonical scalar form, once.
"""
from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.sync_engine.models_schedule import (
    SyncSchedule,
    format_days,
    format_times,
    parse_times,
)
from apps.sync_engine.schedule import MAX_INTERVAL_MINUTES, MIN_INTERVAL_MINUTES, WEEKDAYS

# Named, because "how often?" is a question with about five real answers and a text box
# invites the sixth. The shortest offered matches the engine's own floor, so the form can
# never offer something the model will refuse.
INTERVAL_CHOICES = (
    (15, _("Every 15 minutes")),
    (30, _("Every 30 minutes")),
    (60, _("Every hour")),
    (120, _("Every 2 hours")),
    (240, _("Every 4 hours")),  # magic-number-allow: interval choice, minutes, self-labelled
    (480, _("Every 8 hours")),  # magic-number-allow: interval choice, minutes, self-labelled
)

DAY_CHOICES = tuple((str(value), _(label)) for value, label in WEEKDAYS)


class SyncScheduleForm(forms.ModelForm):
    """One rule. A tenant may hold several — term time and holidays are two rules."""

    days_of_week = forms.MultipleChoiceField(
        choices=DAY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("Days"),
    )
    interval_minutes = forms.TypedChoiceField(
        choices=INTERVAL_CHOICES,
        coerce=int,
        required=False,
        empty_value=None,
        label=_("How often"),
    )
    at_times = forms.CharField(
        required=False,
        label=_("Times"),
        help_text=_("Times of day, 24-hour, separated by commas. For example 06:00, 22:00"),
        widget=forms.TextInput(attrs={"placeholder": "06:00, 22:00"}),
    )

    class Meta:
        model = SyncSchedule
        fields = ("name", "is_enabled", "mode", "window_start", "window_end")
        widgets = {
            "window_start": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "window_end": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }
        labels = {
            "name": _("Name"),
            "is_enabled": _("Active"),
            "mode": _("Type"),
            "window_start": _("From"),
            "window_end": _("Until"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if instance is not None and instance.pk:
            self.fields["days_of_week"].initial = [str(d) for d in sorted(instance.days)]
            self.fields["interval_minutes"].initial = instance.interval_minutes
            self.fields["at_times"].initial = ", ".join(
                t.strftime("%H:%M") for t in instance.times
            )
        else:
            # A new rule opens on the shape most schools want, so the common case is two
            # clicks rather than eight decisions.
            self.fields["days_of_week"].initial = ["0", "1", "2", "3", "4"]
            self.fields["interval_minutes"].initial = 30

    def clean_at_times(self):
        raw = (self.cleaned_data.get("at_times") or "").strip()
        if not raw:
            return ""
        parsed = parse_times(raw)
        if not parsed:
            raise forms.ValidationError(
                _("Use 24-hour times separated by commas, for example 06:00, 22:00.")
            )
        return format_times(parsed)

    def clean_interval_minutes(self):
        value = self.cleaned_data.get("interval_minutes")
        if value in (None, ""):
            return None
        value = int(value)
        if not (MIN_INTERVAL_MINUTES <= value <= MAX_INTERVAL_MINUTES):
            raise forms.ValidationError(_("Choose one of the listed intervals."))
        return value

    def clean_days_of_week(self):
        return format_days(int(d) for d in (self.cleaned_data.get("days_of_week") or []))

    def clean(self):
        data = super().clean()
        # Put the canonical scalar form on the instance BEFORE Django runs the model's own
        # clean() in _post_clean, so there is exactly one validation implementation and the
        # form can never accept something the engine would refuse.
        self.instance.days_of_week = data.get("days_of_week") or ""
        self.instance.interval_minutes = data.get("interval_minutes")
        self.instance.at_times = data.get("at_times") or ""
        return data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.days_of_week = self.cleaned_data.get("days_of_week") or ""
        instance.interval_minutes = self.cleaned_data.get("interval_minutes")
        instance.at_times = self.cleaned_data.get("at_times") or ""
        if commit:
            instance.save()
        return instance
