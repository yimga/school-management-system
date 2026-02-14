"""
Forms for group/thread creation and management.
"""
from django import forms
from django.contrib.auth import get_user_model
from apps.communication.models import MessageThread
from apps.academics.models import Department, Classroom
from apps.accounts.models import User

User = get_user_model()


class MessageThreadCreateForm(forms.ModelForm):
    """Form for creating message threads/groups."""
    
    scope = forms.ChoiceField(
        choices=MessageThread.Scope.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select the scope for this group"
    )
    
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Required if scope is DEPARTMENT"
    )
    
    classroom = forms.ModelChoiceField(
        queryset=Classroom.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Required if scope is CLASSROOM"
    )
    
    audience_role = forms.ChoiceField(
        choices=[
            ('', 'All Roles'),
            ('TEACHER', 'Teachers Only'),
            ('PARENT', 'Parents Only'),
            ('STUDENT', 'Students Only'),
            ('STAFF', 'Staff Only'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Optional: Limit group to specific role"
    )
    
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '10'}),
        help_text="Select members for this group (optional - can add later)"
    )
    
    class Meta:
        model = MessageThread
        fields = ['title', 'description', 'scope', 'department', 'classroom', 'audience_role']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Math Department - Senior Teachers'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional description of this group'}),
        }
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        
        # If user is a teacher, limit department choices to their department
        if user and hasattr(user, 'teacher_profile') and user.teacher_profile.department:
            self.fields['department'].queryset = Department.objects.filter(
                id=user.teacher_profile.department.id
            )
            # Pre-select their department if scope is DEPARTMENT
            if not self.instance.pk and not self.data:
                self.fields['scope'].initial = MessageThread.Scope.DEPARTMENT
                self.fields['department'].initial = user.teacher_profile.department
        
        # Filter members based on scope when scope changes
        if 'scope' in self.data:
            scope = self.data.get('scope')
            if scope == MessageThread.Scope.DEPARTMENT:
                dept_id = self.data.get('department')
                if dept_id:
                    from apps.people.models import TeacherProfile
                    teachers = TeacherProfile.objects.filter(
                        department_id=dept_id, is_active=True
                    ).select_related('user')
                    self.fields['members'].queryset = User.objects.filter(
                        id__in=[t.user_id for t in teachers]
                    )
            elif scope == MessageThread.Scope.CLASSROOM:
                classroom_id = self.data.get('classroom')
                if classroom_id:
                    from apps.people.models import StudentProfile
                    students = StudentProfile.objects.filter(
                        classroom_id=classroom_id
                    ).select_related('user')
                    self.fields['members'].queryset = User.objects.filter(
                        id__in=[s.user_id for s in students if s.user_id]
                    )
    
    def clean(self):
        cleaned_data = super().clean()
        scope = cleaned_data.get('scope')
        department = cleaned_data.get('department')
        classroom = cleaned_data.get('classroom')
        
        if scope == MessageThread.Scope.DEPARTMENT and not department:
            raise forms.ValidationError({
                'department': 'Department is required when scope is DEPARTMENT'
            })
        
        if scope == MessageThread.Scope.CLASSROOM and not classroom:
            raise forms.ValidationError({
                'classroom': 'Classroom is required when scope is CLASSROOM'
            })
        
        # Check permissions
        if self.user and scope == MessageThread.Scope.DEPARTMENT and department:
            if hasattr(self.user, 'teacher_profile'):
                if self.user.teacher_profile.department != department:
                    # Allow if user is admin/superuser
                    if not (self.user.is_staff or self.user.is_superuser):
                        raise forms.ValidationError(
                            'You can only create groups for your own department'
                        )
        
        return cleaned_data


class MessageThreadUpdateForm(forms.ModelForm):
    """Form for updating thread details and managing members."""
    
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '10'}),
        help_text="Group members"
    )
    
    class Meta:
        model = MessageThread
        fields = ['title', 'description', 'is_archived']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_archived': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Pre-populate members
            self.fields['members'].initial = self.instance.members.all()
            
            # Filter members based on scope
            if self.instance.scope == MessageThread.Scope.DEPARTMENT and self.instance.department:
                from apps.people.models import TeacherProfile
                teachers = TeacherProfile.objects.filter(
                    department=self.instance.department, is_active=True
                ).select_related('user')
                self.fields['members'].queryset = User.objects.filter(
                    id__in=[t.user_id for t in teachers]
                )
            elif self.instance.scope == MessageThread.Scope.CLASSROOM and self.instance.classroom:
                from apps.people.models import StudentProfile
                students = StudentProfile.objects.filter(
                    classroom=self.instance.classroom
                ).select_related('user')
                self.fields['members'].queryset = User.objects.filter(
                    id__in=[s.user_id for s in students if s.user_id]
                )
