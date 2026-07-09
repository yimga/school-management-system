from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


SCAN_GLOBS = [
    "templates/studio_os/**/*.html",
    "templates/siteconfig/**/*.html",
    "templates/admin/**/*.html",
    "templates/accounts/**/*.html",
    "static/css/*.css",
    "static/js/*.js",
]


@dataclass
class Finding:
    path: str
    category: str
    severity: str
    message: str
    evidence: str


@dataclass
class ClosedItem:
    path: str
    category: str
    decision: str
    evidence: str


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def strip_django_comments(text: str) -> str:
    return re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", text, flags=re.DOTALL)


def is_manager_only_template(path: Path, text: str) -> bool:
    r = rel(path)
    if r.startswith("templates/siteconfig/super/"):
        return True
    if r in {
        "templates/admin/index_superadmin.html",
        "templates/admin/includes/admin_operator_steering_strip.html",
    }:
        return True
    head = text[:900]
    return "{% if is_manager_host %}" in head and "{% endif %}" in text


def is_inside_manager_guard(text: str, index: int) -> bool:
    """Return true when index is inside a simple manager-host template block."""
    prior = text[:index]
    manager_if = re.compile(
        r"\{%\s*if\s+(?:is_manager_host|request\.public_host_kind\s*==\s*['\"]manager['\"])\s*(?:and[^%]*)?%\}"
    )
    last_manager_if = max((match.start() for match in manager_if.finditer(prior)), default=-1)
    if last_manager_if < 0:
        return False
    last_endif = prior.rfind("{% endif %}")
    return last_manager_if > last_endif


def has_host_guard(text: str, index: int) -> bool:
    window = text[max(0, index - 600) : index + 600]
    return (
        "is_manager_host" in window
        or "request.public_host_kind == 'manager'" in window
        or is_inside_manager_guard(text, index)
    )


def shared_contracts() -> dict[str, bool]:
    workspace_css = read(ROOT / "static" / "css" / "tenant-command-workspace.css")
    studio_css = read(ROOT / "static" / "css" / "studio-workspace.css")
    studio_experience_css = read(ROOT / "static" / "css" / "studio-experience-mode.css")
    admin_css = read(ROOT / "static" / "css" / "rmc-admin-workspace-10x.css")
    workspace_template = read(ROOT / "templates" / "studio_os" / "components" / "workspace_layout.html")
    experience_canvas = read(ROOT / "templates" / "studio_os" / "partials" / "workspace" / "experience_inpage_canvas.html")
    theme_content = read(ROOT / "templates" / "siteconfig" / "partials" / "theme_colors_content.html")
    offline_queue = read(ROOT / "apps" / "platform_runtime" / "offline_queue.py")
    return {
        "command_workspace_full_width": (
            "[data-rmc-command-workspace].container" in workspace_css
            and "max-width: none !important" in workspace_css
            and "max-inline-size: none !important" in workspace_css
        ),
        "evidence_surface_full_width": (
            ".cp-evidence-page[data-cp-evidence-surface]" in workspace_css
            and ".cp-evidence-page[data-shell-surface]" in workspace_css
            and "max-inline-size: none !important" in workspace_css
        ),
        "studio_context_drawer": "rmc-studio-workspace__context-drawer" in studio_css,
        "studio_workspace_mode_marker": 'data-rmc-studio-mode="{{ workspace_mode }}"' in workspace_template,
        "studio_experience_inline_preview_suppressed": (
            "suppress_theme_inline_preview=1" in experience_canvas
            and "not suppress_theme_inline_preview" in theme_content
            and 'data-rmc-theme-content-surface="{{ theme_content_surface' in theme_content
        ),
        "studio_experience_dual_selector": (
            '[data-rmc-studio-mode="experience"]' in studio_experience_css
            and '[data-studio-workspace-mode="experience"]' in studio_experience_css
        ),
        "admin_dual_host_full_width": (
            "body:is(.admin-manager-shell, .admin-premium-shell).change-list #result_list" in admin_css
            and "width: max-content !important" in admin_css
            and "min-width: 100% !important" in admin_css
        ),
        "offline_enqueue_school_idempotency": (
            "except IntegrityError" in offline_queue
            and "OfflineAction.objects.filter(\n                school_id=school_id,\n                idempotency_key=key," in offline_queue
        ),
    }


def scan_file(path: Path, contracts: dict[str, bool]) -> tuple[list[Finding], list[ClosedItem]]:
    raw_text = read(path)
    text = strip_django_comments(raw_text)
    r = rel(path)
    findings: list[Finding] = []
    closed: list[ClosedItem] = []

    if path.suffix == ".html":
        if "data-rmc-live-preview-contract" in text:
            required = {
                "retry": "data-rmc-preview-retry",
                "modal": "data-rmc-preview-modal",
                "popout": "data-rmc-preview-popout",
                "new_tab": "data-rmc-preview-new-tab",
                "frame": "data-rmc-preview-frame",
            }
            missing = [name for name, needle in required.items() if needle not in text]
            if missing:
                findings.append(
                    Finding(
                        r,
                        "live_preview",
                        "blocking",
                        "Live preview contract is missing required fallback controls.",
                        ", ".join(missing),
                    )
                )

        if "workspace_context_template" in text and "context-drawer" not in text and "workspace_layout.html" not in r:
            if contracts["studio_context_drawer"] and "studio_os/components/workspace_layout.html" in text:
                closed.append(
                    ClosedItem(
                        r,
                        "space_intelligence",
                        "CLOSED_BY_SHARED_STUDIO_WORKSPACE",
                        "workspace_layout.html includes context drawer fallback",
                    )
                )
            else:
                findings.append(
                    Finding(
                        r,
                        "space_intelligence",
                        "watch",
                        "Workspace context is used; verify it inherits the shared drawer fallback.",
                        "workspace_context_template",
                    )
                )

        if re.search(r"class=[\"'][^\"']*\bcontainer\b", text) and "data-rmc-command-workspace" in text:
            if contracts["command_workspace_full_width"]:
                closed.append(
                    ClosedItem(
                        r,
                        "full_width",
                        "CLOSED_BY_COMMAND_WORKSPACE_CSS",
                        "tenant-command-workspace.css removes container max-width and max-inline-size",
                    )
                )
            else:
                findings.append(
                    Finding(
                        r,
                        "full_width",
                        "watch",
                        "Command workspace contains a narrow container class; confirm CSS removes max-width.",
                        "container + data-rmc-command-workspace",
                    )
                )

        has_report_measure = "--rmc-report-measure" in text or re.search(
            r"max-width\s*:\s*(var\(--rmc-report-measure\)|\d+rem|\d+px)", text
        )
        if has_report_measure:
            evidence_surface = (
                "cp-evidence-page" in text
                and (
                    "data-cp-evidence-surface" in text
                    or "data-rmc-operator-evidence-surface" in text
                    or "data-shell-surface" in text
                )
            )
            intentionally_measured = (
                "/email/" in r
                or r.endswith("public_status.html")
                or r.endswith("public_status_history.html")
                or r in {
                    "templates/accounts/notification_preferences.html",
                    "templates/accounts/profile.html",
                    "templates/accounts/backend_dashboard.html",
                    "templates/admin/index.html",
                    "templates/siteconfig/partials/mock_reportcard_preview.html",
                    "templates/siteconfig/partials/theme_colors_page_body.html",
                    "templates/siteconfig/school_group_hierarchy.html",
                }
            )
            if evidence_surface and contracts["evidence_surface_full_width"]:
                closed.append(
                    ClosedItem(
                        r,
                        "narrow_surface",
                        "CLOSED_BY_EVIDENCE_SURFACE_CSS",
                        "tenant-command-workspace.css forces evidence surfaces full width",
                    )
                )
            elif intentionally_measured:
                closed.append(
                    ClosedItem(
                        r,
                        "narrow_surface",
                        "ACCEPTED_READABILITY_MEASURE",
                        "not a Studio/configuration workbench surface",
                    )
                )
            else:
                findings.append(
                    Finding(
                        r,
                        "narrow_surface",
                        "watch",
                        "Template has an inline max-width/report measure cap that may be wrong for configuration workspaces.",
                        "max-width/report-measure",
                    )
                )

        for match in re.finditer(r"('|\")?super:", text):
            if not is_manager_only_template(path, text) and not has_host_guard(text, match.start()):
                findings.append(
                    Finding(
                        r,
                        "tenant_operator_boundary",
                        "blocking",
                        "Potential unguarded operator route reference in a template that may render on tenant host.",
                        text[max(0, match.start() - 80) : match.start() + 120].replace("\n", " "),
                    )
                )

        if ('href="/super/' in text or "href='/super/" in text) and not is_manager_only_template(path, text):
            for match in re.finditer(r"href=(\"|')/super/", text):
                if not has_host_guard(text, match.start()):
                    findings.append(
                        Finding(
                            r,
                            "tenant_operator_boundary",
                            "blocking",
                            "Potential hard-coded /super/ link without nearby manager-host guard.",
                            text[max(0, match.start() - 80) : match.start() + 120].replace("\n", " "),
                        )
                    )

    if path.suffix == ".css":
        if "body.admin-manager-shell" in text and "admin-premium-shell" not in text and "workspace" in r:
            findings.append(
                Finding(
                    r,
                    "tenant_admin_parity",
                    "watch",
                    "Admin workspace CSS references manager shell but not tenant premium shell.",
                    "body.admin-manager-shell",
                )
            )

        if re.search(r"max-width\s*:\s*(720px|940px|1120px|1200px)", text) and "configuration" in r:
            findings.append(
                Finding(
                    r,
                    "full_width",
                    "watch",
                    "Configuration-related CSS contains fixed max-width; verify it is not constraining work surfaces.",
                    "fixed max-width",
                )
            )

    if path.suffix == ".js" and "data-rmc-live-preview-contract" in text:
        for required in ("data-rmc-preview-modal", "data-rmc-preview-popout", "data-rmc-preview-new-tab"):
            if required not in text:
                findings.append(
                    Finding(
                        r,
                        "live_preview",
                        "blocking",
                        "Live preview JS does not wire one required fallback action.",
                        required,
                    )
                )

    return findings, closed


def main() -> int:
    files: list[Path] = []
    for glob in SCAN_GLOBS:
        files.extend(ROOT.glob(glob))
    files = sorted(set(p for p in files if p.is_file()))

    contracts = shared_contracts()
    findings: list[Finding] = []
    closed_items: list[ClosedItem] = []
    for name, ok in contracts.items():
        if not ok:
            findings.append(
                Finding(
                    "shared_contracts",
                    "deployment_contract",
                    "blocking",
                    "Required Stage 08 deployment contract is not satisfied.",
                    name,
                )
            )
    for path in files:
        file_findings, file_closed = scan_file(path, contracts)
        findings.extend(file_findings)
        closed_items.extend(file_closed)

    severity_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for item in findings:
        severity_counts[item.severity] = severity_counts.get(item.severity, 0) + 1
        category_counts[item.category] = category_counts.get(item.category, 0) + 1

    out = {
        "scanned_files": len(files),
        "finding_count": len(findings),
        "severity_counts": severity_counts,
        "category_counts": category_counts,
        "contracts": contracts,
        "findings": [asdict(item) for item in findings],
        "closed_items": [asdict(item) for item in closed_items],
    }

    generated = ROOT / "docs" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "stage_08_layout_gap_analysis.json").write_text(
        json.dumps(out, indent=2, sort_keys=True), encoding="utf-8"
    )

    lines = [
        "# Stage 08 Layout Gap Analysis",
        "",
        f"- Scanned files: {len(files)}",
        f"- Findings: {len(findings)}",
        f"- Severity counts: {severity_counts}",
        f"- Category counts: {category_counts}",
        f"- Closed by contract/decision: {len(closed_items)}",
        "",
        "## Contracts",
        "",
        *(f"- `{name}`: {value}" for name, value in contracts.items()),
        "",
        "## Findings",
        "",
    ]
    if findings:
        for item in findings:
            lines.append(f"- **{item.severity.upper()}** `{item.category}` `{item.path}` - {item.message} ({item.evidence})")
    else:
        lines.append("- No findings.")
    if closed_items:
        lines.extend(["", "## Closed Items", ""])
        for item in closed_items:
            lines.append(f"- **{item.decision}** `{item.category}` `{item.path}` - {item.evidence}")
    (generated / "stage_08_layout_gap_analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"scanned_files": len(files), "finding_count": len(findings), "severity_counts": severity_counts}, sort_keys=True))
    return 1 if severity_counts.get("blocking") else 0


if __name__ == "__main__":
    raise SystemExit(main())
