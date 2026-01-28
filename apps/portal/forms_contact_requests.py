from __future__ import annotations

from django import forms

from apps.accounts.models import User
from apps.communication.models import ContactRequest
from apps.people.models import StudentProfile


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)
        self.widget = MultiFileInput(attrs={"class": "form-control", "multiple": True})

    def clean(self, data, initial=None):
        # data can be a list from request.FILES.getlist
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            return list(data)
        return [data]


class ContactRequestCreateForm(forms.Form):
    student = forms.ModelChoiceField(
        queryset=StudentProfile.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Optional: choose the student this request is about.",
    )
    contact_name = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control"}))
    contact_phone = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    contact_whatsapp = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    contact_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": "form-control"}))

    audience = forms.ChoiceField(choices=ContactRequest.Audience.choices, widget=forms.Select(attrs={"class": "form-select"}))
    preferred_channel = forms.ChoiceField(
        choices=ContactRequest.Channel.choices, widget=forms.Select(attrs={"class": "form-select"})
    )
    desired_staff = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Optional: pick a specific staff member (if you know them).",
    )
    subject = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control"}))
    message = forms.CharField(widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}))
    attachments = MultiFileField(help_text="Optional: attach screenshots, documents, or images (max 10MB each).")

    def __init__(self, *args, parent: User | None = None, students=None, **kwargs):
        super().__init__(*args, **kwargs)
        students = students or []
        self.fields["student"].queryset = StudentProfile.objects.filter(id__in=[s.id for s in students])

        # Keep this broad: any staff/superuser can be chosen if parent knows them.
        self.fields["desired_staff"].queryset = User.objects.filter(is_staff=True).order_by("first_name", "last_name", "username")

        if parent:
            full = (parent.get_full_name() or "").strip()
            self.fields["contact_name"].initial = full or parent.username
            self.fields["contact_email"].initial = parent.email or ""


class ContactRequestAssignForm(forms.ModelForm):
    class Meta:
        model = ContactRequest
        fields = ["assigned_to", "triage_notes"]
        widgets = {
            "assigned_to": forms.Select(attrs={"class": "form-select"}),
            "triage_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(is_staff=True).order_by("first_name", "last_name", "username")


class ContactRequestUpdateStatusForm(forms.ModelForm):
    class Meta:
        model = ContactRequest
        fields = ["status", "resolution_notes"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "resolution_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

