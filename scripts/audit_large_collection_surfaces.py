from __future__ import annotations

import ast
import json
import re
import sys
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


_CONTROL_ID_RE = re.compile(r'\bid\s*=\s*"(?P<value>[^"]*)"', re.IGNORECASE)
_FORM_ACTION_RE = re.compile(r'\baction\s*=\s*"(?P<value>[^"]*)"', re.IGNORECASE)
_HIDDEN_VALUE_RE = re.compile(
    r'<input\b[^>]*type\s*=\s*"hidden"[^>]*\bvalue\s*=\s*"(?P<value>[^"]*)"',
    re.IGNORECASE,
)
_TEMPLATE_VAR_RE = re.compile(r"{{.*?}}", re.DOTALL)
_TEMPLATE_STRING_RE = re.compile(r"""["'](?P<path>[A-Za-z0-9_./-]+\.html)["']""")
_SLICE_CLAIM_RE = re.compile(r"slice", re.IGNORECASE)

_TEMPLATE_REF_INDEX: dict[str, list[Path]] | None = None
_VIEW_BOUND_CACHE: dict[str, str | None] = {}


def _row_interaction_is_individuated(tbody_html: str) -> bool:
    """Does every repeated control carry a per-row identity?

    The risk this gate states for a control inside a repeated row is concrete:
    duplicate ids, an ambiguous submit target, and a screen reader announcing one
    control N times. A control whose `id` interpolates the row --
    `id="mtss-tier-{{ c.student_id }}"` -- has none of them. The id is unique, a
    `<label for>` pointing at it resolves to exactly one control, and a form that
    carries the row in its action or in a hidden field is unambiguous about which
    row it means.

    So this is EVIDENCE, read off the markup, that the stated risk does not land
    here -- rather than a comment promising that it does not.

    Deliberately strict: every control and every editing form must qualify. One
    un-individuated checkbox among good controls is still a control a screen
    reader cannot tell from the others, and that is exactly the defect writing
    this found in `siteconfig/sync_conflicts.html`.
    """
    controls = _editing_controls(tbody_html)
    forms = _editing_forms(tbody_html)
    if not controls and not forms:
        return False
    for control in controls:
        found = _CONTROL_ID_RE.search(control)
        if not found or not _TEMPLATE_VAR_RE.search(found.group("value")):
            return False
    for form in forms:
        head = form[: form.find(">") + 1]
        action = _FORM_ACTION_RE.search(head)
        if action and _TEMPLATE_VAR_RE.search(action.group("value")):
            continue
        if any(_TEMPLATE_VAR_RE.search(v) for v in _HIDDEN_VALUE_RE.findall(form)):
            continue
        return False
    return True


def _template_reference_index() -> dict[str, list[Path]]:
    """Map a template path to the python modules that name it as a string.

    Resolved by the literal template string appearing in a module -- a `render()`
    call, a `template_name` -- and NOT through the urlconf. The urlconf here is
    host-split (`config.urls` is a dev superset; a real tenant is served
    `config.tenant_urls`), so resolving a route to decide which view serves a
    template gives a different answer depending on which urlconf you ask, and the
    answer for `testserver` is not the answer for a tenant. The literal string is
    the same fact from every host.
    """
    global _TEMPLATE_REF_INDEX
    if _TEMPLATE_REF_INDEX is not None:
        return _TEMPLATE_REF_INDEX
    index: dict[str, list[Path]] = {}
    for py_path in (ROOT / "apps").rglob("*.py"):
        try:
            text = py_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _TEMPLATE_STRING_RE.finditer(text):
            index.setdefault(match.group("path"), []).append(py_path)
    _TEMPLATE_REF_INDEX = index
    return index


def _view_bound_evidence(template_rel: str) -> str | None:
    """A real row bound in the scope that renders this template, or None.

    A bound is a bound whether the TEMPLATE shows a pager or the VIEW caps the
    queryset, and most of them here are in the view. Demanding a template-side
    pager made 77 tables read as unbounded when they are capped one frame up,
    and that pressure is exactly why the old rule reached for
    `data-rmc-scroll-policy="paginate"` as an escape hatch. Look where the bound
    actually lives instead of asking the template to re-declare it.

    Counts as a bound: a slice with an upper bound, a `Paginator`, or a ListView
    `paginate_by`.

    Scoped to the function or class that NAMES the template, never the whole
    module: `views_teacher.py` runs to thousands of lines and slices things all
    over, so a module-wide search would accept any slice anywhere as proof of a
    bound on this table -- the same "asserts the word" mistake one level up.
    """
    if template_rel in _VIEW_BOUND_CACHE:
        return _VIEW_BOUND_CACHE[template_rel]
    result: str | None = None
    for py_path in _template_reference_index().get(template_rel, []):
        try:
            source = py_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (OSError, SyntaxError, ValueError):
            continue
        for scope in ast.walk(tree):
            if not isinstance(
                scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            names_template = any(
                isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and child.value == template_rel
                for child in ast.walk(scope)
            )
            if not names_template:
                continue
            where = "%s in %s" % (py_path.relative_to(ROOT).as_posix(), scope.name)
            for node in ast.walk(scope):
                if (
                    isinstance(node, ast.Subscript)
                    and isinstance(node.slice, ast.Slice)
                    and node.slice.upper is not None
                ):
                    try:
                        rendered = ast.unparse(node)[:70]
                    except Exception:  # noqa: BLE001 - the detail is optional
                        rendered = "<slice>"
                    result = "%s: slice %s" % (where, rendered)
                    break
                if (
                    isinstance(node, ast.Call)
                    and isinstance(getattr(node, "func", None), ast.Name)
                    and node.func.id == "Paginator"
                ):
                    result = "%s: Paginator(...)" % where
                    break
                if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "paginate_by"
                    for target in node.targets
                ):
                    result = "%s: paginate_by" % where
                    break
            if result is not None:
                break
        if result is not None:
            break
    _VIEW_BOUND_CACHE[template_rel] = result
    return result


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
    template_rel = path.relative_to(TEMPLATES).as_posix()
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
    # Two different ways a repeated control can be safe, and they are not the
    # same claim. Disclosure HIDES the control behind a click. Individuation
    # leaves it in the open and shows the stated risk cannot land on it.
    individuated = _row_interaction_is_individuated(tbody)
    interaction_is_safe = has_disclosed_row_form or individuated
    row_interaction_controlled = interaction_is_safe or (
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
    # Where the bound really is. Checked, not declared: a marker is a sentence in
    # a template and the cap it names lives in a view nobody edits at the same
    # time, so the two drift apart in silence and the template goes on asserting
    # a bound that was deleted.
    slice_evidence = _view_bound_evidence(template_rel)
    bound_reason = _bound_declaration(file_text)
    # A declaration is only worth its evidence. One that names a slice the view
    # does not have is not a bound, it is a claim -- and it is reported as one.
    claims_slice = bound_reason is not None and _SLICE_CLAIM_RE.search(bound_reason)
    unverified_claim = bool(claims_slice) and slice_evidence is None
    if unverified_claim:
        bound_reason = None
    has_pagination = (
        has_real_pagination or slice_evidence is not None or bound_reason is not None
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
        if interaction_is_safe:
            score += 0
        elif undisclosed_forms:
            score += 4
            reasons.append(f"{undisclosed_forms} form(s) inside repeated rows")
        else:
            score += 1
            reasons.append(f"{row_form_count} disclosure-contained row form(s)")

    if row_input_count >= 2:
        if interaction_is_safe:
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

    # `data-rmc-scroll-policy="paginate"` used to excuse a missing bound. It
    # drives static/js/rmc-tenant-surface-paginator.js, which is a long-page
    # SECTION navigator: it groups top-level sections into pages and marks a
    # big table as an oversize scroll zone. It never removes a row. Accepting
    # it meant a one-line template edit turned this gate green and bounded
    # nothing, which is the cheapest false green in the file.
    if not has_pagination:
        score += 2
        reasons.append("no pagination and no verified row bound")
    if unverified_claim:
        reasons.append(
            "bound declaration claims a view-side slice, but no slice was "
            "found in the scope that renders this template"
        )

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
        "bound_slice_evidence": slice_evidence,
        "row_controls_individuated": individuated,
        "has_paginate_scroll_policy": has_scroll_policy,
        "reasons": reasons,
        "recommendations": recommendations,
    }


BASELINE_PATH = ROOT / "var" / "large-collection-unbounded-baseline.json"


def _counts_by_file(findings: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding["file"]] = counts.get(finding["file"], 0) + 1
    return counts


def _compare_to_baseline(findings: list[dict]) -> int:
    """Burndown ratchet: this list may only shrink, and it must stay exact.

    Be clear about what this file is, because this repo has two other baselines
    and they are a different thing. `companion-server-contract` and
    `wizard-label-token` record DECISIONS -- a surface deliberately not mounted,
    an i18n architecture not yet chosen. This one records DEBT: 37 tables that
    render an unbounded collection, every one of them a real defect nobody has
    fixed yet.

    It exists because the alternative was worse. Before this the gate had zero
    runners, so a thirty-eighth unbounded table could land unnoticed. A ratchet
    that can only tighten blocks that, and it keeps the number in front of
    people instead of in a report nothing reads.

    Exact counts on purpose. A file that improves from 3 to 2 FAILS until the
    number is corrected, so the tally always closes -- a baseline that silently
    over-states the debt makes "no regressions" easier to pass, which is how a
    ratchet quietly stops meaning anything.
    """
    if not BASELINE_PATH.is_file():
        print("FAIL: %s is missing; the ratchet cannot be evaluated."
              % BASELINE_PATH.relative_to(ROOT).as_posix())
        return 1
    try:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("FAIL: %s is unreadable: %s" % (BASELINE_PATH.name, exc))
        return 1

    listed: dict[str, int] = {}
    for entry in baseline.get("known_unbounded", []):
        name = entry.get("file")
        if not name:
            print("FAIL: a baseline entry has no `file`.")
            return 1
        if not str(entry.get("note") or "").strip():
            print("FAIL: baseline entry %s has no `note` saying what is unbounded."
                  % name)
            return 1
        listed[name] = int(entry.get("count") or 0)

    current = _counts_by_file(findings)
    problems: list[str] = []
    for name in sorted(set(current) | set(listed)):
        now, was = current.get(name, 0), listed.get(name, 0)
        if now == was:
            continue
        if name not in listed:
            problems.append(
                "  NEW      %s has %d unbounded table(s) and is not in the baseline"
                % (name, now))
        elif now == 0:
            problems.append(
                "  FIXED    %s is clean now -- delete its baseline entry" % name)
        elif now > was:
            problems.append(
                "  WORSE    %s has %d unbounded table(s), baseline records %d"
                % (name, now, was))
        else:
            problems.append(
                "  IMPROVED %s has %d unbounded table(s), baseline records %d "
                "-- correct the count" % (name, now, was))

    if problems:
        print("FAIL: the large-collection burndown baseline no longer matches "
              "the tree.")
        for line in problems:
            print(line)
        print("  Fix the table, or update %s in the same commit."
              % BASELINE_PATH.relative_to(ROOT).as_posix())
        return 1

    print("OK: %d known unbounded table(s) across %d file(s); none new, none stale."
          % (sum(listed.values()), len(listed)))
    # Anchored sentinel. The parent used to require LARGE_COLLECTION_SURFACE_PASS,
    # which only prints at zero findings -- so under a burndown it could never
    # pass. This one says the ratchet held, which is the property being enforced.
    print("LARGE_COLLECTION_RATCHET_OK")
    return 0


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
    summary["remediation_status"] = "PASS" if len(findings) == 0 else "PARTIAL"
    # No generated_at, and write_BYTES with a literal newline. This file is
    # tracked, and .gitattributes pins docs/generated/*.json to eol=lf -- but
    # Path.write_text is TEXT mode and emitted CRLF on Windows, so every run
    # left the file "modified" with byte-identical content and `git rebase`
    # refused with "You have unstaged changes". A wall-clock timestamp did the
    # same damage honestly. This gate runs in the pre-push hook now, so a run
    # that dirties the tree breaks the very push that ran it.
    REPORT_PATH.write_bytes(
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )

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

    # Without --compare this stays a report that exits 0, because its parent
    # `verify_cp_v8_operator_closeout` reads the JSON and decides for itself.
    # With --compare it is a gate something can actually run.
    if "--compare" in sys.argv[1:]:
        return _compare_to_baseline(findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
