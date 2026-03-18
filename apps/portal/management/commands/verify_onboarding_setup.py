"""
Management command to verify onboarding improvements are properly set up
Checks migrations, models, views, and templates
"""

from django.core.management.base import BaseCommand
from django.apps import apps
from django.conf import settings
from pathlib import Path


class Command(BaseCommand):
    help = "Verify that onboarding improvements are properly configured"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Verifying onboarding setup...\n"))

        issues = []
        warnings = []

        # 1. Check migration (§2.4 raw SQL wrapped in portal.onboarding_verification)
        self.stdout.write("1. Checking migrations...")
        from apps.portal.onboarding_verification import (
            check_siteconfig_migration_applied,
        )

        result = check_siteconfig_migration_applied(
            "siteconfig", "0043_sitesettings_admission_number_config"
        )
        if result is True:
            self.stdout.write(self.style.SUCCESS("  ✓ Migration 0043 applied"))
        elif result is False:
            issues.append(
                "Migration 0043 not applied. Run: python manage.py migrate siteconfig"
            )
            self.stdout.write(self.style.WARNING("  ✗ Migration 0043 not found"))
        else:
            warnings.append("Could not check migrations (DB error); see logs")
            self.stdout.write(self.style.WARNING("  ⚠ Could not verify migration"))

        # 2. Check SiteSettings model
        self.stdout.write("\n2. Checking SiteSettings model...")
        try:
            SiteSettings = apps.get_model("siteconfig", "SiteSettings")
            if hasattr(SiteSettings, "admission_number_mode"):
                self.stdout.write(
                    self.style.SUCCESS("  ✓ admission_number_mode field exists")
                )
            else:
                issues.append("SiteSettings missing admission_number_mode field")
                self.stdout.write(
                    self.style.ERROR("  ✗ admission_number_mode field missing")
                )

            if hasattr(SiteSettings, "admission_number_pattern"):
                self.stdout.write(
                    self.style.SUCCESS("  ✓ admission_number_pattern field exists")
                )
            else:
                issues.append("SiteSettings missing admission_number_pattern field")
                self.stdout.write(
                    self.style.ERROR("  ✗ admission_number_pattern field missing")
                )
        except LookupError as e:
            issues.append(f"Error checking SiteSettings: {e}")
            self.stdout.write(self.style.ERROR(f"  ✗ Error: {e}"))

        # 3. Check StudentProfile model
        self.stdout.write("\n3. Checking StudentProfile model...")
        try:
            StudentProfile = apps.get_model("people", "StudentProfile")
            # Check if save method has admission number logic
            import inspect

            save_source = inspect.getsource(StudentProfile.save)
            if "admission_number_mode" in save_source:
                self.stdout.write(
                    self.style.SUCCESS(
                        "  ✓ StudentProfile.save() includes admission number logic"
                    )
                )
            else:
                warnings.append(
                    "StudentProfile.save() may not have admission number logic"
                )
                self.stdout.write(
                    self.style.WARNING(
                        "  ⚠ Could not verify StudentProfile.save() logic"
                    )
                )
        except (LookupError, OSError, TypeError) as e:
            warnings.append(f"Could not check StudentProfile: {e}")
            self.stdout.write(self.style.WARNING(f"  ⚠ Could not verify: {e}"))

        # 4. Check views
        self.stdout.write("\n4. Checking views...")
        try:
            from apps.portal import views

            if hasattr(views, "link_child_wizard"):
                self.stdout.write(
                    self.style.SUCCESS("  ✓ link_child_wizard view exists")
                )
            else:
                issues.append("link_child_wizard view missing")
                self.stdout.write(
                    self.style.ERROR("  ✗ link_child_wizard view missing")
                )

            if hasattr(views, "parent_onboarding_score"):
                self.stdout.write(
                    self.style.SUCCESS("  ✓ parent_onboarding_score function exists")
                )
            else:
                # Check services
                from apps.portal import services

                if hasattr(services, "parent_onboarding_score"):
                    self.stdout.write(
                        self.style.SUCCESS(
                            "  ✓ parent_onboarding_score function exists"
                        )
                    )
                else:
                    issues.append("parent_onboarding_score function missing")
                    self.stdout.write(
                        self.style.ERROR("  ✗ parent_onboarding_score function missing")
                    )
        except ImportError as e:
            issues.append(f"Error checking views: {e}")
            self.stdout.write(self.style.ERROR(f"  ✗ Error: {e}"))

        # 5. Check templates
        self.stdout.write("\n5. Checking templates...")
        base_dir = Path(settings.BASE_DIR)
        wizard_template = base_dir / "templates" / "parent" / "link_child_wizard.html"
        if wizard_template.exists():
            self.stdout.write(
                self.style.SUCCESS("  ✓ link_child_wizard.html template exists")
            )
        else:
            issues.append("link_child_wizard.html template missing")
            self.stdout.write(
                self.style.ERROR("  ✗ link_child_wizard.html template missing")
            )

        dashboard_template = base_dir / "templates" / "parent" / "dashboard.html"
        if dashboard_template.exists():
            # Check if it has onboarding content
            dashboard_content = dashboard_template.read_text()
            if "onboarding" in dashboard_content or "Get Started" in dashboard_content:
                self.stdout.write(
                    self.style.SUCCESS("  ✓ dashboard.html includes onboarding content")
                )
            else:
                warnings.append("dashboard.html may not have onboarding content")
                self.stdout.write(
                    self.style.WARNING(
                        "  ⚠ dashboard.html may not have onboarding content"
                    )
                )
        else:
            warnings.append("dashboard.html not found")
            self.stdout.write(self.style.WARNING("  ⚠ dashboard.html not found"))

        # 6. Check URLs
        self.stdout.write("\n6. Checking URLs...")
        try:
            from django.urls import reverse, NoReverseMatch

            try:
                url = reverse("portal:link_child")
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ link_child URL configured: {url}")
                )
            except NoReverseMatch:
                issues.append("link_child URL not configured")
                self.stdout.write(self.style.ERROR("  ✗ link_child URL not found"))
        except ImportError as e:
            warnings.append(f"Could not check URLs: {e}")
            self.stdout.write(self.style.WARNING(f"  ⚠ Could not verify URLs: {e}"))

        # 7. Check sessions configuration
        self.stdout.write("\n7. Checking session configuration...")
        if (
            hasattr(settings, "SESSION_SAVE_EVERY_REQUEST")
            and settings.SESSION_SAVE_EVERY_REQUEST
        ):
            self.stdout.write(
                self.style.SUCCESS("  ✓ SESSION_SAVE_EVERY_REQUEST is enabled")
            )
        else:
            warnings.append(
                "SESSION_SAVE_EVERY_REQUEST not enabled (wizard may not persist data)"
            )
            self.stdout.write(
                self.style.WARNING("  ⚠ SESSION_SAVE_EVERY_REQUEST not enabled")
            )

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("SUMMARY")
        self.stdout.write("=" * 60)

        if not issues and not warnings:
            self.stdout.write(
                self.style.SUCCESS(
                    "\n✅ All checks passed! Onboarding is ready for testing."
                )
            )
        else:
            if issues:
                self.stdout.write(
                    self.style.ERROR(f"\n❌ Found {len(issues)} critical issue(s):")
                )
                for issue in issues:
                    self.stdout.write(self.style.ERROR(f"  • {issue}"))

            if warnings:
                self.stdout.write(
                    self.style.WARNING(f"\n⚠️  Found {len(warnings)} warning(s):")
                )
                for warning in warnings:
                    self.stdout.write(self.style.WARNING(f"  • {warning}"))

            if issues:
                self.stdout.write(
                    "\n"
                    + self.style.ERROR("Please fix the issues above before testing.")
                )
            else:
                self.stdout.write(
                    "\n"
                    + self.style.SUCCESS(
                        "Warnings only - you can proceed with testing, but review warnings."
                    )
                )

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("\nNext steps:")
        self.stdout.write(
            "  1. Run migration if needed: python manage.py migrate siteconfig"
        )
        self.stdout.write("  2. Start server: python manage.py runserver")
        self.stdout.write(
            "  3. Test wizard: Navigate to /parent/link-child/ as a parent user"
        )
        self.stdout.write(
            "  4. Check dashboard: Verify onboarding progress indicator appears"
        )
        self.stdout.write("")
