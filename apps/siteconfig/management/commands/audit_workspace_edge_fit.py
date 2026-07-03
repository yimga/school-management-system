from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, reverse


EDGE_FIT_CSS = "css/rmc-platform-workspace-edge-fit.css"
KNOWN_AUTH_SHELLS = {
    "control_plane_base.html",
    "portal_base.html",
    "backend_base.html",
    "backend_base_manager.html",
    "backend_base_tenant.html",
    "admin/base.html",
    "admin/base_site.html",
    "studio_os/shell.html",
}
IGNORED_TEMPLATE_PREFIXES = (
    "admin/",
    "emails/",
    "errors/",
    "registration/",
    "unfold/",
)
IGNORED_TEMPLATE_PARTS = (
    "/partials/",
    "/components/",
    "/widgets/",
    "/includes/",
)
URL_TAG_FULL_RE = re.compile(r"{%\s*url\s+['\"]([^'\"]+)['\"]([^%]*)%}")
EXTENDS_RE = re.compile(r"{%\s*extends\s+['\"]([^'\"]+)['\"]")


@dataclass
class DummyUser:
    is_authenticated: bool = True
    is_staff: bool = True
    is_superuser: bool = True
    role: str = "ADMIN"

    def has_perm(self, _perm: str) -> bool:
        return True

    def has_module_perms(self, _app_label: str) -> bool:
        return True


class Command(BaseCommand):
    help = (
        "Audit manager and tenant workspace edge-fit coverage, menu targets, "
        "and template shell inheritance. Writes JSON and Markdown reports."
    )

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
            "edge_fit_css": EDGE_FIT_CSS,
            "shell_loads": self._audit_shell_loads(root),
            "css_contract": self._audit_css_contract(root),
            "templates": self._audit_templates(root),
            "menu_targets": self._audit_menu_targets(root),
        }
        report["summary"] = self._summarize(report)

        json_path = output_dir / "runmycampus_workspace_edge_fit_audit.json"
        md_path = output_dir / "runmycampus_workspace_edge_fit_audit.md"
        gap_path = output_dir / "runmycampus_workspace_edge_fit_gap_analysis.md"
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        md_path.write_text(self._render_markdown(report), encoding="utf-8")
        gap_path.write_text(self._render_gap_analysis(report), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Wrote {json_path}"))
        self.stdout.write(self.style.SUCCESS(f"Wrote {md_path}"))
        self.stdout.write(self.style.SUCCESS(f"Wrote {gap_path}"))
        if report["summary"]["gap_count"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Workspace edge-fit audit completed with {report['summary']['gap_count']} gaps."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Workspace edge-fit audit found no gaps."))

    def _audit_shell_loads(self, root: Path) -> dict:
        shells = {
            "manager_shell": "templates/control_plane_base.html",
            "portal_shell": "templates/portal_base.html",
            "manager_admin_shell": "templates/admin/base_site.html",
        }
        results = {}
        for key, rel in shells.items():
            path = root / rel
            text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
            results[key] = {
                "path": rel,
                "exists": path.exists(),
                "loads_edge_fit_css": EDGE_FIT_CSS in text,
            }
        return results

    def _audit_css_contract(self, root: Path) -> dict:
        rel = f"static/{EDGE_FIT_CSS}"
        path = root / rel
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        return {
            "path": rel,
            "exists": path.exists(),
            "control_plane_body_scope": "body.control-plane-shell" in text,
            "tenant_portal_scope": "body.portal-body-with-layout:not(.control-plane-shell)" in text,
            "manager_admin_scope": ".rmc-app-shell.admin-manager-shell.control-plane-shell" in text,
            "removes_centered_caps": "max-inline-size: none !important" in text,
        }

    def _audit_templates(self, root: Path) -> dict:
        template_root = root / "templates"
        all_pages = []
        outside_scope = []
        shared_bases = []
        gaps = []
        shell_counts: dict[str, int] = {}
        for path in sorted(template_root.rglob("*.html")):
            rel = path.relative_to(template_root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            extends = self._first_match(EXTENDS_RE, text)
            if extends:
                shell_counts[extends] = shell_counts.get(extends, 0) + 1
            classification = self._classify_template_scope(rel, text, extends)
            if classification == "shared-base":
                shared_bases.append({"template": rel, "extends": extends})
                continue
            if classification == "outside":
                if extends and extends not in KNOWN_AUTH_SHELLS:
                    outside_scope.append({"template": rel, "extends": extends})
                continue
            row = {
                "template": rel,
                "extends": extends,
                "known_shell": extends in KNOWN_AUTH_SHELLS,
                "classification": classification,
            }
            all_pages.append(row)
            if not row["known_shell"]:
                gaps.append(row)
        return {
            "authenticated_page_like_count": len(all_pages),
            "shared_base_count": len(shared_bases),
            "shared_bases": shared_bases,
            "outside_edge_fit_scope_count": len(outside_scope),
            "outside_edge_fit_scope_samples": outside_scope[:100],
            "known_shell_counts": shell_counts,
            "candidate_shell_gaps": gaps,
        }

    def _audit_menu_targets(self, root: Path) -> dict:
        manager = self._audit_manager_nav()
        tenant = self._audit_template_url_tags(
            root,
            [
                "templates/partials/portal_sidebar.html",
                "templates/partials/tenant_primary_nav.html",
            ],
            preferred_urlconf=getattr(settings, "TENANT_SCHEMA_URLCONF", None),
        )
        return {
            "manager": manager,
            "tenant": tenant,
        }

    def _audit_manager_nav(self) -> dict:
        request = SimpleNamespace(
            path="/super/",
            urlconf="config.manager_urls",
            user=DummyUser(),
            public_host_kind="manager",
        )
        groups = []
        errors = []
        try:
            from apps.schools.manager_nav_convergence import (
                build_manager_complete_sidebar_groups,
            )

            groups = build_manager_complete_sidebar_groups(request)
        except Exception as exc:  # pragma: no cover - audit must report, not crash
            errors.append(f"build_manager_complete_sidebar_groups: {exc}")

        items = []
        for group in groups:
            for item in group.get("items") or []:
                items.append(
                    {
                        "group": group.get("label"),
                        "id": item.get("id"),
                        "label": str(item.get("label") or ""),
                        "url": item.get("url"),
                    }
                )
        return {
            "group_count": len(groups),
            "item_count": len(items),
            "items_without_url": [row for row in items if not row.get("url")],
            "errors": errors,
        }

    def _audit_template_url_tags(
        self, root: Path, rel_paths: list[str], *, preferred_urlconf: str | None
    ) -> dict:
        names: dict[str, dict] = {}
        for rel in rel_paths:
            path = root / rel
            text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
            for name, suffix in URL_TAG_FULL_RE.findall(text):
                entry = names.setdefault(
                    name, {"sources": set(), "has_template_args": False}
                )
                entry["sources"].add(rel)
                if suffix.strip():
                    entry["has_template_args"] = True

        urlconfs = [preferred_urlconf, settings.ROOT_URLCONF]
        if "config.manager_urls" not in urlconfs:
            urlconfs.append("config.manager_urls")
        urlconfs = [u for u in urlconfs if u]

        rows = []
        for name, meta in sorted(names.items()):
            resolved = self._resolve_name(
                name, urlconfs, has_template_args=meta["has_template_args"]
            )
            rows.append(
                {
                    "name": name,
                    "sources": sorted(meta["sources"]),
                    "has_template_args": meta["has_template_args"],
                    "resolved": bool(resolved),
                    "urlconf": resolved.get("urlconf") if resolved else None,
                    "url": resolved.get("url") if resolved else None,
                    "dynamic_args_required": bool(
                        resolved.get("dynamic_args_required") if resolved else False
                    ),
                }
            )
        return {
            "source_templates": rel_paths,
            "url_name_count": len(rows),
            "unresolved": [row for row in rows if not row["resolved"]],
            "targets": rows,
        }

    def _resolve_name(
        self, name: str, urlconfs: list[str], *, has_template_args: bool
    ) -> dict | None:
        for urlconf in urlconfs:
            try:
                url = reverse(name, urlconf=urlconf)
                return {"urlconf": urlconf, "url": url}
            except NoReverseMatch:
                if has_template_args:
                    return {
                        "urlconf": urlconf,
                        "url": None,
                        "dynamic_args_required": True,
                    }
                continue
            except TypeError:
                if has_template_args:
                    return {
                        "urlconf": urlconf,
                        "url": None,
                        "dynamic_args_required": True,
                    }
                continue
            except Exception:
                continue
        return None

    def _classify_template_scope(
        self, rel: str, text: str, extends: str | None
    ) -> str:
        if rel.startswith(IGNORED_TEMPLATE_PREFIXES):
            return "outside"
        if any(part in f"/{rel}" for part in IGNORED_TEMPLATE_PARTS):
            return "outside"
        if rel in {
            "backend_base.html",
            "control_plane_base.html",
            "portal_base.html",
            "base.html",
        }:
            return "shared-base"
        if not extends:
            return "outside"
        if extends in KNOWN_AUTH_SHELLS:
            return "shared-shell"
        if self._is_public_or_minimal(rel, extends):
            return "outside"
        shell_signals = (
            "portal-sidebar-col",
            "cp-sidebar-col",
            "rmc-app-shell__canvas-body",
            "data-rmc-authenticated-shell",
            "data-authenticated-surface",
            "data-rmc-cp-page-body",
            "data-rmc-portal-page-body",
            "data-shell-main=",
        )
        if any(signal in text for signal in shell_signals):
            return "possible-gap"
        return "outside"

    def _is_public_or_minimal(self, rel: str, extends: str | None) -> bool:
        if extends in {"marketing/base_marketing.html", "schools/marketing_base.html"}:
            return True
        if extends in {"base.html", "schools/tenant_minimal_shell.html"}:
            public_markers = (
                "auth/",
                "marketing/",
                "feedback/public",
                "home.html",
                "maintenance.html",
                "accounts/claim_invite",
                "accounts/guardian_setup",
                "accounts/mfa_verify",
                "accounts/operator_invite_accept",
                "accounts/owner_onboarding",
                "accounts/tenant_staff_invite_accept",
                "marketplace/public",
                "marketplace/publisher_signup",
                "schoolops/lost_belongings_lookup",
                "schools/404_tenant",
                "schools/accept_invite",
                "schools/developer",
                "schools/docs",
                "schools/find",
                "schools/frozen",
                "schools/global_login",
                "schools/onboard",
                "schools/public",
                "schools/resend",
                "schools/signup",
                "schools/tenant_setup",
                "schools/verify",
            )
            return rel.startswith(public_markers) or rel in public_markers
        if extends == "control_plane_skeleton.html" and rel.startswith("auth/"):
            return True
        return False

    def _first_match(self, pattern: re.Pattern, text: str) -> str | None:
        match = pattern.search(text)
        return match.group(1) if match else None

    def _summarize(self, report: dict) -> dict:
        shell_gaps = [
            row for row in report["shell_loads"].values() if not row["loads_edge_fit_css"]
        ]
        css_gaps = [
            {"check": key, "value": value}
            for key, value in report["css_contract"].items()
            if key != "path" and value is not True
        ]
        template_gaps = report["templates"]["candidate_shell_gaps"]
        manager_errors = report["menu_targets"]["manager"]["errors"]
        manager_url_gaps = report["menu_targets"]["manager"]["items_without_url"]
        tenant_url_gaps = report["menu_targets"]["tenant"]["unresolved"]
        gap_count = (
            len(shell_gaps)
            + len(css_gaps)
            + len(template_gaps)
            + len(manager_errors)
            + len(manager_url_gaps)
            + len(tenant_url_gaps)
        )
        return {
            "gap_count": gap_count,
            "shell_gap_count": len(shell_gaps),
            "css_contract_gap_count": len(css_gaps),
            "template_shell_gap_count": len(template_gaps),
            "manager_menu_gap_count": len(manager_errors) + len(manager_url_gaps),
            "tenant_menu_gap_count": len(tenant_url_gaps),
        }

    def _render_markdown(self, report: dict) -> str:
        summary = report["summary"]
        lines = [
            "# RunMyCampus Workspace Edge-Fit Audit",
            "",
            "Generated by `python manage.py audit_workspace_edge_fit`.",
            "",
            "## Summary",
            "",
            f"- Gap count: {summary['gap_count']}",
            f"- Shell CSS load gaps: {summary['shell_gap_count']}",
            f"- CSS contract gaps: {summary['css_contract_gap_count']}",
            f"- Candidate template shell gaps: {summary['template_shell_gap_count']}",
            f"- Manager menu gaps: {summary['manager_menu_gap_count']}",
            f"- Tenant menu gaps: {summary['tenant_menu_gap_count']}",
            "",
            "## Shell CSS Loads",
            "",
        ]
        for key, row in report["shell_loads"].items():
            status = "OK" if row["loads_edge_fit_css"] else "GAP"
            lines.append(f"- {status}: `{key}` -> `{row['path']}`")

        lines += ["", "## CSS Contract", ""]
        for key, value in report["css_contract"].items():
            if key == "path":
                continue
            status = "OK" if value is True else "GAP"
            lines.append(f"- {status}: `{key}`")

        lines += [
            "",
            "## Menu Coverage",
            "",
            f"- Manager groups: {report['menu_targets']['manager']['group_count']}",
            f"- Manager items: {report['menu_targets']['manager']['item_count']}",
            f"- Tenant URL names scanned: {report['menu_targets']['tenant']['url_name_count']}",
            "",
            "## Candidate Template Shell Gaps",
            "",
        ]
        gaps = report["templates"]["candidate_shell_gaps"]
        if not gaps:
            lines.append("- None found.")
        else:
            for row in gaps[:200]:
                lines.append(
                    f"- `{row['template']}` extends `{row.get('extends') or 'NONE'}`"
                )
            if len(gaps) > 200:
                lines.append(f"- Truncated: {len(gaps) - 200} more in JSON.")

        lines += [
            "",
            "## Tenant Menu URL Gaps",
            "",
        ]
        unresolved = report["menu_targets"]["tenant"]["unresolved"]
        if not unresolved:
            lines.append("- None found.")
        else:
            for row in unresolved:
                lines.append(f"- `{row['name']}` from {', '.join(row['sources'])}")

        manager_errors = report["menu_targets"]["manager"]["errors"]
        if manager_errors:
            lines += ["", "## Manager Menu Build Errors", ""]
            for error in manager_errors:
                lines.append(f"- {error}")

        lines.append("")
        return "\n".join(lines)

    def _render_gap_analysis(self, report: dict) -> str:
        summary = report["summary"]
        lines = [
            "# RunMyCampus Workspace Edge-Fit Gap Analysis",
            "",
            f"- Code-owned gaps found: {summary['gap_count']}",
            f"- Shell CSS load gaps: {summary['shell_gap_count']}",
            f"- CSS contract gaps: {summary['css_contract_gap_count']}",
            f"- Candidate template shell gaps: {summary['template_shell_gap_count']}",
            f"- Manager menu gaps: {summary['manager_menu_gap_count']}",
            f"- Tenant menu gaps: {summary['tenant_menu_gap_count']}",
            "",
            "## Covered Shells",
        ]
        for key, row in report["shell_loads"].items():
            status = "PASS" if row["loads_edge_fit_css"] else "GAP"
            lines.append(f"- {status}: `{key}` via `{row['path']}`")
        lines.extend(["", "## CSS Contract"])
        for key, value in report["css_contract"].items():
            if key == "path":
                continue
            status = "PASS" if value is True else "GAP"
            lines.append(f"- {status}: `{key}`")
        if summary["gap_count"] == 0:
            lines.extend(
                [
                    "",
                    "## Result",
                    "No code-owned gaps were found for the shared workspace edge-fit contract.",
                ]
            )
        return "\n".join(lines) + "\n"
