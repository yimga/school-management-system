"""The Sync Center's editor for the policy that sits AROUND the schedule rules.

Two settings, both of which used to be decisions the product made silently:

* the CHECK-IN CEILING -- previously ``RMC_EDGE_SYNC_IDLE_CEILING_SECONDS``, an
  environment variable on a host the school cannot see, which meant a tenant who asked
  for "06:00 and 18:00 only" got hourly check-ins and no way to learn that or change it;
* CATCH-UP -- documented in three places and implemented in none, so the panel would say
  "missed window" while the box quietly waited for the next scheduled time.

Named choices rather than a free integer box, for the same reason the interval field
uses them: "how long may this box stay silent?" has about six real answers, and a text
box invites the seventh. Each choice states the CONSEQUENCE, because the trade-off is not
guessable from the number -- the ceiling is also the longest an operator's "Queue full
resync" can take to reach this box.
"""
from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.sync_engine.models_policy import (
    MAX_IDLE_CEILING_MINUTES,
    MIN_IDLE_CEILING_MINUTES,
    SyncPolicy,
)

# Every label carries its consequence. A school choosing "twice a day" is choosing to
# wait up to twelve hours for an operator instruction, and that has to be on the label
# rather than in a doc nobody opens.
IDLE_CEILING_CHOICES = (
    (15, _("Every 15 minutes — instructions arrive almost immediately")),
    (30, _("Every 30 minutes")),
    (60, _("Every hour (recommended)")),
    (180, _("Every 3 hours")),  # magic-number-allow: check-in choice, minutes, self-labelled
    (360, _("Every 6 hours — instructions can take that long to arrive")),  # magic-number-allow: check-in choice, minutes, self-labelled
    (720, _("Twice a day — slowest; the box is nearly unreachable between check-ins")),  # magic-number-allow: check-in choice, minutes, self-labelled
    (MAX_IDLE_CEILING_MINUTES, _("Once a day — the longest allowed")),
)


class SyncPolicyForm(forms.ModelForm):
    """Field names match the model's, for the reason documented in forms_sync_schedule."""

    idle_ceiling_minutes = forms.TypedChoiceField(
        choices=IDLE_CEILING_CHOICES,
        coerce=int,
        required=True,
        label=_("Check in at least"),
        help_text=_(
            "Even when nothing is scheduled, the box checks in this often. The cloud "
            "cannot contact a box, so this is also how long an instruction from support "
            "can take to reach it."
        ),
    )

    class Meta:
        model = SyncPolicy
        fields = ("idle_ceiling_minutes", "catch_up_missed")
        labels = {"catch_up_missed": _("Catch up after a missed time")}
        help_texts = {
            "catch_up_missed": _(
                "If the box was off or offline when a sync was due, sync once as soon as "
                "it is back instead of waiting for the next scheduled time."
            )
        }

    def clean_idle_ceiling_minutes(self):
        value = self.cleaned_data.get("idle_ceiling_minutes")
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise forms.ValidationError(_("Choose one of the listed check-in times."))
        # Bounds re-checked here as well as in the model: the choice list is the friendly
        # path, not the security boundary, and a POST does not have to come from the form.
        if not (MIN_IDLE_CEILING_MINUTES <= value <= MAX_IDLE_CEILING_MINUTES):
            raise forms.ValidationError(_("Choose one of the listed check-in times."))
        return value
