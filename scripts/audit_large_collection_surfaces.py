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
# A REAL paginator, as opposed to the word "pagination" appearing somewhere in
# the file. The bare substring matched an aria-label ("Chain pagination"), a print
# stylesheet href (rmc-pagination-grammar.css) and Django's own get_pagination_key
# -- none of which bound a single row.
PAGINATION_CONTEXT_RE = re.compile(r"\b(?:page_obj|is_paginated|paginator)\b")
PAGINATION_INCLUDE_RE = re.compile(r"{%\s*include\s+[\"'][^\"']*pagination[^\"']*[\"']")

# Not every paginated page uses Django's ListView names. token_rotation_chain.html
# slices to PAGE_SIZE in the view and hands the template page_num/page_count/
# has_prev/has_next -- real pagination that none of the names above match. What it
# does have, and what an aria-label or a stylesheet href never has, is a link that
# asks the SERVER for another page. That link is the behaviour; the word was not.
PAGE_QUERY_LINK_RE = re.compile(r"href=[\"'][^\"']*[?&]page=", re.IGNORECASE)

# `table-pagination-allow:` is verify_platform_ux_invariants.py's marker for "this
# table is bounded, and here is why". This gate was honouring it BY ACCIDENT --
# the marker contains the word "pagination", so the bare substring test passed.
# Honour it deliberately instead, and require the reason it is supposed to carry:
# a marker with no reason bounds nothing and explains nothing.
BOUND_DECLARATION_RE = re.compile(
    r"table-pagination-allow:\s*(?P<reason>[^\r\n]*?)\s*(?:{%\s*endcomment|--!?>|$)",
    re.IGNORECASE | re.MULTILINE,
)
MIN_BOUND_REASON_TOKENS = 2

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


#: An <input> a user can neither type into nor choose from. A hidden field
#: carries context; a submit/button/reset IS the action. Neither is a control
#: that gets repeated N times down a table and announced N times to a screen
#: reader, which is the entire risk this scanner exists to catch.
_NON_EDITING_INPUT_RE = re.compile(
    r'type\s*=\s*["\']\s*(?:hidden|submit|button|reset|image)\s*["\']', re.IGNORECASE
)
_CONTROL_TAG_RE = re.compile(r"<(?:input|select|textarea)\b[^>]*>", re.IGNORECASE)
_FORM_BLOCK_RE = re.compile(r"<form\b[^>]*>.*?</form>", re.IGNORECASE | re.DOTALL)


_DETAILS_TOKEN_RE = re.compile(r"<details\b[^>]*>|</details\s*>", re.IGNORECASE)


def _bound_declaration(file_text: str) -> str | None:
    """The written reason from a `table-pagination-allow:` marker, if it has one.

    Returns None when the marker is absent OR present without a real reason, so a
    bare marker cannot silence the gate. Callers treat None as "not bounded".
    """
    for match in BOUND_DECLARATION_RE.finditer(file_text):
        reason = (match.group("reason") or "").strip()
        if len(reason.split()) >= MIN_BOUND_REASON_TOKENS:
            return reason
    return None


def _details_blocks(html: str) -> list[str]:
    """The body of every TOP-LEVEL <details>, matched by depth.

    The previous form was ``<details\b[^>]*>(?P<body>.*?)</details>`` -- non-greedy,
    so a NESTED <details> closed the outer match at the INNER element's tag and
    everything after it read as undisclosed.

    templates/siteconfig/module_market.html does exactly this: an outer
    "Actions" row disclosure containing an inner "Impact before activate" one, so
    both of its row forms -- genuinely behind the outer summary, which is the
    pattern this scanner asks for -- were counted as undisclosed and the template
    was reported for complying with the rule.

    Top-level only, so an inner block is never counted twice.
    """
    out: list[str] = []
    taken_to = 0
    for m in re.finditer(r"<details\b[^>]*>", html, re.IGNORECASE):
        if m.start() < taken_to:
            continue
        depth = 1
        pos = m.end()
        close_start = -1
        while depth:
            nxt = _DETAILS_TOKEN_RE.search(html, pos)
            if nxt is None:
                break
            pos = nxt.end()
            if nxt.group(0).lower().startswith("<details"):
                depth += 1
            else:
                depth -= 1
                if depth == 0:
                    close_start = nxt.start()
        if close_start >= 0:
            out.append(html[m.end() : close_start])
            taken_to = pos
    return out


def _editing_controls(html: str) -> list[str]:
    """Controls a user actually edits -- text fields, selects, textareas.

    Deliberately NOT hidden inputs and NOT submit buttons. Counting those was
    the scanner's central error: it reported "10 input/select controls inside
    repeated rows" for a row whose ten inputs were every one of them
    ``<input type="hidden">`` carrying a year id and a scope, with a single
    Generate button. There is nothing there to disclose.
    """
    out: list[str] = []
    for tag in _CONTROL_TAG_RE.findall(html):
        if tag[:6].lower() == "<input" and _NON_EDITING_INPUT_RE.search(tag):
            continue
        out.append(tag)
    return out


def _editing_forms(html: str) -> list[str]:
    """Row forms that EDIT something, as opposed to performing one action.

    A per-row ``<form method="post">{% csrf_token %}<button>Remove</button></form>``
    is not a defect -- it is the pattern Django and OWASP both require for a
    state-changing action, precisely because the alternative is a GET link that
    mutates. Measured on the live tree, SIX of this scanner's eleven findings
    were exactly that shape and carried no editable control at all.

    The rule's own stated risk does not reach them: those forms declare no id,
    so nothing collides; each carries its own explicit action or intent, so no
    submit target is ambiguous; and a screen reader announcing "Remove" once per
    row is correct, because there IS one Remove per row. Wrapping them in a
    disclosure would put a click in front of every destructive action and an
    "Actions" summary on every row -- worse for the same users the rule protects.

    What the rule is genuinely about is an EDITABLE control repeated down a
    table: N selects, N text fields, N id attributes, N announcements. Those
    still count.
    """
    return [f for f in _FORM_BLOCK_RE.findall(html) if _editing_controls(f)]


def _forms_inside_details(tbody_html: str) -> tuple[int, int]:
    """Count forms/inputs that live inside a <details> block (not merely same tbody)."""
    disclosed_forms = 0
    disclosed_inputs = 0
    for block in _details_blocks(tbody_html):
        # Same definitions as the totals above, or a disclosed editing form
        # would be subtracted from a count that never included it and the
        # difference would go negative into max(0, ...) and read as clean.
        disclosed_forms += len(_editing_forms(block))
        disclosed_inputs += len(_editing_controls(block))
    return disclosed_forms, disclosed_inputs


def _allow_marker_before_table(file_text: str, table_start: int) -> str | None:
    window = file_text[max(0, table_start - 400) : table_start]
    matches = list(ALLOW_MARKER_RE.finditer(window))
    if not matches:
        return None
    return matches[-1].group("reason").strip()


def _actions_inside_details(tbody_html: str) -> int:
    disclosed_actions = 0
    for block in _details_blocks(tbody_html):
        disclosed_actions += len(ACTION_RE.findall(block))
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
    # Count what the rule is actually about. `FORM_RE`/`INPUT_RE` over the whole
    # tbody counted every CSRF action button as a row form and every hidden
    # context field as a control -- see _editing_forms for the measurement.
    raw_row_forms = len(FORM_RE.findall(tbody))
    row_form_count = len(_editing_forms(tbody))
    row_input_count = len(_editing_controls(tbody))
    disclosed_forms, disclosed_inputs = _forms_inside_details(tbody)
    undisclosed_forms = max(0, row_form_count - disclosed_forms)
    undisclosed_inputs = max(0, row_input_count - disclosed_inputs)
    # Two DIFFERENT questions, and I conflated them on the first attempt.
    #
    # has_disclosed_row_form keeps its original meaning -- every EDITING form is
    # behind a <details> -- because it also suppresses the form/input scoring
    # below, and broadening it there wrongly silenced a table with two real
    # per-row selects (siteconfig/sync_conflicts) whose separate action buttons
    # happened to be undisclosed.
    #
    # row_interaction_controlled is the operational-table question: is this
    # table's row interaction under control at all? A table whose row forms are
    # ALL plain CSRF action buttons has nothing to disclose, which is at least as
    # good as having disclosed them -- and without this arm such a table LOSES
    # the credit it used to get, so seven tables that were doing the right thing
    # started scoring worse for it. Measured, not reasoned.
    has_disclosed_row_form = undisclosed_forms == 0 and row_form_count > 0
    row_interaction_controlled = has_disclosed_row_form or (
        raw_row_forms > 0 and row_form_count == 0
    )
    collection = loop_match.group("collection")
    has_real_pagination = (
        "components/pagination.html" in file_text
        or PAGINATION_INCLUDE_RE.search(file_text) is not None
        or PAGINATION_CONTEXT_RE.search(file_text) is not None
        or PAGE_QUERY_LINK_RE.search(file_text) is not None
        or collection.startswith("page_obj")
        or collection.startswith("page.")
    )
    bound_reason = _bound_declaration(file_text)
    has_pagination = has_real_pagination or bound_reason is not None
    has_density = (
        "density" in table_html
        or "table-sm" in table_html
        or "table-density" in table_html
        or "rmc-data-table" in table_html
        or "table-sticky-head" in table_html
    )
    has_scroll_policy = "data-rmc-scroll-policy=\"paginate\"" in file_text
    actions_header = re.search(r">\s*(Actions?|Action)\s*<", header_html, re.IGNORECASE) is not None
    operational_table = has_scroll_policy and has_density and (has_pagination or row_interaction_controlled)

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
        "has_real_pagination": has_real_pagination,
        "bound_declaration_reason": bound_reason,
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
    # Print EVERY finding. This was `findings[:10]` with nothing said about the
    # rest, so a run reporting 11 listed 10 and the eleventh existed only in the
    # JSON report. Its sole caller then kept the LAST 300 characters of this
    # output, and since the list is sorted by descending severity that tail was
    # the mildest end: three of eleven findings reached CI, and the eight worst
    # were the ones dropped. A tally that does not close is worse than no tally --
    # the header said 11, the body showed 10, and nobody subtracted.
    for finding in findings:
        reasons = "; ".join(finding["reasons"])
        print(f"  {finding['score']:02d} {finding['file']}:{finding['line']} [{finding['surface']}] {reasons}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
