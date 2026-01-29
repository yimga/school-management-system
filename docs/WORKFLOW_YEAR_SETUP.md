# Year Setup Process
## Complete Guide to Setting Up a New Academic Year

**Target Audience:** School Administrators  
**Difficulty:** Intermediate  
**Estimated Time:** 2-3 hours

---

## Overview

This guide walks you through setting up a new academic year from start to finish. This is typically done once per year, before students arrive.

---

## Prerequisites

- Admin or Super Admin access
- School information configured
- Basic understanding of your school's structure

---

## Step-by-Step Process

### Step 1: Create Academic Year

1. **Navigate to:** `/admin/academics/academicyear/` or use Workflow Center
2. **Click:** "Add Academic Year"
3. **Fill in:**
   - **Name:** e.g., "2026-2027"
   - **Start Date:** First day of school
   - **End Date:** Last day of school
   - **Is Active:** Check this box
   - **Enable GCE Registration:** Check if you need GCE/Certification workflow (optional)
4. **Click:** "Save"

**Important:** Only one academic year should be active at a time.

---

### Step 2: Create Terms

1. **Navigate to:** `/admin/academics/term/` or use Workflow Center
2. **For each term (typically 3 terms):**
   - **Click:** "Add Term"
   - **Fill in:**
     - **Academic Year:** Select the year you just created
     - **Name:** e.g., "Term 1", "Term 2", "Term 3"
     - **Start Date:** Term start date
     - **End Date:** Term end date
     - **Sequence:** 1, 2, 3 (order)
     - **Is Active:** Check for current term
   - **Click:** "Save"

**Cameroon Note:** Most schools follow a 3-term structure (Sept-Dec, Jan-Mar, Apr-Jul).

---

### Step 3: Create Departments

1. **Navigate to:** `/admin/people/department/` or use Workflow Center
2. **For each department:**
   - **Click:** "Add Department"
   - **Fill in:**
     - **Name:** e.g., "Science", "Arts", "Commercial"
     - **Code:** Short code (e.g., "SCI", "ART", "COM")
     - **Description:** Optional
   - **Click:** "Save"

**Note:** Departments organize teachers and can be used for group messaging.

---

### Step 4: Create Specialties

1. **Navigate to:** `/admin/academics/specialty/` or use Workflow Center
2. **For each specialty:**
   - **Click:** "Add Specialty"
   - **Fill in:**
     - **Name:** e.g., "General Arts", "Science", "Commercial"
     - **Code:** Short code (e.g., "GA", "SCI", "COM")
     - **Department:** Select department
     - **Description:** Optional
   - **Click:** "Save"

**Cameroon Note:** Specialties are important for technical schools (IND/STT) and GCE registration.

---

### Step 5: Create Classrooms

1. **Navigate to:** `/admin/academics/classroom/` or use Workflow Center
2. **For each classroom:**
   - **Click:** "Add Classroom"
   - **Fill in:**
     - **Name:** e.g., "Form 1A", "Form 2B", "Upper Sixth Science"
     - **Academic Year:** Select the active year
     - **Grade Level:** e.g., "Form 1", "Form 5", "Upper Sixth"
     - **Specialty:** Select specialty (if applicable)
     - **Capacity:** Maximum students
     - **Is Active:** Check
   - **Click:** "Save"

**Tip:** Create all classrooms before assigning students.

---

### Step 6: Create Subjects

1. **Navigate to:** `/admin/academics/subject/` or use Workflow Center
2. **For each subject:**
   - **Click:** "Add Subject"
   - **Fill in:**
     - **Name:** e.g., "Mathematics", "English Language", "Physics"
     - **Code:** Short code (e.g., "MATH", "ENG", "PHY")
     - **Department:** Select department
     - **Is Core:** Check for core subjects
     - **Description:** Optional
   - **Click:** "Save"

**Note:** Subjects can be assigned to classrooms later.

---

### Step 7: Assign Subjects to Classrooms

1. **Navigate to:** `/admin/academics/subjectassignment/`
2. **For each classroom:**
   - **Click:** "Add Subject Assignment"
   - **Select:** Classroom and Subject
   - **Select:** Teacher (if known)
   - **Fill in:** Schedule details (optional)
   - **Click:** "Save"

**Tip:** You can assign subjects later as teachers are onboarded.

---

## Verification Checklist

After setup, verify:

- [ ] Academic year is active
- [ ] All terms created and dates correct
- [ ] All departments created
- [ ] All specialties created
- [ ] All classrooms created
- [ ] All subjects created
- [ ] Subjects assigned to classrooms
- [ ] Teachers assigned to subjects (if available)

---

## Common Issues

### Issue: Can't create term
**Solution:** Ensure academic year exists and is active.

### Issue: Can't assign subject to classroom
**Solution:** Ensure both subject and classroom exist and are active.

### Issue: Students can't be assigned to classroom
**Solution:** Ensure classroom is created for the active academic year.

---

## Next Steps

After year setup:
1. Onboard students (see Student Onboarding guide)
2. Onboard teachers (see Teacher Onboarding guide)
3. Configure fees (see Finance Setup guide)

---

## Related Documentation

- Student Onboarding Workflow
- Teacher Onboarding Workflow
- Finance Setup Guide
- GCE Registration Workflow (if enabled)
