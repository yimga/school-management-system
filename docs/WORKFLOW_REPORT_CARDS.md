# Report Card Generation & Publishing Workflow
## Complete Guide to Creating and Publishing Report Cards

**Target Audience:** Academic Directors, Registrars, Administrators  
**Difficulty:** Intermediate  
**Estimated Time:** 30-60 minutes per term

---

## Overview

This guide covers generating report cards, customizing styles, calculating rankings, and publishing to parents.

---

## Prerequisites

Before generating report cards:

- [ ] All marks entered and approved
- [ ] Term is complete
- [ ] Report card style configured
- [ ] Academic year and term active

---

## Step 1: Configure Report Card Style

### Create/Edit Style

1. **Navigate to:** `/siteconfig/reports/builder/` or Report Card Builder
2. **Create New Style** (if needed):
   - Click "Create Report Card Style"
   - **Fill in:**
     - Name: e.g., "Cameroon Term Report 2026"
     - Template: Select template (Term or Annual)
     - Labels: Customize field labels (JSON)
     - Layout: Configure layout (JSON)
   - **Click:** "Save"

3. **Assign to Classrooms:**
   - Select classroom
   - Assign style
   - **Click:** "Save Assignment"

---

## Step 2: Verify Marks Approval

1. **Navigate to:** Approval Requests
2. **Check:** All marks approved for term
3. **Verify:** No pending approvals
4. **Note:** Cannot publish if marks not approved

---

## Step 3: Generate Report Cards

### Batch Generation

1. **Navigate to:** `/reports/publish-term-results/` or "Publish Results"
2. **Select:**
   - Academic Year
   - Term
   - Classroom(s)
3. **Configure:**
   - Report Card Style (if not assigned)
   - Include rankings (Class, School, Specialty)
   - Include comments
   - Include conduct grade
4. **Click:** "Generate Report Cards"
5. **Wait:** System processes (may take a few minutes)

---

## Step 4: Review Generated Report Cards

1. **Preview:** Click "Preview" for each student
2. **Check:**
   - Marks correct
   - Rankings correct
   - Comments present
   - Formatting correct
3. **Edit:** Make corrections if needed
4. **Regenerate:** If major changes needed

---

## Step 5: Publish to Parents

1. **Review:** Ensure all report cards correct
2. **Select:** Classrooms to publish
3. **Click:** "Publish to Parents"
4. **Confirm:** Publishing action
5. **Wait:** System publishes (may take a few minutes)

**What Happens:**
- Report cards become visible to parents
- Parents receive notification
- Report cards available in parent portal
- PDFs generated and stored

---

## Ranking Calculation

### Class Rank

**How It Works:**
- Rank within same classroom
- Based on term average
- Same rank for same average

**Example:**
- Student A: 18.5/20 → Rank 1
- Student B: 18.0/20 → Rank 2
- Student C: 18.0/20 → Rank 2 (tied)

---

### School Rank

**How It Works:**
- Rank across entire school
- Based on term average
- Includes all active students

---

### Specialty Rank

**How It Works:**
- Rank within same classroom AND specialty
- Based on term average
- Only for students with same specialty

**Cameroon Note:** Important for technical schools (IND/STT).

---

## Report Card Styles

### Cameroon Term Report

**Features:**
- Term-based layout
- Sequence 1, Sequence 2, Exam
- Term average
- Class rank
- Specialty rank
- Conduct grade
- Teacher comments
- Principal signature

### Cameroon Annual Report

**Features:**
- Annual summary
- All three terms
- Annual average
- Promotion status
- Overall rank
- Principal signature

---

## Customization

### Editable Labels

**What Can Be Changed:**
- Field labels (e.g., "Mathematics" → "Maths")
- Section headers
- Footer text
- Signature labels

**How to Change:**
1. Edit Report Card Style
2. Modify "Labels" JSON field
3. Save

---

### Layout Configuration

**What Can Be Changed:**
- Section order
- Field positions
- Column widths
- Font sizes
- Colors

**How to Change:**
1. Edit Report Card Style
2. Modify "Layout Config" JSON field
3. Save

---

## Publishing Options

### Publish All at Once

**When to Use:**
- All classes ready
- Want to publish simultaneously
- Bulk operation

**Steps:**
1. Select multiple classrooms
2. Click "Publish All"
3. System publishes all selected

---

### Publish by Classroom

**When to Use:**
- Some classes ready, others not
- Want to publish incrementally
- Need to review each class

**Steps:**
1. Select one classroom
2. Review report cards
3. Click "Publish"
4. Repeat for other classes

---

## Post-Publishing

### What Parents See

1. **Parent Portal:**
   - Navigate to child's dashboard
   - Click "View Report Card"
   - Download PDF

2. **Notifications:**
   - Email notification (if configured)
   - SMS notification (if configured)
   - In-app notification

3. **Access:**
   - View online
   - Download PDF
   - Print report card

---

## Common Issues

### Issue: Report cards not generating
**Solution:**
- Check all marks approved
- Verify term dates correct
- Check report card style assigned

### Issue: Rankings incorrect
**Solution:**
- Verify marks entered correctly
- Check ranking calculation settings
- Regenerate report cards

### Issue: Parents can't see report cards
**Solution:**
- Verify report cards published
- Check parent linked to student
- Verify parent portal access

---

## Related Documentation

- Marks Entry Process
- Approval Workflow Guide
- Report Card Builder Guide
- Parent Portal Guide
