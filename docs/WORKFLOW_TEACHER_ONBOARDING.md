# Teacher Onboarding Workflow
## Complete Guide to Enrolling Teachers

**Target Audience:** School Administrators, HR  
**Difficulty:** Beginner  
**Estimated Time:** 5-10 minutes per teacher

---

## Overview

This guide covers enrolling new teachers, assigning them to classes/subjects, and granting appropriate access.

---

## Methods of Onboarding

### Method 1: Admin Creates Teacher (Recommended)

**When to Use:**
- Bulk teacher enrollment
- Admin has all information
- Need immediate access control

**Steps:**
1. **Create User Account:**
   - Navigate to `/admin/accounts/user/`
   - Click "Add User"
   - Fill in: Username, Email, Password
   - Set Role: "TEACHER"
   - Click "Save"

2. **Create Teacher Profile:**
   - Navigate to `/admin/people/teacherprofile/`
   - Click "Add Teacher Profile"
   - Link to User account
   - Fill in:
     - **Staff ID:** Unique identifier
     - **Phone:** Contact number
     - **Position Title:** e.g., "Mathematics Teacher"
     - **Department:** Select department
     - **Reports To:** Supervisor (if applicable)
     - **Pay Grade:** Salary grade
     - **Is Active:** Check
   - Click "Save"

3. **Assign Classes/Subjects:**
   - Navigate to `/admin/academics/subjectassignment/`
   - Create assignments for each subject/classroom
   - Assign teacher to each assignment

4. **Grant Permissions:**
   - Navigate to User's permissions
   - Ensure teacher role has appropriate access
   - Test login

---

### Method 2: Teacher Self-Registration Wizard

**When to Use:**
- Teachers register themselves
- Need to collect information during registration
- Want to streamline onboarding

**Steps:**
1. **Teacher Accesses Wizard:**
   - Navigate to `/portal/teacher/onboarding/`
   - Or admin sends registration link

2. **Complete Multi-Step Wizard:**
   - **Step 1:** Basic Information (email, name, phone)
   - **Step 2:** Professional Details (staff ID, position, department)
   - **Step 3:** Preferences (payment method, dashboard view)

3. **System Creates:**
   - User account
   - Teacher profile
   - Sends credentials to email

4. **Admin Reviews:**
   - Approve teacher profile
   - Assign classes/subjects
   - Grant permissions

---

## Teacher Profile Fields

### Required Fields:
- **User Account:** Linked user
- **Staff ID:** Unique identifier
- **Is Active:** Status flag

### Optional Fields:
- **Phone:** Contact number
- **Position Title:** Job title
- **Department:** Department assignment
- **Reports To:** Supervisor
- **Pay Grade:** Salary grade
- **Salary Amount:** Base salary
- **Profile Photo:** Teacher photo

---

## Class/Subject Assignment

### Assigning Subjects to Teachers

1. **Navigate to:** `/admin/academics/subjectassignment/`
2. **For each subject:**
   - Click "Add Subject Assignment"
   - **Select:** Classroom and Subject
   - **Select:** Teacher
   - **Fill in:** Schedule (optional)
   - **Click:** "Save"

**Tip:** You can assign multiple subjects to one teacher.

---

## Access Control

### Teacher Permissions

**Default Access:**
- View assigned classes
- Enter marks for assigned subjects
- View student profiles (assigned classes only)
- Send messages to parents/students
- View own payslips
- Request leave

**Restricted Access:**
- Cannot access admin panel
- Cannot view other teachers' classes
- Cannot modify system settings
- Cannot access finance (unless granted)

---

## Payroll Setup

### Salary Configuration

1. **Navigate to:** `/admin/payroll/payscale/`
2. **Create Pay Scale** (if not exists):
   - Name: e.g., "Teacher Grade 1"
   - Base Salary: Amount
   - Click "Save"

3. **Assign to Teacher:**
   - Edit teacher profile
   - Select Pay Grade
   - Set Salary Amount
   - Set Salary Cap (if applicable)
   - Click "Save"

---

## Verification Checklist

After onboarding teacher:

- [ ] User account created
- [ ] Teacher profile created
- [ ] Staff ID assigned
- [ ] Department assigned
- [ ] Classes/subjects assigned
- [ ] Permissions verified
- [ ] Login tested
- [ ] Payroll configured (if applicable)

---

## Common Issues

### Issue: Teacher can't see assigned classes
**Solution:** Verify `SubjectAssignment` records exist and teacher is assigned.

### Issue: Teacher can't enter marks
**Solution:** Check permissions and ensure subject assignments are active.

### Issue: Teacher can't login
**Solution:** Verify user account is active and credentials are correct.

---

## Related Documentation

- Year Setup Process
- Student Onboarding Workflow
- Marks Entry Process
- Payroll Setup Guide
