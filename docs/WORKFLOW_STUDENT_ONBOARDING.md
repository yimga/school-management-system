# Student Onboarding Workflow
## Complete Guide to Enrolling Students

**Target Audience:** School Administrators, Registrars  
**Difficulty:** Beginner  
**Estimated Time:** 5-10 minutes per student

---

## Overview

This guide covers the complete process of enrolling a new student, from initial registration to linking parents.

---

## Methods of Onboarding

### Method 1: Admin Creates Student (Recommended for Bulk)

**When to Use:**
- Bulk enrollment at start of year
- Admin has all student information
- Need to create many students quickly

**Steps:**
1. Navigate to `/admin/people/studentprofile/` or use Backend Dashboard
2. Click "Add Student Profile"
3. Fill in required fields:
   - **Basic Info:** Name, DOB, Gender, Place of Birth
   - **Academic Info:** Academic Year, Classroom, Specialty, Admission Number
   - **Contact Info:** Parent Phone, Email
   - **Status:** Set to "ACTIVE"
4. Click "Save"
5. Create parent account (if email provided)
6. Send guardian invite (if needed)

---

### Method 2: Student Self-Registration Wizard

**When to Use:**
- Students register themselves online
- Parents provide information during registration
- Need to collect information before creating account

**Steps:**
1. Student/Parent navigates to `/portal/student/onboarding/`
2. Completes multi-step wizard:
   - **Step 1:** Basic Information (name, DOB, gender)
   - **Step 2:** Academic Information (year, specialty, classroom, admission number)
   - **Step 3:** Parent/Guardian Information
   - **Step 4:** Payment & Referral
3. System creates student profile
4. System creates parent account (if email provided)
5. Parent receives login credentials

---

### Method 3: Guardian Invite System

**When to Use:**
- Student already exists in system
- Need to link existing parent account
- Parent needs to claim their child

**Steps:**
1. Admin creates guardian invite:
   - Navigate to `/admin/portal/pendingguardianinvite/`
   - Click "Add Pending Guardian Invite"
   - Select student
   - Enter parent email/phone
   - Select relationship
   - Generate invite token
2. Send invite to parent (email/SMS)
3. Parent claims invite:
   - Navigates to `/portal/parent/claim-invite/`
   - Enters invite code
   - Links child to their account

---

## Admission Number Configuration

### Auto-Generation Mode

**Setup:**
1. Go to Site Settings → Admission Number Mode
2. Select "AUTO" or "AUTO_OR_MANUAL"
3. Configure pattern (if needed)

**How It Works:**
- If admission number is left blank, system generates one
- Format: `YY + SCHOOL_CODE + #### + SPECIALTY + CLASS`
- Example: `26GT0012SCI5` (Year 26, School GT, Student 0012, Science, Form 5)

### Manual Entry Mode

**Setup:**
1. Go to Site Settings → Admission Number Mode
2. Select "MANUAL"

**How It Works:**
- Admin must enter admission number for each student
- System validates format (if pattern configured)
- No auto-generation

---

## Complete Onboarding Checklist

### For Each Student:

- [ ] Student profile created
- [ ] Admission number assigned (auto or manual)
- [ ] Assigned to classroom
- [ ] Assigned to specialty (if applicable)
- [ ] Parent/guardian information added
- [ ] Parent account created (if email provided)
- [ ] Guardian invite sent (if needed)
- [ ] Parent linked to student
- [ ] Student status set to "ACTIVE"

---

## Parent Linking Process

### Option 1: Automatic Linking

**When:** Parent email provided during student creation

**Process:**
1. System creates parent user account
2. System creates `StudentGuardian` link
3. Parent receives login credentials
4. Parent can immediately access student data

---

### Option 2: Invite Code

**When:** Parent needs to claim their child

**Process:**
1. Admin creates guardian invite
2. Invite code generated
3. Code sent to parent (email/SMS)
4. Parent enters code at `/portal/parent/claim-invite/`
5. Link created automatically

---

### Option 3: Self-Service Linking

**When:** Parent has admission number

**Process:**
1. Parent navigates to `/portal/parent/link-child/`
2. Enters student admission number
3. System verifies and creates link
4. Parent can access student data

---

## Bulk Import

### CSV Import

1. **Prepare CSV file** with columns:
   - first_name, last_name
   - date_of_birth
   - gender
   - admission_number
   - classroom (name or ID)
   - specialty (name or ID)
   - parent_phone
   - parent_email

2. **Navigate to:** Backend Dashboard → Entity Console
3. **Select:** "Bulk Import Students"
4. **Upload:** CSV file
5. **Review:** Import preview
6. **Confirm:** Import

**Note:** System validates data and reports errors.

---

## Common Issues

### Issue: Admission number already exists
**Solution:** Check for duplicate. System prevents duplicates.

### Issue: Parent can't link child
**Solution:** Verify admission number is correct and student exists.

### Issue: Guardian invite expired
**Solution:** Create new invite. Invites expire after set period.

### Issue: Student not showing in parent dashboard
**Solution:** Verify `StudentGuardian` link exists and is active.

---

## Post-Onboarding

After student is onboarded:

1. **Assign Subjects:** Ensure student is enrolled in correct subjects
2. **Set Fees:** Create invoices for tuition and fees
3. **Send Welcome:** Send welcome message to parent
4. **Verify Access:** Test parent can see student data

---

## Related Documentation

- Year Setup Process
- Teacher Onboarding Workflow
- Finance Setup Guide
- Parent Portal Guide
