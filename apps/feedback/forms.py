from django import forms

from .models import FeatureRequest, FeedbackSubmission, SurveyResponse


class FeedbackSubmissionForm(forms.Form):
    title = forms.CharField(max_length=180)
    category = forms.ChoiceField(choices=FeedbackSubmission.Category.choices)
    module = forms.CharField(max_length=80, required=False)
    route = forms.CharField(max_length=255, required=False)
    severity = forms.ChoiceField(choices=FeedbackSubmission.Severity.choices)
    privacy_level = forms.ChoiceField(choices=FeedbackSubmission.PrivacyLevel.choices)
    contact_preference = forms.CharField(max_length=80, required=False)
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}))


class RoleFeedbackForm(FeedbackSubmissionForm):
    def __init__(self, *args, role_categories=None, **kwargs):
        super().__init__(*args, **kwargs)
        if role_categories:
            self.fields["category"].choices = role_categories


class FeatureRequestForm(forms.Form):
    title = forms.CharField(max_length=180)
    problem_statement = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))
    proposed_solution = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    current_workaround = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    affected_roles = forms.CharField(required=False, help_text="Comma-separated roles")
    module = forms.CharField(max_length=80, required=False)
    impact = forms.ChoiceField(choices=FeatureRequest.Impact.choices)
    urgency = forms.ChoiceField(choices=FeatureRequest.Urgency.choices)
    school_type = forms.CharField(max_length=80, required=False)
    region = forms.CharField(max_length=80, required=False)
    pilot_interest = forms.BooleanField(required=False)


class SurveyResponseForm(forms.Form):
    survey_type = forms.ChoiceField(choices=SurveyResponse.SurveyType.choices)
    workflow = forms.CharField(max_length=80, required=False)
    score = forms.IntegerField(min_value=0, max_value=10)
    route = forms.CharField(max_length=255, required=False)
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
