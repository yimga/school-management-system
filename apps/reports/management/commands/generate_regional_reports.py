"""
Generate regional reports with localized content and score conversion.
Usage: python manage.py generate_regional_reports [--language LANG] [--region REGION] [--format pdf|html]
"""

from django.core.management.base import BaseCommand
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import translation
from datetime import datetime

from apps.academics.models import AcademicYear, Term, Classroom
from apps.people.models import StudentProfile
from apps.reports.models import ReportCard
from apps.reports.localization import (
    get_certificate_localizer,
    get_transcript_localizer,
)
from apps.siteconfig.translations import SUPPORTED_LANGUAGES
from apps.siteconfig.models import RegionConfig
from apps.evals.models import Evaluation
from decimal import Decimal


class Command(BaseCommand):
    help = 'Generate regional reports with localized content and score conversion'

    def add_arguments(self, parser):
        parser.add_argument(
            '--language',
            type=str,
            default='en',
            help='Language for report (en, fr, sw, yo, pid, ha)',
        )
        parser.add_argument(
            '--region',
            type=str,
            help='Region code for score conversion (CMR, USA, KEN, NGA, etc)',
        )
        parser.add_argument(
            '--classroom',
            type=int,
            help='Generate for specific classroom',
        )
        parser.add_argument(
            '--student',
            type=int,
            help='Generate for specific student',
        )
        parser.add_argument(
            '--format',
            type=str,
            default='pdf',
            choices=['pdf', 'html'],
            help='Output format',
        )
        parser.add_argument(
            '--send-email',
            action='store_true',
            help='Send reports via email to parents',
        )
        parser.add_argument(
            '--academic-year',
            type=int,
            help='Academic year ID',
        )
        parser.add_argument(
            '--term',
            type=int,
            help='Term ID',
        )

    def handle(self, *args, **options):
        language = options.get('language', 'en')
        if language not in SUPPORTED_LANGUAGES:
            self.stdout.write(self.style.ERROR(f'Invalid language: {language}'))
            return

        translation.activate(language)

        region = None
        if options.get('region'):
            try:
                region = RegionConfig.objects.get(code=options['region'])
            except RegionConfig.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Region not found: {options['region']}"))
                return

        self.stdout.write(self.style.SUCCESS(f'\n[*] Regional Report Generator'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'Language: {language}')
        if region:
            self.stdout.write(f'Region: {region.name} ({region.code})')
        else:
            self.stdout.write('Region: Default (no score conversion)')

        # Query students
        students = StudentProfile.objects.all()

        if options.get('student'):
            students = students.filter(id=options['student'])
        
        if options.get('classroom'):
            students = students.filter(current_classroom_id=options['classroom'])

        if not students.exists():
            self.stdout.write(self.style.WARNING('No students found'))
            return

        # Get academic year and term
        academic_year = None
        if options.get('academic_year'):
            try:
                academic_year = AcademicYear.objects.get(id=options['academic_year'])
            except AcademicYear.DoesNotExist:
                pass

        term = None
        if options.get('term'):
            try:
                term = Term.objects.get(id=options['term'])
            except Term.DoesNotExist:
                pass

        if not academic_year:
            academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not term:
            term = Term.objects.filter(is_active=True).first()

        self.stdout.write(f'Academic Year: {academic_year}')
        self.stdout.write(f'Term: {term}')
        self.stdout.write(f'Students to process: {students.count()}')
        self.stdout.write('=' * 60)

        success_count = 0
        error_count = 0

        for student in students:
            try:
                report_data = self._build_report_data(student, academic_year, term, language, region)
                
                if options.get('send_email'):
                    self._send_report_email(student, report_data, language)

                success_count += 1
                self.stdout.write(f'[+] Generated for {student.user.get_full_name()}')
            
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f'[!] Error for {student}: {str(e)}'))

        self.stdout.write('=' * 60)
        self.stdout.write(self.style.SUCCESS(f'[+] Completed: {success_count} success, {error_count} errors'))

    def _build_report_data(self, student, academic_year, term, language, region):
        """Build report data for a student."""
        localizer = get_certificate_localizer(language, region.code if region else None)

        # Get evaluations for student
        evaluations = Evaluation.objects.filter(
            student=student,
            academic_year=academic_year,
            term=term,
        ).select_related('component', 'subject')

        # Calculate average
        scores = {}
        for eval in evaluations:
            subject_name = eval.subject.name if eval.subject else 'General'
            if subject_name not in scores:
                scores[subject_name] = []
            scores[subject_name].append(float(eval.score or 0))

        average_score = 0
        if scores:
            all_scores = []
            for subject_scores in scores.values():
                all_scores.extend(subject_scores)
            average_score = sum(all_scores) / len(all_scores) if all_scores else 0

        return {
            'student_name': student.user.get_full_name(),
            'student_id': student.admission_number,
            'class': student.current_classroom.name if student.current_classroom else 'N/A',
            'academic_year': str(academic_year),
            'term': term.label if term else 'N/A',
            'language': language,
            'region': region.name if region else 'Default',
            'average_score': round(average_score, 2),
            'scores': scores,
            'grade_letter': localizer.get_grade_letter(average_score),
            'performance_comment': localizer.get_performance_comment(average_score),
            'date_issued': datetime.now().strftime('%Y-%m-%d'),
            'certificate_strings': localizer.strings,
        }

    def _send_report_email(self, student, report_data, language):
        """Send report via email to student's guardians."""
        from apps.people.models import StudentGuardian
        
        guardians = StudentGuardian.objects.filter(
            student=student,
            can_view_results=True,
        ).select_related('guardian_user')

        if not guardians.exists():
            self.stdout.write(self.style.WARNING(f'No guardians found for {student}'))
            return

        # Get email template
        template_name = f'emails/report_ready_{language}.html'
        
        # Build absolute logo URL for email templates (one place for report emails)
        logo_url = ''
        try:
            from django.conf import settings
            from apps.siteconfig.models import SiteSettings
            site = SiteSettings.get_solo()
            if site and getattr(site, 'active_theme', None):
                theme = site.active_theme
                if theme and getattr(theme, 'logo', None):
                    logo_url = theme.logo.url if theme.logo else ''
            if logo_url and not logo_url.startswith(('http://', 'https://')):
                logo_url = (getattr(settings, 'SITE_ROOT_URL', '') or '').rstrip('/') + logo_url
        except Exception:
            pass
        context = {
            'parent_name': guardians.first().guardian_user.get_full_name(),
            'student_name': student.user.get_full_name(),
            'class_name': report_data['class'],
            'academic_year': report_data['academic_year'],
            'term_name': report_data['term'],
            'average_score': report_data['average_score'],
            'class_rank': 'TBD',  # Would calculate from ranking system
            'report_url': 'https://schoolmanagement.local/reports/view/',
            'school_name': 'School Management System',
            'current_year': datetime.now().year,
            'logo_url': logo_url,
        }

        try:
            html_message = render_to_string(template_name, context)
            
            email = EmailMessage(
                subject=f"Report Card Ready - {report_data['student_name']}",
                body=html_message,
                from_email='noreply@schoolmanagement.local',
                to=[g.guardian_user.email for g in guardians],
            )
            email.content_subtype = 'html'
            email.send()
            
            self.stdout.write(self.style.SUCCESS(f'  [+] Email sent to guardians'))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  [!] Email error: {str(e)}'))
