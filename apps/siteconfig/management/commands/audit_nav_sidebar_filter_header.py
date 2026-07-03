from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


TOOLBAR = "templates/partials/rmc_nav_sidebar_toolbar.html"
SIDEBAR_CSS = "static/css/rmc-nav-sidebar.css"
SIDEBAR_JS = "static/js/rmc-nav-sidebar.js"
SHELLS = {
    "control_plane": "templates/control_plane_base.html",
    "portal": "templates/portal_base.html",
    "manager_admin": "templates/admin/base.html",
    "zero_ticket": "templates/siteconfig/zero_ticket_shell.html",
}
NAV_PARTIALS = {
    "operator": "templates/partials/control_plane_sidebar.html",
    "tenant": "templates/partials/portal_sidebar.html",
    "manager_admin": "templates/partials/manager_platform_admin_sidebar.html",
}
EXTENDS_RE = re.compile(r"{%\s*extends\s+['\"]([^'\"]+)['\"]")


class Command(BaseCommand):
    help = "Audit platform-wide nav-sidebar filter header coverage and writes generated gap reports."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="docs/generated",
            help="Directory for generated audit reports.",
        )

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR)
        output_dir = root / options["output_dir"]
        output_dir.mkdir(parents=True, exist_ok=True)

        report = {
            "scope": "shared desktop nav sidebar toolbar used by operator, manager-admin, zero-ticket, and tenant shells",
            "toolbar": self._audit_toolbar(root),
            "css": self._audit_css(root),
            "javascript": self._audit_js(root),
            "shell_mounts": self._audit_shell_mounts(root),
            "nav_partials": self._audit_nav_partials(root),
            "template_inheritance": self._audit_template_inheritance(root),
        }
        report["summary"] = self._summarize(report)

        json_path = output_dir / "runmycampus_nav_sidebar_filter_header_audit.json"
        md_path = output_dir / "runmycampus_nav_sidebar_filter_header_audit.md"
        gap_path = output_dir / "runmycampus_nav_sidebar_filter_header_gap_analysis.md"
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        md = self._render_markdown(report)
        md_path.write_text(md, encoding="utf-8")
        gap_path.write_text(self._render_gap_analysis(report), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Wrote {json_path}"))
        self.stdout.write(self.style.SUCCESS(f"Wrote {md_path}"))
        self.stdout.write(self.style.SUCCESS(f"Wrote {gap_path}"))
        if report["summary"]["gap_count"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Nav sidebar filter-header audit completed with {report['summary']['gap_count']} gaps."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Nav sidebar filter-header audit found no gaps."))

    def _read(self, root: Path, rel: str) -> str:
        path = root / rel
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    def _audit_toolbar(self, root: Path) -> dict:
        text = self._read(root, TOOLBAR)
        order = {
            "toggle": text.find("rmc-nav-sidebar__toggle"),
            "filter": text.find("data-rmc-sidebar-filter-input"),
            "label": text.find("rmc-nav-sidebar__toggle-label"),
        }
        return {
            "path": TOOLBAR,
            "exists": bool(text),
            "has_filter_input": "data-rmc-sidebar-filter-input" in text,
            "has_filter_placeholder": "Filter..." in text,
            "has_filter_aria_label": "Filter navigation" in text,
            "keeps_navigation_label": "rmc-nav-sidebar__toggle-label" in text,
            "filter_between_toggle_and_label": order["toggle"] >= 0
            and order["toggle"] < order["filter"] < order["label"],
            "order": order,
        }

    def _audit_css(self, root: Path) -> dict:
        text = self._read(root, SIDEBAR_CSS)
        required = {
            "toolbar_grid": "grid-template-columns: 2rem minmax(0, 1fr) auto" in text,
            "filter_styles": ".rmc-nav-sidebar__filter" in text,
            "filter_input_styles": ".rmc-nav-sidebar__filter-input" in text,
            "rail_hides_operator_filter": "#cp-sidebar-col.rmc-nav-sidebar--rail .rmc-nav-sidebar__filter" in text,
            "rail_hides_tenant_filter": "#portal-sidebar-col.rmc-nav-sidebar--rail .rmc-nav-sidebar__filter" in text,
            "rail_hides_app_shell_filter": '.rmc-app-shell[data-rmc-nav-sidebar="rail"] .rmc-nav-sidebar__filter' in text,
        }
        return {"path": SIDEBAR_CSS, "exists": bool(text), **required}

    def _audit_js(self, root: Path) -> dict:
        text = self._read(root, SIDEBAR_JS)
        required = {
            "binds_filter": "bindSidebarFilter(shell)" in text,
            "finds_filter_input": "[data-rmc-sidebar-filter-input]" in text,
            "filters_operator_items": ".cp-sidebar__item" in text,
            "filters_tenant_items": ".nav-link" in text,
            "filters_admin_items": ".admin-sidebar-link" in text,
            "slash_focus": 'event.key !== "/"' in text,
        }
        return {"path": SIDEBAR_JS, "exists": bool(text), **required}

    def _audit_shell_mounts(self, root: Path) -> dict:
        rows = {}
        for name, rel in SHELLS.items():
            text = self._read(root, rel)
            rows[name] = {
                "path": rel,
                "exists": bool(text),
                "includes_toolbar": "rmc_nav_sidebar_toolbar.html" in text,
                "has_desktop_mount": "data-shell-sidebar-mount=\"desktop\"" in text
                or "data-shell-sidebar-mount='desktop'" in text,
            }
        return rows

    def _audit_nav_partials(self, root: Path) -> dict:
        rows = {}
        for name, rel in NAV_PARTIALS.items():
            text = self._read(root, rel)
            rows[name] = {
                "path": rel,
                "exists": bool(text),
                "has_sidebar_nav": "data-sidebar-nav" in text,
                "has_filter_contract": "data-rmc-sidebar-search" in text
                or name == "manager_admin",
            }
        return rows

    def _audit_template_inheritance(self, root: Path) -> dict:
        template_root = root / "templates"
        shell_counts: dict[str, int] = {}
        toolbar_include_templates = []
        for path in sorted(template_root.rglob("*.html")):
            rel = path.relative_to(template_root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            match = EXTENDS_RE.search(text)
            if match:
                shell = match.group(1)
                shell_counts[shell] = shell_counts.get(shell, 0) + 1
            if "rmc_nav_sidebar_toolbar.html" in text:
                toolbar_include_templates.append(rel)
        authenticated_shells = {
            "portal_base.html": shell_counts.get("portal_base.html", 0),
            "control_plane_base.html": shell_counts.get("control_plane_base.html", 0),
            "admin/base.html": shell_counts.get("admin/base.html", 0),
        }
        return {
            "authenticated_shell_extends": authenticated_shells,
            "toolbar_include_templates": toolbar_include_templates,
            "toolbar_include_count": len(toolbar_include_templates),
        }

    def _summarize(self, report: dict) -> dict:
        gaps = []
        for section in ("toolbar", "css", "javascript"):
            for key, value in report[section].items():
                if key in {"path", "order"}:
                    continue
                if value is not True:
                    gaps.append({"section": section, "check": key, "value": value})
        for section in ("shell_mounts", "nav_partials"):
            for name, row in report[section].items():
                for key, value in row.items():
                    if key == "path":
                        continue
                    if value is not True:
                        gaps.append({"section": section, "surface": name, "check": key, "value": value})
        return {
            "gap_count": len(gaps),
            "gaps": gaps,
            "toolbar_include_count": report["template_inheritance"]["toolbar_include_count"],
            "authenticated_shell_extends": report["template_inheritance"]["authenticated_shell_extends"],
        }

    def _render_markdown(self, report: dict) -> str:
        summary = report["summary"]
        lines = [
            "# RunMyCampus Nav Sidebar Filter Header Audit",
            "",
            f"- Scope: {report['scope']}",
            f"- Gap count: {summary['gap_count']}",
            f"- Toolbar include templates: {summary['toolbar_include_count']}",
            "",
            "## Authenticated Shell Coverage",
        ]
        for shell, count in summary["authenticated_shell_extends"].items():
            lines.append(f"- `{shell}`: {count} templates extend this shell")
        lines.extend(["", "## Shell Mounts"])
        for name, row in report["shell_mounts"].items():
            status = "PASS" if all(v is True for k, v in row.items() if k != "path") else "GAP"
            lines.append(f"- {status}: `{name}` via `{row['path']}`")
        lines.extend(["", "## Nav Partials"])
        for name, row in report["nav_partials"].items():
            status = "PASS" if all(v is True for k, v in row.items() if k != "path") else "GAP"
            lines.append(f"- {status}: `{name}` via `{row['path']}`")
        if summary["gaps"]:
            lines.extend(["", "## Gaps"])
            for gap in summary["gaps"]:
                lines.append(f"- `{gap}`")
        return "\n".join(lines) + "\n"

    def _render_gap_analysis(self, report: dict) -> str:
        summary = report["summary"]
        lines = [
            "# RunMyCampus Nav Sidebar Filter Header Gap Analysis",
            "",
            f"- Code-owned gaps found: {summary['gap_count']}",
            f"- Shared toolbar source: `{TOOLBAR}`",
            f"- Shared CSS source: `{SIDEBAR_CSS}`",
            f"- Shared JS source: `{SIDEBAR_JS}`",
            "",
            "## Result",
        ]
        if summary["gap_count"]:
            lines.append("The audit found gaps that must be closed before this can be called complete.")
        else:
            lines.append(
                "No code-owned gaps were found for desktop sidebar surfaces that use the shared nav-sidebar toolbar."
            )
        lines.extend(
            [
                "",
                "## Coverage",
                "- Operator control-plane pages inherit the toolbar through `control_plane_base.html`.",
                "- Tenant pages inherit the toolbar through `portal_base.html`.",
                "- Manager `/admin/` pages inherit the toolbar through `templates/admin/base.html` when on the manager host.",
                "- Zero-ticket diagnostic pages inherit the toolbar through `templates/siteconfig/zero_ticket_shell.html`.",
                "- Mobile offcanvas menus are outside this request because they do not have the collapse-icon/Navigation header slot.",
                "",
                "## Measurements",
            ]
        )
        for shell, count in summary["authenticated_shell_extends"].items():
            lines.append(f"- `{shell}` extending templates: {count}")
        lines.append(f"- Toolbar include templates: {summary['toolbar_include_count']}")
        if summary["gaps"]:
            lines.extend(["", "## Open Gaps"])
            for gap in summary["gaps"]:
                lines.append(f"- `{gap}`")
        return "\n".join(lines) + "\n"
