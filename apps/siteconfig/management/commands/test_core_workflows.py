"""
Management command to run core workflow regression tests with detailed output.
Usage: python manage.py test_core_workflows
"""
from django.core.management.base import BaseCommand
from django.test.runner import DiscoverRunner
import sys


class Command(BaseCommand):
    help = "Run Phase 7 core workflow regression tests"

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Verbose test output',
        )
        parser.add_argument(
            '--failfast',
            action='store_true',
            help='Stop on first test failure',
        )
        parser.add_argument(
            '--keepdb',
            action='store_true',
            help='Preserve and reuse the test database between runs.',
        )
        parser.add_argument(
            '--noinput',
            action='store_true',
            help='Run non-interactively.',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("\n" + "="*70))
        self.stdout.write(self.style.SUCCESS("Phase 7: Core Workflow Regression Tests"))
        self.stdout.write(self.style.SUCCESS("="*70 + "\n"))

        # Configure test runner
        test_runner = DiscoverRunner(
            verbosity=2 if options['verbose'] else 1,
            failfast=options['failfast'],
            keepdb=options['keepdb'],
            interactive=not options['noinput'],
        )

        # Run specific test module
        test_labels = ['apps.siteconfig.tests.test_phase7_regression']
        
        self.stdout.write("Running tests:\n")
        for label in test_labels:
            self.stdout.write(f"  • {label}")
        self.stdout.write("\n")

        # Execute tests
        failures = test_runner.run_tests(test_labels)

        # Report results
        self.stdout.write("\n" + "="*70)
        if failures == 0:
            self.stdout.write(self.style.SUCCESS("OK: All workflow tests passed."))
        else:
            self.stdout.write(self.style.ERROR(f"FAIL: {failures} test(s) failed."))
        self.stdout.write("="*70 + "\n")

        # Exit with appropriate code
        if failures:
            sys.exit(1)
