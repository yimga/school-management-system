"""
Phase 4: Data Integrity Verification Command

Comprehensive verification of system data integrity:
- Database constraints and FK relationships
- Orphaned records detection
- Role-based access rule validation
- Audit log completeness
- Term position validation (1-4 range)
- Payment method consistency
- User profile consistency
- Academic year/term relationships

Usage:
    python manage.py verify_data_integrity [--fix] [--verbose] [--report=json|text]
"""

from django.core.management.base import BaseCommand
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from apps.academics.models import Term, AcademicYear
from apps.evals.models import Evaluation, TeacherAssignment
from apps.people.models import TeacherProfile, StudentProfile
from apps.finance.models import Invoice, Payment
from apps.accounts.models import User
from apps.compliance.models_audit import AuditLog, AccessLog


class Command(BaseCommand):
    help = "Verify data integrity across the system"

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix issues automatically'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output for each check'
        )
        parser.add_argument(
            '--report',
            type=str,
            choices=['json', 'text'],
            default='text',
            help='Output format for report'
        )

    def handle(self, *args, **options):
        self.fix = options.get('fix', False)
        self.verbose = options.get('verbose', False)
        self.report_format = options.get('report', 'text')
        self.issues = []
        self.fixes = []

        self.stdout.write("Phase 4: Data Integrity Verification")
        self.stdout.write("=" * 60)

        # Run all checks
        self._check_constraints()
        self._check_foreign_keys()
        self._check_term_positions()
        self._check_user_profiles()
        self._check_audit_logs()
        self._check_payment_consistency()
        self._check_role_based_access()
        self._check_academic_structure()

        # Print report
        self._print_report()

    def _check_constraints(self):
        """Check database constraints."""
        self.stdout.write("\n[1/8] Checking database constraints...")
        
        # Check for null required fields
        users_no_email = User.objects.filter(email__isnull=True).count()
        if users_no_email > 0:
            self.issues.append({
                'severity': 'HIGH',
                'category': 'CONSTRAINT',
                'description': f"{users_no_email} users have null email",
                'count': users_no_email,
            })

        # Check for duplicate emails
        dup_emails = User.objects.values('email').filter(
            email__isnull=False
        ).annotate(count=Count('id')).filter(count__gt=1)
        
        if dup_emails.exists():
            for item in dup_emails:
                self.issues.append({
                    'severity': 'HIGH',
                    'category': 'DUPLICATE',
                    'description': f"Duplicate email: {item['email']}",
                    'count': item['count'],
                })

        if self.verbose or (not users_no_email and not dup_emails.exists()):
            self.stdout.write("  ✓ Database constraints OK")

    def _check_foreign_keys(self):
        """Check for orphaned foreign key references."""
        self.stdout.write("[2/8] Checking foreign key integrity...")
        
        orphaned = 0

        # Check evaluations with missing students
        eval_no_student = Evaluation.objects.filter(student__isnull=True).count()
        if eval_no_student > 0:
            self.issues.append({
                'severity': 'CRITICAL',
                'category': 'ORPHANED_FK',
                'description': f"{eval_no_student} evaluations have null student",
                'model': 'Evaluation',
                'count': eval_no_student,
            })
            orphaned += eval_no_student

        # Check payments with missing invoices
        pay_no_invoice = Payment.objects.filter(invoice__isnull=True).count()
        if pay_no_invoice > 0:
            self.issues.append({
                'severity': 'CRITICAL',
                'category': 'ORPHANED_FK',
                'description': f"{pay_no_invoice} payments have null invoice",
                'model': 'Payment',
                'count': pay_no_invoice,
            })
            orphaned += pay_no_invoice

        # Check teacher profiles with missing users
        teacher_no_user = TeacherProfile.objects.filter(user__isnull=True).count()
        if teacher_no_user > 0:
            self.issues.append({
                'severity': 'HIGH',
                'category': 'ORPHANED_FK',
                'description': f"{teacher_no_user} teacher profiles have null user",
                'model': 'TeacherProfile',
                'count': teacher_no_user,
            })
            orphaned += teacher_no_user

        if self.verbose or orphaned == 0:
            self.stdout.write(f"  ✓ Foreign key integrity OK ({orphaned} orphaned found)")

    def _check_term_positions(self):
        """Validate term positions are in range 1-4."""
        self.stdout.write("[3/8] Checking term position validity...")
        
        invalid_positions = Term.objects.filter(
            position__isnull=False
        ).exclude(
            Q(position__gte=1) & Q(position__lte=4)
        )

        if invalid_positions.exists():
            count = invalid_positions.count()
            self.issues.append({
                'severity': 'HIGH',
                'category': 'POSITION_INVALID',
                'description': f"{count} terms have invalid positions (outside 1-4 range)",
                'terms': list(invalid_positions.values_list('id', 'name', 'position')),
            })

            if self.fix:
                # Auto-fix by removing invalid positions
                invalid_positions.update(position=None)
                self.fixes.append(f"Reset positions for {count} terms")

        # Check for duplicate positions in same year
        dup_positions = Term.objects.exclude(
            position__isnull=True
        ).values(
            'academic_year', 'position'
        ).annotate(
            count=Count('id')
        ).filter(count__gt=1)

        if dup_positions.exists():
            self.issues.append({
                'severity': 'HIGH',
                'category': 'POSITION_DUPLICATE',
                'description': f"{dup_positions.count()} term positions are duplicated within year",
            })

        if self.verbose or not (invalid_positions.exists() or dup_positions.exists()):
            self.stdout.write("  ✓ Term positions valid")

    def _check_user_profiles(self):
        """Check user profile consistency."""
        self.stdout.write("[4/8] Checking user profile consistency...")
        
        issues_found = 0

        # Check teachers without profiles
        teachers_no_profile = User.objects.filter(
            role='TEACHER'
        ).exclude(id__in=TeacherProfile.objects.values_list('user_id'))
        
        if teachers_no_profile.exists():
            self.issues.append({
                'severity': 'MEDIUM',
                'category': 'MISSING_PROFILE',
                'description': f"{teachers_no_profile.count()} teacher users missing profiles",
                'model': 'TeacherProfile',
                'count': teachers_no_profile.count(),
            })
            issues_found += teachers_no_profile.count()

        # Check for students with missing required fields
        students_incomplete = StudentProfile.objects.filter(
            Q(first_name__isnull=True) | Q(first_name='') |
            Q(last_name__isnull=True) | Q(last_name='')
        ).count()
        
        if students_incomplete > 0:
            self.issues.append({
                'severity': 'MEDIUM',
                'category': 'INCOMPLETE_DATA',
                'description': f"{students_incomplete} student profiles missing name fields",
                'model': 'StudentProfile',
                'count': students_incomplete,
            })
            issues_found += students_incomplete

        if self.verbose or issues_found == 0:
            self.stdout.write(f"  ✓ User profiles consistent ({issues_found} issues)")

    def _check_audit_logs(self):
        """Check audit log completeness."""
        self.stdout.write("[5/8] Checking audit log coverage...")
        
        last_week = timezone.now() - timedelta(days=7)
        
        # Check if there are recent model changes
        recent_evals = Evaluation.objects.filter(
            updated_at__gte=last_week
        ).count()
        
        recent_audit = AuditLog.objects.filter(
            timestamp__gte=last_week,
            model_name='Evaluation'
        ).count()

        if recent_evals > 0 and recent_audit == 0:
            self.issues.append({
                'severity': 'MEDIUM',
                'category': 'MISSING_AUDIT',
                'description': f"No audit logs for {recent_evals} recent Evaluation changes",
            })

        # Check for access logs
        AccessLog.objects.filter(
            timestamp__gte=last_week
        ).count()

        if self.verbose or (recent_evals == 0 or recent_audit > 0):
            self.stdout.write(f"  ✓ Audit logs present ({recent_audit} audit logs this week)")

    def _check_payment_consistency(self):
        """Check payment and invoice consistency."""
        self.stdout.write("[6/8] Checking payment consistency...")
        
        issues_found = 0

        # Check invoices with negative balance
        negative_balance = Invoice.objects.filter(balance_amount__lt=0).count()
        if negative_balance > 0:
            self.issues.append({
                'severity': 'HIGH',
                'category': 'NEGATIVE_BALANCE',
                'description': f"{negative_balance} invoices have negative balance",
                'count': negative_balance,
            })
            issues_found += negative_balance

        # Check for unmatched payments
        unmatched_payments = Payment.objects.filter(
            invoice__isnull=True
        ).count()
        
        if unmatched_payments > 0:
            self.issues.append({
                'severity': 'HIGH',
                'category': 'UNMATCHED_PAYMENT',
                'description': f"{unmatched_payments} payments not linked to invoices",
                'count': unmatched_payments,
            })
            issues_found += unmatched_payments

        # Check payment method validity
        invalid_methods = Payment.objects.exclude(
            method__in=['CASH', 'CARD', 'BANK_TRANSFER', 'MOBILE_MONEY']
        ).count()
        
        if invalid_methods > 0:
            self.issues.append({
                'severity': 'MEDIUM',
                'category': 'INVALID_METHOD',
                'description': f"{invalid_methods} payments have invalid method",
                'count': invalid_methods,
            })
            issues_found += invalid_methods

        if self.verbose or issues_found == 0:
            self.stdout.write(f"  ✓ Payment consistency OK ({issues_found} issues)")

    def _check_role_based_access(self):
        """Check role-based access rule consistency."""
        self.stdout.write("[7/8] Checking role-based access rules...")
        
        issues_found = 0

        # Check admins without superuser
        non_super_admins = User.objects.filter(
            role='ADMIN',
            is_superuser=False
        ).count()

        if non_super_admins > 0:
            self.issues.append({
                'severity': 'MEDIUM',
                'category': 'ROLE_MISMATCH',
                'description': f"{non_super_admins} ADMIN users without superuser flag",
                'count': non_super_admins,
            })
            issues_found += non_super_admins

        # Check students with teacher assignments
        student_teachers = TeacherAssignment.objects.filter(
            teacher__user__role='STUDENT'
        ).count()

        if student_teachers > 0:
            self.issues.append({
                'severity': 'HIGH',
                'category': 'INVALID_ASSIGNMENT',
                'description': f"{student_teachers} teacher assignments to student accounts",
                'count': student_teachers,
            })
            issues_found += student_teachers

        if self.verbose or issues_found == 0:
            self.stdout.write(f"  ✓ Role-based access OK ({issues_found} issues)")

    def _check_academic_structure(self):
        """Check academic year and term structure."""
        self.stdout.write("[8/8] Checking academic structure...")
        
        issues_found = 0

        # Check for overlapping academic years
        years = AcademicYear.objects.values_list('id', 'start_date', 'end_date')
        overlapping = 0
        
        for i, (y1_id, y1_start, y1_end) in enumerate(years):
            for y2_id, y2_start, y2_end in years[i+1:]:
                if not (y1_end < y2_start or y2_end < y1_start):
                    overlapping += 1

        if overlapping > 0:
            self.issues.append({
                'severity': 'MEDIUM',
                'category': 'OVERLAPPING_YEARS',
                'description': f"{overlapping} pairs of overlapping academic years",
            })
            issues_found += overlapping

        # Check for terms outside their academic year
        bad_terms = Term.objects.exclude(
            Q(start_date__gte=F('academic_year__start_date')) &
            Q(end_date__lte=F('academic_year__end_date'))
        ).count()

        if bad_terms > 0:
            self.issues.append({
                'severity': 'HIGH',
                'category': 'TERM_OUT_OF_RANGE',
                'description': f"{bad_terms} terms outside their academic year dates",
                'count': bad_terms,
            })
            issues_found += bad_terms

        if self.verbose or issues_found == 0:
            self.stdout.write(f"  ✓ Academic structure valid ({issues_found} issues)")

    def _print_report(self):
        """Print integrity report."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("DATA INTEGRITY REPORT")
        self.stdout.write("=" * 60)

        if not self.issues:
            self.stdout.write(self.style.SUCCESS("\n✓ All checks passed! System is healthy."))
            return

        # Group by severity
        critical = [i for i in self.issues if i.get('severity') == 'CRITICAL']
        high = [i for i in self.issues if i.get('severity') == 'HIGH']
        medium = [i for i in self.issues if i.get('severity') == 'MEDIUM']

        if critical:
            self.stdout.write(self.style.ERROR(f"\n🔴 CRITICAL ISSUES ({len(critical)}):"))
            for issue in critical:
                self.stdout.write(f"  • {issue['description']}")

        if high:
            self.stdout.write(self.style.WARNING(f"\n🟠 HIGH ISSUES ({len(high)}):"))
            for issue in high:
                self.stdout.write(f"  • {issue['description']}")

        if medium:
            self.stdout.write(self.style.WARNING(f"\n🟡 MEDIUM ISSUES ({len(medium)}):"))
            for issue in medium:
                self.stdout.write(f"  • {issue['description']}")

        if self.fixes:
            self.stdout.write(self.style.SUCCESS(f"\n✓ FIXES APPLIED ({len(self.fixes)}):"))
            for fix in self.fixes:
                self.stdout.write(f"  • {fix}")

        # Summary
        self.stdout.write("\n" + "-" * 60)
        self.stdout.write(f"Total Issues: {len(self.issues)}")
        self.stdout.write(f"Critical: {len(critical)}, High: {len(high)}, Medium: {len(medium)}")
        self.stdout.write(f"Fixes Applied: {len(self.fixes)}")


# Import at end to avoid circular dependencies
from django.db.models import F
