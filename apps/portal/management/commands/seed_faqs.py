"""
Seed a curated FAQ set into the portal FAQ system.

Idempotent: if a question already exists (case-insensitive), it is skipped.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.portal.models_kb import FAQ, FAQCategory

User = get_user_model()


class Command(BaseCommand):
    help = "Seed curated FAQs for operators/teachers/parents."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing.",
        )

    def handle(self, *args, **options):
        if options.get("dry_run"):
            self.stdout.write(
                self.style.SUCCESS(
                    "Dry run: would ensure FAQ categories and curated questions."
                )
            )
            return
        admin_user = (
            User.objects.filter(is_superuser=True).first()
            or User.objects.filter(is_staff=True).first()
        )

        categories = {
            "getting-started": {
                "name": "Getting Started",
                "icon": "fa-rocket",
                "order": 1,
            },
            "year-setup": {"name": "Year Setup", "icon": "fa-calendar", "order": 2},
            "student-management": {
                "name": "Student Management",
                "icon": "fa-user-graduate",
                "order": 3,
            },
            "teacher-management": {
                "name": "Teacher Management",
                "icon": "fa-chalkboard-teacher",
                "order": 4,
            },
            "marks-evaluations": {
                "name": "Marks & Evaluations",
                "icon": "fa-clipboard-check",
                "order": 5,
            },
            "reports": {
                "name": "Reports & Report Cards",
                "icon": "fa-file-alt",
                "order": 6,
            },
            "finance": {"name": "Finance & Fees", "icon": "fa-coins", "order": 7},
            "messaging": {
                "name": "Messaging & Communication",
                "icon": "fa-comments",
                "order": 8,
            },
            "document-library": {
                "name": "Document Library",
                "icon": "fa-folder-open",
                "order": 9,
            },
            "gce-certification": {
                "name": "GCE/Certification",
                "icon": "fa-certificate",
                "order": 10,
            },
            "onboarding": {"name": "Onboarding", "icon": "fa-user-plus", "order": 11},
            "troubleshooting": {
                "name": "Troubleshooting",
                "icon": "fa-life-ring",
                "order": 99,
            },
        }

        cat_objs = {}
        for slug, meta in categories.items():
            obj, _ = FAQCategory.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": meta["name"],
                    "description": f"FAQs about {meta['name']}",
                    "icon": meta["icon"],
                    "display_order": meta["order"],
                    "is_active": True,
                },
            )
            cat_objs[slug] = obj

        faqs = [
            {
                "category": "messaging",
                "question": "Where do I find Messaging?",
                "answer": (
                    "Use the left sidebar: **Messages** (for your class threads/inbox) and **Message Groups** "
                    "(for staff/department/group chats). If you are a Parent, use **Class Messages** and/or **Contact School**."
                ),
                "tags": "messaging, chat, groups, sidebar, communication",
                "is_featured": True,
                "order": 1,
            },
            {
                "category": "reports",
                "question": "How do I publish report cards to parents?",
                "answer": (
                    "Go to **Publish term results** (from the sidebar or Workflow Center), run batch generation for the class, "
                    "review, then publish. Parents will see results in their portal once published."
                ),
                "tags": "reports, publish, term results, report cards",
                "is_featured": True,
                "order": 2,
            },
            {
                "category": "reports",
                "question": "Where is the report card builder?",
                "answer": (
                    "Admins can open **Report Card Builder** from the sidebar (or Workflow Center). "
                    "This controls report styles/templates (including Cameroon-style layouts)."
                ),
                "tags": "report builder, templates, styles, cameroon",
                "order": 3,
            },
            {
                "category": "onboarding",
                "question": "How do parents link a child to their account?",
                "answer": (
                    "Parents can link a child via **Invite code** (recommended) or via **Admission number** using the Link Child wizard."
                ),
                "tags": "parent, link child, invite, admission number",
                "order": 4,
            },
            {
                "category": "onboarding",
                "question": "How do admission numbers work?",
                "answer": (
                    "Admission numbers can be system-generated or manually entered depending on Site Settings. "
                    "If left blank during student creation, the system can auto-generate a number following your configured pattern."
                ),
                "tags": "admission number, registration, configuration",
                "order": 5,
            },
            {
                "category": "getting-started",
                "question": "What is the difference between /admin and /backend?",
                "answer": (
                    "**/admin**: Django Admin panel for system configuration (backend administrators only). "
                    "**/backend**: User-friendly dashboard for school administrators (operators, registrars, etc.). "
                    "**/portal**: Parent and student-facing portal. Use /backend for daily operations, /admin for advanced configuration."
                ),
                "tags": "getting started, admin, backend, portal",
                "is_featured": True,
                "order": 1,
            },
            {
                "category": "year-setup",
                "question": "How do I set up a new academic year?",
                "answer": (
                    "1. Create Academic Year 2. Create Terms (typically 3) 3. Create Classrooms 4. Create Subjects "
                    "5. Assign Subjects to Classrooms. See the complete Year Setup Process guide in the Knowledge Base."
                ),
                "tags": "year setup, academic year, terms, classrooms",
                "is_featured": True,
                "order": 1,
            },
            {
                "category": "year-setup",
                "question": "Can I have multiple academic years active at once?",
                "answer": (
                    "No, only one academic year should be active at a time. The system uses the active year for most operations."
                ),
                "tags": "academic year, active year",
                "order": 2,
            },
            {
                "category": "student-management",
                "question": "How do I enroll a new student?",
                "answer": (
                    "Three methods: 1) Admin creates student in /admin/people/studentprofile/, "
                    "2) Self-registration via /portal/student/onboarding/, or 3) Bulk import via CSV upload. "
                    "See the Student Onboarding Workflow guide for complete steps."
                ),
                "tags": "student, enrollment, onboarding",
                "is_featured": True,
                "order": 1,
            },
            {
                "category": "marks-evaluations",
                "question": "How do I enter marks?",
                "answer": (
                    "Three methods: 1) Manual entry - enter scores directly, 2) OCR upload - upload marksheet image, "
                    "3) CSV import - bulk import from spreadsheet. See the Marks Entry Process guide for details."
                ),
                "tags": "marks, entry, ocr, csv",
                "is_featured": True,
                "order": 1,
            },
            {
                "category": "marks-evaluations",
                "question": "What is the approval workflow for marks?",
                "answer": (
                    "1. Teacher submits marks 2. First approver (Dean/HOD) reviews 3. Final approver (Registrar/Director) reviews "
                    "4. Marks approved and finalized 5. Can be published to report cards."
                ),
                "tags": "marks, approval, workflow",
                "order": 2,
            },
            {
                "category": "reports",
                "question": "How do I generate report cards?",
                "answer": (
                    "1. Ensure all marks approved 2. Configure report card style 3. Navigate to 'Publish Term Results' "
                    "4. Select Year, Term, Classroom 5. Generate report cards 6. Review and publish. "
                    "See the Report Card Generation Workflow guide for complete steps."
                ),
                "tags": "report cards, generation, publishing",
                "is_featured": True,
                "order": 1,
            },
            {
                "category": "reports",
                "question": "How are rankings calculated?",
                "answer": (
                    "**Class Rank**: Rank within same classroom. **School Rank**: Rank across entire school. "
                    "**Specialty Rank**: Rank within same classroom AND specialty. Same rank for tied averages."
                ),
                "tags": "rankings, class rank, school rank",
                "order": 2,
            },
            {
                "category": "finance",
                "question": "How do I create invoices?",
                "answer": (
                    "Two methods: 1) Single invoice - create for one student, 2) Bulk creation - create for multiple students "
                    "using fee template. See the Finance Workflows guide for complete steps."
                ),
                "tags": "invoices, fees, bulk",
                "is_featured": True,
                "order": 1,
            },
            {
                "category": "finance",
                "question": "How do I process mobile money payments?",
                "answer": (
                    "1. Parent pays via MTN Mobile Money or Orange Money 2. Parent uploads payment proof "
                    "3. Finance staff verifies transaction 4. Approve payment 5. System updates invoice status."
                ),
                "tags": "mobile money, payment, mtn, orange",
                "order": 2,
            },
            {
                "category": "document-library",
                "question": "What is the Document Library?",
                "answer": (
                    "A centralized place to store and share school documents (registration forms, consent forms, fee forms, etc.). "
                    "Admin access: /portal/backend/documents/ (manage). Public access: /portal/feature/documents/ (view/download)."
                ),
                "tags": "documents, library, forms",
                "is_featured": True,
                "order": 1,
            },
            {
                "category": "document-library",
                "question": "How do electronic signatures work?",
                "answer": (
                    "1. Admin uploads form requiring signature 2. Admin creates signature request for parent "
                    "3. Parent receives notification 4. Parent signs form electronically 5. System generates signed PDF "
                    "6. Both parties receive copy."
                ),
                "tags": "signatures, e-signature, forms",
                "order": 2,
            },
            {
                "category": "gce-certification",
                "question": "How do I enable GCE registration?",
                "answer": (
                    "Navigate to Academic Year settings, check 'Enable GCE Registration', and save. "
                    "Note: Must be enabled per academic year."
                ),
                "tags": "gce, certification, registration",
                "order": 1,
            },
            {
                "category": "gce-certification",
                "question": "How do I export CA marks for GCE?",
                "answer": (
                    "Navigate to Exam Session Detail, click 'Export Pack', system generates ca_marks.csv with technical splits, "
                    "download ZIP file. System calculates CA marks automatically based on preset configuration."
                ),
                "tags": "gce, ca marks, export",
                "order": 2,
            },
            {
                "category": "troubleshooting",
                "question": "I clicked a menu item and nothing happened. What should I do?",
                "answer": (
                    "First refresh the page and try again. If the item still does nothing, check if your role has access. "
                    "Use **Request access** (Messages) or contact the school admin to enable the feature/permission."
                ),
                "tags": "troubleshooting, permissions, access",
                "order": 99,
            },
            {
                "category": "troubleshooting",
                "question": "Why can't I enter marks?",
                "answer": (
                    "Check: 1) Are you assigned to the subject/classroom? 2) Is the term active? "
                    "3) Are marks already approved? (may need to request changes) 4) Do you have permission? "
                    "Verify subject assignments and permissions."
                ),
                "tags": "troubleshooting, marks, permissions",
                "order": 100,
            },
            {
                "category": "troubleshooting",
                "question": "Why can't parents see report cards?",
                "answer": (
                    "Check: 1) Are report cards published? 2) Is parent linked to student? "
                    "3) Is parent account active? 4) Is term/classroom correct? Verify publishing status and parent-student link."
                ),
                "tags": "troubleshooting, report cards, parents",
                "order": 101,
            },
        ]

        created = 0
        skipped = 0
        for item in faqs:
            category = cat_objs[item["category"]]
            question = item["question"].strip()
            exists = FAQ.objects.filter(Q(question__iexact=question)).exists()
            if exists:
                skipped += 1
                continue

            faq = FAQ.objects.create(
                category=category,
                question=question,
                answer=item["answer"],
                tags=item.get("tags", ""),
                is_featured=bool(item.get("is_featured", False)),
                display_order=int(item.get("order", 0)),
                status="APPROVED",
                submitted_by=admin_user,
                reviewed_by=admin_user,
            )
            created += 1
            self.stdout.write(self.style.SUCCESS(f"Created FAQ: {faq.question}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("FAQ seed complete."))
        self.stdout.write(f"  Created: {created}")
        self.stdout.write(f"  Skipped (already existed): {skipped}")
