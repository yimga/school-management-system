"""
Enhanced forms for announcements with department support.
"""
from django import forms
from apps.communication.models import Announcement, ClassAnnouncement
from apps.academics.models import Department, Classroom
from apps.accounts.models import User


class AnnouncementCreateForm(forms.ModelForm):
    """Enhanced announcement form with department selection."""
    
    send_to_department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Optional: Send this announcement to all teachers in a department"
    )
    
    class Meta:
        model = Announcement
        fields = ['title', 'content', 'announcement_type', 'audience', 'is_urgent', 'expiry_date']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Announcement title'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Announcement content'}),
            'announcement_type': forms.Select(attrs={'class': 'form-select'}),
            'audience': forms.Select(attrs={'class': 'form-select'}),
            'is_urgent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'expiry_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        
        # If user is a teacher, limit department choices to their department
        if user and hasattr(user, 'teacher_profile') and user.teacher_profile.department:
            self.fields['send_to_department'].queryset = Department.objects.filter(
                id=user.teacher_profile.department.id
            )
    
    def save(self, commit=True):
        announcement = super().save(commit=False)
        if self.user:
            announcement.created_by = self.user
        
        if commit:
            announcement.save()
            
            # If send_to_department is selected, also create ClassAnnouncement
            department = self.cleaned_data.get('send_to_department')
            if department:
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
        fields = ['title', 'body', 'classroom', 'department', 'audience', 'is_pinned']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'body': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'classroom': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'audience': forms.Select(attrs={'class': 'form-select'}),
            'is_pinned': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        
        # If user is a teacher, limit department choices
        if user and hasattr(user, 'teacher_profile') and user.teacher_profile.department:
            self.fields['department'].queryset = Department.objects.filter(
                id=user.teacher_profile.department.id
            )
    
    def clean(self):
        cleaned_data = super().clean()
        classroom = cleaned_data.get('classroom')
        department = cleaned_data.get('department')
        
        if not classroom and not department:
            raise forms.ValidationError(
                'Either classroom or department must be selected'
            )
        
        if classroom and department:
            raise forms.ValidationError(
                'Select either classroom OR department, not both'
            )
        
        return cleaned_data
    
    def save(self, commit=True):
        announcement = super().save(commit=False)
        if self.user:
            announcement.created_by = self.user
        if commit:
            announcement.save()
        return announcement
