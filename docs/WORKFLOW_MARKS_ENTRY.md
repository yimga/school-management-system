# Marks Entry Process
## Complete Guide to Entering and Approving Grades

**Target Audience:** Teachers, Academic Directors, Deans  
**Difficulty:** Intermediate  
**Estimated Time:** 10-15 minutes per class

---

## Overview

This guide covers the complete process of entering marks, using OCR for marksheets, approval workflow, and publishing results.

---

## Marks Entry Methods

### Method 1: Manual Entry

**When to Use:**
- Small classes (< 30 students)
- Need immediate entry
- Marks are already calculated

**Steps:**
1. **Navigate to:** `/evals/teacher/marks-entry/` or Teacher Dashboard
2. **Select:** Classroom, Subject, Term, Assessment Type
3. **Enter Marks:**
   - For each student, enter score
   - System validates (0-20 for Cameroon, or configured scale)
   - System calculates letter grade automatically
4. **Review:** Check all marks entered
5. **Submit:** Click "Submit for Approval"

---

### Method 2: OCR Marksheet Upload

**When to Use:**
- Large classes (> 30 students)
- Have physical marksheets
- Want to save time

**Steps:**
1. **Prepare Marksheet:**
   - Scan or photograph marksheet
   - Ensure clear, readable handwriting
   - Include student names and scores

2. **Upload:**
   - Navigate to Marks Entry page
   - Click "Upload Marksheet"
   - Select image file (PDF, JPG, PNG)
   - System processes with OCR

3. **Review OCR Results:**
   - System shows detected marks
   - Review each field
   - Correct any errors
   - System shows confidence scores

4. **Delta Mode (Fill Missing):**
   - If some marks already exist
   - System only fills missing marks
   - Preserves existing data

5. **Submit:** Click "Submit for Approval"

---

### Method 3: CSV/Excel Import

**When to Use:**
- Bulk marks entry
- Have marks in spreadsheet
- Need to import many classes

**Steps:**
1. **Prepare Spreadsheet:**
   - Download template from `/evals/grade-import/template/`
   - Fill in: Student ID/Admission Number, Scores
   - Save as CSV or Excel

2. **Upload:**
   - Navigate to `/evals/grade-import/upload/`
   - Upload file
   - System validates data
   - Shows preview

3. **Review:** Check preview for errors
4. **Import:** Confirm import
5. **Submit:** Submit for approval

---

## Assessment Types

### Sequence 1 (SEQ1)
- **Weight:** Typically 20-30% of term grade
- **Timing:** First half of term
- **Entry:** Enter SEQ1 scores

### Sequence 2 (SEQ2)
- **Weight:** Typically 20-30% of term grade
- **Timing:** Second half of term
- **Entry:** Enter SEQ2 scores

### Exam
- **Weight:** Typically 40-50% of term grade
- **Timing:** End of term
- **Entry:** Enter exam scores

### Continuous Assessment (CA)
- **Weight:** Varies
- **Timing:** Throughout term
- **Entry:** Enter CA scores

**Note:** System calculates term average automatically based on configured weights.

---

## Approval Workflow

### Step 1: Teacher Submits

1. Teacher enters marks
2. Clicks "Submit for Approval"
3. System creates `GradeApprovalRequest`
4. Status: "PENDING"

### Step 2: First Approver Reviews

**Who:** Dean, HOD, or configured approver

**Steps:**
1. Navigate to Approval Requests
2. Review marks
3. **Options:**
   - **Approve:** Marks approved, move to next step
   - **Reject:** Return to teacher with comments
   - **Request Changes:** Ask for modifications

### Step 3: Final Approver Reviews

**Who:** Registrar, Academic Director, or configured approver

**Steps:**
1. Review approved marks
2. **Options:**
   - **Approve:** Marks finalized
   - **Reject:** Return to previous approver
   - **Bypass:** Approve if first approver unavailable (admin only)

### Step 4: Publishing

**Who:** Registrar, Academic Director

**Steps:**
1. Navigate to "Publish Term Results"
2. Select: Academic Year, Term, Classroom
3. Review: Check all marks approved
4. Generate: Create report cards
5. Publish: Make visible to parents

---

## Approval Bypass (Admin)

**When to Use:**
- First approver unavailable
- Urgent publishing needed
- Admin override required

**Steps:**
1. Navigate to Approval Request
2. Click "Admin Override"
3. Select approver to bypass
4. Provide reason
5. Approve directly

**Note:** All bypasses are logged for audit.

---

## OCR Configuration

### Confidence Thresholds

**Setup:**
1. Navigate to Site Settings
2. Configure OCR settings:
   - **Low Confidence Threshold:** e.g., 70%
   - **High Confidence Threshold:** e.g., 90%
   - **Require Review:** If confidence < threshold

**How It Works:**
- System shows confidence score for each field
- Low confidence fields highlighted for review
- Teacher must verify before submitting

---

## Delta Updates

**What It Is:**
- Fill missing marks only
- Preserve existing marks
- Useful for partial marksheets

**How to Use:**
1. Upload marksheet
2. Select "Delta Mode"
3. System only fills empty fields
4. Existing marks unchanged

---

## Common Issues

### Issue: OCR not recognizing handwriting
**Solution:** 
- Improve image quality
- Use clearer handwriting
- Adjust OCR settings
- Manually correct low-confidence fields

### Issue: Approval stuck
**Solution:**
- Check approver availability
- Use admin bypass if needed
- Verify approval workflow configured

### Issue: Marks not calculating correctly
**Solution:**
- Check assessment weights
- Verify all sequences entered
- Check grading scale configuration

---

## Related Documentation

- Report Card Generation Workflow
- Approval Workflow Guide
- OCR Setup Guide
- Grading Configuration
