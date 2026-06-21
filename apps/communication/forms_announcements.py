"""
Enhanced forms for announcements with department support.
Supports draft, publish, and submit-for-approval (optional workflow).
"""

from django import forms
from apps.communication.models import (
    Announcement,
    AnnouncementAuditLog,
    ClassAnnouncement,
    log_announcement_audit,
)
from apps.academics.models import Department, Classroom


# Submit action: how the user is saving the announcement
SUBMIT_ACTION_PUBLISH = "publish"
SUBMIT_ACTION_DRAFT = "draft"
SUBMIT_ACTION_SUBMIT_FOR_APPROVAL = "submit_for_approval"


class AnnouncementCreateForm(forms.ModelForm):
    """Enhanced announcement form with department selection and optional status/approval."""

    send_to_department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Optional: Send this announcement to all teachers in a department",
    )

    #: Explicit recipient picker, surfaced only when Audience == "Specific Group".
    #: Declared (not auto-generated) so its queryset can be scoped to the school in
    #: ``__init__``; it is also listed in ``Meta.fields`` so ``_save_m2m`` persists
    #: the relation after the manual ``announcement.save()`` in ``save()``.
    specific_recipients = forms.ModelMultipleChoiceField(
        queryset=Announcement.specific_recipients.field.remote_field.model.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 8}),
        help_text=(
            "Only used when Audience is 'Specific Group' — the exact users in this "
            "school who should receive the announcement."
        ),
    )

    class Meta:
        model = Announcement
        fields = [
            "title",
            "content",
            "announcement_type",
            "audience",
            "specific_recipients",
            "is_urgent",
            "is_active",
            "expiry_date",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Announcement title"}
            ),
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Announcement content",
                }
            ),
            "announcement_type": forms.Select(attrs={"class": "form-select"}),
            "audience": forms.Select(attrs={"class": "form-select"}),
            "is_urgent": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "expiry_date": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
        }

    def __init__(self, *args, user=None, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.school = (
            school
            or getattr(getattr(self.instance, "school", None), "pk", None)
            and getattr(self.instance, "school", None)
        )

        if self.school is not None:
            self.fields["send_to_department"].queryset = Department.objects.filter(
                school=self.school
            ).order_by("name")
            # Scope the specific-recipient picker to this school's own users only.
            # Because the field is a ModelMultipleChoiceField, a POSTed pk outside
            # this queryset is rejected at validation — so the form layer is itself
            # a tenant boundary, on top of the school re-scope at fan-out time.
            from apps.communication.announcement_delivery import (
                _school_user_queryset,
            )

            self.fields["specific_recipients"].queryset = _school_user_queryset(
                self.school
            ).order_by("first_name", "last_name", "username")
        else:
            self.fields["send_to_department"].queryset = Department.objects.none()

        if (
            user
            and hasattr(user, "teacher_profile")
            and user.teacher_profile.department
        ):
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            self.fields["send_to_department"].queryset = Department.objects.filter(
                id=user.teacher_profile.department.id
            )

    def save(self, commit=True, submit_action=SUBMIT_ACTION_PUBLISH):
        announcement = super().save(commit=False)
        if self.user:
            announcement.created_by = self.user

        is_new = not announcement.pk
        if is_new:
            if submit_action == SUBMIT_ACTION_DRAFT:
                announcement.status = Announcement.Status.DRAFT
            elif submit_action == SUBMIT_ACTION_SUBMIT_FOR_APPROVAL:
                announcement.status = Announcement.Status.PENDING_APPROVAL
            else:
                announcement.status = Announcement.Status.PUBLISHED

        if commit:
            was_active = getattr(announcement, "_prev_is_active", None)
            if not is_new and announcement.pk:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                try:
                    prev = Announcement.objects.get(pk=announcement.pk)
                    was_active = prev.is_active
                except Announcement.DoesNotExist:
                    was_active = True
            announcement.save()
            # The instance now has a PK; persist the specific-recipients M2M.
            # ``_save_m2m`` honours ``Meta.fields`` (the field is listed there) and
            # only touches the school-scoped picks that passed validation.
            self.save_m2m()

            if is_new:
                log_announcement_audit(
                    announcement,
                    self.user,
                    AnnouncementAuditLog.Action.SUBMITTED_FOR_APPROVAL
                    if submit_action == SUBMIT_ACTION_SUBMIT_FOR_APPROVAL
                    else AnnouncementAuditLog.Action.CREATED,
                    notes="Submitted for approval"
                    if submit_action == SUBMIT_ACTION_SUBMIT_FOR_APPROVAL
                    else "",
                )
            else:
                log_announcement_audit(
                    announcement, self.user, AnnouncementAuditLog.Action.UPDATED
                )
                if was_active and not announcement.is_active:
                    log_announcement_audit(
                        announcement, self.user, AnnouncementAuditLog.Action.DEACTIVATED
                    )

            department = self.cleaned_data.get("send_to_department")
            if department and is_new:
                ClassAnnouncement.objects.create(
                    title=announcement.title,
                    body=announcement.content,
                    department=department,
                    audience=ClassAnnouncement.Audience.TEACHERS,
                    created_by=self.user,
                    is_active=True,
                )

        return announcement


class ClassAnnouncementForm(forms.ModelForm):
    """Form for class/department announcements."""

    class Meta:
        model = ClassAnnouncement
        fields = ["title", "body", "classroom", "department", "audience", "is_pinned"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "audience": forms.Select(attrs={"class": "form-select"}),
            "is_pinned": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, user=None, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.school = (
            school
            or getattr(getattr(self.instance, "school", None), "pk", None)
            and getattr(self.instance, "school", None)
        )

        if self.school is not None:
            self.fields["department"].queryset = Department.objects.filter(
                school=self.school
            ).order_by("name")
            self.fields["classroom"].queryset = Classroom.objects.filter(
                school=self.school
            ).order_by("name")
        else:
            self.fields["department"].queryset = Department.objects.none()
            self.fields["classroom"].queryset = Classroom.objects.none()

        # If user is a teacher, limit department choices
        if (
            user
            and hasattr(user, "teacher_profile")
            and user.teacher_profile.department
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        ):
            self.fields["department"].queryset = Department.objects.filter(
                id=user.teacher_profile.department.id
            )

    def clean(self):
        cleaned_data = super().clean()
        classroom = cleaned_data.get("classroom")
        department = cleaned_data.get("department")

        if not classroom and not department:
            raise forms.ValidationError(
                "Either classroom or department must be selected"
            )

        if classroom and department:
            raise forms.ValidationError(
                "Select either classroom OR department, not both"
            )

        return cleaned_data

    def save(self, commit=True):
        announcement = super().save(commit=False)
        if self.user:
            announcement.created_by = self.user
        if commit:
            announcement.save()
        return announcement
