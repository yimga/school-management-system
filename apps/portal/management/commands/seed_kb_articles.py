"""
Management command to seed initial Knowledge Base articles
Populates database with comprehensive how-to guides and tutorials
"""
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from apps.portal.models_kb import KBCategory, KBArticle
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Seed initial Knowledge Base articles with comprehensive guides'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting KB article seeding...'))

        # Get or create categories
        categories_data = {
            'getting-started': {
                'name': 'Getting Started',
                'description': 'Begin your journey with our system',
                'icon': 'fa-rocket',
                'ordering': 1,
            },
            'student-management': {
                'name': 'Student Management',
                'description': 'Manage student records, admissions, and profiles',
                'icon': 'fa-users',
                'ordering': 2,
            },
            'grading-assessment': {
                'name': 'Grading & Assessment',
                'description': 'Manage grades, evaluations, and academic assessments',
                'icon': 'fa-chart-bar',
                'ordering': 3,
            },
            'reports': {
                'name': 'Reports & Analytics',
                'description': 'Generate reports and analyze school data',
                'icon': 'fa-file-excel',
                'ordering': 4,
            },
            'communication': {
                'name': 'Communication',
                'description': 'Connect with parents, students, and staff',
                'icon': 'fa-comments',
                'ordering': 5,
            },
            'finance': {
                'name': 'Finance & Fees',
                'description': 'Manage fees, payments, and financial records',
                'icon': 'fa-coins',
                'ordering': 6,
            },
            'staff-management': {
                'name': 'Staff Management',
                'description': 'Manage staff records, schedules, and payroll',
                'icon': 'fa-id-badge',
                'ordering': 7,
            },
            'system-admin': {
                'name': 'System Administration',
                'description': 'System configuration and administration',
                'icon': 'fa-cogs',
                'ordering': 8,
            },
        }

        categories = {}
        for slug, data in categories_data.items():
            cat, _ = KBCategory.objects.get_or_create(
                slug=slug,
                defaults={
                    'name': data['name'],
                    'description': data['description'],
                    'icon': data['icon'],
                    'display_order': data['ordering'],
                    'parent': None,
                }
            )
            categories[slug] = cat
            self.stdout.write(f"  ✓ Category: {data['name']}")

        # Get admin user for article author
        try:
            admin_user = User.objects.filter(is_superuser=True).first()
            if not admin_user:
                admin_user = User.objects.first()
        except:
            admin_user = None

        # KB Articles Data
        articles = [
            # Getting Started Articles
            {
                'title': 'Complete System Overview & Tour',
                'slug': 'system-overview-tour',
                'summary': 'A comprehensive introduction to the school management system, featuring all major modules and how they work together.',
                'content': '''
<h2>Welcome to Your School Management System</h2>
<p>This comprehensive platform is designed to streamline all aspects of school administration and management. Below is a complete overview of what you can accomplish.</p>

<h3>Main Modules</h3>
<h4>1. Student Management</h4>
<p>Centralize all student information including:</p>
<ul>
<li>Student profiles and contact information</li>
<li>Academic history and records</li>
<li>Enrollment status and class assignments</li>
<li>Emergency contacts and guardians</li>
</ul>

<h4>2. Academics & Grading</h4>
<p>Manage academic performance:</p>
<ul>
<li>Grade tracking and entry</li>
<li>Assignment and assessment management</li>
<li>Report card generation</li>
<li>Academic performance analytics</li>
</ul>

<h4>3. Finance & Fees</h4>
<p>Complete financial management:</p>
<ul>
<li>Fee structure setup and management</li>
<li>Payment tracking and receipts</li>
<li>Financial reports and analytics</li>
<li>Budget planning</li>
</ul>

<h4>4. Staff Management</h4>
<p>Manage your teaching and administrative staff:</p>
<ul>
<li>Staff records and qualifications</li>
<li>Schedule and timetable management</li>
<li>Payroll and compensation</li>
<li>Performance tracking</li>
</ul>

<h4>5. Communication</h4>
<p>Keep everyone connected:</p>
<ul>
<li>Internal messaging system</li>
<li>Parent-teacher communication</li>
<li>Announcements and notifications</li>
<li>Virtual classroom capabilities</li>
</ul>

<h2>Getting Started Steps</h2>
<ol>
<li>Log in with your credentials</li>
<li>Complete your user profile</li>
<li>Navigate to your dashboard</li>
<li>Set up your school information in System Settings</li>
<li>Add students and staff</li>
<li>Configure academic structure</li>
</ol>

<h2>Key Features for Success</h2>
<ul>
<li><strong>Intuitive Dashboard:</strong> Quick access to essential information</li>
<li><strong>Real-time Updates:</strong> All data syncs instantly across the system</li>
<li><strong>Role-based Access:</strong> Security controls ensure data privacy</li>
<li><strong>Mobile Compatible:</strong> Access from any device</li>
<li><strong>Comprehensive Reports:</strong> Data-driven decision making</li>
</ul>
                ''',
                'category': 'getting-started',
                'difficulty': 'BEGINNER',
                'read_time': 15,
                'tags': ['overview', 'introduction', 'features', 'modules'],
                'is_featured': True,
            },
            {
                'title': 'Setting Up Your School Information',
                'slug': 'setting-up-school-info',
                'summary': 'Step-by-step guide to configure your school details, academic year, and system settings.',
                'content': '''
<h2>Configuring Your School Profile</h2>
<p>Before using the system, set up your school information to ensure all records and communications are accurate.</p>

<h3>Step 1: Access System Settings</h3>
<ol>
<li>Log in as a System Administrator</li>
<li>Navigate to: Settings → School Information</li>
<li>Click "Edit School Profile"</li>
</ol>

<h3>Step 2: Fill in Basic Information</h3>
<ul>
<li><strong>School Name:</strong> Official name of your institution</li>
<li><strong>Registration Number:</strong> Government registration ID</li>
<li><strong>Contact Phone:</strong> Main telephone number</li>
<li><strong>Email Address:</strong> Official school email</li>
<li><strong>Address:</strong> Complete physical address</li>
<li><strong>Website:</strong> School website URL (optional)</li>
</ul>

<h3>Step 3: Add Branding</h3>
<ul>
<li>Upload school logo (recommended: 200x200px PNG)</li>
<li>Set primary and secondary colors</li>
<li>Add school motto or tagline</li>
</ul>

<h3>Step 4: Configure Academic Year</h3>
<ol>
<li>Go to: System Settings → Academic Year</li>
<li>Set start date (usually January or September)</li>
<li>Set end date</li>
<li>Define term dates if applicable</li>
<li>Click "Save Academic Year"</li>
</ol>

<h3>Step 5: Set Up Grade Structure</h3>
<ol>
<li>Navigate to: Academics → Grade Configuration</li>
<li>Add each grade/class level offered</li>
<li>Specify number of sections per grade</li>
<li>Define capacity per section</li>
</ol>

<h3>Step 6: Configure Subjects (Optional)</h3>
<ol>
<li>Go to: Academics → Subjects</li>
<li>Add all subjects taught in your school</li>
<li>Assign codes and categories</li>
<li>Set credit hours where applicable</li>
</ol>

<h2>Important Notes</h2>
<ul>
<li>Some settings can only be changed during initial setup</li>
<li>Back up your configuration before making major changes</li>
<li>Test settings with sample data before going live</li>
<li>Contact support if you need to modify locked settings</li>
</ul>
                ''',
                'category': 'getting-started',
                'difficulty': 'INTERMEDIATE',
                'read_time': 10,
                'tags': ['setup', 'configuration', 'school-info', 'settings'],
                'is_featured': True,
            },
            {
                'title': 'Understanding User Roles and Permissions',
                'slug': 'user-roles-permissions',
                'summary': 'Learn about different user roles in the system and what each role can access and do.',
                'content': '''
<h2>User Roles Overview</h2>
<p>The system uses role-based access control to ensure data security and appropriate access levels.</p>

<h3>Administrator (Super Admin)</h3>
<p><strong>Access Level:</strong> Full system access</p>
<p><strong>Responsibilities:</strong></p>
<ul>
<li>System configuration and setup</li>
<li>User account management</li>
<li>System maintenance and backups</li>
<li>Generate system-wide reports</li>
<li>Manage system security settings</li>
</ul>

<h3>Principal/Head</h3>
<p><strong>Access Level:</strong> High-level administrative access</p>
<p><strong>Responsibilities:</strong></p>
<ul>
<li>Oversee all academic operations</li>
<li>Review reports and analytics</li>
<li>Approve policies and procedures</li>
<li>Manage staff performance</li>
<li>Communication with parents</li>
</ul>

<h3>Teacher</h3>
<p><strong>Access Level:</strong> Class and student data access</p>
<p><strong>Responsibilities:</strong></p>
<ul>
<li>Enter grades and marks</li>
<li>Create assignments and assessments</li>
<li>Communicate with students and parents</li>
<li>View class roster</li>
<li>Submit attendance</li>
</ul>

<h3>Parent</h3>
<p><strong>Access Level:</strong> Child's academic information only</p>
<p><strong>Permissions:</strong></p>
<ul>
<li>View child's grades and progress</li>
<li>View attendance records</li>
<li>Communicate with teachers</li>
<li>View report cards</li>
<li>Update contact information</li>
</ul>

<h3>Student</h3>
<p><strong>Access Level:</strong> Own academic information</p>
<p><strong>Permissions:</strong></p>
<ul>
<li>View personal academic records</li>
<li>View grades and assignments</li>
<li>Access class schedule</li>
<li>View announcements</li>
<li>Submit assignments</li>
</ul>

<h3>Staff (Non-Teaching)</h3>
<p><strong>Access Level:</strong> Assigned department data</p>
<p><strong>Examples:</strong></p>
<ul>
<li>Finance Staff: Access to billing and payments</li>
<li>Admissions: Student enrollment data</li>
<li>HR: Staff records and payroll</li>
</ul>

<h2>Best Practices</h2>
<ul>
<li>Assign roles based on job responsibilities</li>
<li>Regularly audit role assignments</li>
<li>Remove access immediately when staff leave</li>
<li>Use strong passwords for all accounts</li>
<li>Enable two-factor authentication where available</li>
</ul>
                ''',
                'category': 'getting-started',
                'difficulty': 'BEGINNER',
                'read_time': 8,
                'tags': ['roles', 'permissions', 'access', 'security'],
                'is_featured': False,
            },

            # Student Management Articles
            {
                'title': 'Adding and Managing Student Records',
                'slug': 'adding-managing-students',
                'summary': 'Complete guide on how to add new students, update their information, and manage student records effectively.',
                'content': '''
<h2>Adding New Students</h2>
<h3>Method 1: Individual Entry</h3>
<ol>
<li>Navigate to: Student Management → Students</li>
<li>Click "Add New Student"</li>
<li>Fill in required information (marked with *)</li>
<li>Click "Create Student"</li>
</ol>

<h3>Required Information</h3>
<ul>
<li><strong>First Name & Last Name:</strong> Student's legal name</li>
<li><strong>Date of Birth:</strong> Essential for age verification</li>
<li><strong>Gender:</strong> Male, Female, or Other</li>
<li><strong>Grade/Class:</strong> Current enrollment level</li>
<li><strong>Admission Number:</strong> Unique identifier</li>
<li><strong>Contact Email:</strong> Student or parent email</li>
</ul>

<h3>Optional Information</h3>
<ul>
<li>Student photo</li>
<li>Medical information</li>
<li>Special needs or accommodations</li>
<li>Previous school information</li>
<li>Nationality and citizenship</li>
</ul>

<h3>Method 2: Bulk Import via CSV</h3>
<ol>
<li>Go to: Student Management → Bulk Import</li>
<li>Download template CSV file</li>
<li>Fill in student data using the template</li>
<li>Click "Upload CSV"</li>
<li>Review imported data for errors</li>
<li>Confirm import</li>
</ol>

<h2>Managing Student Information</h2>
<h3>Updating Student Details</h3>
<ol>
<li>Search for student using name or ID</li>
<li>Click student name to open profile</li>
<li>Click "Edit Profile"</li>
<li>Update required fields</li>
<li>Click "Save Changes"</li>
</ol>

<h3>Linking Parents/Guardians</h3>
<ol>
<li>Open student profile</li>
<li>Click "Family & Guardians"</li>
<li>Click "Add Parent/Guardian"</li>
<li>Enter parent information</li>
<li>Define relationship (Parent, Guardian, etc.)</li>
<li>Set contact permissions</li>
<li>Save</li>
</ol>

<h3>Managing Admissions</h3>
<p>Use admission number format:</p>
<pre>YYYY/GRADE/SEQUENCE
Example: 2024/10/001</pre>

<h2>Tips for Data Quality</h2>
<ul>
<li>Use consistent formatting for names</li>
<li>Keep contact information current</li>
<li>Update emergency contacts yearly</li>
<li>Remove duplicate records promptly</li>
<li>Verify critical information in person</li>
</ul>
                ''',
                'category': 'student-management',
                'difficulty': 'BEGINNER',
                'read_time': 12,
                'tags': ['students', 'records', 'admission', 'registration'],
                'is_featured': True,
            },
            {
                'title': 'Class Assignment and Section Management',
                'slug': 'class-assignment-sections',
                'summary': 'Learn how to organize students into classes and sections, manage class rosters, and handle transfers.',
                'content': '''
<h2>Class Structure Overview</h2>
<p>Classes are organized by grade level with multiple sections for better management.</p>

<h3>Setting Up Classes</h3>
<ol>
<li>Navigate to: Academics → Classes</li>
<li>Click "Add New Class"</li>
<li>Enter class name (e.g., "Class X-A")</li>
<li>Select grade level</li>
<li>Set capacity</li>
<li>Assign class teacher</li>
<li>Save</li>
</ol>

<h2>Adding Students to Classes</h2>
<h3>Method 1: Individual Assignment</h3>
<ol>
<li>Open student profile</li>
<li>Click "Class Assignment"</li>
<li>Select class from dropdown</li>
<li>Set academic year</li>
<li>Save</li>
</ol>

<h3>Method 2: Bulk Assignment</h3>
<ol>
<li>Go to: Academics → Class Management</li>
<li>Select target class</li>
<li>Click "Add Students in Bulk"</li>
<li>Select students from list</li>
<li>Confirm assignment</li>
</ol>

<h2>Managing Class Rosters</h2>
<h3>Viewing Class List</h3>
<ol>
<li>Go to: Academics → Classes</li>
<li>Click class name</li>
<li>View all students in the class</li>
</ol>

<h3>Removing Students</h3>
<ol>
<li>Open class roster</li>
<li>Find student</li>
<li>Click "Remove" or "Transfer"</li>
<li>Confirm action</li>
</ol>

<h2>Transferring Students</h2>
<ol>
<li>Open student profile</li>
<li>Click "Transfer to Different Class"</li>
<li>Select new class</li>
<li>Mark effective date</li>
<li>Confirm transfer</li>
</ol>

<h2>Section Management Tips</h2>
<ul>
<li>Balance sections evenly for fairness</li>
<li>Consider special needs when forming sections</li>
<li>Keep roster updated in real-time</li>
<li>Generate roster reports for parents</li>
<li>Update section assignments after transfers</li>
</ul>
                ''',
                'category': 'student-management',
                'difficulty': 'INTERMEDIATE',
                'read_time': 10,
                'tags': ['classes', 'sections', 'roster', 'assignments'],
                'is_featured': False,
            },

            # Grading Articles
            {
                'title': 'Recording and Managing Student Grades',
                'slug': 'recording-managing-grades',
                'summary': 'Complete tutorial on how teachers can enter grades, manage assessments, and track student performance.',
                'content': '''
<h2>Getting Started with Grade Entry</h2>
<h3>Accessing the Gradebook</h3>
<ol>
<li>Log in as a teacher</li>
<li>Navigate to: Academics → Gradebook</li>
<li>Select your class</li>
<li>Select subject</li>
<li>Click "Open Gradebook"</li>
</ol>

<h2>Entering Grades</h2>
<h3>Single Grade Entry</h3>
<ol>
<li>Click on the grade cell for a student</li>
<li>Enter the grade (0-100 or A-F depending on system)</li>
<li>Add comments if needed</li>
<li>Press Enter or Tab to move to next cell</li>
<li>Click "Save" to confirm</li>
</ol>

<h3>Bulk Grade Entry</h3>
<ol>
<li>Click "Import Grades"</li>
<li>Upload CSV with student IDs and grades</li>
<li>Review the data</li>
<li>Confirm import</li>
</ol>

<h2>Assessment Types</h2>
<ul>
<li><strong>Continuous Assessment:</strong> Regular class participation and assignments</li>
<li><strong>Tests:</strong> Periodic written assessments</li>
<li><strong>Practicals:</strong> Hands-on skill assessments</li>
<li><strong>Projects:</strong> Extended submission-based work</li>
<li><strong>Final Exam:</strong> End-of-term comprehensive assessment</li>
</ul>

<h3>Setting Assessment Weights</h3>
<ol>
<li>Go to: Academics → Assessment Weights</li>
<li>Select your class and subject</li>
<li>Set percentage for each assessment type</li>
<li>Verify total = 100%</li>
<li>Save weights</li>
</ol>

<h2>Calculating Final Grades</h2>
<p>The system automatically calculates using the formula:</p>
<pre>Final Grade = (Continuous × 0.4) + (Test × 0.3) + (Practical × 0.2) + (Project × 0.1)</pre>

<h2>Grade Management Best Practices</h2>
<ul>
<li>Enter grades promptly after assessments</li>
<li>Keep records of all assessment scores</li>
<li>Use consistent grading scales</li>
<li>Provide constructive feedback with grades</li>
<li>Review grades for accuracy before finalizing</li>
<li>Maintain confidentiality of student grades</li>
</ul>

<h2>Handling Grade Changes</h2>
<ol>
<li>Click the grade cell</li>
<li>Click "Edit Grade History"</li>
<li>Add reason for change</li>
<li>Enter new grade</li>
<li>System tracks all changes automatically</li>
</ol>
                ''',
                'category': 'grading-assessment',
                'difficulty': 'INTERMEDIATE',
                'read_time': 14,
                'tags': ['grades', 'assessment', 'gradebook', 'marks'],
                'is_featured': True,
            },

            # Reports Articles
            {
                'title': 'Generating and Customizing Report Cards',
                'slug': 'generating-report-cards',
                'summary': 'Learn how to generate report cards, customize templates, and distribute to parents.',
                'content': '''
<h2>Report Card Generation Process</h2>
<h3>Step 1: Prepare Academic Data</h3>
<ul>
<li>Ensure all grades are entered</li>
<li>Verify assessment weights are set correctly</li>
<li>Confirm attendance records are complete</li>
<li>Review teacher comments</li>
</ul>

<h3>Step 2: Generate Report Cards</h3>
<ol>
<li>Navigate to: Reports → Report Cards</li>
<li>Select academic year</li>
<li>Select term/period</li>
<li>Select class or individual students</li>
<li>Click "Generate Report Cards"</li>
<li>System processes and displays preview</li>
</ol>

<h2>Customizing Report Card Templates</h2>
<h3>Accessing Template Settings</h3>
<ol>
<li>Go to: Reports → Report Card Templates</li>
<li>Select existing template or create new</li>
<li>Click "Edit Template"</li>
</ol>

<h3>Customization Options</h3>
<ul>
<li><strong>Logo & Header:</strong> Add school branding</li>
<li><strong>Sections:</strong> Choose which sections to include</li>
<li><strong>Grading Scale:</strong> Show letter grades, percentages, or both</li>
<li><strong>Comments:</strong> Include teacher feedback section</li>
<li><strong>Attendance:</strong> Display attendance percentage</li>
<li><strong>Footer:</strong> Add principal signature line</li>
</ul>

<h2>Distribution Methods</h2>
<h3>Print Report Cards</h3>
<ol>
<li>Open generated report cards</li>
<li>Click "Print"</li>
<li>Select paper size and quality</li>
<li>Print to physical copies</li>
</ol>

<h3>Email to Parents</h3>
<ol>
<li>Click "Send via Email"</li>
<li>Select recipients (all parents or specific)</li>
<li>Add message (optional)</li>
<li>Click "Send"</li>
<li>System sends PDF attachments</li>
</ol>

<h3>Online Portal</h3>
<ol>
<li>Report cards automatically appear in parent portal</li>
<li>Parents can download PDF versions</li>
<li>Audit trail tracks all downloads</li>
</ol>

<h2>Report Card Best Practices</h2>
<ul>
<li>Generate test reports before final release</li>
<li>Verify all information is accurate</li>
<li>Schedule release date in advance</li>
<li>Provide interpretation guide for grades</li>
<li>Allow time for parent-teacher meetings</li>
<li>Archive copies for records</li>
</ul>
                ''',
                'category': 'reports',
                'difficulty': 'INTERMEDIATE',
                'read_time': 12,
                'tags': ['reports', 'report-cards', 'grades', 'parents'],
                'is_featured': True,
            },

            # Communication Articles
            {
                'title': 'Using the Internal Communication System',
                'slug': 'internal-communication-system',
                'summary': 'Learn how to send messages, create announcements, and use the communication features effectively.',
                'content': '''
<h2>Communication Overview</h2>
<p>The internal communication system enables secure messaging between:</p>
<ul>
<li>Teachers and parents</li>
<li>Teachers and students</li>
<li>Staff members</li>
<li>Administration and all users</li>
</ul>

<h2>Sending Direct Messages</h2>
<h3>One-to-One Messaging</h3>
<ol>
<li>Click "Messages" in navigation</li>
<li>Click "New Message"</li>
<li>Select recipient from contacts</li>
<li>Type your message</li>
<li>Add attachments if needed</li>
<li>Click "Send"</li>
</ol>

<h3>Group Messaging</h3>
<ol>
<li>Click "New Group Message"</li>
<li>Select multiple recipients</li>
<li>Type message</li>
<li>Send to entire group</li>
</ol>

<h2>Creating Announcements</h2>
<h3>School-Wide Announcements</h3>
<ol>
<li>Navigate to: Communication → Announcements</li>
<li>Click "Create Announcement"</li>
<li>Enter announcement details</li>
<li>Select audience (All Users, Parents, Staff, etc.)</li>
<li>Set start and end dates</li>
<li>Click "Publish"</li>
</ol>

<h3>Class-Specific Announcements</h3>
<ol>
<li>Open class</li>
<li>Click "Create Announcement"</li>
<li>Write announcement for class only</li>
<li>Publish</li>
</ol>

<h2>Message Management</h2>
<h3>Organizing Messages</h3>
<ul>
<li>Create folders for different conversations</li>
<li>Star important messages</li>
<li>Search message history</li>
<li>Archive old conversations</li>
</ul>

<h3>Message Settings</h3>
<ol>
<li>Go to: Settings → Communication Preferences</li>
<li>Choose notification methods:</li>
<li>Email on new messages (On/Off)</li>
<li>SMS notifications (optional)</li>
<li>In-app notifications (always on)</li>
</ol>

<h2>Best Practices</h2>
<ul>
<li>Be professional and courteous</li>
<li>Respond to messages within 24 hours</li>
<li>Keep conversations focused on topic</li>
<li>Use announcements for broad updates</li>
<li>Use direct messages for sensitive matters</li>
<li>Do not send during non-school hours unless urgent</li>
</ul>
                ''',
                'category': 'communication',
                'difficulty': 'BEGINNER',
                'read_time': 10,
                'tags': ['communication', 'messaging', 'announcements', 'parents'],
                'is_featured': False,
            },

            # Finance Articles
            {
                'title': 'Setting Up Fee Structure and Payment Plans',
                'slug': 'fee-structure-payment-plans',
                'summary': 'Complete guide to configuring fees, creating payment plans, and managing financial structures.',
                'content': '''
<h2>Fee Structure Setup</h2>
<h3>Creating Fee Categories</h3>
<ol>
<li>Navigate to: Finance → Fee Structure</li>
<li>Click "Create Fee Category"</li>
<li>Define category name (e.g., "Tuition", "Activities")</li>
<li>Set category code</li>
<li>Click "Create"</li>
</ol>

<h3>Adding Fees to Categories</h3>
<ol>
<li>Open fee category</li>
<li>Click "Add Fee"</li>
<li>Enter fee name and amount</li>
<li>Define applicability (all students, specific grades, etc.)</li>
<li>Set due date</li>
<li>Save fee</li>
</ol>

<h2>Creating Payment Plans</h2>
<h3>Annual Plan (Single Payment)</h3>
<ol>
<li>Click "Create Payment Plan"</li>
<li>Select "Annual Payment"</li>
<li>Set due date (usually beginning of academic year)</li>
<li>Save</li>
</ol>

<h3>Installment Plan (Multiple Payments)</h3>
<ol>
<li>Click "Create Payment Plan"</li>
<li>Select "Installment Plan"</li>
<li>Enter number of installments (e.g., 3, 4, 6)</li>
<li>Define payment schedule:</li>
<li>Installment 1: Due Date</li>
<li>Installment 2: Due Date</li>
<li>Etc.</li>
<li>Save plan</li>
</ol>

<h2>Assigning Plans to Students</h2>
<ol>
<li>Navigate to: Finance → Student Billing</li>
<li>Search for student</li>
<li>Click "Create Invoice"</li>
<li>Select fees applicable to student</li>
<li>Select payment plan</li>
<li>Click "Generate Invoice"</li>
</ol>

<h2>Discount and Concession Management</h2>
<h3>Creating Discount Policies</h3>
<ol>
<li>Go to: Finance → Discounts</li>
<li>Click "Create Discount Policy"</li>
<li>Define discount type:</li>
<li>Percentage discount</li>
<li>Fixed amount discount</li>
<li>Set eligibility criteria</li>
<li>Save policy</li>
</ol>

<h3>Applying Discounts</h3>
<ol>
<li>Open student invoice</li>
<li>Click "Apply Discount"</li>
<li>Select discount policy</li>
<li>Verify amount</li>
<li>Confirm application</li>
</ol>

<h2>Invoice Management</h2>
<ul>
<li>Invoices are generated automatically based on fees</li>
<li>Send invoices to parents via email</li>
<li>Print invoices for distribution</li>
<li>Track payment status</li>
<li>Send reminders for overdue payments</li>
</ul>
                ''',
                'category': 'finance',
                'difficulty': 'INTERMEDIATE',
                'read_time': 13,
                'tags': ['fees', 'payments', 'invoices', 'finance'],
                'is_featured': True,
            },

            # Staff Management Articles
            {
                'title': 'Staff Record Management and Payroll Setup',
                'slug': 'staff-records-payroll',
                'summary': 'Learn how to add staff records, manage employment information, and set up payroll systems.',
                'content': '''
<h2>Adding Staff Members</h2>
<h3>Creating Staff Profiles</h3>
<ol>
<li>Navigate to: Staff Management → Staff Directory</li>
<li>Click "Add New Staff Member"</li>
<li>Fill in personal information</li>
<li>Upload profile photo</li>
<li>Click "Create Profile"</li>
</ol>

<h3>Required Information</h3>
<ul>
<li>Full name and date of birth</li>
<li>Gender and nationality</li>
<li>Contact information</li>
<li>Email address</li>
<li>Qualification and certifications</li>
<li>Employee ID</li>
</ul>

<h2>Employment Details</h2>
<h3>Setting Up Employment Records</h3>
<ol>
<li>Open staff profile</li>
<li>Click "Employment Details"</li>
<li>Fill in:</li>
<li>Position/Designation</li>
<li>Department</li>
<li>Date of joining</li>
<li>Employment type (Full-time, Part-time, Contract)</li>
<li>Reporting manager</li>
<li>Save</li>
</ol>

<h2>Payroll Configuration</h2>
<h3>Setting Up Salary Structure</h3>
<ol>
<li>Navigate to: Staff Management → Payroll</li>
<li>Click "Create Salary Structure"</li>
<li>Define salary components:</li>
<li>Basic salary</li>
<li>Dearness allowance</li>
<li>House rent allowance</li>
<li>Other allowances</li>
<li>Deductions (PF, TDS, etc.)</li>
<li>Save structure</li>
</ol>

<h3>Assigning Salary to Staff</h3>
<ol>
<li>Search for staff member</li>
<li>Click "Set Salary"</li>
<li>Select salary structure</li>
<li>Adjust amounts as needed</li>
<li>Confirm assignment</li>
</ol>

<h2>Generating Payroll</h2>
<h3>Monthly Payroll Processing</h3>
<ol>
<li>Go to: Staff Management → Payroll Processing</li>
<li>Select month</li>
<li>Click "Generate Payroll"</li>
<li>Review calculations</li>
<li>Verify attendance and leaves</li>
<li>Click "Finalize Payroll"</li>
</ol>

<h3>Generating Pay Slips</h3>
<ol>
<li>Go to: Staff Management → Pay Slips</li>
<li>Select staff member and month</li>
<li>Click "Generate Pay Slip"</li>
<li>Download or print</li>
<li>Send to employee</li>
</ol>

<h2>Attendance and Leave Management</h2>
<ul>
<li>Track daily attendance</li>
<li>Manage different leave types (Sick, Casual, Earned)</li>
<li>Deduct leave days from salary</li>
<li>Generate attendance reports</li>
<li>Monitor unauthorized absences</li>
</ul>
                ''',
                'category': 'staff-management',
                'difficulty': 'ADVANCED',
                'read_time': 14,
                'tags': ['staff', 'payroll', 'salary', 'employees'],
                'is_featured': True,
            },

            # System Admin Articles
            {
                'title': 'System Backup and Data Security',
                'slug': 'system-backup-security',
                'summary': 'Essential information about backing up your data, maintaining security, and protecting sensitive information.',
                'content': '''
<h2>Data Backup Overview</h2>
<p>Regular backups are crucial for business continuity and disaster recovery.</p>

<h3>Types of Backups</h3>
<ul>
<li><strong>Daily Backups:</strong> Automatic, stored on secure servers</li>
<li><strong>Weekly Backups:</strong> Comprehensive backup of all data</li>
<li><strong>Monthly Backups:</strong> Archive for long-term retention</li>
</ul>

<h2>Automatic Backup Configuration</h2>
<h3>Setting Up Auto-Backups</h3>
<ol>
<li>Navigate to: System Settings → Backup & Recovery</li>
<li>Click "Configure Automatic Backups"</li>
<li>Set backup frequency (Daily, Weekly, Monthly)</li>
<li>Choose backup time (preferably off-peak hours)</li>
<li>Enable encryption for sensitive data</li>
<li>Save configuration</li>
</ol>

<h3>Backup Schedule</h3>
<pre>Monday-Friday: 2:00 AM UTC
Weekend: 4:00 AM UTC
First of month: Full system backup</pre>

<h2>Manual Backup Process</h2>
<ol>
<li>Go to: System Settings → Backup & Recovery</li>
<li>Click "Create Manual Backup Now"</li>
<li>Select data to include</li>
<li>Click "Start Backup"</li>
<li>Download backup file when complete</li>
<li>Store securely offline</li>
</ol>

<h2>Data Security Best Practices</h2>
<h3>Access Control</h3>
<ul>
<li>Use strong passwords (minimum 12 characters)</li>
<li>Enable two-factor authentication (2FA)</li>
<li>Regularly audit user access rights</li>
<li>Disable inactive accounts</li>
<li>Implement role-based access control</li>
</ul>

<h3>Data Privacy</h3>
<ul>
<li>Encrypt sensitive student data</li>
<li>Encrypt financial information</li>
<li>Use HTTPS for all communications</li>
<li>Comply with data protection regulations</li>
<li>Implement data retention policies</li>
</ul>

<h2>Disaster Recovery</h2>
<h3>Backup Verification</h3>
<ol>
<li>Monthly test restore of backups</li>
<li>Verify all data is recoverable</li>
<li>Document recovery procedures</li>
<li>Train staff on recovery process</li>
</ol>

<h3>Recovery Process</h3>
<ol>
<li>Contact system administrator</li>
<li>Identify backup to restore</li>
<li>Initiate recovery procedure</li>
<li>Verify data integrity post-recovery</li>
<li>Communicate with affected users</li>
</ol>

<h2>Important Notes</h2>
<ul>
<li>Backups are retained for 90 days by default</li>
<li>Extended backups require storage upgrade</li>
<li>Deleted data may be recovered from backups</li>
<li>System maintenance requires brief downtime</li>
<li>Maintenance windows: Sundays 2-4 AM UTC</li>
</ul>
                ''',
                'category': 'system-admin',
                'difficulty': 'ADVANCED',
                'read_time': 12,
                'tags': ['backup', 'security', 'data-protection', 'administration'],
                'is_featured': False,
            },
        ]

        # Create articles
        created_count = 0
        for article_data in articles:
            category = categories.get(article_data['category'])
            if not category:
                self.stdout.write(self.style.WARNING(f"  ! Category not found: {article_data['category']}"))
                continue

            tags_str = ', '.join(article_data.get('tags', []))
            article, created = KBArticle.objects.get_or_create(
                slug=article_data['slug'],
                defaults={
                    'title': article_data['title'],
                    'summary': article_data['summary'],
                    'content': article_data['content'],
                    'category': category,
                    'difficulty': article_data['difficulty'],
                    'estimated_read_time': article_data.get('read_time', 5),
                    'tags': tags_str,
                    'author': admin_user,
                    'status': 'PUBLISHED',
                    'is_featured': article_data.get('is_featured', False),
                }
            )

            if created:
                created_count += 1
                self.stdout.write(f"  ✓ Article: {article_data['title']}")
            else:
                self.stdout.write(f"  - Article already exists: {article_data['title']}")

        self.stdout.write(
            self.style.SUCCESS(f'\n✓ Successfully created {created_count} KB articles!')
        )
        self.stdout.write(self.style.SUCCESS('✓ KB seeding complete!'))
