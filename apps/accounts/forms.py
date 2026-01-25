from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

from .models import AccessRole, Permission, User, UserPreference
from apps.portal.models import PendingGuardianInvite


# User preference form for background logo and opacity
class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = [
            "show_background_logo",
            "background_logo_opacity",
            "high_contrast_mode",
            "reduced_motion",
        ]
        widgets = {
            "show_background_logo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "background_logo_opacity": forms.NumberInput(attrs={"class": "form-range", "min": 0, "max": 1, "step": 0.01}),
            "high_contrast_mode": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "reduced_motion": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
class RoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = AccessRole
        fields = ["code", "name", "description", "permissions"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class PermissionForm(forms.ModelForm):
    class Meta:
        model = Permission
        fields = ["code", "name", "description"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class UserRoleForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.all())
    roles = forms.ModelMultipleChoiceField(
        queryset=AccessRole.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].widget.attrs.update({"class": "form-select"})


class UserPermissionForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.all())
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].widget.attrs.update({"class": "form-select"})


class ClaimInviteAccountForm(forms.Form):
    token = forms.CharField(
        label="Invite token",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    username = forms.CharField(
        label="Desired username",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
    first_name = forms.CharField(
        label="First name",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    last_name = forms.CharField(
        label="Last name",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        self.invite = None
        super().__init__(*args, **kwargs)

    def clean_token(self):
        token = self.cleaned_data["token"].strip()
        try:
            invite = PendingGuardianInvite.objects.select_related("student").get(token=token)
        except PendingGuardianInvite.DoesNotExist:
            raise forms.ValidationError("Invite not found.")
        if invite.is_claimed:
            raise forms.ValidationError("This invite has already been claimed.")
        self.invite = invite
        return token

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Username is already taken.")
        return username

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError("Passwords must match.")
            try:
                password_validation.validate_password(password1)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save_user(self) -> User:
        data = self.cleaned_data
        user = User.objects.create_user(
            username=data["username"],
            email=data["email"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            role=User.Role.PARENT,
            password=data["password1"],
        )
        return user
