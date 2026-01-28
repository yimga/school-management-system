# Messaging System: Department-Based Groups & Announcements

## Current State

The messaging system **already supports** department-based groups:

1. **MessageThread Model** (`apps/communication/models.py:177-224`)
   - Has `scope` field with `DEPARTMENT` option
   - Has `department` ForeignKey to Department
   - Has `members` ManyToManyField for explicit membership
   - Supports role-based filtering via `audience_role`

2. **ClassAnnouncement Model** (`apps/communication/models.py:144-174`)
   - Has `department` ForeignKey
   - Supports department-scoped announcements
   - Has audience filtering (PARENTS, TEACHERS, STAFF, ALL)

3. **TeacherProfile Model** (`apps/people/models.py:35-41`)
   - Has `department` ForeignKey linking teachers to departments

## What's Missing / Needs Enhancement

### Option A: Auto-Create Department Threads (Recommended) ⭐
**Description**: Automatically create and manage department-based message threads when teachers join departments.

**Implementation**:
- When a teacher's department is set/updated, auto-add them to department thread
- Create department thread if it doesn't exist
- Allow department heads to manage thread membership
- Auto-remove teachers when department changes

**Pros**:
- Seamless - works automatically
- No manual setup needed
- Always up-to-date membership

**Cons**:
- Less control over who can join
- May need opt-out mechanism

**Code Changes Needed**:
```python
# apps/people/signals.py (new file)
from django.db.models.signals import post_save
from apps.communication.models import MessageThread
from apps.people.models import TeacherProfile

def sync_teacher_to_department_thread(sender, instance, **kwargs):
    if instance.department:
        thread, created = MessageThread.objects.get_or_create(
            scope=MessageThread.Scope.DEPARTMENT,
            department=instance.department,
            defaults={
                'title': f"{instance.department.name} Department",
                'created_by': instance.user,
            }
        )
        thread.members.add(instance.user)
```

---

### Option B: Manual Group Creation UI
**Description**: Add admin/teacher interface to create and manage department groups manually.

**Implementation**:
- New view: `/communication/groups/create/`
- Form to select department, set group name, add members
- Department heads can create groups for their department
- Admins can create any group

**Pros**:
- Full control
- Can create custom groups (not just departments)
- Clear ownership

**Cons**:
- Requires manual setup
- More maintenance

**Code Changes Needed**:
- New view: `apps/communication/views_groups.py`
- New form: `apps/communication/forms_groups.py`
- New template: `templates/communication/create_group.html`
- URL route: `path('groups/create/', create_group, name='create_group')`

---

### Option C: Enhanced Announcement System
**Description**: Improve `ClassAnnouncement` to support department-wide announcements with better UI.

**Implementation**:
- Add "Send to Department" option in announcement form
- Auto-select all teachers in department
- Add department filter to announcement list
- Add notification when department announcement is posted

**Pros**:
- Uses existing model
- Simple to implement
- Good for one-way communication

**Cons**:
- Not for two-way chat
- Less interactive

**Code Changes Needed**:
- Enhance `ClassAnnouncement` form
- Add department selection widget
- Update announcement views to handle department filtering

---

### Option D: Hybrid Approach (Best) ⭐⭐⭐
**Description**: Combine auto-created threads (Option A) with manual group creation (Option B).

**Implementation**:
1. Auto-create department threads when teachers join departments
2. Allow manual creation of custom groups (e.g., "Math Department - Senior Teachers")
3. Department heads can manage their department thread
4. Enhanced announcement system for broadcast messages

**Pros**:
- Best of both worlds
- Automatic for common use case
- Flexible for special needs

**Cons**:
- More complex implementation
- More code to maintain

---

## Recommended Implementation Plan

### Phase 1: Auto-Create Department Threads (Quick Win)
1. Create signal handler to sync teachers to department threads
2. Add management command to backfill existing teachers
3. Add UI to view department threads in teacher dashboard

### Phase 2: Manual Group Creation
1. Create group creation form and view
2. Add group management interface
3. Add permissions (department heads can manage their department groups)

### Phase 3: Enhanced Announcements
1. Add department filter to announcement form
2. Add "Send to Department" quick action
3. Add department announcement notifications

---

## Code Examples

### Auto-Sync Signal (Option A)
```python
# apps/people/signals.py
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from apps.communication.models import MessageThread
from apps.people.models import TeacherProfile
from apps.accounts.models import User

@receiver(post_save, sender=TeacherProfile)
def sync_teacher_department_thread(sender, instance, created, **kwargs):
    """Auto-add teacher to department thread when department is set."""
    if instance.department and instance.user:
        thread, _ = MessageThread.objects.get_or_create(
            scope=MessageThread.Scope.DEPARTMENT,
            department=instance.department,
            defaults={
                'title': f"{instance.department.name} Department",
                'description': f"Group chat for {instance.department.name} department members",
                'created_by': instance.user,
            }
        )
        if instance.user not in thread.members.all():
            thread.members.add(instance.user)
```

### Manual Group Creation View (Option B)
```python
# apps/communication/views_groups.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from apps.communication.models import MessageThread
from apps.communication.forms_groups import GroupCreationForm

@login_required
def create_group(request):
    if request.method == 'POST':
        form = GroupCreationForm(request.POST, user=request.user)
        if form.is_valid():
            group = form.save(commit=False)
            group.created_by = request.user
            group.save()
            form.save_m2m()  # Save members
            return redirect('communication:group_detail', group_id=group.id)
    else:
        form = GroupCreationForm(user=request.user)
    return render(request, 'communication/create_group.html', {'form': form})
```

---

## Recommendation

**Implement Option D (Hybrid)**:
1. Start with **Option A** (auto-create) - quick win, solves 80% of use cases
2. Add **Option B** (manual groups) - for special cases
3. Enhance announcements (Option C) - for broadcast messages

This gives you:
- ✅ Automatic department groups (no setup needed)
- ✅ Manual custom groups (flexibility)
- ✅ Department announcements (broadcast capability)
- ✅ Full two-way chat (via MessageThread)
- ✅ File sharing (already supported via ThreadMessage)

---

**Next Steps**:
1. Review these options
2. Choose preferred approach
3. I'll implement the selected option(s)
