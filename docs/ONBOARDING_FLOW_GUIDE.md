# Complete Onboarding Flow Guide

## Overview

This document explains how the onboarding process works for **Students**, **Teachers**, and **Parents** in the school management system. It covers who creates accounts, how users get access, and the complete workflow for each role.

---

## 1. Student Onboarding

### Who Creates Student Accounts?

**Admin/Staff** creates student profiles through the Django admin interface (`/admin/people/studentprofile/`).

### Student Onboarding Flow

#### Step 1: Admin Creates Student Profile
1. **Admin/Staff** navigates to `/admin/people/studentprofile/add/`
2. Fills in student information:
   - First name, last name
   - Academic year, classroom, specialty
   - Date of birth, gender, etc.
   - Parent phone number (optional)
3. **Admission Number**:
   - If left blank → Auto-generated (based on `admission_number_mode` setting)
   - If entered → Validated against pattern
   - Format: `YY + SCHOOL + #### + SPEC + CLASS` (e.g., `26GIL1234CS001`)
4. Admin saves the student profile

#### Step 2: Student User Account (Optional)
- **Student profiles can exist WITHOUT a user account**
- The `user` field on `StudentProfile` is optional (`null=True, blank=True`)
- If a student needs portal access, admin can:
  - Create a `User` account with role `STUDENT`
  - Link it to the `StudentProfile` via the `user` field

#### Step 3: Parent Linking (Two Methods)

**Method A: Invite-Based (Recommended)**
1. Admin selects student(s) in admin
2. Uses action: **"Create guardian invites"**
3. System generates `PendingGuardianInvite` with unique token
4. Admin shares token with parent (via email/SMS/WhatsApp)
5. Parent visits `/portal/claim-invite/` or `/portal/claim-invite/<token>/`
6. Parent creates account and claims invite
7. System creates `StudentGuardian` link automatically

**Method B: Self-Service Linking**
1. Parent already has account (created via invite or manually)
2. Parent visits `/portal/parent/link-child/`
3. Uses **3-step wizard**:
   - **Step 1**: Enter admission number + relationship
   - **Step 2**: Set contact preferences & permissions
   - **Step 3**: Add optional details (DOB, address, etc.)
4. System creates `StudentGuardian` link

### Student Profile Fields

**Required for Auto-Generation:**
- `academic_year`
- `classroom`
- `specialty`

**Auto-Generated:**
- `admission_number` (if mode allows and field is blank)
- `student_code` (falls back to admission number or TEMP code)
- `referral_code` (for referral rewards)

**Optional:**
- `user` (for portal access)
- `date_of_birth`, `place_of_birth`, `gender`
- `parent_phone`

---

## 2. Teacher Onboarding

### Who Creates Teacher Accounts?

**Admin/Staff** creates both the `User` account and `TeacherProfile` through the Django admin.

### Teacher Onboarding Flow

#### Step 1: Admin Creates User Account
1. Admin navigates to `/admin/accounts/user/add/`
2. Creates user with:
   - Username, email, password
   - Role: `TEACHER` (or `DEPT_LEAD`, `LEADERSHIP`)
   - First name, last name
3. Admin saves user

#### Step 2: Admin Creates Teacher Profile
1. Admin navigates to `/admin/people/teacherprofile/add/`
2. Links to the user created in Step 1
3. Fills in teacher information:
   - `staff_id` (employee number)
   - `phone`
   - `position_title`
   - `department`
   - `reports_to` (if applicable)
   - `pay_grade`, `salary_amount` (optional)
4. Admin saves profile

#### Step 3: Teacher Access
- Teacher can immediately log in with their credentials
- Access to teacher dashboard at `/portal/teacher/`
- Can view assigned classes, students, grades, etc.

### Teacher Profile Fields

**Required:**
- `user` (must be linked to a User with teacher role)
- `is_active` (default: True)

**Optional:**
- `staff_id`
- `phone`
- `position_title`
- `department`
- `reports_to`
- `pay_grade`, `salary_amount`
- `profile_photo`

### Bulk Import

Admins can also import teachers via CSV:
- Use `import_teachers_csv()` function
- Creates both User and TeacherProfile
- Requires: Email, Employee Number

---

## 3. Parent Onboarding

### Who Creates Parent Accounts?

**Two methods:**

1. **Self-Service** (via invite claim)
2. **Admin** (manually in admin interface)

### Parent Onboarding Flow

#### Method A: Invite-Based (Most Common)

**Step 1: Admin Creates Invite**
1. Admin selects student(s) in `/admin/people/studentprofile/`
2. Uses action: **"Create guardian invites"**
3. System creates `PendingGuardianInvite` with:
   - Unique token
   - Student reference
   - Invited email/phone (from student's `parent_phone`)
   - Referral code (from student's `referral_code`)

**Step 2: Parent Claims Invite**
1. Parent receives invite (email/SMS/WhatsApp with token)
2. Parent visits `/portal/claim-invite/` or `/portal/claim-invite/<token>/`
3. Parent fills form:
   - Username
   - Email
   - Password
   - First name, last name
4. Parent submits
5. System:
   - Creates `User` account with role `PARENT`
   - Links to student via `StudentGuardian`
   - Logs parent in automatically
   - Redirects to parent dashboard

**Step 3: Parent Completes Profile**
- Parent can add more details via dashboard
- Can link additional children via `/portal/parent/link-child/`

#### Method B: Self-Service Linking (Parent Already Has Account)

**Step 1: Parent Has Account**
- Parent account created via invite (Method A) or manually by admin

**Step 2: Parent Links Child**
1. Parent visits `/portal/parent/link-child/`
2. Uses **3-step wizard**:
   - **Step 1**: Enter admission number + relationship
     - System validates admission number
     - Shows student confirmation
   - **Step 2**: Set contact preferences
     - Phone number
     - Preferred contact method
     - Permissions (can_view_results, can_view_finance)
   - **Step 3**: Add optional details
     - Student DOB, place of birth, etc.
     - Parent profile details
     - Referral code
3. Parent completes setup
4. System creates `StudentGuardian` link

#### Method C: Admin Creates Parent Account

1. Admin creates `User` with role `PARENT` in `/admin/accounts/user/`
2. Admin can manually create `StudentGuardian` link in `/admin/people/studentguardian/`
3. Parent logs in and accesses portal

### Parent Account Fields

**Required:**
- Username
- Email
- Password
- Role: `PARENT`

**Optional:**
- First name, last name
- Phone number

### Parent Portal Access

Once linked to a student, parent can:
- View student grades and results
- View attendance
- View finance (if `can_view_finance=True`)
- Message teachers
- View announcements
- Access all portal features

---

## Complete Onboarding Workflow Diagram

```
STUDENT ONBOARDING
┌─────────────────────────────────────────┐
│ 1. Admin creates StudentProfile         │
│    - Fills student info                  │
│    - Admission number (auto or manual)  │
│    - Academic year, class, specialty     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 2. Admin creates guardian invite        │
│    (or parent self-links)               │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 3. Parent claims invite OR              │
│    Parent links via wizard              │
└─────────────────────────────────────────┘

TEACHER ONBOARDING
┌─────────────────────────────────────────┐
│ 1. Admin creates User (role=TEACHER)   │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 2. Admin creates TeacherProfile         │
│    - Links to User                      │
│    - Adds staff_id, department, etc.    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 3. Teacher logs in → Access granted     │
└─────────────────────────────────────────┘

PARENT ONBOARDING (Invite Path)
┌─────────────────────────────────────────┐
│ 1. Admin creates invite for student     │
│    - Generates token                    │
│    - Sends to parent email/phone        │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 2. Parent visits /claim-invite/<token>  │
│    - Creates account                    │
│    - Sets password                      │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 3. System auto-links student            │
│    - Creates StudentGuardian            │
│    - Logs parent in                     │
│    - Redirects to dashboard             │
└─────────────────────────────────────────┘

PARENT ONBOARDING (Self-Service Path)
┌─────────────────────────────────────────┐
│ 1. Parent has account (from invite)     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 2. Parent visits /parent/link-child/    │
│    - Step 1: Enter admission number     │
│    - Step 2: Set contact & permissions  │
│    - Step 3: Add optional details       │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 3. System creates StudentGuardian link  │
│    - Parent can now view student data   │
└─────────────────────────────────────────┘
```

---

## Key Models and Relationships

### StudentProfile
- **Created by**: Admin/Staff
- **User account**: Optional (can exist without user)
- **Admission number**: Auto-generated or manual
- **Parent linking**: Via `StudentGuardian` or `PendingGuardianInvite`

### TeacherProfile
- **Created by**: Admin/Staff
- **User account**: Required (must have linked User)
- **Role**: Must be TEACHER, DEPT_LEAD, or LEADERSHIP

### User (Parent Role)
- **Created by**: 
  - Self-service (via invite claim)
  - Admin (manually)
- **Role**: PARENT
- **Linking**: Via `StudentGuardian` model

### StudentGuardian
- **Links**: Parent User ↔ Student Profile
- **Created by**:
  - System (when parent claims invite)
  - System (when parent completes wizard)
  - Admin (manually)

### PendingGuardianInvite
- **Created by**: Admin (via bulk action)
- **Used by**: Parent (to claim and create account)
- **Token**: Unique identifier for invite

---

## Admin Actions Available

### Student Admin Actions

1. **"Create guardian invites"**
   - Bulk action on selected students
   - Creates `PendingGuardianInvite` for each
   - Uses student's `parent_phone` for contact

2. **"Issue referral rewards"**
   - Processes referral codes
   - Awards bonuses to parents

### Bulk Operations

- **CSV Import**: Import students/teachers from CSV
- **CSV Export**: Export student/teacher data

---

## Configuration Settings

### Admission Number Configuration

**Location**: `/admin/siteconfig/sitesettings/`

**Settings**:
- `school_code`: Short identifier (e.g., "GIL")
- `admission_number_mode`: AUTO, MANUAL, or AUTO_OR_MANUAL
- `admission_number_pattern`: Regex for validation

**Impact**:
- Controls how admission numbers are generated
- Affects student profile creation workflow
- Supports offline registration scenarios

---

## Common Scenarios

### Scenario 1: New Student Registration (Online)

1. Admin creates student profile in admin
2. Admission number auto-generates
3. Admin creates guardian invite
4. Parent receives invite via email/SMS
5. Parent claims invite and creates account
6. Parent automatically linked to student

### Scenario 2: New Student Registration (Offline)

1. Admin sets `admission_number_mode` to `MANUAL` or `AUTO_OR_MANUAL`
2. Admin creates student profile with manual admission number
3. When internet is available, admin creates invite
4. Parent claims invite later

### Scenario 3: Parent Links Additional Child

1. Parent already has account (linked to one child)
2. Parent visits `/portal/parent/link-child/`
3. Uses wizard to link second child
4. System creates new `StudentGuardian` link

### Scenario 4: Teacher Joins Mid-Year

1. Admin creates User account with TEACHER role
2. Admin creates TeacherProfile linked to user
3. Admin assigns teacher to classes/subjects
4. Teacher logs in and accesses dashboard

---

## Troubleshooting

### "Student has no admission number"
- Check `admission_number_mode` in Site Settings
- Ensure student has `academic_year`, `classroom`, and `specialty`
- If mode is AUTO, admission number should generate on save

### "Parent can't link child"
- Verify student exists and is active
- Check admission number is correct
- Ensure parent isn't already linked (check `StudentGuardian`)

### "Invite token not working"
- Check invite hasn't expired
- Verify token matches exactly
- Check if invite already claimed (`is_claimed=True`)

### "Teacher can't access portal"
- Verify User role is TEACHER
- Check TeacherProfile is linked to User
- Ensure `is_active=True` on TeacherProfile

---

## Best Practices

1. **Use Invite-Based Flow for Parents**
   - More secure
   - Automatic linking
   - Better user experience

2. **Bulk Create Invites**
   - Use admin action for multiple students
   - Saves time during enrollment periods

3. **Configure Admission Numbers**
   - Set appropriate mode for your workflow
   - Test pattern validation
   - Document format for staff

4. **Complete Student Profiles**
   - Fill in all required fields
   - Add parent phone for easier invite creation
   - Set academic year, class, specialty

5. **Monitor Onboarding Progress**
   - Check parent dashboard onboarding score
   - Follow up on incomplete profiles
   - Track invite claims

---

## Related Documentation

- [Admission Number Guide](./ADMISSION_NUMBER_GUIDE.md) - Configuration details
- [Testing Checklist](./TESTING_CHECKLIST_ONBOARDING.md) - Testing procedures
- [Onboarding Ready for Testing](./ONBOARDING_READY_FOR_TESTING.md) - Implementation summary

---

**Last Updated**: 2026-01-28  
**Status**: Current as of onboarding improvements implementation
