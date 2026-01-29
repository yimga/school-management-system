# GCE/Certification Registration Workflow
## Complete Guide to National Exam Registration

**Target Audience:** Registrars, Academic Directors, Administrators  
**Difficulty:** Advanced  
**Estimated Time:** 2-4 hours per exam session

**Note:** This feature is toggleable per academic year. Enable in Academic Year settings.

---

## Overview

This guide covers the complete workflow for registering students for national exams (GCE, CAP, Probatoire, etc.), including candidate creation, fee collection, CA marks export, and document management.

---

## Prerequisites

Before starting:

- [ ] GCE Registration enabled for academic year
- [ ] Exam presets configured
- [ ] Fee templates created
- [ ] Document checklists configured
- [ ] Students in exam classes (Form 5, Upper Sixth)

---

## Step 1: Configure Exam Presets

### Create Preset

1. **Navigate to:** `/admin/academics/certificationexampreset/`
2. **Click:** "Add Certification Exam Preset"
3. **Fill in:**
   - **Code:** e.g., "GCE_OLEVEL_2026"
   - **Name:** e.g., "GCE Ordinary Level 2026"
   - **Board:** GCE Board, OBC, etc.
   - **Level:** Ordinary Level, Advanced Level, etc.
   - **Rules:** JSON configuration (allowed classes, required fields)
   - **CA Export Config:** JSON configuration (subject columns, weights)
4. **Click:** "Save"

**Use:** Presets define exam rules and CA export format.

---

## Step 2: Create Fee Templates

### Create Template

1. **Navigate to:** `/admin/academics/certificationfeatemplate/`
2. **Click:** "Add Certification Fee Template"
3. **Fill in:**
   - **Name:** e.g., "GCE O-Level Fees 2026"
   - **Currency:** XAF (or your currency)
   - **Is Default:** Check if default
4. **Add Fee Lines:**
   - **Registration Fee:** Base amount
   - **Subject Fees:** Per subject
   - **Practical Fees:** For practical subjects
   - **Other Fees:** As needed
5. **Click:** "Save"

---

## Step 3: Create Document Checklist

### Create Checklist

1. **Navigate to:** `/admin/academics/certificationdocumentchecklist/`
2. **Click:** "Add Certification Document Checklist"
3. **Fill in:**
   - **Name:** e.g., "GCE O-Level Documents"
   - **Is Default:** Check if default
4. **Add Checklist Items:**
   - **Birth Certificate:** Required
   - **ID Card:** Required
   - **Previous Result Slip:** Required
   - **Photo:** Required
   - **Other Documents:** As needed
5. **Click:** "Save"

---

## Step 4: Create Exam Session

1. **Navigate to:** `/admin/academics/certificationexamsession/` or Certification Center
2. **Click:** "Add Certification Exam Session"
3. **Fill in:**
   - **Name:** e.g., "GCE O-Level June 2026"
   - **Academic Year:** Select active year
   - **Board:** GCE Board, OBC, etc.
   - **Level:** Ordinary Level, Advanced Level
   - **Preset:** Select preset created in Step 1
   - **Fee Template:** Select fee template
   - **Document Checklist:** Select checklist
   - **Centre Number:** Your school's centre number
   - **Centre Name:** Your school name
   - **Registration Start Date:** When registration opens
   - **Registration End Date:** When registration closes
   - **CA Deadline:** Deadline for CA marks submission
   - **Is Active:** Check
4. **Click:** "Save"

---

## Step 5: Create Candidates

### Bulk Creation (Recommended)

1. **Navigate to:** Certification Session Detail page
2. **Click:** "Bulk Add Candidates"
3. **Select:**
   - **Classrooms:** Form 5, Upper Sixth, etc.
   - **Specialties:** Optional (leave empty for all)
   - **Skip Existing:** Check to avoid duplicates
   - **Include Inactive:** Uncheck (usually)
4. **Click:** "Create Candidates"
5. **System Creates:** Candidate records for all selected students

### Manual Creation

1. Navigate to Session Detail
2. Click "Add Candidate"
3. Select student
4. Fill in details
5. Click "Save"

---

## Step 6: Collect Fees

### Payment Processing

1. **Navigate to:** Candidate Detail page
2. **Review:** Fee amount (from template)
3. **Process Payment:**
   - Parent pays via Mobile Money
   - Upload payment proof
   - Verify transaction
   - Mark as paid
4. **System Updates:** Candidate payment status

### Payment Verification

**Steps:**
1. Review payment proofs
2. Verify transaction references
3. Match amounts
4. Approve payments
5. System blocks unpaid candidates from verification

---

## Step 7: Document Collection

### Upload Documents

1. **Navigate to:** Candidate Detail page
2. **Review:** Document checklist
3. **Upload Documents:**
   - Birth Certificate
   - ID Card
   - Previous Result Slip
   - Photos
   - Other required documents
4. **Mark Status:** Complete/Incomplete for each item

### Document Verification

**Steps:**
1. Review uploaded documents
2. Verify authenticity
3. Mark as verified
4. System tracks completion status

---

## Step 8: CA Marks Export

### Automatic Calculation

**How It Works:**
- System calculates CA marks automatically
- Based on preset configuration
- Supports technical education (Theory/Practical splits)
- Applies coefficients
- Generates weighted averages

### Export Pack Generation

1. **Navigate to:** Session Detail page
2. **Click:** "Export Pack"
3. **System Generates:**
   - `candidates.csv` - Candidate list
   - `ca_marks.csv` - CA marks with technical splits
   - `document_checklist.csv` - Document status
   - `README.txt` - Instructions
4. **Download:** ZIP file ready for GCE Board portal

---

## Step 9: Verification & Locking

### Candidate Verification

**Steps:**
1. Review each candidate:
   - Fees paid
   - Documents complete
   - CA marks entered
   - Information correct
2. **Mark as Verified:**
   - Click "Verify Candidate"
   - System locks candidate data
   - Status: "VERIFIED"

### Deadline Enforcement

**How It Works:**
- System enforces registration deadline
- Blocks new candidates after deadline
- Blocks edits after CA deadline
- Admin can override (with audit trail)

---

## Step 10: Final Export & Submission

### Generate Final Pack

1. **Navigate to:** Session Detail page
2. **Verify:** All candidates verified
3. **Click:** "Export Final Pack"
4. **System Generates:**
   - Complete candidate list
   - CA marks (formatted for board)
   - Document checklist summary
   - All required files
5. **Download:** Final ZIP file

### Upload to GCE Board Portal

1. **Download:** Export pack
2. **Extract:** ZIP file
3. **Upload:** Files to GCE Board portal
4. **Verify:** Upload successful
5. **Track:** Submission status

---

## Admin Override

### When to Use

- Registration deadline passed but need to add candidate
- CA deadline passed but need to update marks
- Urgent corrections needed

### How to Use

1. Navigate to Session Detail
2. Click "Admin Override"
3. **Select:**
   - Override type (Registration Lock, CA Lock)
   - Reason for override
4. **Click:** "Set Override"
5. **System:** Allows operations, logs override

**Note:** All overrides are logged for audit.

---

## Technical Education Support

### Theory/Practical Splits

**How It Works:**
- Some subjects have Theory and Practical components
- System calculates both separately
- Applies coefficients
- Generates combined average

**Example:**
- Electricity Theory: 15/20 (Coefficient 3)
- Electricity Practical: 18/20 (Coefficient 5)
- Combined: Weighted average

---

## Common Issues

### Issue: Can't create candidates after deadline
**Solution:** Use admin override or extend deadline in session settings.

### Issue: CA marks not calculating correctly
**Solution:** Check preset configuration and subject assignments.

### Issue: Export pack missing data
**Solution:** Verify all candidates have required information and documents.

---

## Related Documentation

- Year Setup Process
- Student Onboarding Workflow
- Marks Entry Process
- Finance Workflows
