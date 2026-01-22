"""
Management command to seed FAQ database with comprehensive questions
"""
from django.core.management.base import BaseCommand
from apps.portal.models_kb import FAQCategory, FAQ


class Command(BaseCommand):
    help = 'Seed FAQ database with initial content covering all features'

    def handle(self, *args, **options):
        self.stdout.write('Seeding FAQ database...')
        
        # Create categories
        categories = self.create_categories()
        
        # Create FAQs
        faq_count = self.create_faqs(categories)
        
        self.stdout.write(self.style.SUCCESS(
            f'Successfully created {len(categories)} categories and {faq_count} FAQs'
        ))

    def create_categories(self):
        """Create FAQ categories"""
        category_data = [
            {
                'name': 'Getting Started',
                'slug': 'getting-started',
                'description': 'Basic questions about logging in and navigating the system',
                'icon': 'fa-rocket',
                'display_order': 1
            },
            {
                'name': 'Student Management',
                'slug': 'student-management',
                'description': 'Questions about student profiles, enrollment, and tracking',
                'icon': 'fa-graduation-cap',
                'display_order': 2
            },
            {
                'name': 'Grading & Evaluations',
                'slug': 'grading-evaluations',
                'description': 'Questions about entering grades, assessments, and rankings',
                'icon': 'fa-chart-line',
                'display_order': 3
            },
            {
                'name': 'Report Cards',
                'slug': 'report-cards',
                'description': 'Questions about generating and customizing report cards',
                'icon': 'fa-file-alt',
                'display_order': 4
            },
            {
                'name': 'Finance & Fees',
                'slug': 'finance-fees',
                'description': 'Questions about invoices, payments, and fee management',
                'icon': 'fa-dollar-sign',
                'display_order': 5
            },
            {
                'name': 'Parent Portal',
                'slug': 'parent-portal',
                'description': 'Questions for parents accessing the system',
                'icon': 'fa-users',
                'display_order': 6
            },
            {
                'name': 'Teachers & Staff',
                'slug': 'teachers-staff',
                'description': 'Questions about teacher management and payroll',
                'icon': 'fa-chalkboard-teacher',
                'display_order': 7
            },
            {
                'name': 'Communication',
                'slug': 'communication',
                'description': 'Questions about messaging, notifications, and video classes',
                'icon': 'fa-comments',
                'display_order': 8
            },
            {
                'name': 'System Settings',
                'slug': 'system-settings',
                'description': 'Questions about customization and configuration',
                'icon': 'fa-cog',
                'display_order': 9
            },
            {
                'name': 'Troubleshooting',
                'slug': 'troubleshooting',
                'description': 'Common problems and solutions',
                'icon': 'fa-wrench',
                'display_order': 10
            },
        ]
        
        categories = {}
        for cat_data in category_data:
            category, created = FAQCategory.objects.get_or_create(
                slug=cat_data['slug'],
                defaults=cat_data
            )
            categories[cat_data['slug']] = category
            action = 'Created' if created else 'Found'
            self.stdout.write(f'{action} category: {category.name}')
        
        return categories

    def create_faqs(self, categories):
        """Create FAQ items"""
        faqs_data = [
            # Getting Started FAQs
            {
                'category': 'getting-started',
                'question': 'How do I log in to the system for the first time?',
                'answer': '''Visit the login page at /accounts/login/. Enter your username and password provided by your administrator. If you have Multi-Factor Authentication (MFA) enabled, you'll be prompted to enter your verification code after your password.

First-time users should change their password immediately after logging in. Click on your profile icon and select "Change Password".''',
                'tags': 'login, authentication, first-time, password',
                'is_featured': True
            },
            {
                'category': 'getting-started',
                'question': 'What are the different user roles and what can they do?',
                'answer': '''The system supports 12 user roles:

1. **ADMIN** - Full system access
2. **PRINCIPAL** - School-wide oversight
3. **VICE_PRINCIPAL** - Assistant principal duties
4. **DEAN** - Academic affairs management
5. **BURSAR** - Financial management
6. **HOD** - Head of Department
7. **TEACHER** - Grade entry and class management
8. **PARENT** - View student information and make payments
9. **STUDENT** - View own grades and schedules
10. **IT_ADMIN** - Technical administration
11. **BOARDING_MANAGER** - Dormitory management
12. **CENSOR** - Discipline and conduct

Each role has specific permissions that control what they can view and modify in the system.''',
                'tags': 'roles, permissions, access, RBAC',
                'is_featured': True
            },
            {
                'category': 'getting-started',
                'question': 'How do I navigate the dashboard?',
                'answer': '''Your dashboard is customizable based on your role. Common elements include:

- **Top Navigation**: Access main modules (Students, Teachers, Finance, Reports)
- **Sidebar**: Quick links to frequently used features
- **Widgets**: Customizable cards showing key metrics
- **Notifications**: Bell icon shows recent alerts

You can customize your dashboard by clicking "Preferences" in your profile menu and selecting which widgets to display.''',
                'tags': 'dashboard, navigation, interface, widgets'
            },
            {
                'category': 'getting-started',
                'question': 'What browsers are supported?',
                'answer': '''The system works best with modern browsers:

**Recommended:**
- Google Chrome (version 90+)
- Mozilla Firefox (version 88+)
- Microsoft Edge (version 90+)
- Safari (version 14+)

**Mobile:** The system is responsive and works on mobile browsers. For the best mobile experience, use the mobile app (if available).

**Note:** Internet Explorer is not supported.''',
                'tags': 'browser, compatibility, requirements, mobile'
            },
            
            # Student Management FAQs
            {
                'category': 'student-management',
                'question': 'How do I add a new student?',
                'answer': '''To add a new student:

1. Navigate to **People → Students**
2. Click the **"Add Student"** button
3. Fill in required information:
   - First name, last name
   - Gender, date of birth
   - Classroom and specialty (if applicable)
   - Student status (NEW, RETURNING, etc.)
4. The system will auto-generate an admission number
5. Click **"Save"**

You can also import multiple students via CSV by going to **People → Students → Import**.''',
                'tags': 'add student, enrollment, admission, CSV import',
                'is_featured': True
            },
            {
                'category': 'student-management',
                'question': 'What is the admission number format?',
                'answer': '''Admission numbers follow the format: **YY-SCHOOL-NNNN-CLASS**

Example: **23-GIL-0016-CJ1**

- **YY**: Admission year (e.g., 23 for 2023)
- **SCHOOL**: School code (configured in Site Settings)
- **NNNN**: Sequential number
- **CLASS**: Classroom code

The system automatically generates these numbers when you create a student.''',
                'tags': 'admission number, student ID, format'
            },
            {
                'category': 'student-management',
                'question': 'How do I bulk import students from a spreadsheet?',
                'answer': '''To import students in bulk:

1. Download the CSV template from **People → Students → Import → Download Template**
2. Fill in the required fields: admission_number, first_name, last_name, gender, DOB, classroom, specialty, status
3. Save the file as CSV
4. Go to **People → Students → Import**
5. Upload your CSV file
6. Review validation errors (if any)
7. Click **"Confirm Import"**

The system will create or update student records based on admission numbers. Any errors will be reported with specific row numbers.''',
                'tags': 'import, CSV, bulk upload, spreadsheet, Excel'
            },
            {
                'category': 'student-management',
                'question': 'How do I link parents/guardians to students?',
                'answer': '''There are two ways to link guardians:

**Method 1: Guardian Invitation**
1. Go to **Portal → Guardian Invitations**
2. Click **"Create Invitation"**
3. Select student and enter parent's email/phone
4. Choose relationship type (MOTHER, FATHER, GUARDIAN, OTHER)
5. Click **"Send Invitation"**
6. Parent receives token-based link to claim account

**Method 2: Direct Linking (Admin)**
1. Go to **People → Students → [Student Name] → Guardians**
2. Click **"Add Guardian"**
3. Select existing user or create new one
4. Specify relationship type
5. Save

Parents can then access the Parent Portal to view student information.''',
                'tags': 'parent, guardian, link, invitation, family'
            },
            
            # Grading & Evaluations FAQs
            {
                'category': 'grading-evaluations',
                'question': 'How do I enter grades for my students?',
                'answer': '''To enter grades:

1. Navigate to **Evaluations → Enter Grades**
2. Select academic year, term, and classroom
3. Select the subject you teach
4. You'll see a list of all students in that class
5. Enter scores for each component:
   - Seq1 (Sequence 1)
   - Seq2 (Sequence 2)
   - Exam
   - Mock (optional)
   - Practical (optional)
6. Add remarks if needed
7. Click **"Save"**

The system automatically calculates weighted averages based on configured assessment weights.

**Tip:** You can also use the bulk grade import feature to upload grades from a spreadsheet.''',
                'tags': 'enter grades, grading, scores, teacher, assessment',
                'is_featured': True
            },
            {
                'category': 'grading-evaluations',
                'question': 'What are assessment weights and how do they work?',
                'answer': '''Assessment weights determine how much each component contributes to the final grade. The system supports:

**Components:**
- Seq1 (Sequence 1)
- Seq2 (Sequence 2)
- Exam
- Mock (optional)
- Practical (optional)

**Example Cameroon System:**
- Seq1: 20%
- Seq2: 20%
- Exam: 60%
- Total: 100%

Weights can be configured:
- School-wide default
- Per classroom
- Per term

Administrators can configure weights at **Settings → Assessment Weights**.

**Calculation:** Final Grade = (Seq1 × 0.20) + (Seq2 × 0.20) + (Exam × 0.60)''',
                'tags': 'weights, calculation, assessment, grading scale'
            },
            {
                'category': 'grading-evaluations',
                'question': 'Can I import grades from Excel/CSV?',
                'answer': '''Yes! To import grades in bulk:

1. Navigate to **Evaluations → Grade Import**
2. Download the CSV template
3. Fill in: student_admission_number, subject_code, seq1, seq2, exam, mock, practical, remarks
4. Save as CSV
5. Upload the file
6. System validates all entries
7. Preview the changes
8. Confirm import

The system will:
- Validate all student and subject codes
- Check score ranges (0-20 for Cameroon system)
- Report any errors with row numbers
- Track import job status
- Provide detailed logs

**Note:** You must have teacher assignment for the subjects you're importing.''',
                'tags': 'import grades, CSV, Excel, bulk entry'
            },
            {
                'category': 'grading-evaluations',
                'question': 'How are student rankings calculated?',
                'answer': '''Rankings are calculated using:

1. **Coefficient-Weighted Averages**: Each subject has a coefficient (e.g., Math = 4, PE = 1)
2. **Class Rankings**: Students ranked within their classroom
3. **School Rankings**: Students ranked across entire school (if applicable)
4. **Tie Handling**: When students have identical averages:
   - First, compare number of subjects passed
   - Then, compare total points earned
   - Finally, assign same rank with subsequent rank skipped

**Example:**
- Student A: 14.5 average → Rank 1
- Student B: 14.5 average → Rank 1 (tie)
- Student C: 14.3 average → Rank 3 (not rank 2)

Rankings are cached for performance and recalculated when grades change.''',
                'tags': 'ranking, position, calculation, coefficient, ties'
            },
            {
                'category': 'grading-evaluations',
                'question': 'What is the grading deadline system?',
                'answer': '''The grading deadline system helps ensure timely grade submission:

**Features:**
- Administrators set deadlines per term/subject/classroom
- Teachers receive reminders before deadlines
- Compliance dashboard shows submission status
- Late submissions are flagged
- Extension requests can be submitted

**Teacher View:**
- Dashboard shows upcoming deadlines
- Color-coded status: Green (on track), Orange (approaching), Red (overdue)
- Completion percentage per subject

**Admin View:**
- Teacher compliance report
- At-risk teachers identification
- Bulk deadline extension
- Compliance analytics

Configure at **Evaluations → Grading Deadlines**.''',
                'tags': 'deadline, compliance, submission, reminder'
            },
            
            # Report Cards FAQs
            {
                'category': 'report-cards',
                'question': 'How do I generate report cards?',
                'answer': '''To generate report cards:

1. Navigate to **Reports → Report Cards**
2. Select:
   - Academic year
   - Term (or "Annual" for full year)
   - Classroom (or individual student)
3. Click **"Generate Report"**
4. Preview the report
5. Download as PDF

**Features:**
- Multiple report card templates
- Multi-language support (6 languages)
- Customizable branding
- Includes grades, rankings, attendance
- Teacher and principal signatures

**Publishing:** Reports must be published before parents can view them. Go to **Reports → Publish Settings** to control visibility.''',
                'tags': 'report card, transcript, generate, PDF, download',
                'is_featured': True
            },
            {
                'category': 'report-cards',
                'question': 'How do I customize report card appearance?',
                'answer': '''Report card customization options:

1. **Report Card Styles** (Admin → Site Config → Report Card Styles):
   - Multiple templates available
   - Set default for term reports
   - Set default for annual reports
   - Override per classroom

2. **Branding** (Admin → Site Settings):
   - Upload school logo
   - Set school colors
   - Add school motto/tagline
   - Configure header/footer

3. **Language** (Reports → Settings):
   - Choose from 6 languages
   - English, French, Swahili, Hausa, Yoruba, Pidgin
   - Translations for all report sections

4. **Grading Scale** (Evaluations → Assessment Weights):
   - Numeric (0-20)
   - Letter grades (A-E)
   - GPA (4.0 scale)
   - Percentage (0-100)

Contact IT Administrator for custom templates.''',
                'tags': 'customize, template, branding, style, logo'
            },
            {
                'category': 'report-cards',
                'question': 'When can parents see report cards?',
                'answer': '''Parents can view report cards after they are published:

**Publishing Process:**
1. Teachers enter all grades
2. Grades are reviewed by administrators
3. Admin publishes reports via **Reports → Publish Settings**
4. Publishing can be:
   - School-wide (all classes at once)
   - Per classroom
   - Individual student

**Parent Access:**
- Parents receive email notification when published
- Access via Parent Portal → My Children → Reports
- Can download PDF copies
- Can share via temporary link

**Unpublishing:** Administrators can unpublish reports if corrections are needed. Parents will lose access until republished.

**Status Check:** **Reports → Publish Status** shows which reports are currently visible to parents.''',
                'tags': 'publish, parent view, access, visibility, notification'
            },
            
            # Finance & Fees FAQs
            {
                'category': 'finance-fees',
                'question': 'How do I set up fee structures?',
                'answer': '''To configure fees:

1. Navigate to **Finance → Fee Plans**
2. Click **"Add Fee Plan"**
3. Configure:
   - Academic year
   - Classroom and/or specialty
   - Fee items:
     * TUITION
     * ACTIVITY (sports, clubs, etc.)
     * CUSTOM (uniforms, books, etc.)
4. For each fee item:
   - Set amount
   - Mark as mandatory/optional
   - Set due date
5. Create installment plans if needed
6. Activate the fee plan

**Multiple Fee Plans:** You can have different fee structures for different classrooms or specialties.

**Bulk Setup:** Use CSV import for multiple classes.''',
                'tags': 'fees, tuition, setup, fee plan, pricing',
                'is_featured': True
            },
            {
                'category': 'finance-fees',
                'question': 'What payment methods are supported?',
                'answer': '''The system supports 7 payment methods:

**Mobile Money:**
- MTN Mobile Money
- Orange Money

**Traditional:**
- Bank Transfer
- Check
- Cash

**Online:**
- Credit Card
- Debit Card

**Online Payment Processors:**
- Stripe
- PayPal
- Flutterwave (African markets)
- Paystack (African markets)

**Security Features:**
- PCI-DSS compliance
- Card tokenization
- Encrypted transactions
- Fraud detection
- Webhook verification

Configure payment processors at **Finance → Payment Settings**.''',
                'tags': 'payment methods, mobile money, credit card, online payment'
            },
            {
                'category': 'finance-fees',
                'question': 'How do parents make online payments?',
                'answer': '''Parents can pay fees online through the Parent Portal:

1. Log in to Parent Portal
2. Click **"Finances"** or **"Outstanding Fees"**
3. View all invoices for their children
4. Click **"Pay Now"** on an invoice
5. Select payment method
6. Enter payment details:
   - Mobile money: phone number
   - Card: card details (securely processed)
   - Bank transfer: confirmation code
7. Submit payment
8. Receive instant confirmation

**Features:**
- Split payments (pay partial amounts)
- Save payment methods for future use
- Download receipts
- Payment history
- Multiple children in one transaction

**Notifications:**
- Email receipt immediately
- SMS confirmation (if enabled)
- Payment reflected in real-time''',
                'tags': 'online payment, parent portal, pay fees, mobile money'
            },
            {
                'category': 'finance-fees',
                'question': 'Can I create payment installment plans?',
                'answer': '''Yes! Installment plans allow families to pay fees over time:

**Creating Installment Plans:**
1. Go to **Finance → Fee Plans → [Select Plan] → Installments**
2. Click **"Add Installment"**
3. Set:
   - Installment number (1, 2, 3...)
   - Amount for this installment
   - Due date
4. Repeat for each installment
5. Total installments must equal fee amount

**Example: $1000 Tuition**
- Installment 1: $400 due Sep 1
- Installment 2: $300 due Oct 1
- Installment 3: $300 due Nov 1

**Automated Features (Phase 9):**
- Auto-generate equal installments
- Recurring payment subscriptions
- Auto-charge on due dates (with parent consent)
- Late payment interest calculation
- Payment reminders

Parents can view installment schedules in the Parent Portal.''',
                'tags': 'installment, payment plan, split payment, recurring'
            },
            
            # Parent Portal FAQs
            {
                'category': 'parent-portal',
                'question': 'How do I access the Parent Portal?',
                'answer': '''**First-Time Access:**
1. Receive invitation email/SMS from school
2. Click invitation link
3. Create account with your email
4. Set password
5. Claim your child(ren)
6. Access granted

**Subsequent Logins:**
1. Visit school's portal URL
2. Click **"Parent Portal"** or **"Parent Login"**
3. Enter username and password
4. View dashboard

**Forgot Password:**
- Click **"Forgot Password"** on login page
- Enter email address
- Follow reset link sent to email

**Multiple Children:**
- One account can be linked to multiple students
- Switch between children using dropdown
- View consolidated information

**Troubleshooting:**
- If you didn't receive invitation, contact school administrator
- Invitations expire after 7 days (request new one)''',
                'tags': 'parent portal, access, login, invitation, registration',
                'is_featured': True
            },
            {
                'category': 'parent-portal',
                'question': 'What can I do in the Parent Portal?',
                'answer': '''The Parent Portal provides:

**Academic Information:**
- View current grades
- View report cards (when published)
- Check attendance records
- See class rankings
- Download transcripts

**Financial Management:**
- View outstanding fees
- See payment history
- Make online payments
- Download receipts
- Set up payment plans

**Communication:**
- Message teachers
- Receive school announcements
- Get grade notifications
- View event calendar
- Book parent-teacher meetings

**Profile Management:**
- Update contact information
- Set notification preferences
- Add emergency contacts
- Link additional children

**Features are configurable:** Administrators control which features are available to parents.''',
                'tags': 'parent portal, features, dashboard, capabilities'
            },
            {
                'category': 'parent-portal',
                'question': 'How do I link multiple children to my account?',
                'answer': '''To link multiple children:

**Option 1: During Initial Setup**
- When claiming invitation, you can link all children at once
- System detects if multiple students share your contact info

**Option 2: Add Later**
- Log in to Parent Portal
- Go to **Profile → My Children**
- Click **"Link Another Child"**
- Enter student's admission number or name
- Request link (requires school approval)

**Option 3: School Links for You**
- School administrator can link students to your account
- You'll receive notification when new student is linked

**Switching Between Children:**
- Use dropdown at top of dashboard
- Select child to view their information
- Some views show all children together (finances, notifications)

**Privacy:** Each parent only sees children linked to their account. Other students' information remains private.''',
                'tags': 'multiple children, link student, family, siblings'
            },
            
            # Teachers & Staff FAQs
            {
                'category': 'teachers-staff',
                'question': 'How do I view my teaching schedule?',
                'answer': '''To view your schedule:

1. Log in to your teacher account
2. Dashboard shows today's classes automatically
3. Click **"Full Schedule"** or navigate to **Academics → My Schedule**
4. View:
   - Weekly timetable
   - Classroom assignments
   - Subject assignments
   - Student counts per class

**Schedule Features:**
- Color-coded by subject
- Room numbers shown
- Conflict detection
- Export to calendar (iCal format)
- Print-friendly version

**Phase 9 Enhancement:**
- Automated timetable generation
- AI-powered conflict resolution
- Room availability checking
- Workload balancing

**Mobile Access:** Download the mobile app to access your schedule on-the-go with push notifications for upcoming classes.''',
                'tags': 'schedule, timetable, teaching, classroom, teacher'
            },
            {
                'category': 'teachers-staff',
                'question': 'How do I request leave?',
                'answer': '''To request leave:

1. Navigate to **Staff → Leave Requests**
2. Click **"Request Leave"**
3. Fill in:
   - Leave type (ANNUAL, SICK, MATERNITY, UNPAID, OTHER)
   - Start date
   - End date
   - Reason for leave
   - Whether paid/unpaid
4. Submit request
5. Receive notification when approved/rejected

**Leave Request Status:**
- PENDING: Awaiting review
- APPROVED: Leave granted
- REJECTED: Leave denied (with reason)
- CANCELLED: You cancelled the request

**Leave Balance:**
- View remaining days at **Staff → My Leave Balance**
- Accrual rates based on employment contract
- Automatic calculation of used/remaining days

**Approvers:**
- Configure at **Settings → Leave Approval Workflow**
- Usually HOD → Principal → HR

**Notifications:**
- Email when status changes
- Calendar invite when approved''',
                'tags': 'leave, vacation, absence, request, teacher'
            },
            {
                'category': 'teachers-staff',
                'question': 'How do I view my paystubs?',
                'answer': '''To access paystubs:

1. Log in to your account
2. Navigate to **Staff → Pay History**
3. View list of all pay periods
4. Click on any period to see detailed paystub
5. Download PDF for your records

**Paystub Information:**
- Gross pay
- Itemized deductions:
  * Income tax
  * CNPS contributions (if applicable)
  * Other deductions
- Net pay
- Year-to-date totals
- Payment method
- Payment date

**Payment Methods:**
- Direct deposit to bank account
- Mobile money transfer
- Check pickup

**Privacy:**
- Only you and HR can view your paystubs
- Encrypted storage
- Audit logs track all access

**Questions?** Contact HR or Finance department if you notice discrepancies.''',
                'tags': 'paystub, salary, pay, compensation, payroll'
            },
            
            # Communication FAQs
            {
                'category': 'communication',
                'question': 'How do I send messages to parents?',
                'answer': '''Teachers can communicate with parents through:

**Individual Messages:**
1. Navigate to **Communication → Messages**
2. Click **"New Message"**
3. Select recipient (parent of specific student)
4. Write message
5. Send

**Bulk Announcements:**
1. Go to **Communication → Announcements**
2. Click **"New Announcement"**
3. Select audience:
   - Entire class
   - Multiple classes
   - All parents
4. Write announcement
5. Schedule or send immediately

**Delivery Channels:**
- In-app notification (Portal)
- Email
- SMS (if configured)
- Push notification (mobile app)

**Message Features:**
- Attachments supported
- Read receipts
- Reply tracking
- Message threading
- Archive old messages

**Parent Response:**
- Parents receive notification
- Can reply directly
- Creates conversation thread''',
                'tags': 'messaging, communication, parent contact, announcements'
            },
            {
                'category': 'communication',
                'question': 'How do I set up a virtual classroom?',
                'answer': '''To create virtual classrooms (Phase 9 feature):

1. Navigate to **Communication → Virtual Classrooms**
2. Click **"Schedule Session"**
3. Configure:
   - Session title
   - Date and time
   - Duration
   - Classroom (links to students)
   - Platform (Zoom, Google Meet, Microsoft Teams, or Jitsi)
4. Set options:
   - Enable recording
   - Waiting room
   - Max participants
   - Allow breakout rooms
5. Click **"Create Session"**

**Before Session:**
- System sends join links to students/parents
- Email reminders 24 hours and 1 hour before
- Test audio/video in advance

**During Session:**
- Students join via Parent Portal or mobile app
- Host controls: mute, kick, screen share
- Create breakout rooms for group work
- Record session for later viewing

**After Session:**
- Attendance automatically tracked
- Recording available in portal
- Analytics: participation time, engagement

**Supported Platforms:**
- Zoom (most features)
- Google Meet
- Microsoft Teams
- Jitsi (open-source)''',
                'tags': 'virtual classroom, video, zoom, online class, remote learning'
            },
            
            # System Settings FAQs
            {
                'category': 'system-settings',
                'question': 'How do I customize the school branding?',
                'answer': '''To customize branding:

1. Navigate to **Admin → Site Settings**
2. Upload school logo:
   - Recommended: 200x200px PNG with transparent background
   - Maximum file size: 2MB
3. Set colors:
   - Primary color (main theme color)
   - Accent color (buttons, highlights)
4. Configure school information:
   - Official name
   - Short name/acronym
   - Motto/tagline
   - Address
   - Contact information
5. Set homepage background image
6. Choose font family
7. Save changes

**Advanced Customization:**
- Custom CSS: Admin → Site Settings → Custom CSS
- Theme packs: Choose from pre-made themes
- Dark mode: Enable dark theme option
- Layout: Standard, wide, card, or minimal

**Preview:** Click "Preview" to see changes before saving.

**Revert:** Keep "Reset to Defaults" option available to undo changes.''',
                'tags': 'branding, logo, customization, theme, colors'
            },
            {
                'category': 'system-settings',
                'question': 'How do I set up term and academic year structures?',
                'answer': '''To configure academic calendar:

**1. Academic Years:**
- Navigate to **Academics → Academic Years**
- Click **"Add Academic Year"**
- Set:
  * Name (e.g., "2024-2025")
  * Start date
  * End date
  * Mark as active (only one can be active)

**2. Terms/Semesters:**
- Go to **Academics → Terms**
- Click **"Add Term"**
- Configure:
  * Academic year
  * Term name (flexible: "First", "Semester 1", "Q1", etc.)
  * Custom label (display name)
  * Position (1-4 for ordering)
  * Start and end dates
- Save

**Flexible Term System:**
- Supports 2-4 terms per year
- Free-text naming (not restricted to FIRST/SECOND/THIRD)
- Custom labels for display
- Can block third term for specific classes (e.g., Form 5, Upper Sixth)

**Best Practices:**
- Set up academic year before creating terms
- Ensure term dates don't overlap
- Configure before enrolling students
- Keep at least one academic year active

**Phase 3 Enhancement:** Dynamic term system with backward compatibility for existing data.''',
                'tags': 'academic year, term, semester, calendar, setup'
            },
            
            # Troubleshooting FAQs
            {
                'category': 'troubleshooting',
                'question': 'I forgot my password. How do I reset it?',
                'answer': '''To reset your password:

**Step 1: Request Reset**
1. Go to login page
2. Click **"Forgot Password?"**
3. Enter your email address or username
4. Click **"Send Reset Link"**

**Step 2: Check Email**
1. Check your inbox (and spam folder)
2. Click the reset link in the email
3. Link expires after 24 hours

**Step 3: Set New Password**
1. Enter new password (twice for confirmation)
2. Password requirements:
   - At least 8 characters
   - Mix of uppercase and lowercase
   - At least one number
   - At least one special character
3. Click **"Reset Password"**
4. You'll be redirected to login page

**Troubleshooting:**
- **Email not received?** Check spam folder or request new link
- **Link expired?** Start process again
- **Still can't access?** Contact your administrator

**Security Note:** Never share your password. Administrators cannot see your password.''',
                'tags': 'password reset, forgot password, login issues, access'
            },
            {
                'category': 'troubleshooting',
                'question': 'Why can I not see certain features or menus?',
                'answer': '''Feature visibility depends on your role and permissions:

**Common Reasons:**

1. **Role Restrictions:**
   - Each role has specific permissions
   - Teachers can't access financial settings
   - Parents can't access admin functions
   - Check with administrator about your assigned role

2. **Feature Not Enabled:**
   - Some features are optional modules
   - Administrator controls which features are active
   - Example: Virtual classrooms, mobile API, etc.

3. **Permission Overrides:**
   - Individual users can have specific features enabled/disabled
   - Check **Profile → Permissions** to see your access

4. **Trial/License Restrictions:**
   - Advanced features may require license upgrade
   - Check **Admin → System Info → License**

**To Request Access:**
1. Contact your school administrator
2. Specify which feature you need
3. Explain your use case
4. Administrator can grant access if appropriate

**Check Your Permissions:**
- Navigate to **Profile → My Permissions**
- View list of allowed features
- See which roles you have''',
                'tags': 'permissions, access denied, features, visibility, roles'
            },
            {
                'category': 'troubleshooting',
                'question': 'The system is slow. What can I do?',
                'answer': '''If experiencing slowness:

**Quick Fixes:**
1. **Clear Browser Cache:**
   - Chrome: Ctrl+Shift+Delete
   - Firefox: Ctrl+Shift+Delete
   - Clear cached images and files

2. **Check Internet Connection:**
   - Run speed test
   - Minimum recommended: 5 Mbps
   - Close bandwidth-heavy applications

3. **Try Different Browser:**
   - Switch to Chrome or Firefox
   - Update browser to latest version
   - Disable unnecessary extensions

4. **Reduce Page Load:**
   - Decrease number of dashboard widgets
   - Reduce number of results per page
   - Close unused browser tabs

**Report Persistent Issues:**
If slowness continues:
1. Note what action is slow
2. Record time of day
3. Check if others experience same issue
4. Contact IT administrator with:
   - Your browser version
   - Screenshot of issue
   - Steps to reproduce

**System Optimizations:**
- Phase 8 includes caching and performance improvements
- Database query optimization
- Connection pooling
- Batch operations support

**Administrator Tools:**
- Monitor system health at **Admin → Monitoring**
- Check slow query log
- Review performance metrics''',
                'tags': 'slow, performance, speed, loading, optimization'
            },
            {
                'category': 'troubleshooting',
                'question': 'I entered grades incorrectly. Can I change them?',
                'answer': '''Yes, grades can be corrected:

**Edit Existing Grades:**
1. Navigate to **Evaluations → Enter Grades**
2. Select same academic year, term, classroom, and subject
3. Find the student
4. Modify scores
5. Save changes

**Important Notes:**
- **Audit Logging:** All grade changes are logged with timestamp and user
- **Revision History:** System tracks before/after values
- **Approval Required:** Some schools require admin approval for changes
- **Deadline Restrictions:** Changes after deadline may require special permission

**Grade Change Workflow (if enabled):**
1. Teacher submits change request
2. HOD reviews
3. Principal approves
4. Change applied
5. Parent notified of correction

**Bulk Corrections:**
- Use CSV import to update multiple grades
- Download existing grades first
- Modify and re-upload
- System updates only changed values

**After Publishing:**
- If report cards already published, changes may unpublish them
- Administrator must republish for parents to see updates
- Parents receive notification of grade corrections

**Best Practice:** Double-check grades before final submission to avoid corrections.''',
                'tags': 'edit grades, change grades, correction, mistakes, audit'
            },
        ]
        
        count = 0
        for faq_data in faqs_data:
            category = categories[faq_data['category']]
            faq, created = FAQ.objects.get_or_create(
                question=faq_data['question'],
                defaults={
                    'category': category,
                    'answer': faq_data['answer'],
                    'tags': faq_data.get('tags', ''),
                    'is_featured': faq_data.get('is_featured', False),
                    'status': 'APPROVED'
                }
            )
            if created:
                count += 1
                self.stdout.write(f'Created: {faq.question[:80]}...')
            else:
                self.stdout.write(f'Exists: {faq.question[:80]}...')
        
        return count
