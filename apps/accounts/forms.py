from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.utils import timezone

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


class EditRoleForm(forms.Form):
    """Edit an existing role's description and permissions (used in RBAC Edit Role modal)."""
    role_id = forms.IntegerField(widget=forms.HiddenInput)
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    def __init__(self, role=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if role is not None:
            self.fields["role_id"].initial = role.pk
            self.fields["description"].initial = role.description or ""
            self.fields["permissions"].initial = list(role.permissions.all())


class UserRoleForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=True,
        empty_label="Select user",
    )
    roles = forms.ModelMultipleChoiceField(
        queryset=AccessRole.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].widget.attrs.update({"class": "form-select"})


class TemporaryRoleGrantForm(forms.Form):
    """Grant a role to a user with an expiry date (e.g. auditor for one month)."""
    user = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=True,
        empty_label="Select user",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    role = forms.ModelChoiceField(
        queryset=AccessRole.objects.all(),
        required=True,
        empty_label="Select role",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    expires_at = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        help_text="Grant stops being active after this date (end of day).",
    )
    valid_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        help_text="Optional: grant active from this date.",
    )
    notes = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. External auditor"}),
    )

    def clean_expires_at(self):
        value = self.cleaned_data.get("expires_at")
        if value and value < timezone.localdate():
            raise ValidationError("Expiry date must be today or in the future.")
        return value


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


class UserProfileEditForm(forms.ModelForm):
    """My profile: edit name, email, profile photo (user can only edit self)."""
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "profile_photo"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email"}),
            "profile_photo": forms.FileInput(attrs={"class": "form-control", "accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = False
        self.fields["profile_photo"].required = False


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
