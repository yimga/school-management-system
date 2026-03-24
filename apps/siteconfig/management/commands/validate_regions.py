"""
Validate region configurations for completeness and consistency.
Usage: python manage.py validate_regions
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
import pytz

from apps.registries.services import is_known_currency_code
from apps.siteconfig.models import RegionConfig


class Command(BaseCommand):
    help = "Validate regional configurations for completeness and consistency"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Attempt to fix minor issues automatically",
        )
        parser.add_argument(
            "--region",
            type=str,
            help="Validate specific region by code (e.g., CMR)",
        )
        parser.add_argument(
            "--report",
            action="store_true",
            help="Generate detailed report of all validations",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("\n🔍 Regional Configuration Validator\n"))
        self.stdout.write("=" * 60)

        # Get regions to validate
        regions = RegionConfig.objects.annotate(
            grading_scales_count=Count("gradingscaleconfig"),
            holidays_count=Count("holidays"),
        )

        if options["region"]:
            regions = regions.filter(code=options["region"])
            if not regions.exists():
                raise CommandError(f"Region '{options['region']}' not found")

        total_issues = 0
        validation_report = []

        for region in regions:
            issues = self._validate_region(region)
            total_issues += len(issues)

            if issues:
                self.stdout.write(
                    self.style.WARNING(f"\n❌ {region.code} - {region.name}")
                )
                for issue in issues:
                    self.stdout.write(f"  • {issue['message']}")
                    if options["fix"] and issue.get("fixable"):
                        self._fix_issue(region, issue, options)
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ {region.code} - {region.name} (All checks passed)"
                    )
                )

            validation_report.append(
                {
                    "region": region,
                    "issues": issues,
                }
            )

        # Summary
        self.stdout.write("\n" + "=" * 60)
        if total_issues == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ All {regions.count()} region(s) validated successfully!"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"✗ Found {total_issues} issue(s) across {regions.count()} region(s)"
                )
            )

        if options["report"]:
            self._generate_report(validation_report)

    def _validate_region(self, region):
        """Validate a single region."""
        issues = []

        # Check grading scales
        if region.gradingscaleconfig_set.count() < 5:
            issues.append(
                {
                    "code": "GRADING_SCALES_INCOMPLETE",
                    "message": f"Grading scales incomplete: {region.gradingscaleconfig_set.count()}/5",
                    "severity": "ERROR",
                    "fixable": False,
                }
            )

        # Check timezone
        try:
            pytz.timezone(region.timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            issues.append(
                {
                    "code": "INVALID_TIMEZONE",
                    "message": f"Invalid timezone: {region.timezone}",
                    "severity": "ERROR",
                    "fixable": False,
                }
            )

        # Check currency
        if not is_known_currency_code(region.default_currency):
            issues.append(
                {
                    "code": "UNKNOWN_CURRENCY",
                    "message": f"Unknown currency: {region.default_currency}",
                    "severity": "WARNING",
                    "fixable": False,
                }
            )

        # Check portal features
        portal_count = sum(
            [
                region.enable_online_admissions,
                region.enable_parent_portal,
                region.enable_student_portal,
            ]
        )
        if portal_count == 0:
            issues.append(
                {
                    "code": "NO_PORTALS",
                    "message": "No portal features enabled",
                    "severity": "INFO",
                    "fixable": True,
                }
            )

        # Check academic year configuration
        if (
            region.academic_year_start_month < 1
            or region.academic_year_start_month > 12
        ):
            issues.append(
                {
                    "code": "INVALID_YEAR_START",
                    "message": f"Invalid academic year start month: {region.academic_year_start_month}",
                    "severity": "ERROR",
                    "fixable": False,
                }
            )

        if region.term_count_per_year < 1 or region.term_count_per_year > 12:
            issues.append(
                {
                    "code": "INVALID_TERM_COUNT",
                    "message": f"Invalid term count: {region.term_count_per_year}",
                    "severity": "WARNING",
                    "fixable": False,
                }
            )

        return issues

    def _fix_issue(self, region, issue, options):
        """Attempt to fix a validation issue."""
        if issue["code"] == "NO_PORTALS":
            region.enable_student_portal = True
            region.save()
            self.stdout.write(f"      ✓ Fixed: Enabled student portal")

    def _generate_report(self, validation_report):
        """Generate a detailed validation report."""
        self.stdout.write(self.style.SUCCESS("\n\n📋 DETAILED VALIDATION REPORT\n"))
        self.stdout.write("=" * 60)

        for item in validation_report:
            region = item["region"]
            issues = item["issues"]

            self.stdout.write(f"\n{region.code} - {region.name}")
            self.stdout.write("-" * 40)

            # Region details
            self.stdout.write(f"Language:        {region.default_language}")
            self.stdout.write(f"Timezone:        {region.timezone}")
            self.stdout.write(f"Date Format:     {region.date_format}")
            self.stdout.write(f"Grading Scale:   {region.grading_scale}")
            self.stdout.write(f"Currency:        {region.default_currency}")
            self.stdout.write(
                f"Year Start:      Month {region.academic_year_start_month}"
            )
            self.stdout.write(f"Terms/Year:      {region.term_count_per_year}")

            # Portal status
            portals = []
            if region.enable_online_admissions:
                portals.append("Online Admissions")
            if region.enable_parent_portal:
                portals.append("Parent Portal")
            if region.enable_student_portal:
                portals.append("Student Portal")

            self.stdout.write(
                f"Portals:         {', '.join(portals) if portals else 'None'}"
            )

            # Scales count
            scales = region.gradingscaleconfig_set.count()
            self.stdout.write(f"Grading Scales:  {scales}/5")

            # Issues
            if issues:
                self.stdout.write(f"\nIssues ({len(issues)}):")
                for issue in issues:
                    icon = (
                        "❌"
                        if issue["severity"] == "ERROR"
                        else ("⚠️" if issue["severity"] == "WARNING" else "ℹ️")
                    )
                    self.stdout.write(f"  {icon} {issue['message']}")
            else:
                self.stdout.write(self.style.SUCCESS("\n✓ No issues found"))
