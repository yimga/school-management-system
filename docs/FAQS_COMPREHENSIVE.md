# Comprehensive FAQ
## Frequently Asked Questions for School Management System

**Last Updated:** January 2026  
**Version:** 1.0

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Year Setup](#year-setup)
3. [Student Management](#student-management)
4. [Teacher Management](#teacher-management)
5. [Marks & Evaluations](#marks--evaluations)
6. [Report Cards](#report-cards)
7. [Finance & Fees](#finance--fees)
8. [Communication](#communication)
9. [Document Library](#document-library)
10. [GCE/Certification](#gcecertification)
11. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Q: How do I log in for the first time?

**A:** 
1. Navigate to the login page
2. Enter your username and password (provided by administrator)
3. If you forgot your password, click "Forgot Password" to reset
4. First-time users may need to complete profile setup

---

### Q: What is the difference between `/admin` and `/backend`?

**A:**
- **`/admin`**: Django Admin panel for system configuration (backend administrators only)
- **`/backend`**: User-friendly dashboard for school administrators (operators, registrars, etc.)
- **`/portal`**: Parent and student-facing portal

**Use `/backend` for daily operations, `/admin` for advanced configuration.**

---

### Q: Where do I find the Workflow Center?

**A:** Navigate to `/accounts/workflow-center/` or click "Workflow Center" in the sidebar. This provides step-by-step guidance for all major processes.

---

### Q: How do I customize my dashboard?

**A:**
1. Navigate to Backend Dashboard
2. Click "Customize" button (if available)
3. Select widgets to display
4. Arrange layout
5. Save preferences

**Note:** Customizer may be in Site Settings or Preferences depending on your role.

---

## Year Setup

### Q: How do I set up a new academic year?

**A:** See the complete guide: [Year Setup Process](WORKFLOW_YEAR_SETUP.md)

**Quick Steps:**
1. Create Academic Year
2. Create Terms (typically 3)
3. Create Classrooms
4. Create Subjects
5. Assign Subjects to Classrooms

---

### Q: Can I have multiple academic years active at once?

**A:** No, only one academic year should be active at a time. The system uses the active year for most operations.

---

### Q: How do I create terms?

**A:**
1. Navigate to `/admin/academics/term/`
2. Click "Add Term"
3. Select Academic Year
4. Enter term name, start date, end date
5. Set sequence (1, 2, 3)
6. Mark as active if current term

---

### Q: What is the difference between Departments and Specialties?

**A:**
- **Departments**: Organize teachers (e.g., Science, Arts, Commercial)
- **Specialties**: Organize students (e.g., General Arts, Science, Commercial)

**Region note:** In many regions (e.g. Cameroon, CEMAC), specialties are important for technical schools (IND/STT) and local exam registration (e.g. GCE).

---

## Student Management

### Q: How do I enroll a new student?

**A:** See complete guide: [Student Onboarding Workflow](WORKFLOW_STUDENT_ONBOARDING.md)

**Methods:**
1. **Admin creates:** `/admin/people/studentprofile/`
2. **Self-registration:** `/portal/student/onboarding/`
3. **Bulk import:** CSV upload

---

### Q: How do admission numbers work?

**A:**
- **Auto-generation:** System generates if left blank (configured in Site Settings)
- **Manual entry:** Admin enters admission number
- **Format:** Configurable (e.g., `YY + SCHOOL_CODE + #### + SPECIALTY + CLASS`)

**See:** Site Settings → Admission Number Mode

---

### Q: How do parents link their child to their account?

**A:**
**Three methods:**
1. **Invite Code:** Admin creates invite, parent claims
2. **Admission Number:** Parent enters admission number
3. **Automatic:** If parent email provided during student creation

**See:** [Student Onboarding Workflow](WORKFLOW_STUDENT_ONBOARDING.md)

---

### Q: Can I bulk import students?

**A:** Yes. Prepare CSV with required columns and upload via Backend Dashboard → Entity Console → Bulk Import Students.

---

## Teacher Management

### Q: How do I onboard a new teacher?

**A:** See complete guide: [Teacher Onboarding Workflow](WORKFLOW_TEACHER_ONBOARDING.md)

**Steps:**
1. Create User account (Role: TEACHER)
2. Create Teacher Profile
3. Assign to Department
4. Assign Classes/Subjects
5. Grant Permissions

---

### Q: How do I assign a teacher to a class?

**A:**
1. Navigate to `/admin/academics/subjectassignment/`
2. Click "Add Subject Assignment"
3. Select Classroom and Subject
4. Select Teacher
5. Save

---

### Q: What permissions do teachers have?

**A:**
**Default:**
- View assigned classes
- Enter marks for assigned subjects
- View student profiles (assigned classes only)
- Send messages
- View own payslips

**Restricted:**
- Cannot access admin panel
- Cannot view other teachers' classes
- Cannot modify system settings

---

## Marks & Evaluations

### Q: How do I enter marks?

**A:** See complete guide: [Marks Entry Process](WORKFLOW_MARKS_ENTRY.md)

**Methods:**
1. **Manual entry:** Enter scores directly
2. **OCR upload:** Upload marksheet image
3. **CSV import:** Bulk import from spreadsheet

---

### Q: How does OCR marksheet upload work?

**A:**
1. Scan/photograph marksheet
2. Upload image (PDF, JPG, PNG)
3. System processes with OCR
4. Review detected marks
5. Correct errors
6. Submit for approval

**Note:** Requires OCR module enabled. See OCR Setup Guide.

---

### Q: What is the approval workflow?

**A:**
1. Teacher submits marks
2. First approver (Dean/HOD) reviews
3. Final approver (Registrar/Director) reviews
4. Marks approved and finalized
5. Can be published to report cards

**See:** [Marks Entry Process](WORKFLOW_MARKS_ENTRY.md)

---

### Q: What are the assessment types?

**A:**
- **SEQ1 (Sequence 1):** First half of term (20-30% weight)
- **SEQ2 (Sequence 2):** Second half of term (20-30% weight)
- **Exam:** End of term (40-50% weight)
- **CA (Continuous Assessment):** Throughout term (varies)

**System calculates term average automatically.**

---

## Report Cards

### Q: How do I generate report cards?

**A:** See complete guide: [Report Card Generation Workflow](WORKFLOW_REPORT_CARDS.md)

**Steps:**
1. Ensure all marks approved
2. Configure report card style
3. Navigate to "Publish Term Results"
4. Select Year, Term, Classroom
5. Generate report cards
6. Review and publish

---

### Q: Where is the Report Card Builder?

**A:** Navigate to `/siteconfig/reports/builder/` or click "Report Card Builder" in sidebar. This allows you to customize report card styles and layouts.

---

### Q: How are rankings calculated?

**A:**
- **Class Rank:** Rank within same classroom
- **School Rank:** Rank across entire school
- **Specialty Rank:** Rank within same classroom AND specialty

**Same rank for tied averages.**

---

### Q: Can parents see report cards?

**A:** Yes, after publishing. Parents can view and download report cards from their portal.

---

## Finance & Fees

### Q: How do I create invoices?

**A:** See complete guide: [Finance Workflows](WORKFLOW_FINANCE.md)

**Methods:**
1. **Single invoice:** Create for one student
2. **Bulk creation:** Create for multiple students using fee template

---

### Q: How do I process mobile money payments?

**A:**
1. Parent pays via MTN Mobile Money or Orange Money
2. Parent uploads payment proof
3. Finance staff verifies transaction
4. Approve payment
5. System updates invoice status

**See:** Mobile Money Setup Guide

---

### Q: How do fee reminders work?

**A:**
- **Automatic:** System sends reminders based on due date (configurable)
- **Manual:** Finance staff can send reminders for overdue invoices

**Configure:** Payment Reminders settings

---

### Q: What financial reports are available?

**A:**
- Revenue Report
- Outstanding Fees
- Payment History
- Fee Collection Rate

**Access:** Finance Dashboard → Reports

---

## Communication

### Q: How do I send a message?

**A:**
1. Navigate to Messages (`/accounts/messages/`)
2. Click "New Message"
3. Select recipient
4. Type message
5. Attach files (optional)
6. Send

---

### Q: How do message groups work?

**A:**
- **Department Groups:** Auto-created for departments
- **Custom Groups:** Create for committees, projects, etc.

**Access:** Message Groups in sidebar

---

### Q: How do I create an announcement?

**A:**
1. Navigate to "Announcements" or `/communication/announcement/create/`
2. Fill in title, message, banner type
3. Set dates (optional)
4. Publish

**Who can create:** Administrators, Leadership, IT Admin

---

### Q: Where do announcements appear?

**A:** All dashboard pages (parent portal, teacher portal, student portal, backend dashboard).

---

## Document Library

### Q: What is the Document Library?

**A:** A centralized place to store and share school documents (registration forms, consent forms, fee forms, etc.).

**Access:** 
- **Admin:** `/portal/backend/documents/` (manage)
- **Public:** `/portal/feature/documents/` (view/download)

---

### Q: How do I upload a document?

**A:**
1. Navigate to Document Library (Backend)
2. Click "Upload Document"
3. Fill in:
   - Title, Description
   - Document Type (Form, Policy, etc.)
   - Upload file OR enter external link
   - Set signature requirement (if form)
   - Set visibility (who can view)
4. Save

---

### Q: How do electronic signatures work?

**A:**
1. Admin uploads form requiring signature
2. Admin creates signature request for parent
3. Parent receives notification
4. Parent signs form electronically
5. System generates signed PDF
6. Both parties receive copy

**See:** Document Library Guide

---

### Q: Who can access documents?

**A:** Configured via "Visible To Roles" setting. Options:
- All Users
- Parents Only
- Teachers Only
- Administrators Only
- Custom role combinations

---

## GCE/Certification

### Q: How do I enable GCE registration?

**A:**
1. Navigate to Academic Year settings
2. Check "Enable GCE Registration"
3. Save

**Note:** Must be enabled per academic year.

---

### Q: How do I register students for GCE?

**A:** See complete guide: [GCE/Certification Registration Workflow](WORKFLOW_GCE_CERTIFICATION.md)

**Steps:**
1. Configure exam presets
2. Create exam session
3. Create candidates (bulk or manual)
4. Collect fees
5. Collect documents
6. Export CA marks
7. Generate final pack

---

### Q: How do I export CA marks?

**A:**
1. Navigate to Exam Session Detail
2. Click "Export Pack"
3. System generates `ca_marks.csv` with technical splits
4. Download ZIP file

**Note:** System calculates CA marks automatically based on preset configuration.

---

## Troubleshooting

### Q: I clicked a menu item and nothing happened. What should I do?

**A:**
1. Refresh the page and try again
2. Check if your role has access to that feature
3. Check browser console for errors
4. Contact administrator if issue persists

---

### Q: I can't see a feature in the sidebar. Why?

**A:**
**Possible reasons:**
1. Your role doesn't have permission
2. Feature not enabled in Site Settings
3. Feature hidden in dashboard customizer
4. Feature not configured

**Solution:** Check with administrator or review Site Settings.

---

### Q: Why can't I enter marks?

**A:**
**Check:**
1. Are you assigned to the subject/classroom?
2. Is the term active?
3. Are marks already approved? (may need to request changes)
4. Do you have permission?

**Solution:** Verify subject assignments and permissions.

---

### Q: Why can't parents see report cards?

**A:**
**Check:**
1. Are report cards published?
2. Is parent linked to student?
3. Is parent account active?
4. Is term/classroom correct?

**Solution:** Verify publishing status and parent-student link.

---

### Q: Payment not recorded. What do I do?

**A:**
1. Check payment proof uploaded
2. Verify transaction reference matches
3. Check payment reconciliation status
4. Manually reconcile if needed

**Solution:** Review payment proofs and reconcile manually if automatic matching failed.

---

### Q: How do I reset my password?

**A:**
1. Click "Forgot Password" on login page
2. Enter email/username
3. Check email for reset link
4. Follow link to reset password

**If email not received:** Contact administrator.

---

### Q: Where is the Customizer?

**A:**
- **For Admins:** Site Settings → Customizer section
- **For Staff:** Preferences → Customizer section
- **Direct Link:** `/siteconfig/customizer/` (if you have permission)

**Note:** Customizer may redirect to Site Settings or Preferences depending on your role.

---

### Q: How do I contact support?

**A:**
1. Use "Contact School" form in parent portal
2. Send message to IT Admin
3. Check Help Center (`/kb/`) for documentation
4. Review FAQs

---

## Additional Resources

- [Year Setup Process](WORKFLOW_YEAR_SETUP.md)
- [Student Onboarding Workflow](WORKFLOW_STUDENT_ONBOARDING.md)
- [Teacher Onboarding Workflow](WORKFLOW_TEACHER_ONBOARDING.md)
- [Marks Entry Process](WORKFLOW_MARKS_ENTRY.md)
- [Report Card Generation Workflow](WORKFLOW_REPORT_CARDS.md)
- [Communication Workflows](WORKFLOW_COMMUNICATION.md)
- [Finance Workflows](WORKFLOW_FINANCE.md)
- [GCE/Certification Registration Workflow](WORKFLOW_GCE_CERTIFICATION.md)

---

**Need more help?** Visit the Help Center (`/kb/`) or contact your system administrator.
