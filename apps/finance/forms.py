from django import forms

from .models import ReportRequest


class ReportRequestForm(forms.ModelForm):
    class Meta:
        model = ReportRequest
        fields = ["report_type", "description"]
        widgets = {
            "report_type": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
