from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import AccessRole, Permission, User, UserPreference
from .delegation import get_allowed_delegate_queryset, SCOPE_CHOICES
from apps.siteconfig.config_service import get_effective_site_settings


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
            "show_background_logo": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "background_logo_opacity": forms.NumberInput(
                attrs={"class": "form-range", "min": 0, "max": 1, "step": 0.01}
            ),
            "high_contrast_mode": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
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
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )
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
        queryset=User.objects.none(),
        required=True,
        empty_label="Select user",
    )
    # tenant-isolation-allow: class-level-queryset-overridden-in-form-init-via-roles-queryset-for-school
    roles = forms.ModelMultipleChoiceField(
        queryset=AccessRole.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].widget.attrs.update({"class": "form-select"})
        if school is not None:
            from apps.accounts.tenant_identity import users_queryset_for_school
            from apps.accounts.access_roles import roles_queryset_for_school

            self.fields["user"].queryset = users_queryset_for_school(school)
            self.fields["roles"].queryset = roles_queryset_for_school(school)


class TemporaryRoleGrantForm(forms.Form):
    """Grant a role to a user with an expiry date (e.g. auditor for one month)."""

    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=True,
        empty_label="Select user",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    # tenant-isolation-allow: class-level-queryset-overridden-in-form-init-via-roles-queryset-for-school
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
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. External auditor"}
        ),
    )

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school is not None:
            from apps.accounts.tenant_identity import users_queryset_for_school
            from apps.accounts.access_roles import roles_queryset_for_school

            self.fields["user"].queryset = users_queryset_for_school(school)
            self.fields["role"].queryset = roles_queryset_for_school(school)

    def clean_expires_at(self):
        value = self.cleaned_data.get("expires_at")
        if value and value < timezone.localdate():
            raise ValidationError("Expiry date must be today or in the future.")
        return value


class UserPermissionForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.none())
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].widget.attrs.update({"class": "form-select"})
        if school is not None:
            from apps.accounts.tenant_identity import users_queryset_for_school

            self.fields["user"].queryset = users_queryset_for_school(school)


class UserProfileEditForm(forms.ModelForm):
    """My profile: edit name, email, profile photo (user can only edit self).

    The form is role-aware and only ever exposes *safe*, self-owned fields:

    * **Teachers / staff** can self-edit their contact phone
      (``TeacherProfile.phone`` — the generic staff profile). Sensitive role
      data (pay scale, salary, permissions, staff_id) stays admin-managed and
      is never exposed here.
    * **Parents / guardians** can self-edit their contact details and
      notification preferences (``StudentGuardian`` phone / WhatsApp / address /
      preferred channel + the three ``receives_*`` toggles). A parent holds one
      link per child; on save the values are written uniformly across every
      link so their contact stays consistent for all their children. The
      admin-managed permission fields (``can_view_results`` / ``can_view_finance``)
      are never exposed.

    Each block of extra fields is added only when the user actually has the
    matching profile, so a user sees exactly the fields they own and nothing
    more.
    """

    contact_phone = forms.CharField(
        required=False,
        max_length=50,  # matches TeacherProfile.phone
        label="Contact phone",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Contact phone",
                "autocomplete": "tel",
                "inputmode": "tel",
            }
        ),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "profile_photo"]
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "First name"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Last name"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "Email"}
            ),
            "profile_photo": forms.FileInput(
                attrs={"class": "form-control", "accept": "image/*"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = False
        self.fields["profile_photo"].required = False

        from django.core.exceptions import ObjectDoesNotExist

        self._teacher_profile = None
        instance = getattr(self, "instance", None)
        if instance is not None and getattr(instance, "pk", None):
            try:
                self._teacher_profile = instance.teacher_profile
            except ObjectDoesNotExist:
                self._teacher_profile = None
        if self._teacher_profile is not None:
            self.fields["contact_phone"].initial = self._teacher_profile.phone or ""
        else:
            # Only teachers/staff have a self-editable role-profile contact field.
            self.fields.pop("contact_phone", None)

        # Parent/guardian contact + notification self-edit. A guardian holds one
        # StudentGuardian link per child; contact details are logically
        # per-parent, so we surface a single set of fields (seeded from a
        # representative link) and write them uniformly across every link on
        # save. Fields are added only when the user actually has guardian links,
        # so non-parents never see them. Permission fields (can_view_results /
        # can_view_finance) are admin-managed and deliberately never surfaced.
        self._guardian_links = []
        if instance is not None and getattr(instance, "pk", None):
            self._guardian_links = list(instance.guardian_links.all())
        if self._guardian_links:
            from apps.people.models import StudentGuardian

            rep = self._guardian_links[0]

            def _guardian_max_length(field_name):
                # Derive widths from the model so they never drift / hardcode.
                return StudentGuardian._meta.get_field(field_name).max_length

            self.fields["guardian_phone"] = forms.CharField(
                required=False,
                max_length=_guardian_max_length("phone"),
                label="Phone",
                initial=rep.phone or "",
                widget=forms.TextInput(
                    attrs={
                        "class": "form-control",
                        "placeholder": "Phone",
                        "autocomplete": "tel",
                        "inputmode": "tel",
                    }
                ),
            )
            self.fields["guardian_whatsapp"] = forms.CharField(
                required=False,
                max_length=_guardian_max_length("whatsapp_number"),
                label="WhatsApp number",
                initial=rep.whatsapp_number or "",
                widget=forms.TextInput(
                    attrs={
                        "class": "form-control",
                        "placeholder": "WhatsApp number",
                        "autocomplete": "tel",
                        "inputmode": "tel",
                    }
                ),
            )
            self.fields["guardian_address"] = forms.CharField(
                required=False,
                max_length=_guardian_max_length("address"),
                label="Address",
                initial=rep.address or "",
                widget=forms.TextInput(
                    attrs={
                        "class": "form-control",
                        "placeholder": "Address",
                        "autocomplete": "street-address",
                    }
                ),
            )
            self.fields["preferred_contact"] = forms.ChoiceField(
                required=False,
                label="Preferred contact method",
                choices=StudentGuardian.PreferredContact.choices,
                initial=rep.preferred_contact,
                widget=forms.Select(attrs={"class": "form-select"}),
            )
            self.fields["receives_email"] = forms.BooleanField(
                required=False,
                label="Email notifications",
                initial=rep.receives_email,
                widget=forms.CheckboxInput(
                    attrs={"class": "form-check-input", "role": "switch"}
                ),
            )
            self.fields["receives_sms"] = forms.BooleanField(
                required=False,
                label="SMS notifications",
                initial=rep.receives_sms,
                widget=forms.CheckboxInput(
                    attrs={"class": "form-check-input", "role": "switch"}
                ),
            )
            self.fields["receives_whatsapp"] = forms.BooleanField(
                required=False,
                label="WhatsApp notifications",
                initial=rep.receives_whatsapp,
                widget=forms.CheckboxInput(
                    attrs={"class": "form-check-input", "role": "switch"}
                ),
            )

    def save(self, commit: bool = True):
        user = super().save(commit=commit)
        profile = getattr(self, "_teacher_profile", None)
        if commit and profile is not None and "contact_phone" in self.cleaned_data:
            new_phone = (self.cleaned_data.get("contact_phone") or "").strip()
            if profile.phone != new_phone:
                profile.phone = new_phone
                profile.save(update_fields=["phone"])

        links = getattr(self, "_guardian_links", None)
        if commit and links and "guardian_phone" in self.cleaned_data:
            cd = self.cleaned_data
            updates = {
                "phone": (cd.get("guardian_phone") or "").strip(),
                "whatsapp_number": (cd.get("guardian_whatsapp") or "").strip(),
                "address": (cd.get("guardian_address") or "").strip(),
                "receives_email": bool(cd.get("receives_email")),
                "receives_sms": bool(cd.get("receives_sms")),
                "receives_whatsapp": bool(cd.get("receives_whatsapp")),
            }
            preferred = cd.get("preferred_contact")
            if preferred:
                # Skip an empty submission rather than write an invalid choice.
                updates["preferred_contact"] = preferred
            update_fields = list(updates.keys())
            for link in links:
                for model_field, value in updates.items():
                    setattr(link, model_field, value)
                link.save(update_fields=update_fields)
        return user


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
        from apps.portal.models import PendingGuardianInvite

        token = self.cleaned_data["token"].strip()
        try:
            invite = PendingGuardianInvite.objects.select_related("student").get(
                token=token
            )
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


# Delegation (Out of Office) form – used in views_delegation
class DelegationForm(forms.Form):
    delegate = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=True,
        empty_label="Select who will act on your behalf",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    start_date = forms.DateTimeField(
        required=True,
        widget=forms.DateTimeInput(
            attrs={"class": "form-control", "type": "datetime-local"}
        ),
        help_text="When the delegation becomes active.",
    )
    end_date = forms.DateTimeField(
        required=True,
        widget=forms.DateTimeInput(
            attrs={"class": "form-control", "type": "datetime-local"}
        ),
        help_text="When the delegation ends (max duration set by admin).",
    )
    scope = forms.MultipleChoiceField(
        choices=SCOPE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        help_text="Leave empty for “all” workflows.",
    )
    reason = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. Annual leave"}
        ),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def __init__(self, delegator, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.delegator = delegator
        self.fields["delegate"].queryset = get_allowed_delegate_queryset(delegator)

    def clean_end_date(self):
        start = self.cleaned_data.get("start_date")
        end = self.cleaned_data.get("end_date")
        if start and end and end <= start:
            raise ValidationError("End date must be after start date.")
        if start and end and self.delegator:
            teacher_profile = getattr(self.delegator, "teacher_profile", None)
            school = getattr(teacher_profile, "school", None)
            site = get_effective_site_settings(school=school)
            max_days = getattr(site, "delegation_max_days", 14) or 14
            if (end - start).days > max_days:
                raise ValidationError(
                    f"Duration cannot exceed {max_days} days (admin setting)."
                )
        return end

    def clean_delegate(self):
        delegate = self.cleaned_data.get("delegate")
        if delegate and self.delegator and delegate.pk == self.delegator.pk:
            raise ValidationError("You cannot delegate to yourself.")
        return delegate
