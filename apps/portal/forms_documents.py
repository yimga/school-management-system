"""
Forms for Document Library Management
"""

from django import forms
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.people.models import StudentProfile
from .models import PortalFeatureItem, FormSignature


class DocumentUploadForm(forms.ModelForm):
    """Form for uploading/editing documents"""
    
    class Meta:
        model = PortalFeatureItem
        fields = [
            "title",
            "description",
            "document_type",
            "file",
            "link",
            "requires_signature",
            "visible_to_roles",
            "is_active",
        ]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g., Registration Form 2026"
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Brief description of the document..."
            }),
            "document_type": forms.Select(attrs={"class": "form-select"}),
            "file": forms.FileInput(attrs={
                "class": "form-control",
                "accept": ".pdf,.doc,.docx,.xls,.xlsx"
            }),
            "link": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "https://example.com/document.pdf"
            }),
            "requires_signature": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "visible_to_roles": forms.SelectMultiple(attrs={
                "class": "form-select",
                "size": 6
            }),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Role choices for visibility
        role_choices = [
            ("ADMIN", "Admin"),
            ("TEACHER", "Teacher"),
            ("PARENT", "Parent"),
            ("STUDENT", "Student"),
        ]
        self.fields["visible_to_roles"].choices = role_choices
        self.fields["visible_to_roles"].help_text = (
            "Select roles that can view this document. Leave empty for all authenticated users."
        )
        
        # Make file/link optional in form (validation in model)
        self.fields["file"].required = False
        self.fields["link"].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        file = cleaned_data.get("file")
        link = cleaned_data.get("link")
        
        # Ensure either file or link is provided
        if not file and not link:
            raise ValidationError("Either a file or link must be provided.")
        
        if file and link:
            raise ValidationError("Provide either a file OR a link, not both.")
        
        # If requires_signature, must be a FORM type
        if cleaned_data.get("requires_signature") and cleaned_data.get("document_type") != PortalFeatureItem.DocumentType.FORM:
            raise ValidationError("Only FORM documents can require signatures.")
        
        return cleaned_data


class SignatureRequestForm(forms.ModelForm):
    """Form for creating signature requests"""
    
    class Meta:
        model = FormSignature
        fields = [
            "form_document",
            "student",
            "parent",
            "expires_at",
            "notes",
        ]
        widgets = {
            "form_document": forms.Select(attrs={"class": "form-select"}),
            "student": forms.Select(attrs={"class": "form-select"}),
            "parent": forms.Select(attrs={"class": "form-select"}),
            "expires_at": forms.DateTimeInput(attrs={
                "class": "form-control",
                "type": "datetime-local"
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Optional notes for the parent..."
            }),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        
        # Only show forms that require signature
        self.fields["form_document"].queryset = PortalFeatureItem.objects.filter(
            feature=PortalFeatureItem.Feature.DOCUMENTS,
            requires_signature=True,
            is_active=True
        )
        
        # Only show active students
        self.fields["student"].queryset = StudentProfile.objects.filter(is_active=True)
        
        # Only show parent users
        self.fields["parent"].queryset = User.objects.filter(role=User.Role.PARENT)
        
        # Set default expiry (30 days from now)
        from django.utils import timezone
        from datetime import timedelta
        if not self.instance.pk:
            default_expiry = timezone.now() + timedelta(days=30)
            self.fields["expires_at"].initial = default_expiry
    
    def clean(self):
        cleaned_data = super().clean()
        form_document = cleaned_data.get("form_document")
        student = cleaned_data.get("student")
        parent = cleaned_data.get("parent")
        
        # Ensure form requires signature
        if form_document and not form_document.requires_signature:
            raise ValidationError("Selected document does not require signature.")
        
        # Check for duplicate signature requests
        if form_document and student and parent:
            existing = FormSignature.objects.filter(
                form_document=form_document,
                student=student,
                parent=parent,
                status=FormSignature.SignatureStatus.PENDING
            ).exclude(pk=self.instance.pk if self.instance.pk else None)
            
            if existing.exists():
                raise ValidationError(
                    "A pending signature request already exists for this form, student, and parent."
                )
        
        return cleaned_data
