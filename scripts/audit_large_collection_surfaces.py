from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
REPORT_PATH = ROOT / "docs" / "generated" / "large_collection_surface_audit.json"

ALLOW_MARKER_RE = re.compile(
    r"<!--\s*large-collection-allow:\s*(?P<reason>[^-]+(?:-[^-]+)*)\s*-->",
    re.IGNORECASE,
)
TABLE_RE = re.compile(r"<table\b(?P<table_attrs>[^>]*)>(?P<body>.*?)</table>", re.IGNORECASE | re.DOTALL)
THEAD_RE = re.compile(r"<thead\b[^>]*>(?P<body>.*?)</thead>", re.IGNORECASE | re.DOTALL)
TBODY_RE = re.compile(r"<tbody\b[^>]*>(?P<body>.*?)</tbody>", re.IGNORECASE | re.DOTALL)
FOR_RE = re.compile(r"{%\s*for\s+(?P<var>\w+)\s+in\s+(?P<collection>[\w.]+)")
ACTION_RE = re.compile(r"<(?:a|button)\b", re.IGNORECASE)
FORM_RE = re.compile(r"<form\b", re.IGNORECASE)
INPUT_RE = re.compile(r"<(?:input|select|textarea)\b", re.IGNORECASE)

SURFACE_PREFIXES = (
    ("operator", "schools/super_"),
    ("operator", "migration_cloud/operator/"),
    ("operator", "migration_cloud/super/"),
    ("operator", "apicenter/super/"),
    ("operator", "customersuccess/super_"),
    ("operator", "observability/"),
    ("operator", "orchestration/"),
    ("tenant", "accounts/"),
    ("tenant", "academics/"),
    ("tenant", "analytics/"),
    ("tenant", "finance/"),
    ("tenant", "feedback/"),
    ("tenant", "marketplace/"),
    ("tenant", "migration_cloud/customer/"),
    ("tenant", "parent/"),
    ("tenant", "people/"),
    ("tenant", "portal/"),
    ("tenant", "reports/"),
    ("tenant", "requests/"),
    ("tenant", "schoolops/"),
    ("tenant", "siteconfig/"),
    ("tenant", "teacher/"),
)


def surface_for(path: Path) -> str:
    rel = path.relative_to(TEMPLATES).as_posix()
    for surface, prefix in SURFACE_PREFIXES:
        if rel.startswith(prefix):
            return surface
    if rel.startswith("admin/"):
        return "admin"
    return "shared"


def line_for(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def compact_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _forms_inside_details(tbody_html: str) -> tuple[int, int]:
    """Count forms/inputs that live inside a <details> block (not merely same tbody)."""
    disclosed_forms = 0
    disclosed_inputs = 0
    for details_match in re.finditer(
        r"<details\b[^>]*>(?P<body>.*?)</details>",
        tbody_html,
        re.IGNORECASE | re.DOTALL,
    ):
        block = details_match.group("body")
        disclosed_forms += len(FORM_RE.findall(block))
        disclosed_inputs += len(INPUT_RE.findall(block))
    return disclosed_forms, disclosed_inputs


def _allow_marker_before_table(file_text: str, table_start: int) -> str | None:
    window = file_text[max(0, table_start - 400) : table_start]
    matches = list(ALLOW_MARKER_RE.finditer(window))
    if not matches:
        return None
    return matches[-1].group("reason").strip()


def _actions_inside_details(tbody_html: str) -> int:
    disclosed_actions = 0
    for details_match in re.finditer(
        r"<details\b[^>]*>(?P<body>.*?)</details>",
        tbody_html,
        re.IGNORECASE | re.DOTALL,
    ):
        disclosed_actions += len(ACTION_RE.findall(details_match.group("body")))
    return disclosed_actions


def score_table(file_text: str, table_match: re.Match[str], path: Path) -> dict | None:
    if _allow_marker_before_table(file_text, table_match.start()):
        return None

    table_html = table_match.group(0)
    thead_match = THEAD_RE.search(table_html)
    tbody_match = TBODY_RE.search(table_html)
    if not tbody_match:
        return None

    tbody = tbody_match.group("body")
    loop_match = FOR_RE.search(tbody)
    if not loop_match:
        return None

    header_html = thead_match.group("body") if thead_match else ""
    column_count = len(re.findall(r"<th\b", header_html, re.IGNORECASE))
    row_action_count = len(ACTION_RE.findall(tbody))
    row_action_count = max(0, row_action_count - _actions_inside_details(tbody))
    row_form_count = len(FORM_RE.findall(tbody))
    row_input_count = len(INPUT_RE.findall(tbody))
    disclosed_forms, disclosed_inputs = _forms_inside_details(tbody)
    undisclosed_forms = max(0, row_form_count - disclosed_forms)
    undisclosed_inputs = max(0, row_input_count - disclosed_inputs)
    has_disclosed_row_form = undisclosed_forms == 0 and row_form_count > 0
    collection = loop_match.group("collection")
    has_pagination = (
        "components/pagination.html" in file_text
        or "pagination" in file_text
        or collection.startswith("page_obj")
        or collection.startswith("page.")
    )
    has_density = (
        "density" in table_html
        or "table-sm" in table_html
        or "table-density" in table_html
        or "rmc-data-table" in table_html
        or "table-sticky-head" in table_html
    )
    has_scroll_policy = "data-rmc-scroll-policy=\"paginate\"" in file_text
    actions_header = re.search(r">\s*(Actions?|Action)\s*<", header_html, re.IGNORECASE) is not None
    operational_table = has_scroll_policy and has_density and (has_pagination or has_disclosed_row_form)

    reasons: list[str] = []
    score = 0

    if column_count >= 8:
        if operational_table:
            score += 1
            reasons.append(f"{column_count} columns (operational table — compact + paginated)")
        else:
            score += 3
            reasons.append(f"{column_count} columns")
    elif column_count >= 6:
        score += 1
        reasons.append(f"{column_count} columns")

    if row_form_count:
        if has_disclosed_row_form:
            score += 0
        elif undisclosed_forms:
            score += 4
            reasons.append(f"{undisclosed_forms} form(s) inside repeated rows")
        else:
            score += 1
            reasons.append(f"{row_form_count} disclosure-contained row form(s)")

    if row_input_count >= 2:
        if has_disclosed_row_form:
            score += 0
        elif undisclosed_inputs >= 2:
            score += 3
            reasons.append(f"{undisclosed_inputs} input/select controls inside repeated rows")
        elif undisclosed_inputs:
            score += 1
            reasons.append(f"{undisclosed_inputs} disclosed row input/select controls")

    if actions_header and row_action_count >= 3:
        score += 2
        reasons.append(f"{row_action_count} row actions under an Actions column")
    elif row_action_count >= 5:
        score += 1
        reasons.append(f"{row_action_count} row links/buttons")

    if not has_pagination and not has_scroll_policy:
        score += 2
        reasons.append("no pagination or paginate scroll policy found")

    if column_count >= 7 and not has_density:
        score += 1
        reasons.append("wide table without compact density marker")

    if operational_table and score <= 2:
        return None

    if score < 3:
        return None

    recommendations = []
    if undisclosed_forms or undisclosed_inputs:
        recommendations.append("Move row forms behind disclosure, drawer, or detail page.")
    if column_count >= 8:
        recommendations.append("Use compact density, sticky headers, and hide secondary fields behind row detail.")
    if not has_pagination:
        recommendations.append("Add pagination or virtualization for large collections.")
    if actions_header and row_action_count >= 3:
        recommendations.append("Collapse secondary actions into a menu or row expansion.")

    rel = path.relative_to(ROOT).as_posix()
    return {
        "file": rel,
        "line": line_for(file_text, table_match.start()),
        "surface": surface_for(path),
        "loop": compact_spaces(loop_match.group(0).strip("{% ")),
        "collection": loop_match.group("collection"),
        "score": score,
        "columns": column_count,
        "row_actions": row_action_count,
        "row_forms": row_form_count,
        "row_inputs": row_input_count,
        "has_pagination": has_pagination,
        "has_paginate_scroll_policy": has_scroll_policy,
        "reasons": reasons,
        "recommendations": recommendations,
    }


def main() -> int:
    findings = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = path.relative_to(TEMPLATES).as_posix()
        if rel.startswith(("admin_doc/", "registration/")):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for table_match in TABLE_RE.finditer(text):
            finding = score_table(text, table_match, path)
            if finding:
                findings.append(finding)

    findings.sort(key=lambda item: (-item["score"], item["surface"], item["file"], item["line"]))
    summary = {
        "finding_count": len(findings),
        "by_surface": {},
        "top_findings": findings[:25],
        "findings": findings,
    }
    for finding in findings:
        summary["by_surface"][finding["surface"]] = summary["by_surface"].get(finding["surface"], 0) + 1

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary["generated_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary["remediation_status"] = "PASS" if len(findings) == 0 else "PARTIAL"
    REPORT_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Large collection surface findings: {len(findings)}")
    if len(findings) == 0:
        print("LARGE_COLLECTION_SURFACE_PASS")
    for surface, count in sorted(summary["by_surface"].items()):
        print(f"  {surface}: {count}")
    for finding in findings[:10]:
        reasons = "; ".join(finding["reasons"])
        print(f"  {finding['score']:02d} {finding['file']}:{finding['line']} [{finding['surface']}] {reasons}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
