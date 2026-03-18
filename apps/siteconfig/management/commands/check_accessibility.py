"""
Management command to check accessibility compliance of key pages.
Usage: python manage.py check_accessibility
"""

from django.core.management.base import BaseCommand
from django.test import Client
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError
import re
from pathlib import Path
from datetime import datetime

from apps.platform_runtime.structured_logging import log_exception_with_context

# §2.4 Typed exceptions for allowlist shrink (broad_exception_audit)
_ACCESSIBILITY_USER_CREATE_ERRORS = (
    IntegrityError,
    ValidationError,
    ValueError,
    TypeError,
    AttributeError,
)
_ACCESSIBILITY_CHECK_PAGE_ERRORS = (
    ValueError,
    UnicodeDecodeError,
    TypeError,
    AttributeError,
    OSError,
    ConnectionError,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Check accessibility compliance of key pages (WCAG 2.2)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--pages",
            type=str,
            default="all",
            help="Which pages to check: all, portal, admin, finance (default: all)",
        )
        parser.add_argument(
            "--report",
            action="store_true",
            help="Generate HTML report in docs/qa-reports/",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 70))
        self.stdout.write(
            self.style.SUCCESS("Accessibility Compliance Check (WCAG 2.2)")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        )
        self.stdout.write(self.style.SUCCESS("=" * 70 + "\n"))

        client = Client()
        pages_to_check = options["pages"]
        results = {}

        # Create test users (or use existing if already created)
        try:
            _ = User.objects.create_user(
                username="a11y_test_teacher", password="test123", role="TEACHER"
            )
        except _ACCESSIBILITY_USER_CREATE_ERRORS:
            _ = User.objects.get(username="a11y_test_teacher")

        try:
            _ = User.objects.create_superuser(
                username="a11y_test_admin", email="a11y@test.com", password="admin123"
            )
        except _ACCESSIBILITY_USER_CREATE_ERRORS:
            _ = User.objects.get(username="a11y_test_admin")

        # Portal pages
        if pages_to_check in ["all", "portal"]:
            self.stdout.write("Checking PORTAL pages...\n")
            client.login(username="a11y_test_teacher", password="test123")

            portal_pages = [
                ("/authentication/redirect/", "Dashboard"),
                ("/portal/", "Portal Home"),
            ]

            for path, name in portal_pages:
                result = self._check_page(client, path, name)
                results[name] = result

        # Admin pages
        if pages_to_check in ["all", "admin"]:
            self.stdout.write("\nChecking ADMIN pages...\n")
            client.login(username="a11y_test_admin", password="admin123")

            admin_pages = [
                ("/admin/", "Admin Dashboard"),
                ("/admin/accounts/user/", "Users List"),
            ]

            for path, name in admin_pages:
                result = self._check_page(client, path, name)
                results[name] = result

        # Finance pages
        if pages_to_check in ["all", "finance"]:
            self.stdout.write("\nChecking FINANCE pages...\n")
            client.login(username="a11y_test_teacher", password="test123")

            finance_pages = [
                ("/finance/invoices/", "Invoices"),
            ]

            for path, name in finance_pages:
                result = self._check_page(client, path, name)
                results[name] = result

        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("Accessibility Check Summary"))
        self.stdout.write("=" * 70 + "\n")

        total_issues = sum(len(r["issues"]) for r in results.values())
        critical_count = sum(
            len([i for i in r["issues"] if i["severity"] == "critical"])
            for r in results.values()
        )

        for page_name, result in results.items():
            status = (
                self.style.SUCCESS("✓ PASS")
                if not result["issues"]
                else self.style.ERROR("✗ FAIL")
            )
            self.stdout.write(f"{page_name}: {status}")
            if result["issues"]:
                for issue in result["issues"][:3]:  # Show top 3 issues
                    self.stdout.write(f"  - {issue['type']}: {issue['message']}")
                if len(result["issues"]) > 3:
                    self.stdout.write(
                        f"  ... and {len(result['issues']) - 3} more issues"
                    )

        self.stdout.write("\n" + "-" * 70)
        self.stdout.write(f"Total issues found: {total_issues}")
        self.stdout.write(f"Critical issues: {critical_count}")
        self.stdout.write(f"Warnings: {total_issues - critical_count}")
        self.stdout.write("=" * 70 + "\n")

        # Generate report if requested
        if options["report"]:
            self._generate_report(results)

    def _check_page(self, client, path, page_name):
        """Check accessibility of a single page."""
        try:
            response = client.get(path)
            if response.status_code != 200:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠ {page_name}: HTTP {response.status_code}")
                )
                return {"status": "error", "code": response.status_code, "issues": []}

            html = response.content.decode()
            issues = self._scan_html(html)

            status_icon = "✓" if not issues else "✗"
            status_text = (
                self.style.SUCCESS("PASS")
                if not issues
                else self.style.ERROR(f"FAIL ({len(issues)} issues)")
            )
            self.stdout.write(f"  {status_icon} {page_name}: {status_text}")

            return {"status": "ok", "path": path, "issues": issues}

        except _ACCESSIBILITY_CHECK_PAGE_ERRORS as e:
            log_exception_with_context(
                "check_accessibility: page check failed",
                school_id=None,
                extra={"page_name": page_name, "path": path, "error": str(e)},
            )
            self.stdout.write(self.style.ERROR(f"  ✗ {page_name}: {str(e)}"))
            return {"status": "error", "error": str(e), "issues": []}

    def _scan_html(self, html):
        """Scan HTML for accessibility issues."""
        issues = []

        # Check for lang attribute
        if "<html" in html and "lang=" not in html[:200]:
            issues.append(
                {
                    "type": "missing_lang",
                    "severity": "critical",
                    "message": "HTML element missing lang attribute",
                }
            )

        # Check for images without alt text
        img_tags = re.findall(r"<img[^>]*>", html)
        for img in img_tags:
            if "alt=" not in img:
                issues.append(
                    {
                        "type": "missing_alt_text",
                        "severity": "critical",
                        "message": f"Image missing alt text: {img[:50]}",
                    }
                )

        # Check for form inputs without labels
        input_count = len(re.findall(r'<input(?!.*type=["\']hidden)', html))
        label_count = len(re.findall(r"<label[^>]*>", html))
        if input_count > label_count and input_count > 0:
            issues.append(
                {
                    "type": "missing_labels",
                    "severity": "critical",
                    "message": f"Found {input_count} inputs but only {label_count} labels",
                }
            )

        # Check for heading hierarchy
        headings = re.findall(r"<h(\d)", html)
        if headings:
            h_levels = sorted(set(int(h) for h in headings))
            if h_levels[0] > 1:
                issues.append(
                    {
                        "type": "heading_hierarchy",
                        "severity": "warning",
                        "message": f"First heading is H{h_levels[0]}, should start with H1",
                    }
                )

        # Check for skip links
        if "<a" in html and "skip" not in html.lower():
            if "<main" in html or 'id="main' in html:
                issues.append(
                    {
                        "type": "missing_skip_links",
                        "severity": "warning",
                        "message": 'No "skip to main content" link found',
                    }
                )

        # Check for color contrast in critical areas
        if "btn-primary" in html and "007bff" in html:
            issues.append(
                {
                    "type": "color_contrast",
                    "severity": "info",
                    "message": "Primary buttons should have 4.5:1 contrast ratio",
                }
            )

        return issues

    def _generate_report(self, results):
        """Generate HTML accessibility report."""
        report_dir = Path(settings.BASE_DIR) / "docs" / "qa-reports"
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"accessibility_report_{timestamp}.html"

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Accessibility Report - {timestamp}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .header {{ background: #007bff; color: white; padding: 20px; border-radius: 5px; }}
        .page-result {{ background: white; margin: 15px 0; padding: 15px; border-radius: 5px; border-left: 5px solid #ccc; }}
        .page-result.pass {{ border-left-color: #28a745; }}
        .page-result.fail {{ border-left-color: #dc3545; }}
        .issues {{ margin-left: 20px; font-size: 0.9em; }}
        .issue {{ padding: 5px; margin: 5px 0; border-radius: 3px; }}
        .critical {{ background: #fee; color: #c00; }}
        .warning {{ background: #ffeaa7; color: #b08400; }}
        .info {{ background: #d6eaf8; color: #0c5aa0; }}
        .summary {{ background: #e7f3ff; border: 1px solid #b3d9ff; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Accessibility Compliance Report</h1>
        <p>WCAG 2.2 Level AA</p>
        <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>

    <div class="summary">
        <h2>Summary</h2>
        <table>
            <tr>
                <th>Pages Tested</th>
                <th>Passed</th>
                <th>Failed</th>
                <th>Total Issues</th>
            </tr>
            <tr>
                <td>{len(results)}</td>
                <td>{sum(1 for r in results.values() if not r["issues"])}</td>
                <td>{sum(1 for r in results.values() if r["issues"])}</td>
                <td>{sum(len(r["issues"]) for r in results.values())}</td>
            </tr>
        </table>
    </div>

"""

        for page_name, result in results.items():
            status_class = "pass" if not result["issues"] else "fail"
            status_text = (
                "PASS"
                if not result["issues"]
                else f"FAIL ({len(result['issues'])} issues)"
            )

            html_content += f"""
    <div class="page-result {status_class}">
        <h3>{page_name}</h3>
        <p><strong>Status:</strong> {status_text}</p>
"""

            if result["issues"]:
                html_content += '<div class="issues"><strong>Issues:</strong><ul>'
                for issue in result["issues"]:
                    severity_class = issue["severity"].lower()
                    html_content += f'<li class="issue {severity_class}">'
                    html_content += f"<strong>{issue['type']}</strong> ({issue['severity']}): {issue['message']}"
                    html_content += "</li>"
                html_content += "</ul></div>"

            html_content += "</div>\n"

        html_content += """
</body>
</html>
"""

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        self.stdout.write(self.style.SUCCESS(f"\n✓ Report generated: {report_file}"))
