from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOTS = [
    ROOT / "templates" / "studio_os",
    ROOT / "templates" / "siteconfig",
    ROOT / "templates" / "admin",
    ROOT / "templates" / "accounts",
    ROOT / "templates" / "platform_runtime",
]
CSS_ROOTS = [ROOT / "static" / "css"]
OUT_JSON = ROOT / "docs" / "generated" / "stage_08_surface_rework_audit.json"
OUT_MD = ROOT / "docs" / "generated" / "stage_08_surface_rework_audit.md"


@dataclass
class Finding:
    severity: str
    category: str
    path: str
    line: int
    evidence: str
    recommendation: str


def iter_files(roots: list[Path], suffixes: tuple[str, ...]):
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in suffixes:
                yield path


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def line_no(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def strip_template_comments(text: str) -> str:
    text = re.sub(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", text, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def is_operator_only_template(path_str: str) -> bool:
    return path_str.startswith(
        (
            "templates/siteconfig/super/",
            "templates/admin/",
        )
    )


def is_text_reading_surface(path_str: str) -> bool:
    return any(
        token in path_str
        for token in (
            "/email/",
            "/emails/",
            "marketing",
            "privacy",
            "terms",
            "policy",
            "report_",
            "_report",
            "bulk_letters",
            "public_status",
            "evidence",
            "print",
            "pdf",
        )
    )


def add_findings_for_pattern(findings: list[Finding], path: Path, text: str, pattern: str, severity: str, category: str, recommendation: str):
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        if category == "inline_width_cap":
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.start())
            line_text = text[line_start : line_end if line_end != -1 else len(text)].lower()
            if "@media" in line_text and "max-width" in line_text:
                continue
            context = text[max(0, match.start() - 80) : match.start()].lower()
            if "@media" in context and "max-width" in context:
                continue
            value = match.group(0).split(":", 1)[-1].strip().lower()
            numeric = re.match(r"([0-9.]+)(rem|px|ch)", value)
            if numeric:
                amount = float(numeric.group(1))
                unit = numeric.group(2)
                if (unit == "rem" and amount <= 24) or (unit == "px" and amount <= 420) or (unit == "ch" and amount <= 60):
                    continue
        snippet = " ".join(match.group(0).strip().split())
        findings.append(Finding(severity, category, rel(path), line_no(text, match.start()), snippet[:220], recommendation))


def audit_templates() -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_files(TEMPLATE_ROOTS, (".html",)):
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        text = strip_template_comments(raw_text)
        path_str = rel(path)

        if "var/design-previews" in path_str:
            continue

        if "studio_os" in path_str and "mode_canvas" in path.name and "rmc-studio-workspace" not in text:
            findings.append(
                Finding(
                    "HIGH",
                    "studio_workspace_contract",
                    path_str,
                    1,
                    "Mode canvas lacks data-rmc-studio-workspace/rmc-studio-workspace markup.",
                    "Wrap the mode in the shared Studio workspace contract or explicitly document why it is full-canvas native.",
                )
            )

        if path_str.startswith("templates/studio_os") and "<iframe" in text and "data-rmc-live-preview-contract" not in text and "Open in full window" not in text:
            idx = text.find("<iframe")
            findings.append(
                Finding(
                    "MEDIUM",
                    "preview_recovery",
                    path_str,
                    line_no(text, idx),
                    "Iframe preview without visible fallback controls.",
                    "Add retry, modal/popout, or new-tab recovery controls for iframe-backed previews.",
                )
            )

        if (
            path_str.startswith(("templates/siteconfig", "templates/platform_runtime", "templates/accounts"))
            and not is_text_reading_surface(path_str)
            and "cp-evidence-page" not in text
        ):
            add_findings_for_pattern(
                findings,
                path,
                text,
                r'class="[^"]*(?<![\w-])container(?![\w-]|-fluid)[^"]*"',
                "MEDIUM",
                "narrow_container",
                "Use container-fluid or the tenant command workspace contract for operational/configuration pages.",
            )
            add_findings_for_pattern(
                findings,
                path,
                text,
                r"max-width\s*:\s*(?:var\(--rmc-report-measure\)|[0-9.]+(?:px|rem|ch))",
                "MEDIUM",
                "inline_width_cap",
                "Remove fixed max-width caps from work surfaces unless the page is a text/report reading surface.",
            )

        if (
            path_str.startswith(("templates/siteconfig", "templates/accounts", "templates/studio_os"))
            and not is_operator_only_template(path_str)
            and "/super/" in text
        ):
            idx = text.find("/super/")
            findings.append(
                Finding(
                    "CRITICAL",
                    "tenant_operator_boundary",
                    path_str,
                    line_no(text, idx),
                    "/super/ reference inside tenant-adjacent template.",
                    "Ensure tenant-host links resolve to tenant backend/configuration routes and manager-host links stay operator-only.",
                )
            )

        if "preview" in path.name.lower() and "<iframe" in text and "target=\"_blank\"" not in text and "data-rmc-preview" not in text:
            idx = text.find("<iframe")
            findings.append(
                Finding(
                    "MEDIUM",
                    "live_preview_fallback",
                    path_str,
                    line_no(text, idx),
                    "Preview iframe lacks fallback affordance markers.",
                    "Provide modal, popout, and new-tab preview options for blocked or cramped previews.",
                )
            )

    return findings


def audit_css() -> list[Finding]:
    findings: list[Finding] = []
    risk_tokens = (
        "admin-manager-shell",
        "admin-premium-shell",
        "change-form",
        "change-list",
        "rmc-admin-workspace",
        "rmc-live-preview",
        "theme-experience",
        "studio-os__canvas",
        "rmc-studio-workspace",
        "data-rmc-command-workspace",
        "reportcard",
        "dashboard-preview",
        "feature-control",
    )
    safe_cap_tokens = (
        "modal",
        "subtitle",
        "lede",
        "hero__copy",
        "header__command",
        "cp-brand",
        "empty-message",
        "empty-purpose",
        "action-checkbox",
        "#result_list th",
        "#result_list td",
        "filter",
        "select",
        "pill",
        "chip",
        "label",
        "notebook",
        "theme-experience-preview-wrap",
    )
    for path in iter_files(CSS_ROOTS, (".css",)):
        text = path.read_text(encoding="utf-8", errors="replace")
        path_str = rel(path)
        if path.name.endswith(".min.css"):
            continue
        for match in re.finditer(r"max-width\s*:\s*(?:[0-9.]+(?:px|rem|ch)|var\(--rmc-report-measure\))", text, flags=re.IGNORECASE):
            line = line_no(text, match.start())
            selector_start = text.rfind("}", 0, match.start()) + 1
            selector = text[selector_start : match.start()].split("{", 1)[0].strip().replace("\n", " ")
            selector_l = selector.lower()
            if any(token in selector for token in (".mkt-", ".auth", ".error-page", "marketing", "@media")):
                continue
            if not any(token in selector_l for token in risk_tokens):
                continue
            if any(token in selector_l for token in safe_cap_tokens):
                continue
            if "theme-experience-preview-wrap" in selector_l and "max-width: none !important" in text:
                continue
            findings.append(
                Finding(
                    "LOW",
                    "css_width_cap_review",
                    path_str,
                    line,
                    f"{selector[-120:]} {{ {match.group(0)} }}",
                    "Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.",
                )
            )
    return findings


def write_outputs(findings: list[Finding]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "audit": "stage_08_surface_rework",
        "summary": {
            "total": len(findings),
            "critical": sum(1 for f in findings if f.severity == "CRITICAL"),
            "high": sum(1 for f in findings if f.severity == "HIGH"),
            "medium": sum(1 for f in findings if f.severity == "MEDIUM"),
            "low": sum(1 for f in findings if f.severity == "LOW"),
        },
        "findings": [asdict(f) for f in findings],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Stage 08 Surface Rework Audit",
        "",
        f"- Total findings: {payload['summary']['total']}",
        f"- Critical: {payload['summary']['critical']}",
        f"- High: {payload['summary']['high']}",
        f"- Medium: {payload['summary']['medium']}",
        f"- Low: {payload['summary']['low']}",
        "",
        "## Findings",
        "",
    ]
    for finding in findings[:200]:
        lines.extend(
            [
                f"### {finding.severity} - {finding.category}",
                f"- Path: `{finding.path}:{finding.line}`",
                f"- Evidence: `{finding.evidence}`",
                f"- Recommendation: {finding.recommendation}",
                "",
            ]
        )
    if len(findings) > 200:
        lines.append(f"_Only the first 200 findings are shown. See `{rel(OUT_JSON)}` for the full audit._")
    OUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    findings = audit_templates() + audit_css()
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    findings.sort(key=lambda f: (severity_order.get(f.severity, 9), f.category, f.path, f.line))
    write_outputs(findings)
    print(json.dumps({"total": len(findings), "outputs": [rel(OUT_JSON), rel(OUT_MD)]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
