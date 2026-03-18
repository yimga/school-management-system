"""
Export regional configurations to JSON or CSV format.
Usage: python manage.py export_config --format json --output configs.json
"""

import csv
import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from apps.siteconfig.models import RegionConfig


class Command(BaseCommand):
    help = "Export regional configurations to JSON or CSV format"

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            type=str,
            choices=["json", "csv"],
            default="json",
            help="Export format (default: json)",
        )
        parser.add_argument(
            "--output",
            type=str,
            help="Output file path (default: configs_TIMESTAMP.{format})",
        )
        parser.add_argument(
            "--region",
            type=str,
            help="Export specific region by code",
        )
        parser.add_argument(
            "--include-scales",
            action="store_true",
            help="Include grading scales in export",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("\n📤 Regional Configuration Exporter\n"))

        # Get regions to export
        regions = RegionConfig.objects.all().order_by("code")
        if options["region"]:
            regions = regions.filter(code=options["region"])
            if not regions.exists():
                raise CommandError(f"Region '{options['region']}' not found")

        export_format = options["format"]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = options["output"] or f"configs_{timestamp}.{export_format}"

        self.stdout.write(f"Format:   {export_format.upper()}")
        self.stdout.write(f"Output:   {output_file}")
        self.stdout.write(f"Regions:  {regions.count()}")
        self.stdout.write("-" * 60)

        try:
            if export_format == "json":
                self._export_json(regions, output_file, options)
            elif export_format == "csv":
                self._export_csv(regions, output_file, options)
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Exported {regions.count()} region(s) to {output_file}\n"
                )
            )
        except (OSError, TypeError, ValueError, KeyError, DatabaseError) as e:
            raise CommandError(f"Error exporting configurations: {e}") from e

    def _export_json(self, regions, output_file, options):
        """Export configurations to JSON format."""
        data = {
            "export_timestamp": datetime.now().isoformat(),
            "format_version": "1.0",
            "regions": [],
        }

        for region in regions:
            region_data = {
                "code": region.code,
                "name": region.name,
                "default_language": region.default_language,
                "timezone": region.timezone,
                "date_format": region.date_format,
                "grading_scale": region.grading_scale,
                "default_currency": region.default_currency,
                "academic_year_start_month": region.academic_year_start_month,
                "term_count_per_year": region.term_count_per_year,
                "enable_online_admissions": region.enable_online_admissions,
                "enable_parent_portal": region.enable_parent_portal,
                "enable_student_portal": region.enable_student_portal,
            }

            # Include grading scales if requested
            if options["include_scales"]:
                region_data["grading_scales"] = []
                for scale in region.gradingscaleconfig_set.all():
                    region_data["grading_scales"].append(
                        {
                            "scale_type": scale.scale_type,
                            "min_score": str(scale.min_score),
                            "max_score": str(scale.max_score),
                            "grade_a_min": str(scale.grade_a_min),
                            "grade_b_min": str(scale.grade_b_min),
                            "grade_c_min": str(scale.grade_c_min),
                            "grade_d_min": str(scale.grade_d_min),
                            "grade_f_min": str(scale.grade_f_min),
                            "display_format": scale.display_format,
                        }
                    )

            data["regions"].append(region_data)

        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

    def _export_csv(self, regions, output_file, options):
        """Export configurations to CSV format."""
        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)

            # Header
            writer.writerow(
                [
                    "Code",
                    "Name",
                    "Language",
                    "Timezone",
                    "Date Format",
                    "Grading Scale",
                    "Currency",
                    "Year Start (Month)",
                    "Terms/Year",
                    "Admissions",
                    "Parent Portal",
                    "Student Portal",
                    "Grading Scales",
                ]
            )

            # Rows
            for region in regions:
                scales_count = region.gradingscaleconfig_set.count()
                writer.writerow(
                    [
                        region.code,
                        region.name,
                        region.default_language,
                        region.timezone,
                        region.date_format,
                        region.grading_scale,
                        region.default_currency,
                        region.academic_year_start_month,
                        region.term_count_per_year,
                        "Yes" if region.enable_online_admissions else "No",
                        "Yes" if region.enable_parent_portal else "No",
                        "Yes" if region.enable_student_portal else "No",
                        scales_count,
                    ]
                )
